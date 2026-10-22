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
