# -*- coding: utf-8 -*-
"""frontend/data/indicators 의 JSON 을 DATABASE_URL 의 DB(Supabase PostgreSQL 또는 로컬 SQLite)에 적재한다.

  # Supabase 에 넣기 (저장소 루트에서, URL 은 환경변수로만 준다 — 코드·Git 에 넣지 않는다)
  $env:DATABASE_URL = "postgresql+psycopg://postgres.PROJECT:PASSWORD@HOST.pooler.supabase.com:5432/postgres"
  python scripts/load_indicators.py

  # 적재 결과 확인만
  python scripts/load_indicators.py --check

같은 내용(해시 동일)은 건너뛰고, 바뀐 변수는 계열을 지우고 다시 넣는다. 변수 52개 · 계열 약 1,500행.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import IndicatorSeries, IndicatorVariable  # noqa: E402
from app.db.session import Base, database_url, get_engine  # noqa: E402
from app.services.indicator_store import data_dir, load_from_files  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="적재하지 않고 DB 의 변수·계열 수만 출력")
    args = ap.parse_args()

    print(f"DB: {database_url().get_backend_name()}  (자료 폴더: {data_dir()})")
    engine = get_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if not args.check:
            result = load_from_files(session, verbose=True)
            print(f"\n추가 {result['inserted']} · 갱신 {result['updated']} · 변경 없음 {result['skipped']}  (자료 생성일 {result['generated_at']})")
        variables = session.scalar(select(func.count()).select_from(IndicatorVariable))
        series = session.scalar(select(func.count()).select_from(IndicatorSeries))
        print(f"DB 상태: 변수 {variables}개 · 계열 {series}행")


if __name__ == "__main__":
    main()
