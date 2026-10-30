# backend/prd_diagrams.py
"""
Every diagram of a PRD in one .drawio file:

    ERD, Class Diagram, Kamus Data   from the plan's SQL (no AI)
    Use Case                         from the plan's use case text (no AI)
    Sequence and Activity            one page per MVP feature, written by the AI

The sequence and activity texts are asked for at the same time, each with the
same system instruction as the chat and one repair round when the parser
finds a broken line. Whatever still fails is listed per page, never hidden.
"""

import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from chat import ChatError, check_rate_limit, clean_reply  # type: ignore
from generator import generate_drawio_xml  # type: ignore
from prd import _earlier, ask_model, clean_input, model_prefix, normalize_idea, normalize_plan, slug  # type: ignore
from sql_parser import parse_sql  # type: ignore
from system_instruction import build_system_instruction  # type: ignore
from uml import drawio_url, generate_uml  # type: ignore

MAX_FEATURES = 5
KIND_LABEL = {'usecase': 'Use Case', 'sequence': 'Sequence', 'activity': 'Activity'}


def mvp_features(idea: dict[str, Any]) -> list[dict[str, Any]]:
    """The phase 1 features (the MVP); the first ones when no feature is marked phase 1."""
    features = idea.get('features') or []
    first = [f for f in features if f.get('phase') == 1] or features[:3]
    return first[:MAX_FEATURES]


def _request(kind: str, idea: dict[str, Any], plan: dict[str, Any], features: list[dict[str, Any]]) -> str:
    """What the model is asked for one diagram type, with the PRD as context."""
    actors = [line.strip() for line in plan.get('usecase_text', '').splitlines() if line.strip().startswith('actor ')]
    lines = [
        f'Buat {kind} diagram untuk SETIAP fitur di bawah, satu blok "=== Nama Fitur" per fitur, '
        f'dengan nama halaman sama persis dengan nama fiturnya. Jangan membuat diagram untuk hal lain.',
        '',
        'FITUR:',
        *[f"- {f['name']}: {', '.join(f.get('sub_features') or [])}" for f in features],
        '',
        f"KONTEKS PRD (produk {idea.get('product_name') or 'ini'}):",
        f"Masalah: {idea.get('problem_statement', '')}",
        f"Aktor: {'; '.join(actors) or ', '.join(idea.get('target_users') or [])}",
        'Tabel database: ' + ', '.join(e['name'] for e in plan.get('entities') or []),
        'Endpoint API: ' + '; '.join(f"{a['method']} {a['path']}" for a in plan.get('api') or []),
    ]
    if kind == 'sequence':
        lines.append('Pakai aktor dari use case sebagai actor, halaman atau aplikasi sebagai boundary, '
                     'controller atau endpoint sebagai control, dan tabel database sebagai entity.')
    else:
        lines.append('Pakai aktor dari use case dan Sistem sebagai swimlane.')
    return '\n'.join(lines)


def _write(kind: str, idea: dict[str, Any], plan: dict[str, Any], features: list[dict[str, Any]], prefix: str,
           skill: str = '') -> dict[str, Any]:
    """One diagram type from the model, checked by the parser, with one repair round."""
    conversation = [{'role': 'system', 'content': build_system_instruction(kind)},
                    {'role': 'user', 'content': _request(kind, idea, plan, features)}]
    text = clean_reply(ask_model(conversation, prefix, skill))
    result = generate_uml(kind, text)
    if result['errors'] or not result['pages']:
        problems = '\n'.join(f"Baris {e['line']}: {e['message']}" for e in result['errors'][:8]) or 'Tidak ada halaman yang terbaca.'
        retry = [*conversation, {'role': 'assistant', 'content': text}, {
            'role': 'user',
            'content': f'Teks tadi punya kesalahan:\n{problems}\nKembalikan teks LENGKAP yang sudah diperbaiki, tetap tanpa penjelasan.'}]
        fixed = clean_reply(ask_model(retry, prefix, skill))
        fixed_result = generate_uml(kind, fixed)
        if (fixed_result['pages'] and len(fixed_result['errors']) <= len(result['errors'])) or not result['pages']:
            text, result = fixed, fixed_result
    return {'text': text, 'result': result}


def merge_drawio(parts: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """
    One .drawio from several: (label prefix, xml). Every page keeps its content,
    gets a fresh page id and, when a prefix is given, a name like "Sequence: Login".
    """
    mxfile = ET.Element('mxfile', host='ERD Generator')
    names: list[str] = []
    for prefix, xml in parts:
        for diagram in ET.fromstring(xml).findall('diagram'):
            name = diagram.get('name') or 'Halaman'
            name = f'{prefix}: {name}' if prefix else name
            while name in names:
                name += ' (2)'
            names.append(name)
            diagram.set('id', f'page-{len(names)}')
            diagram.set('name', name)
            mxfile.append(diagram)
    return ET.tostring(mxfile, encoding='unicode'), names


def build_diagram_bundle(raw_input: dict[str, Any], idea: dict[str, Any], plan: dict[str, Any],
                         visitor: str) -> dict[str, Any]:
    skill = clean_input(raw_input)['constraints']['skill']
    idea = _earlier(normalize_idea, 'idea', idea, '1 (Ide)')
    plan = _earlier(normalize_plan, 'plan', plan, '2 (Rencana)')
    features = mvp_features(idea)
    if not features:
        raise ChatError('Struktur fitur masih kosong; buat ulang tahap Ide.')
    check_rate_limit(visitor)

    parts: list[tuple[str, str]] = []
    errors: list[dict[str, Any]] = []
    try:
        parts.append(('', generate_drawio_xml(parse_sql(plan['ddl']))))
    except ValueError as exc:
        errors.append({'line': 0, 'page': 'ERD', 'message': str(exc)})

    usecase = generate_uml('usecase', plan['usecase_text'])
    if usecase['xml']:
        single = len(usecase['pages']) == 1
        xml = usecase['xml']
        if single:                                       # one use case page is just "Use Case"
            root = ET.fromstring(xml)
            root.find('diagram').set('name', 'Use Case')
            xml = ET.tostring(root, encoding='unicode')
        parts.append(('' if single else 'Use Case', xml))
    errors += [dict(e, page=f"Use Case: {e['page']}") for e in usecase['errors']]

    prefix = model_prefix()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {kind: pool.submit(_write, kind, idea, plan, features, prefix, skill) for kind in ('sequence', 'activity')}
        written = {}
        for kind, job in jobs.items():
            try:
                written[kind] = job.result()
            except ChatError as exc:
                errors.append({'line': 0, 'page': KIND_LABEL[kind], 'message': str(exc)})
    for kind in ('sequence', 'activity'):
        if kind in written and written[kind]['result']['xml']:
            parts.append((KIND_LABEL[kind], written[kind]['result']['xml']))
        if kind in written:
            errors += [dict(e, page=f"{KIND_LABEL[kind]}: {e['page']}") for e in written[kind]['result']['errors']]

    if not parts:
        raise ChatError('Belum ada diagram yang bisa dibuat dari PRD ini.', 502)
    xml, pages = merge_drawio(parts)
    return {
        'xml': xml,
        'pages': pages,
        'errors': errors,
        'texts': {kind: written[kind]['text'] for kind in written},
        'features': [f['name'] for f in features],
        'file_name': f"{slug(idea.get('product_name', ''))}_paket-diagram.drawio",
        'open_url': drawio_url(xml),
    }
