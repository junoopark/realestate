from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot
from app.db.session import get_engine


def test_warning_snapshot_is_persisted_and_served(local_database):
    with Session(get_engine()) as session:
        row = session.get(ContentSnapshot, "warning")
        assert row is not None and row.content["experiment"].startswith("1차")
    from app.main import app

    body = TestClient(app).get("/warning").json()
    assert body["storage"]["available"] is True and body["sync"]["mode"] == "reviewed_snapshot"
    assert set(body["timeline"]) == {"17시도|급등", "17시도|급락", "서울25구|급등", "서울25구|급락"}
    seoul = body["timeline"]["서울25구|급락"]["강남구"]
    assert len(seoul["month"]) == len(seoul["p"]) == len(seoul["y"]) == 60
    assert all(len(v) == 60 for v in seoul["contrib"].values())
    assert any(s["panel"] == "서울25구" and s["task"] == "급락" and s["set"] == "M3" for s in body["summary"])
    assert body["setup"]["sets"]["M3"]
