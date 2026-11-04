# 글로벌 도시 주택시장 비교 — 서울의 렌트 부담은 어느 수준인가

서울과 해외 10개 도시(런던·파리·도쿄·홍콩·싱가포르·뉴욕·샌프란시스코·토론토·밴쿠버·시드니)의
매매가격·임대료 수준, **소득 대비 임대료(렌트 부담)**, 소득·임대료 대비 가격, 과거 대비 괴리를 공개자료로 비교하는
재실행 가능한 파이프라인이다. UBS Global Real Estate Bubble Index 2026(pp.26–27)을 참고했지만 UBS 의 계열 코드·가중치·
위험등급을 복제하지 않는다. 설계: [docs/설계서_글로벌비교.md](docs/설계서_글로벌비교.md), UBS 원문 메모: [docs/ubs_2026_방법론_메모.md](docs/ubs_2026_방법론_메모.md).

- 분석 기준일 **2026-11-04** (`configs/project.yaml` 의 `as_of` 로 바꿀 수 있다)
- 결과 보고서: [outputs/report_ko.md](outputs/report_ko.md) · Excel: `outputs/global_housing_comparison.xlsx`
- KHMI 서비스(상위 폴더 `backend/`·`frontend/`)와 독립된 분석 프로젝트다. 서비스 코드와 배포에는 영향이 없다.

## 실행

```bash
cd global_housing
pip install -r requirements.txt
```

```bash
python -m src.run --config configs/project.yaml --stage all --env-file ../backend/.env
```

```bash
python -m src.run --config configs/project.yaml --offline
```

```bash
python -m pytest
```

- `--stage all` = 수집 → 정제 → 검증 → 지표 → 도표 → 내보내기 → 보고서. 단계를 골라 `--stage clean,metrics` 처럼 돌릴 수 있다.
- `--offline` 은 내려받지 않고 `data/raw` 에 커밋된 원자료만으로 전부 다시 만든다.
- `--only kr_rone,uk_hpi` 로 일부 출처만 다시 받는다. `--refresh` 는 이미 받은 서울 실거래 연도 파일도 다시 받는다.
- API 키는 서울 자료(`kr_rone`·`kr_rtms`·`kr_kosis`)에만 필요하다(`.env.example`). 키 값은 저장·출력하지 않고 manifest 에도 `***` 로 가린다.
  키가 없으면 해당 출처만 `unavailable` 로 기록하고 기존 원자료로 계속한다.

## 구조

```text
configs/project.yaml   기준일·기준연도 후보·면적(60㎡, 50~70㎡)·보증금 환산 시나리오·합성지수 규칙
configs/cities.yaml    11개 도시, 지역 범위, UBS p.27 기관 목록
configs/series.yaml    도시별 계열 선택(지역·주택유형·면적·소득개념·품질등급·원자료 위치) — 도시·변수당 계열 하나
configs/gaps.yaml      미확보 항목과 이유
src/fetch/*.py         출처별 수집 (재시도·시간제한·호출 간격, 네트워크 실패와 '자료 없음' 구분)
src/clean/*.py         원자료 → 표준 long format (설계서 8절 필수 필드)
src/metrics.py         연간화, PIR·PTR·수익률·소득 대비 임대료, USD·PPP 환산, 실질 경로, 상대지수, 서울 보증금 민감도, 선택 합성지수
src/validate.py        중복·0/음수·도약·단위 배율·월/연 환산·지역 혼용·PTR/수익률 역수 검사
src/charts.py · export.py · report.py
data/raw/              원자료(변경 없음). 큰 원본은 필요한 행만 부분집합으로 두고 _manifest.csv 에 원본 URL·sha256·거른 조건 기록
data/manual_inputs/    수동 입력 양식 (도쿄 등 키·유료 자료)
data/processed/        지표 산출물 (outputs 의 원본)
outputs/               보고서·Excel·차트·source_catalog·coverage_matrix
tests/                 인공 자료는 tests 안에서만 사용
```

## 확보한 자료 (2026-11-04 수집)

