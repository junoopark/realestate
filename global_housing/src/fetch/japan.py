"""일본(도쿄).

jp_mlit  국토교통성 부동산가격지수(주택) 최신 Excel — 도쿄도·전국, 맨션(구분소유)·주택 종합, 원계열(월)
도쿄의 임대료 수준·지수와 소득은 e-Stat API(appId 필요) 또는 유료 자료(Tokyo Kantei 등)라 자동 수집하지 않는다.
data/manual_inputs/tokyo_manual_template.csv 에 출처를 적어 넣으면 정제 단계가 읽는다.
"""

from __future__ import annotations

import re

from ..netio import DataUnavailable

PAGE = "https://www.mlit.go.jp/totikensangyo/totikensangyo_tk5_000085.html"


def fetch(ctx, f, log, source_id):
    res = f.get(PAGE)
    res.encoding = res.apparent_encoding
    html = res.text
    i = html.find("最新データ")
    links = re.findall(r'href="([^"]+\.xlsx)"', html[i:] if i >= 0 else html)
    if not links:
        raise DataUnavailable("MLIT 부동산가격지수 Excel 링크를 찾지 못함")
    url = "https://www.mlit.go.jp" + links[0] if links[0].startswith("/") else links[0]
    f.download("jp_mlit", url, "mlit_rppi_residential_latest.xlsx",
               note=f"不動産価格指数（住宅） 최신 공표 Excel (페이지 {PAGE} 의 '最新データ' 첫 링크)")
    log(f"  jp_mlit {url}")
