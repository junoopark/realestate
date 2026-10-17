from datetime import date

from app.services import region_mapper as rm
from app.services.rone_collector import UNNAMED


def leaf(fullnm):
    return rm.chain(fullnm)[-1]


def rone(cls_id, fullnm, statbl="A_2024_00055", nm=None, first=date(2015, 6, 1), last=date(2026, 9, 1), legacy=False):
    return {"statbl_id": statbl, "cls_id": cls_id, "cls_nm": nm or fullnm.split(">")[-1], "cls_fullnm": fullnm,
            "first_seen": first, "last_seen": last, "is_legacy": legacy}


def test_nation_and_zone():
    assert leaf("전국") == {"region_key": "전국", "name": "전국", "level": "nation", "parent_key": None, "area_key": None}
    assert leaf("수도권")["level"] == "zone"
    assert leaf("수도권")["parent_key"] == "전국"


def test_area_removed_from_key_and_kept_as_area_key():
    gu = leaf("서울>강북지역>도심권>종로구")
    assert (gu["region_key"], gu["level"], gu["parent_key"], gu["area_key"]) == (
        "서울>종로구", "sigungu", "서울", "서울>강북지역>도심권")
    area = leaf("서울>강북지역>도심권")
    assert (area["region_key"], area["level"], area["parent_key"]) == ("서울>강북지역>도심권", "area", "서울>강북지역")


def test_general_gu_under_city():
    gu = leaf("경기>경부1권>안양시>만안구")
    assert (gu["region_key"], gu["level"], gu["parent_key"], gu["area_key"]) == (
        "경기>안양시>만안구", "gu", "경기>안양시", "경기>경부1권")
    assert leaf("충북>청주시>상당구")["area_key"] is None


def test_merged_sido_is_parent_of_gwangju_and_jeonnam():
    assert leaf("전남광주")["level"] == "sido"
    assert leaf("전남광주>광주>동구")["region_key"] == "광주>동구"
    assert rm.chain("전남광주>전남>목포시")[2]["parent_key"] == "전남광주"
    # 구지수처럼 접두어 없이 '광주'만 와도 같은 상위
    assert leaf("광주")["parent_key"] == "전남광주"


def test_build_maps_every_row_and_orders_parents_first():
    rows = [
        rone(500009, "광주", statbl="A_2024_00164", legacy=True),
        rone(500013, "전남광주>광주"),
        rone(510009, "서울>강북지역"),
        rone(510004, "서울>강북지역", statbl="A_2024_00164", legacy=True),
        rone(530011, "서울>강북지역>도심권>종로구"),
        rone(510020, f"{UNNAMED} CLS_ID 510020", nm=UNNAMED, last=date(2026, 7, 1)),
        rone(530096, "인천>제물포구", first=date(2026, 6, 1)),
    ]
    ordered, mapping = rm.build(rows)
    keys = [r["region_key"] for r in ordered]
    for r in ordered:
        for ref in (r["parent_key"], r["area_key"]):
            assert ref is None or keys.index(ref) < keys.index(r["region_key"])
    assert mapping[("A_2024_00164", 510004)] == mapping[("A_2024_00055", 510009)] == "서울>강북지역"
    assert mapping[("A_2024_00055", 510020)] == "인천>중구"
    by_key = {r["region_key"]: r for r in ordered}
    assert by_key["광주"]["parent_key"] == "전남광주"
    assert "추정" in by_key["인천>중구"]["note"]
    assert by_key["인천>중구"]["last_period"] == date(2026, 7, 1)
    assert by_key["인천>제물포구"]["first_period"] == date(2026, 6, 1)


def test_unknown_unnamed_code_is_left_unmapped():
    _, mapping = rm.build([rone(599999, f"{UNNAMED} CLS_ID 599999", nm=UNNAMED)])
    assert mapping == {}
