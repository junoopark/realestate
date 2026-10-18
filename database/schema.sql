-- KHMI 스키마. ORM(backend/app/db/models.py)과 같다. DB 소유자로 실행한다. FastAPI 도 시작 시 없는 테이블만 만든다.
-- 익명/공개 REST 정책은 없다. 브라우저는 FastAPI 를 통해서만 읽는다.

-- ── 정량 지표: 외부 Open API(R-ONE·ECOS·KOSIS) → DB 캐시 → GET /indicators ──
CREATE TABLE IF NOT EXISTS indicator_variables (        -- 변수(지표) 1개 = 1행. 코드의 레지스트리와 시작 시 동기화
    id VARCHAR(10) PRIMARY KEY,                          -- 데이터사전 변수 ID (V002)
    label TEXT NOT NULL,
    driver VARCHAR(20) NOT NULL,                         -- demand · supply · finance · rental · trigger · macro
    source VARCHAR(10) NOT NULL,                         -- R-ONE · ECOS · KOSIS
    source_ref TEXT NOT NULL,                            -- 'R-ONE A_2024_00045' (통계표·항목 코드)
    freq VARCHAR(2) NOT NULL,                            -- M · Q · A
    scope VARCHAR(10) NOT NULL,                          -- sido · nation
    unit VARCHAR(20) NOT NULL DEFAULT '',
    release TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    item_name TEXT,                                      -- 실제 수집한 항목명
    first_period VARCHAR(10),
    last_period VARCHAR(10),                             -- DB 에 있는 가장 최근 시점
    last_fetched_at VARCHAR(40),                         -- 마지막 성공 수집 시각(UTC ISO)
    last_status VARCHAR(20) NOT NULL DEFAULT 'never',    -- never · ok · error
    last_error TEXT,
    updated_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS indicator_observations (     -- 관측값 1개 = 1행
    variable_id VARCHAR(10) NOT NULL REFERENCES indicator_variables(id),
    region VARCHAR(30) NOT NULL,                         -- 서울 · 부산 … · 전국
    period VARCHAR(10) NOT NULL,                         -- 2026-08 · 2026-Q1 · 2026
    value DOUBLE PRECISION NOT NULL,
    fetched_at VARCHAR(40) NOT NULL,
    PRIMARY KEY (variable_id, region, period)            -- 재수집은 INSERT … ON CONFLICT DO UPDATE 로 제자리 갱신
);
CREATE INDEX IF NOT EXISTS ix_indicator_observations_variable_period ON indicator_observations(variable_id, period);
CREATE TABLE IF NOT EXISTS indicator_fetch_logs (       -- 수집 1회 = 1행 (모니터·캐시 효과 근거)
    id SERIAL PRIMARY KEY,
    variable_id VARCHAR(10) NOT NULL REFERENCES indicator_variables(id),
    started_at VARCHAR(40) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,                         -- ok · error
    trigger VARCHAR(20) NOT NULL,                        -- cli · admin · lazy · background
    rows_received INTEGER NOT NULL DEFAULT 0,
    rows_upserted INTEGER NOT NULL DEFAULT 0,
    last_period VARCHAR(10),
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_indicator_fetch_logs_variable_id ON indicator_fetch_logs(variable_id);

-- ── 지표 기본 패널: 전처리본(51개 변수·106개 계열) 적재 — python scripts/seed_indicators.py ──
CREATE TABLE IF NOT EXISTS indicator_series (           -- 계열 1개 = 1행 (변수 × 지역 단위 × 세부 항목)
    id VARCHAR(80) PRIMARY KEY,                          -- '{scope}:{원자료 열}'
    var_id VARCHAR(10) NOT NULL,                         -- 데이터사전 변수 ID (V001 …)
    scope VARCHAR(10) NOT NULL,                          -- sido · gu · seoul · nation
    column_name TEXT NOT NULL,
    label TEXT NOT NULL,
    unit VARCHAR(30) NOT NULL DEFAULT '',
    freq VARCHAR(2) NOT NULL,                            -- M · Q · H · A
    periods JSON NOT NULL,                               -- 시점 목록 (값 배열 순서)
    source TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    release TEXT NOT NULL DEFAULT '',
    filled INTEGER,
    provisional_from VARCHAR(10),
    sort_order INTEGER NOT NULL DEFAULT 0,
    dataset TEXT NOT NULL DEFAULT '',
    loaded_at VARCHAR(40) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_indicator_series_var_id ON indicator_series(var_id);
CREATE TABLE IF NOT EXISTS indicator_series_values (    -- 값 1개 = 1행. 빈칸은 저장하지 않는다
    series_id VARCHAR(80) NOT NULL REFERENCES indicator_series(id) ON DELETE CASCADE,
    region VARCHAR(30) NOT NULL,
    period VARCHAR(10) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series_id, region, period)
);
CREATE TABLE IF NOT EXISTS rtms_progress (               -- 국토부 실거래 시군구·월별 건수 겸 수집 진행 기록 (원자료 행은 저장하지 않음)
    kind VARCHAR(12) NOT NULL,                           -- apt_rent(V006 전월세) · apt_trade(V007 매매)
    lawd_cd VARCHAR(5) NOT NULL,                         -- 시군구 코드 (backend/app/services/sgg_codes.py)
    deal_ym VARCHAR(6) NOT NULL,                         -- 계약년월 YYYYMM
    count_all INTEGER NOT NULL DEFAULT 0,                -- 전월세 전체 · 매매(해제 제외)
    count_monthly INTEGER NOT NULL DEFAULT 0,            -- 월세(보증부 포함)
    count_jeonse INTEGER NOT NULL DEFAULT 0,             -- 전세
    count_canceled INTEGER NOT NULL DEFAULT 0,           -- 매매 해제(참고)
    calls INTEGER NOT NULL DEFAULT 1,
    first_fetched_at VARCHAR(40) NOT NULL,
    fetched_at VARCHAR(40) NOT NULL,
    PRIMARY KEY (kind, lawd_cd, deal_ym)
);

-- ── 정성 자료: 검토한 JSON 스냅샷과 정책 수집 ──
CREATE TABLE IF NOT EXISTS content_snapshots (
    key VARCHAR(40) PRIMARY KEY,
    content JSON NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_source_states (
    id VARCHAR(50) PRIMARY KEY,
    last_checked_at VARCHAR(40),
    last_success_at VARCHAR(40),
    status VARCHAR(30) NOT NULL DEFAULT 'never_collected',
    error TEXT,
    item_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS policy_documents (
    id VARCHAR(64) PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    agency VARCHAR(100) NOT NULL,
    published_at VARCHAR(40),
    summary TEXT NOT NULL,
    category VARCHAR(40) NOT NULL,
    matched_keywords JSON NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    first_seen_at VARCHAR(40) NOT NULL,
    last_seen_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_policy_documents_source_id ON policy_documents(source_id);
CREATE INDEX IF NOT EXISTS ix_policy_documents_published_at ON policy_documents(published_at);
CREATE TABLE IF NOT EXISTS policy_document_versions (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES policy_documents(id),
    revision INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content JSON NOT NULL,
    observed_at VARCHAR(40) NOT NULL,
    UNIQUE(document_id, revision)
);
CREATE INDEX IF NOT EXISTS ix_policy_document_versions_document_id ON policy_document_versions(document_id);
ALTER TABLE content_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_source_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_variables ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_fetch_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_series ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_series_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE rtms_progress ENABLE ROW LEVEL SECURITY;
