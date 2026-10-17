"""지표 기본 패널 — 전처리본(frontend/data/factor_sample.json 과 같은 모양)을 DB 에 적재하고, 화면 형식으로 다시 꺼낸다.

  적재: python scripts/seed_indicators.py  (한 번, 또는 새 전처리본이 나왔을 때)
        → indicator_series(계열 106개) + indicator_series_values(값 약 8만 개) + content_snapshots['indicator-panel'](지역·별칭)
  조회: /indicators/bundle?set=all 이 이 패널을 읽고, Open API 로 받는 변수는 같은 (변수, 지역 단위) 계열을 실제 수집값으로 덮어쓴다.

다시 적재해도 결과가 같다: 파일에 있는 계열의 값은 지우고 다시 넣고, 파일에서 빠진 계열은 지운다.
"""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot, IndicatorSeries, IndicatorSeriesValue

META_KEY = "indicator-panel"
SCOPE_ORDER = ["sido", "seoul", "nation", "gu"]  # 변수 하나만 요청할 때 고르는 순서
BATCH = 5000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def series_id(metric: dict) -> str:
    return f"{metric['scope']}:{metric['column']}"


def _number(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN 제외


def _chunks(items, size=BATCH):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ── 적재 ──

def seed_panel(session: Session, data: dict) -> dict:
    """전처리본 JSON(dict)을 DB 에 넣는다. 반환: 계열·값·삭제 계열 수."""
    metrics = data.get("metrics") or []
    if not metrics:
        raise ValueError("metrics 가 비어 있습니다. factor_sample.json 형식인지 확인하세요.")
    now = utc_now()
    dataset = str(data.get("generated") or "")
    seen: dict[str, dict] = {}
    for order, m in enumerate(metrics):
        sid = series_id(m)
        if sid in seen:
            raise ValueError(f"같은 계열 ID 가 두 번 나옵니다: {sid}")
        seen[sid] = {"order": order, "metric": m}

    # 파일에서 빠진 계열은 지운다(값도 함께)
    existing = set(session.execute(select(IndicatorSeries.id)).scalars())
    removed = sorted(existing - set(seen))
    for ids in _chunks(removed, 500):
        session.execute(delete(IndicatorSeriesValue).where(IndicatorSeriesValue.series_id.in_(ids)))
        session.execute(delete(IndicatorSeries).where(IndicatorSeries.id.in_(ids)))

    # 계열 메타: 있으면 고치고 없으면 만든다
    for sid, item in seen.items():
        m = item["metric"]
        fields = dict(var_id=m["var"], scope=m["scope"], column_name=m["column"], label=m.get("label") or m["var"],
                      unit=m.get("unit") or "", freq=m.get("freq") or "M", periods=list(m.get("periods") or []),
                      source=m.get("source") or "", method=m.get("method") or "", release=m.get("release") or "",
                      filled=m.get("filled"), provisional_from=m.get("provisional_from"), sort_order=item["order"],
                      dataset=dataset, loaded_at=now)
        row = session.get(IndicatorSeries, sid)
        if row is None:
            session.add(IndicatorSeries(id=sid, **fields))
        else:
            for k, v in fields.items():
                setattr(row, k, v)
    session.flush()

    # 값: 계열별로 지우고 다시 넣는다 (기간이 줄어든 경우까지 정확히 맞추기 위해)
    for ids in _chunks(list(seen), 500):
        session.execute(delete(IndicatorSeriesValue).where(IndicatorSeriesValue.series_id.in_(ids)))
    rows = []
    for sid, item in seen.items():
        m = item["metric"]
        periods = m.get("periods") or []
        for region, values in (m.get("series") or {}).items():
            for period, v in zip(periods, values):
                f = _number(v)
                if f is not None:
                    rows.append({"series_id": sid, "region": region, "period": period, "value": f})
    for chunk in _chunks(rows):
        session.execute(insert(IndicatorSeriesValue), chunk)

    meta = {"generated": data.get("generated"), "source_note": data.get("_source"), "aliases": data.get("aliases") or {},
            "regions": data.get("regions") or {}, "loaded_at": now, "series": len(seen), "values": len(rows)}
    digest = hashlib.sha256(json.dumps(meta, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    snap = session.get(ContentSnapshot, META_KEY)
    if snap is None:
        session.add(ContentSnapshot(key=META_KEY, content=meta, content_hash=digest, updated_at=now))
    else:
        snap.content, snap.content_hash, snap.updated_at = meta, digest, now
    session.commit()
    return {"status": "ok", "series": len(seen), "values": len(rows), "removed_series": len(removed), "loaded_at": now,
            "dataset": dataset}


# ── 조회 ──

def panel_meta(session: Session) -> dict | None:
    snap = session.get(ContentSnapshot, META_KEY)
    return dict(snap.content) if snap else None


def _region_order(meta: dict | None) -> dict[str, int]:
    regions = (meta or {}).get("regions") or {}
    order = ["전국", "서울"] + list(regions.get("sido") or []) + list(regions.get("gu") or [])
    out: dict[str, int] = {}
    for r in order:
        out.setdefault(r, len(out))
    return out


def panel_metrics(session: Session, var_ids: list[str] | None = None, regions: list[str] | None = None,
                  start: str | None = None, scope: str | None = None) -> list[dict]:
    """factor_sample.json 의 metrics[] 와 같은 모양의 목록. 원본 파일 순서를 지킨다."""
    q = select(IndicatorSeries).order_by(IndicatorSeries.sort_order)
    if var_ids:
        q = q.where(IndicatorSeries.var_id.in_(var_ids))
    if scope:
        q = q.where(IndicatorSeries.scope == scope)
    series = session.execute(q).scalars().all()
    if not series:
        return []
    by_id = {s.id: s for s in series}
    vq = select(IndicatorSeriesValue.series_id, IndicatorSeriesValue.region, IndicatorSeriesValue.period, IndicatorSeriesValue.value)
    if var_ids or scope:
        vq = vq.where(IndicatorSeriesValue.series_id.in_(list(by_id)))
    if start:
        vq = vq.where(IndicatorSeriesValue.period >= start)
    values: dict[str, dict[str, dict[str, float]]] = {}
    for sid, region, period, value in session.execute(vq):
        if sid in by_id:
            values.setdefault(sid, {}).setdefault(region, {})[period] = value

    rank = _region_order(panel_meta(session))
    out = []
    for s in series:
        periods = [p for p in (s.periods or []) if not start or p >= start]
        by_region = values.get(s.id, {})
        names = [r for r in by_region if not regions or s.scope == "nation" or r in regions]
        names.sort(key=lambda r: (rank.get(r, len(rank)), r))
        out.append({
            "var": s.var_id, "column": s.column_name, "label": s.label, "unit": s.unit, "freq": s.freq, "scope": s.scope,
            "periods": periods, "series": {r: [by_region[r].get(p) for p in periods] for r in names},
            "source": s.source, "source_name": "", "source_url": "", "method": s.method, "release": s.release,
            "filled": s.filled, "provisional_from": s.provisional_from,
            "live": False, "fetched_at": s.loaded_at, "origin": "db(panel)", "stale": False,
        })
    return out


def pick_metric(metrics: list[dict], scope: str | None = None) -> dict | None:
    """변수 하나를 요청받았을 때 줄 계열: 지정한 지역 단위, 없으면 sido → seoul → nation → gu 순."""
    if scope:
        return next((m for m in metrics if m["scope"] == scope), None)
    for sc in SCOPE_ORDER:
        m = next((m for m in metrics if m["scope"] == sc), None)
        if m:
            return m
    return metrics[0] if metrics else None


def panel_status(session: Session) -> dict:
    meta = panel_meta(session) or {}
    series = session.execute(select(func.count()).select_from(IndicatorSeries)).scalar() or 0
    values = session.execute(select(func.count()).select_from(IndicatorSeriesValue)).scalar() or 0
    variables = session.execute(select(func.count(func.distinct(IndicatorSeries.var_id)))).scalar() or 0
    return {"loaded": series > 0, "variables": variables, "series": series, "values": values,
            "generated": meta.get("generated"), "loaded_at": meta.get("loaded_at")}


# ── Open API 수집값 → 기본 패널 계열에 이어붙이기 ──

def _targets(session: Session, spec) -> list:
    """레지스트리 outputs 가 가리키는 패널 계열. 변수·지역 단위(+열 이름 일부)로 하나만 맞아야 쓴다."""
    out = []
    for o in getattr(spec, "outputs", ()) or ():
        rows = session.execute(select(IndicatorSeries).where(IndicatorSeries.var_id == spec.var_id,
                                                            IndicatorSeries.scope == o.scope)).scalars().all()
        if o.match:
            rows = [r for r in rows if o.match in r.column_name]
        if len(rows) == 1:
            out.append((o, rows[0]))
        elif len(rows) > 1:
            import logging
            logging.getLogger(__name__).warning("%s: %s 계열이 %d개라 이어붙이지 않습니다. outputs 에 match 를 적으세요.",
                                                spec.id, o.scope, len(rows))
    return out


def apply_outputs(session: Session, spec, rows: list[tuple]) -> dict:
    """수집한 (지역, 시점, 값) 을 패널 계열에 반영한다. 겹치는 시점은 바뀐 값만 고치고, 새 시점은 뒤에 붙인다.
    화면이 쓰는 것만: 패널 계열에 이미 있는 지역(또는 outputs.regions)과 계열 시작 시점 이후만 쓴다."""
    from app.services.indicator_pipeline import _dialect_insert, _same, month_range
    written = targets = 0
    for o, s in _targets(session, spec):
        targets += 1
        rename = o.rename_map
        allowed = set(o.regions) if o.regions else set(session.execute(
            select(IndicatorSeriesValue.region).where(IndicatorSeriesValue.series_id == s.id).distinct()).scalars())
        first = (s.periods or [None])[0]
        vals = {}
        for region, period, value in rows:
            r2 = rename.get(region, region)
            if allowed and r2 not in allowed:
                continue
            if first and period < first:
                continue
            vals[(r2, period)] = value
        if not vals:
            continue
        ps = sorted({p for _, p in vals})
        existing = {(r, p): v for r, p, v in session.execute(
            select(IndicatorSeriesValue.region, IndicatorSeriesValue.period, IndicatorSeriesValue.value)
            .where(IndicatorSeriesValue.series_id == s.id, IndicatorSeriesValue.period >= ps[0],
                   IndicatorSeriesValue.period <= ps[-1]))}
        changed = [{"series_id": s.id, "region": r, "period": p, "value": v}
                   for (r, p), v in vals.items() if not _same(existing.get((r, p)), v)]
        insert_ = _dialect_insert(session)
        for chunk in _chunks(changed, 1000):
            stmt = insert_(IndicatorSeriesValue).values(chunk)
            session.execute(stmt.on_conflict_do_update(index_elements=["series_id", "region", "period"],
                                                       set_={"value": stmt.excluded.value}))
        written += len(changed)
        allp = set(s.periods or []) | set(ps)
        newp = month_range(min(allp), max(allp)) if s.freq == "M" else sorted(allp)
        if newp != list(s.periods or []):
            s.periods = newp
    return {"targets": targets, "written": written}


def live_series(session: Session, specs) -> dict:
    """패널 계열 ID → 그 계열을 채우는 Open API 수집 정보 (한 번이라도 성공한 것만)."""
    from app.db.models import IndicatorVariable
    out = {}
    for spec in specs:
        var = session.get(IndicatorVariable, spec.id)
        if var is None or not var.last_fetched_at:
            continue
        for _, s in _targets(session, spec):
            out[s.id] = {"spec": spec.id, "source": spec.source, "source_ref": spec.source_ref, "fetched_at": var.last_fetched_at}
    return out
