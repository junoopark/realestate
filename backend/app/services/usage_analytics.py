"""Validated anonymous attention events and aggregate-only usage reporting."""

import hashlib
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy import DateTime, MetaData, Table, bindparam, case, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot, IndicatorSeries, PolicyBrief, PolicyDocument, UsageEvent
from app.db.session import get_engine
from app.services.content_store import read_seed
from app.services.indicator_registry import REGISTRY

KST = timezone(timedelta(hours=9))
ACTIVITY_EVENTS = ("login", "logout", "download")
VIEW_EVENTS = ("indicator_view", "policy_view", "policy_open")
_rate_lock = threading.Lock()
_rates: OrderedDict[str, tuple[int, int]] = OrderedDict()
_global_rate = (0, 0)


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds")


def rate_limit(session_id: str, size: int):
    """Bounded per-process and per-tab budgets; no IP addresses are retained."""
    global _global_rate
    minute = int(time.monotonic() // 60)
    with _rate_lock:
        global_count = _global_rate[1] if _global_rate[0] == minute else 0
        bucket, count = _rates.get(session_id, (minute, 0))
        count = count if bucket == minute else 0
        if count + size > 120 or global_count + size > 2000:
            raise HTTPException(429, "잠시 후 다시 시도하세요.", headers={"Retry-After": "60"})
        _rates[session_id] = (minute, count + size)
        _rates.move_to_end(session_id)
        while len(_rates) > 4096:
            _rates.popitem(last=False)
        _global_rate = (minute, global_count + size)


def indicator_catalog(session: Session):
    catalog = {}
    for spec in REGISTRY:
        var = spec.var or spec.id.split(".")[0]
        for scope in ({o.scope for o in spec.outputs} or {spec.scope}):
            catalog.setdefault(f"{var}:{scope}", {"label": spec.label, "scope": scope})
    for row in session.execute(select(IndicatorSeries).order_by(IndicatorSeries.sort_order)).scalars():
        catalog[f"{row.var_id}:{row.scope}"] = {"label": row.label, "scope": row.scope}
    for target, detail in list(catalog.items()):
        if detail["scope"] == "sido":
            catalog[target + "-map"] = {**detail, "scope": "sido-map"}
    return catalog


def _content(session: Session, key: str):
    row = session.get(ContentSnapshot, key)
    return row.content if row else (read_seed(key) or {})


def _policy_identity_url(url):
    """Like policy_briefs.identity_url, also ignore MOLIT's list-page position."""
    parts = urlsplit(url)
    display_parameters = {"kw", "src", "curpage", "lcmspage"}
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                             if k.lower() not in display_parameters and not k.lower().startswith("utm_")))
    return urlunsplit(("https", parts.netloc.lower().removeprefix("www."), parts.path, query, ""))


def _canonical_policy(target, item, aliases):
    url = item.get("source_url") or next((s.get("url") for s in item.get("sources", []) if s.get("url")), "")
    primary = item.get("original_source_url") or url
    identity = _policy_identity_url(primary) if primary else target
    identity = aliases.get(identity, identity)
    return {
        "target": "policy:" + hashlib.sha256(identity.encode()).hexdigest(),
        "label": item["title"], "scope": "", "agency": item.get("agency", ""), "source_url": url,
    }


def resolve_policy(session: Session, target: str):
    kind, separator, identifier = target.partition(":")
    if not separator or not identifier:
        return None
    reviewed = _content(session, "policies").get("policies", [])
    aliases = {}
    for item in reviewed:
        primary = item.get("original_source_url") or item.get("source_url")
        if primary:
            for key in ("original_source_url", "source_url"):
                if item.get(key):
                    aliases[_policy_identity_url(item[key])] = _policy_identity_url(primary)
    if kind == "brief":
        for item in reviewed:
            if item.get("id") == identifier:
                return _canonical_policy(target, item, aliases)
        if identifier.startswith("auto-"):
            brief = session.get(PolicyBrief, identifier[5:])
            if brief and brief.content:
                return _canonical_policy(target, brief.content, aliases)
    elif kind == "monitor":
        row = session.get(PolicyDocument, identifier)
        if row:
            return _canonical_policy(target, {"title": row.title, "agency": row.agency, "source_url": row.source_url}, aliases)
    elif kind == "history":
        for item in _content(session, "policy-history").get("events", []):
            if item.get("id") == identifier:
                return _canonical_policy(target, item, aliases)
    return None


def record_events(batch):
    session_id = str(batch.session_id)
    rate_limit(session_id, len(batch.events))
    engine = get_engine()
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    accepted = duplicates = rejected = 0
    now = utc_now()
    with Session(engine) as session:
        known_count = session.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.session_id == session_id))
        if known_count >= 1000:
            raise HTTPException(429, "한 탭의 기록 한도에 도달했습니다.")
        catalog = indicator_catalog(session)
        resolved = {}
        for event in batch.events:
            if event.event == "indicator_view":
                detail = catalog.get(event.target)
                target = {"target": event.target, **detail, "agency": "", "source_url": ""} if detail else None
            else:
                if event.target not in resolved:
                    resolved[event.target] = resolve_policy(session, event.target)
                target = resolved[event.target]
            if target is None:
                rejected += 1
                continue
            statement = insert(UsageEvent).values(
                event_id=str(event.event_id), session_id=session_id, event=event.event,
                page=event.page, occurred_at=now, **target,
            ).on_conflict_do_nothing()
            written = session.execute(statement).rowcount
            accepted += int(bool(written))
            duplicates += int(not written)
        session.commit()
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected, "ignored": False}


