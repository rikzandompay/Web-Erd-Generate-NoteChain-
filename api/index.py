# backend/main.py
"""
FastAPI application
  • POST /api/generate — .sql file upload → .drawio (ERD, class diagram, data dictionary) download
  • POST /api/dictionary — .sql file upload → the data dictionary as Markdown and CSV
  • POST /api/code     — .sql file upload → starter code (Laravel, Prisma, SQLAlchemy), as JSON or a .zip
  • POST /api/uml      — UML text (sequence, …) → JSON with the .drawio XML, pages and line errors
  • POST /api/chat     — a plain-language request → UML text from an AI model, built into a diagram
  • POST /api/prd/...  — idea → plan → tasks: a PRD in three AI stages, plus its Markdown (see prd.py)
  • POST /api/prd/diagrams — every diagram of a PRD in one .drawio (see prd_diagrams.py)
  • /api/auth/...      — sign in with Google, who is signed in, sign out (see auth.py)
  • /api/plans/...     — the signed-in user's saved PRDs and every version of them (see db.py)
"""

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import RedirectResponse, Response  # type: ignore
from pydantic import BaseModel  # type: ignore

import io
import os
import sys
import json
import zipfile
from datetime import date
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(__file__))

from sql_parser import parse_sql  # type: ignore
from generator import generate_drawio_xml  # type: ignore
from chat import ChatError, chat_generate  # type: ignore
from data_dictionary import to_csv as dictionary_csv, to_markdown as dictionary_markdown  # type: ignore
from uml import DIAGRAM_BUILDERS, generate_uml  # type: ignore
from fixer import fix_text  # type: ignore
from codegen import TARGETS as CODE_TARGETS, generate_code  # type: ignore
from prd_diagrams import build_diagram_bundle  # type: ignore
from prd import prd_idea, prd_plan, prd_questions, prd_tasks, render_prd_markdown, slug  # type: ignore
import auth  # type: ignore
import db  # type: ignore

app = FastAPI(title='SQL to ERD Generator')

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


