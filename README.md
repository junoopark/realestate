# DFMBA 한국 주택시장 101

주요 부동산 지표를 한 화면에 모아 보는 대시보드입니다.
[mypage](https://github.com/junoopark/mypage) 프로젝트의 뼈대(프론트엔드 틀 · FastAPI 백엔드 · 배포 구성)를 가져와 시작했습니다.

## 프로젝트 소개

- **Overview 탭**: 3 x 2 타일(주택가격·거래·전월세·공급·금리대출·심리)에 최신값, 전기 대비·전년동기 대비 변화, 최근 3년 추세선을 보여줍니다. 헤더의 지역 선택(17개 시도·서울 25개 구)을 따르며, 그 지역 자료가 없는 지표는 서울 → 전국 순으로 대체하고 실제 지역명을 표시합니다. 자료는 [`frontend/data/indicators/`](frontend/data/indicators)의 정적 JSON(변수별 1파일)입니다.
- **동인 탭 6개**: 서울 자치구 월세 리스크 데이터사전의 6개 동인(① 임차수요 압력 ~ ⑥ 거시경기·금융시장 여건)별로 핵심 질문과 변수 목록을 보여줍니다. 내용은 [`frontend/data/drivers.json`](frontend/data/drivers.json)에서 읽습니다.
- **조기경보**: `warning.html` — 월세가 6개월 안에 급등·급락할 확률을 추정한 기계학습 1차 실험 결과. 패널(17개 시도·서울 25개 구)·과제·지역 필터로 경보 확률 시계열과 동인별 기여(SHAP), 모형 비교(AUC), 연도별 성적, 상위 변수를 봅니다. 모든 차트에 툴팁과 표 보기가 있습니다. 자료는 [`frontend/data/warning.json`](frontend/data/warning.json)(dfmba-dashboard `export/export_warning.py` 산출)이며 백엔드 `/warning`이 같은 내용을 DB 스냅샷으로 제공합니다.
- **부동산 기초**: `learn.html` — 용어 검색, 매매·전세·월세 절차, 기관 개발과 투자 심사 가이드. 공식 출처를 함께 제공합니다.
- **정책 모니터**: `policies.html` — 검토한 정책 요약, 공식 발표 자동 수집 후보, 적용 조건·리스크와 수집 상태를 제공합니다. **정책 히스토리** 탭은 최근 10년의 주요 전환점 27건을 5개 시기와 연도별 타임라인으로 보여줍니다.
- **API 연동 실습 페이지**: `demo.html` — 배포된 화면이 FastAPI 백엔드를 호출해 서버 상태, 지표 목록, 지표 데이터를 보여줍니다. (헤더 메뉴에서는 뺐고 주소로 직접 엽니다)
- **다크모드**: 헤더 버튼으로 전환합니다. 처음에는 OS 설정을 따르고, 직접 고르면 그 선택을 기억합니다.
- **언어**: 한국어로 고정했습니다. (English 문구 사전은 `js/i18n.js`에 남아 있습니다)

## 주요 구성

| 구분 | 기술 | 배포처 | 폴더 |
|---|---|---|---|
| 프론트엔드 | HTML · CSS · JavaScript (빌드 없음) | Vercel | [`frontend/`](frontend) |
| 백엔드 | Python · FastAPI · Pydantic | Render | [`backend/`](backend) |
| 데이터베이스 | SQLite(로컬 구현) · PostgreSQL(Supabase 연결 준비) | Supabase | [`database/`](database) |

```
realestate/
├─ frontend/              # Vercel (Root Directory)
│   ├─ index.html         # 대시보드 (Overview 3 x 2 타일 + 동인 탭 6개)
│   ├─ demo.html          # API 연동 실습
│   ├─ warning.html       # 월세 조기경보 (ML 실험 결과: 경보 확률·동인 기여·모형 비교)
│   ├─ learn.html         # 용어·거래·개발·기관 투자 기초
│   ├─ policies.html      # 정책 요약·자동 수집 후보·출처
│   ├─ css/style.css      # 라이트/다크 색상 토큰 포함
│   ├─ data/drivers.json  # 6개 동인·변수 목록 (데이터사전 엑셀에서 추출)
│   ├─ data/indicators/   # 정량 지표 시계열 (index.json + 변수별 V001.json …). 재생성: dfmba-dashboard 레포에서
│   │                     #   python export/export_indicators.py --out ../realestate/frontend/data/indicators
│   └─ js/
│       ├─ config.js      # API 주소 (로컬/배포 자동 선택)
│       ├─ theme-init.js  # 다크모드 초기값 (깜빡임 방지)
│       ├─ i18n.js        # 한국어/English 문구 사전
│       ├─ main.js        # 테마 전환 버튼
│       ├─ factors.js     # 탭 전환(#overview, #demand …) · 동인 탭 화면 (변수 카드 차트 포함)
│       ├─ indicators.js  # 정량 지표 공용: JSON 로딩·지역 선택·변화율·스파크라인
│       ├─ tiles.js       # Overview 타일 6개 구성과 그리기
│       ├─ warning.js     # 조기경보 페이지(절 탭·필터) · warning-charts.js: 시계열·막대·히트맵·툴팁·표 보기
│       └─ demo.js        # API 호출·결과 표시
├─ backend/               # Render (Root Directory)
│   ├─ requirements.txt
│   └─ app/
│       ├─ main.py        # 앱 생성 + CORS + 라우터 조립
│       ├─ schemas.py     # Pydantic 모델
│       ├─ routers/       # indicators.py · qualitative.py
│       ├─ services/      # indicator_store.py(지표 DB 적재·조회) · content_store · policy_collector · ECOS/FRED 클라이언트(미사용)
│       ├─ db/            # 정성자료 DB 연결·모델
│       └─ crud/          # 정량 지표 저장 기능 확장용 자리
├─ database/              # PostgreSQL 스키마·연결 및 테이블 설명
├─ scripts/               # 데이터 가공 스크립트 (load_indicators.py: 지표 JSON → DB 적재)
└─ docs/                  # 작업설계서.md · qualitative-guide.md
```

## 배포 주소

| 항목 | 주소 |
|---|---|
| 대시보드 (Vercel) | https://realestate-junoo1.vercel.app |
| API 연동 실습 페이지 (Vercel) | https://realestate-junoo1.vercel.app/demo.html |
| 백엔드 Swagger UI (Render) | https://realestate-qr7h.onrender.com/docs |
| GitHub 저장소 | https://github.com/junoopark/realestate |

> Render 무료 플랜은 일정 시간 요청이 없으면 서버가 잠듭니다. 첫 요청은 30~60초 걸릴 수 있습니다.

## API 목록

| 메서드 | 경로 | 설명 | 응답 |
|---|---|---|---|
| GET | `/` | 환영 메시지 | 200 |
| GET | `/health` | 서버 생존 확인 | 200 |
| GET | `/indicators` | 데이터사전 변수 52개 목록(항목·지역·기간 요약)과 저장소 상태 | 200 · 503 |
| GET | `/indicators/{id}` | 변수 하나의 시계열. `?item=&region=`으로 한 계열만. 응답 모양은 `frontend/data/indicators/*.json`과 같음 | 200 · 404 |
| GET | `/knowledge` | 출처가 있는 부동산 기초 학습 콘텐츠 | 200 · 503 |
| GET | `/policies` | 검토한 정책 요약 및 저장소 상태 | 200 · 503 |
| GET | `/policies/monitor` | 수집 후보와 기관별 성공·실패 기록 | 200 · 422 |
| GET | `/policies/history` | 최근 10년의 검토한 정책 연혁·시기별 흐름·출처 | 200 · 503 |
| GET | `/warning` | 월세 조기경보 ML 실험 결과(성적표·연도별 AUC·SHAP·지역별 경보 시계열) | 200 · 503 |
| POST | `/policies/refresh` | 관리자 토큰으로 공식 발표 수집 | 200 · 401 · 409 · 503 |

- 정량 지표는 DB 테이블 `indicator_variables`·`indicator_series`에서 읽습니다. 로컬에서는 서버 시작 시 `frontend/data/indicators/`를 자동 적재하고, Supabase에는 `python scripts/load_indicators.py`로 적재합니다(`DATABASE_URL` 필요). DB가 비어 있거나 연결이 안 되면 정적 JSON으로 대체하고 응답의 `storage.source`가 `static_json`이 됩니다.
- 지표 자료 자체를 바꾸려면 dfmba-dashboard 레포에서 `export/export_indicators.py`를 다시 실행해 JSON을 갱신한 뒤 적재합니다.
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

## 정성 자료 기능과 팀 인수인계

**부동산 기초·정책 모니터·정책 히스토리 담당: 박민영**

구현 내용·출처·API 응답·수집 운영은 [정성 자료 가이드](docs/qualitative-guide.md), Supabase 연결과 테이블은 [DB 설명](database/README.md)을 참고하세요.

- 기초/정책/연혁 원본은 `frontend/data/knowledge.json`, `frontend/data/policies.json`, `frontend/data/policy-history.json`입니다. 연혁 수정 후 `python scripts/check_history_data.py`로 형식을 검사하고, `python scripts/sync_qualitative_data.py`로 Render 배포용 `backend/data/` 사본도 갱신합니다.
- 실제 발표 수집: 저장소 루트에서 `python scripts/collect_policies.py --export frontend/data/monitor.json`. 수집은 DB에 기록하고, 옵션의 JSON은 프론트 서버 연결 실패 시 표시할 실제 수집 스냅샷입니다.
- Supabase 연결 전에는 SQLite를 사용합니다. Render의 임시 디스크는 재배포 시 수집 이력이 사라질 수 있으므로, 누적 모니터링 운영 전 `DATABASE_URL`을 연결합니다.
