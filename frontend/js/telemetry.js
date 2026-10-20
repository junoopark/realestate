// 사용 기록: Vercel Web Analytics(방문 통계 · 이벤트) + Supabase activity_logs(로그인 사용자의 행동 원장)
// 설계: docs/설계서_로그인_데이터다운로드.md 6·7장
// - Vercel 로는 사용자를 알아볼 수 있는 값(이메일·ID)을 보내지 않는다.
// - 기록이 실패해도 로그인·내려받기 같은 화면 동작은 막지 않는다.
// config.js 다음, auth.js 앞에 불러온다.

(function () {
  const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
  const memorySessions = {};

  // Vercel: 스크립트가 늦게 와도 호출이 쌓이도록 큐를 먼저 만든다. 로컬에는 스크립트가 없으므로 붙이지 않는다.
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
  if (!LOCAL && typeof VERCEL_ANALYTICS_SRC === "string") {
    const s = document.createElement("script");
    s.defer = true;
    s.src = VERCEL_ANALYTICS_SRC;
    document.head.append(s);
  }

  function storedSession(storageKey) {
    if (memorySessions[storageKey]) return memorySessions[storageKey];
    try {
      let id = sessionStorage.getItem(storageKey);
      if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id || "")) {
        id = crypto.randomUUID();
        sessionStorage.setItem(storageKey, id);
      }
      return (memorySessions[storageKey] = id);
    } catch (e) {
      // 저장소가 차단되어도 현재 페이지에서 같은 익명 세션을 유지한다.
      try { return (memorySessions[storageKey] = crypto.randomUUID()); } catch { return null; }
    }
  }

  const sessionId = () => storedSession("khmi_sid");
  // 로그인 기록의 세션 키를 공유하지 않아 계정 기록과 직접 연결할 수 없게 한다.
  const usageSessionId = () => storedSession("khmi_usage_sid");

  function page() {
    return ((location.pathname.split("/").pop() || "index.html") + location.hash).slice(0, 80);
  }

  // Vercel 커스텀 이벤트. Hobby 요금제에서는 집계되지 않지만 Pro 로 올리면 바로 쌓이도록 호출해 둔다.
  function track(name, data) {
    try {
      window.va("event", data ? { name, data } : { name });
    } catch (e) {}
  }

  // Supabase activity_logs 한 줄. user_id 는 DB 가 로그인 세션에서 채운다(auth.uid()).
  // 조회 권한이 없으므로 insert 뒤에 .select() 를 붙이지 않는다.
  async function log(event, { target = null, detail = {} } = {}) {
    const client = window.KHMI_AUTH && window.KHMI_AUTH.client;
    if (!client || !window.KHMI_AUTH.user) return;
    try {
      const { error } = await client.from("activity_logs").insert({
        event,
        page: page(),
        target,
        detail,
        session_id: sessionId(),
        user_agent: navigator.userAgent.slice(0, 200),
      });
      if (error) console.warn("사용 기록을 저장하지 못했습니다:", error.message);
    } catch (e) {
      console.warn("사용 기록을 저장하지 못했습니다:", e);
    }
  }

  // 자체 이용 통계: 로그인 여부와 무관하게 고정된 자료 ID와 동작만 보낸다.
  // 계정·IP·사용자 에이전트·검색어·외부 URL은 요청 데이터에 포함하지 않는다.
  const optedOut = () => navigator.doNotTrack === "1" || window.doNotTrack === "1" || navigator.globalPrivacyControl === true;
  const seen = new Set();
  const pending = [];
  const watched = new Map();
  let seenLoaded = false, flushTimer = null, inFlight = false, observer = null;
  const seenKey = "khmi_usage_seen_v1";
  const contextPage = () => {
    const path = location.pathname.split("/").pop() || "index.html";
    if (path === "policies.html") return location.hash === "#history" ? "history" : "policies";
    return ["", "#home"].includes(location.hash) ? "index" : "dashboard";
  };

  function remember(key) {
    if (!seenLoaded) {
      seenLoaded = true;
      try {
        const saved = JSON.parse(sessionStorage.getItem(seenKey) || "null");
        if (saved?.session === usageSessionId() && Array.isArray(saved.keys)) {
          saved.keys.slice(-1000).forEach(value => { if (typeof value === "string") seen.add(value); });
        }
      } catch {}
    }
    if (seen.has(key)) return false;
    seen.add(key);
    // 메모리와 sessionStorage 모두 커지지 않도록 제한한다.
    if (seen.size > 1000) seen.delete(seen.values().next().value);
    try { sessionStorage.setItem(seenKey, JSON.stringify({ session: usageSessionId(), keys: [...seen] })); } catch {}
    return true;
  }

  function scheduleFlush(delay = 500) {
    if (!flushTimer && pending.length) flushTimer = setTimeout(() => { flushTimer = null; flush(); }, delay);
  }

  async function flush(leaving = false) {
    if (optedOut()) { pending.length = 0; return; }
    if (!pending.length || (inFlight && !leaving) || typeof API_BASE_URL !== "string") return;
    const batch = pending.splice(0, 20);
    if (!leaving) inFlight = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let retry = false;
    try {
      const response = await fetch(`${API_BASE_URL}/usage/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        keepalive: true,
        signal: controller.signal,
        body: JSON.stringify({ session_id: usageSessionId(), events: batch.map(item => item.event) }),
      });
      retry = response.status === 429 || response.status >= 500;
    } catch { retry = true; }
    finally {
      clearTimeout(timeout);
      if (!leaving) inFlight = false;
    }
    if (retry && !leaving) {
      for (const item of batch) {
        if (++item.attempts < 3 && pending.length < 200) pending.push(item);
      }
    }
    scheduleFlush(retry ? 2000 : 500);
  }

  function usage(event, target, pageName = contextPage()) {
    if (optedOut() || !usageSessionId() || pending.length >= 200) return;
    if (!["indicator_view", "policy_view", "policy_open"].includes(event) || !/^[a-zA-Z0-9_:-]{1,100}$/.test(target || "")) return;
    if (!remember(`${event}:${target}`)) return;
    let eventId;
    try { eventId = crypto.randomUUID(); } catch { return; }
    pending.push({ event: { event_id: eventId, event, target, page: pageName }, attempts: 0 });
    scheduleFlush();
  }

  function stopTimer(item) {
    if (item.timer) clearTimeout(item.timer);
    item.timer = null;
  }

  function forget(element) {
    const item = watched.get(element);
    if (item) stopTimer(item);
    observer?.unobserve(element);
    watched.delete(element);
  }

  function startTimer(element, item) {
    stopTimer(item);
    if (!item.visible || document.visibilityState !== "visible" || optedOut()) return;
    item.timer = setTimeout(() => {
      item.timer = null;
      if (!element.isConnected || !item.visible || document.visibilityState !== "visible") return;
      // IntersectionObserver 통지와 실제 DOM 교체 사이에 숨겨진 차트는 세지 않는다.
      const rect = element.getBoundingClientRect();
      const area = rect.width * rect.height;
      const visibleArea = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0))
        * Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
      if (!area || visibleArea / area < 0.5 || getComputedStyle(element).visibility !== "visible") return;
      item.targets.forEach(target => usage("indicator_view", target, item.page));
      forget(element);
    }, 2000);
  }

  function observeIndicators(element, targets) {
    if (!element || optedOut() || !("IntersectionObserver" in window)) return;
    for (const node of watched.keys()) if (!node.isConnected) forget(node);
    forget(element);
    if (!observer) observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const item = watched.get(entry.target);
        if (!item) continue;
        item.visible = entry.isIntersecting && entry.intersectionRatio >= 0.5;
        startTimer(entry.target, item);
      }
    }, { threshold: [0, 0.5] });
    watched.set(element, { targets: [...new Set(targets)], page: contextPage(), visible: false, timer: null });
    observer.observe(element);
  }

  function bindPolicy(details, target) {
    const summary = details.querySelector("summary");
    if (!summary) return;
    let requested = false;
    summary.addEventListener("click", () => { requested = true; });
    details.addEventListener("toggle", () => {
      if (requested && details.open && details.isConnected && document.visibilityState === "visible") usage("policy_view", target);
      requested = false;
    });
  }

  function bindPolicyLink(anchor, target) {
    const record = event => {
      if (event.type === "click" || event.button === 1) usage("policy_open", target);
    };
    anchor.addEventListener("click", record);
    anchor.addEventListener("auxclick", record);
  }

  document.addEventListener("visibilitychange", () => {
    for (const [element, item] of watched) {
      if (!element.isConnected) forget(element);
      else startTimer(element, item);
    }
    if (document.visibilityState === "hidden") flush(true);
  });
  window.addEventListener("pagehide", () => flush(true));

  // 대시보드 탭(#overview, #rental …) 이동은 Vercel 이 페이지로 세지 않으므로 이벤트로 보낸다. Supabase 에는 남기지 않는다.
  if (/(^|\/)(index\.html)?$/.test(location.pathname)) {
    window.addEventListener("hashchange", () => track("tab_view", { view: location.hash.slice(1) || "home" }));
  }

  window.KHMI_TELEMETRY = { track, log, observeIndicators, bindPolicy, bindPolicyLink };
})();
