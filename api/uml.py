# backend/uml.py
"""
UML text → .drawio. The text may hold several diagrams, each starting with a
`=== Page name` line; every diagram becomes its own page (tab) in one file.
A bad line is reported with its line number and never stops the other pages.
"""

import base64
import re
import urllib.parse
import zlib
from typing import Any

from activity import build_activity_page  # type: ignore
from class_diagram import build_class_text_page  # type: ignore
from layout import build_mxfile  # type: ignore
from sequence import build_sequence_page  # type: ignore
from usecase import build_usecase_page  # type: ignore

# Diagram type → builder(title, numbered lines) → (mxGraphModel | None, [(line, reason)])
DIAGRAM_BUILDERS = {
    'sequence': build_sequence_page,
    'activity': build_activity_page,
    'class': build_class_text_page,
    'usecase': build_usecase_page,
}

_PAGE_HEADER = re.compile(r'^\s*===\s*(.*?)\s*$')


def split_pages(text: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """Split the text at `=== Name` lines into (name, [(line number, line)])."""
    pages: list[tuple[str, list[tuple[int, str]]]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        header = _PAGE_HEADER.match(line)
        stripped = line.strip()
        if header:
            pages.append((header.group(1) or f'Diagram {len(pages) + 1}', []))
        elif pages:
            # If the current page still has the default "Diagram X" name and a title is given, adopt it
            if pages[-1][0].startswith('Diagram ') and stripped.lower().startswith('title '):
                t_val = stripped[6:].strip()
                if t_val:
                    pages[-1] = (t_val, pages[-1][1])
            pages[-1][1].append((lineno, line))
        elif stripped and not stripped.startswith("'") and not stripped.startswith('//'):
            # Text before the first === header
            initial_name = 'Diagram 1'
            if stripped.lower().startswith('title '):
                t_val = stripped[6:].strip()
                if t_val:
                    initial_name = t_val
            pages.append((initial_name, [(lineno, line)]))
    return pages


def generate_uml(kind: str, text: str) -> dict[str, Any]:
    """Build every page in `text` with the `kind` builder; report bad lines per page."""
    builder = DIAGRAM_BUILDERS[kind]
    pages, errors = [], []
    for title, lines in split_pages(text):
        model, page_errors = builder(title, lines)
        errors += [{'page': title, 'line': line, 'message': reason} for line, reason in page_errors]
        if model is not None:
            pages.append((title, model))

    xml = build_mxfile(pages) if pages else None
    return {
        'pages': [title for title, _ in pages],
        'errors': sorted(errors, key=lambda e: e['line']),
        'xml': xml,
        'open_url': drawio_url(xml) if xml else None,
    }


def drawio_url(xml: str) -> str:
    """
    Link that opens the file in app.diagrams.net, packed the way draw.io packs
    its own `#R` links: URI-encode, raw-deflate, then base64.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = compressor.compress(urllib.parse.quote(xml, safe="-_.!~*'()").encode('ascii'))
    packed += compressor.flush()
    return 'https://app.diagrams.net/#R' + urllib.parse.quote(base64.b64encode(packed).decode('ascii'), safe='')
