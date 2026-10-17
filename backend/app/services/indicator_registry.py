"""지표 레지스트리 — 외부 API 에서 받아올 변수를 한 곳에 등록한다.

지표를 추가하는 방법
1. 아래 REGISTRY 에 항목을 하나 추가한다. id 는 데이터사전(frontend/data/drivers.json)의 변수 ID 와 맞춘다.
2. source 별로 필요한 코드를 적는다.
   - R-ONE : statbl_id(통계표 ID). item(항목명 일부)·cls(지역 분류 필터)는 선택. 모르면
             `python scripts/collect_indicators.py --probe V002` 로 실제 항목·지역 이름을 본 뒤 적는다.
   - ECOS  : stat_code(통계표 코드), item_code(항목 코드 1).
   - KOSIS : org_id, tbl_id, itm_id, obj_l1(지역 분류, 'ALL' 이면 전체).
3. `python scripts/collect_indicators.py --vars <id>` 로 한 번 받아 보고 /indicators/<id> 로 확인한다.

여기 적힌 출처(source_name·source_url·license)는 발표 자료의 '사용 데이터 및 출처' 와 /indicators 응답에 그대로 쓰인다.
"""

from dataclasses import dataclass, field, asdict

START_PERIOD = "2016-01"  # 화면 샘플(factor_sample.json)과 같은 시작 시점

SOURCES = {
    "R-ONE": {
        "name": "한국부동산원 부동산통계정보 R-ONE Open API",
        "organization": "한국부동산원",
        "url": "https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do",
        "license": "공공누리 제1유형(출처표시)",
        "method": "Open API (SttsApiTblData, JSON)",
    },
    "ECOS": {
        "name": "한국은행 경제통계시스템 ECOS Open API",
        "organization": "한국은행",
        "url": "https://ecos.bok.or.kr/api/",
        "license": "한국은행 Open API 이용약관(출처표시)",
        "method": "Open API (StatisticSearch, JSON)",
    },
    "KOSIS": {
        "name": "국가통계포털 KOSIS 공유서비스 Open API",
        "organization": "통계청",
        "url": "https://kosis.kr/openapi/",
        "license": "공공누리 제1유형(출처표시)",
        "method": "Open API (statisticsParameterData, JSON)",
    },
}


@dataclass(frozen=True)
class Output:
    """수집한 값을 기본 패널(indicator_series)의 어느 계열에 이어붙일지.

    scope   : 패널 계열의 지역 단위 (sido · gu · seoul · nation)
    match   : 패널 원자료 열 이름에 들어 있는 글자. 그 변수·지역 단위에 계열이 하나면 비워 둔다
    regions : 이 지역만 쓴다 (예: seoul 계열은 ('서울',)). 비우면 패널 계열에 이미 있는 지역 전부
    rename  : 수집 지역명 → 패널 지역명 (예: ECOS 전국 계열을 '서울 권역' 계열로)
    """
    scope: str
    match: str | None = None
    regions: tuple | None = None
    rename: tuple = ()  # ((수집 지역명, 패널 지역명), …) — frozen dataclass 라 dict 대신 tuple

    @property
    def rename_map(self) -> dict:
        return dict(self.rename)


@dataclass(frozen=True)
class IndicatorSpec:
    id: str                 # 수집 단위 ID. 보통 변수 ID 와 같고, 한 변수를 여러 번 부르면 'V069.1' 처럼 쓴다 (10자 이내)
    label: str              # 화면 이름
    driver: str             # 동인 id (demand·supply·finance·rental·trigger·macro)
    source: str             # R-ONE · ECOS · KOSIS
    freq: str = "M"         # M 월 · Q 분기 · H 반기 · A 연
    scope: str = "sido"     # 수집 지역 단위: sido(17개 시도) · nation(전국 1계열)
    unit: str = ""
    release: str = ""       # 공표 시기 메모 (화면 해설에 사용)
    start: str = START_PERIOD
    enabled: bool = True    # False 면 수집·조회 대상에서 제외 (코드 확인 전 자리만 잡아 둔 변수)
    params: dict = field(default_factory=dict)  # source 별 호출 파라미터
    note: str = ""          # 전처리·주의 메모 (화면 'method' 로 노출)
    var: str = ""           # 데이터사전 변수 ID. 비우면 id 와 같다
    outputs: tuple = ()     # 수집값을 이어붙일 기본 패널 계열 (Output …)

    @property
    def var_id(self) -> str:
        return self.var or self.id

    @property
    def source_ref(self) -> str:
        """화면 출처 표기. 샘플 파일의 'R-ONE A_2024_00045' 와 같은 꼴."""
        p = self.params
        if self.source == "R-ONE":
            return f"R-ONE {p.get('statbl_id', '')}"
        if self.source == "ECOS":
            if p.get("segments"):
                return "ECOS " + " · ".join(f"{g['stat_code']}/{g['item_code']}" for g in p["segments"])
            return f"ECOS {p.get('stat_code', '')}/{p.get('item_code', '')}"
        if self.source == "KOSIS":
            return f"KOSIS {p.get('org_id', '')}/{p.get('tbl_id', '')}"
        return self.source

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_ref"] = self.source_ref
        d["source_info"] = SOURCES.get(self.source, {})
        return d


