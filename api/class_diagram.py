# backend/class_diagram.py
"""
UML class diagram — from a parsed SQL schema (one class per table) or from
PlantUML-like text — laid out on the same grid engine as the ERD.

  • Class    → draw.io stacked swimlane: name / attributes / separator / methods
  • Relation → orthogonal line with multiplicities at its ends; association,
               inheritance, realization, composition, aggregation or dependency

Text format:

    class bahan {
      - id : int
      + create()
    }
    bahan "1" -- "0..*" stok_masuk : memiliki
    bahan <|-- bahan_kering        ' inheritance (bahan_kering extends bahan)
    order *-- order_item           ' composition, filled diamond at order
    order o-- customer             ' aggregation, hollow diamond at order
    order ..> payment              ' dependency
"""

import html
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from layout import (  # type: ignore
    GRID, OPPOSITE, GridGeometry, Lane, LanePlanner, PageBuilder, Rect, assign_grid,
    assign_ports, edge_style, half_steps, port_point, toward,
)

CLASS_MIN_W = 160       # uniform class width range (widest class wins)
CLASS_MAX_W = 300
CHAR_W = 7              # rough width of one character at the default font size
HEADER_H = 30           # class name row
ROW_H = 20              # one attribute / method row
SEPARATOR_H = 10        # line between attributes and methods
CLASS_GAP = 80          # space between neighbouring classes
GAP_CLEAR = 30          # space between a gap's lanes and the classes beside it

CRUD_METHODS = ('create', 'read', 'update', 'delete')

CLASS_STYLE = (
    'swimlane;fontStyle=1;align=center;verticalAlign=top;childLayout=stackLayout;'
    f'horizontal=1;startSize={HEADER_H};horizontalStack=0;resizeParent=1;'
    'resizeParentMax=0;resizeLast=0;collapsible=0;marginBottom=0;html=1;'
)
MEMBER_STYLE = (
    'text;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;'
    'spacingLeft=4;spacingRight=4;overflow=hidden;rotatable=0;'
    'points=[[0,0.5],[1,0.5]];portConstraint=eastwest;whiteSpace=wrap;html=1;'
)
SEPARATOR_STYLE = (
    'line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;spacingTop=-1;'
    'spacingLeft=3;spacingRight=3;rotatable=0;labelPosition=right;points=[];'
    'portConstraint=eastwest;html=1;'
)

# Line ends per relation kind (PRD CLS-7); the line runs from `source` to `target`
RELATION_ENDS = {
    'association': 'endArrow=none;startArrow=none;',
    'directed': 'endArrow=open;endSize=10;startArrow=none;',
    'inheritance': 'endArrow=block;endFill=0;endSize=14;startArrow=none;',
    'realization': 'endArrow=block;endFill=0;endSize=14;startArrow=none;dashed=1;',
    'composition': 'startArrow=diamondThin;startFill=1;startSize=16;endArrow=none;',
    'aggregation': 'startArrow=diamondThin;startFill=0;startSize=16;endArrow=none;',
    'dependency': 'endArrow=open;endSize=10;startArrow=none;dashed=1;',
    'link': 'endArrow=none;startArrow=none;dashed=1;',
}

_TYPE_ALIASES = {
    'integer': 'int',
    'serial': 'int',
    'bigserial': 'bigint',
    'smallserial': 'smallint',
    'bool': 'boolean',
}


# ── Model ────────────────────────────────────────────────────────────────────

@dataclass
class UmlClass:
    name: str
    attributes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    stereotype: str = ''        # 'interface' / 'abstract'


@dataclass
class UmlRelation:
    source: str                 # the line starts here …
    target: str                 # … and ends here (arrowheads sit at the target)
    kind: str                   # a key of RELATION_ENDS
    source_label: str = ''      # multiplicity written at each end
    target_label: str = ''
    label: str = ''             # name written along the line


# ── From a SQL schema ────────────────────────────────────────────────────────

def build_class_page(schema: dict[str, Any]) -> ET.Element:
    """Class diagram for a parsed SQL schema: one class per table, one association per FK."""
    tables: list[dict[str, Any]] = schema.get('tables', [])
    known = {t['name'] for t in tables}
    fks = [r for r in schema.get('relations', [])
           if r['from_table'] in known and r['to_table'] in known]

    classes = [UmlClass(t['name'], _attribute_lines(t), _method_lines(t['name'], fks))
               for t in tables]
    relations = [UmlRelation(r['from_table'], r['to_table'], 'association', '0..*', '1')
                 for r in fks]
    return render_class_diagram(classes, relations)


