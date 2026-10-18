"""국토부 실거래 이후분: 응답 읽기·세기, 다시 받을 순서, 호출 상한·한도, 시도 합계 조건, 화면 계열 반영. 외부 API 는 부르지 않는다."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.models import IndicatorSeries
from app.db.session import get_engine
from app.services import cache, rtms
from app.services import indicator_pipeline as pipeline
from app.services.indicator_panel import panel_metrics, seed_panel
from app.services.sgg_codes import SGG

TODAY = date(2026, 10, 18)
SEJONG = "36110"  # 세종은 시군구가 하나라 시도 합계 조건을 보기 쉽다
GANGNAM = "11680"


@pytest.fixture
def db(local_database, monkeypatch):
    cache.clear()
    monkeypatch.setattr(rtms, "utc_now", lambda: "2026-10-18T01:00:00+00:00")  # 조회 시각 고정(다시 받을 주기 계산)
    yield
    cache.clear()


def xml(items, total=None, code="000"):
    body = "".join("<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in it.items()) + "</item>" for it in items)
    return (f"<response><header><resultCode>{code}</resultCode><resultMsg>OK</resultMsg></header>"
            f"<body><items>{body}</items><totalCount>{len(items) if total is None else total}</totalCount></body></response>").encode()


class Resp:
    def __init__(self, content, status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        pass


class Http:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self.pages.pop(0)


def test_count_rules():
    rent = [{"monthlyRent": "0"}, {"monthlyRent": "50"}, {"monthlyRent": "1,200"}]
    assert rtms.count_rows("apt_rent", rent) == {"count_all": 3, "count_monthly": 2, "count_jeonse": 1, "count_canceled": 0}
    trade = [{"cdealType": ""}, {"cdealType": "O"}, {}]
    assert rtms.count_rows("apt_trade", trade) == {"count_all": 2, "count_monthly": 0, "count_jeonse": 0, "count_canceled": 1}


def test_client_pages_no_data_and_quota():
    page1 = [{"monthlyRent": "0"}] * 1000
    http = Http([Resp(xml(page1, total=1500)), Resp(xml([{"monthlyRent": "10"}] * 500, total=1500))])
    c = rtms.RtmsClient(api_key="k", session=http, pause=0)
    items, used = c.fetch_month("apt_rent", GANGNAM, "202609")
    assert len(items) == 1500 and used == 2 and http.calls[1]["pageNo"] == 2 and http.calls[0]["LAWD_CD"] == GANGNAM
    assert rtms.RtmsClient(api_key="k", session=Http([Resp(xml([], code="03"))]), pause=0).fetch_month("apt_rent", SEJONG, "202609") == ([], 1)
    with pytest.raises(rtms.RtmsQuotaError):
        rtms.RtmsClient(api_key="k", session=Http([Resp(xml([], code="22"))]), pause=0).fetch_month("apt_trade", SEJONG, "202609")
    with pytest.raises(rtms.RtmsQuotaError):
        rtms.RtmsClient(api_key="k", session=Http([Resp(b"", status=429)]), pause=0).fetch_month("apt_trade", SEJONG, "202609")
    # 인증키 오류는 0건이 아니라 오류로 — 그래야 시도 합계를 0 으로 덮어쓰지 않는다
    bad_key = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
               b"<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode>"
               b"</cmmMsgHeader></OpenAPI_ServiceResponse>")
    with pytest.raises(rtms.RtmsError, match="SERVICE_KEY_IS_NOT_REGISTERED"):
        rtms.RtmsClient(api_key="k", session=Http([Resp(bad_key)]), pause=0).fetch_month("apt_rent", SEJONG, "202609")
    quota = bad_key.replace(b"SERVICE_KEY_IS_NOT_REGISTERED_ERROR", b"LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR").replace(b">30<", b">22<")
    with pytest.raises(rtms.RtmsQuotaError):
        rtms.RtmsClient(api_key="k", session=Http([Resp(quota)]), pause=0).fetch_month("apt_rent", SEJONG, "202609")


def test_plan_order_and_intervals(db):
    with Session(get_engine()) as s:
        rtms._save(s, "apt_rent", [(SEJONG, "202610", rtms.count_rows("apt_rent", []), 1)])
        first = rtms.plan(s, "apt_rent", TODAY, window=2, codes=[SEJONG, GANGNAM])
        # 한 번도 안 받은 것부터, 최근 달 먼저. 오늘 받은 세종 2026-10 은 빠진다
        assert first == [(GANGNAM, "202610"), (GANGNAM, "202609"), (SEJONG, "202609")]
        later = rtms.plan(s, "apt_rent", date(2026, 10, 20), window=2, codes=[SEJONG])
        assert (SEJONG, "202610") in later  # 이번 달은 하루마다 다시


class FakeRtms:
    def __init__(self, n=3, quota_after=None):
        self.calls, self.n, self.quota_after = 0, n, quota_after

    def fetch_month(self, kind, cd, ym):
        if self.quota_after is not None and self.calls >= self.quota_after:
            raise rtms.RtmsQuotaError("한도")
        self.calls += 1
        return [{"monthlyRent": "10", "cdealType": ""}] * self.n, 1


def test_collect_respects_budget_and_quota(db):
    with Session(get_engine()) as s:
        out = rtms.collect(s, ["apt_rent"], budget=5, window=1, client=FakeRtms(), today=TODAY, log=lambda m: None)
        assert out["apt_rent"]["fetched"] == 5 and out["apt_rent"]["stopped"] == "budget" and out["apt_rent"]["changed"] == 5
        out = rtms.collect(s, ["apt_rent", "apt_trade"], budget=1000, window=1, client=FakeRtms(quota_after=3), today=TODAY,
                           log=lambda m: None)
        assert out["apt_rent"]["stopped"].startswith("quota") and "apt_trade" not in out  # 같은 키라 다음 유형도 멈춘다
        st = rtms.status(s, TODAY, window=1)
        assert st["apt_rent"]["202610"]["sgg"] == 8 and st["apt_rent"]["202610"]["of"] == len(SGG)


def test_aggregate_sido_only_when_complete(db):
    with Session(get_engine()) as s:
        rows = [(cd, "202609", {"count_all": 2, "count_monthly": 1, "count_jeonse": 1, "count_canceled": 0}, 1)
                for cd, (sido, _) in SGG.items() if sido in ("세종", "서울")]
        rows = [r for r in rows if r[0] != "11110"]  # 종로구가 빠지면 서울 합계는 아직 내지 않는다
        rtms._save(s, "apt_rent", rows)
        agg = rtms.aggregate(s, "apt_rent", "count_monthly", keep_gu={"강남구"})
        assert agg[("세종", "2026-09")] == 1.0 and agg[("강남구", "2026-09")] == 1.0
        assert ("서울", "2026-09") not in agg and ("마포구", "2026-09") not in agg
        rtms._save(s, "apt_rent", [("11110", "202609", {"count_all": 2, "count_monthly": 1, "count_jeonse": 1, "count_canceled": 0}, 1)])
        assert rtms.aggregate(s, "apt_rent", "count_all")[("서울", "2026-09")] == 50.0


def test_molit_spec_updates_panel_and_provisional(db, monkeypatch):
    """수집한 건수가 화면 계열(V006 월세)에 이어붙고, 마지막 3개월이 잠정으로 옮겨 간다. 이번 달은 내지 않는다."""
    monkeypatch.setattr(pipeline, "today_period", lambda freq="M": "2026-10" if freq == "M" else "2026")
    p = ["2026-07", "2026-08"]
    col = "V006_국토부실거래_아파트전월세_월세(보증부포함)_건"
    data = {"generated": "t", "aliases": {}, "regions": {"sido": ["세종"], "gu": ["강남구"]}, "metrics": [
        {"var": "V006", "column": col, "label": "월세", "unit": "건", "freq": "M", "scope": "sido", "periods": p,
         "series": {"세종": [10.0, 11.0]}, "provisional_from": "2026-08"},
        {"var": "V006", "column": col, "label": "월세", "unit": "건", "freq": "M", "scope": "gu", "periods": p,
         "series": {"강남구": [20.0, 21.0]}, "provisional_from": "2026-07"}]}
    with Session(get_engine()) as s:
        seed_panel(s, data)
        counts = lambda m: {"count_all": m + 1, "count_monthly": m, "count_jeonse": 1, "count_canceled": 0}  # noqa: E731
        rtms._save(s, "apt_rent", [(SEJONG, "202608", counts(12), 1), (SEJONG, "202609", counts(13), 1), (SEJONG, "202610", counts(2), 1),
                                   (GANGNAM, "202609", counts(30), 1)])
        r = pipeline.refresh_variable(s, pipeline.get_spec("V006.2"), force=True, client="rtms_progress")
        assert r["status"] == "ok" and r["last_period"] == "2026-09"
        ms = {m["scope"]: m for m in panel_metrics(s, ["V006"])}
        assert ms["sido"]["periods"] == ["2026-07", "2026-08", "2026-09"]
        assert ms["sido"]["series"]["세종"] == [10.0, 12.0, 13.0]  # 8월은 수정, 9월은 새로, 10월(이번 달)은 내지 않음
        assert ms["gu"]["series"]["강남구"] == [20.0, 21.0, 30.0]
        assert s.get(IndicatorSeries, f"sido:{col}").provisional_from == "2026-07"  # 3개월 [7,8,9] → 7월부터


def test_molit_recomputes_even_when_recently_run(db, monkeypatch):
    """실거래 합계는 DB 만 읽으므로 '신선함' 으로 건너뛰지 않는다 — 방금 받은 건수가 같은 날 바로 반영돼야 한다."""
    monkeypatch.setattr(pipeline, "today_period", lambda freq="M": "2026-10" if freq == "M" else "2026")
    with Session(get_engine()) as s:
        spec = pipeline.get_spec("V007")
        assert pipeline.refresh_variable(s, spec, client="rtms_progress")["status"] == "ok"  # 처음: 건수 없음
        rtms._save(s, "apt_trade", [(SEJONG, "202609", rtms.count_rows("apt_trade", [{}] * 4), 1)])
        r = pipeline.refresh_variable(s, spec, client="rtms_progress")  # force 없이 곧바로 다시
        assert r["status"] == "ok" and r["new"] == 1 and r["last_period"] == "2026-09"


def test_rtms_job_endpoints(db, monkeypatch):
    """Actions 는 비밀값 없이 API 서버에 실거래 수집을 맡긴다: 시작(202) → 진행 상태 확인 → 끝나면 요약. 키는 응답에 나오지 않는다."""
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("POLICY_ADMIN_TOKEN", "t0ken")
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "SECRET-KEY-123")
    monkeypatch.setattr(rtms, "RtmsClient", lambda: FakeRtms(n=2))
    with TestClient(app) as client:
        assert client.post("/indicators/rtms/collect").status_code == 401
        assert client.get("/indicators/rtms/job").status_code == 401
        res = client.post("/indicators/rtms/collect", params={"budget": 3, "window": 1}, headers={"X-Admin-Token": "t0ken"})
        assert res.status_code == 202 and res.json()["running"] is True and res.json()["budget"] == 3
        rtms._thread.join(timeout=30)
        st = client.get("/indicators/rtms/job", headers={"X-Admin-Token": "t0ken"})
        body = st.json()
        assert st.status_code == 200 and body["running"] is False and body["error"] is None
        assert body["result"]["apt_rent"]["fetched"] == 3 and body["result"]["apt_rent"]["stopped"] == "budget"
        assert body["lines"] > 0 and "SECRET-KEY-123" not in st.text
        monkeypatch.delenv("DATA_GO_KR_API_KEY")
        assert client.post("/indicators/rtms/collect", headers={"X-Admin-Token": "t0ken"}).status_code == 503


def test_rtms_redacts_service_key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "abc%2Bdef")
    assert rtms._redact("GET /x?serviceKey=abc%2Bdef&LAWD_CD=11110 failed") == "GET /x?serviceKey=***&LAWD_CD=11110 failed"
    assert rtms._redact("key abc%2Bdef leaked") == "key *** leaked"
