# 정량 지표 파이프라인 — 외부 Open API → DB 캐시 → `/indicators`

> 작성 2026-10-14 · 담당 노경수. 발표 자료의 **서비스 아키텍처 · 사용 데이터 및 출처 · API 설명 문서 · DB 테이블 문서** 항목에 그대로 쓸 수 있게 정리했다.

## 1. 한 장 요약

```
한국부동산원 R-ONE ─┐                                   ┌─ GET /indicators/bundle ──▶ Vercel 대시보드(Home·Overview·동인)
한국은행 ECOS ─────┼─▶ FastAPI 수집기 ─▶ Supabase PostgreSQL ─┼─ GET /indicators/{var} ──▶ demo.html · Swagger
통계청 KOSIS ─────┘   (정규화·UPSERT)   indicator_* 3개 테이블  └─ GET /indicators/status ─▶ 수집 모니터
        ▲                                                           ▲
        │  하루 1회 GitHub Actions cron ─▶ POST /indicators/refresh (관리자 토큰)
        │  또는 python scripts/collect_indicators.py                │
        └────────── 사용자 요청 경로에서는 외부 API 를 부르지 않는다 ─┘ (DB 에 아예 없을 때 1회 예외)
```

**두 계층 (2단계, 2026-10-17)** — 화면이 쓰는 51개 변수·106개 계열은 모두 DB 에서 나온다.

| 계층 | 테이블 | 채우는 방법 | 범위 |
|---|---|---|---|
| 기본 패널 | `indicator_series` · `indicator_series_values` | `python scripts/seed_indicators.py` 로 전처리본(DFMBA, `factor_sample.json` 형식)을 한 번 적재 | 51개 변수 전체 (시도·서울 구·서울·전국) |
| 실제 수집값 | `indicator_observations` | Open API 수집 (매일 Actions · CLI · lazy) | 레지스트리의 Open API 변수 (현재 9개) |

`GET /indicators/bundle?set=all` 은 기본 패널을 읽는다. Open API 로 받는 변수는 수집할 때마다 같은 패널 계열에 바뀐 값만 이어붙이므로(5단계), 매일 새 값과 아직 API 로 옮기지 않은 변수의 전처리본 값이 같은 응답 하나로 나간다. API 로 갱신되는 계열은 응답에 `live: true`, `origin: "db(api)"`, `fetched_at` 이 붙는다. 정적 파일은 DB 에 넣을 원본(시드)으로만 남는다.

핵심 아이디어는 교재 06의 **"있으면 DB 에서, 없으면 API 에서"** 를 월 단위 통계에 맞게 확장한 것이다. 값이 한 달에 한 번 바뀌는 자료를 사용자가 볼 때마다 외부 기관에 묻는 대신, **DB 를 외부 API 의 영속 캐시**로 쓰고 갱신은 하루 한 번 스케줄로 돌린다.

## 2. 캐시 4계층 (3단계, 2026-10-17)

화면은 같은 주소의 `/api/…` 를 부르고, Vercel 이 `frontend/vercel.json` 의 rewrite 로 Render 에 전달하면서 응답을 CDN 에 보관한다. 화면과 API 가 같은 주소라 CORS 설정이 필요 없다.

| 층 | 위치 | 수명 | 역할 |
|---|---|---|---|
| ① 브라우저 | `Cache-Control: public, max-age=300` + `ETag` | 5분 | 같은 사용자가 화면을 오가도 요청 자체가 안 나간다. 바뀐 게 없으면 `304 Not Modified` |
| ② Vercel CDN | `CDN-Cache-Control: public, max-age=3600, stale-while-revalidate=86400, stale-if-error=604800` | 1시간 + 1일 + 7일 | 1시간은 CDN 이 바로 응답. 그 뒤 1일은 보관본을 먼저 주고 뒤에서 갱신 → **Render 무료 플랜이 잠들어 있어도 사용자는 기다리지 않는다**. Render 오류·장애 때는 7일까지 보관본으로 응답. `Vercel-Cache-Tag: indicators` 로 태그 단위 비우기 가능 |
| ③ 메모리 TTL | `backend/app/services/cache.py` | 10분 | 같은 응답 JSON 을 DB 에서 다시 만들지 않는다. 수집이 끝나면 비운다 |
| ④ DB (영속 캐시) | `indicator_observations`(실제 수집값) · `indicator_series_values`(기본 패널) | 갱신 전까지 | 외부 API 응답을 정규화해 저장. **모든 조회는 여기서만** |

