# backend/test_codegen.py
"""Starter code from SQL: naming rules, each target's output, and (when the tools exist) running it."""

import io
import os
import shutil
import subprocess
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # type: ignore

from codegen import class_name, column_kind, generate_code, role_of, singular  # type: ignore
from index import app  # type: ignore
from sql_parser import parse_sql  # type: ignore

# Self reference, two keys to one table, composite and text keys, a cycle, one-to-one, Python keywords
EDGE_SQL = """CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP NULL,
  updated_at TIMESTAMP NULL,
  deleted_at TIMESTAMP NULL
);
CREATE TABLE categories (
  id INT PRIMARY KEY,
  parent_id INT NULL, -- kategori induk
  name VARCHAR(80) NOT NULL,
  FOREIGN KEY (parent_id) REFERENCES categories(id)
);
CREATE TABLE produk (
  kode VARCHAR(20) PRIMARY KEY,
  nama VARCHAR(120) NOT NULL,
  harga DECIMAL(12) NOT NULL DEFAULT 0,
  berat DOUBLE,
  status ENUM('aktif','arsip') DEFAULT 'aktif',
  category_id INT,
  FOREIGN KEY (category_id) REFERENCES categories(id)
);
CREATE TABLE articles (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  author_id INT NOT NULL,
  editor_id INT,
  `from` VARCHAR(50),
  class TEXT,
  body LONGTEXT,
  meta JSON,
  published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (author_id) REFERENCES users(id),
  FOREIGN KEY (editor_id) REFERENCES users(id)
);
CREATE TABLE profiles (
  user_id INT PRIMARY KEY,
  bio TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE article_tags (
  article_id BIGINT NOT NULL,
  tag VARCHAR(30) NOT NULL,
  PRIMARY KEY (article_id, tag),
  FOREIGN KEY (article_id) REFERENCES articles(id)
);
CREATE TABLE teams (
  id INT AUTO_INCREMENT PRIMARY KEY,
  captain_id INT NULL,
  FOREIGN KEY (captain_id) REFERENCES players(id)
);
CREATE TABLE players (
  id INT AUTO_INCREMENT PRIMARY KEY,
  team_id INT NULL,
  passport_no VARCHAR(20) UNIQUE,
  FOREIGN KEY (team_id) REFERENCES teams(id)
);
"""

YABUN_SQL = Path('/home/rikzan24_/YABUN PONTIANAK/database/yabun_pontianak.sql')
TODAY = date(2026, 10, 25)


@pytest.fixture(scope='module')
def edge():
    return parse_sql(EDGE_SQL)


def files_of(parsed, target, db='postgresql'):
    return {f['path']: f['content'] for f in generate_code(parsed, target, 'edge.sql', db, TODAY)}


# ── Names and types ──────────────────────────────────────────────────────────

def test_names():
    assert [singular(w) for w in ['users', 'categories', 'kas', 'status', 'kelas', 'donasi', 'address']] == \
        ['user', 'category', 'kas', 'status', 'kelas', 'donasi', 'address']
    assert class_name('financial_transactions') == 'FinancialTransaction' and class_name('rekening_bank') == 'RekeningBank'
    assert [role_of(c) for c in ['penulis_id', 'id_pelanggan', 'diverifikasi_oleh', 'kode_produk']] == \
        ['penulis', 'pelanggan', 'diverifikasi_oleh', 'produk']


def test_column_kinds():
    assert column_kind('DECIMAL(10, 2)')['args'] == ['10', '2']
    assert column_kind('TINYINT(1)')['kind'] == 'bool' and column_kind('TINYINT(4)')['kind'] == 'tinyint'
    assert column_kind("ENUM('aktif', 'arsip')")['args'] == ['aktif', 'arsip']
    assert column_kind('BIGINT UNSIGNED')['unsigned'] and column_kind('SERIAL')['serial']
    assert column_kind('GEOMETRY')['kind'] == 'string'


# ── Laravel ──────────────────────────────────────────────────────────────────

