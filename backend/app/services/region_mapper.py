"""R-ONE 지역 분류(rone_regions)를 공통 지역 키(regions)로 연결한다.

키 규칙은 database/migrations/002_regions_mapping.sql 맨 위 주석을 따른다.
- 경로(CLS_FULLNM)에서 R-ONE 권역(…지역, …권)은 키에서 빼고 area_key 로 따로 둔다.
- '전남광주>광주' 처럼 2026 통합 단위가 앞에 붙으면 떼고, 광주·전남의 상위(parent)로 둔다.
- R-ONE 이 이름 없이 주는 코드는 UNNAMED_GUESS 로 연결하고 note 에 추정이라고 남긴다.
"""

from sqlalchemy import Column, Date, Integer, MetaData, String, Table, Text, bindparam, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.services.rone_collector import UNNAMED, rone_regions, stat_tables

NATION = "전국"
ZONES = {"수도권", "지방권", "5대광역시", "4대광역시", "8개도", "7개도", "8개시도"}
MERGED_SIDO = {"전남광주": ("광주", "전남")}  # 2026 통합 단위: 하위 시도
AREA_SUFFIXES = ("지역", "권")
LEVEL_ORDER = {"nation": 0, "zone": 1, "sido": 2, "area": 3, "sigungu": 4, "gu": 5}
# 코드 순서(중구·동구·미추홀구 … 계양구·서구)와 2026.07 이후 값이 끊긴 점으로 추정
UNNAMED_GUESS = {510020: "인천>중구", 510021: "인천>동구", 510027: "인천>서구"}
GUESS_NOTE = "R-ONE 이 이름 없이 제공(CLS_ID {ids}). 코드 순서와 2026.07 개편 시점으로 추정"

meta = MetaData()
regions = Table(
    "regions", meta,
    Column("region_key", String, primary_key=True), Column("name", String), Column("level", String),
    Column("parent_key", String), Column("area_key", String), Column("sort_order", Integer),
    Column("note", Text), Column("first_period", Date), Column("last_period", Date),
)


def is_area(name):
    return name.endswith(AREA_SUFFIXES)


def chain(fullnm):
    """CLS_FULLNM → 상위부터 차례로 regions 행 dict 목록. 마지막 행이 이 분류의 지역."""
    parts = [p.strip() for p in fullnm.split(">") if p.strip()]
    if parts == [NATION]:
        return [{"region_key": NATION, "name": NATION, "level": "nation", "parent_key": None, "area_key": None}]
    out = [{"region_key": NATION, "name": NATION, "level": "nation", "parent_key": None, "area_key": None}]
    if len(parts) == 1 and parts[0] in ZONES:
        return out + [{"region_key": parts[0], "name": parts[0], "level": "zone", "parent_key": NATION, "area_key": None}]

    sido_parent = NATION
    merged = next((m for m, subs in MERGED_SIDO.items() if parts[0] in subs), None)
    if merged:  # 구지수처럼 '광주'만 와도 통합 단위 아래에 둔다
        parts = [merged] + parts
    if parts[0] in MERGED_SIDO:
        out.append({"region_key": parts[0], "name": parts[0], "level": "sido", "parent_key": NATION, "area_key": None})
        if len(parts) == 1:
            return out
        sido_parent = parts[0]
        parts = parts[1:]

    sido = parts[0]
    out.append({"region_key": sido, "name": sido, "level": "sido", "parent_key": sido_parent, "area_key": None})
    area_path, admin = [], []
    for name in parts[1:]:
        if is_area(name) and not admin:
            area_path.append(name)
            key = ">".join([sido] + area_path)
            parent = ">".join([sido] + area_path[:-1])
            out.append({"region_key": key, "name": name, "level": "area", "parent_key": parent, "area_key": None})
        else:
            admin.append(name)
            key = ">".join([sido] + admin)
            parent = ">".join([sido] + admin[:-1])
            out.append({"region_key": key, "name": name, "level": "sigungu" if len(admin) == 1 else "gu",
                        "parent_key": parent, "area_key": ">".join([sido] + area_path) if area_path else None})
    return out


