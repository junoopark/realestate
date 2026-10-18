"""KOSIS 묶음: 시점 표기, 광주·전남 복원, 표별 가공(reader), 레지스트리 ↔ 기본 패널 연결. 외부 기관은 부르지 않는다."""

import json
from pathlib import Path

import pytest

from app.services.indicator_registry import enabled_specs, get_spec
from app.services.kosis_client import KosisClient, KosisError, _year_chunks, period_param, to_period
from app.services.kosis_readers import read, restore_gwangju_jeonnam

SAMPLE = Path(__file__).resolve().parents[2] / "frontend" / "data" / "factor_sample.json"
GU = {"강남구", "마포구", "노원구"}


class FakeKosis:
    """KOSIS 대신 미리 넣은 행을 돌려준다. 요청 기간(startPrdDe~endPrdDe)과 objL1 코드만 거른다."""

    def __init__(self, tables: dict):
        self.tables, self.calls = tables, []

    def fetch(self, org_id, tbl_id, itm_id, prd_se, start, end, obj=None, chunk_years=None):
        self.calls.append(tbl_id)
        s, e = period_param(start, prd_se), period_param(end, prd_se)
        codes = (obj or {}).get("objL1", "ALL")
        keep = None if codes == "ALL" else set(codes.strip("+").split("+"))
        return [r for r in self.tables.get(tbl_id, []) if s <= r["PRD_DE"] <= e and (keep is None or r.get("C1") in keep)]


def row(prd, c1, dt, **kw):
    return {"PRD_DE": prd, "C1": c1, "DT": str(dt), **kw}


def test_period_formats_round_trip():
    assert period_param("2016-01", "M") == "201601" and to_period("202608", "M") == "2026-08"
    assert period_param("2026Q2", "Q") == "202602" and to_period("202602", "Q") == "2026Q2"  # KOSIS 분기는 YYYY0q
    assert period_param("2021H2", "H") == "202102" and to_period("202102", "H") == "2021H2"
    assert period_param("2016", "Y") == "2016" and to_period("2024", "Y") == "2024"
    assert _year_chunks("2016-03", "2020-05", "M", 2) == [("201603", "201712"), ("201801", "201912"), ("202001", "202005")]
    assert _year_chunks("2016-03", "2016-05", "M", None) == [("201603", "201605")]


def test_gwangju_jeonnam_restored_after_merger():
    by_code = {"12": 3157777, "12210": 105344, "12240": 274408, "12270": 205428, "12300": 416780, "12330": 382841}
    assert restore_gwangju_jeonnam(by_code) == {"광주": 1384801, "전남": 1772976}
    # 순이동 표는 통합 뒤에도 옛 코드(29·46)가 0 으로 온다 → 옛 코드 대신 복원값
    moved = {"29": 0, "46": 0, "12": -444, "12210": 174, "12240": -203, "12270": -173, "12300": 41, "12330": -385}
    assert restore_gwangju_jeonnam(moved) == {"광주": -546, "전남": 102}
    assert restore_gwangju_jeonnam({"29": 10, "46": 20}) == {}  # 통합 전


def test_admin_reader_sido_gu_and_restoration():
    rows = [row("202606", "11", 9300000, ITM_ID="T20"), row("202606", "29", 1385460, ITM_ID="T20"),
            row("202606", "46", 1773650, ITM_ID="T20"), row("202606", "11680", 550000, ITM_ID="T20"),
            row("202606", "11110", 140000, ITM_ID="T20"),  # 종로구: 화면에 없는 구
            row("202607", "11", 9299000, ITM_ID="T20"), row("202607", "12", 3157777, ITM_ID="T20"),
            *[row("202607", c, v, ITM_ID="T20") for c, v in zip(("12210", "12240", "12270", "12300", "12330"),
                                                                (105344, 274408, 205428, 416780, 382841))]]
    out, _ = read(FakeKosis({"DT_1B040A3": rows}), get_spec("V009"), "2026-06", "2026-07", keep_gu=GU)
    got = {(r, p): v for r, p, v in out}
    assert got[("광주", "2026-06")] == 1385460 and got[("광주", "2026-07")] == 1384801 and got[("전남", "2026-07")] == 1772976
    assert got[("강남구", "2026-06")] == 550000 and ("종로구", "2026-06") not in got
    assert not any(r.startswith("12") or r == "전남광주" for r, _ in got)


