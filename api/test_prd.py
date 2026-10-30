# backend/test_prd.py
"""PRD generator: input checks, the three stages with a fake model, task ordering, Markdown."""

import copy
import json

import pytest
from fastapi.testclient import TestClient  # type: ignore

import chat
import prd
from index import app  # type: ignore
from prd_instruction import IDEA_EXAMPLE, PLAN_EXAMPLE, QUESTIONS_EXAMPLE, TASKS_EXAMPLE, instruction  # type: ignore

INPUT = {
    'idea_text': 'Yayasan mencatat donasi di buku, laporan selalu terlambat. Mau aplikasi web untuk admin dan donatur.',
    'answers': [{'question': 'Fitur wajib?', 'answer': 'Catat donasi, Laporan bulanan'}],
    'language': 'Bahasa Indonesia',
    'stack': {'frontend': 'React', 'backend': 'FastAPI', 'database': 'PostgreSQL', 'deployment': 'Vercel'},
    'constraints': {'skill': 'pemula', 'budget': 'free tier'},
    'context': {'text': '', 'sql_text': ''},
}


@pytest.fixture(autouse=True)
def fresh_limits():
    chat._hits.clear()


def fake_model(monkeypatch, *replies):
    seen, queue = [], [r if isinstance(r, str) else json.dumps(r) for r in replies]
    monkeypatch.setattr(prd, 'call_model', lambda messages, prefix='AI': (seen.append(messages), queue.pop(0))[1])
    return seen


# ── Input ────────────────────────────────────────────────────────────────────

def test_missing_fields_are_all_named():
    bad = copy.deepcopy(INPUT)
    bad['idea_text'] = 'app'
    bad['stack']['database'] = ''
    bad['constraints']['skill'] = 'dewa'
    with pytest.raises(chat.ChatError) as err:
        prd.clean_input(bad)
    assert 'deskripsi ide' in str(err.value) and 'tech stack database' in str(err.value) and 'tingkat keahlian' in str(err.value)
    # the questions come before the stack is chosen
    assert prd.clean_input({'idea_text': INPUT['idea_text']}, need_stack=False)['language'] == 'Bahasa Indonesia'


def test_answers_and_language_reach_the_model():
    brief = prd._brief(prd.clean_input(INPUT))
    assert '- Fitur wajib? -> Catat donasi, Laporan bulanan' in brief and 'Bahasa dokumen: Bahasa Indonesia' in brief
    english = dict(INPUT, language='English', answers=[{'question': 'x', 'answer': ''}, 'junk'])
    data = prd.clean_input(english)
    assert data['language'] == 'English' and data['answers'] == []


def test_old_schema_is_summarised_for_the_model():
    data = copy.deepcopy(INPUT)
    data['context']['sql_text'] = ('CREATE TABLE a (id INT PRIMARY KEY);'
                                   'CREATE TABLE b (id INT PRIMARY KEY, a_id INT REFERENCES a(id));')
    brief = prd._brief(prd.clean_input(data))
    assert '- b: id INT PK, a_id INT FK->a.id' in brief and 'Skema database lama' in brief


# ── Stages ───────────────────────────────────────────────────────────────────

def test_idea_stage(monkeypatch):
    seen = fake_model(monkeypatch, '```json\n' + json.dumps(IDEA_EXAMPLE) + '\n```')
    out = prd.prd_idea(INPUT, 'v')
    assert out['idea']['product_name'] == 'DonasiKu' and out['assumptions']
    assert 'TAHAP 1' in seen[0][0]['content'] and 'Yayasan mencatat donasi' in seen[0][1]['content']
    assert [f['phase'] for f in out['idea']['features']] == [1, 1, 2, 2, 3]


def test_plan_stage_checks_sql_and_use_case(monkeypatch):
    fake_model(monkeypatch, PLAN_EXAMPLE)
    out = prd.prd_plan(INPUT, IDEA_EXAMPLE['idea'], 'v')
    assert out['checks'] == {'ddl_errors': [], 'usecase_errors': [], 'consistency': []}
    assert out['plan']['api'][0]['path'] == '/api/donasi'


def test_broken_sql_gets_one_repair_round(monkeypatch):
    broken = copy.deepcopy(PLAN_EXAMPLE)
    broken['plan']['ddl'] = 'CREATE TABLE donasi (id INT PRIMARY KEY, donatur_id INT REFERENCES donatur(id));'
    seen = fake_model(monkeypatch, broken, PLAN_EXAMPLE)
    out = prd.prd_plan(INPUT, IDEA_EXAMPLE['idea'], 'v')
    assert len(seen) == 2 and 'merujuk tabel donatur yang tidak ada' in seen[1][-1]['content']
    assert out['checks']['ddl_errors'] == []


