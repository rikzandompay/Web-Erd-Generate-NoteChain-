# backend/test_prd_consistency.py
"""The plan and the tasks must agree with the idea: actors, use cases, data, endpoints."""

import copy
import json

import pytest

import chat
import prd
from prd_consistency import endpoint_key, plan_consistency, tasks_consistency, traceability  # type: ignore
from prd_instruction import IDEA_EXAMPLE, PLAN_EXAMPLE, TASKS_EXAMPLE  # type: ignore
from test_prd import INPUT, fake_model  # type: ignore


@pytest.fixture(autouse=True)
def fresh_limits():
    chat._hits.clear()


def idea():
    return prd.normalize_idea(copy.deepcopy(IDEA_EXAMPLE))


def plan():
    return prd.normalize_plan(copy.deepcopy(PLAN_EXAMPLE))


def test_the_examples_agree():
    assert plan_consistency(idea(), plan()) == []


def test_actors_must_be_the_target_users():
    p = plan()
    p['usecase_text'] = p['usecase_text'].replace('actor Bank <<sekunder>>', 'actor Pemilik <<sekunder>>').replace('Bank -->', 'Pemilik -->')
    problems = plan_consistency(idea(), p)
    assert 'Aktor "Pemilik" tidak ada di target pengguna (Donatur, Admin, Bank).' in problems
    assert 'Target pengguna "Bank" belum menjadi aktor di use case.' in problems


def test_use_cases_and_mvp_features_must_match():
    p = plan()
    p['usecase_text'] = p['usecase_text'].replace('  (Verifikasi Donasi)\n', '  (Verifikasi Donasi)\n  (Buka Dashboard)\n') + '\nAdmin --> (Buka Dashboard)'
    p['usecase_features'] = [{'usecase': 'Input Donasi', 'feature': 'Pencatatan Donasi'},
                             {'usecase': 'Verifikasi Donasi', 'feature': 'Laporan Bulanan'}]
    problems = plan_consistency(idea(), p)
    assert 'Use case "Buka Dashboard" belum dikaitkan ke fitur di usecase_features.' in problems
    assert 'Use case "Verifikasi Donasi" dikaitkan ke "Laporan Bulanan", yang bukan fitur Fase 1.' in problems
    assert 'Fitur Fase 1 "Verifikasi Donasi" belum punya use case.' in problems


def test_every_mvp_sub_feature_needs_existing_tables_and_endpoint():
    p = plan()
    p['coverage'] = [c for c in p['coverage'] if c['sub_feature'] != 'Catatan verifikasi']
    p['coverage'][0] = {'sub_feature': 'Form donasi', 'tables': ['donasi', 'pembayaran'], 'endpoint': 'POST /api/bayar'}
    problems = plan_consistency(idea(), p)
    assert 'Sub-fitur "Catatan verifikasi" (Verifikasi Donasi) belum dipetakan ke tabel dan endpoint di coverage.' in problems
    assert 'Sub-fitur "Form donasi" memakai tabel "pembayaran" yang tidak ada di skema SQL.' in problems
    assert 'Sub-fitur "Form donasi" memakai endpoint "POST /api/bayar" yang tidak ada di API.' in problems


def test_names_compare_without_case_spaces_or_parameter_style():
    p = plan()
    p['coverage'][3]['endpoint'] = 'patch /api/donasi/:donasi_id/verifikasi/'
    p['usecase_features'][0]['feature'] = 'pencatatan  donasi'
    assert plan_consistency(idea(), p) == []
    assert endpoint_key('GET /api/a/{id}') == endpoint_key('get /api/a/:id/')


def test_every_endpoint_must_be_built_by_a_task():
    tasks = prd.order_tasks(TASKS_EXAMPLE['tasks'])[0]
    assert tasks_consistency(plan(), tasks) == []
    tasks[2]['description'] = 'Halaman daftar donasi.'
    assert tasks_consistency(plan(), tasks) == ['Endpoint "GET /api/donasi" belum dikerjakan di task mana pun.',
                                                'Endpoint "PATCH /api/donasi/{id}/verifikasi" belum dikerjakan di task mana pun.']
    tasks[2]['description'] = 'PATCH /api/donasi/12/verifikasi dan GET /api/donasi'          # a value in place of {id}
    assert tasks_consistency(plan(), tasks) == []


