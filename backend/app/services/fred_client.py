"""FRED API 클라이언트 (mypage 프로젝트의 fred_client.py 에서 가져옴).

.env 로딩은 app.main 이 담당한다 (FRED_API_KEY 는 os.getenv 로만 읽는다).
"""

import os

import pandas as pd
from fredapi import Fred


class FredClient:
    # key → FRED 시리즈 코드. key 는 services/indicators.py 의 CATALOG 와 맞춘다.
    SERIES: dict[str, str] = {
        # "us_case_shiller": "CSUSHPINSA",
    }

    def __init__(self, api_key: str = None):
        key = api_key or os.getenv("FRED_API_KEY")
        if not key:
            raise ValueError("FRED_API_KEY가 설정되지 않았습니다.")
        self._fred = Fred(api_key=key)

    def get_by_key(self, key: str, start_date: str = None, end_date: str = None) -> pd.Series:
        series_id = self.SERIES[key]
        return self._fred.get_series(series_id, observation_start=start_date, observation_end=end_date)
