"""통계청 KOSIS 공유서비스 Open API 클라이언트 (2차 연동용).

호출 규격 (https://kosis.kr/openapi/ > 통계자료 > 파라미터 방식)
  GET https://kosis.kr/openapi/Param/statisticsParameterData.do
      ?method=getList&apiKey=인증키&format=json&jsonVD=Y
      &orgId=101&tblId=DT_1B26001_A01&itmId=T70&objL1=ALL&objL2=&…
      &prdSe=M&startPrdDe=201601&endPrdDe=202612
응답
  [{"PRD_DE": "202608", "DT": "1234", "C1": "11", "C1_NM": "서울특별시", "ITM_NM": "순이동자수", "UNIT_NM": "명", …}, …]
  오류는 {"err": "30", "errMsg": "…"} 꼴의 객체로 온다.

인증키는 환경변수 KOSIS_API_KEY 로만 읽는다.
"""

import os

import requests

BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
TIMEOUT = 30


class KosisError(RuntimeError):
    pass


class KosisClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._key = api_key or os.getenv("KOSIS_API_KEY", "").strip()
        if not self._key:
            raise ValueError("KOSIS_API_KEY가 설정되지 않았습니다.")
        self._http = session or requests.Session()

    def fetch_rows(self, org_id: str, tbl_id: str, itm_id: str, start: str, end: str,
                   prd_se: str = "M", obj_l1: str = "ALL", **obj) -> list[dict]:
        params = {"method": "getList", "apiKey": self._key, "format": "json", "jsonVD": "Y",
                  "orgId": org_id, "tblId": tbl_id, "itmId": itm_id, "objL1": obj_l1,
                  "prdSe": prd_se, "startPrdDe": start.replace("-", "")[:6], "endPrdDe": end.replace("-", "")[:6]}
        for i in range(2, 9):  # objL2 … objL8
            params[f"objL{i}"] = obj.get(f"obj_l{i}", "")
        resp = self._http.get(BASE_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            if str(data.get("err")) in {"30", "31"}:  # 자료 없음
                return []
            raise KosisError(f"KOSIS 오류 {data.get('err')}: {data.get('errMsg', '')}")
        return data


def to_period(prd_de: str, prd_se: str = "M") -> str:
    s = str(prd_de).strip()
    if prd_se == "M" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if prd_se == "Q" and len(s) >= 5:  # 기본 패널과 같은 표기 2026Q1
        return f"{s[:4]}Q{s[4]}"
    return s[:4]
