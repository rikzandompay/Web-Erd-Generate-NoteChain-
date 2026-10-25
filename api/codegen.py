# backend/codegen.py
"""
Starter code from a parsed SQL schema, without AI: the same schema always gives
the same files.

    laravel     database/migrations/*.php (parents before children) + app/Models/*.php
    prisma      prisma/schema.prisma
    sqlalchemy  app/models.py (SQLAlchemy 2.0, typed)

Conventions, so the files work as they are:
  • A single integer primary key is treated as auto-increment, also when the SQL
    dump adds AUTO_INCREMENT later with ALTER TABLE (which the parser does not read).
  • Relationship names come from the foreign key column: penulis_id → penulis(),
    diverifikasi_oleh → diverifikasiOleh(). The parent side is named after the child
    table, with the role added when the same child points at the parent twice.
"""

import keyword
import re
from datetime import date
from typing import Any

TARGETS = ('laravel', 'prisma', 'sqlalchemy')
PRISMA_PROVIDERS = {'postgresql': 'postgresql', 'mysql': 'mysql', 'sqlite': 'sqlite'}

_CREATED = ('created_at', 'dibuat_pada')
_UPDATED = ('updated_at', 'diperbarui_pada')


# ── Reading the schema ───────────────────────────────────────────────────────

def column_kind(sql_type: str) -> dict[str, Any]:
    """'DECIMAL(10, 2)' → {'kind': 'decimal', 'args': ['10', '2'], 'unsigned': False}; one neutral vocabulary."""
    t = sql_type.strip()
    m = re.match(r'^([A-Za-z]+)(?:\s+PRECISION)?\s*(?:\((.*)\))?\s*(UNSIGNED)?', t, re.IGNORECASE)
    base = (m.group(1) if m else t).lower()
    raw_args = (m.group(2) or '') if m else ''
    unsigned = bool(m and m.group(3)) or 'unsigned' in t.lower()
    args = [a.strip().strip("'\"") for a in re.findall(r"'(?:[^']|'')*'|[^,]+", raw_args)] if raw_args else []
    kind = {
        'int': 'int', 'integer': 'int', 'mediumint': 'int', 'smallint': 'smallint', 'bigint': 'bigint',
        'serial': 'int', 'bigserial': 'bigint', 'smallserial': 'smallint',
        'boolean': 'bool', 'bool': 'bool',
        'decimal': 'decimal', 'numeric': 'decimal', 'money': 'decimal',
        'float': 'float', 'real': 'float', 'double': 'double',
        'varchar': 'string', 'nvarchar': 'string', 'character': 'string', 'char': 'char', 'nchar': 'char',
        'text': 'text', 'tinytext': 'text', 'mediumtext': 'mediumtext', 'longtext': 'longtext', 'citext': 'text',
        'date': 'date', 'datetime': 'datetime', 'timestamp': 'timestamp', 'timestamptz': 'timestamp',
        'time': 'time', 'year': 'year',
        'json': 'json', 'jsonb': 'json', 'uuid': 'uuid', 'enum': 'enum', 'set': 'string',
        'blob': 'binary', 'longblob': 'binary', 'mediumblob': 'binary', 'bytea': 'binary',
        'binary': 'binary', 'varbinary': 'binary', 'bit': 'bool',
    }.get(base, 'string')
    if base == 'tinyint':
        kind = 'bool' if args == ['1'] else 'tinyint'
    return {'kind': kind, 'args': args, 'unsigned': unsigned, 'serial': base.endswith('serial')}


def _precision(args: list[str], default: tuple[str, str] = ('10', '2')) -> tuple[str, str]:
    """DECIMAL(10, 2) → (10, 2); DECIMAL(10) has scale 0; plain DECIMAL gets the default."""
    if not args:
        return default
    return args[0], args[1] if len(args) > 1 else '0'


