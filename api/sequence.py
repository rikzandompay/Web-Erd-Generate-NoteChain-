# backend/sequence.py
"""
Sequence diagram from PlantUML-like text: parser → model → layout → draw.io cells.

    actor Admin                                  participants: actor, boundary, control,
    boundary Sistem                              entity, participant, database
    Admin -> Sistem : Mengklik Tombol Edit       message (solid line, filled arrowhead)
    Sistem --> Admin : Menampilkan Form Edit     reply (dashed line, open arrowhead)
    Sistem -> Sistem : Validasi Data             self-call
    alt kondisi / else kondisi / end             fragments; also loop … end and opt … end

Messages are numbered automatically. No colours are hard-coded, so the page
follows draw.io's light/dark theme.
"""

import html
import math
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from layout import PageBuilder, Rect, port_style  # type: ignore

PARTICIPANT_KINDS = ('actor', 'boundary', 'control', 'entity', 'participant', 'database')
FRAGMENT_KINDS = ('alt', 'loop', 'opt')

# ── Layout constants ─────────────────────────────────────────────────────────
CHAR_W = 7              # rough width of one character at font size 12
HEADER_H = 40           # lifeline header box
HEADER_MIN_W = 100
ACTOR_W = 20            # actor lifelines are as wide as the stick figure; the name may overhang
MIN_GAP = 160           # between neighbouring lifeline centres
MAX_LABEL_W = 280       # longer message labels wrap onto more lines
BAR_W = 10              # activation bar
ROW = 40                # between messages
LINE_H = 20             # extra room per wrapped label line
SELF_W = 40             # self-call loop width / height
SELF_H = 20
FRAME_PAD = 40          # frame → lifelines
FRAME_TAB_H = 30
FRAGMENT_PAD = 30       # fragment → outermost lifeline inside it (+10 per nested level)

FRAME_STYLE = ('shape=umlFrame;whiteSpace=wrap;html=1;pointerEvents=0;fillColor=none;'
               'fontStyle=1;fontSize=14;height=30;width={w};')
FRAGMENT_STYLE = 'shape=umlFrame;whiteSpace=wrap;html=1;pointerEvents=0;fillColor=none;height=30;width={w};'
CONDITION_STYLE = 'text;html=1;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;'
SEPARATOR_STYLE = 'line;html=1;dashed=1;strokeWidth=1;fillColor=none;'
LIFELINE_STYLE = ('shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=1;container=1;'
                  'dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;'
                  'portConstraint=eastwest;size=40;')
ACTOR_STYLE = ('shape=umlLifeline;participant=umlActor;perimeter=lifelinePerimeter;whiteSpace=wrap;'
               'html=1;container=1;dropTarget=0;collapsible=0;recursiveResize=0;outlineConnect=0;'
               'portConstraint=eastwest;verticalAlign=top;spacingTop=36;labelBackgroundColor=none;size=40;')
ACTIVATION_STYLE = ('html=1;points=[];perimeter=orthogonalPerimeter;outlineConnect=0;'
                    'targetShapes=umlLifeline;portConstraint=eastwest;')
_MESSAGE_BASE = 'html=1;edgeStyle=none;curved=0;rounded=0;fontSize=12;exitPerimeter=0;entryPerimeter=0;'
MESSAGE_STYLE = _MESSAGE_BASE + 'endArrow=block;'
REPLY_STYLE = _MESSAGE_BASE + 'endArrow=open;dashed=1;endSize=8;'
LABEL_ABOVE = 'verticalAlign=bottom;'
LABEL_RIGHT = 'align=left;verticalAlign=middle;spacingLeft=6;'


# ── Model ────────────────────────────────────────────────────────────────────

@dataclass(eq=False)
class Participant:
    name: str
    kind: str


@dataclass(eq=False)
class Message:
    src: str
    dst: str
    label: str
    reply: bool
    line: int


@dataclass(eq=False)
class Branch:
    condition: str
    events: list['Message | Fragment'] = field(default_factory=list)


@dataclass(eq=False)
class Fragment:
    kind: str
    branches: list[Branch]