def _day(column, dialect):
    return func.date(func.timezone("Asia/Seoul", column)) if dialect == "postgresql" else func.date(column, "+9 hours")


def _empty_activity():
    return {
        "activity_available": False, "totals": {e: {"events": 0, "users": 0} for e in ACTIVITY_EVENTS},
        "users": 0, "all_time": {"events": 0, "users": 0, "since": None},
        "daily": [], "downloads": [], "download_details": {"targets": [], "formats": [], "regions": []},
    }


def _activity_summary(conn, cutoff, end, top, catalog):
    empty = _empty_activity()
    if not inspect(conn).has_table("activity_logs"):
        return {**empty, "activity_reason": "activity_logs 테이블이 없어 로그인·다운로드 기록은 아직 제공되지 않습니다."}
    table = Table("activity_logs", MetaData(), autoload_with=conn, resolve_fks=False)
    c = table.c
    selected = (c.occurred_at >= cutoff, c.occurred_at <= end)
    totals = empty["totals"]
    for row in conn.execute(select(c.event, func.count(), func.count(func.distinct(c.user_id))).where(*selected).group_by(c.event)):
        if row[0] in totals:
            totals[row[0]] = {"events": row[1], "users": row[2]}
    users = conn.scalar(select(func.count(func.distinct(c.user_id))).where(*selected))
    all_time = conn.execute(select(func.count(), func.count(func.distinct(c.user_id)), func.min(c.occurred_at))).one()
    day = _day(c.occurred_at, conn.dialect.name)
    daily = [{"day_kst": str(r[0]), "event": r[1], "events": r[2], "users": r[3]} for r in conn.execute(
        select(day, c.event, func.count(), func.count(func.distinct(c.user_id))).where(*selected).group_by(day, c.event).order_by(day, c.event))]
    fmt = func.coalesce(c.detail["format"].as_string(), "unknown")
    count = func.count()
    user_count = func.count(func.distinct(c.user_id))
    last = func.max(c.occurred_at)
    download_filter = (*selected, c.event == "download")

    def describe(target):
        return catalog.get(target, {"label": target or "대상 미기록", "scope": (target or "").partition(":")[2]})

    downloads = [{"target": r[0], **describe(r[0]), "format": r[1], "downloads": r[2], "users": r[3], "last_at": iso(r[4])}
                 for r in conn.execute(select(c.target, fmt, count, user_count, last).where(*download_filter)
                                       .group_by(c.target, fmt).order_by(count.desc(), c.target, fmt).limit(top))]
    targets = [{"target": r[0], **describe(r[0]), "downloads": r[1], "users": r[2], "last_at": iso(r[3])}
               for r in conn.execute(select(c.target, count, user_count, last).where(*download_filter)
                                     .group_by(c.target).order_by(count.desc(), c.target).limit(top))]
    formats = [{"format": r[0], "downloads": r[1], "users": r[2]}
               for r in conn.execute(select(fmt, count, user_count).where(*download_filter).group_by(fmt).order_by(count.desc(), fmt))]
    if conn.dialect.name == "postgresql":
        region_sql = """
            SELECT region, count(DISTINCT a.id) AS downloads, count(DISTINCT a.user_id) AS users
            FROM activity_logs a
            CROSS JOIN LATERAL jsonb_array_elements_text(
              CASE WHEN jsonb_typeof(a.detail->'regions') = 'array' THEN a.detail->'regions' ELSE '[]'::jsonb END
            ) AS selected_regions(region)
            WHERE a.event = 'download' AND a.occurred_at >= :cutoff AND a.occurred_at <= :end
            GROUP BY region ORDER BY downloads DESC, region LIMIT :top
        """
    else:
        region_sql = """
            SELECT r.value AS region, count(DISTINCT a.id) AS downloads, count(DISTINCT a.user_id) AS users
            FROM activity_logs a, json_each(CASE WHEN json_type(a.detail, '$.regions') = 'array'
              THEN json_extract(a.detail, '$.regions') ELSE '[]' END) r
            WHERE a.event = 'download' AND a.occurred_at >= :cutoff AND a.occurred_at <= :end
            GROUP BY r.value ORDER BY downloads DESC, r.value LIMIT :top
        """
    region_query = text(region_sql).bindparams(bindparam("cutoff", type_=DateTime(timezone=True)),
                                               bindparam("end", type_=DateTime(timezone=True)))
    regions = [dict(r._mapping) for r in conn.execute(region_query, {"cutoff": cutoff, "end": end, "top": top})]
    return {
        "activity_available": True, "totals": totals, "users": users or 0,
        "all_time": {"events": all_time[0], "users": all_time[1], "since": iso(all_time[2])},
        "daily": daily, "downloads": downloads,
        "download_details": {"targets": targets, "formats": formats, "regions": regions},
    }


