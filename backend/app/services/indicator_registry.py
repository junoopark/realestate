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
class IndicatorSpec:
    id: str                 # 데이터사전 변수 ID (V001 …)
    label: str              # 화면 이름
    driver: str             # 동인 id (demand·supply·finance·rental·trigger·macro)
    source: str             # R-ONE · ECOS · KOSIS
    freq: str = "M"         # M 월 · Q 분기 · A 연
    scope: str = "sido"     # sido(17개 시도) · nation(전국 1계열)
    unit: str = ""
    release: str = ""       # 공표 시기 메모 (갱신 주기 판단과 화면 해설에 사용)
    start: str = START_PERIOD
    enabled: bool = True    # False 면 수집·조회 대상에서 제외 (코드 확인 전 자리만 잡아 둔 변수)
    params: dict = field(default_factory=dict)  # source 별 호출 파라미터
    note: str = ""          # 전처리·주의 메모 (화면 'method' 로 노출)

    @property
    def source_ref(self) -> str:
        """화면 출처 표기. 샘플 파일의 'R-ONE A_2024_00045' 와 같은 꼴."""
        p = self.params
        if self.source == "R-ONE":
            return f"R-ONE {p.get('statbl_id', '')}"
        if self.source == "ECOS":
            return f"ECOS {p.get('stat_code', '')}/{p.get('item_code', '')}"
        if self.source == "KOSIS":
            return f"KOSIS {p.get('org_id', '')}/{p.get('tbl_id', '')}"
        return self.source

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_ref"] = self.source_ref
        d["source_info"] = SOURCES.get(self.source, {})
        return d


REGISTRY: list[IndicatorSpec] = [
    # ── 한국부동산원 R-ONE (전국주택가격동향조사·월세수급·소비심리) — 17개 시도 월별 ──
    IndicatorSpec("V002", "아파트 매매가격지수", "finance", "R-ONE", unit="",
                  release="조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)",
                  params={"statbl_id": "A_2024_00045", "item": "지수"},
                  note="원자료 그대로 (2021.06=100)"),
    IndicatorSpec("V026", "아파트 전세가격지수", "finance", "R-ONE", unit="",
                  release="조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)",
                  params={"statbl_id": "A_2024_00050", "item": "지수"},
                  note="원자료 그대로 (2021.06=100)"),
    IndicatorSpec("V001", "월세통합가격지수", "rental", "R-ONE", unit="",
                  release="조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)",
                  params={"statbl_id": "A_2024_00054", "item": "지수"},
                  note="API 는 현행 계열만 제공 (샘플 파일의 구지수 연결 구간은 포함하지 않음)"),
    IndicatorSpec("V003", "아파트 전세가율", "finance", "R-ONE", unit="%",
                  release="조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)",
                  params={"statbl_id": "A_2024_00072"},
                  note="원자료 그대로"),
    IndicatorSpec("V005", "아파트 월세수급동향", "rental", "R-ONE", unit="",
                  release="조사기준 월 익월 15일 전후 공표 (전국주택가격동향조사)",
                  params={"statbl_id": "A_2024_00078"},
                  note="100 보다 크면 공급 부족, 작으면 공급 충분"),
    IndicatorSpec("V037", "주택시장 소비심리지수", "trigger", "R-ONE", unit="",
                  release="조사기준 월 익월 15일 전후 공표 (부동산시장 소비자심리조사)",
                  params={"statbl_id": "T232543129897499"},
                  note="원자료 그대로"),
    # ── 한국은행 ECOS — 전국 월별 ──
    IndicatorSpec("V043", "한국은행 기준금리", "macro", "ECOS", scope="nation", unit="연%",
                  release="금통위 결정 즉시 반영. 월말값",
                  params={"stat_code": "722Y001", "item_code": "0101000"}),
    IndicatorSpec("V045", "시장금리 국고채3년", "macro", "ECOS", scope="nation", unit="연%",
                  release="월평균. 해당 월 말 확정",
                  params={"stat_code": "721Y001", "item_code": "5020000"}),
    IndicatorSpec("V056", "예금은행대출금리 주택담보(신규)", "macro", "ECOS", scope="nation", unit="연%",
                  release="기준월 익월 말 공표 (금융기관 가중평균금리)",
                  params={"stat_code": "121Y006", "item_code": "BECBLA0302"}),
    # ── 통계청 KOSIS — 2차 연동 대상 (항목·분류 코드 확인 후 enabled=True 로) ──
    IndicatorSpec("V012", "인구이동 순이동자수", "demand", "KOSIS", unit="명", enabled=False,
                  release="기준월 익월 말 공표 (국내인구이동통계)",
                  params={"org_id": "101", "tbl_id": "DT_1B26001_A01", "itm_id": "T70", "obj_l1": "ALL"}),
    IndicatorSpec("V023", "주택건설 아파트준공", "supply", "KOSIS", unit="호", enabled=False,
                  release="기준월 익월 말 공표 (주택건설실적통계)",
                  params={"org_id": "116", "tbl_id": "DT_MLTM_5373", "itm_id": "T1", "obj_l1": "ALL"}),
]

BY_ID: dict[str, IndicatorSpec] = {s.id: s for s in REGISTRY}


def enabled_specs() -> list[IndicatorSpec]:
    return [s for s in REGISTRY if s.enabled]


def get_spec(var_id: str) -> IndicatorSpec | None:
    return BY_ID.get(var_id.upper())
