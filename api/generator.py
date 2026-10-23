# backend/generator.py
"""
Draw.io generator — turns the parsed SQL schema into a .drawio file with three
pages: a Chen-notation ERD, a UML class diagram (see class_diagram.py) and a
data dictionary (see data_dictionary.py).

Chen Notation rules:
  • Entity    → Rectangle
  • Attribute → Ellipse (PK text underlined, FK italic), stacked in columns on
                a side not used by relationship lines, lines fanning out from it
  • Relation  → Diamond between the two entities, one per FK relationship
  • Edges     → entity–relation lines are horizontal/vertical with N / 1
                cardinality, entity–attribute lines are straight; no arrowheads

No colours are hard-coded, so both pages follow draw.io's light/dark theme.
"""

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from class_diagram import build_class_page  # type: ignore
from data_dictionary import build_dictionary_page  # type: ignore
from layout import (  # type: ignore
    GRID, OPPOSITE, GridGeometry, Lane, LanePlanner, PageBuilder, Rect,
    assign_grid, build_mxfile, edge_style, find_free_spot, h_side, half_steps,
    port_point, side_port, snap, toward,
)

# ── Layout constants ─────────────────────────────────────────────────────────
ENTITY_MIN_W = 120      # entity rectangle width (grows with long names / many ports)
ENTITY_H = 40           # entity rectangle height
ATTR_MIN_W = 80         # attribute ellipse width range
ATTR_MAX_W = 160
ATTR_H = 30             # attribute ellipse height
DIAMOND_W = 100         # relationship diamond width
DIAMOND_H = 60          # relationship diamond height

CELL_GAP = 60           # smallest space between neighbouring cells
GAP_CLEAR = 40          # space between a gap's diamonds/lanes and the cells beside it
PORT_STEP = 20          # spacing between lines leaving the same entity side
PORT_BAND = DIAMOND_W // 2 + GRID   # extra lines on a side stay clear of its centred diamond
LANE_BASE = 20          # first lane offset from the centre of a gap without diamonds

STACK_GAP = 20          # entity → attribute stack above/below it
STACK_SIDE_GAP = 30     # entity → attribute column left/right of it
STACK_COL_GAP = 20      # between the two columns of a stack above/below
STACK_MAX_ROWS = 5      # rows per column before another side is used

# Where attribute stacks go: the free sides, or the corners when every side has relationship lines
_SIDE_SLOTS = ('T', 'B', 'R', 'L')
_CORNER_SLOTS = ('TL', 'TR', 'BR', 'BL')
# Point on the entity that a slot's attribute lines fan out from
_SLOT_ORIGIN = {
    'T': (0.5, 0), 'B': (0.5, 1), 'R': (1, 0.5), 'L': (0, 0.5),
    'TL': (0, 0), 'TR': (1, 0), 'BR': (1, 1), 'BL': (0, 1),
}

ENTITY_STYLE = 'rounded=0;whiteSpace=wrap;html=1;fontStyle=1;fontSize=13;'
DIAMOND_STYLE = 'rhombus;whiteSpace=wrap;html=1;fontSize=11;'


def generate_drawio_xml(schema: dict[str, Any]) -> str:
    """Generate a .drawio file with ERD, class diagram and data dictionary pages from the parsed schema."""
    return build_mxfile([('ERD', build_erd_page(schema)),
                         ('Class Diagram', build_class_page(schema)),
                         ('Kamus Data', build_dictionary_page(schema))])


# ── Relationship planning (grid units) ───────────────────────────────────────

@dataclass
class _Link:
    """One line of a relationship, drawn from an entity to the diamond."""
    entity: str
    side: str                 # entity side the line leaves from
    sign: int                 # 0: middle of the side; ±1: beside the middle, toward −/+ x
    reach: float              # how far the line travels (orders ports and lanes)
    diamond_side: str
    label: str                # cardinality written at the entity end
    # Bends as (x, y) specs: 'port' / 'diamond' take that coordinate from the
    # entity port / diamond centre, a Lane takes its track position.
    waypoints: list[tuple[Any, Any]] = field(default_factory=list)
    offset: int = 0           # port position along the side, set once all links are known


