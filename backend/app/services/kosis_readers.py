"""KOSIS 응답 → (지역, 시점, 값). 표마다 지역 코드 체계와 가공 규칙이 달라 읽는 방식(reader)을 나눴다.

가공 규칙은 기본 패널을 만든 DFMBA 전처리(preprocess/prep_kosis_*.py, impute/build_preprocessed.py)와 같다.

  admin      행정표준코드 표(주민등록 인구·세대·순이동). 2자리 = 시도, 5자리 = 시군구.
             2026-07 광주·전남 통합 뒤에는 통합코드(12)만 공표되고 그 아래 광주 5개 구 코드가 남는다
             → 광주 = 5개 구 합계, 전남 = 통합 - 광주 로 복원 (저량과 순이동에만 성립)
  age        시군구/1세별 인구에서 20–29세·30–39세·20–39세 합계와 20–39세 비중(%) 을 만든다 (admin 과 같은 코드·복원)
  name       시도 이름 표(고용·지역소득·주택건설·주택보급률). 전국대비(ratio_nation), 연중 누계 → 월(ytd) 선택
  seoul_gu   서울 구 이름 표('서울 강남구' 또는 '강남구')
  sum        행 전체 합계(임대주택공급 민간, 임대사업자 유형 x 주택유형)
  pick       분류 이름이 맞는 행 하나(임대주택공급 총계·공공 계·민간 계)
  link       신계열 x 연결계수(가계동향 소득)

공통 선택: per_household=True 면 값 ÷ 그해 12월 주민등록세대수 x 1000 (천 세대당).
"""

from collections import defaultdict

from app.services.kosis_client import to_period
from app.services.regions import SEOUL_GU, SIDO, normalize_sido

# 행정표준코드 → 시도 (강원 42→51, 전북 45→52 로 코드가 바뀌었다)
ADMIN_SIDO = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산", "36": "세종",
    "41": "경기", "42": "강원", "51": "강원", "43": "충북", "44": "충남", "45": "전북", "52": "전북", "46": "전남",
    "47": "경북", "48": "경남", "50": "제주",
}
MERGED_GJ = "12"  # 2026-07~ 전남광주통합특별시
GJ_GU = ("12210", "12240", "12270", "12300", "12330")  # 통합 뒤 광주 5개 구
SEOUL_GU_CODE = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200", "광진구": "11215", "동대문구": "11230",
    "중랑구": "11260", "성북구": "11290", "강북구": "11305", "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470", "강서구": "11500", "구로구": "11530", "금천구": "11545",
    "영등포구": "11560", "동작구": "11590", "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}
GU_BY_CODE = {c: n for n, c in SEOUL_GU_CODE.items()}
AGE_20_39 = [f"{band}{i:02d}" for band in ("12", "13", "15", "16") for i in range(1, 6)]  # 20~24·25~29·30~34·35~39세
HOUSEHOLDS = {"org_id": "101", "tbl_id": "DT_1B040B3", "itm_id": "T1+"}  # 천 세대당 분모


def plus(codes) -> str:
    return "+".join(codes) + "+"


def admin_codes(keep_gu=None) -> list[str]:
    """요청할 행정코드: 시도(신·구 코드) + 통합코드 + 광주 5개 구 + 화면에 있는 서울 구."""
    gu = [SEOUL_GU_CODE[g] for g in SEOUL_GU if keep_gu is None or g in keep_gu]
    return list(ADMIN_SIDO) + [MERGED_GJ, *GJ_GU] + gu


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _prd_se(spec) -> str:
    return {"M": "M", "Q": "Q", "H": "H", "A": "Y"}[spec.freq]


def _fetch(client, spec, start, end, obj=None, itm=None):
    p = spec.params
    return client.fetch(p["org_id"], p["tbl_id"], itm or p["itm_id"], _prd_se(spec), start, end,
                        obj if obj is not None else p.get("obj"), p.get("chunk"))


def _item_ok(row, spec) -> bool:
    want = spec.params.get("item")
    return want is None or row.get("ITM_ID") == want


