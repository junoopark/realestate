"""DATABASE_URL 연결 점검 (Supabase Session pooler 기준). 비밀번호는 출력하지 않는다.

Render Root Directory가 backend이면: python -m app.check_db [--init]
저장소 루트에서:                    python scripts/check_db.py [--init]
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from app.db.session import database_url, get_engine

PLACEHOLDERS = ("[YOUR-PASSWORD]", "<", ">", "PASSWORD@", "PROJECT:")


def check_url():
    """연결 전에 URL 형식만 보고 워크북의 흔한 실수를 찾는다. (masked_url, problems)"""
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        return database_url().render_as_string(hide_password=True), ["DATABASE_URL이 비어 있어 로컬 SQLite를 씁니다. Supabase 연결 문자열을 backend/.env 또는 Render 환경변수에 넣으세요."]
    problems = [f"자리표시자 {p!r}가 남아 있습니다." for p in PLACEHOLDERS if p in raw]
    try:
        url = database_url()
    except Exception:
        return "(해석 불가)", problems + ["URL을 해석할 수 없습니다. 비밀번호에 @ : / ? # 이 있으면 영문·숫자로 재설정하세요."]
    masked = url.render_as_string(hide_password=True)
    if url.get_backend_name() != "postgresql":
        return masked, problems
    host, port, user = url.host or "", url.port or 5432, url.username or ""
    if host.endswith(".supabase.co"):
        problems.append("Direct connection(db.<ref>.supabase.co)은 IPv6 전용입니다. Connect → Session pooler 문자열을 쓰세요.")
    if host.endswith("pooler.supabase.com"):
        if port == 6543:
            problems.append("포트 6543은 Transaction pooler입니다. 상시 실행 서버는 Session pooler(5432)를 쓰세요.")
        if user == "postgres":
            problems.append("pooler 사용자명은 postgres.<프로젝트ref> 형식이어야 합니다.")
    return masked, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="DATABASE_URL 연결 점검")
    parser.add_argument("--init", action="store_true", help="테이블 생성·검증 JSON 반영(앱 시작 시와 같은 작업)까지 실행")
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    masked, problems = check_url()
    print(f"DATABASE_URL: {masked}")
    for problem in problems:
        print(f"  ! {problem}")
    if any("자리표시자" in p or "해석" in p for p in problems):
        return 1

    engine = get_engine()
    try:
        with engine.connect() as connection:
            version = connection.execute(text("select version()" if engine.dialect.name == "postgresql" else "select sqlite_version()")).scalar()
        print(f"연결 성공: {engine.dialect.name} {str(version).split(',')[0]}")
        if args.init:
            from app.services.content_store import initialize_storage

            initialize_storage()
            print("테이블 생성·검증 JSON 반영 완료")
        print("테이블:", ", ".join(sorted(inspect(engine).get_table_names())) or "(없음)")
    except Exception as error:
        # 드라이버 메시지에는 호스트가 들어갈 수 있지만 비밀번호는 넣지 않는다.
        print(f"연결 실패: {type(error).__name__}: {str(error).splitlines()[0][:300]}")
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
