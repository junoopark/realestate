"""싱가포르 원자료 (data.gov.sg, 키 불필요).

민간주택(URA)은 지수만 공개 — 수준(가격·임대료 ㎡ 단가)은 URA API(가입 키) 가 필요해 받지 않는다.
수준 비교는 공공주택 HDB 재판매 가격(건별, 면적 포함)과 HDB 임대료 중위(유형별)로 따로 한다(설계서 4절: HDB·민간 분리).
"""

from __future__ import annotations

import time

import pandas as pd

from ..netio import DataUnavailable

POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download"
DATASETS = {
    "d_97f8a2e995022d311c6c68cfda6d034c": ("ura_private_price_index.csv", "URA Private Residential Property Price Index (2009Q1=100), 분기"),
    "d_8e4c50283fb7052a391dfb746a05c853": ("ura_private_rental_index.csv", "URA Private Residential Property Rental Index (2009Q1=100), 분기"),
    "d_8b84c4ee58e3cfc0ece0d773c8ca6abc": ("hdb_resale_prices_2017on.csv.gz", "HDB Resale flat prices (registration date, Jan-2017~), 건별"),
    "d_23000a00c52996c55106084ed0339566": ("hdb_median_rent_town_flat_type.csv", "HDB Median Rent by Town and Flat Type, 분기"),
    "d_42010db3d76ac3f5871533fff1d725d6": ("household_employment_income_percentiles_incl_cpf.csv",
                                           "Monthly Household Employment Income (incl. employer CPF) among Resident Employed Households at Selected Percentiles, 2000-2025"),
    "d_6d878eb9c5a47f54fee7ce496f681e8d": ("household_employment_income_key_indicators.csv",
                                           "Key Indicators On Household Employment Income Among Resident Employed Households, Annual"),
    "d_52760e82e8786bac11cca40eb29d1a93": ("ft_employed_income_from_employment_incl_cpf.csv",
                                           "Gross Monthly Income From Employment (incl. employer CPF) Of Full-time Employed Residents, Annual"),
}


def _csv_url(f, did):
    for _ in range(6):
        body = f.get(POLL.format(id=did)).json()
        data = body.get("data") or {}
        if data.get("status") == "DOWNLOAD_SUCCESS" and data.get("url"):
            return data["url"]
        f.get(POLL.format(id=did).replace("poll-download", "initiate-download"))
        time.sleep(3)
    raise DataUnavailable(f"data.gov.sg {did}: 다운로드 URL 을 받지 못함 ({body})")


def fetch(ctx, f, log, source_id):
    for did, (fname, desc) in DATASETS.items():
        url = _csv_url(f, did)
        page = f"https://data.gov.sg/datasets/{did}/view"
        if fname.endswith(".gz"):  # 큰 건별 자료: 2019년 이후 행만 gzip 으로 남긴다
            path = f.download("sg_datagov", url, fname[:-3], to_cache=True)
            df = pd.read_csv(path)
            sub = df[df["month"] >= "2019-01"]
            f.write_subset("sg_datagov", fname, sub, page, path, f"month >= 2019-01 (모든 열 유지) — {desc}")
            log(f"  sg_datagov {fname}: {len(sub)}행 (원본 {len(df)})")
            continue
        path = f.download("sg_datagov", url, fname, note=f"{desc} | 데이터셋 페이지 {page}")
        # 서명 URL 은 만료되므로 manifest 에는 데이터셋 페이지를 남긴다
        row = f.manifest.get("sg_datagov", fname)
        row["url"] = page
        log(f"  sg_datagov {fname}")
