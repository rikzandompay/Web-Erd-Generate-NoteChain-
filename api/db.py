# backend/db.py
"""
Storage for accounts and saved PRDs.

    DATABASE_URL (or POSTGRES_URL) set   → PostgreSQL, e.g. Neon added from the Vercel dashboard
    otherwise                            → SQLite file api/.local.db, for running on your own computer

Only plain SQL that both understand is used: TEXT for ids, ISO timestamps and JSON,
'?' placeholders (turned into '%s' for PostgreSQL). Every query that touches a plan
takes the owner's user id, so a plan id from a URL never opens someone else's plan.

    users         id, google_sub, email, name, picture, created_at
    plans         id, user_id, title, screen, draft (wizard state as JSON), created_at, updated_at
    prd_versions  id, plan_id, n, state (one finished PRD as JSON), created_at
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

MAX_VERSIONS = 50                    # per plan; the oldest go first
LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.local.db')

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        google_sub TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        picture TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL DEFAULT '',
        screen TEXT NOT NULL DEFAULT 'start',
        draft TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    'CREATE INDEX IF NOT EXISTS plans_user ON plans (user_id, updated_at)',
    """CREATE TABLE IF NOT EXISTS prd_versions (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
        n INTEGER NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (plan_id, n)
    )""",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def database_url() -> str:
    return (os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or '').strip()


def available() -> bool:
    """A deployed app has no writable disk for SQLite, so there it needs a real database."""
    return bool(database_url()) or not os.environ.get('VERCEL')


class Store:
    """One connection per call; fits serverless functions that start and stop often."""

    def __init__(self, url: str | None = None, sqlite_path: str | None = None):
        self.url = database_url() if url is None else url
        self.sqlite_path = sqlite_path or LOCAL_PATH
        self.postgres = self.url.startswith(('postgres://', 'postgresql://'))
        self._ready = False

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.postgres:
            import psycopg  # type: ignore
            # Neon's pooled address runs PgBouncer, which cannot keep prepared statements
            conn = psycopg.connect(self.url, connect_timeout=10, prepare_threshold=None)
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _sql(self, sql: str) -> str:
        return sql.replace('?', '%s') if self.postgres else sql

    def _run(self, sql: str, params: tuple = (), fetch: str = '') -> Any:
        self.setup()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(self._sql(sql), params)
            if fetch == 'one':
                row = cur.fetchone()
                return dict(zip([d[0] for d in cur.description], row)) if row else None
            if fetch == 'all':
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
            return cur.rowcount

    def setup(self) -> None:
        if self._ready:
            return
        with self._connect() as conn:
            cur = conn.cursor()
            for statement in SCHEMA:
                cur.execute(statement)
        self._ready = True

    # ── Users ────────────────────────────────────────────────────────────────

    def upsert_user(self, google_sub: str, email: str, name: str, picture: str) -> dict[str, Any]:
        existing = self._run('SELECT * FROM users WHERE google_sub = ?', (google_sub,), 'one')
        if existing:
            self._run('UPDATE users SET email = ?, name = ?, picture = ? WHERE id = ?',
                      (email, name, picture, existing['id']))
            return {**existing, 'email': email, 'name': name, 'picture': picture}
        user = {'id': str(uuid.uuid4()), 'google_sub': google_sub, 'email': email, 'name': name,
                'picture': picture, 'created_at': now()}
        self._run('INSERT INTO users (id, google_sub, email, name, picture, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                  tuple(user.values()))
        return user

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._run('SELECT id, email, name, picture, created_at FROM users WHERE id = ?', (user_id,), 'one')

    def delete_user(self, user_id: str) -> None:
        """The account and everything in it; done by hand so it does not depend on cascade support."""
        self._run('DELETE FROM prd_versions WHERE plan_id IN (SELECT id FROM plans WHERE user_id = ?)', (user_id,))
        self._run('DELETE FROM plans WHERE user_id = ?', (user_id,))
        self._run('DELETE FROM users WHERE id = ?', (user_id,))

    # ── Plans ────────────────────────────────────────────────────────────────

    def create_plan(self, user_id: str, title: str, screen: str, draft: dict[str, Any]) -> dict[str, Any]:
        stamp = now()
        plan = {'id': str(uuid.uuid4()), 'user_id': user_id, 'title': title, 'screen': screen,
                'draft': json.dumps(draft), 'created_at': stamp, 'updated_at': stamp}
        self._run('INSERT INTO plans (id, user_id, title, screen, draft, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  tuple(plan.values()))
        return self._plan_out(plan)

    def update_plan(self, user_id: str, plan_id: str, title: str, screen: str, draft: dict[str, Any]) -> bool:
        return self._run('UPDATE plans SET title = ?, screen = ?, draft = ?, updated_at = ? WHERE id = ? AND user_id = ?',
                         (title, screen, json.dumps(draft), now(), plan_id, user_id)) > 0

    def list_plans(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._run(
            """SELECT p.id, p.title, p.screen, p.created_at, p.updated_at,
                      (SELECT COUNT(*) FROM prd_versions v WHERE v.plan_id = p.id) AS versions
               FROM plans p WHERE p.user_id = ? ORDER BY p.updated_at DESC""", (user_id,), 'all')
        return [{**r, 'versions': int(r['versions'])} for r in rows]

    def get_plan(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        row = self._run('SELECT * FROM plans WHERE id = ? AND user_id = ?', (plan_id, user_id), 'one')
        if not row:
            return None
        versions = self._run('SELECT n, state, created_at FROM prd_versions WHERE plan_id = ? ORDER BY n',
                             (plan_id,), 'all')
        plan = self._plan_out(row)
        plan['versions'] = [{'n': v['n'], 'at': v['created_at'], 'state': json.loads(v['state'])} for v in versions]
        return plan

    def delete_plan(self, user_id: str, plan_id: str) -> bool:
        if not self._run('SELECT id FROM plans WHERE id = ? AND user_id = ?', (plan_id, user_id), 'one'):
            return False
        self._run('DELETE FROM prd_versions WHERE plan_id = ?', (plan_id,))
        return self._run('DELETE FROM plans WHERE id = ? AND user_id = ?', (plan_id, user_id)) > 0

    def add_version(self, user_id: str, plan_id: str, state: dict[str, Any]) -> dict[str, Any] | None:
        """A new version, numbered after the last one; never overwrites an older version."""
        if not self._run('SELECT id FROM plans WHERE id = ? AND user_id = ?', (plan_id, user_id), 'one'):
            return None
        last = self._run('SELECT MAX(n) AS n FROM prd_versions WHERE plan_id = ?', (plan_id,), 'one')
        version = {'id': str(uuid.uuid4()), 'plan_id': plan_id, 'n': int(last['n'] or 0) + 1,
                   'state': json.dumps(state), 'created_at': now()}
        self._run('INSERT INTO prd_versions (id, plan_id, n, state, created_at) VALUES (?, ?, ?, ?, ?)',
                  tuple(version.values()))
        self._run('DELETE FROM prd_versions WHERE plan_id = ? AND n <= ?', (plan_id, version['n'] - MAX_VERSIONS))
        self._run('UPDATE plans SET updated_at = ? WHERE id = ?', (version['created_at'], plan_id))
        return {'n': version['n'], 'at': version['created_at'], 'state': state}

    @staticmethod
    def _plan_out(row: dict[str, Any]) -> dict[str, Any]:
        return {'id': row['id'], 'title': row['title'], 'screen': row['screen'], 'draft': json.loads(row['draft']),
                'created_at': row['created_at'], 'updated_at': row['updated_at']}


_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