def _views_summary(session, cutoff, end, top):
    measurement = session.get(ContentSnapshot, "usage-measurement")
    event = UsageEvent
    selected = (event.occurred_at >= cutoff, event.occurred_at <= end)
    count = func.count()
    sessions = func.count(func.distinct(event.session_id))
    totals = {name: {"events": 0, "sessions": 0} for name in VIEW_EVENTS}
    for row in session.execute(select(event.event, count, sessions).where(*selected).group_by(event.event)):
        if row[0] in totals:
            totals[row[0]] = {"events": row[1], "sessions": row[2]}
    day = _day(event.occurred_at, session.bind.dialect.name)
    daily = [{"day_kst": str(r[0]), "event": r[1], "events": r[2], "sessions": r[3]} for r in session.execute(
        select(day, event.event, count, sessions).where(*selected).group_by(day, event.event).order_by(day, event.event))]
    last = func.max(event.occurred_at)
    indicators = [{"target": r[0], "label": r[1], "scope": r[2], "views": r[3], "sessions": r[4], "last_at": iso(r[5])}
                  for r in session.execute(
                      select(event.target, func.max(event.label), func.max(event.scope), count, sessions, last)
                      .where(*selected, event.event == "indicator_view").group_by(event.target)
                      .order_by(count.desc(), event.target).limit(top))]
    view_count = func.sum(case((event.event == "policy_view", 1), else_=0))
    open_count = func.sum(case((event.event == "policy_open", 1), else_=0))
    policies = [{"target": r[0], "title": r[1], "agency": r[2], "url": r[3],
                 "views": r[4], "opens": r[5], "sessions": r[6], "last_at": iso(r[7])}
                for r in session.execute(
                    select(event.target, func.max(event.label), func.max(event.agency), func.max(event.source_url),
                           view_count, open_count, sessions, last)
                    .where(*selected, event.event.in_(("policy_view", "policy_open")))
                    .group_by(event.target).order_by((view_count + open_count).desc(), event.target).limit(top))]
    return {
        "available": True, "since": measurement.content.get("started_at") if measurement else None,
        "first_event_at": iso(session.scalar(select(func.min(event.occurred_at)))),
        "totals": totals, "sessions": session.scalar(select(sessions).where(*selected)) or 0,
        "daily": daily, "indicators": indicators, "policies": policies,
    }


def usage_summary(days=30, top=10):
    now = utc_now()
    start_kst = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    cutoff = start_kst.astimezone(timezone.utc)
    base = {
        "checked_at": iso(now), "days": days, "source": "activity_logs + usage_events (Supabase 집계)",
        "period": {"start_at": iso(cutoff), "end_at": iso(now), "timezone": "Asia/Seoul",
                   "label": f"KST 오늘 포함 최근 {days}일"},
        "notes": [
            "로그인·다운로드는 로그인 계정별 기록이며, 조회는 로그인 여부와 무관한 익명 탭 방문 기록입니다.",
            "같은 탭 방문에서 같은 대상·행동은 한 번만 기록합니다. 세션 수는 실제 사람 수가 아닙니다.",
            "지표 조회는 차트·지도 영역이 화면에 2초 이상 보인 경우, 정책 조회는 상세 펼침, 원문 클릭은 링크 선택입니다.",
            "조회 계측 도입 전 열람은 복원할 수 없습니다. 추적 거부 설정·광고 차단·네트워크 실패로 누락될 수 있습니다.",
            "공개 수집 API에 전달된 관심 신호이며 실제 독해·정확한 이용자 수를 검증한 통계는 아닙니다.",
            "지역별 다운로드는 선택한 지역마다 한 번씩 집계되어 총 다운로드 수와 합계가 다를 수 있습니다. 조회의 선택 지역은 수집하지 않습니다.",
        ],
    }
    engine = get_engine()
    try:
        with Session(engine) as session:
            catalog = indicator_catalog(session)
    except SQLAlchemyError:
        catalog = {}
    try:
        with engine.connect() as conn:
            activity = _activity_summary(conn, cutoff, now, top, catalog)
    except SQLAlchemyError:
        activity = {**_empty_activity(), "activity_reason": "로그인·다운로드 저장소를 읽지 못했습니다."}
    try:
        with Session(engine) as session:
            views = _views_summary(session, cutoff, now, top)
    except SQLAlchemyError:
        views = {"available": False, "since": None, "first_event_at": None,
                 "reason": "익명 조회 기록 저장소를 읽지 못했습니다.",
                 "totals": {e: {"events": 0, "sessions": 0} for e in VIEW_EVENTS},
                 "sessions": 0, "daily": [], "indicators": [], "policies": []}
    return {**base, **activity, "views": views,
            "available": activity["activity_available"] or views["available"]}