def _default(col: dict[str, Any]) -> tuple[str, Any]:
    """('none' | 'now' | 'number' | 'bool' | 'text', value) from the column's DEFAULT."""
    raw = col.get('default')
    if raw is None:
        return 'none', None
    value = str(raw).strip().strip('()').strip()
    upper = value.upper()
    if upper == 'NULL' or not value:
        return 'none', None
    if upper.startswith(('CURRENT_TIMESTAMP', 'NOW', 'LOCALTIMESTAMP', 'CURRENT_DATE')):
        return 'now', None
    kind = column_kind(col['type'])['kind']
    if kind == 'bool':
        return 'bool', upper in ('1', 'TRUE', "B'1'")
    if re.fullmatch(r'-?\d+(\.\d+)?', value):
        return 'number', value
    return 'text', value


class Schema:
    """The parsed schema with the questions every generator asks answered once."""

    def __init__(self, parsed: dict[str, Any]):
        self.tables = parsed['tables']
        self.by_name = {t['name']: t for t in self.tables}
        self.relations = [r for r in parsed['relations'] if r['from_table'] in self.by_name and r['to_table'] in self.by_name]
        self.fk = {(r['from_table'], r['from_column']): r for r in self.relations}

    def pk(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        return [c for c in table['columns'] if c.get('is_pk')]

    def auto_pk(self, table: dict[str, Any]) -> dict[str, Any] | None:
        """The single integer primary key, which is treated as auto-increment."""
        pk = self.pk(table)
        if len(pk) == 1 and column_kind(pk[0]['type'])['kind'] in ('int', 'bigint', 'smallint') \
                and (table['name'], pk[0]['name']) not in self.fk:
            return pk[0]
        return None

    def column(self, table: str, name: str) -> dict[str, Any] | None:
        return next((c for c in self.by_name[table]['columns'] if c['name'] == name), None)

    def order(self) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
        """Tables with parents first; plus the foreign keys that point forward (cycles) and must be added later."""
        done: list[str] = []
        pending = [t['name'] for t in self.tables]
        while pending:
            ready = [n for n in pending if all(r['to_table'] in done or r['to_table'] == n
                                               for r in self.relations if r['from_table'] == n)]
            nxt = ready[0] if ready else pending[0]              # a cycle: take the first and defer its keys
            done.append(nxt)
            pending.remove(nxt)
        position = {n: i for i, n in enumerate(done)}
        deferred = {(r['from_table'], r['from_column']) for r in self.relations
                    if position[r['to_table']] > position[r['from_table']]}
        return [self.by_name[n] for n in done], deferred

    def children(self, parent: str) -> list[dict[str, Any]]:
        return [r for r in self.relations if r['to_table'] == parent]


# ── Names ────────────────────────────────────────────────────────────────────

def _words(name: str) -> list[str]:
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return [w for w in re.split(r'[^A-Za-z0-9]+', name) if w]


def singular(word: str) -> str:
    """English plurals only (users → user, categories → category); Indonesian words stay as they are."""
    w = word.lower()
    if w.endswith('ies') and len(w) > 4:
        return word[:-3] + 'y'
    if w.endswith('s') and len(w) > 3 and not w.endswith(('ss', 'us', 'is', 'as', 'os')):
        return word[:-1]
    return word


def class_name(table: str) -> str:
    words = _words(table) or ['Model']
    words[-1] = singular(words[-1])
    name = ''.join(w[:1].upper() + w[1:].lower() for w in words)
    return name if name[0].isalpha() else 'T' + name


def camel(name: str) -> str:
    words = [w.lower() for w in _words(name)] or ['relasi']
    out = words[0] + ''.join(w[:1].upper() + w[1:] for w in words[1:])
    return out if out[0].isalpha() else 'r' + out


def role_of(column: str) -> str:
    """penulis_id → penulis, id_pelanggan → pelanggan, diverifikasi_oleh → diverifikasi_oleh."""
    words = [w for w in _words(column) if w.lower() not in ('id', 'fk', 'kode')]
    return '_'.join(words).lower() or column.lower()


def _relation_names(schema: Schema) -> tuple[dict, dict]:
    """
    Names of the relationship on both sides of every foreign key:
    child side (belongs to the parent) and parent side (has many children).
    """
    child_side, parent_side = {}, {}
    for table in schema.tables:
        columns = {c['name'].lower() for c in table['columns']}
        used = set(columns)
        for r in (r for r in schema.relations if r['from_table'] == table['name']):
            name = role_of(r['from_column'])
            if name in used:                                   # diverifikasi_oleh → diverifikasi_oleh_pengguna
                name = f"{name}_{r['to_table'].lower()}"
            while name in used:
                name += '_ref'
            used.add(name)
            child_side[(r['from_table'], r['from_column'])] = name
    for parent in schema.tables:
        rels = schema.children(parent['name'])
        used = {c['name'].lower() for c in parent['columns']} | {
            n for (t, _), n in child_side.items() if t == parent['name']}
        count = {}
        for r in rels:
            count[r['from_table']] = count.get(r['from_table'], 0) + 1
        for r in rels:
            name = r['from_table'].lower()
            if count[r['from_table']] > 1 or r['from_table'] == parent['name']:
                name = f"{r['from_table']}_{role_of(r['from_column'])}".lower()
            while name in used:
                name += '_list'
            used.add(name)
            parent_side[(r['from_table'], r['from_column'])] = name
    return child_side, parent_side


def _header(comment: str, source: str) -> str:
    return f'{comment} Dibuat oleh ERD Generator dari {source}. Periksa sebelum dipakai.'


# ── Laravel ──────────────────────────────────────────────────────────────────

def _php(value: str) -> str:
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


def _laravel_type(col: dict[str, Any]) -> str:
    k = column_kind(col['type'])
    name, args, kind = _php(col['name']), k['args'], k['kind']
    unsigned = k['unsigned']
    if kind in ('int', 'smallint', 'bigint', 'tinyint'):
        method = {'int': 'integer', 'smallint': 'smallInteger', 'bigint': 'bigInteger', 'tinyint': 'tinyInteger'}[kind]
        if unsigned:
            method = 'unsigned' + method[0].upper() + method[1:]
        return f'{method}({name})'
    if kind == 'decimal':
        p, s = _precision(args, ('8', '2'))
        return f'decimal({name}, {p}, {s})'
    if kind in ('string', 'char'):
        length = args[0] if args and args[0].isdigit() else None
        method = 'string' if kind == 'string' else 'char'
        return f'{method}({name}, {length})' if length else f'{method}({name})'
    if kind == 'enum':
        return f"enum({name}, [{', '.join(_php(a) for a in args)}])"
    return {
        'bool': f'boolean({name})', 'float': f'float({name})', 'double': f'double({name})',
        'text': f'text({name})', 'mediumtext': f'mediumText({name})', 'longtext': f'longText({name})',
        'date': f'date({name})', 'datetime': f'dateTime({name})', 'timestamp': f'timestamp({name})',
        'time': f'time({name})', 'year': f'year({name})', 'json': f'json({name})', 'uuid': f'uuid({name})',
        'binary': f'binary({name})',
    }.get(kind, f'string({name})')


def _laravel_modifiers(col: dict[str, Any], skip_nullable: bool = False) -> str:
    out = ''
    if col.get('nullable') and not col.get('is_pk') and not skip_nullable:
        out += '->nullable()'
    if col.get('unique') and not col.get('is_pk'):
        out += '->unique()'
    kind, value = _default(col)
    if kind == 'now':
        out += '->useCurrent()'
    elif kind == 'bool':
        out += f"->default({'true' if value else 'false'})"
    elif kind == 'number':
        out += f'->default({value})'
    elif kind == 'text':
        out += f'->default({_php(value)})'
    if col.get('comment'):
        out += f"->comment({_php(col['comment'])})"
    return out


def _laravel_timestamps(table: dict[str, Any]) -> str:
    """'laravel' when created_at/updated_at exist, 'indonesian' for dibuat_pada/diperbarui_pada, else ''."""
    names = {c['name'] for c in table['columns']}
    if {'created_at', 'updated_at'} <= names:
        return 'laravel'
    if {'dibuat_pada', 'diperbarui_pada'} <= names:
        return 'indonesian'
    return ''


def laravel_files(schema: Schema, source: str, today: date) -> list[dict[str, str]]:
    ordered, deferred = schema.order()
    stamp = today.strftime('%Y_%m_%d')
    files = []
    for i, table in enumerate(ordered, start=1):
        lines = []
        auto = schema.auto_pk(table)
        pk = schema.pk(table)
        stamps = _laravel_timestamps(table)
        names = {c['name'] for c in table['columns']}
        for col in table['columns']:
            name = col['name']
            if stamps == 'laravel' and name in ('created_at', 'updated_at'):
                continue
            if name == 'deleted_at' and column_kind(col['type'])['kind'] in ('timestamp', 'datetime'):
                lines.append('$table->softDeletes();')
                continue
            if auto is col:
                lines.append('$table->id();' if name == 'id' else f'$table->id({_php(name)});')
                continue
            rel = schema.fk.get((table['name'], name))
            target = schema.column(rel['to_table'], rel['to_column']) if rel else None
            parent_auto = rel and schema.auto_pk(schema.by_name[rel['to_table']]) is target
            if rel and parent_auto and (table['name'], name) not in deferred:
                lines.append(f"$table->foreignId({_php(name)}){'->nullable()' if col.get('nullable') else ''}"
                             f"{_laravel_modifiers(col, skip_nullable=True)}"
                             f"->constrained({_php(rel['to_table'])}, {_php(rel['to_column'])});")
                continue
            if rel and parent_auto:                              # deferred: the parent table comes later
                lines.append(f"$table->unsignedBigInteger({_php(name)}){_laravel_modifiers(col)};")
                continue
            lines.append(f'$table->{_laravel_type(col)}{_laravel_modifiers(col)};')
            if rel and (table['name'], name) not in deferred:
                lines.append(f"$table->foreign({_php(name)})->references({_php(rel['to_column'])})"
                             f"->on({_php(rel['to_table'])});")
        if len(pk) > 1:
            lines.append(f"$table->primary([{', '.join(_php(c['name']) for c in pk)}]);")
        elif pk and auto is None and pk[0]['name'] in names:
            lines.append(f"$table->primary({_php(pk[0]['name'])});")
        if stamps == 'laravel':
            lines.append('$table->timestamps();')
        body = '\n'.join(f'            {line}' for line in lines)
        files.append({
            'path': f"database/migrations/{stamp}_{i:06d}_create_{table['name'].lower()}_table.php",
            'content': f"""<?php

// {_header('', source).strip()}

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
        Schema::create({_php(table['name'])}, function (Blueprint $table) {{
{body}
        }});
    }}

    public function down(): void
    {{
        Schema::dropIfExists({_php(table['name'])});
    }}
}};
""",
        })
    if deferred:
        adds, drops = [], []
        for t, c in sorted(deferred):
            r = schema.fk[(t, c)]
            adds.append(f"""        Schema::table({_php(t)}, function (Blueprint $table) {{
            $table->foreign({_php(c)})->references({_php(r['to_column'])})->on({_php(r['to_table'])});
        }});""")
            drops.append(f"""        Schema::table({_php(t)}, function (Blueprint $table) {{
            $table->dropForeign([{_php(c)}]);
        }});""")
        files.append({
            'path': f'database/migrations/{stamp}_{len(ordered) + 1:06d}_add_foreign_keys.php',
            'content': f"""<?php

// {_header('', source).strip()}
// Foreign key yang tabel induknya dibuat lebih belakang (relasi melingkar).

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
{chr(10).join(adds)}
    }}

    public function down(): void
    {{
{chr(10).join(drops)}
    }}
}};
""",
        })
    files += laravel_models(schema, source)
    return files


def laravel_models(schema: Schema, source: str) -> list[dict[str, str]]:
    child_side, parent_side = _relation_names(schema)
    files = []
    for table in schema.tables:
        cls = class_name(table['name'])
        auto, pk = schema.auto_pk(table), schema.pk(table)
        stamps = _laravel_timestamps(table)
        soft = any(c['name'] == 'deleted_at' for c in table['columns'])
        props = [f"    protected $table = {_php(table['name'])};"]
        if len(pk) == 1 and pk[0]['name'] != 'id':
            props.append(f"    protected $primaryKey = {_php(pk[0]['name'])};")
        if len(pk) == 1 and auto is None:
            props.append('    public $incrementing = false;')
            if column_kind(pk[0]['type'])['kind'] not in ('int', 'bigint', 'smallint'):
                props.append("    protected $keyType = 'string';")
        if stamps == 'indonesian':
            props += ["    const CREATED_AT = 'dibuat_pada';", "    const UPDATED_AT = 'diperbarui_pada';"]
        elif not stamps:
            props.append('    public $timestamps = false;')
        skip = {c['name'] for c in pk if c is auto} | set(_CREATED + _UPDATED) | {'deleted_at'}
        fillable = [c['name'] for c in table['columns'] if c['name'] not in skip]
        props.append('    protected $fillable = [\n' + ''.join(f'        {_php(n)},\n' for n in fillable) + '    ];')
        casts = []
        for c in table['columns']:
            k = column_kind(c['type'])
            cast = {'bool': 'boolean', 'date': 'date', 'datetime': 'datetime', 'timestamp': 'datetime', 'json': 'array'}.get(k['kind'])
            if k['kind'] == 'decimal':
                cast = f"decimal:{_precision(k['args'], ('8', '2'))[1]}"
            if cast and c['name'] not in ('created_at', 'updated_at', 'deleted_at'):
                casts.append(f"            {_php(c['name'])} => {_php(cast)},")
        if casts:
            props.append('    protected function casts(): array\n    {\n        return [\n' + '\n'.join(casts) + '\n        ];\n    }')

        methods, imports = [], {'Illuminate\\Database\\Eloquent\\Model'}
        for r in (r for r in schema.relations if r['from_table'] == table['name']):
            imports.add('Illuminate\\Database\\Eloquent\\Relations\\BelongsTo')
            methods.append(f"""    public function {camel(child_side[(r['from_table'], r['from_column'])])}(): BelongsTo
    {{
        return $this->belongsTo({class_name(r['to_table'])}::class, {_php(r['from_column'])}, {_php(r['to_column'])});
    }}""")
        for r in schema.children(table['name']):
            imports.add('Illuminate\\Database\\Eloquent\\Relations\\HasMany')
            methods.append(f"""    public function {camel(parent_side[(r['from_table'], r['from_column'])])}(): HasMany
    {{
        return $this->hasMany({class_name(r['from_table'])}::class, {_php(r['from_column'])}, {_php(r['to_column'])});
    }}""")
        uses = ''
        if soft:
            imports.add('Illuminate\\Database\\Eloquent\\SoftDeletes')
            uses = '    use SoftDeletes;\n\n'
        body = '\n\n'.join(props + methods)
        files.append({
            'path': f'app/Models/{cls}.php',
            'content': f"""<?php

// {_header('', source).strip()}

namespace App\\Models;

{chr(10).join(f'use {i};' for i in sorted(imports))}

class {cls} extends Model
{{
{uses}{body}
}}
""",
        })
    return files


# ── Prisma ───────────────────────────────────────────────────────────────────

def _prisma_field_name(name: str) -> str:
    return name if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) else 'f_' + re.sub(r'\W', '_', name)


