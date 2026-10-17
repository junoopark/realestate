-- 한국부동산원 R-ONE 아파트 월세지수 저장소 (Supabase / PostgreSQL)
-- 대상 통계표
--   A_2024_00055  (월) 월세가격지수_아파트        2015.06~  기준시점 2026.06=100
--   A_2024_00054  (월) 월세통합가격지수_아파트    2015.06~  기준시점 2026.06=100  (화면 V001)
--   A_2024_00164  주택유형별 월세가격지수(구)_아파트  2010.06~2015.xx  기준월 2012.06=100
-- 원칙
--   1. R-ONE 응답은 rone_observations 에 원값 그대로 저장한다. 같은 키로 다시 받으면 덮어쓴다(upsert).
--      값이 바뀌면 트리거가 이전 값을 rone_observation_revisions 에 남긴다.
--   2. CLS_ID 는 통계표마다 체계가 다르다(구지수 510004 강북지역 = 현행 510009 강북지역).
--      그래서 지역은 (statbl_id, cls_id) 로 받고, regions 의 공통 키로 연결한다.
--   3. 구지수 연결·권역 역산 같은 가공값은 derived_observations 에 따로 둔다.
-- Supabase SQL Editor 에서 DB 소유자 권한으로 실행. 다시 실행해도 안전하다.
-- 공개 REST 정책은 만들지 않는다(RLS 켜고 정책 없음). 읽기는 FastAPI 가 담당한다.

