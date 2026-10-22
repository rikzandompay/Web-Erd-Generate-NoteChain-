# backend/test_sequence.py
"""Sequence diagram checks: parser, layout rules from the PRD (SEQ-*, GEN-*) and the /api/uml endpoint."""

import base64
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import pytest
from fastapi.testclient import TestClient  # type: ignore

from index import app  # type: ignore
from sequence import Fragment, parse_sequence  # type: ignore
from uml import generate_uml, split_pages  # type: ignore

SAMPLE = '''\
=== Edit Data Stok Bahan
actor Admin
boundary Sistem
control BahanController
entity Bahan

Admin -> Sistem : Mengklik Tombol Edit
Sistem --> Admin : Menampilkan Form Edit
Admin -> Sistem : Mengisi Data
Admin -> Sistem : Mengklik Tombol Simpan
Sistem -> BahanController : Menjalankan Function update()
BahanController -> Bahan : Menyimpan Data
Bahan --> BahanController : Data Berhasil Diperbarui
BahanController --> Sistem : Redirect ke Halaman Stok Bahan dengan Pesan Sukses
Sistem --> Admin : Menampilkan Pesan Sukses dan Data Stok Bahan yang Diperbarui

=== Login
actor Admin
Admin -> Sistem : Mengisi email dan password
Sistem -> AuthController : login(request)
AuthController -> AuthController : validasi input
loop maksimal 3 kali percobaan untuk setiap pengguna yang mencoba masuk
  AuthController -> User : cek kredensial
  User --> AuthController : hasil pencarian
  alt Data valid
    AuthController --> Sistem : redirect ke dashboard
  else Data tidak valid
    AuthController --> Sistem : pesan error
  end
end
Sistem --> Admin : Menampilkan halaman
'''


def _lines(text):
    return list(enumerate(text.splitlines(), start=1))


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parser_reads_participants_messages_and_fragments():
    model, errors = parse_sequence('Login', split_pages(SAMPLE)[1][1])
    assert errors == []
    assert [(p.name, p.kind) for p in model.participants] == [
        ('Admin', 'actor'), ('Sistem', 'participant'),
        ('AuthController', 'participant'), ('User', 'participant')]
    loop = model.events[3]
    assert isinstance(loop, Fragment) and loop.kind == 'loop'
    alt = loop.branches[0].events[2]
    assert alt.kind == 'alt'
    assert [b.condition for b in alt.branches] == ['Data valid', 'Data tidak valid']
    assert alt.branches[1].events[0].reply


def test_parser_reports_bad_lines_with_their_number():
    _, errors = parse_sequence('x', _lines('A -> B : ok\nini salah\nelse\nend\nloop terus\nB --> A : ok'))
    assert errors == [
        (2, 'Baris tidak dikenali: "ini salah". Contoh pesan: A -> B : label'),
        (3, "'else' hanya boleh di dalam 'alt'"),
        (4, "'end' tanpa 'alt', 'loop' atau 'opt' yang dibuka"),
        (5, "'loop' belum ditutup dengan 'end'"),
    ]


def test_a_broken_page_does_not_stop_the_others():
    result = generate_uml('sequence', '=== Rusak\nactor A\n=== Baik\nA -> B : halo\n')
    assert result['pages'] == ['Baik']
    assert result['errors'] == [
        {'page': 'Rusak', 'line': 2, 'message': 'Halaman "Rusak" belum berisi pesan (contoh: A -> B : label)'}]


# ── Layout (rendered XML) ────────────────────────────────────────────────────

def _style(cell):
    return dict(p.split('=', 1) for p in (cell.get('style') or '').split(';') if '=' in p)


@pytest.fixture(scope='module')
def pages():
    result = generate_uml('sequence', SAMPLE)
    assert result['errors'] == []
    return {d.get('name'): d.find('mxGraphModel/root') for d in ET.fromstring(result['xml']).findall('diagram')}


