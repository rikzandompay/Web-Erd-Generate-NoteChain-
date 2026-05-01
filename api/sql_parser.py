# backend/sql_parser.py
"""
Custom SQL Parser — extracts tables, columns, types, PKs, and FK relationships
from raw SQL CREATE TABLE statements using RegEx.
"""

import re
from typing import Any


def strip_comments(sql: str) -> str:
    """Remove SQL comments: single-line (--) and multi-line (/* ... */)."""
    # Remove multi-line comments (non-greedy)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Remove single-line comments
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql


def parse_sql(sql: str) -> dict[str, Any]:
    """
    Parse SQL text and return a structured dict:
    {
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "type": "INT", "is_pk": True},
                    {"name": "email", "type": "VARCHAR(255)", "is_pk": False},
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
    sql = strip_comments(sql)

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
            line = line.strip()
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
                col_type = col_match.group(2).upper()

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

                columns.append({
                    'name': col_name,
                    'type': col_type,
                    'is_pk': is_pk,
                })

        # Mark standalone PKs
        for col in columns:
            if col['name'] in primary_keys:
                col['is_pk'] = True

        tables.append({'name': table_name, 'columns': columns})

    if not tables:
        raise ValueError('No valid CREATE TABLE statements found in SQL file.')

    return {'tables': tables, 'relations': relations}


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
