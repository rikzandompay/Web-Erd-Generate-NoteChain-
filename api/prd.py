# backend/prd.py
"""
PRD generator in three stages, following the "PRD Pro" workflow:

    0. questions          five clarifying questions about the idea, with answer chips
    1. idea   (struktur)  problem statement, solution, features per phase, MVP scope, non-goals
    2. plan   (rencana)   user journey + use case text, architecture, SQL DDL, API spec, AI tools
    3. tasks  (fitur)     atomic, dependency-ordered tasks for an AI coding agent

Every stage is one call to the same OpenAI-compatible model as the chat, answering
JSON. The answer is checked before it is returned: the DDL must parse with this app's
SQL parser, the use case text must build without line errors, and the tasks must have
unique ids and no missing or circular dependencies. When a check fails the model gets
one repair round; whatever is still wrong is reported, never hidden.

Nothing is stored: the browser sends the whole state with every request.

The model is the chat's (AI_*) unless PRD_AI_MODEL is set: then PRD_AI_BASE_URL,
PRD_AI_API_KEY and PRD_AI_MODEL are used together, so the PRD can run on another
provider (a 9Router proxy, say) without the chat's key ever being sent there.
"""

import json
import os
import re
from typing import Any

from chat import ChatError, call_model, check_rate_limit, clean_reply  # type: ignore
from prd_consistency import plan_consistency, tasks_consistency, traceability  # type: ignore
from prd_instruction import MAX_TASKS, instruction  # type: ignore
from sql_parser import parse_sql  # type: ignore
from uml import generate_uml  # type: ignore
from usecase import parse_usecase  # type: ignore

STACK_FIELDS = ('frontend', 'backend', 'database', 'deployment')
SKILLS = ('pemula', 'menengah', 'pro')
BUDGETS = ('zero cost', 'free tier', 'paid')
LANGUAGES = ('Bahasa Indonesia', 'English')
MAX_IDEA_CHARS = 2000
MAX_ANSWERS = 8
MAX_CONTEXT_CHARS = 8000
MAX_SQL_CHARS = 60000


# ── Input ────────────────────────────────────────────────────────────────────

def _text(value: Any, limit: int) -> str:
    return str(value or '').strip()[:limit]


def clean_answers(raw: Any) -> list[dict[str, str]]:
    """Answers to the clarifying questions; skipped ones are simply left out."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            q, a = _text(item.get('question'), 300), _text(item.get('answer'), 600)
            if q and a:
                out.append({'question': q, 'answer': a})
    return out[:MAX_ANSWERS]


def clean_input(raw: dict[str, Any], need_stack: bool = True) -> dict[str, Any]:
    """The wizard's answers, trimmed and checked. Raises ChatError naming every missing field."""
    raw = raw or {}
    stack, constraints, context = raw.get('stack') or {}, raw.get('constraints') or {}, raw.get('context') or {}
    language = _text(raw.get('language'), 40)
    data = {
        'idea_text': _text(raw.get('idea_text'), MAX_IDEA_CHARS),
        'answers': clean_answers(raw.get('answers')),
        'language': language if language in LANGUAGES else LANGUAGES[0],
        'stack': {f: _text(stack.get(f), 60) for f in STACK_FIELDS},
        'constraints': {'skill': _text(constraints.get('skill'), 20).lower(),
                        'budget': _text(constraints.get('budget'), 20).lower()},
        'context': {'text': _text(context.get('text'), MAX_CONTEXT_CHARS),
                    'sql_text': _text(context.get('sql_text'), MAX_SQL_CHARS)},
    }
    missing = []
    if len(data['idea_text']) < 10:
        missing.append('deskripsi ide (minimal satu kalimat)')
    if need_stack:
        missing += [f'tech stack {f}' for f in STACK_FIELDS if not data['stack'][f]]
        if data['constraints']['skill'] not in SKILLS:
            missing.append('tingkat keahlian')
        if data['constraints']['budget'] not in BUDGETS:
            missing.append('budget infra')
    if missing:
        raise ChatError('Lengkapi dulu: ' + ', '.join(missing) + '.')
    return data


