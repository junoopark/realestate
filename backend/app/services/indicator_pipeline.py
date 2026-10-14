"""정량 지표 파이프라인: 외부 Open API → 정규화 → DB UPSERT → DB 에서 조회.

설계 원칙 (교재 06 '있으면 DB 에서, 없으면 API 에서' + 정책 수집기와 같은 운영 방식)
  - 사용자 요청 경로에서는 DB 만 읽는다. DB 에 그 변수가 아예 없을 때만 API 를 한 번 불러 채운다(lazy).
  - 자료가 오래됐으면(REFRESH_HOURS 경과) DB 값을 먼저 돌려주고 뒤에서 갱신한다(stale-while-revalidate).
  - 정기 갱신은 CLI(scripts/collect_indicators.py) 또는 관리자 API(POST /indicators/refresh) 가 맡는다.
  - 같은 (변수, 지역, 시점) 은 INSERT … ON CONFLICT DO UPDATE 로 제자리 갱신 — 재수집해도 중복이 없다.
"""

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.db.models import IndicatorFetchLog, IndicatorObservation, IndicatorVariable
from app.services.indicator_registry import REGISTRY, SOURCES, IndicatorSpec, enabled_specs, get_spec
from app.services.regions import SIDO, normalize_sido

log = logging.getLogger(__name__)

REFRESH_LOCK = threading.Lock()
RELOAD_TAIL_MONTHS = 12  # 재수집 시 최근 N개월은 다시 받아 수정분(잠정→확정)을 반영한다


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def refresh_hours() -> int:
    try:
        return max(1, int(os.getenv("INDICATOR_REFRESH_HOURS", "24")))
    except ValueError:
        return 24


def today_period(freq: str = "M") -> str:
    t = date.today()
    return f"{t.year:04d}-{t.month:02d}" if freq == "M" else f"{t.year:04d}"


