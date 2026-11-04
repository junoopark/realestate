"""내보내기 (설계서 10절) — source_catalog.csv, coverage_matrix.xlsx, 공통연도·최신시점 CSV, 연간 패널, 종합 Excel."""

from __future__ import annotations

import json
import shutil

import pandas as pd

from . import validate
from .config import load_yaml

AGENCY = {
    "kr_rone": "한국부동산원 R-ONE", "kr_rtms": "국토교통부 실거래가(공공데이터포털)", "kr_kosis": "통계청 KOSIS",
    "uk_hpi": "HM Land Registry·ONS (UK HPI)", "uk_ons_pipr": "ONS (PIPR)", "uk_nomis_ashe": "ONS ASHE (Nomis)",
    "hk_rvd": "Rating and Valuation Department", "hk_censtatd": "Census and Statistics Department",
    "sg_datagov": "URA·HDB·SingStat·MOM (data.gov.sg)", "us_zillow": "Zillow Research", "us_acs": "U.S. Census Bureau ACS",
    "us_fhfa": "FHFA", "ca_statcan": "Statistics Canada·CMHC", "au_abs": "Australian Bureau of Statistics",
    "fr_insee": "INSEE·Notaires", "fr_dvf": "DGFiP DVF (data.gouv.fr)", "fr_loyers": "생태전환부·ANIL Carte des loyers",
    "jp_mlit": "国土交通省", "wb_wdi": "World Bank WDI", "bis": "BIS", "manual": "수동 입력",
}
UBS_COL = {"price": 0, "rent": 1, "income": 2, "national": 3, "macro": 4}
UBS_COL_NAME = ["UBS 가격(도시)", "UBS 임대(도시)", "UBS 소득(도시)", "UBS 가격(국가)", "UBS 신용·건설·GDP·물가(국가)"]


def ubs_group(var: str) -> str:
    if var.startswith("price_index_national"):
        return "national"
    if var.startswith(("price", "deposit")):
        return "price"
    if var.startswith(("rent_to_income",)):
        return "income"
    if var.startswith(("rent", "conversion")):
        return "rent"
    if var.startswith(("hh_income", "earnings")):
        return "income"
    return "macro"


def source_catalog(ctx) -> pd.DataFrame:
    log = pd.read_csv(ctx.interim / "clean_log.csv").set_index("series_id")
    rows = []
    for sid, m in ctx.series.items():
        city = ctx.cities.get(m["city_id"], {})
        grp = ubs_group(m["variable"])
        ubs = city.get("ubs_sources", ["", "", "", "", ""])[UBS_COL[grp]] if city else "국가 공통"
        st = log.loc[sid] if sid in log.index else None
        rows.append({
            "city_id": m["city_id"], "city": city.get("name_ko", "국가 단위"), "variable": m["variable"], "series_id": sid,
            "UBS 기관(원문 p.27)": ubs, "본 프로젝트 기관": AGENCY.get(m["source_id"], m["source_id"]),
            "source_id": m["source_id"], "source_url": m.get("source_url", ""), "series_code": m.get("series_code", ""),
            "정의·방법": m.get("method", ""), "geography": m.get("geography_name", ""), "dwelling_type": m.get("dwelling_type", ""),
            "area_basis": m.get("area_basis", ""), "income_concept": m.get("income_concept", ""), "unit": m.get("unit", ""),
            "frequency": m.get("frequency", ""), "quality_flag": m.get("quality_flag", ""),
            "확보 여부": {"ok": "확보", "missing": "미확보"}.get(st["status"], st["status"]) if st is not None else "미정제",
            "first": st["first"] if st is not None else "", "last": st["last"] if st is not None else "",
            "n_obs": int(st["n"]) if st is not None else 0,
            "실패 사유": (st["message"] if st is not None and isinstance(st["message"], str) else ""),
            "UBS 와의 차이": "UBS 계열 코드·가중치는 원문에 없음 — 공개자료로 독립 구성" if grp != "macro" else "국가 보조 변수",
            "notes": m.get("notes", ""),
        })
    gaps = load_yaml(ctx.root / "configs" / "gaps.yaml").get("gaps", [])
    for g in gaps:
        city = ctx.cities.get(g["city_id"], {})
        grp = ubs_group(g["variable"])
        rows.append({"city_id": g["city_id"], "city": city.get("name_ko", "전체"), "variable": g["variable"], "series_id": "",
                     "UBS 기관(원문 p.27)": city.get("ubs_sources", [""] * 5)[UBS_COL[grp]] if city else "",
                     "본 프로젝트 기관": "", "source_id": "", "source_url": "", "series_code": "", "정의·방법": "",
                     "geography": "", "dwelling_type": "", "area_basis": "", "income_concept": "", "unit": "", "frequency": "",
                     "quality_flag": "", "확보 여부": "일부 확보" if g.get("partial") else "미확보", "first": "", "last": "",
                     "n_obs": 0, "실패 사유": g["reason"],
                     "UBS 와의 차이": "수동 입력 가능" if g.get("manual") else "", "notes": ""})
    return pd.DataFrame(rows)


