"""R-ONE 월세지수를 Supabase(PostgreSQL)에 적재한다.

테이블은 database/migrations/001_rone_rent_index.sql 로 먼저 만들어 둔다.
여기서는 테이블을 만들지 않는다(별도 MetaData, create_all 대상 아님).

- 정기 수집: rone_stat_tables.collect = true 인 표의 최근 N개월을 기준월별로 다시 받는다.
  공표 뒤 수정된 값도 같은 키로 덮어쓰고, 값이 바뀐 행만 갱신된다(이력은 DB 트리거가 남김).
- 전체 적재(--full): 기준월 없이 전체 기간을 페이지 단위로 받는다. 첫 적재와 구지수(00164)에 쓴다.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (BigInteger, Boolean, Column, and_, case, or_, Date, DateTime, Float, Integer, MetaData, String, Table, Text,
                        func, literal_column, select, update)
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_engine
from app.services.rone_client import RoneClient, RoneError

KST = timezone(timedelta(hours=9))
BATCH = 1000
LEVELS = {"500": 0, "510": 1, "520": 2, "530": 3}
UNNAMED = "(이름 없음)"

meta = MetaData()
stat_tables = Table(
    "rone_stat_tables", meta,
    Column("statbl_id", String, primary_key=True), Column("name", Text), Column("cycle", String),
    Column("is_legacy", Boolean), Column("collect", Boolean),
    Column("first_period", Date), Column("last_period", Date), Column("updated_at", DateTime(timezone=True)),
)
rone_regions = Table(
    "rone_regions", meta,
    Column("statbl_id", String, primary_key=True), Column("cls_id", BigInteger, primary_key=True),
    Column("cls_nm", String), Column("cls_fullnm", Text), Column("rone_level", Integer),
    Column("region_key", String), Column("first_seen", Date), Column("last_seen", Date),
)
observations = Table(
    "rone_observations", meta,
    Column("statbl_id", String, primary_key=True), Column("cls_id", BigInteger, primary_key=True),
    Column("itm_id", BigInteger, primary_key=True), Column("period", Date, primary_key=True),
    Column("value", Float), Column("unit", String), Column("itm_nm", String),
)
runs = Table(
    "rone_collect_runs", meta,
    Column("id", BigInteger, primary_key=True), Column("statbl_id", String),
    Column("started_at", DateTime(timezone=True)), Column("finished_at", DateTime(timezone=True)),
    Column("status", String), Column("period_from", Date), Column("period_to", Date),
    Column("row_count", Integer), Column("changed_count", Integer), Column("error", Text),
)


def to_period(value):
    """'202609' -> date(2026, 9, 1)"""
    s = str(value)
    return date(int(s[:4]), int(s[4:6]), 1)


def recent_months(n, today=None):
    """오늘(KST) 기준 최근 n개월, 오래된 달부터 'YYYYMM'."""
    today = today or datetime.now(KST).date()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def convert(rows):
    """R-ONE 행 → (지역 행 dict, 관측값 행 dict). 값이 없는 행도 NULL로 남긴다."""
    regions, obs = {}, {}
    for r in rows:
        period = to_period(r["WRTTIME_IDTFR_ID"])
        cls_id = int(r["CLS_ID"])
        key = (r["STATBL_ID"], cls_id)
        reg = regions.setdefault(key, {
            "statbl_id": r["STATBL_ID"], "cls_id": cls_id, "cls_nm": None, "cls_fullnm": None,
            "rone_level": LEVELS.get(str(cls_id)[:3]), "first_seen": period, "last_seen": period, "_named": None,
        })
        reg["first_seen"] = min(reg["first_seen"], period)
        reg["last_seen"] = max(reg["last_seen"], period)
        # 이름은 이름이 있는 행 중 가장 최근 기준월의 것을 쓴다 (행정구역 개편 반영)
        if r.get("CLS_NM") and (reg["_named"] is None or period >= reg["_named"]):
            reg.update(cls_nm=r["CLS_NM"], cls_fullnm=r.get("CLS_FULLNM") or r["CLS_NM"], _named=period)
        value = r.get("DTA_VAL")
        obs[(r["STATBL_ID"], cls_id, int(r["ITM_ID"]), period)] = {
            "statbl_id": r["STATBL_ID"], "cls_id": cls_id, "itm_id": int(r["ITM_ID"]), "period": period,
            "value": None if value in (None, "") else float(value), "unit": r.get("UI_NM"), "itm_nm": r.get("ITM_NM"),
        }
    for reg in regions.values():
        # R-ONE 이 이름 없이 주는 지역이 있다 (예: 2026.07 개편 전 인천 일부 CLS_ID). 원자료에는 추정 이름을 넣지 않는다.
        if reg.pop("_named") is None:
            reg.update(cls_nm=UNNAMED, cls_fullnm=f"{UNNAMED} CLS_ID {reg['cls_id']}")
    return list(regions.values()), list(obs.values())


def _chunks(items, size=BATCH):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def upsert_regions(conn, rows):
    for chunk in _chunks(rows):
        stmt = insert(rone_regions).values(chunk)
        ex = stmt.excluded
        # 새 이름이 있고 더 최근이면, 또는 기존이 이름 없음이면 바꾼다
        rename = or_(and_(ex.cls_nm != UNNAMED, ex.last_seen >= rone_regions.c.last_seen), rone_regions.c.cls_nm == UNNAMED)
        stmt = stmt.on_conflict_do_update(
            index_elements=["statbl_id", "cls_id"],
            set_={
                "cls_nm": case((rename, ex.cls_nm), else_=rone_regions.c.cls_nm),
                "cls_fullnm": case((rename, ex.cls_fullnm), else_=rone_regions.c.cls_fullnm),
                "rone_level": ex.rone_level,
                "first_seen": func.least(rone_regions.c.first_seen, ex.first_seen),
                "last_seen": func.greatest(rone_regions.c.last_seen, ex.last_seen),
            },
        )
        conn.execute(stmt)


def upsert_observations(conn, rows):
    """(새로 들어간 행 수, 값이 바뀐 행 수)"""
    inserted = changed = 0
    for chunk in _chunks(rows):
        stmt = insert(observations).values(chunk)
        ex = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["statbl_id", "cls_id", "itm_id", "period"],
            set_={"value": ex.value, "unit": ex.unit, "itm_nm": ex.itm_nm},
            where=observations.c.value.is_distinct_from(ex.value),
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        for (is_new,) in conn.execute(stmt):
            inserted += bool(is_new)
            changed += not is_new
    return inserted, changed


def _refresh_table_range(conn, statbl_id):
    lo, hi = conn.execute(
        select(func.min(observations.c.period), func.max(observations.c.period)).where(observations.c.statbl_id == statbl_id)
    ).one()
    conn.execute(update(stat_tables).where(stat_tables.c.statbl_id == statbl_id)
                 .values(first_period=lo, last_period=hi, updated_at=func.now()))


def collect_table(engine, client, statbl_id, months=None, full=False, cycle="MM"):
    """한 통계표를 받아 적재하고 결과 dict 를 돌려준다. 실패해도 예외 대신 status=failed."""
    periods = None if full else months
    with engine.begin() as conn:
        run_id = conn.execute(runs.insert().values(
            statbl_id=statbl_id, status="running",
            period_from=to_period(periods[0]) if periods else None,
            period_to=to_period(periods[-1]) if periods else None,
        ).returning(runs.c.id)).scalar_one()

    result = {"statbl_id": statbl_id, "status": "success", "rows": 0, "inserted": 0, "changed": 0}
    try:
        if periods:
            raw = []
            for p in periods:
                raw.extend(client.table_data(statbl_id, cycle, p))
        else:
            raw = client.table_data(statbl_id, cycle)
        regions, obs = convert(raw)
        with engine.begin() as conn:
            upsert_regions(conn, regions)
            inserted, changed = upsert_observations(conn, obs)
            _refresh_table_range(conn, statbl_id)
        result.update(rows=len(obs), inserted=inserted, changed=changed,
                      periods=f"{min(o['period'] for o in obs):%Y-%m}~{max(o['period'] for o in obs):%Y-%m}" if obs else None)
    except Exception as exc:  # 한 표가 실패해도 다른 표는 계속 수집한다
        message = str(exc) if isinstance(exc, RoneError) else f"{type(exc).__name__}: DB 적재 실패"
        result.update(status="failed", error=message)

    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.id == run_id).values(
            finished_at=func.now(), status=result["status"], row_count=result["rows"],
            changed_count=result["changed"], error=result.get("error"),
        ))
    return result


def target_tables(engine, only=None, include_legacy=False):
    with engine.connect() as conn:
        q = select(stat_tables.c.statbl_id, stat_tables.c.cycle, stat_tables.c.is_legacy, stat_tables.c.collect)
        rows = conn.execute(q.order_by(stat_tables.c.statbl_id)).all()
    if only:
        known = {r.statbl_id for r in rows}
        missing = [t for t in only if t not in known]
        if missing:
            raise RoneError(f"rone_stat_tables 에 없는 통계표: {', '.join(missing)}")
        return [r for r in rows if r.statbl_id in only]
    return [r for r in rows if r.collect or (include_legacy and r.is_legacy)]


def collect(only=None, months=12, full=False, include_legacy=False, client=None, engine=None):
    engine = engine or get_engine()
    if engine.url.get_backend_name() != "postgresql":
        raise RoneError("R-ONE 적재는 PostgreSQL(Supabase) DATABASE_URL이 필요합니다.")
    client = client or RoneClient()
    recent = recent_months(months)
    results = []
    for t in target_tables(engine, only, include_legacy):
        # 구지수는 더 이상 갱신되지 않으므로 항상 전체 기간을 받는다
        results.append(collect_table(engine, client, t.statbl_id, recent, full or t.is_legacy, t.cycle or "MM"))
    ok = all(r["status"] == "success" for r in results)
    return {"status": "ok" if ok else "partial_failure", "tables": results}
