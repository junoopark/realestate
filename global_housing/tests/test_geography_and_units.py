"""지역·단위·설정 정합성 검사 — 실제 설정 파일을 읽어 규칙 위반을 막는다."""

import pandas as pd
import pytest

from src.config import load_context
from src.schema import COLUMNS, to_long

CITY_VARS = {"price_index", "rent_index", "price_level", "rent_month", "price_sqm", "rent_sqm_month", "hh_income", "earnings"}


@pytest.fixture(scope="module")
def ctx():
    return load_context("configs/project.yaml", offline=True)


def test_seoul_is_in_sample(ctx):
    assert "seoul" in ctx.cities
    assert len(ctx.cities) >= 10


def test_city_variables_never_use_country_geography(ctx):
    for sid, m in ctx.series.items():
        if m["variable"] in CITY_VARS:
            assert m.get("geography_type") != "country", f"{sid}: 국가 범위 계열을 도시 변수로 씀"


def test_national_variables_are_country(ctx):
    for sid, m in ctx.series.items():
        if m["variable"].startswith("price_index_national"):
            assert m.get("geography_type") == "country", sid


def test_level_series_declare_area_basis(ctx):
    for sid, m in ctx.series.items():
        if m["variable"] in {"price_level", "rent_month", "price_sqm", "rent_sqm_month"}:
            assert m.get("area_basis"), f"{sid}: 면적 기준(area_basis) 없음"


def test_income_series_declare_concept(ctx):
    for sid, m in ctx.series.items():
        if m["variable"] in {"hh_income", "earnings", "hh_income_median_est", "hh_income_renter"}:
            assert m.get("income_concept"), f"{sid}: income_concept 없음"


def test_one_series_per_role_variable_per_city(ctx):
    seen = {}
    for sid, m in ctx.series.items():
        if m["city_id"] == "_national":
            continue
        key = (m["city_id"], m["variable"])
        assert key not in seen, f"{key}: {seen.get(key)} 와 {sid} 가 같은 변수"
        seen[key] = sid


def test_household_credit_is_not_mortgage(ctx):
    for sid, m in ctx.series.items():
        if m["source_id"] == "bis" and "credit" in m["variable"]:
            assert m["variable"] != "mortgage_to_gdp"


def test_jeonse_ratio_is_not_ptr(ctx):
    for sid, m in ctx.series.items():
        if "전세가율" in (m.get("method") or "") or "jeonse" in sid:
            assert m["variable"] != "PTR"


def test_rent_series_are_monthly_units(ctx):
    for sid, m in ctx.series.items():
        if m["variable"] == "rent_month":
            assert m["unit"].endswith("/month"), f"{sid}: 월 임대료 단위가 아님 ({m['unit']})"


def test_income_series_are_annual_units(ctx):
    for sid, m in ctx.series.items():
        if m["variable"] in {"hh_income", "earnings"}:
            assert m["unit"].endswith("/year"), f"{sid}: 연소득 단위가 아님 ({m['unit']})"


def test_to_long_applies_scale_and_schema():
    meta = {"series_id": "t", "city_id": "seoul", "variable": "rent_month", "scale": 1000, "unit": "KRW/month"}
    out = to_long(meta, pd.DataFrame({"period": ["2024"], "value": [1500]}))
    assert list(out.columns) == COLUMNS
    assert out["value"].iloc[0] == 1_500_000


def test_secret_params_are_masked():
    from src.netio import Fetcher

    s = Fetcher._mask({"KEY": "abc123", "STATBL_ID": "A"}, ("KEY",))
    assert "abc123" not in s and "KEY=***" in s
