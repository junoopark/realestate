(() => {
  "use strict";
  const list = document.getElementById("popular-list");
  const status = document.getElementById("popular-status");
  const all = document.getElementById("popular-all");
  const mine = document.getElementById("popular-mine");
  const refresh = document.getElementById("popular-refresh");
  const drivers = { demand: "임차수요", supply: "공급·재고", finance: "금융·상대가격", rental: "임대시장", trigger: "과열·트리거", macro: "거시경제", target: "월세 가격", overview: "월세 가격" };
  let scope = "all";
  function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = text; return node; }
  function render(state) {
    const activeLike = list.contains(document.activeElement) ? document.activeElement?.dataset.likeId : null;
    if (activeLike) queueMicrotask(() => {
      const target = [...list.querySelectorAll("[data-like-id]")].find(button => button.dataset.likeId === activeLike) || list.querySelector("a") || all;
      target.focus({ preventScroll: true });
    });
    list.replaceChildren();
    list.setAttribute("aria-busy", String(state.status === "loading"));
    refresh.disabled = state.status === "loading";
    all.setAttribute("aria-pressed", String(scope === "all"));
    mine.setAttribute("aria-pressed", String(scope === "mine"));
    status.className = "member-list-meta";
    if (state.status === "loading") { status.textContent = "좋아요를 집계하고 있습니다."; return; }
    if (state.status === "error") {
      status.textContent = state.error;
      status.className = "member-error";
      const empty = el("div", "member-empty");
      empty.append(el("h3", "", "인기 지표를 불러오지 못했어요."), el("p", "", "잠시 후 새로고침해 주세요. 전체 지표는 계속 볼 수 있습니다."));
      const link = el("a", "member-btn secondary", "전체 지표 보기"); link.href = "index.html"; empty.append(link);
      list.append(empty); return;
    }
    const items = state.items.filter(item => item.likes > 0 && (scope !== "mine" || item.liked_by_me)).sort((a, b) => b.likes - a.likes || a.id.localeCompare(b.id));
    status.textContent = scope === "mine" ? "내가 좋아요한 지표 " + items.length + "개" : "좋아요를 받은 지표 " + items.length + "개 · 누적 좋아요순";
    if (!items.length) {
      const empty = el("div", "member-empty");
      empty.append(el("h3", "", scope === "mine" ? "아직 좋아요한 지표가 없어요." : "첫 좋아요를 기다리고 있어요."), el("p", "", "대시보드에서 유용한 지표를 찾아 좋아요를 눌러보세요."));
      const link = el("a", "member-btn secondary", "지표 둘러보기 →"); link.href = "index.html"; empty.append(link);
      list.append(empty); return;
    }
    for (const [index, item] of items.entries()) {
      const row = el("article", "popular-row");
      row.dataset.indicatorId = item.id;
      row.append(el("span", "popular-rank", String(index + 1).padStart(2, "0")));
      const content = el("div", "popular-info");
      content.append(el("span", "member-tag", drivers[item.driver] || "주택시장 지표"));
      const heading = el("h3");
      const link = el("a", "", item.name);
      const driver = Object.hasOwn(drivers, item.driver) && !["target", "overview"].includes(item.driver) ? item.driver : "overview";
      link.href = "index.html?indicator=" + encodeURIComponent(item.id) + "#" + driver;
      heading.append(link);
      content.append(heading, el("p", "popular-id", item.id + " · 차트와 상세 자료 보기 →"));
      row.append(content, MemberLikes.button(item.id, item.name));
      list.append(row);
    }
  }
  all.addEventListener("click", () => { scope = "all"; render(MemberLikes.state); });
  mine.addEventListener("click", async () => {
    if (!MemberAuth.state.user) { try { await MemberAuth.login(); } catch (error) { MemberAuth.showNotice(error.message); } return; }
    scope = "mine"; render(MemberLikes.state);
  });
  refresh.addEventListener("click", () => { void MemberLikes.refresh(); });
  let identity = MemberAuth.state.user?.id;
  MemberAuth.subscribe(auth => { if (identity !== auth.user?.id) { identity = auth.user?.id; scope = "all"; render(MemberLikes.state); } });
  MemberLikes.subscribe(render);
})();
