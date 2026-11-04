"""한국어 보고서 (outputs/report_ko.md). 문장은 산출 표에서 계산한 값으로만 만든다.

서울 순위는 '비교 가능한 도시'(같은 지표·같은 소득 개념·품질 A/B)끼리만 말하고 표본 수를 함께 적는다.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .charts import SHORT
from .config import load_yaml


def fmt(v, d=1, suf=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    return f"{v:,.{d}f}{suf}"


def money(v, cur):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    if cur == "KRW":
        return f"{v / 1e4:,.0f}만원" if v < 1e8 else f"{v / 1e8:,.2f}억원"
    return f"{v:,.0f} {cur}"


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(자료 없음)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |")
    return "\n".join(lines) + "\n"


def rank_statement(df, metric_label, higher="높은", seoul="seoul"):
    """df: city_id, value (비교 가능한 집합). 서울 순위 문장."""
    df = df.dropna(subset=["value"]).sort_values("value", ascending=False).reset_index(drop=True)
    if seoul not in set(df["city_id"]) or len(df) < 2:
        return None
    k = int(df.index[df["city_id"] == seoul][0]) + 1
    pos = "가장" if k == 1 else f"{k}번째로"
    return f"{metric_label}은(는) 비교 가능한 {len(df)}개 도시 중 {pos} {higher} 값"


def run(ctx, log):
    proc, out = ctx.processed, ctx.outputs
    meta = json.loads((proc / "run_meta.json").read_text(encoding="utf-8"))
    lv = pd.read_csv(proc / "city_level_metrics.csv")
    la = pd.read_csv(proc / "city_latest_available.csv")
    ps = pd.read_csv(proc / "path_summary.csv")
    panel = pd.read_parquet(proc / "city_panel_annual.parquet")
    dep = pd.read_csv(proc / "seoul_deposit.csv")
    comp = pd.read_csv(proc / "composite_optional.csv")
    qf = pd.read_csv(proc / "quality_flags.csv")
    cat = pd.read_csv(out / "source_catalog.csv")
    gaps = load_yaml(ctx.root / "configs" / "gaps.yaml").get("gaps", [])
    name = {k: v["name_ko"] for k, v in ctx.cities.items()}
    cur = {k: v["currency"] for k, v in ctx.cities.items()}
    cy_year = int(meta["common_year"])
    L = []
    w = L.append

    w(f"# 서울 포함 글로벌 도시 주택시장 비교 — 렌트 부담 중심\n")
    w(f"기준일 {ctx.as_of} · 자동 생성(`python -m src.run`) · 공통연도 **{cy_year}** · 상대지수 기준연도 **{meta['base_year']}**\n")
    w("> 이 보고서의 수치는 `data/processed`·`outputs` 의 표에서 그대로 옮겼다. 확보하지 못한 값은 NA 로 두었고, "
      "UBS 위험등급·가중치·하락확률을 복제했다고 주장하지 않는다.\n")

    # 1
    w("## 1. 연구 질문과 범위\n")
    w("- 서울의 매매가격과 임대료가 해외 주요 도시 대비 어느 수준인가 (A: 현재 수준)")
    w("- 가격이 임대료·소득보다 빨리 올랐는가 (B: 과거 대비 변화, 기준연도=100 상대지수)")
    w("- 신용 확대·도시 집중이 동반되는가 (C: 보조 대시보드)")
    w(f"- 표본: {', '.join(name[c] for c in ctx.cities)} ({len(ctx.cities)}개 도시). "
      "UBS 2026 p.26 의 다섯 구성요소(가격/소득, 가격/임대료, 도시/전국, 주택담보대출/GDP 변화, 건설/GDP 변화)를 참고하되 "
      "p.27 은 기관 목록만 있고 계열 코드가 없어 공개자료로 독립 구성했다.\n")

    # 2
    w("## 2. 자료 확보 현황\n")
    core = ["price_level", "rent_month", "hh_income", "earnings", "price_index", "rent_index", "price_index_national"]
    cov = pd.read_csv(out / "coverage_matrix.csv")
    rows = []
    for cid in ctx.cities:
        r = {"도시": name[cid]}
        for v in core:
            g = cov[(cov["city_id"] == cid) & (cov["variable"] == v)]
            r[v] = f"{int(g['first_year'].min())}–{int(g['last_complete_year'].max())} ({g['quality_flag'].iloc[0]})" \
                if len(g) and g["last_complete_year"].notna().any() else "—"
        rows.append(r)
    w(md_table(pd.DataFrame(rows)))
    w("괄호는 품질 등급. —는 미확보. 미확보·일부 확보 이유:\n")
    for g in gaps:
        w(f"- **{name.get(g['city_id'], '전체')} · {g['variable']}**: {g['reason']}")
    w("")

    # 3
    w(f"## 3. 현재 수준 — 공통연도 {cy_year}\n")
    w("공통연도는 서울을 포함해 PTR·소득 대비 임대료를 계산할 수 있는 도시가 가장 많은 해다 "
      f"(연도별 도시 수: {meta['common_year_scores']}). 도시마다 더 최근 값은 4절 '최신 시점' 표에 따로 둔다.\n")
    cy = lv[lv["year"] == cy_year]

    def table_for(metric, label, d=1, suf=""):
        g = cy[cy["metric"] == metric].copy()
        if g.empty:
            return pd.DataFrame()
        g = g.sort_values("value", ascending=False)
        return pd.DataFrame({"도시": g["city_id"].map(name), label: g["value"].map(lambda v: fmt(v, d, suf)),
                             "소득 개념": g["income_concept"].fillna("").map(lambda c: SHORT.get(c, c)),
                             "주택 유형": g["dwelling_type"].fillna(""), "품질": g["quality_flag"],
                             "비고": g["notes"].fillna("").str.slice(0, 80)})

    w("### 3.1 임대료 대비 가격 (PTR = 가격 ÷ 연 임대료) 과 총임대수익률\n")
    w(md_table(table_for("PTR", "PTR(년)")))
    comp_set = cy[(cy["metric"] == "PTR") & cy["quality_flag"].isin(["A", "B"])][["city_id", "value"]]
    st = rank_statement(comp_set, f"서울의 {cy_year}년 PTR")
    seoul_ptr = cy[(cy["metric"] == "PTR") & (cy["city_id"] == "seoul")]["value"]
    if len(seoul_ptr):
        y = cy[(cy["metric"] == "gross_yield") & (cy["city_id"] == "seoul")]["value"]
        w(f"- 서울 60㎡ 아파트(전용 50~70㎡ 실거래 중위, 보증금 환산 월세 기준) PTR 은 **{fmt(seoul_ptr.iloc[0])}년**, "
          f"총임대수익률 **{fmt(y.iloc[0], 2, '%')}**.")
    if st:
        w(f"- {st}이다 (매매·임대 주택유형이 맞지 않아 품질 C 로 표시된 도시는 순위에서 뺐다). PTR 은 매매·임대 대표값의 비율이며 같은 주택의 수익률이 아니다.")
    w("")

    w("### 3.2 소득 대비 연 임대료 (렌트 부담)\n")
    w("가구소득 기준과 근로자 1인 소득 기준을 나눈다. 소득 개념이 다르면 같은 순위표에 넣지 않는다.\n")
    w("**가구소득 기준**\n")
    w(md_table(table_for("RTI_hh", "임대료/소득(%)", 1, "%")))
    s_rti = cy[(cy["metric"] == "RTI_hh") & (cy["city_id"] == "seoul")]
    if len(s_rti):
        conc = s_rti["income_concept"].iloc[0]
        same = cy[(cy["metric"] == "RTI_hh") & (cy["income_concept"] == conc)]
        w(f"- 서울: 연 환산 임대료(60㎡, 보증금 환산 포함)가 가구 평균 경상소득의 **{fmt(s_rti['value'].iloc[0], 1, '%')}**.")
        cash = cy[(cy["metric"] == "RTI_cash_hh") & (cy["city_id"] == "seoul")]
        if len(cash):
            w(f"  보증금 기회비용을 빼고 현금 월세만 보면 **{fmt(cash['value'].iloc[0], 1, '%')}**.")
        if len(same) < 2:
            w("- 같은 소득 개념(가구 **평균** 소득)을 쓰는 비교 도시가 없어 서울의 순위를 매기지 않는다. "
              "다른 도시는 대부분 **중위** 소득이다.")
    est = cy[(cy["metric"] == "RTI_hh_est") & (cy["city_id"] == "seoul")]
    med = cy[(cy["metric"] == "RTI_hh") & cy["income_concept"].fillna("").str.contains("median") &
             cy["income_concept"].fillna("").str.startswith("household_gross")]
    if len(est):
        w(f"\n**보조표 (추정치 포함, 품질 C)** — 서울 중위소득 추정치(서울 평균 × 전국 중위/평균) 기준 서울 임대료/소득은 "
          f"**{fmt(est['value'].iloc[0], 1, '%')}**. 가구 세전소득 중위를 쓰는 도시(세부 정의 차이 있음)와 나란히 놓으면:\n")
        sub = pd.concat([med[["city_id", "value", "income_concept", "quality_flag"]],
                         est[["city_id", "value", "income_concept", "quality_flag"]]])
        sub = sub.sort_values("value", ascending=False)
        w(md_table(pd.DataFrame({"도시": sub["city_id"].map(name), "임대료/소득(%)": sub["value"].map(lambda v: fmt(v, 1)),
                                 "소득 개념": sub["income_concept"].map(lambda c: SHORT.get(c, c)), "품질": sub["quality_flag"]})))
        st = rank_statement(sub[["city_id", "value"]], "서울(추정 중위소득 기준) 임대료/소득 비율")
        if st:
            w(f"- {st}이다 — 추정치에 기댄 보조 비교이므로 결론의 근거로 쓰지 않는다.\n")
    w("**근로자 1인 소득 기준** (UBS 의 숙련 서비스업 근로자 개념과 비슷한 방향. 도시별 소득 정의가 모두 달라 순위를 매기지 않는다)\n")
    w(md_table(table_for("RTI_earn", "임대료/소득(%)", 1, "%")))
    off = cy[cy["metric"] == "RTI_official"]
    if len(off):
        w("미국 ACS 공식 임대료 부담률(기존 임차가구, 임차가구 소득 대비 중위): " +
          ", ".join(f"{name[c]} {fmt(v, 1, '%')}" for c, v in zip(off["city_id"], off["value"])) + "\n")

    w("### 3.3 소득 대비 가격 (PIR)\n")
    w(md_table(table_for("PIR_hh", "PIR(년, 가구소득)")))
    w(md_table(table_for("PIR_earn", "PIR(년, 근로자 소득)")))

    w("### 3.4 수준(현지통화·USD)\n")
    rows = []
    for cid in ctx.cities:
        g = cy[cy["city_id"] == cid].set_index("metric")["value"]
        if g.empty:
            continue
        rows.append({"도시": name[cid], "대표 주택가격": money(g.get("price_level_local"), cur[cid]),
                     "USD": fmt(g.get("price_level_usd"), 0), "월 임대료": money(g.get("rent_month_local"), cur[cid]),
                     "USD/월": fmt(g.get("rent_month_usd"), 0), "㎡당 가격 USD": fmt(g.get("price_sqm_usd"), 0)})
    w(md_table(pd.DataFrame(rows)))
    w("USD 는 시장환율(연평균) 환산 — 국제 구매자 관점. PPP 환산은 Excel(CommonYear) 에만 둔다(생활비 관점 보조).\n")

    # 4
    w("## 4. 도시별 최신 시점\n")
    keep = ["PTR", "RTI_hh", "RTI_earn", "PIR_hh", "PIR_earn", "RTI_hh_est"]
    g = la[la["metric"].isin(keep)].copy()
    piv = g.pivot_table(index="city_id", columns="metric", values="value", aggfunc="first")
    yrs = g.pivot_table(index="city_id", columns="metric", values="year", aggfunc="first")
    rows = []
    for cid in ctx.cities:
        if cid not in piv.index:
            rows.append({"도시": name[cid], **{m: "NA" for m in keep}})
            continue
        rows.append({"도시": name[cid], **{m: (f"{fmt(piv.loc[cid, m])} ({int(yrs.loc[cid, m])})" if m in piv and not np.isnan(piv.loc[cid, m]) else "NA")
                                           for m in keep}})
    w(md_table(pd.DataFrame(rows)))
    w("괄호는 관측연도. 가격·임대료·소득을 같은 해로 맞춘 마지막 해다(소득을 추정해 늘리지 않음).\n")

    # 5
    w(f"## 5. 과거 대비 변화 (실질, 기준연도 {meta['base_year']})\n")
    w(f"기준연도: {meta['base_year_reason']}\n")
    rows = []
    for cid in ctx.cities:
        r = {"도시": name[cid]}
        for lab, col in (("price", "실질 가격 5년"), ("rent", "실질 임대료 5년"), ("price", "실질 가격 10년")):
            k = "real_cum_10y_pct" if "10년" in col else "real_cum_5y_pct"
            s = ps[(ps["city_id"] == cid) & (ps["series"] == lab)]
            r[col] = f"{fmt(s[k].iloc[0], 1, '%')} ({int(s['last_year'].iloc[0])})" if len(s) and k in s and not np.isnan(s[k].iloc[0]) else "NA"
        for var, col in (("rel_PTR", "가격/임대료 지수"), ("rel_PIR", "가격/소득 지수"), ("city_to_country", "도시/전국 지수")):
            s = panel[(panel["city_id"] == cid) & (panel["variable"] == var)].sort_values("year")
            r[col] = f"{fmt(s['value'].iloc[-1])} ({int(s['year'].iloc[-1])})" if len(s) else "NA"
        rows.append(r)
    w(md_table(pd.DataFrame(rows)))
    w("- 지수 100 초과: 기준연도 이후 분자가 분모보다 더 올랐다는 뜻. 도시 간 실제 PTR 수준이 더 높다는 뜻이 아니다.")
    w("- 실질화는 각국 CPI(World Bank). 미국·호주 가격지수와 일부 임대료는 민간·비층화 중위값이라 품질 B~C.\n")
    s_rel = panel[(panel["city_id"] == "seoul") & (panel["variable"] == "rel_PTR")].sort_values("year")
    if len(s_rel):
        w(f"- 서울 가격/임대료 상대지수는 {int(s_rel['year'].iloc[-1])}년 **{fmt(s_rel['value'].iloc[-1])}** "
          f"(기준 {meta['base_year']}=100). 같은 지표가 있는 다른 도시: " +
          ", ".join(f"{name[c]} {fmt(g.sort_values('year')['value'].iloc[-1])}" for c, g in
                    panel[panel["variable"] == "rel_PTR"].groupby("city_id") if c != "seoul") + ".\n")

    # 6
    w("## 6. 서울 심층 — 보증금 환산과 민감도\n")
    w("`환산 월 임대료 = 계약 월세 + 보증금 × 연 환산율 / 12` 를 계약 건별로 계산한 뒤 전용 50~70㎡ ㎡당 중위값 × 60㎡ 로 집계했다. "
      "기준 환산율은 한국부동산원이 관측한 서울 아파트 전월세 전환율의 해당 연도 평균이며, 법정 상한(기준금리+2%p)을 쓰지 않았다. "
      "전세 보증금/매매가 비율은 PTR 로 부르지 않는다.\n")
    d = dep[dep["contracts"].isin(["월세(보증부 포함), 전체", "월세, 신규", "월세, 갱신", "전세(보증금만)"])].copy()
    if len(d):
        show = d[["year", "contracts", "n", "rate_label", "rate_pct", "cash_rent_60", "deposit_60", "converted_rent_60"] +
                 [c for c in ("PTR", "gross_yield_pct", "RTI_hh_pct", "RTI_earn_pct") if c in d]].copy()
        show["rate_pct"] = show["rate_pct"].map(lambda v: fmt(v, 2))
        for c in ("cash_rent_60", "deposit_60", "converted_rent_60"):
            show[c] = show[c].map(lambda v: money(v, "KRW"))
        for c in ("PTR", "gross_yield_pct", "RTI_hh_pct", "RTI_earn_pct"):
            if c in show:
                show[c] = show[c].map(lambda v: fmt(v, 1))
        show["n"] = show["n"].map(lambda v: "" if np.isnan(v) else f"{int(v):,}")
        w(md_table(show[show["contracts"] == "월세(보증부 포함), 전체"]))
        w("신규·갱신 계약과 전세(보증금만, 환산율 적용) 비교 — 기준 환산율:\n")
        w(md_table(show[(show["contracts"] != "월세(보증부 포함), 전체") & show["rate_label"].str.startswith("기준(")]))
    sv = dep[dep["contracts"] == "R-ONE 표본 평균(전체 면적)"]
    if len(sv):
        last = sv.sort_values("year").iloc[-1]
        w(f"- 교차 확인(R-ONE 표본조사, 전체 면적 평균): {int(last['year'])}년 평균 월세 {money(last['survey_mean_cash_rent'], 'KRW')}, "
          f"평균 보증금 {money(last['survey_mean_deposit'], 'KRW')} → 환산 {money(last['survey_mean_converted_rent'], 'KRW')}/월. "
          "실거래 60㎡ 환산값과 면적·표본이 달라 직접 같지 않다.\n")
    w("- 실거래 중위값은 거래 구성(지역·면적·연식) 변화를 포함하므로 순수 가격·임대료 변화율로 읽지 않는다. "
      "신고 지연분은 수집 시점(2026-11-04) 기준으로 반영돼 있고 2025년 계약은 신고기한(30일)이 지났다.\n")

    # 7
    w("## 7. 신용·건설 (보조)\n")
    cr = panel[panel["variable"] == "household_credit_to_gdp"]
    rows = []
    for cid in ctx.cities:
        s = cr[cr["city_id"] == cid].sort_values("year").set_index("year")["value"]
        if s.empty:
            continue
        t = s.index.max()
        rows.append({"도시(국가)": name[cid], "가계신용/GDP(%)": f"{fmt(s.loc[t])} ({int(t)})",
                     "3년 변화(%p)": fmt(s.loc[t] - s.loc[t - 3]) if t - 3 in s.index else "NA"})
    w(md_table(pd.DataFrame(rows).drop_duplicates("도시(국가)")))
    w("BIS 가계·비영리 신용 전체이며 주택담보대출이 아니다(mortgage_to_gdp 로 쓰지 않음). 건설투자/GDP 는 미수집.\n")

    # 8
    w("## 8. 선택 산출물 — 합성지수\n")
    if len(comp):
        w("설계서 6.1 규칙(본 프로젝트 제안, UBS 원식 아님)의 5개 구성요소 중 주택담보대출/GDP·건설투자/GDP 를 확보하지 못해 "
          "**전체 합성점수는 모든 도시 NA** 다(가중치를 재배분하지 않음). 대신 이름을 달리한 '가격괴리 3항목'"
          "(상대 PIR·PTR·도시/전국의 자기 과거 10년 대비 z 평균)을 별도로 둔다. 확률·조기경보로 해석하지 않는다.\n")
        c2 = comp.copy()
        w(md_table(pd.DataFrame({"도시": c2["city_id"].map(name), "z 상대PIR": c2["z_price_to_income_rel"].map(lambda v: fmt(v, 2)),
                                 "z 상대PTR": c2["z_price_to_rent_rel"].map(lambda v: fmt(v, 2)),
                                 "z 도시/전국": c2["z_city_to_country_rel"].map(lambda v: fmt(v, 2)),
                                 "가격괴리 3항목": c2["price_gap_3item"].map(lambda v: fmt(v, 2)),
                                 "전체 합성": "NA"})))

    # 9
    w("## 9. 정의 차이와 한계\n")
    for cid in ctx.cities:
        notes = cat[(cat["city_id"] == cid) & (cat["확보 여부"] == "확보") & cat["variable"].isin(
            ["price_level", "rent_month", "hh_income", "earnings"])]
        if notes.empty:
            continue
        parts = [f"{r['variable']}: {r['정의·방법']} [{r['quality_flag']}]" for _, r in notes.iterrows()]
        w(f"- **{name[cid]}** — " + " / ".join(parts))
    w("- 가격·임대료 대표값은 같은 주택이 아니다. 홍콩·서울·파리·싱가포르(HDB)는 60㎡ 근방 면적을 맞췄고, 런던은 플랫 전체, "
      "미국은 전체 주택(단독 포함), 시드니는 공동주택 거래가와 전체 임차가구 임대료라 PTR 비교력이 낮다(품질 C 표시).")
    w("- 미국 ZORI·파리 Carte des loyers 는 신규 호가(광고) 임대료, 서울·런던·캐나다·미국 ACS 는 기존 계약 포함 임대료다.")
    w("- 원자료 수정본으로 과거를 다시 구성했다(빈티지 분석 아님). 기준일 이후 공표분은 쓰지 않는다.\n")

    # 10
    w("## 10. 재실행과 검증\n")
    w("```bash\npython -m src.run --config configs/project.yaml --stage all --env-file <.env 경로>\n"
      "python -m src.run --config configs/project.yaml --offline\npython -m pytest\n```\n")
    n_err = int((qf["severity"] == "error").sum())
    w(f"- 검증 결과: {len(qf)}건 (error {n_err}, warning {int((qf['severity'] == 'warning').sum())}) — `QualityFlags` 시트.")
    w("- 출처·계열 코드·확보 여부: `outputs/source_catalog.csv`, 커버리지: `outputs/coverage_matrix.xlsx`.\n")

    w("## 출처\n")
    w("- [S1] UBS, Global Real Estate Bubble Index 2026, pp.26–27 (방법론·출처표)")
    for agency, g in cat[cat["확보 여부"] == "확보"].groupby("본 프로젝트 기관"):
        urls = sorted(set(u for u in g["source_url"] if isinstance(u, str) and u))[:3]
        w(f"- {agency}: " + ", ".join(urls))
    (out / "report_ko.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    log("  outputs/report_ko.md")
