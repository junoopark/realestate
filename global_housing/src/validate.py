"""검증 (설계서 8절) — 결과를 data/processed/quality_flags.csv 에 남긴다. 값을 고치지 않는다.

검사: 중복 키, 0·음수, 비정상 도약, 단위 배율(USD 환산 범위), 월/연 환산(소득 대비 임대료 범위),
     지역 범위(도시 변수에 국가 계열이 들어갔는지), 면적 기준 누락, 공표일, 국가/도시 혼용, 주택담보대출 혼동.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CITY_VARS = {"price_index", "rent_index", "price_level", "rent_month", "price_sqm", "rent_sqm_month", "hh_income",
             "earnings", "rent_month_cash"}
LEVEL_VARS = {"price_level", "rent_month", "rent_month_cash", "price_sqm", "rent_sqm_month"}
# 대략적인 타당 범위 (USD, 연) — 벗어나면 단위 배율 오류 의심 (값은 고치지 않고 경고)
USD_RANGE = {"price_level": (3e4, 1e7), "rent_month": (150, 2e4), "hh_income": (5e3, 6e5), "earnings": (3e3, 4e5),
             "price_sqm": (500, 1e5)}
METRIC_RANGE = {"PTR": (5, 100), "PIR_hh": (1, 80), "PIR_earn": (1, 150), "RTI_hh": (3, 120), "RTI_earn": (3, 200),
                "gross_yield": (1, 20)}


def run(ctx, log):
    flags = []

    def add(check, severity, target, detail):
        flags.append({"check": check, "severity": severity, "target": target, "detail": detail})

    obs = pd.read_parquet(ctx.interim / "observations_long.parquet")
    dup = obs.duplicated(["series_id", "country_code", "period"], keep=False)
    for sid, g in obs[dup].groupby("series_id"):
        add("중복 키", "error", sid, f"{g['period'].nunique()}개 시점 중복")
    nonpos = obs[(obs["value"] <= 0) & ~obs["variable"].isin(["conversion_rate"]) & ~obs["variable"].str.contains("yoy")]
    for sid, g in nonpos.groupby("series_id"):
        add("0·음수 값", "warning", sid, f"{len(g)}개 (예: {g['period'].iloc[0]} = {g['value'].iloc[0]})")
    # 비정상 도약: 월·분기 지수/수준의 한 기간 변화 > 25%
    for sid, g in obs[obs["frequency"].isin(["M", "Q"]) & obs["variable"].isin(CITY_VARS | {"price_index_national"})].groupby("series_id"):
        s = g.sort_values("period")["value"].reset_index(drop=True)
        ch = s.pct_change().abs()
        big = ch[ch > 0.25]
        if len(big):
            per = g.sort_values("period")["period"].reset_index(drop=True)
            add("비정상 도약", "warning", sid, f"{len(big)}회, 최대 {big.max() * 100:.0f}% ({per[big.idxmax()]}) — 원자료 대조 필요")
    # 지역 범위: 도시 변수인데 geography_type 이 country
    bad = obs[obs["variable"].isin(CITY_VARS) & (obs["geography_type"] == "country")]
    for sid in bad["series_id"].unique():
        add("국가/도시 혼용", "error", sid, "도시 변수에 국가 범위 계열")
    # 수준 변수의 면적 기준 누락
    lv_obs = obs[obs["variable"].isin(LEVEL_VARS)]
    for sid in lv_obs[lv_obs["area_basis"].fillna("") == ""]["series_id"].unique():
        add("면적 기준 누락", "warning", sid, "area_basis 비어 있음")
    # 공표일 기록
    for sid, g in obs.groupby("series_id"):
        if (g["release_date"].fillna("").astype(str).isin(["", "nan"])).all():
            add("공표일 미기록", "info", sid, "원자료에 관측별 공표일이 없음 — retrieved_at 으로 시점 통제")
    # 주택담보대출 혼동 방지
    if (obs["variable"] == "mortgage_to_gdp").any():
        add("변수 정의", "info", "mortgage_to_gdp", "주택담보대출/GDP 계열 존재")
    hh = obs[obs["variable"] == "household_credit_to_gdp"]
    if len(hh):
        add("변수 정의", "info", "bis_hh_credit", "가계신용 전체(주택담보대출 아님) — mortgage_to_gdp 로 쓰지 않음")

    # 지표 단계 산출물이 있으면 범위 검사
    lvp = ctx.processed / "city_level_metrics.csv"
    if lvp.exists():
        lv = pd.read_csv(lvp)
        for var, (lo, hi) in USD_RANGE.items():
            g = lv[lv["metric"] == f"{var}_usd"]
            out = g[(g["value"] < lo) | (g["value"] > hi)]
            for _, r in out.iterrows():
                add("단위 배율", "warning", f"{r['city_id']} {r['year']} {var}", f"USD {r['value']:,.0f} — 범위 {lo:,.0f}~{hi:,.0f} 밖")
        for m, (lo, hi) in METRIC_RANGE.items():
            g = lv[lv["metric"] == m]
            out = g[(g["value"] < lo) | (g["value"] > hi)]
            for _, r in out.iterrows():
                add("월/연 환산·범위", "warning", f"{r['city_id']} {r['year']} {m}", f"{r['value']:.2f} — 범위 {lo}~{hi} 밖")
        # PTR 과 수익률의 역수 관계
        a = lv[lv["metric"] == "PTR"].set_index(["city_id", "year"])["value"]
        b = lv[lv["metric"] == "gross_yield"].set_index(["city_id", "year"])["value"]
        j = pd.concat([a, b], axis=1, keys=["ptr", "y"]).dropna()
        err = (j["ptr"] * j["y"] / 100 - 1).abs()
        if (err > 1e-9).any():
            add("PTR·수익률 역수", "error", "city_level_metrics", f"{(err > 1e-9).sum()}행 불일치")
        else:
            add("PTR·수익률 역수", "ok", "city_level_metrics", f"{len(j)}행 일치")
        for _, r in lv[lv["quality_flag"] == "C"].drop_duplicates(["city_id", "metric"]).iterrows():
            if r["metric"] in METRIC_RANGE:
                add("품질 C 지표", "info", f"{r['city_id']} {r['metric']}", str(r.get("notes", ""))[:200])

    out = pd.DataFrame(flags)
    ctx.processed.mkdir(parents=True, exist_ok=True)
    out.to_csv(ctx.processed / "quality_flags.csv", index=False, encoding="utf-8-sig")
    n_err = int((out["severity"] == "error").sum()) if len(out) else 0
    log(f"  검증 {len(out)}건 (error {n_err}, warning {int((out['severity'] == 'warning').sum()) if len(out) else 0})")
    return out
