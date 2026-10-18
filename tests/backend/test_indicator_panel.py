"""지표 기본 패널(전처리본 → DB) 적재·조회 테스트. 외부 기관은 부르지 않는다."""

import gzip
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IndicatorSeries, IndicatorSeriesValue
from app.db.session import get_engine
from app.services import cache
from app.services import indicator_pipeline as pipeline
from app.services.indicator_panel import panel_metrics, panel_status, seed_panel

SAMPLE = Path(__file__).resolve().parents[2] / "frontend" / "data" / "factor_sample.json"


def small_panel():
    p = ["2026-06", "2026-07", "2026-08"]
    return {
        "_source": "테스트 전처리본", "generated": "2026-10-05 | 테스트",
        "aliases": {"V033": "V005"},
        "regions": {"sido": ["서울", "부산"], "gu": ["강남구", "마포구"]},
        "metrics": [
            {"var": "V002", "column": "Y_V002_아파트매매가격지수", "label": "아파트 매매가격지수", "unit": "", "freq": "M", "scope": "sido",
             "periods": p, "series": {"부산": [90.0, 90.5, None], "서울": [100.0, 100.5, 101.0]}, "source": "R-ONE A_2024_00045",
             "method": "원자료", "release": "익월 15일"},
            {"var": "V002", "column": "Y_V002_아파트매매가격지수", "label": "아파트 매매가격지수", "unit": "", "freq": "M", "scope": "gu",
             "periods": p, "series": {"강남구": [110.0, 111.0, 112.0], "마포구": [105.0, None, 106.0]}, "source": "R-ONE A_2024_00045",
             "method": "원자료", "release": "익월 15일"},
            {"var": "V006", "column": "X_V006_매매거래", "label": "실거래 신고건수(매매)", "unit": "건", "freq": "M", "scope": "sido",
             "periods": p, "series": {"서울": [5000, 5100, 4900]}, "source": "국토부 실거래", "method": "합계", "release": "",
             "provisional_from": "2026-07"},
            {"var": "V006", "column": "X_V006_전월세거래", "label": "실거래 신고건수(전월세)", "unit": "건", "freq": "M", "scope": "sido",
             "periods": p, "series": {"서울": [15000, 15100, 14900]}, "source": "국토부 실거래", "method": "합계", "release": "",
             "filled": 2},
            {"var": "V009", "column": "X_V009_주민등록인구", "label": "주민등록 인구", "unit": "명", "freq": "A", "scope": "nation",
             "periods": ["2024", "2025"], "series": {"전국": [51_000_000, 50_900_000]}, "source": "행정안전부", "method": "", "release": ""},
        ],
    }


class FakeRone:
    def fetch_rows(self, statbl_id, start, end, cycle="MM", cls_id=None, itm_id=None):
        return [{"WRTTIME_IDTFR_ID": m.replace("-", ""), "ITM_NM": "지수", "CLS_NM": r, "DTA_VAL": v}
                for m in ("2026-08", "2026-09") if start <= m <= end
                for r, v in (("서울특별시", "102.0"), ("부산광역시", "91.0"))]


