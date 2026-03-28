# backend/generator.py
"""
Chen Notation ERD Generator — converts parsed SQL schema into Draw.io-compatible XML.

Chen Notation rules:
  • Entity    → Rectangle  (fillColor=#dae8fc)
  • Attribute → Ellipse    (fillColor=#fff2cc, PK text is underlined fontStyle=4)
  • Relation  → Diamond    (fillColor=#f8cecc, one per FK relationship)
  • Edges     → Plain lines with no arrowheads
"""

import itertools
import math
import xml.etree.ElementTree as ET
from typing import Any

# ── Layout constants ─────────────────────────────────────────────────────────
ENTITY_W = 160          # entity rectangle width
ENTITY_H = 60           # entity rectangle height
ATTR_W = 120            # attribute ellipse width
ATTR_H = 40             # attribute ellipse height
DIAMOND_W = 120         # relationship diamond width
DIAMOND_H = 60          # relationship diamond height

ENTITY_COLS = 3         # max entities per row before wrapping
COL_GAP = 380           # horizontal distance between entity centres
ROW_GAP = 320           # vertical   distance between entity centres
ATTR_RADIUS = 150       # distance from entity centre to attribute centre


def generate_drawio_xml(schema: dict[str, Any]) -> str:
    """Generate a Draw.io-compatible Chen Notation ERD XML string from parsed schema."""

    tables: list[dict[str, Any]] = schema.get('tables', [])
    relations: list[dict[str, Any]] = schema.get('relations', [])

    # ── Assign grid positions to entities (store as centre x, y) ────────────
    entity_pos: dict[str, tuple[float, float]] = {}
    for idx, table in enumerate(tables):
        col = idx % ENTITY_COLS
        row = idx // ENTITY_COLS
        cx = 200.0 + col * COL_GAP
        cy = 200.0 + row * ROW_GAP
        entity_pos[table['name']] = (cx, cy)

    # ── Build XML tree ───────────────────────────────────────────────────────
    mx_model = ET.Element('mxGraphModel', dx='1422', dy='762', grid='1',
                          gridSize='10', guides='1', tooltips='1', connect='1',
                          arrows='1', fold='1', page='0', pageScale='1',
                          pageWidth='1169', pageHeight='827', math='0', shadow='0')
    root_el = ET.SubElement(mx_model, 'root')

    ET.SubElement(root_el, 'mxCell', id='0')
    ET.SubElement(root_el, 'mxCell', id='1').set('parent', '0')

    cell_id_gen = itertools.count(2)

    def _next_id() -> str:
        return str(next(cell_id_gen))

    # ── Helper to make a plain line edge ────────────────────────────────────
    def add_edge(src: str, tgt: str, label: str = '',
                 label_pos: float | None = None) -> None:
        """
        label_pos controls where the label sits along the edge:
          -1 = at source, 0 = centre (default), +1 = at target.
          Use ~ -0.6 for "near source" and ~ +0.6 for "near target".
        """
        font_size = '11' if label in ('1', 'N', 'M') else '9'
        edge = ET.SubElement(root_el, 'mxCell',
            id=_next_id(),
            value=f'<b>{label}</b>' if label in ('1', 'N', 'M') else label,
            style=(
                'edgeStyle=none;html=1;endArrow=none;startArrow=none;'
                f'strokeColor=#555555;fontSize={font_size};'
            ),
            edge='1',
            source=src,
            target=tgt,
        )
        edge.set('parent', '1')
        geo = ET.SubElement(edge, 'mxGeometry', relative='1')
        geo.set('as', 'geometry')
        if label_pos is not None:
            geo.set('x', str(label_pos))

    # ── Track entity cell IDs ────────────────────────────────────────────────
    entity_cell_id: dict[str, str] = {}

    # ── 1. Draw Entities (Rectangles) ────────────────────────────────────────
    for table in tables:
        cx, cy = entity_pos[table['name']]
        eid = _next_id()
        entity_cell_id[table['name']] = eid

        cell = ET.SubElement(root_el, 'mxCell',
            id=eid,
            value=f"<b>{table['name'].upper()}</b>",
            style=(
                'rounded=0;whiteSpace=wrap;html=1;aspect=fixed;'
                'fillColor=#dae8fc;strokeColor=#6c8ebf;'
                'fontStyle=1;fontSize=14;align=center;'
            ),
            vertex='1',
        )
        cell.set('parent', '1')
        ET.SubElement(cell, 'mxGeometry',
            x=str(cx - ENTITY_W / 2), y=str(cy - ENTITY_H / 2),
            width=str(ENTITY_W), height=str(ENTITY_H),
        ).set('as', 'geometry')

    # ── 2. Draw Attributes (Ellipses) around each entity ─────────────────────
    for table in tables:
        cx, cy = entity_pos[table['name']]
        eid = entity_cell_id[table['name']]
        columns: list[dict[str, Any]] = table.get('columns', [])
        num_cols = len(columns)

        for a_idx, col in enumerate(columns):
            # Spread attributes evenly in a circle, starting from the top
            angle = (2 * math.pi * a_idx / num_cols) - (math.pi / 2)
            ax = cx + ATTR_RADIUS * math.cos(angle) - ATTR_W / 2
            ay = cy + ATTR_RADIUS * math.sin(angle) - ATTR_H / 2

            attr_id = _next_id()

            # PK → underline (fontStyle=4); regular → normal (fontStyle=0)
            font_style = '4' if col['is_pk'] else '0'
            # FK column → italic as well (fontStyle=2)
            is_fk = any(
                r['from_table'] == table['name'] and r['from_column'] == col['name']
                for r in relations
            )
            if col['is_pk'] and is_fk:
                font_style = '6'   # bold-underline
            elif is_fk:
                font_style = '2'   # italic

            attr_cell = ET.SubElement(root_el, 'mxCell',
                id=attr_id,
                value=col['name'],
                style=(
                    'ellipse;whiteSpace=wrap;html=1;'
                    'fillColor=#fff2cc;strokeColor=#d6b656;'
                    f'fontStyle={font_style};fontSize=11;align=center;'
                ),
                vertex='1',
            )
            attr_cell.set('parent', '1')
            ET.SubElement(attr_cell, 'mxGeometry',
                x=str(ax), y=str(ay),
                width=str(ATTR_W), height=str(ATTR_H),
            ).set('as', 'geometry')

            # Line: entity ↔ attribute
            add_edge(eid, attr_id)

    # ── 3. Draw Relationship Diamonds for FK relations ────────────────────────
    for rel in relations:
        ft = rel['from_table']
        tt = rel['to_table']
        if ft not in entity_pos or tt not in entity_pos:
            continue

        fx, fy = entity_pos[ft]
        tx, ty = entity_pos[tt]

        # Place diamond at midpoint between the two entities
        dx = (fx + tx) / 2 - DIAMOND_W / 2
        dy = (fy + ty) / 2 - DIAMOND_H / 2

        # Derive a verb label for the relationship diamond
        rel_label = _relation_label(ft, tt)

        diamond_id = _next_id()

        diamond = ET.SubElement(root_el, 'mxCell',
            id=diamond_id,
            value=rel_label,
            style=(
                'rhombus;whiteSpace=wrap;html=1;'
                'fillColor=#f8cecc;strokeColor=#b85450;'
                'fontSize=11;align=center;fontStyle=1;'
            ),
            vertex='1',
        )
        diamond.set('parent', '1')
        ET.SubElement(diamond, 'mxGeometry',
            x=str(dx), y=str(dy),
            width=str(DIAMOND_W), height=str(DIAMOND_H),
        ).set('as', 'geometry')

        # Line: from_entity(N) ↔ diamond ↔ to_entity(1)
        # from_table has the FK → many side (N)
        # to_table is referenced  → one side  (1)
        add_edge(entity_cell_id[ft], diamond_id, label='N', label_pos=-0.6)
        add_edge(diamond_id, entity_cell_id[tt], label='1', label_pos=0.6)

    return ET.tostring(mx_model, encoding='unicode', xml_declaration=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

# Kata kerja mapping: if from_table contains these keywords, use the mapped verb.
# Otherwise fallback to a generic verb based on the relationship direction.
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


def _relation_label(from_table: str, to_table: str) -> str:
    """
    Derive an Indonesian verb (kata kerja) for the relationship diamond
    based on from_table and to_table names.

    Strategy:
      1. Check if from_table name contains a known keyword → use mapped verb.
      2. If from_table is a detail/junction table (nama mengandung 'detail') → 'memiliki'.
      3. Fallback → 'memiliki'.
    """
    ft_lower = from_table.lower()
    tt_lower = to_table.lower()

    # 1. Check from_table for known keywords
    for keyword, verb in _VERB_MAP.items():
        if keyword in ft_lower:
            return verb

    # 2. Check to_table for known keywords
    for keyword, verb in _VERB_MAP.items():
        if keyword in tt_lower:
            return verb

    # 3. Fallback – generic verb
    return 'memiliki'
