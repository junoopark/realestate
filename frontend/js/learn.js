(() => {
  const { el, sourceLinks, list, sectionTitle, searchControl, matches } = Qual;
  const container = document.querySelector("#learn-content");
  let data = null, query = "", category = "전체", transaction = "";
  const sections = ["glossary", "transactions", "development", "investment", "sources"];
  function process(steps) {
    const ol = el("ol", "process-list");
    for (const step of steps || []) {
      const li = el("li"), content = el("article", "process-step");
      content.append(el("h4", "", step.title), el("p", "", step.description));
      if (step.checks?.length) content.append(list(step.checks));
      li.append(content); ol.append(li);
    }
    return ol;
  }
  function glossary() {
    container.append(sectionTitle("기본 용어", "정의와 함께 ‘어디에 쓰이는지’를 읽어보세요. 대출 한도나 세율처럼 바뀔 수 있는 수치는 원문에서 확인합니다."));
    const filters = el("div", "search-row");
    const result = el("p", "result-count"); result.setAttribute("role", "status");
    const grid = el("div", "term-grid");
    const redraw = () => {
      const items = data.glossary.filter(item => (category === "전체" || category === item.category) && matches(`${item.term} ${item.definition} ${item.why}`, query));
      result.textContent = `${items.length}개 용어 · 전체 ${data.glossary.length}개`;
      grid.replaceChildren();
      for (const term of items) {
        const card = el("article", "term-card");
        card.append(el("p", "term-category", term.category), el("h4", "", term.term), el("p", "", term.definition), el("p", "term-why", term.why), sourceLinks(term.source_ids, data.sources));
        grid.append(card);
      }
      if (!items.length) grid.append(el("p", "empty-state", "일치하는 용어가 없습니다. 검색어 또는 분류를 바꿔보세요."));
    };
    filters.append(searchControl("예: 전세권, LTV, 사업성", query, value => { query = value; redraw(); }));
    const label = el("label", "", "분류"), select = el("select");
    for (const name of ["전체", ...new Set(data.glossary.map(t => t.category))]) {
      const option = el("option", "", name); option.value = name; option.selected = category === name; select.append(option);
    }
    select.addEventListener("change", () => { category = select.value; redraw(); });
    label.append(select); filters.append(label); container.append(filters, result, grid); redraw();
  }
  function transactions() {
    container.append(sectionTitle("매매 · 전세 · 월세", "거래 형태에 따라 돈의 흐름과 확인할 권리가 달라집니다. 계약 전부터 종료까지 일반적인 순서를 살펴보세요."));
    const choices = el("div", "filter-chips"), target = el("div");
    if (!data.transactions.some(t => t.id === transaction)) transaction = data.transactions[0]?.id;
    const draw = () => {
      target.replaceChildren();
      const item = data.transactions.find(t => t.id === transaction);
      if (!item) return;
      for (const button of choices.querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.dataset.id === transaction));
      target.append(el("h4", "", item.title), el("p", "process-intro", item.intro), process(item.steps));
      if (item.pitfalls?.length) {
        const notice = el("aside", "notice-box"); notice.append(el("h4", "", "특히 확인할 위험 신호"), list(item.pitfalls)); target.append(notice);
      }
      target.append(sourceLinks(item.source_ids, data.sources));
    };
    for (const item of data.transactions) {
      const btn = el("button", "", item.title); btn.type = "button"; btn.dataset.id = item.id;
      btn.addEventListener("click", () => { transaction = item.id; draw(); }); choices.append(btn);
    }
    container.append(choices, target); draw();
  }
  function institutional(key) {
    const item = data[key];
    container.append(sectionTitle(item.title, key === "development" ? "개발은 토지 확보부터 운영·회수까지 이어지는 의사결정의 연속입니다." : "수익성, 현금흐름, 계약 구조와 회수 가능성을 함께 판단합니다."));
    container.append(el("p", "process-intro", item.intro), process(item.steps));
    if (item.metrics?.length) {
      const heading = el("h4", "", "사업성을 읽는 핵심 지표"); heading.style.marginTop = "30px";
      const grid = el("div", "metric-grid");
      for (const metric of item.metrics) {
        const card = el("article", "metric-card"); card.append(el("h4", "", metric.name), el("p", "metric-formula", metric.formula), el("p", "", metric.meaning), el("p", "muted", metric.caution)); grid.append(card);
      }
      container.append(heading, grid);
    }
    container.append(sourceLinks(item.source_ids, data.sources));
  }
  function sources() {
    container.append(sectionTitle("참고 자료와 출처", data.scope_note));
    const grid = el("div", "source-grid");
    for (const source of data.sources) {
      const card = el("article", "source-card"); card.append(el("p", "eyebrow", source.organization), el("h4", "", source.name), Qual.link("공식 자료 확인 ↗", source.url)); grid.append(card);
    }
    container.append(grid, el("p", "coverage-note", `자료 확인일: ${data.verified_at}. 기관별 투자 심의 방식은 다르며, 여기에 정리한 절차는 교육용 일반 프레임입니다.`));
  }
  function render() {
    if (!data) return;
    const key = sections.includes(location.hash.slice(1)) ? location.hash.slice(1) : "glossary";
    Qual.setActive(document.querySelector("#learn-nav"), key); container.replaceChildren();
    if (key === "glossary") glossary(); else if (key === "transactions") transactions(); else if (key === "sources") sources(); else institutional(key);
  }
  window.addEventListener("hashchange", render);
  Qual.loadContent("/knowledge", "knowledge.json", value => {
    if (!Array.isArray(value.glossary) || !Array.isArray(value.sources)) throw new Error("Invalid knowledge data");
    if (data && JSON.stringify(data) === JSON.stringify(value)) return;
    data = value; render();
  });
})();
