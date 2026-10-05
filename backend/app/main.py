import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # 로컬 개발용. backend/.env 가 있으면 읽어온다 (배포는 Render 환경변수를 쓴다)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import indicators, qualitative
from app.services.content_store import initialize_storage


@asynccontextmanager
async def lifespan(app):
    try:
        initialize_storage()
    except Exception:
        # Indicator routes stay available if a new Supabase connection is misconfigured.
        logging.getLogger(__name__).error("Qualitative storage unavailable; serving reviewed files when possible.")
    yield


app = FastAPI(title="Real Estate Dashboard API", lifespan=lifespan)

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

app.include_router(indicators.router)
app.include_router(qualitative.router)


@app.get("/")
def read_root():
    return {"message": "Real Estate Dashboard API 에 오신 것을 환영합니다"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
