(() => {
  const { el, list, link, sectionTitle, searchControl, matches } = Qual;
  const container = document.querySelector("#policy-content");
  let data, query = "", category = "전체", monitorData = null, monitorBusy = false, monitorMode = "", monitorQuery = "";
  const active = () => ["briefs", "monitor", "history", "sources"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "briefs";
  function card(policy) {
    const details = el("details", "policy-card"), summary = el("summary");
    const meta = el("div", "policy-meta");
    meta.append(el("span", "qual-tag", policy.category), el("span", "", policy.agency), el("time", "", `발표 ${policy.published_at}`));
    summary.append(meta, el("h4", "", policy.title), el("p", "", policy.summary), el("span", "expand-hint", "핵심 내용 · 적용 시점 · 점검할 리스크 +"));
    const content = el("div", "policy-detail");
    const facts = el("div"), risks = el("div");
    facts.append(el("h5", "", "발표의 핵심"), list(policy.highlights));
    risks.append(el("h5", "", "점검할 리스크 · 학습용 해석"), list(policy.risk_points));
    if (policy.impact_path) risks.append(el("p", "coverage-note", `영향 경로: ${Array.isArray(policy.impact_path) ? policy.impact_path.join(" → ") : policy.impact_path}`));
    content.append(facts, risks);
    const timing = el("div", "effective");
    timing.append(el("strong", "", `${policy.status} · 원문에 제시된 일정: ${policy.effective_date || "원문·후속 공고 확인"}`));
    if (policy.effective_note) timing.append(el("p", "", policy.effective_note));
    if (policy.status_note) timing.append(el("p", "muted", policy.status_note));
    content.append(timing);
    const links = el("div", "source-links"); links.append(link(`${policy.source_name || "공식 발표"} 원문 ↗`, policy.source_url));
    if (policy.original_source_url && policy.original_source_url !== policy.source_url) links.append(link("소관 기관 자료 ↗", policy.original_source_url));
    links.append(el("span", "muted", `확인 ${policy.verified_at || data.verified_at}`)); content.append(links);
    details.append(summary, content); return details;
  }
  function briefs() {
    container.append(sectionTitle("주요 정책 정리", "공식 발표를 확인해 정리한 정책입니다. 카드를 열면 핵심 내용과 적용 조건을 볼 수 있습니다."));
    const policies = [...data.policies].sort((a,b) => b.published_at.localeCompare(a.published_at));
    const strip = el("dl", "summary-strip");
    for (const [label,value] of [["수록 정책", `${policies.length}건`], ["수록 자료의 최근 발표일", policies[0]?.published_at || "없음"], ["출처 확인일", data.verified_at]]) {
      const item = el("div"); item.append(el("dt", "", label), el("dd", "", value)); strip.append(item);
    }
    container.append(strip, el("p", "coverage-note", data.coverage_note));
    const filters = el("div", "search-row"), results = el("div", "policy-list"), count = el("p", "result-count"); count.setAttribute("role", "status");
    const draw = () => {
      const items = policies.filter(p => (category === "전체" || category === p.category) && matches([p.title,p.summary,p.agency,...p.highlights,...p.risk_points].join(" "), query));
      count.textContent = `${items.length}건 · 발표일 최신순`; results.replaceChildren(...items.map(card));
      if (!items.length) results.append(el("p", "empty-state", "일치하는 정책이 없습니다. 검색어 또는 주제를 바꿔보세요."));
    };
    filters.append(searchControl("예: 대출, 공급, 전세, PF", query, value => { query = value; draw(); }));
    const label = el("label", "", "주제"), select = el("select");
    for (const name of ["전체", ...new Set(policies.map(p => p.category))]) {
      const opt = el("option", "", name); opt.value = name; opt.selected = name === category; select.append(opt);
    }
    select.addEventListener("change", () => { category = select.value; draw(); }); label.append(select); filters.append(label);
    container.append(filters, count, results); draw();
  }
  const timeText = value => {
    if (!value) return "아직 없음";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });
  };
  function monitor() {
    container.append(sectionTitle("새 발표 모니터링", "공식 기관에서 수집한 발표 중 주택 관련 키워드가 포함된 항목입니다. 수집 후보에는 보도설명·행사·통계도 포함될 수 있어 정책 확정 여부는 원문 확인이 필요합니다."));
    const top = el("div", "section-heading"), status = el("p", "coverage-note");
    status.textContent = monitorBusy ? "기관별 수집 결과를 불러오고 있습니다…" : monitorData ? `마지막 수집 확인: ${timeText(monitorData.last_checked_at)} · ${monitorMode}` : "수집 결과에 연결하지 못했습니다. 잠시 뒤 다시 확인하거나 아래 공식 출처를 이용하세요.";
    const btn = el("button", "qual-btn", "수집 결과 다시 읽기"); btn.type = "button"; btn.disabled = monitorBusy; btn.addEventListener("click", () => loadMonitor(true)); top.append(status, btn); container.append(top);
    if (!monitorData) {
      container.append(el("p", "empty-state", monitorBusy ? "수집 결과 확인 중" : "표시할 수집 기록이 없습니다. 수집이 실행되면 여기에 표시됩니다."));
      const links = el("div", "source-links"); for (const source of data.sources) links.append(link(`${source.name} ↗`, source.url)); container.append(links); return;
    }
    container.append(el("p", "coverage-note", monitorData.coverage_note || "키워드에 따른 후보 분류입니다. 전체 부동산 정책을 빠짐없이 수집한다는 의미는 아닙니다."));
    const statuses = el("div", "monitor-status");
    for (const source of monitorData.sources || []) {
      const item = el("article");
      const statusesKo = { ok: "수집 성공", success: "수집 성공", error: "수집 실패 · 이전 자료 유지", failed: "수집 실패 · 이전 자료 유지", pending: "수집 전", never: "수집 전", never_collected: "수집 전", storage_unavailable: "수집 기록 연결 실패", partial: "일부 수집" };
      item.append(el("h4", "", source.name || source.id), el("p", "", statusesKo[source.status] || source.status), el("p", "muted", `최근 성공: ${timeText(source.last_success_at)}`));
      if (source.last_checked_at) item.append(el("p", "muted", `최근 시도: ${timeText(source.last_checked_at)}`));
      if (source.status === "ok") item.append(el("p", "muted", `이번 수집의 키워드 일치: ${source.item_count}건`));
      if (source.error) item.append(el("p", "muted", source.error)); statuses.append(item);
    }
    container.append(statuses);
    const filters = el("div", "search-row"), results = el("div", "policy-list"), count = el("p", "result-count");
    const draw = () => {
      const items = (monitorData.items || []).filter(item => matches(`${item.title} ${item.agency} ${item.summary || ""} ${(item.matched_keywords || []).join(" ")}`, monitorQuery));
      count.textContent = `수집 후보 ${items.length}건 · 정책 내용 미검토`;
      results.replaceChildren();
      for (const item of items) {
        const article = el("article", "monitor-card"), meta = el("div", "policy-meta");
        meta.append(el("span", "qual-tag", "원문 확인 필요"), el("span", "", item.agency), el("time", "", item.published_at?.slice(0,10) || "발표일 미확인"));
        article.append(meta, el("h4", "", item.title));
        if (item.summary) article.append(el("p", "", `원문 발췌: ${item.summary}`));
        article.append(el("p", "coverage-note", `분류 키워드: ${(item.matched_keywords || []).join(" · ") || "없음"}`), link("발표 원문 확인 ↗", item.source_url));
        if (item.revision_count > 1) article.append(el("p", "coverage-note", `수집한 제목·개요 변경 ${item.revision_count - 1}회 · 정책 내용 변경 여부는 원문 확인`));
        results.append(article);
      }
      if (!items.length) results.append(el("p", "empty-state", "현재 조건에 맞는 수집 후보가 없습니다. 기관별 수집 상태를 함께 확인하세요."));
    };
    filters.append(searchControl("제목·기관·키워드 검색", monitorQuery, value => { monitorQuery = value; draw(); })); container.append(filters,count,results); draw();
  }
  async function loadMonitor(force = false) {
    if (monitorBusy || (monitorData && !force)) return;
    monitorBusy = true; if (active() === "monitor") render();
    if (!monitorData) {
      try { monitorData = await Qual.json("data/monitor.json", 5000); monitorMode = "저장된 수집 기록"; if (active() === "monitor") render(); } catch { /* API 결과 또는 정직한 빈 상태를 사용 */ }
    }
    try {
      const latest = await Qual.json(`${API_BASE_URL}/policies/monitor`);
      if (!Array.isArray(latest.items) || !Array.isArray(latest.sources) || latest.storage?.available === false) throw new Error("Monitor storage unavailable");
      if (!latest.last_checked_at && monitorData?.items?.length) monitorMode = "서버는 아직 수집 전 · 저장된 수집 기록";
      else { monitorData = latest; monitorMode = "서버의 수집 기록"; }
    }
    catch { monitorMode = "서버 연결 실패 · 저장된 수집 기록"; }
    finally { monitorBusy = false; if (active() === "monitor") render(); }
  }
  function sources() {
    container.append(sectionTitle("수집 출처 · 방법", "주요 정책 정리는 원문을 읽고 검토한 자료이며, 새 발표 모니터링은 공식 피드·공개 게시판에서 수집한 후보입니다."));
    const flow = el("div", "method-steps");
    for (const [title,copy] of [["01 공식 발표 수집","기관이 공개한 제목·날짜·원문 링크·개요"],["02 주제 분류","주택·임대차·대출·PF 등 키워드 대조"],["03 변경 기록","같은 URL 중복 제거, 제목·개요 수정 이력 보존"],["04 원문 검토","발표·시행·예외를 확인한 정책만 요약에 반영"]]) {
      const step = el("div"); step.append(el("strong", "", title),el("p", "", copy)); flow.append(step);
    }
    container.append(flow);
    const grid = el("div", "source-grid");
    for (const source of data.sources) {
      const card = el("article", "source-card"); card.append(el("p", "eyebrow", source.organization),el("h4", "", source.name),el("p", "", `활용 방식: ${source.collection_method}`),el("p", "muted", `수집·확인 항목: ${(source.fields || []).join(" · ")}`));
      if (source.note) card.append(el("p", "coverage-note", source.note));
      if (source.status) card.append(el("p", "muted", `${source.status} · 확인 ${source.verified_at || data.verified_at}`));
      const links = el("div", "source-links"); links.append(link("공식 페이지 ↗",source.url)); if (source.feed_url) links.append(link("공개 RSS ↗",source.feed_url)); card.append(links); grid.append(card);
    }
    container.append(grid);
    const note = el("aside", "notice-box"); note.append(el("h4", "", "이 자료로 알 수 있는 것과 확인해야 할 것"),list(["정책의 영향 경로와 점검 항목은 학습용 해석이며 가격 상승·하락을 예측하는 점수가 아닙니다.","발표 내용이 곧 시행 중인 규정은 아닙니다. 실제 적용은 법령·고시·지역별 공고와 계약 시점에 따라 달라집니다.","자동 수집은 공개 피드·게시판에 노출된 범위만 대상으로 합니다. 누락, 수집 지연, 기관 장애가 있을 수 있어 최근 성공 시각을 함께 표시합니다.","제목·개요가 바뀐 기록은 수집 자료의 수정입니다. 정책 자체가 변경됐다는 뜻으로 단정하지 않습니다."])); container.append(note);
  }
  function render() {
    const section = active();
    document.body.classList.toggle("history-view", section === "history");
    Qual.setActive(document.querySelector("#policy-tabs"), section);
    const tabs = document.querySelector("#policy-tabs"), selectedTab = tabs.querySelector('[aria-current="page"]');
    if (selectedTab) tabs.scrollLeft = selectedTab.offsetLeft - tabs.offsetLeft - (tabs.clientWidth - selectedTab.offsetWidth) / 2;
    if (section === "history") { PolicyHistory.mount(container); return; }
    if (!data) return;
    container.replaceChildren();
    if (section === "briefs") briefs(); else if (section === "monitor") monitor(); else sources();
  }
  window.addEventListener("hashchange", () => { render(); if (active() === "monitor") loadMonitor(); });
  render();
  Qual.loadContent("/policies", "policies.json", value => {
    if (!Array.isArray(value.policies) || !Array.isArray(value.sources)) throw new Error("Invalid policy data");
    if (data && JSON.stringify(data.policies) === JSON.stringify(value.policies) && JSON.stringify(data.sources) === JSON.stringify(value.sources) && data.verified_at === value.verified_at) return;
    data = value; render(); if (active() === "monitor") loadMonitor();
  });
})();