def test_laravel_migrations_come_parents_first_with_cycles_deferred(edge):
    paths = [p for p in files_of(edge, 'laravel') if p.startswith('database/migrations/')]
    names = [p.split('_create_')[-1].replace('_table.php', '') if '_create_' in p else 'FK' for p in paths]
    assert names.index('users') < names.index('articles') < names.index('article_tags')
    assert names.index('categories') < names.index('produk') and names[-1] == 'FK'
    assert paths[0] == 'database/migrations/2026_10_25_000001_create_users_table.php'
    fk = files_of(edge, 'laravel')[paths[-1]]
    assert "Schema::table('teams'" in fk and "->references('id')->on('players')" in fk and 'dropForeign' in fk


def test_laravel_columns(edge):
    f = files_of(edge, 'laravel')
    users = next(v for k, v in f.items() if k.endswith('create_users_table.php'))
    assert '$table->id();' in users and '$table->timestamps();' in users and '$table->softDeletes();' in users
    assert "$table->string('email', 150)->unique();" in users and "$table->boolean('is_active')->nullable()->default(true);" in users
    articles = next(v for k, v in f.items() if k.endswith('create_articles_table.php'))
    assert "$table->foreignId('editor_id')->nullable()->constrained('users', 'id');" in articles
    assert "$table->dateTime('published_at')->nullable()->useCurrent();" in articles
    produk = next(v for k, v in f.items() if k.endswith('create_produk_table.php'))
    assert "$table->decimal('harga', 12, 0)->default(0);" in produk and "$table->primary('kode');" in produk
    assert "$table->enum('status', ['aktif', 'arsip'])->nullable()->default('aktif');" in produk
    tags = next(v for k, v in f.items() if k.endswith('create_article_tags_table.php'))
    assert "$table->primary(['article_id', 'tag']);" in tags


def test_laravel_models(edge):
    f = files_of(edge, 'laravel')
    article = f['app/Models/Article.php']
    assert "return $this->belongsTo(User::class, 'author_id', 'id');" in article and 'public function editor(): BelongsTo' in article
    user = f['app/Models/User.php']
    assert 'public function articlesAuthor(): HasMany' in user and 'public function articlesEditor(): HasMany' in user
    assert 'use SoftDeletes;' in user and "'is_active' => 'boolean'" in user
    produk = f['app/Models/Produk.php']
    assert "protected $primaryKey = 'kode';" in produk and "protected $keyType = 'string';" in produk
    assert 'public $timestamps = false;' in produk


php_ready = shutil.which('php') and Path('/home/rikzan24_/YABUN PONTIANAK/vendor/autoload.php').exists()


