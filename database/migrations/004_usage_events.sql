-- 익명 관심 통계. 앱 시작 시 같은 ORM 테이블/RLS를 자동으로 준비한다.
-- 기존 activity_logs(로그인·다운로드)와 연결하지 않는다. 사용자/IP/UA/임의 URL을 받지 않는다.
CREATE TABLE IF NOT EXISTS usage_events (
    event_id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    event VARCHAR(20) NOT NULL,
    target VARCHAR(100) NOT NULL,
    page VARCHAR(20) NOT NULL,
    label TEXT NOT NULL,
    scope VARCHAR(10) NOT NULL DEFAULT '',
    agency VARCHAR(100) NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_usage_session_event_target UNIQUE(session_id, event, target)
);
CREATE INDEX IF NOT EXISTS ix_usage_events_time ON usage_events(occurred_at);
CREATE INDEX IF NOT EXISTS ix_usage_events_event_target_time ON usage_events(event, target, occurred_at);
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON usage_events FROM anon, authenticated;
-- INSERT/SELECT policy를 만들지 않는다. DB 소유자 연결의 FastAPI만 쓰고 집계 결과만 공개한다.
