"""호주(시드니) — ABS Data API (SDMX, 키 불필요).

RES_DWELL  거래 기반 중위가격(비층화)·거래 건수, 주택 유형별(단독/공동), GCCSA — 분기
RPPI       주거용 부동산 가격지수 (2021Q4 중단) — 분기
CPI        소비자물가지수 — 시드니 임대료(주도별 계열은 2022-07 이후 월간만 API 제공)
C21_G02_SA2    2021 센서스 주요 중위값(가구 주간소득·주간 임대료) — Greater Sydney
"""

from __future__ import annotations

from ..netio import DataUnavailable

ABS = "https://data.api.abs.gov.au/rest/data/ABS,{flow}/{key}"
FLOWS = {
    "RES_DWELL": ("all", {"startPeriod": "2002"}, "Residential Dwellings: Unstratified Medians and Transfer Counts by Dwelling Type, GCCSA"),
    "RPPI": ("all", {"startPeriod": "2002"}, "Residential Property Price Index (discontinued after 2021-Q4)"),
    "CPI": ("all", {"startPeriod": "2022"}, "Consumer Price Index (monthly·quarterly, 주도별 임대료는 2022-07 이후 월간만)"),
    "C21_G02_SA2": ("all", {}, "Census 2021 G02 Selected medians and averages (SA2 and up, GCCSA 포함)"),
}


def fetch(ctx, f, log, source_id):
    for flow, (key, extra, desc) in FLOWS.items():
        params = {"format": "csvfilewithlabels", **extra}
        try:
            path = f.download("au_abs", ABS.format(flow=flow, key=key), f"{flow}.csv", params=params, note=desc,
                              to_cache=flow in ("CPI", "C21_G02_SA2"))
        except DataUnavailable as exc:
            log(f"  ! au_abs {flow}: {exc}")
            continue
        if flow == "CPI":  # CPI 전체는 크다 — 시드니 임대료·전체 항목만 남긴다
            import pandas as pd

            df = pd.read_csv(path, dtype=str)
            sub = df[(df["Region"] == "Sydney") & df["Index"].isin(["Rents", "All groups CPI"])]
            f.write_subset("au_abs", "CPI_sydney_rents.csv.gz", sub, ABS.format(flow=flow, key=key), path,
                           "Region=Sydney, Index in (Rents, All groups CPI) (모든 열 유지)")
        if flow == "C21_G02_SA2":  # Greater Sydney(1GSYD)·호주 전체(AUS)만
            import pandas as pd

            df = pd.read_csv(path, dtype=str)
            col = "REGION" if "REGION" in df else next(c for c in df.columns if c.upper().startswith("REGION"))
            sub = df[df[col].isin(["1GSYD", "AUS", "0"])]
            f.write_subset("au_abs", "C21_G02_greater_sydney.csv", sub, ABS.format(flow=flow, key=key), path,
                           f"{col} in 1GSYD·AUS (모든 열 유지)")
        log(f"  au_abs {flow}")
