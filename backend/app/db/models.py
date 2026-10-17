"""테이블 정의 — 정량 지표(indicator_*)와 정성 자료(content_*·policy_*). 대응 SQL 은 database/schema.sql."""

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


# ── 정량 지표: 외부 Open API(R-ONE·ECOS·KOSIS) → DB 캐시 → /indicators ──

class IndicatorVariable(Base):
    """레지스트리(services/indicator_registry.py)의 변수 1개 = 1행. 앱 시작 시 레지스트리와 동기화."""
    __tablename__ = "indicator_variables"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)          # V002
    label: Mapped[str] = mapped_column(Text)
    driver: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))                        # R-ONE · ECOS · KOSIS
    source_ref: Mapped[str] = mapped_column(Text)                          # 'R-ONE A_2024_00045'
    freq: Mapped[str] = mapped_column(String(2))                           # M · Q · A
    scope: Mapped[str] = mapped_column(String(10))                         # sido · nation
    unit: Mapped[str] = mapped_column(String(20), default="")
    release: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    item_name: Mapped[str | None] = mapped_column(Text)                    # 실제로 받은 항목명 (R-ONE ITM_NM 등)
    first_period: Mapped[str | None] = mapped_column(String(10))
    last_period: Mapped[str | None] = mapped_column(String(10))            # DB 에 있는 가장 최근 시점
    last_fetched_at: Mapped[str | None] = mapped_column(String(40))        # 마지막 성공 수집 시각(UTC)
    last_status: Mapped[str] = mapped_column(String(20), default="never")  # never · ok · error
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(40))


class IndicatorObservation(Base):
    """관측값 1개 = 1행. (변수, 지역, 시점) 이 기본키라 재수집해도 중복이 쌓이지 않는다 (UPSERT)."""
    __tablename__ = "indicator_observations"
    variable_id: Mapped[str] = mapped_column(ForeignKey("indicator_variables.id"), primary_key=True)
    region: Mapped[str] = mapped_column(String(30), primary_key=True)      # 서울 · 부산 … · 전국
    period: Mapped[str] = mapped_column(String(10), primary_key=True)      # 2026-08 · 2026-Q1 · 2026
    value: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[str] = mapped_column(String(40))
    __table_args__ = (Index("ix_indicator_observations_variable_period", "variable_id", "period"),)


class IndicatorFetchLog(Base):
    """수집 1회 = 1행. /indicators/status 와 발표용 '캐시 효과' 근거(소요 시간·행 수)."""
    __tablename__ = "indicator_fetch_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variable_id: Mapped[str] = mapped_column(ForeignKey("indicator_variables.id"), index=True)
    started_at: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))                        # ok · error · skipped
    trigger: Mapped[str] = mapped_column(String(20))                       # cli · admin · lazy · background
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_upserted: Mapped[int] = mapped_column(Integer, default=0)
    last_period: Mapped[str | None] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)


# ── 지표 기본 패널: 전처리본(DFMBA, 51개 변수·106개 계열)을 DB 에 적재 → 화면의 단일 데이터 출처 ──
# Open API 로 받는 변수(indicator_observations)는 같은 (변수, 지역 단위) 계열을 /indicators/bundle 에서 덮어쓴다.

class IndicatorSeries(Base):
    """계열 1개 = 1행. 한 변수가 지역 단위(sido·gu·seoul·nation)와 세부 항목별로 여러 계열을 가질 수 있다."""
    __tablename__ = "indicator_series"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)          # '{scope}:{column}' 예: 'sido:Y_V001_월세통합가격지수(구지수연결)'
    var_id: Mapped[str] = mapped_column(String(10), index=True)            # V001 (데이터사전 drivers.json 의 변수 ID)
    scope: Mapped[str] = mapped_column(String(10))                         # sido · gu · seoul · nation
    column_name: Mapped[str] = mapped_column(Text)                         # 전처리본 원자료 열 이름
    label: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(30), default="")
    freq: Mapped[str] = mapped_column(String(2))                           # M · Q · H · A
    periods: Mapped[list] = mapped_column(JSON)                            # 시점 목록 (값 배열의 순서)
    source: Mapped[str] = mapped_column(Text, default="")                  # 'R-ONE A_2024_00054'
    method: Mapped[str] = mapped_column(Text, default="")                  # 보완·연결 방법
    release: Mapped[str] = mapped_column(Text, default="")                 # 공표 시기
    filled: Mapped[int | None] = mapped_column(Integer)                    # 보완한 칸 수
    provisional_from: Mapped[str | None] = mapped_column(String(10))       # 이 시점부터 잠정값
    sort_order: Mapped[int] = mapped_column(Integer, default=0)            # 원본 파일의 순서
    dataset: Mapped[str] = mapped_column(Text, default="")                 # 적재한 원본 (전처리본 생성 정보)
    loaded_at: Mapped[str] = mapped_column(String(40))


class IndicatorSeriesValue(Base):
    """값 1개 = 1행. (계열, 지역, 시점) 이 기본키. 빈칸(null)은 저장하지 않는다."""
    __tablename__ = "indicator_series_values"
    series_id: Mapped[str] = mapped_column(ForeignKey("indicator_series.id", ondelete="CASCADE"), primary_key=True)
    region: Mapped[str] = mapped_column(String(30), primary_key=True)      # 서울 … · 강남구 · 전국
    period: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


# ── 정성 자료: 검토한 JSON 스냅샷과 정책 수집 ──


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
