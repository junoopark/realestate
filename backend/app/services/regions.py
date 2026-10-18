"""지역 이름 정규화 — 기관마다 다른 시도 표기를 대시보드의 17개 짧은 이름으로 맞춘다.

R-ONE 은 '서울' 또는 '서울특별시', KOSIS 는 '서울특별시', '강원특별자치도', '전북특별자치도'(2024~)·'전라북도'(이전)처럼
같은 지역을 여러 이름으로 적는다. 화면(frontend/data/factor_sample.json·korea_sido.json)은 짧은 이름 17개를 쓴다.
"""

import re

SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]

_LONG_TO_SHORT = {
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주도": "제주", "강원도": "강원",
}
_SUFFIX = re.compile(r"(특별자치시|특별자치도|특별시|광역시|도)$")
_NATION = {"전국", "전체", "계", "합계"}


def normalize_sido(name: str | None) -> str | None:
    """'서울특별시'→'서울', '전북특별자치도'→'전북', '전국'→'전국'. 시도가 아니면 None."""
    if not name:
        return None
    s = re.sub(r"\s+", "", str(name))
    # R-ONE CLS_FULLNM 처럼 '전국 > 수도권 > 서울' 꼴이면 마지막 조각만 본다
    if ">" in s:
        s = s.split(">")[-1]
    if s in _NATION:
        return "전국"
    if s in SIDO:
        return s
    if s in _LONG_TO_SHORT:
        return _LONG_TO_SHORT[s]
    base = _SUFFIX.sub("", s)
    if base in _LONG_TO_SHORT:
        return _LONG_TO_SHORT[base]
    if base in SIDO:
        return base
    return None  # '서울 강남구', '수도권', '5대광역시' 등은 시도가 아니다


def is_sido(name: str | None) -> bool:
    n = normalize_sido(name)
    return n is not None and n != "전국"


# 서울 25개 자치구 (화면의 서울 구 보기는 이 중 기본 패널에 있는 구만 쓴다)
SEOUL_GU = ["종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구", "노원구", "은평구",
            "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구"]


def parse_rone_region(cls_fullnm: str | None) -> tuple[str, str] | None:
    """R-ONE 의 CLS_FULLNM 을 (시도, 서울 구) 로 바꾼다. 대상 밖(권역·집계 중간행)이면 None.
    DFMBA common.parse_rone_region 과 같은 규칙 — 통계표마다 계층 깊이가 달라 마지막 조각으로 판정한다.
      '경기' → ('경기', '')                         '전남광주>광주' · '전남광주>(구)광주' → ('광주', '')  (2026 광주·전남 통합 뒤 표기)
      '경기>계' → ('경기', '')  (거래현황·미분양의 시도 합계행)
      '서울>강남구' · '서울>강남지역>동남권>강남구' → ('서울', '강남구')      '서울>강남지역' → None
    """
    if not cls_fullnm:
        return None
    parts = [p.strip() for p in str(cls_fullnm).split(">")]
    last, first = parts[-1], parts[0]
    if last.startswith("(구)") and last[3:] in SIDO:
        return last[3:], ""
    if last in SIDO:
        return last, ""
    if last == "계" and first in SIDO and len(parts) == 2:
        return first, ""
    if first == "서울" and last.endswith(("구", "군")) and len(parts) >= 2:
        return "서울", last
    return None
