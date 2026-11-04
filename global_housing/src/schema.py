"""표준 long format (설계서 8절)."""

from __future__ import annotations

import pandas as pd

COLUMNS = [
    "city_id", "country_code", "geography_name", "geography_code", "geography_type", "variable", "period",
    "frequency", "value", "unit", "currency", "price_basis", "dwelling_type", "tenure_type", "area_basis",
    "income_concept", "source_id", "source_url", "series_code", "release_date", "retrieved_at", "vintage",
    "method", "quality_flag", "notes", "series_id",
]

# series.yaml 에서 그대로 옮기는 필드
META_FIELDS = [
    "city_id", "country_code", "geography_name", "geography_code", "geography_type", "variable", "frequency", "unit",
    "currency", "price_basis", "dwelling_type", "tenure_type", "area_basis", "income_concept", "source_id",
    "source_url", "series_code", "method", "quality_flag", "notes",
]


def to_long(meta: dict, data: pd.DataFrame, retrieved_at: str = "", vintage: str = "") -> pd.DataFrame:
    """data: period, value 열(선택: release_date, notes). meta: series.yaml 한 항목."""
    if data is None or data.empty:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.DataFrame({"period": data["period"].astype(str), "value": pd.to_numeric(data["value"], errors="coerce")})
    for f in META_FIELDS:
        out[f] = data[f].values if f in data else meta.get(f, "")
    if "release_date" in data:
        out["release_date"] = data["release_date"].astype(str)
    else:
        out["release_date"] = meta.get("release_date", "")
    if "notes" in data:
        out["notes"] = data["notes"].fillna("").astype(str)
    out["retrieved_at"] = retrieved_at
    out["vintage"] = vintage or meta.get("vintage", "")
    out["series_id"] = meta["series_id"]
    scale = meta.get("scale")
    if scale:
        out["value"] = out["value"] * float(scale)
    out = out.dropna(subset=["value"])
    return out[COLUMNS]


def period_year(period: str) -> int:
    return int(str(period)[:4])
