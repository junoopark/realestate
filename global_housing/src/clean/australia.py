"""시드니 정제 — ABS SDMX CSV(라벨 포함)."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing


def _read(ctx, name):
    p = ctx.raw / "au_abs" / name
    if not p.exists():
        raise RawMissing(f"au_abs/{name}")
    return pd.read_csv(p, dtype=str)


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        df = _read(ctx, p["file"])
        if "measure_contains" in p:
            label = next(c for c in df.columns if c.lower().startswith("median/average"))
            g = df[(df["REGION"] == p["region"]) & df[label].str.contains(p["measure_contains"], regex=False)]
        else:
            g = df
            for k, v in p["filters"].items():
                g = g[g[k] == v]
        out[sid] = pd.DataFrame({"period": g["TIME_PERIOD"].astype(str),
                                 "value": pd.to_numeric(g["OBS_VALUE"], errors="coerce")}).dropna().drop_duplicates("period")
    return out