@dataclass
class _Relationship:
    rel: dict[str, Any]
    spot: tuple[float, float]           # diamond position; x.5 = in the gap after x
    links: tuple[_Link, _Link]


def _plan_relationships(relations: list[dict[str, Any]], grid: dict[str, tuple[int, int]],
                        lanes: LanePlanner) -> list[_Relationship]:
    """
    Give each relationship a diamond spot and a path for both of its lines.
    Lines run straight through free cells when they can; otherwise the diamond
    sits in the gap corner next to one entity and the other line follows
    lanes around the tables.
    """
    taken = set(grid.values())
    spots: set[tuple[float, float]] = set()
    lines: dict[tuple[float, float], str] = {}      # grid point → 'h'/'v' line through it
    seen_pairs: set[frozenset[str]] = set()

    def dist(rel: dict[str, Any]) -> int:
        (c1, r1), (c2, r2) = grid[rel['from_table']], grid[rel['to_table']]
        return abs(c1 - c2) + abs(r1 - r2)

    planned: dict[int, _Relationship] = {}
    for i in sorted(range(len(relations)), key=lambda i: dist(relations[i])):
        rel = relations[i]
        pair = frozenset((rel['from_table'], rel['to_table']))
        plan = None
        if pair not in seen_pairs:
            plan = _plan_straight(rel, grid, taken, spots, lines)
        if plan is None:
            plan = _plan_detour(rel, grid, spots, lanes)
        seen_pairs.add(pair)
        planned[i] = plan
    return [planned[i] for i in range(len(relations))]


def _plan_straight(rel, grid, taken, spots, lines) -> _Relationship | None:
    """Straight lines: diamond midway on a shared row/column, or in an empty corner cell."""
    ft, tt = rel['from_table'], rel['to_table']
    a, b = grid[ft], grid[tt]
    if a == b:
        return None
    if a[0] == b[0] or a[1] == b[1]:
        candidates = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)]
    else:
        candidates = [(b[0], a[1]), (a[0], b[1])]

    for spot in candidates:
        legs = [(half_steps(a, spot), 'h' if a[1] == spot[1] else 'v'),
                (half_steps(spot, b), 'h' if b[1] == spot[1] else 'v')]
        path = [(p, d) for pts, d in legs for p in pts]
        if spot in spots or spot in taken or spot in lines:
            continue
        if any(p in taken or p in spots or lines.get(p) == d for p, d in path):
            continue
        spots.add(spot)
        lines.update(path)
        side_a, side_b = toward(a, spot), toward(b, spot)
        return _Relationship(rel, spot, (
            _Link(ft, side_a, 0, 0, OPPOSITE[side_a], 'N'),
            _Link(tt, side_b, 0, 0, OPPOSITE[side_b], '1'),
        ))
    return None


def _plan_detour(rel, grid, spots, lanes) -> _Relationship:
    ft, tt = rel['from_table'], rel['to_table']
    if ft == tt:
        return _plan_self(rel, grid[ft], spots, lanes)

    # Diamond in a gap corner next to one entity, preferring the corner facing the other
    options = []
    for near, far, near_label, far_label in ((ft, tt, 'N', '1'), (tt, ft, '1', 'N')):
        (cn, rn), (cf, rf) = grid[near], grid[far]
        sx, sy = (1 if cf >= cn else -1), (1 if rf > rn else -1)
        for qx, qy in ((sx, sy), (sx, -sy), (-sx, sy), (-sx, -sy)):
            options.append((near, far, near_label, far_label, qx, qy))
    chosen = next((o for o in options
                   if (grid[o[0]][0] + o[4] / 2, grid[o[0]][1] + o[5] / 2) not in spots),
                  options[0])   # all taken: the pixel pass nudges the diamond aside

    near, far, near_label, far_label, sx, sy = chosen
    (cn, rn), (cf, rf) = grid[near], grid[far]
    spot = (cn + sx / 2, rn + sy / 2)
    spots.add(spot)
    gx, gy = spot

    near_link = _Link(near, 'B' if sy > 0 else 'T', sx, 0.5, h_side(-sx), near_label,
                      waypoints=[('port', 'diamond')])

    entry_side = 'T' if rf > gy else 'B'
    entry_gap = rf - 1 if entry_side == 'T' else rf
    to_far = 1 if entry_side == 'T' else -1
    reach = abs(gx - cf) + abs(gy - rf)
    approach = 1 if gx > cf else -1
    y_lane = lanes.request('y', entry_gap, to_far, reach)
    if entry_gap + 0.5 == gy:
        # Far entity borders the diamond's own gap: drop into a lane and run along it
        far_link = _Link(far, entry_side, approach, reach, 'B' if to_far > 0 else 'T', far_label,
                         waypoints=[('port', y_lane), ('diamond', y_lane)])
    else:
        x_lane = lanes.request('x', math.floor(gx), sx, reach)
        far_link = _Link(far, entry_side, approach, reach, h_side(sx), far_label,
                         waypoints=[('port', y_lane), (x_lane, y_lane), (x_lane, 'diamond')])

    links = (near_link, far_link) if near == ft else (far_link, near_link)
    return _Relationship(rel, spot, links)


