from datetime import date

import pytest
import requests
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

from app.services import rone_collector as rc
from app.services.rone_client import RoneClient, RoneError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, pages=None, exc=None):
        self.pages, self.exc, self.calls = pages or [], exc, []

    def get(self, url, params, timeout):
        self.calls.append(params)
        if self.exc:
            raise self.exc
        return FakeResponse(self.pages[len(self.calls) - 1])


def page(total, rows):
    return {"SttsApiTblData": [{"head": [{"list_total_count": total}, {"RESULT": {"CODE": "INFO-000"}}]}, {"row": rows}]}


def row(period="202609", cls_id=500001, nm="전국", full="전국", value=101.38):
    return {"STATBL_ID": "A_2024_00055", "WRTTIME_IDTFR_ID": period, "CLS_ID": cls_id, "CLS_NM": nm,
            "CLS_FULLNM": full, "ITM_ID": 100001, "ITM_NM": "지수", "DTA_VAL": value, "UI_NM": "지수"}


def test_client_follows_pages_until_total():
    session = FakeSession([page(3, [row(), row()]), page(3, [row()])])
    rows = RoneClient("k", session).rows("SttsApiTblData", {"STATBL_ID": "A_2024_00055"}, size=2)
    assert len(rows) == 3
    assert [c["pIndex"] for c in session.calls] == [1, 2]


def test_client_no_data_is_empty():
    session = FakeSession([{"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}])
    assert RoneClient("k", session).table_data("A_2024_00054", period="201505") == []


def test_client_error_code_raises():
    session = FakeSession([{"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}}])
    with pytest.raises(RoneError, match="ERROR-290"):
        RoneClient("k", session).tables()


def test_client_hides_key_in_network_error():
    secret = "SECRET-KEY-123"
    session = FakeSession(exc=requests.ConnectionError(f"failed https://x/?KEY={secret}"))
    with pytest.raises(RoneError) as err:
        RoneClient(secret, session).tables()
    assert secret not in str(err.value)


def test_client_requires_key(monkeypatch):
    monkeypatch.delenv("RONE_API_KEY", raising=False)
    with pytest.raises(RoneError, match="RONE_API_KEY"):
        RoneClient()


def test_recent_months_crosses_year():
    assert rc.recent_months(3, today=date(2026, 2, 17)) == ["202512", "202601", "202602"]


def test_convert_keeps_latest_region_name_and_dedups():
    rows = [
        row("202512", 500021, "전남", "전남"),
        row("202609", 500021, "전남", "전남광주>전남"),
        row("202609", 500021, "전남", "전남광주>전남", value=102.4),  # 같은 키 중복: 마지막 값
        row("202609", 530011, "종로구", "서울>강북지역>도심권>종로구", value=""),
    ]
    regions, obs = rc.convert(rows)
    jeonnam = next(r for r in regions if r["cls_id"] == 500021)
    assert jeonnam["cls_fullnm"] == "전남광주>전남"
    assert (jeonnam["first_seen"], jeonnam["last_seen"]) == (date(2025, 12, 1), date(2026, 9, 1))
    assert next(r for r in regions if r["cls_id"] == 530011)["rone_level"] == 3
    assert len(obs) == 3
    assert next(o for o in obs if o["cls_id"] == 500021 and o["period"] == date(2026, 9, 1))["value"] == 102.4
    assert next(o for o in obs if o["cls_id"] == 530011)["value"] is None


def test_convert_unnamed_region_uses_last_name_or_placeholder():
    rows = [
        row("202606", 510022, "미추홀구", "인천>미추홀구"),
        {**row("202609", 510022), "CLS_NM": None, "CLS_FULLNM": None},
        {**row("202607", 510020), "CLS_NM": None, "CLS_FULLNM": None},
    ]
    regions, _ = rc.convert(rows)
    by_id = {r["cls_id"]: r for r in regions}
    assert by_id[510022]["cls_fullnm"] == "인천>미추홀구"
    assert by_id[510022]["last_seen"] == date(2026, 9, 1)
    assert by_id[510020]["cls_nm"] == rc.UNNAMED
    assert "_named" not in by_id[510020]


def test_upsert_sql_renders_for_postgresql():
    _, obs = rc.convert([row()])
    stmt = insert(rc.observations).values(obs)
    stmt = stmt.on_conflict_do_update(
        index_elements=["statbl_id", "cls_id", "itm_id", "period"], set_={"value": stmt.excluded.value},
        where=rc.observations.c.value.is_distinct_from(stmt.excluded.value),
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (statbl_id, cls_id, itm_id, period) DO UPDATE" in sql
    assert "IS DISTINCT FROM" in sql


def test_collect_refuses_sqlite(local_database):
    with pytest.raises(RoneError, match="PostgreSQL"):
        rc.collect(client=object())
