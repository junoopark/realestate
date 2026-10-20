# KHMI — Korea Housing Market Intelligence

**공공 통계로 읽는 한국 주택 임대시장**

[www.khmi.kr](https://www.khmi.kr)

KHMI(Korea Housing Market Intelligence)는 흩어져 있는 주택시장 공공 통계를 한곳에 모아, 차트와 짧은 해설로 보여주는 주택시장 정보 서비스입니다. 17개 시·도와 서울 자치구의 주택 임대시장을 중심으로, 임대시장에 영향을 주는 지표를 **6개 동인(driver)** 으로 나누어 보여줍니다.

---

## 주요 기능

### Home
한 화면에서 시장 흐름을 봅니다.
- **주택시장 가격 동향** — 월세가격지수 시장 코멘터리와 차트 (수준 · 전년동월 대비 · 전월 대비)
- **이달의 차트** — 기준금리 · 국고채 3년 · 주택담보대출 금리
- **주요 정책 동향** — 최근 발표된 주택 정책
- **시도별 가격 상승률 지도** — 17개 시도의 매매 · 전세 · 월세 가격지수 변화를 지도와 순위로 비교

### 부동산 대시보드
- **Overview** — 6개 동인의 대표 지표와 코멘터리
- **동인별 화면** — 동인에 속한 모든 지표의 시계열 차트, 지역별 최신값 표, 해설과 출처
- **보기 설정** — 17개 시도 중 최대 3곳 비교 또는 서울 자치구 · 기간(3년 / 5년 / 전체) · 값(수준 / 전년동기 대비)

### 부동산 정책
- **주요 정책 정리** — 공식 발표를 6시간마다 자동 선별하고 본문·PDF의 핵심 문장을 발췌. 자동 요약일과 기존 검토 자료의 확인일을 구분하며 별도 AI API 비용 없음
- **새 발표 모니터링** — 국토교통부 등 공식 발표를 자동 수집한 후보 목록
- **정책 히스토리** — 최근 10년 주요 정책 전환점을 시기별 · 연도별 타임라인으로 정리

### About · 부동산 기초
- 사이트 구성, 데이터와 방법, 해설 규칙
- 부동산 기초 학습 자료 — 용어, 매매 · 전세 · 월세 계약 절차, 부동산 개발과 투자 심사
- [프로젝트 발표](https://www.khmi.kr/presentation.html) — 만든 이유 → 화면 시연 → 데이터 수집·API·DB → 전체 아키텍처 → 사업과 다음 단계. 본문 16장과 API·DB 문서 부록 3장으로 구성합니다.

발표 페이지는 `frontend/presentation.html`, 전용 스타일과 동작은 `frontend/css/presentation.css`·`frontend/js/presentation.js`에서 관리합니다. `←`·`→`로 이동하고 `N`은 발표 메모, `F`는 전체 화면, `O`는 전체 읽기 보기입니다. 모바일은 읽기 보기로 시작하며 인쇄 시 전체 슬라이드를 A4 가로로 출력합니다. 화면 캡처와 구현 설명의 확인일은 2026-10-20입니다.

---

## 6개 동인

| # | 동인 | 무엇을 보는가 | 주요 지표 |
|---|---|---|---|
| ① | 임차수요 압력 | 집을 빌리려는 사람의 증가 | 인구 · 세대 · 청년층 · 인구이동 · 고용 · 소득 |
| ② | 주택공급 · 재고 | 늘어난 수요를 흡수할 공급 여력 | 인허가 · 착공 · 준공 · 미분양 · 임대주택 |
| ③ | 매매 · 전세 시장 | 인접 시장 가격의 영향 | 매매 · 전세 가격지수, 전세가율, 전월세전환율 |
| ④ | 임대시장 수급 | 임대 수요와 공급의 균형 | 월세 · 전세 수급동향, 실거래량 |
| ⑤ | 시장심리 | 가격 상승 기대 (단기 신호) | 주택시장 소비심리, 주택가격전망 CSI |
| ⑥ | 금리 · 대출 · 거시경제 | 전국 공통의 금융 · 경기 환경 | 기준 · 대출금리, 가계대출, 물가 · 경기 |

①~④는 지역마다 다른 구조, ⑤는 단기 신호, ⑥은 전국 공통 환경으로 구분합니다. 동인 분류는 선행연구에서 반복해 쓰인 변수를 기준으로 한 데이터사전(52개 변수)을 따릅니다.

---

## 데이터

| 구분 | 내용 |
|---|---|
| 출처 | 한국부동산원 R-ONE, 한국은행 ECOS, 통계청 KOSIS, 국토교통부(실거래가 공개시스템 · 공공데이터포털), 행정안전부, 국토연구원 |
| 지역 범위 | 전국 · 17개 시도 · 서울 25개 자치구 (지표별로 제공 범위가 다름) |
| 기간 | 2011년 이후 월 · 분기 · 연 단위 (지표별 공표 주기를 따름) |
| 갱신 | 각 기관의 공표 일정에 맞춰 갱신 |

**표시 원칙**
- 화면의 값은 각 기관이 공표한 기준기간 값입니다. 빈 기간만 정해진 규칙으로 보완하며, 보완 방법은 차트마다 표시합니다.
- 지수 기준시점이 바뀐 계열은 공식 기준시점에 맞춰 연결하고, 연결 방법을 함께 밝힙니다.
- 신고기한 때문에 바뀔 수 있는 최근 값(예: 실거래 신고건수 최근 3개월)은 잠정값으로 구분해 점선으로 표시합니다.

**해설 원칙**
- 차트의 헤드라인과 설명은 데이터에서 계산한 사실(최신값, 전년동기 대비, 최근 3개월 방향, 최근 3년 범위 내 위치)로만 만듭니다.
- 원인 분석이나 가격 전망은 쓰지 않습니다. 방향 해석은 데이터사전에 정한 예상 부호만 근거로 합니다.

---

## 서비스 구성

```
 www.khmi.kr ──▶  웹 화면 (Vercel)
                    │
                    ▼
                 API 서버 (FastAPI · Render) ──▶ 데이터베이스 (PostgreSQL · Supabase)
                                                      ▲
 공공 통계 API (R-ONE · ECOS · KOSIS · 국토부) ──▶ 수집 · 전처리 파이프라인
```

| 구성 | 기술 |
|---|---|
| 웹 화면 | HTML · CSS · JavaScript (빌드 없음), 자체 SVG 차트, 라이트 / 다크 모드 |
| API 서버 | Python · FastAPI · SQLAlchemy · Pydantic |
| 데이터베이스 | PostgreSQL (Supabase), 행 수준 보안(RLS) 적용 |
| 데이터 수집 | R-ONE · ECOS · KOSIS Open API 수집기(지표 레지스트리), 정책 발표 수집기, [DFMBA](https://github.com/ksroh1913/DFMBA) 전처리 파이프라인 |

### 공개 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 |
| GET | `/indicators` | 제공 지표 목록 · 수집 상태 · 출처 |
| GET | `/indicators/bundle` | 여러 지표 시계열을 한 번에. `set=all`이면 51개 변수 전체(DB 기본 패널 + Open API 실제 수집값) |
| GET | `/indicators/{var}` | 지표 시계열 (DB에 캐시, 없으면 외부 API 1회 수집) |
| GET | `/indicators/status` | 지표별 수집 상태 · 최근 수집 기록 |
| GET | `/usage` | 기간별 다운로드·지표 조회·정책 상세/원문 클릭 순위와 일별 집계. 개인 식별 정보 없음 |
| POST | `/usage/events` | 지표 조회·정책 상세/원문 클릭을 익명 탭 세션 기준으로 수집. 검증된 대상 ID만 허용 |
| GET | `/knowledge` | 부동산 기초 학습 자료 |
| GET | `/policies` | 주요 정책 요약 |
| GET | `/policies/monitor` | 정책 발표 수집 현황 |
| GET | `/policies/history` | 최근 10년 정책 연혁 |

API 명세는 서버의 `/docs`(Swagger UI)에서 볼 수 있습니다.

---

## 개발 환경

Python 3.11 이상이 필요합니다.

```bash
# API 서버 — http://127.0.0.1:8000/docs
cd backend
pip install -r requirements.txt
cp .env.example .env        # API 키와 DATABASE_URL 입력
fastapi dev app/main.py

# 웹 화면 — http://127.0.0.1:5500 (저장소 루트에서)
python -m http.server 5500 -d frontend --bind 127.0.0.1
```

| 문서 | 내용 |
|---|---|
| [데이터베이스](database/README.md) | 테이블 구조, Supabase 연결, R-ONE 수집 · 지역 매핑 |
| [정량 지표 파이프라인](docs/indicator-pipeline.md) | 지표 레지스트리, Open API 수집 → DB 캐시 → `/indicators`, 매일 자동 수집 |
| [정성 자료 가이드](docs/qualitative-guide.md) | 부동산 기초 · 정책 자료의 출처와 수집 운영 |
| [작업 설계서](docs/작업설계서.md) | 설계 결정과 진행 단계 |

---

## 서비스 주소

| 항목 | 주소 |
|---|---|
| 대시보드 | https://www.khmi.kr |
| 이용 통계 | https://www.khmi.kr/usage.html |
| API 연동 실습 페이지 | https://www.khmi.kr/demo.html |
| CDN 경유 API (화면이 부르는 주소) | https://www.khmi.kr/api/indicators/bundle?set=all |
| Swagger UI (API 명세) | https://www.khmi.kr/api/docs |
| 지표 수집 상태 | https://www.khmi.kr/api/indicators/status |

- 웹 화면(Vercel)과 API 서버(Render · FastAPI) 모두 이 저장소 main 을 배포합니다. main 에 합치면 둘 다 자동으로 다시 배포됩니다. `/api/*` 는 `frontend/vercel.json` 이 API 서버로 넘기고 응답을 CDN 에 캐시합니다. 그래서 화면·API·Swagger 모두 www.khmi.kr 한 주소로 씁니다(API 서버 자체 주소는 `vercel.json` 의 전달 목적지와 Actions 비밀값에만 있습니다).
- 매일 수집은 이 저장소의 GitHub Actions 가 트리거합니다. 09:40 에 API 서버의 수집 API(실거래 건수 → R-ONE·ECOS·KOSIS → 실거래 합계)를, 6시간마다 정책 수집 API 를 부릅니다. 외부 API 호출과 DB 저장은 API 서버가 맡고, 오래 걸리는 실거래 수집은 서버의 백그라운드 작업으로 돌립니다(`POST /indicators/rtms/collect` → `GET /indicators/rtms/job`).
- 정책 수집은 주요 정책 자동 요약까지 같은 작업에서 처리합니다. 새 요약은 `policy_briefs`에 보관해 재배포에도 유지합니다. 본문을 읽지 못한 후보는 다음 실행에서 재시도하며, `/api/policies`의 `automation`에서 처리 결과를 확인합니다. 선정 기준·처리 한도·배포 절차는 [정성 자료 가이드](docs/qualitative-guide.md#주요-정책-자동-정리)에 있습니다.
- 저장소 비밀값은 `POLICY_API_BASE_URL`·`POLICY_ADMIN_TOKEN`·`SITE_BASE_URL` 3개뿐입니다. 외부 API 키와 DB 주소(`DATABASE_URL`)는 API 서버(Render) 환경변수에만 둡니다.
- Google 로그인(Supabase Auth)과 이용 기록(`activity_logs`)도 같은 Supabase를 씁니다. 로그인·다운로드는 화면이 supabase-js로 직접 기록하고(RLS: 본인 기록 추가만), 익명 차트·정책 조회는 FastAPI의 `/usage/events`를 거쳐 `usage_events`에 저장합니다. `/usage`는 개인 식별 정보 없이 숫자로 집계합니다. 측정 기준과 한계는 [이용 통계 가이드](docs/usage-analytics.md)를 참고하세요.

---

## 만든 사람들

KHMI는 KAIST 디지털금융 MBA 졸업생들이 함께 시작한 서비스입니다.

## 알림

- KHMI가 제공하는 정보는 공공 통계를 정리한 참고 자료이며, 투자 권유나 가격 예측이 아닙니다.
- 각 통계의 저작권은 원 작성기관에 있습니다. 시도 경계 지도는 통계청 SGIS(2018) 자료를 공공누리 제1유형에 따라 사용했습니다.
