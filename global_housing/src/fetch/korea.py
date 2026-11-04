"""서울·한국 원자료 수집.

kr_rone   한국부동산원 R-ONE Open API (RONE_API_KEY) — 아파트 가격·월세 수준, 지수, 전월세 전환율 (서울·전국, 월)
kr_rtms   국토교통부 실거래가 Open API (DATA_GO_KR_API_KEY) — 서울 25개 구 아파트 매매·전월세 계약 건별
kr_kosis  통계청 KOSIS Open API (KOSIS_API_KEY) — 가계금융복지조사 시도 가구소득, 사업체노동력조사 시도 임금
"""

from __future__ import annotations

import io
import json
import os
import time
from xml.etree import ElementTree as ET

import pandas as pd

from ..netio import DataUnavailable, FetchError, NetworkError, utc_now

# ── R-ONE ─────────────────────────────────────────────────────────────
RONE_URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
RONE_TABLES = {
    # statbl_id: 설명 (모두 월간, 아파트)
    "A_2024_00045": "매매가격지수_아파트",
    "A_2024_00054": "월세통합가격지수_아파트",
    "A_2024_00055": "월세가격지수_아파트",
    "A_2024_00060": "평균매매가격_아파트",
    "A_2024_00061": "평균단위매매가격_아파트",
    "A_2024_00062": "중위매매가격_아파트",
    "A_2024_00063": "중위단위매매가격_아파트",
    "A_2024_00068": "평균월세보증금_아파트",
    "A_2024_00069": "평균월세가격_아파트",
    "A_2024_00070": "중위월세보증금_아파트",
    "A_2024_00071": "중위월세가격_아파트",
    "A_2024_00064": "평균전세가격_아파트",
    "A_2024_00156": "전월세전환율_아파트",
}
RONE_REGIONS = ("서울", "전국")


