"""수집 커넥터 등록부. source_id → 모듈.

각 모듈은 fetch(ctx, fetcher, log, source_id) 를 제공한다. 실패는 예외로 알리고, run.py 가
네트워크 실패(NetworkError)·자료 없음(DataUnavailable)·기타를 구분해 수집 로그에 남긴다.
"""

from importlib import import_module

SOURCES = {
    # 한국
    "kr_rone": "korea",
    "kr_rtms": "korea",
    "kr_kosis": "korea",
    # 영국
    "uk_hpi": "uk",
    "uk_ons_pipr": "uk",
    "uk_nomis_ashe": "uk",
    # 홍콩
    "hk_rvd": "hongkong",
    "hk_censtatd": "hongkong",
    # 싱가포르
    "sg_datagov": "singapore",
    # 미국
    "us_zillow": "usa",
    "us_fhfa": "usa",
    "us_acs": "usa",
    # 캐나다
    "ca_statcan": "canada",
    # 호주
    "au_abs": "australia",
    # 프랑스
    "fr_insee": "france",
    "fr_dvf": "france",
    "fr_loyers": "france",
    # 일본
    "jp_mlit": "japan",
    # 국제
    "wb_wdi": "intl",
    "bis": "intl",
}


def fetch_source(source_id, ctx, fetcher, log):
    mod = import_module(f"{__name__}.{SOURCES[source_id]}")
    return mod.fetch(ctx, fetcher, log, source_id)
