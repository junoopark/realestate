"""집계만 공개하는 이용 통계 및 개인정보 없는 관심 이벤트 수신."""

import os

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from app.schemas import UsageBatchIn, UsageReceiptOut
from app.services import cache
from app.services.usage_analytics import record_events, usage_summary

MAX_BODY_BYTES = 16 * 1024


class BoundedUsageRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request):
            if request.method == "POST":
                length = request.headers.get("content-length")
                if length and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                    raise HTTPException(413, "요청 본문은 16KB 이하여야 합니다.")
                data = bytearray()
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BODY_BYTES:
                        raise HTTPException(413, "요청 본문은 16KB 이하여야 합니다.")
                    data.extend(chunk)
                sent = False

                async def receive():
                    nonlocal sent
                    if sent:
                        return {"type": "http.disconnect"}
                    sent = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}

                request = Request(request.scope, receive)
            return await handler(request)

        return bounded


router = APIRouter(prefix="/usage", tags=["usage"], route_class=BoundedUsageRoute)


@router.get("")
def usage(response: Response, days: int = Query(default=30, ge=1, le=365, description="KST 오늘을 포함한 최근 며칠"),
          top: int = Query(default=10, ge=1, le=50, description="각 순위에 표시할 대상 수")):
    """기간별 로그인·다운로드, 지표 열람, 정책 상세 열람·원문 클릭 순위. 계정·세션 ID는 응답하지 않습니다."""
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["CDN-Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    return cache.get_or_set(f"usage:{days}:{top}", 60, lambda: usage_summary(days, top))


@router.post("/events", response_model=UsageReceiptOut)
def collect_usage(batch: UsageBatchIn, request: Request, response: Response):
    """최대 20건·16KB의 익명 관심 기록. 서버 catalog의 대상만 인정하며 같은 탭·대상·행동은 한 번 집계합니다.

    임의 제목·URL·사용자 ID는 받지 않습니다. DNT/GPC 설정을 존중하며 원문 클릭은 실제 독해를 뜻하지 않습니다.
    """
    response.headers["Cache-Control"] = "no-store"
    origin = request.headers.get("origin")
    allowed = {"https://www.khmi.kr", "https://khmi.kr",
               *(o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(","))}
    if origin and origin.rstrip("/") not in allowed and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "허용된 사이트에서만 기록할 수 있습니다.")
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return {"accepted": 0, "duplicates": 0, "rejected": 0, "ignored": True}
    try:
        result = record_events(batch)
    except SQLAlchemyError:
        raise HTTPException(503, "이용 기록을 저장할 수 없습니다.")
    if result["accepted"]:
        cache.clear("usage:")
    return result
