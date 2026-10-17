"""API 입출력의 모양 (Pydantic). Swagger(/docs) 의 응답 예시가 여기서 만들어진다. 저장 방식은 db/models.py 가 맡는다."""

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    name: str = Field(description="외부 API·오픈데이터 명칭")
    organization: str = Field(description="제공 기관")
    url: str = Field(description="출처 URL")
    license: str = ""
    method: str = ""


class IndicatorVariableOut(BaseModel):
    id: str = Field(description="변수 ID (데이터사전과 동일, 예: V002)")
    label: str
    driver: str = Field(description="동인: demand·supply·finance·rental·trigger·macro")
    source: str = Field(description="R-ONE · ECOS · KOSIS")
    source_ref: str = Field(description="통계표·항목 코드 (예: 'R-ONE A_2024_00045')")
    freq: str = Field(description="M 월 · Q 분기 · A 연")
    scope: str = Field(description="sido(17개 시도) · nation(전국)")
    unit: str = ""
    enabled: bool = True
    item: str | None = Field(default=None, description="실제 수집한 항목명")
    first_period: str | None = None
    last_period: str | None = Field(default=None, description="DB 에 있는 가장 최근 시점")
    rows: int = 0
    last_fetched_at: str | None = Field(default=None, description="마지막 성공 수집 시각(UTC)")
    last_status: str = Field(default="never", description="never · ok · error")
    last_error: str | None = None
    stale: bool = Field(default=True, description="INDICATOR_REFRESH_HOURS 가 지났는지")


class IndicatorListOut(BaseModel):
    variables: list[IndicatorVariableOut]
    sources: dict[str, SourceInfo]
    refresh_hours: int


class MetricOut(BaseModel):
    """frontend/data/factor_sample.json 의 metrics[] 한 항목과 같은 모양 + 캐시 정보."""
    var: str
    column: str | None = Field(default=None, description="전처리본 원자료 열 이름 (기본 패널 계열)")
    label: str
    unit: str = ""
    freq: str
    scope: str = Field(description="지역 단위: sido(17개 시도) · gu(서울 구) · seoul(서울) · nation(전국)")
    periods: list[str] = Field(description="시점 목록 (월: 'YYYY-MM'). series 의 각 배열과 길이가 같다")
    series: dict[str, list[float | None]] = Field(description="지역 → 값 배열 (periods 와 같은 순서, 없으면 null)")
    source: str
    source_name: str = ""
    source_url: str = ""
    method: str = ""
    release: str = ""
    item: str | None = None
    filled: int | None = Field(default=None, description="보완한 칸 수 (기본 패널)")
    provisional_from: str | None = Field(default=None, description="이 시점부터 잠정값 (점선 표시)")
    live: bool = Field(default=True, description="true: Open API 실제 수집값 · false: 기본 패널(전처리본)")
    fetched_at: str | None = None
    origin: str = Field(description="'db(cache)' Open API 수집값을 DB 에서 · 'db(panel)' 기본 패널을 DB 에서 · 'api(R-ONE)' 방금 API 로 받아 저장 후 응답")
    stale: bool = False


class BundleOut(BaseModel):
    generated: str
    set: str = Field(default="live", description="live: Open API 수집 변수만 · all: 기본 패널 전체 + 수집 변수 실제값")
    origin: str = Field(description="'db(cache)' · 'db(cache)+api' (일부 변수를 방금 받아온 경우) · 'db(panel+cache)' (set=all)")
    regions: dict[str, list[str]]
    aliases: dict[str, str] = Field(default_factory=dict, description="같은 값을 쓰는 변수 ID (예: V033 → V005)")
    panel: dict | None = Field(default=None, description="기본 패널 적재 정보: generated(전처리본 생성) · loaded_at(DB 적재 시각) · source_note")
    metrics: list[MetricOut]
    missing: list[str] = Field(default_factory=list, description="DB 에 자료가 없고 키도 없어 못 준 변수")


class RefreshResultItem(BaseModel):
    id: str
    status: str = Field(description="ok · skipped(아직 신선함) · error")
    rows: int | None = None
    last_period: str | None = None
    duration_ms: int | None = None
    reason: str | None = None
    error: str | None = None


class RefreshOut(BaseModel):
    status: str = Field(description="ok · partial · busy")
    checked_at: str | None = None
    results: list[RefreshResultItem] = Field(default_factory=list)
