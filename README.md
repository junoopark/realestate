# KHMI — Korea Housing Market Intelligence

**공공 통계로 읽는 한국 주택 임대시장**

[www.khmi.kr](https://www.khmi.kr)

KHMI(Korea Housing Market Intelligence)는 흩어져 있는 주택시장 공공 통계를 한곳에 모아, 차트와 짧은 해설로 보여주는 주택시장 정보 서비스입니다. 서울 자치구 아파트 월세 리스크를 중심으로, 임대시장에 영향을 주는 지표를 **6개 동인(driver)** 으로 나누어 보여줍니다.

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
- **주요 정책 정리** — 공식 원문을 확인한 정책 요약, 적용 대상 · 조건 · 시행일
- **새 발표 모니터링** — 국토교통부 등 공식 발표를 자동 수집한 후보 목록
- **정책 히스토리** — 최근 10년 주요 정책 전환점을 시기별 · 연도별 타임라인으로 정리

### About · 부동산 기초
- 사이트 구성, 데이터와 방법, 해설 규칙
- 부동산 기초 학습 자료 — 용어, 매매 · 전세 · 월세 계약 절차, 부동산 개발과 투자 심사

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
| 데이터 수집 | R-ONE · ECOS · KOSIS Open API 수집기(지표 레지스트리), R-ONE 월세지수 적재, 정책 발표 수집기, [DFMBA](https://github.com/ksroh1913/DFMBA) 전처리 파이프라인 |

### 공개 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 |
| GET | `/indicators` | 제공 지표 목록 · 수집 상태 · 출처 |
| GET | `/indicators/bundle` | 여러 지표 시계열을 한 번에. `set=all`이면 51개 변수 전체(DB 기본 패널 + Open API 실제 수집값) |
| GET | `/indicators/{var}` | 지표 시계열 (DB에 캐시, 없으면 외부 API 1회 수집) |
| GET | `/indicators/status` | 지표별 수집 상태 · 최근 수집 기록 |
| GET | `/usage` | 이용 통계 — 로그인·로그아웃·데이터 내려받기 횟수와 사용자 수(일별), 많이 내려받은 변수. 개인 정보 없음 (`activity_logs` 집계 뷰) |
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
| API 연동 실습 페이지 | https://www.khmi.kr/demo.html |
| CDN 경유 API (화면이 부르는 주소) | https://www.khmi.kr/api/indicators/bundle?set=all |
| Swagger UI | https://realestate-roh-api.onrender.com/docs |
| 지표 수집 상태 | https://realestate-roh-api.onrender.com/indicators/status |

- 웹 화면은 팀 Vercel 이 이 저장소 main 을 배포합니다. `/api/*` 는 `frontend/vercel.json` 이 API 서버(Render `realestate-roh-api`)로 넘기고 응답을 CDN 에 캐시합니다.
- API 서버와 지표 DB(Supabase)는 지표 담당 계정에서 운영하며, 매일 수집(GitHub Actions)도 그 계정의 포크([ksroh1913/realestate_roh](https://github.com/ksroh1913/realestate_roh))에서 돕니다. 백엔드 변경은 그 포크의 `feat/indicator-api` 에 반영되면 배포됩니다.
- Google 로그인과 이용 기록(`activity_logs`)은 화면이 팀 Supabase 에 직접 기록합니다.

---|---|
| 대시보드 | https://realestateroh-frontend.vercel.app |
| API 연동 실습 페이지 | https://realestateroh-frontend.vercel.app/demo.html |
| Swagger UI | https://realestate-roh-api.onrender.com/docs |
| 지표 수집 상태 | https://realestate-roh-api.onrender.com/indicators/status |
| CDN 경유 API (화면이 부르는 주소) | https://realestateroh-frontend.vercel.app/api/indicators/bundle?set=all |

---

## 만든 사람들

KHMI는 KAIST 디지털금융 MBA 졸업생들이 함께 시작한 서비스입니다.

## 알림

- KHMI가 제공하는 정보는 공공 통계를 정리한 참고 자료이며, 투자 권유나 가격 예측이 아닙니다.
- 각 통계의 저작권은 원 작성기관에 있습니다. 시도 경계 지도는 통계청 SGIS(2018) 자료를 공공누리 제1유형에 따라 사용했습니다.
