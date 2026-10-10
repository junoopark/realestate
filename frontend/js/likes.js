/* One cache serves every occurrence of an indicator, including repeated charts. */
(() => {
  "use strict";
  const cache = new Map();
  const pending = new Set();
  const subscribers = new Set();
  let status = "loading";
  let error = "";
  let sequence = 0;
  let identity = null;
  let identityVersion = 0;
  function snapshot() { return { status, error, items: [...cache.values()].map(item => ({ ...item })) }; }
  function updateButtons() {
    for (const button of document.querySelectorAll("[data-like-id]")) {
      const item = cache.get(button.dataset.likeId);
      const liked = Boolean(item?.liked_by_me && MemberAuth.state.user);
      button.setAttribute("aria-pressed", String(liked));
      button.disabled = pending.has(button.dataset.likeId) || status === "loading";
      button.textContent = (liked ? "♥" : "♡") + " 좋아요" + (item ? " " + item.likes.toLocaleString("ko-KR") : status === "loading" ? " · 확인 중" : " · 다시 확인");
      button.setAttribute("aria-label", button.dataset.likeName + ": " + (liked ? "좋아요 취소" : "좋아요") + (item ? ", " + item.likes + "명" : ", 집계 확인"));
      button.title = error || (liked ? "다시 누르면 좋아요를 취소합니다." : "유용한 지표에 좋아요를 남겨주세요.");
    }
  }
  function publish() { updateButtons(); for (const fn of subscribers) fn(snapshot()); }
  async function refresh() {
    const requestNumber = ++sequence;
    const account = identityVersion;
    status = "loading";
    error = "";
    publish();
    try {
      const data = await MemberAuth.request("/engagement/indicators", { auth: Boolean(MemberAuth.state.user) });
      if (requestNumber !== sequence || account !== identityVersion) return;
      cache.clear();
      for (const item of data.items || []) cache.set(item.id, { ...item, liked_by_me: Boolean(item.liked_by_me && MemberAuth.state.user) });
      status = "ready";
    } catch (err) {
      if (requestNumber !== sequence || account !== identityVersion) return;
      status = "error";
      error = err.message;
    }
    publish();
  }
  async function toggle(id) {
    if (pending.has(id)) return;
    if (!MemberAuth.state.user) {
      try { await MemberAuth.login(); } catch (err) { MemberAuth.showNotice(err.message); }
      return;
    }
    const item = cache.get(id);
    if (!item || status === "error") { await refresh(); return; }
    const account = identityVersion;
    pending.add(id);
    updateButtons();
    try {
      const result = await MemberAuth.request("/engagement/indicators/" + encodeURIComponent(id) + "/like", { auth: true, method: item.liked_by_me ? "DELETE" : "PUT" });
      if (account !== identityVersion) return;
      sequence += 1;
      status = "ready";
      cache.set(id, { ...item, likes: result.likes, liked_by_me: result.liked_by_me });
      publish();
    } catch (err) {
      if (account === identityVersion) MemberAuth.showNotice(err.message);
    } finally { if (account === identityVersion) { pending.delete(id); updateButtons(); } }
  }
  function button(id, name) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "indicator-like";
    node.dataset.likeId = id;
    node.dataset.likeName = name || id;
    const item = cache.get(id);
    node.textContent = (item?.liked_by_me ? "♥" : "♡") + " 좋아요" + (item ? " " + item.likes.toLocaleString("ko-KR") : " · 확인 중");
    node.setAttribute("aria-pressed", String(Boolean(item?.liked_by_me)));
    node.setAttribute("aria-label", (name || id) + ": 좋아요");
    node.disabled = pending.has(id) || status === "loading";
    node.addEventListener("click", () => { void toggle(id); });
    queueMicrotask(updateButtons);
    return node;
  }
  window.MemberLikes = {
    button, refresh, toggle,
    get state() { return snapshot(); },
    subscribe(fn) { subscribers.add(fn); fn(snapshot()); return () => subscribers.delete(fn); }
  };
  let started = false;
  MemberAuth.subscribe(auth => {
    const next = auth.user?.id || null;
    if (next !== identity) {
      identity = next;
      identityVersion += 1;
      sequence += 1;
      pending.clear();
      for (const item of cache.values()) item.liked_by_me = false;
      publish(); // Clear previous account's selections before issuing a request.
      void refresh();
      started = true;
    } else if (!started && auth.status !== "loading") {
      started = true;
      void refresh();
    }
  });
})();