def _prisma_type(col: dict[str, Any], provider: str) -> tuple[str, str]:
    """(Prisma type, native @db attribute or '')."""
    k = column_kind(col['type'])
    kind, args = k['kind'], k['args']
    native = provider in ('postgresql', 'mysql')
    if kind in ('int', 'tinyint'):
        return 'Int', ''
    if kind == 'smallint':
        return 'Int', '@db.SmallInt' if native else ''
    if kind == 'bigint':
        return 'BigInt', ''
    if kind == 'bool':
        return 'Boolean', ''
    if kind == 'decimal':
        p, s = _precision(args)
        return 'Decimal', f'@db.Decimal({p}, {s})' if native else ''
    if kind in ('float', 'double'):
        return 'Float', ''
    if kind in ('string', 'char'):
        length = args[0] if args and args[0].isdigit() else None
        tag = 'VarChar' if kind == 'string' else 'Char'
        return 'String', f'@db.{tag}({length})' if native and length else ''
    if kind in ('text', 'mediumtext', 'longtext'):
        tag = {'mediumtext': 'MediumText', 'longtext': 'LongText'}.get(kind, 'Text') if provider == 'mysql' else 'Text'
        return 'String', f'@db.{tag}' if native else ''
    if kind == 'date':
        return 'DateTime', '@db.Date' if native else ''
    if kind == 'time':
        return 'DateTime', '@db.Time' if native else ''
    if kind in ('datetime', 'timestamp'):
        return 'DateTime', ''
    if kind == 'year':
        return 'Int', ''
    if kind == 'json':
        return ('Json', '') if provider != 'sqlite' else ('String', '')
    if kind == 'uuid':
        return 'String', '@db.Uuid' if provider == 'postgresql' else ''
    if kind == 'binary':
        return 'Bytes', ''
    return 'String', ''                                         # enum and anything unknown