def _attribute_lines(table: dict[str, Any]) -> list[str]:
    return [f"- {col['name']} : {_simple_type(col['type'])}" for col in table.get('columns', [])]


def _method_lines(name: str, relations: list[dict[str, Any]]) -> list[str]:
    """CRUD methods plus one accessor per related table, e.g. `+ produksiBahan()`."""
    related = []
    for rel in relations:
        if rel['from_table'] == name:
            related.append(rel['to_table'])
        if rel['to_table'] == name:
            related.append(rel['from_table'])
    accessors = dict.fromkeys(_camel(t) for t in related)
    return [f'+ {m}()' for m in (*CRUD_METHODS, *accessors)]


def _simple_type(sql_type: str) -> str:
    """VARCHAR(255) → varchar, DECIMAL(10,2) → decimal, TINYINT(1) → boolean, SERIAL → int."""
    base = sql_type.split('(')[0].split()[0].lower()
    if base == 'tinyint' and '(1)' in sql_type.replace(' ', ''):
        return 'boolean'
    return _TYPE_ALIASES.get(base, base)


def _camel(table_name: str) -> str:
    first, *rest = table_name.split('_')
    return first.lower() + ''.join(p.capitalize() for p in rest)


# ── From text ────────────────────────────────────────────────────────────────

_CLASS_HEADER = re.compile(r'^(abstract\s+class|class|interface)\s+([\w.]+)\s*(\{(.*?)(\})?)?\s*$',
                           re.IGNORECASE)
# Operator → (kind, line drawn from the right-hand class instead of the left one)
_OPERATORS = {
    '<|--': ('inheritance', True), '--|>': ('inheritance', False),
    '<|..': ('realization', True), '..|>': ('realization', False),
    '*--': ('composition', False), '--*': ('composition', True),
    'o--': ('aggregation', False), '--o': ('aggregation', True),
    '..>': ('dependency', False), '<..': ('dependency', True),
    '-->': ('directed', False), '<--': ('directed', True),
    '--': ('association', False), '..': ('link', False),
}
_RELATION = re.compile(
    r'^([\w.]+)\s*(?:"([^"]*)")?\s*('
    + '|'.join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True))
    + r')\s*(?:"([^"]*)")?\s*([\w.]+)\s*(?::\s*(.*))?$'
)


def parse_class_text(lines: list[tuple[int, str]]) -> tuple[list[UmlClass], list[UmlRelation], list[tuple[int, str]]]:
    """Parse numbered text lines; bad lines are reported as (line, reason) and skipped."""
    classes: dict[str, UmlClass] = {}
    relations: list[UmlRelation] = []
    errors: list[tuple[int, str]] = []
    body: tuple[UmlClass, int] | None = None     # class whose { … } is open, and its line

    def use(name: str) -> UmlClass:
        return classes.setdefault(name, UmlClass(name))

    def add_member(cls: UmlClass, text: str) -> None:
        text = text.strip()
        if text and text not in ('...', '--', '..', '=='):
            (cls.methods if '(' in text else cls.attributes).append(text)

    for lineno, raw in lines:
        text = _strip_comment(raw).strip()
        if not text:
            continue
        lower = text.lower()
        if lower.startswith(('@startuml', '@enduml', 'title ', 'skinparam', 'scale')):
            continue
        if lower.startswith(('package ', 'end package', 'namespace ', 'end namespace')):
            continue

        if body:
            if text == '}':
                body = None
                continue
            if not _CLASS_HEADER.match(text):
                add_member(body[0], text)
                continue
            # A new class while the last one is still open: its '}' was forgotten
            errors.append((body[1], f"class '{body[0].name}' belum ditutup dengan '}}'"))
            body = None

        if m := _CLASS_HEADER.match(text):
            keyword, name, brace, inline, closed = m.groups()
            cls = use(name)
            cls.stereotype = keyword.split()[0].lower() if keyword.lower() != 'class' else ''
            if brace and closed:
                for member in (inline or '').split(';'):
                    add_member(cls, member)
            elif brace:
                body = (cls, lineno)
                add_member(cls, inline or '')
        elif m := _RELATION.match(text):
            left, left_label, op, right_label, right, label = m.groups()
            kind, reverse = _OPERATORS[op]
            use(left)
            use(right)
            if reverse:
                relations.append(UmlRelation(right, left, kind, right_label or '', left_label or '',
                                             (label or '').strip()))
            else:
                relations.append(UmlRelation(left, right, kind, left_label or '', right_label or '',
                                             (label or '').strip()))
        else:
            errors.append((lineno, f'Baris tidak dikenali: "{text}". '
                                   'Contoh: class Nama { … } atau A "1" -- "0..*" B'))

    if body:
        errors.append((body[1], f"class '{body[0].name}' belum ditutup dengan '}}'"))
    return list(classes.values()), relations, errors


