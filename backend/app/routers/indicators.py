"""정량 지표 API — DB 캐시에서 읽고, 없으면 외부 API 로 한 번 채운다.

  GET  /indicators                 등록된 변수와 수집 상태·출처
  GET  /indicators/status          변수별 상태 + 최근 수집 기록 + 저장소 정보 (모니터)
  GET  /indicators/bundle          여러 변수를 한 번에 (Home·Overview 가 한 요청으로 받는다)
  GET  /indicators/{var}           변수 하나의 시계열 (factor_sample.json 과 같은 모양)
  POST /indicators/refresh         관리자 토큰으로 외부 API 수집 (GitHub Actions cron 이 하루 1회 호출)

응답 origin 값: 'db(cache)' = DB 에서 바로, 'api(R-ONE)' = DB 에 없어 방금 받아와 저장한 뒤 응답.
"""

import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_engine, storage_info
from app.schemas import BundleOut, IndicatorListOut, MetricOut, RefreshOut
from app.services import cache
from app.services.indicator_pipeline import (
    is_stale, load_metric, recent_logs, refresh_all, refresh_hours, refresh_variable, utc_now, variable_status,
)
from app.services.indicator_registry import SOURCES, enabled_specs, get_spec
from app.services.regions import SIDO
from app.db.models import IndicatorVariable

router = APIRouter(prefix="/indicators", tags=["indicators"])

MEMORY_TTL_SECONDS = 10 * 60      # 메모리 캐시: DB 조회 결과를 10분간 재사용
BROWSER_MAX_AGE_SECONDS = 60 * 60  # 브라우저·CDN: 1시간 (월 단위 자료라 충분하다)

KEY_ENV = {"R-ONE": "RONE_API_KEY", "ECOS": "ECOS_API_KEY", "KOSIS": "KOSIS_API_KEY"}


def _has_key(source: str) -> bool:
    return bool(os.getenv(KEY_ENV.get(source, ""), "").strip())


def _parse_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _etag(payload: dict) -> str:
    return '"' + hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:20] + '"'


def _cache_headers(response: Response, payload: dict, request: Request | None = None):
    tag = _etag(payload)
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = f"public, max-age={BROWSER_MAX_AGE_SECONDS}"
    if request is not None and request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": response.headers["Cache-Control"]})
    return None


def _background_refresh(var_ids: list[str]):
    with Session(get_engine()) as session:
        refresh_all(session, var_ids, trigger="background")
    cache.clear("indicator:")


def _metric_or_fetch(session: Session, spec, regions, start, background: BackgroundTasks | None):
    """DB 에서 읽고, 없으면 지금 받아온다(lazy). 오래됐으면 DB 값을 주고 뒤에서 갱신한다."""
    var = session.get(IndicatorVariable, spec.id)
    metric = load_metric(session, spec, regions, start)
    origin = "db(cache)"
    if metric is None and (var is None or var.last_period is None):  # DB 에 아예 없을 때만 외부 API 를 부른다
        if not _has_key(spec.source):
            return None, "missing"
        result = refresh_variable(session, spec, trigger="lazy", force=True)
        if result["status"] != "ok":
            raise HTTPException(status_code=502, detail=f"{spec.id} 자료를 가져오지 못했습니다: {result.get('error', '')}")
        metric = load_metric(session, spec, regions, start)
        origin = f"api({spec.source})"
        var = session.get(IndicatorVariable, spec.id)
    stale = is_stale(var)
    if stale and background is not None and _has_key(spec.source):
        background.add_task(_background_refresh, [spec.id])
    if metric is not None:
        metric["origin"], metric["stale"] = origin, stale
    return metric, origin


@router.get("", response_model=IndicatorListOut)
def list_indicators():
    """등록된 지표 목록과 수집 상태. services/indicator_registry.py 의 REGISTRY 에 추가하면 여기에 나타난다."""
    with Session(get_engine()) as session:
        rows = variable_status(session)
    return {"variables": rows, "sources": SOURCES, "refresh_hours": refresh_hours()}


@router.get("/status")
def status(limit: int = Query(default=50, ge=1, le=300)):
    """변수별 마지막 수집 시각·시점·오류와 최근 수집 로그. 발표용 '캐시 효과' 근거(duration_ms)도 여기 있다."""
    with Session(get_engine()) as session:
        return {"variables": variable_status(session), "logs": recent_logs(session, limit), "storage": storage_info(),
                "refresh_hours": refresh_hours(), "keys": {s: _has_key(s) for s in SOURCES}, "checked_at": utc_now()}