def test_problems_left_after_the_repair_are_reported(monkeypatch):
    broken = copy.deepcopy(PLAN_EXAMPLE)
    broken['plan']['usecase_text'] = '=== X\napa ini\n(A)\nAdmin --> (A)'
    fake_model(monkeypatch, broken, broken)
    out = prd.prd_plan(INPUT, IDEA_EXAMPLE['idea'], 'v')
    assert out['checks']['usecase_errors'] and 'Baris 2' in out['checks']['usecase_errors'][0]


def test_unreadable_answer_twice_is_an_error(monkeypatch):
    fake_model(monkeypatch, 'maaf saya tidak bisa', 'masih bukan json')
    with pytest.raises(chat.ChatError) as err:
        prd.prd_idea(INPUT, 'v')
    assert err.value.status == 502 and 'bukan JSON' in str(err.value)


def test_tasks_stage_orders_and_caps(monkeypatch):
    shuffled = {'tasks': [TASKS_EXAMPLE['tasks'][2], TASKS_EXAMPLE['tasks'][0], TASKS_EXAMPLE['tasks'][1]]}
    seen = fake_model(monkeypatch, shuffled)
    out = prd.prd_tasks(INPUT, IDEA_EXAMPLE['idea'], PLAN_EXAMPLE['plan'], 'v')
    assert [t['id'] for t in out['tasks']] == ['T01', 'T02', 'T03'] and out['problems'] == []
    assert 'paling banyak 25' in seen[0][0]['content']                  # pemula


def test_circular_tasks_get_repaired(monkeypatch):
    loop = {'tasks': [{'id': 'T01', 'title': 'a', 'depends_on': ['T02']}, {'id': 'T02', 'title': 'b', 'depends_on': ['T01']}]}
    seen = fake_model(monkeypatch, loop, TASKS_EXAMPLE)
    out = prd.prd_tasks(INPUT, IDEA_EXAMPLE['idea'], PLAN_EXAMPLE['plan'], 'v')
    assert 'melingkar' in seen[1][-1]['content'] and out['problems'] == []


def test_later_stages_need_the_earlier_ones():
    with pytest.raises(chat.ChatError, match='tahap 1'):
        prd.prd_plan(INPUT, {}, 'v')
    with pytest.raises(chat.ChatError, match='tahap 2'):
        prd.prd_tasks(INPUT, IDEA_EXAMPLE['idea'], {}, 'v')
    with pytest.raises(chat.ChatError, match='tidak lengkap'):
        prd.prd_plan(INPUT, {'product_name': 'x'}, 'v')               # edited down to nothing


def test_each_stage_counts_once_against_the_limit(monkeypatch):
    fake_model(monkeypatch, *[IDEA_EXAMPLE] * 12)
    for _ in range(chat.RATE_LIMIT):
        prd.prd_idea(INPUT, 'v')
    with pytest.raises(chat.ChatError) as err:
        prd.prd_idea(INPUT, 'v')
    assert err.value.status == 429


# ── Task ordering ────────────────────────────────────────────────────────────

def test_order_tasks_reports_every_problem():
    tasks, errors = prd.order_tasks([
        {'id': 'T01', 'title': 'a', 'depends_on': ['T09']},
        {'id': 'T01', 'title': 'dup'},
        {'id': 'T02', 'title': 'b', 'depends_on': ['T02']},
    ])
    assert [t['id'] for t in tasks] == ['T01', 'T02']
    assert any('dipakai lebih dari sekali' in e for e in errors)
    assert any('T09 yang tidak ada' in e for e in errors)
    assert any('dirinya sendiri' in e for e in errors)


def test_order_tasks_keeps_model_order_when_free():
    tasks, errors = prd.order_tasks([{'id': 'T02', 'depends_on': []}, {'id': 'T01', 'depends_on': []},
                                     {'id': 'T03', 'depends_on': ['T01']}])
    assert [t['id'] for t in tasks] == ['T02', 'T01', 'T03'] and errors == []


# ── The examples taught to the model are valid ───────────────────────────────

def test_instruction_examples_pass_the_same_checks():
    assert prd.normalize_idea(IDEA_EXAMPLE)['mvp_scope']
    assert prd.plan_checks(prd.normalize_plan(PLAN_EXAMPLE)) == {'ddl_errors': [], 'usecase_errors': []}
    assert prd.order_tasks(TASKS_EXAMPLE['tasks'])[1] == []
    from prd_consistency import plan_consistency, tasks_consistency
    assert plan_consistency(prd.normalize_idea(IDEA_EXAMPLE), prd.normalize_plan(PLAN_EXAMPLE)) == []
    assert tasks_consistency(prd.normalize_plan(PLAN_EXAMPLE), prd.order_tasks(TASKS_EXAMPLE['tasks'])[0]) == []
    assert len(prd.normalize_questions(QUESTIONS_EXAMPLE)) == 5
    for stage in ('questions', 'idea', 'plan', 'tasks'):
        assert len(instruction(stage)) < 9000
    assert 'paling banyak 40' in instruction('tasks', 'pro')


