"""정량 지표 저장소: frontend/data/indicators 의 JSON 을 DB 에 적재하고, API 는 DB 에서 읽는다.

원본은 Git 의 JSON (dfmba-dashboard 파이프라인 산출). DB 에 없거나 DB 장애면 JSON 파일로 대체한다.
Render(Root=backend) 에는 frontend 폴더가 없으므로 배포 서버는 DB 만 본다. 적재는 scripts/load_indicators.py.
"""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndicatorSeries, IndicatorVariable
from app.db.session import get_engine
from app.services.content_store import digest, utc_now

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRS = [BACKEND_ROOT / "data" / "indicators", BACKEND_ROOT.parent / "frontend" / "data" / "indicators"]


def data_dir():
    for path in DATA_DIRS:
        if (path / "index.json").is_file():
            return path
    return None


def read_json(name):
    base = data_dir()
    if base is None:
        return None
    path = base / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


# ── 적재 ────────────────────────────────────────────────────
def load_from_files(session, index=None, verbose=False):
    """index.json 의 변수마다 V###.json 을 읽어 변수·계열 행을 넣거나 갱신한다. 해시가 같으면 건너뛴다."""
    index = index or read_json("index.json")
    if not index:
        raise FileNotFoundError("data/indicators/index.json 이 없습니다")
    now = utc_now()
    inserted = updated = skipped = 0
    for meta in index["variables"]:
        payload = read_json(meta["file"])
        if not payload:
            continue
        content_hash = digest(payload)
        row = session.get(IndicatorVariable, meta["id"])
        if row is not None and row.content_hash == content_hash:
            skipped += 1
            continue
        if row is None:
            row = IndicatorVariable(id=meta["id"])
            session.add(row)
            inserted += 1
        else:
            for old in session.scalars(select(IndicatorSeries).where(IndicatorSeries.variable_id == row.id)):
                session.delete(old)
            updated += 1
        row.name, row.freq, row.level = meta["name"], meta["freq"], meta["level"]
        row.source, row.table_code, row.note = meta.get("source", ""), meta.get("table", ""), meta.get("note", "")
        row.same_as, row.content_hash, row.updated_at = meta.get("same_as"), content_hash, now
        session.flush()
        for item, body in payload["items"].items():
            for region, s in body["regions"].items():
                session.add(IndicatorSeries(variable_id=row.id, item=item, region=region, freq=s["freq"], unit=body.get("unit", ""),
                                            start=s["dates"][0], end=s["dates"][-1], points=len(s["dates"]), dates=s["dates"], values=s["values"]))
        if verbose:
            print(f"{meta['id']:6} {meta['name'][:30]:32} 계열 {sum(len(b['regions']) for b in payload['items'].values())}")
    session.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "generated_at": index.get("generated_at")}


def seed_if_empty():
    """앱 시작 시: 테이블이 비어 있고 JSON 파일이 곁에 있으면(로컬 개발) 적재한다. 배포 서버는 스크립트로 적재한다."""
    if data_dir() is None:
        return None
    with Session(get_engine()) as session:
        if session.scalar(select(IndicatorVariable.id).limit(1)):
            return None
        return load_from_files(session)


# ── 조회 ────────────────────────────────────────────────────
def _variable_dict(row, series_rows):
    items = {}
    for s in series_rows:
        items.setdefault(s.item, {"unit": s.unit, "regions": {}})["regions"][s.region] = {"freq": s.freq, "dates": s.dates, "values": s.values}
    return {"id": row.id, "name": row.name, "same_as": row.same_as, "items": items}


def list_variables():
    """변수 목록. DB 가 비어 있으면 index.json 으로 대체한다."""
    with Session(get_engine()) as session:
        rows = session.scalars(select(IndicatorVariable).order_by(IndicatorVariable.id)).all()
        if not rows:
            index = read_json("index.json")
            return (index["variables"] if index else []), (index or {}).get("generated_at"), False
        series = session.execute(
            select(IndicatorSeries.variable_id, IndicatorSeries.item, IndicatorSeries.unit, IndicatorSeries.region, IndicatorSeries.start, IndicatorSeries.end)
        ).all()
    by_var = {}
    for variable_id, item, unit, region, start, end in series:
        v = by_var.setdefault(variable_id, {"items": {}, "regions": [], "start": start, "end": end})
        v["items"].setdefault(item, {"key": item, "unit": unit, "regions": 0})["regions"] += 1
        v["regions"].append(region)
        v["start"], v["end"] = min(v["start"], start), max(v["end"], end)
    out = []
    for row in rows:
        v = by_var.get(row.id, {"items": {}, "regions": [], "start": None, "end": None})
        out.append({"id": row.id, "name": row.name, "freq": row.freq, "level": row.level, "source": row.source, "table": row.table_code,
                    "note": row.note, "same_as": row.same_as, "items": list(v["items"].values()), "regions": v["regions"],
                    "start": v["start"], "end": v["end"], "file": f"{row.id}.json"})
    return out, max((r.updated_at for r in rows), default=None), True


def _filter(payload, item, region):
    if not (item or region):
        return payload
    items = {}
    for key, body in payload["items"].items():
        if item and key != item:
            continue
        regions = {r: s for r, s in body["regions"].items() if not region or r == region}
        if regions:
            items[key] = {"unit": body.get("unit", ""), "regions": regions}
    return {**payload, "items": items}


def get_variable_from_files(variable_id, item=None, region=None):
    """정적 JSON 에서 변수 하나 (DB 장애·미적재 시 대체). 없으면 None."""
    payload = read_json(f"{variable_id}.json")
    return _filter(payload, item, region) if payload else None


def get_variable(variable_id, item=None, region=None):
    """변수 하나. item·region 을 주면 그 계열만 담아 돌려준다. (payload, DB에서 읽었는지) 를 돌려주고 없으면 (None, False)."""
    with Session(get_engine()) as session:
        row = session.get(IndicatorVariable, variable_id)
        if row is None:
            return get_variable_from_files(variable_id, item, region), False
        query = select(IndicatorSeries).where(IndicatorSeries.variable_id == variable_id)
        if item:
            query = query.where(IndicatorSeries.item == item)
        if region:
            query = query.where(IndicatorSeries.region == region)
        return _variable_dict(row, session.scalars(query).all()), True