def _plan_self(rel, cell, spots, lanes) -> _Relationship:
    """Self reference: diamond in a gap corner, both lines leave the same side."""
    c, r = cell
    quadrants = ((1, -1), (-1, -1), (1, 1), (-1, 1))
    sx, sy = next((q for q in quadrants if (c + q[0] / 2, r + q[1] / 2) not in spots), quadrants[0])
    spot = (c + sx / 2, r + sy / 2)
    spots.add(spot)
    side = 'T' if sy < 0 else 'B'
    lane = lanes.request('y', math.floor(spot[1]), -sy, 0.6)
    name = rel['from_table']
    return _Relationship(rel, spot, (
        _Link(name, side, sx, 0.5, h_side(-sx), 'N', waypoints=[('port', 'diamond')]),
        _Link(name, side, sx, 0.6, 'B' if sy < 0 else 'T', '1',
              waypoints=[('port', lane), ('diamond', lane)]),
    ))


def _assign_offsets(plans: list[_Relationship]) -> dict[tuple[str, str], int]:
    """
    Place link ports along entity sides. A centred link (straight to its
    diamond) keeps the middle; the others line up outward on their side,
    clear of that diamond. Returns the half-width each top/bottom side needs.
    """
    groups: dict[tuple[str, str], list[_Link]] = {}
    for plan in plans:
        for link in plan.links:
            groups.setdefault((link.entity, link.side), []).append(link)

    needed: dict[tuple[str, str], int] = {}
    for key, links in groups.items():
        centred = [ln for ln in links if ln.sign == 0]
        base = PORT_BAND if centred else PORT_STEP
        if len(centred) > 1:            # never planned, but keep them apart if it happens
            for i, ln in enumerate(centred):
                ln.sign, ln.reach = (1 if i % 2 else -1), -1
            base = PORT_STEP
        half = 0
        for sign in (-1, 1):
            side_links = sorted((ln for ln in links if ln.sign == sign), key=lambda ln: ln.reach)
            for i, ln in enumerate(side_links):
                ln.offset = sign * (base + PORT_STEP * i)
                half = max(half, abs(ln.offset) + GRID)
        needed[key] = half
    return needed


# ── Page ─────────────────────────────────────────────────────────────────────

