# backend/usecase.py
"""
Use case diagram from PlantUML-like text: parser → model → layout → draw.io cells.

    system Perpustakaan {                  system boundary around the use cases
      [Input]                              group label: the use cases below it, until the next group
      (Input Data Buku)                    use case (ellipse)
      [Proses]
      (Proses Peminjaman)
      [Output]
      (Cetak Laporan)
    }
    actor Petugas                          primary actor, drawn left of the system
    actor Pembayaran <<sekunder>>          secondary / external actor, drawn on the right
    Petugas --> (Login Petugas)            association (plain line)
    (Peminjaman Buku) ..> (Login Petugas) : <<include>>     dashed arrow with a label
    (Pengembalian Buku) ..> (Hitung Denda) : <<extend>>
    Admin <|-- SuperAdmin                  generalization (hollow triangle at Admin)

Layout: one column of equally wide ellipses inside the boundary, actors beside
it at the height of the use cases they use. Groups ([Input], [Proses], [Output])
stack in the order written, each under its own label with a dashed divider
between them; use cases outside any group come first. Lines between use cases (and
between actors) run around the outside of their column on lanes of their own,
so no line crosses another ellipse. No colours are hard-coded.
"""

import html
import math
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from layout import PageBuilder, Rect, port_style, snap  # type: ignore

CHAR_W = 7
UC_MIN_W, UC_MAX_W = 140, 260
UC_MIN_H = 60
UC_GAP = 30             # between ellipses (PRD: at least 30)
LINE_H = 20
ACTOR_W, ACTOR_H = 30, 60
ACTOR_STRIDE = 110      # actor top to next actor top: figure + label + air
TITLE_H = 50
GROUP_LABEL_H = 20      # a group's name above its first ellipse
GROUP_LABEL_GAP = 10
DIVIDER_H = 10          # dashed line between two groups
DIVIDER_GAP = 10
PAD_L = 60              # boundary edge to the ellipses
PAD_B = 30
OUTER_GAP = 100         # actor column to boundary
LANE_BASE = 60          # ellipse edge to the first lane
LANE_STEP = 50
SECONDARY = ('sekunder', 'secondary', 'eksternal', 'external')

BOUNDARY_STYLE = ('rounded=0;whiteSpace=wrap;html=1;container=1;collapsible=0;recursiveResize=0;'
                  'verticalAlign=top;align=center;fontStyle=1;fontSize=14;fillColor=none;')
USECASE_STYLE = 'ellipse;whiteSpace=wrap;html=1;'
GROUP_LABEL_STYLE = ('text;html=1;align=left;verticalAlign=middle;fontStyle=1;fontSize=12;'
                     'spacingLeft=0;strokeColor=none;fillColor=none;')
DIVIDER_STYLE = 'line;strokeWidth=1;dashed=1;html=1;fillColor=none;'
ACTOR_STYLE = 'shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;'
EDGE_BASE = 'html=1;edgeStyle=none;rounded=0;fontSize=11;'
EDGE_ENDS = {
    'assoc': 'endArrow=none;startArrow=none;',
    'dependency': 'endArrow=open;endSize=10;startArrow=none;dashed=1;',
    'generalization': 'endArrow=block;endFill=0;endSize=14;startArrow=none;',
}


# ── Model ────────────────────────────────────────────────────────────────────

@dataclass
class Rel:
    kind: str           # assoc, dependency, generalization
    src: str            # node keys: "(Name)" for a use case, "Name" for an actor
    dst: str            # the arrowhead, if any, is at dst
    label: str
    line: int


@dataclass
class UseCaseModel:
    title: str
    system: str = ''
    actors: dict[str, str] = field(default_factory=dict)       # name → 'L' or 'R'
    usecases: list[str] = field(default_factory=list)
    rels: list[Rel] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)            # group names in the order written
    group_of: dict[str, str] = field(default_factory=dict)     # use case → group ('' = none)


# ── Parser ───────────────────────────────────────────────────────────────────