def test_age_reader_bands_and_share():
    ages = {"000": 1000, "1201": 10, "1305": 20, "1501": 30, "1605": 40}
    rows = [row("202608", "11", v, C2=c) for c, v in ages.items()]
    fake = FakeKosis({"DT_1B04006": rows})
    want = {"V011.1": 30, "V011.2": 70, "V011.3": 100, "V011.4": 10.0}
    for sid, v in want.items():
        out, _ = read(fake, get_spec(sid), "2026-08", "2026-08", keep_gu=GU)
        assert out == [("서울", "2026-08", v)], sid


def test_name_reader_ytd_ratio_and_merged_region_dropped():
    cum = [row(p, "x", v, C1_NM=n, ITM_ID="13103871090T1")
           for p, n, v in (("202601", "서울", 100), ("202602", "서울", 250), ("202604", "서울", 400),
                           ("202607", "전남광주", 999), ("202607", "수도권", 5000))]
    out, _ = read(FakeKosis({"DT_MLTM_1948": cum}), get_spec("V021"), "2026-02", "2026-07")
    # 1월은 누계 그대로, 2월은 차감, 3월 누계가 없으면 4월은 비운다. 통합·권역 행은 버린다
    assert sorted(out) == [("서울", "2026-01", 100), ("서울", "2026-02", 150)]
    grdp = [row("2024", "00", 45000, C1_NM="전국", ITM_ID="T1"), row("2024", "11", 54000, C1_NM="서울특별시", ITM_ID="T1"),
            row("2024", "11", 26000, C1_NM="서울특별시", ITM_ID="T3")]
    out, _ = read(FakeKosis({"DT_1C96": grdp}), get_spec("V015.2"), "2016", "2026")
    assert out == [("서울", "2024", pytest.approx(1.2))]


def test_per_household_and_link():
    permits = [row("2024", "001023", 120, C1_NM="강남구", ITM_ID="T001"), row("2024", "001", 900, C1_NM="서울시", ITM_ID="T001")]
    households = [row("202412", "11680", 240000), row("202411", "11680", 1)]
    out, item = read(FakeKosis({"DT_201004_O090005": permits, "DT_1B040B3": households}), get_spec("V024.3"), "2016", "2026",
                     keep_gu=GU)
    assert out == [("강남구", "2024", 0.5)] and "천 세대당" in item
    new = [row("201904", "A", 5150921.848), row("202001", "A", 5000000)]
    out, _ = read(FakeKosis({"DT_1L9V121": new}), get_spec("V074"), "2020Q1", "2026Q4")
    assert out == [("전국", "2020Q1", pytest.approx(5000000 * 0.9416781445361877))]


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _Session:
    def __init__(self, data):
        self.data, self.calls = data, 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return _Resp(self.data)


def test_client_caches_same_request_and_reports_cell_limit():
    s = _Session([{"PRD_DE": "202608", "C1": "11", "DT": "1"}])
    c = KosisClient(api_key="k", session=s)
    c.fetch("101", "DT_X", "T1+", "M", "2026-01", "2026-08", {"objL1": "ALL"})
    c.fetch("101", "DT_X", "T1+", "M", "2026-01", "2026-08", {"objL1": "ALL"})
    assert s.calls == 1
    with pytest.raises(KosisError, match="4만 셀"):
        KosisClient(api_key="k", session=_Session({"err": "31", "errMsg": "초과"})).fetch("101", "DT_X", "T1+", "M", "2026-01", "2026-08")
    assert KosisClient(api_key="k", session=_Session({"err": "30"})).fetch("101", "DT_X", "T1+", "M", "2026-01", "2026-08") == []


@pytest.mark.skipif(not SAMPLE.exists(), reason="frontend/data/factor_sample.json 없음")
def test_every_output_points_to_exactly_one_panel_series():
    """레지스트리의 outputs 가 실제 기본 패널(106개 계열)의 계열 하나씩을 가리킨다 — 화면 계열을 빠짐없이·겹치지 않게 갱신."""
    metrics = json.loads(SAMPLE.read_text(encoding="utf-8"))["metrics"]
    seen = {}
    for spec in enabled_specs():
        for o in spec.outputs:
            cands = [m for m in metrics if m["var"] == spec.var_id and m["scope"] == o.scope and (not o.match or o.match in m["column"])]
            assert len(cands) == 1, (spec.id, o.scope, o.match, [m["column"] for m in cands])
            key = f"{o.scope}:{cands[0]['column']}"
            assert key not in seen, (spec.id, seen.get(key))
            seen[key] = spec.id
    assert len([s for s in enabled_specs("KOSIS")]) >= 30