SIDO_AND_SEOUL = (Output("sido"), Output("seoul", regions=("서울",)))  # 시도 계열 + 서울 단독 계열(같은 값)

# 공표 시기 문구 (DFMBA variables.py 의 공표 시차 표를 옮김: 한국은행 통계메타·KOSIS 통계설명서 등 공식 근거)
REL_REB = "조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)"
REL_MARKET = "시장 관측치(월평균·월말값). 해당 월 말 확정"
REL_RATE = "기준월 익월 말 공표 (금융기관 가중평균금리)"
REL_HHLOAN = "기준월 익익월 14일 이내 공표 (예금취급기관 가계대출)"

REGISTRY: list[IndicatorSpec] = [
    # ── 한국부동산원 R-ONE (전국주택가격동향조사·월세수급·소비심리) — 17개 시도 월별 ──
    IndicatorSpec("V002", "아파트 매매가격지수", "finance", "R-ONE", release=REL_REB,
                  params={"statbl_id": "A_2024_00045", "item": "지수"}, note="원자료 그대로 (2021.06=100)",
                  outputs=(Output("sido"),)),
    IndicatorSpec("V026", "아파트 전세가격지수", "finance", "R-ONE", release=REL_REB,
                  params={"statbl_id": "A_2024_00050", "item": "지수"}, note="원자료 그대로 (2021.06=100)",
                  outputs=(Output("sido"),)),
    IndicatorSpec("V001", "월세통합가격지수", "rental", "R-ONE", release=REL_REB,
                  params={"statbl_id": "A_2024_00054", "item": "지수"},
                  note="API 는 현행 계열(2015.06~). 그 이전 구지수 연결 구간은 기본 패널 값을 유지",
                  outputs=(Output("sido"),)),
    IndicatorSpec("V003", "아파트 전세가율", "finance", "R-ONE", unit="%", release=REL_REB,
                  params={"statbl_id": "A_2024_00072", "item": "매매가격 대비 전세가격"}, note="원자료 그대로",
                  outputs=(Output("sido"),)),
    IndicatorSpec("V005", "아파트 월세수급동향", "rental", "R-ONE", release=REL_REB,
                  params={"statbl_id": "A_2024_00078", "item": "지수"}, note="100 보다 크면 공급 부족, 작으면 공급 충분",
                  outputs=SIDO_AND_SEOUL),
    IndicatorSpec("V037", "주택시장 소비심리지수", "trigger", "R-ONE",
                  release="익월 중순 공표 (국토연구원 부동산시장 소비자심리조사, R-ONE 게시는 더 늦을 수 있음)",
                  params={"statbl_id": "T232543129897499", "item": "지수"}, note="원자료 그대로",
                  outputs=SIDO_AND_SEOUL),
    # ── 한국은행 ECOS — 전국 (V050 만 시도별). 표·항목 코드는 DFMBA collect_ecos.py 와 같다 ──
    IndicatorSpec("V043", "한국은행 기준금리", "macro", "ECOS", scope="nation", unit="연%",
                  release="금통위 결정 즉시 반영. 월말값", params={"stat_code": "722Y001", "item_code": "0101000"},
                  outputs=(Output("nation"),)),
    IndicatorSpec("V044", "시장금리 CD(91일)", "macro", "ECOS", scope="nation", unit="연%", release=REL_MARKET,
                  params={"stat_code": "721Y001", "item_code": "2010000"}, outputs=(Output("nation"),)),
    IndicatorSpec("V045", "시장금리 국고채 3년", "macro", "ECOS", scope="nation", unit="연%", release=REL_MARKET,
                  params={"stat_code": "721Y001", "item_code": "5020000"}, outputs=(Output("nation"),)),
    IndicatorSpec("V046", "M2 통화량(평잔, 원계열)", "macro", "ECOS", scope="nation", unit="십억원",
                  release="기준월 익익월 14일 이내 공표 (통화 및 유동성)",
                  params={"stat_code": "161Y006", "item_code": "BBHA00"}, outputs=(Output("nation"),)),
    IndicatorSpec("V047", "가계신용 총액", "macro", "ECOS", freq="Q", scope="nation", unit="십억원",
                  release="분기 종료 후 약 1.5개월 공표 (가계신용, 잠정치)", start="2016Q1",
                  params={"stat_code": "151Y001", "item_code": "1000000"}, outputs=(Output("nation"),)),
    IndicatorSpec("V048", "소비자물가지수 총지수", "macro", "ECOS", scope="nation", unit="2020=100",
                  release="기준월 익월 초 공표 (소비자물가조사)",
                  params={"stat_code": "901Y009", "item_code": "0"}, outputs=(Output("nation"),)),
    IndicatorSpec("V049", "시간당 명목임금지수(비농전산업)", "macro", "ECOS", freq="Q", scope="nation", unit="2020=100",
                  release="분기 종료 후 다음 분기 중 공표 (노동생산성지수)", start="2016Q1",
                  params={"stat_code": "901Y102", "item_code": "A10001"}, outputs=(Output("nation"),)),
    IndicatorSpec("V050", "지역별 주택관련대출(예금은행)", "macro", "ECOS", scope="sido", unit="십억원",
                  release="기준월 익익월 중순경 공표 (지역별여수신)", note="말잔(월말 잔액). 지역마다 따로 호출해 17개 시도를 모은다",
                  params={"stat_code": "151Y003", "item_code": "11110A0",
                          "region_items": {"서울": "A00", "부산": "B00", "대구": "C00", "인천": "D00", "대전": "E00",
                                           "광주": "F00", "울산": "G00", "세종": "H00", "경기": "L00", "강원": "M00",
                                           "충북": "N00", "충남": "P00", "전북": "Q00", "전남": "R00", "경북": "S00",
                                           "경남": "T00", "제주": "U00"}},
                  outputs=SIDO_AND_SEOUL),
    IndicatorSpec("V056", "예금은행 대출금리 주택담보(신규)", "macro", "ECOS", scope="nation", unit="연%", release=REL_RATE,
                  params={"stat_code": "121Y006", "item_code": "BECBLA0302"}, outputs=(Output("nation"),)),
    IndicatorSpec("V057", "예금은행 대출금리 전세자금(신규)", "macro", "ECOS", scope="nation", unit="연%", release=REL_RATE,
                  params={"stat_code": "121Y006", "item_code": "BECBLA03041"},
                  note="통계 작성 전 구간(~2016)은 기본 패널의 대용값을 유지", outputs=(Output("nation"),)),
    IndicatorSpec("V059", "비은행 대출금리 주택담보", "macro", "ECOS", scope="nation", unit="연%", release=REL_RATE,
                  params={"stat_code": "121Y007", "item_code": "BEDBMC41"},
                  note="통계 작성 전 구간은 기본 패널의 대용값을 유지", outputs=(Output("nation"),)),
    IndicatorSpec("V060", "대출행태서베이 대출태도(국내은행 가계주택)", "macro", "ECOS", freq="Q", scope="nation",
                  release="분기 첫 월 공표 (금융기관 대출행태조사, 다음 분기 전망치)", start="2016Q1",
                  params={"stat_code": "514Y001", "item_code": "AA04"}, outputs=(Output("nation"),)),
    IndicatorSpec("V061", "주택가격전망CSI 서울", "trigger", "ECOS", scope="nation", release="기준월 말 공표 (소비자동향조사)",
                  params={"stat_code": "511Y002", "item_code": "FMFB/F0001"},
                  outputs=(Output("nation", rename=(("전국", "서울 권역"),)),)),
    IndicatorSpec("V062", "주택가격전망CSI 6대광역시", "trigger", "ECOS", scope="nation", release="기준월 말 공표 (소비자동향조사)",
                  params={"stat_code": "511Y002", "item_code": "FMFB/F0002"},
                  outputs=(Output("nation", rename=(("전국", "6대광역시 권역"),)),)),
    IndicatorSpec("V063", "주택가격전망CSI 기타도시", "trigger", "ECOS", scope="nation", release="기준월 말 공표 (소비자동향조사)",
                  params={"stat_code": "511Y002", "item_code": "FMFB/F0003"},
                  outputs=(Output("nation", rename=(("전국", "기타도시 권역"),)),)),
    IndicatorSpec("V064", "KOSPI 종가", "macro", "ECOS", scope="nation", unit="1980.01.04=100", release=REL_MARKET,
                  params={"stat_code": "901Y014", "item_code": "1070000"}, outputs=(Output("nation"),)),
    IndicatorSpec("V066", "사업체노동력조사 월임금총액", "macro", "ECOS", scope="nation", unit="원",
                  release="기준월 약 3개월 뒤 공표 (사업체노동력조사)",
                  note="산업분류 개정으로 표가 바뀐다: 10차(901Y052, 2020~2025) · 11차(901Y148, 2026~). 2019년 이전은 기본 패널(KOSIS 9차) 유지",
                  params={"segments": [{"stat_code": "901Y052", "item_code": "A/I72BI/1", "until": "2025-12"},
                                       {"stat_code": "901Y148", "item_code": "A/I72BI/1", "from": "2026-01"}]},
                  outputs=(Output("nation"),)),
    IndicatorSpec("V067", "경기선행지수 순환변동치", "macro", "ECOS", scope="nation", unit="2020=100",
                  release="기준월 익월 말 공표 (경기종합지수)",
                  params={"stat_code": "901Y067", "item_code": "I16E"}, outputs=(Output("nation"),)),
    IndicatorSpec("V069.1", "예금취급기관 가계대출(전체)", "macro", "ECOS", scope="nation", unit="십억원", release=REL_HHLOAN,
                  var="V069", params={"stat_code": "151Y005", "item_code": "1110000"},
                  outputs=(Output("nation", match="(전체)"),)),
    IndicatorSpec("V069.2", "예금취급기관 가계대출(주택관련)", "macro", "ECOS", scope="nation", unit="십억원", release=REL_HHLOAN,
                  var="V069", params={"stat_code": "151Y005", "item_code": "11100A0"},
                  outputs=(Output("nation", match="(주택관련)"),)),
    IndicatorSpec("V070", "수출금액(통관)", "macro", "ECOS", scope="nation", unit="천불", release="기준월 익월 초 공표 (수출입동향)",
                  params={"stat_code": "901Y118", "item_code": "T002"}, outputs=(Output("nation"),)),
    IndicatorSpec("V071", "정책대출(주금공·주택도시기금)", "macro", "ECOS", scope="nation", unit="십억원", release=REL_HHLOAN,
                  params={"stat_code": "151Y005", "item_code": "1120093"}, outputs=(Output("nation"),)),
    # ── 통계청 KOSIS — 다음 묶음에서 연동 (항목·분류 코드 확인 후 enabled=True 로) ──
    IndicatorSpec("V012", "인구이동 순이동자수", "demand", "KOSIS", unit="명", enabled=False,
                  release="기준월 익월 말 공표 (국내인구이동통계)",
                  params={"org_id": "101", "tbl_id": "DT_1B26001_A01", "itm_id": "T70", "obj_l1": "ALL"}),
    IndicatorSpec("V023", "주택건설 아파트준공", "supply", "KOSIS", unit="호", enabled=False,
                  release="기준월 익월 말 공표 (주택건설실적통계)",
                  params={"org_id": "116", "tbl_id": "DT_MLTM_5373", "itm_id": "T1", "obj_l1": "ALL"}),
]

BY_ID: dict[str, IndicatorSpec] = {s.id: s for s in REGISTRY}


def enabled_specs(source: str | None = None) -> list[IndicatorSpec]:
    return [s for s in REGISTRY if s.enabled and (source is None or s.source == source)]


def get_spec(spec_id: str) -> IndicatorSpec | None:
    return BY_ID.get(spec_id.upper())


def specs_for_var(var_id: str) -> list[IndicatorSpec]:
    """변수 하나에 딸린 수집 단위들 (예: V069 → V069.1, V069.2)."""
    v = var_id.upper()
    return [s for s in REGISTRY if s.var_id == v]
