# 수동 입력

API 키가 없거나 유료·PDF 로만 공표되는 자료(예: 도쿄 임대료·소득, 토론토·밴쿠버 기존주택 가격)를 직접 넣는 곳이다.

1. `manual_observations_template.csv` 를 복사해 `manual_observations.csv` 로 저장한다.
2. 한 행 = 한 관측치. 필수 열: `city_id, variable, period, value, unit, source_id, source_url`.
   - `variable` 은 `configs/series.yaml` 머리말의 표준 변수명(예: `rent_month`, `hh_income`, `price_level`).
   - `period` 는 연 `2024`, 분기 `2024-Q3`, 월 `2024-09`.
   - 단위는 표준 단위로 맞춘다: 월 임대료 `JPY/month`, 연소득 `JPY/year`, 가격 `JPY`.
   - PDF 에서 옮겨 적으면 `notes` 에 문서명·쪽·표 번호·원문 값·단위를 남긴다.
3. `quality_flag` 를 비우면 C 로 처리한다. `python -m src.run --offline` 으로 다시 계산한다.

같은 도시·변수에 자동 수집 계열이 이미 있으면 지표 단계가 오류로 멈춘다(계열은 도시·변수당 하나).
그 경우 `variable` 이름을 바꿔(예: `rent_month_manual`) 보조 계열로 넣는다.