@pytest.mark.skipif(not php_ready, reason='butuh PHP dan vendor Laravel')
@pytest.mark.parametrize('sql', ['edge', 'yabun'])
def test_laravel_files_run_in_laravel(sql, tmp_path, edge):
    parsed = edge if sql == 'edge' else parse_sql(YABUN_SQL.read_text(encoding='utf-8'))
    for path, content in files_of(parsed, 'laravel', 'mysql').items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content)
    (tmp_path / 'check.php').write_text(LARAVEL_CHECK)
    out = subprocess.run(['php', str(tmp_path / 'check.php'), str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and 'rollback OK' in out.stdout, out.stdout + out.stderr


LARAVEL_CHECK = r"""<?php
// Runs generated migrations on an in-memory SQLite database with YABUN's Laravel vendor (read only),
// then loads every model and calls every relationship method.
require '/home/rikzan24_/YABUN PONTIANAK/vendor/autoload.php';
use Illuminate\Container\Container;
use Illuminate\Database\Capsule\Manager as Capsule;
use Illuminate\Support\Facades\Facade;

$dir = $argv[1];
$capsule = new Capsule;
$capsule->addConnection(['driver' => 'sqlite', 'database' => ':memory:', 'foreign_key_constraints' => true]);
$capsule->setAsGlobal();
$capsule->bootEloquent();
$app = new Container;
$app->instance('db', $capsule->getDatabaseManager());
$app->bind('db.schema', fn () => $capsule->getConnection()->getSchemaBuilder());
Facade::setFacadeApplication($app);

$n = 0;
foreach (glob("$dir/database/migrations/*.php") as $file) { $m = require $file; $m->up(); $n++; }
echo "migration jalan: $n\n";
$m = 0; $rels = 0;
foreach (glob("$dir/app/Models/*.php") as $file) { require_once $file; }   // all classes first: relations point at each other
foreach (glob("$dir/app/Models/*.php") as $file) {
    $class = 'App\\Models\\' . basename($file, '.php');
    $model = new $class;
    $model->getTable(); $model->getCasts();
    foreach ((new ReflectionClass($class))->getMethods() as $method) {
        if ($method->class === $class && $method->getReturnType() && str_contains((string) $method->getReturnType(), 'Relations')) {
            $relation = $model->{$method->name}();
            $relation->getRelated()->getTable(); $rels++;
        }
    }
    $m++;
}
echo "model dimuat: $m, relasi dicoba: $rels\n";
// rollback in reverse order proves down() works too
foreach (array_reverse(glob("$dir/database/migrations/*.php")) as $file) { $mig = require $file; $mig->down(); }
echo "rollback OK\n";
"""


# ── Prisma ───────────────────────────────────────────────────────────────────

def test_prisma_schema(edge):
    schema = files_of(edge, 'prisma')['prisma/schema.prisma']
    lines = {' '.join(line.split()) for line in schema.splitlines()}        # alignment spaces do not matter
    assert 'provider = "postgresql"' in lines and 'url = env("DATABASE_URL")' in lines
    assert 'author User @relation("articles_author_id", fields: [author_id], references: [id])' in lines
    assert 'articles_author Article[] @relation("articles_author_id")' in lines
    assert 'parent Category? @relation("categories_parent_id", fields: [parent_id], references: [id])' in lines
    assert 'profiles Profile?' in lines                                  # one-to-one: the key is the primary key
    assert '@@id([article_id, tag])' in lines and '@@map("article_tags")' in lines
    assert 'harga Decimal @default(0) @db.Decimal(12, 0)' in lines
    assert 'updated_at DateTime? @updatedAt' in lines
    assert 'status String? @default("aktif") /// pilihan: aktif, arsip' in lines
    sqlite = files_of(edge, 'prisma', 'sqlite')['prisma/schema.prisma']
    assert 'provider = "sqlite"' in sqlite and '@db.' not in sqlite and 'Json' not in sqlite


# ── SQLAlchemy ───────────────────────────────────────────────────────────────

def test_sqlalchemy_module_compiles_and_names_are_safe(edge):
    src = files_of(edge, 'sqlalchemy')['app/models.py']
    compile(src, 'models.py', 'exec')
    assert "from_: Mapped[Optional[str]] = mapped_column('from', String(50))" in src
    assert "class_: Mapped[Optional[str]] = mapped_column('class', Text)" in src
    assert "author: Mapped['User'] = relationship(back_populates='articles_author', foreign_keys=[author_id])" in src
    assert "remote_side=[id]" in src                                    # self reference


@pytest.mark.parametrize('sql', ['edge', 'yabun'])
def test_sqlalchemy_models_create_tables(sql, edge):
    sqlalchemy = pytest.importorskip('sqlalchemy')
    from sqlalchemy.orm import configure_mappers
    parsed = edge if sql == 'edge' else parse_sql(YABUN_SQL.read_text(encoding='utf-8'))
    namespace = {}
    exec(compile(files_of(parsed, 'sqlalchemy')['app/models.py'], 'models.py', 'exec'), namespace)
    try:
        configure_mappers()
        engine = sqlalchemy.create_engine('sqlite://')
        namespace['Base'].metadata.create_all(engine)
        assert len(sqlalchemy.inspect(engine).get_table_names()) == len(parsed['tables'])
    finally:
        namespace['Base'].registry.dispose()


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_code_endpoints():
    client = TestClient(app)
    upload = {'file': ('toko.sql', EDGE_SQL.encode(), 'application/sql')}
    r = client.post('/api/code', files=upload, data={'target': 'prisma', 'database': 'mysql'})
    assert r.status_code == 200 and r.json()['zip_name'] == 'toko-prisma.zip'
    assert 'provider = "mysql"' in r.json()['files'][0]['content']
    r = client.post('/api/code/zip', files=upload, data={'target': 'laravel'})
    assert r.status_code == 200 and r.headers['content-type'] == 'application/zip'
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert 'app/Models/User.php' in names and any(n.startswith('database/migrations/') for n in names)
    assert client.post('/api/code', files=upload, data={'target': 'django'}).status_code == 400
    bad = {'file': ('x.sql', b'SELECT 1;', 'application/sql')}
    assert client.post('/api/code', files=bad, data={'target': 'prisma'}).status_code == 400
