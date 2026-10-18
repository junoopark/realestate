"""이용 통계 — 팀 Supabase 의 activity_logs(로그인·로그아웃·데이터 내려받기, main #15)를 숫자로만 보여 준다.

기록은 화면이 supabase-js 로 직접 넣는다(database/migrations/003_activity_logs.sql). 이 API 는 DB 소유자 연결로
관리자 집계 뷰(v_activity_daily · v_download_by_target)와 사용자 수만 읽는다. 사용자 ID·이메일은 내보내지 않는다.
테이블이 없는 DB(로컬 SQLite, 테스트용 Supabase)에서는 available=false 로 응답한다.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_engine
from app.services import cache

router = APIRouter(prefix="/usage", tags=["usage"])
EVENTS = ("login", "logout", "download")


def _available(conn) -> bool:
    if conn.dialect.name != "postgresql":
        return False
    row = conn.execute(text("SELECT to_regclass('public.activity_logs') IS NOT NULL AND "
                            "to_regclass('public.v_activity_daily') IS NOT NULL AND "
                            "to_regclass('public.v_download_by_target') IS NOT NULL")).scalar()
    return bool(row)


def usage_summary(days: int = 30, top: int = 10) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {"checked_at": now, "days": days, "source": "activity_logs (Supabase, main #15) · 집계 뷰 v_activity_daily · v_download_by_target"}
    try:
        with get_engine().connect() as conn:
            if not _available(conn):
                return {**base, "available": False,
                        "reason": "이 DB 에 activity_logs 가 없습니다. 사용 기록은 팀 Supabase 에 쌓이며 계정 전환 뒤 숫자가 나옵니다."}
            daily = [dict(r._mapping) for r in conn.execute(text(
                "SELECT day_kst, event, events, users FROM v_activity_daily "
                "WHERE day_kst >= (now() AT TIME ZONE 'Asia/Seoul')::date - :days ORDER BY day_kst, event"), {"days": days})]
            totals = {e: {"events": 0, "users": 0} for e in EVENTS}
            for r in conn.execute(text(
                    "SELECT event, count(*) AS events, count(DISTINCT user_id) AS users FROM activity_logs "
                    "WHERE occurred_at >= now() - make_interval(days => :days) GROUP BY event"), {"days": days}):
                totals[r.event] = {"events": int(r.events), "users": int(r.users)}
            users = conn.execute(text("SELECT count(DISTINCT user_id) FROM activity_logs "
                                      "WHERE occurred_at >= now() - make_interval(days => :days)"), {"days": days}).scalar()
            all_time = conn.execute(text("SELECT count(*), count(DISTINCT user_id), min(occurred_at) FROM activity_logs")).one()
            downloads = [dict(r._mapping) for r in conn.execute(text(
                "SELECT target, format, downloads, users, last_at FROM v_download_by_target "
                "ORDER BY downloads DESC, last_at DESC NULLS LAST LIMIT :top"), {"top": top})]
    except SQLAlchemyError as exc:
        return {**base, "available": False, "reason": f"이용 기록을 읽지 못했습니다: {type(exc).__name__}"}
    for r in daily:
        r["day_kst"] = r["day_kst"].isoformat()
        r["events"], r["users"] = int(r["events"]), int(r["users"])
    for r in downloads:
        r["downloads"], r["users"] = int(r["downloads"]), int(r["users"])
        r["last_at"] = r["last_at"].isoformat() if r["last_at"] else None
    return {**base, "available": True, "totals": totals, "users": int(users or 0),
            "all_time": {"events": int(all_time[0]), "users": int(all_time[1]),
                         "since": all_time[2].isoformat() if all_time[2] else None},
            "daily": daily, "downloads": downloads}


@router.get("")
def usage(response: Response, days: int = Query(default=30, ge=1, le=365, description="최근 며칠"),
          top: int = Query(default=10, ge=1, le=50, description="많이 내려받은 변수 몇 개")):
    """최근 days 일의 로그인·로그아웃·내려받기 횟수와 사용자 수(일별), 많이 내려받은 변수. 개인 식별 정보는 없다."""
    response.headers["Cache-Control"] = "public, max-age=300"
    response.headers["CDN-Cache-Control"] = "public, max-age=600, stale-while-revalidate=3600"
    return cache.get_or_set(f"usage:{days}:{top}", 300, lambda: usage_summary(days, top))
