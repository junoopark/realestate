"""Run from Render/backend: python -m app.collect_policies."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.services.content_store import initialize_storage
from app.services.policy_collector import collect_all, read_monitor
from app.services.policy_sources import COVERAGE_NOTE
from app.db.session import storage_info


def main():
    parser = argparse.ArgumentParser(description="공식 정책자료를 수집해 설정된 DB에 저장합니다.")
    parser.add_argument("--export", type=Path, help="선택: 실제 수집 결과를 JSON 파일로 저장 (검증한 정책 요약 파일과 분리)")
    args = parser.parse_args()
    try:
        initialize_storage()
        result = collect_all()
        if args.export:
            args.export.parent.mkdir(parents=True, exist_ok=True)
            export = {**read_monitor(300), "coverage_note": COVERAGE_NOTE, "storage": storage_info(), "snapshot": True}
            args.export.write_text(json.dumps(export, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ok" else 1
    except Exception:
        print("정책자료 저장소 초기화 또는 연결에 실패했습니다. DATABASE_URL과 DB 권한을 확인하세요.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