@pytest.fixture
def db(local_database, monkeypatch):
    cache.clear()
    for k in ("RONE_API_KEY", "ECOS_API_KEY", "KOSIS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield
    cache.clear()


def counts():
    with Session(get_engine()) as s:
        return (s.execute(select(func.count()).select_from(IndicatorSeries)).scalar(),
                s.execute(select(func.count()).select_from(IndicatorSeriesValue)).scalar())


def test_seed_is_idempotent_and_drops_removed_series(db):
    data = small_panel()
    with Session(get_engine()) as s:
        r1 = seed_panel(s, data)
    assert r1["series"] == 5 and r1["values"] == 5 + 5 + 3 + 3 + 2  # null 2칸은 저장하지 않는다
    assert counts() == (5, r1["values"])
    with Session(get_engine()) as s:
        seed_panel(s, data)  # 같은 파일 다시 적재
    assert counts() == (5, r1["values"])
    data["metrics"] = data["metrics"][:4]  # V009 계열이 빠진 새 전처리본
    with Session(get_engine()) as s:
        r3 = seed_panel(s, data)
        status = panel_status(s)
    assert r3["removed_series"] == 1 and counts() == (4, r1["values"] - 2)
    assert status["loaded"] and status["variables"] == 2 and status["generated"] == "2026-10-05 | 테스트"


def test_panel_metrics_rebuild_sample_shape(db):
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
        ms = panel_metrics(s)
        only = panel_metrics(s, ["V002"], regions=["서울"], start="2026-07")
    assert [(m["var"], m["scope"]) for m in ms] == [("V002", "sido"), ("V002", "gu"), ("V006", "sido"), ("V006", "sido"), ("V009", "nation")]
    v002 = ms[0]
    assert v002["periods"] == ["2026-06", "2026-07", "2026-08"]
    assert list(v002["series"]) == ["서울", "부산"]  # 지역 순서는 패널의 regions 순서
    assert v002["series"]["부산"] == [90.0, 90.5, None] and v002["origin"] == "db(panel)" and v002["live"] is False
    assert ms[2]["provisional_from"] == "2026-07" and ms[3]["filled"] == 2
    assert [m["scope"] for m in only] == ["sido", "gu"]
    assert only[0]["periods"] == ["2026-07", "2026-08"] and list(only[0]["series"]) == ["서울"]
    assert only[1]["series"] == {}  # gu 계열에는 '서울'이 없다


def test_bundle_all_uses_panel_and_live_override(db, monkeypatch):
    from app.main import app
    monkeypatch.setenv("RONE_API_KEY", "test")
    monkeypatch.setattr(pipeline, "make_client", lambda source: FakeRone())
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
        pipeline.refresh_variable(s, pipeline.get_spec("V002"), force=True, client=FakeRone())
    with TestClient(app) as client:
        res = client.get("/indicators/bundle", params={"set": "all"})
        body = res.json()
        assert res.status_code == 200 and body["set"] == "all" and body["aliases"] == {"V033": "V005"}
        assert body["regions"]["gu"] == ["강남구", "마포구"] and body["panel"]["generated"] == "2026-10-05 | 테스트"
        keys = [(m["var"], m["scope"], m["live"]) for m in body["metrics"]]
        # V002 시도·구 계열은 Open API 로 갱신되는 계열(live), 나머지는 기본 패널 그대로
        assert keys[:2] == [("V002", "sido", True), ("V002", "gu", True)]
        assert ("V006", "sido", False) in keys and len([k for k in keys if k[0] == "V006"]) == 2
        live = body["metrics"][0]
        assert live["periods"][-1] == "2026-09" and live["series"]["서울"][-1] == 102.0
        # 기본값(set=live)은 예전처럼 Open API 수집 변수만
        default = client.get("/indicators/bundle").json()
        assert default["set"] == "live" and all(m["live"] for m in default["metrics"])
        # 변수 필터 + 아무 데도 없는 변수는 missing
        part = client.get("/indicators/bundle", params={"set": "all", "vars": "V006,V999"}).json()
        assert {m["var"] for m in part["metrics"]} == {"V006"} and part["missing"] == ["V999"]


def test_bundle_all_does_not_block_on_unfetched_live_vars(db, monkeypatch):
    """Open API 변수가 아직 한 번도 수집되지 않았어도 기다리지 않고 기본 패널로 응답한다(수집은 뒤에서)."""
    from app.main import app
    monkeypatch.setenv("RONE_API_KEY", "test")
    calls = []
    monkeypatch.setattr(pipeline, "make_client", lambda source: calls.append(source) or FakeRone())
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
    with TestClient(app) as client:
        body = client.get("/indicators/bundle", params={"set": "all", "vars": "V002"}).json()
    assert [(m["scope"], m["live"]) for m in body["metrics"]] == [("sido", False), ("gu", False)]


def test_get_indicator_falls_back_to_panel(db):
    from app.main import app
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
    with TestClient(app) as client:
        v006 = client.get("/indicators/V006")
        assert v006.status_code == 200 and v006.json()["origin"] == "db(panel)" and v006.json()["column"] == "X_V006_매매거래"
        assert client.get("/indicators/V002", params={"scope": "gu"}).json()["series"]["강남구"][-1] == 112.0
        # V002 는 Open API 변수지만 키가 없으면 기본 패널로 응답
        assert client.get("/indicators/V002").json()["origin"] == "db(panel)"
        assert client.get("/indicators/V999").status_code == 404
        assert client.get("/indicators/V034").status_code == 404  # 수집 안 함(종료 통계)이고 이 테스트 패널에도 없음
        assert client.get("/indicators/V012").status_code == 503  # 수집 변수지만 키가 없고 패널에도 없음
        status = client.get("/indicators/status").json()
        assert status["panel"]["series"] == 5


@pytest.mark.skipif(not SAMPLE.exists(), reason="frontend/data/factor_sample.json 없음")
def test_real_sample_round_trips_through_db(db):
    """실제 전처리본 전체를 적재하고 꺼내면 화면이 쓰던 파일과 값이 같다 — DB 를 단일 출처로 바꿔도 화면 값이 그대로."""
    from app.main import app
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with Session(get_engine()) as s:
        result = seed_panel(s, data)
    assert result["series"] == len(data["metrics"])
    with TestClient(app) as client:
        res = client.get("/indicators/bundle", params={"set": "all"}, headers={"Accept-Encoding": "gzip"})
        assert res.headers.get("content-encoding") == "gzip"
        body = res.json()
    assert len(body["metrics"]) == len(data["metrics"]) and body["aliases"] == data["aliases"]
    for want, got in zip(data["metrics"], body["metrics"]):
        assert (got["var"], got["scope"], got["column"]) == (want["var"], want["scope"], want["column"])
        assert got["periods"] == want["periods"]
        for region, values in want["series"].items():
            assert got["series"].get(region, [None] * len(values)) == [None if v is None else float(v) for v in values], (want["column"], region)


def test_cache_headers_for_browser_cdn_and_monitor(db):
    """① 브라우저 5분 · ② CDN(Vercel) 1시간 + 보관본 갱신·장애 대비 · 모니터는 캐시 금지."""
    from app.main import app
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
    with TestClient(app) as client:
        res = client.get("/indicators/bundle", params={"set": "all"})
        assert res.headers["cache-control"] == "public, max-age=300"
        cdn = res.headers["cdn-cache-control"]
        assert "max-age=3600" in cdn and "stale-while-revalidate=86400" in cdn and "stale-if-error=604800" in cdn
        assert res.headers["vercel-cache-tag"] == "indicators"
        again = client.get("/indicators/bundle", params={"set": "all"}, headers={"If-None-Match": res.headers["etag"]})
        assert again.status_code == 304 and again.headers["cdn-cache-control"] == cdn
        status = client.get("/indicators/status")
        assert status.headers["cache-control"] == "no-store" and status.headers["cdn-cache-control"] == "no-store"
        assert "cdn-cache-control" not in client.get("/indicators/V999").headers  # 오류 응답은 캐시하지 않는다


def test_vercel_rewrite_points_api_to_backend():
    """vercel.json: /api/* → Render, 오래된 Vercel 프로젝트에서도 rewrite 캐시를 켠다."""
    conf = json.loads((SAMPLE.parents[1] / "vercel.json").read_text(encoding="utf-8"))
    rw = conf["rewrites"][0]
    assert rw["source"] == "/api/:path*" and rw["destination"].startswith("https://") and rw["destination"].endswith("/:path*")
    hdrs = {h["key"]: h["value"] for h in conf["headers"][0]["headers"]}
    assert conf["headers"][0]["source"] == "/api/:path*" and hdrs["x-vercel-enable-rewrite-caching"] == "1"


def test_bundle_live_keeps_multi_series_vars_apart(db):
    """한 변수에 화면 계열이 여럿이면(V011 연령대) set=live 도 열 이름별로 따로 준다 — 화면이 엉뚱한 계열을 덮어쓰지 않게."""
    from app.main import app
    p = ["2026-07", "2026-08"]
    data = {"generated": "t", "aliases": {}, "regions": {"sido": ["서울"], "gu": []}, "metrics": [
        {"var": "V011", "column": "V011_주민등록인구_20-29세_명", "label": "20-29", "unit": "명", "freq": "M", "scope": "sido",
         "periods": p, "series": {"서울": [1.0, 2.0]}},
        {"var": "V011", "column": "V011_주민등록인구_20-39세비중_%", "label": "비중", "unit": "%", "freq": "M", "scope": "sido",
         "periods": p, "series": {"서울": [3.0, 4.0]}}]}
    rows = [{"PRD_DE": "202608", "C1": "11", "DT": v, "C2": c} for c, v in (("000", "1000"), ("1201", "100"), ("1501", "50"))]

    class FakeKosis:
        def fetch(self, *args, **kwargs):
            return rows

    with Session(get_engine()) as s:
        seed_panel(s, data)
        for sid in ("V011.1", "V011.4"):
            assert pipeline.refresh_variable(s, pipeline.get_spec(sid), force=True, client=FakeKosis())["status"] == "ok"
    with TestClient(app) as client:
        body = client.get("/indicators/bundle", params={"vars": "V011.1,V011.4"}).json()
    got = {m["column"]: m["series"]["서울"] for m in body["metrics"]}
    assert got == {"V011_주민등록인구_20-29세_명": [1.0, 100.0], "V011_주민등록인구_20-39세비중_%": [3.0, 15.0]}
    assert all(m["live"] and m["origin"] == "db(api)" for m in body["metrics"])


def test_bundle_reads_db_in_few_round_trips(db, monkeypatch):
    """묶음 응답은 변수 수와 상관없이 DB 를 몇 번만 읽는다(Render ↔ Supabase 왕복 1회 ≈ 70ms 라 변수마다 물으면 20초를 넘는다)."""
    from sqlalchemy import event
    from app.main import app
    monkeypatch.setenv("RONE_API_KEY", "test")
    with Session(get_engine()) as s:
        seed_panel(s, small_panel())
        pipeline.refresh_variable(s, pipeline.get_spec("V002"), force=True, client=FakeRone())
    monkeypatch.delenv("RONE_API_KEY")
    seen = []
    listener = lambda *args, **kwargs: seen.append(1)  # noqa: E731
    event.listen(get_engine(), "before_cursor_execute", listener)
    try:
        with TestClient(app) as client:
            for params in ({"set": "all"}, {"vars": "V002"}):
                cache.clear()
                seen.clear()
                assert client.get("/indicators/bundle", params=params).status_code == 200
                assert len(seen) <= 8, (params, len(seen))
    finally:
        event.remove(get_engine(), "before_cursor_execute", listener)
