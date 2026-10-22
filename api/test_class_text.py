# backend/test_class_text.py
"""Class diagram from text: parser, relation styles and layout rules (PRD CLS-*)."""

import itertools
import xml.etree.ElementTree as ET

import pytest

from class_diagram import parse_class_text  # type: ignore
from test_generator import _crosses, _overlap, _polyline, _rect, _top_vertices  # type: ignore
from uml import generate_uml  # type: ignore

# PRD §10: 10 classes with 12 relations of every kind, plus one class without relations
SAMPLE = '''\
=== Class Diagram
class menu {
  - id : int
  - nama_menu : varchar
  + create()
  + update()
}
class bahan {
  - id : int
  - nama_bahan : varchar
  - satuan : varchar
  + create()
  + update()
  + delete()
}
class bahan_kering { - kadar_air : decimal; + keringkan() }
class bahan_basah { - suhu_simpan : int }
class menu_bahan { - jumlah : decimal }
class stok_masuk { - tanggal : date; - jumlah : decimal }
class stok_keluar { - tanggal : date; - jumlah : decimal }
class gizi { - energi : double; - protein : double }
class produksi_harian { - tanggal : date; - total_porsi : int }
class laporan { + cetak() }
class pengaturan { - kunci : varchar; - nilai : text }

menu "1" -- "0..*" menu_bahan : terdiri dari
bahan "1" -- "0..*" menu_bahan
bahan <|-- bahan_kering      ' inheritance
bahan <|-- bahan_basah
bahan "1" -- "0..*" stok_masuk
bahan "1" -- "0..*" stok_keluar
bahan "1" -- "1" gizi
menu "1" -- "0..*" produksi_harian
produksi_harian *-- stok_keluar   ' composition
laporan o-- produksi_harian       ' aggregation
laporan ..> stok_masuk            ' dependency
gizi --> menu
'''


@pytest.fixture(scope='module')
def page():
    result = generate_uml('class', SAMPLE)
    assert result['errors'] == []
    assert result['pages'] == ['Class Diagram']
    return ET.fromstring(result['xml']).find('diagram/mxGraphModel/root')


def _edges(root):
    return [c for c in root if c.get('edge') == '1']


def test_parser_reads_classes_members_and_every_relation_kind():
    lines = list(enumerate(SAMPLE.splitlines(), start=1))[1:]
    classes, relations, errors = parse_class_text(lines)
    assert errors == []
    assert len(classes) == 11 and len(relations) == 12
    bahan = next(c for c in classes if c.name == 'bahan')
    assert bahan.attributes == ['- id : int', '- nama_bahan : varchar', '- satuan : varchar']
    assert bahan.methods == ['+ create()', '+ update()', '+ delete()']
    kering = next(c for c in classes if c.name == 'bahan_kering')
    assert (kering.attributes, kering.methods) == (['- kadar_air : decimal'], ['+ keringkan()'])

    by_kind = {}
    for r in relations:
        by_kind.setdefault(r.kind, r)
    assert (by_kind['inheritance'].source, by_kind['inheritance'].target) == ('bahan_kering', 'bahan')
    assert (by_kind['composition'].source, by_kind['composition'].target) == ('produksi_harian', 'stok_keluar')
    assert (by_kind['aggregation'].source, by_kind['aggregation'].target) == ('laporan', 'produksi_harian')
    assert (by_kind['dependency'].source, by_kind['dependency'].target) == ('laporan', 'stok_masuk')
    first = relations[0]
    assert (first.source_label, first.target_label, first.label) == ('1', '0..*', 'terdiri dari')


def test_parser_reports_bad_lines():
    lines = list(enumerate(['class a {', '  - id : int', 'class b {', '  - id : int'], start=1))
    classes, _, errors = parse_class_text(lines)
    assert [c.name for c in classes] == ['a', 'b']
    assert errors == [(1, "class 'a' belum ditutup dengan '}'"), (3, "class 'b' belum ditutup dengan '}'")]
    _, _, errors = parse_class_text([(1, 'a ?? b')])
    assert errors == [(1, 'Baris tidak dikenali: "a ?? b". Contoh: class Nama { … } atau A "1" -- "0..*" B')]


def test_no_overlap_and_lines_stay_orthogonal_outside_classes(page):
    cells = _top_vertices(page)
    for a, b in itertools.combinations(cells, 2):
        assert not _overlap(_rect(a), _rect(b)), (a.get('value'), b.get('value'))   # CLS-4
    rects = {c.get('id'): _rect(c) for c in cells}
    for edge in _edges(page):
        points = _polyline(edge, rects)
        ends = {edge.get('source'), edge.get('target')}
        for p, q in zip(points, points[1:]):
            assert p[0] == q[0] or p[1] == q[1]                                       # CLS-5
            for cid, rect in rects.items():
                if cid not in ends:
                    assert not _crosses(p, q, rect), (edge.get('id'), cid)


def test_relation_ends_follow_their_kind(page):
    names = {c.get('id'): c.get('value') for c in _top_vertices(page)}
    styles = {(names[e.get('source')], names[e.get('target')]): e.get('style') for e in _edges(page)}
    assert 'endArrow=block;endFill=0' in styles[('bahan_kering', 'bahan')]               # CLS-7
    assert 'startArrow=diamondThin;startFill=1' in styles[('produksi_harian', 'stok_keluar')]
    assert 'startArrow=diamondThin;startFill=0' in styles[('laporan', 'produksi_harian')]
    assert 'dashed=1' in styles[('laporan', 'stok_masuk')] and 'endArrow=open' in styles[('laporan', 'stok_masuk')]
    assert 'endArrow=none;startArrow=none' in styles[('menu', 'menu_bahan')]


def test_multiplicities_sit_at_the_line_ends(page):
    edge = next(e for e in _edges(page) if e.get('value') == 'terdiri dari')
    labels = {c.get('value'): c.find('mxGeometry').get('x') for c in page if c.get('parent') == edge.get('id')}
    assert labels == {'1': '-1', '0..*': '1'}                                          # CLS-6


def test_subclasses_below_parent_and_loners_on_the_right(page):
    rect = {c.get('value'): _rect(c) for c in _top_vertices(page)}
    for child in ('bahan_kering', 'bahan_basah'):
        assert rect[child][1] > rect['bahan'][1]
    assert rect['pengaturan'][0] == max(x for x, _, _, _ in rect.values())             # CLS-3
