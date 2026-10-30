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
    return sorted(c.get('value').replace('<br>', ' ') for c in root if (c.get('style') or '').startswith('rhombus'))


def test_tables_without_known_keywords_no_longer_all_say_memiliki():
    labels = _diamond_labels(SNACK_SQL)
    assert len(labels) == 6
    assert labels.count('memiliki') == 0
    assert set(labels) == {'mencatat', 'mengelompokkan', 'memasok', 'tercatat pada'}
    assert labels.count('mencatat') == 2 and labels.count('tercatat pada') == 2


def test_each_relation_reads_as_parent_verb_child():
    assert _relation_label('produk_snack', 'kategori') == 'mengelompokkan'
    assert _relation_label('barang_masuk', 'supplier') == 'memasok'
    assert _relation_label('barang_masuk', 'users') == 'mencatat'
    assert _relation_label('barang_keluar', 'produk_snack') == 'tercatat pada'
    assert _relation_label('transaksi', 'pelanggan') == 'melakukan'
    assert _relation_label('jadwal', 'dosen') == 'mengajar'


def test_transaction_tables_name_their_relations():
    assert _relation_label('pemesanan', 'pelanggan') == 'memesan'
    assert _relation_label('detail_pemesanan', 'pemesanan') == 'terdiri atas'     # a part of the order
    assert _relation_label('pembayaran', 'pemesanan') == 'dibayar melalui'          # the order is paid through it


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


# ── Layout: a table that links two others sits between them ──────────────────

def test_cycle_of_tables_is_packed_without_long_lines():
    """users links barang_masuk and barang_keluar, which both link produk_snack: a four-table loop."""
    from layout import assign_grid  # type: ignore
    schema = parse_sql(SNACK_SQL)
    grid = assign_grid([t['name'] for t in schema['tables']], schema['relations'])
    for rel in schema['relations']:
        (c1, r1), (c2, r2) = grid[rel['from_table']], grid[rel['to_table']]
        assert abs(c1 - c2) + abs(r1 - r2) == 1, (rel['from_table'], rel['to_table'])
    assert len(set(grid.values())) == len(grid)                      # nobody shares a cell


# ── Verbs that fit the relation (relation_names.py) ──────────────────────────

from relation_names import active_verb, diamond_text, relation_label  # type: ignore  # noqa: E402

YABUN_SQL = '''
CREATE TABLE pengguna (id INT PRIMARY KEY);
CREATE TABLE program (id INT PRIMARY KEY);
CREATE TABLE katalog (id INT PRIMARY KEY, program_id INT REFERENCES program(id));
CREATE TABLE artikel (id INT PRIMARY KEY, program_id INT REFERENCES program(id),
                      penulis_id INT REFERENCES pengguna(id));
CREATE TABLE donatur (id INT PRIMARY KEY);
CREATE TABLE rekening_bank (id INT PRIMARY KEY);
CREATE TABLE donasi (id INT PRIMARY KEY, donatur_id INT REFERENCES donatur(id),
                     rekening_bank_id INT REFERENCES rekening_bank(id),
                     diverifikasi_oleh INT REFERENCES pengguna(id));
CREATE TABLE transaksi_keuangan (id INT PRIMARY KEY, donasi_id INT REFERENCES donasi(id),
                                 dicatat_oleh INT REFERENCES pengguna(id));
CREATE TABLE kegiatan (id INT PRIMARY KEY);
CREATE TABLE foto_kegiatan (id INT PRIMARY KEY, kegiatan_id INT REFERENCES kegiatan(id));
'''


def test_yabun_relations_get_the_verbs_that_fit_them():
    schema = parse_sql(YABUN_SQL)
    got = {(r['to_table'], r['from_table']): relation_label(r['from_table'], r['to_table'], '', r['from_column'])
           for r in schema['relations']}
    assert got == {
        ('program', 'katalog'): 'menaungi',
        ('program', 'artikel'): 'memuat',
        ('pengguna', 'artikel'): 'menulis',                     # penulis_id
        ('donatur', 'donasi'): 'memberikan',
        ('rekening_bank', 'donasi'): 'menerima',
        ('pengguna', 'donasi'): 'memverifikasi',                 # diverifikasi_oleh
        ('donasi', 'transaksi_keuangan'): 'tercatat sebagai',
        ('pengguna', 'transaksi_keuangan'): 'mencatat',          # dicatat_oleh
        ('kegiatan', 'foto_kegiatan'): 'dilengkapi',
    }
    assert 'memiliki' not in _diamond_labels(YABUN_SQL)


def test_the_fk_column_names_the_role():
    assert relation_label('artikel', 'users', column='author_id') == 'menulis'
    assert relation_label('pengajuan', 'users', column='approved_by') == 'menyetujui'
    assert relation_label('tiket', 'users', column='assigned_to') == 'menangani'
    assert relation_label('produk', 'users', column='created_by') == 'membuat'
    assert relation_label('laporan', 'pengguna', column='disetujui_oleh') == 'menyetujui'
    assert relation_label('stok', 'pengguna', column='diperbarui_oleh') == 'memperbarui'
    assert relation_label('pegawai', 'pegawai', column='atasan_id') == 'membawahi'
    assert relation_label('toko', 'users', column='pemilik_id') == 'memiliki'   # the one place it fits
    # a generic users table seen through the column's role
    assert relation_label('penjualan', 'users', column='kasir_id') == 'melayani'
    assert relation_label('pemesanan', 'users', column='pelanggan_id') == 'memesan'