def restore_gwangju_jeonnam(by_code: dict) -> dict:
    """{행정코드: 값} → {'광주': v, '전남': v} 또는 {}.
    통합코드(12)와 광주 5개 구가 모두 있으면 복원한다. 통합 뒤에도 옛 코드(29·46)가 0 으로 남아 오는 표(순이동)가 있어
    옛 코드 값보다 복원값을 쓴다."""
    total = by_code.get(MERGED_GJ)
    parts = [by_code.get(c) for c in GJ_GU]
    if total is None or any(v is None for v in parts):
        return {}
    gwangju = sum(parts)
    return {"광주": gwangju, "전남": total - gwangju}


def _emit_admin(grid: dict, keep_gu=None) -> dict:
    """{(key, 시점): {코드: 값}} → {(key, 지역, 시점): 값}."""
    out = {}
    for (key, period), by_code in grid.items():
        restored = restore_gwangju_jeonnam(by_code)
        for code, v in by_code.items():
            if code in ADMIN_SIDO:
                name = ADMIN_SIDO[code]
                if name not in restored:
                    out[(key, name, period)] = v
            elif code in GU_BY_CODE and (keep_gu is None or GU_BY_CODE[code] in keep_gu):
                out[(key, GU_BY_CODE[code], period)] = v
        for name, v in restored.items():
            out[(key, name, period)] = v
    return out


# ── readers: (client, spec, start, end, keep_gu) → ({(지역, 시점): 값}, 항목명) ──

def read_admin(client, spec, start, end, keep_gu=None):
    grid, item = defaultdict(dict), None
    for r in _fetch(client, spec, start, end, obj={"objL1": plus(admin_codes(keep_gu))}):
        v = _num(r.get("DT"))
        if v is None or not _item_ok(r, spec):
            continue
        item = item or r.get("ITM_NM")
        grid[(None, to_period(r["PRD_DE"], "M"))][r["C1"]] = v
    return {(reg, per): v for (_, reg, per), v in _emit_admin(grid, keep_gu).items()}, item


def _age_band(code: str):
    if code == "000":
        return "total"
    if code[:2] in ("12", "13"):
        return "20-29"
    if code[:2] in ("15", "16"):
        return "30-39"
    return None


def read_age(client, spec, start, end, keep_gu=None):
    obj = {"objL1": plus(admin_codes(keep_gu)), "objL2": plus(["000", *AGE_20_39])}
    grid = defaultdict(lambda: defaultdict(float))
    for r in _fetch(client, spec, start, end, obj=obj):
        v, band = _num(r.get("DT")), _age_band(r.get("C2", ""))
        if v is None or band is None:
            continue
        per = to_period(r["PRD_DE"], "M")
        grid[(band, per)][r["C1"]] += v
        if band != "total":
            grid[("20-39", per)][r["C1"]] += v
    vals = _emit_admin({k: dict(v) for k, v in grid.items()}, keep_gu)
    want = spec.params["band"]
    if want == "share":
        out = {}
        for (band, reg, per), v in vals.items():
            total = vals.get(("total", reg, per))
            if band == "20-39" and total:
                out[(reg, per)] = v / total * 100
        return out, "20-39세 비중(%)"
    return {(reg, per): v for (band, reg, per), v in vals.items() if band == want}, f"{want}세"


def read_name(client, spec, start, end, keep_gu=None):
    p = spec.params
    fetch_start = f"{start[:4]}-01" if p.get("ytd") else start  # 누계 차감은 그해 1월부터 있어야 한다
    raw = {}
    item = None
    for r in _fetch(client, spec, fetch_start, end):
        v = _num(r.get("DT"))
        if v is None or not _item_ok(r, spec):
            continue
        if any(r.get(k) != code for k, code in (p.get("where") or {}).items()):
            continue
        region = normalize_sido(r.get("C1_NM"))
        if region is None:  # 수도권·지방소계·전남광주(통합) 등 집계행
            continue
        item = item or r.get("ITM_NM")
        raw[(region, to_period(r["PRD_DE"], _prd_se(spec)))] = v
    if p.get("ytd"):  # 연중 누계 → 월 실적: 1월은 그대로, 나머지는 전월 누계를 뺀다 (전월이 없으면 비움)
        monthly = {}
        for (region, per), v in raw.items():
            if per.endswith("-01"):
                monthly[(region, per)] = v
            else:
                prev = raw.get((region, f"{per[:5]}{int(per[5:]) - 1:02d}"))
                if prev is not None:
                    monthly[(region, per)] = v - prev
        raw = monthly
    if p.get("ratio_nation"):
        nation = {per: v for (region, per), v in raw.items() if region == "전국"}
        raw = {(region, per): v / nation[per] for (region, per), v in raw.items() if region != "전국" and nation.get(per)}
    return {k: v for k, v in raw.items() if k[0] in SIDO}, item


