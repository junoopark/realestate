"""캐나다(토론토·밴쿠버) — Statistics Canada 전체 표 CSV(zip, 키 불필요).

34-10-0133  CMHC 임대시장조사 평균 임대료 (10월 조사, 목적형 임대주택, 구조·침실 유형별)
11-10-0190  경제가족 유형별 소득 (CIS) — 총소득·세후소득 평균/중위, CMA 포함
18-10-0205  신규주택가격지수 NHPI (월, 신규 단독·연립 주택만 — 가격 지수 대용, 품질 C)
18-10-0004  소비자물가지수 (월) — CMA 별 전체·임대료 항목
수준 가격(기존 주택 거래가)은 CREA·Teranet 자료가 유료/가입이라 확보하지 않는다.
"""

from __future__ import annotations

import zipfile

import pandas as pd

from ..netio import DataUnavailable

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{pid}/en"
TABLES = {
    "34100133": "CMHC average rents for areas with a population of 10,000 and over",
    "11100190": "Market income, government transfers, total income, income tax and after-tax income by economic family type",
    "18100205": "New housing price index, monthly",
    "18100004": "Consumer Price Index, monthly, not seasonally adjusted",
}
GEO_KEEP = ("Canada", "Toronto", "Vancouver")
CPI_PRODUCTS = ("All-items", "Rent", "Rented accommodation")


def fetch(ctx, f, log, source_id):
    for pid, desc in TABLES.items():
        body = f.get(WDS.format(pid=pid)).json()
        url = body.get("object")
        if body.get("status") != "SUCCESS" or not url:
            raise DataUnavailable(f"StatCan {pid}: {body}")
        zpath = f.download("ca_statcan", url, f"{pid}-eng.zip", to_cache=True)
        with zipfile.ZipFile(zpath) as z:
            with z.open(f"{pid}.csv") as fh:
                chunks = []
                for ch in pd.read_csv(fh, chunksize=200_000, low_memory=False, dtype=str):
                    geo = ch["GEO"].fillna("")
                    keep = geo.eq("Canada") | geo.str.startswith("Toronto") | geo.str.startswith("Vancouver")
                    ch = ch[keep]
                    if pid == "18100004":
                        ch = ch[ch["Products and product groups"].isin(CPI_PRODUCTS)]
                    chunks.append(ch)
        sub = pd.concat(chunks)
        if sub.empty:
            raise DataUnavailable(f"StatCan {pid}: 대상 지역 행이 없음")
        f.write_subset("ca_statcan", f"{pid}_canada_toronto_vancouver.csv.gz", sub,
                       f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}01", zpath,
                       f"GEO = Canada 또는 Toronto*/Vancouver* (모든 열 유지){' · CPI 항목 ' + str(CPI_PRODUCTS) if pid == '18100004' else ''} — {desc}")
        log(f"  ca_statcan {pid}: {len(sub)}행")
