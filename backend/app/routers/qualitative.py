import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Query

from app.db.session import storage_info
from app.services.content_store import get_content, read_seed
from app.services.policy_collector import collect_all, read_monitor
from app.services.policy_sources import COVERAGE_NOTE, SOURCES

router = APIRouter(tags=["qualitative"])


def content_response(key):
    available = True
    try:
        content = get_content(key)
    except Exception:
        available, content = False, read_seed(key)
    if content is None:
        raise HTTPException(status_code=503, detail="검증한 콘텐츠 파일을 아직 준비하지 못했습니다.")
    return content, available


@router.get("/knowledge")
def knowledge():
    content, _ = content_response("knowledge")
    return content


@router.get("/policies")
def policies():
    content, available = content_response("policies")
    return {**content, "storage": storage_info(available), "sync": {"mode": "reviewed_snapshot", "verified_at": content.get("verified_at"), "note": "원문을 확인한 편집 자료입니다. 자동 수집 후보는 /policies/monitor에서 제공합니다."}}


@router.get("/policies/monitor")
def monitor(limit: int = Query(default=100, ge=1, le=300)):
    try:
        return {**read_monitor(limit), "coverage_note": COVERAGE_NOTE, "storage": storage_info()}
    except Exception:
        return {"items": [], "sources": [{**source, "status": "storage_unavailable", "last_success_at": None, "last_checked_at": None, "error": "저장소에 연결할 수 없습니다.", "item_count": 0} for source in SOURCES], "last_checked_at": None, "coverage_note": COVERAGE_NOTE, "storage": storage_info(False)}


@router.get("/policies/history")
def history():
    content, available = content_response("policy-history")
    return {
        **content,
        "storage": storage_info(available),
        "sync": {
            "mode": "reviewed_snapshot",
            "verified_at": content.get("verified_at"),
            "note": "공식 발표를 검토해 선정한 정책 변화 연표입니다. 발표일 기준이며 전체 정책 목록이나 현재 적용 규정은 아닙니다.",
        },
    }


@router.get("/warning")
def warning():
    """월세 조기경보 ML 실험 결과 (dfmba-dashboard ml/output → export/export_warning.py). 정성 콘텐츠와 같은 스냅샷 방식."""
    content, available = content_response("warning")
    return {**content, "storage": storage_info(available),
            "sync": {"mode": "reviewed_snapshot", "generated_at": content.get("generated_at"),
                     "note": "표본외 예측 실험 결과입니다. 예측 확률은 학습용 추정치이며 투자·계약 판단의 근거가 아닙니다."}}


@router.post("/policies/refresh")
def refresh(x_admin_token: str | None = Header(default=None)):
    expected = os.getenv("POLICY_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="관리자 수집 기능이 설정되지 않았습니다. 서버에서 POLICY_ADMIN_TOKEN을 설정하세요.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
    try:
        result = collect_all()
    except Exception:
        raise HTTPException(status_code=503, detail="정책 수집 결과를 저장할 수 없습니다. 서버의 저장소 연결을 확인하세요.")
    if result["status"] == "busy":
        raise HTTPException(status_code=409, detail="정책 수집이 이미 진행 중입니다.")
    return result
