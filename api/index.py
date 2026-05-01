# backend/main.py
"""
FastAPI application — POST /api/generate endpoint
Accepts .sql file upload, returns .drawio XML for download.
"""

from fastapi import FastAPI, File, HTTPException, UploadFile  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import Response  # type: ignore

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sql_parser import parse_sql  # type: ignore
from generator import generate_drawio_xml  # type: ignore

app = FastAPI(title='SQL to ERD Generator')

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.post('/api/generate')
async def generate_erd(file: UploadFile = File(...)):
    """Accept a .sql file upload, parse it, and return a .drawio ERD file."""

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
        schema = parse_sql(sql_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