@dataclass
class SequenceModel:
    title: str
    participants: list[Participant]
    events: list[Message | Fragment]


# ── Parser ───────────────────────────────────────────────────────────────────

_DECLARATION = re.compile(rf'^({"|".join(PARTICIPANT_KINDS)})\s+(.+)$', re.IGNORECASE)
_MESSAGE = re.compile(r'^(.+?)\s*(-->|->)\s*(.+?)\s*(?::\s*(.*))?$')
_FRAGMENT = re.compile(rf'^({"|".join(FRAGMENT_KINDS)})\b\s*(.*)$', re.IGNORECASE)
_ELSE = re.compile(r'^else\b\s*(.*)$', re.IGNORECASE)
_END = re.compile(r'^end\s*$', re.IGNORECASE)


def parse_sequence(title: str, lines: list[tuple[int, str]]) -> tuple[SequenceModel, list[tuple[int, str]]]:
    """Parse numbered text lines; bad lines are reported as (line, reason) and skipped."""
    participants: dict[str, Participant] = {}
    events: list[Message | Fragment] = []
    open_fragments: list[tuple[Fragment, int]] = []
    errors: list[tuple[int, str]] = []

    def current() -> list[Message | Fragment]:
        return open_fragments[-1][0].branches[-1].events if open_fragments else events

    def use(name: str) -> str:
        participants.setdefault(name, Participant(name, 'participant'))
        return name

    for lineno, raw in lines:
        text = raw.strip()
        if not text or text.startswith("'") or text.startswith('//'):
            continue
        lower = text.lower()
        if lower.startswith(('@startuml', '@enduml', 'title ', 'skinparam', 'autonumber', 'scale')):
            continue
        if lower.startswith(('activate ', 'deactivate ', 'activate', 'deactivate')):
            continue
        if lower.startswith(('note left', 'note right', 'note over')):
            continue

        if _END.match(text):
            if open_fragments:
                open_fragments.pop()
            else:
                errors.append((lineno, "'end' tanpa 'alt', 'loop' atau 'opt' yang dibuka"))
        elif m := _ELSE.match(text):
            if open_fragments and open_fragments[-1][0].kind == 'alt':
                open_fragments[-1][0].branches.append(Branch(_condition(m.group(1))))
            else:
                errors.append((lineno, "'else' hanya boleh di dalam 'alt'"))
        elif m := _MESSAGE.match(text):
            src, arrow, dst, label = m.groups()
            current().append(Message(use(src.strip()), use(dst.strip()), (label or '').strip(),
                                     arrow == '-->', lineno))
        elif m := _FRAGMENT.match(text):
            fragment = Fragment(m.group(1).lower(), [Branch(_condition(m.group(2)))])
            current().append(fragment)
            open_fragments.append((fragment, lineno))
        elif m := _DECLARATION.match(text):
            # A participant keeps its place from first use, the declaration only sets its kind
            participants[use(m.group(2).strip())].kind = m.group(1).lower()
        else:
            errors.append((lineno, f'Baris tidak dikenali: "{text}". Contoh pesan: A -> B : label'))

    for fragment, lineno in open_fragments:
        errors.append((lineno, f"'{fragment.kind}' belum ditutup dengan 'end'"))

    return SequenceModel(title, list(participants.values()), events), errors


def _condition(text: str) -> str:
    return text.strip().strip('[]').strip()


# ── Layout ───────────────────────────────────────────────────────────────────

@dataclass
class _Row:
    """A laid-out message."""
    msg: Message
    number: int
    y: int
    lines: list[str]


@dataclass
class _Box:
    """A laid-out fragment."""
    fragment: Fragment
    top: int
    header_h: int                   # tab row, tall enough for the first condition
    conditions: list[list[str]]     # wrapped condition lines per branch
    cond_x: int                     # conditions start right of the leftmost activation bar
    bottom: int = 0
    separators: list[int] = field(default_factory=list)    # y of each `else` line
    left: int = 0
    right: int = 0


