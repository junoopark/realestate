"""Member preferences use their own metadata and non-exposed PostgreSQL schema."""

from functools import lru_cache
from threading import RLock

from fastapi import HTTPException
from sqlalchemy import String, create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.db.session import database_url


class MemberBase(DeclarativeBase):
    pass


class IndicatorLike(MemberBase):
    __tablename__ = "indicator_likes"
    __table_args__ = {"schema": "member_space"}
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    indicator_id: Mapped[str] = mapped_column(String(80), primary_key=True, index=True)


_initialization_lock = RLock()
_ready_engine = None


@lru_cache(maxsize=1)
def get_member_engine():
    url = database_url()
    sqlite = url.get_backend_name() == "sqlite"
    args = {"check_same_thread": False, "timeout": 15} if sqlite else {"connect_timeout": 10, "sslmode": "require"}
    options = {"schema_translate_map": {"member_space": None}} if sqlite else {}
    return create_engine(url, connect_args=args, pool_pre_ping=True, execution_options=options)


def initialize_member_storage():
    global _ready_engine
    with _initialization_lock:
        _ready_engine = None
        engine = get_member_engine()
        # Creating the schema/tables and revoking browser privileges is one
        # transaction, so a partly initialized store is never accepted by routes.
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(742903817)"))
                connection.execute(text("CREATE SCHEMA IF NOT EXISTS member_space"))
                connection.execute(text("REVOKE ALL ON SCHEMA member_space FROM PUBLIC"))
            MemberBase.metadata.create_all(connection)
            if engine.dialect.name == "postgresql":
                connection.execute(text("ALTER TABLE member_space.indicator_likes ENABLE ROW LEVEL SECURITY"))
                connection.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA member_space FROM PUBLIC"))
                roles = set(connection.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")).scalars())
                for role in ("anon", "authenticated"):
                    if role in roles:
                        # role is from the fixed allowlist above, never user input.
                        connection.execute(text(f"REVOKE ALL ON SCHEMA member_space FROM {role}"))
                        connection.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA member_space FROM {role}"))
                        connection.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA member_space REVOKE ALL ON TABLES FROM {role}"))
                connection.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA member_space REVOKE ALL ON TABLES FROM PUBLIC"))
        _ready_engine = engine


def storage_unavailable():
    return HTTPException(status_code=503, detail="좋아요 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")


def get_member_session():
    try:
        engine = get_member_engine()
    except Exception:
        raise storage_unavailable() from None
    if engine is not _ready_engine:
        raise storage_unavailable()
    with Session(engine) as session:
        try:
            yield session
        except HTTPException:
            raise
        except SQLAlchemyError:
            try:
                session.rollback()
            except SQLAlchemyError:
                pass
            raise storage_unavailable() from None


def member_storage_status():
    try:
        engine = get_member_engine()
        kind = engine.dialect.name
        available = engine is _ready_engine
        if available:
            with Session(engine) as session:
                session.execute(select(IndicatorLike.indicator_id).limit(1))
    except Exception:
        available = False
        try:
            kind = database_url().get_backend_name()
        except Exception:
            kind = "unavailable"
    return {"type": kind, "available": available, "persistent": available and kind == "postgresql"}
