# backend/test_sql_parser.py
"""Parser checks for the SQL dialects people export from their tools."""

from sql_parser import parse_sql  # type: ignore


def _links(schema):
    return {(r['from_table'], r['from_column'], r['to_table'], r['to_column'])
            for r in schema['relations']}


def test_foreign_keys_added_by_alter_table():
    # dbdiagram.io export: one ALTER TABLE per foreign key
    schema = parse_sql('''
        CREATE TABLE `program` (`id` BIGINT PRIMARY KEY AUTO_INCREMENT);
        CREATE TABLE `katalog` (
          `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
          `program_id` BIGINT NOT NULL,
          `dibuat_pada` TIMESTAMP DEFAULT (CURRENT_TIMESTAMP)
        );
        ALTER TABLE `katalog` ADD CONSTRAINT `fk_katalog_program`
          FOREIGN KEY (`program_id`) REFERENCES `program` (`id`) ON DELETE CASCADE;
    ''')
    assert [t['name'] for t in schema['tables']] == ['program', 'katalog']
    assert _links(schema) == {('katalog', 'program_id', 'program', 'id')}


def test_several_foreign_keys_in_one_alter_table():
    # phpMyAdmin export: all constraints of a table in one statement
    schema = parse_sql('''
        CREATE TABLE `pelanggan` (`id_pelanggan` int(11) NOT NULL);
        CREATE TABLE `studio` (`id_studio` int(11) NOT NULL);
        CREATE TABLE `pemesanan` (
          `id_pemesanan` int(11) NOT NULL,
          `id_pelanggan` int(11) NOT NULL,
          `id_studio` int(11) NOT NULL
        );
        ALTER TABLE `pemesanan`
          ADD PRIMARY KEY (`id_pemesanan`),
          ADD KEY `id_pelanggan` (`id_pelanggan`);
        ALTER TABLE `pemesanan`
          ADD CONSTRAINT `pemesanan_ibfk_1` FOREIGN KEY (`id_pelanggan`) REFERENCES `pelanggan` (`id_pelanggan`),
          ADD CONSTRAINT `pemesanan_ibfk_2` FOREIGN KEY (`id_studio`) REFERENCES `studio` (`id_studio`);
    ''')
    assert _links(schema) == {
        ('pemesanan', 'id_pelanggan', 'pelanggan', 'id_pelanggan'),
        ('pemesanan', 'id_studio', 'studio', 'id_studio'),
    }


# ── Column details used by the data dictionary ───────────────────────────────

def _columns(schema, table):
    return {c['name']: c for c in next(t for t in schema['tables'] if t['name'] == table)['columns']}


def test_column_details_null_default_unique_and_comments():
    schema = parse_sql('''
        -- Daftar pelanggan (komentar bagian, bukan kolom)
        CREATE TABLE pelanggan (
            id_pelanggan INT AUTO_INCREMENT PRIMARY KEY,   -- nomor unik pelanggan
            nama VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE, -- dipakai untuk login
            status ENUM('Aktif', 'Nonaktif') DEFAULT 'Aktif' COMMENT 'Status akun',
            saldo DECIMAL(10, 2) DEFAULT 0.00,
            dibuat TIMESTAMP DEFAULT (CURRENT_TIMESTAMP),
            catatan TEXT
        );
    ''')
    c = _columns(schema, 'pelanggan')
    assert (c['id_pelanggan']['is_pk'], c['id_pelanggan']['nullable'], c['id_pelanggan']['auto_increment']) == (True, False, True)
    assert c['id_pelanggan']['comment'] == 'nomor unik pelanggan'
    assert (c['nama']['nullable'], c['nama']['default'], c['nama']['comment']) == (False, None, '')
    assert (c['email']['unique'], c['email']['comment']) == (True, 'dipakai untuk login')
    assert c['status']['type'] == "ENUM('Aktif', 'Nonaktif')"        # values keep their case
    assert (c['status']['default'], c['status']['comment'], c['status']['nullable']) == ('Aktif', 'Status akun', True)
    assert c['saldo']['default'] == '0.00' and c['saldo']['type'] == 'DECIMAL(10, 2)'
    assert c['dibuat']['default'] == '(CURRENT_TIMESTAMP)'
    assert (c['catatan']['nullable'], c['catatan']['default'], c['catatan']['unique']) == (True, None, False)


def test_comment_after_the_comma_belongs_to_the_column_before_it():
    schema = parse_sql('CREATE TABLE a (\n  x INT, -- kolom pertama\n  y INT -- kolom kedua\n);')
    c = _columns(schema, 'a')
    assert (c['x']['comment'], c['y']['comment']) == ('kolom pertama', 'kolom kedua')


def test_primary_key_added_by_alter_table():
    schema = parse_sql('''
        CREATE TABLE `studio` (`id_studio` int(11) NOT NULL, `nama` varchar(50) DEFAULT NULL);
        ALTER TABLE `studio` ADD PRIMARY KEY (`id_studio`);
    ''')
    c = _columns(schema, 'studio')
    assert (c['id_studio']['is_pk'], c['id_studio']['nullable']) == (True, False)
    assert (c['nama']['is_pk'], c['nama']['default'], c['nama']['nullable']) == (False, 'NULL', True)
