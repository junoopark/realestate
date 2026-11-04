"""캐나다 정제 — StatCan 표 부분집합. 11-10-0190 은 불변달러 → 캐나다 CPI(전체, 연평균)로 명목 환산."""

from __future__ import annotations

import pandas as pd

from ..netio import RawMissing


def _table(ctx, pid):
    p = ctx.raw / "ca_statcan" / f"{pid}_canada_toronto_vancouver.csv.gz"
    if not p.exists():
        raise RawMissing(f"ca_statcan {pid}")
    return pd.read_csv(p, dtype=str)


def canada_cpi_annual(ctx) -> pd.Series:
    df = _table(ctx, "18100004")
    g = df[(df["GEO"] == "Canada") & (df["Products and product groups"] == "All-items")].copy()
    g["year"] = g["REF_DATE"].str[:4].astype(int)
    g["v"] = pd.to_numeric(g["VALUE"], errors="coerce")
    cnt = g.groupby("year")["v"].count()
    return g.groupby("year")["v"].mean()[cnt == 12]


def clean(ctx, metas, source_id):
    out = {}
    cache = {}
    cpi = None
    for sid, m in metas.items():
        p = m["parse"]
        df = cache.setdefault(p["table"], _table(ctx, p["table"]))
        g = df[df["GEO"] == p["geo"]]
        for k, v in p["filters"].items():
            g = g[g[k] == v]
        res = pd.DataFrame({"period": g["REF_DATE"].astype(str).str[:7], "value": pd.to_numeric(g["VALUE"], errors="coerce")})
        res = res.dropna()
        if p.get("real_base"):
            cpi = canada_cpi_annual(ctx) if cpi is None else cpi
            base = cpi.get(int(p["real_base"]))
            yr = res["period"].astype(int)
            factor = yr.map(lambda y: cpi.get(y, float("nan")) / base)
            res["value"] = res["value"] * factor.values
            res["notes"] = f"{p['real_base']}년 불변달러 × (CPI_t / CPI_{p['real_base']})"
            res = res.dropna(subset=["value"])
        out[sid] = res
    return out
