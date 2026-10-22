# backend/test_generator.py
"""Layout checks for the generated .drawio pages, run against every sample .sql file."""

import itertools
import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

from generator import generate_drawio_xml  # type: ignore
from sql_parser import parse_sql  # type: ignore

# Hub with many neighbours, self reference, two FKs to the same table,
# a table without relations and one with lots of columns.
EDGE_CASE_SQL = '\n'.join(
    ['CREATE TABLE hub (id INT PRIMARY KEY, nama VARCHAR(50));']
    + [f'CREATE TABLE anak_{i} (id INT PRIMARY KEY, hub_id INT REFERENCES hub(id));'
       for i in range(9)]
    + [
        'CREATE TABLE pegawai (id INT PRIMARY KEY, atasan_id INT REFERENCES pegawai(id));',
        'CREATE TABLE transfer (id INT PRIMARY KEY, dari_id INT REFERENCES hub(id),'
        ' ke_id INT REFERENCES hub(id));',
        'CREATE TABLE lepas (id INT PRIMARY KEY, catatan TEXT);',
        'CREATE TABLE lebar (id INT PRIMARY KEY, hub_id INT REFERENCES hub(id), '
        + ', '.join(f'kolom_panjang_nomor_{i} VARCHAR(20)' for i in range(14)) + ');',
    ]
)

CASES = {p.name: p.read_text(encoding='utf-8')
         for p in sorted(pathlib.Path(__file__).parent.glob('*.sql'))}
CASES['edge_cases'] = EDGE_CASE_SQL


@pytest.fixture(params=list(CASES), ids=list(CASES))
def generated(request):
    schema = parse_sql(CASES[request.param])
    xml = generate_drawio_xml(schema)
    pages = {d.get('name'): d.find('mxGraphModel/root') for d in ET.fromstring(xml).findall('diagram')}
    return schema, xml, pages


def _top_vertices(root):
    return [c for c in root if c.get('vertex') == '1' and c.get('parent') == '1']


def _rect(cell):
    geo = cell.find('mxGeometry')
    return tuple(float(geo.get(k)) for k in ('x', 'y', 'width', 'height'))


def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_two_pages(generated):
    _, _, pages = generated
    assert list(pages) == ['ERD', 'Class Diagram']


def test_shapes_on_grid(generated):
    _, _, pages = generated
    for root in pages.values():
        for cell in _top_vertices(root):
            assert all(v % 10 == 0 for v in _rect(cell)), cell.get('value')


def test_no_overlapping_shapes(generated):
    _, _, pages = generated
    for page, root in pages.items():
        cells = _top_vertices(root)
        for a, b in itertools.combinations(cells, 2):
            assert not _overlap(_rect(a), _rect(b)), (page, a.get('value'), b.get('value'))


def test_edges_drawn_behind_shapes(generated):
    _, _, pages = generated
    for root in pages.values():
        kinds = [c.get('edge') == '1' for c in root if c.get('parent') == '1']
        assert kinds == sorted(kinds, reverse=True)


def test_one_diamond_and_class_link_per_relation(generated):
    schema, _, pages = generated
    diamonds = [c for c in _top_vertices(pages['ERD']) if c.get('style').startswith('rhombus')]
    class_edges = [c for c in pages['Class Diagram'] if c.get('edge') == '1']
    assert len(diamonds) == len(schema['relations'])
    assert len(class_edges) == len(schema['relations'])


def _style(cell):
    return dict(part.split('=', 1) for part in cell.get('style').split(';') if '=' in part)


def _polyline(edge, rects):
    """Absolute points of a relation line: exit port, waypoints, entry port."""
    style = _style(edge)

    def port(rect, prefix):
        x, y, w, h = rect
        return (x + float(style[prefix + 'X']) * w + float(style[prefix + 'Dx']),
                y + float(style[prefix + 'Y']) * h + float(style[prefix + 'Dy']))

    waypoints = [(float(p.get('x')), float(p.get('y')))
                 for p in edge.findall("mxGeometry/Array[@as='points']/mxPoint")]
    return [port(rects[edge.get('source')], 'exit'), *waypoints,
            port(rects[edge.get('target')], 'entry')]


def _crosses(p, q, rect):
    """Whether the axis-aligned segment p–q runs through the inside of `rect`."""
    x, y, w, h = rect
    lo_x, hi_x = sorted((p[0], q[0]))
    lo_y, hi_y = sorted((p[1], q[1]))
    return lo_x < x + w - 1 and hi_x > x + 1 and lo_y < y + h - 1 and hi_y > y + 1


def _relation_lines(pages):
    for name, root in pages.items():
        rects = {c.get('id'): _rect(c) for c in _top_vertices(root)}
        diamonds = {c.get('id') for c in _top_vertices(root) if c.get('style').startswith('rhombus')}
        for edge in root:
            if edge.get('edge') == '1' and (name == 'Class Diagram' or edge.get('target') in diamonds):
                yield name, edge, rects


def test_relation_lines_only_run_horizontally_or_vertically(generated):
    _, _, pages = generated
    for page, edge, rects in _relation_lines(pages):
        points = _polyline(edge, rects)
        for p, q in zip(points, points[1:]):
            assert p[0] == q[0] or p[1] == q[1], (page, edge.get('id'), points)


def test_relation_lines_do_not_cross_shapes(generated):
    _, _, pages = generated
    for page, edge, rects in _relation_lines(pages):
        points = _polyline(edge, rects)
        ends = {edge.get('source'), edge.get('target')}
        for p, q in zip(points, points[1:]):
            for cid, rect in rects.items():
                if cid not in ends:
                    assert not _crosses(p, q, rect), (page, edge.get('id'), cid, points)


def test_no_hardcoded_colours(generated):
    _, xml, _ = generated
    assert not re.search(r'(fill|stroke|font)Color=#', xml)
