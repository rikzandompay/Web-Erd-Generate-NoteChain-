"""
Rule-based UML text fixer.

Given the diagram type, the original text, and the list of errors from the
parser, apply heuristic fixes to each broken line:

  • Sequence: missing arrow (-> / -->), wrong participant keyword, missing colon
  • Activity: missing colon-semicolon wrapper, wrong block keywords, unclosed actions
  • Class:    missing braces, wrong relation operator

The fixer never invents content.  It reshapes the line so the parser accepts it.
When it cannot fix a line, it leaves the original and says why.
"""

import re
from typing import Any


# Sequence fixes

_SEQ_ARROW = re.compile(r'^(.+?)\s*(--?>|-+>|→|──>|==>)\s*(.+?)$')
_SEQ_PARTICIPANT_TYPOS = {
    'actir': 'actor', 'actr': 'actor', 'aktor': 'actor',
    'boundry': 'boundary', 'boudary': 'boundary', 'boundari': 'boundary',
    'controll': 'control', 'controler': 'control', 'kontroler': 'control',
    'entiti': 'entity', 'entitas': 'entity',
    'partisipan': 'participant', 'partisipant': 'participant',
    'databse': 'database', 'dtabase': 'database',
}
_SEQ_KINDS = ('actor', 'boundary', 'control', 'entity', 'participant', 'database')

_ACT_BLOCK_TYPOS = {
    'star': 'start', 'stat': 'start', 'mulai': 'start',
    'stp': 'stop', 'stap': 'stop', 'selesai': 'stop', 'akhir': 'stop',
    'endiff': 'endif', 'end if': 'endif',
    'endfork': 'end fork', 'end_fork': 'end fork',
    'forkagain': 'fork again', 'fork_again': 'fork again',
}

_CLASS_RELATION_TYPOS = {
    '->': '-->',
    '<-': '<--',
    '-': '--',
}


