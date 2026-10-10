"""Local browser smoke test. Start the API :8000 and static server :5500 first.

Requires playwright and a local Edge installation (no personal browser profile).
Screenshots go to ignored tmp/ui. No source website is crawled by this test.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:5500/"
OUT = Path(__file__).resolve().parents[1] / "tmp" / "ui"


def check_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Horizontal overflow: {page.url}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="light")
        context.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(BASE + "learn.html", wait_until="domcontentloaded")
        page.locator(".term-card").first.wait_for()
        assert page.locator(".term-card").count() == 36
        page.get_by_role("searchbox").fill("LTV")
        assert 0 < page.locator(".term-card").count() < 36
        page.get_by_role("searchbox").fill("nonexistent-search-zzzz")
        assert page.locator(".term-card").count() == 0
        page.get_by_role("searchbox").fill("")
        page.screenshot(path=str(OUT / "learn-desktop.png"))
        page.locator('[data-section="transactions"]').click()
        expect(page.locator(".filter-chips button")).to_have_count(3)
        for button in page.locator(".filter-chips button").all():
            button.click()
            expect(page.locator(".process-step")).to_have_count(7)
        page.locator('[data-section="development"]').click()
        expect(page.locator("#learn-content h3")).to_contain_text("개발")
        expect(page.locator(".process-step")).to_have_count(7)
        page.locator('[data-section="investment"]').click()
        expect(page.locator(".metric-card")).to_have_count(7)
        check_overflow(page)
        page.screenshot(path=str(OUT / "investment-desktop.png"), full_page=True)

        page.goto(BASE + "policies.html", wait_until="domcontentloaded")
        page.locator(".policy-card").first.wait_for()
        assert page.locator(".policy-card").count() == 8
        page.locator(".policy-card summary").first.click()
        assert page.locator("details[open]").count() == 1
        page.get_by_role("searchbox").fill("PF")
        assert 0 < page.locator(".policy-card").count() < 8
        page.get_by_role("searchbox").fill("")
        page.screenshot(path=str(OUT / "policies-desktop.png"))
        page.locator('[data-section="monitor"]').click()
        page.locator(".monitor-card").first.wait_for()
        assert page.locator(".monitor-status article").count() == 3
        assert page.locator(".monitor-card").count() >= 1
        page.screenshot(path=str(OUT / "monitor-desktop.png"))
        page.locator('[data-section="sources"]').click()
        expect(page.locator(".source-card")).to_have_count(6)
        check_overflow(page)

        for width in [390, 760]:
            page.set_viewport_size({"width": width, "height": 844})
            for path, ready in [("learn.html", ".term-card"), ("learn.html#transactions", ".process-step"), ("learn.html#investment", ".metric-card"), ("policies.html", ".policy-card"), ("policies.html#monitor", ".monitor-card"), ("index.html", "#ov-briefs .brief"), ("index.html#macro", ".var-card"), ("about.html", ".about-list")]:
                page.goto(BASE + path, wait_until="domcontentloaded")
                page.locator(ready).first.wait_for()
                check_overflow(page)
                if width == 390:
                    page.screenshot(path=str(OUT / (path.replace(".html", "").replace("#", "-") + "-mobile.png")))
            page.goto(BASE + "policies.html", wait_until="domcontentloaded")
            page.locator(".policy-card").first.wait_for()
            page.locator("#theme-btn").click()
            assert page.locator("html").get_attribute("data-theme") == "dark"
            check_overflow(page)
            page.screenshot(path=str(OUT / f"policies-dark-{width}.png"), animations="disabled")
            page.locator("#theme-btn").click()

        # A disconnected API must still show the genuine saved documents.
        offline = browser.new_context(viewport={"width": 1200, "height": 900})
        offline.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
        offline.route("http://127.0.0.1:8000/**", lambda route: route.abort())
        fallback = offline.new_page()
        fallback.goto(BASE + "learn.html", wait_until="domcontentloaded")
        fallback.locator("#data-status button").wait_for()
        assert fallback.locator(".term-card").count() == 36
        fallback.goto(BASE + "policies.html#monitor", wait_until="domcontentloaded")
        fallback.locator(".monitor-card").first.wait_for()
        assert fallback.locator(".monitor-status article").count() == 3
        assert not errors, errors
        print(json.dumps({"status": "passed", "javascript_errors": errors, "screenshots": str(OUT)}, ensure_ascii=True))
        browser.close()


if __name__ == "__main__":
    main()
