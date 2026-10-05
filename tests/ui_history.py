"""Policy-history UX checks against the local static server and API.

Run: python tests/ui_history.py (Playwright + Edge, servers :5500 and :8000).
"""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:5500/"
OUT = Path(__file__).resolve().parents[1] / "tmp" / "ui"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="light", reduced_motion="reduce")
        context.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "policies.html", wait_until="domcontentloaded")
        expect(page.locator("#policy-tabs a")).to_have_text(["주요 정책 정리", "새 발표 모니터링", "정책 히스토리", "수집 출처 · 방법"])
        page.locator('[data-section="history"]').click()
        expect(page.locator(".history-event")).to_have_count(27)
        expect(page.locator(".history-era")).to_have_count(5)
        expect(page.locator(".history-year-button")).to_have_count(11)
        expect(page.locator(".policy-hero")).not_to_be_visible()
        expect(page.locator("#history-data-status")).to_contain_text("서버의 검토 자료")
        page.screenshot(path=str(OUT / "history-desktop.png"), animations="disabled")

        page.locator('.history-era[data-era="e3"]').click()
        expect(page.locator(".history-event")).to_have_count(5)
        expect(page.locator(".history-year-button")).to_have_text(["2022", "2023"])
        page.locator('.history-topic[data-topic="rental"]').click()
        expect(page.locator(".history-event")).to_have_count(1)
        expect(page.locator(".history-date-kind")).to_have_text("시행")
        page.locator("#history-reset").click()
        expect(page.locator(".history-event")).to_have_count(27)

        page.get_by_role("searchbox").fill("8.2")
        expect(page.locator('.history-event[data-event-id="history-2017-0802"]')).to_be_visible()
        assert page.locator(".history-event").count() < 27
        page.get_by_role("searchbox").fill("nonexistent-history-query")
        expect(page.locator(".history-event")).to_have_count(0)
        expect(page.locator(".history-empty")).to_contain_text("이 조건에 맞는 전환점이 없습니다")
        page.get_by_role("button", name="전체 흐름으로 돌아가기").click()
        expect(page.locator(".history-event")).to_have_count(27)

        page.locator('.history-year-button[data-year="2025"]').click()
        expect(page.locator("#history-year-2025")).to_be_focused()
        assert page.locator("#history-year-2025").bounding_box()["y"] > 60
        summary = page.locator('.history-event[data-event-id="housing-20250627"] summary')
        summary.focus()
        page.keyboard.press("Enter")
        expect(page.locator('.history-event[data-event-id="housing-20250627"]')).to_have_attribute("open", "")
        expect(page.locator('.history-event[data-event-id="housing-20250627"] .history-event-sources a')).to_have_count(1)
        page.locator('.history-event[data-event-id="housing-20250627"]').scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "history-detail.png"), animations="disabled")
        page.locator('[data-section="briefs"]').click()
        expect(page.locator(".policy-card")).to_have_count(8)
        expect(page.locator(".policy-hero")).to_be_visible()

        for width in [320, 390, 760]:
            mobile = browser.new_page(viewport={"width": width, "height": 844}, color_scheme="light", reduced_motion="reduce")
            mobile.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
            mobile.on("pageerror", lambda error: errors.append(str(error)))
            mobile.goto(BASE + "policies.html#history", wait_until="domcontentloaded")
            expect(mobile.locator(".history-event")).to_have_count(27)
            assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"overflow at {width}"
            mobile.screenshot(path=str(OUT / f"history-mobile-{width}.png"), animations="disabled")
            mobile.locator('.history-era[data-era="e5"]').click()
            expect(mobile.locator(".history-event")).to_have_count(2)
            mobile.locator(".history-event summary").first.click()
            assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
            mobile.locator("#theme-btn").click()
            expect(mobile.locator("html")).to_have_attribute("data-theme", "dark")
            mobile.screenshot(path=str(OUT / f"history-dark-{width}.png"), animations="disabled")
            mobile.close()

        # History is independently readable even if the other policy data/API fail.
        offline = browser.new_context(viewport={"width": 1200, "height": 900}, reduced_motion="reduce")
        offline.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
        offline.route("http://127.0.0.1:8000/**", lambda route: route.abort())
        offline.route("**/data/policies.json", lambda route: route.abort())
        fallback = offline.new_page()
        fallback.on("pageerror", lambda error: errors.append(str(error)))
        fallback.goto(BASE + "policies.html#history", wait_until="domcontentloaded")
        expect(fallback.locator(".history-event")).to_have_count(27)
        expect(fallback.locator("#history-data-status")).to_contain_text("저장된 검토 자료")

        # No fabricated history appears if both the file and API are unavailable.
        offline.route("**/data/policy-history.json", lambda route: route.abort())
        fallback.reload(wait_until="domcontentloaded")
        expect(fallback.locator(".history-event")).to_have_count(0)
        expect(fallback.get_by_role("button", name="서버 다시 확인", exact=True)).to_be_visible()
        offline.unroute("**/data/policy-history.json")
        offline.unroute("http://127.0.0.1:8000/**")
        fallback.get_by_role("button", name="서버 다시 확인", exact=True).click()
        expect(fallback.locator(".history-event")).to_have_count(27)
        assert not errors, errors
        print(json.dumps({"history_ux": "passed", "events": 27, "eras": 5, "javascript_errors": errors}))
        browser.close()


if __name__ == "__main__":
    main()
