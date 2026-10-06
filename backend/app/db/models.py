"""Qualitative content tables and quantitative indicator tables."""

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class IndicatorVariable(Base):
    """데이터사전 변수 하나 (V001 …). 시계열은 indicator_series 에 항목·지역별로 나뉘어 있다."""
    __tablename__ = "indicator_variables"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    freq: Mapped[str] = mapped_column(String(4))            # 데이터사전상 주기: M · Q · H · Y
    level: Mapped[str] = mapped_column(String(20))          # 시도 / 서울구 / 시도+서울구 / 전국
    source: Mapped[str] = mapped_column(String(40))
    table_code: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    same_as: Mapped[str | None] = mapped_column(String(10))  # 중복 변수면 원본 변수 id
    content_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))


class IndicatorSeries(Base):
    """변수 × 항목 × 지역 하나의 시계열. dates/values 는 같은 길이의 JSON 배열."""
    __tablename__ = "indicator_series"
    __table_args__ = (UniqueConstraint("variable_id", "item", "region"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variable_id: Mapped[str] = mapped_column(ForeignKey("indicator_variables.id"), index=True)
    item: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(30), index=True)
    freq: Mapped[str] = mapped_column(String(4))            # 이 계열의 실제 주기 (서울 구 고용률은 반기 등)
    unit: Mapped[str] = mapped_column(String(40), default="")
    start: Mapped[str] = mapped_column(String(10))
    end: Mapped[str] = mapped_column(String(10))
    points: Mapped[int] = mapped_column(Integer)
    dates: Mapped[list] = mapped_column(JSON)
    values: Mapped[list] = mapped_column(JSON)


class ContentSnapshot(Base):
    __tablename__ = "content_snapshots"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))


class PolicySourceState(Base):
    __tablename__ = "policy_source_states"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_checked_at: Mapped[str | None] = mapped_column(String(40))
    last_success_at: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="never_collected")
    error: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(50), index=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    agency: Mapped[str] = mapped_column(String(100))
    published_at: Mapped[str | None] = mapped_column(String(40), index=True)
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    matched_keywords: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class PolicyDocumentVersion(Base):
    __tablename__ = "policy_document_versions"
    __table_args__ = (UniqueConstraint("document_id", "revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("policy_documents.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[str] = mapped_column(String(40))