def test_parts_of_a_table():
    assert relation_label('detail_pemesanan', 'pemesanan') == 'terdiri atas'
    assert relation_label('order_items', 'orders') == 'terdiri atas'
    assert relation_label('riwayat_stok', 'stok') == 'tercatat dalam'
    assert relation_label('anggota_tim', 'tim') == 'beranggotakan'
    assert relation_label('ulasan_produk', 'produk') == 'menerima'


def test_kinds_of_tables():
    cases = {
        ('produk', 'kategori'): 'mengelompokkan', ('articles', 'program_categories'): 'mengelompokkan',
        ('barang_masuk', 'supplier'): 'memasok', ('barang_masuk', 'users'): 'mencatat',
        ('produk', 'users'): 'mengelola', ('artikel', 'admin'): 'menulis',
        ('pemesanan', 'pelanggan'): 'memesan', ('peminjaman', 'anggota'): 'meminjam',
        ('pembayaran', 'pelanggan'): 'membayar', ('kunjungan', 'pasien'): 'melakukan',
        ('detail_pemesanan', 'produk'): 'dipesan dalam', ('peminjaman', 'buku'): 'dipinjam dalam',
        ('barang_keluar', 'produk_snack'): 'tercatat pada',
        ('pembayaran', 'pemesanan'): 'dibayar melalui', ('tiket', 'pemesanan'): 'menghasilkan',
        ('financial_transactions', 'donatur'): 'bertransaksi',
        ('siswa', 'kelas'): 'menampung', ('pemesanan', 'studio'): 'dipesan dalam',
        ('mahasiswa', 'jurusan'): 'menaungi', ('stok', 'gudang'): 'menyimpan',
        ('pelanggan', 'wilayah'): 'mencakup', ('jadwal', 'dosen'): 'mengajar',
        ('komentar', 'artikel'): 'menerima', ('peserta', 'kegiatan'): 'diikuti',
    }
    for (child, parent), verb in cases.items():
        assert relation_label(child, parent) == verb, (child, parent)


def test_memiliki_is_only_the_last_resort():
    assert relation_label('xyz', 'abc') == 'memiliki'
    labels = [relation_label(c, p) for (c, p) in [
        ('produk', 'kategori'), ('barang_masuk', 'supplier'), ('pemesanan', 'pelanggan'),
        ('pembayaran', 'pemesanan'), ('detail_pemesanan', 'produk')]]
    assert 'memiliki' not in labels and len(set(labels)) == len(labels)


def test_active_verbs_follow_the_men_prefix_rules():
    pairs = {
        'verifikasi': 'memverifikasi', 'catat': 'mencatat', 'buat': 'membuat', 'setujui': 'menyetujui',
        'tangani': 'menangani', 'perbarui': 'memperbarui', 'periksa': 'memeriksa', 'kirim': 'mengirim',
        'konfirmasi': 'mengonfirmasi', 'unggah': 'mengunggah', 'input': 'menginput', 'proses': 'memproses',
        'terima': 'menerima', 'tulis': 'menulis', 'cek': 'mengecek', 'hapus': 'menghapus',
        'nilai': 'menilai', 'simpan': 'menyimpan', 'daftar': 'mendaftar', 'jual': 'menjual',
        'transfer': 'mentransfer', 'klik': 'mengeklik', 'kembalikan': 'mengembalikan', 'ubah': 'mengubah',
        'rekam': 'merekam', 'pesan': 'memesan', 'gunakan': 'menggunakan', 'validasi': 'memvalidasi',
        'pakai': 'memakai', 'bom': 'mengebom',
    }
    for root, verb in pairs.items():
        assert active_verb(root) == verb, root


def test_long_labels_wrap_inside_the_diamond():
    assert diamond_text('tercatat sebagai') == 'tercatat<br>sebagai'
    assert diamond_text('mengelompokkan') == 'mengelompokkan'
    assert diamond_text('menulis') == 'menulis'
    assert diamond_text('<script>') == '&lt;script&gt;'                 # names from SQL comments are escaped


# ── An HR system: the employee does, the shift is used ───────────────────────

def test_employee_tables_read_correctly():
    assert relation_label('absensi', 'karyawan', column='karyawan_id') == 'melakukan'
    assert relation_label('cuti', 'karyawan', column='karyawan_id') == 'mengajukan'
    assert relation_label('lembur', 'pegawai') == 'mengajukan'
    assert relation_label('gaji', 'karyawan', column='karyawan_id') == 'menerima'
    assert relation_label('penggajian', 'employee') == 'menerima'
    assert relation_label('xyz', 'karyawan') == 'memiliki'              # no longer "mengelola" for anything unknown
    assert relation_label('absensi', 'shift', column='shift_id') == 'digunakan dalam'
    assert relation_label('absensi', 'users', column='karyawan_id') == 'melakukan'   # a generic users table seen as an employee


def test_admin_like_tables_are_unchanged():
    assert relation_label('produk', 'users') == 'mengelola' and relation_label('barang_masuk', 'users') == 'mencatat'
    assert relation_label('artikel', 'admin') == 'menulis'


def test_presensiku_prd_relations():
    sql = """
    CREATE TABLE karyawan (id SERIAL PRIMARY KEY, nama VARCHAR(100));
    CREATE TABLE shift (id SERIAL PRIMARY KEY, nama_shift VARCHAR(50));
    CREATE TABLE absensi (id SERIAL PRIMARY KEY, karyawan_id INT REFERENCES karyawan(id), shift_id INT REFERENCES shift(id));
    CREATE TABLE cuti (id SERIAL PRIMARY KEY, karyawan_id INT REFERENCES karyawan(id));
    CREATE TABLE gaji (id SERIAL PRIMARY KEY, karyawan_id INT REFERENCES karyawan(id));
    """
    assert _diamond_labels(sql) == ['digunakan dalam', 'melakukan', 'menerima', 'mengajukan']