_SYSTEM = re.compile(r'^(?:system|rectangle|package)\s+(.+?)\s*\{\s*$', re.IGNORECASE)
_ACTOR = re.compile(r'^actor\s+(.+?)(?:\s*<<\s*([\w ]+?)\s*>>)?\s*$', re.IGNORECASE)
_USECASE = re.compile(r'^\(([^()]+)\)\s*$')
_GROUP = re.compile(r'^\[\s*([^\[\]]+?)\s*\]$')
_OPERAND = r'(\([^()]+\)|[^()<>:|]+?)'
_REL = re.compile(rf'^{_OPERAND}\s*(<\|--|--\|>|\.\.>|-->|->|--)\s*{_OPERAND}\s*(?::\s*(.*))?$')


def parse_usecase(title: str, lines: list[tuple[int, str]]) -> tuple[UseCaseModel, list[tuple[int, str]]]:
    """Parse numbered text lines; bad lines are reported as (line, reason) and skipped."""
    model = UseCaseModel(title)
    errors: list[tuple[int, str]] = []
    inside: int | None = None        # line of the open `system {`
    group = ''                        # the group new use cases are written under

    def add_usecase(name: str) -> str:
        if name not in model.usecases:
            model.usecases.append(name)
            model.group_of[name] = group
        return f'({name})'

    def node(operand: str) -> str:
        operand = operand.strip()
        if operand.startswith('('):
            return add_usecase(operand[1:-1].strip())
        model.actors.setdefault(operand, 'L')
        return operand

    for lineno, raw in lines:
        text = raw.strip()
        if not text or text.startswith("'"):
            continue

        if inside is not None and text == '}':
            inside, group = None, ''
        elif m := _GROUP.match(text):
            group = m.group(1)
            if group not in model.groups:
                model.groups.append(group)
        elif m := _SYSTEM.match(text):
            if model.system or inside is not None:
                errors.append((lineno, 'Hanya satu blok system per halaman'))
            else:
                model.system, inside = m.group(1).strip(), lineno
        elif m := _ACTOR.match(text):
            name = m.group(1).strip()
            model.actors[name] = 'R' if (m.group(2) or '').strip().lower() in SECONDARY else 'L'
        elif m := _USECASE.match(text):
            add_usecase(m.group(1).strip())
        elif m := _REL.match(text):
            # Use cases first named in a line like this one belong to no group
            group, saved = '', group
            left, op, right, label = m.groups()
            src, dst = node(left), node(right)
            if op == '<|--':                       # right is the child, the triangle sits at the left
                model.rels.append(Rel('generalization', dst, src, (label or '').strip(), lineno))
            elif op == '--|>':
                model.rels.append(Rel('generalization', src, dst, (label or '').strip(), lineno))
            elif op == '..>':
                model.rels.append(Rel('dependency', src, dst, (label or '').strip(), lineno))
            else:
                model.rels.append(Rel('assoc', src, dst, (label or '').strip(), lineno))
            group = saved
        else:
            errors.append((lineno, f'Baris tidak dikenali: "{text}". Contoh: actor Admin, [Input], (Input Data), Admin --> (Input Data)'))

    if inside is not None:
        errors.append((inside, "blok system belum ditutup dengan '}'"))
    return model, errors


# ── Layout & render ──────────────────────────────────────────────────────────

