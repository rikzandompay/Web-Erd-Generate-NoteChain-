# backend/activity.py
"""
Activity diagram with swimlanes from PlantUML-like text: parser → model → layout → draw.io cells.

    |Admin|                          switch swimlane
    start / stop                     start and end nodes
    :Membuka halaman login;          action (may continue over several lines up to ';')
    if (Data valid?) then (ya)       decision; `elseif (…) then (…)`, `else (…)`, `endif`
    fork / fork again / end fork     parallel branches
    -> Mengisi email dan password    arrow back to an earlier action (loop)

Every step gets its own row, so lines between consecutive steps only run
downwards; lines that skip rows or go back up follow tracks along the lane
edges. No colours are hard-coded.
"""

import html
import math
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from layout import PageBuilder, Port, Rect, port_style  # type: ignore

# ── Layout constants ─────────────────────────────────────────────────────────
CHAR_W = 7
LANE_MIN_W = 260        # every lane gets the same width (PRD ACT-1)
HEADER_H = 30           # pool title and lane name rows
ACTION_W = 180
ACTION_MIN_H = 40
LINE_H = 20             # extra height per wrapped action line
NODE_D = 40             # start / stop / decision / merge size
BAR_H = 20              # fork/join cell; the thick line is drawn through its middle
ROW_GAP = 30            # between the rows of steps (PRD ACT-3)
SUB_GAP = 40            # between parallel branches side by side
TRACK_STEP = 10         # between tracks along a lane edge
TRACK_INSET = 20        # lane edge → first track
CONTENT_PAD = 20        # lane header → first row, last row → pool bottom

POOL_STYLE = ('swimlane;html=1;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;'
              'horizontal=1;horizontalStack=1;startSize=30;fontStyle=1;fontSize=14;')
LANE_STYLE = 'swimlane;html=1;startSize=30;horizontal=1;'
NODE_STYLES = {
    # fillColor=strokeColor fills with the line colour, so the dot follows the light/dark theme
    'start': 'ellipse;html=1;shape=startState;fillColor=strokeColor;',
    'stop': 'ellipse;html=1;shape=endState;fillColor=strokeColor;',
    'action': 'rounded=1;whiteSpace=wrap;html=1;arcSize=40;',
    'decision': ('rhombus;html=1;labelPosition=right;verticalLabelPosition=top;'
                 'align=left;verticalAlign=bottom;spacingLeft=-10;'),
    'merge': 'rhombus;html=1;',
    'fork': 'shape=line;html=1;strokeWidth=6;',
    'join': 'shape=line;html=1;strokeWidth=6;',
}
EDGE_ENDS = 'endArrow=open;endSize=8;startArrow=none;exitPerimeter=0;entryPerimeter=0;'


# ── Model ────────────────────────────────────────────────────────────────────

@dataclass(eq=False)
class Step:
    kind: str           # start, stop, action
    text: str
    lane: str
    line: int


@dataclass(eq=False)
class Branch:
    label: str
    items: list = field(default_factory=list)


@dataclass(eq=False)
class Decision:
    condition: str
    lane: str
    line: int
    branches: list[Branch] = field(default_factory=list)


@dataclass(eq=False)
class Fork:
    lane: str
    line: int
    branches: list[list] = field(default_factory=list)


@dataclass(eq=False)
class Goto:
    target: str
    line: int


@dataclass
class ActivityModel:
    title: str
    lanes: list[str]            # in order of first use; [] → a pool without lanes
    items: list


# ── Parser ───────────────────────────────────────────────────────────────────

_LANE = re.compile(r'^\|\s*(.+?)\s*\|$')
_IF = re.compile(r'^if\s*\((.*?)\)\s*(?:then\s*(?:\((.*)\))?)?$', re.IGNORECASE)
_ELSEIF = re.compile(r'^else\s*if\s*\((.*?)\)\s*(?:then\s*(?:\((.*)\))?)?$', re.IGNORECASE)
_ELSE = re.compile(r'^else\s*(?:\((.*)\))?$', re.IGNORECASE)
_ENDIF = re.compile(r'^end\s*if$', re.IGNORECASE)
_FORK = re.compile(r'^fork$', re.IGNORECASE)
_FORK_AGAIN = re.compile(r'^fork\s+again$', re.IGNORECASE)
_END_FORK = re.compile(r'^end\s*(fork|merge)$', re.IGNORECASE)
_GOTO = re.compile(r'^->\s*(.+?);?$')


