# backend/test_usecase.py
"""Use case diagram: parser and the layout rules of PRD section 3.3."""

import itertools
import re
import xml.etree.ElementTree as ET

import pytest

from test_sequence import _cells, _ends  # type: ignore
from uml import generate_uml, split_pages  # type: ignore
from usecase import parse_usecase  # type: ignore

SAMPLE = '''\
=== Sistem Informasi Perpustakaan
system Perpustakaan {
  (Login Petugas)
  (Kelola Anggota)
  (Peminjaman Buku)
  (Pengembalian Buku)
  (Katalog Pencarian)
  (Hitung Denda)
  (Cetak Laporan)
}

actor Petugas
actor Anggota
actor Admin
actor SuperAdmin
actor Payment Gateway <<sekunder>>

Petugas --> (Login Petugas)
Petugas --> (Kelola Anggota)
Petugas --> (Peminjaman Buku)
Petugas --> (Pengembalian Buku)
Petugas --> (Cetak Laporan)

Anggota --> (Katalog Pencarian)
Anggota --> (Peminjaman Buku)
Payment Gateway --> (Hitung Denda)

(Peminjaman Buku) ..> (Login Petugas) : <<include>>
(Pengembalian Buku) ..> (Hitung Denda) : <<extend>>
Admin <|-- SuperAdmin
Admin <|-- Petugas
'''


@pytest.fixture(scope='module')
def root():
    result = generate_uml('usecase', SAMPLE)
    assert result['errors'] == [] and result['pages'] == ['Sistem Informasi Perpustakaan']
    return ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')


def _text(cell):
    """A cell's label as plain text: line breaks become spaces, bold tags go."""
    return ' '.join(re.sub(r'<[^>]+>', ' ', (cell.get('value') or '').replace('<br>', ' ')).split())


def _top(root):
    return [c for c in root if c.get('vertex') == '1' and c.get('parent') == '1']


def _usecases(root):
    return [c for c in root if (c.get('style') or '').startswith('ellipse')]


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parser_reads_system_actors_sides_and_relations():
    model, errors = parse_usecase('x', split_pages(SAMPLE)[0][1])
    assert errors == []
    assert model.system == 'Perpustakaan' and len(model.usecases) == 7
    assert model.actors['Petugas'] == 'L' and model.actors['Payment Gateway'] == 'R'
    kinds = [(r.kind, r.src, r.dst, r.label) for r in model.rels]
    assert ('dependency', '(Peminjaman Buku)', '(Login Petugas)', '<<include>>') in kinds
    assert ('generalization', 'SuperAdmin', 'Admin', '') in kinds       # child → parent, triangle at parent
    assert ('assoc', 'Petugas', '(Login Petugas)', '') in kinds


def test_actors_and_use_cases_used_in_relations_are_declared_implicitly():
    model, errors = parse_usecase('x', list(enumerate(['Kasir --> (Bayar Tagihan)'], start=1)))
    assert errors == [] and model.actors == {'Kasir': 'L'} and model.usecases == ['Bayar Tagihan']


def test_parser_reports_bad_lines_and_unclosed_system():
    _, errors = parse_usecase('x', list(enumerate(['system A {', '(Satu)', 'apa ini', 'system B {'], start=1)))
    assert errors == [(3, 'Baris tidak dikenali: "apa ini". Contoh: actor Admin, [Input], (Input Data), Admin --> (Input Data)'),
                      (4, 'Hanya satu blok system per halaman'),
                      (1, "blok system belum ditutup dengan '}'")]


def test_page_without_use_cases_is_reported():
    result = generate_uml('usecase', '=== Kosong\nactor Admin\n')
    assert result['pages'] == [] and 'belum berisi use case' in result['errors'][0]['message']


# ── Layout ───────────────────────────────────────────────────────────────────

def test_everything_on_the_10px_grid_and_nothing_overlaps(root):
    cells, rects = _cells(root)
    top = _top(root)
    for c in top:
        assert all(v % 10 == 0 for v in rects[c.get('id')])
    for a, b in itertools.combinations(top, 2):
        (ax, ay, aw, ah), (bx, by, bw, bh) = rects[a.get('id')], rects[b.get('id')]
        assert not (ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah), (a.get('value'), b.get('value'))


