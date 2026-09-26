"""Shared pytest fixtures: every test gets its own throwaway SQLite file, so tests never
touch backend/data/expert_workflows.db and the LLM slots stay unconfigured (rule-based
paths) unless a test patches them explicitly."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