def shift_month(period: str, months: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    idx = y * 12 + (m - 1) + months
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    out, p = [], start
    while p <= end:
        out.append(p)
        p = shift_month(p, 1)
    return out


# ── 외부 API 호출 → (region, period, value) 목록 ──

def _rone_rows(client, spec: IndicatorSpec, start: str, end: str) -> tuple[list[tuple], str | None]:
    from app.services.rone_client import to_period
    p = spec.params
    cycle = {"M": "MM", "Q": "QY", "A": "YY"}[spec.freq]
    raw = client.fetch_rows(p["statbl_id"], start, end, cycle=cycle, cls_id=p.get("cls_id"), itm_id=p.get("itm_id"))
    items = sorted({str(r.get("ITM_NM", "")).strip() for r in raw})
    want = p.get("item")
    if want:
        chosen = next((i for i in items if want in i), None)
        if chosen is None and items:
            raise RuntimeError(f"{spec.id}: 항목 '{want}' 을 찾지 못했습니다. 실제 항목: {items[:10]}")
    else:
        chosen = items[0] if items else None
        if len(items) > 1:
            log.warning("%s: 항목이 여러 개라 첫 항목 '%s' 을 씁니다 (%s). registry 의 item 으로 고정하세요.", spec.id, chosen, items)
    out = []
    for r in raw:
        if chosen is not None and str(r.get("ITM_NM", "")).strip() != chosen:
            continue
        region = _region_for(spec, r.get("CLS_NM") or r.get("CLS_FULLNM"))
        if region is None:
            continue
        value = _to_float(r.get("DTA_VAL"))
        if value is None:
            continue
        out.append((region, to_period(r.get("WRTTIME_IDTFR_ID", ""), cycle), value))
    return out, chosen


def _ecos_rows(client, spec: IndicatorSpec, start: str, end: str) -> tuple[list[tuple], str | None]:
    from app.services.ecos_client import to_period
    p = spec.params
    raw = client.fetch_rows(p["stat_code"], p["item_code"], start, end, freq=spec.freq)
    out, item = [], None
    for r in raw:
        item = item or r.get("ITEM_NAME1")
        value = _to_float(r.get("DATA_VALUE"))
        if value is None:
            continue
        out.append(("전국", to_period(r.get("TIME", ""), spec.freq), value))
    return out, item


def _kosis_rows(client, spec: IndicatorSpec, start: str, end: str) -> tuple[list[tuple], str | None]:
    from app.services.kosis_client import to_period
    p = spec.params
    raw = client.fetch_rows(p["org_id"], p["tbl_id"], p["itm_id"], start, end, prd_se=spec.freq if spec.freq != "A" else "Y",
                            obj_l1=p.get("obj_l1", "ALL"), **{k: v for k, v in p.items() if k.startswith("obj_l") and k != "obj_l1"})
    out, item = [], None
    for r in raw:
        item = item or r.get("ITM_NM")
        region = _region_for(spec, r.get("C1_NM"))
        if region is None:
            continue
        value = _to_float(r.get("DT"))
        if value is None:
            continue
        out.append((region, to_period(r.get("PRD_DE", ""), "M" if spec.freq == "M" else "Y"), value))
    return out, item


def _region_for(spec: IndicatorSpec, name) -> str | None:
    n = normalize_sido(name)
    if spec.scope == "nation":
        return "전국" if n == "전국" else None
    return n if n in SIDO else None


def _to_float(v):
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN 제외


FETCHERS = {"R-ONE": _rone_rows, "ECOS": _ecos_rows, "KOSIS": _kosis_rows}


def make_client(source: str):
    """키가 없으면 ValueError — 호출한 쪽에서 '설정되지 않음' 으로 기록한다."""
    if source == "R-ONE":
        from app.services.rone_client import RoneClient
        return RoneClient()
    if source == "ECOS":
        from app.services.ecos_client import EcosClient
        return EcosClient()
    if source == "KOSIS":
        from app.services.kosis_client import KosisClient
        return KosisClient()
    raise ValueError(f"지원하지 않는 출처: {source}")


# ── DB 쓰기 ──

def sync_registry(session: Session) -> None:
    """레지스트리 → indicator_variables. 수집 상태 열은 건드리지 않는다."""
    now = utc_now()
    for spec in REGISTRY:
        row = session.get(IndicatorVariable, spec.id)
        fields = dict(label=spec.label, driver=spec.driver, source=spec.source, source_ref=spec.source_ref,
                      freq=spec.freq, scope=spec.scope, unit=spec.unit, release=spec.release, enabled=spec.enabled, updated_at=now)
        if row is None:
            session.add(IndicatorVariable(id=spec.id, **fields))
        else:
            for k, v in fields.items():
                setattr(row, k, v)
    session.commit()


def upsert_observations(session: Session, variable_id: str, rows: list[tuple], fetched_at: str) -> int:
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    # 같은 (지역, 시점) 이 응답에 두 번 있으면 마지막 값만 쓴다
    dedup = {(r, p): v for r, p, v in rows}
    payload = [{"variable_id": variable_id, "region": r, "period": p, "value": v, "fetched_at": fetched_at} for (r, p), v in dedup.items()]
    for i in range(0, len(payload), 500):
        stmt = insert(IndicatorObservation).values(payload[i:i + 500])
        stmt = stmt.on_conflict_do_update(
            index_elements=["variable_id", "region", "period"],
            set_={"value": stmt.excluded.value, "fetched_at": stmt.excluded.fetched_at},
        )
        session.execute(stmt)
    return len(payload)


def is_stale(var: IndicatorVariable | None, hours: int | None = None) -> bool:
    if var is None or not var.last_fetched_at:
        return True
    try:
        last = datetime.fromisoformat(var.last_fetched_at)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last > timedelta(hours=hours or refresh_hours())


def refresh_variable(session: Session, spec: IndicatorSpec, trigger: str = "cli", force: bool = False,
                     client=None) -> dict:
    """변수 하나를 받아 DB 에 넣는다. 오래되지 않았고 force 가 아니면 건너뛴다(skipped)."""
    var = session.get(IndicatorVariable, spec.id)
    if var is None:
        sync_registry(session)
        var = session.get(IndicatorVariable, spec.id)
    if not force and not is_stale(var):
        return {"id": spec.id, "status": "skipped", "reason": "fresh", "last_period": var.last_period, "last_fetched_at": var.last_fetched_at}

    started, t0 = utc_now(), time.perf_counter()
    entry = IndicatorFetchLog(variable_id=spec.id, started_at=started, status="error", trigger=trigger)
    try:
        client = client or make_client(spec.source)
        # 증분 수집: DB 에 있으면 마지막 시점 - 12개월부터, 없으면 레지스트리 시작 시점부터
        start = spec.start
        if var.last_period and spec.freq == "M" and not force:
            start = max(spec.start, shift_month(var.last_period, -RELOAD_TAIL_MONTHS))
        rows, item = FETCHERS[spec.source](client, spec, start, today_period(spec.freq))
        count = upsert_observations(session, spec.id, rows, started)
        bounds = session.execute(
            select(func.min(IndicatorObservation.period), func.max(IndicatorObservation.period))
            .where(IndicatorObservation.variable_id == spec.id)).one()
        var.item_name = item or var.item_name
        var.first_period, var.last_period = bounds[0], bounds[1]
        var.last_fetched_at, var.last_status, var.last_error, var.updated_at = started, "ok", None, started
        entry.status, entry.rows_received, entry.rows_upserted, entry.last_period = "ok", len(rows), count, bounds[1]
        entry.duration_ms = int((time.perf_counter() - t0) * 1000)
        session.add(entry)
        session.commit()
        return {"id": spec.id, "status": "ok", "rows": count, "last_period": bounds[1], "duration_ms": entry.duration_ms}
    except Exception as exc:  # 한 변수의 실패가 다른 변수와 기존 자료를 해치지 않는다
        session.rollback()
        var = session.get(IndicatorVariable, spec.id)
        var.last_status, var.last_error, var.updated_at = "error", str(exc)[:500], utc_now()
        entry.error, entry.duration_ms = str(exc)[:500], int((time.perf_counter() - t0) * 1000)
        session.add(entry)
        session.commit()
        log.warning("indicator %s refresh failed: %s", spec.id, exc)
        return {"id": spec.id, "status": "error", "error": str(exc)[:200], "duration_ms": entry.duration_ms}


def refresh_all(session: Session, var_ids: list[str] | None = None, force: bool = False, trigger: str = "cli",
                clients: dict | None = None) -> dict:
    """여러 변수를 차례로 갱신. 동시에 두 번 돌지 않도록 잠근다(busy)."""
    if not REFRESH_LOCK.acquire(blocking=False):
        return {"status": "busy", "results": []}
    try:
        specs = enabled_specs() if not var_ids else [s for s in (get_spec(v) for v in var_ids) if s]
        clients = dict(clients or {})
        results = []
        for spec in specs:
            if spec.source not in clients:
                try:
                    clients[spec.source] = make_client(spec.source)
                except ValueError as exc:  # 키 미설정
                    results.append({"id": spec.id, "status": "error", "error": str(exc)})
                    continue
            results.append(refresh_variable(session, spec, trigger=trigger, force=force, client=clients[spec.source]))
        status = "ok" if all(r["status"] in ("ok", "skipped") for r in results) else "partial"
        return {"status": status, "checked_at": utc_now(), "results": results}
    finally:
        REFRESH_LOCK.release()


# ── DB 읽기 → 화면 형식 ──

def load_metric(session: Session, spec: IndicatorSpec, regions: list[str] | None = None, start: str | None = None) -> dict | None:
    """frontend/data/factor_sample.json 의 metrics[] 한 항목과 같은 모양으로 돌려준다. 자료가 없으면 None."""
    stmt = select(IndicatorObservation.region, IndicatorObservation.period, IndicatorObservation.value).where(IndicatorObservation.variable_id == spec.id)
    if regions and spec.scope != "nation":  # 전국 1계열은 지역 필터와 무관하게 준다
        stmt = stmt.where(IndicatorObservation.region.in_(regions))
    if start:
        stmt = stmt.where(IndicatorObservation.period >= start)
    rows = session.execute(stmt).all()
    if not rows:
        return None
    var = session.get(IndicatorVariable, spec.id)
    periods_seen = sorted({p for _, p, _ in rows})
    periods = month_range(periods_seen[0], periods_seen[-1]) if spec.freq == "M" else periods_seen
    index = {p: i for i, p in enumerate(periods)}
    order = SIDO if spec.scope == "sido" else ["전국"]
    series: dict[str, list] = {}
    for region, period, value in rows:
        series.setdefault(region, [None] * len(periods))[index[period]] = value
    series = {r: series[r] for r in order if r in series} | {r: v for r, v in series.items() if r not in order}
    return {
        "var": spec.id, "label": spec.label, "unit": spec.unit, "freq": spec.freq, "scope": spec.scope,
        "periods": periods, "series": series,
        "source": spec.source_ref, "source_name": SOURCES[spec.source]["name"], "source_url": SOURCES[spec.source]["url"],
        "method": spec.note or "원자료 그대로 (Open API)", "release": spec.release, "item": var.item_name if var else None,
        "live": True, "fetched_at": var.last_fetched_at if var else None,
    }


def variable_status(session: Session) -> list[dict]:
    rows = session.execute(select(IndicatorVariable).order_by(IndicatorVariable.id)).scalars().all()
    counts = dict(session.execute(select(IndicatorObservation.variable_id, func.count()).group_by(IndicatorObservation.variable_id)).all())
    out = []
    for v in rows:
        out.append({"id": v.id, "label": v.label, "driver": v.driver, "source": v.source, "source_ref": v.source_ref,
                    "freq": v.freq, "scope": v.scope, "unit": v.unit, "enabled": v.enabled, "item": v.item_name,
                    "first_period": v.first_period, "last_period": v.last_period, "rows": counts.get(v.id, 0),
                    "last_fetched_at": v.last_fetched_at, "last_status": v.last_status, "last_error": v.last_error,
                    "stale": is_stale(v)})
    return out


def recent_logs(session: Session, limit: int = 50) -> list[dict]:
    rows = session.execute(select(IndicatorFetchLog).order_by(IndicatorFetchLog.id.desc()).limit(limit)).scalars().all()
    return [{"id": r.id, "variable_id": r.variable_id, "started_at": r.started_at, "duration_ms": r.duration_ms, "status": r.status,
             "trigger": r.trigger, "rows_received": r.rows_received, "rows_upserted": r.rows_upserted, "last_period": r.last_period,
             "error": r.error} for r in rows]