def fix_text(kind: str, text: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Fix the text based on errors. Returns {fixed_text, changes, unfixed}."""
    if not errors:
        return {'fixed_text': text, 'changes': [], 'unfixed': []}

    lines = text.split('\n')
    error_map: dict[int, list[dict]] = {}
    for e in errors:
        error_map.setdefault(e['line'], []).append(e)

    changes: list[dict] = []
    unfixed: list[dict] = []

    for abs_line, errs in sorted(error_map.items()):
        idx = abs_line - 1
        if idx < 0 or idx >= len(lines):
            for e in errs:
                unfixed.append({'line': abs_line, 'message': e['message'], 'reason': 'Nomor baris di luar jangkauan.'})
            continue

        original = lines[idx]
        stripped = original.strip()

        if not stripped or stripped.startswith("'") or stripped.startswith('==='):
            for e in errs:
                unfixed.append({'line': abs_line, 'message': e['message'], 'reason': 'Baris kosong atau komentar.'})
            continue

        fixed = None
        reason = ''

        for e in errs:
            msg = e['message']

            if 'Baris tidak dikenali' in msg:
                fixed, reason = _fix_unrecognised(kind, stripped)
            elif 'belum ditutup' in msg:
                fixed, reason = _fix_unclosed(kind, stripped, msg)
            elif 'tidak ditemukan' in msg:
                unfixed.append({'line': abs_line, 'message': msg,
                                'reason': 'Nama aksi tujuan perlu disamakan manual dengan aksi yang ada.'})
                continue
            elif "'end' tanpa" in msg or "'else' tanpa" in msg or "'endif' tanpa" in msg:
                unfixed.append({'line': abs_line, 'message': msg,
                                'reason': 'Blok pembuka yang hilang perlu ditambahkan manual.'})
                continue

            if fixed is not None:
                break

        if fixed is not None and fixed != stripped:
            leading = original[:len(original) - len(original.lstrip())]
            lines[idx] = (leading + fixed) if fixed else ''
            changes.append({
                'line': abs_line,
                'before': original.rstrip(),
                'after': lines[idx].rstrip() if fixed else '(dihapus)',
                'reason': reason,
            })
        elif fixed is None:
            unfixed.append({'line': abs_line, 'message': errs[0]['message'],
                            'reason': 'Tidak bisa diperbaiki otomatis. Periksa sintaks secara manual.'})

    return {
        'fixed_text': '\n'.join(lines),
        'changes': changes,
        'unfixed': unfixed,
    }


def _fix_unrecognised(kind: str, text: str) -> tuple[str | None, str]:
    if kind == 'sequence':
        return _fix_seq_line(text)
    elif kind == 'activity':
        return _fix_act_line(text)
    elif kind == 'class':
        return _fix_class_line(text)
    return None, ''


def _fix_unclosed(kind: str, text: str, msg: str) -> tuple[str | None, str]:
    if "belum ditutup dengan ';'" in msg:
        if not text.endswith(';'):
            return text + ';', "Menambahkan ';' di akhir aksi."
    if "belum ditutup dengan '}'" in msg:
        return None, ''
    if "belum ditutup dengan 'end'" in msg or "belum ditutup dengan 'endif'" in msg or "belum ditutup dengan 'end fork'" in msg:
        return None, ''
    return None, ''


def _fix_seq_line(text: str) -> tuple[str | None, str]:
    lower = text.lower().strip()

    # PlantUML-style @startuml / @enduml tags
    if lower.startswith(('@startuml', '@enduml')):
        return '', 'Menghapus tag PlantUML yang tidak dibutuhkan.'

    # title directive
    if lower.startswith('title '):
        return '', 'Menghapus direktif "title" yang tidak didukung. Gunakan === untuk nama halaman.'

    # PlantUML directives not needed in this tool
    if lower.startswith(('activate ', 'deactivate ', 'activate', 'deactivate')):
        return '', 'Menghapus direktif activate/deactivate (garis hidup sudah otomatis).'

    if lower.startswith(('skinparam', 'autonumber', 'scale', 'note left', 'note right', 'note over')):
        return '', 'Menghapus direktif styling/catatan PlantUML yang tidak didukung.'

    # typo in participant keyword
    for typo, correct in _SEQ_PARTICIPANT_TYPOS.items():
        if lower.startswith(typo + ' '):
            rest = text[len(typo):].strip()
            return f'{correct} {rest}', f'Memperbaiki kata kunci peserta: "{typo}" menjadi "{correct}".'

    # missing colon separator in message
    m = _SEQ_ARROW.match(text)
    if m:
        src, arrow, rest = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        norm_arrow = '-->' if '-' in arrow and '-' in arrow[1:] else '->'
        if ':' not in rest:
            return f'{src} {norm_arrow} {rest} : ', f'Menambahkan pemisah ":" setelah tujuan.'
        return f'{src} {norm_arrow} {rest}', f'Memperbaiki format panah menjadi "{norm_arrow}".'

    # looks like a participant declaration with wrong keyword
    words = text.split()
    if len(words) == 2 and words[0].lower() not in _SEQ_KINDS:
        best = _closest_keyword(words[0].lower(), list(_SEQ_KINDS))
        if best:
            return f'{best} {words[1]}', f'Memperbaiki "{words[0]}" menjadi "{best}".'

    # looks like a message without proper arrows: "A B : pesan" -> "A -> B : pesan"
    colon_pos = text.find(':')
    if colon_pos > 0:
        before = text[:colon_pos].strip()
        after = text[colon_pos + 1:].strip()
        parts = before.split()
        if len(parts) == 2:
            return f'{parts[0]} -> {parts[1]} : {after}', 'Menambahkan panah "->" antara pengirim dan penerima.'

    return None, ''


def _fix_act_line(text: str) -> tuple[str | None, str]:
    lower = text.lower().strip()

    # PlantUML-style @startuml / @enduml
    if lower.startswith(('@startuml', '@enduml')):
        return '', 'Menghapus tag PlantUML yang tidak dibutuhkan.'

    if lower.startswith('title '):
        return '', 'Menghapus direktif "title" yang tidak didukung.'

    if lower.startswith(('skinparam', 'scale', 'footer', 'header', 'note left', 'note right', 'note over')):
        return '', 'Menghapus direktif styling/catatan PlantUML yang tidak didukung.'

    # typo in block keywords
    for typo, correct in _ACT_BLOCK_TYPOS.items():
        if lower == typo:
            return correct, f'Memperbaiki "{text}" menjadi "{correct}".'

    # missing colon-semicolon wrapper for action text
    if not text.startswith(':') and not text.startswith('|') and not text.startswith('-'):
        if lower not in ('start', 'stop', 'end', 'fork', 'fork again', 'end fork', 'end merge') \
                and not lower.startswith('if ') and not lower.startswith('if(') \
                and not lower.startswith('else') and not lower.startswith('endif') \
                and not lower.startswith('end if'):
            action = text.rstrip(';')
            return f':{action};', f'Membungkus teks dengan ":...;" agar dikenali sebagai aksi.'

    # action that starts with : but missing semicolon
    if text.startswith(':') and not text.endswith(';'):
        return text + ';', "Menambahkan ';' di akhir aksi."

    # action that ends with ; but missing colon
    if text.endswith(';') and not text.startswith(':'):
        return ':' + text, "Menambahkan ':' di awal aksi."

    # swimlane missing pipes: AdminSistem -> |Admin| or |Sistem|
    if lower.startswith('|') and not lower.endswith('|'):
        return text + '|', 'Menambahkan "|" penutup pada nama swimlane.'
    if lower.endswith('|') and not lower.startswith('|'):
        return '|' + text, 'Menambahkan "|" pembuka pada nama swimlane.'

    return None, ''


def _fix_class_line(text: str) -> tuple[str | None, str]:
    lower = text.lower().strip()

    # PlantUML tags
    if lower.startswith(('@startuml', '@enduml')):
        return '', 'Menghapus tag PlantUML yang tidak dibutuhkan.'

    if lower.startswith('title '):
        return '', 'Menghapus direktif "title" yang tidak didukung.'

    if lower.startswith(('skinparam', 'scale', 'package ', 'end package', 'namespace ', 'end namespace')):
        return '', 'Menghapus direktif styling/pembungkus yang tidak didukung.'

    # single-dash relation: A - B -> A -- B
    parts = re.split(r'\s+', text.strip())
    if len(parts) >= 3:
        for i, p in enumerate(parts):
            if p in ('-', '<-', '->'):
                fix = _CLASS_RELATION_TYPOS.get(p)
                if fix:
                    parts[i] = fix
                    result = ' '.join(parts)
                    return result, f'Memperbaiki operator relasi "{p}" menjadi "{fix}".'

    return None, ''


def _closest_keyword(word: str, keywords: list[str]) -> str | None:
    """Levenshtein distance <= 3."""
    best, best_d = None, 4
    for kw in keywords:
        d = _levenshtein(word, kw)
        if d < best_d:
            best, best_d = kw, d
    return best


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]
