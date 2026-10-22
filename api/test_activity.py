# backend/test_activity.py
"""Activity diagram checks: parser and the layout rules from the PRD (ACT-*, GEN-*)."""

import itertools
import re
import xml.etree.ElementTree as ET

import pytest

from activity import Decision, Goto, parse_activity  # type: ignore
from test_sequence import _cells, _ends  # type: ignore
from uml import generate_uml, split_pages  # type: ignore

SAMPLE = '''\
=== Login
|Admin|
start
:Membuka halaman login;
|Sistem|
:Menampilkan form login;
|Admin|
:Mengisi email dan password;
:Klik tombol masuk;
|Sistem|
:Validasi data;
if (Data valid?) then (ya)
  :Redirect ke dashboard;
else (tidak)
  :Menampilkan pesan error;
  -> Mengisi email dan password
endif
stop

=== Tambah Donatur
|Admin|
start
:Mengisi form donatur dan donasi
yang panjang sampai dua baris;
|Sistem|
if (Input valid?) then (ya)
  fork
    :Menyimpan data donatur;
  fork again
    :Mencatat transaksi pemasukan;
  end fork
  :Menampilkan pesan sukses;
else (tidak)
  :Menampilkan pesan error validasi;
endif
|Admin|
:Melihat daftar donatur;
stop
'''


@pytest.fixture(scope='module')
def pages():
    result = generate_uml('activity', SAMPLE)
    assert result['errors'] == []
    return {d.get('name'): d.find('mxGraphModel/root') for d in ET.fromstring(result['xml']).findall('diagram')}


def _nodes(root):
    """Flow nodes (children of a lane) as (cell, absolute rect, lane name)."""
    cells, rects = _cells(root)
    lanes = {c.get('id'): c.get('value') for c in root if (c.get('style') or '').startswith('swimlane;html=1;startSize')}
    return [(c, rects[c.get('id')], lanes[c.get('parent')]) for c in root if c.get('parent') in lanes], rects, lanes


def _text(cell):
    return (cell.get('value') or '').replace('<br>', ' ')


def _polyline(edge, rects):
    start, end = _ends(edge, rects)
    points = [(float(p.get('x')), float(p.get('y'))) for p in edge.findall('mxGeometry/Array/mxPoint')]
    return [start, *points, end]


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parser_reads_lanes_steps_decisions_and_loops():
    model, errors = parse_activity('Login', split_pages(SAMPLE)[0][1])
    assert errors == []
    assert model.lanes == ['Admin', 'Sistem']
    decision = next(i for i in model.items if isinstance(i, Decision))
    assert (decision.condition, decision.lane) == ('Data valid?', 'Sistem')
    assert [b.label for b in decision.branches] == ['ya', 'tidak']
    assert isinstance(decision.branches[1].items[-1], Goto)


def test_parser_reports_bad_lines():
    lines = list(enumerate(['start', 'else', 'endif', 'end fork', 'apa ini', 'if (x) then (y)',
                            ':aksi tanpa titik koma', 'stop'], start=1))
    _, errors = parse_activity('x', lines)
    assert errors == [
        (2, "'else' tanpa 'if' yang dibuka"),
        (3, "'endif' tanpa 'if' yang dibuka"),
        (4, "'end fork' tanpa 'fork' yang dibuka"),
        (5, 'Baris tidak dikenali: "apa ini". Contoh aksi: :Mengisi data;'),
        (7, "aksi belum ditutup dengan ';'"),
        (6, "blok dibuka di sini belum ditutup dengan 'endif'"),
    ]


def test_loop_to_an_unknown_action_is_reported():
    result = generate_uml('activity', '=== A\nstart\n:Satu;\n-> Dua\n')
    assert result['errors'] == [{'page': 'A', 'line': 4, 'message': 'Aksi tujuan "Dua" tidak ditemukan'}]
    assert result['pages'] == ['A']


# ── Layout ───────────────────────────────────────────────────────────────────