def _key(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise DataUnavailable(f"{name} 환경변수가 없습니다 (.env.example 참고)")
    return v


def _rone_page(f, key, params, index, size=1000):
    q = {"KEY": key, "Type": "json", "pIndex": index, "pSize": size, **params}
    res = f.get(RONE_URL, params=q, secret=("KEY",))
    res.encoding = "utf-8"
    body = res.json()
    if "RESULT" in body:
        if body["RESULT"].get("CODE") == "INFO-200":
            return 0, []
        raise DataUnavailable(f"R-ONE 오류 {body['RESULT'].get('CODE')}: {body['RESULT'].get('MESSAGE')}")
    parts = body["SttsApiTblData"]
    total = next((h["list_total_count"] for h in parts[0]["head"] if "list_total_count" in h), 0)
    rows = parts[1].get("row", []) if len(parts) > 1 else []
    return int(total), rows


def _rone_all(f, key, params):
    out, i = [], 1
    while True:
        total, rows = _rone_page(f, key, params, i)
        out.extend(rows)
        if not rows or len(out) >= total:
            break
        i += 1
    seen, uniq = set(), []
    for r in out:
        k = (r["WRTTIME_IDTFR_ID"], r["CLS_ID"], r["ITM_ID"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq, total


def fetch_rone(ctx, f, log):
    key = _key("RONE_API_KEY")
    end = ctx.as_of[:7].replace("-", "")
    for tid, name in RONE_TABLES.items():
        # 1) 최근 한 달로 지역 코드(CLS_ID) 확인 — 표마다 서울 코드가 다르다(예: 500008, 500006)
        probe, _ = _rone_all(f, key, {"STATBL_ID": tid, "DTACYCLE_CD": "MM", "WRTTIME_IDTFR_ID": "202501"})
        cls = {r["CLS_FULLNM"]: r["CLS_ID"] for r in probe if r["CLS_FULLNM"] in RONE_REGIONS}
        rows = []
        for region, cls_id in cls.items():
            got, total = _rone_all(f, key, {"STATBL_ID": tid, "DTACYCLE_CD": "MM", "CLS_ID": cls_id,
                                            "START_WRTTIME": "200001", "END_WRTTIME": end})
            if len(got) < total:
                raise FetchError(f"R-ONE {tid} {region}: {len(got)}/{total}행만 받음")
            rows.extend(got)
        f.save_json("kr_rone", f"{tid}_{name}.json", rows, RONE_URL,
                    {"STATBL_ID": tid, "DTACYCLE_CD": "MM", "CLS": "+".join(cls), "KEY": "x"}, secret=("KEY",),
                    note=f"R-ONE {name} 서울·전국 월간 전체 기간")
        log(f"  kr_rone {tid} {name}: {len(rows)}행 ({', '.join(cls)})")


# ── 국토교통부 실거래 ─────────────────────────────────────────────────
RTMS = {
    "apt_trade": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "apt_rent": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}
SEOUL_GU = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구", "11215": "광진구", "11230": "동대문구",
    "11260": "중랑구", "11290": "성북구", "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구", "11530": "구로구", "11545": "금천구",
    "11560": "영등포구", "11590": "동작구", "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}
RTMS_YEARS = (2024, 2025)


def _rtms_month(f, key, url, lawd, ym):
    items, page = [], 1
    while True:
        params = {"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ym, "numOfRows": 1000, "pageNo": page}
        res = f.get(url, params=params, secret=("serviceKey",))
        root = ET.fromstring(res.content)
        code = (root.findtext("./header/resultCode") or "").strip()
        if not code:
            msg = (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or root.tag).strip()
            raise DataUnavailable(f"실거래 API 오류 {lawd} {ym}: {msg}")
        if code not in ("000", "00"):
            if code in ("03", "004"):
                return items
            raise DataUnavailable(f"실거래 API 오류 {lawd} {ym}: {code} {root.findtext('./header/resultMsg')}")
        got = [{c.tag: (c.text or "").strip() for c in it} for it in root.findall("./body/items/item")]
        items.extend(got)
        total = int(root.findtext("./body/totalCount") or 0)
        if not got or page * 1000 >= total:
            return items
        page += 1


def fetch_rtms(ctx, f, log):
    """서울 25개 구 × 월. 연·유형마다 CSV(gzip) 하나로 저장한다. 이미 받은 연도는 다시 받지 않는다(--refresh 로 강제)."""
    key = _key("DATA_GO_KR_API_KEY")
    for kind, url in RTMS.items():
        for year in RTMS_YEARS:
            fname = f"seoul_{kind}_{year}.csv.gz"
            path = f.raw_path("kr_rtms", fname)
            if path.exists() and not ctx.project.get("_refresh"):
                log(f"  kr_rtms {fname}: 이미 있음 — 건너뜀")
                continue
            rows, calls0 = [], f.calls
            for lawd, gu in SEOUL_GU.items():
                for m in range(1, 13):
                    ym = f"{year}{m:02d}"
                    if ym > ctx.as_of[:7].replace("-", ""):
                        continue
                    for r in _rtms_month(f, key, url, lawd, ym):
                        r["_lawd_cd"], r["_gu"] = lawd, gu
                        rows.append(r)
            df = pd.DataFrame(rows)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False, encoding="utf-8", compression="gzip")
            from ..netio import sha256
            f.manifest.record(source_id="kr_rtms", file=fname, url=url,
                              params=f"serviceKey=***&LAWD_CD=서울25구&DEAL_YMD={year}01~{year}12&numOfRows=1000",
                              retrieved_at=utc_now(), bytes=path.stat().st_size, sha256=sha256(path), http_status=200,
                              note=f"응답 item 을 그대로 CSV 로 저장 ({len(df)}건, 호출 {f.calls - calls0}회). "
                                   f"_lawd_cd·_gu 열만 추가")
            log(f"  kr_rtms {fname}: {len(df)}건 (호출 {f.calls - calls0}회)")


# ── KOSIS ─────────────────────────────────────────────────────────────
KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
KOSIS_TABLES = {
    # 파일명: (orgId, tblId, prdSe, start, end, 추가 파라미터, 설명)
    "INH_1HD_AAA01_01": ("101", "INH_1HD_AAA01_01", "Y", "2017", "2026", {"objL2": "ALL"},
                         "가계금융복지조사 가구소득(지역별, 시도) — 조사연도 기준, 소득은 전년도"),
    "DT_1YL15006": ("101", "DT_1YL15006", "Y", "2011", "2026", {},
                    "월평균 임금 및 임금상승률(시도) — 사업체노동력조사"),
    "DT_1HDAAB03": ("101", "DT_1HDAAB03", "Y", "2017", "2026", {"objL2": "ALL"},
                    "가계금융복지조사 가구특성별 소득구간별 가구분포(전국) — 전국 중위소득 보간용"),
}


def fetch_kosis(ctx, f, log):
    key = _key("KOSIS_API_KEY")
    for name, (org, tbl, prd, s, e, extra, desc) in KOSIS_TABLES.items():
        params = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y", "prdSe": prd,
                  "startPrdDe": s, "endPrdDe": e, "orgId": org, "tblId": tbl, "itmId": "ALL", "objL1": "ALL", **extra}
        res = f.get(KOSIS_URL, params=params, secret=("apiKey",))
        body = res.json()
        if isinstance(body, dict):
            raise DataUnavailable(f"KOSIS {tbl}: {body}")
        f.save_json("kr_kosis", f"{name}.json", body, KOSIS_URL, params, secret=("apiKey",), note=desc)
        log(f"  kr_kosis {name}: {len(body)}행")


def fetch(ctx, f, log, source_id):
    {"kr_rone": fetch_rone, "kr_rtms": fetch_rtms, "kr_kosis": fetch_kosis}[source_id](ctx, f, log)
