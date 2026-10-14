"""정량 지표 파이프라인·API 테스트. 외부 기관은 부르지 않고 응답 모양을 흉내 낸 가짜 클라이언트를 쓴다."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IndicatorFetchLog, IndicatorObservation, IndicatorVariable
from app.db.session import get_engine
from app.services import cache
from app.services import indicator_pipeline as pipeline
from app.services.indicator_registry import get_spec
from app.services.regions import normalize_sido
from app.services.rone_client import RoneClient, RoneError


# ── 가짜 외부 API ──

class FakeRone:
    """R-ONE SttsApiTblData 행 모양. 시도 17 + 전국 + 서울 강남구(구 단위, 걸러져야 함) × 항목 2개."""
    calls = 0

    def __init__(self, months=("2026-07", "2026-08"), items=("지수", "전월대비")):
        self.months, self.items = months, items

    def fetch_rows(self, statbl_id, start, end, cycle="MM", cls_id=None, itm_id=None):
        FakeRone.calls += 1
        regions = ["전국", "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
                   "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도", "서울 강남구"]
        rows = []
        for m in self.months:
            if not (start <= m <= end):
                continue
            for i, region in enumerate(regions):
                for j, item in enumerate(self.items):
                    rows.append({"STATBL_ID": statbl_id, "DTACYCLE_CD": cycle, "WRTTIME_IDTFR_ID": m.replace("-", ""),
                                 "ITM_ID": f"I{j}", "ITM_NM": item, "CLS_ID": f"C{i}", "CLS_NM": region, "CLS_FULLNM": f"전국 > {region}",
                                 "UI_NM": "", "DTA_VAL": f"{100 + i + j * 50:.1f}"})
        return rows


class FakeEcos:
    def fetch_rows(self, stat_code, item_code, start, end, freq="M"):
        return [{"STAT_CODE": stat_code, "ITEM_CODE1": item_code, "ITEM_NAME1": "한국은행 기준금리", "UNIT_NAME": "연%", "TIME": "202607", "DATA_VALUE": "2.50"},
                {"STAT_CODE": stat_code, "ITEM_CODE1": item_code, "ITEM_NAME1": "한국은행 기준금리", "UNIT_NAME": "연%", "TIME": "202608", "DATA_VALUE": "2.25"},
                {"STAT_CODE": stat_code, "ITEM_CODE1": item_code, "ITEM_NAME1": "한국은행 기준금리", "UNIT_NAME": "연%", "TIME": "202609", "DATA_VALUE": "-"}]


@pytest.fixture
def db(local_database, monkeypatch):
    cache.clear()
    FakeRone.calls = 0
    monkeypatch.setenv("RONE_API_KEY", "test")
    monkeypatch.setenv("ECOS_API_KEY", "test")
    monkeypatch.delenv("KOSIS_API_KEY", raising=False)
    monkeypatch.setattr(pipeline, "make_client", lambda source: {"R-ONE": FakeRone(), "ECOS": FakeEcos()}[source])
    yield


# ── 지역 이름 정규화 ──

def test_normalize_sido_handles_institution_spellings():
    assert normalize_sido("서울특별시") == "서울"
    assert normalize_sido("전북특별자치도") == "전북" and normalize_sido("전라북도") == "전북"
    assert normalize_sido("강원특별자치도") == "강원" and normalize_sido("충청북도") == "충북"
    assert normalize_sido("세종특별자치시") == "세종" and normalize_sido("경기") == "경기"
    assert normalize_sido("전국 > 수도권 > 서울") == "서울" and normalize_sido("전국") == "전국"
    assert normalize_sido("서울 강남구") is None and normalize_sido("수도권") is None


# ── 수집 → UPSERT ──

def test_refresh_variable_normalizes_filters_and_upserts(db):
    with Session(get_engine()) as session:
        spec = get_spec("V002")
        result = pipeline.refresh_variable(session, spec, trigger="cli", force=True, client=FakeRone())
        assert result["status"] == "ok" and result["last_period"] == "2026-08"
        rows = session.execute(select(IndicatorObservation).where(IndicatorObservation.variable_id == "V002")).scalars().all()
        regions = {r.region for r in rows}
        assert len(regions) == 17 and "전국" not in regions and "서울" in regions and "전북" in regions
        assert all(r.value < 150 for r in rows), "item='지수' 만 남고 '전월대비'(+50) 는 걸러져야 한다"
        var = session.get(IndicatorVariable, "V002")
        assert var.last_status == "ok" and var.item_name == "지수" and var.first_period == "2026-07"
        # 같은 자료를 다시 받아도 행이 늘지 않는다 (UPSERT)
        pipeline.refresh_variable(session, spec, force=True, client=FakeRone())
        assert session.scalar(select(func.count()).select_from(IndicatorObservation).where(IndicatorObservation.variable_id == "V002")) == 34
        # 수정된 값은 제자리에서 갱신된다
        pipeline.upsert_observations(session, "V002", [("서울", "2026-08", 999.0)], pipeline.utc_now())
        session.commit()
        assert session.get(IndicatorObservation, ("V002", "서울", "2026-08")).value == 999.0
        assert session.scalar(select(func.count()).select_from(IndicatorFetchLog)) == 2


def test_refresh_skips_when_fresh_and_logs_errors(db):
    with Session(get_engine()) as session:
        spec = get_spec("V043")
        first = pipeline.refresh_variable(session, spec, client=FakeEcos())
        assert first["status"] == "ok" and first["rows"] == 2  # '-' 값은 제외
        assert pipeline.refresh_variable(session, spec, client=FakeEcos())["status"] == "skipped"

        class Broken:
            def fetch_rows(self, *a, **k):
                raise RoneError("R-ONE ERROR-337: 일일 호출 한도 초과")
        bad = pipeline.refresh_variable(session, get_spec("V001"), force=True, client=Broken())
        assert bad["status"] == "error" and "337" in bad["error"]
        assert session.get(IndicatorVariable, "V001").last_status == "error"
        # 실패해도 다른 변수 자료는 그대로
        assert session.get(IndicatorVariable, "V043").last_status == "ok"


def test_refresh_all_reports_missing_key_without_stopping(db, monkeypatch):
    monkeypatch.setattr(pipeline, "make_client", lambda source: (_ for _ in ()).throw(ValueError(f"{source} 키 없음")) if source == "R-ONE" else FakeEcos())
    with Session(get_engine()) as session:
        result = pipeline.refresh_all(session, ["V002", "V043"], force=True)
        by = {r["id"]: r for r in result["results"]}
        assert by["V002"]["status"] == "error" and "키" in by["V002"]["error"]
        assert by["V043"]["status"] == "ok" and result["status"] == "partial"


# ── 조회 형식 ──

def test_load_metric_matches_sample_shape(db):
    with Session(get_engine()) as session:
        pipeline.refresh_variable(session, get_spec("V002"), force=True, client=FakeRone(months=("2026-05", "2026-08")))
        m = pipeline.load_metric(session, get_spec("V002"))
        assert m["periods"] == ["2026-05", "2026-06", "2026-07", "2026-08"], "빈 달은 채워서 길이를 맞춘다"
        assert list(m["series"])[:3] == ["서울", "부산", "대구"] and m["series"]["서울"] == [101.0, None, None, 101.0]
        assert m["scope"] == "sido" and m["source"] == "R-ONE A_2024_00045" and m["live"] is True
        sub = pipeline.load_metric(session, get_spec("V002"), regions=["경기"], start="2026-08")
        assert list(sub["series"]) == ["경기"] and sub["periods"] == ["2026-08"]


# ── API ──

def test_get_indicator_lazy_fetches_then_serves_from_db(db):
    from app.main import app
    with TestClient(app) as client:
        first = client.get("/indicators/V002")
        assert first.status_code == 200 and first.json()["origin"] == "api(R-ONE)"
        assert FakeRone.calls == 1
        cache.clear()
        second = client.get("/indicators/V002")
        assert second.json()["origin"] == "db(cache)" and FakeRone.calls == 1
        assert second.headers["cache-control"].startswith("public, max-age=") and second.headers["etag"]
        assert client.get("/indicators/V002", headers={"If-None-Match": second.headers["etag"]}).status_code == 304
        assert client.get("/indicators/V999").status_code == 404
        assert client.get("/indicators/V012").status_code == 404  # enabled=False


def test_bundle_and_status(db):
    from app.main import app
    with TestClient(app) as client:
        res = client.get("/indicators/bundle", params={"vars": "V002,V043,V012", "regions": "서울,부산", "start": "2026-08"})
        body = res.json()
        assert res.status_code == 200 and body["origin"] == "db(cache)+api" and body["missing"] == ["V012"]
        assert [m["var"] for m in body["metrics"]] == ["V002", "V043"]
        assert list(body["metrics"][0]["series"]) == ["서울", "부산"] and body["metrics"][1]["series"]["전국"] == [2.25]
        listing = client.get("/indicators").json()
        assert {v["id"] for v in listing["variables"]} >= {"V001", "V002", "V043", "V012"}
        assert listing["sources"]["R-ONE"]["organization"] == "한국부동산원"
        status = client.get("/indicators/status").json()
        assert status["keys"] == {"R-ONE": True, "ECOS": True, "KOSIS": False}
        assert status["logs"][0]["trigger"] == "lazy" and status["storage"]["type"] == "sqlite"


def test_refresh_endpoint_requires_token(db, monkeypatch):
    from app.main import app
    with TestClient(app) as client:
        monkeypatch.delenv("POLICY_ADMIN_TOKEN", raising=False)
        assert client.post("/indicators/refresh").status_code == 503
        monkeypatch.setenv("POLICY_ADMIN_TOKEN", "secret")
        assert client.post("/indicators/refresh").status_code == 401
        assert client.post("/indicators/refresh", headers={"X-Admin-Token": "wrong"}).status_code == 401
        res = client.post("/indicators/refresh", params={"vars": "V002,V043"}, headers={"X-Admin-Token": "secret"})
        assert res.status_code == 200 and res.json()["status"] == "ok"
        assert {r["id"]: r["status"] for r in res.json()["results"]} == {"V002": "ok", "V043": "ok"}
        again = client.post("/indicators/refresh", params={"vars": "V002"}, headers={"X-Admin-Token": "secret"}).json()
        assert again["results"][0]["status"] == "skipped"


# ── R-ONE 클라이언트: 페이지 넘기기·오류 코드 ──

def test_rone_client_paginates_and_handles_result_codes(monkeypatch):
    class Resp:
        def __init__(self, payload):
            self.payload, self.encoding = payload, None
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload

    pages = {
        1: {"SttsApiTblData": [{"head": [{"list_total_count": 3}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]}, {"row": [{"DTA_VAL": "1"}, {"DTA_VAL": "2"}]}]},
        2: {"SttsApiTblData": [{"head": [{"list_total_count": 3}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]}, {"row": [{"DTA_VAL": "3"}]}]},
    }
    seen = []

    class Http:
        def get(self, url, params=None, timeout=None):
            seen.append(params)
            return Resp(pages[params["pIndex"]])

    monkeypatch.setattr("app.services.rone_client.time.sleep", lambda s: None)
    client = RoneClient(api_key="k", session=Http())
    rows = client.fetch_rows("A_2024_00045", "2016-01", "2026-12")
    assert [r["DTA_VAL"] for r in rows] == ["1", "2", "3"] and len(seen) == 2
    assert seen[0]["START_WRTTIME"] == "201601" and seen[0]["END_WRTTIME"] == "202612" and seen[0]["DTACYCLE_CD"] == "MM"

    class NoData:
        def get(self, url, params=None, timeout=None):
            return Resp({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}})
    assert RoneClient(api_key="k", session=NoData()).fetch_rows("X", "2016-01", "2016-02") == []

    class Limit:
        def get(self, url, params=None, timeout=None):
            return Resp({"RESULT": {"CODE": "ERROR-337", "MESSAGE": "일일 트래픽 초과"}})
    with pytest.raises(RoneError, match="ERROR-337"):
        RoneClient(api_key="k", session=Limit()).fetch_rows("X", "2016-01", "2016-02")

    monkeypatch.delenv("RONE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        RoneClient()