# ── Markdown ─────────────────────────────────────────────────────────────────

def _full_state():
    return {'input': INPUT, 'idea': IDEA_EXAMPLE['idea'], 'plan': PLAN_EXAMPLE['plan'],
            'tasks': TASKS_EXAMPLE['tasks'], 'assumptions': ['Satu yayasan per instalasi.']}


def test_markdown_has_every_section_in_order():
    md = prd.render_prd_markdown(_full_state(), '2026-10-25')
    heads = [line for line in md.splitlines() if line.startswith('## ')]
    assert heads == ['## 1. Ringkasan', '## 2. Scope MVP', '## 3. Struktur Fitur', '## 4. User Journey',
                     '## 5. Arsitektur', '## 6. Data Model', '## 7. API Spec', '## 8. Keterlacakan Fitur',
                     '## 9. Atomic Tasks', '## 10. Asumsi dan Pertanyaan Terbuka']
    assert '| Verifikasi Donasi | Catatan verifikasi | Verifikasi Donasi | donasi | PATCH /api/donasi/{id}/verifikasi |' in md
    assert '### Fase 1 (MVP)' in md and '- **Pencatatan Donasi**: Form donasi, Unggah bukti transfer' in md
    assert md.startswith('# PRD: DonasiKu') and '| Tanggal | 2026-10-25 |' in md
    assert '```sql\nCREATE TABLE donatur' in md and '### `POST /api/donasi`' in md
    assert '| T02 | Endpoint POST /api/donasi | T01 |' in md


def test_markdown_marks_missing_stages_and_tool_section_only_when_needed():
    md = prd.render_prd_markdown({'input': INPUT, 'idea': IDEA_EXAMPLE['idea']})
    assert md.count('_Belum dibuat.') >= 4 and 'Tool-call AI' not in md
    state = _full_state()
    state['plan'] = copy.deepcopy(PLAN_EXAMPLE['plan'])
    state['plan']['ai_tools'] = [{'name': 'cari_donasi', 'description': 'Mencari donasi', 'parameters': {'type': 'object'}}]
    md = prd.render_prd_markdown(state)
    assert '## 8. Tool-call AI' in md and '## 9. Keterlacakan Fitur' in md and '## 10. Atomic Tasks' in md and '## 11. Asumsi' in md


def test_the_sql_and_use_case_in_the_markdown_build_diagrams():
    from generator import generate_drawio_xml
    from sql_parser import parse_sql
    from uml import generate_uml
    md = prd.render_prd_markdown(_full_state())
    sql = md.split('```sql\n', 1)[1].split('\n```', 1)[0]
    usecase = md.split('```text\n', 1)[1].split('\n```', 1)[0]
    assert 'name="ERD"' in generate_drawio_xml(parse_sql(sql))
    assert generate_uml('usecase', usecase)['errors'] == []


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_endpoints(monkeypatch):
    client = TestClient(app)
    fake_model(monkeypatch, IDEA_EXAMPLE)
    r = client.post('/api/prd/idea', json={'input': INPUT})
    assert r.status_code == 200 and r.json()['idea']['product_name'] == 'DonasiKu'
    assert client.post('/api/prd/idea', json={'input': {}}).status_code == 400
    assert client.post('/api/prd/plan', json={'input': INPUT}).status_code == 400
    r = client.post('/api/prd/markdown', json=_full_state())
    assert r.status_code == 200 and r.json()['file_name'] == 'PRD-donasiku.md'
    assert r.json()['markdown'].startswith('# PRD: DonasiKu')


def test_use_case_without_an_output_actor_is_flagged():
    plan = prd.normalize_plan(PLAN_EXAMPLE)
    plan['usecase_text'] = '=== X\nsystem X {\n  (A)\n}\nactor Admin\nAdmin --> (A)'
    assert prd.plan_checks(plan)['usecase_errors'] == ['Belum ada aktor <<sekunder>> di kanan yang menerima hasil.']


def test_the_same_party_on_both_sides_is_flagged():
    plan = prd.normalize_plan(PLAN_EXAMPLE)
    plan['usecase_text'] = ('=== X\nsystem X {\n  (A)\n  (B)\n}\nactor Pemilik\nactor Pemilik Toko <<sekunder>>\n'
                            'Pemilik --> (A)\nPemilik Toko --> (B)')
    assert prd.plan_checks(plan)['usecase_errors'] == ['Aktor Pemilik dan Pemilik Toko tampaknya pihak yang sama; tulis sekali saja.']


