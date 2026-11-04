"""지표 계산 (설계서 5·6절).

입력: data/interim/observations_long.parquet
출력(data/processed):
  annual_series.csv            계열별 연간값(월·분기 평균, 완전한 해만 지표에 사용)
  city_level_metrics.csv       도시·연도별 수준 지표 (PIR·PTR·수익률·소득 대비 임대료, USD·PPP 환산)
  city_latest_common_year.csv  공통연도 비교표
  city_latest_available.csv    도시별 최신 시점 (구성요소가 같은 해에 모두 있는 마지막 해)
  city_panel_annual.parquet    연간 패널(원계열 + 파생지표, 추적 가능한 long)
  path_summary.csv             실질 가격·임대료·소득 5년/10년 변화, 상대 PTR·PIR, 도시 집중도
  seoul_deposit.csv            서울 보증금 환산 민감도
  composite_optional.csv       선택 합성지수(본 프로젝트 규칙) — 구성요소가 빠지면 NA
  run_meta.json                기준연도·공통연도 선택 근거
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

ROLES = {
    "P": "price_level", "R": "rent_month", "R_cash": "rent_month_cash", "Y_hh": "hh_income", "Y_earn": "earnings",
    "PI": "price_index", "RI": "rent_index", "PIN": "price_index_national", "P_sqm": "price_sqm",
    "R_sqm": "rent_sqm_month", "RTI_off": "rent_to_income_official", "Y_renter": "hh_income_renter",
    "R_stock": "rent_month_stock", "DEP": "deposit_level", "Y_hh_est": "hh_income_median_est",
}
NEED = {"M": 12, "Q": 4, "A": 1}
FLAG_ORDER = {"A": 0, "B": 1, "C": 2}


def worst(*flags):
    fl = [f for f in flags if isinstance(f, str) and f in FLAG_ORDER]
    return max(fl, key=FLAG_ORDER.get) if fl else ""


# ── 1. 연간화 ───────────────────────────────────────────────────────
def annualize(obs: pd.DataFrame, as_of_year: int | None = None) -> pd.DataFrame:
    obs = obs.copy()
    obs["year"] = obs["period"].astype(str).str[:4].astype(int)
    keys = ["series_id", "country_code", "year"]
    meta_cols = ["city_id", "variable", "frequency", "unit", "currency", "geography_name", "dwelling_type", "tenure_type",
                 "area_basis", "income_concept", "source_id", "quality_flag", "method", "price_basis"]
    rows = []
    for (sid, cc, y), g in obs.groupby(keys, sort=False):
        freq = g["frequency"].iloc[0]
        if g["variable"].iloc[0] == "household_credit_to_gdp":  # 연말(4분기) 값
            q4 = g[g["period"].str.endswith("Q4")]
            val, n, complete = (q4["value"].iloc[-1], 1, True) if len(q4) else (g["value"].iloc[-1], len(g), False)
        else:
            n = g["period"].nunique()
            val, complete = g["value"].mean(), n >= NEED.get(freq, 1)
            if freq == "A" and as_of_year is not None and y >= as_of_year:
                complete = False  # 진행 중인 해(건별 자료의 연간 집계·연중 갱신 통계)는 완전한 연간값이 아니다
        r = {"series_id": sid, "country_code": cc, "year": y, "value": val, "n_periods": n, "complete": complete}
        for c in meta_cols:
            r[c] = g[c].iloc[0]
        r["notes"] = "; ".join(sorted(set(x for x in g["notes"].astype(str) if x and x != "nan")))[:300]
        rows.append(r)
    return pd.DataFrame(rows)


# ── 2. 도시·연도별 역할 값 ─────────────────────────────────────────
def city_roles(ann: pd.DataFrame, cities: dict) -> dict:
    """{city_id: {role: DataFrame(year, value, series_id, quality_flag, ...)}} — 완전한 해만."""
    out = {}
    full = ann[ann["complete"]]
    for cid in cities:
        sub = full[full["city_id"] == cid]
        roles = {}
        for role, var in ROLES.items():
            g = sub[sub["variable"] == var]
            if g["series_id"].nunique() > 1:
                raise ValueError(f"{cid}: 변수 {var} 에 계열이 둘 이상 {g['series_id'].unique()} — series.yaml 에서 하나만 지정")
            if len(g):
                roles[role] = g.set_index("year")
        out[cid] = roles
    return out


def national(ann: pd.DataFrame, var: str) -> pd.DataFrame:
    g = ann[(ann["city_id"] == "_national") & (ann["variable"] == var) & ann["complete"]]
    return g.set_index(["country_code", "year"])["value"]


# ── 3. 수준 지표 ────────────────────────────────────────────────────
LEVEL_METRICS = {
    # 이름: (분자 역할, 분모 역할, 계산식, 단위, 설명)
    "PIR_hh": ("P", "Y_hh", lambda p, y: p / y, "years", "가격 / 가구 연소득"),
    "PIR_earn": ("P", "Y_earn", lambda p, y: p / y, "years", "가격 / 근로자 연소득"),
    "PTR": ("P", "R", lambda p, r: p / (12 * r), "years", "가격 / (12 × 월 임대료)"),
    "gross_yield": ("R", "P", lambda r, p: 12 * r / p * 100, "pct", "12 × 월 임대료 / 가격 × 100 (비용·공실·세금 차감 전)"),
    "RTI_hh": ("R", "Y_hh", lambda r, y: 12 * r / y * 100, "pct", "12 × 월 임대료 / 가구 연소득 × 100"),
    "RTI_earn": ("R", "Y_earn", lambda r, y: 12 * r / y * 100, "pct", "12 × 월 임대료 / 근로자 연소득 × 100"),
    "RTI_cash_hh": ("R_cash", "Y_hh", lambda r, y: 12 * r / y * 100, "pct", "서울: 현금 월세(보증금 환산 전) 기준"),
    "RTI_cash_earn": ("R_cash", "Y_earn", lambda r, y: 12 * r / y * 100, "pct", "서울: 현금 월세 기준"),
    "RTI_renter_hh": ("R_stock", "Y_renter", lambda r, y: 12 * r / y * 100, "pct", "미국: 기존 임차가구 중위 총임대료 / 임차가구 중위소득"),
    "PIR_hh_est": ("P", "Y_hh_est", lambda p, y: p / y, "years", "서울 보조: 가격 / 추정 중위 가구소득"),
    "RTI_hh_est": ("R", "Y_hh_est", lambda r, y: 12 * r / y * 100, "pct", "서울 보조: 12 × 월 임대료 / 추정 중위 가구소득"),
    "RTI_cash_hh_est": ("R_cash", "Y_hh_est", lambda r, y: 12 * r / y * 100, "pct", "서울 보조: 현금 월세 / 추정 중위 가구소득"),
}


def level_metrics(roles: dict, ann: pd.DataFrame, cities: dict) -> pd.DataFrame:
    fx = national(ann, "fx_usd")
    ppp = national(ann, "ppp_private")
    rows = []
    for cid, rr in roles.items():
        cc = cities[cid]["country_code"]
        years = sorted(set().union(*[set(df.index) for df in rr.values()])) if rr else []
        for y in years:
            def get(role):
                df = rr.get(role)
                if df is None or y not in df.index:
                    return None
                return df.loc[y]
            base = {"city_id": cid, "country_code": cc, "year": y}
            for name, (a, b, fn, unit, desc) in LEVEL_METRICS.items():
                ra, rb = get(a), get(b)
                if ra is None or rb is None:
                    continue
                v = fn(ra["value"], rb["value"])
                q = worst(ra["quality_flag"], rb["quality_flag"])
                note = []
                housing = {"P", "R", "R_cash"}
                if a in housing and b in housing:
                    if ra["dwelling_type"] != rb["dwelling_type"]:
                        note.append(f"주택유형 불일치: {ra['dwelling_type']} vs {rb['dwelling_type']}")
                        q = worst(q, "C")
                    if ra["area_basis"] != rb["area_basis"]:
                        note.append(f"면적기준: {ra['area_basis']} / {rb['area_basis']}")
                    note.append("매매 대표값과 임대 대표값의 비율 — 같은 주택의 수익률이 아님")
                rows.append({**base, "metric": name, "value": v, "unit": unit, "definition": desc,
                             "numerator_series": ra["series_id"], "denominator_series": rb["series_id"],
                             "income_concept": rb["income_concept"] if b.startswith("Y") else "",
                             "dwelling_type": ra["dwelling_type"] if a in housing else rb["dwelling_type"],
                             "quality_flag": q, "notes": "; ".join(note)})
            # 단위면적·통화 환산
            for role, label in (("P", "price_level"), ("R", "rent_month"), ("P_sqm", "price_sqm"), ("R_sqm", "rent_sqm_month"),
                                ("Y_hh", "hh_income"), ("Y_earn", "earnings")):
                r0 = get(role)
                if r0 is None:
                    continue
                f = fx.get((cc, y))
                p = ppp.get((cc, y))
                rows.append({**base, "metric": f"{label}_local", "value": r0["value"], "unit": r0["unit"],
                             "definition": "현지통화", "numerator_series": r0["series_id"], "denominator_series": "",
                             "income_concept": r0["income_concept"], "quality_flag": r0["quality_flag"], "notes": r0["area_basis"]})
                if f is not None and not np.isnan(f):
                    rows.append({**base, "metric": f"{label}_usd", "value": r0["value"] / f, "unit": "USD",
                                 "definition": "시장환율(연평균) USD 환산", "numerator_series": r0["series_id"],
                                 "denominator_series": "wb_fx", "income_concept": r0["income_concept"],
                                 "quality_flag": r0["quality_flag"], "notes": ""})
                if p is not None and not np.isnan(p):
                    rows.append({**base, "metric": f"{label}_ppp", "value": r0["value"] / p, "unit": "intl$",
                                 "definition": "민간소비 PPP 환산(보조, 도시 주거 구매력 조정 아님)", "numerator_series": r0["series_id"],
                                 "denominator_series": "wb_ppp", "income_concept": r0["income_concept"],
                                 "quality_flag": r0["quality_flag"], "notes": ""})
            r_off = get("RTI_off")
            if r_off is not None:
                rows.append({**base, "metric": "RTI_official", "value": r_off["value"], "unit": "pct",
                             "definition": "공식 통계의 임차가구 소득 대비 임대료 비율(중위)", "numerator_series": r_off["series_id"],
                             "denominator_series": "", "income_concept": r_off["income_concept"],
                             "quality_flag": r_off["quality_flag"], "notes": ""})
    return pd.DataFrame(rows)


CORE = ["PTR", "gross_yield", "PIR_hh", "RTI_hh", "PIR_earn", "RTI_earn"]


def choose_common_year(lv: pd.DataFrame, as_of_year: int) -> tuple[int, dict]:
    """도시 수가 가장 많은 해(동률이면 최근). 서울이 빠진 해는 고르지 않는다."""
    scores = {}
    for y in range(as_of_year - 6, as_of_year):
        g = lv[(lv["year"] == y) & lv["metric"].isin(["PTR", "RTI_hh", "RTI_earn"])]
        cities = set(g["city_id"])
        if "seoul" not in cities:
            continue
        scores[y] = len(cities)
    if not scores:
        return as_of_year - 2, {}
    best = max(scores, key=lambda y: (scores[y], y))
    return best, scores


def latest_available(lv: pd.DataFrame) -> pd.DataFrame:
    g = lv[lv["metric"].isin(CORE + ["RTI_cash_hh", "RTI_cash_earn", "RTI_official", "RTI_renter_hh", "PIR_hh_est",
                                     "RTI_hh_est", "RTI_cash_hh_est"])]
    idx = g.groupby(["city_id", "metric"])["year"].idxmax()
    return g.loc[idx].sort_values(["metric", "city_id"])


# ── 4. 경로 (설계서 5.2) ───────────────────────────────────────────
def rebase(s: pd.Series, b: int) -> pd.Series:
    return s / s.loc[b] * 100 if b in s.index and s.loc[b] else s * np.nan


def choose_base_year(roles: dict, candidates: list[int], min_years: int = 10) -> tuple[int, str]:
    """가격·임대 지수가 모두 min_years 이상인 도시가 전부 관측된 첫 후보 연도. 짧은 계열 도시는 판정에서 빼고 이유에 적는다."""
    have = [c for c, rr in roles.items() if "PI" in rr and "RI" in rr]
    short = [c for c in have if min(len(roles[c]["PI"]), len(roles[c]["RI"])) < min_years]
    elig = [c for c in have if c not in short]
    note_short = f"; 지수 이력이 {min_years}년 미만이라 판정에서 뺀 도시: {', '.join(short)}" if short else ""
    failed = []
    for b in candidates:
        miss = [c for c in elig if b not in roles[c]["PI"].index or b not in roles[c]["RI"].index]
        if elig and not miss:
            why = f" (앞선 후보: {'; '.join(failed)})" if failed else ""
            return b, f"{b}년: 가격·임대 지수가 있는 {len(elig)}개 도시 모두 완전한 연간 관측{why}{note_short}"
        failed.append(f"{b}년은 {', '.join(miss)} 미관측")
    b = candidates[-1]
    return b, f"후보 {candidates} 중 모든 도시가 관측된 해가 없어 {b}년 사용 ({'; '.join(failed)}){note_short}"


def paths(roles: dict, ann: pd.DataFrame, cities: dict, base: int, min_years: int):
    cpi = national(ann, "cpi")
    bis_rpp = national(ann, "price_index_national_bis")
    credit = national(ann, "household_credit_to_gdp")
    panel, summary = [], []
    for cid, rr in roles.items():
        cc = cities[cid]["country_code"]
        cpi_c = cpi.xs(cc, level=0) if cc in cpi.index.get_level_values(0) else pd.Series(dtype=float)
        series = {}
        for role, label in (("PI", "price"), ("RI", "rent"), ("Y_hh", "income_hh"), ("Y_earn", "income_earn"), ("PIN", "price_national")):
            if role in rr:
                s = rr[role]["value"].sort_index()
                series[label] = (s, rr[role]["series_id"].iloc[0], rr[role]["quality_flag"].iloc[0])
        if "price_national" not in series and not cities[cid].get("city_equals_country") and cc in bis_rpp.index.get_level_values(0):
            s = bis_rpp.xs(cc, level=0).sort_index()
            series["price_national"] = (s, "bis_rpp", "B")
        for label, (s, sid, q) in series.items():
            for y, v in s.items():
                panel.append({"city_id": cid, "year": y, "variable": f"{label}_nominal", "value": v, "series_id": sid,
                              "quality_flag": q, "base_year": ""})
            rb = rebase(s, base)
            real = (s / cpi_c.reindex(s.index)) if len(cpi_c) else s * np.nan
            real_b = rebase(real.dropna(), base) if len(real.dropna()) else real
            for y, v in rb.dropna().items():
                panel.append({"city_id": cid, "year": y, "variable": f"{label}_index_b", "value": v, "series_id": sid,
                              "quality_flag": q, "base_year": base})
            for y, v in real_b.dropna().items():
                panel.append({"city_id": cid, "year": y, "variable": f"{label}_real_index_b", "value": v,
                              "series_id": f"{sid} / CPI({cc})", "quality_flag": q, "base_year": base})
            yoy = real.dropna().pct_change() * 100
            for y, v in yoy.dropna().items():
                panel.append({"city_id": cid, "year": y, "variable": f"{label}_real_yoy", "value": v,
                              "series_id": f"{sid} / CPI({cc})", "quality_flag": q, "base_year": ""})
        # 상대 PTR·PIR·도시 집중도 (기준연도 = 100)
        rel = {}
        if "price" in series and "rent" in series:
            rel["rel_PTR"] = (series["price"][0] / series["rent"][0], series["price"][2], series["rent"][2])
        inc = "income_hh" if "income_hh" in series and len(series["income_hh"][0]) >= min_years else (
            "income_earn" if "income_earn" in series else ("income_hh" if "income_hh" in series else None))
        if "price" in series and inc:
            rel["rel_PIR"] = (series["price"][0] / series[inc][0], series["price"][2], series[inc][2])
        if "price" in series and "price_national" in series and not cities[cid].get("city_equals_country"):
            rel["city_to_country"] = (series["price"][0] / series["price_national"][0], series["price"][2],
                                      series["price_national"][2])
        for name, (ratio, q1, q2) in rel.items():
            ratio = ratio.dropna()
            for y, v in rebase(ratio, base).dropna().items():
                panel.append({"city_id": cid, "year": y, "variable": name, "value": v,
                              "series_id": f"{name}({'income=' + inc if name == 'rel_PIR' else ''})", "quality_flag": worst(q1, q2),
                              "base_year": base})
        if cc in credit.index.get_level_values(0):
            cr = credit.xs(cc, level=0).sort_index()
            for y, v in cr.items():
                panel.append({"city_id": cid, "year": y, "variable": "household_credit_to_gdp", "value": v,
                              "series_id": "bis_hh_credit", "quality_flag": "B", "base_year": ""})
        # 요약: 최근 연도 기준 5·10년 누적 변화와 CAGR (실질)
        for label in ("price", "rent", "income_hh", "income_earn"):
            if label not in series:
                continue
            s, sid, q = series[label]
            real = (s / cpi_c.reindex(s.index)).dropna() if len(cpi_c) else pd.Series(dtype=float)
            if real.empty:
                continue
            t = real.index.max()
            row = {"city_id": cid, "series": label, "series_id": sid, "quality_flag": q, "last_year": t,
                   "first_year": real.index.min(), "n_years": len(real)}
            for k in (5, 10):
                if t - k in real.index:
                    ratio = real.loc[t] / real.loc[t - k]
                    row[f"real_cum_{k}y_pct"] = (ratio - 1) * 100
                    row[f"real_cagr_{k}y_pct"] = (ratio ** (1 / k) - 1) * 100
            summary.append(row)
    return pd.DataFrame(panel), pd.DataFrame(summary)


# ── 5. 서울 보증금 민감도 (설계서 5.3) ────────────────────────────
def seoul_deposit(ctx, ann: pd.DataFrame, roles: dict) -> pd.DataFrame:
    path = ctx.interim / "seoul_rtms_rent_contracts.parquet"
    if not path.exists():
        return pd.DataFrame()
    c = pd.read_parquet(path)
    cfg = ctx.project.get("seoul_deposit", {})
    band_pp = float(cfg.get("band_pp", 1.0))
    scen = [float(x) for x in cfg.get("scenarios_pct", [2, 4, 6])]
    lo, hi = ctx.project["project"]["area_band_sqm"]
    target = ctx.project["project"]["target_area_sqm"]
    conv = ann[(ann["series_id"] == "seoul_conversion_rate") & ann["complete"]].set_index("year")["value"]
    rr = roles.get("seoul", {})
    P = rr.get("P")
    Yh, Ye = rr.get("Y_hh"), rr.get("Y_earn")
    rows = []
    band = c[(c["area"] >= lo) & (c["area"] <= hi)]
    for y, g in band.groupby("year"):
        y = int(y)
        base_rate = conv.get(y)
        rates = []
        if base_rate is not None:
            rates += [("기준(R-ONE 관측 전환율)", base_rate), ("기준 -1%p", base_rate - band_pp), ("기준 +1%p", base_rate + band_pp)]
        rates += [(f"시나리오 {s:.0f}%", s) for s in scen]
        groups = {"월세(보증부 포함), 전체": g[g["rent"] > 0], "월세, 신규": g[(g["rent"] > 0) & (g["contract_type"] == "신규")],
                  "월세, 갱신": g[(g["rent"] > 0) & (g["contract_type"] == "갱신")], "전세(보증금만)": g[g["rent"] == 0]}
        for gname, gg in groups.items():
            if gg.empty:
                continue
            for rname, rate in rates:
                conv_rent = ((gg["rent"] + gg["deposit"] * rate / 100 / 12) / gg["area"]).median() * target
                row = {"year": y, "contracts": gname, "n": len(gg), "rate_label": rname, "rate_pct": rate,
                       "cash_rent_60": (gg["rent"] / gg["area"]).median() * target,
                       "deposit_60": (gg["deposit"] / gg["area"]).median() * target,
                       "converted_rent_60": conv_rent}
                if P is not None and y in P.index:
                    row["PTR"] = P.loc[y, "value"] / (12 * conv_rent)
                    row["gross_yield_pct"] = 12 * conv_rent / P.loc[y, "value"] * 100
                if Yh is not None and y in Yh.index:
                    row["RTI_hh_pct"] = 12 * conv_rent / Yh.loc[y, "value"] * 100
                if Ye is not None and y in Ye.index:
                    row["RTI_earn_pct"] = 12 * conv_rent / Ye.loc[y, "value"] * 100
                rows.append(row)
    # 표본조사(R-ONE) 평균 기준: 평균(월세 + 보증금×r/12) = 평균 월세 + 평균 보증금 × r/12
    rm = ann[(ann["series_id"] == "seoul_rent_month_mean") & ann["complete"]].set_index("year")["value"]
    dm = ann[(ann["series_id"] == "seoul_deposit_mean") & ann["complete"]].set_index("year")["value"]
    for y in sorted(set(rm.index) & set(dm.index) & set(conv.index)):
        rows.append({"year": int(y), "contracts": "R-ONE 표본 평균(전체 면적)", "n": np.nan, "rate_label": "기준(R-ONE 관측 전환율)",
                     "rate_pct": conv[y], "cash_rent_60": np.nan, "deposit_60": np.nan,
                     "converted_rent_60": np.nan, "survey_mean_cash_rent": rm[y], "survey_mean_deposit": dm[y],
                     "survey_mean_converted_rent": rm[y] + dm[y] * conv[y] / 100 / 12})
    return pd.DataFrame(rows)


# ── 6. 선택 합성지수 (설계서 6.1) ──────────────────────────────────
def composite(panel: pd.DataFrame, cfg: dict, min_years: int) -> pd.DataFrame:
    if not cfg.get("enabled") or panel.empty:
        return pd.DataFrame()
    window = int(cfg.get("window_years", 10))
    k = int(cfg.get("change_years", 3))
    comps = {"price_to_income_rel": "rel_PIR", "price_to_rent_rel": "rel_PTR", "city_to_country_rel": "city_to_country"}
    rows = []
    for cid, g in panel.groupby("city_id"):
        z = {}
        info = {}
        for comp, var in comps.items():
            s = g[g["variable"] == var].set_index("year")["value"].sort_index()
            if len(s) < min_years:
                z[comp], info[comp] = np.nan, f"관측 {len(s)}년 < {min_years}"
                continue
            win = s.iloc[-window:]
            sd = win.std(ddof=1)
            z[comp] = (s.iloc[-1] - win.mean()) / sd if sd else np.nan
            info[comp] = f"{win.index.min()}~{win.index.max()} 평균 {win.mean():.1f}, 표준편차 {sd:.1f}, n={len(win)}"
        cr = g[g["variable"] == "household_credit_to_gdp"].set_index("year")["value"].sort_index()
        # 가계신용(주택담보대출 아님)의 k년 변화(%p) — 설계서 구성요소의 대체가 아니므로 별도 표시만
        credit_change = cr.iloc[-1] - cr.loc[cr.index.max() - k] if len(cr) and cr.index.max() - k in cr.index else np.nan
        full = np.nan  # 주택담보대출/GDP·건설투자/GDP 미확보 → 설계서 규칙 5: 전체 점수 NA
        three = [z[c] for c in comps]
        alt = np.mean(three) if all(not np.isnan(v) for v in three) else np.nan
        rows.append({"city_id": cid, "last_year": int(g["year"].max()), **{f"z_{c}": z[c] for c in comps},
                     **{f"basis_{c}": info[c] for c in comps},
                     "household_credit_to_gdp_change_pp": credit_change,
                     "composite_full": full,
                     "composite_full_note": "주택담보대출/GDP·건설투자/GDP 미확보 → NA (가중치 재배분 안 함)",
                     "price_gap_3item": alt,
                     "price_gap_3item_note": "가격괴리 3항목(상대 PIR·PTR·도시/전국) 도시별 자기 과거 대비 z 평균 — 합성지수와 다른 지표"})
    return pd.DataFrame(rows)


# ── 실행 ────────────────────────────────────────────────────────────
def run(ctx, log):
    obs = pd.read_parquet(ctx.interim / "observations_long.parquet")
    as_of_year = int(ctx.as_of[:4])
    obs = obs[obs["period"].astype(str).str[:4].astype(int) <= as_of_year]
    ann = annualize(obs, as_of_year)
    proc = ctx.processed
    proc.mkdir(parents=True, exist_ok=True)
    ann.to_csv(proc / "annual_series.csv", index=False, encoding="utf-8-sig")

    roles = city_roles(ann, ctx.cities)
    lv = level_metrics(roles, ann, ctx.cities)
    lv.to_csv(proc / "city_level_metrics.csv", index=False, encoding="utf-8-sig")

    common, scores = choose_common_year(lv, as_of_year)
    cy = lv[(lv["year"] == common)]
    cy.to_csv(proc / "city_latest_common_year.csv", index=False, encoding="utf-8-sig")
    la = latest_available(lv)
    la.to_csv(proc / "city_latest_available.csv", index=False, encoding="utf-8-sig")

    pcfg = ctx.project["project"]
    base, base_reason = choose_base_year(roles, list(pcfg["base_year_candidates"]), int(pcfg["min_years_long_run"]))
    panel, summary = paths(roles, ann, ctx.cities, base, int(pcfg["min_years_long_run"]))
    # 패널에 원계열(연간)도 함께 — 추적용
    raw_panel = ann[ann["city_id"].isin(ctx.cities)][["city_id", "year", "variable", "value", "series_id", "quality_flag"]].copy()
    raw_panel["variable"] = "raw:" + raw_panel["variable"]
    raw_panel["base_year"] = ""
    full_panel = pd.concat([raw_panel, panel], ignore_index=True)
    full_panel["base_year"] = full_panel["base_year"].astype(str)
    full_panel.to_parquet(proc / "city_panel_annual.parquet", index=False)
    full_panel.to_csv(proc / "city_panel_annual.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(proc / "path_summary.csv", index=False, encoding="utf-8-sig")

    dep = seoul_deposit(ctx, ann, roles)
    dep.to_csv(proc / "seoul_deposit.csv", index=False, encoding="utf-8-sig")
    comp = composite(panel, ctx.project.get("composite", {}), int(pcfg["min_years_long_run"]))
    comp.to_csv(proc / "composite_optional.csv", index=False, encoding="utf-8-sig")

    meta = {"as_of": ctx.as_of, "common_year": common, "common_year_scores": scores, "base_year": base,
            "base_year_reason": base_reason, "n_level_rows": len(lv), "n_panel_rows": len(full_panel)}
    (proc / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"  공통연도 {common} (도시 수 {scores}), 기준연도 {base} — {base_reason}")
    log(f"  수준지표 {len(lv)}행, 패널 {len(full_panel)}행, 서울 보증금 {len(dep)}행")
    return meta