수집 모니터(`/indicators/status`)와 관리자 수집 응답은 `no-store` 로 어느 층에도 보관하지 않는다. 오류 응답(404·5xx)에는 캐시 헤더가 없어 CDN 이 보관하지 않고, 대신 `stale-if-error` 로 직전 정상 응답을 준다. 매일 수집 뒤 GitHub Actions 가 화면 주소(`SITE_BASE_URL`)의 `/api/indicators/bundle` 을 두 번씩 불러 CDN 을 새 응답으로 채운다(예열).

| `vercel.json` | 내용 |
|---|---|
| `rewrites` | `/api/:path*` → `https://<Render 주소>/:path*` (쿼리 문자열은 그대로 전달) |
| `headers` | `/api/:path*` 에 `x-vercel-enable-rewrite-caching: 1` — 2026-04-06 이전에 만든 Vercel 프로젝트에서도 rewrite 응답 캐시를 켠다 |

갱신 판단은 변수마다 `last_fetched_at` 과 `INDICATOR_REFRESH_HOURS`(기본 24, 매일 수집 시각이 흔들려도 건너뛰지 않게 2시간 여유) 로 한다. 신선하면 `skipped`, 오래됐으면 **최근 12개월만 다시 받아** 잠정치 수정분을 반영한다(증분 수집). 요청이 왔는데 오래됐으면 DB 값을 먼저 돌려주고 뒤에서 갱신한다(stale-while-revalidate, FastAPI `BackgroundTasks`).

응답의 `origin` 필드가 어느 층에서 왔는지 말해 준다 — `db(cache)` 는 DB 의 실제 수집값, `db(panel)` 은 DB 의 기본 패널, `api(R-ONE)` 은 DB 에 없어 방금 받아 저장한 뒤 응답한 경우다. 발표 때 Swagger 에서 같은 변수를 두 번 호출해 `origin` 과 `duration_ms`(`/indicators/status` 의 수집 로그) 를 비교하면 캐시 효과를 바로 보여 줄 수 있다.

## 3. 사용 데이터 및 출처

| 변수 | 지표 | 출처 (기관) | 통계표·항목 | 단위·주기·범위 |
|---|---|---|---|---|
| V002 | 아파트 매매가격지수 | 한국부동산원 R-ONE | `A_2024_00045` / 지수 | 2021.06=100 · 월 · 17개 시도 |
| V026 | 아파트 전세가격지수 | 한국부동산원 R-ONE | `A_2024_00050` / 지수 | 2021.06=100 · 월 · 17개 시도 |
| V001 | 월세통합가격지수 | 한국부동산원 R-ONE | `A_2024_00054` / 지수 | 2021.06=100 · 월 · 17개 시도 |
| V003 | 아파트 전세가율 | 한국부동산원 R-ONE | `A_2024_00072` | % · 월 · 17개 시도 |
| V005 | 아파트 월세수급동향 | 한국부동산원 R-ONE | `A_2024_00078` | 지수 · 월 · 17개 시도 |
| V037 | 주택시장 소비심리지수 | 한국부동산원 R-ONE | `T232543129897499` | 지수 · 월 · 17개 시도 |
| V043 | 한국은행 기준금리 | 한국은행 ECOS | `722Y001` / `0101000` | 연% · 월 · 전국 |
| V045 | 국고채 3년 | 한국은행 ECOS | `721Y001` / `5020000` | 연% · 월 · 전국 |
| V056 | 주택담보대출 금리(신규) | 한국은행 ECOS | `121Y006` / `BECBLA0302` | 연% · 월 · 전국 |
| V004 · V031 · V032 · V035(2) · V036(2) · V038 | R-ONE 6개 (5단계 2차) + V002·V003·V026 서울 구 | 한국부동산원 R-ONE | `indicator_registry.py` 참고 (DFMBA `collect_rone.py` 와 같은 표) | 월 · 17개 시도 + 서울 구(화면에 있는 구) |
| V044 · V046 · V047 · V048 · V049 · V050 · V057 · V059 · V060 · V061~V063 · V064 · V066 · V067 · V069 · V070 · V071 | ECOS 18개 (5단계 1차) | 한국은행 ECOS | `indicator_registry.py` 참고 (DFMBA `collect_ecos.py` 와 같은 표·항목) | 월·분기 · 전국 (V050 만 17개 시도) |
| V009 · V010 · V011 · V012 · V013 · V015 · V017 · V021 · V022 · V023 · V024 · V072 · V074 · V076 | KOSIS 14개 (5단계 3차, 수집 단위 31개 → 화면 계열 43개) | 통계청 KOSIS (국토부·서울시 표 포함) | `indicator_registry.py` · `kosis_readers.py` 참고 (DFMBA `collect_kosis.py`·`prep_kosis_*.py` 와 같은 표·가공) | 월·반기·분기·연 · 17개 시도 + 서울 구 |

