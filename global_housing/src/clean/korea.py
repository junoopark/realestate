"""서울 정제 — R-ONE, 국토부 실거래(건별 → 연간 중위), KOSIS."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..netio import RawMissing

AREA_LO, AREA_HI, TARGET = 50.0, 70.0, 60.0


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def rone_series(ctx, table: str, region: str) -> pd.DataFrame:
    paths = list((ctx.raw / "kr_rone").glob(f"{table}_*.json"))
    if not paths:
        raise RawMissing(f"kr_rone {table}")
    rows = json.load(open(paths[0], encoding="utf-8"))
    df = pd.DataFrame(rows)
    df = df[df["CLS_FULLNM"] == region]
    out = pd.DataFrame({"period": df["WRTTIME_IDTFR_ID"].str[:4] + "-" + df["WRTTIME_IDTFR_ID"].str[4:6],
                        "value": pd.to_numeric(df["DTA_VAL"], errors="coerce")})
    return out.dropna().drop_duplicates("period").sort_values("period")


def conversion_rate_annual(ctx) -> pd.Series:
    """R-ONE 서울 아파트 전월세 전환율(%) 연평균 — 보증금 환산 기준값."""
    s = rone_series(ctx, "A_2024_00156", "서울")
    s["year"] = s["period"].str[:4].astype(int)
    return s.groupby("year")["value"].mean()


def rtms_contracts(ctx) -> dict[str, pd.DataFrame]:
    """실거래 건별 → 분석용 열만 정리. 매매: 해제 제외. 전월세: 보증금·월세(원)."""
    out = {}
    d = ctx.raw / "kr_rtms"
    trade = [pd.read_csv(p, dtype=str) for p in sorted(d.glob("seoul_apt_trade_*.csv.gz"))]
    rent = [pd.read_csv(p, dtype=str) for p in sorted(d.glob("seoul_apt_rent_*.csv.gz"))]
    if trade:
        t = pd.concat(trade, ignore_index=True)
        t = t[t.get("cdealType", pd.Series("", index=t.index)).fillna("").str.strip() != "O"]
        t = pd.DataFrame({
            "year": _num(t["dealYear"]).astype("Int64"), "month": _num(t["dealMonth"]).astype("Int64"),
            "gu": t["_gu"], "area": _num(t["excluUseAr"]), "price": _num(t["dealAmount"]) * 10_000,
            "build_year": _num(t.get("buildYear", pd.Series(np.nan, index=t.index))),
        }).dropna(subset=["year", "area", "price"])
        t = t[(t["area"] > 0) & (t["price"] > 0)]
        t["price_sqm"] = t["price"] / t["area"]
        out["trade"] = t
    if rent:
        r = pd.concat(rent, ignore_index=True)
        r = pd.DataFrame({
            "year": _num(r["dealYear"]).astype("Int64"), "month": _num(r["dealMonth"]).astype("Int64"),
            "gu": r["_gu"], "area": _num(r["excluUseAr"]),
            "deposit": _num(r["deposit"]) * 10_000, "rent": _num(r["monthlyRent"]) * 10_000,
            "contract_type": r.get("contractType", pd.Series("", index=r.index)).fillna("").str.strip(),
        }).dropna(subset=["year", "area", "deposit", "rent"])
        r = r[r["area"] > 0]
        out["rent"] = r
    return out


def rtms_annual(ctx, contracts, stat: str, rates: pd.Series) -> pd.DataFrame:
    rows = []
    if stat in ("price_sqm", "price_60"):
        t = contracts.get("trade")
        if t is None:
            return pd.DataFrame()
        band = t[(t["area"] >= AREA_LO) & (t["area"] <= AREA_HI)]
        for y, g in band.groupby("year"):
            v = g["price_sqm"].median()
            rows.append({"period": str(y), "value": v if stat == "price_sqm" else v * TARGET,
                         "notes": f"거래 {len(g)}건(전용 {AREA_LO:.0f}~{AREA_HI:.0f}㎡)"})
        return pd.DataFrame(rows)
    r = contracts.get("rent")
    if r is None:
        return pd.DataFrame()
    band = r[(r["area"] >= AREA_LO) & (r["area"] <= AREA_HI) & (r["rent"] > 0)]
    for y, g in band.groupby("year"):
        if stat == "rent_cash_60":
            v = (g["rent"] / g["area"]).median() * TARGET
            note = f"월세 계약 {len(g)}건"
        elif stat == "deposit_60":
            v = (g["deposit"] / g["area"]).median() * TARGET
            note = f"월세 계약 {len(g)}건"
        else:
            rate = rates.get(int(y))
            if rate is None or np.isnan(rate):
                continue
            v = ((g["rent"] + g["deposit"] * rate / 100 / 12) / g["area"]).median() * TARGET
            note = f"월세 계약 {len(g)}건, 환산율 {rate:.2f}%"
        rows.append({"period": str(y), "value": v, "notes": note})
    return pd.DataFrame(rows)


def kosis_series(ctx, file: str, region: str, item: str, lag: int = 0) -> pd.DataFrame:
    path = ctx.raw / "kr_kosis" / f"{file}.json"
    if not path.exists():
        raise RawMissing(f"kr_kosis {file}")
    df = pd.DataFrame(json.load(open(path, encoding="utf-8")))
    df = df[df["C1_NM"] == region]
    name = df["ITM_NM"].fillna("") + " " + df.get("C2_NM", pd.Series("", index=df.index)).fillna("")
    df = df[name.str.contains(item, regex=False)]
    if "ITM_NM" in df and (df["ITM_NM"] == "전가구 평균").any():
        df = df[df["ITM_NM"] == "전가구 평균"]
    out = pd.DataFrame({"period": (df["PRD_DE"].astype(int) - lag).astype(str),
                        "value": pd.to_numeric(df["DT"], errors="coerce"),
                        "release_date": df.get("LST_CHN_DE", pd.Series("", index=df.index)).fillna("")})
    if lag:
        out["notes"] = "조사연도 " + df["PRD_DE"].astype(str).values + " (전년도 소득)"
    return out.dropna(subset=["value"]).drop_duplicates("period").sort_values("period")


BRACKETS = {"10": (0, 1000), "20": (1000, 3000), "30": (3000, 5000), "40": (5000, 7000), "50": (7000, 10000),
            "60": (10000, None)}


def national_median_ratio(ctx) -> pd.DataFrame:
    """전국 가구소득 중위(소득구간 분포의 선형 보간) ÷ 전국 평균 경상소득. 기간 = 소득연도(조사연도-1)."""
    p = ctx.raw / "kr_kosis" / "DT_1HDAAB03.json"
    if not p.exists():
        return pd.DataFrame()
    d = pd.DataFrame(json.load(open(p, encoding="utf-8")))
    d = d[(d["C1"] == "000") & d["C2"].isin(BRACKETS)]
    d["share"] = pd.to_numeric(d["DT"], errors="coerce")
    mean = kosis_series(ctx, "INH_1HD_AAA01_01", "전국", "경상소득", lag=1).set_index("period")["value"]
    rows = []
    for prd, g in d.groupby("PRD_DE"):
        g = g.sort_values("C2")
        cum = 0.0
        med = np.nan
        for _, r in g.iterrows():
            lo, hi = BRACKETS[r["C2"]]
            if cum + r["share"] >= 50 and hi is not None:
                med = lo + (50 - cum) / r["share"] * (hi - lo)
                break
            cum += r["share"]
        y = str(int(prd) - 1)
        if y in mean.index and not np.isnan(med):
            rows.append({"period": y, "median": med, "mean": mean[y], "ratio": med / mean[y]})
    return pd.DataFrame(rows)


def clean(ctx, metas, source_id):
    out = {}
    if source_id == "kr_rone":
        for sid, m in metas.items():
            out[sid] = rone_series(ctx, m["parse"]["table"], m["parse"]["region"])
    elif source_id == "kr_rtms":
        contracts = rtms_contracts(ctx)
        rates = conversion_rate_annual(ctx)
        for sid, m in metas.items():
            out[sid] = rtms_annual(ctx, contracts, m["parse"]["stat"], rates)
        # 보증금 민감도·신규/갱신 분해에 쓰도록 건별 정리본을 남긴다(분석 산출물, 원자료 아님)
        if "rent" in contracts:
            ctx.interim.mkdir(parents=True, exist_ok=True)
            contracts["rent"].to_parquet(ctx.interim / "seoul_rtms_rent_contracts.parquet", index=False)
        if "trade" in contracts:
            contracts["trade"].to_parquet(ctx.interim / "seoul_rtms_trade_contracts.parquet", index=False)
    elif source_id == "kr_kosis":
        for sid, m in metas.items():
            p = m["parse"]
            if p.get("derive") == "median_estimate":
                base = kosis_series(ctx, p["file"], p["region"], p["item"], p.get("lag", 0)).set_index("period")
                ratio = national_median_ratio(ctx).set_index("period")
                j = base.join(ratio, how="inner")
                out[sid] = pd.DataFrame({"period": j.index, "value": j["value"] * j["ratio"],
                                         "notes": [f"서울 평균 {v:,.0f}만원 × 전국 중위/평균 {r:.3f} (전국 중위 {md:,.0f}만원 보간)"
                                                   for v, r, md in zip(j["value"], j["ratio"], j["median"])]})
                continue
            out[sid] = kosis_series(ctx, p["file"], p["region"], p["item"], p.get("lag", 0))
    return out
