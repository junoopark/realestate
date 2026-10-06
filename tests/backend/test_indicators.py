from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IndicatorSeries, IndicatorVariable
from app.db.session import get_engine
from app.services import indicator_store


def seed():
    with Session(get_engine()) as session:
        return indicator_store.load_from_files(session)


def test_load_from_files_is_idempotent(local_database):
    first = seed()
    assert first["inserted"] >= 50 and first["updated"] == 0
    with Session(get_engine()) as session:
        variables = session.scalar(select(func.count()).select_from(IndicatorVariable))
        series = session.scalar(select(func.count()).select_from(IndicatorSeries))
    assert variables == first["inserted"]
    assert series > variables
    second = seed()
    assert second["inserted"] == 0 and second["updated"] == 0 and second["skipped"] == variables


def test_list_and_get_from_database(local_database):
    seed()
    from app.main import app

    client = TestClient(app)
    listing = client.get("/indicators").json()
    assert listing["count"] >= 50 and listing["storage"]["source"] == "database"
    v001 = next(v for v in listing["variables"] if v["id"] == "V001")
    assert "서울" in v001["regions"] and v001["items"][0]["key"] == "지수"

    full = client.get("/indicators/V001").json()
    seoul = full["items"]["지수"]["regions"]["서울"]
    assert seoul["freq"] == "M" and len(seoul["dates"]) == len(seoul["values"]) > 100
    assert full["storage"]["source"] == "database"

    one = client.get("/indicators/V013", params={"item": "고용률", "region": "강남구"}).json()
    assert list(one["items"]) == ["고용률"] and list(one["items"]["고용률"]["regions"]) == ["강남구"]
    assert one["items"]["고용률"]["regions"]["강남구"]["freq"] == "H"   # 서울 구는 반기 자료

    assert client.get("/indicators/V033").json()["same_as"] == "V005"
    assert client.get("/indicators/V999").status_code == 404
    assert client.get("/indicators/V001", params={"region": "없는지역"}).status_code == 404


def test_static_fallback_when_database_is_empty(local_database):
    from app.main import app

    client = TestClient(app)
    listing = client.get("/indicators").json()
    assert listing["count"] >= 50 and listing["storage"]["source"] == "static_json"
    one = client.get("/indicators/V002", params={"region": "서울"}).json()
    assert list(one["items"]["지수"]["regions"]) == ["서울"] and one["storage"]["source"] == "static_json"
