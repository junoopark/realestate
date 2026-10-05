"""Qualitative content only; the existing indicator service is independent."""

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


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