**KOSIS 표별 가공 (5단계 3차)** — 표마다 지역 코드 체계가 달라 `kosis_readers.py` 의 읽는 방식(reader)으로 나눴다. 주민등록 표(V009~V012)는 행정표준코드로 시도·서울 구를 고르고, 2026-07 광주·전남 통합 뒤에는 통합코드 아래 광주 5개 구로 광주 = 5개 구 합계, 전남 = 통합 - 광주 를 복원한다. V011 은 1세별 인구를 더해 20–29세·30–39세·20–39세와 비중(%)을 만들고, V021 인허가는 월별 누계라 전월 누계를 뺀다. V015·V017 전국대비는 같은 해 전국 값으로 나누고, V024·V076 천 세대당은 그해 12월 주민등록세대수로 나눈다. V074 는 구계열이 2019Q4 에 끝나 2020Q1 부터 신계열(DT_1L9V121) x 0.9417(2019년 4개 분기 평균 비율)로 잇는다. 같은 표를 여러 수집 단위가 쓰면(예: V011 4개 계열) 클라이언트가 한 번만 부른다. DFMBA 원자료로 대조한 결과 43개 계열 약 3만 값이 기본 패널과 같았고, 다른 곳은 V012 광주·전남 2026-07~08 4칸뿐이었다(기본 패널은 통합 뒤 0 으로 오는 옛 코드를 그대로 썼고, 수집기는 복원값을 쓴다). V021~V023 의 2024년까지 빈 달 보완값과 V074 구계열 구간은 원자료에 없어 기본 패널 값을 그대로 둔다(2025년부터는 0 도 공표된다).

**국토부 실거래 이후분 (6단계)** — 실거래(V006 전월세 · V007 매매)는 건별 원자료라 매번 전 기간을 받을 수 없다(시군구 256개 x 월 x 페이지, 데이터포털 일일 호출 한도). 그래서 DFMBA 가 2026-10 초까지 받아 만든 월별 건수는 기본 패널 값을 그대로 쓰고, 최근 6개월만 다시 받는다. `scripts/collect_rtms.py`(`services/rtms.py`) 가 GitHub Actions 러너에서 매일 시군구-월을 급한 순(한 번도 안 받은 것 → 최근 달 → 오래 묵은 것)으로 부르되 유형마다 하루 `RTMS_BUDGET`(기본 1,000회)을 넘지 않는다. 계약 0~1개월 전 달은 하루마다, 2~3개월 전은 3일마다, 4~5개월 전은 7일마다 다시 받는다(신고기한 30일, 매매 해제 5개월 안에 98.9%). 받은 건수는 `rtms_progress` 에 시군구·월 단위로만 저장하고(원자료 행은 저장하지 않음), 레지스트리의 MOLIT 수집 단위 4개(V006 전체·월세·전세, V007)가 이를 시도(소속 시군구를 모두 받은 달만)·서울 구로 합쳐 다른 지표처럼 바뀐 값만 화면 계열에 반영한다. 이번 달은 막 시작해 건수가 거의 없으므로 화면에는 내지 않고, 마지막 3개월은 잠정으로 표시한다. DFMBA 원자료로 시군구 건수를 만들어 넣어 본 결과 2026-04~09 의 시도·서울 구 값 520여 개가 기본 패널과 모두 같았다. 한도에 걸리면 받은 데까지 저장하고 멈추며 다음 날 이어받는다.