-- 통계표 메타
CREATE TABLE IF NOT EXISTS rone_stat_tables (
    statbl_id      VARCHAR(30) PRIMARY KEY,
    name           TEXT NOT NULL,
    stat_id        VARCHAR(20),
    cycle          VARCHAR(10) NOT NULL DEFAULT 'MM',
    base_period    TEXT,                       -- 예: '2026.06.=100.0'
    housing_type   VARCHAR(20) NOT NULL,       -- 아파트, 주택종합 ...
    measure        VARCHAR(40) NOT NULL,       -- 월세가격지수, 월세통합가격지수
    is_legacy      BOOLEAN NOT NULL DEFAULT FALSE,
    collect        BOOLEAN NOT NULL DEFAULT TRUE,  -- 정기 수집 대상 여부
    first_period   DATE,
    last_period    DATE,
    note           TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 화면·분석에서 쓰는 공통 지역
-- region_key 예: '전국', '서울', '서울>강남구', '경기>수원시'
CREATE TABLE IF NOT EXISTS regions (
    region_key   VARCHAR(80) PRIMARY KEY,
    name         VARCHAR(40) NOT NULL,
    level        VARCHAR(10) NOT NULL CHECK (level IN ('nation', 'zone', 'sido', 'area', 'sigungu', 'gu')),
    parent_key   VARCHAR(80) REFERENCES regions(region_key),
    sort_order   INTEGER,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS ix_regions_parent_key ON regions(parent_key);

-- R-ONE 지역 분류(CLS) → 공통 지역
CREATE TABLE IF NOT EXISTS rone_regions (
    statbl_id    VARCHAR(30) NOT NULL REFERENCES rone_stat_tables(statbl_id),
    cls_id       BIGINT NOT NULL,
    cls_nm       VARCHAR(40) NOT NULL,
    cls_fullnm   TEXT NOT NULL,                -- 예: '서울>강북지역>도심권>종로구'
    rone_level   SMALLINT,                     -- CLS_ID 앞 3자리 기준 500=0, 510=1, 520=2, 530=3
    region_key   VARCHAR(80) REFERENCES regions(region_key),  -- 매핑 전에는 NULL
    first_seen   DATE,
    last_seen    DATE,
    PRIMARY KEY (statbl_id, cls_id)
);
CREATE INDEX IF NOT EXISTS ix_rone_regions_region_key ON rone_regions(region_key);

-- 원자료 관측값
CREATE TABLE IF NOT EXISTS rone_observations (
    statbl_id     VARCHAR(30) NOT NULL,
    cls_id        BIGINT NOT NULL,
    itm_id        BIGINT NOT NULL,
    period        DATE NOT NULL,               -- 기준월 1일 (WRTTIME_IDTFR_ID 202609 → 2026-09-01)
    value         DOUBLE PRECISION,
    unit          VARCHAR(20),                 -- UI_NM
    itm_nm        VARCHAR(40),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (statbl_id, cls_id, itm_id, period),
    FOREIGN KEY (statbl_id, cls_id) REFERENCES rone_regions(statbl_id, cls_id)
);
CREATE INDEX IF NOT EXISTS ix_rone_observations_period ON rone_observations(statbl_id, period);

-- 공표 후 수정된 값의 이력
CREATE TABLE IF NOT EXISTS rone_observation_revisions (
    id           BIGSERIAL PRIMARY KEY,
    statbl_id    VARCHAR(30) NOT NULL,
    cls_id       BIGINT NOT NULL,
    itm_id       BIGINT NOT NULL,
    period       DATE NOT NULL,
    old_value    DOUBLE PRECISION,
    new_value    DOUBLE PRECISION,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rone_observation_revisions_key
    ON rone_observation_revisions(statbl_id, cls_id, itm_id, period);

CREATE OR REPLACE FUNCTION rone_log_revision() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF NEW.value IS DISTINCT FROM OLD.value THEN
        INSERT INTO rone_observation_revisions (statbl_id, cls_id, itm_id, period, old_value, new_value)
        VALUES (OLD.statbl_id, OLD.cls_id, OLD.itm_id, OLD.period, OLD.value, NEW.value);
        NEW.updated_at := now();
    ELSE
        NEW.updated_at := OLD.updated_at;  -- 값이 같으면 수정 시각을 바꾸지 않는다
    END IF;
    NEW.first_seen_at := OLD.first_seen_at;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rone_observations_revision ON rone_observations;
CREATE TRIGGER trg_rone_observations_revision
    BEFORE UPDATE ON rone_observations
    FOR EACH ROW EXECUTE FUNCTION rone_log_revision();

-- 수집 실행 기록
CREATE TABLE IF NOT EXISTS rone_collect_runs (
    id            BIGSERIAL PRIMARY KEY,
    statbl_id     VARCHAR(30) NOT NULL REFERENCES rone_stat_tables(statbl_id),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    period_from   DATE,
    period_to     DATE,
    row_count     INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_rone_collect_runs_statbl ON rone_collect_runs(statbl_id, started_at DESC);

-- 가공 계열 (구지수 연결, 권역 역산 등)
CREATE TABLE IF NOT EXISTS derived_series (
    series_key    VARCHAR(60) PRIMARY KEY,     -- 예: 'apt_rent_combined_linked'
    label         TEXT NOT NULL,
    var_id        VARCHAR(10),                 -- 화면 변수 ID (V001 등)
    method        TEXT NOT NULL,               -- 예: '비율 연결: 구계열 x [현행(2015.06) ÷ 구계열(2015.06)]'
    source_tables TEXT[] NOT NULL,
    base_period   TEXT,
    for_training_only BOOLEAN NOT NULL DEFAULT FALSE,  -- 권역 역산처럼 학습에만 쓰는 값
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS derived_observations (
    series_key   VARCHAR(60) NOT NULL REFERENCES derived_series(series_key) ON DELETE CASCADE,
    region_key   VARCHAR(80) NOT NULL REFERENCES regions(region_key),
    period       DATE NOT NULL,
    value        DOUBLE PRECISION,
    is_filled    BOOLEAN NOT NULL DEFAULT FALSE,  -- 원자료가 아닌 연결·역산으로 채운 값
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series_key, region_key, period)
);

-- 화면용 조회: 공통 지역 기준 원자료
CREATE OR REPLACE VIEW v_rone_observations
WITH (security_invoker = true) AS
SELECT o.statbl_id, t.name AS table_name, t.measure, t.is_legacy,
       r.region_key, rr.cls_nm, rr.cls_fullnm,
       o.period, o.value, o.unit, o.updated_at
FROM rone_observations o
JOIN rone_stat_tables t ON t.statbl_id = o.statbl_id
JOIN rone_regions rr ON rr.statbl_id = o.statbl_id AND rr.cls_id = o.cls_id
LEFT JOIN regions r ON r.region_key = rr.region_key;

-- 통계표 메타 초기값 (실행 시점 R-ONE SttsApiTbl 응답 기준)
INSERT INTO rone_stat_tables (statbl_id, name, stat_id, base_period, housing_type, measure, is_legacy, collect, note) VALUES
    ('A_2024_00055', '(월) 월세가격지수_아파트', 'S234820263', '2026.06.=100.0', '아파트', '월세가격지수', FALSE, TRUE, NULL),
    ('A_2024_00054', '(월) 월세통합가격지수_아파트', 'S234820263', '2026.06.=100.0', '아파트', '월세통합가격지수', FALSE, TRUE, '화면 V001 원계열'),
    ('A_2024_00164', '주택유형별 월세가격지수(구)_아파트', 'S249620303', '2012.06.=100', '아파트', '월세가격지수', TRUE, FALSE,
     '2015.06 이전 구계열. 현행 계열과 연결할 때만 사용. 갱신되지 않으므로 한 번만 적재')
ON CONFLICT (statbl_id) DO UPDATE SET
    name = EXCLUDED.name, stat_id = EXCLUDED.stat_id, base_period = EXCLUDED.base_period,
    housing_type = EXCLUDED.housing_type, measure = EXCLUDED.measure, is_legacy = EXCLUDED.is_legacy,
    collect = EXCLUDED.collect, note = EXCLUDED.note, updated_at = now();

INSERT INTO derived_series (series_key, label, var_id, method, source_tables, base_period, for_training_only) VALUES
    ('apt_rent_combined_linked', '월세통합가격지수(구지수연결)', 'V001',
     '비율 연결: 구계열(t) x [현행(2015.06) ÷ 구계열(2015.06)], 2015.06 이후는 현행 원값',
     ARRAY['A_2024_00054', 'A_2024_00164'], '2026.06.=100.0', FALSE)
ON CONFLICT (series_key) DO NOTHING;

ALTER TABLE rone_stat_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE regions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rone_regions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rone_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rone_observation_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rone_collect_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE derived_series ENABLE ROW LEVEL SECURITY;
ALTER TABLE derived_observations ENABLE ROW LEVEL SECURITY;
