"""정량 지표 API — DB 캐시에서 읽고, 없으면 외부 API 로 한 번 채운다.

  GET  /indicators                 등록된 변수와 수집 상태·출처
  GET  /indicators/status          변수별 상태 + 최근 수집 기록 + 저장소 정보 (모니터)
  GET  /indicators/bundle          여러 변수를 한 번에. set=live(기본): Open API 수집 변수만 · set=all: 기본 패널 51개 변수 전체 + 실제 수집값
  GET  /indicators/{var}           변수 하나의 시계열 (factor_sample.json 과 같은 모양). Open API 변수가 아니면 기본 패널에서
  POST /indicators/refresh         관리자 토큰으로 외부 API 수집 (GitHub Actions cron 이 하루 1회 호출)

응답 origin 값: 'db(cache)' = Open API 수집값을 DB 에서, 'db(panel)' = 기본 패널(전처리본 적재분)을 DB 에서,
'api(R-ONE)' = DB 에 없어 방금 받아와 저장한 뒤 응답.
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
from app.services.indicator_panel import panel_meta, panel_metrics, panel_status, pick_metric
from app.services.indicator_registry import SOURCES, enabled_specs, get_spec
from app.services.regions import SIDO
from app.db.models import IndicatorVariable

router = APIRouter(prefix="/indicators", tags=["indicators"])

MEMORY_TTL_SECONDS = 10 * 60      # ③ 메모리 캐시: DB 조회 결과를 10분간 재사용
# ① 브라우저: 5분. 같은 사용자가 화면을 오가도 요청이 나가지 않는다
BROWSER_CACHE = "public, max-age=300"
# ② CDN(Vercel, vercel.json 의 /api rewrite): 1시간 신선 → 이후 1일은 보관본을 먼저 주고 뒤에서 갱신(Render 가 잠들어 있어도
#    사용자는 기다리지 않는다) → Render 오류·장애 때는 7일까지 보관본으로 응답. 월 단위 통계라 충분하다.
CDN_CACHE = "public, max-age=3600, stale-while-revalidate=86400, stale-if-error=604800"
CACHE_TAG = "indicators"           # Vercel 에서 태그 단위로 캐시를 비울 때 쓴다

KEY_ENV = {"R-ONE": "RONE_API_KEY", "ECOS": "ECOS_API_KEY", "KOSIS": "KOSIS_API_KEY"}


def _has_key(source: str) -> bool:
    return bool(os.getenv(KEY_ENV.get(source, ""), "").strip())


def _parse_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _etag(payload: dict) -> str:
    return '"' + hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:20] + '"'


def _cache_headers(response: Response, payload: dict, request: Request | None = None):
    tag = _etag(payload)
    headers = {"ETag": tag, "Cache-Control": BROWSER_CACHE, "CDN-Cache-Control": CDN_CACHE, "Vercel-Cache-Tag": CACHE_TAG}
    response.headers.update(headers)
    if request is not None and request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return None


def _no_store(response: Response):
    """수집 모니터·관리자 수집 응답은 어느 층에도 캐시하지 않는다(항상 지금 상태)."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["CDN-Cache-Control"] = "no-store"


def _background_refresh(var_ids: list[str]):
    with Session(get_engine()) as session:
        refresh_all(session, var_ids, trigger="background")
    cache.clear("indicator:")


def _metric_or_fetch(session: Session, spec, regions, start, background: BackgroundTasks | None, allow_fetch: bool = True):
    """DB 에서 읽고, 없으면 지금 받아온다(lazy). 오래됐으면 DB 값을 주고 뒤에서 갱신한다.
    allow_fetch=False 면 기다리지 않고 뒤에서만 받는다(기본 패널로 대신 응답할 수 있을 때)."""
    var = session.get(IndicatorVariable, spec.id)
    metric = load_metric(session, spec, regions, start)
    origin = "db(cache)"
    if metric is None and (var is None or var.last_period is None):  # DB 에 아예 없을 때만 외부 API 를 부른다
        if not _has_key(spec.source):
            return None, "missing"
        if not allow_fetch:
            if background is not None:
                background.add_task(_background_refresh, [spec.id])
            return None, "pending"
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
def status(response: Response, limit: int = Query(default=50, ge=1, le=300)):
    """변수별 마지막 수집 시각·시점·오류와 최근 수집 로그. 발표용 '캐시 효과' 근거(duration_ms)도 여기 있다."""
    _no_store(response)
    with Session(get_engine()) as session:
        return {"variables": variable_status(session), "panel": panel_status(session), "logs": recent_logs(session, limit), "storage": storage_info(),
                "refresh_hours": refresh_hours(), "keys": {s: _has_key(s) for s in SOURCES}, "checked_at": utc_now()}


