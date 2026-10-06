"""Import reviewed JSON at startup, serve it through the database."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import ContentSnapshot
from app.db.session import Base, get_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def read_seed(key):
    # backend/data is committed so Render's backend root works independently.
    candidates = [BACKEND_ROOT / "data" / f"{key}.json", BACKEND_ROOT.parent / "frontend" / "data" / f"{key}.json"]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    return None


def initialize_storage():
    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # The browser uses FastAPI, never Supabase's anonymous REST table access.
        # Fixed ORM table names, not user input. The DB owner still serves the API.
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
    with Session(engine) as session:
        for key in ("knowledge", "policies", "policy-history", "warning"):
            value = read_seed(key)
            if value is None:
                continue
            content_hash = digest(value)
            row = session.get(ContentSnapshot, key)
            if row is None:
                session.add(ContentSnapshot(key=key, content=value, content_hash=content_hash, updated_at=utc_now()))
            elif row.content_hash != content_hash:
                # Reviewed git content remains the source of truth for this MVP.
                row.content, row.content_hash, row.updated_at = value, content_hash, utc_now()
        session.commit()


def get_content(key):
    with Session(get_engine()) as session:
        row = session.get(ContentSnapshot, key)
        return row.content if row else read_seed(key)