def test_boundary_holds_the_ellipses_and_actors_stand_outside(root):
    cells, rects = _cells(root)
    boundary = next(c for c in _top(root) if 'container=1' in c.get('style'))
    bx, by, bw, bh = rects[boundary.get('id')]
    assert _text(boundary) == 'Perpustakaan'
    for uc in _usecases(root):
        x, y, w, h = rects[uc.get('id')]
        assert uc.get('parent') == boundary.get('id') and bx < x and x + w < bx + bw and by < y and y + h < by + bh
    actors = {c.get('value'): rects[c.get('id')] for c in _top(root) if 'umlActor' in c.get('style')}
    assert actors['Petugas'][0] + actors['Petugas'][2] < bx                    # primary actors on the left
    assert actors['Payment Gateway'][0] > bx + bw                              # secondary on the right


def test_ellipses_are_stacked_with_even_gaps_and_a_shared_width(root):
    _, rects = _cells(root)
    boxes = sorted((rects[c.get('id')] for c in _usecases(root)), key=lambda r: r[1])
    assert len({(x, w) for x, _, w, _ in boxes}) == 1 and boxes[0][2] >= 140
    assert all(h >= 60 for *_, h in boxes)
    gaps = {nxt[1] - (cur[1] + cur[3]) for cur, nxt in zip(boxes, boxes[1:])}
    assert gaps == {30}                                                        # ≥ 30px between ellipses


def test_actors_sit_at_the_height_of_their_use_cases(root):
    cells, rects = _cells(root)
    by_text = {_text(c): rects[c.get('id')] for c in _usecases(root)}
    actor = next(rects[c.get('id')] for c in _top(root) if c.get('value') == 'Anggota')
    low, high = by_text['Katalog Pencarian'], by_text['Peminjaman Buku']
    assert min(high[1], low[1]) <= actor[1] + 30 <= max(high[1] + high[3], low[1] + low[3])


def test_no_line_runs_through_another_use_case(root):
    cells, rects = _cells(root)
    boxes = {c.get('id'): rects[c.get('id')] for c in _usecases(root)}
    for edge in (c for c in root if c.get('edge') == '1'):
        start, end = _ends(edge, rects)
        points = [start, *[(float(p.get('x')), float(p.get('y'))) for p in edge.findall('mxGeometry/Array/mxPoint')], end]
        for p, q in zip(points, points[1:]):
            for cid, (x, y, w, h) in boxes.items():
                if cid in (edge.get('source'), edge.get('target')):
                    continue
                lo_x, hi_x, lo_y, hi_y = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
                assert not (lo_x < x + w - 1 and hi_x > x + 1 and lo_y < y + h - 1 and hi_y > y + 1), (edge.get('id'), cid)


def test_relation_styles_and_labels(root):
    cells, _ = _cells(root)
    edges = [c for c in root if c.get('edge') == '1']
    names = {c.get('id'): _text(c) for c in cells.values() if c.get('vertex') == '1'}
    by_pair = {(names[e.get('source')], names[e.get('target')]): e for e in edges}
    include = by_pair[('Peminjaman Buku', 'Login Petugas')]
    assert include.get('value') == '&lt;&lt;include&gt;&gt;' and 'dashed=1' in include.get('style') and 'endArrow=open' in include.get('style')
    assert 'dashed=1' in by_pair[('Pengembalian Buku', 'Hitung Denda')].get('style')
    general = by_pair[('SuperAdmin', 'Admin')]
    assert 'endArrow=block' in general.get('style') and 'endFill=0' in general.get('style')
    plain = by_pair[('Petugas', 'Login Petugas')]
    assert 'endArrow=none' in plain.get('style') and 'dashed' not in plain.get('style')


def test_long_names_wrap_inside_the_ellipse():
    result = generate_uml('usecase', '=== T\n(Memverifikasi dan mengesahkan data kependudukan warga baru)\n(Cetak)\nWarga --> (Cetak)\n')
    root = ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')
    long = next(c for c in _usecases(root) if 'Memverifikasi' in c.get('value'))
    _, rects = _cells(root)
    assert '<br>' in long.get('value') and rects[long.get('id')][3] > 60 and rects[long.get('id')][2] <= 260


