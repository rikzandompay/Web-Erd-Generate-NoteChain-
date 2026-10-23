# backend/test_relation_labels.py
"""Names written in the relationship diamonds."""

import xml.etree.ElementTree as ET

from generator import _relation_label, generate_drawio_xml  # type: ignore
from sql_parser import parse_sql  # type: ignore

SNACK_SQL = '''
CREATE TABLE users (id_user INT PRIMARY KEY, username VARCHAR(50));
CREATE TABLE kategori (id_kategori INT PRIMARY KEY, nama_kategori VARCHAR(50));
CREATE TABLE supplier (id_supplier INT PRIMARY KEY, nama_supplier VARCHAR(50));
CREATE TABLE produk_snack (
    id_produk INT PRIMARY KEY,
    id_kategori INT,
    FOREIGN KEY (id_kategori) REFERENCES kategori(id_kategori)
);
CREATE TABLE barang_masuk (
    id_masuk INT PRIMARY KEY,
    id_produk INT, id_supplier INT, id_user INT,
    FOREIGN KEY (id_produk) REFERENCES produk_snack(id_produk),
    FOREIGN KEY (id_supplier) REFERENCES supplier(id_supplier),
    FOREIGN KEY (id_user) REFERENCES users(id_user)
);
CREATE TABLE barang_keluar (
    id_keluar INT PRIMARY KEY,
    id_produk INT, id_user INT,
    FOREIGN KEY (id_produk) REFERENCES produk_snack(id_produk),
    FOREIGN KEY (id_user) REFERENCES users(id_user)
);
'''


def _diamond_labels(sql):
    root = ET.fromstring(generate_drawio_xml(parse_sql(sql))).find("diagram[@name='ERD']/mxGraphModel/root")
    return sorted(c.get('value') for c in root if (c.get('style') or '').startswith('rhombus'))


def test_tables_without_known_keywords_no_longer_all_say_memiliki():
    labels = _diamond_labels(SNACK_SQL)
    assert len(labels) == 6
    assert labels.count('memiliki') == 0
    assert set(labels) == {'mencatat', 'mencakup', 'memasok', 'tercatat pada'}
    assert labels.count('mencatat') == 2 and labels.count('tercatat pada') == 2


def test_each_relation_reads_as_parent_verb_child():
    assert _relation_label('produk_snack', 'kategori') == 'mencakup'
    assert _relation_label('barang_masuk', 'supplier') == 'memasok'
    assert _relation_label('barang_masuk', 'users') == 'mencatat'
    assert _relation_label('barang_keluar', 'produk_snack') == 'tercatat pada'
    assert _relation_label('transaksi', 'pelanggan') == 'melakukan'
    assert _relation_label('jadwal', 'dosen') == 'mengajar'


def test_child_keyword_still_wins_over_the_parent_role():
    assert _relation_label('pemesanan', 'pelanggan') == 'memesan'
    assert _relation_label('detail_pemesanan', 'pemesanan') == 'memiliki'
    assert _relation_label('pembayaran', 'pemesanan') == 'membayar'


def test_unknown_tables_fall_back_to_memiliki():
    assert _relation_label('xyz', 'abc') == 'memiliki'


def test_the_author_can_name_a_relation_in_a_sql_comment():
    schema = parse_sql('''
        CREATE TABLE toko (id INT PRIMARY KEY);
        CREATE TABLE stok (
            id INT PRIMARY KEY,
            id_toko INT, -- toko tempat barang disimpan @rel: menyimpan
            FOREIGN KEY (id_toko) REFERENCES toko(id)
        );''')
    col = next(c for c in schema['tables'][1]['columns'] if c['name'] == 'id_toko')
    assert col['rel_label'] == 'menyimpan'
    assert col['comment'] == 'toko tempat barang disimpan'          # the tag is not part of the description
    assert _diamond_labels('CREATE TABLE toko (id INT PRIMARY KEY);'
                           'CREATE TABLE stok (id INT PRIMARY KEY, id_toko INT, -- @rel: menyimpan\n'
                           'FOREIGN KEY (id_toko) REFERENCES toko(id));') == ['menyimpan']


def test_a_custom_name_wins_over_every_rule():
    assert _relation_label('pemesanan', 'pelanggan', 'dipesan oleh') == 'dipesan oleh'
    assert _relation_label('x', 'y', '  ') == 'memiliki'              # blank is ignored


def test_columns_without_the_tag_have_an_empty_name():
    schema = parse_sql('CREATE TABLE a (x INT, -- catatan biasa\n y INT);')
    assert [c['rel_label'] for c in schema['tables'][0]['columns']] == ['', '']
