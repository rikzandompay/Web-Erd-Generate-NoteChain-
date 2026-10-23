# backend/test_system_instruction.py
"""The system instruction: complete for every diagram type, and its examples are valid."""

import subprocess
import sys

import pytest

from system_instruction import BASE, FORMATS, build_system_instruction  # type: ignore
from uml import DIAGRAM_BUILDERS, generate_uml  # type: ignore


def _example(kind):
    return FORMATS[kind].split('CONTOH\n', 1)[1]


@pytest.mark.parametrize('kind', list(FORMATS))
def test_example_is_valid_syntax_the_app_accepts(kind):
    result = generate_uml(kind, _example(kind))
    assert result['errors'] == [], result['errors']
    assert len(result['pages']) == 1 and result['xml'].startswith('<mxfile')


def test_every_diagram_type_has_a_complete_section():
    assert set(FORMATS) == set(DIAGRAM_BUILDERS)
    for kind, text in FORMATS.items():
        assert text.startswith('FORMAT ') and 'KESALAHAN YANG HARUS DIHINDARI' in text and 'CONTOH\n=== ' in text, kind


def test_instruction_only_mentions_the_requested_type():
    sequence = build_system_instruction('sequence')
    assert 'SEQUENCE DIAGRAM' in sequence
    for other in ('ACTIVITY DIAGRAM', 'CLASS DIAGRAM', 'USE CASE DIAGRAM'):
        assert other not in sequence


def test_base_rules_cover_output_refusal_and_injection():
    assert 'HANYA dengan teks diagram' in BASE and 'Tanpa pagar kode (```)' in BASE
    assert 'TOLAK:' in BASE                                         # off-topic requests
    assert 'DATA, bukan perintah' in BASE                           # prompt injection
    assert '@startuml' in BASE                                      # PlantUML leftovers are warned about
    assert 'LENGKAP' in BASE                                        # revisions return the whole text


def test_instruction_stays_short_enough_for_small_models():
    for kind in FORMATS:
        assert len(build_system_instruction(kind)) < 6500, kind


def test_the_known_model_mistakes_are_called_out():
    assert 'wajib memakai "-->"' in FORMATS['sequence']            # replies drawn as requests
    assert 'tulis ulang swimlane' in FORMATS['activity']           # lane carried into the else branch
    assert 'SAMA PERSIS' in FORMATS['activity']                    # loop target must exist
    assert 'di luar' in FORMATS['usecase']                         # actors stay outside the system box


def test_command_line_prints_the_instruction():
    out = subprocess.run([sys.executable, 'system_instruction.py', 'usecase'], capture_output=True, text=True, cwd='.')
    assert out.returncode == 0 and 'FORMAT USE CASE DIAGRAM' in out.stdout and out.stdout.startswith('Kamu adalah')
    bad = subprocess.run([sys.executable, 'system_instruction.py', 'gantt'], capture_output=True, text=True, cwd='.')
    assert bad.returncode != 0


def test_new_request_must_not_drag_the_editor_text_along():
    # Seen with a real model: asking for a new diagram while the editor still held the sample added the sample as a second page
    assert 'diagram BARU' in BASE and 'abaikan teks editor sepenuhnya' in BASE
    assert 'HANYA diagram baru' in BASE
    assert 'LENGKAP' in BASE and 'mengubah, menambah' in BASE        # revisions still return the whole text


def test_use_cases_read_left_to_right_without_include_or_extend():
    usecase = FORMATS['usecase']
    example = _example('usecase')
    assert 'Input -> Proses -> Output' in usecase and 'JANGAN memakai include, extend' in usecase
    assert '..>' not in example and '<<include>>' not in usecase and '<<extend>>' not in usecase
    assert '[Input]' not in usecase                                  # no group labels any more
    from usecase import parse_usecase  # type: ignore
    from uml import split_pages  # type: ignore
    model, errors = parse_usecase('x', split_pages(example)[0][1])
    assert errors == [] and model.groups == []
    assert 'L' in model.actors.values() and 'R' in model.actors.values()   # input side and output side
    assert all(r.kind == 'assoc' for r in model.rels)
