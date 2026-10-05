import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PolicyDocument, PolicyDocumentVersion
from app.db.session import database_url, get_engine
from app.services import policy_collector as collector
from app.services.content_store import get_content, initialize_storage, read_seed
from app.services.policy_sources import SOURCES


def rss(title="주택 공급계획", description="", link="https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95000000"):
    # Test-only fixtures. These values never enter delivered content or the normal DB.
    return f'<rss><channel><item><title>{title}</title><link>{link}</link><description><![CDATA[{description}]]></description><pubDate>Mon, 05 Oct 2026 10:11:14 +0900</pubDate></item></channel></rss>'.encode()


def test_rss_scrubs_markup_and_preserves_korean_time():
    rows = collector.parse_rss(rss(description='<p>주택 공급</p><script>bad()</script><iframe src="x"></iframe>'), SOURCES[0])
    assert rows[0]["summary"] == "주택 공급"
    assert rows[0]["published_at"] == "2026-10-05T10:11:14+09:00"
    assert "주택" in rows[0]["matched_keywords"]
    assert collector.parse_date("THU, 01 OCT 2026 15:44:12 KST") == "2026-10-01T15:44:12+09:00"
    assert collector.parse_rss(rss(title="항공 안전 점검"), SOURCES[0]) == []
    assert collector.classify("지방자치인재개발원 교육 안내") == (None, [])


def test_rss_empty_iframe_is_not_invented_summary():
    assert collector.parse_rss(rss(description='<iframe src="https://example.org"></iframe>'), SOURCES[0])[0]["summary"] == ""


def test_html_parser_and_changed_markup():
    body = '<ul><li><div class="subject"><a href="/no010101/123?curPage=2">가계대출 관리</a></div><div class="day">2026-09-30</div></li></ul>'.encode()
    rows = collector.parse_fsc_html(body, SOURCES[2])
    assert rows[0]["source_url"] == "https://www.fsc.go.kr/no010101/123"
    assert rows[0]["summary"] == ""
    with pytest.raises(ValueError):
        collector.parse_fsc_html(b"<html>maintenance</html>", SOURCES[2])


def test_rejects_nonofficial_links_and_xml_entities():
    with pytest.raises(ValueError):
        collector.parse_rss(rss(link="https://evil.example/document"), SOURCES[0])
    with pytest.raises(Exception):
        collector.parse_rss(b'<!DOCTYPE rss [<!ENTITY bad "expand">]><rss><channel><item><title>&bad;</title></item></channel></rss>', SOURCES[0])


def test_dedup_revisions_and_failure_retains_success(local_database):
    source = SOURCES[0]
    original = collector.parse_rss(rss(description="주택 관련 설명"), source)
    fetcher = lambda _: original
    assert collector.collect_all([source], fetcher)["sources"][0]["created"] == 1
    assert collector.collect_all([source], fetcher)["sources"][0]["created"] == 0
    # Dispose/reopen represents a process restart; identity is stored in the DB.
    get_engine().dispose()
    get_engine.cache_clear()
    assert collector.collect_all([source], fetcher)["sources"][0]["changed"] == 0
    changed = collector.parse_rss(rss(description="주택 관련 설명 정정"), source)
    assert collector.collect_all([source], lambda _: changed)["sources"][0]["changed"] == 1
    before = collector.read_monitor()
    success_time = before["sources"][0]["last_success_at"]
    def fail(_):
        raise requests.Timeout("sensitive internal detail")
    assert collector.collect_all([source], fail)["status"] == "partial_failure"
    after = collector.read_monitor()
    assert len(after["items"]) == 1
    assert after["items"][0]["summary"] == "주택 관련 설명 정정"
    assert after["sources"][0]["last_success_at"] == success_time
    assert after["sources"][0]["status"] == "error"
    assert "sensitive" not in after["sources"][0]["error"]
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(PolicyDocument)) == 1
        assert session.scalar(select(func.count()).select_from(PolicyDocumentVersion)) == 2


def test_postgres_url_normalization_without_network(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://postgres.project:placeholder@db.example:5432/postgres")
    assert database_url().drivername == "postgresql+psycopg"
    assert database_url().get_backend_name() == "postgresql"


def test_seed_available_and_idempotent(local_database):
    value = read_seed("policies")
    assert value and value["policies"]
    initialize_storage()
    assert get_content("policies") == value


def test_api_read_does_not_collect_and_refresh_is_protected(local_database, monkeypatch):
    from app.main import app
    from app.routers import qualitative
    called = []
    def fake_collect():
        called.append(True)
        return {"status": "ok", "sources": []}
    monkeypatch.setattr(qualitative, "collect_all", fake_collect)
    monkeypatch.delenv("POLICY_ADMIN_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/policies").status_code == 200
        response = client.get("/policies/monitor").json()
        assert response["items"] == []
        assert response["sources"][0]["status"] == "never_collected"
        assert called == []
        assert client.post("/policies/refresh").status_code == 503
        monkeypatch.setenv("POLICY_ADMIN_TOKEN", "private-test-token")
        assert client.post("/policies/refresh").status_code == 401
        assert client.post("/policies/refresh", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert client.post("/policies/refresh", headers={"X-Admin-Token": "private-test-token"}).status_code == 200
        assert called == [True]
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/indicators").status_code == 200


def test_database_failure_uses_reviewed_files_without_secrets(local_database, monkeypatch):
    from app.main import app
    from app.routers import qualitative
    def fail(*args, **kwargs):
        raise RuntimeError("postgres://username:secret@private-host/db")
    with TestClient(app) as client:
        monkeypatch.setattr(qualitative, "get_content", fail)
        monkeypatch.setattr(qualitative, "read_monitor", fail)
        response = client.get("/policies")
        assert response.status_code == 200
        assert response.json()["storage"]["available"] is False
        assert "secret" not in response.text
        response = client.get("/policies/monitor")
        assert response.json()["storage"]["available"] is False
        assert "secret" not in response.text
