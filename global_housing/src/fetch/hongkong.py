"""홍콩 원자료.

hk_rvd       Rating and Valuation Department 민간주택 역사자료(xls): 평균 임대료·가격(등급·지역별, ㎡ 실용면적),
             임대·가격 지수(등급별, 1999=100)
hk_censtatd  Census and Statistics Department web table API: 가구 월소득 중위(130-06606),
             취업자 월 취업소득 중위(210-06315)
"""

from __future__ import annotations

from ..netio import DataUnavailable

RVD = "https://www.rvd.gov.hk/doc/en/statistics/his_data_{n}.xls"
RVD_FILES = {
    1: "Private Domestic - Average Rents by Class (from 1982), HK$/m2/month (saleable area)",
    2: "Private Domestic - Average Prices by Class (from 1982), HK$/m2 (saleable area)",
    3: "Private Domestic - Rental Indices by Class (Territory-wide), 1999=100",
    4: "Private Domestic - Price Indices by Class (Territory-wide), 1999=100",
}
CSD = "https://www.censtatd.gov.hk/api/get.php"
CSD_TABLES = {
    "130-06606": "Median monthly household income by household size",
    "210-06315": "Median monthly employment earnings of employed persons by educational attainment and sex",
}


def fetch_rvd(ctx, f, log):
    for n, desc in RVD_FILES.items():
        f.download("hk_rvd", RVD.format(n=n), f"his_data_{n}.xls", note=desc)
        log(f"  hk_rvd his_data_{n}.xls")


def fetch_csd(ctx, f, log):
    for tid, desc in CSD_TABLES.items():
        params = {"id": tid, "lang": "en", "full_series": "1"}
        body = f.get(CSD, params=params).json()
        if body.get("header", {}).get("status", {}).get("code") != 0:
            raise DataUnavailable(f"C&SD {tid}: {body.get('header', {}).get('status')}")
        f.save_json("hk_censtatd", f"{tid}.json", body, CSD, params, note=desc)
        log(f"  hk_censtatd {tid}: {len(body['dataSet'])}행")


def fetch(ctx, f, log, source_id):
    {"hk_rvd": fetch_rvd, "hk_censtatd": fetch_csd}[source_id](ctx, f, log)