def parse_activity(title: str, lines: list[tuple[int, str]]) -> tuple[ActivityModel, list[tuple[int, str]]]:
    """Parse numbered text lines; bad lines are reported as (line, reason) and skipped."""
    lanes: list[str] = []
    lane = ''
    root: list = []
    stack: list[tuple[Decision | Fork, list]] = []   # open blocks with the item list being filled
    errors: list[tuple[int, str]] = []
    pending: tuple[int, list[str]] | None = None     # multi-line action being collected

    def items() -> list:
        return stack[-1][1] if stack else root

    for lineno, raw in lines:
        text = raw.strip()
        if pending:
            pending[1].append(text)
            if text.endswith(';'):
                body = ' '.join(pending[1])[1:-1].strip()
                items().append(Step('action', body, lane, pending[0]))
                pending = None
            continue
        if not text or text.startswith("'") or text.startswith('//'):
            continue
        lower = text.lower()
        if lower.startswith(('@startuml', '@enduml', 'title ', 'skinparam', 'scale', 'footer', 'header')):
            continue
        if lower.startswith(('note left', 'note right', 'note over')):
            continue

        if m := _LANE.match(text):
            lane = m.group(1)
            if lane not in lanes:
                lanes.append(lane)
        elif text.lower() == 'start':
            items().append(Step('start', '', lane, lineno))
        elif text.lower() in ('stop', 'end'):
            items().append(Step('stop', '', lane, lineno))
        elif text.startswith(':'):
            if text.endswith(';') and len(text) > 1:
                items().append(Step('action', text[1:-1].strip(), lane, lineno))
            else:
                pending = (lineno, [text])
        elif m := _IF.match(text):
            decision = Decision(m.group(1).strip(), lane, lineno, [Branch(_label(m.group(2)))])
            items().append(decision)
            stack.append((decision, decision.branches[0].items))
        elif m := _ELSEIF.match(text) or _ELSE.match(text):
            if stack and isinstance(stack[-1][0], Decision):
                decision = stack[-1][0]
                label = _label(m.group(2) if m.re is _ELSEIF else m.group(1)) or (
                    m.group(1).strip() if m.re is _ELSEIF else '')
                decision.branches.append(Branch(label))
                stack[-1] = (decision, decision.branches[-1].items)
            else:
                errors.append((lineno, "'else' tanpa 'if' yang dibuka"))
        elif _ENDIF.match(text):
            if stack and isinstance(stack[-1][0], Decision):
                lane = stack.pop()[0].lane
            else:
                errors.append((lineno, "'endif' tanpa 'if' yang dibuka"))
        elif _FORK.match(text):
            fork = Fork(lane, lineno, [[]])
            items().append(fork)
            stack.append((fork, fork.branches[0]))
        elif _FORK_AGAIN.match(text):
            if stack and isinstance(stack[-1][0], Fork):
                fork = stack[-1][0]
                fork.branches.append([])
                stack[-1] = (fork, fork.branches[-1])
            else:
                errors.append((lineno, "'fork again' tanpa 'fork' yang dibuka"))
        elif _END_FORK.match(text):
            if stack and isinstance(stack[-1][0], Fork):
                lane = stack.pop()[0].lane
            else:
                errors.append((lineno, "'end fork' tanpa 'fork' yang dibuka"))
        elif m := _GOTO.match(text):
            items().append(Goto(m.group(1).strip(), lineno))
        else:
            errors.append((lineno, f'Baris tidak dikenali: "{text}". Contoh aksi: :Mengisi data;'))

    if pending:
        errors.append((pending[0], "aksi belum ditutup dengan ';'"))
    for block, _ in stack:
        word = 'endif' if isinstance(block, Decision) else 'end fork'
        errors.append((block.line, f"blok dibuka di sini belum ditutup dengan '{word}'"))
    return ActivityModel(title, lanes, root), errors


def _label(text: str | None) -> str:
    return (text or '').strip()


# ── Layout ───────────────────────────────────────────────────────────────────

