"""통계청 KOSIS 공유서비스 Open API 클라이언트.

호출 규격 (https://kosis.kr/openapi/ > 통계자료 > 파라미터 방식)
  GET https://kosis.kr/openapi/Param/statisticsParameterData.do
      ?method=getList&apiKey=인증키&format=json&jsonVD=Y
      &orgId=101&tblId=DT_1B26001_A01&itmId=T25+&objL1=ALL&objL2=&…
      &prdSe=M&startPrdDe=201601&endPrdDe=202612
응답
  [{"PRD_DE": "202608", "DT": "1234", "C1": "11", "C1_NM": "서울특별시", "ITM_ID": "T25", "ITM_NM": "순이동", …}, …]
  오류는 {"err": "30", "errMsg": "…"} 꼴의 객체로 온다. 30 = 조회 결과 없음, 31 = 4만 셀 초과.

시점 파라미터 (DFMBA collect_kosis.py 와 같다)
  월 M: 201601 · 분기 Q: 201601(1분기)~201604(4분기) · 반기 H: 202101(상반기)·202102(하반기) · 연 Y: 2016

한 번에 4만 셀까지만 주므로 긴 기간은 연 단위로 나눠 받는다(chunk_years).
같은 표를 여러 수집 단위가 나눠 쓰므로(예: V011 연령대 4개 계열) 같은 요청은 한 번만 보내고 결과를 재사용한다.
인증키는 환경변수 KOSIS_API_KEY 로만 읽는다. 오류 메시지에 키를 남기지 않는다.
"""

import os
import time

import requests

BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
TIMEOUT = 60
PAUSE = 0.2  # 요청 사이 간격(초)


class KosisError(RuntimeError):
    pass


def period_param(period: str, prd_se: str) -> str:
    """'2016-01'(M) → '201601', '2016Q1'(Q) → '201601', '2021H2'(H) → '202102', '2016'(Y) → '2016'."""
    s = str(period).strip()
    if prd_se == "M":
        return s.replace("-", "")[:6]
    if prd_se == "Q":
        return f"{s[:4]}{int(s[5]):02d}" if "Q" in s else s[:6]
    if prd_se == "H":
        return f"{s[:4]}{int(s[5]):02d}" if "H" in s else s[:6]
    return s[:4]


def to_period(prd_de: str, prd_se: str = "M") -> str:
    """KOSIS PRD_DE → 기본 패널 표기. 202608 → 2026-08 · 202601(Q) → 2026Q1 · 202102(H) → 2021H2 · 2024 → 2024."""
    s = str(prd_de).strip()
    if prd_se == "M" and len(s) >= 6:
        return f"{s[:4]}-{s[4:6]}"
    if prd_se == "Q" and len(s) >= 5:
        return f"{s[:4]}Q{int(s[4:6]) if len(s) >= 6 else int(s[4])}"
    if prd_se == "H" and len(s) >= 5:
        return f"{s[:4]}H{int(s[4:6]) if len(s) >= 6 else int(s[4])}"
    return s[:4]


def _year_chunks(start: str, end: str, prd_se: str, years: int | None) -> list[tuple[str, str]]:
    """(시작, 끝) 시점 파라미터 목록. years 가 없으면 한 번에."""
    s, e = period_param(start, prd_se), period_param(end, prd_se)
    if not years:
        return [(s, e)]
    first ={"M": "01", "Q": "01", "H": "01", "Y": ""}[prd_se]
    last = {"M": "12", "Q": "04", "H": "02", "Y": ""}[prd_se]
    y0, y1 = int(s[:4]), int(e[:4])
    out = []
    for cy in range(y0, y1 + 1, years):
        ce = min(cy + years - 1, y1)
        out.append((s if cy == y0 else f"{cy}{first}", e if ce == y1 else f"{ce}{last}"))
    return out


class KosisClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self._key = (api_key or os.getenv("KOSIS_API_KEY", "")).strip()
        if not self._key:
            raise ValueError("KOSIS_API_KEY가 설정되지 않았습니다.")
        self._http = session or requests.Session()
        self._cache: dict[tuple, list] = {}
        self.calls = 0

    def _hide(self, text) -> str:
        return str(text).replace(self._key, "***")

    def _get(self, params: dict) -> list[dict]:
        key = tuple(sorted((k, v) for k, v in params.items() if k != "apiKey"))
        if key in self._cache:
            return self._cache[key]
        last_exc = None
        for attempt in range(3):
            try:
                if self.calls:
                    time.sleep(PAUSE)
                self.calls += 1
                resp = self._http.get(BASE_URL, params=params, timeout=TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                time.sleep(1 + attempt)
        else:
            raise KosisError(f"KOSIS {params.get('tblId')} 호출 실패: {self._hide(last_exc)}") from None
        if isinstance(data, dict):
            err = str(data.get("err"))
            if err == "30":  # 조회 결과 없음
                data = []
            elif err == "31":
                raise KosisError(f"KOSIS {params.get('tblId')}: 한 번에 받을 수 있는 4만 셀을 넘었습니다. chunk_years 를 줄이세요.")
            else:
                raise KosisError(f"KOSIS {params.get('tblId')} 오류 {err}: {data.get('errMsg', '')}")
        self._cache[key] = data
        return data

    def fetch(self, org_id: str, tbl_id: str, itm_id: str, prd_se: str, start: str, end: str,
              obj: dict | None = None, chunk_years: int | None = None) -> list[dict]:
        """기간(start~end, 기본 패널 표기)의 행을 모두 받는다. obj = {'objL1': 'ALL', 'objL2': '000+1201+', …}."""
        out = []
        for s, e in _year_chunks(start, end, prd_se, chunk_years):
            params = {"method": "getList", "apiKey": self._key, "format": "json", "jsonVD": "Y",
                      "orgId": org_id, "tblId": tbl_id, "itmId": itm_id, "prdSe": prd_se,
                      "startPrdDe": s, "endPrdDe": e}
            for i in range(1, 9):
                params[f"objL{i}"] = (obj or {}).get(f"objL{i}", "ALL" if i == 1 else "")
            out.extend(self._get(params))
        return out

    def fetch_rows(self, org_id: str, tbl_id: str, itm_id: str, start: str, end: str,
                   prd_se: str = "M", obj_l1: str = "ALL", **obj) -> list[dict]:
        """예전 호출 방식(--probe 등) 호환."""
        objs = {"objL1": obj_l1} | {f"objL{k[5:]}": v for k, v in obj.items() if k.startswith("obj_l")}
        return self.fetch(org_id, tbl_id, itm_id, prd_se, start, end, objs)
