"""정량 지표 API. 데이터사전 변수 52개의 시계열을 DB(indicator_variables · indicator_series)에서 읽는다.

  GET /indicators                      변수 목록 (항목·지역·기간 요약) + 저장소 상태
  GET /indicators/{id}                 변수 하나의 시계열 전체: items -> 항목 -> regions -> 지역 -> {freq, dates, values}
  GET /indicators/{id}?item=&region=   그 항목·지역 계열만

응답 모양은 frontend/data/indicators/*.json 과 같아서 화면은 정적 파일과 API 를 같은 코드로 읽는다.
"""

from fastapi import APIRouter, HTTPException, Query

from app.db.session import storage_info
from app.services import indicator_store

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("")
def list_indicators():
    try:
        variables, updated_at, from_db = indicator_store.list_variables()
    except Exception:
        index = indicator_store.read_json("index.json")
        if not index:
            raise HTTPException(status_code=503, detail="지표 저장소에 연결할 수 없고 정적 자료도 없습니다.")
        variables, updated_at, from_db = index["variables"], index.get("generated_at"), False
    return {"count": len(variables), "updated_at": updated_at, "variables": variables,
            "storage": storage_info(from_db) | {"source": "database" if from_db else "static_json"}}


@router.get("/{variable_id}")
def get_indicator(variable_id: str, item: str | None = Query(default=None, max_length=100), region: str | None = Query(default=None, max_length=30)):
    try:
        payload, from_db = indicator_store.get_variable(variable_id, item, region)
    except Exception:
        payload, from_db = indicator_store.get_variable_from_files(variable_id, item, region), False
    if payload is None:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 지표입니다: {variable_id}")
    if (item or region) and not payload["items"]:
        raise HTTPException(status_code=404, detail="해당 항목·지역의 계열이 없습니다.")
    return payload | {"storage": storage_info(from_db) | {"source": "database" if from_db else "static_json"}}
