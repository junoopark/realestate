-- 공통 지역(regions) 보강: 소속 권역과 R-ONE 관측 기간
-- 001_rone_rent_index.sql 다음에 실행. 다시 실행해도 안전하다.
--
-- region_key 규칙 (backend/app/services/region_mapper.py 가 R-ONE CLS_FULLNM 에서 만든다)
--   전국 / 수도권·5대광역시 등 묶음(zone)            : '전국', '수도권'
--   시도(sido)                                        : '서울', '광주', '전남', '전남광주'(2026 통합, 광주·전남의 상위)
--   R-ONE 권역(area)                                  : '서울>강북지역', '서울>강북지역>도심권', '경기>경부1권'
--   시·군·자치구(sigungu), 권역은 키에서 뺀다         : '서울>종로구', '경기>안양시', '부산>중구'
--   일반구(gu)                                        : '경기>안양시>만안구', '충북>청주시>상당구'
-- parent_key 는 행정 상위, area_key 는 소속 R-ONE 권역(구 단위 역산 등에 사용).

ALTER TABLE regions ADD COLUMN IF NOT EXISTS area_key VARCHAR(80) REFERENCES regions(region_key);
ALTER TABLE regions ADD COLUMN IF NOT EXISTS first_period DATE;  -- R-ONE 에 값이 처음 나온 기준월
ALTER TABLE regions ADD COLUMN IF NOT EXISTS last_period DATE;   -- 마지막 기준월 (개편으로 없어진 지역 확인용)
CREATE INDEX IF NOT EXISTS ix_regions_area_key ON regions(area_key);
CREATE INDEX IF NOT EXISTS ix_regions_level ON regions(level);
