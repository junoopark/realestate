"""홍콩 정제 — RVD 연간 시트(위치 기반), C&SD JSON."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..netio import RawMissing

# 연간 시트 위치: his_data_1·2 = 'Annual(from 99)' (5번째), his_data_3·4 = 'Annual' (3번째)
ANNUAL_SHEET = {1: 4, 2: 4, 3: 2, 4: 2}
YEAR_COL = 2


def rvd_annual(ctx, n: int, cols: list[int]) -> pd.DataFrame:
    p = ctx.raw / "hk_rvd" / f"his_data_{n}.xls"
    if not p.exists():
        raise RawMissing(f"hk_rvd his_data_{n}.xls")
    x = pd.ExcelFile(p)
    df = pd.read_excel(p, sheet_name=x.sheet_names[ANNUAL_SHEET[n]], header=None)
    yrs = pd.to_numeric(df[YEAR_COL], errors="coerce")
    rows = df[(yrs >= 1979) & (yrs <= 2100)]
    vals = rows[cols].apply(pd.to_numeric, errors="coerce")
    complete = vals.notna().all(axis=1)
    out = pd.DataFrame({"period": yrs[rows.index].astype(int).astype(str), "value": vals.mean(axis=1).where(complete)})
    if len(cols) > 1:
        out["notes"] = "홍콩섬·구룡·신계 단순평균: " + vals.round(0).astype("Int64").astype(str).agg(" / ".join, axis=1)
    return out.dropna(subset=["value"])


def csd(ctx, table: str, filters: dict) -> pd.DataFrame:
    p = ctx.raw / "hk_censtatd" / f"{table}.json"
    if not p.exists():
        raise RawMissing(f"hk_censtatd {table}")
    ds = pd.DataFrame(json.load(open(p, encoding="utf-8"))["dataSet"])
    g = ds[ds["freq"] == "Y"]
    for k, v in filters.items():
        g = g[g[k] == v]
    return pd.DataFrame({"period": g["period"].astype(str), "value": pd.to_numeric(g["figure"], errors="coerce")}).dropna()


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        if source_id == "hk_rvd":
            cols = p.get("cols") or [p["col"]]
            out[sid] = rvd_annual(ctx, int(p["file"]), cols)
        else:
            out[sid] = csd(ctx, p["table"], p["filters"])
    return out
