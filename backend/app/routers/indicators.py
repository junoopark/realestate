from fastapi import APIRouter, HTTPException

from app.schemas import IndicatorInfo, IndicatorSeries
from app.services.cache import get_or_set
from app.services.indicators import CATALOG, fetch_series

router = APIRouter(prefix="/indicators", tags=["indicators"])

CACHE_TTL_SECONDS = 12 * 60 * 60  # 부동산 지표는 대부분 주·월 단위라 12시간 캐시로 충분하다


@router.get("", response_model=list[IndicatorInfo])
def list_indicators():
    """등록된 지표 목록. services/indicators.py 의 CATALOG 에 추가하면 여기에 나타난다."""
    return list(CATALOG.values())


@router.get("/{key}", response_model=IndicatorSeries)
def get_indicator(key: str):
    if key not in CATALOG:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 지표입니다: {key}")
    try:
        return get_or_set(f"indicator:{key}", CACHE_TTL_SECONDS, lambda: fetch_series(key))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"지표 데이터를 가져오지 못했습니다: {exc}")