def coverage(ctx) -> pd.DataFrame:
    ann = pd.read_csv(ctx.processed / "annual_series.csv")
    ann = ann[ann["city_id"].isin(ctx.cities)]
    rows = []
    for (cid, var, sid), g in ann.groupby(["city_id", "variable", "series_id"]):
        full = g[g["complete"]]
        span = range(int(g["year"].min()), int(g["year"].max()) + 1)
        rows.append({"city_id": cid, "city": ctx.cities[cid]["name_ko"], "variable": var, "series_id": sid,
                     "frequency": g["frequency"].iloc[0], "first_year": int(g["year"].min()), "last_year": int(g["year"].max()),
                     "last_complete_year": int(full["year"].max()) if len(full) else None,
                     "n_years_complete": len(full), "missing_years_in_span": len(set(span) - set(g["year"].astype(int))),
                     "partial_years": ", ".join(str(int(y)) for y in g.loc[~g["complete"], "year"]),
                     "geography": g["geography_name"].iloc[0], "dwelling_type": g["dwelling_type"].iloc[0],
                     "area_basis": g["area_basis"].iloc[0], "income_concept": g["income_concept"].iloc[0],
                     "quality_flag": g["quality_flag"].iloc[0], "source_id": g["source_id"].iloc[0]})
    return pd.DataFrame(rows)


README_TEXT = [
    ("프로젝트", "서울과 해외 도시의 매매가격·임대료 수준, 소득 대비 가격·임대료, 과거 대비 괴리 비교 (기준일 {as_of})"),
    ("참고", "UBS Global Real Estate Bubble Index 2026 pp.26–27 의 구성요소·기관 목록. UBS 계열 코드·가중치·위험등급은 복제하지 않음"),
    ("공통연도", "{common_year} — 서울 포함, 수준지표(PTR·소득 대비 임대료)를 계산할 수 있는 도시 수가 가장 많은 해"),
    ("기준연도", "{base_year} — {base_year_reason}"),
    ("지수와 수준", "AnnualPanel 의 *_index_b, rel_* 는 기준연도=100 상대지수. 도시 간 실제 PTR 수준 비교는 CommonYear·LatestAvailable 의 PTR 을 본다"),
    ("소득 개념", "가구소득(평균/중위, 세전/근로소득만)과 근로자 개인소득을 섞지 않는다. income_concept 열이 같은 도시끼리만 비교"),
    ("서울 보증금", "환산 월 임대료 = 월세 + 보증금 × 연 환산율 / 12. 기준 환산율 = R-ONE 서울 아파트 전월세 전환율 연평균. 전세가율은 PTR 이 아님"),
    ("품질 등급", "A 정의·범위 일치 원자료 / B 공식이나 일부 불일치·공개 민간 / C 추정·범위 불일치 큼"),
    ("결측", "확보하지 못한 값은 비워 둔다(0 으로 채우거나 보간하지 않음). 이유는 Sources 시트 '실패 사유'"),
    ("재실행", "python -m src.run --config configs/project.yaml --offline"),
]


def run(ctx, log):
    validate.run(ctx, log)  # 지표 단계 산출물까지 포함해 다시 검증
    out, proc = ctx.outputs, ctx.processed
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((proc / "run_meta.json").read_text(encoding="utf-8"))
    cat = source_catalog(ctx)
    cat.to_csv(out / "source_catalog.csv", index=False, encoding="utf-8-sig")
    cov = coverage(ctx)
    cov.to_csv(out / "coverage_matrix.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(out / "coverage_matrix.xlsx", engine="openpyxl") as xw:
        cov.to_excel(xw, sheet_name="Coverage", index=False)
        piv = cov.pivot_table(index="city", columns="variable", values="n_years_complete", aggfunc="max")
        piv.to_excel(xw, sheet_name="YearsComplete")
    for name in ("city_latest_common_year.csv", "city_latest_available.csv", "city_panel_annual.parquet"):
        shutil.copy2(proc / name, out / name)

    cy = pd.read_csv(proc / "city_latest_common_year.csv")
    la = pd.read_csv(proc / "city_latest_available.csv")
    panel = pd.read_parquet(proc / "city_panel_annual.parquet")
    dep = pd.read_csv(proc / "seoul_deposit.csv")
    qf = pd.read_csv(proc / "quality_flags.csv")
    comp = pd.read_csv(proc / "composite_optional.csv")
    readme = pd.DataFrame([(k, v.format(**meta)) for k, v in README_TEXT], columns=["항목", "내용"])
    with pd.ExcelWriter(out / "global_housing_comparison.xlsx", engine="openpyxl") as xw:
        readme.to_excel(xw, sheet_name="README", index=False)
        cat.to_excel(xw, sheet_name="Sources", index=False)
        cov.to_excel(xw, sheet_name="Coverage", index=False)
        cy.to_excel(xw, sheet_name="CommonYear", index=False)
        la.to_excel(xw, sheet_name="LatestAvailable", index=False)
        panel.to_excel(xw, sheet_name="AnnualPanel", index=False)
        dep.to_excel(xw, sheet_name="SeoulDeposit", index=False)
        qf.to_excel(xw, sheet_name="QualityFlags", index=False)
        comp.to_excel(xw, sheet_name="CompositeOptional", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width * 1.1), 60)
    log(f"  source_catalog {len(cat)}행, coverage {len(cov)}행 → outputs/ (Excel 9개 시트)")