def test_traceability_rows():
    rows = traceability(idea(), plan())
    assert len(rows) == 6 and rows[3] == {'feature': 'Verifikasi Donasi', 'sub_feature': 'Terima atau tolak donasi',
                                          'usecases': ['Verifikasi Donasi'], 'tables': ['donasi'],
                                          'endpoint': 'PATCH /api/donasi/{id}/verifikasi'}


def test_plan_stage_repairs_an_out_of_sync_plan(monkeypatch):
    broken = copy.deepcopy(PLAN_EXAMPLE)
    broken['plan']['coverage'] = broken['plan']['coverage'][:2]
    seen = fake_model(monkeypatch, broken, PLAN_EXAMPLE)
    out = prd.prd_plan(INPUT, IDEA_EXAMPLE['idea'], 'v')
    assert len(seen) == 2 and 'Tidak sinkron dengan tahap Ide: Sub-fitur "Daftar donasi masuk"' in seen[1][-1]['content']
    assert out['checks']['consistency'] == []


def test_leftover_problems_are_reported_not_hidden(monkeypatch):
    broken = copy.deepcopy(PLAN_EXAMPLE)
    broken['plan']['usecase_features'] = []
    fake_model(monkeypatch, broken, broken)
    out = prd.prd_plan(INPUT, IDEA_EXAMPLE['idea'], 'v')
    assert 'Fitur Fase 1 "Pencatatan Donasi" belum punya use case.' in out['checks']['consistency']


def test_tasks_stage_reports_unbuilt_endpoints(monkeypatch):
    lazy = {'tasks': TASKS_EXAMPLE['tasks'][:2]}
    fake_model(monkeypatch, lazy, lazy)
    out = prd.prd_tasks(INPUT, IDEA_EXAMPLE['idea'], PLAN_EXAMPLE['plan'], 'v')
    assert 'Endpoint "GET /api/donasi" belum dikerjakan di task mana pun.' in out['problems']


def test_presensiku_prd_problems_are_caught():
    """The PRD from the screenshot: Pemilik not a target user, Admin not an actor, a use case outside the features."""
    presensi_idea = {'idea': {
        'product_name': 'PresensiKu', 'problem_statement': 'x', 'solution': 'y', 'target_users': ['HRD', 'Admin', 'Karyawan'],
        'features': [{'name': 'Absensi Vermuk', 'phase': 1, 'sub_features': ['Pindai kode QR']},
                     {'name': 'Pengajuan Cuti', 'phase': 1, 'sub_features': ['Setujui atau tolak']}]}}
    presensi_plan = {'plan': {
        'ddl': 'CREATE TABLE karyawan (id SERIAL PRIMARY KEY); CREATE TABLE absensi (id SERIAL PRIMARY KEY, karyawan_id INT REFERENCES karyawan(id));',
        'usecase_text': ('=== P\nsystem P {\n  (Buka Dashboard Utama)\n  (Absensi Vermuk)\n  (Pengajuan Cuti)\n}\n'
                         'actor HRD\nactor Karyawan\nactor Pemilik <<sekunder>>\nHRD --> (Buka Dashboard Utama)\n'
                         'Karyawan --> (Absensi Vermuk)\nKaryawan --> (Pengajuan Cuti)\nPemilik --> (Buka Dashboard Utama)'),
        'api': [{'method': 'POST', 'path': '/api/absensi'}]}}
    problems = plan_consistency(prd.normalize_idea(presensi_idea), prd.normalize_plan(presensi_plan))
    assert 'Aktor "Pemilik" tidak ada di target pengguna (HRD, Admin, Karyawan).' in problems
    assert 'Target pengguna "Admin" belum menjadi aktor di use case.' in problems
    assert 'Use case "Buka Dashboard Utama" belum dikaitkan ke fitur di usecase_features.' in problems
    assert 'Sub-fitur "Setujui atau tolak" (Pengajuan Cuti) belum dipetakan ke tabel dan endpoint di coverage.' in problems
