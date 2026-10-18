"""R-ONE Open API 클라이언트(rone_client) 단위 테스트. 지표 수집(indicator_pipeline)이 이 클라이언트를 쓴다."""
import pytest
import requests

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