def render_usecase(model: UseCaseModel) -> ET.Element:
    ucs = model.usecases
    actors = list(model.actors)

    # ── Ellipses: one width for all, height by wrapped lines ────────────────
    longest = max(len(n) for n in ucs)
    uc_w = max(UC_MIN_W, min(UC_MAX_W, int(math.ceil(longest * CHAR_W / 0.68 / 10)) * 10))
    inner = max(8, int(uc_w * 0.68) // CHAR_W)
    uc_lines = {n: textwrap.wrap(n, inner) or [n] for n in ucs}
    uc_h = {n: max(UC_MIN_H, int(math.ceil((LINE_H * len(uc_lines[n]) + 30) / 10)) * 10) for n in ucs}

    # Ungrouped use cases first, then each group in the order written
    ordered = [(g, [n for n in ucs if model.group_of.get(n, '') == g]) for g in ['', *model.groups]]
    ordered = [(g, members) for g, members in ordered if members]

    uc_top: dict[str, int] = {}
    labels: list[tuple[str, int]] = []          # (group name, y)
    dividers: list[int] = []
    y = TITLE_H
    for i, (g, members) in enumerate(ordered):
        if i:
            dividers.append(y - UC_GAP + (UC_GAP + DIVIDER_GAP) // 2)   # midway to the next label
            y += DIVIDER_H + DIVIDER_GAP
        if g:
            labels.append((g, y))
            y += GROUP_LABEL_H + GROUP_LABEL_GAP
        for n in members:
            uc_top[n] = y
            y += uc_h[n] + UC_GAP
    stack_end = y - UC_GAP
    uc_mid = {n: uc_top[n] + uc_h[n] // 2 for n in ucs}

    # ── Actors: at the height of the use cases they use, no overlaps ────────
    def uc_of(rel: Rel, actor: str) -> str | None:
        other = rel.dst if rel.src == actor else rel.src
        return other[1:-1] if other.startswith('(') else None

    desired: dict[str, float] = {}
    for a in actors:
        mids = [uc_mid[u] for r in model.rels if r.kind == 'assoc' and a in (r.src, r.dst)
                if (u := uc_of(r, a)) in uc_mid]
        desired[a] = (sum(mids) / len(mids) if mids else (TITLE_H + stack_end) / 2) - ACTOR_H / 2

    actor_top: dict[str, int] = {}
    for side in 'LR':
        previous = None
        for a in sorted((a for a in actors if model.actors[a] == side), key=lambda a: (desired[a], actors.index(a))):
            top = max(snap(desired[a]), 40, (previous + ACTOR_STRIDE) if previous is not None else 0)
            actor_top[a] = previous = top
    actors_end = max([t + ACTOR_H + LINE_H for t in actor_top.values()] + [0])
    height = snap(max(stack_end, actors_end) + PAD_B)

    # ── Lanes: each line that runs around a column gets a track, reused when spans are disjoint ──
    def centre(key: str) -> int:
        return uc_mid[key[1:-1]] if key.startswith('(') else actor_top[key] + ACTOR_H // 2

    def lanes_for(rels: list[Rel]) -> dict[int, int]:
        taken: list[list[tuple[int, int]]] = []
        assigned: dict[int, int] = {}
        for rel in sorted(rels, key=lambda r: abs(centre(r.src) - centre(r.dst))):
            lo, hi = sorted((centre(rel.src), centre(rel.dst)))
            for k, spans in enumerate(taken):
                if all(hi + 20 < a or lo - 20 > b for a, b in spans):
                    spans.append((lo, hi))
                    assigned[id(rel)] = k
                    break
            else:
                taken.append([(lo, hi)])
                assigned[id(rel)] = len(taken) - 1
        return assigned

    def is_uc(key: str) -> bool:
        return key.startswith('(')

    # A line between an actor and a use case is drawn straight; the rest goes around its column
    uc_loops = [r for r in model.rels if is_uc(r.src) and is_uc(r.dst)]
    actor_loops = {side: [r for r in model.rels if not is_uc(r.src) and not is_uc(r.dst)
                          and model.actors[r.src] == side] for side in 'LR'}
    uc_lane = lanes_for(uc_loops)
    side_lane = {side: lanes_for(actor_loops[side]) for side in 'LR'}
    uc_lane_count = max(uc_lane.values(), default=-1) + 1
    side_lane_count = {s: max(side_lane[s].values(), default=-1) + 1 for s in 'LR'}

    # ── Columns, left to right ──────────────────────────────────────────────
    widths = {s: max([len(a) * CHAR_W + 20 for a in actors if model.actors[a] == s] + [ACTOR_W + 30])
              for s in 'LR'}
    has = {s: any(v == s for v in model.actors.values()) for s in 'LR'}
    x_left = 40 * side_lane_count['L'] + 40 if has['L'] else 0
    left_end = x_left + (widths['L'] if has['L'] else 0)
    bx = snap(left_end + (OUTER_GAP if has['L'] else 0))
    title = model.system or model.title
    right_room = (LANE_BASE + LANE_STEP * (uc_lane_count - 1) + 50) if uc_lane_count else PAD_L
    bw = snap(max(PAD_L + uc_w + right_room, int(len(title) * 8.5) + 40))
    x_right = bx + bw + OUTER_GAP

    actor_x: dict[str, int] = {}
    for a in actors:
        if model.actors[a] == 'L':
            actor_x[a] = snap(x_left + (widths['L'] - ACTOR_W) // 2)
        else:
            actor_x[a] = snap(x_right + (widths['R'] - ACTOR_W) // 2)
    uc_x = bx + PAD_L

    # ── Cells ───────────────────────────────────────────────────────────────
    page = PageBuilder()
    boundary = page.vertex(html.escape(title), BOUNDARY_STYLE, (bx, 0, bw, height))
    cell: dict[str, str] = {}
    rect: dict[str, Rect] = {}
    # Labels and dividers span the ellipse column only, so no actor line crosses them
    for g, gy in labels:
        page.vertex(html.escape(g), GROUP_LABEL_STYLE, (PAD_L, gy, uc_w, GROUP_LABEL_H), parent=boundary)
    for dy in dividers:
        page.vertex('', DIVIDER_STYLE, (PAD_L, dy, uc_w, DIVIDER_H), parent=boundary)
    for n in ucs:
        cell[f'({n})'] = page.vertex('<br>'.join(html.escape(line) for line in uc_lines[n]), USECASE_STYLE,
                                      (PAD_L, uc_top[n], uc_w, uc_h[n]), parent=boundary)
        rect[f'({n})'] = (uc_x, uc_top[n], uc_w, uc_h[n])
    for a in actors:
        cell[a] = page.vertex(html.escape(a), ACTOR_STYLE, (actor_x[a], actor_top[a], ACTOR_W, ACTOR_H))
        rect[a] = (actor_x[a], actor_top[a], ACTOR_W, ACTOR_H)

    for rel in model.rels:
        ends = EDGE_ENDS[rel.kind]
        label = html.escape(rel.label)
        s_uc, d_uc = is_uc(rel.src), is_uc(rel.dst)
        if s_uc != d_uc:                                              # actor ↔ use case: straight line
            a = rel.dst if s_uc else rel.src
            on_left = model.actors[a] == 'L'
            actor_port = (1, 0.35, 0, 0) if on_left else (0, 0.35, 0, 0)
            uc_port = (0, 0.5, 0, 0) if on_left else (1, 0.5, 0, 0)
            ports = (uc_port, actor_port) if s_uc else (actor_port, uc_port)
            page.edge(cell[rel.src], cell[rel.dst], EDGE_BASE + ends + port_style(*ports), value=label)
            continue
        # Everything else runs around the outside of its column
        if s_uc and d_uc:
            lane_x = uc_x + uc_w + LANE_BASE + LANE_STEP * uc_lane[id(rel)]
            port = (1, 0.5, 0, 0)
        else:
            on_left = model.actors[rel.src] == 'L'
            k = side_lane[model.actors[rel.src]][id(rel)]
            if on_left:
                lane_x, port = x_left - 30 - 40 * k, (0, 0.5, 0, 0)
            else:
                lane_x, port = x_right + widths['R'] + 30 + 40 * k, (1, 0.5, 0, 0)
        page.edge(cell[rel.src], cell[rel.dst], EDGE_BASE + ends + port_style(port, port),
                  points=[(lane_x, centre(rel.src)), (lane_x, centre(rel.dst))], value=label)

    return page.to_model()


# ── Page entry point ─────────────────────────────────────────────────────────

def build_usecase_page(title: str, lines: list[tuple[int, str]]) -> tuple[ET.Element | None, list[tuple[int, str]]]:
    model, errors = parse_usecase(title, lines)
    if not model.usecases:
        first_line = lines[0][0] if lines else 0
        return None, errors + [(first_line, f'Halaman "{title}" belum berisi use case (contoh: (Login Petugas))')]
    return render_usecase(model), errors