def build(rone_rows):
    """rone_regions 행(statbl_id, cls_id, cls_fullnm, first_seen, last_seen, is_legacy)
    → (regions 행 목록 — 상위부터, {(statbl_id, cls_id): region_key})"""
    found, mapping, guessed = {}, {}, {}
    for r in sorted(rone_rows, key=lambda r: r["cls_id"]):
        fullnm = r["cls_fullnm"]
        if r["cls_nm"] == UNNAMED or fullnm.startswith(UNNAMED):
            fullnm = UNNAMED_GUESS.get(r["cls_id"])
            if not fullnm:
                continue  # 추정도 없는 코드는 연결하지 않는다
            guessed.setdefault(fullnm, set()).add(r["cls_id"])
        rows = chain(fullnm)
        for row in rows:
            cur = found.setdefault(row["region_key"], {**row, "sort_order": None, "note": None,
                                                       "first_period": None, "last_period": None})
            # 같은 키가 권역 없이 먼저 나왔더라도 소속 권역은 채운다
            if row["area_key"] and not cur["area_key"]:
                cur["area_key"] = row["area_key"]
        leaf = found[rows[-1]["region_key"]]
        mapping[(r["statbl_id"], r["cls_id"])] = leaf["region_key"]
        if leaf["sort_order"] is None:
            leaf["sort_order"] = r["cls_id"]
        if not r.get("is_legacy"):  # 관측 기간은 현행 표 기준
            leaf["first_period"] = min(filter(None, [leaf["first_period"], r["first_seen"]]), default=None)
            leaf["last_period"] = max(filter(None, [leaf["last_period"], r["last_seen"]]), default=None)
    for key, ids in guessed.items():
        found[key]["note"] = GUESS_NOTE.format(ids=", ".join(map(str, sorted(ids))))
    # 부모·권역이 먼저 들어가도록 정렬 (전남광주 → 광주·전남 → 시군구)
    ordered = sorted(found.values(), key=lambda x: (_depth(x, found), LEVEL_ORDER[x["level"]], x["region_key"]))
    return ordered, mapping


def _depth(row, found, seen=None):
    seen = seen or set()
    refs = [k for k in (row["parent_key"], row["area_key"]) if k and k not in seen]
    if not refs:
        return 0
    return 1 + max(_depth(found[k], found, seen | {row["region_key"]}) for k in refs)


def apply(engine):
    """rone_regions 전체를 읽어 regions 를 upsert 하고 rone_regions.region_key 를 채운다."""
    with engine.begin() as conn:
        rows = [dict(r._mapping) for r in conn.execute(
            select(rone_regions.c.statbl_id, rone_regions.c.cls_id, rone_regions.c.cls_nm, rone_regions.c.cls_fullnm,
                   rone_regions.c.first_seen, rone_regions.c.last_seen, stat_tables.c.is_legacy)
            .join(stat_tables, stat_tables.c.statbl_id == rone_regions.c.statbl_id))]
        ordered, mapping = build(rows)
        for row in ordered:
            stmt = insert(regions).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["region_key"],
                set_={c: stmt.excluded[c] for c in ("name", "level", "parent_key", "area_key", "sort_order", "note",
                                                    "first_period", "last_period")},
            )
            conn.execute(stmt)
        if mapping:
            conn.execute(
                update(rone_regions)
                .where(rone_regions.c.statbl_id == bindparam("sid"), rone_regions.c.cls_id == bindparam("cid"))
                .values(region_key=bindparam("rkey")),
                [{"sid": s, "cid": c, "rkey": k} for (s, c), k in mapping.items()],
            )
        unmapped = conn.execute(select(func.count()).select_from(rone_regions)
                                .where(rone_regions.c.region_key.is_(None))).scalar_one()
    levels = {}
    for row in ordered:
        levels[row["level"]] = levels.get(row["level"], 0) + 1
    return {"regions": len(ordered), "levels": levels, "mapped": len(mapping), "unmapped": unmapped}
