"""한국부동산원 R-ONE Open API 클라이언트.

통계표 목록(SttsApiTbl), 항목(SttsApiTblItm), 데이터(SttsApiTblData)를 같은 방식으로 호출한다.
응답 형식: {"<op>": [{"head": [{"list_total_count": n}, {"RESULT": {...}}]}, {"row": [...]}]}
데이터가 없으면 {"RESULT": {"CODE": "INFO-200", ...}} 만 온다. 일일 호출 한도 초과는 ERROR-337.
인증키는 URL 파라미터로 가므로 오류 메시지에 URL을 그대로 남기지 않는다.

이 클라이언트를 쓰는 곳 (R-ONE 호출 코드는 이 파일 하나로 통일)
- rone_collector.py      월세지수 원값 적재      rows · tables · table_data(기준월 1개)
- indicator_pipeline.py  정량 지표 레지스트리    fetch_rows(기간 범위) · latest_periods(--probe)
"""

import os
import time
from datetime import date

import requests

BASE_URL = "https://www.reb.or.kr/r-one/openapi"
PAGE_SIZE = 1000
NO_DATA = "INFO-200"
PAGE_PAUSE = 0.2  # 페이지 사이 간격(초). 일일 한도와 서버 부담을 줄인다


class RoneError(RuntimeError):
    pass


class RoneKeyError(RoneError, ValueError):
    """인증키 미설정. ValueError 이기도 해서, 다른 출처(ECOS·KOSIS)와 같은 방식으로 '키 없음'을 처리할 수 있다."""


def _period_param(period, cycle="MM"):
    """'2016-01' → '201601' (MM) / '2016' (YY) / '2016-Q1' → '20161' (QY)."""
    digits = str(period).replace("-", "").replace("Q", "")
    return {"YY": digits[:4], "MM": digits[:6]}.get(cycle, digits)


class RoneClient:
    def __init__(self, key=None, session=None, timeout=60, api_key=None):
        self.key = (key or api_key or os.getenv("RONE_API_KEY", "")).strip()
        if not self.key:
            raise RoneKeyError("RONE_API_KEY가 설정되지 않았습니다. backend/.env 또는 서버 환경변수를 확인하세요.")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _hide_key(self, text):
        return str(text).replace(self.key, "***")

    def page(self, op, params, index=1, size=PAGE_SIZE):
        """한 페이지를 받아 (전체 건수, 행 목록)을 돌려준다."""
        query = {"KEY": self.key, "Type": "json", "pIndex": index, "pSize": size, **params}
        try:
            res = self.session.get(f"{BASE_URL}/{op}.do", params=query, timeout=self.timeout)
            res.raise_for_status()
            res.encoding = "utf-8"  # Type=json 응답의 문자셋 선언이 빠지거나 틀릴 때가 있다
            body = res.json()
        except (requests.RequestException, ValueError) as exc:
            raise RoneError(f"R-ONE {op} 호출 실패: {self._hide_key(exc)}") from None

        if "RESULT" in body:  # 데이터 없음 또는 인증·파라미터 오류
            result = body["RESULT"]
            if result.get("CODE") == NO_DATA:
                return 0, []
            raise RoneError(f"R-ONE {op} 오류 {result.get('CODE')}: {result.get('MESSAGE')}")

        parts = body.get(op)
        if not parts:
            raise RoneError(f"R-ONE {op} 응답 형식이 예상과 다릅니다.")
        head = parts[0].get("head", [])
        total = next((h["list_total_count"] for h in head if "list_total_count" in h), 0)
        result = next((h["RESULT"] for h in head if "RESULT" in h), {})
        if result.get("CODE") not in (None, "INFO-000"):
            raise RoneError(f"R-ONE {op} 오류 {result.get('CODE')}: {result.get('MESSAGE')}")
        rows = parts[1].get("row", []) if len(parts) > 1 else []
        return int(total), rows

    def rows(self, op, params, size=PAGE_SIZE):
        """모든 페이지를 이어 받는다."""
        out, index = [], 1
        while True:
            total, rows = self.page(op, params, index, size)
            out.extend(rows)
            if not rows or len(out) >= total:
                return out
            index += 1
            time.sleep(PAGE_PAUSE)

    def tables(self):
        return self.rows("SttsApiTbl", {})

    def table_data(self, statbl_id, cycle="MM", period=None):
        """period 를 주면 그 기준월(YYYYMM)만, 없으면 전체 기간을 받는다."""
        params = {"STATBL_ID": statbl_id, "DTACYCLE_CD": cycle}
        if period:
            params["WRTTIME_IDTFR_ID"] = period
        return self.rows("SttsApiTblData", params)

    def fetch_rows(self, statbl_id, start, end, cycle="MM", cls_id=None, itm_id=None):
        """기간 범위(START_WRTTIME~END_WRTTIME)의 행을 모두 받는다. start·end 는 'YYYY-MM'."""
        params = {"STATBL_ID": statbl_id, "DTACYCLE_CD": cycle,
                  "START_WRTTIME": _period_param(start, cycle), "END_WRTTIME": _period_param(end, cycle)}
        if cls_id:
            params["CLS_ID"] = cls_id
        if itm_id:
            params["ITM_ID"] = itm_id
        return self.rows("SttsApiTblData", params)

    def latest_periods(self, statbl_id, cycle="MM", months=2):
        """항목·지역 이름 확인용(--probe): 최근 몇 달치만 받는다."""
        today = date.today()
        y, m = today.year, today.month - months
        while m <= 0:
            y, m = y - 1, m + 12
        return self.fetch_rows(statbl_id, f"{y:04d}-{m:02d}", f"{today.year:04d}-{today.month:02d}", cycle)


def to_period(wrttime, cycle="MM"):
    """'202608' → '2026-08', '2026' → '2026', '20261'(분기) → '2026Q1'. (정량 지표 테이블의 시점 표기)"""
    s = str(wrttime).strip()
    if cycle == "MM" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if cycle == "QY" and len(s) >= 5:  # 기본 패널과 같은 표기 2026Q1
        return f"{s[:4]}Q{s[4]}"
    return s[:4]