5단계에서 데이터사전 51개 중 47개를 같은 방식으로 붙인다(ECOS 21 → R-ONE 12 → KOSIS 14). 실거래 2개는 예외(호출 한도 안에서 이후분만), 끝난 통계 2개(V034 · V077)는 적재값을 그대로 쓴다. 변수별 표는 계획서의 '변수별 수집 방식' 절.

**R-ONE 지역·페이지 처리 (5단계 2차)** — 지역은 `CLS_FULLNM` 의 마지막 조각으로 판정한다(`regions.parse_rone_region`, DFMBA 와 같은 규칙): '전남광주>광주'·'(구)광주' → 광주(2026 광주·전남 통합 뒤 표기), '경기>계' → 경기(거래현황·미분양의 시도 합계행), '서울>강남지역>동남권>강남구' → 강남구, 권역 중간행은 제외. R-ONE 은 페이지를 넘기면 행이 빠질 수 있어(DFMBA 실측) 한 번에 1,000행 이하가 되도록 기간을 반씩 나눠 받고 고유 행 수를 총건수와 대조한다. 미분양(V038)은 0 인 구의 행이 없으므로, 서울 25개 구 합계가 서울 값과 같은 달은 빠진 구를 0 으로 채운다. DFMBA 원자료로 대조한 결과 12개 변수 27개 계열 모두 기본 패널 값과 같았다.

### 매일 수집 규칙 (5단계)

1. 매일 09:40 GitHub Actions 가 출처별로 `POST /indicators/refresh?source=R-ONE|ECOS|KOSIS` 를 부른다.
2. 변수마다 최근 12개월을 다시 받는다(새로 공표된 달 + 공표 뒤 수정분). 분기·연 계열은 2016년부터 다시 받는다(행이 적다).
3. **바뀐 값만 저장한다.** 받은 값을 DB 와 비교해 새로 생긴 것(`new`)·달라진 것(`changed`)만 쓰고, 같은 것(`unchanged`)은 쓰지 않는다. SQL 도 `ON CONFLICT … DO UPDATE … WHERE value IS DISTINCT FROM excluded.value` 라 같은 값은 다시 쓰지 않는다.
4. 받은 값은 화면용 계열(`indicator_series_values`)에도 이어붙인다. 레지스트리의 `outputs` 가 '어느 패널 계열에, 어느 지역만' 을 정한다. 겹치는 시점은 바뀐 값만 고치고 새 시점은 뒤에 붙이며, 계열 시작 이전과 화면에 없는 지역은 쓰지 않는다(화면에서 쓰는 데이터만).
5. 바뀐 값이 하나라도 있을 때만 메모리 캐시를 비우고 CDN 을 예열한다. 대부분의 날은 `changed=0` 이라 캐시가 그대로 유지된다.

| 레지스트리 항목 | 뜻 | 예 |
|---|---|---|
| `id` / `var` | 수집 단위 / 데이터사전 변수. 한 변수를 여러 번 부르면 `V069.1`·`V069.2` | V069 가계대출 전체·주택관련 |
| `params.segments` | 기간에 따라 통계표가 바뀌는 계열 | V066 임금: 10차 표(~2025) · 11차 표(2026~) |
| `params.region_items` | 지역마다 항목 코드가 다른 표 | V050 지역별 주택대출: 서울 A00 … 제주 U00 (17회 호출) |
| `outputs` | 이어붙일 패널 계열 (`scope`, `match`, `regions`, `rename`) | V061 CSI: ECOS '전국' 값을 '서울 권역' 계열로 |