@dataclass
class SequenceLayout:
    centres: dict[str, int]
    widths: dict[str, int]      # room each participant's name needs (spacing, frame)
    top: int                    # top of the lifelines
    bottom: int                 # end of the lifelines
    rows: list[_Row]
    boxes: list[_Box]
    bars: dict[str, tuple[int, int]]            # participant → (y from, y to)
    nested_bars: list[tuple[str, int, int]]     # self-call bars
    frame: Rect


def layout_sequence(model: SequenceModel) -> SequenceLayout:
    participants = model.participants
    order = {p.name: i for i, p in enumerate(participants)}
    kinds = {p.name: p.kind for p in participants}
    messages = list(_messages(model.events))
    numbers = {id(m): i for i, m in enumerate(messages, start=1)}

    def label_text(m: Message) -> str:
        return f'{numbers[id(m)]}. {m.label}'.rstrip()

    # ── Horizontal: lifelines far enough apart for the labels between them ──
    widths = {p.name: max(HEADER_MIN_W, _ceil(len(p.name) * CHAR_W + 20, 20)) for p in participants}
    names = [p.name for p in participants]
    gaps = [max(MIN_GAP, (widths[a] + widths[b]) / 2 + 40) for a, b in zip(names, names[1:])]
    for m in messages:
        a, b = order[m.src], order[m.dst]
        text_w = min(len(label_text(m)) * CHAR_W, MAX_LABEL_W)
        if a == b and a < len(gaps):
            gaps[a] = max(gaps[a], BAR_W / 2 + SELF_W + 10 + text_w + 20)
        elif abs(a - b) == 1:
            gaps[min(a, b)] = max(gaps[min(a, b)], text_w + 20 + BAR_W)

    centres = {names[0]: widths[names[0]] // 2} if names else {}
    for i, gap in enumerate(gaps):
        centres[names[i + 1]] = centres[names[i]] + _ceil(gap, 10)

    def wrap(m: Message) -> list[str]:
        a, b = order[m.src], order[m.dst]
        if a != b:
            room = abs(centres[m.dst] - centres[m.src]) - 20 - BAR_W
        elif a < len(names) - 1:
            room = centres[names[a + 1]] - centres[m.src] - (BAR_W / 2 + SELF_W + 10) - 20
        else:
            room = MAX_LABEL_W
        return _wrap(label_text(m), room)

    def leftmost_centre(fragment: Fragment) -> int:
        return min((centres[n] for m in _messages([fragment]) for n in (m.src, m.dst)),
                   default=centres[names[0]])

    def condition_room(x: int) -> float:
        """Width for condition text starting right of the bar at `x`, before the next lifeline."""
        nxt = min((c for c in centres.values() if c > x), default=None)
        return nxt - x - BAR_W - 30 if nxt is not None else MAX_LABEL_W

    # ── Vertical: one row per message, fragments add their headers ─────────
    top = FRAME_TAB_H + 20
    cursor = top + HEADER_H
    rows: list[_Row] = []
    boxes: list[_Box] = []

    def walk(events: list[Message | Fragment]) -> None:
        nonlocal cursor
        for event in events:
            if isinstance(event, Message):
                lines = wrap(event)
                y = cursor + ROW + LINE_H * (len(lines) - 1)
                rows.append(_Row(event, numbers[id(event)], y, lines))
                cursor = y + (SELF_H if event.src == event.dst else 0)
                continue
            left_c = leftmost_centre(event)
            room = condition_room(left_c)
            conditions = [_wrap(f'[{b.condition}]', room) if b.condition else []
                          for b in event.branches]
            box = _Box(event, top=cursor + 20,
                       header_h=max(FRAME_TAB_H, LINE_H * len(conditions[0]) + 10),
                       conditions=conditions, cond_x=left_c + BAR_W // 2 + 10)
            boxes.append(box)
            cursor = box.top + box.header_h
            for i, branch in enumerate(event.branches):
                if i:
                    separator = cursor + 20
                    box.separators.append(separator)
                    cursor = separator + max(LINE_H, LINE_H * len(conditions[i]))
                walk(branch.events)
            box.bottom = cursor + 20
            cursor = box.bottom

    walk(model.events)
    bottom = cursor + 40

    # ── Activation bars: from a participant's first message to its last ────
    involved: dict[str, list[int]] = {}
    nested_bars = []
    for row in rows:
        is_self = row.msg.src == row.msg.dst
        for name in {row.msg.src, row.msg.dst}:
            involved.setdefault(name, []).extend([row.y, row.y + SELF_H] if is_self else [row.y])
        if is_self and kinds[row.msg.src] != 'actor':
            nested_bars.append((row.msg.src, row.y + 10, row.y + SELF_H + 10))
    bars = {name: (min(ys) - 10, max(ys) + 10)
            for name, ys in involved.items() if kinds[name] != 'actor'}

    # ── Fragment widths: the tab sits left of the lifelines inside ──────────
    self_label_right = {
        id(row.msg): centres[row.msg.src] + BAR_W // 2 + SELF_W + 6 + max(len(ln) for ln in row.lines) * CHAR_W
        for row in rows if row.msg.src == row.msg.dst
    }
    for box in boxes:
        inside = list(_messages([box.fragment]))
        xs = [centres[n] for m in inside for n in (m.src, m.dst)] or [centres[names[0]]]
        nesting = 10 * _nesting(box.fragment)
        right = max([max(xs) + FRAGMENT_PAD + nesting]
                    + [self_label_right[id(m)] + 10 for m in inside if m.src == m.dst]
                    + [box.cond_x + len(ln) * CHAR_W + 10 for lines in box.conditions for ln in lines])
        box.left = _floor(min(xs) - _tab_width(box.fragment.kind) - 10 - nesting, 10)
        box.right = _ceil(right, 10)

    # ── Frame around everything ─────────────────────────────────────────────
    lefts = [centres[n] - widths[n] // 2 for n in names] + [b.left for b in boxes]
    rights = ([centres[n] + widths[n] // 2 for n in names] + [b.right for b in boxes]
              + [_ceil(x, 10) for x in self_label_right.values()])
    frame_left = min(lefts) - FRAME_PAD
    frame = (frame_left, 0, max(rights) + FRAME_PAD - frame_left, bottom + FRAME_PAD)

    return SequenceLayout(centres, widths, top, bottom, rows, boxes, bars, nested_bars, frame)


def _messages(events: list[Message | Fragment]):
    for event in events:
        if isinstance(event, Message):
            yield event
        else:
            for branch in event.branches:
                yield from _messages(branch.events)


def _nesting(fragment: Fragment) -> int:
    """How many fragment levels sit inside this one."""
    inner = [_nesting(e) + 1 for b in fragment.branches for e in b.events if isinstance(e, Fragment)]
    return max(inner, default=0)


def _wrap(text: str, room: float) -> list[str]:
    """Break `text` into lines that fit `room` px."""
    return textwrap.wrap(text, max(10, int(room // CHAR_W))) or ['']


def _tab_width(text: str) -> int:
    return _ceil(len(text) * CHAR_W + 30, 10)


def _ceil(v: float, step: int) -> int:
    return int(math.ceil(v / step)) * step


def _floor(v: float, step: int) -> int:
    return int(math.floor(v / step)) * step


# ── Renderer ─────────────────────────────────────────────────────────────────

def render_sequence(model: SequenceModel, lay: SequenceLayout) -> ET.Element:
    page = PageBuilder()
    title = f'sd {model.title}'
    page.vertex(title, FRAME_STYLE.format(w=max(160, _tab_width(title))), lay.frame)

    for box in lay.boxes:
        kind = box.fragment.kind
        width = box.right - box.left
        page.vertex(kind, FRAGMENT_STYLE.format(w=_tab_width(kind)),
                    (box.left, box.top, width, box.bottom - box.top))
        text_w = box.right - box.cond_x - 10
        if box.conditions[0]:
            page.vertex(_html_lines(box.conditions[0]), CONDITION_STYLE,
                        (box.cond_x, box.top, text_w, box.header_h))
        for y, lines in zip(box.separators, box.conditions[1:]):
            page.vertex('', SEPARATOR_STYLE, (box.left, y - 10, width, 20))
            if lines:
                page.vertex(_html_lines(lines), CONDITION_STYLE, (box.cond_x, y, text_w, LINE_H * len(lines)))

    # Lifelines, with their activation bars as children so they move together
    lifeline_id: dict[str, str] = {}
    bar_cells: dict[str, tuple[str, Rect]] = {}           # absolute rects
    for p in model.participants:
        c = lay.centres[p.name]
        w = ACTOR_W if p.kind == 'actor' else lay.widths[p.name]
        rect = (c - w // 2, lay.top, w, lay.bottom - lay.top)
        style = ACTOR_STYLE if p.kind == 'actor' else LIFELINE_STYLE
        lifeline_id[p.name] = page.vertex(html.escape(p.name), style, rect)
        if p.name in lay.bars:
            y1, y2 = lay.bars[p.name]
            bar_cells[p.name] = (_bar(page, lifeline_id[p.name], lay.top, w // 2 - BAR_W // 2, y1, y2),
                                 (c - BAR_W // 2, y1, BAR_W, y2 - y1))
    nested_cells: dict[int, tuple[str, Rect]] = {}       # self-call row y → nested bar
    for name, y1, y2 in lay.nested_bars:          # never on actors, so the width is the header width
        c, w = lay.centres[name], lay.widths[name]
        cid = _bar(page, lifeline_id[name], lay.top, w // 2, y1, y2)
        nested_cells[y1 - 10] = (cid, (c, y1, BAR_W, y2 - y1))

    def terminal(name: str, y: int, side: int) -> tuple[str, tuple[float, float, float, float]]:
        """Cell and port for a message end at height `y`, on the left (0) or right (1) edge."""
        if name in bar_cells:
            cid, (_, by, _, _) = bar_cells[name]
            return cid, (side, 0, 0, y - by)
        return lifeline_id[name], (0.5, 0, 0, y - lay.top)

    for row in lay.rows:
        m = row.msg
        label = _html_lines(row.lines)
        base = REPLY_STYLE if m.reply else MESSAGE_STYLE
        c = lay.centres[m.src]
        if m.src == m.dst:
            source, exit_port = terminal(m.src, row.y, 1)
            if row.y in nested_cells:
                target, (_, ny, _, _) = nested_cells[row.y]
                entry_port = (1, 0, 0, row.y + SELF_H - ny)
            else:
                target, entry_port = terminal(m.src, row.y + SELF_H, 1)
            loop_x = c + BAR_W // 2 + SELF_W
            page.edge(source, target, base + LABEL_RIGHT + port_style(exit_port, entry_port),
                      points=[(loop_x, row.y), (loop_x, row.y + SELF_H)], value=label)
        else:
            rightward = lay.centres[m.dst] > c
            source, exit_port = terminal(m.src, row.y, 1 if rightward else 0)
            target, entry_port = terminal(m.dst, row.y, 0 if rightward else 1)
            page.edge(source, target, base + LABEL_ABOVE + port_style(exit_port, entry_port),
                      value=label)

    return page.to_model()


def _html_lines(lines: list[str]) -> str:
    return '<br>'.join(html.escape(line) for line in lines)


def _bar(page: PageBuilder, lifeline: str, lifeline_top: int, x: int, y1: int, y2: int) -> str:
    """Activation bar inside a lifeline (`x` relative to the lifeline, `y1`/`y2` absolute)."""
    return page.vertex('', ACTIVATION_STYLE, (x, y1 - lifeline_top, BAR_W, y2 - y1), parent=lifeline)


# ── Page entry point ─────────────────────────────────────────────────────────

def build_sequence_page(title: str, lines: list[tuple[int, str]]) -> tuple[ET.Element | None, list[tuple[int, str]]]:
    model, errors = parse_sequence(title, lines)
    if not any(True for _ in _messages(model.events)):
        first_line = lines[0][0] if lines else 0
        return None, errors + [(first_line, f'Halaman "{title}" belum berisi pesan (contoh: A -> B : label)')]
    return render_sequence(model, layout_sequence(model)), errors
