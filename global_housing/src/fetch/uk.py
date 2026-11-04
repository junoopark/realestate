"""영국(런던) 원자료.

uk_hpi         HM Land Registry·ONS UK House Price Index full file (월, 1968~/1995~) — London·England·UK 행만 부분집합
uk_ons_pipr    ONS Price Index of Private Rents (월, 2015.01~) — 임대료 수준(£/월)·지수, London·England·UK
uk_nomis_ashe  ONS ASHE 거주지 기준(NM_30_1, Nomis API) — 상근 근로자 연간 총급여 중위·평균
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from ..netio import DataUnavailable

HPI_BASE = "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-{ym}.csv"
HPI_REGIONS = ["London", "England", "United Kingdom"]
PIPR_PAGE = "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics"
PIPR_AREAS = ["London", "England", "United Kingdom"]
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset/NM_30_1.data.csv"
NOMIS_GEO = {"2013265927": "London", "2092957699": "England", "2092957697": "United Kingdom"}


def _months_back(as_of: str, n: int):
    y, m = int(as_of[:4]), int(as_of[5:7])
    for _ in range(n):
        yield f"{y:04d}-{m:02d}"
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)


def fetch_hpi(ctx, f, log):
    last_err = None
    for ym in _months_back(ctx.as_of, 6):  # 공표 시차(약 2개월)를 고려해 최근 파일부터 찾는다
        url = HPI_BASE.format(ym=ym)
        try:
            path = f.download("uk_hpi", url, f"UK-HPI-full-file-{ym}.csv", to_cache=True)
        except DataUnavailable as exc:
            last_err = exc
            continue
        df = pd.read_csv(path, low_memory=False)
        sub = df[df["RegionName"].isin(HPI_REGIONS)]
        f.write_subset("uk_hpi", "uk_hpi_london_england_uk.csv", sub, url, path,
                       f"RegionName in {HPI_REGIONS} (모든 열 유지)")
        log(f"  uk_hpi {ym}: {len(sub)}행 (원본 {len(df)}행)")
        return
    raise DataUnavailable(f"UK HPI full file 을 찾지 못함: {last_err}")


def fetch_pipr(ctx, f, log):
    html = f.get(PIPR_PAGE).text
    links = set(re.findall(r'href="(/file\?uri=[^"]+\.xlsx)"', html))

    def pub_date(link):
        m = re.search(r"/(\d{1,2})([a-z]+)(\d{4})/", link)
        try:
            return datetime.strptime("".join(m.groups()), "%d%B%Y").date() if m else date(1900, 1, 1)
        except ValueError:
            return date(1900, 1, 1)

    cands = sorted((l for l in links if pub_date(l) <= date.fromisoformat(ctx.as_of)), key=pub_date)
    if not cands:
        raise DataUnavailable("PIPR xlsx 링크를 찾지 못함")
    link = cands[-1]
    url = "https://www.ons.gov.uk" + link
    pub = pub_date(link).isoformat()
    path = f.download("uk_ons_pipr", url, f"pipr_{pub}.xlsx", to_cache=True)
    df = pd.read_excel(path, sheet_name="Table 1", header=2)
    sub = df[df["Area name"].isin(PIPR_AREAS)].copy()
    sub.insert(0, "release_date", pub)
    f.write_subset("uk_ons_pipr", "pipr_london_england_uk.csv", sub, url, path,
                   f"Table 1, Area name in {PIPR_AREAS} (모든 열 유지, release_date 열 추가)")
    log(f"  uk_ons_pipr {pub}: {len(sub)}행")


def fetch_ashe(ctx, f, log):
    params = {"geography": ",".join(NOMIS_GEO), "date": "2005-latest", "sex": "7,8", "item": "2,4", "pay": "7",
              "measures": "20100",
              "select": "date_name,geography_name,geography_code,sex_name,item_name,pay_name,measures_name,"
                        "obs_value,obs_status_name"}
    path = f.download("uk_nomis_ashe", NOMIS, "ashe_resident_annual_gross_pay.csv", params=params,
                      note="ASHE resident analysis: 연간 총급여(pay=7), 중위(2)·평균(4), 전체(7)·상근(8)")
    n = sum(1 for _ in open(path, encoding="utf-8")) - 1
    if n <= 0:
        raise DataUnavailable("Nomis ASHE 응답이 비어 있음")
    log(f"  uk_nomis_ashe: {n}행")


def fetch(ctx, f, log, source_id):
    {"uk_hpi": fetch_hpi, "uk_ons_pipr": fetch_pipr, "uk_nomis_ashe": fetch_ashe}[source_id](ctx, f, log)
