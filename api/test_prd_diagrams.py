# backend/test_prd_diagrams.py
"""The diagram bundle of a PRD, with a fake model."""

import threading
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient  # type: ignore

import chat
import prd
import prd_diagrams
from index import app  # type: ignore
from prd_instruction import IDEA_EXAMPLE, PLAN_EXAMPLE  # type: ignore
from test_prd import INPUT  # type: ignore

SEQUENCE = '''=== Pencatatan Donasi
actor Donatur
boundary Sistem
entity donasi
Donatur -> Sistem : Mengisi form donasi
Sistem -> donasi : Simpan donasi
donasi --> Sistem : Donasi tersimpan
Sistem --> Donatur : Menampilkan pesan sukses

=== Verifikasi Donasi
actor Admin
boundary Sistem
Admin -> Sistem : Buka daftar donasi
Sistem --> Admin : Menampilkan daftar
'''
ACTIVITY = '''=== Pencatatan Donasi
|Donatur|
start
:Mengisi form donasi;
|Sistem|
:Menyimpan donasi;
stop

=== Verifikasi Donasi
|Admin|
start
:Memeriksa bukti transfer;
stop
'''


@pytest.fixture(autouse=True)
def fresh_limits():
    chat._hits.clear()


def fake_model(monkeypatch, replies):
    """replies: {'sequence': [...], 'activity': [...]}, picked by the system instruction of each call."""
    seen, lock = [], threading.Lock()

    def model(messages, prefix='AI'):
        kind = 'sequence' if 'SEQUENCE DIAGRAM' in messages[0]['content'] else 'activity'
        with lock:
            seen.append((kind, messages, prefix))
            return replies[kind].pop(0)
    monkeypatch.setattr(prd, 'call_model', model)
    return seen


def bundle(monkeypatch, sequence=(SEQUENCE,), activity=(ACTIVITY,)):
    seen = fake_model(monkeypatch, {'sequence': list(sequence), 'activity': list(activity)})
    return prd_diagrams.build_diagram_bundle(INPUT, IDEA_EXAMPLE['idea'], PLAN_EXAMPLE['plan'], 'v'), seen


def test_bundle_has_every_diagram_in_one_file(monkeypatch):
    out, seen = bundle(monkeypatch)
    assert out['pages'] == ['ERD', 'Class Diagram', 'Kamus Data', 'Use Case',
                            'Sequence: Pencatatan Donasi', 'Sequence: Verifikasi Donasi',
                            'Activity: Pencatatan Donasi', 'Activity: Verifikasi Donasi']
    assert out['errors'] == [] and out['features'] == ['Pencatatan Donasi', 'Verifikasi Donasi']
    root = ET.fromstring(out['xml'])
    assert [d.get('id') for d in root.findall('diagram')] == [f'page-{i}' for i in range(1, 9)]
    assert out['file_name'] == 'donasiku_paket-diagram.drawio' and out['open_url'].startswith('https://app.diagrams.net/#R')
    assert sorted(k for k, *_ in seen) == ['activity', 'sequence']


def test_the_model_is_asked_only_for_mvp_features_with_the_prd_as_context(monkeypatch):
    _, seen = bundle(monkeypatch)
    request = next(m for k, m, _ in seen if k == 'sequence')[1]['content']
    assert '- Pencatatan Donasi: Form donasi, Unggah bukti transfer' in request
    assert 'Laporan Bulanan' not in request                          # phase 2 is not part of the MVP
    assert 'Tabel database: donatur, donasi' in request and 'POST /api/donasi' in request
    assert 'actor Donatur' in request                                # actors from the PRD's use case


def test_broken_text_gets_one_repair_and_leftovers_are_listed(monkeypatch):
    broken = SEQUENCE + 'baris ngawur\n'
    out, seen = bundle(monkeypatch, sequence=(broken, broken))
    assert [k for k, *_ in seen].count('sequence') == 2
    assert out['errors'] == [{'line': 15, 'page': 'Sequence: Verifikasi Donasi',
                              'message': out['errors'][0]['message']}]
    assert 'Sequence: Pencatatan Donasi' in out['pages']              # the good pages are still there


def test_a_failed_model_call_keeps_the_rest_of_the_bundle(monkeypatch):
    def model(messages, prefix='AI'):
        if 'SEQUENCE DIAGRAM' in messages[0]['content']:
            raise chat.ChatError('Model AI sedang sibuk.', 503)
        return ACTIVITY
    monkeypatch.setattr(prd, 'call_model', model)
    out = prd_diagrams.build_diagram_bundle(INPUT, IDEA_EXAMPLE['idea'], PLAN_EXAMPLE['plan'], 'v')
    assert 'Activity: Pencatatan Donasi' in out['pages'] and not any(p.startswith('Sequence') for p in out['pages'])
    assert out['errors'] == [{'line': 0, 'page': 'Sequence', 'message': 'Model AI sedang sibuk.'}]


def test_the_prd_model_settings_are_used(monkeypatch):
    monkeypatch.setenv('PRD_AI_MODEL', 'kr/auto')
    _, seen = bundle(monkeypatch)
    assert {p for *_, p in seen} == {'PRD_AI'}


def test_merge_renames_and_keeps_names_unique():
    one = '<mxfile><diagram id="a" name="Login"><mxGraphModel/></diagram></mxfile>'
    xml, names = prd_diagrams.merge_drawio([('Sequence', one), ('Sequence', one), ('', one)])
    assert names == ['Sequence: Login', 'Sequence: Login (2)', 'Login']


def test_mvp_features_fall_back_to_the_first_ones():
    idea = {'features': [{'name': f'F{i}', 'phase': 2} for i in range(6)]}
    assert [f['name'] for f in prd_diagrams.mvp_features(idea)] == ['F0', 'F1', 'F2']


def test_endpoint(monkeypatch):
    fake_model(monkeypatch, {'sequence': [SEQUENCE], 'activity': [ACTIVITY]})
    r = TestClient(app).post('/api/prd/diagrams', json={'input': INPUT, 'idea': IDEA_EXAMPLE['idea'], 'plan': PLAN_EXAMPLE['plan']})
    assert r.status_code == 200 and len(r.json()['pages']) == 8
    assert TestClient(app).post('/api/prd/diagrams', json={'input': INPUT}).status_code == 400
