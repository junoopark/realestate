"""Usage dashboard UI regression with explicitly synthetic API fixtures.

Run a frontend server, then: python tests/ui_usage.py --base-url http://127.0.0.1:8778
The API is intercepted in an isolated browser context; this test never creates
production events, logs in, or claims its fixture counts as real usage.
"""

import argparse
import copy
import csv
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = {
    "available": True, "activity_available": True, "days": 30,
    "checked_at": "2026-10-20T04:00:00+00:00",
    "period": {"start_at": "2026-09-21T00:00:00+09:00", "end_at": "2026-10-20T13:00:00+09:00", "timezone": "Asia/Seoul"},
    "totals": {"download": {"events": 6, "users": 2}},
    "users": 2, "all_time": {"events": 9, "users": 2, "since": "2026-10-17T03:00:00+00:00"},
    "daily": [{"day_kst": "2026-10-17", "event": "download", "events": 3, "users": 1},
              {"day_kst": "2026-10-20", "event": "download", "events": 3, "users": 2}],
    "downloads": [],
    "download_details": {
        "targets": [{"target": "V043", "label": "한국은행 기준금리", "scope": "nation", "downloads": 4, "users": 2},
                    {"target": "V001", "label": "주민등록인구", "scope": "시도", "downloads": 2, "users": 1}],
        "formats": [{"format": "csv", "downloads": 4, "users": 2}, {"format": "xlsx", "downloads": 2, "users": 1}],
        "regions": [{"region": "서울", "downloads": 6, "users": 2}, {"region": "경기", "downloads": 2, "users": 1}],
    },
    "views": {
        "available": True, "since": "2026-10-19T00:00:00+09:00",
        "totals": {"indicator_view": {"events": 12, "sessions": 4}, "policy_view": {"events": 3, "sessions": 2}, "policy_open": {"events": 5, "sessions": 3}},
        "daily": [{"day_kst": "2026-10-19", "event": "indicator_view", "events": 4, "sessions": 2},
                  {"day_kst": "2026-10-20", "event": "indicator_view", "events": 8, "sessions": 4},
                  {"day_kst": "2026-10-20", "event": "policy_view", "events": 3, "sessions": 2},
                  {"day_kst": "2026-10-20", "event": "policy_open", "events": 5, "sessions": 3}],
        "indicators": [{"target": "V001", "label": "주민등록인구", "scope": "sido", "views": 6, "sessions": 4},
                       {"target": "V043", "label": "한국은행 기준금리", "scope": "nation", "views": 4, "sessions": 2},
                       {"target": "map", "label": "지역별 매매가격 상승률", "scope": "sido-map", "views": 1, "sessions": 1},
                       {"target": "district", "label": "자치구 월세가격지수", "scope": "sigungu", "views": 1, "sessions": 1}],
        "policies": [{"target": "policy1", "title": "공공주택 공급 확대 계획", "agency": "국토교통부", "url": "https://www.molit.go.kr/", "views": 3, "opens": 0, "sessions": 2},
                     {"target": "policy2", "title": "=정책 <img src=x onerror=alert(1)>", "agency": "금융위원회", "url": "javascript:alert(1)", "views": 0, "opens": 5, "sessions": 3}],
    },
    "notes": ["화면 검증용 가상 데이터입니다."],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8778")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "ui-usage")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, calls, checks = [], [], []
    state = {"mode": "populated"}

    def handle(route):
        query = parse_qs(urlparse(route.request.url).query)
        calls.append(query)
        if state["mode"] == "error":
            route.fulfill(status=503, json={"detail": "synthetic error"})
            return
        if state["mode"] == "legacy":
            route.fulfill(json={"available": True, "checked_at": FIXTURE["checked_at"], "days": int(query.get("days", [30])[0]),
                                "totals": {"download": {"events": 2, "users": 1}}, "daily": [], "downloads": []})
            return
        fixture = copy.deepcopy(FIXTURE)
        fixture["days"] = int(query.get("days", [30])[0])
        if state["mode"] == "empty":
            fixture["totals"]["download"] = {"events": 0, "users": 0}
            fixture["daily"] = []
            fixture["download_details"] = {"targets": [], "formats": [], "regions": []}
            fixture["views"].update({"daily": [], "indicators": [], "policies": []})
            fixture["views"]["totals"] = {kind: {"events": 0, "sessions": 0} for kind in ["indicator_view", "policy_view", "policy_open"]}
        route.fulfill(json=fixture)

    def ready(page):
        page.wait_for_function("document.documentElement.dataset.usageReady === 'true'")

    def refresh(page):
        page.locator("#usage-refresh").click()
        ready(page)

    def assert_no_overflow(page):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Page has horizontal overflow"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.route("**/usage?**", handle)
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))
        response = page.goto(args.base_url.rstrip("/") + "/usage.html", wait_until="domcontentloaded")
        assert response and response.ok
        ready(page)
        expect(page.locator("#kpi-download")).to_have_text("6")
        expect(page.locator("#kpi-indicator_view")).to_have_text("12")
        expect(page.locator("#download-ranking .usage-rank-name").first).to_have_text("한국은행 기준금리")
        expect(page.locator("#indicator-ranking .usage-rank-name").first).to_have_text("주민등록인구")
        expect(page.locator("#download-ranking .usage-rank-scope")).to_have_text(["전국", "시도"])
        expect(page.locator("#indicator-ranking .usage-rank-scope")).to_have_text(["시도", "전국", "시도 지도", "시군구"])
        expect(page.locator("#policy-ranking tr").first).to_contain_text("=정책")
        expect(page.locator("#policy-ranking img")).to_have_count(0)
        expect(page.locator("#policy-ranking a[href^='javascript:']")).to_have_count(0)
        expect(page.locator("#usage-daily-body tr").last.locator("td").nth(2)).to_have_text("—")
        expect(page.locator("#usage-trend-chart svg")).to_have_count(1)
        assert_no_overflow(page)
        page.screenshot(path=str(output / "populated-desktop.png"), full_page=True)
        checks.append("four totals, Korean scope labels, rankings, pre-measurement gaps, actual-day chart, safe policy text and links")

        page.locator("#policy-sort").select_option("views")
        expect(page.locator("#policy-ranking tr").first).to_contain_text("공공주택")
        page.locator("#policy-sort").select_option("opens")
        expect(page.locator("#policy-ranking tr").first).to_contain_text("=정책")
        page.locator("[data-days='7']").click()
        ready(page)
        assert calls[-1]["days"] == ["7"] and calls[-1]["top"] == ["50"]
        expect(page.locator("[data-days='7']")).to_have_attribute("aria-pressed", "true")
        checks.append("policy ordering and period-specific query")

        with page.expect_download() as pending:
            page.locator("#usage-export").click()
        download = pending.value
        download.save_as(str(output / "fixture-export.csv"))
        text = (output / "fixture-export.csv").read_text(encoding="utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        malicious = [row for row in rows if len(row) > 2 and "정책 <img" in row[2]][0]
        assert malicious[2].startswith("'="), "CSV formula was not neutralized"
        assert all(len(row) == 12 for row in rows)
        assert rows[1][3] == "전국", "CSV scope did not use the same Korean label as the screen"
        assert "user_id" not in text and "session_id" not in text
        checks.append("CSV export includes aggregate rankings and neutralizes formula-like titles")

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        assert_no_overflow(page)
        svg_width = float(page.locator("#usage-trend-chart svg").get_attribute("viewBox").split()[2])
        assert svg_width < 500, "Mobile chart labels are being scaled down from desktop"
        page.screenshot(path=str(output / "populated-mobile.png"), full_page=True)
        page.locator("#theme-btn").click()
        page.screenshot(path=str(output / "populated-mobile-dark.png"), full_page=True)
        assert_no_overflow(page)
        checks.append("390px layout and dark theme, readable mobile chart coordinates")

        state["mode"] = "empty"
        refresh(page)
        expect(page.locator("#kpi-download")).to_have_text("0")
        expect(page.locator("#kpi-indicator_view")).to_have_text("0")
        expect(page.locator("#usage-trend-chart svg")).to_have_count(0)
        expect(page.locator("#usage-trend-chart")).to_contain_text("기록된 활동이 없습니다")
        expect(page.locator("#indicator-ranking")).to_contain_text("기록이 없습니다")
        expect(page.locator("#policy-ranking td")).to_be_visible()
        page.screenshot(path=str(output / "empty-mobile.png"), full_page=True)
        checks.append("genuine zero and empty state without fabricated chart")

        state["mode"] = "legacy"
        refresh(page)
        expect(page.locator("#kpi-download")).to_have_text("2")
        expect(page.locator("#kpi-indicator_view")).to_have_text("—")
        expect(page.locator("#usage-status")).to_contain_text("열람 통계는 현재 확인할 수 없습니다")
        checks.append("older response preserves known downloads and marks missing view metrics unavailable")

        state["mode"] = "error"
        refresh(page)
        for kind in ["download", "indicator_view", "policy_view", "policy_open"]:
            expect(page.locator("#kpi-" + kind)).to_have_text("—")
        expect(page.locator("#usage-export")).to_be_disabled()
        expect(page.locator("#usage-coverage")).to_contain_text("0이라는 뜻이 아닙니다")
        expect(page.locator("#usage-status")).to_contain_text("불러오지 못했습니다")
        checks.append("HTTP failure clears stale counts and disables export instead of displaying zeros")
        assert not errors, errors
        context.close()
        browser.close()
    report = {"fixture_test": True, "checks": checks, "errors": errors, "requests": calls}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