def test_plantuml_aliases_are_flagged():
    plan = prd.normalize_plan(PLAN_EXAMPLE)
    plan['usecase_text'] = ('=== X\nsystem X {\n  (A)\n}\nactor "Admin Prodi" as Admin\nactor Bank <<sekunder>>\n'
                            '"Admin Prodi" as Admin --> (A)\nBank --> (A)')
    assert any('alias' in e for e in prd.plan_checks(plan)['usecase_errors'])


def test_the_tools_own_name_is_not_used_for_the_product():
    answer = copy.deepcopy(IDEA_EXAMPLE)
    answer['idea']['product_name'] = 'ERD Generator'
    assert prd.normalize_idea(answer)['product_name'] == ''
    assert 'jangan pernah memakai nama "ERD Generator"' in instruction('idea')


# ── Clarifying questions and features ────────────────────────────────────────

def test_questions_stage(monkeypatch):
    seen = fake_model(monkeypatch, QUESTIONS_EXAMPLE)
    out = prd.prd_questions({'idea_text': INPUT['idea_text']}, 'v')
    assert out['fallback'] is False and [q['type'] for q in out['questions']] == ['text', 'single', 'multi', 'single', 'single']
    assert 'PERTANYAAN KLARIFIKASI' in seen[0][0]['content']


def test_unreadable_questions_fall_back_to_general_ones(monkeypatch):
    fake_model(monkeypatch, 'bukan json', '{"questions": []}')
    out = prd.prd_questions({'idea_text': INPUT['idea_text']}, 'v')
    assert out['fallback'] is True and len(out['questions']) == 5


def test_questions_without_choices_are_dropped():
    with pytest.raises(ValueError):
        prd.normalize_questions({'questions': [{'question': 'a', 'type': 'single', 'options': ['x']},
                                               {'question': 'b', 'type': 'text'}]})


def test_features_are_cleaned_and_sorted_by_phase():
    features = prd.normalize_features([{'name': 'B', 'phase': 3, 'sub_features': ['x']}, {'name': '', 'phase': 1},
                                       {'name': 'A', 'phase': '9'}, {'name': 'C', 'phase': 'x'}])
    assert features == [{'name': 'C', 'phase': 1, 'sub_features': []}, {'name': 'B', 'phase': 3, 'sub_features': ['x']},
                        {'name': 'A', 'phase': 4, 'sub_features': []}]
    idea = copy.deepcopy(IDEA_EXAMPLE)
    idea['idea']['mvp_scope'] = []
    assert prd.normalize_idea(idea)['mvp_scope'] == ['Pencatatan Donasi', 'Verifikasi Donasi']


# ── Its own model ────────────────────────────────────────────────────────────

def test_prd_uses_its_own_settings_only_when_prd_ai_model_is_set(monkeypatch):
    used = []
    monkeypatch.setattr(prd, 'call_model', lambda messages, prefix='AI': (used.append(prefix), json.dumps(QUESTIONS_EXAMPLE))[1])
    monkeypatch.delenv('PRD_AI_MODEL', raising=False)
    prd.prd_questions({'idea_text': INPUT['idea_text']}, 'v')
    monkeypatch.setenv('PRD_AI_MODEL', 'kr/auto')
    chat._hits.clear()
    prd.prd_questions({'idea_text': INPUT['idea_text']}, 'v')
    assert used == ['AI', 'PRD_AI']


def test_call_model_reads_the_prefixed_variables(monkeypatch):
    import httpx
    sent = {}

    class Reply:
        status_code, text = 200, '{"choices":[{"message":{"content":"halo"}}]}'

        def json(self):
            return json.loads(self.text)

    def post(url, headers, timeout, json):
        sent.update(url=url, auth=headers.get('Authorization'), model=json['model'])
        return Reply()

    monkeypatch.setattr(chat.httpx, 'post', post)
    monkeypatch.setenv('PRD_AI_BASE_URL', 'http://router.test/v1')
    monkeypatch.setenv('PRD_AI_API_KEY', 'kunci-router')
    monkeypatch.setenv('PRD_AI_MODEL', 'kr/auto')
    assert chat.call_model([{'role': 'user', 'content': 'x'}], 'PRD_AI') == 'halo'
    assert sent == {'url': 'http://router.test/v1/chat/completions', 'auth': 'Bearer kunci-router', 'model': 'kr/auto'}
    monkeypatch.delenv('PRD_AI_API_KEY')
    chat.call_model([{'role': 'user', 'content': 'x'}], 'PRD_AI')
    assert sent['auth'] is None                          # never falls back to the chat's key
