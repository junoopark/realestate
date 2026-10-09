from fastapi.testclient import TestClient

from app.check_db import check_url, main
from app.main import app


def test_check_url_flags_supabase_mistakes(monkeypatch):
    cases = {
        "postgresql://postgres:pw123@db.abcd.supabase.co:5432/postgres": "Direct connection",
        "postgresql+psycopg://postgres.abcd:pw123@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres": "6543",
        "postgresql+psycopg://postgres:pw123@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres": "postgres.<프로젝트ref>",
        "postgresql+psycopg://postgres.abcd:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres": "자리표시자",
    }
    for url, expected in cases.items():
        monkeypatch.setenv("DATABASE_URL", url)
        masked, problems = check_url()
        assert "pw123" not in masked
        assert any(expected in p for p in problems), (url, problems)


def test_check_url_accepts_session_pooler(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres.abcd:Secret2026Pw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres")
    masked, problems = check_url()
    assert problems == []
    assert masked.startswith("postgresql+psycopg://postgres.abcd:***@")


def test_check_db_cli_initializes_sqlite(tmp_path, monkeypatch, capsys):
    from app.db.session import get_engine

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'check.db').as_posix()}")
    get_engine.cache_clear()
    try:
        assert main(["--init"]) == 0
    finally:
        get_engine.cache_clear()
    out = capsys.readouterr().out
    assert "연결 성공: sqlite" in out
    assert "content_snapshots" in out


def test_health_db_hides_connection_details(local_database):
    response = TestClient(app).get("/health/db")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "sqlite" and body["available"] is True
    assert "DATABASE_URL" not in response.text and "sqlite:///" not in response.text
