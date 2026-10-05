"""Validate reviewed policy history before syncing deployment copies.

Usage: python scripts/check_history_data.py [path/to/policy-history.json]
Only the standard library is required. This checks the content contract; official
sources must still be read to verify the facts and the meaning of policy changes.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

DATA_PATH = Path(__file__).resolve().parents[1] / "frontend" / "data" / "policy-history.json"
TOPICS = {"finance", "tax", "supply", "rental", "market"}
DIRECTIONS = {"tighten", "ease", "supply", "protect", "stabilize"}
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def validate_history(data):
    """Return actionable validation errors without changing data or using the network."""
    errors = []

    def error(where, message):
        errors.append(f"{where}: {message}")

    def text_fields(record, fields, where):
        for field in fields:
            if not isinstance(record.get(field), str) or not record[field].strip():
                error(f"{where}.{field}", "비어 있지 않은 문자열이 필요합니다")

    def text_list(value, where, allowed=None):
        if not isinstance(value, list) or not value:
            error(where, "항목이 1개 이상인 배열이 필요합니다")
            return
        seen = set()
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                error(f"{where}[{index}]", "비어 있지 않은 문자열이 필요합니다")
                continue
            if allowed is not None and item not in allowed:
                error(f"{where}[{index}]", f"허용 값: {', '.join(sorted(allowed))}")
            if item in seen:
                error(where, f"중복 항목: {item}")
            seen.add(item)

    def checked_date(value, where):
        if isinstance(value, str) and ISO_DATE.fullmatch(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        error(where, "실제로 존재하는 YYYY-MM-DD 날짜가 필요합니다")
        return None

    def unique_id(record, seen, where):
        key = record.get("id")
        if not isinstance(key, str) or not key.strip():
            error(f"{where}.id", "비어 있지 않은 문자열이 필요합니다")
            return None
        if key in seen:
            error(f"{where}.id", f"중복 ID: {key}")
        seen.add(key)
        return key

    if not isinstance(data, dict):
        return ["root: JSON 객체가 필요합니다"]
    text_fields(data, ("coverage_note",), "root")
    verified = checked_date(data.get("verified_at"), "verified_at")
    start = checked_date(data.get("period_start"), "period_start")
    end = checked_date(data.get("period_end"), "period_end")
    if start and end and start > end:
        error("period_start", "period_end보다 늦을 수 없습니다")

    eras = data.get("eras")
    if not isinstance(eras, list) or not eras:
        error("eras", "구간이 1개 이상인 배열이 필요합니다")
        eras = []
    era_ids, era_ranges = set(), {}
    for index, era in enumerate(eras):
        where = f"eras[{index}]"
        if not isinstance(era, dict):
            error(where, "객체가 필요합니다")
            continue
        era_id = unique_id(era, era_ids, where)
        text_fields(era, ("label", "period", "title", "summary", "shift"), where)
        text_list(era.get("focus"), f"{where}.focus")
        era_start = checked_date(era.get("from"), f"{where}.from")
        era_end = checked_date(era.get("to"), f"{where}.to")
        if era_start and era_end:
            if era_start > era_end:
                error(where, "구간 시작이 종료보다 늦습니다")
            if (start and era_start < start) or (end and era_end > end):
                error(where, "표시 기간 밖의 구간입니다")
            if era_id:
                era_ranges[era_id] = (era_start, era_end)

    events = data.get("events")
    if not isinstance(events, list) or not events:
        error("events", "정책이 1개 이상인 배열이 필요합니다")
        events = []
    event_ids = set()
    for index, event in enumerate(events):
        where = f"events[{index}]"
        if not isinstance(event, dict):
            error(where, "객체가 필요합니다")
            continue
        unique_id(event, event_ids, where)
        text_fields(event, ("title", "short_title", "agency", "summary", "change", "context", "timing_note", "reading_note"), where)
        event_date = checked_date(event.get("date"), f"{where}.date")
        event_verified = checked_date(event.get("verified_at"), f"{where}.verified_at")
        if event_date:
            if (start and event_date < start) or (end and event_date > end):
                error(f"{where}.date", "표시 기간 밖의 발표일입니다")
            if event_verified and event_date > event_verified:
                error(f"{where}.verified_at", "자료 확인일이 발표일보다 빠릅니다")
        if verified and event_verified and event_verified > verified:
            error(f"{where}.verified_at", "전체 자료 확인일보다 늦습니다")
        era_id = event.get("era")
        if not isinstance(era_id, str) or era_id not in era_ids:
            error(f"{where}.era", "존재하는 eras.id를 참조해야 합니다")
        elif event_date and era_id in era_ranges:
            if not era_ranges[era_id][0] <= event_date <= era_ranges[era_id][1]:
                error(f"{where}.era", "발표일이 참조한 구간 밖에 있습니다")
        text_list(event.get("topics"), f"{where}.topics", TOPICS)
        text_list(event.get("directions"), f"{where}.directions", DIRECTIONS)
        text_list(event.get("highlights"), f"{where}.highlights")
        sources = event.get("sources")
        if not isinstance(sources, list) or not sources:
            error(f"{where}.sources", "출처가 1개 이상 필요합니다")
            continue
        for number, source in enumerate(sources):
            spot = f"{where}.sources[{number}]"
            if not isinstance(source, dict):
                error(spot, "객체가 필요합니다")
                continue
            text_fields(source, ("title", "organization", "url"), spot)
            url = source.get("url")
            try:
                parsed = urlsplit(url) if isinstance(url, str) else None
                valid = parsed and parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not re.search(r"\s", url)
            except ValueError:
                valid = False
            if not valid:
                error(f"{spot}.url", "유효한 http(s) 출처 주소가 필요합니다")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DATA_PATH)
    args = parser.parse_args()
    try:
        data = json.loads(args.path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"ERROR 파일을 읽을 수 없습니다: {exc}")
        return 1
    errors = validate_history(data)
    for message in errors:
        print(f"ERROR {message}")
    if errors:
        print(f"정책 히스토리 검증 실패: 오류 {len(errors)}개")
        return 1
    print(f"정책 히스토리 검증 통과: {data['period_start']}~{data['period_end']}, {len(data['eras'])}개 구간, {len(data['events'])}개 정책")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