| 출처 | 명칭 | 제공 기관 | URL | 수집 방식 | 이용 조건 |
|---|---|---|---|---|---|
| R-ONE | 부동산통계정보 Open API | 한국부동산원 | https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do | `SttsApiTblData.do` JSON, 월별, 1,000행 페이지 | 공공누리 제1유형(출처표시), 인증키 |
| ECOS | 경제통계시스템 Open API | 한국은행 | https://ecos.bok.or.kr/api/ | `StatisticSearch` JSON | 한국은행 Open API 이용약관(출처표시), 인증키 |
| KOSIS | 공유서비스 Open API | 통계청 | https://kosis.kr/openapi/ | `statisticsParameterData.do` JSON | 공공누리 제1유형(출처표시), 인증키 |

출처·코드·이용 조건은 코드의 `backend/app/services/indicator_registry.py` 한 곳에 적혀 있고 `GET /indicators` 응답의 `sources` 로도 나온다. 변수를 더 붙일 때도 이 파일에 한 항목만 추가한다.

시작 시점은 화면 기본본과 같은 2016-01 이다. 월세통합가격지수(V001)는 API 가 현행 계열만 주므로 기본본의 구지수 연결 구간보다 짧다 — 화면은 둘 중 더 최신 시점을 가진 계열을 쓴다.

## 4. API 설명 문서

기본 주소: Render 배포 주소(README). 대화형 문서는 `/docs`(Swagger UI), 명세는 `/openapi.json`.

### GET `/indicators` — 등록된 지표와 수집 상태

입력값 없음. 응답 `200`:

```json
{
  "variables": [
    {"id": "V002", "label": "아파트 매매가격지수", "driver": "finance", "source": "R-ONE", "source_ref": "R-ONE A_2024_00045",
     "freq": "M", "scope": "sido", "unit": "", "enabled": true, "item": "지수",
     "first_period": "2016-01", "last_period": "2026-08", "rows": 2176,
     "last_fetched_at": "2026-10-14T00:41:12+00:00", "last_status": "ok", "last_error": null, "stale": false}
  ],
  "sources": {"R-ONE": {"name": "한국부동산원 부동산통계정보 R-ONE Open API", "organization": "한국부동산원", "url": "…", "license": "…"}},
  "refresh_hours": 24
}
```

### GET `/indicators/{var}` — 변수 하나의 시계열

| 입력 | 위치 | 설명 |
|---|---|---|
| `var` | 경로 | 변수 ID (`V002`). 대소문자 무관 |
| `regions` | 쿼리, 선택 | 쉼표 구분 지역 (`서울,경기`). 전국 계열(`scope=nation`)은 무시 |
| `start` | 쿼리, 선택 | 시작 시점 `YYYY-MM` |
| `scope` | 쿼리, 선택 | 지역 단위 `sido`·`gu`·`seoul`·`nation`. 비우면 sido → seoul → nation → gu 순 |

Open API 변수는 실제 수집값, 그 밖의 변수(또는 키가 없을 때)는 기본 패널에서 준다(`origin: "db(panel)"`, `live: false`, 원자료 열 `column`·보완 칸 수 `filled`·잠정 시작 `provisional_from` 포함).

응답 `200` — `frontend/data/factor_sample.json` 의 `metrics[]` 한 항목과 같은 모양이라 화면 코드가 그대로 쓴다:

```json
{"var": "V002", "label": "아파트 매매가격지수", "unit": "", "freq": "M", "scope": "sido",
 "periods": ["2016-01", "2016-02", "…", "2026-08"],
 "series": {"서울": [87.1, 87.3, "…", 102.4], "부산": ["…"], "…": "…"},
 "source": "R-ONE A_2024_00045", "source_name": "한국부동산원 부동산통계정보 R-ONE Open API", "source_url": "…",
 "method": "원자료 그대로 (2021.06=100)", "release": "조사기준 월 익월 15일 전후 공표", "item": "지수",
 "live": true, "fetched_at": "2026-10-14T00:41:12+00:00", "origin": "db(cache)", "stale": false}
```

