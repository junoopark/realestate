-- 사용 기록(로그인·로그아웃·데이터 내려받기). 설계: docs/설계서_로그인_데이터다운로드.md 6장
-- 002 다음에 실행. 다시 실행해도 안전하다.
-- 쓰기: 웹 화면이 supabase-js(공개 키 + 로그인 세션)로 직접 insert 한다.
--       RLS 로 '로그인한 사용자가 자기 user_id 행만' 추가할 수 있다. 조회·수정·삭제 정책은 없다.
-- 읽기: Supabase 대시보드나 DB 소유자 연결(SQL Editor, FastAPI)에서만.
-- 개인정보: user_id(UUID)만 남긴다. 이메일·이름은 auth.users 에만 있다.

CREATE TABLE IF NOT EXISTS activity_logs (
    id          BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    event       VARCHAR(20) NOT NULL CHECK (event IN ('login', 'logout', 'download')),
    page        VARCHAR(80),                          -- 'index.html#rental' 처럼 경로+탭
    target      VARCHAR(80),                          -- 내려받기: 'V001:sido' 처럼 변수 ID·범위
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {format, rows, regions[], range, view}
    session_id  VARCHAR(40),                          -- 브라우저 탭 단위 임의 값 (같은 방문 묶기)
    user_agent  VARCHAR(200),
    CONSTRAINT activity_logs_detail_size CHECK (pg_column_size(detail) < 4000)
);
CREATE INDEX IF NOT EXISTS ix_activity_logs_time ON activity_logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_activity_logs_user ON activity_logs(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_activity_logs_event ON activity_logs(event, occurred_at DESC);

ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS activity_logs_insert_own ON activity_logs;
CREATE POLICY activity_logs_insert_own ON activity_logs
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

-- 공개 키(anon)로는 아무것도 못 하고, 로그인 사용자는 insert 만 한다
REVOKE ALL ON activity_logs FROM anon;
REVOKE ALL ON activity_logs FROM authenticated;
GRANT INSERT ON activity_logs TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE activity_logs_id_seq TO authenticated;

-- 관리자 집계용 뷰 (security_invoker: 조회하는 사람의 권한을 따르므로 anon·authenticated 는 볼 수 없다)
CREATE OR REPLACE VIEW v_activity_daily
WITH (security_invoker = true) AS
SELECT date_trunc('day', occurred_at AT TIME ZONE 'Asia/Seoul')::date AS day_kst,
       event,
       count(*) AS events,
       count(DISTINCT user_id) AS users
FROM activity_logs
GROUP BY 1, 2;

CREATE OR REPLACE VIEW v_download_by_target
WITH (security_invoker = true) AS
SELECT target,
       detail->>'format' AS format,
       count(*) AS downloads,
       count(DISTINCT user_id) AS users,
       max(occurred_at) AS last_at
FROM activity_logs
WHERE event = 'download'
GROUP BY 1, 2;

REVOKE ALL ON v_activity_daily, v_download_by_target FROM anon, authenticated;
