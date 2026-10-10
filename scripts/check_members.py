"""Read-only configuration check. Run: python scripts/check_members.py --api URL"""
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        with urlopen(args.api.rstrip("/") + "/members/status", timeout=55) as response:
            status = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        print("상태를 확인하지 못했습니다. API 주소와 서버 실행 여부를 확인하세요.")
        return 1
    storage = status.get("storage", {})
    checks = [
        ("Google 로그인 설정값", status.get("auth_configured", False)),
        ("좋아요 DB 조회", storage.get("available", False)),
        ("영구 PostgreSQL 저장소", storage.get("persistent", False)),
        ("다운로드 파일 준비", status.get("downloads_ready", False)),
    ]
    for label, ok in checks:
        print(f"[{'OK' if ok else '확인 필요'}] {label}")
    print("설정값 확인 결과입니다. 실제 Google 로그인과 두 계정의 좋아요 집계는 브라우저에서 최종 확인하세요.")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
