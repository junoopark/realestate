"""Counts are public; each member can change only their own indicator likes."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.member_auth import Member, optional_member, require_member
from app.member_store import IndicatorLike, get_member_session

router = APIRouter(prefix="/engagement", tags=["engagement"])
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "member-indicators.json"


def indicator_registry():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list) or not data:
            raise ValueError("Invalid indicator registry")
        registry = {}
        for item in data:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("id", "name", "driver")):
                raise ValueError("Invalid indicator registry")
            if len(item["id"]) > 80 or item["id"] in registry:
                raise ValueError("Invalid indicator registry")
            registry[item["id"]] = {key: item[key] for key in ("id", "name", "driver")}
        return registry
    except (OSError, ValueError, TypeError):
        raise HTTPException(status_code=503, detail="지표 목록을 준비 중입니다.") from None


def known_indicator(indicator_id):
    if indicator_id not in indicator_registry():
        raise HTTPException(status_code=404, detail="지표를 찾을 수 없습니다.")


def _indicators(session, member):
    registry = indicator_registry()
    counts = dict(session.execute(select(IndicatorLike.indicator_id, func.count()).group_by(IndicatorLike.indicator_id)).all())
    own = set(session.scalars(select(IndicatorLike.indicator_id).where(IndicatorLike.user_id == member.id))) if member else set()
    return [{**item, "likes": counts.get(key, 0), "liked_by_me": key in own} for key, item in registry.items()]


def _indicator_result(session, indicator_id, member):
    likes = session.scalar(select(func.count()).select_from(IndicatorLike).where(IndicatorLike.indicator_id == indicator_id))
    own = session.get(IndicatorLike, (member.id, indicator_id)) is not None
    return {"id": indicator_id, "likes": likes, "liked_by_me": own}


async def reject_payload(request: Request):
    # No arbitrary author/user IDs or other mutation fields are accepted.
    if await request.body():
        raise HTTPException(status_code=422, detail="이 요청에는 본문을 넣지 않습니다.")


@router.get("/indicators")
def list_indicators(member: Member | None = Depends(optional_member), session: Session = Depends(get_member_session)):
    return {"items": _indicators(session, member)}


@router.get("/popular")
def popular_indicators(limit: int = Query(default=5, ge=1, le=50),
                       member: Member | None = Depends(optional_member), session: Session = Depends(get_member_session)):
    items = [item for item in _indicators(session, member) if item["likes"] > 0]
    items.sort(key=lambda item: (-item["likes"], item["id"]))
    return {"items": items[:limit]}


@router.put("/indicators/{indicator_id}/like")
def like_indicator(indicator_id: str, member: Member = Depends(require_member),
                   session: Session = Depends(get_member_session), no_payload=Depends(reject_payload)):
    known_indicator(indicator_id)
    insert = postgresql_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(IndicatorLike).values(user_id=member.id, indicator_id=indicator_id).on_conflict_do_nothing(
        index_elements=["user_id", "indicator_id"])
    session.execute(statement)
    session.commit()
    return _indicator_result(session, indicator_id, member)


@router.delete("/indicators/{indicator_id}/like")
def unlike_indicator(indicator_id: str, member: Member = Depends(require_member),
                     session: Session = Depends(get_member_session), no_payload=Depends(reject_payload)):
    known_indicator(indicator_id)
    session.execute(delete(IndicatorLike).where(IndicatorLike.user_id == member.id, IndicatorLike.indicator_id == indicator_id))
    session.commit()
    return _indicator_result(session, indicator_id, member)
