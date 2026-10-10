# KHMI — Korea Housing Market Intelligence

주요 부동산 지표를 한 화면에 모아 보는 대시보드입니다.
[mypage](https://github.com/junoopark/mypage) 프로젝트의 뼈대(프론트엔드 틀 · FastAPI 백엔드 · 배포 구성)를 가져와 시작했습니다.

## 프로젝트 소개

- **Home** (`index.html#home`, 첫 화면, `js/home.js`): ① KHMI Dashboard — 주택시장 가격 동향(월세가격지수 코멘터리·차트) · 이달의 차트(기준금리·국고채 3년·주택담보대출 금리) · 주요 정책 동향(`data/policies.json` 최근 발표 4건)을 한 줄 3단으로 ② 시도별 가격 상승률 지도 — 17개 시도 히트맵(매매·전세·월세 가격지수, 전년동월·전월 대비, 상승 파랑·하락 빨강)과 순위 막대.
- **해설 문장**: 차트 제목·불릿·설명은 `js/notes.js`가 데이터에서 계산해 만듭니다(최신값, 전년동기 대비, 최근 3개월 방향, 최근 3년 범위 위치). 원인·전망은 쓰지 않고, 방향 해석은 데이터사전의 예상 부호만 근거로 합니다.
- **부동산 대시보드** (`index.html#overview`, `#demand` … `#macro`, `js/factors.js`): Overview(6개 동인 대표 지표의 코멘터리+차트)와 6개 동인 화면. 동인 화면은 차트가 먼저 나오고 개요·핵심 포인트·지역별 최신값 표·차트별 해설은 접어 둡니다.
  - 보기 설정: 지역(17개 시도 중 최대 3곳을 가로 스크롤 토글로 선택, 또는 서울 구) · 기간(3년/5년/전체) · 값(수준/전년동기 대비)
  - 변수별 시계열 차트(마우스·키보드로 값 읽기), 접힌 해설·출처·전처리 방법
  - 설명은 [`frontend/data/drivers.json`](frontend/data/drivers.json), 값은 [`frontend/data/factor_sample.json`](frontend/data/factor_sample.json)에서 읽습니다.
- **상단 메뉴 4개**: Home · 부동산 대시보드(하위 메뉴: Overview, 6개 동인) · 부동산 정책 · About(하위 메뉴: 사이트 소개, 데이터·방법, 부동산 기초). 다섯 페이지(`index`·`learn`·`policies`·`about`·`demo`)에 같은 메뉴가 들어 있으니 바꿀 때는 함께 고칩니다.
- **About**: `about.html` — 사이트 구성, 데이터사전·전처리·해설 규칙, 부동산 기초·프로젝트 안내.
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
│   ├─ index.html         # 대시보드 (Overview 차트 타일 + 동인 탭 6개)
│   ├─ about.html         # 사이트 소개 · 데이터·방법
│   ├─ demo.html          # API 연동 실습
│   ├─ learn.html         # 용어·거래·개발·기관 투자 기초
│   ├─ policies.html      # 정책 요약·자동 수집 후보·출처
│   ├─ css/style.css      # 라이트/다크 색상 토큰 포함
│   ├─ data/drivers.json  # 6개 동인·변수 목록 (데이터사전 엑셀에서 추출)
│   ├─ data/factor_sample.json # 대시보드 값 샘플 (DFMBA 전처리본, 17개 시도)
│   ├─ data/korea_sido.json    # Home 지도용 17개 시도 경계 (통계청 SGIS 2018, 공공누리 제1유형)
│   └─ js/
│       ├─ config.js      # API 주소 (로컬/배포 자동 선택)
│       ├─ theme-init.js  # 다크모드 초기값 (깜빡임 방지)
│       ├─ i18n.js        # 한국어/English 문구 사전
│       ├─ main.js        # 테마 전환 버튼
│       ├─ notes.js       # 차트 해설 문장 (데이터에서 계산)
│       ├─ charts.js      # 숫자 표시 규칙 · SVG 선 차트
│       ├─ factors.js     # 화면 전환(#home, #overview, #demand …) · 대시보드 Overview · 동인 화면
│       ├─ home.js        # Home: 가격 동향 · 이달의 차트 · 정책 동향 · 시도 지도 히트맵
│       └─ demo.js        # API 호출·결과 표시
├─ backend/               # Render (Root Directory)
│   ├─ requirements.txt
│   └─ app/
│       ├─ main.py        # 앱 생성 + CORS + 라우터 조립
│       ├─ schemas.py     # Pydantic 모델
│       ├─ routers/       # indicators.py · qualitative.py
│       ├─ services/      # 지표 목록(CATALOG) · ECOS/FRED 클라이언트 · 캐시
│       ├─ db/            # 정성자료 DB 연결·모델
│       └─ crud/          # 정량 지표 저장 기능 확장용 자리
├─ database/              # PostgreSQL 스키마·연결 및 테이블 설명
├─ scripts/               # 데이터 가공 스크립트
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
| GET | `/indicators` | 등록된 지표 목록 | 200 |
| GET | `/indicators/{key}` | 지표 시계열 (최근 10년, 12시간 캐시) | 200 · 404 · 502 |
| GET | `/knowledge` | 출처가 있는 부동산 기초 학습 콘텐츠 | 200 · 503 |
| GET | `/policies` | 검토한 정책 요약 및 저장소 상태 | 200 · 503 |
| GET | `/policies/monitor` | 수집 후보와 기관별 성공·실패 기록 | 200 · 422 |
| GET | `/policies/history` | 최근 10년의 검토한 정책 연혁·시기별 흐름·출처 | 200 · 503 |
| POST | `/policies/refresh` | 관리자 토큰으로 공식 발표 수집 | 200 · 401 · 409 · 503 |

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

## 정성 자료 기능과 팀 인수인계

**부동산 기초·정책 모니터·정책 히스토리 담당: 박민영**

구현 내용·출처·API 응답·수집 운영은 [정성 자료 가이드](docs/qualitative-guide.md), Supabase 연결과 테이블은 [DB 설명](database/README.md)을 참고하세요.

- 동인 탭 값(`frontend/data/factor_sample.json`)은 [DFMBA](https://github.com/ksroh1913/DFMBA) 파이프라인의 `데이터취합_전처리_YYYYMMDD.xlsx`(1차_결측보완 시트)에서 뽑은 **샘플**입니다(17개 시도, 서울 구 강남·마포·노원, 2016년~). 새 전처리본이 나오면 `python scripts/build_factor_sample.py <엑셀 경로>`로 다시 만듭니다. Home 지도 경계는 `python scripts/build_korea_map.py <skorea-provinces-2018-geo.json>`([southkorea-maps](https://github.com/southkorea/southkorea-maps)의 통계청 2018 경계)로 만듭니다. 국토부 실거래 신고건수(V006·V007)의 최근 3개월은 신고기한 때문에 잠정값으로 표시합니다.
- 기초/정책/연혁 원본은 `frontend/data/knowledge.json`, `frontend/data/policies.json`, `frontend/data/policy-history.json`입니다. 연혁 수정 후 `python scripts/check_history_data.py`로 형식을 검사하고, `python scripts/sync_qualitative_data.py`로 Render 배포용 `backend/data/` 사본도 갱신합니다.
- 실제 발표 수집: 저장소 루트에서 `python scripts/collect_policies.py --export frontend/data/monitor.json`. 수집은 DB에 기록하고, 옵션의 JSON은 프론트 서버 연결 실패 시 표시할 실제 수집 스냅샷입니다.
- Supabase 연결 전에는 SQLite를 사용합니다. Render의 임시 디스크는 재배포 시 수집 이력이 사라질 수 있으므로, 누적 모니터링 운영 전 `DATABASE_URL`을 연결합니다.
