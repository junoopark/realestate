import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # 로컬 개발용. backend/.env 가 있으면 읽어온다 (배포는 Render 환경변수를 쓴다)

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.routers import indicators, qualitative, usage
from app.services.content_store import initialize_storage


@asynccontextmanager
async def lifespan(app):
    # 시작 시 할 일: 테이블 준비 + 검토한 JSON·지표 레지스트리를 DB 에 반영. 외부 API 수집은 여기서 하지 않는다
    # (수집은 CLI 또는 관리자 API 가 맡는다 — 서버가 켜질 때마다 외부 기관을 부르지 않기 위해).
    try:
        initialize_storage()
    except Exception:
        # DB 연결이 잘못돼도 정적 사본(backend/data)으로 정성 자료는 계속 제공한다.
        logging.getLogger(__name__).error("Storage unavailable; serving reviewed files when possible.")
    yield


app = FastAPI(
    title="KHMI — Korea Housing Market Intelligence API",
    version="0.2.0",
    description=(
        "주택시장 지표 대시보드 백엔드. 정량 지표는 한국부동산원 R-ONE·한국은행 ECOS·통계청 KOSIS Open API 에서 받아 "
        "PostgreSQL(Supabase)에 캐시하고 `/indicators` 로 제공합니다. 정성 자료(기초 지식·정책)는 `/knowledge`·`/policies` 입니다."
    ),
    lifespan=lifespan,
    # 문서·Swagger 의 주소를 사이트 주소(https://www.khmi.kr/api/…)로 통일한다. 아래 StripApiPrefix 덕분에 서버 주소로 직접 와도 같은 경로가 통한다
    servers=[{"url": "/api", "description": "www.khmi.kr/api (Vercel CDN 경유) · 서버 주소에서도 같은 경로"}],
    docs_url=None,
    redoc_url=None,
)

# CORS: 허용 출처는 환경변수로 받는다 (배포 시 Vercel 주소를 넣는다)
origins = os.getenv(
    "ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 응답 압축: /indicators/bundle?set=all(약 0.7MB JSON)을 전송할 때 크기를 크게 줄인다
app.add_middleware(GZipMiddleware, minimum_size=1000)

class StripApiPrefix:
    """'/api/…' 로 들어온 요청을 '/…' 로 바꿔 넘긴다. 화면 요청은 Vercel 이 /api 를 떼고 넘기지만(frontend/vercel.json),
    서버 주소로 직접 와도 같은 경로가 통하게 해서 Swagger(/api/docs)와 문서의 주소를 사이트 주소 하나로 쓴다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] in ("http", "websocket") else ""
        if path == "/api" or path.startswith("/api/"):
            raw = scope.get("raw_path") or path.encode()
            scope = {**scope, "path": path[4:] or "/", "raw_path": raw[4:] if raw.startswith(b"/api") and len(raw) > 4 else b"/"}
        await self.app(scope, receive, send)


app.add_middleware(StripApiPrefix)  # 마지막에 넣은 미들웨어가 가장 바깥 — 경로를 먼저 고친 뒤 라우팅한다

app.include_router(indicators.router)
app.include_router(qualitative.router)
app.include_router(usage.router)


@app.get("/")
def read_root():
    return {"message": "Real Estate Dashboard API 에 오신 것을 환영합니다"}


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    """Swagger UI. 명세는 /api/openapi.json 으로 읽는다 — www.khmi.kr/api/docs 와 서버 주소의 /docs 둘 다에서 열린다."""
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="KHMI API — Swagger UI")


@app.get("/health")
def health_check():
    return {"status": "ok"}
