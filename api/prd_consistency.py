# backend/prd_consistency.py
"""
Does the plan (and the tasks) agree with the idea? Every check here is exact,
not a guess from similar words: the model states its own mapping in the plan
(use case → feature, sub-feature → tables + endpoint) and the code checks that
mapping against the use case text, the SQL and the API.

  • every use case actor is one of the target users, and every target user is an actor
  • every use case belongs to an MVP (phase 1) feature, and every MVP feature has a use case
  • every MVP sub-feature names the tables and the endpoint that make it work, and those exist
  • every endpoint is built by some task
"""

import re
from typing import Any

from sql_parser import parse_sql  # type: ignore
from usecase import parse_usecase  # type: ignore


def _key(text: str) -> str:
    """'Admin  HRD ' and 'admin hrd' are the same name."""
    return ' '.join(str(text).lower().split())


def endpoint_key(text: str) -> str:
    """'GET /api/donasi/{id}' and 'get /api/donasi/:id/' compare equal."""
    text = re.sub(r'\{[^}]*\}|:\w+|<[^>]*>', '*', str(text).strip())
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0].isalpha():
        return f'{parts[0].upper()} {parts[1].rstrip("/").lower()}'
    return text.rstrip('/').lower()


def _endpoint_pattern(path: str, method: str = '') -> re.Pattern:
    """Finds a path in free text, with any value in place of a parameter; with `method`, only right after it."""
    pieces = [r'[^\s/`]+' if p == '*' else re.escape(p) for p in endpoint_key(path).split('/')]
    prefix = rf'\b{re.escape(method)}\s+' if method else ''
    return re.compile(prefix + '/'.join(pieces) + r'(?![\w/-])', re.IGNORECASE)


def mvp_features(idea: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in idea.get('features') or [] if f.get('phase') == 1]


def plan_consistency(idea: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """What in the plan does not agree with the idea, in words a person can act on."""
    problems: list[str] = []
    lines = [(n, line) for n, line in enumerate(plan.get('usecase_text', '').splitlines(), start=1)]
    model, _ = parse_usecase('', lines)

    # Actors ↔ target users
    targets = {_key(t): t for t in idea.get('target_users') or []}
    actors = {_key(a): a for a in model.actors}
    for key, actor in actors.items():
        if key not in targets:
            problems.append(f'Aktor "{actor}" tidak ada di target pengguna ({", ".join(targets.values())}).')
    for key, target in targets.items():
        if key not in actors:
            problems.append(f'Target pengguna "{target}" belum menjadi aktor di use case.')

    # Use cases ↔ MVP features
    features = {_key(f['name']): f for f in mvp_features(idea)}
    mapped = {_key(m['usecase']): m['feature'] for m in plan.get('usecase_features') or []}
    for uc in model.usecases:
        feature = mapped.get(_key(uc))
        if feature is None:
            problems.append(f'Use case "{uc}" belum dikaitkan ke fitur di usecase_features.')
        elif _key(feature) not in features:
            problems.append(f'Use case "{uc}" dikaitkan ke "{feature}", yang bukan fitur Fase 1.')
    covered = {_key(f) for u, f in mapped.items() if u in {_key(x) for x in model.usecases}}
    for key, feature in features.items():
        if key not in covered:
            problems.append(f'Fitur Fase 1 "{feature["name"]}" belum punya use case.')

    # MVP sub-features ↔ tables and endpoints
    try:
        tables = {t['name'].lower() for t in parse_sql(plan.get('ddl', ''))['tables']}
    except ValueError:
        tables = set()                           # already reported by the SQL check
    endpoints = {endpoint_key(f"{a['method']} {a['path']}") for a in plan.get('api') or []}
    coverage = {_key(c['sub_feature']): c for c in plan.get('coverage') or []}
    for feature in features.values():
        for sub in feature.get('sub_features') or []:
            item = coverage.get(_key(sub))
            if item is None:
                problems.append(f'Sub-fitur "{sub}" ({feature["name"]}) belum dipetakan ke tabel dan endpoint di coverage.')
                continue
            for table in item.get('tables') or []:
                if tables and table.lower() not in tables:
                    problems.append(f'Sub-fitur "{sub}" memakai tabel "{table}" yang tidak ada di skema SQL.')
            if item.get('endpoint') and endpoint_key(item['endpoint']) not in endpoints:
                problems.append(f'Sub-fitur "{sub}" memakai endpoint "{item["endpoint"]}" yang tidak ada di API.')
    return problems


def tasks_consistency(plan: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    """Every endpoint of the plan is built by some task. A path shared by several methods must be named with its method."""
    text = '\n'.join(' '.join([t.get('title', ''), t.get('description', ''), *t.get('acceptance', []), *t.get('files', [])])
                     for t in tasks)
    api = [a for a in plan.get('api') or [] if a.get('path')]
    methods: dict[str, int] = {}
    for a in api:
        methods[endpoint_key(a['path'])] = methods.get(endpoint_key(a['path']), 0) + 1
    return [f'Endpoint "{a["method"]} {a["path"]}" belum dikerjakan di task mana pun.'
            for a in api
            if not _endpoint_pattern(a['path'], a['method'] if methods[endpoint_key(a['path'])] > 1 else '').search(text)]


def traceability(idea: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows of feature → sub-feature → use case → tables → endpoint, for the document."""
    usecases: dict[str, list[str]] = {}
    for m in plan.get('usecase_features') or []:
        usecases.setdefault(_key(m['feature']), []).append(m['usecase'])
    coverage = {_key(c['sub_feature']): c for c in plan.get('coverage') or []}
    rows = []
    for feature in mvp_features(idea):
        for sub in feature.get('sub_features') or [None]:
            item = coverage.get(_key(sub or '')) or {}
            rows.append({'feature': feature['name'], 'sub_feature': sub or '',
                         'usecases': usecases.get(_key(feature['name']), []),
                         'tables': item.get('tables') or [], 'endpoint': item.get('endpoint') or ''})
    return rows
