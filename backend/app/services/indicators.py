"""부동산 지표 목록(CATALOG)과 데이터 수집.

지표를 추가하는 방법
1. 아래 CATALOG 에 한 줄 추가한다. (key 는 영문 소문자·밑줄)
2. 출처가 ECOS 면 ecos_client.py 의 SERIES 에, FRED 면 fred_client.py 의 SERIES 에 같은 key 로 코드를 등록한다.
3. GET /indicators/{key} 로 확인한다.
"""

from datetime import date, timedelta

import pandas as pd

from .ecos_client import EcosClient
from .fred_client import FredClient

LOOKBACK_YEARS = 10

# key → 지표 정보. 예시는 주석으로 두었다 — 실제 코드를 확인한 뒤 주석을 풀고 쓴다.
CATALOG: dict[str, dict] = {
    # "hpi_seoul": {"key": "hpi_seoul", "label": "서울 아파트 매매가격지수", "source": "ECOS", "freq": "M", "unit": "지수"},
    # "us_case_shiller": {"key": "us_case_shiller", "label": "미국 케이스-실러 주택가격지수", "source": "FRED", "freq": "M", "unit": "지수"},
}


def _date_range() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=365 * LOOKBACK_YEARS)
    return start.isoformat(), end.isoformat()


def _series_to_points(series: pd.Series) -> list[dict]:
    return [{"date": idx.date().isoformat(), "value": round(float(v), 3)} for idx, v in series.dropna().items()]


def fetch_series(key: str) -> dict:
    info = CATALOG[key]
    start, end = _date_range()
    if info["source"] == "ECOS":
        series = EcosClient().get_by_key(key, start, end)
    elif info["source"] == "FRED":
        series = FredClient().get_by_key(key, start, end)
    else:
        raise ValueError(f"지원하지 않는 출처입니다: {info['source']}")
    return {"info": info, "points": _series_to_points(series)}
