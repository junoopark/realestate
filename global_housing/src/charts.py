"""도표 (outputs/charts/*.png). 서울을 강조색, 다른 도시는 중립 회색으로 둔다(색 = 서울 여부, 순위 아님).
품질 C 지표는 빗금으로 표시한다. 선택 합성지수는 별도 도표.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e2dc"
SEOUL, OTHER, ALT = "#2a78d6", "#b8b6ae", "#eb6834"

from matplotlib import font_manager  # noqa: E402

_AVAILABLE = {f.name for f in font_manager.fontManager.ttflist}
_FONTS = [f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR") if f in _AVAILABLE] + ["DejaVu Sans"]

plt.rcParams.update({
    "font.family": _FONTS,
    "axes.unicode_minus": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9.5,
})

SHORT = {
    "household_gross_current_income_mean": "가구 세전 평균",
    "household_gross_current_income_median_ESTIMATE": "가구 세전 중위(추정)",
    "household_gross_cash_income_median": "가구 세전 중위",
    "household_gross_money_income_median": "가구 세전 중위",
    "household_employment_income_incl_employer_cpf_median_employed_households": "취업가구 근로소득 중위",
    "economic_family_and_unattached_total_income_median": "경제가족 총소득 중위",
    "household_gross_total_income_median": "가구 총소득 중위",
    "employee_regular_monthly_wage_mean_x12": "상용근로자 평균",
    "employee_fulltime_annual_gross_median": "상근 중위",
    "employed_persons_monthly_earnings_median_x12": "취업자 중위",
    "employee_fulltime_monthly_income_incl_employer_cpf_median_x12": "상근 중위(CPF 포함)",
}


def _name(ctx, cid):
    return ctx.cities.get(cid, {}).get("name_ko", cid)


def _bars(ax, df, ctx, fmt, title, xlabel):
    df = df.sort_values("value")
    y = np.arange(len(df))
    colors = [SEOUL if c == "seoul" else OTHER for c in df["city_id"]]
    hatches = ["////" if q == "C" else "" for q in df["quality_flag"]]
    for i, (v, c, h) in enumerate(zip(df["value"], colors, hatches)):
        ax.barh(i, v, color=c, height=0.62, hatch=h, edgecolor=SURFACE if not h else "#7d7b74", linewidth=0)
    labels = [f"{_name(ctx, c)} ({int(yr)})" for c, yr in zip(df["city_id"], df["year"])]
    ax.set_yticks(y, labels)
    for i, (v, ic) in enumerate(zip(df["value"], df.get("income_concept", pd.Series([""] * len(df))).fillna(""))):
        tag = SHORT.get(ic, "")
        ax.text(v, i, f"  {fmt(v)}" + (f"  · {tag}" if tag else ""), va="center", fontsize=8.3, color=INK)
    ax.set_title(title, loc="left", fontsize=10.5, color=INK)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, df["value"].max() * 1.55 if len(df) else 1)


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run(ctx, log):
    proc, out = ctx.processed, ctx.outputs / "charts"
    out.mkdir(parents=True, exist_ok=True)
    la = pd.read_csv(proc / "city_latest_available.csv")
    made = []

    # 1. 소득 대비 임대료 (최신 시점)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2))
    for ax, (m, alt, title) in zip(axes, [("RTI_hh", "RTI_hh_est", "가구소득 대비 연 임대료 (%)"),
                                          ("RTI_earn", None, "근로자 1인 소득 대비 연 임대료 (%)")]):
        d = la[la["metric"] == m].copy()
        if alt:
            e = la[la["metric"] == alt].copy()
            e["city_id"] = e["city_id"]
            e["quality_flag"] = "C"
            d = pd.concat([d, e.assign(city_id=e["city_id"] + "_est")])
        d["city_id"] = d["city_id"].astype(str)
        _bars(ax, d.assign(city_id=d["city_id"].str.replace("_est", "", regex=False)), ctx, lambda v: f"{v:.0f}%", title,
              "12 × 월 임대료 ÷ 연소득 × 100")
    fig.suptitle("소득 개념이 도시마다 달라 막대 길이를 순위로 읽지 않는다 (빗금 = 품질 C·추정)", x=0.01, ha="left",
                 fontsize=8.5, color=INK2)
    _save(fig, out / "rent_to_income.png")
    made.append("rent_to_income.png")

    # 2. PTR · PIR
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.0))
    for ax, (m, title, fmt) in zip(axes, [("PTR", "가격 / 연 임대료 (년)", lambda v: f"{v:.1f}년"),
                                          ("PIR_hh", "가격 / 가구 연소득 (년)", lambda v: f"{v:.1f}년"),
                                          ("PIR_earn", "가격 / 근로자 연소득 (년)", lambda v: f"{v:.1f}년")]):
        _bars(ax, la[la["metric"] == m].copy(), ctx, fmt, title, "년")
    _save(fig, out / "level_ptr_pir.png")
    made.append("level_ptr_pir.png")

    # 3. 실질 5년 변화
    ps = pd.read_csv(proc / "path_summary.csv")
    if "real_cum_5y_pct" in ps:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=False)
        for ax, (lab, title) in zip(axes, [("price", "실질 주택가격 5년 누적 변화 (%)"), ("rent", "실질 임대료 5년 누적 변화 (%)")]):
            d = ps[(ps["series"] == lab)].dropna(subset=["real_cum_5y_pct"]).copy()
            d = d.rename(columns={"real_cum_5y_pct": "value", "last_year": "year"})
            d = d.sort_values("value")
            yy = np.arange(len(d))
            ax.barh(yy, d["value"], color=[SEOUL if c == "seoul" else OTHER for c in d["city_id"]], height=0.62,
                    hatch=None)
            ax.axvline(0, color=INK2, linewidth=0.8)
            ax.set_yticks(yy, [f"{_name(ctx, c)} ({int(a) - 5}→{int(a)})" for c, a in zip(d["city_id"], d["year"])])
            for i, v in enumerate(d["value"]):
                ax.text(v, i, f" {v:+.1f}%" if v >= 0 else f"{v:+.1f}% ", va="center", ha="left" if v >= 0 else "right",
                        fontsize=8.3, color=INK)
            ax.set_title(title, loc="left", fontsize=10.5, color=INK)
            ax.grid(axis="y", visible=False)
            lim = max(abs(d["value"]).max() * 1.35, 5) if len(d) else 5
            ax.set_xlim(-lim, lim)
        _save(fig, out / "real_change_5y.png")
        made.append("real_change_5y.png")

    # 4. 기준연도 이후 가격/임대료 경로
    panel = pd.read_parquet(proc / "city_panel_annual.parquet")
    meta = json.loads((proc / "run_meta.json").read_text(encoding="utf-8"))
    rel = panel[panel["variable"] == "rel_PTR"]
    if len(rel):
        start = int(meta["base_year"]) - 7
        rel = rel[rel["year"] >= start]
        fig, ax = plt.subplots(figsize=(10, 5.4))
        ends = []
        for cid, g in rel.groupby("city_id"):
            g = g.sort_values("year")
            is_s = cid == "seoul"
            ax.plot(g["year"], g["value"], color=SEOUL if is_s else OTHER, linewidth=2.4 if is_s else 1.4, zorder=3 if is_s else 2)
            ends.append([g["value"].iloc[-1], g["year"].iloc[-1], cid])
        # 끝 라벨 겹침 방지: 값 순으로 정렬해 최소 간격을 둔다
        ends.sort()
        span = rel["value"].max() - rel["value"].min()
        gap = span * 0.045
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
        for v, yr, cid in ends:
            ax.text(yr + 0.2, v, _name(ctx, cid), fontsize=8, color=INK if cid == "seoul" else INK2, va="center")
        ax.set_xlim(start - 0.3, rel["year"].max() + 1.6)
        ax.axhline(100, color=INK2, linewidth=0.8)
        ax.set_title(f"가격지수 / 임대료지수 (기준연도 {meta['base_year']} = 100) — 100 위면 기준연도 이후 가격이 임대료보다 더 올랐다는 뜻",
                     loc="left", fontsize=10, color=INK)
        ax.set_xlabel("연도")
        _save(fig, out / "price_rent_path.png")
        made.append("price_rent_path.png")

    # 5. 서울 보증금 환산 민감도
    dep = pd.read_csv(proc / "seoul_deposit.csv")
    d = dep[(dep["contracts"] == "월세(보증부 포함), 전체")]
    if len(d):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
        for i, (y, g) in enumerate(d.groupby("year")):
            g = g.sort_values("rate_pct")
            col = [SEOUL, ALT][i % 2]
            axes[0].plot(g["rate_pct"], g["converted_rent_60"] / 1e4, marker="o", color=col, linewidth=2, label=str(y))
            if "RTI_hh_pct" in g and g["RTI_hh_pct"].notna().any():
                axes[1].plot(g["rate_pct"], g["RTI_hh_pct"], marker="o", color=col, linewidth=2, label=f"{y} 가구 평균소득")
            if "RTI_earn_pct" in g and g["RTI_earn_pct"].notna().any():
                axes[1].plot(g["rate_pct"], g["RTI_earn_pct"], marker="s", color=col, linewidth=1.4, linestyle="--",
                             label=f"{y} 상용근로자")
            base = g[g["rate_label"].str.startswith("기준(")]
            if len(base):
                axes[0].annotate(f"기준 {base['rate_pct'].iloc[0]:.2f}%", (base["rate_pct"].iloc[0], base["converted_rent_60"].iloc[0] / 1e4),
                                 textcoords="offset points", xytext=(6, -12 - 12 * i), fontsize=8, color=INK2)
        axes[0].set_title("60㎡ 환산 월 임대료 (만원) = 월세 + 보증금 × 환산율 / 12", loc="left", fontsize=10, color=INK)
        axes[0].set_xlabel("연 환산율 (%)")
        axes[1].set_title("연 환산 임대료 / 연소득 (%)", loc="left", fontsize=10, color=INK)
        axes[1].set_xlabel("연 환산율 (%)")
        for ax in axes:
            ax.legend(frameon=False, fontsize=8)
        _save(fig, out / "seoul_deposit_sensitivity.png")
        made.append("seoul_deposit_sensitivity.png")

    # 6. 자료 커버리지
    from .export import coverage

    c = coverage(ctx)
    if len(c):
        keep = ["price_level", "price_sqm", "rent_month", "hh_income", "earnings", "price_index", "rent_index",
                "price_index_national"]
        c = c[c["variable"].isin(keep)]
        piv = c.pivot_table(index="city_id", columns="variable", values="n_years_complete", aggfunc="max").fillna(0)
        piv = piv.reindex(columns=[k for k in keep if k in piv.columns])
        order = [k for k in ctx.cities if k in piv.index]
        piv = piv.reindex(order)
        fig, ax = plt.subplots(figsize=(max(8, 1.0 * piv.shape[1] + 3), 0.45 * len(piv) + 1.8))
        vmax = max(20, piv.values.max())
        ax.imshow(piv.values, cmap="Blues", aspect="auto", vmin=0, vmax=vmax)
        ax.set_xticks(range(piv.shape[1]), piv.columns, rotation=40, ha="right")
        ax.set_yticks(range(len(piv)), [_name(ctx, k) for k in piv.index])
        for i in range(piv.shape[0]):
            for j in range(piv.shape[1]):
                v = piv.values[i, j]
                ax.text(j, i, "–" if v == 0 else f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if v > 0.55 * vmax else INK)
        ax.grid(False)
        ax.set_title("핵심 변수별 완전한 연간 관측 연수 (– = 미확보, 전체 목록은 coverage_matrix.xlsx)", loc="left",
                     fontsize=10, color=INK)
        _save(fig, out / "coverage.png")
        made.append("coverage.png")

    # 7. 선택 산출물: 가격괴리 3항목 (합성지수와 별도)
    comp = pd.read_csv(proc / "composite_optional.csv")
    if len(comp) and comp["price_gap_3item"].notna().any():
        d = comp.dropna(subset=["price_gap_3item"]).rename(columns={"price_gap_3item": "value", "last_year": "year"})
        d["quality_flag"] = "B"
        fig, ax = plt.subplots(figsize=(7.5, 0.5 * len(d) + 1.8))
        _bars(ax, d, ctx, lambda v: f"{v:+.2f}", "가격괴리 3항목 (도시별 자기 과거 10년 대비 z 평균, 선택 산출물)", "z")
        ax.set_xlim(min(0, d["value"].min() * 1.6), max(0.5, d["value"].max() * 1.6))
        _save(fig, out / "composite_optional_price_gap.png")
        made.append("composite_optional_price_gap.png")
    log(f"  도표 {len(made)}개 → outputs/charts/")