def read_seoul_gu(client, spec, start, end, keep_gu=None):
    out, item = {}, None
    for r in _fetch(client, spec, start, end):
        v = _num(r.get("DT"))
        if v is None or not _item_ok(r, spec):
            continue
        name = str(r.get("C1_NM") or "").strip()
        if name.startswith("서울 "):
            name = name[3:].strip()
        if name not in SEOUL_GU or (keep_gu is not None and name not in keep_gu):
            continue
        item = item or r.get("ITM_NM")
        out[(name, to_period(r["PRD_DE"], _prd_se(spec)))] = v
    return out, item


def read_sum(client, spec, start, end, keep_gu=None):
    out = defaultdict(float)
    for r in _fetch(client, spec, start, end):
        v, region = _num(r.get("DT")), normalize_sido(r.get("C1_NM"))
        if v is None or region not in SIDO:
            continue
        out[(region, to_period(r["PRD_DE"], _prd_se(spec)))] += v
    return dict(out), "합계"


def _squash(s) -> str:
    return "".join(str(s or "").split())


def read_pick(client, spec, start, end, keep_gu=None):
    want = tuple(_squash(x) for x in spec.params["pick"])  # (C2_NM, C3_NM, ITM_NM)
    out = {}
    for r in _fetch(client, spec, start, end):
        if (_squash(r.get("C2_NM")), _squash(r.get("C3_NM")), _squash(r.get("ITM_NM"))) != want:
            continue
        v, region = _num(r.get("DT")), normalize_sido(r.get("C1_NM"))
        if v is not None and region in SIDO:
            out[(region, to_period(r["PRD_DE"], _prd_se(spec)))] = v
    return out, spec.params["pick"][0]


def read_link(client, spec, start, end, keep_gu=None):
    p = spec.params
    start = max(start, p["link_from"])
    out, item = {}, None
    for r in _fetch(client, spec, start, end):
        v = _num(r.get("DT"))
        if v is None:
            continue
        item = item or r.get("ITM_NM")
        per = to_period(r["PRD_DE"], _prd_se(spec))
        if per >= p["link_from"]:
            out[("전국", per)] = v * p["link_k"]
    return out, item


READERS = {"admin": read_admin, "age": read_age, "name": read_name, "seoul_gu": read_seoul_gu,
           "sum": read_sum, "pick": read_pick, "link": read_link}


def households_december(client, years: list[str], keep_gu=None) -> dict:
    """{(지역, 연도): 그해 12월 주민등록세대수}. 천 세대당 분모."""
    if not years:
        return {}
    y0, y1 = min(years), max(years)
    grid = defaultdict(dict)
    rows = client.fetch(HOUSEHOLDS["org_id"], HOUSEHOLDS["tbl_id"], HOUSEHOLDS["itm_id"], "M", f"{y0}-12", f"{y1}-12",
                        {"objL1": plus(admin_codes(keep_gu))}, 5)
    for r in rows:
        v = _num(r.get("DT"))
        if v is not None and str(r.get("PRD_DE", "")).endswith("12"):
            grid[(None, r["PRD_DE"][:4])][r["C1"]] = v
    return {(reg, year): v for (_, reg, year), v in _emit_admin(grid, keep_gu).items()}


def read(client, spec, start: str, end: str, keep_gu=None) -> tuple[list[tuple], str | None]:
    values, item = READERS[spec.params["reader"]](client, spec, start, end, keep_gu)
    if spec.params.get("per_household"):
        hh = households_december(client, sorted({per[:4] for _, per in values}), keep_gu)
        values = {(reg, per): v / hh[(reg, per[:4])] * 1000 for (reg, per), v in values.items() if hh.get((reg, per[:4]))}
        item = f"{item} (천 세대당)"
    return [(reg, per, v) for (reg, per), v in values.items()], item
