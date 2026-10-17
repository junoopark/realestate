// Google 로그인 (Supabase Auth). 머리띠의 #auth-slot 에 로그인 버튼 / 프로필 메뉴를 그린다.
// 다른 스크립트는 window.KHMI_AUTH.user 와 'khmi:auth' 이벤트(detail.user)로 로그인 여부를 안다.
// 필요: config.js(SUPABASE_URL, SUPABASE_KEY) → supabase-js UMD → telemetry.js → 이 파일
// 설계: docs/설계서_로그인_데이터다운로드.md 5.1·6.3장

(function () {
  const slot = document.querySelector("#auth-slot");
  const PENDING = "khmi_login_pending"; // 로그인 버튼을 눌렀다는 표시 (돌아온 뒤 'login' 기록을 한 번만 남기려고)
  const RETURN_HASH = "khmi_login_hash"; // 로그인 전에 보던 탭(#rental 등)

  const state = { client: null, user: null, ready: false, signIn, signOut };
  window.KHMI_AUTH = state;
  if (!slot || !window.supabase || typeof SUPABASE_URL !== "string") return;

  state.client = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  const telemetry = window.KHMI_TELEMETRY || { track() {}, log: async () => {} };

  const G_ICON =
    '<svg viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.6 9.2c0-.6-.1-1.2-.2-1.7H9v3.3h4.8a4.1 4.1 0 0 1-1.8 2.7v2.2h2.9c1.7-1.6 2.7-3.9 2.7-6.5z"/><path fill="#34A853" d="M9 18c2.4 0 4.5-.8 5.9-2.2l-2.9-2.2c-.8.5-1.8.9-3 .9-2.3 0-4.3-1.6-5-3.7H1v2.3A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M4 10.8a5.4 5.4 0 0 1 0-3.5V5H1a9 9 0 0 0 0 8.1l3-2.3z"/><path fill="#EA4335" d="M9 3.6c1.3 0 2.5.5 3.4 1.3l2.6-2.6A9 9 0 0 0 1 5l3 2.3c.7-2.1 2.7-3.7 5-3.7z"/></svg>';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function notice(message) {
    let box = document.querySelector(".auth-notice");
    if (!box) {
      box = el("div", "auth-notice");
      box.setAttribute("role", "status");
      document.body.append(box);
    }
    box.textContent = message;
    box.hidden = false;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => (box.hidden = true), 6000);
  }

  function displayName(user) {
    const m = user.user_metadata || {};
    return m.full_name || m.name || (user.email || "").split("@")[0] || "사용자";
  }

  function render(mode) {
    slot.replaceChildren();
    if (!state.user) {
      const btn = el("button", "auth-login");
      btn.type = "button";
      btn.innerHTML = G_ICON;
      btn.append(el("span", "auth-login-lbl", mode === "busy" ? "로그인 중…" : "로그인"));
      btn.disabled = mode === "busy" || !state.ready;
      btn.setAttribute("aria-label", "Google 계정으로 로그인");
      btn.addEventListener("click", signIn);
      slot.append(btn);
      return;
    }
    const user = state.user;
    const name = displayName(user);
    const btn = el("button", "auth-avatar");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", "auth-menu");
    btn.setAttribute("aria-label", `${name} 계정 메뉴`);
    const photo = user.user_metadata && user.user_metadata.avatar_url;
    if (photo) {
      const img = el("img");
      img.src = photo;
      img.alt = "";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => img.replaceWith(el("span", "auth-initial", name.slice(0, 1))));
      btn.append(img);
    } else {
      btn.append(el("span", "auth-initial", name.slice(0, 1)));
    }

    const menu = el("div", "auth-menu");
    menu.id = "auth-menu";
    menu.hidden = true;
    menu.append(el("strong", "auth-name", name), el("span", "auth-email", user.email || ""));
    const out = el("button", "auth-logout", "로그아웃");
    out.type = "button";
    out.addEventListener("click", signOut);
    menu.append(out);

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMenu(menu.hidden);
    });
    slot.append(btn, menu);
  }

  function toggleMenu(open) {
    const btn = slot.querySelector(".auth-avatar");
    const menu = slot.querySelector(".auth-menu");
    if (!btn || !menu) return;
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
  }

  // 메뉴 밖을 누르거나 Esc 를 누르면 닫는다 (한 번만 등록)
  document.addEventListener("click", (e) => {
    if (!slot.contains(e.target)) toggleMenu(false);
  });
  slot.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && slot.querySelector(".auth-menu:not([hidden])")) {
      toggleMenu(false);
      slot.querySelector(".auth-avatar").focus();
    }
  });

  async function signIn() {
    try {
      sessionStorage.setItem(PENDING, "1");
      sessionStorage.setItem(RETURN_HASH, location.hash);
    } catch (e) {}
    render("busy");
    // 돌아올 주소에는 #탭을 넣지 않는다(인증 코드가 ?code= 로 붙기 때문). 탭은 돌아온 뒤 되살린다.
    const { error } = await state.client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: location.origin + location.pathname },
    });
    if (error) {
      try { sessionStorage.removeItem(PENDING); } catch (e) {}
      render();
      notice("로그인을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.");
      console.warn("로그인 시작 실패:", error.message);
    }
  }

  async function signOut() {
    // 로그아웃하면 기록 권한이 사라지므로 기록을 먼저 남긴다
    await telemetry.log("logout");
    telemetry.track("logout");
    await state.client.auth.signOut();
  }

  // 로그인 직후 한 번: 기록 남기고, 보던 탭으로 되돌린다
  function afterLogin() {
    let pending = false;
    let hash = "";
    try {
      pending = sessionStorage.getItem(PENDING) === "1";
      hash = sessionStorage.getItem(RETURN_HASH) || "";
      sessionStorage.removeItem(PENDING);
      sessionStorage.removeItem(RETURN_HASH);
    } catch (e) {}
    if (!pending) return;
    // 보던 탭을 먼저 되살려야 기록의 page 가 'index.html#rental' 처럼 남는다
    if (hash && hash !== location.hash) location.hash = hash;
    telemetry.log("login", { detail: { provider: "google" } });
    telemetry.track("login", { provider: "google" });
  }

  // Google 에서 돌아온 주소의 ?code= · ?error= 정리
  function cleanUrl() {
    const url = new URL(location.href);
    const err = url.searchParams.get("error_description") || url.searchParams.get("error");
    let changed = false;
    for (const k of ["code", "error", "error_code", "error_description", "state"]) {
      if (url.searchParams.has(k)) {
        url.searchParams.delete(k);
        changed = true;
      }
    }
    if (changed) history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
    if (err) {
      try { sessionStorage.removeItem(PENDING); } catch (e) {}
      notice("로그인하지 못했습니다. 다시 시도해 주세요.");
      console.warn("로그인 실패:", err);
    }
  }

  state.client.auth.onAuthStateChange((event, session) => {
    const before = state.user && state.user.id;
    state.user = session ? session.user : null;
    state.ready = true;
    if ((state.user && state.user.id) !== before || event === "INITIAL_SESSION") {
      render();
      document.dispatchEvent(new CustomEvent("khmi:auth", { detail: { user: state.user } }));
    }
    // 콜백 안에서 다른 Supabase 호출을 기다리면 멈출 수 있어 다음 차례로 미룬다
    if (state.user && (event === "SIGNED_IN" || event === "INITIAL_SESSION")) setTimeout(afterLogin, 0);
    if (event === "INITIAL_SESSION") setTimeout(cleanUrl, 0);
  });

  render();
})();
