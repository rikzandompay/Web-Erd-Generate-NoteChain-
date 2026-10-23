# backend/test_data_dictionary.py
"""Data dictionary: rows, draw.io page, Markdown, CSV and the /api/dictionary endpoint."""

import csv
import io
import itertools
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient  # type: ignore

from data_dictionary import HEADERS, build_dictionary_page, dictionary_rows, to_csv, to_markdown  # type: ignore
from generator import generate_drawio_xml  # type: ignore
from index import app  # type: ignore
from sql_parser import parse_sql  # type: ignore

SQL = '''
CREATE TABLE pelanggan (
    id_pelanggan INT AUTO_INCREMENT PRIMARY KEY, -- nomor unik pelanggan
    nama VARCHAR(100) NOT NULL,
    catatan TEXT
);
CREATE TABLE pemesanan (
    id_pemesanan INT AUTO_INCREMENT PRIMARY KEY,
    id_pelanggan INT NOT NULL,
    status ENUM('Pending', 'Sukses') DEFAULT 'Pending' COMMENT 'Status pesanan | dipisah garis',
    total DECIMAL(12, 2) DEFAULT 0.00,
    FOREIGN KEY (id_pelanggan) REFERENCES pelanggan(id_pelanggan)
);
'''


@pytest.fixture(scope='module')
def schema():
    return parse_sql(SQL)


def test_rows_follow_the_seven_columns(schema):
    rows = dict(dictionary_rows(schema))
    assert rows['pelanggan'][0] == ('1', 'id_pelanggan', 'INT', 'PK', 'Tidak', '', 'nomor unik pelanggan')
    assert rows['pelanggan'][1] == ('2', 'nama', 'VARCHAR(100)', '', 'Tidak', '', '')
    assert rows['pelanggan'][2] == ('3', 'catatan', 'TEXT', '', 'Ya', '', '')
    assert rows['pemesanan'][1][3] == 'FK -> pelanggan.id_pelanggan'
    assert rows['pemesanan'][2][2:6] == ("ENUM('Pending', 'Sukses')", '', 'Ya', 'Pending')
    assert rows['pemesanan'][3][5] == '0.00'


def test_primary_key_that_is_also_a_foreign_key():
    rows = dict(dictionary_rows(parse_sql(
        'CREATE TABLE a (id INT PRIMARY KEY);'
        'CREATE TABLE b (id INT PRIMARY KEY REFERENCES a(id));')))
    assert rows['b'][0][3] == 'PK, FK -> a.id'


def test_markdown_has_a_table_per_sql_table_and_escapes_pipes(schema):
    md = to_markdown(schema)
    assert '### Tabel: pelanggan' in md and '### Tabel: pemesanan' in md
    assert '| No | Nama Kolom | Tipe Data | Kunci | Null | Default | Keterangan |' in md
    assert '| 1 | id_pelanggan | INT | PK | Tidak |  | nomor unik pelanggan |' in md
    assert 'Status pesanan \\| dipisah garis' in md


def test_csv_round_trips_with_a_table_column(schema):
    rows = list(csv.reader(io.StringIO(to_csv(schema))))
    assert rows[0] == ['Tabel', *HEADERS]
    assert len(rows) == 1 + 3 + 4
    assert rows[1][:3] == ['pelanggan', '1', 'id_pelanggan']
    assert next(r for r in rows if r[2] == 'status')[7] == 'Status pesanan | dipisah garis'


def _cells(model):
    root = model.find('root')
    return [c for c in root if c.get('vertex') == '1']


def _rect(cell):
    g = cell.find('mxGeometry')
    return tuple(float(g.get(k)) for k in ('x', 'y', 'width', 'height'))


def test_page_is_a_clean_grid_on_the_10px_grid(schema):
    cells = _cells(build_dictionary_page(schema))
    assert all(v % 10 == 0 for c in cells for v in _rect(c))
    for a, b in itertools.combinations(cells, 2):
        (ax, ay, aw, ah), (bx, by, bw, bh) = _rect(a), _rect(b)
        assert not (ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah)


def test_page_has_header_row_and_every_value(schema):
    values = [c.get('value') for c in _cells(build_dictionary_page(schema))]
    assert values.count('Nama Kolom') == 2                       # one header row per table
    assert 'Tabel: pelanggan' in values
    assert 'FK -&gt; pelanggan.id_pelanggan' in values            # labels are HTML-escaped for html=1 cells
    cell_count = 2 + 2 * 7 + 7 * 7                               # titles, headers, 3+4 column rows
    assert len(values) == cell_count


def test_long_comment_makes_the_row_taller_not_wider():
    long = 'x ' * 80
    cells = _cells(build_dictionary_page(parse_sql(f"CREATE TABLE t (a INT, -- {long}\n b INT);")))
    rows = {}
    for c in cells:
        x, y, w, h = _rect(c)
        rows.setdefault(y, []).append((x, w, h))
    grid_rows = [r for r in rows.values() if len(r) == 7]          # the title row spans the whole table
    heights = sorted({r[0][2] for r in grid_rows})
    assert heights[0] == 30 and heights[-1] > 30
    assert max(w for r in grid_rows for _, w, _ in r) <= 320


def test_no_hardcoded_colours_in_the_page(schema):
    assert 'Color=#' not in ET.tostring(build_dictionary_page(schema), encoding='unicode')


def test_generated_file_has_the_dictionary_as_third_page(schema):
    names = [d.get('name') for d in ET.fromstring(generate_drawio_xml(schema)).findall('diagram')]
    assert names == ['ERD', 'Class Diagram', 'Kamus Data']


def test_endpoint_returns_markdown_and_csv():
    client = TestClient(app)
    r = client.post('/api/dictionary', files={'file': ('toko.sql', SQL.encode(), 'application/sql')})
    assert r.status_code == 200
    body = r.json()
    assert body['tables'] == 2 and '### Tabel: pemesanan' in body['markdown'] and body['csv'].startswith('Tabel,No,')
    bad = client.post('/api/dictionary', files={'file': ('toko.txt', b'x', 'text/plain')})
    assert bad.status_code == 400
    empty = client.post('/api/dictionary', files={'file': ('kosong.sql', b'SELECT 1;', 'application/sql')})
    assert empty.status_code == 400 and 'CREATE TABLE' in empty.json()['detail']