@router.get("/bundle", response_model=BundleOut)
def bundle(request: Request, response: Response, background: BackgroundTasks,
           vars: str | None = Query(default=None, description="쉼표 구분 변수 ID. 비우면 전체"),
           regions: str | None = Query(default=None, description="쉼표 구분 지역 (예: 서울,경기). 비우면 전체"),
           start: str | None = Query(default=None, description="시작 시점 'YYYY-MM' (예: 2021-01)"),
           dataset: str = Query(default="live", alias="set", pattern="^(live|all)$",
                                description="live: Open API 로 수집하는 변수만 · all: 기본 패널(51개 변수) 전체 + 수집 변수는 실제 수집값으로")):
    """여러 변수의 시계열을 한 번에. set=all 이면 화면이 쓰는 factor_sample.json 과 같은 내용 전체를 DB 에서 준다."""
    requested = [v.upper() for v in _parse_list(vars)]
    live_ids = [v for v in requested if (get_spec(v) and get_spec(v).enabled)] if requested else [s.id for s in enabled_specs()]
    region_list = _parse_list(regions) or None
    key = f"indicator:bundle:{dataset}:{','.join(requested)}:{','.join(region_list or [])}:{start or ''}"

    def build():
        metrics, missing, fetched = [], [], False
        live: dict[tuple, dict] = {}
        with Session(get_engine()) as session:
            for vid in (live_ids if dataset == "all" else (requested or live_ids)):
                spec = get_spec(vid)
                if spec is None or not spec.enabled:
                    missing.append(vid)
                    continue
                try:
                    metric, origin = _metric_or_fetch(session, spec, region_list, start, background, allow_fetch=dataset != "all")
                except HTTPException:  # 한 변수의 수집 실패가 묶음 전체를 막지 않는다
                    metric, origin = None, "error"
                if metric is None:
                    missing.append(vid)
                    continue
                fetched = fetched or origin.startswith("api")
                live[(metric["var"], metric["scope"])] = metric
            if dataset == "all":
                missing, used = [], set()
                for m in panel_metrics(session, requested or None, region_list, start):
                    k = (m["var"], m["scope"])
                    if k in live:  # 같은 변수·지역 단위는 Open API 실제 수집값으로 바꾼다
                        if k not in used:
                            metrics.append(live[k])
                            used.add(k)
                        continue
                    metrics.append(m)
                metrics += [m for k, m in live.items() if k not in used]
                have = {m["var"] for m in metrics}
                missing = [v for v in requested if v not in have]
                meta = panel_meta(session) or {}
            else:
                metrics, meta = list(live.values()), {}
        regions_out = {"sido": SIDO, "nation": ["전국"]}
        if meta.get("regions"):
            regions_out = {**meta["regions"], "nation": ["전국"]}
        origin = "db(cache)+api" if fetched else "db(cache)"
        if dataset == "all":
            origin = "db(panel+cache)" + ("+api" if fetched else "")
        panel = {k: meta.get(k) for k in ("generated", "loaded_at", "source_note")} if meta else None
        return {"generated": utc_now(), "set": dataset, "origin": origin, "regions": regions_out,
                "aliases": meta.get("aliases") or {}, "panel": panel, "metrics": metrics, "missing": missing}

    payload = cache.get_or_set(key, MEMORY_TTL_SECONDS, build)
    return _cache_headers(response, payload, request) or payload


@router.get("/{var}", response_model=MetricOut)
def get_indicator(var: str, request: Request, response: Response, background: BackgroundTasks,
                  regions: str | None = Query(default=None, description="쉼표 구분 지역. 비우면 전체"),
                  start: str | None = Query(default=None, description="시작 시점 'YYYY-MM'"),
                  scope: str | None = Query(default=None, description="지역 단위 sido·gu·seoul·nation. 비우면 sido 우선")):
    """변수 하나의 시계열. Open API 수집 변수는 DB 의 실제 수집값(없으면 API 1회 수집), 나머지는 기본 패널에서 준다."""
    vid = var.upper()
    spec = get_spec(vid)
    region_list = _parse_list(regions) or None
    key = f"indicator:var:{vid}:{scope or ''}:{','.join(region_list or [])}:{start or ''}"

    def build():
        with Session(get_engine()) as session:
            error = None
            if spec is not None and spec.enabled and (not scope or scope == spec.scope):
                try:
                    metric, _ = _metric_or_fetch(session, spec, region_list, start, background)
                except HTTPException as exc:  # 수집 실패 — 기본 패널이 있으면 그것으로 응답
                    metric, error = None, exc
                if metric is not None:
                    return metric
            metric = pick_metric(panel_metrics(session, [vid], region_list, start, scope), scope)
        if metric is not None:
            return metric
        if error is not None:
            raise error
        if spec is None:
            raise HTTPException(status_code=404, detail=f"등록되지 않은 지표입니다: {var}")
        if not spec.enabled:
            raise HTTPException(status_code=404, detail=f"아직 연동하지 않은 지표입니다: {var} (registry enabled=False, 기본 패널에도 없음)")
        raise HTTPException(status_code=503, detail=f"{spec.id} 자료가 아직 없고 {KEY_ENV[spec.source]} 도 설정되지 않았습니다. 수집 후 다시 시도하세요.")

    payload = cache.get_or_set(key, MEMORY_TTL_SECONDS, build)
    return _cache_headers(response, payload, request) or payload


@router.post("/refresh", response_model=RefreshOut)
def refresh(response: Response, vars: str | None = Query(default=None, description="쉼표 구분 변수 ID. 비우면 enabled 전체"),
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
    _no_store(response)
    return result
