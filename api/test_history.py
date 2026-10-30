"""
Accounts and saved PRDs: Google sign-in (with Google itself replaced by a stub),
the session cookie, and that every plan stays with its owner.
The store tests also run on PostgreSQL when TEST_POSTGRES_URL is set, e.g.
    docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=x postgres:16
    TEST_POSTGRES_URL=postgresql://postgres:x@127.0.0.1:55432/postgres pytest test_history.py
"""

import os
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient  # type: ignore

import auth
import db
import index

CLIENT_ID = 'client-123.apps.googleusercontent.com'


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', CLIENT_ID)
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'secret')
    monkeypatch.setenv('SESSION_SECRET', 'test-session-secret')
    for name in ('APP_URL', 'VERCEL', 'DATABASE_URL', 'POSTGRES_URL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(db, '_store', db.Store(url='', sqlite_path=str(tmp_path / 'test.db')))


def google_claims(**changes):
    claims = {'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'exp': time.time() + 600,
              'sub': 'google-1', 'email': 'ani@example.com', 'email_verified': True, 'name': 'Ani', 'picture': ''}
    return {**claims, **changes}


def sign_in(client, monkeypatch, sub='google-1', email='ani@example.com', **changes):
    """Runs the whole Google flow with the token endpoint stubbed; returns the final response."""
    start = client.get('/api/auth/google/login?next=/prd', follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers['location']).query)
    nonce = query['nonce'][0]
    monkeypatch.setattr(auth, 'exchange_code', lambda code, base: google_claims(
        **{'sub': sub, 'email': email, 'nonce': nonce, **changes}))
    return client.get(f'/api/auth/google/callback?code=abc&state={query["state"][0]}', follow_redirects=False)


def test_login_redirects_to_google_with_state_and_exact_callback():
    client = TestClient(index.app)
    response = client.get('/api/auth/google/login?next=/prd', follow_redirects=False)
    url = urlparse(response.headers['location'])
    query = parse_qs(url.query)
    assert url.netloc == 'accounts.google.com'
    assert query['client_id'] == [CLIENT_ID]
    assert query['redirect_uri'] == ['http://testserver/api/auth/google/callback']
    assert query['scope'] == ['openid email profile']
    cookie = response.headers['set-cookie']
    assert auth.FLOW_COOKIE in cookie and 'HttpOnly' in cookie and 'samesite=lax' in cookie.lower()


def test_full_sign_in_sets_session_and_returns_to_page(monkeypatch):
    client = TestClient(index.app)
    response = sign_in(client, monkeypatch)
    assert response.status_code == 303 and response.headers['location'] == '/prd'
    assert auth.SESSION_COOKIE in response.headers['set-cookie']
    me = client.get('/api/auth/me').json()
    assert me['login_ready'] is True
    assert me['user']['email'] == 'ani@example.com' and 'google_sub' not in me['user']


@pytest.mark.parametrize('changes, reason', [
    ({'aud': 'someone-else'}, 'bukan untuk aplikasi ini'),
    ({'iss': 'https://evil.example'}, 'bukan untuk aplikasi ini'),
    ({'exp': time.time() - 10}, 'kedaluwarsa'),
    ({'email_verified': False}, 'belum terverifikasi'),
])
def test_bad_tokens_are_refused(monkeypatch, changes, reason):
    client = TestClient(index.app)
    response = sign_in(client, monkeypatch, **changes)
    assert response.status_code == 303
    assert reason in parse_qs(urlparse(response.headers['location']).query)['login_error'][0]
    assert client.get('/api/auth/me').json()['user'] is None


def test_wrong_state_and_wrong_nonce_are_refused(monkeypatch):
    client = TestClient(index.app)
    client.get('/api/auth/google/login', follow_redirects=False)
    monkeypatch.setattr(auth, 'exchange_code', lambda code, base: google_claims(nonce='x'))
    response = client.get('/api/auth/google/callback?code=abc&state=forged', follow_redirects=False)
    assert 'login_error' in response.headers['location']
    response = sign_in(client, monkeypatch, nonce='not-the-one-sent')
    assert 'login_error' in response.headers['location']
    assert client.get('/api/auth/me').json()['user'] is None


