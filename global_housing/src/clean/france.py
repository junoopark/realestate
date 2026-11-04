"""파리 정제 — INSEE BDM(SDMX XML), DVF(거래 건별 → 연간 중위), Carte des loyers."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..netio import RawMissing

AREA_LO, AREA_HI, TARGET = 50.0, 70.0, 60.0


def insee(ctx, idbank):
    p = ctx.raw / "fr_insee" / "insee_bdm_paris_series.xml"
    if not p.exists():
        raise RawMissing("fr_insee xml")
    x = p.read_text(encoding="utf-8")
    m = re.search(rf'<Series [^>]*IDBANK="{idbank}"[^>]*>(.*?)</Series>', x, re.S)
    if not m:
        return pd.DataFrame(columns=["period", "value"])
    head = re.search(rf'<Series [^>]*IDBANK="{idbank}"[^>]*>', x).group(0)
    upd = re.search(r'LAST_UPDATE="([^"]+)"', head)
    obs = re.findall(r'TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"(?: OBS_STATUS="([^"]*)")?', m.group(1))
    df = pd.DataFrame(obs, columns=["period", "value", "status"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["release_date"] = upd.group(1) if upd else ""
    df["notes"] = df["status"].map({"P": "잠정", "A": ""}).fillna("")
    return df[["period", "value", "release_date", "notes"]].dropna(subset=["value"]).sort_values("period")


def dvf(ctx, stat):
    rows = []
    for p in sorted((ctx.raw / "fr_dvf").glob("dvf_75_*_ventes_appartements.csv.gz")):
        year = p.name.split("_")[2]
        df = pd.read_csv(p, dtype=str, low_memory=False)
        df["surface"] = pd.to_numeric(df["surface_reelle_bati"], errors="coerce")
        df["price"] = pd.to_numeric(df["valeur_fonciere"], errors="coerce")
        # 같은 부동산이 필지별로 여러 행이 되는 경우를 하나로 — (거래, 유형, 면적, 1번 로트)
        d = df.drop_duplicates(["id_mutation", "type_local", "surface_reelle_bati", "lot1_numero"])
        kinds = d.groupby("id_mutation")["type_local"].agg(lambda s: tuple(sorted(s.fillna(""))))
        single = kinds[kinds == ("Appartement",)].index  # 아파트 1채만(주차장·창고·다른 호실 없음)
        a = d[d["id_mutation"].isin(single) & (d["type_local"] == "Appartement")]
        a = a[(a["surface"] >= AREA_LO) & (a["surface"] <= AREA_HI) & (a["price"] > 0)]
        psm = a["price"] / a["surface"]
        psm = psm[(psm > 1000) & (psm < 60000)]  # 명백한 오기(지분 거래 등) 제거
        v = psm.median()
        rows.append({"period": year, "value": v if stat == "price_sqm" else v * TARGET,
                     "notes": f"거래 {len(psm)}건(아파트 단독 매매, 실면적 50~70㎡)"})
    if not rows:
        raise RawMissing("fr_dvf")
    return pd.DataFrame(rows)


def loyers(ctx):
    rows = []
    for p in sorted((ctx.raw / "fr_loyers").glob("loyers_appartements_*_paris.csv")):
        year = p.name.split("_")[2]
        df = pd.read_csv(p, dtype=str)
        v = pd.to_numeric(df["loypredm2"].str.replace(",", "."), errors="coerce")
        w = pd.to_numeric(df["nbobs_com"], errors="coerce")
        ok = v.notna() & w.notna()
        rows.append({"period": year, "value": float(np.average(v[ok], weights=w[ok])),
                     "notes": f"{ok.sum()}개 구, 광고 {int(w[ok].sum())}건 가중"})
    if not rows:
        raise RawMissing("fr_loyers")
    return pd.DataFrame(rows)


def clean(ctx, metas, source_id):
    out = {}
    for sid, m in metas.items():
        p = m["parse"]
        if source_id == "fr_insee":
            out[sid] = insee(ctx, p["idbank"])
        elif source_id == "fr_dvf":
            out[sid] = dvf(ctx, p["stat"])
        else:
            out[sid] = loyers(ctx)
    return out
