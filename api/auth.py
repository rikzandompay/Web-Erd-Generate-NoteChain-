# backend/auth.py
"""
Sign in with Google, and a session cookie.

    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET   an OAuth client from Google Cloud Console
    SESSION_SECRET                           a long random string that signs the cookies
    APP_URL (optional)                       e.g. https://erd.example.com; otherwise taken from the request

Flow: /api/auth/google/login sends the browser to Google with a random `state` and
`nonce` kept in a short-lived signed cookie; Google sends it back to
/api/auth/google/callback, which checks the state, trades the code for an ID token
directly with Google over TLS, checks the token's audience, issuer, expiry, nonce
and verified email, saves the user and sets the session cookie (HttpOnly, SameSite=Lax,
Secure on https). Nothing about the session is readable from JavaScript.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx  # type: ignore

SESSION_COOKIE = 'erdgen_session'
FLOW_COOKIE = 'erdgen_oauth'
SESSION_DAYS = 30
FLOW_SECONDS = 600
GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_ISSUERS = ('accounts.google.com', 'https://accounts.google.com')

# Without SESSION_SECRET, a local run gets a random one (sessions end when the server restarts)
_local_secret = secrets.token_urlsafe(32)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(os.environ.get('GOOGLE_CLIENT_ID') and os.environ.get('GOOGLE_CLIENT_SECRET') and _secret())


def _secret() -> str:
    secret = os.environ.get('SESSION_SECRET', '').strip()
    if secret:
        return secret
    if os.environ.get('VERCEL'):                  # deployed: never sign with a throwaway key
        return ''
    return _local_secret


# ── Signed values ────────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(',', ':')).encode())
    mac = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest()
    return f'{body}.{_b64(mac)}'


def unsign(value: str | None) -> dict[str, Any] | None:
    """The payload of a value made by sign(), or None when it was altered, malformed or expired."""
    if not value or '.' not in value or not _secret():
        return None
    body, mac = value.rsplit('.', 1)
    expected = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(mac)):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get('exp', 0) < time.time():
        return None
    return payload


def session_value(user_id: str) -> str:
    return sign({'uid': user_id, 'exp': int(time.time()) + SESSION_DAYS * 86400})


def session_user_id(cookie: str | None) -> str | None:
    payload = unsign(cookie)
    return payload.get('uid') if payload else None


def cookie_options(request_url: str, max_age: int) -> dict[str, Any]:
    return {'max_age': max_age, 'httponly': True, 'samesite': 'lax', 'path': '/',
            'secure': request_url.startswith('https://')}


# ── Google ───────────────────────────────────────────────────────────────────

def safe_next(value: str | None) -> str:
    """Only a path on this site: no other host, no '//evil.example' tricks."""
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value:
        return '/'
    return value


def base_url(headers: dict[str, str], fallback: str) -> str:
    """https://host of this app, as Google must send the user back to the exact registered address."""
    if os.environ.get('APP_URL'):
        return os.environ['APP_URL'].rstrip('/')
    proto = headers.get('x-forwarded-proto') or fallback.split('://', 1)[0]
    host = headers.get('x-forwarded-host') or headers.get('host') or fallback.split('://', 1)[1].split('/', 1)[0]
    return f'{proto}://{host}'


def redirect_uri(base: str) -> str:
    return f'{base}/api/auth/google/callback'


def start_login(base: str, next_path: str | None) -> tuple[str, str]:
    """(Google URL to send the browser to, signed flow cookie)."""
    if not configured():
        raise AuthError('Login belum diatur di server: isi GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, dan SESSION_SECRET.', 503)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    flow = sign({'state': state, 'nonce': nonce, 'next': safe_next(next_path), 'exp': int(time.time()) + FLOW_SECONDS})
    query = urlencode({
        'client_id': os.environ['GOOGLE_CLIENT_ID'], 'redirect_uri': redirect_uri(base), 'response_type': 'code',
        'scope': 'openid email profile', 'state': state, 'nonce': nonce, 'prompt': 'select_account',
    })
    return f'{GOOGLE_AUTH}?{query}', flow


def exchange_code(code: str, base: str) -> dict[str, Any]:
    """The ID token's claims, from Google's token endpoint (trusted because it is fetched directly over TLS)."""
    try:
        response = httpx.post(GOOGLE_TOKEN, timeout=15, data={
            'code': code, 'client_id': os.environ['GOOGLE_CLIENT_ID'],
            'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
            'redirect_uri': redirect_uri(base), 'grant_type': 'authorization_code'})
    except httpx.HTTPError:
        raise AuthError('Tidak bisa menghubungi Google. Coba lagi.', 502)
    if response.status_code != 200:
        raise AuthError('Google menolak login ini. Coba masuk lagi.', 400)
    token = response.json().get('id_token', '')
    try:
        return json.loads(_unb64(token.split('.')[1]))
    except (IndexError, ValueError):
        raise AuthError('Balasan Google tidak bisa dibaca.', 502)


def finish_login(params: dict[str, str], flow_cookie: str | None, base: str) -> tuple[dict[str, str], str]:
    """Checks Google's answer; returns (profile, path to go back to)."""
    flow = unsign(flow_cookie)
    if params.get('error'):
        raise AuthError('Login dibatalkan.', 400)
    if not flow or not params.get('state') or not hmac.compare_digest(flow['state'], params['state']):
        raise AuthError('Sesi login kedaluwarsa atau tidak cocok. Coba masuk lagi.', 400)
    if not params.get('code'):
        raise AuthError('Google tidak mengirim kode login.', 400)
    claims = exchange_code(params['code'], base)
    if claims.get('aud') != os.environ['GOOGLE_CLIENT_ID'] or claims.get('iss') not in GOOGLE_ISSUERS:
        raise AuthError('Token login bukan untuk aplikasi ini.', 400)
    if claims.get('exp', 0) < time.time() or claims.get('nonce') != flow['nonce']:
        raise AuthError('Token login kedaluwarsa atau tidak cocok.', 400)
    if not claims.get('sub') or not claims.get('email') or claims.get('email_verified') is not True:
        raise AuthError('Email akun Google belum terverifikasi.', 400)
    profile = {'sub': str(claims['sub']), 'email': str(claims['email']), 'name': str(claims.get('name', '')),
               'picture': str(claims.get('picture', ''))}
    return profile, flow['next']
