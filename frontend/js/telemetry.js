// 사용 기록: Vercel Web Analytics(방문 통계 · 이벤트) + Supabase activity_logs(로그인 사용자의 행동 원장)
// 설계: docs/설계서_로그인_데이터다운로드.md 6·7장
// - Vercel 로는 사용자를 알아볼 수 있는 값(이메일·ID)을 보내지 않는다.
// - 기록이 실패해도 로그인·내려받기 같은 화면 동작은 막지 않는다.
// config.js 다음, auth.js 앞에 불러온다.

(function () {
  const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);

  // Vercel: 스크립트가 늦게 와도 호출이 쌓이도록 큐를 먼저 만든다. 로컬에는 스크립트가 없으므로 붙이지 않는다.
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
  if (!LOCAL && typeof VERCEL_ANALYTICS_SRC === "string") {
    const s = document.createElement("script");
    s.defer = true;
    s.src = VERCEL_ANALYTICS_SRC;
    document.head.append(s);
  }

  function sessionId() {
    try {
      let id = sessionStorage.getItem("khmi_sid");
      if (!id) {
        id = crypto.randomUUID();
        sessionStorage.setItem("khmi_sid", id);
      }
      return id;
    } catch (e) {
      return null;
    }
  }

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

  // 대시보드 탭(#overview, #rental …) 이동은 Vercel 이 페이지로 세지 않으므로 이벤트로 보낸다. Supabase 에는 남기지 않는다.
  if (/(^|\/)(index\.html)?$/.test(location.pathname)) {
    window.addEventListener("hashchange", () => track("tab_view", { view: location.hash.slice(1) || "home" }));
  }

  window.KHMI_TELEMETRY = { track, log };
})();
