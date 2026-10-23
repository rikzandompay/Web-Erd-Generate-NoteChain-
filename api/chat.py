# backend/chat.py
"""
Chat that only does one job: turn a request ("buatkan sequence diagram untuk
edit stok bahan") into UML text in this app's format, then build it with the
same generator as the editor. Any OpenAI-compatible endpoint works (9Router,
OpenRouter, a provider directly), configured through environment variables:

    AI_BASE_URL   default http://localhost:20128/v1   (9Router's local address)
    AI_API_KEY    optional, sent as a Bearer token
    AI_MODEL      required: the model name the endpoint knows
"""

import json
import os
import re
import time
from collections import defaultdict, deque
from typing import Any

import httpx  # type: ignore

from system_instruction import build_system_instruction  # type: ignore
from uml import DIAGRAM_BUILDERS, generate_uml  # type: ignore

def load_dotenv(path: str | None = None) -> None:
    """Fill os.environ from the project's .env (KEY=VALUE lines) for local runs.

    Variables already set in the environment win, so Vercel's settings are never overridden.
    """
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    try:
        with open(path, encoding='utf-8') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


load_dotenv()

MAX_MESSAGE_CHARS = 1500
MAX_HISTORY = 10
MAX_EDITOR_CHARS = 12000
RATE_LIMIT = 10             # requests per window per visitor
RATE_WINDOW = 3600          # seconds
TIMEOUT = 90.0

class ChatError(Exception):
    """Something the visitor should be told about; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ── Rate limit ───────────────────────────────────────────────────────────────
# Kept in memory: it limits each running instance, not the whole deployment.
_hits: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(visitor: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    hits = _hits[visitor]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        wait = int((RATE_WINDOW - (now - hits[0])) // 60) + 1
        raise ChatError(f'Batas {RATE_LIMIT} permintaan per jam tercapai. Coba lagi sekitar {wait} menit lagi.', 429)
    hits.append(now)


# ── Model call ───────────────────────────────────────────────────────────────

def call_model(messages: list[dict[str, str]]) -> str:
    """One chat completion from the configured OpenAI-compatible endpoint."""
    model = os.environ.get('AI_MODEL', '').strip()
    if not model:
        raise ChatError('Chatbot belum diatur: variabel AI_MODEL belum diisi di server.', 503)
    base = os.environ.get('AI_BASE_URL', 'http://localhost:20128/v1').rstrip('/')
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('AI_API_KEY'):
        headers['Authorization'] = f"Bearer {os.environ['AI_API_KEY']}"
    try:
        response = httpx.post(f'{base}/chat/completions', headers=headers, timeout=TIMEOUT,
                              json={'model': model, 'messages': messages, 'temperature': 0.2, 'stream': False})
    except httpx.TimeoutException:
        raise ChatError(f'Model AI terlalu lama menjawab (lebih dari {int(TIMEOUT)} detik). Coba lagi, atau ganti AI_MODEL ke model yang lebih cepat.', 504)
    except httpx.HTTPError:
        raise ChatError('Server AI tidak bisa dihubungi. Periksa AI_BASE_URL dan pastikan penyedia AI-nya berjalan.', 502)
    if response.status_code in (429, 503):
        wait = re.search(r'reset after ([0-9hms ]+)', response.text)
        hint = f' Kata server AI: bisa dicoba lagi dalam {wait.group(1).strip()}.' if wait else ''
        raise ChatError(f'Model AI sedang sibuk atau dibatasi oleh penyedianya.{hint} Coba lagi sebentar, atau ganti AI_MODEL.', 503)
    if response.status_code != 200:
        raise ChatError(f'Server AI menolak permintaan (kode {response.status_code}). Cek AI_MODEL dan AI_API_KEY.', 502)
    text = reply_text(response)
    if not text.strip():
        raise ChatError('Balasan server AI kosong atau tidak bisa dibaca.', 502)
    return text


def reply_text(response: httpx.Response) -> str:
    """The model's text from a normal reply, or glued together from a streamed (SSE) one.

    Some gateways (9Router among them) answer with `data: {...}` chunks even when
    streaming was not asked for, so both shapes are read.
    """
    body = response.text.strip()
    if body.startswith('data:'):
        parts = []
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith('data:') or line == 'data: [DONE]':
                continue
            try:
                delta = json.loads(line[5:])['choices'][0].get('delta', {})
            except (ValueError, KeyError, IndexError):
                continue
            parts.append(delta.get('content') or '')
        return ''.join(parts)
    try:
        return response.json()['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, ValueError, TypeError):
        return ''


def clean_reply(text: str) -> str:
    """The diagram text without markdown fences, which models add even when told not to."""
    text = text.strip()
    fenced = re.match(r'^```[a-zA-Z]*\n(.*?)\n?```\s*$', text, re.DOTALL)
    return (fenced.group(1) if fenced else text).strip()


# ── Public entry point ───────────────────────────────────────────────────────

def chat_generate(kind: str, messages: list[dict[str, str]], editor_text: str,
                  visitor: str) -> dict[str, Any]:
    """Run one chat turn and return the new text, the built diagram and a short reply."""
    if kind not in DIAGRAM_BUILDERS:
        raise ChatError(f'Jenis diagram "{kind}" belum didukung.')
    messages = [m for m in messages if m.get('role') in ('user', 'assistant') and m.get('content', '').strip()]
    if not messages or messages[-1]['role'] != 'user':
        raise ChatError('Tulis permintaan dulu.')
    messages = [{'role': m['role'], 'content': m['content'][:MAX_MESSAGE_CHARS]} for m in messages[-MAX_HISTORY:]]

    check_rate_limit(visitor)

    context = ''
    if editor_text.strip():
        context = f'\n\nTeks diagram yang sekarang ada di editor:\n{editor_text[:MAX_EDITOR_CHARS]}'
    conversation = [{'role': 'system', 'content': build_system_instruction(kind)}, *messages]
    conversation[-1] = {'role': 'user', 'content': conversation[-1]['content'] + context}

    reply = clean_reply(call_model(conversation))
    if reply.upper().startswith('TOLAK:'):
        return {'text': None, 'result': None, 'reply': reply[6:].strip() or 'Permintaan itu bukan soal diagram.'}

    result = generate_uml(kind, reply)
    # One automatic repair round when the model broke the syntax
    if result['errors']:
        problems = '\n'.join(f"Baris {e['line']}: {e['message']}" for e in result['errors'][:8])
        retry = [*conversation, {'role': 'assistant', 'content': reply}, {
            'role': 'user',
            'content': f'Teks tadi punya kesalahan sintaks:\n{problems}\nKembalikan teks LENGKAP yang sudah diperbaiki, tetap tanpa penjelasan.'}]
        fixed = clean_reply(call_model(retry))
        fixed_result = generate_uml(kind, fixed)
        if len(fixed_result['errors']) <= len(result['errors']):
            reply, result = fixed, fixed_result

    if not result['pages']:
        raise ChatError('AI belum menghasilkan diagram yang bisa dibaca. Coba tulis permintaannya lebih rinci.', 502)
    names = ', '.join(result['pages'])
    note = f"Sudah dibuat {len(result['pages'])} halaman: {names}. Teksnya ada di editor, boleh diedit atau diminta revisi."
    if result['errors']:
        note += f" {len(result['errors'])} baris masih perlu diperbaiki, lihat daftar di panel Hasil."
    return {'text': reply, 'result': result, 'reply': note}