@pytest.mark.parametrize('target', ['https://evil.example/', '//evil.example/x', '/\\evil.example', 'javascript:alert(1)'])
def test_next_never_leaves_the_site(target):
    assert auth.safe_next(target) == '/'
    assert auth.safe_next('/prd?x=1') == '/prd?x=1'


def test_session_cookie_cannot_be_forged_or_reused_after_expiry(monkeypatch):
    value = auth.session_value('user-1')
    assert auth.session_user_id(value) == 'user-1'
    body, mac = value.rsplit('.', 1)
    forged = auth._b64(b'{"uid":"user-2","exp":9999999999}') + '.' + mac
    assert auth.session_user_id(forged) is None
    assert auth.session_user_id(auth.sign({'uid': 'user-1', 'exp': int(time.time()) - 1})) is None
    monkeypatch.setenv('SESSION_SECRET', 'another-secret')
    assert auth.session_user_id(value) is None


def test_login_not_configured_reports_it(monkeypatch):
    monkeypatch.delenv('GOOGLE_CLIENT_ID')
    client = TestClient(index.app)
    response = client.get('/api/auth/google/login?next=/', follow_redirects=False)
    assert 'login_error' in response.headers['location']
    assert client.get('/api/auth/me').json() == {'user': None, 'login_ready': False}


