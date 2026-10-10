(() => {
  "use strict";
  const list = document.getElementById("downloads-list");
  const status = document.getElementById("download-status");
  let catalog = [];
  let loading = true;
  let identityVersion = 0;
  let identity = null;
  const pending = new Set();
  function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text) node.textContent = text; return node; }
  function render() {
    list.replaceChildren();
    list.setAttribute("aria-busy", String(loading));
    for (const item of catalog) {
      const card = el("article", "download-card");
      card.append(el("span", "member-tag", (item.format || "CSV").toUpperCase()));
      card.append(el("h3", "", item.title), el("p", "", item.description));
      const details = el("div", "download-details");
      details.append(el("span", "", item.filename));
      if (item.bytes) details.append(el("span", "", (item.bytes / 1024).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + " KB"));
      card.append(details);
      const button = el("button", "member-btn", pending.has(item.id) ? "파일 준비 중…" : MemberAuth.state.user ? "자료 내려받기 ↓" : "Google 로그인 후 내려받기");
      button.type = "button";
      button.dataset.downloadId = item.id;
      button.disabled = pending.has(item.id) || ["loading", "unavailable"].includes(MemberAuth.state.status);
      if (MemberAuth.state.status === "unavailable") button.textContent = "로그인 준비 중";
      if (item.available === false) { button.disabled = true; button.textContent = "자료 준비 중"; }
      button.addEventListener("click", () => { void download(item); });
      card.append(button);
      list.append(card);
    }
  }
  async function download(item) {
    if (pending.has(item.id)) return;
    if (!MemberAuth.state.user) {
      try { if (MemberAuth.state.status === "error") await MemberAuth.retry(); await MemberAuth.login("downloads.html"); } catch (error) { status.textContent = error.message; status.className = "member-error"; }
      return;
    }
    const version = identityVersion;
    pending.add(item.id);
    render();
    status.className = "member-list-meta";
    status.textContent = "파일을 준비하고 있습니다.";
    try {
      const blob = await MemberAuth.request("/members/downloads/" + encodeURIComponent(item.id), { auth: true, blob: true });
      if (version !== identityVersion || !MemberAuth.state.user) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = (item.filename || item.id + ".csv").replace(/[\\/]/g, "_");
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.className = "member-success";
      status.textContent = item.title + " 파일 다운로드를 시작했습니다.";
    } catch (error) { if (version === identityVersion) { status.className = "member-error"; status.textContent = error.message; } }
    finally { if (version === identityVersion) { pending.delete(item.id); render(); } }
  }
  async function load() {
    loading = true;
    status.textContent = "자료 목록을 불러오고 있습니다.";
    status.className = "member-list-meta";
    render();
    try {
      const data = await MemberAuth.request("/members/downloads");
      catalog = data.items || [];
      loading = false;
      status.textContent = "제공 자료 " + catalog.length + "개";
      render();
      if (!catalog.length) { const empty = el("div", "member-empty"); empty.append(el("h3", "", "자료를 준비하고 있어요."), el("p", "", "공개할 자료가 등록되면 이곳에서 확인할 수 있습니다.")); list.append(empty); }
    } catch (error) {
      loading = false;
      render();
      status.textContent = error.message;
      status.className = "member-error";
      const retry = el("button", "member-btn secondary", "자료 목록 다시 불러오기");
      retry.type = "button";
      retry.onclick = load;
      list.append(retry);
    }
  }
  MemberAuth.subscribe(auth => {
    const next = auth.user?.id || null;
    if (next !== identity) { identity = next; identityVersion += 1; pending.clear(); status.textContent = auth.user ? "자료를 내려받을 수 있습니다." : "자료를 내려받으려면 로그인해 주세요."; status.className = "member-list-meta"; }
    if (catalog.length) render();
  });
  void load();
})();