빈 달은 `null` 로 채워 `periods` 와 각 `series` 배열의 길이를 맞춘다. 오류: `404` 미등록·미연동 변수, `502` DB 에 없어 외부 API 를 불렀는데 실패, `503` DB 에 없고 인증키도 없음. 헤더 `ETag`·`Cache-Control: public, max-age=3600`, `If-None-Match` 가 같으면 `304`.

### GET `/indicators/bundle` — 여러 변수를 한 번에

| 입력 | 설명 |
|---|---|
| `set` | `live`(기본): Open API 수집 변수만 · `all`: 기본 패널 51개 변수 전체 + 수집 변수는 실제 수집값으로 (화면 전체용) |
| `vars` | 쉼표 구분 변수 ID. 비우면 전체 |
| `regions`, `start` | 위와 같음 |

응답 `200`: `{"generated": "…", "set": "all", "origin": "db(panel+cache)", "regions": {"sido": [17개], "gu": ["강남구", "마포구", "노원구"], "nation": ["전국"]}, "aliases": {"V033": "V005"}, "panel": {"generated": "…", "loaded_at": "…"}, "metrics": [MetricOut…], "missing": []}`. `set=all` 은 `factor_sample.json` 과 같은 내용(약 0.76MB, gzip 압축 전송)이다. 한 변수가 실패해도 나머지는 준다(`missing` 에 표시). `set=all` 에서 아직 한 번도 수집하지 않은 Open API 변수는 기다리지 않고 기본 패널로 응답한 뒤 뒤에서 수집한다.

### GET `/indicators/status` — 수집 모니터

입력 `limit`(기본 50, ≤300). 응답: `variables`(위와 같음) + `panel`(기본 패널 변수·계열·값 수, 전처리본 생성 정보, 적재 시각) + `logs`(최근 수집 기록: `variable_id`, `started_at`, `duration_ms`, `status`, `trigger`(cli·admin·lazy·background), `rows_received`, `rows_upserted`, `last_period`, `error`) + `storage`(sqlite/postgresql, 영속 여부) + `keys`(출처별 인증키 설정 여부) + `refresh_hours`.

### POST `/indicators/refresh` — 외부 API 수집 (관리자)

| 입력 | 위치 | 설명 |
|---|---|---|
| `X-Admin-Token` | 헤더, 필수 | 서버 환경변수 `POLICY_ADMIN_TOKEN` 과 같아야 한다 (정책 수집과 공용) |
| `vars` | 쿼리, 선택 | 쉼표 구분 변수 ID. 비우면 `enabled` 전체 |
| `force` | 쿼리, 선택 | `true` 면 신선해도 전체 기간 재수집 |
| `source` | 쿼리, 선택 | `R-ONE` · `ECOS` · `KOSIS` 중 하나만 수집 (Actions 가 출처별로 나눠 부른다) |

응답 `200`: `{"status": "ok" | "partial", "checked_at": "…", "changed": 3, "results": [{"id": "V043", "status": "ok" | "skipped" | "error", "rows": 12, "new": 1, "changed": 0, "unchanged": 11, "panel_written": 1, "last_period": "2026-09", "duration_ms": 840, "reason": "fresh", "error": null}]}`. `changed` 는 새로·수정된 값의 합이고 0 이면 캐시를 비우지 않는다. 오류: `401` 토큰 불일치, `409` 이미 수집 중, `503` 토큰 미설정 또는 DB 쓰기 실패. GET 요청은 절대 외부 수집·DB 쓰기를 하지 않는다(DB 에 변수가 아예 없을 때의 1회 lazy 수집 제외).

## 5. DB 테이블 문서

ORM `backend/app/db/models.py`, SQL `database/schema.sql`. 앱 시작 시 없는 테이블만 만들고 레지스트리를 `indicator_variables` 에 동기화한다. 외부 수집은 시작 시 하지 않는다.

```
indicator_variables (1) ──< indicator_observations (N)      PK (variable_id, region, period)   ← Open API 실제 수집값
                    (1) ──< indicator_fetch_logs (N)        FK variable_id
indicator_series    (1) ──< indicator_series_values (N)     PK (series_id, region, period)     ← 기본 패널(전처리본)
```

