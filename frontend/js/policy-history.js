/* 정책 연혁: 검토한 공식 발표를 시간순으로 읽는 독립 화면. */
window.PolicyHistory = (() => {
  const { el, link, list, matches } = Qual;
  const TOPICS = { finance: "대출·금융", tax: "세금", supply: "공급·정비", rental: "임대차", market: "거래·청약" };
  const DIRECTIONS = { tighten: "규제 강화", ease: "규제 완화", supply: "공급 확대", protect: "주거·임차인 보호", stabilize: "금융 안정" };
  let root, data, loading = false, attempted = false, loadNote = "", apiFailed = false;
  let eraId = "all", topic = "all", query = "", observedYear = null;
  const openEvents = new Set();
  let yearObserver;
  const header = document.querySelector(".site-header");
  if (header && "ResizeObserver" in window) {
    new ResizeObserver(entries => {
      document.documentElement.style.setProperty("--history-header-height", `${Math.ceil(entries[0].target.getBoundingClientRect().height)}px`);
    }).observe(header);
  }
  const visible = () => location.hash === "#history" && root?.isConnected;
  const dateLabel = date => date.replaceAll("-", ".");
  function button(text, className, handler) {
    const node = el("button", className, text); node.type = "button"; node.addEventListener("click", handler); return node;
  }
  function selectedEvents() {
    return data.events.filter(event =>
      (eraId === "all" || event.era === eraId) &&
      (topic === "all" || event.topics.includes(topic)) &&
      matches([event.title, event.short_title, event.date, dateLabel(event.date), event.date.slice(5).split("-").map(Number).join("."), event.summary, event.change, event.agency, ...event.highlights].join(" "), query)
    ).sort((a,b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
  }
  function statusNode() {
    const node = el("p", "history-data-status"); node.id = "history-data-status"; node.setAttribute("role", "status");
    node.append(el("span", "", loadNote));
    if (apiFailed && !loading) node.append(button("서버 다시 확인", "history-retry", () => load(true)));
    return node;
  }
  function updateStatus() {
    if (!visible()) return;
    root.querySelector("#history-data-status")?.replaceWith(statusNode());
  }
  function validate(value) {
    if (!Array.isArray(value.events) || !value.events.length || !Array.isArray(value.eras) || !value.eras.length) throw new Error("Invalid history data");
    return value;
  }
  async function load(retry = false) {
    if (loading) return;
    loading = true; attempted = true; apiFailed = false;
    loadNote = data ? "저장된 연혁 표시 중 · 서버 업데이트 확인 중" : "공식 발표를 정리한 연혁을 불러오고 있습니다.";
    updateStatus();
    if (!retry && !data) {
      try {
        data = validate(await Qual.json("data/policy-history.json", 6000));
        if (visible()) render();
      } catch { /* 검토본 파일이 없으면 API에서 읽는다. */ }
    }
    try {
      const next = validate(await Qual.json(`${API_BASE_URL}/policies/history`));
      const changed = !data || JSON.stringify(data.events) !== JSON.stringify(next.events) || JSON.stringify(data.eras) !== JSON.stringify(next.eras) || data.verified_at !== next.verified_at || data.coverage_note !== next.coverage_note;
      data = next; loadNote = "서버의 검토 자료 연결됨";
      if (changed && visible()) render();
    } catch {
      apiFailed = true;
      loadNote = data ? "서버 연결이 어려워 저장된 검토 자료를 표시합니다." : "연혁 자료를 불러오지 못했습니다. 연결을 확인하고 다시 시도해 주세요.";
    } finally {
      loading = false;
      if (!data && visible()) render(); else updateStatus();
    }
  }
  function eventCard(event) {
    const details = el("details", "history-event"); details.dataset.eventId = event.id; details.open = openEvents.has(event.id);
    details.addEventListener("toggle", () => { if (details.open) openEvents.add(event.id); else openEvents.delete(event.id); });
    const summary = el("summary", "history-event-summary"), meta = el("div", "history-event-meta");
    const time = el("time", "history-date", dateLabel(event.date)); time.dateTime = event.date;
    meta.append(time, el("span", "history-date-kind", event.date_kind || "발표"));
    for (const direction of event.directions) meta.append(el("span", `history-badge history-${direction}`, DIRECTIONS[direction]));
    const title = el("div", "history-event-title"); title.append(el("h5", "", event.short_title || event.title), el("span", "history-expand", "+"));
    title.lastChild.setAttribute("aria-hidden", "true");
    summary.append(meta, title, el("p", "history-change", event.change));
    const content = el("div", "history-event-content");
    const official = el("div", "history-facts");
    official.append(el("h6", "", "무엇을 발표했나요?"), el("p", "history-full-title", event.title), el("p", "", event.summary), list(event.highlights));
    const context = el("div", "history-context");
    context.append(el("h6", "", "당시 발표가 밝힌 배경"), el("p", "", event.context), el("h6", "", "흐름을 읽는 포인트 · 해설"), el("p", "", event.reading_note));
    const note = el("p", "history-timing"); note.append(el("strong", "", "발표와 적용 시점  "), document.createTextNode(event.timing_note));
    const sources = el("div", "history-event-sources"); sources.append(el("span", "", event.agency));
    for (const source of event.sources) {
      const anchor = link(`${source.title} ↗`, source.url); anchor.title = source.organization; sources.append(anchor);
    }
    content.append(official, context, note, sources); details.append(summary, content); return details;
  }
  function reset() { eraId = "all"; topic = "all"; query = ""; render(); root.querySelector("input[type=search]")?.focus({ preventScroll: true }); }
  function renderResults() {
    const output = root.querySelector("#history-results"), yearsNav = root.querySelector("#history-year-nav"), count = root.querySelector("#history-result-count");
    if (!output || !yearsNav) return;
    yearObserver?.disconnect();
    const events = selectedEvents();
    count.textContent = `${eraId === "all" ? "전체 기간" : data.eras.find(era => era.id === eraId).period} · ${topic === "all" ? "모든 주제" : TOPICS[topic]} · 전환점 ${events.length}건`;
    const resetBtn = root.querySelector("#history-reset"); resetBtn.hidden = eraId === "all" && topic === "all" && !query;
    output.replaceChildren(); yearsNav.replaceChildren();
    const years = [...new Set(events.map(event => event.date.slice(0,4)))];
    for (const year of years) {
      const node = button(year, "history-year-button", () => {
        const target = root.querySelector(`#history-year-${year}`);
        if (!target) return;
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
        markYear(year);
      });
      node.dataset.year = year; node.setAttribute("aria-label", `${year}년 정책으로 이동`); yearsNav.append(node);
    }
    if (!events.length) {
      const empty = el("div", "history-empty"); empty.append(el("strong", "", "이 조건에 맞는 전환점이 없습니다."), el("p", "", "선정한 주요 정책만 수록되어 있습니다. 다른 시기나 주제를 선택해 보세요."), button("전체 흐름으로 돌아가기", "qual-btn", reset)); output.append(empty); return;
    }
    for (const era of data.eras) {
      const eraEvents = events.filter(event => event.era === era.id);
      if (!eraEvents.length) continue;
      const phase = el("section", "history-phase"); phase.setAttribute("aria-label", `${era.period} ${era.title}`);
      const phaseHead = el("header", "history-phase-head");
      phaseHead.append(el("p", "eyebrow", `${era.label} / ${era.period}`), el("h4", "", era.title), el("p", "", era.shift)); phase.append(phaseHead);
      for (const year of [...new Set(eraEvents.map(event => event.date.slice(0,4)))]) {
        const group = el("section", "history-year-group"); group.dataset.year = year;
        const yearHeading = el("h4", "history-year-heading", year); yearHeading.id = `history-year-${year}`; yearHeading.tabIndex = -1;
        group.setAttribute("aria-labelledby", yearHeading.id); group.append(yearHeading);
        const spine = el("div", "history-spine"); for (const event of eraEvents.filter(event => event.date.startsWith(year))) spine.append(eventCard(event));
        group.append(spine); phase.append(group);
      }
      output.append(phase);
    }
    markYear(years.includes(observedYear) ? observedYear : years[0]);
    if ("IntersectionObserver" in window) {
      yearObserver = new IntersectionObserver(entries => {
        const entry = entries.filter(item => item.isIntersecting).sort((a,b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (entry) markYear(entry.target.dataset.year);
      }, { rootMargin: `-${Math.ceil(header.getBoundingClientRect().height + 60)}px 0px -45% 0px`, threshold: 0 });
      for (const group of root.querySelectorAll(".history-year-group")) yearObserver.observe(group);
    }
  }
  function markYear(year) {
    observedYear = year;
    for (const node of root.querySelectorAll(".history-year-button")) {
      if (node.dataset.year === year) node.setAttribute("aria-current", "location"); else node.removeAttribute("aria-current");
      if (node.dataset.year === year && window.innerWidth <= 700) {
        const nav = node.parentElement;
        nav.scrollLeft = node.offsetLeft - nav.offsetLeft - (nav.clientWidth - node.offsetWidth) / 2;
      }
    }
  }
  function render() {
    yearObserver?.disconnect(); root.replaceChildren();
    const intro = el("header", "history-intro");
    intro.append(el("p", "eyebrow", "POLICY HISTORY · 10 YEARS"), el("h3", "", "정책의 방향이 바뀐 순간들"), el("p", "history-intro-copy", "과열 억제에서 거래 정상화로, 다시 공급과 금융 관리로. 주요 전환점을 따라 지난 10년의 주택정책을 읽어보세요."));
    if (data) {
      const meta = el("div", "history-meta"); meta.append(el("span", "", `${dateLabel(data.period_start)} — ${dateLabel(data.period_end)}`), el("span", "", `주요 전환점 ${data.events.length}건`), el("span", "", `원문 확인 ${dateLabel(data.verified_at)}`)); intro.append(meta);
    }
    root.append(intro);
    if (!data) {
      root.append(el("div", "history-empty", loading || !attempted ? "정책 연혁을 불러오는 중입니다…" : "연혁 자료를 표시할 수 없습니다."), statusNode()); return;
    }
    const overview = el("section", "history-overview"); overview.setAttribute("aria-labelledby", "history-overview-title");
    const overviewHeading = el("div", "history-overview-heading");
    const h = el("h4", "", "10년의 흐름, 다섯 장면"); h.id = "history-overview-title";
    overviewHeading.append(h, el("p", "", "시기를 선택해 자세히 살펴보세요")); overview.append(overviewHeading);
    const eraGrid = el("div", "history-era-grid");
    for (const era of data.eras) {
      const node = button("", "history-era", () => {
        eraId = eraId === era.id ? "all" : era.id;
        for (const b of eraGrid.children) b.setAttribute("aria-pressed", String(b.dataset.era === eraId));
        renderResults();
        root.querySelector(".history-filters").scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
      });
      node.dataset.era = era.id; node.setAttribute("aria-pressed", String(eraId === era.id));
      node.append(el("span", "history-era-period", era.period), el("strong", "", era.title), el("span", "history-era-summary", era.summary));
      const focus = el("span", "history-era-focus"); for (const word of era.focus) focus.append(el("span", "", word)); node.append(focus); eraGrid.append(node);
    }
    overview.append(eraGrid, el("p", "history-era-caption", "시기 구분과 방향 요약은 선정한 발표를 바탕으로 한 해설입니다. 같은 시기에도 정책 수단별 방향은 다를 수 있습니다.")); root.append(overview);
    const filters = el("section", "history-filters"); filters.setAttribute("aria-label", "연혁 검색과 주제 선택");
    const filterTop = el("div", "history-filter-top"); filterTop.append(el("h4", "", "시간을 따라 읽기"), el("span", "", "과거 → 현재 · 발표·시행일 기준"));
    const chips = el("div", "history-topic-chips");
    for (const [key,label] of Object.entries({ all: "모든 주제", ...TOPICS })) {
      const node = button(label, "history-topic", () => {
        topic = key; for (const b of chips.children) b.setAttribute("aria-pressed", String(b.dataset.topic === topic)); renderResults();
      }); node.dataset.topic = key; node.setAttribute("aria-pressed", String(topic === key)); chips.append(node);
    }
    const row = el("div", "history-search-row");
    row.append(Qual.searchControl("정책명·날짜 검색 (예: 8.2, DSR, 전세)", query, value => { query = value; renderResults(); }));
    const resetBtn = button("필터 초기화", "qual-btn", reset); resetBtn.id = "history-reset"; row.append(resetBtn);
    filters.append(filterTop, chips, row); root.append(filters);
    const resultHead = el("div", "history-results-head"), count = el("p", "result-count"); count.id = "history-result-count"; count.setAttribute("role", "status");
    resultHead.append(count, el("span", "", "카드를 펼치면 당시 내용과 공식 원문을 볼 수 있습니다.")); root.append(resultHead);
    const layout = el("div", "history-layout"), aside = el("aside", "history-year-rail"), nav = el("nav", "history-year-nav");
    nav.id = "history-year-nav"; nav.setAttribute("aria-label", "연도별 바로 이동"); aside.append(el("p", "eyebrow", "YEAR INDEX"), nav);
    const output = el("div", "history-results"); output.id = "history-results"; layout.append(aside, output); root.append(layout);
    const footer = el("aside", "history-method-note"); footer.append(el("h4", "", "이 타임라인을 읽는 방법"), el("p", "", data.coverage_note), el("p", "", "‘규제 강화·완화’는 당시 발표의 방향입니다. 과거 대출 한도·세율·대상 지역을 현재 거래에 그대로 적용하지 마세요. 공급 계획과 실제 준공·입주 실적도 구분해 읽어야 합니다."), statusNode()); root.append(footer);
    renderResults();
  }
  function mount(container) {
    root = container; render(); if (!attempted) load();
  }
  return { mount };
})();