def prisma_files(schema: Schema, source: str, provider: str) -> list[dict[str, str]]:
    provider = PRISMA_PROVIDERS.get(provider, 'postgresql')
    child_side, parent_side = _relation_names(schema)
    # Named relations where one table pair has more than one relation, or a table points at itself
    pair_count: dict[tuple[str, str], int] = {}
    for r in schema.relations:
        key = tuple(sorted((r['from_table'], r['to_table'])))
        pair_count[key] = pair_count.get(key, 0) + 1

    def relation_name(r):
        key = tuple(sorted((r['from_table'], r['to_table'])))
        if pair_count[key] > 1 or r['from_table'] == r['to_table']:
            return f"{r['from_table']}_{r['from_column']}"
        return ''

    blocks = [f"""// {_header('', source).strip()}

generator client {{
  provider = "prisma-client-js"
}}

datasource db {{
  provider = "{provider}"
  url      = env("DATABASE_URL")
}}"""]
    for table in schema.tables:
        auto, pk = schema.auto_pk(table), schema.pk(table)
        rows: list[list[str]] = []
        for col in table['columns']:
            ptype, native = _prisma_type(col, provider)
            optional = col.get('nullable') and not col.get('is_pk')
            attrs = []
            if len(pk) == 1 and col is pk[0]:
                attrs.append('@id')
            kind, value = _default(col)
            if auto is col:
                attrs.append('@default(autoincrement())')
            elif kind == 'now' and ptype == 'DateTime':
                attrs.append('@default(now())')
            elif kind == 'bool':
                attrs.append(f"@default({'true' if value else 'false'})")
            elif kind == 'number' and ptype in ('Int', 'BigInt', 'Float', 'Decimal'):
                attrs.append(f'@default({value})')
            elif kind == 'text' and ptype == 'String':
                attrs.append('@default("' + value.replace('"', '\\"') + '")')
            if col['name'] in _UPDATED and ptype == 'DateTime':
                attrs.append('@updatedAt')
            if col.get('unique') and not col.get('is_pk'):
                attrs.append('@unique')
            if native:
                attrs.append(native)
            field = _prisma_field_name(col['name'])
            if field != col['name']:
                attrs.append(f'@map("{col["name"]}")')
            comment = f"  /// {col['comment']}" if col.get('comment') else ''
            if column_kind(col['type'])['kind'] == 'enum':
                comment = f"  /// pilihan: {', '.join(column_kind(col['type'])['args'])}"
            rows.append([field, ptype + ('?' if optional else ''), ' '.join(attrs), comment])
        for r in (r for r in schema.relations if r['from_table'] == table['name']):
            col = schema.column(table['name'], r['from_column'])
            name = relation_name(r)
            label = f'"{name}", ' if name else ''
            rows.append([child_side[(r['from_table'], r['from_column'])],
                         class_name(r['to_table']) + ('?' if col and col.get('nullable') else ''),
                         f"@relation({label}fields: [{_prisma_field_name(r['from_column'])}], "
                         f"references: [{_prisma_field_name(r['to_column'])}])", ''])
        for r in schema.children(table['name']):
            name = relation_name(r)
            fk_col = schema.column(r['from_table'], r['from_column']) or {}
            child_pk = schema.pk(schema.by_name[r['from_table']])
            one_to_one = fk_col.get('unique') or (len(child_pk) == 1 and child_pk[0] is fk_col)
            rows.append([parent_side[(r['from_table'], r['from_column'])],
                         class_name(r['from_table']) + ('?' if one_to_one else '[]'),
                         f'@relation("{name}")' if name else '', ''])
        w0 = max(len(r[0]) for r in rows)
        w1 = max(len(r[1]) for r in rows)
        lines = [f'  {f.ljust(w0)} {t.ljust(w1)} {a}'.rstrip() + c for f, t, a, c in rows]
        if len(pk) > 1:
            lines += ['', f"  @@id([{', '.join(_prisma_field_name(c['name']) for c in pk)}])"]
        lines.append(f'  @@map("{table["name"]}")')
        if not pk and not any(c.get('unique') for c in table['columns']):
            lines += ['  /// Tabel tanpa PRIMARY KEY: Prisma tidak bisa memakainya sampai kunci ditambahkan.', '  @@ignore']
        blocks.append(f'model {class_name(table["name"])} {{\n' + '\n'.join(lines) + '\n}')
    return [{'path': 'prisma/schema.prisma', 'content': '\n\n'.join(blocks) + '\n'}]


