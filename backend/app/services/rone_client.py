"""한국부동산원 R-ONE Open API 클라이언트.

호출 규격 (https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do)
  GET https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do
      ?KEY=인증키&Type=json&pIndex=1&pSize=1000
      &STATBL_ID=통계표ID&DTACYCLE_CD=MM&START_WRTTIME=201601&END_WRTTIME=202612
      [&CLS_ID=지역분류ID][&ITM_ID=항목ID]
응답
  {"SttsApiTblData": [{"head": [{"list_total_count": N}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]},
                      {"row": [{"STATBL_ID", "DTACYCLE_CD", "WRTTIME_IDTFR_ID": "202608", "WRTTIME_DESC",
                                "ITM_ID", "ITM_NM", "CLS_ID", "CLS_NM", "CLS_FULLNM", "UI_NM", "DTA_VAL": "101.2"}, …]}]}
  오류·안내는 {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}} 처럼 RESULT 만 온다.
  한 번에 최대 1,000행(ERROR-336), 일일 호출 한도 초과는 ERROR-337.

인증키는 환경변수 RONE_API_KEY 로만 읽는다 (.env 는 app.main 이 로딩).
"""

import os
import time

import requests

BASE_URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
PAGE_SIZE = 1000
TIMEOUT = 30
NO_DATA_CODES = {"INFO-200"}


class RoneError(RuntimeError):
    pass


def _period_param(period: str, cycle: str) -> str:
    """'2016-01' → '201601' (MM) / '2016' (YY) / '2016-Q1' → '20161' (QY)."""
    digits = period.replace("-", "").replace("Q", "")
    return {"YY": digits[:4], "MM": digits[:6]}.get(cycle, digits)


class RoneClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._key = api_key or os.getenv("RONE_API_KEY", "").strip()
        if not self._key:
            raise ValueError("RONE_API_KEY가 설정되지 않았습니다.")
        self._http = session or requests.Session()

    def _get(self, params: dict) -> dict:
        resp = self._http.get(BASE_URL, params={"KEY": self._key, "Type": "json", **params}, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = "utf-8"  # Type=json 응답의 한글 인코딩 선언이 빠져 있을 때가 있다
        try:
            return resp.json()
        except ValueError as exc:
            raise RoneError(f"R-ONE 응답이 JSON 이 아닙니다: {resp.text[:200]}") from exc

    def fetch_rows(self, statbl_id: str, start: str, end: str, cycle: str = "MM",
                   cls_id: str | None = None, itm_id: str | None = None) -> list[dict]:
        """통계표 한 개의 행을 전부 받아온다 (페이지를 넘기며 합친다)."""
        base = {"STATBL_ID": statbl_id, "DTACYCLE_CD": cycle,
                "START_WRTTIME": _period_param(start, cycle), "END_WRTTIME": _period_param(end, cycle),
                "pSize": PAGE_SIZE}
        if cls_id:
            base["CLS_ID"] = cls_id
        if itm_id:
            base["ITM_ID"] = itm_id
        rows: list[dict] = []
        page, total = 1, None
        while True:
            data = self._get({**base, "pIndex": page})
            if "RESULT" in data and "SttsApiTblData" not in data:
                code = data["RESULT"].get("CODE", "")
                if code in NO_DATA_CODES:
                    return rows
                raise RoneError(f"R-ONE {code}: {data['RESULT'].get('MESSAGE', '')}")
            parts = data.get("SttsApiTblData", [])
            for part in parts:
                for h in part.get("head", []):
                    if "list_total_count" in h:
                        total = int(h["list_total_count"])
                    result = h.get("RESULT")
                    if result and not str(result.get("CODE", "")).startswith("INFO-0"):
                        raise RoneError(f"R-ONE {result.get('CODE')}: {result.get('MESSAGE', '')}")
                rows.extend(part.get("row", []))
            if total is None or len(rows) >= total or not any("row" in p for p in parts):
                return rows
            page += 1
            time.sleep(0.2)  # 연속 호출 간격 — 일일 한도와 서버 부담을 줄인다

    def latest_periods(self, statbl_id: str, cycle: str = "MM", months: int = 2) -> list[dict]:
        """항목·지역 이름 확인용(--probe): 최근 몇 달치만 받는다."""
        from datetime import date
        today = date.today()
        y, m = today.year, today.month - months
        while m <= 0:
            y, m = y - 1, m + 12
        return self.fetch_rows(statbl_id, f"{y:04d}-{m:02d}", f"{today.year:04d}-{today.month:02d}", cycle)


def to_period(wrttime: str, cycle: str = "MM") -> str:
    """'202608' → '2026-08', '2026' → '2026', '20261'(분기) → '2026-Q1'."""
    s = str(wrttime).strip()
    if cycle == "MM" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if cycle == "QY" and len(s) >= 5:
        return f"{s[:4]}-Q{s[4]}"
    return s[:4]
