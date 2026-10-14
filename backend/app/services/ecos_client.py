"""한국은행 ECOS Open API 클라이언트.

호출 규격 (https://ecos.bok.or.kr/api/#/DevGuide/StatisticalCodeSearch)
  GET https://ecos.bok.or.kr/api/StatisticSearch/{인증키}/json/kr/{시작행}/{끝행}/{통계표코드}/{주기}/{시작}/{끝}/{항목코드1}
      주기 D·M·Q·A, 시작·끝은 주기에 맞춰 YYYYMMDD·YYYYMM·YYYYQn·YYYY
응답
  {"StatisticSearch": {"list_total_count": N,
                       "row": [{"STAT_CODE", "STAT_NAME", "ITEM_CODE1", "ITEM_NAME1", "UNIT_NAME",
                                "TIME": "202608", "DATA_VALUE": "2.5"}, …]}}
  오류는 {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}} 로 온다.

인증키는 환경변수 ECOS_API_KEY 로만 읽는다 (.env 는 app.main 이 로딩).
"""

import os

import pandas as pd
import requests

_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
TIMEOUT = 20
NO_DATA_CODES = {"INFO-200"}


class EcosError(RuntimeError):
    pass


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _period_param(period: str, freq: str) -> str:
    """'2016-01' → '201601' (M) / '2016' (A) / '2016-Q1' → '2016Q1' (Q) / '2016-01-05' → '20160105' (D)."""
    s = period.replace("-", "")
    return {"A": s[:4], "M": s[:6], "D": s[:8]}.get(freq, s)


class EcosClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._key = api_key or os.getenv("ECOS_API_KEY", "").strip()
        if not self._key:
            raise ValueError("ECOS_API_KEY가 설정되지 않았습니다.")
        self._http = session or requests.Session()

    def fetch_rows(self, stat_code: str, item_code: str, start: str, end: str, freq: str = "M") -> list[dict]:
        """통계표·항목 하나의 행(TIME·DATA_VALUE …)을 받아온다."""
        url = f"{_BASE_URL}/{self._key}/json/kr/1/10000/{stat_code}/{freq}/{_period_param(start, freq)}/{_period_param(end, freq)}/{item_code}"
        resp = self._http.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "StatisticSearch" not in data:
            result = data.get("RESULT", {})
            if result.get("CODE") in NO_DATA_CODES:
                return []
            raise EcosError(f"ECOS 응답 오류 ({stat_code}/{item_code}): {result or data}")
        return data["StatisticSearch"].get("row", [])

    def get_series(self, stat_code: str, item_code: str, start_date: str, end_date: str, freq: str = "M") -> pd.Series:
        """pandas Series 로 받는다 (mypage 시절 인터페이스 유지)."""
        rows = self.fetch_rows(stat_code, item_code, start_date, end_date, freq)
        fmt_map = {"D": "%Y%m%d", "M": "%Y%m", "A": "%Y"}
        series = pd.Series({row["TIME"]: _to_float(row["DATA_VALUE"]) for row in rows}, name=item_code, dtype="float64")
        if len(series):
            series.index = pd.to_datetime(series.index, format=fmt_map.get(freq, "%Y%m%d"))
        return series.sort_index()


def to_period(time_value: str, freq: str = "M") -> str:
    """'202608' → '2026-08', '2026Q1' → '2026-Q1', '2026' → '2026'."""
    s = str(time_value).strip()
    if freq == "M" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if freq == "Q" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if freq == "D" and len(s) >= 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:4]
