# backend/test_chat.py
"""Chat generation with a fake model: no network, no key."""

import pytest
from fastapi.testclient import TestClient  # type: ignore

import chat
from index import app  # type: ignore

GOOD = '''=== Login
actor Admin
boundary Sistem
Admin -> Sistem : Mengisi form
Sistem --> Admin : Menampilkan dashboard
'''
BROKEN = GOOD + 'ini baris salah\n'


@pytest.fixture(autouse=True)
def fresh_limits():
    chat._hits.clear()


def fake_model(monkeypatch, *replies):
    """Make call_model return `replies` in turn; returns the list of conversations it received."""
    seen, queue = [], list(replies)
    monkeypatch.setattr(chat, 'call_model', lambda messages: (seen.append(messages), queue.pop(0))[1])
    return seen


def ask(text, kind='sequence', editor=''):
    return chat.chat_generate(kind, [{'role': 'user', 'content': text}], editor, 'tester')


def test_request_becomes_text_and_diagram(monkeypatch):
    seen = fake_model(monkeypatch, GOOD)
    out = ask('buatkan sequence login admin')
    assert out['text'] == GOOD.strip()
    assert out['result']['pages'] == ['Login'] and out['result']['errors'] == []
    assert out['result']['xml'].startswith('<mxfile')
    assert 'Sudah dibuat 1 halaman: Login' in out['reply']
    system = seen[0][0]['content']
    assert 'SEQUENCE DIAGRAM' in system and 'ACTIVITY' not in system     # only the chosen format
    assert seen[0][-1]['content'] == 'buatkan sequence login admin'


def test_markdown_fences_are_stripped(monkeypatch):
    fake_model(monkeypatch, '```text\n' + GOOD + '```')
    assert ask('login')['text'] == GOOD.strip()


def test_editor_text_is_sent_as_context_for_revisions(monkeypatch):
    seen = fake_model(monkeypatch, GOOD)
    ask('tambahkan validasi', editor='=== Lama\nA -> B : x')
    last = seen[0][-1]['content']
    assert last.startswith('tambahkan validasi') and '=== Lama' in last


def test_syntax_errors_trigger_one_repair_round(monkeypatch):
    seen = fake_model(monkeypatch, BROKEN, GOOD)
    out = ask('login')
    assert len(seen) == 2
    assert 'Baris 6' in seen[1][-1]['content'] and 'Baris tidak dikenali' in seen[1][-1]['content']
    assert out['text'] == GOOD.strip() and out['result']['errors'] == []


def test_repair_that_is_no_better_is_not_used(monkeypatch):
    fake_model(monkeypatch, BROKEN, BROKEN + 'lagi salah\n')
    out = ask('login')
    assert out['text'] == BROKEN.strip() and len(out['result']['errors']) == 1
    assert '1 baris masih perlu diperbaiki' in out['reply']


def test_off_topic_requests_are_declined(monkeypatch):
    fake_model(monkeypatch, 'TOLAK: saya hanya membuat diagram.')
    out = ask('ceritakan lelucon')
    assert out['text'] is None and out['result'] is None and 'hanya membuat diagram' in out['reply']


def test_rate_limit_per_visitor(monkeypatch):
    fake_model(monkeypatch, *[GOOD] * 12)
    for _ in range(chat.RATE_LIMIT):
        ask('login')
    with pytest.raises(chat.ChatError) as err:
        ask('login')
    assert err.value.status == 429 and 'per jam' in str(err.value)
    # another visitor is unaffected
    assert chat.chat_generate('sequence', [{'role': 'user', 'content': 'login'}], '', 'orang-lain')['text']


def test_limits_on_input(monkeypatch):
    seen = fake_model(monkeypatch, GOOD)
    long_history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'x' * 5000} for i in range(21)]
    chat.chat_generate('sequence', long_history, '', 'tester')
    sent = seen[0][1:]
    assert len(sent) == chat.MAX_HISTORY and all(len(m['content']) <= chat.MAX_MESSAGE_CHARS for m in sent)


def test_validation(monkeypatch):
    with pytest.raises(chat.ChatError):
        chat.chat_generate('gantt', [{'role': 'user', 'content': 'x'}], '', 'v')
    with pytest.raises(chat.ChatError):
        chat.chat_generate('sequence', [], '', 'v')
    with pytest.raises(chat.ChatError):
        chat.chat_generate('sequence', [{'role': 'assistant', 'content': 'halo'}], '', 'v')


def test_missing_model_setting_is_reported(monkeypatch):
    monkeypatch.delenv('AI_MODEL', raising=False)
    with pytest.raises(chat.ChatError) as err:
        chat.call_model([{'role': 'user', 'content': 'x'}])
    assert err.value.status == 503 and 'AI_MODEL' in str(err.value)


