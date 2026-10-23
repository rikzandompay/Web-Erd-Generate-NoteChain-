# backend/sql_parser.py
"""
Custom SQL Parser — extracts tables, columns (type, key, NULL, default, comment)
and FK relationships from raw SQL CREATE TABLE statements using RegEx.
"""

import re
from typing import Any

_FOREIGN_KEY_PATTERN = re.compile(
    r'FOREIGN\s+KEY\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)\s*'
    r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)',
    re.IGNORECASE,
)
_ADD_PRIMARY_KEY_PATTERN = re.compile(r'ADD\s+PRIMARY\s+KEY\s*\(([^)]+)\)', re.IGNORECASE)
_DEFAULT_PATTERN = re.compile(
    r"\bDEFAULT\s+(\((?:[^()]|\([^()]*\))*\)|'(?:[^']|'')*'|[^\s,]+)", re.IGNORECASE)
_COLUMN_COMMENT_PATTERN = re.compile(r"\bCOMMENT\s+'((?:[^']|'')*)'", re.IGNORECASE)
_MARKER = re.compile(r'@@C(\d+)@@')


def strip_comments(sql: str) -> str:
    """Remove SQL comments: single-line (--) and multi-line (/* ... */)."""
    # Remove multi-line comments (non-greedy)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Remove single-line comments
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql


def _extract_comments(sql: str) -> tuple[str, dict[int, str]]:
    """
    Remove comments like strip_comments does, but keep the ones written after
    code on the same line (`email VARCHAR(100), -- login address`) as markers
    `@@C<n>@@`, so a column can still be given its description. Comments on a
    line of their own describe a section, not a column, and are dropped.
    """
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    comments: dict[int, str] = {}
    lines = []
    for line in sql.split('\n'):
        idx = line.find('--')
        if idx == -1:
            lines.append(line)
            continue
        before, text = line[:idx], line[idx + 2:].strip()
        if before.strip() and text:
            comments[len(comments)] = text
            before += f' @@C{len(comments) - 1}@@'
        lines.append(before)
    return '\n'.join(lines), comments


