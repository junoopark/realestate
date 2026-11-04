"""국제기구 자료 — 국가 단위 보조 변수.

wb_wdi  World Bank WDI API: CPI(2010=100), 시장환율(LCU/USD, 연평균), 민간소비 PPP, 명목 GDP(LCU)
bis     BIS Data Portal: 가계·비영리 신용/GDP(%) (주택담보대출이 아니라 가계신용 전체 — household_credit_to_gdp),
        선별 주거용 부동산 가격(WS_SPP, 명목, 전국 대표계열) — 도시/전국 비교의 전국 분모
"""

from __future__ import annotations

COUNTRIES = ["KOR", "GBR", "FRA", "JPN", "HKG", "SGP", "USA", "CAN", "AUS"]
WB = "https://api.worldbank.org/v2/country/{c}/indicator/{i}"
WB_INDICATORS = {
    "FP.CPI.TOTL": "Consumer price index (2010 = 100)",
    "PA.NUS.FCRF": "Official exchange rate (LCU per US$, period average)",
    "PA.NUS.PRVT.PP": "PPP conversion factor, private consumption (LCU per international $)",
    "NY.GDP.MKTP.CN": "GDP (current LCU)",
}
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_TC/2.0/{key}"
BIS_ISO2 = {"KOR": "KR", "GBR": "GB", "FRA": "FR", "JPN": "JP", "HKG": "HK", "SGP": "SG", "USA": "US", "CAN": "CA",
            "AUS": "AU"}


def fetch_wb(ctx, f, log):
    for ind, desc in WB_INDICATORS.items():
        params = {"format": "json", "date": "2000:2026", "per_page": "2000"}
        url = WB.format(c=";".join(COUNTRIES), i=ind)
        body = f.get(url, params=params).json()
        f.save_json("wb_wdi", f"{ind}.json", body, url, params, note=desc)
        log(f"  wb_wdi {ind}: {len(body[1]) if len(body) > 1 and body[1] else 0}행")


def fetch_bis(ctx, f, log):
    key = "Q." + "+".join(BIS_ISO2.values()) + ".H.A.M.770.A"
    f.download("bis", BIS.format(key=key), "ws_tc_household_credit_pct_gdp.csv", params={"format": "csv"},
               note="BIS total credit statistics: Credit to households and NPISHs from all sectors, % of GDP, adjusted for breaks")
    key = "Q." + "+".join(BIS_ISO2.values()) + ".N.628"
    f.download("bis", "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_SPP/1.0/" + key,
               "ws_spp_nominal_index.csv", params={"format": "csv"},
               note="BIS selected residential property prices, nominal, index 2010=100 (국가별 대표 계열)")
    log("  bis ws_tc_household_credit_pct_gdp.csv · ws_spp_nominal_index.csv")


def fetch(ctx, f, log, source_id):
    {"wb_wdi": fetch_wb, "bis": fetch_bis}[source_id](ctx, f, log)
