"""미국(뉴욕·샌프란시스코) 원자료.

us_zillow  Zillow Research 공개 CSV — ZHVI(주택가치, 중간 계층, 계절조정), ZORI(호가 임대료) MSA 월간
us_fhfa    FHFA HPI all-transactions (분기) — 미국 전국 (전국 대비 도시 가격 보조)
us_acs     ACS 1-year 요약파일(Census, 키 불필요) — MSA 가구소득 중위·임대료 중위·주택가치 중위·임대료 부담률
"""

from __future__ import annotations

import io

import pandas as pd

from ..netio import DataUnavailable

ZILLOW = "https://files.zillowstatic.com/research/public_csvs/{kind}/{name}"
ZILLOW_FILES = {
    "Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv": ("zhvi", "ZHVI 전체 주택(단독+콘도), 중간 계층, 평활·계절조정"),
    "Metro_zhvi_uc_condo_tier_0.33_0.67_sm_sa_month.csv": ("zhvi", "ZHVI 콘도·코업, 중간 계층"),
    "Metro_zori_uc_sfrcondomfr_sm_month.csv": ("zori", "ZORI 전체 임대(단독·콘도·다세대), 평활"),
}
ZILLOW_REGIONS = {"United States": 102001, "New York, NY": 394913, "San Francisco, CA": 395057}

FHFA_US = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_us_and_census.csv"

ACS = "https://www2.census.gov/programs-surveys/acs/summary_file/{y}/table-based-SF/data/1YRData/acsdt1y{y}-{t}.dat"
ACS_TABLES = {
    "b19013": "Median household income (inflation-adjusted to survey year dollars)",
    "b25119": "Median household income by tenure",
    "b25064": "Median gross rent (dollars)",
    "b25031": "Median gross rent by bedrooms",
    "b25071": "Median gross rent as a percentage of household income",
    "b25077": "Median value (owner-occupied housing units)",
}
ACS_GEOS = {"US35620": "New York-Newark-Jersey City, NY-NJ MSA", "US41860": "San Francisco-Oakland-Fremont, CA MSA",
            "0100000US": "United States"}


def fetch_zillow(ctx, f, log):
    for name, (kind, desc) in ZILLOW_FILES.items():
        url = ZILLOW.format(kind=kind, name=name)
        path = f.download("us_zillow", url, name, to_cache=True)
        df = pd.read_csv(path)
        sub = df[df["RegionID"].isin(ZILLOW_REGIONS.values())]
        if len(sub) < len(ZILLOW_REGIONS):
            raise DataUnavailable(f"Zillow {name}: 지역 일부 없음 ({sub['RegionName'].tolist()})")
        f.write_subset("us_zillow", name, sub, url, path, f"RegionID in {list(ZILLOW_REGIONS.values())} — {desc}")
        log(f"  us_zillow {name}: {len(sub)}행")


def fetch_fhfa(ctx, f, log):
    f.download("us_fhfa", FHFA_US, "hpi_at_us_and_census.csv", note="FHFA HPI all-transactions, 미국·센서스 권역, 분기")
    log("  us_fhfa hpi_at_us_and_census.csv")


def fetch_acs(ctx, f, log):
    last = int(ctx.as_of[:4]) - 1
    got = 0
    for y in range(2005, last + 1):
        for t, desc in ACS_TABLES.items():
            url = ACS.format(y=y, t=t)
            try:
                path = f.download("us_acs", url, f"acsdt1y{y}-{t}.dat", to_cache=True)
            except DataUnavailable:
                continue
            df = pd.read_csv(path, sep="|", dtype=str)
            mask = df["GEO_ID"].apply(lambda g: any(g.endswith(k) and (k == "0100000US" and g == k or g.startswith("310"))
                                                    for k in ACS_GEOS))
            sub = df[mask]
            if sub.empty:
                continue
            f.write_subset("us_acs", f"acs1y_{y}_{t}.csv", sub, url, path,
                           f"GEO_ID: 미국 전체(0100000US)·CBSA 35620·41860 — {desc}")
            got += 1
    if not got:
        raise DataUnavailable("ACS 1-year 요약파일을 하나도 받지 못함")
    log(f"  us_fred(ACS): {got}개 표-연도")


def fetch(ctx, f, log, source_id):
    {"us_zillow": fetch_zillow, "us_fhfa": fetch_fhfa, "us_acs": fetch_acs}[source_id](ctx, f, log)