def parse_sql(sql: str) -> dict[str, Any]:
    """
    Parse SQL text and return a structured dict:
    {
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "type": "INT", "is_pk": True, "nullable": False,
                     "default": None, "unique": False, "auto_increment": True, "comment": ""},
                    {"name": "email", "type": "VARCHAR(255)", "is_pk": False, ...},
                ],
            }
        ],
        "relations": [
            {
                "from_table": "orders",
                "from_column": "user_id",
                "to_table": "users",
                "to_column": "id",
            }
        ],
    }
    """
    sql, comments = _extract_comments(sql)

    tables: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    # ── Extract CREATE TABLE blocks ──────────────────────────────────────
    create_table_pattern = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'[`"\[]?(\w+)[`"\]]?'        # table name
        r'\s*\((.*?)\)\s*;',           # body inside parentheses
        re.IGNORECASE | re.DOTALL,
    )

    for match in create_table_pattern.finditer(sql):
        table_name = match.group(1)
        body = match.group(2)

        columns: list[dict[str, Any]] = []
        primary_keys: list[str] = []

        # Split body into lines, handling nested parentheses properly
        lines = _split_definitions(body)

        for line in lines:
            # A comment written after the comma belongs to the column before it
            leading = _MARKER.match(line.lstrip())
            while leading and columns:
                _add_comment(columns[-1], comments[int(leading.group(1))])
                line = line.lstrip()[leading.end():]
                leading = _MARKER.match(line.lstrip())
            markers = [int(n) for n in _MARKER.findall(line)]
            line = _MARKER.sub('', line).strip()
            if not line:
                continue

            # ── PRIMARY KEY (standalone constraint) ──────────────────────
            pk_match = re.match(
                r'PRIMARY\s+KEY\s*\(([^)]+)\)',
                line,
                re.IGNORECASE,
            )
            if pk_match:
                pk_cols = [
                    c.strip().strip('`"[]') for c in pk_match.group(1).split(',')
                ]
                primary_keys.extend(pk_cols)
                continue

            # ── FOREIGN KEY constraint ───────────────────────────────────
            fk_match = re.match(
                r'(?:CONSTRAINT\s+[`"\[]?\w+[`"\]]?\s+)?'
                r'FOREIGN\s+KEY\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)\s*'
                r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)',
                line,
                re.IGNORECASE,
            )
            if fk_match:
                relations.append({
                    'from_table': table_name,
                    'from_column': fk_match.group(1),
                    'to_table': fk_match.group(2),
                    'to_column': fk_match.group(3),
                })
                continue

            # ── Skip other constraints (UNIQUE, INDEX, CHECK, KEY) ──────
            if re.match(
                r'(UNIQUE|INDEX|KEY|CHECK|CONSTRAINT)\b',
                line,
                re.IGNORECASE,
            ):
                continue

            # ── Regular column definition ────────────────────────────────
            col_match = re.match(
                r'[`"\[]?(\w+)[`"\]]?\s+'       # column name
                r'([A-Za-z]+(?:\s*\([^)]*\))?'   # type (+ optional params)
                r'(?:\s+UNSIGNED)?'               # optional UNSIGNED
                r')',
                line,
                re.IGNORECASE,
            )
            if col_match:
                col_name = col_match.group(1)
                col_type = _upper_outside_parens(col_match.group(2))
                rest = line[col_match.end():]

                # Inline PRIMARY KEY
                is_pk = bool(
                    re.search(r'\bPRIMARY\s+KEY\b', line, re.IGNORECASE)
                )

                # Inline REFERENCES (FK shorthand)
                inline_ref = re.search(
                    r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)',
                    line,
                    re.IGNORECASE,
                )
                if inline_ref:
                    relations.append({
                        'from_table': table_name,
                        'from_column': col_name,
                        'to_table': inline_ref.group(1),
                        'to_column': inline_ref.group(2),
                    })

                default = _DEFAULT_PATTERN.search(rest)
                column: dict[str, Any] = {
                    'name': col_name,
                    'type': col_type,
                    'is_pk': is_pk,
                    'nullable': not (is_pk or re.search(r'\bNOT\s+NULL\b', rest, re.IGNORECASE)),
                    'default': default.group(1).strip("'") if default else None,
                    'unique': bool(re.search(r'\bUNIQUE\b', rest, re.IGNORECASE)),
                    'auto_increment': bool(re.search(
                        r'\bAUTO_?INCREMENT\b|^SERIAL$|^BIGSERIAL$', rest + ' ' + col_type, re.IGNORECASE)),
                    'comment': '',
                }
                declared = _COLUMN_COMMENT_PATTERN.search(rest)
                if declared:
                    _add_comment(column, declared.group(1).replace("''", "'"))
                for n in markers:
                    _add_comment(column, comments[n])
                columns.append(column)

        # Mark standalone PKs
        for col in columns:
            if col['name'] in primary_keys:
                col['is_pk'] = True
                col['nullable'] = False

        tables.append({'name': table_name, 'columns': columns})

    # ── Keys added afterwards (dbdiagram.io / phpMyAdmin exports) ───────────
    # e.g. ALTER TABLE `a` ADD PRIMARY KEY (`id`),
    #                      ADD CONSTRAINT `fk` FOREIGN KEY (`b_id`) REFERENCES `b` (`id`);
    alter_table_pattern = re.compile(
        r'ALTER\s+TABLE\s+(?:ONLY\s+)?[`"\[]?(\w+)[`"\]]?(.*?);',
        re.IGNORECASE | re.DOTALL,
    )
    by_name = {t['name']: t for t in tables}
    for match in alter_table_pattern.finditer(sql):
        for fk_match in _FOREIGN_KEY_PATTERN.finditer(match.group(2)):
            relations.append({
                'from_table': match.group(1),
                'from_column': fk_match.group(1),
                'to_table': fk_match.group(2),
                'to_column': fk_match.group(3),
            })
        for pk_match in _ADD_PRIMARY_KEY_PATTERN.finditer(match.group(2)):
            wanted = {c.strip().strip('`"[]') for c in pk_match.group(1).split(',')}
            for col in by_name.get(match.group(1), {}).get('columns', []):
                if col['name'] in wanted:
                    col['is_pk'] = True
                    col['nullable'] = False

    if not tables:
        raise ValueError('No valid CREATE TABLE statements found in SQL file.')

    return {'tables': tables, 'relations': relations}


def _add_comment(column: dict[str, Any], text: str) -> None:
    column['comment'] = f"{column['comment']} {text}".strip() if column['comment'] else text.strip()


def _upper_outside_parens(text: str) -> str:
    """VARCHAR(100) stays as is apart from the keyword; ENUM('a','b') keeps its values' case."""
    out, depth = [], 0
    for ch in text:
        depth += ch == '('
        depth -= ch == ')'
        out.append(ch if depth else ch.upper())
    return ''.join(out)


def _split_definitions(body: str) -> list[str]:
    """
    Split the body of a CREATE TABLE statement by commas,
    respecting parentheses nesting (so `DECIMAL(10,2)` stays intact).
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []

    for char in body:
        if char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append(''.join(current))

    return parts
