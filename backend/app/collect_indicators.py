"""정량 지표 수집 CLI. Render(backend 루트)에서는 python -m app.collect_indicators, 저장소 루트에서는 scripts/collect_indicators.py.

  python -m app.collect_indicators                 # enabled 전체, 오래된 것만
  python -m app.collect_indicators --vars V002,V043 --force
  python -m app.collect_indicators --probe V002    # 실제 항목(ITM_NM)·지역(CLS_NM) 이름을 보고 registry 를 맞출 때
  python -m app.collect_indicators --status        # DB 상태만
  python -m app.collect_indicators --export ../frontend/data/factor_live.json   # 서버 없이 볼 정적 스냅샷
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine, storage_info  # noqa: E402
from app.services.content_store import initialize_storage  # noqa: E402
from app.services.indicator_pipeline import load_metric, make_client, refresh_all, utc_now, variable_status  # noqa: E402
from app.services.indicator_registry import enabled_specs, get_spec  # noqa: E402
from app.services.regions import SIDO, normalize_sido  # noqa: E402


def probe(var_id: str) -> int:
    spec = get_spec(var_id)
    if spec is None:
        print(f"등록되지 않은 변수: {var_id}")
        return 1
    client = make_client(spec.source)
    print(f"{spec.id} {spec.label} — {spec.source_ref}")
    if spec.source == "R-ONE":
        rows = client.latest_periods(spec.params["statbl_id"])
        print(f"최근 2개월 행 수: {len(rows)}")
        print("항목(ITM_ID · ITM_NM):", Counter((r.get("ITM_ID"), r.get("ITM_NM")) for r in rows).most_common(10))
        names = Counter(r.get("CLS_NM") for r in rows)
        print("지역(CLS_NM) 상위:", names.most_common(25))
        matched = sorted({normalize_sido(n) for n in names if normalize_sido(n) in SIDO})
        print(f"17개 시도로 인식된 지역 {len(matched)}개: {matched}")
        if rows:
            print("샘플 행:", json.dumps(rows[0], ensure_ascii=False))
    elif spec.source == "ECOS":
        rows = client.fetch_rows(spec.params["stat_code"], spec.params["item_code"], "2026-01", "2026-12", freq=spec.freq)
        print(f"올해 행 수: {len(rows)}")
        if rows:
            print("샘플 행:", json.dumps(rows[-1], ensure_ascii=False))
    else:
        p = spec.params
        rows = client.fetch_rows(p["org_id"], p["tbl_id"], p["itm_id"], "2026-01", "2026-12", obj_l1=p.get("obj_l1", "ALL"))
        print(f"올해 행 수: {len(rows)}")
        print("지역(C1_NM):", Counter(r.get("C1_NM") for r in rows).most_common(25))
        if rows:
            print("샘플 행:", json.dumps(rows[-1], ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description="외부 Open API(R-ONE·ECOS·KOSIS)에서 지표를 받아 설정된 DB에 저장합니다.")
    parser.add_argument("--vars", help="쉼표 구분 변수 ID (기본: enabled 전체)")
    parser.add_argument("--force", action="store_true", help="신선해도 다시 받기 (전체 기간 재수집)")
    parser.add_argument("--probe", metavar="VAR", help="수집하지 않고 실제 항목·지역 이름만 출력")
    parser.add_argument("--status", action="store_true", help="수집하지 않고 DB 상태만 출력")
    parser.add_argument("--export", type=Path, help="선택: DB 내용을 factor_sample.json 과 같은 모양의 JSON 으로 저장")
    args = parser.parse_args()

    if args.probe:
        return probe(args.probe)

    initialize_storage()
    with Session(get_engine()) as session:
        if not args.status:
            ids = [v.strip() for v in args.vars.split(",")] if args.vars else None
            result = refresh_all(session, ids, force=args.force, trigger="cli")
            for r in result["results"]:
                print(f"  {r['id']}: {r['status']}  rows={r.get('rows', '')} last={r.get('last_period', '')} {r.get('error', r.get('reason', ''))}")
            print(f"수집 결과: {result['status']}")
        status = variable_status(session)
        print(f"DB({storage_info()['type']}): 변수 {len(status)}개 · 관측 {sum(s['rows'] for s in status):,}행")
        for s in status:
            print(f"  {s['id']} {s['label']:<22} {s['source']:<6} {s['last_status']:<6} {s['first_period'] or '-'}~{s['last_period'] or '-'} rows={s['rows']}")
        if args.export:
            metrics = [m for m in (load_metric(session, spec) for spec in enabled_specs()) if m]
            payload = {"_source": "Open API 수집본 (app.collect_indicators --export)", "generated": utc_now(),
                       "aliases": {}, "regions": {"sido": SIDO, "gu": []}, "metrics": metrics}
            args.export.parent.mkdir(parents=True, exist_ok=True)
            args.export.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"저장: {args.export} ({len(metrics)}개 계열)")
        failed = [s for s in status if s["enabled"] and s["last_status"] == "error"]
        return 1 if (not args.status and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
