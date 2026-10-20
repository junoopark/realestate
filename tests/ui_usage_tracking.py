"""Browser checks for anonymous usage measurement; all event POSTs are intercepted.

Runs its own local static server and installed Edge. No production analytics or
external service is written. The fixture tests visibility timing, tab deduplication,
privacy preferences, storage failures and bounded retries; actual policy/chart
pages then verify that their interactions connect to the measurement helpers.
"""

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FIXTURE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"></head>
<body style="margin:0"><div id="chart" style="width:400px;height:200px">차트</div>
<details id="policy"><summary>정책 펼치기</summary><a href="#original">공식 원문</a></details>
<div style="height:1800px"></div><div id="below" style="width:400px;height:200px">아래 차트</div>
<script>const API_BASE_URL = "/api";</script><script src="/js/telemetry.js"></script>
<script>
KHMI_TELEMETRY.observeIndicators(document.querySelector("#chart"), ["V043:nation"]);
KHMI_TELEMETRY.observeIndicators(document.querySelector("#below"), ["V045:nation"]);
KHMI_TELEMETRY.bindPolicy(document.querySelector("#policy"), "brief:example");
KHMI_TELEMETRY.bindPolicyLink(document.querySelector("#policy a"), "brief:example");
document.querySelector("#policy a").addEventListener("click", event => event.preventDefault());
</script></body></html>"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(FRONTEND)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    sample = json.loads((FRONTEND / "data/factor_sample.json").read_text(encoding="utf-8"))
    checks = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)

        def setup(init=None, statuses=None):
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            if init:
                context.add_init_script(init)
            attempts, errors = [], []
            status_list = list(statuses or [])

            def route_request(route):
                request, path = route.request, urlparse(route.request.url).path
                if path.endswith("/usage/events"):
                    payload = request.post_data_json
                    attempts.append(payload)
                    route.fulfill(status=status_list.pop(0) if status_list else 202, json={"accepted": len(payload["events"])})
                elif path == "/tracking-fixture.html":
                    route.fulfill(content_type="text/html", body=FIXTURE)
                elif path == "/indicators/bundle":
                    route.fulfill(json=sample)
                elif request.url.startswith(base + "/"):
                    route.continue_()
                else:
                    # Prevent external fonts, auth SDKs, live data and linked news.
                    route.abort()

            context.route("**/*", route_request)
            page = context.new_page()
            page.set_default_timeout(8000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            return context, page, attempts, errors

        def events(attempts, name=None):
            return [event for batch in attempts for event in batch["events"] if name is None or event["event"] == name]

        def settle(page, millis=2700):
            page.wait_for_timeout(millis)

        legacy_session = "11111111-1111-4111-8111-111111111111"
        context, page, attempts, errors = setup(f"sessionStorage.setItem('khmi_sid', '{legacy_session}');")
        page.goto(base + "/tracking-fixture.html")
        settle(page, 1200)
        assert not attempts, "Rendering a chart must not immediately count as viewing it."
        # Interrupted visibility must restart the full two-second interval.
        page.evaluate("""() => {
            window.__visibility = 'hidden';
            Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => window.__visibility });
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        settle(page, 1400)
        assert not attempts, "Background tabs must not complete the view timer."
        page.evaluate("window.__visibility = 'visible'; document.dispatchEvent(new Event('visibilitychange'))")
        settle(page, 1200)
        assert not attempts, "Resuming a tab must start a new full visibility interval."
        settle(page, 1500)
        assert [event["target"] for event in events(attempts)] == ["V043:nation"]
        assert attempts[0]["session_id"] != legacy_session
        assert page.evaluate("sessionStorage.getItem('khmi_sid')") == legacy_session
        assert page.evaluate("sessionStorage.getItem('khmi_usage_sid')") == attempts[0]["session_id"]
        checks.append("로그인 기록 세션과 신규 익명 조회 세션 ID 분리")
        checks.append("2초 연속·50% 이상 화면 노출 및 foreground 조건")

        page.evaluate("KHMI_TELEMETRY.observeIndicators(document.querySelector('#chart'), ['V043:nation'])")
        settle(page)
        assert len(events(attempts)) == 1
        page.reload()
        settle(page)
        assert len(events(attempts)) == 1, "Reloads in the same tab must preserve the deduplication key."
        page.locator("#below").scroll_into_view_if_needed()
        settle(page)
        assert [event["target"] for event in events(attempts)] == ["V043:nation", "V045:nation"]
        checks.append("화면 밖 차트 제외, 스크롤 조회, 렌더·새로고침 중복 방지")

        page.locator("#policy").scroll_into_view_if_needed()
        page.evaluate("document.querySelector('#policy').open = true")
        settle(page, 650)
        assert not events(attempts, "policy_view"), "Restoring an open card is not a new user view."
        page.evaluate("document.querySelector('#policy').open = false")
        settle(page, 50)
        page.locator("#policy summary").click()
        settle(page, 650)
        page.locator("#policy a").click()
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        settle(page, 150)
        assert len(events(attempts, "policy_open")) == 1, "Leaving the page must flush pending clicks immediately."
        page.locator("#policy summary").click()
        page.locator("#policy summary").click()
        page.locator("#policy a").dispatch_event("auxclick", {"button": 1})
        settle(page, 650)
        assert len(events(attempts, "policy_view")) == len(events(attempts, "policy_open")) == 1
        for batch in attempts:
            assert set(batch) == {"session_id", "events"}
            UUID(batch["session_id"])
            assert len(batch["events"]) <= 20
            for event in batch["events"]:
                assert set(event) == {"event_id", "event", "target", "page"}
                UUID(event["event_id"])
        assert not errors, errors
        checks.append("사용자가 연 정책과 원문 클릭 구분, 제목·URL·PII 미전송")
        context.close()

        for preference in ["doNotTrack", "globalPrivacyControl"]:
            value = "'1'" if preference == "doNotTrack" else "true"
            context, page, attempts, errors = setup(f"Object.defineProperty(navigator, '{preference}', {{ get: () => {value} }});")
            page.goto(base + "/tracking-fixture.html")
            page.locator("#policy summary").click()
            page.locator("#policy a").click()
            settle(page)
            assert not attempts and not errors, (attempts, errors)
            context.close()
        checks.append("Do Not Track·Global Privacy Control 수집 제외")

        context, page, attempts, errors = setup(
            "Storage.prototype.getItem = () => { throw new Error('blocked'); }; Storage.prototype.setItem = () => { throw new Error('blocked'); };"
        )
        page.goto(base + "/tracking-fixture.html")
        settle(page)
        page.locator("#policy summary").click()
        settle(page, 650)
        assert len(attempts) == 2 and attempts[0]["session_id"] == attempts[1]["session_id"]
        assert not errors, errors
        checks.append("저장소 차단 시 페이지 메모리 세션 유지")
        context.close()

        context, page, attempts, errors = setup(statuses=[503, 503, 503, 503])
        page.goto(base + "/tracking-fixture.html")
        page.locator("#chart").evaluate("node => node.hidden = true")
        page.locator("#policy summary").click()
        settle(page, 5800)
        assert len(attempts) == 3, "Failed analytics batches must stop after three attempts."
        assert len({batch["events"][0]["event_id"] for batch in attempts}) == 1
        assert not errors, errors
        checks.append("API 실패 시 최대 3회 동일 ID 재시도")
        context.close()

        context, page, attempts, errors = setup()
        page.goto(base + "/policies.html#briefs")
        card = page.locator(".policy-card").first
        expect(card).to_be_visible()
        card.locator("summary").click()
        settle(page, 650)
        assert events(attempts, "policy_view")[0]["target"].startswith("brief:")
        card.locator(".source-links a").first.evaluate("node => node.addEventListener('click', event => event.preventDefault())")
        card.locator(".source-links a").first.click()
        settle(page, 650)
        assert events(attempts, "policy_open")[0]["target"].startswith("brief:")
        page.goto(base + "/policies.html#history")
        history = page.locator(".history-event").first
        expect(history).to_be_visible()
        history.locator("summary").click()
        settle(page, 650)
        assert any(event["target"].startswith("history:") and event["page"] == "history" for event in events(attempts, "policy_view"))
        page.goto(base + "/policies.html#monitor")
        original = page.locator(".monitor-card a").first
        expect(original).to_be_visible()
        original.evaluate("node => node.addEventListener('click', event => event.preventDefault())")
        original.click()
        settle(page, 650)
        assert any(event["target"].startswith("monitor:") for event in events(attempts, "policy_open"))
        assert not errors, errors
        checks.append("실제 주요 정책·연혁 카드와 새 발표 원문 계측 연결")
        context.close()

        context, page, attempts, errors = setup()
        page.goto(base + "/index.html#home")
        expect(page.locator("#home-feature .fig")).to_be_visible()
        page.locator("#home-gow").scroll_into_view_if_needed()
        settle(page)
        targets = {event["target"].split(":")[0] for event in events(attempts, "indicator_view")}
        assert {"V043", "V045", "V056"}.issubset(targets), targets
        page.locator("#home-map .map-plot").scroll_into_view_if_needed()
        settle(page)
        assert any(event["target"] == "V002:sido-map" for event in events(attempts, "indicator_view"))
        page.goto(base + "/index.html#finance")
        expect(page.locator(".var-card .chart-box").first).to_be_visible()
        page.locator(".var-card .chart-box").first.scroll_into_view_if_needed()
        settle(page)
        assert any(event["page"] == "dashboard" for event in events(attempts, "indicator_view"))
        assert not errors, errors
        checks.append("실제 합성 금리 차트 3지표·홈 지도·대시보드 계측 연결")
        context.close()

        browser.close()
    server.shutdown()
    print(json.dumps({"passed": len(checks), "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
