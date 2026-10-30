"""Tests must not depend on the developer's own .env, which chat.py loads when it is imported."""

import pytest


@pytest.fixture(autouse=True)
def no_model_per_skill(monkeypatch):
    for level in ('PEMULA', 'MENENGAH', 'PRO'):
        monkeypatch.delenv(f'PRD_AI_MODEL_{level}', raising=False)