def test_many_actors_do_not_overlap_each_other():
    text = '=== T\n(A)\n' + ''.join(f'actor Aktor {i}\nAktor {i} --> (A)\n' for i in range(6))
    root = ET.fromstring(generate_uml('usecase', text)['xml']).find('diagram/mxGraphModel/root')
    _, rects = _cells(root)
    actors = sorted(rects[c.get('id')] for c in _top(root) if 'umlActor' in c.get('style'))
    assert len(actors) == 6 and all(b[1] - a[1] >= 100 for a, b in zip(actors, actors[1:]))


def test_no_hardcoded_colours():
    assert not re.search(r'(fill|stroke|font)Color=#', generate_uml('usecase', SAMPLE)['xml'])


def test_dependency_between_an_actor_and_a_use_case_is_drawn_straight():
    result = generate_uml('usecase', '=== T\n(Cetak)\n(Login)\nAdmin ..> (Cetak) : <<uses>>\n(Login) <|-- Admin\n')
    assert result['errors'] == [] and result['pages'] == ['T']
    root = ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')
    assert len([c for c in root if c.get('edge') == '1']) == 2
    assert not [p for c in root if c.get('edge') == '1' for p in c.findall('mxGeometry/Array/mxPoint')]


# ── Input → Proses → Output groups ───────────────────────────────────────────

IPO = """\
=== Sistem Donasi
system Sistem Donasi {
  [Input]
  (Input Data Donatur)
  (Input Data Donasi)
  [Proses]
  (Verifikasi Donasi)
  (Hitung Total Dana)
  [Output]
  (Cetak Laporan Donasi)
  (Lihat Riwayat Donasi)
}
actor Admin
actor Donatur
Admin --> (Input Data Donatur)
Admin --> (Verifikasi Donasi)
Admin --> (Hitung Total Dana)
Admin --> (Cetak Laporan Donasi)
Donatur --> (Input Data Donasi)
Donatur --> (Lihat Riwayat Donasi)
"""


def _ipo_root():
    result = generate_uml('usecase', IPO)
    assert result['errors'] == [] and result['pages'] == ['Sistem Donasi']
    return ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')


def test_groups_are_parsed_in_the_order_written():
    model, errors = parse_usecase('x', split_pages(IPO)[0][1])
    assert errors == [] and model.groups == ['Input', 'Proses', 'Output']
    assert model.group_of['Input Data Donasi'] == 'Input'
    assert model.group_of['Verifikasi Donasi'] == 'Proses'
    assert model.group_of['Lihat Riwayat Donasi'] == 'Output'


def test_groups_stack_input_then_process_then_output_under_their_labels():
    root = _ipo_root()
    _, rects = _cells(root)
    y = {_text(c): rects[c.get('id')][1] for c in root if c.get('vertex') == '1'}
    labels = [c for c in root if (c.get('style') or '').startswith('text;') and c.get('value') in ('Input', 'Proses', 'Output')]
    assert [c.get('value') for c in sorted(labels, key=lambda c: y[c.get('value')])] == ['Input', 'Proses', 'Output']
    assert y['Input'] < y['Input Data Donatur'] < y['Input Data Donasi'] < y['Proses'] < y['Verifikasi Donasi'] \
        < y['Hitung Total Dana'] < y['Output'] < y['Cetak Laporan Donasi'] < y['Lihat Riwayat Donasi']
    dividers = [c for c in root if (c.get('style') or '').startswith('line;')]
    assert len(dividers) == 2 and all('dashed=1' in c.get('style') for c in dividers)


def test_labels_and_dividers_stay_inside_the_ellipse_column():
    root = _ipo_root()
    _, rects = _cells(root)
    ellipse = next(rects[c.get('id')] for c in root if (c.get('style') or '').startswith('ellipse'))
    for c in root:
        if (c.get('style') or '').startswith(('line;', 'text;')):
            x, _, w, _ = rects[c.get('id')]
            assert x == ellipse[0] and w == ellipse[2]          # actor lines end at the ellipse edge, never cross these


