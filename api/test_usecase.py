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
    assert errors == [(3, 'Baris tidak dikenali: "apa ini". Contoh: actor Admin, (Login), Admin --> (Login)'),
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
    assert boundary.get('value') == 'Perpustakaan'
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
    by_text = {c.get('value'): rects[c.get('id')] for c in _usecases(root)}
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
    names = {c.get('id'): c.get('value') for c in cells.values() if c.get('vertex') == '1'}
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
