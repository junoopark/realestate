"""주소 통일: 서버는 '/api/…' 로 와도 '/…' 와 같게 답하고, Swagger 는 /api/openapi.json 을 읽는다(www.khmi.kr/api/docs)."""

from fastapi.testclient import TestClient


def test_api_prefix_and_swagger(local_database):
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/health").json() == client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/indicators/status").status_code == 200
        docs = client.get("/api/docs")
        assert docs.status_code == 200 and "/api/openapi.json" in docs.text
        assert client.get("/docs").status_code == 200
        spec = client.get("/api/openapi.json").json()
        assert spec["servers"][0]["url"] == "/api" and "/indicators/status" in spec["paths"]
        assert "/docs" not in spec["paths"]
        assert client.get("/apiary").status_code == 404  # '/api' 로 시작하는 다른 경로는 건드리지 않는다
