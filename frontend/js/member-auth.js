/* Shared Google sign-in. Only public Supabase configuration reaches the browser. */
(() => {
  "use strict";
  const SDK_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.99.1/dist/umd/supabase.js";
  const RETURN_KEY = "dfmba.member.return";
  const allowedPages = new Set(["index.html", "learn.html", "policies.html", "demo.html", "popular.html", "downloads.html"]);
  let client = null;
  let initPromise;
  let authVersion = 0;
  let noticeTimer;
  const listeners = new Set();
  const state = { status: "loading", user: null, message: "로그인 확인 중" };

  function snapshot() { return { ...state, user: state.user ? { ...state.user } : null }; }
  function publish() {
    renderControls();
    for (const listener of listeners) listener(snapshot());
  }
  function displayName(user) {
    const value = user?.user_metadata?.full_name || user?.user_metadata?.name || "회원";
    // Never expose a provider's email as the display name.
    return typeof value === "string" && !value.includes("@") ? value.slice(0, 80) : "회원";
  }
  function setSession(session) {
    authVersion += 1;
    state.user = session?.user ? { id: session.user.id, display_name: displayName(session.user) } : null;
    if (state.status === "ready") state.message = "";
    publish();
  }
  function safeReturn(value) {
    try {
      const url = new URL(value || "popular.html", location.href);
      const folder = new URL(".", location.href).pathname;
      const filename = url.pathname.slice(folder.length);
      if (url.origin !== location.origin || !url.pathname.startsWith(folder) || !allowedPages.has(filename)) return new URL("popular.html", location.href).href;
      const selected = url.searchParams.get("indicator");
      const query = filename === "index.html" && /^V\d{3}$/.test(selected || "") ? "?indicator=" + selected : "";
      return url.origin + url.pathname + query + url.hash;
    } catch (_) { return new URL("popular.html", location.href).href; }
  }
  function returnTo() {
    let value;
    try { value = sessionStorage.getItem(RETURN_KEY); sessionStorage.removeItem(RETURN_KEY); } catch (_) {}
    return safeReturn(value);
  }
  function loadSdk() {
    if (window.supabase?.createClient) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SDK_URL;
      script.async = true;
      const timer = setTimeout(() => reject(new Error("로그인 서비스를 불러오지 못했습니다. 다시 시도해 주세요.")), 15000);
      script.onload = () => { clearTimeout(timer); window.supabase?.createClient ? resolve() : reject(new Error("로그인 서비스를 불러오지 못했습니다.")); };
      script.onerror = () => { clearTimeout(timer); reject(new Error("로그인 서비스를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.")); };
      document.head.append(script);
    });
  }
  async function request(path, options = {}) {
    const { auth = false, blob = false, ...fetchOptions } = options;
    const headers = new Headers(fetchOptions.headers || {});
    let requestAuthVersion;
    let requestUserId;
    if (auth) {
      const expectedUserId = state.user?.id;
      await ready();
      if (!client || !state.user) throw new Error("Google 로그인 후 이용해 주세요.");
      if (expectedUserId !== state.user.id) throw new Error("로그인 계정이 변경되었습니다. 다시 시도해 주세요.");
      const { data, error } = await client.auth.getSession();
      if (error || !data.session) throw new Error("로그인이 만료되었습니다. 다시 로그인해 주세요.");
      if (expectedUserId !== state.user?.id || data.session.user.id !== expectedUserId) throw new Error("로그인 계정이 변경되었습니다. 다시 시도해 주세요.");
      headers.set("Authorization", "Bearer " + data.session.access_token);
      requestAuthVersion = authVersion;
      requestUserId = state.user?.id;
    }
    if (fetchOptions.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    let response;
    try {
      response = await fetch(API_BASE_URL + path, { ...fetchOptions, headers, cache: "no-store", signal: controller.signal });
    } catch (_) {
      throw new Error("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally { clearTimeout(timer); }
    if (!response.ok) {
      if (response.status === 401 && auth && requestAuthVersion === authVersion && requestUserId === state.user?.id) {
        setSession(null);
        void client.auth.signOut({ scope: "local" }).catch(() => {});
      }
      const messages = {
        401: "로그인이 만료되었습니다. 다시 로그인해 주세요.",
        403: "이 작업을 수행할 권한이 없습니다.",
        404: "요청한 내용을 찾을 수 없습니다.",
        422: "요청 내용을 확인한 후 다시 시도해 주세요.",
        429: "요청이 많습니다. 잠시 후 다시 시도해 주세요.",
        503: "서비스를 준비 중입니다. 잠시 후 다시 시도해 주세요."
      };
      throw new Error(messages[response.status] || "요청을 처리하지 못했습니다. 다시 시도해 주세요.");
    }
    if (response.status === 204) return null;
    return blob ? response.blob() : response.json();
  }
  async function initialize() {
    state.status = "loading";
    state.message = "로그인 확인 중";
    publish();
    try {
      const config = await request("/members/config");
      if (!config.enabled || !config.supabase_url || !config.supabase_publishable_key) {
        state.status = "unavailable";
        state.message = "로그인 준비 중";
        publish();
        return snapshot();
      }
      await loadSdk();
      client = window.supabase.createClient(config.supabase_url, config.supabase_publishable_key, {
        auth: { flowType: "pkce", autoRefreshToken: true, persistSession: true, detectSessionInUrl: false }
      });
      // Keep this callback synchronous: awaiting auth calls inside it can deadlock the SDK.
      client.auth.onAuthStateChange((_event, session) => setSession(session));
      const { data, error } = await client.auth.getSession();
      if (error) throw new Error("로그인 정보를 확인하지 못했습니다. 다시 시도해 주세요.");
      state.status = "ready";
      setSession(data.session);
    } catch (error) {
      state.status = "error";
      state.message = error.message || "로그인 서비스에 연결하지 못했습니다.";
      publish();
    }
    return snapshot();
  }
  function ready() { if (!initPromise) initPromise = initialize(); return initPromise; }
  async function retry() { if (state.status === "loading") return ready(); initPromise = initialize(); return initPromise; }
  async function login(destination = location.href) {
    await ready();
    if (!client || state.status !== "ready") throw new Error(state.status === "unavailable" ? "로그인 기능을 준비 중입니다. 인기 지표는 로그인 없이 볼 수 있어요." : state.message);
    try { sessionStorage.setItem(RETURN_KEY, safeReturn(destination)); } catch (_) {}
    const { error } = await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: new URL("auth-callback.html", location.href).href, queryParams: { prompt: "select_account" } }
    });
    if (error) throw new Error("Google 로그인을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.");
  }
  async function logout() {
    if (!client) return;
    setSession(null); // Clear private UI before the network request completes.
    const { error } = await client.auth.signOut({ scope: "local" });
    if (error) {
      state.message = "로그아웃을 완료하지 못했습니다. 다시 시도해 주세요.";
      publish();
      throw new Error(state.message);
    }
  }
  async function completeLogin(code) {
    await ready();
    if (!client || state.status !== "ready") throw new Error(state.message);
    if (!code) throw new Error("로그인 요청이 없거나 만료되었습니다. Google 로그인을 다시 시작해 주세요.");
    const { data, error } = await client.auth.exchangeCodeForSession(code);
    if (error || !data.session) throw new Error("로그인을 완료하지 못했습니다. 로그인을 시작한 브라우저에서 다시 시도해 주세요.");
    setSession(data.session);
    // The API verifies the token; a browser session alone is not authorization.
    const version = authVersion;
    const profile = await request("/members/me", { auth: true });
    if (version === authVersion && state.user?.id === profile.id) {
      state.user.display_name = profile.display_name || "회원";
      publish();
    }
  }
  function renderControls() {
    for (const control of document.querySelectorAll("[data-member-controls]")) {
      control.replaceChildren();
      const button = document.createElement("button");
      button.type = "button";
      button.className = "member-account-button";
      if (state.user) {
        const name = document.createElement("span");
        name.className = "member-name";
        name.textContent = state.user.display_name;
        control.append(name);
        button.textContent = "로그아웃";
        button.onclick = async () => { button.disabled = true; try { await logout(); } catch (error) { showNotice(error.message); } };
      } else {
        button.textContent = state.status === "loading" ? "로그인 확인 중" : state.status === "unavailable" ? "로그인 준비 중" : state.status === "error" ? "로그인 다시 확인" : "Google 로그인";
        button.disabled = ["loading", "unavailable"].includes(state.status);
        button.onclick = async () => { try { if (state.status === "error") await retry(); else await login(); } catch (error) { showNotice(error.message); } };
      }
      control.append(button);
    }
    for (const hint of document.querySelectorAll("[data-auth-hint]")) {
      hint.textContent = state.user ? state.user.display_name + "님, 로그인되어 있습니다." : state.status === "unavailable" ? "로그인 기능을 준비 중입니다. 인기 지표와 자료 목록은 미리 볼 수 있어요." : state.status === "error" ? state.message : state.status === "loading" ? "로그인 상태를 확인하고 있습니다." : "Google 계정으로 로그인하고 자료를 내려받거나 유용한 지표에 좋아요를 남겨보세요.";
    }
  }
  function showNotice(message) {
    let notice = document.getElementById("member-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "member-notice";
      notice.className = "member-toast";
      notice.setAttribute("role", "alert");
      document.body.append(notice);
    }
    notice.textContent = message;
    notice.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 8000);
  }
  window.MemberAuth = {
    ready, retry, login, logout, completeLogin, returnTo, request, showNotice,
    get state() { return snapshot(); },
    subscribe(listener) { listeners.add(listener); listener(snapshot()); return () => listeners.delete(listener); }
  };
  void ready();
})();
