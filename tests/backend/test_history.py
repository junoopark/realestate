import copy
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot
from app.db.session import get_engine
from app.services import content_store


@pytest.fixture
def history_seed(monkeypatch):
    # Test-only content; never written to deployed JSON or the normal database.
    content = {
        "verified_at": "2026-10-05",
        "period_start": "2016-10-05",
        "period_end": "2026-10-05",
        "coverage_note": "테스트 전용 검토본",
        "eras": [{"id": "e1", "label": "테스트 구간", "period": "2016~2017", "from": "2016-10-05", "to": "2017-12-31", "title": "구간 제목", "summary": "구간 설명", "shift": "변화 설명", "focus": ["테스트 항목"]}],
        "events": [{"id": "test-event", "date": "2017-08-02", "title": "테스트 제목", "short_title": "테스트", "agency": "테스트 기관", "era": "e1", "topics": ["finance"], "directions": ["tighten"], "summary": "검토 요약", "change": "달라진 점", "context": "발표 맥락", "highlights": ["확인할 내용"], "timing_note": "시점 설명", "reading_note": "해석 범위", "sources": [{"title": "테스트 출처", "organization": "테스트 기관", "url": "https://example.org/test-only"}], "verified_at": "2026-10-05"}],
    }
    original = content_store.read_seed
    monkeypatch.setattr(content_store, "read_seed", lambda key: copy.deepcopy(content) if key == "policy-history" else original(key))
    return content


def test_history_startup_persists_and_updates_reviewed_snapshot(history_seed, local_database):
    with Session(get_engine()) as session:
        original = session.get(ContentSnapshot, "policy-history")
        assert original.content == history_seed
        first_updated = original.updated_at
        first_hash = original.content_hash
    content_store.initialize_storage()
    with Session(get_engine()) as session:
        unchanged = session.get(ContentSnapshot, "policy-history")
        assert unchanged.content_hash == first_hash
        assert unchanged.updated_at == first_updated
    history_seed["coverage_note"] = "수정된 테스트 검토본"
    content_store.initialize_storage()
    with Session(get_engine()) as session:
        changed = session.get(ContentSnapshot, "policy-history")
        assert changed.content_hash != first_hash
        assert changed.content == history_seed


def test_history_api_reads_without_collecting_or_writing(history_seed, local_database, monkeypatch):
    from app.main import app
    from app.routers import qualitative

    def unexpected_collect():
        pytest.fail("History GET must not collect external data")

    monkeypatch.setattr(qualitative, "collect_all", unexpected_collect)
    statements = []

    def record_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())

    with TestClient(app) as client:
        engine = get_engine()
        sql_event.listen(engine, "before_cursor_execute", record_sql)
        try:
            response = client.get("/policies/history")
        finally:
            sql_event.remove(engine, "before_cursor_execute", record_sql)
    assert response.status_code == 200
    body = response.json()
    assert body["events"] == history_seed["events"]
    assert body["storage"]["available"] is True
    assert body["storage"]["type"] == "sqlite"
    assert body["sync"]["mode"] == "reviewed_snapshot"
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for statement in statements)


def test_history_api_database_failure_uses_seed_without_secrets(history_seed, local_database, monkeypatch):
    from app.main import app
    from app.routers import qualitative

    def unavailable(*args):
        raise RuntimeError("postgres://private-user:secret@private-host/db")

    with TestClient(app) as client:
        monkeypatch.setattr(qualitative, "get_content", unavailable)
        monkeypatch.setattr(qualitative, "read_seed", lambda key: history_seed if key == "policy-history" else None)
        response = client.get("/policies/history")
    assert response.status_code == 200
    assert response.json()["events"] == history_seed["events"]
    assert response.json()["storage"]["available"] is False
    assert "secret" not in response.text


def test_history_api_missing_content_is_unavailable(local_database, monkeypatch):
    from app.main import app
    from app.routers import qualitative

    with TestClient(app) as client:
        monkeypatch.setattr(qualitative, "get_content", lambda key: None)
        response = client.get("/policies/history")
    assert response.status_code == 503


@pytest.mark.parametrize("field,value,expected", [
    ("date", "2017-02-29", "실제로 존재하는"),
    ("date", "2016-10-04", "표시 기간 밖"),
    ("era", "missing", "eras.id"),
    ("topics", ["unknown"], "허용 값"),
])
def test_history_validator_rejects_bad_event(history_seed, field, value, expected):
    validate = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "check_history_data.py"))["validate_history"]
    assert validate(history_seed) == []
    history_seed["events"][0][field] = value
    assert any(expected in error for error in validate(history_seed))
