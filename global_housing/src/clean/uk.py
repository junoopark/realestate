"""런던 정제 — UK HPI, ONS PIPR, ASHE(Nomis)."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing


def _read(ctx, source_id, name, **kw):
    p = ctx.raw / source_id / name
    if not p.exists():
        raise RawMissing(f"{source_id}/{name}")
    return pd.read_csv(p, **kw)


def clean(ctx, metas, source_id):
    out = {}
    if source_id == "uk_hpi":
        df = _read(ctx, "uk_hpi", "uk_hpi_london_england_uk.csv", low_memory=False)
        df["period"] = pd.to_datetime(df["Date"], dayfirst=True).dt.strftime("%Y-%m")
        for sid, m in metas.items():
            p = m["parse"]
            g = df[df["RegionName"] == p["region"]]
            out[sid] = pd.DataFrame({"period": g["period"], "value": pd.to_numeric(g[p["column"]], errors="coerce")}).dropna()
    elif source_id == "uk_ons_pipr":
        df = _read(ctx, "uk_ons_pipr", "pipr_london_england_uk.csv")
        df["period"] = pd.to_datetime(df["Time period"]).dt.strftime("%Y-%m")
        for sid, m in metas.items():
            p = m["parse"]
            g = df[df["Area name"] == p["area"]]
            out[sid] = pd.DataFrame({"period": g["period"], "value": pd.to_numeric(g[p["column"]], errors="coerce"),
                                     "release_date": g["release_date"]}).dropna(subset=["value"])
    elif source_id == "uk_nomis_ashe":
        df = _read(ctx, "uk_nomis_ashe", "ashe_resident_annual_gross_pay.csv")
        for sid, m in metas.items():
            p = m["parse"]
            g = df[(df["GEOGRAPHY_NAME"] == p["geography"]) & (df["SEX_NAME"] == p["sex"]) & (df["ITEM_NAME"] == p["item"])]
            notes = g["OBS_STATUS_NAME"].where(g["OBS_STATUS_NAME"] != "Normal Value", "")
            out[sid] = pd.DataFrame({"period": g["DATE_NAME"].astype(str), "value": pd.to_numeric(g["OBS_VALUE"], errors="coerce"),
                                     "notes": notes}).dropna(subset=["value"])
    return out