@dataclass(eq=False)
class _Node:
    kind: str
    text: str
    lane: str
    rank: int
    sub: int                    # parallel column inside the lane (forks)
    lines: list[str] = field(default_factory=list)
    x: int = 0                  # centre
    y: int = 0
    w: int = 0
    h: int = 0

    @property
    def rect(self) -> Rect:
        return (self.x - self.w // 2, self.y - self.h // 2, self.w, self.h)


@dataclass(eq=False)
class _Edge:
    src: _Node
    dst: _Node
    label: str = ''
    branch: int | None = None   # decision branch index (0 leaves downwards, 1 right, 2 left)
    track: tuple[str, str, int] | None = None   # (lane, side, index) for detours


@dataclass
class ActivityLayout:
    nodes: list[_Node]
    edges: list[_Edge]
    lanes: list[str]
    lane_w: int
    height: int                 # pool height


def layout_activity(model: ActivityModel, errors: list[tuple[int, str]]) -> ActivityLayout:
    lanes = model.lanes or ['']
    nodes: list[_Node] = []
    edges: list[_Edge] = []
    actions: dict[str, _Node] = {}
    gotos: list[tuple[list, Goto]] = []

    def add(kind: str, text: str, lane: str, rank: int, sub: int) -> _Node:
        node = _Node(kind, text, lane or lanes[0], rank, sub)
        nodes.append(node)
        if kind == 'action':
            actions.setdefault(text.lower(), node)
        return node

    def connect(preds: list, node: _Node) -> None:
        for src, label, branch in preds:
            edges.append(_Edge(src, node, label, branch))

    def walk(items: list, rank: int, preds: list, sub: int) -> tuple[int, list]:
        """Place `items` from row `rank`; returns the next free row and the open ends."""
        for item in items:
            if isinstance(item, Step):
                node = add(item.kind, item.text, item.lane, rank, sub)
                connect(preds, node)
                preds = [] if item.kind == 'stop' else [(node, '', None)]
                rank += 1
            elif isinstance(item, Decision):
                decision = add('decision', item.condition, item.lane, rank, sub)
                connect(preds, decision)
                rank += 1
                ends = []
                for i, branch in enumerate(item.branches):
                    rank, tails = walk(branch.items, rank, [(decision, branch.label, i)], sub)
                    ends += tails
                if len(item.branches) == 1:     # no else: the condition can also be false
                    ends.append((decision, '', 1))
                if len(ends) > 1:
                    merge = add('merge', '', item.lane, rank, sub)
                    connect(ends, merge)
                    preds = [(merge, '', None)]
                    rank += 1
                else:   # other branches stopped or looped back: nothing to merge
                    preds = ends
            elif isinstance(item, Fork):
                bar = add('fork', '', item.lane, rank, sub)
                connect(preds, bar)
                start, offset, last, ends = rank + 1, sub, rank + 1, []
                for branch in item.branches:
                    end, tails = walk(branch, start, [(bar, '', None)], offset)
                    last, ends = max(last, end), ends + tails
                    offset += _span(branch)
                join = add('join', '', item.lane, last, sub)
                connect(ends, join)
                preds = [(join, '', None)]
                rank = last + 1
            else:   # Goto: the flow jumps back, nothing continues from here
                gotos.append((preds, item))
                preds = []
        return rank, preds

    walk(model.items, 0, [], 0)
    for preds, goto in gotos:
        target = actions.get(goto.target.lower())
        if target is None:
            errors.append((goto.line, f'Aksi tujuan "{goto.target}" tidak ditemukan'))
        else:
            connect(preds, target)

    # ── Node sizes ──────────────────────────────────────────────────────────
    for node in nodes:
        if node.kind == 'action':
            node.lines = textwrap.wrap(node.text, (ACTION_W - 20) // CHAR_W) or ['']
            node.w, node.h = ACTION_W, ACTION_MIN_H + LINE_H * (len(node.lines) - 1)
        elif node.kind in ('fork', 'join'):
            node.w, node.h = 0, BAR_H                   # width set from its branches below
        else:
            node.w = node.h = NODE_D
            if node.kind == 'decision':
                node.lines = textwrap.wrap(node.text, 18) or ['']

    # ── Detour tracks along lane edges (in row units) ───────────────────────
    lane_index = {name: i for i, name in enumerate(lanes)}
    used: dict[tuple[str, str], list[list[tuple[int, int]]]] = {}
    for edge in edges:
        if _route_kind(edge) != 'track':
            continue
        lane, side = _track_place(edge, lane_index)
        lo, hi = sorted((edge.src.rank, edge.dst.rank))
        tracks = used.setdefault((lane, side), [])
        k = next((k for k, spans in enumerate(tracks)
                  if all(hi < a or lo > b for a, b in spans)), len(tracks))
        if k == len(tracks):
            tracks.append([])
        tracks[k].append((lo, hi))
        edge.track = (lane, side, k)

    # ── Lane width: equal for all, wide enough for parallel branches and tracks
    subs = max((n.sub for n in nodes), default=0) + 1
    content = subs * ACTION_W + (subs - 1) * SUB_GAP
    margin = max((TRACK_INSET + TRACK_STEP * len(t) for t in used.values()), default=TRACK_INSET) + 10
    lane_w = _ceil(max(LANE_MIN_W, content + 2 * margin), 20)

    # ── Rows ────────────────────────────────────────────────────────────────
    ranks = max((n.rank for n in nodes), default=-1) + 1
    row_h = [max([n.h for n in nodes if n.rank == r], default=0) for r in range(ranks)]
    # A decision's condition sits above it: long conditions push its row down
    extra = [max([_ceil(15 * len(n.lines), 10) - ROW_GAP + 10
                  for n in nodes if n.rank == r and n.kind == 'decision'] + [0])
             for r in range(ranks)]
    top = HEADER_H + (HEADER_H if model.lanes else 0) + CONTENT_PAD
    centres, y = [], top
    for h, pad in zip(row_h, extra):
        y += pad
        centres.append(y + h // 2)
        y += h + ROW_GAP
    height = y - ROW_GAP + CONTENT_PAD

    sub_used: dict[str, int] = {}
    for n in nodes:
        sub_used[n.lane] = max(sub_used.get(n.lane, 0), n.sub + 1)
    for n in nodes:
        lane_centre = lane_index[n.lane] * lane_w + lane_w // 2
        width = sub_used[n.lane]
        n.x = lane_centre + int((n.sub - (width - 1) / 2) * (ACTION_W + SUB_GAP))
        n.y = centres[n.rank]

    # Fork/join bars are as wide as the branches they split or join (PRD ACT-8)
    for n in nodes:
        if n.kind in BARS:
            # Only the parallel branches count: the step before a fork or after a join may sit in another lane
            linked = [e.dst for e in edges if e.src is n] if n.kind == 'fork' else [e.src for e in edges if e.dst is n]
            left = min((m.x - m.w // 2 for m in linked if m.kind not in BARS), default=n.x - 60) - 20
            right = max((m.x + m.w // 2 for m in linked if m.kind not in BARS), default=n.x + 60) + 20
            n.w = _ceil(right - left, 20)
            n.x = left + n.w // 2

    return ActivityLayout(nodes, edges, model.lanes, lane_w, height)


def _span(items: list) -> int:
    """Parallel columns a list of items needs."""
    widest = 1
    for item in items:
        if isinstance(item, Fork):
            widest = max(widest, sum(_span(b) for b in item.branches))
        elif isinstance(item, Decision):
            widest = max([widest] + [_span(b.items) for b in item.branches])
    return widest


BARS = ('fork', 'join')


def _route_kind(edge: _Edge) -> str:
    """'straight' / 'zigzag' to the next row, 'track' for anything that skips rows or goes back."""
    a, b = edge.src, edge.dst
    if b.rank != a.rank + 1:
        return 'track'
    if (a.lane, a.sub) == (b.lane, b.sub) or a.kind in BARS or b.kind in BARS:
        return 'straight'       # bars stretch to sit above / below each branch
    return 'zigzag'


def _track_place(edge: _Edge, lane_index: dict[str, int]) -> tuple[str, str]:
    """Lane and side whose edge track a detour runs along."""
    a, b = edge.src, edge.dst
    if a.lane != b.lane:
        return b.lane, ('L' if lane_index[a.lane] < lane_index[b.lane] else 'R')
    if a.kind == 'decision' and edge.branch:
        return b.lane, 'R' if edge.branch % 2 else 'L'
    return b.lane, 'R' if b.rank < a.rank else 'L'


def _ceil(v: float, step: int) -> int:
    return int(math.ceil(v / step)) * step


# ── Renderer ─────────────────────────────────────────────────────────────────

def render_activity(model: ActivityModel, lay: ActivityLayout) -> ET.Element:
    page = PageBuilder()
    lanes = lay.lanes or ['']
    pool_w = lay.lane_w * len(lanes)
    pool = page.vertex(html.escape(model.title), POOL_STYLE, (0, 0, pool_w, lay.height))

    # Lanes are children of the pool, nodes children of their lane (all move together)
    parent_of: dict[str, tuple[str, int, int]] = {}      # lane → (cell, absolute x, absolute y)
    for i, name in enumerate(lanes):
        if lay.lanes:
            cid = page.vertex(html.escape(name), LANE_STYLE,
                              (i * lay.lane_w, HEADER_H, lay.lane_w, lay.height - HEADER_H), parent=pool)
            parent_of[name] = (cid, i * lay.lane_w, HEADER_H)
        else:
            parent_of[name] = (pool, 0, 0)

    cell_of: dict[int, str] = {}
    for n in lay.nodes:
        cid, px, py = parent_of[n.lane]
        x, y, w, h = n.rect
        value = '<br>'.join(html.escape(line) for line in n.lines)
        cell_of[id(n)] = page.vertex(value, NODE_STYLES[n.kind], (x - px, y - py, w, h), parent=cid)

    for e in lay.edges:
        start, end, points, exit_side = _path(e, lay)
        style = 'html=1;rounded=0;' + ('edgeStyle=none;' if points else 'edgeStyle=orthogonalEdgeStyle;')
        style += EDGE_ENDS + port_style(_port(e.src, start), _port(e.dst, end))
        edge_id = page.edge(cell_of[id(e.src)], cell_of[id(e.dst)], style, points)
        if e.label:
            # Branch labels sit beside the line, away from the condition text above the diamond
            page.end_label(edge_id, html.escape(f'[{e.label}]'), 'B' if exit_side in 'BR' else 'L')

    return page.to_model()


def _port(node: _Node, point: tuple[int, int]) -> Port:
    x, y, _, _ = node.rect
    return (0, 0, point[0] - x, point[1] - y)


def _spans(bar: _Node, x: int) -> bool:
    return bar.x - bar.w // 2 <= x <= bar.x + bar.w // 2


def _anchor(node: _Node, side: str, x: int | None = None) -> tuple[int, int]:
    """Where a line meets `node` on `side`; bars take any x along their length."""
    if node.kind in ('fork', 'join'):
        return (x if x is not None else node.x, node.y)
    return {'T': (node.x, node.y - node.h // 2), 'B': (node.x, node.y + node.h // 2),
            'L': (node.x - node.w // 2, node.y), 'R': (node.x + node.w // 2, node.y)}[side]


def _path(e: _Edge, lay: ActivityLayout):
    """(start, end, bends, exit side) of an edge."""
    a, b = e.src, e.dst
    kind = _route_kind(e)
    if kind == 'straight':
        x = b.x if a.kind in BARS else a.x
        if all(_spans(n, x) for n in (a, b) if n.kind in BARS):
            return _anchor(a, 'B', x), _anchor(b, 'T', x), [], 'B'
        kind = 'zigzag'         # a bar that doesn't reach across to the other end
    if kind == 'zigzag':
        start, end = _anchor(a, 'B'), _anchor(b, 'T')
        mid = (start[1] + end[1]) // 2
        mid -= mid % 10
        return start, end, [(start[0], mid), (end[0], mid)], 'B'

    lane, side, k = e.track
    lane_x = (lay.lanes or ['']).index(lane) * lay.lane_w
    track_x = (lane_x + TRACK_INSET + TRACK_STEP * k if side == 'L'
               else lane_x + lay.lane_w - TRACK_INSET - TRACK_STEP * k)
    exit_side = 'L' if track_x < a.x else 'R'
    if a.kind == 'decision' and e.branch == 0 and a.lane == b.lane:
        exit_side = 'L'
    start = _anchor(a, exit_side)
    end = _anchor(b, 'L' if track_x < b.x else 'R')
    return start, end, [(track_x, start[1]), (track_x, end[1])], exit_side


# ── Page entry point ─────────────────────────────────────────────────────────

def build_activity_page(title: str, lines: list[tuple[int, str]]) -> tuple[ET.Element | None, list[tuple[int, str]]]:
    model, errors = parse_activity(title, lines)
    if not model.items:
        first_line = lines[0][0] if lines else 0
        return None, errors + [(first_line, f'Halaman "{title}" belum berisi aktivitas (contoh: start, :Aksi;, stop)')]
    layout = layout_activity(model, errors)
    return render_activity(model, layout), sorted(errors)
