"""국토부 실거래(V006 전월세 · V007 매매) 이후분 수집 CLI. 저장소 루트에서는 scripts/collect_rtms.py.

  python scripts/collect_rtms.py                    # 유형마다 1,000회까지 받고 → 시도·서울 구 합계를 화면 계열에 반영
  python scripts/collect_rtms.py --budget 3000      # 일일 한도가 넉넉하면(운영계정) 한 번에 더 받는다
  python scripts/collect_rtms.py --kinds apt_rent   # 전월세만
  python scripts/collect_rtms.py --no-apply         # 받기만 (GitHub Actions: 반영은 Render 수집 API 의 source=MOLIT 가 맡아 캐시도 비운다)
  python scripts/collect_rtms.py --apply-only       # API 를 부르지 않고 이미 받은 건수만 화면 계열에 반영
  python scripts/collect_rtms.py --status           # 받지 않고 월별 진행 상황만

키: DATA_GO_KR_API_KEY (공공데이터포털 인증키, 국토교통부 아파트 전월세·매매 실거래가 두 API 활용신청). DB: DATABASE_URL.
한도에 걸리면 받은 데까지 저장하고 멈춘다. 다음 실행이 남은 것부터 이어받는다.
"""

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine, storage_info  # noqa: E402
from app.services import rtms  # noqa: E402
from app.services.content_store import initialize_storage  # noqa: E402
from app.services.indicator_pipeline import refresh_all  # noqa: E402


def show_status(session: Session) -> None:
    for kind, months in rtms.status(session).items():
        cells = " · ".join(f"{ym[:4]}-{ym[4:]} {v['sgg']}/{v['of']}" for ym, v in sorted(months.items()))
        print(f"  {rtms.KINDS[kind]['label']}: {cells}")


def main() -> int:
    parser = argparse.ArgumentParser(description="국토부 실거래 최근 몇 달을 호출 한도 안에서 다시 받아 건수를 저장하고 화면 계열에 반영합니다.")
    parser.add_argument("--budget", type=int, default=rtms.BUDGET, help=f"유형 1개당 이번 실행 호출 상한 (기본 {rtms.BUDGET})")
    parser.add_argument("--window", type=int, default=rtms.WINDOW, help=f"최근 몇 개월을 다시 받는가 (기본 {rtms.WINDOW})")
    parser.add_argument("--kinds", default="apt_rent,apt_trade", help="apt_rent(전월세) · apt_trade(매매), 쉼표 구분")
    parser.add_argument("--no-apply", action="store_true", help="받기만 하고 화면 계열 반영은 하지 않는다")
    parser.add_argument("--apply-only", action="store_true", help="API 를 부르지 않고 이미 받은 건수만 화면 계열에 반영")
    parser.add_argument("--status", action="store_true", help="받지 않고 진행 상황만 출력")
    args = parser.parse_args()

    initialize_storage()
    print(f"DB: {storage_info()['type']}")
    with Session(get_engine()) as session:
        if not args.status:
            kinds = [k.strip() for k in args.kinds.split(",") if k.strip() in rtms.KINDS]
            summary = {}
            if not args.apply_only:
                try:
                    client = rtms.RtmsClient()
                except ValueError as exc:
                    print(exc)
                    return 1
                summary = rtms.collect(session, kinds, budget=args.budget, window=args.window, client=client,
                                       log=lambda msg: print(msg, flush=True))
            if not args.no_apply:
                result = refresh_all(session, source="MOLIT", force=True, trigger="cli")
                for r in result["results"]:
                    print(f"  {r['id']}: {r['status']} 새로={r.get('new', '')} 수정={r.get('changed', '')} 같음={r.get('unchanged', '')} "
                          f"화면계열={r.get('panel_written', '')} last={r.get('last_period', '')} {r.get('error', '')}".rstrip())
            failed = any(v["stopped"] == "errors" for v in summary.values())
        else:
            failed = False
        print("월별 진행 (받은 시군구/전체):")
        show_status(session)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
