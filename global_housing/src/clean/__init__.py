"""정제: 원자료(data/raw) → 표준 long format (data/interim/observations_long.*).

각 출처 모듈은 clean(ctx, metas) → {series_id: DataFrame(period, value[, country_code, release_date, notes])} 를 돌려준다.
출처 하나가 실패해도 다른 출처는 계속하고, 실패 이유를 clean_log 에 남긴다(자료 없음 = NA, 0 으로 채우지 않음).
수동 입력(data/manual_inputs/manual_observations.csv)이 있으면 함께 읽는다.
"""

from __future__ import annotations

import csv
import traceback
from importlib import import_module

import pandas as pd

from ..netio import Manifest, RawMissing
from ..schema import COLUMNS, to_long

MODULES = {
    "kr_rone": "korea", "kr_rtms": "korea", "kr_kosis": "korea",
    "uk_hpi": "uk", "uk_ons_pipr": "uk", "uk_nomis_ashe": "uk",
    "hk_rvd": "hongkong", "hk_censtatd": "hongkong",
    "sg_datagov": "singapore",
    "us_zillow": "usa", "us_acs": "usa",
    "ca_statcan": "canada",
    "au_abs": "australia",
    "fr_insee": "france", "fr_dvf": "france", "fr_loyers": "france",
    "jp_mlit": "japan",
    "wb_wdi": "intl", "bis": "intl",
}
MANUAL_FILE = "manual_observations.csv"


def _retrieved(manifest: Manifest, source_id: str) -> str:
    times = [r["retrieved_at"] for (sid, _), r in manifest.rows.items() if sid == source_id and r.get("retrieved_at")]
    return max(times) if times else ""


def read_manual(ctx) -> pd.DataFrame:
    path = ctx.manual / MANUAL_FILE
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    need = {"city_id", "variable", "period", "value", "unit", "source_id", "source_url"}
    miss = need - set(df.columns)
    if miss:
        raise ValueError(f"수동 입력 파일에 필수 열이 없음: {sorted(miss)}")
    for c in COLUMNS:
        if c not in df:
            df[c] = ""
    df["quality_flag"] = df["quality_flag"].replace("", "C")
    df["method"] = df["method"].replace("", "수동 입력")
    df["series_id"] = df["series_id"].where(df["series_id"] != "", "manual_" + df["city_id"] + "_" + df["variable"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[COLUMNS].dropna(subset=["value"])


def clean_all(ctx, log):
    manifest = Manifest(ctx.raw / "_manifest.csv")
    frames, logs = [], []
    by_source: dict[str, dict] = {}
    for sid, meta in ctx.series.items():
        by_source.setdefault(meta["source_id"], {})[sid] = meta
    for source_id, metas in by_source.items():
        mod = MODULES.get(source_id)
        if not mod:
            for sid in metas:
                logs.append({"series_id": sid, "source_id": source_id, "status": "no_cleaner", "n": 0, "first": "",
                             "last": "", "message": "정제 모듈 없음"})
            continue
        try:
            out = import_module(f"{__name__}.{mod}").clean(ctx, metas, source_id)
            err = ""
        except RawMissing as exc:
            out, err = {}, f"원자료 없음: {exc}"
        except Exception as exc:  # 형식 변경 등
            out, err = {}, f"{type(exc).__name__}: {exc}"
            traceback.print_exc(limit=4)
        ret = _retrieved(manifest, source_id)
        for sid, meta in metas.items():
            data = out.get(sid)
            if data is None or data.empty:
                logs.append({"series_id": sid, "source_id": source_id, "status": "missing", "n": 0, "first": "",
                             "last": "", "message": err or "정제 결과 없음"})
                continue
            long = to_long(meta, data, retrieved_at=ret)
            frames.append(long)
            logs.append({"series_id": sid, "source_id": source_id, "status": "ok", "n": len(long),
                         "first": long["period"].min(), "last": long["period"].max(), "message": ""})
        log(f"  {source_id}: {sum(1 for s in metas if out.get(s) is not None and not out.get(s).empty)}/{len(metas)} 계열"
            + (f" — {err[:150]}" if err else ""))
    manual = read_manual(ctx)
    if not manual.empty:
        frames.append(manual)
        log(f"  manual: {len(manual)}행")
    obs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    ctx.interim.mkdir(parents=True, exist_ok=True)
    obs.to_csv(ctx.interim / "observations_long.csv", index=False, encoding="utf-8-sig")
    obs.to_parquet(ctx.interim / "observations_long.parquet", index=False)
    with open(ctx.interim / "clean_log.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["series_id", "source_id", "status", "n", "first", "last", "message"])
        w.writeheader()
        w.writerows(logs)
    log(f"  관측치 {len(obs)}행, 계열 {obs['series_id'].nunique() if len(obs) else 0}개 → data/interim/observations_long.*")
    return obs