def build_erd_page(schema: dict[str, Any]) -> ET.Element:
    """Build the Chen-notation ERD as an mxGraphModel element."""

    tables: list[dict[str, Any]] = schema.get('tables', [])
    all_relations: list[dict[str, Any]] = schema.get('relations', [])
    names = [t['name'] for t in tables]
    known = set(names)
    relations = [r for r in all_relations
                 if r['from_table'] in known and r['to_table'] in known]

    grid = assign_grid(names, relations)
    custom_names = {(t['name'], c['name']): c['rel_label']
                    for t in tables for c in t.get('columns', []) if c.get('rel_label')}

    # ── 1. Plan diamonds, lines and lanes on the grid ───────────────────────
    diamond_gaps: dict[str, set[int]] = {'x': set(), 'y': set()}

    def lane_base(axis: str, idx: int) -> int:
        if idx in diamond_gaps[axis]:
            return (DIAMOND_W if axis == 'x' else DIAMOND_H) // 2 + GRID
        return LANE_BASE

    lanes = LanePlanner(lane_base)
    plans = _plan_relationships(relations, grid, lanes)
    for plan in plans:
        gx, gy = plan.spot
        if gx % 1:
            diamond_gaps['x'].add(math.floor(gx))
        if gy % 1:
            diamond_gaps['y'].add(math.floor(gy))
    lanes.finalize()
    side_half = _assign_offsets(plans)

    # ── 2. Entity sizes and attribute fans away from the sides in use ───────
    widths = {n: max(_entity_width(n), _ceil20(2 * side_half.get((n, 'T'), 0)),
                     _ceil20(2 * side_half.get((n, 'B'), 0)))
              for n in names}
    sides = {n: {side for (e, side) in side_half if e == n} for n in names}
    stacks = {t['name']: _stack_attributes(t.get('columns', []), widths[t['name']], sides[t['name']])
              for t in tables}
    extents = {n: _extent(widths[n], [rect for rect, _ in stacks[n]]) for n in names}

    # ── 3. Size the grid around cells, diamonds and lanes ───────────────────
    def gap(axis: str, idx: int) -> int:
        diamond_half = (DIAMOND_W if axis == 'x' else DIAMOND_H) // 2
        content = max(diamond_half if idx in diamond_gaps[axis] else 0,
                      lanes.half_extent(axis, idx))
        return max(CELL_GAP, 2 * (content + GAP_CLEAR)) if content else CELL_GAP

    geo = GridGeometry(
        grid, extents,
        gap_x=lambda c: gap('x', c),
        gap_y=lambda r: gap('y', r),
        min_half=(DIAMOND_W // 2 + GRID, DIAMOND_H // 2 + GRID),
    )

    page = PageBuilder()
    entity_id: dict[str, str] = {}
    entity_rect: dict[str, Rect] = {}
    occupied: list[Rect] = []

    # ── 4. Entities (rectangles) and their attributes (ellipses) ────────────
    for table in tables:
        name = table['name']
        cx, cy = geo.x(grid[name][0]), geo.y(grid[name][1])
        w = widths[name]
        rect = (cx - w // 2, cy - ENTITY_H // 2, w, ENTITY_H)
        entity_rect[name] = rect
        entity_id[name] = page.vertex(name, ENTITY_STYLE, rect)
        occupied.append(rect)

        fk_columns = {r['from_column'] for r in all_relations if r['from_table'] == name}
        for col, (offset_rect, slot) in zip(table.get('columns', []), stacks[name]):
            ox, oy, aw, ah = offset_rect
            attr_rect = (cx + ox, cy + oy, aw, ah)
            attr_id = page.vertex(col['name'],
                                  _attr_style(col['is_pk'], col['name'] in fk_columns),
                                  attr_rect)
            page.edge(entity_id[name], attr_id, _attr_edge_style(slot, offset_rect))
            occupied.append(attr_rect)

    # ── 5. Relationship diamonds and their lines ────────────────────────────
    for plan in plans:
        gx, gy = plan.spot
        rect = find_free_spot(
            (geo.x(gx) - DIAMOND_W // 2, geo.y(gy) - DIAMOND_H // 2, DIAMOND_W, DIAMOND_H),
            occupied)
        occupied.append(rect)
        centre = (rect[0] + DIAMOND_W / 2, rect[1] + DIAMOND_H / 2)
        diamond_id = page.vertex(
            _relation_label(plan.rel['from_table'], plan.rel['to_table'],
                            custom_names.get((plan.rel['from_table'], plan.rel['from_column']), '')),
            DIAMOND_STYLE, rect)

        # from_table holds the FK → many side (N); to_table is referenced → one side (1)
        for link in plan.links:
            port = side_port(link.side, link.offset)
            start = port_point(entity_rect[link.entity], port)

            def coord(spec: Any, axis: int) -> float:
                if isinstance(spec, Lane):
                    return lanes.position(spec, geo)
                return (start if spec == 'port' else centre)[axis]

            points = [(coord(xs, 0), coord(ys, 1)) for xs, ys in link.waypoints]
            edge_id = page.edge(entity_id[link.entity], diamond_id,
                                edge_style(port, side_port(link.diamond_side), routed=bool(points)),
                                points)
            page.end_label(edge_id, link.label, link.side)

    return page.to_model()


# ── Attribute stacks ─────────────────────────────────────────────────────────

def _stack_attributes(columns: list[dict[str, Any]], entity_w: int,
                      used_sides: set[str]) -> list[tuple[Rect, str]]:
    """
    Stack the attribute ellipses in tight columns beside the entity, every
    line fanning out from one point: two columns above/below, one column
    left/right, on sides that relationship lines leave free. When all four
    sides carry relationship lines, one column goes off each corner instead.

    Returns (rect relative to the entity centre, slot) per attribute, in order.
    """
    n = len(columns)
    if not n:
        return []

    slots = [s for s in _SIDE_SLOTS if s not in used_sides] or list(_CORNER_SLOTS)

    def column_count(chosen: list[str]) -> int:
        return sum(2 if s in 'TB' else 1 for s in chosen)

    # As few slots as possible, up to STACK_MAX_ROWS rows per column
    k = next((k for k in range(1, len(slots) + 1)
              if n <= column_count(slots[:k]) * STACK_MAX_ROWS), len(slots))
    slots = slots[:k]

    stacks = [(slot, part) for slot in slots for part in ((-1, 1) if slot in 'TB' else (0,))]
    per_stack = [n // len(stacks) + (1 if i < n % len(stacks) else 0) for i in range(len(stacks))]
    widths = [_attr_width(c['name']) for c in columns]

    hw, hh = entity_w / 2, ENTITY_H / 2
    # Columns left/right are centred on the entity; stacks above/below start beyond them
    side_half = max((per_stack[i] * ATTR_H / 2 for i, (s, _) in enumerate(stacks) if s in 'LR'),
                    default=0)
    vertical_start = max(hh + STACK_GAP, side_half + GRID)

    placed: list[tuple[Rect, str]] = []
    attr_iter = iter(widths)
    for (slot, part), count in zip(stacks, per_stack):
        # Same-size ellipses within a column, sized for its longest name
        w = max([next(attr_iter) for _ in range(count)], default=0)
        for j in range(count):
            if slot in 'TB':
                x = -STACK_COL_GAP / 2 - w if part < 0 else STACK_COL_GAP / 2
                y = (-vertical_start - (count - j) * ATTR_H if slot == 'T'
                     else vertical_start + j * ATTR_H)
            elif slot in 'LR':
                x = hw + STACK_SIDE_GAP if slot == 'R' else -hw - STACK_SIDE_GAP - w
                y = snap(-count * ATTR_H / 2) + j * ATTR_H
            else:   # corner: column just outside the corner, growing away from the entity
                x = hw + GRID if slot[1] == 'R' else -hw - GRID - w
                y = (-hh - GRID - (count - j) * ATTR_H if slot[0] == 'T'
                     else hh + GRID + j * ATTR_H)
            placed.append(((x, y, w, ATTR_H), slot))
    return placed


def _attr_edge_style(slot: str, rect: Rect) -> str:
    """Straight line from the slot's fan point to the ellipse tip facing the entity."""
    x, _, w, _ = rect
    if x + w <= 0:
        tip = (1, 0.5)
    elif x >= 0:
        tip = (0, 0.5)
    else:
        tip = (0.5, 1) if slot.startswith('T') else (0.5, 0)
    origin = _SLOT_ORIGIN[slot]
    return edge_style((*origin, 0, 0), (*tip, 0, 0), routed=True)


def _extent(entity_w: int, rects: list[Rect]) -> tuple[float, float, float, float]:
    """Space an entity and its attributes need around the entity centre."""
    hw, hh = entity_w / 2, ENTITY_H / 2
    return (
        max([hw] + [-x for x, _, _, _ in rects]),
        max([hh] + [-y for _, y, _, _ in rects]),
        max([hw] + [x + w for x, _, w, _ in rects]),
        max([hh] + [y + h for _, y, _, h in rects]),
    )


def _entity_width(name: str) -> int:
    return max(ENTITY_MIN_W, _ceil20(len(name) * 9 + 30))


def _attr_width(name: str) -> int:
    return min(ATTR_MAX_W, max(ATTR_MIN_W, _ceil20(len(name) * 7 + 20)))


def _ceil20(v: float) -> int:
    """Round up to a multiple of 20 so half the width still lands on the grid."""
    return int(math.ceil(v / 20)) * 20


def _attr_style(is_pk: bool, is_fk: bool) -> str:
    # PK → underline (4); FK → italic (2); both → italic-underline (6)
    font_style = (4 if is_pk else 0) + (2 if is_fk else 0)
    return f'ellipse;whiteSpace=wrap;html=1;fontStyle={font_style};fontSize=11;'


# ── Helpers ──────────────────────────────────────────────────────────────────

# Kata kerja mapping: if the child table (the one holding the FK) contains one of these
# keywords, the diamond says this verb. Tried first because it is the most specific.
_VERB_MAP: dict[str, str] = {
    'detail':       'memiliki',
    'transaksi':    'melakukan',
    'pemesanan':    'memesan',
    'pesanan':      'memesan',
    'order':        'memesan',
    'pembayaran':   'membayar',
    'payment':      'membayar',
    'penjualan':    'menjual',
    'pembelian':    'membeli',
    'pengiriman':   'mengirim',
    'pendaftaran':  'mendaftar',
    'penilaian':    'menilai',
    'review':       'menilai',
    'pemakaian':    'memakai',
    'penggunaan':   'menggunakan',
    'penugasan':    'menugaskan',
    'enrollment':   'mendaftar',
    'booking':      'memesan',
    'reservasi':    'mereservasi',
}

# What the referenced (parent) table does to the child rows, by the kind of table it is.
# Read as "<parent> <verb> <child>": kategori mencakup produk, supplier memasok barang_masuk.
_PARENT_ROLE: list[tuple[tuple[str, ...], str]] = [
    (('kategori', 'jenis', 'golongan', 'klasifikasi', 'tipe'), 'mencakup'),
    (('supplier', 'pemasok', 'vendor', 'distributor'), 'memasok'),
    (('users', 'user', 'pengguna', 'petugas', 'admin', 'karyawan', 'pegawai', 'kasir', 'operator'), 'mencatat'),
    (('pelanggan', 'customer', 'pembeli', 'konsumen', 'anggota', 'member', 'peminjam', 'donatur',
      'siswa', 'mahasiswa', 'pasien', 'peserta'), 'melakukan'),
    (('dosen', 'guru', 'pengajar', 'instruktur'), 'mengajar'),
    (('produk', 'barang', 'buku', 'obat', 'menu', 'snack', 'item', 'bahan', 'aset'), 'tercatat pada'),
    (('gudang', 'rak', 'lokasi'), 'menyimpan'),
    (('kelas', 'jurusan', 'prodi', 'departemen', 'divisi', 'cabang', 'toko'), 'memiliki'),
]


def _relation_label(from_table: str, to_table: str, custom: str = '') -> str:
    """
    The verb written in a relationship diamond, in Indonesian, read as
    "<to_table> <verb> <from_table>" (the referenced table acts on the table holding the FK).

    Order of preference:
      1. A name the author gave in the SQL (`-- @rel: memasok` on the FK column).
      2. A keyword in the child table's name (pemesanan → memesan).
      3. The kind of table the parent is (supplier → memasok, kategori → mencakup).
      4. A keyword in the parent table's name.
      5. 'memiliki'.
    """
    if custom.strip():
        return custom.strip()
    child, parent = from_table.lower(), to_table.lower()

    for keyword, verb in _VERB_MAP.items():
        if keyword in child:
            return verb
    for keywords, verb in _PARENT_ROLE:
        if any(k in parent for k in keywords):
            return verb
    for keyword, verb in _VERB_MAP.items():
        if keyword in parent:
            return verb
    return 'memiliki'
