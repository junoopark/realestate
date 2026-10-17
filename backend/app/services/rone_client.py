"""한국부동산원 R-ONE Open API 클라이언트.

통계표 목록(SttsApiTbl), 항목(SttsApiTblItm), 데이터(SttsApiTblData)를 같은 방식으로 호출한다.
응답 형식: {"<op>": [{"head": [{"list_total_count": n}, {"RESULT": {...}}]}, {"row": [...]}]}
데이터가 없으면 {"RESULT": {"CODE": "INFO-200", ...}} 만 온다.
인증키는 URL 파라미터로 가므로 오류 메시지에 URL을 그대로 남기지 않는다.
"""

import os

import requests

BASE_URL = "https://www.reb.or.kr/r-one/openapi"
PAGE_SIZE = 1000
NO_DATA = "INFO-200"


class RoneError(RuntimeError):
    pass


class RoneClient:
    def __init__(self, key=None, session=None, timeout=60):
        self.key = (key or os.getenv("RONE_API_KEY", "")).strip()
        if not self.key:
            raise RoneError("RONE_API_KEY가 설정되지 않았습니다. backend/.env 또는 서버 환경변수를 확인하세요.")
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

    def tables(self):
        return self.rows("SttsApiTbl", {})

    def table_data(self, statbl_id, cycle="MM", period=None):
        """period 를 주면 그 기준월(YYYYMM)만, 없으면 전체 기간을 받는다."""
        params = {"STATBL_ID": statbl_id, "DTACYCLE_CD": cycle}
        if period:
            params["WRTTIME_IDTFR_ID"] = period
        return self.rows("SttsApiTblData", params)
