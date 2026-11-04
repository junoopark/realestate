"""국가 단위 정제 — World Bank WDI JSON, BIS CSV. country_code 를 행마다 채운다."""

from __future__ import annotations

import json

import pandas as pd

from ..netio import RawMissing

ISO2_TO_3 = {"KR": "KOR", "GB": "GBR", "FR": "FRA", "JP": "JPN", "HK": "HKG", "SG": "SGP", "US": "USA", "CA": "CAN",
             "AU": "AUS"}


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        if source_id == "wb_wdi":
            path = ctx.raw / "wb_wdi" / f"{p['indicator']}.json"
            if not path.exists():
                raise RawMissing(f"wb_wdi {p['indicator']}")
            body = json.load(open(path, encoding="utf-8"))
            recs = body[1] or []
            df = pd.DataFrame({"country_code": [r["countryiso3code"] for r in recs], "period": [r["date"] for r in recs],
                               "value": [r["value"] for r in recs]})
            df["release_date"] = body[0].get("lastupdated", "")
            df["geography_name"] = [r["country"]["value"] for r in recs]
            out[sid] = df.dropna(subset=["value"])
        else:
            path = ctx.raw / "bis" / p["file"]
            if not path.exists():
                raise RawMissing(f"bis {p['file']}")
            df = pd.read_csv(path, dtype=str)
            cc = df["BORROWERS_CTY"] if "BORROWERS_CTY" in df else df["REF_AREA"]
            res = pd.DataFrame({"country_code": cc.map(ISO2_TO_3), "period": df["TIME_PERIOD"],
                                "value": pd.to_numeric(df["OBS_VALUE"], errors="coerce")})
            res["geography_name"] = res["country_code"]
            out[sid] = res.dropna()
    return out
