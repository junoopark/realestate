"""싱가포르 정제 — URA 지수, HDB 재판매(건별 → 연간 중위), HDB 임대료, 소득."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing

AREA_LO, AREA_HI, TARGET = 50.0, 70.0, 60.0


def _read(ctx, name):
    p = ctx.raw / "sg_datagov" / name
    if not p.exists():
        raise RawMissing(f"sg_datagov/{name}")
    return pd.read_csv(p)


def _wide_row(df, label_col, label):
    row = df[df[label_col].astype(str).str.strip() == label]
    if row.empty:
        return pd.DataFrame(columns=["period", "value"])
    s = row.iloc[0].drop(labels=[label_col, "_id"], errors="ignore")
    out = pd.DataFrame({"period": s.index.astype(str), "value": pd.to_numeric(s.values, errors="coerce")})
    return out[out["period"].str.fullmatch(r"\d{4}")].dropna()


def hdb_resale(ctx, stat):
    df = _read(ctx, "hdb_resale_prices_2017on.csv.gz")
    df["year"] = df["month"].str[:4]
    band = df[(df["floor_area_sqm"] >= AREA_LO) & (df["floor_area_sqm"] <= AREA_HI)].copy()
    band["psm"] = band["resale_price"] / band["floor_area_sqm"]
    rows = []
    for y, g in band.groupby("year"):
        v = g["psm"].median()
        rows.append({"period": y, "value": v if stat == "price_sqm" else v * TARGET,
                     "notes": f"거래 {len(g)}건(50~70㎡); 3-room 바닥면적 중위 "
                              f"{df.loc[(df['year'] == y) & (df['flat_type'] == '3 ROOM'), 'floor_area_sqm'].median():.0f}㎡"})
    return pd.DataFrame(rows)


def hdb_rent(ctx, file, flat_type):
    df = _read(ctx, file)
    df = df[df["flat_type"] == flat_type].copy()
    df["value"] = pd.to_numeric(df["median_rent"], errors="coerce")
    df["year"] = df["quarter"].str[:4]
    by_town = df.dropna(subset=["value"]).groupby(["year", "town"])["value"].mean().reset_index()
    nq = df.dropna(subset=["value"]).groupby("year")["quarter"].nunique()
    rows = []
    for y, g in by_town.groupby("year"):
        rows.append({"period": y, "value": g["value"].median(), "notes": f"타운 {len(g)}개, 분기 {nq.get(y, 0)}개"})
    return pd.DataFrame(rows)


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        if "stat" in p:
            out[sid] = hdb_resale(ctx, p["stat"])
        elif "flat_type" in p:
            out[sid] = hdb_rent(ctx, p["file"], p["flat_type"])
        elif "row" in p:
            df = _read(ctx, p["file"])
            out[sid] = _wide_row(df, "DataSeries", p["row"])
        else:
            df = _read(ctx, p["file"])
            for k, v in p["filters"].items():
                df = df[df[k] == v]
            out[sid] = pd.DataFrame({"period": df["quarter"].astype(str),
                                     "value": pd.to_numeric(df["index"], errors="coerce")}).dropna()
    return out
