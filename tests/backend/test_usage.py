"""Anonymous views, data minimization, bounds, and consistent date-filtered aggregates."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ContentSnapshot, PolicyDocument, UsageEvent
from app.db.session import get_engine
from app.services import cache
from app.services import usage_analytics as analytics
from app.services.content_store import initialize_storage, read_seed


@pytest.fixture
def client(local_database):
    from app.main import app
    cache.clear()
    analytics._rates.clear()
    analytics._global_rate = (0, 0)
    with TestClient(app) as test_client:
        yield test_client
    cache.clear()


def payload(event="indicator_view", target="V043:nation", *, session=None, event_id=None, page="index"):
    return {"session_id": session or str(uuid4()), "events": [
        {"event_id": event_id or str(uuid4()), "event": event, "target": target, "page": page}
    ]}


def test_usage_without_activity_logs_still_supports_views(client):
    res = client.get("/usage")
    body = res.json()
    assert res.status_code == 200 and body["available"] is True
    assert body["activity_available"] is False and "activity_logs" in body["activity_reason"]
    assert body["views"]["available"] is True and body["views"]["since"]
    assert body["views"]["first_event_at"] is None
    assert body["days"] == 30 and res.headers["cache-control"] == "public, max-age=60"
    assert "user_id" not in res.text and "session_id" not in res.text


def test_record_deduplicates_retries_and_same_tab_target(client):
    batch = payload()
    first = client.post("/usage/events", json=batch)
    assert first.status_code == 200 and first.json()["accepted"] == 1
    assert first.headers["cache-control"] == "no-store"
    assert client.post("/usage/events", json=batch).json()["duplicates"] == 1
    batch["events"][0]["event_id"] = str(uuid4())
    assert client.post("/usage/events", json=batch).json()["duplicates"] == 1
    batch["session_id"] = str(uuid4())
    batch["events"][0]["event_id"] = str(uuid4())
    assert client.post("/usage/events", json=batch).json()["accepted"] == 1
    summary = client.get("/usage").json()["views"]
    assert summary["totals"]["indicator_view"] == {"events": 2, "sessions": 2}
    assert summary["indicators"][0]["views"] == 2
    assert summary["indicators"][0]["label"] != "V043:nation"
    assert summary["first_event_at"]


def test_only_known_targets_and_no_client_titles(client):
    assert client.post("/usage/events", json=payload(target="V999:nation")).json()["rejected"] == 1
    assert client.post("/usage/events", json=payload(target="V043:gu")).json()["rejected"] == 1
    invalid = payload()
    invalid["events"][0]["title"] = "arbitrary"
    assert client.post("/usage/events", json=invalid).status_code == 422
    invalid = payload()
    invalid["user_id"] = str(uuid4())
    assert client.post("/usage/events", json=invalid).status_code == 422
    invalid = payload()
    invalid["events"][0]["event"] = "login"
    assert client.post("/usage/events", json=invalid).status_code == 422


def test_policy_prefixes_merge_same_original_and_click_is_distinct(client):
    brief = read_seed("policies")["policies"][0]
    with Session(get_engine()) as session:
        session.add(PolicyDocument(
            id="existing-document", source_id="molit", source_url=brief["source_url"], title=brief["title"],
            agency=brief["agency"], published_at="2026-10-01", summary="", category="공급",
            matched_keywords=[], content_hash="hash", first_seen_at="2026-10-20",
            last_seen_at="2026-10-20", updated_at="2026-10-20", revision=1,
        ))
        session.commit()
    sid = str(uuid4())
    assert client.post("/usage/events", json=payload("policy_view", "brief:" + brief["id"], session=sid)).json()["accepted"] == 1
    assert client.post("/usage/events", json=payload("policy_view", "monitor:existing-document", session=sid)).json()["duplicates"] == 1
    assert client.post("/usage/events", json=payload("policy_open", "monitor:existing-document", session=sid)).json()["accepted"] == 1
    history = read_seed("policy-history")["events"][0]
    assert client.post("/usage/events", json=payload("policy_view", "history:" + history["id"], page="history")).json()["accepted"] == 1
    assert client.post("/usage/events", json=payload("policy_view", "brief:invented")).json()["rejected"] == 1
    policies = client.get("/usage").json()["views"]["policies"]
    row = next(p for p in policies if p["url"] == brief["source_url"])
    assert row["views"] == 1 and row["opens"] == 1 and row["sessions"] == 1
    assert len(policies) == 2


def test_policy_original_source_alias_ignores_list_controls_but_keeps_article_id(client):
    brief = read_seed("policies")["policies"][0]
    original = brief["original_source_url"]
    shifted = original.replace("lcmspage=1", "lcmspage=99") + "&kw=주택&src=rss&curPage=4&utm_source=rss"
    other_article = shifted.replace("id=95092476", "id=95092477")
    with Session(get_engine()) as session:
        for key, url in (("same-release", shifted), ("different-release", other_article)):
            session.add(PolicyDocument(
                id=key, source_id="molit", source_url=url, title=brief["title"], agency=brief["agency"],
                published_at="2026-10-01", summary="", category="공급", matched_keywords=[],
                content_hash="hash", first_seen_at="2026-10-20", last_seen_at="2026-10-20",
                updated_at="2026-10-20", revision=1,
            ))
        session.commit()
    sid = str(uuid4())
    assert client.post("/usage/events", json=payload("policy_view", "brief:" + brief["id"], session=sid)).json()["accepted"] == 1
    assert client.post("/usage/events", json=payload("policy_view", "monitor:same-release", session=sid)).json()["duplicates"] == 1
    assert client.post("/usage/events", json=payload("policy_view", "monitor:different-release", session=sid)).json()["accepted"] == 1
    rows = client.get("/usage").json()["views"]["policies"]
    assert len(rows) == 2 and sum(row["views"] for row in rows) == 2


def test_activity_sql_failure_keeps_response_shape_and_views(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("synthetic storage failure")

    monkeypatch.setattr(analytics, "_activity_summary", unavailable)
    assert client.post("/usage/events", json=payload()).json()["accepted"] == 1
    body = client.get("/usage").json()
    assert body["available"] is True and body["activity_available"] is False
    assert body["totals"] == {event: {"events": 0, "users": 0} for event in ("login", "logout", "download")}
    assert body["users"] == 0 and body["daily"] == [] and body["downloads"] == []
    assert body["download_details"] == {"targets": [], "formats": [], "regions": []}
    assert body["all_time"] == {"events": 0, "users": 0, "since": None}
    assert body["views"]["totals"]["indicator_view"]["events"] == 1
    assert "synthetic storage failure" not in str(body)


def test_request_limits_origins_and_tracking_preferences(client):
    assert client.post("/usage/events", json=payload(), headers={"Origin": "https://other.example"}).status_code == 403
    for header in ("DNT", "Sec-GPC"):
        response = client.post("/usage/events", json=payload(), headers={header: "1"})
        assert response.json() == {"accepted": 0, "duplicates": 0, "rejected": 0, "ignored": True}
    batch = payload()
    batch["events"] *= 21
    assert client.post("/usage/events", json=batch).status_code == 422
    assert client.post("/usage/events", content=b"x" * 16385, headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/usage/events", content=(b"x" * 8192 for _ in range(3)),
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/usage/events", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": "17000"}).status_code == 413
    assert client.post("/usage/events", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(UsageEvent)) == 0


def test_session_rate_limit(client):
    batch = payload()
    batch["events"] *= 20
    for _ in range(6):
        assert client.post("/usage/events", json=batch).status_code == 200
    response = client.post("/usage/events", json=batch)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_chart_and_map_have_separate_scope(client):
    with Session(get_engine()) as session:
        target = next(k for k in analytics.indicator_catalog(session) if k.endswith(":sido"))
    batch = payload(target=target)
    assert client.post("/usage/events", json=batch).json()["accepted"] == 1
    batch["events"][0].update(target=target + "-map", event_id=str(uuid4()))
    assert client.post("/usage/events", json=batch).json()["accepted"] == 1
    rows = client.get("/usage").json()["views"]["indicators"]
    assert {r["scope"] for r in rows} == {"sido", "sido-map"}


def test_global_rate_budget_without_persisting_addresses(client, monkeypatch):
    monkeypatch.setattr(analytics, "_global_rate", (int(analytics.time.monotonic() // 60), 2000))
    assert client.post("/usage/events", json=payload()).status_code == 429
    with Session(get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(UsageEvent)) == 0


def test_measurement_start_persists_across_restarts(client):
    before = client.get("/usage").json()["views"]["since"]
    initialize_storage()
    with Session(get_engine()) as session:
        assert session.get(ContentSnapshot, "usage-measurement").content["started_at"] == before


def test_kst_calendar_period_applies_to_downloads_and_views(client, monkeypatch):
    now = datetime(2026, 10, 20, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(analytics, "utc_now", lambda: now)
    table = Table(
        "activity_logs", MetaData(), Column("id", Integer, primary_key=True),
        Column("occurred_at", DateTime(timezone=True)), Column("user_id", String),
        Column("event", String), Column("target", String), Column("detail", JSON),
    )
    table.create(get_engine())
    cutoff = datetime(2026, 10, 19, 15, tzinfo=timezone.utc)  # October 20, 00:00 KST
    with get_engine().begin() as conn:
        conn.execute(table.insert(), [
            {"occurred_at": cutoff - timedelta(seconds=1), "user_id": "old-user", "event": "download",
             "target": "V002:sido", "detail": {"format": "csv", "regions": ["부산"]}},
            {"occurred_at": cutoff, "user_id": "user-one", "event": "download",
             "target": "V043:nation", "detail": {"format": "csv", "regions": ["전국", "서울"]}},
            {"occurred_at": cutoff + timedelta(hours=1), "user_id": "user-one", "event": "download",
             "target": "V043:nation", "detail": {"format": "xlsx", "regions": ["전국"]}},
            {"occurred_at": cutoff + timedelta(hours=2), "user_id": "user-two", "event": "login",
             "target": None, "detail": {}},
        ])
    with Session(get_engine()) as session:
        for instant in (cutoff - timedelta(seconds=1), cutoff, now):
            session.add(UsageEvent(event_id=str(uuid4()), session_id=str(uuid4()), event="indicator_view",
                                   target="V043:nation", label="기준금리", scope="nation", page="index",
                                   agency="", source_url="", occurred_at=instant))
        session.commit()
    result = client.get("/usage?days=1").json()
    assert result["activity_available"] is True
    assert result["period"]["start_at"] == "2026-10-19T15:00:00+00:00"
    assert result["totals"]["download"] == {"events": 2, "users": 1}
    assert result["users"] == 2 and result["all_time"]["events"] == 4
    assert {r["target"] for r in result["downloads"]} == {"V043:nation"}
    assert result["download_details"]["targets"][0]["downloads"] == 2
    assert {r["format"] for r in result["download_details"]["formats"]} == {"csv", "xlsx"}
    assert {r["region"]: r["downloads"] for r in result["download_details"]["regions"]} == {"전국": 2, "서울": 1}
    assert {r["day_kst"] for r in result["daily"]} == {"2026-10-20"}
    assert result["views"]["totals"]["indicator_view"]["events"] == 2
    assert {r["day_kst"] for r in result["views"]["daily"]} == {"2026-10-20"}
    assert "old-user" not in str(result) and "user-one" not in str(result)
    assert client.get("/usage?days=2").json()["totals"]["download"]["events"] == 3


def test_docs_include_typed_bounded_event_contract(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/usage/events"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("UsageBatchIn")
    assert schema["components"]["schemas"]["UsageBatchIn"]["properties"]["events"]["maxItems"] == 20
    assert schema["components"]["schemas"]["UsageEventIn"]["additionalProperties"] is False