def test_lanes_have_equal_size_and_nodes_stay_in_their_lane(pages):
    for root in pages.values():
        nodes, rects, lanes = _nodes(root)
        lane_rects = [rects[cid] for cid in lanes]
        assert len({(w, h) for _, _, w, h in lane_rects}) == 1                     # ACT-1
        for cell, (x, y, w, h), lane in nodes:
            lx, ly, lw, lh = next(rects[cid] for cid, name in lanes.items() if name == lane)
            assert lx < x and x + w < lx + lw and ly < y and y + h < ly + lh       # ACT-3
            assert all(v % 10 == 0 for v in (x, y, w, h))                          # GEN-2


def test_one_step_per_row_and_actions_centred(pages):
    nodes, rects, lanes = _nodes(pages['Login'])
    for (_, a, _), (_, b, _) in itertools.combinations(nodes, 2):
        assert a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]                          # ACT-4
    for cell, (x, y, w, h), lane in nodes:
        lx, _, lw, _ = next(rects[cid] for cid, name in lanes.items() if name == lane)
        assert x + w / 2 == lx + lw / 2


def test_lines_run_down_orthogonally_and_avoid_other_nodes(pages):
    for root in pages.values():
        nodes, rects, _ = _nodes(root)
        node_rects = {c.get('id'): r for c, r, _ in nodes}
        for edge in (c for c in root if c.get('edge') == '1'):
            points = _polyline(edge, rects)
            for p, q in zip(points, points[1:]):
                assert p[0] == q[0] or p[1] == q[1]                                # ACT-5
                for cid, (x, y, w, h) in node_rects.items():
                    if cid in (edge.get('source'), edge.get('target')):
                        continue
                    lo_x, hi_x = sorted((p[0], q[0]))
                    lo_y, hi_y = sorted((p[1], q[1]))
                    assert not (lo_x < x + w - 1 and hi_x > x + 1 and lo_y < y + h - 1 and hi_y > y + 1)
            looping_back = points[-1][1] < points[0][1]
            target = root.find(f".//mxCell[@id='{edge.get('target')}']")
            if looping_back:                                                       # ACT-7
                assert _text(target) == 'Mengisi email dan password'
                assert len(points) == 4                                            # out, up, back in


def test_decision_branches_are_labelled_and_meet_again(pages):
    root = pages['Login']
    labels = sorted(c.get('value') for c in root if (c.get('style') or '').startswith('edgeLabel'))
    assert labels == ['[tidak]', '[ya]']                                           # ACT-6
    # 'tidak' loops back, so only one branch goes on: no merge needed
    assert not [c for c in root if c.get('style') == 'rhombus;html=1;']

    root = pages['Tambah Donatur']     # both branches go on and meet again
    merges = [c for c in root if c.get('style') == 'rhombus;html=1;']
    assert len(merges) == 1
    incoming = [c for c in root if c.get('edge') == '1' and c.get('target') == merges[0].get('id')]
    assert len(incoming) == 2


def test_parallel_branches_sit_side_by_side(pages):
    nodes, _, _ = _nodes(pages['Tambah Donatur'])
    by_text = {_text(c): r for c, r, _ in nodes}
    a, b = by_text['Menyimpan data donatur'], by_text['Mencatat transaksi pemasukan']
    assert a[1] + a[3] / 2 == b[1] + b[3] / 2 and a[0] + a[2] < b[0]               # ACT-8
    bars = [r for c, r, _ in nodes if c.get('style').startswith('shape=line')]
    assert len(bars) == 2 and all(r[0] < a[0] and b[0] + b[2] < r[0] + r[2] for r in bars)
    # A long action wraps and grows taller instead of widening
    tall = by_text['Mengisi form donatur dan donasi yang panjang sampai dua baris']
    assert tall[2] == 180 and tall[3] > 40


def test_no_hardcoded_colours():
    assert not re.search(r'(fill|stroke|font)Color=#', generate_uml('activity', SAMPLE)['xml'])


def test_api_builds_activity_and_class_pages():
    from fastapi.testclient import TestClient  # type: ignore
    from index import app  # type: ignore

    client = TestClient(app)
    activity = client.post('/api/uml', json={'type': 'activity', 'text': SAMPLE}).json()
    assert activity['pages'] == ['Login', 'Tambah Donatur'] and activity['errors'] == []
    klass = client.post('/api/uml', json={'type': 'class', 'text': 'class A\nclass B\nA "1" -- "0..*" B\n'}).json()
    assert klass['pages'] == ['Diagram 1'] and klass['xml'].startswith('<mxfile')
