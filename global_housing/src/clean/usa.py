"""미국 정제 — Zillow(넓은 표 → long), ACS 요약파일."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing


def zillow(ctx, file, region_id):
    p = ctx.raw / "us_zillow" / file
    if not p.exists():
        raise RawMissing(f"us_zillow/{file}")
    df = pd.read_csv(p)
    row = df[df["RegionID"] == int(region_id)]
    if row.empty:
        return pd.DataFrame(columns=["period", "value"])
    dates = [c for c in df.columns if c[:2] in ("19", "20") and len(c) == 10]
    s = row.iloc[0][dates]
    return pd.DataFrame({"period": [d[:7] for d in dates], "value": pd.to_numeric(s.values, errors="coerce")}).dropna()


def acs(ctx, table, cbsa, col):
    rows = []
    for p in sorted((ctx.raw / "us_acs").glob(f"acs1y_*_{table}.csv")):
        year = p.name.split("_")[1]
        df = pd.read_csv(p, dtype=str)
        g = df[df["GEO_ID"].str.startswith("310") & df["GEO_ID"].str.endswith("US" + cbsa)]
        if g.empty or col not in g:
            continue
        rows.append({"period": year, "value": pd.to_numeric(g.iloc[0][col], errors="coerce"),
                     "notes": f"GEO_ID {g.iloc[0]['GEO_ID']}"})
    if not rows:
        raise RawMissing(f"us_acs {table} {cbsa}")
    return pd.DataFrame(rows).dropna(subset=["value"])


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        if source_id == "us_zillow":
            out[sid] = zillow(ctx, p["file"], p["region_id"])
        else:
            out[sid] = acs(ctx, p["table"], p["cbsa"], p["col"])
    return out