# ── SQLAlchemy ───────────────────────────────────────────────────────────────

def _py_name(name: str) -> str:
    out = re.sub(r'\W', '_', name)
    if not out or out[0].isdigit():
        out = 'c_' + out
    return out + '_' if keyword.iskeyword(out) or out in ('metadata', 'registry') else out


def _sa_type(col: dict[str, Any], table: str) -> tuple[str, str, set[str]]:
    """(python annotation, SQLAlchemy type expression, sqlalchemy imports)."""
    k = column_kind(col['type'])
    kind, args = k['kind'], k['args']
    if kind in ('int', 'tinyint', 'year'):
        return 'int', 'Integer', {'Integer'}
    if kind == 'smallint':
        return 'int', 'SmallInteger', {'SmallInteger'}
    if kind == 'bigint':
        return 'int', 'BigInteger', {'BigInteger'}
    if kind == 'bool':
        return 'bool', 'Boolean', {'Boolean'}
    if kind == 'decimal':
        p, s = _precision(args)
        return 'Decimal', f'Numeric({p}, {s})', {'Numeric'}
    if kind == 'float':
        return 'float', 'Float', {'Float'}
    if kind == 'double':
        return 'float', 'Double', {'Double'}
    if kind in ('string', 'char', 'uuid'):
        length = args[0] if args and args[0].isdigit() else ('36' if kind == 'uuid' else '255')
        return 'str', f'String({length})', {'String'}
    if kind in ('text', 'mediumtext', 'longtext'):
        return 'str', 'Text', {'Text'}
    if kind == 'date':
        return 'date', 'Date', {'Date'}
    if kind in ('datetime', 'timestamp'):
        return 'datetime', 'DateTime', {'DateTime'}
    if kind == 'time':
        return 'time', 'Time', {'Time'}
    if kind == 'json':
        return 'dict', 'JSON', {'JSON'}
    if kind == 'enum':
        values = ', '.join(repr(a) for a in args)
        return 'str', f"Enum({values}, name={repr(f'{table}_{col['name']}'.lower())})", {'Enum'}
    if kind == 'binary':
        return 'bytes', 'LargeBinary', {'LargeBinary'}
    return 'str', 'String(255)', {'String'}


