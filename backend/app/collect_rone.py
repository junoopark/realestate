"""Run from Render/backend: python -m app.collect_rone."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.db.session import get_engine
from app.services import region_mapper
from app.services.rone_client import RoneError
from app.services.rone_collector import collect


def main(argv=None):
    parser = argparse.ArgumentParser(description="R-ONE 월세지수를 받아 Supabase(PostgreSQL)에 적재합니다.")
    parser.add_argument("--table", action="append", help="통계표 ID (여러 번 지정 가능). 생략하면 rone_stat_tables.collect=true 인 표")
    parser.add_argument("--months", type=int, default=12, help="정기 수집 시 다시 받을 최근 개월 수 (기본 12)")
    parser.add_argument("--full", action="store_true", help="기준월 없이 전체 기간을 받는다 (첫 적재용)")
    parser.add_argument("--include-legacy", action="store_true", help="구지수 표(is_legacy)도 함께 적재한다")
    parser.add_argument("--map-only", action="store_true", help="수집 없이 공통 지역 키(regions) 매핑만 다시 한다")
    args = parser.parse_args(argv)
    try:
        if args.map_only:
            result = {"status": "ok", "tables": []}
        else:
            result = collect(only=args.table, months=args.months, full=args.full, include_legacy=args.include_legacy)
        # 새 지역이 생겼을 수 있으니 수집 뒤 매번 공통 지역 키를 다시 맞춘다
        result["regions"] = region_mapper.apply(get_engine())
    except RoneError as exc:
        print(str(exc))
        return 1
    except Exception:
        print("R-ONE 적재 저장소 연결에 실패했습니다. DATABASE_URL과 database/migrations 의 SQL(001, 002) 실행 여부를 확인하세요.")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