def test_endpoint_returns_errors_as_http_status(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv('AI_MODEL', raising=False)
    r = client.post('/api/chat', json={'type': 'sequence', 'messages': [{'role': 'user', 'content': 'login'}]})
    assert r.status_code == 503 and 'AI_MODEL' in r.json()['detail']

    fake_model(monkeypatch, GOOD)
    r = client.post('/api/chat', json={'type': 'sequence', 'messages': [{'role': 'user', 'content': 'login'}]},
                    headers={'x-forwarded-for': '203.0.113.9, 10.0.0.1'})
    assert r.status_code == 200 and r.json()['result']['pages'] == ['Login']
    assert '203.0.113.9' in chat._hits


# ── Real HTTP to an OpenAI-compatible endpoint (9Router-shaped) ──────────────

@pytest.fixture
def openai_server(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = []

    class Handler(BaseHTTPRequestHandler):
        status = 200

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append({'path': self.path, 'auth': self.headers.get('Authorization'), 'body': body})
            self.send_response(Handler.status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            reply = {'choices': [{'message': {'role': 'assistant', 'content': '```\n' + GOOD + '```'}}]}
            self.wfile.write(json.dumps(reply if Handler.status == 200 else {'error': getattr(Handler, 'error_text', 'nope')}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv('AI_BASE_URL', f'http://127.0.0.1:{server.server_port}/v1/')
    monkeypatch.setenv('AI_MODEL', 'model-uji')
    monkeypatch.setenv('AI_API_KEY', 'kunci-rahasia')
    yield received, Handler
    server.shutdown()
    Handler.status = 200
    Handler.error_text = 'nope'


def test_calls_chat_completions_with_model_and_key(openai_server):
    received, _ = openai_server
    out = ask('login admin')
    assert out['result']['pages'] == ['Login']
    call = received[0]
    assert call['path'] == '/v1/chat/completions'
    assert call['auth'] == 'Bearer kunci-rahasia'
    assert call['body']['model'] == 'model-uji' and call['body']['messages'][0]['role'] == 'system'


def test_upstream_failure_gives_a_readable_error(openai_server):
    _, handler = openai_server
    handler.status = 401
    with pytest.raises(chat.ChatError) as err:
        ask('login admin')
    assert err.value.status == 502 and '401' in str(err.value) and 'AI_API_KEY' in str(err.value)


def test_unreachable_server_gives_a_readable_error(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'http://127.0.0.1:9/v1')
    monkeypatch.setenv('AI_MODEL', 'model-uji')
    with pytest.raises(chat.ChatError) as err:
        ask('login admin')
    assert err.value.status == 502 and 'tidak bisa dihubungi' in str(err.value)


def test_streamed_reply_is_glued_together(openai_server):
    """9Router answers with SSE chunks even when stream=false was sent."""
    import json as j
    received, handler = openai_server

    def streamed(self):
        body = j.loads(self.rfile.read(int(self.headers['Content-Length'])))
        received.append({'body': body})
        chunks = [{'choices': [{'delta': {'role': 'assistant'}}]}]
        chunks += [{'choices': [{'delta': {'content': line + '\n'}}]} for line in GOOD.splitlines()]
        chunks.append({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write(''.join(f'data: {j.dumps(c)}\n\n' for c in chunks).encode() + b'data: [DONE]\n\n')

    handler.do_POST = streamed
    out = ask('login admin')
    assert out['text'] == GOOD.strip() and out['result']['pages'] == ['Login']
    assert received[0]['body']['stream'] is False


def test_busy_model_is_explained_not_blamed_on_settings(openai_server):
    _, handler = openai_server
    handler.status = 503
    handler.error_text = 'upstream queued (reset after 1m 55s)'
    with pytest.raises(chat.ChatError) as err:
        ask('login admin')
    assert err.value.status == 503
    assert 'sibuk' in str(err.value) and '1m 55s' in str(err.value) and 'AI_API_KEY' not in str(err.value)


def test_dotenv_fills_missing_variables_but_never_overrides(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('# komentar\nAI_MODEL=model-dari-file\nAI_BASE_URL="http://contoh/v1"\nAI_API_KEY=\n\nrusak tanpa sama dengan\n')
    monkeypatch.delenv('AI_MODEL', raising=False)
    monkeypatch.delenv('AI_BASE_URL', raising=False)
    monkeypatch.setenv('AI_API_KEY', 'dari-environment')
    chat.load_dotenv(str(env_file))
    import os
    assert os.environ['AI_MODEL'] == 'model-dari-file'
    assert os.environ['AI_BASE_URL'] == 'http://contoh/v1'
    assert os.environ['AI_API_KEY'] == 'dari-environment'      # real environment wins
    chat.load_dotenv(str(tmp_path / 'tidak-ada.env'))           # a missing file is fine


def test_every_diagram_type_has_a_prompt_format():
    from uml import DIAGRAM_BUILDERS
    from system_instruction import FORMATS
    assert set(FORMATS) == set(DIAGRAM_BUILDERS)


def test_use_case_request_builds_a_use_case_page(monkeypatch):
    seen = fake_model(monkeypatch, "=== Perpustakaan\nsystem P {\n(Login)\n}\nactor Petugas\nPetugas --> (Login)\n")
    out = chat.chat_generate('usecase', [{'role': 'user', 'content': 'buat use case perpustakaan'}], '', 'tester')
    assert out['result']['pages'] == ['Perpustakaan'] and out['result']['errors'] == []
    assert 'USE CASE DIAGRAM' in seen[0][0]['content']


def test_slow_model_gets_its_own_message(monkeypatch):
    import httpx
    monkeypatch.setenv('AI_BASE_URL', 'http://127.0.0.1:9/v1')
    monkeypatch.setenv('AI_MODEL', 'model-uji')
    def too_slow(*args, **kwargs):
        raise httpx.ReadTimeout('lambat')
    monkeypatch.setattr(chat.httpx, 'post', too_slow)
    with pytest.raises(chat.ChatError) as err:
        ask('login admin')
    assert err.value.status == 504 and 'terlalu lama' in str(err.value) and '9Router' not in str(err.value)