def test_nothing_inside_the_box_overlaps():
    root = _ipo_root()
    _, rects = _cells(root)
    boundary = next(c.get('id') for c in root if 'container=1' in (c.get('style') or ''))
    inside = [rects[c.get('id')] for c in root if c.get('parent') == boundary]
    for a, b in itertools.combinations(inside, 2):
        assert not (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def test_without_groups_nothing_changes():
    root = ET.fromstring(generate_uml('usecase', SAMPLE)['xml']).find('diagram/mxGraphModel/root')
    assert not [c for c in root if (c.get('style') or '').startswith(('line;', 'text;html=1;align=left'))]


def test_use_cases_first_named_in_a_relation_are_not_put_in_a_group():
    model, errors = parse_usecase('x', list(enumerate(['system S {', '[Input]', '(A)', '}', 'Admin --> (B)'], start=1)))
    assert errors == [] and model.group_of == {'A': 'Input', 'B': ''}


# ── Left to right: primary actors → use cases → secondary actors (the ATM picture) ──

ATM = """\
=== Sistem ATM
system Bank ATM <<subsystem>> {
  (Perawatan Mesin)
  (Cek Saldo)
  (Perbaikan Mesin)
  (Setor Tunai)
  (Tarik Tunai)
  (Transfer Dana)
}
actor Nasabah
actor Teknisi ATM
actor Bank <<sekunder>>
Nasabah --> (Cek Saldo)
Nasabah --> (Setor Tunai)
Nasabah --> (Tarik Tunai)
Nasabah --> (Transfer Dana)
Teknisi ATM --> (Perawatan Mesin)
Teknisi ATM --> (Perbaikan Mesin)
Bank --> (Cek Saldo)
Bank --> (Setor Tunai)
Bank --> (Tarik Tunai)
Bank --> (Transfer Dana)
"""


def _atm():
    result = generate_uml('usecase', ATM)
    assert result['errors'] == []
    root = ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')
    _, rects = _cells(root)
    return root, rects


def test_system_title_shows_the_stereotype_above_the_bold_name_at_the_left():
    root, _ = _atm()
    boundary = next(c for c in root if 'container=1' in (c.get('style') or ''))
    assert boundary.get('value') == '&laquo;subsystem&raquo;<br><b>Bank ATM</b>'
    assert 'align=left' in boundary.get('style')


def test_use_cases_are_grouped_by_the_actor_that_uses_them():
    root, rects = _atm()
    order = [_text(c) for c in sorted(_usecases(root), key=lambda c: rects[c.get('id')][1])]
    # written mixed up, drawn as the nasabah's four and then the technician's two
    assert order == ['Cek Saldo', 'Setor Tunai', 'Tarik Tunai', 'Transfer Dana', 'Perawatan Mesin', 'Perbaikan Mesin']


def test_input_left_process_middle_output_right():
    root, rects = _atm()
    boundary = next(c for c in root if 'container=1' in (c.get('style') or ''))
    bx, _, bw, _ = rects[boundary.get('id')]
    actor = {c.get('value'): rects[c.get('id')] for c in _top(root) if 'umlActor' in c.get('style')}
    assert actor['Nasabah'][0] < bx and actor['Teknisi ATM'][0] < bx
    assert actor['Bank'][0] > bx + bw
    # each actor at the height of its own use cases: the nasabah above the technician, the bank beside the nasabah's
    assert actor['Nasabah'][1] < actor['Teknisi ATM'][1]
    assert abs(actor['Bank'][1] - actor['Nasabah'][1]) <= 10


def test_lines_from_different_actors_do_not_cross():
    root, rects = _atm()
    edges = [c for c in root if c.get('edge') == '1']
    segments = [_ends(e, rects) for e in edges]

    def cross(p1, p2, q1, q2):
        def side(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return side(p1, p2, q1) * side(p1, p2, q2) < 0 and side(q1, q2, p1) * side(q1, q2, p2) < 0

    for (a1, a2), (b1, b2) in itertools.combinations(segments, 2):
        assert not cross(a1, a2, b1, b2)


def test_names_go_on_two_balanced_lines_in_equal_ellipses():
    root, rects = _atm()
    values = {_text(c): c.get('value') for c in _usecases(root)}
    assert values['Transfer Dana'] == 'Transfer<br>Dana'
    assert len({rects[c.get('id')][2] for c in _usecases(root)}) == 1
    assert all(rects[c.get('id')][3] == 60 for c in _usecases(root))
    from usecase import _two_lines  # type: ignore
    assert _two_lines('Cetak Laporan Peminjaman Buku') == ['Cetak Laporan', 'Peminjaman Buku']
    assert _two_lines('Login') == ['Login']


def test_output_is_another_name_for_the_right_side():
    model, _ = parse_usecase('x', list(enumerate(['(A)', 'actor Pimpinan <<output>>', 'Pimpinan --> (A)'], start=1)))
    assert model.actors == {'Pimpinan': 'R'}
