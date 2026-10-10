import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import member_auth, member_store
from app.db.session import get_engine
from app.main import app
from app.routers import engagement

ALICE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
BOB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
A = {"Authorization": "Bearer alice"}
B = {"Authorization": "Bearer bob"}


@pytest.fixture
def engagement_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'engagement.db').as_posix()}")
    monkeypatch.setenv("SUPABASE_URL", "https://engagement-test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test_public_key_1234567890")
    registry = tmp_path / "indicators.json"
    registry.write_text(json.dumps([
        {"id": "V001", "name": "인구", "driver": "population"},
        {"id": "V002", "name": "금리", "driver": "finance"},
        {"id": "V003", "name": "공급", "driver": "supply"},
    ]), encoding="utf-8")
    monkeypatch.setattr(engagement, "REGISTRY_PATH", registry)
    get_engine.cache_clear()
    member_store.get_member_engine.cache_clear()
    def fake_get(url, **kwargs):
        token = kwargs["headers"]["Authorization"].split(" ")[1]
        users = {"alice": (ALICE, "앨리스"), "bob": (BOB, "밥")}
        if token not in users:
            return SimpleNamespace(status_code=401, json=lambda: {})
        uid, name = users[token]
        return SimpleNamespace(status_code=200, json=lambda: {
            "id": uid, "email": name + "@example.com", "email_confirmed_at": "2026-10-10T00:00:00Z",
            "app_metadata": {"providers": ["google"]}, "identities": [{"provider": "google"}],
            "user_metadata": {"full_name": name},
        })
    monkeypatch.setattr(member_auth.requests, "get", fake_get)
    with TestClient(app) as client:
        yield client
    member_store.get_member_engine().dispose()
    member_store.get_member_engine.cache_clear()
    get_engine().dispose()
    get_engine.cache_clear()


def put(client, indicator="V001", headers=A):
    response = client.put(f"/engagement/indicators/{indicator}/like", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_public_counts_and_two_account_ownership(engagement_client):
    client = engagement_client
    assert client.get("/engagement/popular").json()["items"] == []
    assert put(client) == {"id": "V001", "likes": 1, "liked_by_me": True}
    for headers in ({}, B):
        response = client.get("/engagement/indicators", headers=headers)
        item = response.json()["items"][0]
        assert item["likes"] == 1 and item["liked_by_me"] is False
        assert ALICE not in response.text and BOB not in response.text and "@" not in response.text
        assert "user_id" not in item and "author" not in item
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/engagement/indicators", headers=A).json()["items"][0]["liked_by_me"] is True
    # Bob's DELETE can never remove Alice's vote.
    response = client.delete("/engagement/indicators/V001/like", headers=B)
    assert response.json() == {"id": "V001", "likes": 1, "liked_by_me": False}
    assert put(client, headers=B)["likes"] == 2
    assert client.delete("/engagement/indicators/V001/like", headers=A).json() == {"id": "V001", "likes": 1, "liked_by_me": False}
    assert client.get("/engagement/indicators", headers=B).json()["items"][0]["liked_by_me"] is True


def test_repeated_put_and_delete_are_idempotent(engagement_client):
    client = engagement_client
    for _ in range(3):
        assert put(client) == {"id": "V001", "likes": 1, "liked_by_me": True}
    for _ in range(3):
        assert client.delete("/engagement/indicators/V001/like", headers=A).json() == {"id": "V001", "likes": 0, "liked_by_me": False}
    assert client.get("/engagement/popular").json()["items"] == []


def test_concurrent_puts_cannot_duplicate_vote(engagement_client):
    client = engagement_client
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: client.put("/engagement/indicators/V001/like", headers=A), range(10)))
    assert all(result.status_code == 200 for result in results)
    assert client.get("/engagement/indicators").json()["items"][0]["likes"] == 1
    with Session(member_store.get_member_engine()) as session:
        assert session.scalar(select(func.count()).select_from(member_store.IndicatorLike)) == 1


def test_popular_sorted_and_positive_only(engagement_client):
    client = engagement_client
    put(client, "V002")
    put(client, "V001")
    assert [row["id"] for row in client.get("/engagement/popular").json()["items"]] == ["V001", "V002"]
    put(client, "V002", B)
    response = client.get("/engagement/popular?limit=1").json()
    assert len(response["items"]) == 1 and response["items"][0]["id"] == "V002"
    assert response["items"][0]["likes"] == 2
    assert response["items"][0]["liked_by_me"] is False
    assert client.get("/engagement/popular?limit=0").status_code == 422
    assert client.get("/engagement/popular?limit=51").status_code == 422


def test_mutations_require_auth_and_ignore_no_untrusted_fields(engagement_client):
    client = engagement_client
    assert client.put("/engagement/indicators/V001/like").status_code == 401
    assert client.delete("/engagement/indicators/V001/like").status_code == 401
    assert client.put("/engagement/indicators/V001/like", headers={"Authorization": "Bearer forged"}).status_code == 401
    for method in ("put", "delete"):
        response = client.request(method, "/engagement/indicators/V001/like", headers=A, json={"user_id": BOB})
        assert response.status_code == 422
        assert client.request(method, "/engagement/indicators/not-an-indicator/like", headers=A).status_code == 404
    assert client.get("/engagement/popular").json()["items"] == []


def test_storage_persists_after_engine_restart(engagement_client):
    put(engagement_client)
    member_store.get_member_engine().dispose()
    member_store.get_member_engine.cache_clear()
    member_store.initialize_member_storage()
    assert engagement_client.get("/engagement/indicators", headers=A).json()["items"][0]["liked_by_me"] is True
    assert engagement_client.get("/members/status").json()["storage"] == {"type": "sqlite", "available": True, "persistent": False}


def test_failed_initialization_closes_engagement_only(engagement_client, monkeypatch):
    put(engagement_client)
    def fail(*args, **kwargs):
        raise RuntimeError("postgres://user:secret@internal-host/db")
    with monkeypatch.context() as patch:
        patch.setattr(member_store.MemberBase.metadata, "create_all", fail)
        with pytest.raises(RuntimeError):
            member_store.initialize_member_storage()
        for method, url, kwargs in (
            ("get", "/engagement/indicators", {}),
            ("get", "/engagement/popular", {"headers": A}),
            ("put", "/engagement/indicators/V001/like", {"headers": A}),
            ("delete", "/engagement/indicators/V001/like", {"headers": A}),
        ):
            response = getattr(engagement_client, method)(url, **kwargs)
            assert response.status_code == 503 and "secret" not in response.text
            assert response.headers["cache-control"] == "no-store"
        assert engagement_client.get("/health").status_code == 200
        assert engagement_client.get("/members/config").status_code == 200
        assert engagement_client.get("/members/status").json()["storage"]["available"] is False
    member_store.initialize_member_storage()


def test_corrupt_registry_is_closed_without_internal_paths(engagement_client, monkeypatch, tmp_path):
    monkeypatch.setattr(engagement, "REGISTRY_PATH", tmp_path / "private-secret-file")
    response = engagement_client.get("/engagement/indicators")
    assert response.status_code == 503 and "private-secret-file" not in response.text
    assert engagement_client.put("/engagement/indicators/V001/like", headers=A).status_code == 503