| 도시 | 가격 수준 | 임대료 수준 | 가구소득 | 근로자 소득 | 가격지수 | 임대지수 |
|---|---|---|---|---|---|---|
| 서울 | 실거래 60㎡ 환산 2024–25 | 실거래 월세+보증금 환산 2024–25 | 가계금융복지조사 평균 2016–24 | 사업체노동력조사 2011–25 | R-ONE 2003– | R-ONE 2016– |
| 런던 | UK HPI 플랫 | ONS PIPR 플랫 2015– | — | ASHE 2005– | UK HPI | PIPR 2015– |
| 파리 | DVF 60㎡ 2024–25 | Carte des loyers 2023–25 | — | — | INSEE | INSEE(광역권) |
| 도쿄 | — | — | — | — | 국토교통성 2008– | — |
| 홍콩 | RVD Class B | RVD Class B | C&SD 중위 | C&SD 중위 | RVD | RVD |
| 싱가포르 | HDB 60㎡ (민간 수준 미확보) | HDB 3-room | 취업가구 근로소득 중위 | MOM 상근 중위 | URA | URA |
| 뉴욕·SF | Zillow ZHVI | Zillow ZORI·ACS | ACS 중위 2021–25 | — | ZHVI | ZORI 2015– |
| 토론토·밴쿠버 | — | CMHC 2침실 | StatCan 중위 | — | NHPI(신규, C) | CPI 임차주거 |
| 시드니 | ABS 공동주택 중위 | 2021 센서스 | 2021 센서스 | — | ABS 중위(C) | — |

전체 목록·기간·품질은 `outputs/source_catalog.csv`, `outputs/coverage_matrix.xlsx`.

## 주요 결과 (자세한 표·주의점은 보고서)

공통연도 2024 (서울 포함 9개 도시에서 PTR 또는 소득 대비 임대료 계산 가능).

- **서울 60㎡ 아파트**(전용 50~70㎡ 실거래 중위): 가격 8.40억 원, 보증금 환산 월 임대료 166만 원 → PTR 42.3년, 총임대수익률 2.4%.
  품질 A/B 인 4개 도시(서울·홍콩·파리·런던) 중 PTR 이 가장 높다.
- **렌트 부담**: 연 환산 임대료 ÷ 서울 가구 평균 경상소득 = 24.3% (현금 월세만 13.4%). 다른 도시는 대부분 중위소득이라 순위를 매기지 않는다.
  서울 중위소득 추정치(품질 C) 기준 31.0% — 홍콩 68.7%, 뉴욕 38.4% 보다 낮고 샌프란시스코 25.7% 보다 높다(보조 비교, 4개 도시).
- 근로자 1인 소득 기준(정의가 도시마다 달라 순위 없음): 서울 37.4%(상용근로자 평균), 런던 49.8%(상근 중위), 홍콩 103.0%(취업자 중위).
- 보증금 환산율을 ±1%p 바꾸면 서울 환산 임대료는 150만~182만 원, PTR 38.5~46.8년 (2024).
- 2019=100 가격/임대료 상대지수: 서울 101.9(2025) — 런던·파리·홍콩·토론토·밴쿠버·싱가포르는 100 아래, 뉴욕·샌프란시스코는 위.

## 미완료 항목

- 도쿄: 임대료 수준·지수, 소득, 가격 수준 (e-Stat appId·유료 자료 필요 → `data/manual_inputs`)
- 런던·파리 가구소득, 파리·토론토·밴쿠버·시드니 근로자 소득
- 토론토·밴쿠버 기존주택 가격 수준(CREA·Teranet), 싱가포르 민간주택 가격·임대료 수준(URA API 키)
- 시드니 2022년 이후 임대료·소득 수준(센서스 2021 한 시점만)
- 국가별 주택담보대출/GDP, 건설투자/GDP → 설계서 6.1 합성지수는 전 도시 NA. 이름을 달리한 '가격괴리 3항목'만 제공
- 6.2 회귀(도시·연도 고정효과)는 패널이 짧아 구현하지 않음
- 홍콩 C&SD API 는 재수집 때 403 을 돌려줘 첫 수집분(2026-11-04)을 사용

## 자료 이용 조건

각 원자료의 저작권과 이용 조건은 해당 기관을 따른다(ONS·HM Land Registry: Open Government Licence, data.gov.sg: Singapore Open Data Licence,
U.S. Census Bureau: 공공 저작물, Zillow: Zillow Research 이용 조건, RVD·C&SD: 홍콩 정부 저작권 — 출처 표기 비상업적 이용, 공공데이터포털·KOSIS·R-ONE: 각 이용약관).