**indicator_variables** — 변수(지표) 1개 = 1행. 코드 레지스트리의 사본 + 수집 상태.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | VARCHAR(10) **PK** | 데이터사전 변수 ID (`V002`) |
| `label`, `driver`, `source`, `source_ref` | TEXT/VARCHAR | 이름, 동인, 출처(R-ONE·ECOS·KOSIS), 통계표·항목 코드 |
| `freq`, `scope`, `unit`, `release` | VARCHAR/TEXT | 주기(M·Q·A), 지역단위(sido·nation), 단위, 공표 시기 |
| `enabled` | BOOLEAN | `false` 면 수집·조회 제외 (코드 확인 전 변수) |
| `item_name` | TEXT | 실제 수집한 항목명 (R-ONE `ITM_NM` 등) |
| `first_period`, `last_period` | VARCHAR(10) | DB 에 있는 첫·마지막 시점 |
| `last_fetched_at`, `last_status`, `last_error` | | 마지막 성공 시각(UTC), never·ok·error, 오류 메시지 |
| `updated_at` | VARCHAR(40) | 행 갱신 시각 |

**indicator_observations** — 관측값 1개 = 1행. 9개 변수 × 17개 시도 × 128개월 ≈ 2만 행.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `variable_id` | VARCHAR(10) **PK·FK** → `indicator_variables.id` | |
| `region` | VARCHAR(30) **PK** | 17개 시도 짧은 이름 또는 `전국` (기관별 표기는 `regions.py` 가 통일) |
| `period` | VARCHAR(10) **PK** | `2026-08` · `2026-Q1` · `2026` |
| `value` | DOUBLE PRECISION | 값 |
| `fetched_at` | VARCHAR(40) | 이 값을 받은 시각 |

기본키가 (변수, 지역, 시점) 이라 재수집은 `INSERT … ON CONFLICT (variable_id, region, period) DO UPDATE` 로 제자리 갱신된다 — 중복이 쌓이지 않고 잠정치가 확정치로 바뀌어도 행 수가 늘지 않는다 (교재 06 §7.2 의 UPSERT 와 같은 문법, SQLite·PostgreSQL 공통). 인덱스 `(variable_id, period)`.

**indicator_fetch_logs** — 수집 1회 = 1행.

| 컬럼 | 설명 |
|---|---|
| `id` SERIAL PK, `variable_id` FK | |
| `started_at`, `duration_ms` | 시작 시각, 소요 시간(ms) — 캐시 효과 근거 |
| `status`, `trigger` | ok·error / cli·admin·lazy·background |
| `rows_received`, `rows_upserted`, `last_period`, `error` | 받은 행·저장 행·최신 시점·오류 |

**indicator_series** — 기본 패널의 계열 1개 = 1행 (106행). 한 변수가 지역 단위·세부 항목별로 여러 계열을 가진다(예: V006 실거래 신고건수 매매·전세·월세).

| 컬럼 | 설명 |
|---|---|
| `id` VARCHAR(80) **PK** | `{scope}:{원자료 열}` 예: `sido:Y_V001_월세통합가격지수(구지수연결)` |
| `var_id`, `scope`, `column_name` | 변수 ID, 지역 단위(sido·gu·seoul·nation), 전처리본 원자료 열 |
| `label`, `unit`, `freq`, `periods` | 이름, 단위, 주기(M·Q·H·A), 시점 목록(JSON, 값 배열 순서) |
| `source`, `method`, `release` | 출처 코드, 보완·연결 방법, 공표 시기 |
| `filled`, `provisional_from` | 보완한 칸 수, 잠정값 시작 시점 |
| `sort_order`, `dataset`, `loaded_at` | 원본 순서, 전처리본 생성 정보, 적재 시각 |

**indicator_series_values** — 값 1개 = 1행 (약 8만 행). PK (`series_id` FK, `region`, `period`), `value`. 빈칸은 저장하지 않는다. 다시 적재하면 계열별로 지우고 다시 넣고, 파일에서 빠진 계열은 지운다. 지역 목록·변수 별칭은 `content_snapshots['indicator-panel']` 에 둔다.

