# backend/data_dictionary.py
"""
Data dictionary (kamus data) from a parsed SQL schema: one table per SQL table
with the columns  No | Nama Kolom | Tipe Data | Kunci | Null | Default | Keterangan.

Three outputs from the same rows: a draw.io page (grid of cells), Markdown and
CSV for pasting into a report. "Keterangan" is only what the SQL itself says
(a trailing `-- comment` or COMMENT '...'); nothing is invented.
"""

import csv
import html
import io
import math
import textwrap
import xml.etree.ElementTree as ET
from typing import Any

from layout import PageBuilder  # type: ignore

HEADERS = ('No', 'Nama Kolom', 'Tipe Data', 'Kunci', 'Null', 'Default', 'Keterangan')

CHAR_W = 7
CELL_PAD = 20           # text padding inside a cell, both sides together
MIN_W = (50, 140, 140, 90, 60, 90, 160)
MAX_W = (50, 240, 240, 280, 60, 200, 320)
ROW_MIN_H = 30
LINE_H = 20
TABLE_GAP = 40
TITLE_H = 30

TITLE_STYLE = 'text;html=1;align=left;verticalAlign=middle;fontStyle=1;fontSize=14;strokeColor=none;fillColor=none;'
HEADER_STYLE = 'rounded=0;whiteSpace=wrap;html=1;align={a};verticalAlign=middle;spacingLeft=6;spacingRight=6;fontStyle=1;strokeWidth=2;'
CELL_STYLE = 'rounded=0;whiteSpace=wrap;html=1;align={a};verticalAlign=middle;spacingLeft=6;spacingRight=6;'
CENTRED = (0, 4)        # columns shown centred: No, Null


def dictionary_rows(schema: dict[str, Any]) -> list[tuple[str, list[tuple[str, ...]]]]:
    """[(table name, [row of 7 strings per column])] in the order of the SQL file."""
    foreign = {(r['from_table'], r['from_column']): f"{r['to_table']}.{r['to_column']}"
               for r in schema.get('relations', [])}
    out = []
    for table in schema.get('tables', []):
        rows = []
        for no, col in enumerate(table.get('columns', []), start=1):
            keys = []
            if col.get('is_pk'):
                keys.append('PK')
            target = foreign.get((table['name'], col['name']))
            if target:
                keys.append(f'FK -> {target}')
            rows.append((
                str(no),
                col['name'],
                col['type'],
                ', '.join(keys),
                'Ya' if col.get('nullable', True) else 'Tidak',
                '' if col.get('default') is None else str(col['default']),
                col.get('comment', ''),
            ))
        out.append((table['name'], rows))
    return out


# ── Text outputs ─────────────────────────────────────────────────────────────

def to_markdown(schema: dict[str, Any]) -> str:
    blocks = []
    for name, rows in dictionary_rows(schema):
        lines = [f'### Tabel: {name}', '',
                 '| ' + ' | '.join(HEADERS) + ' |',
                 '|' + '|'.join('---' for _ in HEADERS) + '|']
        for row in rows:
            lines.append('| ' + ' | '.join(_md_cell(c) for c in row) + ' |')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) + '\n'


def _md_cell(text: str) -> str:
    return text.replace('|', '\\|').replace('\n', ' ')


def to_csv(schema: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(('Tabel', *HEADERS))
    for name, rows in dictionary_rows(schema):
        for row in rows:
            writer.writerow((name, *row))
    return buffer.getvalue()


# ── draw.io page ─────────────────────────────────────────────────────────────

def build_dictionary_page(schema: dict[str, Any]) -> ET.Element:
    """One grid per table, all with the same column widths, stacked top to bottom."""
    tables = dictionary_rows(schema)
    widths = _column_widths(tables)

    page = PageBuilder()
    y = 0
    for name, rows in tables:
        page.vertex(html.escape(f'Tabel: {name}'), TITLE_STYLE, (0, y, sum(widths), TITLE_H))
        y += TITLE_H
        for row, is_header in [(HEADERS, True), *[(r, False) for r in rows]]:
            height = _row_height(row, widths)
            x = 0
            for i, (text, width) in enumerate(zip(row, widths)):
                align = 'center' if i in CENTRED else 'left'
                style = (HEADER_STYLE if is_header else CELL_STYLE).format(a=align)
                page.vertex(html.escape(text), style, (x, y, width, height))
                x += width
            y += height
        y += TABLE_GAP
    return page.to_model()


def _column_widths(tables: list[tuple[str, list[tuple[str, ...]]]]) -> list[int]:
    widths = []
    for i, header in enumerate(HEADERS):
        longest = max([len(header)] + [len(row[i]) for _, rows in tables for row in rows])
        want = int(math.ceil((longest * CHAR_W + CELL_PAD) / 10)) * 10
        widths.append(max(MIN_W[i], min(MAX_W[i], want)))
    return widths


def _row_height(row: tuple[str, ...], widths: list[int]) -> int:
    lines = max(len(textwrap.wrap(text, max(4, (w - CELL_PAD) // CHAR_W)) or ['']) for text, w in zip(row, widths))
    return max(ROW_MIN_H, int(math.ceil((LINE_H * lines + 10) / 10)) * 10)
