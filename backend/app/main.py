import os

from dotenv import load_dotenv

load_dotenv()  # 로컬 개발용. backend/.env 가 있으면 읽어온다 (배포는 Render 환경변수를 쓴다)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import indicators

app = FastAPI(title="Real Estate Dashboard API")

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


@app.get("/")
def read_root():
    return {"message": "Real Estate Dashboard API 에 오신 것을 환영합니다"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
