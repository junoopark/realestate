"""Read-only browser regression for the KHMI presentation and its About entry.

Run a frontend server first, then run:
    python tests/ui_presentation.py
    python tests/ui_presentation.py --base-url https://www.khmi.kr

Uses installed Microsoft Edge through Playwright. No network mocks, credentials,
form submissions, or production writes; external fonts and scripts load normally.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8768")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "ui-presentation")
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/"
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    errors = []
    checks = []

    def record_errors(page, label):
        page.on("pageerror", lambda error: errors.append({"page": label, "error": str(error)}))

    def ready(page, path="presentation.html"):
        response = page.goto(urljoin(base, path), wait_until="domcontentloaded", timeout=30000)
        assert response and response.ok, f"Page did not load: {path}"
        page.wait_for_function("document.documentElement.dataset.presentationReady === 'true'")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page = context.new_page()
        page.set_default_timeout(8000)
        record_errors(page, "desktop presentation")
        ready(page)
        ids = page.locator("#deck > .slide").evaluate_all("slides => slides.map(slide => slide.id)")
        assert len(ids) >= 16 and len(ids) == len(set(ids)), "Slide IDs must be unique."

        def active(index):
            expect(page.locator("#deck > .slide.active")).to_have_attribute("id", ids[index])
            expect(page.locator("#slide-counter")).to_have_text(f"{index + 1} / {len(ids)}")
            expect(page).to_have_url(urljoin(base, "presentation.html") + "#" + ids[index])

        def hash_to(slug):
            page.evaluate("slug => { location.hash = slug; }", slug)
            active(ids.index(slug))

        expect(page.locator("body")).to_have_class("deck-mode")
        expect(page.locator("#deck > .slide:visible")).to_have_count(1)
        active(0)
        expect(page.locator("#prev-slide")).to_be_disabled()
        page.locator("#next-slide").click()
        active(1)
        page.keyboard.press("ArrowRight")
        active(2)
        page.keyboard.press("PageDown")
        active(3)
        page.keyboard.press("PageUp")
        active(2)
        page.keyboard.press("ArrowLeft")
        active(1)
        page.locator("#prev-slide").click()
        active(0)
        page.keyboard.press("End")
        active(len(ids) - 1)
        expect(page.locator("#next-slide")).to_be_disabled()
        page.keyboard.press("Home")
        active(0)
        page.locator("#next-slide").focus()
        page.keyboard.press("Enter")
        active(1)
        checks.append("button, keyboard, endpoints, counter and hash navigation")

        page.locator("#next-slide").click()
        active(2)
        page.evaluate("history.back()")
        active(1)
        page.evaluate("history.forward()")
        active(2)
        hash_to("api")
        page.locator("#api a[href='#api-reference']").click()
        active(ids.index("api-reference"))
        checks.append("browser back/forward and internal appendix links")

        page.locator("#contents-btn").click()
        expect(page.locator("#contents-dialog")).to_be_visible()
        entries = page.locator("#contents-list button")
        expect(entries).to_have_count(len(ids))
        expect(page.locator("#contents-list [data-slide-id='api-reference']")).to_be_focused()
        page.keyboard.press("ArrowRight")
        active(ids.index("api-reference"))
        page.keyboard.press("Escape")
        expect(page.locator("#contents-dialog")).not_to_be_visible()
        expect(page.locator("#contents-btn")).to_be_focused()
        page.locator("#contents-btn").click()
        page.locator("#contents-list [data-slide-id='demo']").click()
        active(ids.index("demo"))
        expect(page.locator("#contents-dialog")).not_to_be_visible()
        expect(page.locator("#demo")).to_be_focused()
        checks.append("contents selection, shortcut isolation and focus return")

        page.locator("#notes-btn").click()
        expect(page.locator("#presenter-notes")).to_be_visible()
        expect(page.locator("#notes-btn")).to_have_attribute("aria-expanded", "true")
        expect(page.locator("#notes-copy")).to_have_text(page.locator("#demo .speaker-note").inner_text())
        page.keyboard.press("ArrowRight")
        active(ids.index("demo") + 1)
        note = page.locator(".slide.active .speaker-note").inner_text()
        expect(page.locator("#notes-copy")).to_have_text(note)
        page.locator("#close-notes").click()
        expect(page.locator("#presenter-notes")).not_to_be_visible()
        expect(page.locator("#notes-btn")).to_be_focused()
        page.keyboard.press("n")
        expect(page.locator("#presenter-notes")).to_be_visible()
        page.keyboard.press("n")
        expect(page.locator("#presenter-notes")).not_to_be_visible()
        checks.append("notes open/close, keyboard toggle and current-slide text")

        hash_to("demo")
        demo_hrefs = {
            "home": "index.html#home",
            "dashboard": "index.html#overview",
            "policies": "policies.html#briefs",
            "learn": "learn.html",
        }
        for key, href in demo_hrefs.items():
            button = page.locator(f"button.demo-tab[data-demo='{key}']")
            button.click()
            expect(button).to_have_attribute("aria-pressed", "true")
            expect(page.locator("button.demo-tab[aria-pressed='true']")).to_have_count(1)
            expect(page.locator("#demo-image")).to_have_attribute("src", f"assets/presentation/{key}.jpg")
            page.wait_for_function("document.getElementById('demo-image').complete && document.getElementById('demo-image').naturalWidth > 0")
            expect(page.locator("#demo-link")).to_have_attribute("href", href)
            expect(page.locator("#demo-link")).to_have_attribute("target", "_blank")
            expect(page.locator("#demo-caption")).to_contain_text("2026.10.20")
        page.locator("button.demo-tab[data-demo='home']").focus()
        page.keyboard.press("Space")
        expect(page.locator("button.demo-tab[data-demo='home']")).to_have_attribute("aria-pressed", "true")
        active(ids.index("demo"))
        page.screenshot(path=str(output / "desktop-demo.png"))
        checks.append("four real demo images, captions, links and native Space activation")

        page.locator("#view-btn").click()
        expect(page.locator("body")).to_have_class("reading-mode")
        expect(page.locator("#deck > .slide:visible")).to_have_count(len(ids))
        assert page.locator("#deck > .slide").evaluate_all("slides => slides.every(slide => !slide.inert && slide.getAttribute('aria-hidden') !== 'true')")
        page.locator("#contents-btn").click()
        page.locator("#contents-list [data-slide-id='database']").click()
        active(ids.index("database"))
        page.wait_for_timeout(180)
        page.evaluate("document.getElementById('operations').scrollIntoView({behavior:'instant', block:'start'})")
        active(ids.index("operations"))
        page.keyboard.press("o")
        expect(page.locator("body")).to_have_class("deck-mode")
        active(ids.index("operations"))
        expect(page.locator("#deck > .slide:visible")).to_have_count(1)
        assert page.locator("#deck > .slide:not(.active)").evaluate_all("slides => slides.every(slide => slide.inert && slide.getAttribute('aria-hidden') === 'true')")
        checks.append("reading visibility, scroll tracking, mode toggle and inactive-slide accessibility")

        # Browser support differs in headless/fullscreen environments; either a real
        # transition or the visible accessible error message is the required outcome.
        page.locator("#fullscreen-btn").click()
        page.wait_for_function("document.fullscreenElement || /전체화면.*(지원|없습니다)/.test(document.getElementById('slide-announcement').textContent)")
        if page.evaluate("Boolean(document.fullscreenElement)"):
            expect(page.locator("#fullscreen-btn")).to_have_attribute("aria-pressed", "true")
            page.locator("#fullscreen-btn").click()
            page.wait_for_function("!document.fullscreenElement")
        checks.append("fullscreen transition or accessible unsupported-state feedback")

        # Check the actual About definition-list entry, not only another nav link.
        about = context.new_page()
        record_errors(about, "About")
        about.goto(urljoin(base, "about.html#intro"), wait_until="domcontentloaded", timeout=30000)
        about_link = about.locator("dt > a[href='presentation.html']")
        expect(about_link).to_have_text("About")
        expect(about.locator("dt:has(> a[href='presentation.html']) + dd")).to_contain_text("프로젝트 설명")
        about_link.click()
        about.wait_for_function("document.documentElement.dataset.presentationReady === 'true'")
        expect(about.locator("#intro")).to_be_visible()
        checks.append("About introduction link opens the presentation")

        mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, reduced_motion="reduce")
        mobile = mobile_context.new_page()
        mobile.set_default_timeout(8000)
        record_errors(mobile, "mobile presentation")
        ready(mobile)
        expect(mobile.locator("body")).to_have_class("reading-mode")
        expect(mobile.locator("#deck > .slide:visible")).to_have_count(len(ids))
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
        mobile.screenshot(path=str(output / "mobile-intro.png"))
        mobile.locator("#contents-btn").click()
        mobile.locator("#contents-list [data-slide-id='demo']").click()
        expect(mobile.locator("#slide-counter")).to_have_text(f"{ids.index('demo') + 1} / {len(ids)}")
        mobile.locator("button.demo-tab[data-demo='policies']").click()
        expect(mobile.locator("#demo-link")).to_have_attribute("href", "policies.html#briefs")
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile demo horizontal overflow"
        mobile.screenshot(path=str(output / "mobile-demo.png"))
        checks.append("390px initial reading mode, mobile contents/demo and no horizontal overflow")

        assert not errors, json.dumps(errors, ensure_ascii=False)
        result = {
            "status": "passed", "base_url": base, "slides": len(ids),
            "widths": [1440, 390], "elapsed_seconds": round(time.monotonic() - started, 2),
            "javascript_errors": errors, "checks": checks,
        }
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        browser.close()
        print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
