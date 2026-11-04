"""설명변수 시계열 보드(docs/설명변수_시계열.html)를 만들고, 설명변수 정의가 서로 맞는지 점검한다.

입력: frontend/data/factor_sample.json  (전처리 계열 — build_factor_sample.py 가 만든다)
      frontend/data/drivers.json        (데이터사전 — 변수 이름·동인·예상 부호)
      backend/app/services/indicator_registry.py (Open API 수집 레지스트리)
틀:   scripts/xvar_board_template.html
출력: docs/설명변수_시계열.html (데이터를 파일 안에 넣어 서버 없이 열린다)

점검 (경고만 출력하고 보드는 그대로 만든다. --strict 면 경고가 있을 때 실패)
  - factor_sample 의 변수가 데이터사전에 없음 / 데이터사전 변수가 factor_sample 에 없음
  - 레지스트리 변수가 데이터사전에 없음, 동인(driver)이 데이터사전과 다름
  - 데이터사전에 없는 동인 id

사용법:
  python scripts/build_xvar_board.py            # 보드 만들기 + 점검
  python scripts/build_xvar_board.py --strict   # 점검 경고가 있으면 종료 코드 1
"""

import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SAMPLE = os.path.join(ROOT, "frontend", "data", "factor_sample.json")
DRIVERS = os.path.join(ROOT, "frontend", "data", "drivers.json")
TEMPLATE = os.path.join(ROOT, "scripts", "xvar_board_template.html")
OUT = os.path.join(ROOT, "docs", "설명변수_시계열.html")
Y_VAR = "V001"  # 종속변수 — 이 보드에서는 비교 기준으로만 쓴다


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rnd(v):
    return None if v is None else float(f"{v:.6g}")


def check(fs, dv):
    warns = []
    var = {v["id"]: v for v in dv["variables"]}
    driver_ids = {d["id"] for d in dv["drivers"]}
    alias = fs.get("aliases", {})
    in_sample = {m["var"] for m in fs["metrics"]}
    for vid in sorted(in_sample):
        if vid not in var and alias.get(vid) not in var:
            warns.append(f"factor_sample 의 {vid} 가 데이터사전(drivers.json)에 없습니다")
    covered = in_sample | {alias[k] for k in alias if k in in_sample} | set(alias)
    for vid in sorted(var):
        if vid not in covered:
            warns.append(f"데이터사전의 {vid} {var[vid]['name']} 에 전처리 계열(factor_sample)이 없습니다")
        if var[vid].get("driver") not in driver_ids:
            warns.append(f"데이터사전의 {vid} 동인 '{var[vid].get('driver')}' 가 drivers 목록에 없습니다")
    try:
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app.services.indicator_registry import REGISTRY
    except Exception as e:  # 백엔드 의존성이 없는 환경에서도 보드는 만든다
        warns.append(f"레지스트리를 읽지 못해 수집 쪽 점검을 건너뜁니다: {e}")
        return warns
    for spec in REGISTRY:
        vid = spec.var or spec.id
        if vid not in var:
            warns.append(f"레지스트리 {spec.id} 의 변수 {vid} 가 데이터사전에 없습니다")
        elif spec.driver != var[vid].get("driver"):
            warns.append(f"레지스트리 {spec.id} 동인 '{spec.driver}' ≠ 데이터사전 '{var[vid].get('driver')}'")
    return warns


def payload(fs, dv):
    var = {v["id"]: v for v in dv["variables"]}
    alias = fs.get("aliases", {})
    metrics = []
    for m in fs["metrics"]:
        meta = var.get(m["var"]) or var.get(alias.get(m["var"], ""), {})
        metrics.append({
            "v": m["var"], "col": m["column"], "label": m["label"], "unit": m.get("unit") or "",
            "freq": m["freq"], "scope": m["scope"], "p": m["periods"],
            "s": {k: [rnd(x) for x in vs] for k, vs in m["series"].items()},
            "driver": meta.get("driver", "macro"), "sign": meta.get("sign", ""),
            "filled": m.get("filled") or 0, "method": m.get("method") or "", "source": m.get("source") or "",
            "y": m["var"] == Y_VAR, "excluded": max(m["periods"]) < "2016",
        })
    return {
        "source": fs["_source"], "generated": fs["generated"], "regions": fs["regions"],
        "drivers": [{k: d[k] for k in ("id", "no", "name", "short")} for d in dv["drivers"]],
        "metrics": metrics,
    }


def main(argv):
    fs, dv = load(SAMPLE), load(DRIVERS)
    warns = check(fs, dv)
    data = json.dumps(payload(fs, dv), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read().replace("__DATA__", data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    xs = [m for m in fs["metrics"] if m["var"] != Y_VAR]
    print(f"보드: {os.path.relpath(OUT, ROOT)} ({len(html) // 1024} KB) · 설명변수 {len({m['var'] for m in xs})}개 · 계열 {len(xs)}개")
    for w in warns:
        print("  경고:", w)
    if not warns:
        print("  점검: 이상 없음")
    return 1 if warns and "--strict" in argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
