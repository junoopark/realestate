"""실행 진입점.

  python -m src.run --config configs/project.yaml --stage all [--env-file ../backend/.env]
  python -m src.run --config configs/project.yaml --offline        # 수집 없이 확보한 원자료로 전부 재생성
  python -m src.run --stage fetch --only kr_rone,uk_hpi            # 일부 출처만 다시 받기

단계: fetch → clean → validate → metrics → charts → export → report  (all = 전부)
--offline 이면 fetch 를 건너뛰고 data/raw 에 있는 파일만 쓴다.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback

from .config import load_context, load_env_file
from .netio import DataUnavailable, Fetcher, NetworkError, RawMissing, utc_now

STAGES = ["fetch", "clean", "validate", "metrics", "charts", "export", "report"]


def log(msg: str):
    print(msg, flush=True)


def stage_fetch(ctx):
    from .fetch import SOURCES, fetch_source

    f = Fetcher(ctx)
    status_path = ctx.raw / "_fetch_status.csv"
    prev = {}
    if status_path.exists():
        with open(status_path, encoding="utf-8-sig", newline="") as fh:
            prev = {r["source_id"]: r for r in csv.DictReader(fh)}
    targets = [s for s in SOURCES if not ctx.only or s in ctx.only]
    for sid in targets:
        t0 = time.time()
        log(f"[fetch] {sid}")
        try:
            fetch_source(sid, ctx, f, log)
            status, msg = "ok", ""
        except NetworkError as exc:
            status, msg = "network_error", str(exc)
        except DataUnavailable as exc:
            status, msg = "unavailable", str(exc)
        except Exception as exc:  # 파서·형식 변경 등 — 원인을 남기고 다음 출처로
            status, msg = "error", f"{type(exc).__name__}: {exc}"
            traceback.print_exc(limit=3)
        finally:
            f.manifest.save()
        prev[sid] = {"source_id": sid, "status": status, "message": msg[:500], "checked_at": utc_now(),
                     "seconds": f"{time.time() - t0:.1f}"}
        log(f"  → {status} {msg[:200]}")
    repair_manifest(ctx, f.manifest)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with open(status_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_id", "status", "message", "checked_at", "seconds"])
        w.writeheader()
        for k in sorted(prev):
            w.writerow(prev[k])


def repair_manifest(ctx, manifest):
    """data/raw 에 있는데 manifest 기록이 없는 파일(예: 이후 수집이 실패해 이전 수집분이 남은 경우)을 기록한다.

    URL 은 series.yaml 의 source_url(출처 페이지)로, 수집 시각은 파일 수정시각으로 적고 그 사실을 note 에 밝힌다.
    """
    from datetime import datetime, timezone

    from .netio import sha256

    for key in [k for k in manifest.rows if not (ctx.raw / k[0] / k[1]).exists()]:
        del manifest.rows[key]  # 지운 파일의 기록은 남기지 않는다
    pages = {}
    for m in ctx.series.values():
        pages.setdefault(m["source_id"], m.get("source_url", ""))
    for d in sorted(p for p in ctx.raw.iterdir() if p.is_dir()):
        for p in sorted(d.iterdir()):
            if p.is_file() and not p.name.endswith(".part") and not manifest.get(d.name, p.name):
                ts = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
                manifest.record(source_id=d.name, file=p.name, url=pages.get(d.name, ""), params="", retrieved_at=ts,
                                bytes=p.stat().st_size, sha256=sha256(p), http_status="",
                                note="manifest 복구: 기록이 없던 기존 파일(수집 시각 = 파일 수정시각, URL = 출처 페이지)")
    manifest.save(merge=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description="글로벌 도시 주택시장 비교 파이프라인")
    ap.add_argument("--config", default="configs/project.yaml")
    ap.add_argument("--stage", default="all", help="all 또는 " + ",".join(STAGES))
    ap.add_argument("--offline", action="store_true", help="수집하지 않고 확보한 원자료로만 재생성")
    ap.add_argument("--only", default="", help="fetch 대상 source_id (쉼표 구분)")
    ap.add_argument("--env-file", default="", help="API 키를 담은 .env 파일 경로 (값은 출력하지 않음)")
    ap.add_argument("--refresh", action="store_true", help="이미 받은 실거래 연도 파일도 다시 받기")
    args = ap.parse_args(argv)

    if args.env_file:
        names = load_env_file(args.env_file)
        log(f"env: {len(names)}개 키 이름을 읽음")
    ctx = load_context(args.config, offline=args.offline, only=[s for s in args.only.split(",") if s])
    ctx.project["_refresh"] = args.refresh
    stages = STAGES if args.stage == "all" else [s.strip() for s in args.stage.split(",")]
    if args.offline and "fetch" in stages:
        stages = [s for s in stages if s != "fetch"]
        log("offline: fetch 단계를 건너뜀")

    from . import charts, export, metrics, report, validate
    from .clean import clean_all

    for st in stages:
        log(f"=== {st} ===")
        if st == "fetch":
            stage_fetch(ctx)
        elif st == "clean":
            clean_all(ctx, log)
        elif st == "validate":
            validate.run(ctx, log)
        elif st == "metrics":
            metrics.run(ctx, log)
        elif st == "charts":
            charts.run(ctx, log)
        elif st == "export":
            export.run(ctx, log)
        elif st == "report":
            report.run(ctx, log)
        else:
            raise SystemExit(f"알 수 없는 단계: {st}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
