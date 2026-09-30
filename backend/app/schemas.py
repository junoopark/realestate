"""API 입출력의 모양 (Pydantic). 저장 방식은 db/models.py 가 맡는다."""

from datetime import date

from pydantic import BaseModel


class IndicatorInfo(BaseModel):
    key: str        # 식별자 (예: "hpi_seoul")
    label: str      # 화면에 보일 이름 (예: "서울 아파트 매매가격지수")
    source: str     # 출처 (예: "ECOS", "FRED")
    freq: str       # 주기: "D" · "M" · "Q" · "A"
    unit: str       # 단위 (예: "지수", "%", "건")


class IndicatorPoint(BaseModel):
    date: date
    value: float


class IndicatorSeries(BaseModel):
    info: IndicatorInfo
    points: list[IndicatorPoint]
