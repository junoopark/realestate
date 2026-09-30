"""DB 연결·세션 (예정 — 아직 사용하지 않는다).

DB 를 붙이는 단계에서 아래를 채운다. (database/README.md 의 진행 순서 참고)

- DATABASE_URL 환경변수를 읽는다.
    로컬 기본값: sqlite:///./local.db
    배포: Supabase Session pooler 연결 문자열 (Render 환경변수로 설정)
- SQLAlchemy engine, SessionLocal, Base 를 만든다.
- 요청마다 세션을 열고 닫는 get_db() 의존성을 제공한다 (FastAPI Depends 용).

주의: sqlalchemy 는 아직 requirements.txt 에 없다. 이 파일을 실제로 쓰기 전에 추가한다.
"""
