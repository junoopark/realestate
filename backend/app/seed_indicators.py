"""지표 기본 패널 적재 CLI. 저장소 루트에서는 python scripts/seed_indicators.py, backend 루트에서는 python -m app.seed_indicators.

  python scripts/seed_indicators.py                          # frontend/data/factor_sample.json 을 DB 에 적재
  python scripts/seed_indicators.py --file <다른 전처리본.json>
  python scripts/seed_indicators.py --status                 # 적재 상태만

대상 DB 는 backend/.env 의 DATABASE_URL (없으면 backend/local.db). 테이블이 없으면 만든다.
같은 파일을 다시 적재해도 결과가 같다(계열별로 지우고 다시 넣음).
"""

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / ".env")

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine, storage_info  # noqa: E402
from app.services.content_store import initialize_storage  # noqa: E402
from app.services.indicator_panel import panel_status, seed_panel  # noqa: E402

DEFAULT_FILE = BACKEND.parent / "frontend" / "data" / "factor_sample.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="전처리본(factor_sample.json 형식)을 지표 기본 패널 테이블에 적재합니다.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help=f"적재할 JSON (기본 {DEFAULT_FILE})")
    parser.add_argument("--status", action="store_true", help="적재하지 않고 상태만 본다")
    args = parser.parse_args(argv)

    initialize_storage()
    engine = get_engine()
    print(f"저장소: {storage_info()}")
    with Session(engine) as session:
        if args.status:
            print(json.dumps(panel_status(session), ensure_ascii=False, indent=2))
            return 0
        if not args.file.exists():
            print(f"파일이 없습니다: {args.file}")
            return 1
        data = json.loads(args.file.read_text(encoding="utf-8"))
        t0 = time.perf_counter()
        result = seed_panel(session, data)
        result["duration_s"] = round(time.perf_counter() - t0, 1)
        result["file"] = str(args.file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(panel_status(session), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
