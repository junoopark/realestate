"""핵심 계산 검증 — 작은 인공 자료(이 파일 안에서만 사용, 실제 분석 데이터와 섞지 않음)."""

import numpy as np
import pandas as pd
import pytest

from src import metrics
from src.metrics import LEVEL_METRICS, annualize, rebase


def _ann(rows):
    df = pd.DataFrame(rows)
    defaults = dict(country_code="KOR", frequency="A", unit="", currency="KRW", geography_name="", dwelling_type="apartment",
                    tenure_type="", area_basis="60㎡", income_concept="", source_id="t", quality_flag="A", method="",
                    price_basis="nominal", n_periods=1, complete=True, notes="")
    for k, v in defaults.items():
        if k not in df:
            df[k] = v
    return df


def test_ptr_and_yield_are_reciprocal():
    p, r = 900_000_000.0, 1_750_000.0
    ptr = LEVEL_METRICS["PTR"][2](p, r)
    yld = LEVEL_METRICS["gross_yield"][2](r, p)
    assert ptr == pytest.approx(p / (12 * r))
    assert ptr * yld / 100 == pytest.approx(1.0)


def test_rent_to_income_uses_annual_rent():
    assert LEVEL_METRICS["RTI_hh"][2](2_000, 60_000) == pytest.approx(40.0)  # 12×2000/60000×100


def test_deposit_conversion_formula():
    # 환산 월 임대료 = 월세 + 보증금 × 연 환산율 / 12
    rent, deposit, rate = 1_000_000, 150_000_000, 4.8
    assert rent + deposit * rate / 100 / 12 == pytest.approx(1_600_000)


def test_cagr_and_cumulative_change():
    s = pd.Series([100.0, 110.0, 121.0, 133.1, 146.41, 161.051], index=range(2020, 2026))
    cum = (s.loc[2025] / s.loc[2020] - 1) * 100
    cagr = ((s.loc[2025] / s.loc[2020]) ** (1 / 5) - 1) * 100
    assert cum == pytest.approx(61.051)
    assert cagr == pytest.approx(10.0)


def test_pp_change_is_difference_not_ratio():
    a, b = 92.0, 88.1  # 가계신용/GDP(%) 3년 전 → 최근
    assert b - a == pytest.approx(-3.9)  # %p


def test_rebase_common_base_year():
    s = pd.Series([80.0, 100.0, 120.0], index=[2018, 2019, 2020])
    out = rebase(s, 2019)
    assert out.loc[2019] == pytest.approx(100.0)
    assert out.loc[2020] == pytest.approx(120.0)
    assert np.isnan(rebase(s, 2015)).all()  # 기준연도가 없으면 NA (임의 보간 안 함)


def test_relative_ptr_index_definition():
    price = pd.Series([100.0, 130.0], index=[2019, 2025])
    rent = pd.Series([100.0, 110.0], index=[2019, 2025])
    rel = rebase(price / rent, 2019)
    assert rel.loc[2025] == pytest.approx(130 / 110 * 100)


def test_annualize_flags_incomplete_years():
    obs = pd.DataFrame({
        "series_id": "x", "country_code": "KOR", "city_id": "seoul", "variable": "price_index", "frequency": "M",
        "unit": "index", "currency": "KRW", "geography_name": "", "dwelling_type": "", "tenure_type": "", "area_basis": "",
        "income_concept": "", "source_id": "t", "quality_flag": "A", "method": "", "price_basis": "nominal", "notes": "",
        "period": [f"2024-{m:02d}" for m in range(1, 13)] + ["2025-01", "2025-02"], "value": list(range(1, 13)) + [20, 22],
    })
    ann = annualize(obs, as_of_year=2026).set_index("year")
    assert ann.loc[2024, "complete"] and ann.loc[2024, "value"] == pytest.approx(6.5)
    assert not ann.loc[2025, "complete"]


def test_annualize_marks_current_year_annual_as_partial():
    obs = pd.DataFrame({
        "series_id": "y", "country_code": "KOR", "city_id": "seoul", "variable": "earnings", "frequency": "A", "unit": "",
        "currency": "KRW", "geography_name": "", "dwelling_type": "", "tenure_type": "", "area_basis": "", "income_concept": "",
        "source_id": "t", "quality_flag": "B", "method": "", "price_basis": "nominal", "notes": "",
        "period": ["2025", "2026"], "value": [1.0, 2.0],
    })
    ann = annualize(obs, as_of_year=2026).set_index("year")
    assert ann.loc[2025, "complete"] and not ann.loc[2026, "complete"]


def test_level_metrics_blocks_mismatched_dwelling_types():
    ann = _ann([
        dict(series_id="p", city_id="c1", variable="price_level", year=2024, value=600_000.0, dwelling_type="sfr_condo"),
        dict(series_id="r", city_id="c1", variable="rent_month", year=2024, value=3_000.0, dwelling_type="multifamily"),
        dict(series_id="fx", city_id="_national", variable="fx_usd", year=2024, value=1.0),
    ])
    roles = metrics.city_roles(ann, {"c1": {"country_code": "KOR"}})
    lv = metrics.level_metrics(roles, ann, {"c1": {"country_code": "KOR"}})
    ptr = lv[lv["metric"] == "PTR"].iloc[0]
    assert ptr["quality_flag"] == "C" and "주택유형 불일치" in ptr["notes"]


def test_city_roles_rejects_two_series_for_one_variable():
    ann = _ann([
        dict(series_id="a", city_id="c1", variable="price_level", year=2024, value=1.0),
        dict(series_id="b", city_id="c1", variable="price_level", year=2024, value=2.0),
    ])
    with pytest.raises(ValueError):
        metrics.city_roles(ann, {"c1": {"country_code": "KOR"}})
