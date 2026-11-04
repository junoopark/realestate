"""HTML 보고서 (outputs/report.html) — 산출 표를 JSON 으로 넣고 브라우저에서 표·차트를 그린다.

외부 자원은 Google Fonts 만 쓴다(없어도 시스템 글꼴로 표시). 수치는 data/processed·outputs 의 표에서 그대로 가져온다.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .charts import SHORT
from .config import load_yaml

DWELL = {
    "apartment": "아파트", "flat_maisonette": "플랫·메조네트", "private_domestic_class_B": "민간 Class B(40~70㎡)",
    "private_domestic_all_classes": "민간 전체", "hdb_flat": "HDB 공공주택", "sfr_condo": "단독+콘도",
    "sfr_condo_multifamily": "단독+콘도+다세대", "purpose_built_apartment_2br": "목적형 임대 2침실",
    "attached_dwelling": "공동주택", "all_renter_occupied": "전체 임차가구", "condominium": "맨션",
}
VAR_KO = {"price_level": "가격 수준", "price_sqm": "㎡당 가격", "rent_month": "임대료 수준", "hh_income": "가구소득",
          "earnings": "근로자 소득", "price_index": "가격지수", "rent_index": "임대지수", "price_index_national": "전국 가격지수",
          "mortgage_to_gdp": "주택담보대출/GDP", "construction_to_gdp": "건설투자/GDP"}


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def _rows(df: pd.DataFrame, cols: dict) -> list[dict]:
    return [{k: _clean(r[c]) if c in r else None for k, c in cols.items()} for _, r in df.iterrows()]


def build_data(ctx) -> dict:
    proc, out = ctx.processed, ctx.outputs
    meta = json.loads((proc / "run_meta.json").read_text(encoding="utf-8"))
    cy_year = int(meta["common_year"])
    lv = pd.read_csv(proc / "city_level_metrics.csv")
    la = pd.read_csv(proc / "city_latest_available.csv")
    ps = pd.read_csv(proc / "path_summary.csv")
    panel = pd.read_parquet(proc / "city_panel_annual.parquet")
    dep = pd.read_csv(proc / "seoul_deposit.csv")
    comp = pd.read_csv(proc / "composite_optional.csv")
    cov = pd.read_csv(out / "coverage_matrix.csv")
    cat = pd.read_csv(out / "source_catalog.csv")
    qf = pd.read_csv(proc / "quality_flags.csv")
    gaps = load_yaml(ctx.root / "configs" / "gaps.yaml").get("gaps", [])

    cy = lv[lv["year"] == cy_year].copy()
    cy["concept"] = cy["income_concept"].fillna("").map(lambda c: SHORT.get(c, c))
    cy["dwell"] = cy["dwelling_type"].fillna("").map(lambda d: DWELL.get(d, d))
    metric_rows = {}
    for m in ["PTR", "gross_yield", "RTI_hh", "RTI_hh_est", "RTI_cash_hh", "RTI_earn", "PIR_hh", "PIR_earn", "RTI_official"]:
        g = cy[cy["metric"] == m]
        metric_rows[m] = _rows(g, {"city": "city_id", "value": "value", "year": "year", "q": "quality_flag",
                                   "concept": "concept", "dwell": "dwell", "notes": "notes"})
    levels = []
    for cid in ctx.cities:
        g = cy[cy["city_id"] == cid].set_index("metric")["value"]
        if g.empty:
            continue
        levels.append({"city": cid, **{k: _clean(g.get(k)) for k in (
            "price_level_local", "price_level_usd", "rent_month_local", "rent_month_usd", "price_sqm_usd", "hh_income_local",
            "hh_income_usd", "earnings_local", "earnings_usd")}})
    latest = _rows(la[la["metric"].isin(["PTR", "RTI_hh", "RTI_hh_est", "RTI_earn", "PIR_hh", "PIR_earn"])],
                   {"city": "city_id", "metric": "metric", "value": "value", "year": "year", "q": "quality_flag"})
    rel = panel[(panel["variable"] == "rel_PTR") & (panel["year"] >= int(meta["base_year"]) - 7)]
    relptr = {c: [[int(y), round(float(v), 2)] for y, v in zip(g.sort_values("year")["year"], g.sort_values("year")["value"])]
              for c, g in rel.groupby("city_id")}
    real5 = []
    for cid in ctx.cities:
        r = {"city": cid}
        for lab in ("price", "rent"):
            s = ps[(ps["city_id"] == cid) & (ps["series"] == lab)]
            r[lab] = _clean(s["real_cum_5y_pct"].iloc[0]) if len(s) else None
            r[lab + "_last"] = _clean(s["last_year"].iloc[0]) if len(s) else None
            r[lab + "_q"] = s["quality_flag"].iloc[0] if len(s) else None
        real5.append(r)
    deposit = _rows(dep[dep["contracts"] != "R-ONE 표본 평균(전체 면적)"], {
        "year": "year", "contracts": "contracts", "n": "n", "label": "rate_label", "rate": "rate_pct",
        "cash": "cash_rent_60", "dep": "deposit_60", "conv": "converted_rent_60", "ptr": "PTR", "yield": "gross_yield_pct",
        "rti_hh": "RTI_hh_pct", "rti_earn": "RTI_earn_pct"})
    sv = dep[dep["contracts"] == "R-ONE 표본 평균(전체 면적)"].sort_values("year")
    survey = _rows(sv.tail(1), {"year": "year", "cash": "survey_mean_cash_rent", "dep": "survey_mean_deposit",
                                "conv": "survey_mean_converted_rent", "rate": "rate_pct"})
    core = ["price_level", "rent_month", "hh_income", "earnings", "price_index", "rent_index", "price_index_national"]
    coverage = []
    for cid in ctx.cities:
        for v in core:
            g = cov[(cov["city_id"] == cid) & (cov["variable"] == v)]
            if len(g) and g["last_complete_year"].notna().any():
                coverage.append({"city": cid, "var": v, "n": int(g["n_years_complete"].max()), "first": int(g["first_year"].min()),
                                 "last": int(g["last_complete_year"].max()), "q": g["quality_flag"].iloc[0]})
    sources = []
    ok = cat[(cat["확보 여부"] == "확보") & cat["variable"].isin(["price_level", "rent_month", "hh_income", "earnings",
                                                                 "price_index", "rent_index"])]
    for _, r in ok.iterrows():
        sources.append({"city": r["city_id"], "var": r["variable"], "ubs": r["UBS 기관(원문 p.27)"], "ours": r["본 프로젝트 기관"],
                        "code": r["series_code"], "url": r["source_url"], "method": r["정의·방법"], "q": r["quality_flag"],
                        "first": r["first"], "last": r["last"]})
    composite = _rows(comp, {"city": "city_id", "z_pir": "z_price_to_income_rel", "z_ptr": "z_price_to_rent_rel",
                             "z_cc": "z_city_to_country_rel", "gap3": "price_gap_3item", "credit": "household_credit_to_gdp_change_pp"})
    cr = panel[panel["variable"] == "household_credit_to_gdp"]
    credit = []
    for cid in ctx.cities:
        s = cr[cr["city_id"] == cid].sort_values("year").set_index("year")["value"]
        if len(s):
            t = int(s.index.max())
            credit.append({"city": cid, "value": _clean(s.loc[t]), "year": t,
                           "change3": _clean(s.loc[t] - s.loc[t - 3]) if t - 3 in s.index else None})
    return {
        "meta": {**meta, "n_flags": len(qf), "n_errors": int((qf["severity"] == "error").sum())},
        "cities": [{"id": k, "name": v["name_ko"], "en": v["name_en"], "currency": v["currency"], "geo": v["geography"]}
                   for k, v in ctx.cities.items()],
        "metrics": metric_rows, "levels": levels, "latest": latest, "relptr": relptr, "real5": real5,
        "deposit": deposit, "survey": survey[0] if survey else None, "coverage": coverage,
        "gaps": [{"city": g["city_id"], "var": VAR_KO.get(g["variable"], g["variable"]), "reason": g["reason"],
                  "partial": bool(g.get("partial"))} for g in gaps],
        "sources": sources, "composite": composite, "credit": credit, "var_ko": VAR_KO,
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>서울 렌트 부담 국제 비교</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Gothic+A1:wght@500;700;800&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  /* 통계 연보 같은 차분한 청회색 지면, 서울만 파랑으로 강조 · 요약 → 렌트 부담 → 가격 → 추세 → 서울 심층 → 자료 */
  --paper: #f6f7f8;
  --surface: #ffffff;
  --ink: #12161c;
  --ink-2: #4c5562;
  --ink-3: #7b8491;
  --rule: #dfe3e8;
  --track: #eceff2;
  --seoul: #2a78d6;
  --seoul-soft: #dbe8f8;
  --other: #b3b9c1;
  --alt: #eb6834;
  --good: #1f7a4d; --good-bg: #e2f2e9;
  --warn: #8a5a00; --warn-bg: #fbefd2;
  --neutral-bg: #eceff2;
  --font-display: "Gothic A1", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  --font-body: "IBM Plex Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #14171b; --surface: #1b1f24; --ink: #eef1f4; --ink-2: #b4bcc6; --ink-3: #8a939e; --rule: #2c323a;
    --track: #262b32; --seoul: #3987e5; --seoul-soft: #1d3554; --other: #5d6670; --alt: #d95926;
    --good: #6cc79a; --good-bg: #183327; --warn: #e6b34d; --warn-bg: #3a2e14; --neutral-bg: #262b32;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --paper: #14171b; --surface: #1b1f24; --ink: #eef1f4; --ink-2: #b4bcc6; --ink-3: #8a939e; --rule: #2c323a;
  --track: #262b32; --seoul: #3987e5; --seoul-soft: #1d3554; --other: #5d6670; --alt: #d95926;
  --good: #6cc79a; --good-bg: #183327; --warn: #e6b34d; --warn-bg: #3a2e14; --neutral-bg: #262b32;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--paper); color: var(--ink); font-family: var(--font-body); font-size: 15px; line-height: 1.6; }
main { max-width: 1120px; margin: 0 auto; padding: 32px 20px 64px; display: grid; gap: 28px; }
h1, h2, h3 { font-family: var(--font-display); text-wrap: balance; margin: 0; letter-spacing: -0.01em; }
h1 { font-size: clamp(26px, 4vw, 36px); font-weight: 800; }
h2 { font-size: 21px; font-weight: 800; }
h3 { font-size: 16px; font-weight: 700; }
p { margin: 0; max-width: 72ch; }
.muted { color: var(--ink-2); }
.small { font-size: 13px; }
.num { font-variant-numeric: tabular-nums; }
a { color: var(--seoul); }
a:focus-visible, button:focus-visible, summary:focus-visible { outline: 2px solid var(--seoul); outline-offset: 2px; }
header.top { display: grid; gap: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--rule); }
.meta-line { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--ink-2); }
.meta-line b { color: var(--ink); font-weight: 600; }
section.card { background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 22px 22px 20px; display: grid; gap: 16px; min-width: 0; }
.sec-head { display: grid; gap: 6px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 22px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.tile { border: 1px solid var(--rule); border-left: 4px solid var(--seoul); border-radius: 8px; padding: 12px 14px; background: var(--surface); display: grid; gap: 4px; }
.tile.est { border-left-style: dashed; }
.tile .k { font-size: 12.5px; color: var(--ink-2); }
.tile .v { font-family: var(--font-display); font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; }
.tile .s { font-size: 12.5px; color: var(--ink-3); }
.pill { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: var(--neutral-bg); color: var(--ink-2); white-space: nowrap; }
.pill.qA { background: var(--good-bg); color: var(--good); }
.pill.qC { background: var(--warn-bg); color: var(--warn); }
.chip { display: inline-block; font-size: 11.5px; padding: 0 6px; border: 1px solid var(--rule); border-radius: 4px; color: var(--ink-2); white-space: nowrap; }
.note { font-size: 13px; color: var(--ink-2); border-left: 3px solid var(--rule); padding-left: 10px; }
/* 가로 막대 */
.bars { display: grid; gap: 6px; }
.bar-row { display: grid; grid-template-columns: minmax(86px, 128px) 1fr minmax(64px, auto); align-items: center; gap: 10px; cursor: default; }
.bar-row .lab { font-size: 13.5px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-row .lab .yr { color: var(--ink-3); font-size: 12px; }
.bar-track { position: relative; height: 22px; background: var(--track); border-radius: 0 4px 4px 0; }
.bar { position: absolute; left: 0; top: 0; bottom: 0; background: var(--other); border-radius: 0 4px 4px 0; min-width: 2px; }
.bar.seoul { background: var(--seoul); }
.bar.hatch { background-image: repeating-linear-gradient(135deg, rgba(255,255,255,.55) 0 3px, transparent 3px 7px); }
.bar-row .val { font-size: 13px; font-variant-numeric: tabular-nums; white-space: nowrap; display: flex; gap: 6px; align-items: center; }
.bar-row:hover .bar-track, .bar-row:focus-within .bar-track { outline: 1px solid var(--ink-3); }
.bar-sub { grid-column: 2 / 4; font-size: 11.5px; color: var(--ink-3); margin-top: -4px; }
/* 발산 막대 (0 기준) */
.dbar-track { position: relative; height: 20px; }
.dbar-track .zero { position: absolute; top: -3px; bottom: -3px; width: 1px; background: var(--ink-3); }
.dbar { position: absolute; top: 0; bottom: 0; background: var(--other); }
.dbar.seoul { background: var(--seoul); }
/* 표 */
.tbl-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { padding: 7px 9px; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; }
th { font-weight: 600; color: var(--ink-2); font-size: 12.5px; background: var(--paper); position: sticky; top: 0; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; }
tr.seoul-row td { background: var(--seoul-soft); }
details { border-top: 1px dashed var(--rule); padding-top: 8px; }
summary { cursor: pointer; font-size: 13px; color: var(--seoul); }
/* 커버리지 */
.cov td.c { text-align: center; font-size: 12px; font-variant-numeric: tabular-nums; min-width: 86px; }
.cov td.c span { display: block; border-radius: 4px; padding: 3px 4px; }
.cov td.none { color: var(--ink-3); text-align: center; }
/* SVG 차트 */
.chart { position: relative; width: 100%; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart text { fill: var(--ink-2); font-size: 12px; font-family: var(--font-body); }
.chart .grid line { stroke: var(--rule); stroke-width: 1; }
.chart .axis-label { fill: var(--ink-3); font-size: 11.5px; }
.tip { position: fixed; z-index: 10; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--rule); border-radius: 8px; padding: 8px 10px; font-size: 12.5px; line-height: 1.45; box-shadow: 0 6px 20px rgba(0,0,0,.14); max-width: 320px; display: none; }
.tip b { font-weight: 600; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; color: var(--ink-2); }
.legend i { display: inline-block; width: 18px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
ul.gaps { margin: 0; padding-left: 18px; display: grid; gap: 4px; font-size: 13.5px; }
footer { font-size: 12.5px; color: var(--ink-3); display: grid; gap: 4px; }
@media (max-width: 520px) {
  main { padding: 20px 16px 48px; }
  section.card { padding: 16px; }
  .bar-row { grid-template-columns: 78px 1fr auto; gap: 8px; }
}
@media (prefers-reduced-motion: no-preference) { .bar, .dbar { transition: width .25s ease; } }
</style>
</head>
<body>
<main>
<header class="top">
  <h1>서울 렌트 부담, 해외 10개 도시와 비교</h1>
  <p class="muted">서울 60㎡ 아파트의 임대료·가격을 같은 기준으로 맞춘 해외 도시 자료와 비교했다. 소득 개념이 도시마다 달라 서로 다른 개념은 한 순위에 넣지 않았다.</p>
  <div class="meta-line" id="metaLine"></div>
</header>

<section class="card" aria-labelledby="h-sum">
  <div class="sec-head"><h2 id="h-sum">서울 요약</h2>
    <p class="muted small" id="sumNote"></p></div>
  <div class="tiles" id="tiles"></div>
</section>

<section class="card" aria-labelledby="h-rti">
  <div class="sec-head"><h2 id="h-rti">소득 대비 연 임대료</h2>
    <p class="muted small">12 × 월 임대료 ÷ 연소득 × 100. 막대 옆 칩은 소득 개념이다. 빗금은 품질 C(추정·정의 불일치)다. 막대에 마우스를 올리면 정의가 보인다.</p></div>
  <div class="grid-2">
    <div><h3>가구소득 기준</h3><div class="bars" id="barsRtiHh"></div></div>
    <div><h3>근로자 1인 소득 기준</h3><div class="bars" id="barsRtiEarn"></div></div>
  </div>
  <p class="note" id="rtiNote"></p>
  <details><summary>표로 보기</summary><div class="tbl-wrap" id="tblRti"></div></details>
</section>

<section class="card" aria-labelledby="h-ptr">
  <div class="sec-head"><h2 id="h-ptr">임대료·소득 대비 가격</h2>
    <p class="muted small">PTR = 가격 ÷ 연 임대료, PIR = 가격 ÷ 연소득 (단위: 년). 매매·임대 대표값의 비율이며 같은 주택의 수익률이 아니다.</p></div>
  <div class="grid-2">
    <div><h3>PTR</h3><div class="bars" id="barsPtr"></div></div>
    <div><h3>PIR (가구소득)</h3><div class="bars" id="barsPirHh"></div>
      <h3 style="margin-top:14px">PIR (근로자 소득)</h3><div class="bars" id="barsPirEarn"></div></div>
  </div>
  <p class="note" id="ptrNote"></p>
  <details><summary>수준 표(현지통화·USD) 보기</summary><div class="tbl-wrap" id="tblLevels"></div></details>
</section>

<section class="card" aria-labelledby="h-latest">
  <div class="sec-head"><h2 id="h-latest">도시별 최신 시점</h2>
    <p class="muted small">가격·임대료·소득을 같은 해로 맞춘 마지막 해의 값이다(괄호 = 관측연도). 소득을 추정해 늘리지 않았다.</p></div>
  <div class="tbl-wrap" id="tblLatest"></div>
</section>

<section class="card" aria-labelledby="h-path">
  <div class="sec-head"><h2 id="h-path">기준연도 이후 가격 대비 임대료</h2>
    <p class="muted small" id="pathNote"></p></div>
  <div class="chart" id="chartRel"></div>
  <div class="grid-2">
    <div><h3>실질 주택가격 5년 누적 변화</h3><div class="bars" id="barsRealP"></div></div>
    <div><h3>실질 임대료 5년 누적 변화</h3><div class="bars" id="barsRealR"></div></div>
  </div>
  <details><summary>표로 보기</summary><div class="tbl-wrap" id="tblPath"></div></details>
</section>

<section class="card" aria-labelledby="h-dep">
  <div class="sec-head"><h2 id="h-dep">서울 보증금 환산과 민감도</h2>
    <p class="muted small">환산 월 임대료 = 계약 월세 + 보증금 × 연 환산율 ÷ 12. 계약마다 계산한 뒤 전용 50~70㎡ ㎡당 중위값 × 60㎡로 모았다. 기준 환산율은 한국부동산원이 관측한 서울 아파트 전월세 전환율의 연평균이다(법정 상한 아님).</p></div>
  <div class="grid-2">
    <div><h3>환산율별 60㎡ 월 임대료 (만원)</h3><div class="legend" id="legDep"></div><div class="chart" id="chartDep"></div></div>
    <div><h3>계약 유형별 (기준 환산율)</h3><div class="tbl-wrap" id="tblDepType"></div></div>
  </div>
  <p class="note" id="depNote"></p>
  <details><summary>환산율 시나리오 전체 표</summary><div class="tbl-wrap" id="tblDep"></div></details>
</section>

<section class="card" aria-labelledby="h-cov">
  <div class="sec-head"><h2 id="h-cov">자료 확보 현황</h2>
    <p class="muted small">칸 = 확보 기간과 완전한 연간 관측 연수, 품질 등급(A 정의·범위 일치 / B 일부 불일치·공개 민간 / C 추정·불일치 큼). 빈칸은 미확보.</p></div>
  <div class="tbl-wrap"><table class="cov" id="tblCov"></table></div>
  <h3>미확보·일부 확보 이유</h3>
  <ul class="gaps" id="gapList"></ul>
</section>

<section class="card" aria-labelledby="h-c">
  <div class="sec-head"><h2 id="h-c">보조 지표: 신용과 가격괴리</h2>
    <p class="muted small">가계신용/GDP 는 BIS 가계·비영리 신용 전체이며 주택담보대출이 아니다. 주택담보대출/GDP·건설투자/GDP 를 확보하지 못해 설계서의 5항목 합성지수는 모든 도시에서 계산하지 않았다(가중치 재배분 없음). '가격괴리 3항목'은 상대 PIR·PTR·도시/전국 지수를 각 도시의 최근 10년과 비교한 z 점수 평균으로, 위험 확률이 아니다.</p></div>
  <div class="tbl-wrap" id="tblComp"></div>
</section>

<section class="card" aria-labelledby="h-src">
  <div class="sec-head"><h2 id="h-src">출처와 정의</h2>
    <p class="muted small">UBS Global Real Estate Bubble Index 2026 p.27 의 기관 목록과 이 분석이 실제로 쓴 계열을 나란히 둔다. UBS 원문에는 계열 코드·가중치가 없어 공개자료로 독립 구성했다.</p></div>
  <div class="tbl-wrap" id="tblSrc"></div>
</section>

<footer id="foot"></footer>
</main>
<div class="tip" id="tip" role="status"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById("data").textContent);
  const city = Object.fromEntries(D.cities.map(c => [c.id, c]));
  const nm = id => (city[id] ? city[id].name : id);
  const nf = (v, d = 1) => v == null ? "NA" : v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const won = v => v == null ? "NA" : (v >= 1e8 ? nf(v / 1e8, 2) + "억 원" : nf(v / 1e4, 0) + "만 원");
  const money = (v, cur) => v == null ? "NA" : (cur === "KRW" ? won(v) : nf(v, 0) + " " + cur);
  const el = (tag, attrs = {}, html = "") => { const e = document.createElement(tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (html) e.innerHTML = html; return e; };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pill = q => q ? `<span class="pill q${q}">품질 ${q}</span>` : "";
  const M = D.metrics, meta = D.meta;
  const get = (m, c) => (M[m] || []).find(r => r.city === c);

  // tooltip
  const tip = document.getElementById("tip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.style.display = "block";
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = x + 14, top = y + 14;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (top + h > window.innerHeight - 8) top = y - h - 14;
    tip.style.left = Math.max(8, left) + "px"; tip.style.top = Math.max(8, top) + "px";
  }
  const hideTip = () => { tip.style.display = "none"; };

  // header
  document.getElementById("metaLine").innerHTML =
    `<span>기준일 <b>${meta.as_of}</b></span><span>공통연도 <b>${meta.common_year}</b></span>` +
    `<span>상대지수 기준연도 <b>${meta.base_year}</b></span><span>표본 <b>${D.cities.length}개 도시</b></span>` +
    `<span>검증 ${meta.n_flags}건 · 오류 ${meta.n_errors}건</span>`;

  // tiles
  const s = k => get(k, "seoul");
  const tiles = [
    { k: "PTR (가격 ÷ 연 임대료)", v: s("PTR") && nf(s("PTR").value) + "년", s: s("gross_yield") && "총임대수익률 " + nf(s("gross_yield").value, 2) + "%" },
    { k: "가구 평균소득 대비 임대료", v: s("RTI_hh") && nf(s("RTI_hh").value) + "%", s: s("RTI_cash_hh") && "현금 월세만 " + nf(s("RTI_cash_hh").value) + "%" },
    { k: "중위소득(추정) 대비 임대료", v: s("RTI_hh_est") && nf(s("RTI_hh_est").value) + "%", s: "서울 평균 × 전국 중위/평균 · 품질 C", est: true },
    { k: "근로자 1인 소득 대비 임대료", v: s("RTI_earn") && nf(s("RTI_earn").value) + "%", s: "상용근로자 평균 임금 기준" },
    { k: "PIR (가격 ÷ 가구 평균소득)", v: s("PIR_hh") && nf(s("PIR_hh").value) + "년", s: s("PIR_earn") && "근로자 소득 기준 " + nf(s("PIR_earn").value) + "년" },
  ];
  const tl = document.getElementById("tiles");
  tiles.forEach(t => { if (t.v) tl.appendChild(el("div", { class: "tile" + (t.est ? " est" : "") }, `<span class="k">${t.k}</span><span class="v">${t.v}</span><span class="s">${t.s || ""}</span>`)); });
  const lvS = D.levels.find(r => r.city === "seoul");
  document.getElementById("sumNote").textContent = lvS ?
    `${meta.common_year}년 서울 60㎡ 아파트(전용 50~70㎡ 실거래 중위): 가격 ${won(lvS.price_level_local)}, 보증금을 포함해 환산한 월 임대료 ${won(lvS.rent_month_local)}. 소득은 가계금융복지조사 서울 가구 평균 경상소득(세전).` : "";

  // bar chart (HTML)
  function bars(id, rows, opt) {
    const box = document.getElementById(id); box.innerHTML = "";
    rows = rows.filter(r => r.value != null).sort((a, b) => b.value - a.value);
    if (!rows.length) { box.innerHTML = '<p class="muted small">자료 없음</p>'; return; }
    const max = Math.max(...rows.map(r => r.value)) * 1.04;
    rows.forEach(r => {
      const isS = r.city === "seoul";
      const row = el("div", { class: "bar-row", tabindex: "0" });
      row.innerHTML = `<div class="lab">${esc(r.label || nm(r.city))} <span class="yr">${r.year || ""}</span></div>` +
        `<div class="bar-track"><div class="bar ${isS ? "seoul" : ""} ${r.q === "C" ? "hatch" : ""}" style="width:${(r.value / max * 100).toFixed(2)}%"></div></div>` +
        `<div class="val"><b class="num">${opt.fmt(r.value)}</b>${r.q === "C" ? '<span class="pill qC">C</span>' : ""}</div>` +
        (r.concept ? `<div class="bar-sub">${esc(r.concept)}${r.dwell ? " · " + esc(r.dwell) : ""}</div>` : "");
      const html = `<b>${esc(r.label || nm(r.city))} ${r.year || ""}</b><br>${opt.fmt(r.value)} ${pill(r.q)}` +
        (r.concept ? `<br>소득: ${esc(r.concept)}` : "") + (r.dwell ? `<br>주택: ${esc(r.dwell)}` : "") +
        (r.notes ? `<br><span class="muted">${esc(r.notes)}</span>` : "");
      row.addEventListener("mousemove", e => showTip(html, e.clientX, e.clientY));
      row.addEventListener("mouseleave", hideTip);
      row.addEventListener("focus", () => { const b = row.getBoundingClientRect(); showTip(html, b.right - 40, b.top); });
      row.addEventListener("blur", hideTip);
      box.appendChild(row);
    });
  }
  const pct = v => nf(v) + "%", yrs = v => nf(v) + "년";
  const est = (M.RTI_hh_est || []).map(r => ({ ...r, label: "서울(중위 추정)", q: "C" }));
  bars("barsRtiHh", [...(M.RTI_hh || []), ...est], { fmt: pct });
  bars("barsRtiEarn", M.RTI_earn || [], { fmt: pct });
  bars("barsPtr", M.PTR || [], { fmt: yrs });
  bars("barsPirHh", M.PIR_hh || [], { fmt: yrs });
  bars("barsPirEarn", M.PIR_earn || [], { fmt: yrs });

  // rent burden note (computed)
  const med = (M.RTI_hh || []).filter(r => /중위/.test(r.concept) && /^가구/.test(r.concept));
  const sEst = (M.RTI_hh_est || [])[0];
  let rn = "서울은 시도별 가구소득 중위값이 공표되지 않아 평균소득을 쓴다. 같은 개념을 쓰는 비교 도시가 없어 순위를 매기지 않는다.";
  if (sEst && med.length) {
    const all = [...med, { city: "seoul", value: sEst.value }].sort((a, b) => b.value - a.value);
    const k = all.findIndex(r => r.city === "seoul") + 1;
    rn += ` 보조 비교로 중위소득 추정치를 쓰면 ${nf(sEst.value)}%로, 가구 세전소득 중위를 쓰는 ${all.length}개 도시 중 ${k === 1 ? "가장" : k + "번째로"} 높다(추정치라 결론의 근거로 쓰지 않음).`;
  }
  const off = M.RTI_official || [];
  if (off.length) rn += " 미국 ACS 공식 임대료 부담률(기존 임차가구 중위): " + off.map(r => `${nm(r.city)} ${nf(r.value)}%`).join(", ") + ".";
  document.getElementById("rtiNote").textContent = rn;

  // PTR note
  const ab = (M.PTR || []).filter(r => r.q === "A" || r.q === "B").sort((a, b) => b.value - a.value);
  const kS = ab.findIndex(r => r.city === "seoul") + 1;
  document.getElementById("ptrNote").textContent = kS ?
    `주택유형이 비교적 맞는 품질 A·B ${ab.length}개 도시(${ab.map(r => nm(r.city)).join(", ")}) 중 서울 PTR 이 ${kS === 1 ? "가장" : kS + "번째로"} 높다. 뉴욕·샌프란시스코는 단독주택 포함 가격과 다세대 포함 호가 임대료라, 싱가포르는 HDB 공공주택이라 품질 C 로 순위에서 뺐다.` : "";

  // tables helpers
  function table(id, head, rows, rowCls) {
    const t = `<table><thead><tr>${head.map(h => `<th class="${h.r ? "r" : ""}">${h.t}</th>`).join("")}</tr></thead><tbody>` +
      rows.map(r => `<tr class="${rowCls ? rowCls(r) : ""}">${r.cells.map((c, i) => `<td class="${head[i].r ? "r" : ""}">${c}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
    document.getElementById(id).innerHTML = t;
  }
  const rtiRows = [];
  [["RTI_hh", "가구소득"], ["RTI_hh_est", "가구 중위(추정)"], ["RTI_earn", "근로자 소득"]].forEach(([m, lab]) =>
    (M[m] || []).forEach(r => rtiRows.push({ city: r.city, cells: [nm(r.city), lab, nf(r.value) + "%", esc(r.concept), esc(r.dwell), pill(r.q)] })));
  table("tblRti", [{ t: "도시" }, { t: "기준" }, { t: "임대료/소득", r: 1 }, { t: "소득 개념" }, { t: "주택" }, { t: "품질" }], rtiRows, r => r.city === "seoul" ? "seoul-row" : "");
  table("tblLevels", [{ t: "도시" }, { t: "대표 주택가격" }, { t: "USD", r: 1 }, { t: "월 임대료" }, { t: "USD/월", r: 1 }, { t: "㎡당 가격 USD", r: 1 }, { t: "가구소득" }, { t: "근로자 소득" }],
    D.levels.map(r => { const cur = city[r.city].currency; return { city: r.city, cells: [nm(r.city), money(r.price_level_local, cur), nf(r.price_level_usd, 0), money(r.rent_month_local, cur), nf(r.rent_month_usd, 0), nf(r.price_sqm_usd, 0), money(r.hh_income_local, cur), money(r.earnings_local, cur)] }; }),
    r => r.city === "seoul" ? "seoul-row" : "");

  // latest table
  const LM = [["PTR", "PTR(년)"], ["RTI_hh", "임대료/가구소득"], ["RTI_hh_est", "임대료/중위 추정"], ["RTI_earn", "임대료/근로자 소득"], ["PIR_hh", "PIR 가구"], ["PIR_earn", "PIR 근로자"]];
  table("tblLatest", [{ t: "도시" }, ...LM.map(([, t]) => ({ t, r: 1 }))],
    D.cities.map(c => ({ city: c.id, cells: [c.name, ...LM.map(([m]) => { const r = D.latest.find(x => x.city === c.id && x.metric === m); return r ? `${nf(r.value)}${/RTI/.test(m) ? "%" : ""} <span class="muted small">(${r.year})</span>` : '<span class="muted">NA</span>'; })] })),
    r => r.city === "seoul" ? "seoul-row" : "");

  // line chart: rel PTR
  function lineChart(id, series, opt) {
    const box = document.getElementById(id); box.innerHTML = "";
    const W = Math.max(340, Math.round(box.clientWidth || 980)), H = W < 600 ? 300 : (opt.h || 340), L = 40, R = W < 600 ? 84 : 110, T = 14, B = 30;
    const pts = Object.values(series).flat();
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ys, opt.ref || Infinity), y1 = Math.max(...ys, opt.ref || -Infinity);
    const pad = (y1 - y0) * 0.08; y0 -= pad; y1 += pad;
    const sx = x => L + (x - x0) / (x1 - x0) * (W - L - R), sy = y => T + (y1 - y) / (y1 - y0) * (H - T - B);
    const step = (y1 - y0) > 60 ? 20 : (y1 - y0) > 25 ? 10 : 5;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.aria)}"><g class="grid">`;
    for (let v = Math.ceil(y0 / step) * step; v <= y1; v += step) svg += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${L - 8}" y="${sy(v) + 4}" text-anchor="end">${v}</text>`;
    const xstep = W < 600 ? 3 : (x1 - x0 > 12 ? 2 : 1);
    for (let x = x0; x <= x1; x++) if ((x - x0) % xstep === 0) svg += `<text x="${sx(x)}" y="${H - 8}" text-anchor="middle">${x}</text>`;
    svg += "</g>";
    if (opt.ref != null) svg += `<line x1="${L}" x2="${W - R}" y1="${sy(opt.ref)}" y2="${sy(opt.ref)}" stroke="var(--ink-3)" stroke-width="1.2"/>`;
    const order = Object.keys(series).sort((a, b) => (a === opt.hi) - (b === opt.hi));
    const ends = [];
    order.forEach(k => {
      const p = series[k], hi = k === opt.hi;
      svg += `<polyline fill="none" stroke="${hi ? "var(--seoul)" : "var(--other)"}" stroke-width="${hi ? 2.6 : 1.6}" stroke-linejoin="round" points="${p.map(q => sx(q[0]) + "," + sy(q[1])).join(" ")}"/>`;
      const last = p[p.length - 1];
      if (hi) svg += `<circle cx="${sx(last[0])}" cy="${sy(last[1])}" r="4" fill="var(--seoul)" stroke="var(--surface)" stroke-width="2"/>`;
      ends.push({ k, y: sy(last[1]), x: sx(last[0]), hi });
    });
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 14);
    ends.forEach(e => { svg += `<text x="${e.x + 8}" y="${e.y + 4}" style="fill:${e.hi ? "var(--ink)" : "var(--ink-2)"};font-weight:${e.hi ? 600 : 400}">${esc(nm(e.k))}</text>`; });
    svg += `<line id="${id}-x" y1="${T}" y2="${H - B}" stroke="var(--ink-3)" stroke-dasharray="3 3" style="display:none"/>`;
    svg += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" id="${id}-hit"/></svg>`;
    box.innerHTML = svg;
    const s = box.querySelector("svg"), hit = box.querySelector(`#${id}-hit`), cross = box.querySelector(`#${id}-x`);
    hit.addEventListener("mousemove", e => {
      const r = s.getBoundingClientRect(), xv = Math.round(x0 + ((e.clientX - r.left) / r.width * W - L) / (W - L - R) * (x1 - x0));
      const yr = Math.max(x0, Math.min(x1, xv));
      cross.setAttribute("x1", sx(yr)); cross.setAttribute("x2", sx(yr)); cross.style.display = "";
      const rows = Object.entries(series).map(([k, p]) => [k, (p.find(q => q[0] === yr) || [])[1]]).filter(v => v[1] != null).sort((a, b) => b[1] - a[1]);
      showTip(`<b>${yr}</b><br>` + rows.map(([k, v]) => `${k === opt.hi ? "<b>" : ""}${esc(nm(k))} ${opt.fmt(v)}${k === opt.hi ? "</b>" : ""}`).join("<br>"), e.clientX, e.clientY);
    });
    hit.addEventListener("mouseleave", () => { cross.style.display = "none"; hideTip(); });
  }
  const drawRel = () => lineChart("chartRel", D.relptr, { hi: "seoul", ref: 100, fmt: v => nf(v), aria: "도시별 가격지수/임대료지수 상대값 추이" });
  drawRel();
  const sr = D.relptr.seoul || [];
  const lastRel = Object.entries(D.relptr).map(([k, p]) => [k, p[p.length - 1]]);
  const above = lastRel.filter(([k, p]) => k !== "seoul" && p[1] > 100).map(([k]) => nm(k));
  const below = lastRel.filter(([k, p]) => k !== "seoul" && p[1] <= 100).map(([k]) => nm(k));
  document.getElementById("pathNote").textContent =
    `가격지수 ÷ 임대료지수, ${meta.base_year}년 = 100. 100 위면 기준연도 이후 가격이 임대료보다 더 올랐다는 뜻이며 도시 간 실제 PTR 수준 비교가 아니다. ` +
    (sr.length ? `서울 ${sr[sr.length - 1][0]}년 ${nf(sr[sr.length - 1][1])}. 100 위: ${above.join(", ") || "없음"} · 100 아래: ${below.join(", ") || "없음"}. ` : "") +
    `기준연도 선택: ${meta.base_year_reason}`;

  // diverging bars for real change
  function dbars(id, rows) {
    const box = document.getElementById(id); box.innerHTML = "";
    rows = rows.filter(r => r.value != null).sort((a, b) => b.value - a.value);
    const m = Math.max(5, ...rows.map(r => Math.abs(r.value))) * 1.05;
    rows.forEach(r => {
      const isS = r.city === "seoul", w = Math.abs(r.value) / m * 50, left = r.value >= 0 ? 50 : 50 - w;
      const row = el("div", { class: "bar-row", tabindex: "0" });
      row.innerHTML = `<div class="lab">${esc(nm(r.city))} <span class="yr">${r.from}→${r.last}</span></div>` +
        `<div class="dbar-track"><div class="zero" style="left:50%"></div><div class="dbar ${isS ? "seoul" : ""}" style="left:${left}%;width:${w}%"></div></div>` +
        `<div class="val"><b class="num">${r.value > 0 ? "+" : ""}${nf(r.value)}%</b></div>`;
      const html = `<b>${esc(nm(r.city))}</b> ${r.from}→${r.last}<br>실질 ${r.value > 0 ? "+" : ""}${nf(r.value)}% ${pill(r.q)}`;
      row.addEventListener("mousemove", e => showTip(html, e.clientX, e.clientY));
      row.addEventListener("mouseleave", hideTip);
      box.appendChild(row);
    });
  }
  dbars("barsRealP", D.real5.map(r => ({ city: r.city, value: r.price, last: r.price_last, from: r.price_last - 5, q: r.price_q })));
  dbars("barsRealR", D.real5.map(r => ({ city: r.city, value: r.rent, last: r.rent_last, from: r.rent_last - 5, q: r.rent_q })));
  table("tblPath", [{ t: "도시" }, { t: "실질 가격 5년", r: 1 }, { t: "실질 임대료 5년", r: 1 }, { t: `가격/임대료 지수 (${meta.base_year}=100)`, r: 1 }],
    D.real5.map(r => { const p = D.relptr[r.city]; return { city: r.city, cells: [nm(r.city), r.price == null ? "NA" : nf(r.price) + "%", r.rent == null ? "NA" : nf(r.rent) + "%", p ? `${nf(p[p.length - 1][1])} (${p[p.length - 1][0]})` : "NA"] }; }),
    r => r.city === "seoul" ? "seoul-row" : "");

  // deposit chart
  const dep = D.deposit.filter(r => r.contracts === "월세(보증부 포함), 전체");
  const years = [...new Set(dep.map(r => r.year))].sort();
  const colors = ["var(--seoul)", "var(--alt)"];
  document.getElementById("legDep").innerHTML = years.map((y, i) => `<span><i style="background:${colors[i % 2]}"></i>${y}년 계약</span>`).join("");
  function drawDep() {
    const box = document.getElementById("chartDep");
    const W = Math.max(300, Math.round(box.clientWidth || 520)), H = 280, L = 44, R = 20, T = 12, B = 34;
    const pts = dep.map(r => [r.rate, r.conv / 1e4]);
    const x0 = 1.5, x1 = 6.5, y0 = Math.floor(Math.min(...pts.map(p => p[1])) / 10) * 10 - 5, y1 = Math.ceil(Math.max(...pts.map(p => p[1])) / 10) * 10 + 5;
    const sx = x => L + (x - x0) / (x1 - x0) * (W - L - R), sy = y => T + (y1 - y) / (y1 - y0) * (H - T - B);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="환산율별 서울 60㎡ 월 임대료"><g class="grid">`;
    for (let v = Math.ceil(y0 / 20) * 20; v <= y1; v += 20) svg += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${v}</text>`;
    for (let x = 2; x <= 6; x++) svg += `<text x="${sx(x)}" y="${H - 14}" text-anchor="middle">${x}%</text>`;
    svg += `<text class="axis-label" x="${(L + W - R) / 2}" y="${H - 1}" text-anchor="middle">연 환산율</text></g>`;
    years.forEach((y, i) => {
      const g = dep.filter(r => r.year === y).sort((a, b) => a.rate - b.rate);
      svg += `<polyline fill="none" stroke="${colors[i % 2]}" stroke-width="2.2" points="${g.map(r => sx(r.rate) + "," + sy(r.conv / 1e4)).join(" ")}"/>`;
      g.forEach(r => {
        const base = /^기준\(/.test(r.label);
        svg += `<circle class="dpt" data-y="${y}" data-r="${r.rate}" cx="${sx(r.rate)}" cy="${sy(r.conv / 1e4)}" r="${base ? 6 : 4.5}" fill="${base ? "var(--surface)" : colors[i % 2]}" stroke="${colors[i % 2]}" stroke-width="${base ? 3 : 2}"/>`;
      });
    });
    svg += "</svg>";
    box.innerHTML = svg;
    box.querySelectorAll(".dpt").forEach(c => {
      const r = dep.find(d => d.year == c.dataset.y && Math.abs(d.rate - c.dataset.r) < 1e-9);
      const html = `<b>${r.year}년 · ${esc(r.label)} ${nf(r.rate, 2)}%</b><br>환산 월 임대료 ${won(r.conv)}<br>PTR ${nf(r.ptr)}년 · 수익률 ${nf(r.yield, 2)}%` +
        (r.rti_hh != null ? `<br>가구 평균소득 대비 ${nf(r.rti_hh)}%` : "") + (r.rti_earn != null ? `<br>근로자 소득 대비 ${nf(r.rti_earn)}%` : "");
      c.addEventListener("mousemove", e => showTip(html, e.clientX, e.clientY));
      c.addEventListener("mouseleave", hideTip);
    });
  }
  drawDep();
  let rz;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { drawRel(); drawDep(); }, 150); });
  const dt = D.deposit.filter(r => /^기준\(/.test(r.label));
  table("tblDepType", [{ t: "연도" }, { t: "계약" }, { t: "건수", r: 1 }, { t: "현금 월세", r: 1 }, { t: "보증금", r: 1 }, { t: "환산 월세", r: 1 }],
    dt.map(r => ({ cells: [r.year, esc(r.contracts), nf(r.n, 0), won(r.cash), won(r.dep), "<b>" + won(r.conv) + "</b>"] })));
  table("tblDep", [{ t: "연도" }, { t: "환산율" }, { t: "%", r: 1 }, { t: "환산 월세", r: 1 }, { t: "PTR(년)", r: 1 }, { t: "수익률 %", r: 1 }, { t: "가구 평균소득 대비 %", r: 1 }, { t: "근로자 소득 대비 %", r: 1 }],
    dep.map(r => ({ cells: [r.year, esc(r.label), nf(r.rate, 2), won(r.conv), nf(r.ptr), nf(r.yield, 2), nf(r.rti_hh), nf(r.rti_earn)] })));
  const sv = D.survey, b24 = dep.find(r => /^기준\(/.test(r.label));
  const lo = dep.find(r => r.year === b24.year && r.label === "기준 -1%p"), hi = dep.find(r => r.year === b24.year && r.label === "기준 +1%p");
  document.getElementById("depNote").textContent =
    `${b24.year}년 기준 환산율 ${nf(b24.rate, 2)}%에서 60㎡ 환산 월 임대료는 ${won(b24.conv)}이고, 환산율을 ±1%p 바꾸면 ${won(lo.conv)}~${won(hi.conv)}, PTR 은 ${nf(hi.ptr)}~${nf(lo.ptr)}년이다. ` +
    `전세 계약의 보증금을 같은 환산율로 바꾼 월 임대료도 월세 계약과 비슷한 수준이다(계약 유형별 표). ` +
    (sv ? `교차 확인: 한국부동산원 표본조사(전체 면적 평균) ${sv.year}년 월세 ${won(sv.cash)}, 보증금 ${won(sv.dep)} → 환산 ${won(sv.conv)}. 면적·표본이 달라 실거래 60㎡ 값과 같지 않다. ` : "") +
    "전세가율(전세가/매매가)은 PTR 이 아니므로 쓰지 않았다.";

  // coverage
  const VARS = ["price_level", "rent_month", "hh_income", "earnings", "price_index", "rent_index", "price_index_national"];
  let ch = `<thead><tr><th>도시</th>${VARS.map(v => `<th>${D.var_ko[v] || v}</th>`).join("")}</tr></thead><tbody>`;
  D.cities.forEach(c => {
    ch += `<tr class="${c.id === "seoul" ? "seoul-row" : ""}"><td>${c.name}</td>` + VARS.map(v => {
      const r = D.coverage.find(x => x.city === c.id && x.var === v);
      if (!r) return '<td class="none">—</td>';
      const a = Math.min(1, r.n / 25);
      return `<td class="c"><span style="background:color-mix(in srgb, var(--seoul) ${Math.round(8 + a * 40)}%, transparent)">${r.first}–${r.last}<br>${r.n}년 · ${r.q}</span></td>`;
    }).join("") + "</tr>";
  });
  document.getElementById("tblCov").innerHTML = ch + "</tbody>";
  document.getElementById("gapList").innerHTML = D.gaps.map(g => `<li><b>${esc(g.city === "_all" ? "전체" : nm(g.city))} · ${esc(g.var)}</b>${g.partial ? ' <span class="pill">일부 확보</span>' : ""} — ${esc(g.reason)}</li>`).join("");

  // composite & credit
  table("tblComp", [{ t: "도시" }, { t: "z 상대PIR", r: 1 }, { t: "z 상대PTR", r: 1 }, { t: "z 도시/전국", r: 1 }, { t: "가격괴리 3항목", r: 1 }, { t: "가계신용/GDP", r: 1 }, { t: "3년 변화 %p", r: 1 }, { t: "5항목 합성" }],
    D.cities.map(c => { const r = D.composite.find(x => x.city === c.id) || {}; const k = D.credit.find(x => x.city === c.id) || {};
      return { city: c.id, cells: [c.name, nf(r.z_pir, 2), nf(r.z_ptr, 2), nf(r.z_cc, 2), r.gap3 == null ? "NA" : "<b>" + nf(r.gap3, 2) + "</b>", k.value == null ? "NA" : `${nf(k.value)}% (${k.year})`, nf(k.change3), '<span class="muted">NA</span>'] }; }),
    r => r.city === "seoul" ? "seoul-row" : "");

  // sources
  const VK = { price_level: "가격", rent_month: "임대료", hh_income: "가구소득", earnings: "근로자 소득", price_index: "가격지수", rent_index: "임대지수" };
  const src = D.sources.slice().sort((a, b) => D.cities.findIndex(c => c.id === a.city) - D.cities.findIndex(c => c.id === b.city));
  table("tblSrc", [{ t: "도시" }, { t: "항목" }, { t: "UBS 기관(p.27)" }, { t: "이 분석의 출처" }, { t: "정의" }, { t: "기간" }, { t: "품질" }],
    src.map(r => ({ city: r.city, cells: [nm(r.city), VK[r.var] || r.var, esc(r.ubs), r.url ? `<a href="${esc(r.url)}">${esc(r.ours)}</a>` : esc(r.ours), esc(r.method), `${esc(r.first)}–${esc(r.last)}`, pill(r.q)] })),
    r => r.city === "seoul" ? "seoul-row" : "");

  document.getElementById("foot").innerHTML =
    `<span>자동 생성: <code>python -m src.run --offline</code> (global_housing/). 수치는 data/processed·outputs 의 표에서 그대로 가져왔다.</span>` +
    `<span>UBS Global Real Estate Bubble Index 2026 pp.26–27 을 참고했으나 UBS 의 계열·가중치·위험등급·하락확률을 복제하지 않는다. 확보하지 못한 값은 NA 로 두었다.</span>`;
})();
</script>
</body>
</html>
"""


def run(ctx, log):
    data = build_data(ctx)
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", payload)
    path = ctx.outputs / "report.html"
    path.write_text(html, encoding="utf-8")
    log(f"  outputs/report.html ({len(html) // 1024} KB)")
    return path
