/* 콘텐츠는 textContent로 표시하며, 외부 링크는 http(s)만 허용한다. */
window.Qual = (() => {
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function link(label, url, className = "") {
    const node = el("a", className, label);
    try {
      const parsed = new URL(url);
      if (!["https:", "http:"].includes(parsed.protocol)) return el("span", className, label);
      node.href = parsed.href;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    } catch { return el("span", className, label); }
    return node;
  }
  function sourceLinks(ids, sources) {
    const wrap = el("div", "source-links");
    for (const id of ids || []) {
      const source = sources.find(s => s.id === id);
      if (source) {
        const anchor = link(`${source.name} ↗`, source.url);
        anchor.title = source.organization || source.name;
        wrap.append(anchor);
      }
    }
    return wrap;
  }
  function list(items) {
    const ul = el("ul");
    for (const item of items || []) ul.append(el("li", "", item));
    return ul;
  }
  function sectionTitle(title, copy) {
    const frag = document.createDocumentFragment();
    const heading = el("div", "section-heading");
    heading.append(el("h3", "", title));
    frag.append(heading);
    if (copy) frag.append(el("p", "section-copy", copy));
    return frag;
  }
  function searchControl(placeholder, value, onInput) {
    const label = el("label", "search-field", "검색");
    const input = el("input");
    input.type = "search"; input.placeholder = placeholder; input.value = value;
    input.addEventListener("input", () => onInput(input.value));
    label.append(input);
    return label;
  }
  function matches(value, query) {
    const text = String(value).toLocaleLowerCase("ko");
    return query.trim().toLocaleLowerCase("ko").split(/\s+/).every(word => text.includes(word));
  }
  async function json(url, timeout = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { signal: controller.signal, cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  // 저장된 검증 자료를 즉시 보여주고 서버가 응답하면 같은 데이터 계약으로 갱신한다.
  async function loadContent(endpoint, filename, onData) {
    const status = document.querySelector("#data-status");
    let hasData = false;
    let date = "";
    function setStatus(message, retry = false) {
      status.replaceChildren(el("span", "", message));
      if (retry) {
        const btn = el("button", "qual-btn", "서버 다시 확인");
        btn.type = "button"; btn.addEventListener("click", update);
        status.append(btn);
      }
    }
    try {
      const data = await json(`data/${filename}`, 6000);
      onData(data); hasData = true; date = data.verified_at || "";
      setStatus(`출처 확인 ${date} · 저장된 자료 표시 중 · 서버의 업데이트를 확인하고 있습니다.`);
    } catch { setStatus("저장된 자료를 읽지 못해 서버에서 자료를 확인하고 있습니다."); }
    async function update() {
      setStatus(hasData ? `출처 확인 ${date} · 저장된 자료 표시 중 · 서버 확인 중…` : "서버에서 자료를 불러오고 있습니다…");
      try {
        const data = await json(`${API_BASE_URL}${endpoint}`);
        onData(data); hasData = true; date = data.verified_at || date;
        setStatus(`출처 확인 ${date} · 서버 자료 연결됨 · 정책·법령은 원문의 적용 조건을 함께 확인하세요.`);
      } catch {
        setStatus(hasData ? `출처 확인 ${date} · 서버에 연결되지 않아 저장된 자료를 표시합니다. 서버의 첫 응답에는 시간이 걸릴 수 있습니다.` : "자료를 불러오지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.", true);
      }
    }
    await update();
  }
  function setActive(nav, id) {
    for (const a of nav.querySelectorAll("a[data-section]")) {
      if (a.dataset.section === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
  }
  return { el, link, sourceLinks, list, sectionTitle, searchControl, matches, json, loadContent, setActive };
})();
