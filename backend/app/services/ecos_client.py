"""BOK ECOS API 클라이언트 (mypage 프로젝트의 ecos_client.py 에서 가져옴).

.env 로딩은 app.main 이 담당한다 (ECOS_API_KEY 는 os.getenv 로만 읽는다).
통계표·항목 코드는 ECOS 웹사이트 > 통계검색 또는 OpenAPI > 개발 명세서에서 확인한다.
"""

import os

import pandas as pd
import requests

_BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


class EcosClient:
    # key → (stat_code, item_code, 주기, 한글명). key 는 services/indicators.py 의 CATALOG 와 맞춘다.
    SERIES: dict[str, tuple[str, str, str, str]] = {
        # "hpi_seoul": ("통계표코드", "항목코드", "M", "서울 아파트 매매가격지수"),
    }

    def __init__(self, api_key: str = None):
        self._key = api_key or os.getenv("ECOS_API_KEY")
        if not self._key:
            raise ValueError("ECOS_API_KEY가 설정되지 않았습니다.")

    def get_series(self, stat_code: str, item_code: str, start_date: str, end_date: str, freq: str = "M") -> pd.Series:
        fmt = {"D": 8, "M": 6, "A": 4}
        n = fmt.get(freq, 8)
        start = start_date.replace("-", "")[:n]
        end = end_date.replace("-", "")[:n]

        url = f"{_BASE_URL}/{self._key}/json/kr/1/10000/{stat_code}/{freq}/{start}/{end}/{item_code}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if "StatisticSearch" not in data:
            raise RuntimeError(f"ECOS 응답 오류 ({stat_code}/{item_code}): {data}")

        rows = data["StatisticSearch"]["row"]
        fmt_map = {"D": "%Y%m%d", "M": "%Y%m", "A": "%Y"}
        series = pd.Series(
            {row["TIME"]: _to_float(row["DATA_VALUE"]) for row in rows},
            name=item_code,
        )
        series.index = pd.to_datetime(series.index, format=fmt_map.get(freq, "%Y%m%d"))
        return series.sort_index()

    def get_by_key(self, key: str, start_date: str, end_date: str) -> pd.Series:
        stat_code, item_code, freq, _ = self.SERIES[key]
        return self.get_series(stat_code, item_code, start_date, end_date, freq)