def _strip_comment(line: str) -> str:
    """Drop a PlantUML `'` comment (outside of quotes)."""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "'" and not in_quotes:
            return line[:i]
    return line


def build_class_text_page(title: str, lines: list[tuple[int, str]]) -> tuple[ET.Element | None, list[tuple[int, str]]]:
    classes, relations, errors = parse_class_text(lines)
    if not classes:
        first_line = lines[0][0] if lines else 0
        return None, errors + [(first_line, f'Halaman "{title}" belum berisi class (contoh: class Nama {{ … }})')]
    return render_class_diagram(classes, relations), errors


# ── Layout & rendering ───────────────────────────────────────────────────────

def render_class_diagram(classes: list[UmlClass], relations: list[UmlRelation]) -> ET.Element:
    """Lay out and draw classes and relations as an mxGraphModel element."""
    names = [c.name for c in classes]
    links = [{'from_table': r.source, 'to_table': r.target} for r in relations]
    # Parents above their subclasses / implementations
    above = {(r.target, r.source) for r in relations if r.kind in ('inheritance', 'realization')}
    grid = assign_grid(names, links, singles='right', above=above)

    lanes = LanePlanner(lambda axis, idx: GRID)
    taken = set(grid.values())
    routes = [_plan_route(grid[r.source], grid[r.target], taken, lanes) for r in relations]
    lanes.finalize()

    headers = {c.name: _header(c) for c in classes}
    longest = max(len(line) for c in classes
                  for line in [headers[c.name], *c.attributes, *c.methods])
    width = min(CLASS_MAX_W, max(CLASS_MIN_W, int(math.ceil((longest * CHAR_W + 20) / 20)) * 20))
    heights = {c.name: HEADER_H + ROW_H * len(c.attributes) + SEPARATOR_H + ROW_H * len(c.methods)
               for c in classes}

    # A named line between side-by-side classes needs a gap wide enough for its name
    label_gap: dict[int, int] = {}
    for rel, (side, _, kind, route_lanes) in zip(relations, routes):
        if rel.label and kind == 'straight' and side in 'LR':
            idx = route_lanes[0].idx
            label_gap[idx] = max(label_gap.get(idx, 0), len(rel.label) * CHAR_W + 40)

    # Rows are top-aligned: the anchor of each class is the middle of its top edge
    extents = {n: (width / 2, 0, width / 2, heights[n]) for n in names}
    geo = GridGeometry(
        grid, extents,
        gap_x=lambda c: max(CLASS_GAP, label_gap.get(c, 0), 2 * (lanes.half_extent('x', c) + GAP_CLEAR)),
        gap_y=lambda r: max(CLASS_GAP, 2 * (lanes.half_extent('y', r) + GAP_CLEAR)),
    )

    page = PageBuilder()
    class_id: dict[str, str] = {}
    class_rect: dict[str, Rect] = {}

    for cls in classes:
        name = cls.name
        rect = (geo.x(grid[name][0]) - width // 2, geo.y(grid[name][1]), width, heights[name])
        class_rect[name] = rect
        style = CLASS_STYLE + ('fontStyle=3;' if cls.stereotype == 'abstract' else '')
        cid = page.vertex(html.escape(headers[name]), style, rect)
        class_id[name] = cid

        y = HEADER_H
        for line in cls.attributes:
            page.vertex(html.escape(line), MEMBER_STYLE, (0, y, width, ROW_H), parent=cid)
            y += ROW_H
        page.vertex('', SEPARATOR_STYLE, (0, y, width, SEPARATOR_H), parent=cid)
        y += SEPARATOR_H
        for line in cls.methods:
            page.vertex(html.escape(line), MEMBER_STYLE, (0, y, width, ROW_H), parent=cid)
            y += ROW_H

    port_requests = [(class_id[r.source], class_rect[r.source], route[0],
                      class_id[r.target], class_rect[r.target], route[1])
                     for r, route in zip(relations, routes)]

    for rel, req, route, (exit_port, entry_port) in zip(relations, port_requests, routes,
                                                         assign_ports(port_requests)):
        start, end = port_point(req[1], exit_port), port_point(req[4], entry_port)
        points = _waypoints(route, start, end, lanes, geo)
        # The name goes under the line, the multiplicities above it
        ends = RELATION_ENDS[rel.kind] + ('verticalAlign=top;spacingTop=2;' if rel.label else '')
        style = edge_style(exit_port, entry_port, routed=bool(points), ends=ends)
        edge_id = page.edge(req[0], req[3], style, points, value=html.escape(rel.label))
        if rel.source_label:
            page.end_label(edge_id, html.escape(rel.source_label), req[2], at_source=True)
        if rel.target_label:
            page.end_label(edge_id, html.escape(rel.target_label), req[5], at_source=False)

    return page.to_model()


def _header(cls: UmlClass) -> str:
    return f'«interface» {cls.name}' if cls.stereotype == 'interface' else cls.name


# A route is (from side, to side, kind, lanes): kind is 'straight', 'corner' or 'lanes'
Route = tuple[str, str, str, list[Lane]]


def _plan_route(a: tuple[int, int], b: tuple[int, int], taken: set[tuple[int, int]],
                lanes: LanePlanner) -> Route:
    """Pick the sides and path of the line between the classes in grid cells `a` and `b`."""
    (c1, r1), (c2, r2) = a, b
    if a == b:   # self reference: out on the right, around the corner, back in on top
        return 'R', 'T', 'lanes', [lanes.request('x', c1, -1, 0), lanes.request('y', r1 - 1, 1, 0)]

    if c1 == c2 or r1 == r2:
        if not any(p in taken for p in half_steps(a, b)):
            side = toward(a, b)
            axis, idx = ('x', min(c1, c2)) if r1 == r2 else ('y', min(r1, r2))
            # A lane in case both ends can't line up and the line needs a jog
            return side, OPPOSITE[side], 'straight', [lanes.request(axis, idx, 1, 0)]
    else:
        for corner in ((c2, r1), (c1, r2)):
            if not any(p in taken for p in [*half_steps(a, corner), corner, *half_steps(corner, b)]):
                return toward(a, corner), toward(b, corner), 'corner', []

    # Blocked: leave through the gap next to `a`, follow lanes, enter `b` from its own gap
    reach = abs(c2 - c1) + abs(r2 - r1)
    if r1 == r2:
        return 'T', 'T', 'lanes', [lanes.request('y', r1 - 1, 1, reach)]
    down = r2 > r1
    side_a, side_b = ('B', 'T') if down else ('T', 'B')
    gap_a = r1 if down else r1 - 1
    if abs(r2 - r1) == 1:
        return side_a, side_b, 'lanes', [lanes.request('y', gap_a, 1 if down else -1, reach)]
    gap_b = r2 - 1 if down else r2
    gap_x, sign_x = (c2 - 1, 1) if c2 > c1 else (c2, -1)
    return side_a, side_b, 'lanes', [
        lanes.request('y', gap_a, 1 if down else -1, reach),
        lanes.request('x', gap_x, sign_x, reach),
        lanes.request('y', gap_b, 1 if down else -1, reach),
    ]


def _waypoints(route: Route, start: tuple[float, float], end: tuple[float, float],
               lanes: LanePlanner, geo: GridGeometry) -> list[tuple[float, float]]:
    """Bends of the line from `start` to `end`; empty for a straight line."""
    side_a, side_b, kind, route_lanes = route
    (sx, sy), (ex, ey) = start, end
    if kind == 'straight':
        if (sx == ex) if side_a in 'TB' else (sy == ey):
            return []
        jog = lanes.position(route_lanes[0], geo)
        return [(sx, jog), (ex, jog)] if side_a in 'TB' else [(jog, sy), (jog, ey)]
    if kind == 'corner':
        return [(ex, sy)] if side_a in 'LR' else [(sx, ey)]

    tracks = [lanes.position(ln, geo) for ln in route_lanes]
    if side_a == 'R':                    # self reference
        return [(tracks[0], sy), (tracks[0], tracks[1]), (ex, tracks[1])]
    if len(tracks) == 1:
        return [(sx, tracks[0]), (ex, tracks[0])]
    return [(sx, tracks[0]), (tracks[1], tracks[0]), (tracks[1], tracks[2]), (ex, tracks[2])]
