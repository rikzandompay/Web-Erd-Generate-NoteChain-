# backend/main.py
"""
FastAPI application
  • POST /api/generate — .sql file upload → .drawio (ERD, class diagram, data dictionary) download
  • POST /api/dictionary — .sql file upload → the data dictionary as Markdown and CSV
  • POST /api/uml      — UML text (sequence, …) → JSON with the .drawio XML, pages and line errors
  • POST /api/chat     — a plain-language request → UML text from an AI model, built into a diagram
  • POST /api/prd/...  — idea → plan → tasks: a PRD in three AI stages, plus its Markdown (see prd.py)
"""

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import Response  # type: ignore
from pydantic import BaseModel  # type: ignore

import sys
import os
from datetime import date
sys.path.insert(0, os.path.dirname(__file__))

from sql_parser import parse_sql  # type: ignore
from generator import generate_drawio_xml  # type: ignore
from chat import ChatError, chat_generate  # type: ignore
from data_dictionary import to_csv as dictionary_csv, to_markdown as dictionary_markdown  # type: ignore
from uml import DIAGRAM_BUILDERS, generate_uml  # type: ignore
from fixer import fix_text  # type: ignore
from prd import prd_idea, prd_plan, prd_questions, prd_tasks, render_prd_markdown, slug  # type: ignore

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


@app.post('/api/prd/markdown')
async def prd_markdown(body: PrdRequest):
    """The PRD as one Markdown file; no AI involved."""
    state = body.model_dump()
    name = (body.idea or {}).get('product_name', '')
    return {'markdown': render_prd_markdown(state, date.today().isoformat()), 'file_name': f'PRD-{slug(name)}.md'}
