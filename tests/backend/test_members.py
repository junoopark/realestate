import base64
import json
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from app import member_auth, member_store
from app.main import app
from app.routers import members

USER_ID = "22222222-2222-4222-8222-222222222222"
PUBLIC_KEY = "sb_publishable_test_public_key_1234567890"


def user_payload(**changes):
    return {"id": USER_ID, "email": "test-user@example.com", "email_confirmed_at": "2026-10-10T00:00:00Z",
            "app_metadata": {"providers": ["google"]}, "identities": [{"provider": "google"}],
            "user_metadata": {"full_name": "테스트 회원"}, **changes}


@pytest.fixture
def member_client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", PUBLIC_KEY)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    # No lifespan in these auth-only tests: no database or network setup occurs.
    return TestClient(app)


def mock_user(monkeypatch, payload=None, status=200):
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=status, json=lambda: user_payload() if payload is None else payload)
    monkeypatch.setattr(member_auth.requests, "get", fake_get)
    return calls


def test_real_auth_contract_and_no_email_disclosure(member_client, monkeypatch):
    calls = mock_user(monkeypatch)
    response = member_client.get("/members/me", headers={"Authorization": "Bearer signed-user-token"})
    assert response.status_code == 200
    assert response.json() == {"id": USER_ID, "display_name": "테스트 회원"}
    assert "email" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "Authorization" in response.headers["vary"]
    url, options = calls[0]
    assert url == "https://test-project.supabase.co/auth/v1/user"
    assert options["headers"] == {"apikey": PUBLIC_KEY, "Authorization": "Bearer signed-user-token"}
    assert options["allow_redirects"] is False
    assert options["timeout"] == (3, 8)


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer ", "Bearer a b", "Bearer " + "x" * 8193])
def test_missing_or_malformed_bearer_denied(member_client, monkeypatch, authorization):
    calls = mock_user(monkeypatch)
    headers = {"Authorization": authorization} if authorization is not None else {}
    response = member_client.get("/members/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


@pytest.mark.parametrize("status", [401, 403])
def test_forged_and_expired_tokens_rejected_by_upstream(member_client, monkeypatch, status):
    calls = mock_user(monkeypatch, status=status)
    response = member_client.get("/members/me", headers={"Authorization": "Bearer forged-or-expired"})
    assert response.status_code == 401
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [
    {"id": "not-a-uuid"}, {"email_confirmed_at": None}, {"email": ""}, {"is_anonymous": True},
    {"app_metadata": {"providers": ["email"]}, "identities": [], "user_metadata": {"provider": "google"}},
    {"app_metadata": "google", "identities": "google"},
])
def test_only_confirmed_google_accounts_allowed(member_client, monkeypatch, changes):
    mock_user(monkeypatch, user_payload(**changes))
    response = member_client.get("/members/me", headers={"Authorization": "Bearer valid-other-account"})
    assert response.status_code == 401


def test_upstream_error_is_closed_and_sanitized(member_client, monkeypatch):
    def fail(*args, **kwargs):
        raise requests.Timeout("secret bearer and private host")
    monkeypatch.setattr(member_auth.requests, "get", fail)
    response = member_client.get("/members/me", headers={"Authorization": "Bearer sensitive-token"})
    assert response.status_code == 503
    assert "secret" not in response.text and "sensitive-token" not in response.text
    mock_user(monkeypatch, status=500)
    assert member_client.get("/members/me", headers={"Authorization": "Bearer valid"}).status_code == 503


def legacy_key(role):
    claims = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return "header." + claims + ".signature"


@pytest.mark.parametrize("key", ["sb_secret_sensitive_secret_value", legacy_key("service_role"), "invalid", ""])
def test_secret_or_invalid_keys_never_reach_config(member_client, monkeypatch, key):
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", key)
    response = member_client.get("/members/config")
    assert response.json() == {"enabled": False, "supabase_url": "", "supabase_publishable_key": "", "provider": "google"}
    if key:
        assert key not in response.text
    assert member_client.get("/members/me", headers={"Authorization": "Bearer valid"}).status_code == 503


def test_publishable_and_legacy_anon_config(member_client, monkeypatch):
    assert member_client.get("/members/config").json()["supabase_publishable_key"] == PUBLIC_KEY
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", legacy_key("anon"))
    assert member_client.get("/members/config").json()["enabled"] is True


@pytest.mark.parametrize("url", ["http://test.supabase.co", "https://user:password@test.supabase.co", "https://test.supabase.co/path", "https://test.supabase.co?key=private"])
def test_bad_config_url_not_exposed(member_client, monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    assert member_client.get("/members/config").json()["enabled"] is False


def test_download_auth_allowlist_and_content(member_client, monkeypatch, tmp_path):
    monkeypatch.setattr(members, "DOWNLOAD_ROOT", tmp_path)
    (tmp_path / "factor-sample.csv").write_text("date,value\n2026-10,123\n", encoding="utf-8-sig")
    mock_user(monkeypatch)
    catalog = member_client.get("/members/downloads").json()["items"]
    assert len(catalog) == 2 and catalog[0]["available"] is True
    assert catalog[0]["bytes"] > 0
    assert "path" not in catalog[0]
    assert member_client.get("/members/downloads/factor-sample").status_code == 401
    headers = {"Authorization": "Bearer valid"}
    response = member_client.get("/members/downloads/factor-sample", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'filename="factor-sample.csv"' in response.headers["content-disposition"]
    assert "2026-10,123" in response.text
    for path in ("not-a-file", "..%2F.env", "%2e%2e%5c.env", ".env"):
        assert member_client.get("/members/downloads/" + path, headers=headers).status_code == 404
    assert member_client.get("/members/downloads/variable-dictionary", headers=headers).status_code == 503


def test_download_path_cannot_escape_root(member_client, monkeypatch, tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    (tmp_path / "secret.csv").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(members, "DOWNLOAD_ROOT", root)
    assert members._download_path({"filename": "../secret.csv"}) is None


def test_status_is_operational_and_sanitized(member_client, monkeypatch):
    def fail():
        raise RuntimeError("postgres://secret:secret@private/db")
    monkeypatch.setattr(member_store, "get_member_engine", fail)
    response = member_client.get("/members/status")
    assert response.status_code == 200
    result = response.json()
    assert result["auth_configured"] is True
    assert result["storage"]["available"] is False
    assert result["storage"]["persistent"] is False
    assert isinstance(result["downloads_ready"], bool)
    assert "secret" not in response.text