정성 자료 테이블(`content_snapshots`, `policy_*`)은 `database/README.md` 참고. 모든 테이블은 RLS 를 켜고 브라우저는 FastAPI 를 통해서만 읽는다.

## 6. 운영 절차

```powershell
# 1) 키 설정: backend/.env 에 RONE_API_KEY, ECOS_API_KEY, KOSIS_API_KEY, DATA_GO_KR_API_KEY(실거래)
# 2) 실제 항목·지역 이름 확인 (처음 한 번, 변수별)
python scripts/collect_indicators.py --probe V002
# 3) 수집 → DB (없으면 backend/local.db)
python scripts/collect_indicators.py
python scripts/collect_indicators.py --vars V043,V045,V056 --force
# 4) 기본 패널 적재 (처음 한 번, 새 전처리본이 나오면 다시)
python scripts/seed_indicators.py            # frontend/data/factor_sample.json → indicator_series·indicator_series_values
python scripts/seed_indicators.py --status
# 5) 확인
python scripts/collect_indicators.py --status
fastapi dev backend/app/main.py      # http://127.0.0.1:8000/docs → /indicators/V002 두 번 호출해 origin 비교
# 실거래(V006·V007) 이후분: 호출 한도 안에서 최근 6개월 → 시도·서울 구 합계 반영
python scripts/collect_rtms.py --budget 1000
python scripts/collect_rtms.py --status
# 6) 서버 없이 볼 정적 스냅샷 (선택)
python scripts/collect_indicators.py --export frontend/data/factor_live.json
```

Supabase 연결은 `DATABASE_URL`(Session pooler) 만 바꾸면 된다(`database/README.md`). Render 환경변수에 `RONE_API_KEY`·`ECOS_API_KEY`·`KOSIS_API_KEY`·`POLICY_ADMIN_TOKEN` 을 넣고, GitHub 저장소 Secrets 에 `POLICY_API_BASE_URL`·`POLICY_ADMIN_TOKEN` 을 넣으면 `.github/workflows/collect-indicators.yml` 이 매일 09:40(KST) 수집을 호출한다. Render 무료 플랜이 잠들어 있어도 워크플로가 `/health` 로 먼저 깨운다.

## 7. 알려진 한계와 다음 단계

- R-ONE 통계표의 항목명(`ITM_NM`)·지역명(`CLS_NM`)은 표마다 다르다. 레지스트리의 `item` 은 '지수' 부분 일치로 잡아 두었고, `--probe` 로 실제 이름을 보고 다르면 고친다. 응답 `Type=json` 의 한글 인코딩 선언이 빠진 사례가 보고돼 `resp.encoding = "utf-8"` 로 고정했다.
- 일일 호출 한도(R-ONE `ERROR-337`)를 넘기지 않도록 사용자 요청 경로에서는 외부 API 를 부르지 않고, 수집도 변수당 하루 1회·증분(최근 12개월)으로 제한했다.
- KOSIS 는 한 번에 4만 셀까지만 준다. 넘으면 오류 31 로 멈추게 했다(예전처럼 '자료 없음' 으로 넘기지 않는다). 표가 커지면 레지스트리의 `chunk`(연 단위로 나눠 받기)를 줄인다.
- 화면은 값을 모두 `GET /api/indicators/bundle?set=all`(DB)에서 읽는다(`factors.js`). `factor_sample.json` 은 DB 적재용 원본으로만 남고 화면은 읽지 않는다. 마지막 응답을 브라우저 localStorage 에 보관해 다시 오면 바로 그리고, 새 응답이 바뀌었을 때만 다시 그린다. 서버에 닿지 않으면 보관본으로 보여 주며 안내 줄과 '다시 시도' 버튼을 띄운다(보관본도 없으면 안내만). CDN 이 서버 장애 때 7일까지 이전 응답을 주므로(stale-if-error) 보통은 여기까지 가지 않는다.