@router.get("/bundle", response_model=BundleOut)
def bundle(request: Request, response: Response, background: BackgroundTasks,
           vars: str | None = Query(default=None, description="쉼표 구분 변수 ID. 비우면 enabled 전체"),
           regions: str | None = Query(default=None, description="쉼표 구분 지역 (예: 서울,경기). 비우면 전체"),
           start: str | None = Query(default=None, description="시작 시점 'YYYY-MM' (예: 2021-01)")):
    """여러 변수의 시계열을 한 번에. Home·Overview 화면이 이 응답을 factor_sample.json 위에 덮어쓴다."""
    ids = _parse_list(vars) or [s.id for s in enabled_specs()]
    region_list = _parse_list(regions) or None
    key = f"indicator:bundle:{','.join(ids)}:{','.join(region_list or [])}:{start or ''}"

    def build():
        metrics, missing, fetched = [], [], False
        with Session(get_engine()) as session:
            for vid in ids:
                spec = get_spec(vid)
                if spec is None or not spec.enabled:
                    missing.append(vid)
                    continue
                try:
                    metric, origin = _metric_or_fetch(session, spec, region_list, start, background)
                except HTTPException:  # 한 변수의 수집 실패가 묶음 전체를 막지 않는다
                    metric = None
                if metric is None:
                    missing.append(vid)
                    continue
                fetched = fetched or origin.startswith("api")
                metrics.append(metric)
        return {"generated": utc_now(), "origin": "db(cache)+api" if fetched else "db(cache)",
                "regions": {"sido": SIDO, "nation": ["전국"]}, "metrics": metrics, "missing": missing}

    payload = cache.get_or_set(key, MEMORY_TTL_SECONDS, build)
    return _cache_headers(response, payload, request) or payload


@router.get("/{var}", response_model=MetricOut)
def get_indicator(var: str, request: Request, response: Response, background: BackgroundTasks,
                  regions: str | None = Query(default=None, description="쉼표 구분 지역. 비우면 전체"),
                  start: str | None = Query(default=None, description="시작 시점 'YYYY-MM'")):
    """변수 하나의 시계열. DB 에 없으면 외부 API 를 불러 채운 뒤 응답한다(origin='api(…)')."""
    spec = get_spec(var)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 지표입니다: {var}")
    if not spec.enabled:
        raise HTTPException(status_code=404, detail=f"아직 연동하지 않은 지표입니다: {var} (registry enabled=False)")
    region_list = _parse_list(regions) or None
    key = f"indicator:var:{spec.id}:{','.join(region_list or [])}:{start or ''}"

    def build():
        with Session(get_engine()) as session:
            metric, _ = _metric_or_fetch(session, spec, region_list, start, background)
        if metric is None:
            raise HTTPException(status_code=503, detail=f"{spec.id} 자료가 아직 없고 {KEY_ENV[spec.source]} 도 설정되지 않았습니다. 수집 후 다시 시도하세요.")
        return metric

    payload = cache.get_or_set(key, MEMORY_TTL_SECONDS, build)
    return _cache_headers(response, payload, request) or payload


@router.post("/refresh", response_model=RefreshOut)
def refresh(vars: str | None = Query(default=None, description="쉼표 구분 변수 ID. 비우면 enabled 전체"),
            force: bool = Query(default=False, description="신선해도 다시 받기"),
            x_admin_token: str | None = Header(default=None)):
    """관리자 토큰(X-Admin-Token)으로 외부 API 수집을 실행한다. 정책 수집과 같은 POLICY_ADMIN_TOKEN 을 쓴다."""
    expected = os.getenv("POLICY_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="관리자 수집 기능이 설정되지 않았습니다. 서버에서 POLICY_ADMIN_TOKEN을 설정하세요.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
    try:
        with Session(get_engine()) as session:
            result = refresh_all(session, _parse_list(vars) or None, force=force, trigger="admin")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"지표 수집 결과를 저장할 수 없습니다: {exc}")
    if result["status"] == "busy":
        raise HTTPException(status_code=409, detail="지표 수집이 이미 진행 중입니다.")
    cache.clear("indicator:")
    return result
