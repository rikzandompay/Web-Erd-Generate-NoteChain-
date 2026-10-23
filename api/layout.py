# backend/layout.py
"""
Shared layout helpers for the draw.io generators (ERD + class diagram).

Tables are first placed on an abstract grid (col, row) from their FK graph.
Each column/row is then sized from the extents of what is drawn in its cells,
so neighbouring cells can never overlap however large their content gets.
Every coordinate that reaches the XML is snapped to the 10px draw.io grid.
"""

import itertools
import math
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

GRID = 10
PAGE_MARGIN = 40

Rect = tuple[float, float, float, float]      # x, y, width, height
Extent = tuple[float, float, float, float]    # left, top, right, bottom (from anchor)

OPPOSITE = {'L': 'R', 'R': 'L', 'T': 'B', 'B': 'T'}

# Where an end label sits so it points away from the box it is attached to
_END_LABEL_ALIGN = {
    'R': ('left', 'bottom'),
    'L': ('right', 'bottom'),
    'T': ('left', 'bottom'),
    'B': ('left', 'top'),
}


def snap(v: float) -> int:
    """Round to the nearest multiple of the draw.io grid size."""
    return int(round(v / GRID)) * GRID


def rects_overlap(a: Rect, b: Rect, pad: float = 0) -> bool:
    return (a[0] < b[0] + b[2] + pad and b[0] < a[0] + a[2] + pad and
            a[1] < b[1] + b[3] + pad and b[1] < a[1] + a[3] + pad)


def find_free_spot(rect: Rect, occupied: list[Rect], pad: float = GRID) -> Rect:
    """Nudge `rect` outward in grid steps until it no longer touches anything in `occupied`."""
    x, y, w, h = rect
    for d in itertools.count(0, GRID):
        for dx, dy in ((0, -d), (0, d), (-d, 0), (d, 0),
                       (-d, -d), (d, -d), (-d, d), (d, d)):
            cand = (x + dx, y + dy, w, h)
            if not any(rects_overlap(cand, o, pad) for o in occupied):
                return cand
    raise AssertionError('unreachable')


def h_side(dc: int) -> str:
    return 'R' if dc > 0 else 'L'


def v_side(dr: int) -> str:
    return 'B' if dr > 0 else 'T'


# ── Grid placement ───────────────────────────────────────────────────────────