def test_vercel_without_database_or_secret_is_not_ready(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    assert not db.available()
    monkeypatch.delenv('SESSION_SECRET')
    assert not auth.configured()
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@host/db')
    assert db.available()


def test_plans_need_a_session():
    client = TestClient(index.app)
    assert client.get('/api/plans').status_code == 401
    assert client.post('/api/plans', json={'draft': {}}).status_code == 401
    forged = TestClient(index.app, cookies={auth.SESSION_COOKIE: 'abc.def'})
    assert forged.get('/api/plans').status_code == 401


def test_plan_life_cycle(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    plan = client.post('/api/plans', json={'title': 'Kasir', 'screen': 'tech', 'draft': {'idea': 'kasir toko'}}).json()
    assert plan['draft'] == {'idea': 'kasir toko'} and plan['screen'] == 'tech'

    assert client.put(f'/api/plans/{plan["id"]}', json={'title': 'Kasir Toko', 'screen': 'prd',
                                                       'draft': {'idea': 'kasir toko', 'step': 3}}).status_code == 200
    v1 = client.post(f'/api/plans/{plan["id"]}/versions', json={'state': {'idea': {'product_name': 'Kasir'}}}).json()
    v2 = client.post(f'/api/plans/{plan["id"]}/versions', json={'state': {'idea': {'product_name': 'Kasir 2'}}}).json()
    assert (v1['n'], v2['n']) == (1, 2)

    listed = client.get('/api/plans').json()['plans']
    assert [(p['title'], p['screen'], p['versions']) for p in listed] == [('Kasir Toko', 'prd', 2)]
    full = client.get(f'/api/plans/{plan["id"]}').json()
    assert [v['n'] for v in full['versions']] == [1, 2]
    assert full['versions'][1]['state'] == {'idea': {'product_name': 'Kasir 2'}}
    assert full['draft'] == {'idea': 'kasir toko', 'step': 3}

    assert client.delete(f'/api/plans/{plan["id"]}').status_code == 204
    assert client.get(f'/api/plans/{plan["id"]}').status_code == 404
    assert client.get('/api/plans').json()['plans'] == []


def test_unknown_screen_falls_back_to_start(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    plan = client.post('/api/plans', json={'screen': '<script>', 'draft': {}}).json()
    assert plan['screen'] == 'start'


def test_other_users_cannot_see_or_touch_a_plan(monkeypatch):
    ani, budi = TestClient(index.app), TestClient(index.app)
    sign_in(ani, monkeypatch)
    sign_in(budi, monkeypatch, sub='google-2', email='budi@example.com')
    plan = ani.post('/api/plans', json={'title': 'Rahasia', 'draft': {'x': 1}}).json()
    path = f'/api/plans/{plan["id"]}'

    assert budi.get('/api/plans').json()['plans'] == []
    assert budi.get(path).status_code == 404
    assert budi.put(path, json={'title': 'diambil', 'draft': {}}).status_code == 404
    assert budi.post(f'{path}/versions', json={'state': {'a': 1}}).status_code == 404
    assert budi.delete(path).status_code == 404
    assert ani.get(path).json()['title'] == 'Rahasia'
    assert ani.get(path).json()['versions'] == []


def test_changes_from_another_site_are_refused(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    evil = {'origin': 'https://evil.example'}
    assert client.post('/api/plans', json={'draft': {}}, headers=evil).status_code == 403
    assert client.delete('/api/account', headers=evil).status_code == 403
    assert client.post('/api/plans', json={'draft': {}}, headers={'origin': 'http://testserver'}).status_code == 200


def test_oversized_draft_is_refused(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    response = client.post('/api/plans', json={'draft': {'x': 'a' * (index.MAX_DRAFT_BYTES + 1)}})
    assert response.status_code == 413


def test_delete_account_removes_everything(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    plan = client.post('/api/plans', json={'draft': {}}).json()
    client.post(f'/api/plans/{plan["id"]}/versions', json={'state': {}})
    user_id = client.get('/api/auth/me').json()['user']['id']

    assert client.delete('/api/account').status_code == 204
    assert client.get('/api/auth/me').json()['user'] is None
    store = db.store()
    assert store.get_user(user_id) is None
    assert store._run('SELECT COUNT(*) AS c FROM plans', (), 'one')['c'] == 0
    assert store._run('SELECT COUNT(*) AS c FROM prd_versions', (), 'one')['c'] == 0


def test_logout_clears_the_cookie(monkeypatch):
    client = TestClient(index.app)
    sign_in(client, monkeypatch)
    assert client.post('/api/auth/logout').status_code == 204
    assert client.get('/api/auth/me').json()['user'] is None


# ── The store on its own, on SQLite and (when available) PostgreSQL ──────────

@pytest.fixture(params=['sqlite', 'postgres'])
def store(request, tmp_path):
    if request.param == 'sqlite':
        return db.Store(url='', sqlite_path=str(tmp_path / 'store.db'))
    if not os.environ.get('TEST_POSTGRES_URL'):
        pytest.skip('TEST_POSTGRES_URL is not set')
    pg = db.Store(url=os.environ['TEST_POSTGRES_URL'])
    pg.setup()
    for table in ('prd_versions', 'plans', 'users'):
        pg._run(f'DELETE FROM {table}')
    return pg


def test_store_upsert_keeps_one_user_per_google_account(store):
    first = store.upsert_user('g-1', 'a@example.com', 'A', '')
    again = store.upsert_user('g-1', 'a2@example.com', 'A2', 'pic')
    assert first['id'] == again['id']
    assert store.get_user(first['id'])['email'] == 'a2@example.com'


def test_store_versions_are_numbered_and_capped(store, monkeypatch):
    monkeypatch.setattr(db, 'MAX_VERSIONS', 3)
    user = store.upsert_user('g-1', 'a@example.com', 'A', '')
    plan = store.create_plan(user['id'], 'P', 'start', {'k': [1, 2]})
    numbers = [store.add_version(user['id'], plan['id'], {'i': i})['n'] for i in range(5)]
    assert numbers == [1, 2, 3, 4, 5]
    kept = store.get_plan(user['id'], plan['id'])['versions']
    assert [(v['n'], v['state']) for v in kept] == [(3, {'i': 2}), (4, {'i': 3}), (5, {'i': 4})]
    assert store.list_plans(user['id'])[0]['versions'] == 3
    assert store.add_version('someone-else', plan['id'], {}) is None


def test_store_delete_user_cascades(store):
    user = store.upsert_user('g-1', 'a@example.com', 'A', '')
    other = store.upsert_user('g-2', 'b@example.com', 'B', '')
    mine = store.create_plan(user['id'], 'P', 'start', {})
    theirs = store.create_plan(other['id'], 'Q', 'start', {})
    store.add_version(user['id'], mine['id'], {})
    store.add_version(other['id'], theirs['id'], {})
    store.delete_user(user['id'])
    assert store.get_user(user['id']) is None
    assert store.get_plan(other['id'], theirs['id'])['versions'][0]['n'] == 1
