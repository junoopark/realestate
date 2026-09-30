# Real Estate Dashboard

주요 부동산 지표를 한 화면에 모아 보는 대시보드입니다.
[mypage](https://github.com/junoopark/mypage) 프로젝트의 뼈대(프론트엔드 틀 · FastAPI 백엔드 · 배포 구성)를 가져와 시작했습니다.

## 프로젝트 소개

- **대시보드**: 3 x 2 타일에 부동산 지표를 나눠 보여줍니다. (타일 구성은 임시)
- **API 연동 실습 페이지**: 배포된 화면이 FastAPI 백엔드를 호출해 서버 상태, 지표 목록, 지표 데이터를 보여줍니다.
- **다크모드**: 헤더 버튼으로 전환합니다. 처음에는 OS 설정을 따르고, 직접 고르면 그 선택을 기억합니다.
- **한국어 / English**: 헤더 버튼으로 전환합니다. 처음에는 브라우저 언어를 따르고, 직접 고르면 그 선택을 기억합니다.

## 주요 구성

| 구분 | 기술 | 배포처 | 폴더 |
|---|---|---|---|
| 프론트엔드 | HTML · CSS · JavaScript (빌드 없음) | Vercel | [`frontend/`](frontend) |
| 백엔드 | Python · FastAPI · Pydantic | Render | [`backend/`](backend) |
| 데이터베이스 (예정) | SQLite(로컬) · Supabase(배포) | Supabase | [`database/`](database) |

```
realestate/
├─ frontend/              # Vercel (Root Directory)
│   ├─ index.html         # 대시보드 (3 x 2 타일)
│   ├─ demo.html          # API 연동 실습
│   ├─ css/style.css      # 라이트/다크 색상 토큰 포함
│   ├─ data/              # 정적 JSON (필요할 때)
│   └─ js/
│       ├─ config.js      # API 주소 (로컬/배포 자동 선택)
│       ├─ theme-init.js  # 다크모드 초기값 (깜빡임 방지)
│       ├─ i18n.js        # 한국어/English 문구 사전
│       ├─ main.js        # 테마·언어 전환 버튼
│       └─ demo.js        # API 호출·결과 표시
├─ backend/               # Render (Root Directory)
│   ├─ requirements.txt
│   └─ app/
│       ├─ main.py        # 앱 생성 + CORS + 라우터 조립
│       ├─ schemas.py     # Pydantic 모델
│       ├─ routers/       # indicators.py
│       ├─ services/      # 지표 목록(CATALOG) · ECOS/FRED 클라이언트 · 캐시
│       ├─ db/            # (예정) DB 연결·모델
│       └─ crud/          # (예정) DB 조회·저장
├─ database/              # (예정) 스키마·시드
├─ scripts/               # 데이터 가공 스크립트
└─ docs/작업설계서.md
```

## 배포 주소

| 항목 | 주소 |
|---|---|
| 대시보드 (Vercel) | (배포 후 기입) |
| API 연동 실습 페이지 (Vercel) | (배포 후 기입) |
| 백엔드 Swagger UI (Render) | (배포 후 기입) |
| GitHub 저장소 | (생성 후 기입) |

> Render 무료 플랜은 일정 시간 요청이 없으면 서버가 잠듭니다. 첫 요청은 30~60초 걸릴 수 있습니다.

## API 목록

| 메서드 | 경로 | 설명 | 응답 |
|---|---|---|---|
| GET | `/` | 환영 메시지 | 200 |
| GET | `/health` | 서버 생존 확인 | 200 |
| GET | `/indicators` | 등록된 지표 목록 | 200 |
| GET | `/indicators/{key}` | 지표 시계열 (최근 10년, 12시간 캐시) | 200 · 404 · 502 |

- 지표를 추가하는 방법은 [`backend/app/services/indicators.py`](backend/app/services/indicators.py) 맨 위 주석을 참고합니다.
- 허용할 프론트엔드 주소는 환경변수 `ALLOWED_ORIGINS`로 지정합니다(쉼표로 구분, 끝에 `/` 없이).

## 로컬 실행 방법

Python 3.11 이상과 Git이 필요합니다. (아래는 Windows PowerShell 기준)

**백엔드** — `http://127.0.0.1:8000/docs`

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
fastapi dev app/main.py
```

`.env`는 커밋되지 않으므로 PC마다 새로 만들고, `ECOS_API_KEY`·`FRED_API_KEY` 값을 채웁니다(mypage와 같은 키를 써도 됩니다. 값은 `G:\내 드라이브\coding\shared\api_keys.env`에 있습니다).

**프론트엔드** — `http://127.0.0.1:5500`

```powershell
# 저장소 루트에서 (VS Code Live Server 확장을 써도 됩니다)
python -m http.server 5500 -d frontend --bind 127.0.0.1
```

`frontend/js/config.js`가 접속 주소를 보고 API 주소를 자동으로 고릅니다. `localhost`/`127.0.0.1`이면 로컬 백엔드(`:8000`)를, 그 밖에는 Render 주소를 호출합니다.

## 배포 설정

| 플랫폼 | 설정 |
|---|---|
| Render | Root Directory `backend` · Build `pip install -r requirements.txt` · Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` · 환경변수 `ALLOWED_ORIGINS` = Vercel 주소, `ECOS_API_KEY`, `FRED_API_KEY` |
| Vercel | Root Directory `frontend` · Framework Preset `Other` · 빌드 없음 |

`main` 브랜치에 push하면 Vercel과 Render가 자동으로 다시 배포합니다.
