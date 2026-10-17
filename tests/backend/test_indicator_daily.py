"""매일 수집 → 바뀐 값만 저장 → 기본 패널 계열에 이어붙이기 (ECOS 묶음). 외부 기관은 부르지 않는다."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndicatorSeries, IndicatorSeriesValue
from app.db.session import get_engine
from app.services import cache
from app.services import indicator_pipeline as pipeline
from app.services.ecos_client import to_period as ecos_period
from app.services.indicator_panel import seed_panel
from app.services.indicator_registry import enabled_specs, get_spec

P = ["2026-06", "2026-07", "2026-08"]


def panel():
    def m(var, column, scope, series, unit=""):
        return {"var": var, "column": column, "label": column, "unit": unit, "freq": "M", "scope": scope, "periods": P,
                "series": series, "source": "ECOS", "method": "", "release": ""}
    return {"generated": "테스트", "aliases": {}, "regions": {"sido": ["서울", "부산"], "gu": []}, "metrics": [
        m("V043", "V043_한국은행_기준금리_연%", "nation", {"전국": [2.5, 2.5, 2.5]}, "연%"),
        m("V061", "V061_주택가격전망CSI_서울", "nation", {"서울 권역": [130.0, 131.0, 132.0]}),
        m("V069", "V069_가계대출(전체)_십억원", "nation", {"전국": [100.0, 101.0, 102.0]}),
        m("V069", "V069_가계대출(주택관련)_십억원", "nation", {"전국": [70.0, 71.0, 72.0]}),
        m("V050", "V050_지역별주택관련대출_십억원", "sido", {"서울": [1.0, 2.0, 3.0], "부산": [4.0, 5.0, 6.0]}),
        m("V050", "서울_V050_지역별주택관련대출_십억원", "seoul", {"서울": [1.0, 2.0, 3.0]}),
    ]}


class FakeEcos:
    """항목 경로별 {시점: 값}. 기간 안의 달만 돌려준다."""
    def __init__(self, data):
        self.data, self.calls = data, []

    def fetch_rows(self, stat_code, item_code, start, end, freq="M"):
        self.calls.append((stat_code, item_code, start, end))
        rows = []
        for period, value in self.data.get(item_code, self.data.get("*", {})).items():
            if start <= period <= end:
                rows.append({"STAT_CODE": stat_code, "ITEM_NAME1": item_code, "TIME": period.replace("-", ""), "DATA_VALUE": str(value)})
        return rows


@pytest.fixture
def db(local_database, monkeypatch):
    cache.clear()
    monkeypatch.setenv("ECOS_API_KEY", "test")
    with Session(get_engine()) as s:
        seed_panel(s, panel())
    yield
    cache.clear()


def values(series_id):
    with Session(get_engine()) as s:
        return {(r, p): v for r, p, v in s.execute(select(IndicatorSeriesValue.region, IndicatorSeriesValue.period,
                                                           IndicatorSeriesValue.value).where(IndicatorSeriesValue.series_id == series_id))}


def test_ecos_call_plan_for_split_tables_and_regions():
    calls = pipeline._ecos_calls(get_spec("V066"), "2025-10", "2026-09")
    assert calls == [("901Y052", "A/I72BI/1", "2025-10", "2025-12", None), ("901Y148", "A/I72BI/1", "2026-01", "2026-09", None)]
    v050 = pipeline._ecos_calls(get_spec("V050"), "2025-10", "2026-09")
    assert len(v050) == 17 and v050[0] == ("151Y003", "11110A0/A00", "2025-10", "2026-09", "서울")
    assert ecos_period("2026Q2", "Q") == "2026Q2" and re.fullmatch(r"\d{4}Q[1-4]", pipeline.today_period("Q"))
    ecos = [s for s in enabled_specs("ECOS")]
    assert len({s.var_id for s in ecos}) == 21 and all(s.outputs for s in ecos)


def test_daily_refresh_writes_only_changes_and_extends_panel(db):
    spec = get_spec("V043")
    fake = FakeEcos({"0101000": {"2026-07": 2.5, "2026-08": 2.25, "2026-09": 2.25}})
    with Session(get_engine()) as s:
        r1 = pipeline.refresh_variable(s, spec, force=True, client=fake)
    assert r1["status"] == "ok" and r1["new"] == 3 and r1["changed"] == 0
    assert r1["panel_written"] == 2  # 2026-07 은 패널 값과 같아 쓰지 않음, 08 수정 + 09 새로
    sid = "nation:V043_한국은행_기준금리_연%"
    v = values(sid)
    assert v[("전국", "2026-06")] == 2.5 and v[("전국", "2026-08")] == 2.25 and v[("전국", "2026-09")] == 2.25
    with Session(get_engine()) as s:
        assert s.get(IndicatorSeries, sid).periods == ["2026-06", "2026-07", "2026-08", "2026-09"]
        r2 = pipeline.refresh_variable(s, spec, force=True, client=fake)  # 다음 날: 같은 자료
    assert (r2["new"], r2["changed"], r2["unchanged"], r2["panel_written"]) == (0, 0, 3, 0)
    fake.data["0101000"]["2026-09"] = 2.0  # 공표 뒤 수정
    with Session(get_engine()) as s:
        r3 = pipeline.refresh_variable(s, spec, force=True, client=fake)
    assert (r3["new"], r3["changed"], r3["panel_written"]) == (0, 1, 1) and values(sid)[("전국", "2026-09")] == 2.0


def test_outputs_rename_match_and_region_filter(db):
    fake = FakeEcos({"FMFB/F0001": {"2026-09": 133.0}, "1110000": {"2026-09": 103.0}, "11100A0": {"2026-09": 73.0},
                     "*": {"2026-09": 9.0}})
    with Session(get_engine()) as s:
        for sid in ("V061", "V069.1", "V069.2", "V050"):
            assert pipeline.refresh_variable(s, get_spec(sid), force=True, client=fake)["status"] == "ok"
    assert values("nation:V061_주택가격전망CSI_서울")[("서울 권역", "2026-09")] == 133.0  # '전국' → '서울 권역'
    assert values("nation:V069_가계대출(전체)_십억원")[("전국", "2026-09")] == 103.0
    assert values("nation:V069_가계대출(주택관련)_십억원")[("전국", "2026-09")] == 73.0
    sido = values("sido:V050_지역별주택관련대출_십억원")
    assert {r for r, p in sido if p == "2026-09"} == {"서울", "부산"}  # 화면이 쓰는 지역만 (17개 중 패널에 있는 2곳)
    assert values("seoul:서울_V050_지역별주택관련대출_십억원")[("서울", "2026-09")] == 9.0


def test_bundle_marks_api_series_and_refresh_by_source(db, monkeypatch):
    from app.main import app
    monkeypatch.setenv("POLICY_ADMIN_TOKEN", "t")
    fake = FakeEcos({"*": {"2026-08": 5.0, "2026-09": 5.0}})
    monkeypatch.setattr(pipeline, "make_client", lambda source: fake)
    with TestClient(app) as client:
        res = client.post("/indicators/refresh", params={"source": "ECOS", "force": "true"}, headers={"X-Admin-Token": "t"})
        body = res.json()
        assert res.status_code == 200 and body["changed"] > 0
        assert {get_spec(r["id"]).source for r in body["results"]} == {"ECOS"}
        bundle = client.get("/indicators/bundle", params={"set": "all"}).json()
        by = {m["column"]: m for m in bundle["metrics"]}
        v043 = by["V043_한국은행_기준금리_연%"]
        assert v043["live"] is True and v043["origin"] == "db(api)" and v043["periods"][-1] == "2026-09"
        assert v043["source"].startswith("ECOS 722Y001") and v043["fetched_at"]
        again = client.post("/indicators/refresh", params={"source": "ECOS", "force": "true"}, headers={"X-Admin-Token": "t"}).json()
        assert again["changed"] == 0  # 다음 날 같은 자료면 아무것도 쓰지 않는다


# ── R-ONE 묶음: 지역 계층 파싱 · 서울 구 · 미분양 0 채움 ──

def test_parse_rone_region_matches_dfmba_rules():
    from app.services.regions import parse_rone_region
    assert parse_rone_region("경기") == ("경기", "")
    assert parse_rone_region("전남광주>광주") == ("광주", "") and parse_rone_region("전남광주>(구)광주") == ("광주", "")
    assert parse_rone_region("경기>계") == ("경기", "")
    assert parse_rone_region("서울>강남지역>동남권>강남구") == ("서울", "강남구") and parse_rone_region("서울>마포구") == ("서울", "마포구")
    assert parse_rone_region("서울>강남지역") is None and parse_rone_region("부산>해운대구") is None
    assert parse_rone_region("전남광주") is None and parse_rone_region("수도권") is None


class FakeRoneTree:
    """R-ONE 실제 CLS_FULLNM 꼴(시도 · 권역 · 4단 계층 구 · '계' 합계행)."""
    def __init__(self, rows):
        self.rows = rows

    def fetch_rows(self, statbl_id, start, end, cycle="MM", cls_id=None, itm_id=None):
        return [{"WRTTIME_IDTFR_ID": p.replace("-", ""), "ITM_ID": "100001", "ITM_NM": item, "CLS_NM": full.split(">")[-1],
                 "CLS_FULLNM": full, "DTA_VAL": str(v)} for full, p, v, item in self.rows if start <= p <= end]


def test_rone_rows_keep_sido_and_shown_gu_only(db):
    fake = FakeRoneTree([("서울", "2026-09", 103.0, "지수"), ("전남광주>광주", "2026-09", 99.0, "지수"), ("수도권", "2026-09", 101.0, "지수"),
                         ("서울>강남지역", "2026-09", 104.0, "지수"), ("서울>강남지역>동남권>강남구", "2026-09", 105.0, "지수"),
                         ("서울>강북지역>도심권>종로구", "2026-09", 98.0, "지수")])
    rows, item = pipeline._rone_rows(fake, get_spec("V002"), "2026-09", "2026-09", keep_gu={"강남구", "마포구"})
    assert sorted(rows) == [("강남구", "2026-09", 105.0), ("광주", "2026-09", 99.0), ("서울", "2026-09", 103.0)]
    rows, _ = pipeline._rone_rows(fake, get_spec("V001"), "2026-09", "2026-09")  # V001 은 서울 구를 받지 않는다
    assert {r for r, _, _ in rows} == {"서울", "광주"}


def test_unsold_zero_fill_when_gu_total_matches(db):
    from app.services.regions import SEOUL_GU
    base = [("서울>계", "2026-08", 30.0, "미분양현황"), ("서울>강남구", "2026-08", 10.0, "미분양현황"), ("서울>송파구", "2026-08", 20.0, "미분양현황"),
            ("서울>계", "2026-09", 50.0, "미분양현황"), ("서울>강남구", "2026-09", 10.0, "미분양현황")]  # 9월은 합계가 안 맞음
    rows, _ = pipeline._rone_rows(FakeRoneTree(base), get_spec("V038"), "2026-08", "2026-09", keep_gu={"강남구", "마포구"})
    got = {(r, p): v for r, p, v in rows}
    assert got[("마포구", "2026-08")] == 0.0 and got[("강남구", "2026-08")] == 10.0
    assert ("마포구", "2026-09") not in got  # 구 합계 ≠ 서울 값이면 채우지 않는다
    assert not any(r == "송파구" for r, _ in got) and len(SEOUL_GU) == 25
