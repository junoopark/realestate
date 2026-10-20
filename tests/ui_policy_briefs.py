"""Isolated browser check: local static server, mocked APIs, no production writes.

Run: python tests/ui_policy_briefs.py (Playwright + installed Edge required).
Test-only automatic content never enters a normal DB or committed data file.
"""

import copy
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "ui-policy-briefs"
TITLE = "화면 검증용 청년 주택 공급 확대 계획"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    reviewed = json.loads((ROOT / "frontend/data/policies.json").read_text(encoding="utf-8"))
    payload = copy.deepcopy(reviewed)
    automatic = {
        "id": "test-only-auto", "title": TITLE, "agency": "테스트 기관", "published_at": "2026-10-19",
        "category": "공급·정비", "summary": "화면 검증을 위한 원문 발췌입니다. 실제 정책이 아닙니다.",
        "highlights": ["화면 검증을 위한 원문 발췌입니다. 실제 정책이 아닙니다."],
        "effective_date": None, "effective_note": "적용 대상·시행일은 발표 원문을 확인하세요.",
        "status": "공식 발표 · 자동 요약", "risk_points": [], "impact_path": None,
        "source_url": "https://www.molit.go.kr/test-only-policy", "source_kind": "official_html",
        "review_status": "automatic", "verified_at": None,
        "generated_at": "2026-10-20T00:00:00+00:00", "source_checked_at": "2026-10-20T00:00:00+00:00",
        "selection_reason": "주택 관련 발표이며 확대 내용을 포함합니다.",
    }
    payload["policies"].append(automatic)
    payload["coverage_note"] = "공식 발표의 자동 요약과 검토한 정책 자료를 구분해 표시합니다. 전체 정책을 빠짐없이 수록한 목록은 아닙니다."
    payload.update({"automation": {"enabled": True, "count": 1, "failed": 0},
                    "last_checked_at": automatic["generated_at"], "reviewed_at": reviewed["verified_at"],
                    "storage": {"available": True}})
    bundle = json.loads((ROOT / "frontend/data/factor_sample.json").read_text(encoding="utf-8"))
    bundle.update({"set": "all", "origin": "test-only", "panel": {"loaded_at": "2026-10-20"}})
    monitor = json.loads((ROOT / "frontend/data/monitor.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "frontend")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
            def api(route):
                url = route.request.url
                if "/indicators/bundle" in url:
                    route.fulfill(json=bundle)
                elif "/policies/monitor" in url:
                    route.fulfill(json=monitor)
                elif url.endswith("/policies"):
                    route.fulfill(json=payload)
                else:
                    route.abort()
            context.route("http://127.0.0.1:8000/**", api)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 1000 if width == 1440 else 844})
                page.goto(base + "policies.html", wait_until="domcontentloaded")
                expect(page.locator(".policy-card")).to_have_count(len(payload["policies"]))
                expect(page.locator(".summary-strip")).to_contain_text("자동 요약 1건")
                expect(page.locator(".summary-strip")).to_contain_text("자동 수집 확인")
                expect(page.locator("#data-status")).to_contain_text("검토 자료 확인 2026-10-05")
                auto_card = page.locator(".policy-card").filter(has_text=TITLE)
                auto_card.locator("summary").click()
                expect(auto_card.locator(".source-links")).to_contain_text("자동 요약")
                expect(auto_card.locator(".source-links")).not_to_contain_text("2026-10-05")
                expect(auto_card).to_contain_text("자동 선정 기준")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
                page.screenshot(path=str(OUT / f"policies-{width}.png"), full_page=True)
                page.get_by_role("searchbox").fill("화면 검증용")
                expect(page.locator(".policy-card")).to_have_count(1)
                page.get_by_role("searchbox").fill("")
                page.goto(base + "index.html", wait_until="domcontentloaded")
                expect(page.locator("#home-policies .policy-item")).to_have_count(4)
                expect(page.locator("#home-policies")).to_contain_text(TITLE)
                expect(page.locator("#home-policy-note")).to_contain_text("자동 수집 확인")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(OUT / f"home-{width}.png"), full_page=True)
            offline = browser.new_context(viewport={"width": 390, "height": 844})
            offline.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
            offline.route("http://127.0.0.1:8000/**", lambda route: route.abort())
            fallback = offline.new_page()
            fallback.goto(base + "policies.html", wait_until="domcontentloaded")
            expect(fallback.locator(".policy-card")).to_have_count(len(reviewed["policies"]))
            expect(fallback.locator("#data-status")).to_contain_text("저장된 자료")
            expect(fallback.locator("#data-status")).to_contain_text("2026-10-05")
            expect(fallback.locator(".summary-strip")).to_contain_text("검토 자료 확인일")
            assert not errors, errors
            browser.close()
            print(json.dumps({"status": "passed", "widths": [1440, 390], "javascript_errors": errors,
                              "checks": ["automatic/reviewed dates", "search", "home update", "offline fallback", "no overflow"]}, ensure_ascii=True))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