def _cells(root):
    cells = {c.get('id'): c for c in root}
    rects = {}

    def rect(cid):
        geo = cells[cid].find('mxGeometry')
        x, y, w, h = (float(geo.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
        parent = cells[cid].get('parent')
        if parent not in ('0', '1'):
            px, py, _, _ = rect(parent)
            x, y = x + px, y + py
        return x, y, w, h

    for cid, cell in cells.items():
        if cell.get('vertex') == '1' and cells.get(cell.get('parent'), cell).get('edge') != '1':
            rects[cid] = rect(cid)
    return cells, rects


def _messages(root):
    return [c for c in root if c.get('edge') == '1']


def _ends(edge, rects):
    s = {k: float(v) for k, v in _style(edge).items() if k[:4] in ('exit', 'entr') and 'Perimeter' not in k}
    sx, sy, sw, sh = rects[edge.get('source')]
    tx, ty, tw, th = rects[edge.get('target')]
    return ((sx + s['exitX'] * sw + s['exitDx'], sy + s['exitY'] * sh + s['exitDy']),
            (tx + s['entryX'] * tw + s['entryDx'], ty + s['entryY'] * th + s['entryDy']))


def test_pages_and_frames(pages):
    assert list(pages) == ['Edit Data Stok Bahan', 'Login']
    for name, root in pages.items():
        cells, rects = _cells(root)
        frame = next(c for c in root if c.get('value') == f'sd {name}')
        fx, fy, fw, fh = rects[frame.get('id')]
        for cid, (x, y, w, h) in rects.items():
            if cid != frame.get('id'):   # SEQ-1: everything inside the frame, ≥ 30px padding
                assert fx + 30 <= x and x + w <= fx + fw - 30 and fy + 30 <= y and y + h <= fy + fh - 30


def test_messages_are_numbered_horizontal_and_styled(pages):
    for root in pages.values():
        cells, rects = _cells(root)
        messages = _messages(root)
        numbers = [int(re.match(r'(\d+)\. ', m.get('value')).group(1)) for m in messages]
        assert numbers == list(range(1, len(messages) + 1))                     # SEQ-6
        for m in messages:
            style = _style(m)
            (ax, ay), (bx, by) = _ends(m, rects)
            points = m.findall("mxGeometry/Array/mxPoint")
            if m.get('source') == m.get('target') or points:                     # self-call loop
                assert len(points) == 2 and by - ay == 20
            else:
                assert ay == by                                                  # SEQ-8
            if style.get('dashed') == '1':
                assert style['endArrow'] == 'open'                               # SEQ-7
            else:
                assert style['endArrow'] == 'block'


def test_message_rows_are_evenly_spaced(pages):
    _, rects = _cells(pages['Edit Data Stok Bahan'])
    ys = [_ends(m, rects)[0][1] for m in _messages(pages['Edit Data Stok Bahan'])]
    wrapped = [m.get('value').count('<br>') for m in _messages(pages['Edit Data Stok Bahan'])]
    for (y1, y2), extra in zip(zip(ys, ys[1:]), wrapped[1:]):
        assert y2 - y1 == 40 + 20 * extra                                        # SEQ-6


def test_lifelines_in_one_row_far_enough_apart(pages):
    for root in pages.values():
        _, rects = _cells(root)
        lifelines = sorted((rects[c.get('id')] for c in root
                            if (c.get('style') or '').startswith('shape=umlLifeline')), key=lambda r: r[0])
        assert len({r[1] for r in lifelines}) == 1                               # SEQ-2
        centres = [x + w / 2 for x, _, w, _ in lifelines]
        assert all(b - a >= 160 for a, b in zip(centres, centres[1:]))           # SEQ-3
        for x, y, w, h in lifelines:
            assert x % 10 == 0 and y % 10 == 0 and w % 10 == 0 and h % 10 == 0  # GEN-2


def test_activation_bars_cover_every_message(pages):
    for root in pages.values():
        cells, rects = _cells(root)
        bars = {}
        for c in root:
            if (c.get('style') or '').startswith('html=1;points=[]'):
                bars.setdefault(cells[c.get('parent')].get('value'), []).append(rects[c.get('id')])
        actors = {c.get('value') for c in root if 'participant=umlActor' in (c.get('style') or '')}
        for m in _messages(root):
            for end, (x, y) in zip((m.get('source'), m.get('target')), _ends(m, rects)):
                cell = cells[end]
                owner = cells[cell.get('parent')].get('value') if cell.get('parent') != '1' else cell.get('value')
                if owner in actors:
                    assert owner not in bars                                     # SEQ-5
                else:
                    assert any(bx <= x <= bx + bw and by <= y <= by + bh for bx, by, bw, bh in bars[owner])


def test_long_labels_wrap_between_their_lifelines(pages):
    _, rects = _cells(pages['Edit Data Stok Bahan'])
    for m in _messages(pages['Edit Data Stok Bahan']):
        (ax, _), (bx, _) = _ends(m, rects)
        for line in m.get('value').split('<br>'):
            assert len(line) * 7 <= abs(bx - ax) + 10                            # SEQ-9


def test_no_hardcoded_colours():
    assert not re.search(r'(fill|stroke|font)Color=#', generate_uml('sequence', SAMPLE)['xml'])


# ── Open in draw.io link & API ───────────────────────────────────────────────

def test_open_link_unpacks_to_the_file():
    result = generate_uml('sequence', SAMPLE)
    packed = urllib.parse.unquote(result['open_url'].split('#R', 1)[1])
    unpacked = zlib.decompress(base64.b64decode(packed), -15).decode('ascii')
    assert urllib.parse.unquote(unpacked) == result['xml']


def test_api_returns_pages_and_errors():
    client = TestClient(app)
    response = client.post('/api/uml', json={'type': 'sequence', 'text': SAMPLE + '\nbaris aneh\n'})
    assert response.status_code == 200
    body = response.json()
    assert body['pages'] == ['Edit Data Stok Bahan', 'Login']
    assert body['errors'][0]['line'] == len(SAMPLE.splitlines()) + 2
    assert body['xml'].startswith('<mxfile')

    assert client.post('/api/uml', json={'type': 'gantt', 'text': 'x'}).status_code == 400
    assert client.post('/api/uml', json={'type': 'sequence', 'text': '  '}).status_code == 400