def assign_grid(names: list[str], relations: list[dict[str, Any]], singles: str = 'below',
                above: set[tuple[str, str]] | None = None) -> dict[str, tuple[int, int]]:
    """
    Place every table on a (col, row) grid so that related tables sit next to
    each other, with the most connected table of each group in the middle.
    Connected groups are laid out side by side; tables without any relation
    fill rows underneath them, or a column on the right with singles='right'.
    `above` holds (upper, lower) pairs, e.g. parent class → subclass, that
    should preferably be stacked that way.
    """
    adj: dict[str, list[str]] = {n: [] for n in names}
    for rel in relations:
        a, b = rel['from_table'], rel['to_table']
        if a in adj and b in adj and a != b and b not in adj[a]:
            adj[a].append(b)
            adj[b].append(a)
    above = above or set()

    order_idx = {n: i for i, n in enumerate(names)}
    seen: set[str] = set()
    components: list[list[str]] = []
    for name in names:
        if name in seen:
            continue
        comp, queue = [], deque([name])
        seen.add(name)
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        components.append(comp)

    connected = sorted((c for c in components if len(c) > 1), key=len, reverse=True)
    loners = [c[0] for c in components if len(c) == 1]

    # Groups are packed like books on shelves: left to right until the shelf is
    # about as wide as a landscape page of all tables would be, then a new shelf
    shapes = []
    for comp in connected:
        placed = _refine(_place_component(comp, adj, order_idx, above), adj, above)
        min_c = min(c for c, _ in placed.values())
        min_r = min(r for _, r in placed.values())
        shapes.append({n: (c - min_c, r - min_r) for n, (c, r) in placed.items()})
    shelf_cols = max([max(c for c, _ in s.values()) + 1 for s in shapes]
                     + [math.ceil(math.sqrt(1.6 * len(names)))])

    grid: dict[str, tuple[int, int]] = {}
    col, row, shelf_h = 0, 0, 0
    for shape in shapes:
        width = max(c for c, _ in shape.values()) + 1
        height = max(r for _, r in shape.values()) + 1
        if col and col + width > shelf_cols:
            col, row, shelf_h = 0, row + shelf_h, 0
        for name, (c, r) in shape.items():
            grid[name] = (col + c, row + r)
        col += width
        shelf_h = max(shelf_h, height)

    used_cols = max((c for c, _ in grid.values()), default=-1) + 1
    if loners and singles == 'right':
        rows = max(3, max((r for _, r in grid.values()), default=0) + 1)
        for i, name in enumerate(loners):
            grid[name] = (used_cols + i // rows, i % rows)
    elif loners:
        top = max((r for _, r in grid.values()), default=-1) + 1
        per_row = max(used_cols, math.ceil(math.sqrt(len(loners))))
        for i, name in enumerate(loners):
            grid[name] = (i % per_row, top + i // per_row)

    return grid


def _place_component(comp: list[str], adj: dict[str, list[str]], order_idx: dict[str, int],
                     above: set[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    def busiest_first(n: str) -> tuple[int, int]:
        return (-len(adj[n]), order_idx[n])

    start = min(comp, key=busiest_first)
    order, seen, queue = [], {start}, deque([start])
    while queue:
        cur = queue.popleft()
        order.append(cur)
        for nb in sorted(adj[cur], key=busiest_first):
            if nb not in seen:
                seen.add(nb)
                queue.append(nb)

    placed = {start: (0, 0)}
    taken = {(0, 0)}
    for node in order[1:]:
        anchors = [placed[nb] for nb in adj[node] if nb in placed]
        # +1: node should sit below that neighbour, −1: above it
        wanted = [1 if (nb, node) in above else -1 if (node, nb) in above else 0
                  for nb in adj[node] if nb in placed]
        for radius in itertools.count(1):
            cands = {(ac + dc, ar + dr)
                     for ac, ar in anchors
                     for dc in range(-radius, radius + 1)
                     for dr in range(-radius, radius + 1)} - taken
            if cands:
                break
        cell = min(sorted(cands), key=lambda c: _cell_score(c, anchors, taken, wanted))
        placed[node] = cell
        taken.add(cell)
    return placed


# ── Layout refinement ────────────────────────────────────────────────────────

def _cells_between(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Grid cells strictly between two cells on the same row or column."""
    (c1, r1), (c2, r2) = a, b
    if r1 == r2:
        return [(c, r1) for c in range(min(c1, c2) + 1, max(c1, c2))]
    return [(c1, r) for r in range(min(r1, r2) + 1, max(r1, r2))]


def _line_cost(a: tuple[int, int], b: tuple[int, int], occupied: set[tuple[int, int]]) -> float:
    """How awkward it is to join two cells: far, elbowed or running through another table."""
    dc, dr = abs(a[0] - b[0]), abs(a[1] - b[1])
    cost = 10.0 * (dc + dr)
    if not (dc and dr):
        return cost + (40 if any(c in occupied for c in _cells_between(a, b)) else 0)
    cost += 4
    for corner in ((b[0], a[1]), (a[0], b[1])):          # an elbow needs a free corner and free legs
        if corner not in occupied and not any(c in occupied for c in
                                              _cells_between(a, corner) + _cells_between(corner, b)):
            return cost
    return cost + 40


def _layout_cost(placed: dict[str, tuple[int, int]], adj: dict[str, list[str]],
                 above: set[tuple[str, str]]) -> float:
    occupied = set(placed.values())
    cost = 0.0
    for name, cell in placed.items():
        for other in adj[name]:
            if name < other and other in placed:
                cost += _line_cost(cell, placed[other], occupied)
    for upper, lower in above:
        if upper in placed and lower in placed and placed[upper][1] >= placed[lower][1]:
            cost += 15                                   # parent should sit above its subclass
    cs, rs = [c for c, _ in occupied], [r for _, r in occupied]
    cx, cy = sum(cs) / len(cs), sum(rs) / len(rs)       # tie-breaker: stay compact
    return cost + 0.5 * sum(abs(c - cx) + abs(r - cy) for c, r in occupied)


def _refine(placed: dict[str, tuple[int, int]], adj: dict[str, list[str]],
            above: set[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    """
    Greedy placement never looks back, so a table that links two others can end up far
    from one of them. Try moving each table to a free cell, or swapping it with another,
    and keep every change that makes the whole layout cheaper, until nothing improves.
    """
    placed = dict(placed)
    best = _layout_cost(placed, adj, above)
    names = sorted(placed, key=lambda n: (-len(adj[n]), n))
    for _ in range(30):
        improved = False
        for name in names:
            cs = [c for c, _ in placed.values()]
            rs = [r for _, r in placed.values()]
            origin = placed[name]
            owner = {cell: other for other, cell in placed.items()}
            options = [(c, r) for c in range(min(cs) - 1, max(cs) + 2) for r in range(min(rs) - 1, max(rs) + 2)
                       if (c, r) != origin]
            winner, winner_cost = None, best - 1e-9
            for cell in options:
                trial = dict(placed)
                trial[name] = cell
                if cell in owner:
                    trial[owner[cell]] = origin          # swap places with whoever is there
                cost = _layout_cost(trial, adj, above)
                if cost < winner_cost:
                    winner, winner_cost = trial, cost
            if winner is not None:
                placed, best, improved = winner, winner_cost, True
        if not improved:
            break
    return placed


def _cell_score(cell: tuple[int, int], anchors: list[tuple[int, int]],
                taken: set[tuple[int, int]], wanted: list[int]) -> float:
    c, r = cell
    score = 0.0
    for (ac, ar), direction in zip(anchors, wanted):
        if direction and (r - ar) * direction <= 0:
            score += 15                                  # e.g. subclass not below its parent
    for ac, ar in anchors:
        dc, dr = abs(c - ac), abs(r - ar)
        score += 10 * (dc + dr)
        if dc and dr:
            score += 4                                   # needs an elbow
            blocked = (c, ar) in taken and (ac, r) in taken
        elif dr == 0:
            blocked = any((x, r) in taken for x in range(min(c, ac) + 1, max(c, ac)))
        else:
            blocked = any((c, y) in taken for y in range(min(r, ar) + 1, max(r, ar)))
        if blocked:
            score += 25                                  # line would cross a table
    # Stay close to the centre in every direction so chains curl around instead
    # of running off in a long line; a little wider than tall (screens are landscape)
    return score + 2 * math.hypot(c, 1.3 * r)


class GridGeometry:
    """Pixel centres for grid columns/rows, each sized to its widest/tallest cell."""

    def __init__(self, grid: dict[str, tuple[int, int]], extents: dict[str, Extent],
                 gap_x: Callable[[int], int], gap_y: Callable[[int], int],
                 min_half: tuple[int, int] = (0, 0)) -> None:
        self._gap_x, self._gap_y = gap_x, gap_y
        self._cols = self._axis({n: g[0] for n, g in grid.items()},
                                {n: (e[0], e[2]) for n, e in extents.items()},
                                gap_x, min_half[0])
        self._rows = self._axis({n: g[1] for n, g in grid.items()},
                                {n: (e[1], e[3]) for n, e in extents.items()},
                                gap_y, min_half[1])

    @staticmethod
    def _axis(index_of: dict[str, int], spans: dict[str, tuple[float, float]],
              gap: Callable[[int], int], min_half: int) -> dict[int, tuple[int, float, float]]:
        """Return {index: (centre, before, after)} along one axis."""
        members: dict[int, list[tuple[float, float]]] = {}
        for name, idx in index_of.items():
            members.setdefault(idx, []).append(spans[name])
        axis: dict[int, tuple[int, float, float]] = {}
        cursor = None
        for idx in range(min(members), max(members) + 1):
            items = members.get(idx, [])
            before = max([s[0] for s in items] + [min_half])
            after = max([s[1] for s in items] + [min_half])
            start = 0 if cursor is None else cursor + gap(idx - 1)
            centre = snap(start + before)
            axis[idx] = (centre, before, after)
            cursor = centre + after
        return axis

    @staticmethod
    def _at(axis: dict[int, tuple[int, float, float]],
            gap: Callable[[int], int], g: float) -> int:
        """Pixel for a grid coordinate; x.5 means the middle of the gap after x."""
        if float(g).is_integer():
            return axis[int(g)][0]
        lo = math.floor(g)
        hi = lo + 1
        if lo in axis and hi in axis:
            return snap((axis[lo][0] + axis[lo][2] + axis[hi][0] - axis[hi][1]) / 2)
        if hi in axis:
            return snap(axis[hi][0] - axis[hi][1] - gap(lo) / 2)
        return snap(axis[lo][0] + axis[lo][2] + gap(lo) / 2)

    def x(self, g: float) -> int:
        return self._at(self._cols, self._gap_x, g)

    def y(self, g: float) -> int:
        return self._at(self._rows, self._gap_y, g)


def half_steps(p: tuple[float, float], q: tuple[float, float]) -> list[tuple[float, float]]:
    """Grid positions in 0.5 steps strictly between two points on the same row or column."""
    n = int(round(2 * max(abs(q[0] - p[0]), abs(q[1] - p[1]))))
    return [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(1, n)]


def toward(p: tuple[float, float], q: tuple[float, float]) -> str:
    """Side of a box at `p` that faces `q` (same row or column)."""
    return h_side(q[0] - p[0]) if p[1] == q[1] else v_side(q[1] - p[1])


# ── Lanes: tracks in the gaps between rows/columns ───────────────────────────

@dataclass
class Lane:
    """A track in the gap after column/row `idx` for a line that has to go around tables."""
    axis: str        # 'x': vertical track between columns, 'y': horizontal track between rows
    idx: int
    sign: int        # which half of the gap the track lies in (−1 / +1)
    reach: float     # lines that travel further get tracks further from the gap centre
    k: int = 0


class LanePlanner:
    STEP = 20

    def __init__(self, base: Callable[[str, int], int]) -> None:
        self._base = base           # offset of the first track from the gap centre
        self._lanes: list[Lane] = []

    def request(self, axis: str, idx: int, sign: int, reach: float) -> Lane:
        lane = Lane(axis, idx, sign, reach)
        self._lanes.append(lane)
        return lane

    def finalize(self) -> None:
        """Give every lane its own track; call once all lanes are requested."""
        groups: dict[tuple[str, int, int], list[Lane]] = {}
        for lane in self._lanes:
            groups.setdefault((lane.axis, lane.idx, lane.sign), []).append(lane)
        for lanes in groups.values():
            for k, lane in enumerate(sorted(lanes, key=lambda ln: ln.reach)):
                lane.k = k

    def offset(self, lane: Lane) -> int:
        return lane.sign * (self._base(lane.axis, lane.idx) + self.STEP * lane.k)

    def half_extent(self, axis: str, idx: int) -> int:
        """How far from its centre the gap's tracks reach."""
        return max((abs(self.offset(ln)) for ln in self._lanes
                    if ln.axis == axis and ln.idx == idx), default=0)

    def position(self, lane: Lane, geo: 'GridGeometry') -> int:
        centre = geo.x(lane.idx + 0.5) if lane.axis == 'x' else geo.y(lane.idx + 0.5)
        return centre + self.offset(lane)


# ── Edge ports ───────────────────────────────────────────────────────────────

Port = tuple[float, float, float, float]   # relative x/y on the box + absolute dx/dy
PortRequest = tuple[str, Rect, str, str, Rect, str]  # src id/rect/side, dst id/rect/side


def side_port(side: str, offset: float = 0) -> Port:
    """Point on `side` of a box, `offset` px from the middle of that side."""
    return {'L': (0, 0.5, 0, offset), 'R': (1, 0.5, 0, offset),
            'T': (0.5, 0, offset, 0), 'B': (0.5, 1, offset, 0)}[side]


def port_point(rect: Rect, port: Port) -> tuple[float, float]:
    x, y, w, h = rect
    return x + port[0] * w + port[2], y + port[1] * h + port[3]


def _along(side: str, rect: Rect) -> float:
    """Centre of `rect` measured along the axis of `side`."""
    return rect[0] + rect[2] / 2 if side in 'TB' else rect[1] + rect[3] / 2


def _side_span(side: str, rect: Rect) -> tuple[float, float]:
    return (rect[0], rect[2]) if side in 'TB' else (rect[1], rect[3])


def assign_ports(edges: list[PortRequest]) -> list[tuple[Port, Port]]:
    """
    Spread edge endpoints evenly along each box side, ordered by where the
    other end lies so lines leaving the same side don't cross each other.
    Returns the (exit, entry) ports for each edge, in order.
    """
    groups: dict[tuple[str, str], list[tuple[float, int, int]]] = {}
    for i, (sid, srect, sside, did, drect, dside) in enumerate(edges):
        groups.setdefault((sid, sside), []).append((_along(sside, drect), i, 0))
        groups.setdefault((did, dside), []).append((_along(dside, srect), i, 1))

    offsets = [[0.0, 0.0] for _ in edges]
    for (_, side), items in groups.items():
        items.sort()
        length = _side_span(side, edges[items[0][1]][1 if items[0][2] == 0 else 4])[1]
        for k, (_, i, end) in enumerate(items):
            offsets[i][end] = round(length * ((k + 1) / (len(items) + 1) - 0.5))

    # A lone edge between two facing sides gets one shared coordinate so it is
    # drawn as a single straight segment instead of a zig-zag.
    for i, (sid, srect, sside, did, drect, dside) in enumerate(edges):
        if (OPPOSITE[sside] == dside and len(groups[(sid, sside)]) == 1
                and len(groups[(did, dside)]) == 1):
            lo_s, len_s = _side_span(sside, srect)
            lo_d, len_d = _side_span(dside, drect)
            lo, hi = max(lo_s, lo_d), min(lo_s + len_s, lo_d + len_d)
            if hi > lo:
                mid = min(max(snap((lo + hi) / 2), lo), hi)
                offsets[i] = [mid - lo_s - len_s / 2, mid - lo_d - len_d / 2]

    return [(side_port(e[2], o[0]), side_port(e[5], o[1])) for e, o in zip(edges, offsets)]


def _num(v: float) -> str:
    return f'{v:.4f}'.rstrip('0').rstrip('.')


def port_style(exit_port: Port, entry_port: Port) -> str:
    """Style fragment pinning an edge's two ends to exact points on its terminals."""
    return (
        f'exitX={_num(exit_port[0])};exitY={_num(exit_port[1])};'
        f'exitDx={_num(exit_port[2])};exitDy={_num(exit_port[3])};'
        f'entryX={_num(entry_port[0])};entryY={_num(entry_port[1])};'
        f'entryDx={_num(entry_port[2])};entryDy={_num(entry_port[3])};'
    )


def edge_style(exit_port: Port, entry_port: Port, routed: bool = False,
               ends: str = 'endArrow=none;startArrow=none;') -> str:
    """
    Line between two ports, without arrowheads unless `ends` says otherwise.
    Straight lines use draw.io's orthogonal router; `routed` lines follow
    their explicit waypoints exactly.
    """
    shape = ('edgeStyle=none;' if routed
             else 'edgeStyle=orthogonalEdgeStyle;orthogonalLoop=1;jettySize=auto;')
    return f'{shape}rounded=0;html=1;{ends}' + port_style(exit_port, entry_port)


# ── XML output ───────────────────────────────────────────────────────────────

class PageBuilder:
    """Collects cells for one diagram page and writes edges first, so lines sit behind shapes."""

    def __init__(self) -> None:
        self._ids = itertools.count(2)
        self._edges: list[ET.Element] = []
        self._vertices: list[ET.Element] = []
        self._top_geometry: list[ET.Element] = []
        self._waypoints: list[ET.Element] = []

    def _next_id(self) -> str:
        return str(next(self._ids))

    def vertex(self, value: str, style: str, rect: Rect, parent: str = '1') -> str:
        cid = self._next_id()
        cell = ET.Element('mxCell', id=cid, value=value, style=style,
                          vertex='1', parent=parent)
        x, y, w, h = (int(v) for v in rect)
        geo = ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                            width=str(w), height=str(h))
        geo.set('as', 'geometry')
        self._vertices.append(cell)
        if parent == '1':
            self._top_geometry.append(geo)
        return cid

    def edge(self, source: str, target: str, style: str,
             points: list[tuple[float, float]] | None = None, value: str = '') -> str:
        cid = self._next_id()
        cell = ET.Element('mxCell', id=cid, value=value, style=style, edge='1',
                          parent='1', source=source, target=target)
        geo = ET.SubElement(cell, 'mxGeometry', relative='1')
        geo.set('as', 'geometry')
        if points:
            array = ET.SubElement(geo, 'Array')
            array.set('as', 'points')
            for x, y in points:
                self._waypoints.append(ET.SubElement(array, 'mxPoint', x=str(int(x)), y=str(int(y))))
        self._edges.append(cell)
        return cid

    def end_label(self, edge_id: str, text: str, side: str, at_source: bool = True) -> None:
        """Small label (cardinality/multiplicity) at one end of an edge, beside the `side` it leaves from."""
        align, valign = _END_LABEL_ALIGN[side]
        cell = ET.Element('mxCell', id=self._next_id(), value=text,
                          style=(f'edgeLabel;resizable=0;html=1;align={align};'
                                 f'verticalAlign={valign};spacing=4;fontSize=11;'),
                          vertex='1', connectable='0', parent=edge_id)
        geo = ET.SubElement(cell, 'mxGeometry', x='-1' if at_source else '1', relative='1')
        geo.set('as', 'geometry')
        self._edges.append(cell)

    def to_model(self) -> ET.Element:
        # Shift everything so the diagram starts at the page margin
        if self._top_geometry:
            dx = PAGE_MARGIN - min(int(g.get('x')) for g in self._top_geometry)
            dy = PAGE_MARGIN - min(int(g.get('y')) for g in self._top_geometry)
            for g in self._top_geometry + self._waypoints:
                g.set('x', str(int(g.get('x')) + dx))
                g.set('y', str(int(g.get('y')) + dy))

        model = ET.Element('mxGraphModel', dx='1422', dy='762', grid='1',
                           gridSize=str(GRID), guides='1', tooltips='1', connect='1',
                           arrows='1', fold='1', page='0', pageScale='1',
                           pageWidth='1169', pageHeight='827', math='0', shadow='0')
        root = ET.SubElement(model, 'root')
        ET.SubElement(root, 'mxCell', id='0')
        ET.SubElement(root, 'mxCell', id='1').set('parent', '0')
        root.extend(self._edges)
        root.extend(self._vertices)
        return model


def build_mxfile(pages: list[tuple[str, ET.Element]]) -> str:
    """One .drawio file with a page (tab) per (name, mxGraphModel)."""
    mxfile = ET.Element('mxfile', host='ERD Generator')
    for idx, (name, model) in enumerate(pages, start=1):
        diagram = ET.SubElement(mxfile, 'diagram', id=f'page-{idx}', name=name)
        diagram.append(model)
    return ET.tostring(mxfile, encoding='unicode', xml_declaration=False)