def _schema_summary(sql_text: str) -> str:
    """An uploaded .sql as a short table list, so the model sees the old schema without the whole file."""
    if not sql_text:
        return ''
    try:
        schema = parse_sql(sql_text)
    except ValueError:
        return ''
    refs = {(r['from_table'], r['from_column']): f"{r['to_table']}.{r['to_column']}" for r in schema['relations']}
    lines = []
    for table in schema['tables']:
        cols = []
        for c in table['columns']:
            mark = ' PK' if c.get('is_pk') else ''
            if (table['name'], c['name']) in refs:
                mark += f" FK->{refs[(table['name'], c['name'])]}"
            cols.append(f"{c['name']} {c['type']}{mark}")
        lines.append(f"- {table['name']}: " + ', '.join(cols))
    return '\n'.join(lines)


def _brief(data: dict[str, Any]) -> str:
    """The wizard's answers as one message for the model."""
    s, c, ctx = data['stack'], data['constraints'], data['context']
    parts = ['ISIAN PENGGUNA', f"Ide: {data['idea_text']}", f"Bahasa dokumen: {data['language']}"]
    if data['answers']:
        parts.append('Jawaban pertanyaan klarifikasi:')
        parts += [f"- {a['question']} -> {a['answer']}" for a in data['answers']]
    if all(s.values()):
        parts.append(f"Tech stack: frontend {s['frontend']}, backend {s['backend']}, database {s['database']}, deployment {s['deployment']}")
    if c['skill'] in SKILLS and c['budget'] in BUDGETS:
        parts.append(f"Tingkat keahlian: {c['skill']}. Budget infra: {c['budget']}.")
    if ctx['text']:
        parts.append(f"Konteks eksisting (aturan bisnis, API lama):\n{ctx['text']}")
    if summary := _schema_summary(ctx['sql_text']):
        parts.append(f'Skema database lama (pertahankan dan kembangkan, jangan dibuang):\n{summary}')
    return '\n'.join(parts)


# ── Model answers ────────────────────────────────────────────────────────────

def parse_json(text: str) -> dict[str, Any]:
    """The JSON object in a model reply, with code fences or stray text around it removed."""
    text = clean_reply(text)
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise ValueError('balasan bukan JSON')
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('balasan bukan objek JSON')
    return value


def _strings(value: Any, limit: int = 40) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in (value or []) if str(v).strip()][:limit] if isinstance(value, list) else []


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def normalize_features(raw: Any) -> list[dict[str, Any]]:
    """Features with a phase (1 = MVP … 4) and their sub-features, ordered by phase."""
    out = []
    for f in _dicts(raw)[:12]:
        name = _text(f.get('name'), 80)
        if not name:
            continue
        try:
            phase = min(4, max(1, int(f.get('phase') or 1)))
        except (TypeError, ValueError):
            phase = 1
        out.append({'name': name, 'phase': phase, 'sub_features': _strings(f.get('sub_features'), 8)})
    return sorted(out, key=lambda f: f['phase'])


