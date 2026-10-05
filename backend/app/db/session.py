"""Shared storage: local SQLite, or PostgreSQL via DATABASE_URL."""

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def database_url():
    default = f"sqlite:///{(Path(__file__).resolve().parents[2] / 'local.db').as_posix()}"
    value = os.getenv("DATABASE_URL", "").strip() or default
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    url = make_url(value)
    if url.drivername in ("postgresql", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() not in ("sqlite", "postgresql"):
        raise ValueError("Only SQLite and PostgreSQL are supported")
    return url


@lru_cache(maxsize=1)
def get_engine():
    url = database_url()
    args = {"check_same_thread": False, "timeout": 15} if url.get_backend_name() == "sqlite" else {"connect_timeout": 10}
    if url.get_backend_name() == "postgresql":
        # Supabase Session pooler uses TLS. Never log connection strings.
        args["sslmode"] = "require"
    return create_engine(url, connect_args=args, pool_pre_ping=True)


def get_db():
    with Session(get_engine()) as session:
        yield session


def storage_info(available=True):
    try:
        kind = database_url().get_backend_name()
    except (ValueError, TypeError):
        kind = "unavailable"
    return {
        "type": kind,
        "available": available,
        "persistent": available and kind == "postgresql",
        "note": ("PostgreSQL 저장소" if kind == "postgresql" else "로컬 SQLite 저장소: Render 임시 디스크에서는 재배포 시 수집 이력이 사라질 수 있습니다.") if available else "저장소 연결 실패: 검증한 정적 자료만 제공합니다.",
    }