async def read_schema(file: UploadFile) -> dict:
    """Validate an uploaded .sql file and parse it; raises HTTP 400 with a readable reason."""

    # ── Validate file extension ──────────────────────────────────────
    if not file.filename or not file.filename.lower().endswith('.sql'):
        raise HTTPException(
            status_code=400,
            detail='Invalid file type. Please upload a .sql file.',
        )

    # ── Read and decode contents ─────────────────────────────────────
    contents = await file.read()
    try:
        sql_text = contents.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail='Unable to read file. Ensure it is a valid UTF-8 text file.',
        )

    if not sql_text.strip():
        raise HTTPException(
            status_code=400,
            detail='The uploaded SQL file is empty.',
        )

    # ── Parse SQL ────────────────────────────────────────────────────
    try:
        return parse_sql(sql_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/generate')
async def generate_erd(file: UploadFile = File(...)):
    """Accept a .sql file upload, parse it, and return a .drawio file (ERD, class diagram, data dictionary)."""
    schema = await read_schema(file)

    # ── Generate Draw.io XML ─────────────────────────────────────────
    xml_content = generate_drawio_xml(schema)

    # Build output filename from upload name
    base_name = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename
    output_filename = f'{base_name}_erd.drawio'

    return Response(
        content=xml_content,
        media_type='application/xml',
        headers={
            'Content-Disposition': f'attachment; filename="{output_filename}"',
        },
    )


@app.post('/api/dictionary')
async def data_dictionary(file: UploadFile = File(...)):
    """The data dictionary of a .sql upload as Markdown and CSV, ready to paste into a report."""
    schema = await read_schema(file)
    return {
        'markdown': dictionary_markdown(schema),
        'csv': dictionary_csv(schema),
        'tables': len(schema['tables']),
    }


async def code_files(file: UploadFile, target: str, database: str) -> tuple[list[dict], str]:
    if target not in CODE_TARGETS:
        raise HTTPException(status_code=400, detail=f'Target "{target}" belum didukung. Pilih: {", ".join(CODE_TARGETS)}.')
    schema = await read_schema(file)
    base = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename
    return generate_code(schema, target, file.filename, database, date.today()), base


@app.post('/api/code')
async def starter_code(file: UploadFile = File(...), target: str = Form(...), database: str = Form('postgresql')):
    """Starter code from a .sql file, as a list of files to preview."""
    files, base = await code_files(file, target, database)
    return {'files': files, 'zip_name': f'{base}-{target}.zip'}


@app.post('/api/code/zip')
async def starter_code_zip(file: UploadFile = File(...), target: str = Form(...), database: str = Form('postgresql')):
    """The same files in one .zip, keeping their folders."""
    files, base = await code_files(file, target, database)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for f in files:
            archive.writestr(f['path'], f['content'])
    return Response(content=buffer.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="{base}-{target}.zip"'})


class UmlRequest(BaseModel):
    type: str
    text: str


@app.post('/api/uml')
async def generate_uml_diagram(request: UmlRequest):
    """Turn UML text (one diagram per `=== Name` block) into a multi-page .drawio file."""
    if request.type not in DIAGRAM_BUILDERS:
        raise HTTPException(
            status_code=400,
            detail=f'Jenis diagram "{request.type}" belum didukung.',
        )
    if not request.text.strip():
        raise HTTPException(status_code=400, detail='Teks diagram masih kosong.')

    return generate_uml(request.type, request.text)


class FixRequest(BaseModel):
    type: str
    text: str
    errors: list[dict]


@app.post('/api/fix')
async def fix_uml_text(request: FixRequest):
    """Apply rule-based fixes to broken UML lines and return the corrected text."""
    if request.type not in DIAGRAM_BUILDERS:
        raise HTTPException(
            status_code=400,
            detail=f'Jenis diagram "{request.type}" belum didukung.',
        )
    if not request.text.strip():
        raise HTTPException(status_code=400, detail='Teks diagram masih kosong.')

    return fix_text(request.type, request.text, request.errors)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    type: str
    messages: list[ChatMessage]
    editor_text: str = ''


@app.post('/api/chat')
async def chat(request: Request, body: ChatRequest):
    """Turn a plain-language request into UML text with the configured AI model, then build it."""
    try:
        return chat_generate(body.type, [m.model_dump() for m in body.messages], body.editor_text, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


def visitor_of(request: Request) -> str:
    """Who is asking, for the rate limit. Behind Vercel it is the first entry of x-forwarded-for."""
    forwarded = request.headers.get('x-forwarded-for', '')
    return forwarded.split(',')[0].strip() or (request.client.host if request.client else 'unknown')


class PrdRequest(BaseModel):
    input: dict = {}
    idea: dict | None = None
    plan: dict | None = None
    tasks: list | None = None
    assumptions: list = []
    issues: list = []


@app.post('/api/prd/questions')
async def prd_questions_stage(request: Request, body: PrdRequest):
    """Before stage 1: five clarifying questions about the idea, with answer chips."""
    try:
        return prd_questions(body.input, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/prd/idea')
async def prd_idea_stage(request: Request, body: PrdRequest):
    """Stage 1: the idea as problem statement, solution, MVP scope and non-goals."""
    try:
        return prd_idea(body.input, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/prd/plan')
async def prd_plan_stage(request: Request, body: PrdRequest):
    """Stage 2: user journey, use case text, architecture, SQL DDL, API spec, AI tools."""
    try:
        return prd_plan(body.input, body.idea or {}, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/prd/tasks')
async def prd_tasks_stage(request: Request, body: PrdRequest):
    """Stage 3: atomic tasks in dependency order."""
    try:
        return prd_tasks(body.input, body.idea or {}, body.plan or {}, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/prd/diagrams')
async def prd_diagram_bundle(request: Request, body: PrdRequest):
    """ERD, class, data dictionary, use case, and a sequence and activity diagram per MVP feature."""
    try:
        return build_diagram_bundle(body.input, body.idea or {}, body.plan or {}, visitor_of(request))
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.post('/api/prd/markdown')
async def prd_markdown(body: PrdRequest):
    """The PRD as one Markdown file; no AI involved."""
    state = body.model_dump()
    name = (body.idea or {}).get('product_name', '')
    return {'markdown': render_prd_markdown(state, date.today().isoformat()), 'file_name': f'PRD-{slug(name)}.md'}


# ── Accounts and saved PRDs ──────────────────────────────────────────────────

# These talk to the database and Google without async, so they are plain `def`:
# FastAPI runs those in a thread pool instead of blocking every other request.
MAX_DRAFT_BYTES = 2_000_000          # one plan's wizard state; Vercel accepts 4.5 MB per request
SCREENS = {'start', 'questions', 'tech', 'structure', 'prd', 'tasks'}


def same_site_only(request: Request) -> None:
    """Changes may only come from pages of this app (the session cookie is also SameSite=Lax)."""
    origin = request.headers.get('origin')
    if origin and origin.split('://', 1)[-1] != request.headers.get('host', ''):
        raise HTTPException(status_code=403, detail='Permintaan dari situs lain ditolak.')


def with_login_error(path: str, message: str) -> str:
    path = auth.safe_next(path)
    return f'{path}{"&" if "?" in path else "?"}login_error={quote(message)}'


def current_user(request: Request) -> dict:
    """The signed-in user, or HTTP 401; also 503 when no database is set up."""
    if not db.available():
        raise HTTPException(status_code=503, detail='Database belum diatur di server: isi DATABASE_URL.')
    user_id = auth.session_user_id(request.cookies.get(auth.SESSION_COOKIE))
    user = db.store().get_user(user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail='Masuk dulu untuk menyimpan riwayat PRD.')
    return user


@app.get('/api/auth/google/login')
def google_login(request: Request, next: str = '/'):
    """Send the browser to Google's sign-in page."""
    base = auth.base_url(dict(request.headers), str(request.base_url))
    try:
        url, flow = auth.start_login(base, next)
    except auth.AuthError as exc:
        return RedirectResponse(with_login_error(next, str(exc)), 303)
    response = RedirectResponse(url, 303)
    response.set_cookie(auth.FLOW_COOKIE, flow, **auth.cookie_options(base, auth.FLOW_SECONDS))
    return response


@app.get('/api/auth/google/callback')
def google_callback(request: Request):
    """Google sends the browser back here; on success the session cookie is set."""
    base = auth.base_url(dict(request.headers), str(request.base_url))
    params = dict(request.query_params)
    next_path = (auth.unsign(request.cookies.get(auth.FLOW_COOKIE)) or {}).get('next', '/')
    try:
        if not db.available():
            raise auth.AuthError('Database belum diatur di server: isi DATABASE_URL.', 503)
        profile, next_path = auth.finish_login(params, request.cookies.get(auth.FLOW_COOKIE), base)
        user = db.store().upsert_user(profile['sub'], profile['email'], profile['name'], profile['picture'])
    except auth.AuthError as exc:
        response = RedirectResponse(with_login_error(next_path, str(exc)), 303)
        response.delete_cookie(auth.FLOW_COOKIE, path='/')
        return response
    response = RedirectResponse(auth.safe_next(next_path), 303)
    response.delete_cookie(auth.FLOW_COOKIE, path='/')
    response.set_cookie(auth.SESSION_COOKIE, auth.session_value(user['id']),
                        **auth.cookie_options(base, auth.SESSION_DAYS * 86400))
    return response


@app.get('/api/auth/me')
def who_am_i(request: Request):
    """The signed-in user (or null), and whether signing in is possible on this server."""
    ready = auth.configured() and db.available()
    user_id = auth.session_user_id(request.cookies.get(auth.SESSION_COOKIE))
    user = db.store().get_user(user_id) if ready and user_id else None
    return {'user': user, 'login_ready': ready}


@app.post('/api/auth/logout')
def logout(request: Request):
    same_site_only(request)
    response = Response(status_code=204)
    response.delete_cookie(auth.SESSION_COOKIE, path='/')
    return response


@app.delete('/api/account')
def delete_account(request: Request):
    """The account, its plans and every version; cannot be undone."""
    same_site_only(request)
    user = current_user(request)
    db.store().delete_user(user['id'])
    response = Response(status_code=204)
    response.delete_cookie(auth.SESSION_COOKIE, path='/')
    return response


class PlanBody(BaseModel):
    title: str = ''
    screen: str = 'start'
    draft: dict = {}


class VersionBody(BaseModel):
    state: dict


def checked_plan(body: PlanBody) -> tuple[str, str, dict]:
    if len(json.dumps(body.draft)) > MAX_DRAFT_BYTES:
        raise HTTPException(status_code=413, detail='Draf PRD terlalu besar untuk disimpan.')
    screen = body.screen if body.screen in SCREENS else 'start'
    return body.title.strip()[:200], screen, body.draft


@app.get('/api/plans')
def list_plans(request: Request):
    return {'plans': db.store().list_plans(current_user(request)['id'])}


@app.post('/api/plans')
def create_plan(request: Request, body: PlanBody):
    same_site_only(request)
    user = current_user(request)
    return db.store().create_plan(user['id'], *checked_plan(body))


@app.get('/api/plans/{plan_id}')
def get_plan(request: Request, plan_id: str):
    plan = db.store().get_plan(current_user(request)['id'], plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail='PRD tidak ditemukan.')
    return plan


@app.put('/api/plans/{plan_id}')
def update_plan(request: Request, plan_id: str, body: PlanBody):
    same_site_only(request)
    user = current_user(request)
    if not db.store().update_plan(user['id'], plan_id, *checked_plan(body)):
        raise HTTPException(status_code=404, detail='PRD tidak ditemukan.')
    return {'ok': True}


@app.delete('/api/plans/{plan_id}')
def delete_plan(request: Request, plan_id: str):
    same_site_only(request)
    if not db.store().delete_plan(current_user(request)['id'], plan_id):
        raise HTTPException(status_code=404, detail='PRD tidak ditemukan.')
    return Response(status_code=204)


@app.post('/api/plans/{plan_id}/versions')
def add_version(request: Request, plan_id: str, body: VersionBody):
    """A finished PRD as a new version; older versions stay as they are."""
    same_site_only(request)
    user = current_user(request)
    if len(json.dumps(body.state)) > MAX_DRAFT_BYTES:
        raise HTTPException(status_code=413, detail='PRD terlalu besar untuk disimpan.')
    version = db.store().add_version(user['id'], plan_id, body.state)
    if not version:
        raise HTTPException(status_code=404, detail='PRD tidak ditemukan.')
    return version
