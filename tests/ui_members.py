"""Isolated Google-login/download/likes UI checks, with test-only fixtures.

Run: python tests/ui_members.py
Requires: pip install playwright, and a local Microsoft Edge installation.
Starts its own static server; no accounts, credentials, cloud writes or personal
browser profile are used. Actual Google OAuth and Supabase/PostgreSQL integration
still require the setup guide. Backend authorization has separate real API tests.
"""

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "ui"
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
MOCK_SDK = r"""
(() => {
  let callback = () => {};
  let session = JSON.parse(sessionStorage.getItem('test.member.session') || 'null');
  function change(identity) {
    session = identity ? {access_token: 'test-token-' + identity, user: {
      id: identity === 'A' ? '11111111-1111-4111-8111-111111111111' : '22222222-2222-4222-8222-222222222222',
      user_metadata: {full_name: 'Test member ' + identity}
    }} : null;
    sessionStorage.setItem('test.member.session', JSON.stringify(session));
    callback(session ? 'SIGNED_IN' : 'SIGNED_OUT', session);
  }
  window.setTestMember = change;
  window.supabase = {createClient: (url, key, options) => {
    window.testClientOptions = options;
    return {auth: {
      onAuthStateChange: fn => {callback = fn; return {data: {subscription: {unsubscribe() {}}}};},
      getSession: async () => ({data: {session}, error: null}),
      signInWithOAuth: async options => {
        sessionStorage.setItem('test.oauth.options', JSON.stringify(options));
        return {data: {}, error: null};
      },
      exchangeCodeForSession: async code => {
        sessionStorage.setItem('test.oauth.code', code);
        change('A'); return {data: {session}, error: null};
      },
      signOut: async () => {change(null); return {error: null};}
    }};
  }};
})();
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class MockApi:
    def __init__(self):
        self.enabled = True
        self.requests = []
        self.likes = {"V001": {A}, "V012": {B}}
        self.indicators = json.loads((ROOT / "frontend/data/drivers.json").read_text(encoding="utf-8"))["variables"]

    def item(self, variable, member):
        voters = self.likes.get(variable["id"], set())
        return {"id": variable["id"], "name": variable["name"], "driver": variable["driver"],
                "likes": len(voters), "liked_by_me": bool(member and member in voters)}

    def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        path, method = url.path, request.method
        token = request.headers.get("authorization", "")
        member = {"Bearer test-token-A": A, "Bearer test-token-B": B}.get(token)
        headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization,content-type",
                   "Access-Control-Allow-Methods": "GET,PUT,DELETE,OPTIONS", "Cache-Control": "no-store"}

        def respond(data=None, status=200):
            route.fulfill(status=status, headers=headers, content_type="application/json",
                          body="" if status == 204 else json.dumps(data or {}, ensure_ascii=False))

        if method == "OPTIONS":
            return respond(status=204)
        self.requests.append((method, path, token))
        if path == "/members/config":
            return respond({"enabled": self.enabled, "supabase_url": "https://test-project.supabase.co" if self.enabled else "",
                            "supabase_publishable_key": "sb_publishable_test_only_not_a_real_key" if self.enabled else "", "provider": "google"})
        if path == "/members/me":
            return respond({"id": member, "display_name": "Test member A"}) if member else respond(status=401)
        if path == "/members/status":
            return respond({"auth_configured": self.enabled, "storage": {"type": "sqlite", "available": True, "persistent": False}, "downloads_ready": True})
        if path == "/members/downloads":
            return respond({"items": [{"id": name, "title": title, "filename": name + ".csv", "format": "CSV",
                                        "description": "Test-only CSV fixture", "bytes": 123, "available": True}
                                       for name, title in [("factor-sample", "동인별 지표 샘플 데이터"), ("variable-dictionary", "지표 변수 설명서")]]})
        if path.startswith("/members/downloads/"):
            if not member:
                return respond(status=401)
            return route.fulfill(status=200, headers={**headers, "Content-Disposition": 'attachment; filename="factor-sample.csv"'},
                                 content_type="text/csv; charset=utf-8", body="\ufeff지역,값\r\n서울,101\r\n".encode())
        if path in ("/engagement/indicators", "/engagement/popular"):
            items = [self.item(variable, member) for variable in self.indicators]
            if path.endswith("popular"):
                limit = int(parse_qs(url.query).get("limit", [5])[0])
                items = sorted((item for item in items if item["likes"] > 0), key=lambda item: (-item["likes"], item["id"]))[:limit]
            return respond({"items": items})
        if path.startswith("/engagement/indicators/") and path.endswith("/like"):
            if not member:
                return respond(status=401)
            key = path.split("/")[3]
            variable = next((item for item in self.indicators if item["id"] == key), None)
            if variable is None:
                return respond(status=404)
            voters = self.likes.setdefault(key, set())
            if method == "PUT":
                voters.add(member)
            elif method == "DELETE":
                voters.discard(member)
            else:
                return respond(status=405)
            return respond(self.item(variable, member))
        return respond(status=404)


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Horizontal overflow: {page.url}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "frontend")))
    Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    errors = []
    api = MockApi()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce", accept_downloads=True)
            context.add_init_script(MOCK_SDK)
            # Never contact a cloud endpoint, even if a previous local build left
            # a deployed API origin in runtime-config.js. All SDK/API data stay here.
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
            context.route("**/js/runtime-config.js", lambda route: route.fulfill(
                content_type="application/javascript", body='window.DFMBA_DEPLOYMENT = {apiBaseUrl: "http://127.0.0.1:8000"};'))
            context.route("http://127.0.0.1:8000/**", api.route)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            run_likes_checks(page, api, base)
            run_download_checks(page, api, base)
            run_callback_checks(page, base)
            run_layout_and_disabled_checks(page, api, base)

            assert not errors, errors
            browser.close()
            print(json.dumps({"member_ui": "passed", "mode": "isolated test-only mock OAuth/API", "javascript_errors": errors,
                              "mobile_widths": [320, 390, 760], "screenshots": str(OUT)}, ensure_ascii=True))
    finally:
        server.shutdown()
        server.server_close()


def run_likes_checks(page, api, base):
    page.goto(base + "popular.html", wait_until="domcontentloaded")
    page.wait_for_function("window.MemberAuth && MemberAuth.state.status === 'ready'")
    assert page.evaluate("window.testClientOptions.auth.flowType") == "pkce"
    assert page.evaluate("window.testClientOptions.auth.detectSessionInUrl") is False
    page.get_by_role("button", name="Google 로그인", exact=True).first.click()
    options = page.evaluate("JSON.parse(sessionStorage.getItem('test.oauth.options'))")
    assert options["provider"] == "google"
    assert options["options"]["redirectTo"] == base + "auth-callback.html"
    expect(page.locator(".popular-row")).to_have_count(2)
    v001 = page.locator('[data-like-id="V001"]')
    v012 = page.locator('[data-like-id="V012"]')
    expect(v001).to_have_attribute("aria-pressed", "false")
    expect(v012).to_have_attribute("aria-pressed", "false")
    v001.click()
    assert not any(method in ("PUT", "DELETE") for method, _, _ in api.requests)

    # Member A's own choice is loaded; another member's like can be added/removed.
    page.evaluate("setTestMember('A')")
    expect(v001).to_have_attribute("aria-pressed", "true")
    expect(v012).to_have_attribute("aria-pressed", "false")

    # A refresh started while a mutation is in flight must not overwrite the
    # successful toggle with counts captured before that mutation committed.
    page.evaluate("""() => {
      const original = window.fetch.bind(window);
      window.testHoldMutation = true;
      window.testHoldList = true;
      window.fetch = async (...args) => {
        if (window.testHoldMutation && String(args[0]).endsWith('/V012/like')) {
          window.testHoldMutation = false;
          await new Promise(resolve => { window.testReleaseMutation = resolve; });
        }
        const response = await original(...args);
        if (window.testHoldList && String(args[0]).endsWith('/engagement/indicators')) {
          window.testHoldList = false;
          await new Promise(resolve => { window.testReleaseOldList = resolve; });
          window.testOldListDelivered = true;
        }
        return response;
      };
    }""")
    v012.click()
    page.wait_for_function("typeof window.testReleaseMutation === 'function'")
    page.locator("#popular-refresh").click()
    page.wait_for_function("typeof window.testReleaseOldList === 'function'")
    page.evaluate("window.testReleaseMutation()")
    expect(v012).to_have_attribute("aria-pressed", "true")
    expect(v012).to_contain_text("2")
    page.evaluate("window.testReleaseOldList()")
    page.wait_for_function("window.testOldListDelivered === true")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(v012).to_have_attribute("aria-pressed", "true")
    expect(v012).to_contain_text("2")
    v012.click()
    expect(v012).to_have_attribute("aria-pressed", "false")
    assert api.likes["V012"] == {B}
    page.locator("#popular-mine").click()
    expect(page.locator(".popular-row")).to_have_count(1)
    expect(page.locator(".popular-row")).to_have_attribute("data-indicator-id", "V001")
    no_overflow(page)
    page.screenshot(path=str(OUT / "popular-member-desktop.png"), full_page=True)

    # Hold A's result across an account switch. Even its late arrival must not
    # restore A's private liked_by_me flags to B's screen.
    page.evaluate("""() => {
      const original = window.fetch.bind(window);
      window.testHoldNextCounts = true;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (window.testHoldNextCounts && String(args[0]).includes('/engagement/indicators')) {
          window.testHoldNextCounts = false;
          await new Promise(resolve => { window.testReleaseCounts = resolve; });
        }
        return response;
      };
      void MemberLikes.refresh();
    }""")
    page.wait_for_function("typeof window.testReleaseCounts === 'function'")
    page.evaluate("setTestMember('B')")
    expect(v001).to_have_attribute("aria-pressed", "false")
    expect(v012).to_have_attribute("aria-pressed", "true")
    page.evaluate("window.testReleaseCounts()")
    expect(v001).to_have_attribute("aria-pressed", "false")
    page.locator("#popular-mine").click()
    expect(page.locator(".popular-row")).to_have_count(1)
    expect(page.locator(".popular-row")).to_have_attribute("data-indicator-id", "V012")
    page.get_by_role("button", name="로그아웃", exact=True).first.click()
    expect(page.locator(".popular-row")).to_have_count(2)
    expect(v001).to_have_attribute("aria-pressed", "false")
    expect(v012).to_have_attribute("aria-pressed", "false")

    # Existing dashboard charts share one indicator count, including the two
    # V001 overview charts. The real static chart data are served by our server.
    page.goto(base + "index.html", wait_until="domcontentloaded")
    expect(page.locator('[data-like-id="V001"]')).to_have_count(2)
    page.evaluate("setTestMember('A')")
    expect(page.locator('[data-like-id="V001"]').first).to_have_attribute("aria-pressed", "true")
    expect(page.locator('[data-like-id="V001"]').last).to_have_attribute("aria-pressed", "true")
    page.locator('[data-like-id="V001"]').first.click()
    expect(page.locator('[data-like-id="V001"]').first).to_have_attribute("aria-pressed", "false")
    expect(page.locator('[data-like-id="V001"]').last).to_have_attribute("aria-pressed", "false")
    assert api.likes["V001"] == set()
    page.locator('[data-like-id="V001"]').last.click()
    expect(page.locator('[data-like-id="V001"]').first).to_have_attribute("aria-pressed", "true")
    assert api.likes["V001"] == {A}
    page.goto(base + "index.html#demand", wait_until="domcontentloaded")
    expect(page.locator('#view-factor [data-like-id="V012"]')).to_have_count(1)
    assert page.locator(".var-card .indicator-like").count() > 1
    page.screenshot(path=str(OUT / "indicators-likes-desktop.png"))

    # An empty database produces an honest empty state, without a fake ranking.
    saved_likes = api.likes
    api.likes = {}
    page.goto(base + "popular.html", wait_until="domcontentloaded")
    expect(page.locator(".popular-row")).to_have_count(0)
    expect(page.locator("#popular-list")).to_contain_text("첫 좋아요")
    api.likes = saved_likes


def run_download_checks(page, api, base):
    page.goto(base + "downloads.html", wait_until="domcontentloaded")
    expect(page.locator(".download-card")).to_have_count(2)
    page.evaluate("setTestMember(null)")
    button = page.locator('[data-download-id="factor-sample"]')
    expect(button).to_contain_text("Google 로그인")
    files_before = sum(path.startswith("/members/downloads/") for _, path, _ in api.requests)
    button.click()
    assert sum(path.startswith("/members/downloads/") for _, path, _ in api.requests) == files_before
    page.evaluate("setTestMember('A')")
    expect(button).to_contain_text("자료 내려받기")
    with page.expect_download() as pending:
        button.click()
    download = pending.value
    assert download.suggested_filename == "factor-sample.csv"
    downloaded = OUT / "test-only-member-download.csv"
    download.save_as(downloaded)
    assert downloaded.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "서울,101" in downloaded.read_text(encoding="utf-8-sig")
    assert api.requests[-1] == ("GET", "/members/downloads/factor-sample", "Bearer test-token-A")
    expect(page.locator("#download-status")).to_contain_text("다운로드를 시작")
    page.screenshot(path=str(OUT / "downloads-member-desktop.png"), full_page=True)


def run_callback_checks(page, base):
    page.evaluate("sessionStorage.setItem('dfmba.member.return', new URL('popular.html', location.href).href)")
    page.goto(base + "auth-callback.html?code=test-only-code", wait_until="domcontentloaded")
    page.wait_for_url(base + "popular.html")
    assert page.evaluate("sessionStorage.getItem('test.oauth.code')") == "test-only-code"
    assert "code=" not in page.url
    page.evaluate("sessionStorage.setItem('dfmba.member.return', 'https://outside.invalid/')")
    assert page.evaluate("new URL(MemberAuth.returnTo()).origin") == base.rstrip("/")
    page.goto(base + "auth-callback.html?error=access_denied", wait_until="domcontentloaded")
    expect(page.locator("#callback-status")).to_contain_text("취소")
    assert "error=" not in page.url
    page.goto(base + "auth-callback.html", wait_until="domcontentloaded")
    expect(page.locator("#callback-title")).to_contain_text("완료하지 못했어요")


def run_layout_and_disabled_checks(page, api, base):
    for width in [320, 390, 760]:
        page.set_viewport_size({"width": width, "height": 844})
        for name in ["popular", "downloads", "index"]:
            page.goto(base + name + ".html", wait_until="domcontentloaded")
            page.wait_for_function("window.MemberAuth && MemberAuth.state.status === 'ready'")
            if name == "popular":
                expect(page.locator(".popular-row")).to_have_count(2)
            elif name == "downloads":
                expect(page.locator(".download-card")).to_have_count(2)
            else:
                expect(page.locator('[data-like-id="V001"]')).to_have_count(2)
            no_overflow(page)
            page.screenshot(path=str(OUT / f"{name}-mobile-{width}.png"), full_page=True)
        page.locator("#theme-btn").click()
        no_overflow(page)
    api.enabled = False
    for name in ["popular", "downloads"]:
        page.goto(base + name + ".html", wait_until="domcontentloaded")
        expect(page.get_by_role("button", name="로그인 준비 중", exact=True).first).to_be_disabled()
        if name == "popular":
            expect(page.locator(".popular-row")).to_have_count(2)
            assert page.locator('[data-like-id][aria-pressed="true"]').count() == 0
        else:
            expect(page.locator(".download-card")).to_have_count(2)
            expect(page.locator('[data-download-id="factor-sample"]')).to_be_disabled()
        no_overflow(page)


if __name__ == "__main__":
    main()
