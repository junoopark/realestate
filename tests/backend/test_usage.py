"""이용 통계(/usage): activity_logs 가 없는 DB 에서는 이유와 함께 available=false, 캐시 헤더."""

from fastapi.testclient import TestClient

from app.services import cache


def test_usage_without_activity_logs(local_database):
    from app.main import app
    cache.clear()
    with TestClient(app) as client:
        res = client.get("/usage")
    body = res.json()
    assert res.status_code == 200 and body["available"] is False and "계정 전환" in body["reason"]
    assert body["days"] == 30 and res.headers["cache-control"] == "public, max-age=300"
    assert "user_id" not in res.text
    cache.clear()