def normalize_questions(answer: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for q in _dicts(answer.get('questions'))[:6]:
        question = _text(q.get('question'), 300)
        kind = q.get('type') if q.get('type') in ('text', 'single', 'multi') else 'single'
        options = [o[:40] for o in _strings(q.get('options'), 6)] if kind != 'text' else []
        if question and (kind == 'text' or len(options) >= 2):
            out.append({'question': question, 'type': kind, 'options': options})
    if len(out) < 3:
        raise ValueError('minimal 3 pertanyaan dengan pilihan jawaban')
    return out


def normalize_idea(answer: dict[str, Any]) -> dict[str, Any]:
    idea = answer.get('idea') if isinstance(answer.get('idea'), dict) else {}
    out = {
        'product_name': _text(idea.get('product_name'), 80),
        'problem_statement': _text(idea.get('problem_statement'), 1000),
        'solution': _text(idea.get('solution'), 1000),
        'target_users': _strings(idea.get('target_users'), 10),
        'core_value': _text(idea.get('core_value'), 300),
        'mvp_scope': _strings(idea.get('mvp_scope'), 12),
        'non_goals': _strings(idea.get('non_goals'), 10),
        'features': normalize_features(idea.get('features')),
    }
    if not out['mvp_scope']:                         # the first phase is the MVP
        out['mvp_scope'] = [f['name'] for f in out['features'] if f['phase'] == 1]
    if not (out['problem_statement'] and out['solution'] and out['features']):
        raise ValueError('problem_statement, solution, dan features wajib terisi')
    if out['product_name'].lower() == 'erd generator':
        out['product_name'] = ''                     # the tool's own name, not the user's product
    return out


def normalize_plan(answer: dict[str, Any]) -> dict[str, Any]:
    plan = answer.get('plan') if isinstance(answer.get('plan'), dict) else {}
    out = {
        'user_journey': _strings(plan.get('user_journey'), 20),
        'usecase_text': str(plan.get('usecase_text') or '').strip(),
        'architecture': [{'layer': _text(a.get('layer'), 40), 'choice': _text(a.get('choice'), 120),
                          'reason': _text(a.get('reason'), 300)} for a in _dicts(plan.get('architecture'))],
        'ddl': clean_reply(str(plan.get('ddl') or '')),
        'entities': [{'name': _text(e.get('name'), 60), 'purpose': _text(e.get('purpose'), 300)}
                     for e in _dicts(plan.get('entities'))],
        'api': [{'method': _text(a.get('method'), 10).upper() or 'GET', 'path': _text(a.get('path'), 200),
                 'summary': _text(a.get('summary'), 300),
                 'request': a.get('request') if isinstance(a.get('request'), (dict, list)) else {},
                 'response': a.get('response') if isinstance(a.get('response'), (dict, list)) else {},
                 'errors': _strings(a.get('errors'), 10)} for a in _dicts(plan.get('api'))],
        'ai_tools': [{'name': _text(t.get('name'), 60), 'description': _text(t.get('description'), 300),
                      'parameters': t.get('parameters') if isinstance(t.get('parameters'), dict) else {}}
                     for t in _dicts(plan.get('ai_tools'))],
        # The model's own mapping, checked in prd_consistency.py
        'usecase_features': [{'usecase': _text(m.get('usecase'), 120), 'feature': _text(m.get('feature'), 120)}
                             for m in _dicts(plan.get('usecase_features')) if m.get('usecase')],
        'coverage': [{'sub_feature': _text(c.get('sub_feature'), 120), 'tables': _strings(c.get('tables'), 8),
                      'endpoint': _text(c.get('endpoint'), 200)}
                     for c in _dicts(plan.get('coverage')) if c.get('sub_feature')],
    }
    if not out['ddl'] or not out['usecase_text']:
        raise ValueError('ddl dan usecase_text wajib terisi')
    return out


def plan_checks(plan: dict[str, Any]) -> dict[str, list[str]]:
    """What is wrong with the plan's SQL and use case text, in words a person can act on."""
    ddl_errors: list[str] = []
    try:
        schema = parse_sql(plan['ddl'])
        names = {t['name'] for t in schema['tables']}
        for t in schema['tables']:
            if not any(c.get('is_pk') for c in t['columns']):
                ddl_errors.append(f"Tabel {t['name']} belum punya PRIMARY KEY.")
        for r in schema['relations']:
            if r['to_table'] not in names:
                ddl_errors.append(f"Kolom {r['from_table']}.{r['from_column']} merujuk tabel {r['to_table']} yang tidak ada.")
    except ValueError as exc:
        ddl_errors.append(str(exc))
    usecase = generate_uml('usecase', plan['usecase_text'])
    usecase_errors = [f"Baris {e['line']}: {e['message']}" for e in usecase['errors']]
    if not usecase['pages'] and not usecase_errors:
        usecase_errors.append('Teks use case tidak menghasilkan diagram.')
    # The diagram reads left to right: someone gives the input, someone receives the output
    model, _ = parse_usecase('', [(n, line) for n, line in enumerate(plan['usecase_text'].splitlines(), start=1)])
    if model.usecases and 'R' not in model.actors.values():
        usecase_errors.append('Belum ada aktor <<sekunder>> di kanan yang menerima hasil.')
    for actor in model.actors:
        if '"' in actor or re.search(r'\sas\s', actor):
            usecase_errors.append(f'Aktor {actor} memakai alias atau tanda kutip; tulis namanya langsung, misalnya actor Admin Prodi.')
    squash = {a: re.sub(r'[^a-z0-9]', '', a.lower()) for a in model.actors}
    for right in (a for a, side in model.actors.items() if side == 'R'):
        for left in (a for a, side in model.actors.items() if side == 'L'):
            if squash[left] and squash[right] and (squash[left] in squash[right] or squash[right] in squash[left]):
                usecase_errors.append(f'Aktor {left} dan {right} tampaknya pihak yang sama; tulis sekali saja.')
    return {'ddl_errors': ddl_errors, 'usecase_errors': usecase_errors}


def order_tasks(raw: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Tasks cleaned and sorted so every task comes after the ones it depends on; plus what is wrong."""
    tasks, errors, seen = [], [], set()
    for i, t in enumerate(_dicts(raw), start=1):
        tid = _text(t.get('id'), 10) or f'T{i:02d}'
        if tid in seen:
            errors.append(f'ID {tid} dipakai lebih dari sekali.')
            continue
        seen.add(tid)
        tasks.append({'id': tid, 'title': _text(t.get('title'), 200), 'description': _text(t.get('description'), 800),
                      'depends_on': _strings(t.get('depends_on'), 20), 'files': _strings(t.get('files'), 10),
                      'acceptance': _strings(t.get('acceptance'), 6)})
    for t in tasks:
        missing = [d for d in t['depends_on'] if d not in seen]
        if missing:
            errors.append(f"{t['id']} bergantung pada {', '.join(missing)} yang tidak ada.")
            t['depends_on'] = [d for d in t['depends_on'] if d in seen]

    # Kahn's algorithm, keeping the model's order among tasks that are ready together
    position = {t['id']: i for i, t in enumerate(tasks)}
    waiting = {t['id']: set(t['depends_on']) - {t['id']} for t in tasks}
    if any(t['id'] in t['depends_on'] for t in tasks):
        errors.extend(f"{t['id']} bergantung pada dirinya sendiri." for t in tasks if t['id'] in t['depends_on'])
    ordered: list[dict[str, Any]] = []
    done: set[str] = set()
    while len(ordered) < len(tasks):
        ready = [t for t in tasks if t['id'] not in done and waiting[t['id']] <= done]
        if not ready:
            stuck = sorted((t['id'] for t in tasks if t['id'] not in done), key=position.get)
            errors.append('Dependensi melingkar di antara ' + ', '.join(stuck) + '.')
            ordered.extend(t for t in tasks if t['id'] not in done)
            break
        first = min(ready, key=lambda t: position[t['id']])
        ordered.append(first)
        done.add(first['id'])
    return ordered, errors


# ── Stages ───────────────────────────────────────────────────────────────────

def model_prefix() -> str:
    """PRD_AI when the PRD has a model of its own, else the chat's AI settings."""
    return 'PRD_AI' if os.environ.get('PRD_AI_MODEL', '').strip() else 'AI'


def _ask(stage: str, skill: str, content: str, check) -> tuple[Any, list[str], dict[str, Any]]:
    """
    One stage: ask, parse, check. `check(answer)` returns (result, problems).
    With problems the model gets one repair round and the better of the two answers wins.
    """
    conversation = [{'role': 'system', 'content': instruction(stage, skill)}, {'role': 'user', 'content': content}]

    def attempt(reply: str):
        try:
            answer = parse_json(reply)
            result, problems = check(answer)
            return result, problems, answer
        except (ValueError, TypeError) as exc:
            return None, [f'Format balasan tidak sesuai: {exc}.'], {}

    prefix = model_prefix()
    reply = call_model(conversation, prefix)
    result, problems, answer = attempt(reply)
    if problems:
        retry = [*conversation, {'role': 'assistant', 'content': reply}, {
            'role': 'user',
            'content': 'Balasan tadi punya masalah:\n- ' + '\n- '.join(problems[:10]) +
                       '\nKirim ulang objek JSON LENGKAP yang sudah diperbaiki, tetap tanpa penjelasan.'}]
        fixed = attempt(call_model(retry, prefix))
        if fixed[0] is not None and (result is None or len(fixed[1]) <= len(problems)):
            result, problems, answer = fixed
    if result is None:
        raise ChatError('AI belum memberi jawaban yang bisa dibaca: ' + problems[0] + ' Coba lagi.', 502)
    return result, problems, answer


def _assumptions(answer: dict[str, Any]) -> list[str]:
    return _strings(answer.get('assumptions'), 15)


# Used when the model's questions cannot be read, so the wizard never gets stuck
FALLBACK_QUESTIONS = [
    {'question': 'Ceritakan seseorang yang butuh aplikasi ini. Sekarang mereka melakukan apa untuk mengatasi masalahnya?',
     'type': 'text', 'options': []},
    {'question': 'Siapa saja yang akan memakai aplikasi ini?', 'type': 'multi',
     'options': ['Admin', 'Pelanggan', 'Staf', 'Pemilik', 'Publik']},
    {'question': 'Saat pertama membuka aplikasi, satu hal apa yang harus langsung bisa dilakukan?', 'type': 'single',
     'options': ['Daftar atau masuk', 'Input data', 'Lihat informasi', 'Melakukan transaksi']},
    {'question': 'Apa yang membuat aplikasi ini lebih baik daripada cara sekarang?', 'type': 'single',
     'options': ['Lebih cepat', 'Lebih akurat', 'Lebih gampang', 'Gratis']},
    {'question': 'Apa yang membuat pengguna kembali memakai aplikasi ini?', 'type': 'single',
     'options': ['Laporan rutin', 'Notifikasi', 'Riwayat tersimpan', 'Fitur sosial']},
]


def prd_questions(raw_input: dict[str, Any], visitor: str) -> dict[str, Any]:
    """Five questions that make the idea concrete, each with answer chips."""
    data = clean_input(raw_input, need_stack=False)
    check_rate_limit(visitor)

    def check(answer):
        return normalize_questions(answer), []

    try:
        questions, _, _ = _ask('questions', 'menengah', _brief(data), check)
        return {'questions': questions, 'fallback': False}
    except ChatError as exc:
        if exc.status != 502:                        # limit reached or model down: say so
            raise
        return {'questions': FALLBACK_QUESTIONS, 'fallback': True}


def prd_idea(raw_input: dict[str, Any], visitor: str) -> dict[str, Any]:
    data = clean_input(raw_input)
    check_rate_limit(visitor)

    def check(answer):
        return normalize_idea(answer), []

    idea, _, answer = _ask('idea', data['constraints']['skill'], _brief(data), check)
    return {'idea': idea, 'assumptions': _assumptions(answer)}


def _earlier(normalize, key: str, value: Any, stage: str) -> dict[str, Any]:
    """A stage result sent back by the browser (possibly edited), checked again."""
    if not value:
        raise ChatError(f'Selesaikan tahap {stage} dulu.')
    try:
        return normalize({key: value})
    except ValueError as exc:
        raise ChatError(f'Hasil tahap {stage} tidak lengkap: {exc}.')


def prd_plan(raw_input: dict[str, Any], idea: dict[str, Any], visitor: str) -> dict[str, Any]:
    data = clean_input(raw_input)
    idea = _earlier(normalize_idea, 'idea', idea, '1 (Ide)')
    check_rate_limit(visitor)
    content = _brief(data) + '\n\nHASIL TAHAP 1 (IDE)\n' + json.dumps(idea, ensure_ascii=False)

    def all_checks(plan):
        return {**plan_checks(plan), 'consistency': plan_consistency(idea, plan)}

    def check(answer):
        plan = normalize_plan(answer)
        checks = all_checks(plan)
        return plan, [*(f'DDL: {e}' for e in checks['ddl_errors']), *(f'Use case: {e}' for e in checks['usecase_errors']),
                      *(f'Tidak sinkron dengan tahap Ide: {e}' for e in checks['consistency'])]

    plan, _, answer = _ask('plan', data['constraints']['skill'], content, check)
    return {'plan': plan, 'assumptions': _assumptions(answer), 'checks': all_checks(plan)}


def prd_tasks(raw_input: dict[str, Any], idea: dict[str, Any], plan: dict[str, Any], visitor: str) -> dict[str, Any]:
    data = clean_input(raw_input)
    idea = _earlier(normalize_idea, 'idea', idea, '1 (Ide)')
    plan = _earlier(normalize_plan, 'plan', plan, '2 (Rencana)')
    check_rate_limit(visitor)
    skill = data['constraints']['skill']
    limit = MAX_TASKS.get(skill, 30)
    content = (_brief(data) + '\n\nHASIL TAHAP 1 (IDE)\n' + json.dumps(idea, ensure_ascii=False) +
               '\n\nHASIL TAHAP 2 (RENCANA)\n' + json.dumps(plan, ensure_ascii=False))

    def check(answer):
        tasks, problems = order_tasks(answer.get('tasks'))
        if not tasks:
            raise ValueError('daftar tasks kosong')
        if len(tasks) > limit:
            problems.append(f'Ada {len(tasks)} task, batasnya {limit}. Gabungkan task yang terlalu kecil.')
        return tasks, problems + tasks_consistency(plan, tasks)

    tasks, problems, answer = _ask('tasks', skill, content, check)
    return {'tasks': tasks[:limit], 'assumptions': _assumptions(answer), 'problems': problems}


# ── Markdown ─────────────────────────────────────────────────────────────────

def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:60] or 'prd'


def _cell(text: Any) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def _bullets(items: list[str]) -> str:
    items = [str(i).strip() for i in items or [] if str(i).strip()]     # lines left empty while editing
    return '\n'.join(f'- {i}' for i in items) if items else '_Belum diisi._'


def render_prd_markdown(state: dict[str, Any], date: str = '') -> str:
    """The whole PRD as Markdown; a stage that has not been made yet is marked, not left out."""
    state = state or {}
    raw = state.get('input') or {}
    idea, plan, tasks = state.get('idea') or {}, state.get('plan') or {}, state.get('tasks') or []
    stack, cons = raw.get('stack') or {}, raw.get('constraints') or {}
    pending = '_Belum dibuat. Jalankan tahap ini di ERD Generator._'
    name = idea.get('product_name') or 'Produk Baru'
    sections: list[tuple[str, list[str]]] = []

    if idea:
        body = [f"**Masalah.** {idea.get('problem_statement', '')}", '',
                f"**Solusi inti.** {idea.get('solution', '')}", '',
                f"**Target pengguna.** {', '.join(idea.get('target_users') or [])}", '',
                f"**Core value.** {idea.get('core_value', '')}"]
    else:
        body = [pending]
    sections.append(('Ringkasan', body))
    sections.append(('Scope MVP', [_bullets(idea.get('mvp_scope') or []) if idea else pending, '',
                                   '### Non-Goals', '', _bullets(idea.get('non_goals') or []) if idea else pending]))

    features = idea.get('features') or [] if idea else []
    body = []
    for phase in sorted({f['phase'] for f in features}):
        body += [f'### Fase {phase}' + (' (MVP)' if phase == 1 else ''), '']
        for f in (f for f in features if f['phase'] == phase):
            subs = ', '.join(s for s in f.get('sub_features') or [] if str(s).strip())
            body.append(f"- **{f['name']}**" + (f': {subs}' if subs else ''))
        body.append('')
    sections.append(('Struktur Fitur', body[:-1] if body else [pending]))

    if plan:
        steps = [s for s in plan.get('user_journey') or [] if str(s).strip()]
        body = [*(f'{n}. {step}' for n, step in enumerate(steps, start=1)), '',
                'Use case diagram (tempel di tab Teks UML, jenis Use Case):', '', '```text',
                plan.get('usecase_text', ''), '```']
    else:
        body = [pending]
    sections.append(('User Journey', body))

    if plan and plan.get('architecture'):
        body = ['| Lapisan | Pilihan | Alasan |', '|---|---|---|',
                *[f"| {_cell(a['layer'])} | {_cell(a['choice'])} | {_cell(a['reason'])} |" for a in plan['architecture']]]
    else:
        body = [pending]
    sections.append(('Arsitektur', body))

    body = []
    if plan:
        if plan.get('entities'):
            body += ['| Entitas | Kegunaan |', '|---|---|',
                     *[f"| {_cell(e['name'])} | {_cell(e['purpose'])} |" for e in plan['entities']], '']
        body += ['```sql', plan.get('ddl', ''), '```']
    sections.append(('Data Model', body or [pending]))

    body = []
    for a in plan.get('api') or [] if plan else []:
        body += [f"### `{a['method']} {a['path']}`", '', a.get('summary', ''), '',
                 'Request:', '', '```json', json.dumps(a.get('request', {}), ensure_ascii=False, indent=2), '```', '',
                 'Response:', '', '```json', json.dumps(a.get('response', {}), ensure_ascii=False, indent=2), '```', '']
        if a.get('errors'):
            body += ['Error:', '', _bullets(a['errors']), '']
    sections.append(('API Spec', body[:-1] if body else ['_Tidak ada endpoint._' if plan else pending]))

    if plan and plan.get('ai_tools'):
        body = []
        for t in plan['ai_tools']:
            body += [f"### `{t['name']}`", '', t.get('description', ''), '', '```json',
                     json.dumps(t.get('parameters', {}), ensure_ascii=False, indent=2), '```', '']
        sections.append(('Tool-call AI', body[:-1]))

    rows = traceability(idea, plan) if idea and plan else []
    if rows:
        sections.append(('Keterlacakan Fitur', [
            'Setiap sub-fitur MVP, use case yang memakainya, serta tabel dan endpoint yang membuatnya berjalan.', '',
            '| Fitur | Sub-fitur | Use case | Tabel | Endpoint |', '|---|---|---|---|---|',
            *[f"| {_cell(r['feature'])} | {_cell(r['sub_feature'])} | {_cell(', '.join(r['usecases']) or '-')} | "
              f"{_cell(', '.join(r['tables']) or '-')} | {_cell(r['endpoint'] or '-')} |" for r in rows]]))

    if tasks:
        body = ['Kerjakan berurutan; sebuah task baru dimulai setelah semua task di kolom "Bergantung" selesai.', '',
                '| ID | Judul | Bergantung | File | Kriteria selesai |', '|---|---|---|---|---|',
                *[f"| {t['id']} | {_cell(t['title'])} | {', '.join(t.get('depends_on') or []) or '-'} | "
                  f"{_cell(', '.join(t.get('files') or []))} | {_cell('; '.join(t.get('acceptance') or []))} |"
                  for t in tasks]]
        detailed = [t for t in tasks if t.get('description')]
        if detailed:
            body += ['', '### Rincian', '', *[f"- **{t['id']}** {t['description']}" for t in detailed]]
    else:
        body = [pending]
    sections.append(('Atomic Tasks', body))

    body = [_bullets(_strings(state.get('assumptions'), 40))]
    issues = _strings(state.get('issues'), 40)
    if issues:
        body += ['', '### Belum sinkron', '', 'Hal yang masih belum cocok antar-bagian PRD saat dokumen ini dibuat:', '',
                 _bullets(issues)]
    sections.append(('Asumsi dan Pertanyaan Terbuka', body))

    out = [f'# PRD: {name}', '']
    meta = [('Tanggal', date), ('Bahasa', raw.get('language', '')),
            ('Tech stack', ', '.join(f'{k} {stack[k]}' for k in STACK_FIELDS if stack.get(k))),
            ('Tingkat keahlian', cons.get('skill', '')), ('Budget infra', cons.get('budget', ''))]
    out += ['| Metadata | Keterangan |', '|---|---|', *[f'| {k} | {_cell(v)} |' for k, v in meta if v], '']
    for n, (title, body) in enumerate(sections, start=1):
        out += [f'## {n}. {title}', '', *body, '']
    return '\n'.join(out).rstrip() + '\n'