def sqlalchemy_files(schema: Schema, source: str) -> list[dict[str, str]]:
    child_side, parent_side = _relation_names(schema)
    imports: set[str] = set()
    uses_func = False
    classes = []
    for table in schema.tables:
        cls = class_name(table['name'])
        pk = schema.pk(table)
        lines = [f'class {cls}(Base):', f"    __tablename__ = {table['name']!r}", '']
        attr = {c['name']: _py_name(c['name']) for c in table['columns']}
        for col in table['columns']:
            hint, sa_type, needs = _sa_type(col, table['name'])
            imports |= needs
            args = []
            rel = schema.fk.get((table['name'], col['name']))
            if attr[col['name']] != col['name']:
                args.append(repr(col['name']))
            args.append(sa_type)
            if rel:
                imports.add('ForeignKey')
                args.append(f"ForeignKey({repr(rel['to_table'] + '.' + rel['to_column'])})")
            if col.get('is_pk'):
                args.append('primary_key=True')
            if col.get('unique') and not col.get('is_pk'):
                args.append('unique=True')
            kind, value = _default(col)
            if kind == 'now':
                args.append('server_default=func.now()')
                uses_func = True
            elif kind == 'bool':
                args.append(f"server_default={'true' if value else 'false'}()")
                imports.add('true' if value else 'false')
            elif kind in ('number', 'text'):
                args.append(f'server_default={value!r}')
            if col.get('comment'):
                args.append(f"comment={col['comment']!r}")
            optional = col.get('nullable') and not col.get('is_pk')
            annotation = f'Optional[{hint}]' if optional else hint
            lines.append(f"    {attr[col['name']]}: Mapped[{annotation}] = mapped_column({', '.join(args)})")
        rel_lines = []
        for r in (r for r in schema.relations if r['from_table'] == table['name']):
            name = _py_name(child_side[(r['from_table'], r['from_column'])])
            col = schema.column(table['name'], r['from_column'])
            target = class_name(r['to_table'])
            hint = f"Optional['{target}']" if col and col.get('nullable') else f"'{target}'"
            back = _py_name(parent_side[(r['from_table'], r['from_column'])])
            extra = f", remote_side=[{attr[r['to_column']]}]" if r['to_table'] == r['from_table'] else ''
            rel_lines.append(f"    {name}: Mapped[{hint}] = relationship(back_populates={back!r}, "
                             f"foreign_keys=[{attr[r['from_column']]}]{extra})")
        for r in schema.children(table['name']):
            name = _py_name(parent_side[(r['from_table'], r['from_column'])])
            child_cls = class_name(r['from_table'])
            child_attr = _py_name(r['from_column'])
            back = _py_name(child_side[(r['from_table'], r['from_column'])])
            rel_lines.append(f"    {name}: Mapped[list['{child_cls}']] = relationship(back_populates={back!r}, "
                             f"foreign_keys='{child_cls}.{child_attr}')")
        if rel_lines:
            lines += [''] + rel_lines
        if not pk:
            lines.append("    # Tabel ini tidak punya PRIMARY KEY; SQLAlchemy membutuhkannya. Tambahkan dulu.")
        classes.append('\n'.join(lines))
    sa_imports = ', '.join(sorted(imports | ({'func'} if uses_func else set()), key=str.lower))
    head = f'''# {_header('', source).strip()}

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import {sa_imports}
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass
'''
    return [{'path': 'app/models.py', 'content': head + '\n\n' + '\n\n\n'.join(classes) + '\n'}]


# ── Entry point ──────────────────────────────────────────────────────────────

def generate_code(parsed: dict[str, Any], target: str, source: str = 'schema.sql',
                  database: str = 'postgresql', today: date | None = None) -> list[dict[str, str]]:
    """Files ({'path', 'content'}) of starter code for `target` from a parse_sql() result."""
    schema = Schema(parsed)
    if target == 'laravel':
        return laravel_files(schema, source, today or date.today())
    if target == 'prisma':
        return prisma_files(schema, source, database.lower())
    if target == 'sqlalchemy':
        return sqlalchemy_files(schema, source)
    raise ValueError(f'Target "{target}" belum didukung. Pilih: {", ".join(TARGETS)}.')
