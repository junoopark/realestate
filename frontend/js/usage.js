// 공개 이용 통계: 집계 API의 숫자만 표시하고 조회 실패를 0으로 바꾸지 않는다.
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const number = new Intl.NumberFormat("ko-KR");
  const time = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  const date = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });
  const kinds = ["download", "indicator_view", "policy_view", "policy_open"];
  const names = { download: "다운로드", indicator_view: "차트 열람", policy_view: "정책 상세", policy_open: "원문 클릭" };
  let days = 30;
  let data = null;
  let controller = null;
  let requestId = 0;
  let loading = false;

  function count(value) { return Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0; }
  function fmt(value) { return number.format(count(value)); }
  function scopeLabel(value) {
    const labels = { nation: "전국", sido: "시도", sigungu: "시군구", "sido-map": "시도 지도" };
    return labels[value] || value || "";
  }
  function formattedDate(value, includeTime = false) {
    if (!value || !Number.isFinite(new Date(value).getTime())) return "기록 없음";
    return (includeTime ? time : date).format(new Date(value)).replace(/\.\s*$/, "");
  }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function isActivityAvailable() { return Boolean(data && (data.activity_available ?? data.available)); }
  function isViewsAvailable() { return Boolean(data?.views?.available); }
  function isAvailable(kind) { return kind === "download" ? isActivityAvailable() : isViewsAvailable(); }
  function empty(target, message, detail) {
    const node = element("p", "usage-empty", message);
    if (detail) node.append(element("small", "", detail));
    $(target).replaceChildren(node);
  }
  function setStatus(message, kind = "") {
    const status = $("#usage-status");
    status.textContent = message;
    status.className = `usage-status${kind ? ` usage-status-${kind}` : ""}`;
  }
  function recordsUnavailable(kind) {
    return kind === "download" ? "다운로드 통계를 불러올 수 없습니다." : "열람 통계를 아직 확인할 수 없습니다.";
  }
  function safeUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch (_) { return null; }
  }

  function renderKpis() {
    for (const kind of kinds) {
      const totals = kind === "download" ? data?.totals?.download : data?.views?.totals?.[kind];
      $(`#kpi-${kind}`).textContent = isAvailable(kind) ? fmt(totals?.events) : "—";
      $(`#kpi-${kind}-note`).textContent = isAvailable(kind)
        ? kind === "download" ? `로그인 사용자 ${fmt(totals?.users)}명` : `탭 세션 ${fmt(totals?.sessions)}개`
        : "집계 확인 불가";
    }
    const since = data?.views?.since;
    const firstDownload = data?.all_time?.since;
    const info = [];
    if (isActivityAvailable()) info.push(firstDownload ? `이용 기록 시작 ${formattedDate(firstDownload)}` : "아직 저장된 로그인·다운로드 기록이 없습니다");
    if (isViewsAvailable()) info.push(since ? `열람 계측 시작 ${formattedDate(since, true)} KST` : "열람 기록은 계측 시작 이후부터 반영됩니다");
    else info.push("열람 기록은 계측 기능 연결 후부터 표시됩니다");
    $("#usage-coverage").textContent = info.join(" · ");
    $("#usage-since-note").textContent = since
      ? `차트·정책 열람은 ${formattedDate(since, true)} KST부터 계측합니다. 그 이전 조회는 소급하지 않으며, 다운로드 기록의 집계 시작일과 다를 수 있습니다.`
      : "차트·정책의 열람 기록은 이 기능을 도입한 이후부터 쌓입니다. 기존 다운로드 기록과 집계 시작일이 다를 수 있습니다.";
  }

  function ranking(target, rows, key, options = {}) {
    const { available = true, nameKey = "label", showRank = true, limit = 10, emptyText = "선택한 기간에 기록이 없습니다." } = options;
    if (!available) { empty(target, options.unavailable || "이 통계를 불러올 수 없습니다."); return; }
    const entries = (Array.isArray(rows) ? rows : []).filter((row) => count(row[key]) > 0).slice().sort((a, b) => count(b[key]) - count(a[key])).slice(0, limit);
    if (!entries.length) { empty(target, emptyText, "기록이 쌓이면 순위가 표시됩니다."); return; }
    const maximum = Math.max(...entries.map((row) => count(row[key])), 1);
    const list = element("ol");
    for (const [index, row] of entries.entries()) {
      const item = element("li", "usage-rank-row");
      if (showRank) item.append(element("span", "usage-rank-number", String(index + 1).padStart(2, "0")));
      const body = element("div");
      const label = row[nameKey] || row.target || "표시명 없음";
      body.append(element("div", "usage-rank-name", label));
      if (row.scope && nameKey === "label") body.append(element("span", "usage-rank-scope", scopeLabel(row.scope)));
      const track = element("div", "usage-rank-track");
      track.setAttribute("aria-hidden", "true");
      const bar = element("span", "usage-rank-bar");
      bar.style.width = `${Math.max(0, Math.min(100, count(row[key]) / maximum * 100))}%`;
      track.append(bar);
      body.append(track);
      item.append(body);
      const value = element("div", "usage-rank-value", fmt(row[key]));
      value.append(element("small", "", "회"));
      item.append(value);
      list.append(item);
    }
    $(target).replaceChildren(list);
  }

  function downloadTargets() {
    if (Array.isArray(data?.download_details?.targets)) return data.download_details.targets;
    // 이전 서버와 짧은 배포 차이가 있어도 파일 형식별 행을 합쳐 같은 지표가 중복되지 않게 한다.
    const grouped = new Map();
    for (const row of data?.downloads || []) {
      const key = `${row.target || ""}|${row.scope || ""}`;
      const current = grouped.get(key) || { target: row.target, label: row.label || row.target, scope: row.scope, downloads: 0 };
      current.downloads += count(row.downloads);
      grouped.set(key, current);
    }
    return [...grouped.values()].sort((a, b) => b.downloads - a.downloads);
  }
  function renderRankings() {
    const downloads = downloadTargets();
    const indicators = data?.views?.indicators || [];
    ranking("#download-ranking", downloads, "downloads", { available: isActivityAvailable(), unavailable: recordsUnavailable("download") });
    ranking("#indicator-ranking", indicators, "views", { available: isViewsAvailable(), unavailable: recordsUnavailable("indicator_view") });
    $("#download-ranking-count").textContent = isActivityAvailable() && downloads.length ? `응답 ${fmt(downloads.length)}개 지표 중 상위 ${fmt(Math.min(10, downloads.length))}개 · CSV에는 응답된 전체 순위를 포함합니다.` : "";
    $("#indicator-ranking-count").textContent = isViewsAvailable() && indicators.length ? `응답 ${fmt(indicators.length)}개 지표 중 상위 ${fmt(Math.min(10, indicators.length))}개 · CSV에는 응답된 전체 순위를 포함합니다.` : "";
    const formats = (data?.download_details?.formats || []).map((row) => ({ ...row, label: row.format ? String(row.format).toUpperCase() : "형식 미기록" }));
    const regions = (data?.download_details?.regions || []).map((row) => ({ ...row, label: row.region || "지역 미기록" }));
    ranking("#format-ranking", formats, "downloads", { available: isActivityAvailable(), showRank: false, limit: 50, emptyText: "선택한 기간에 파일 형식 기록이 없습니다." });
    ranking("#region-ranking", regions, "downloads", { available: isActivityAvailable(), showRank: false, limit: 50, emptyText: "선택한 기간에 지역 선택 기록이 없습니다." });
  }

  function policyRows() {
    const sort = $("#policy-sort").value;
    const score = (row) => sort === "views" ? count(row.views) : sort === "opens" ? count(row.opens) : count(row.views) + count(row.opens);
    return (data?.views?.policies || []).slice().sort((a, b) => score(b) - score(a) || count(b.views) - count(a.views) || String(a.title || a.target).localeCompare(String(b.title || b.target), "ko"));
  }
  function renderPolicies() {
    const body = $("#policy-ranking");
    const rows = policyRows();
    body.replaceChildren();
    if (!isViewsAvailable() || !rows.length) {
      const tr = element("tr");
      const td = element("td", "usage-empty", !isViewsAvailable() ? recordsUnavailable("policy_view") : "선택한 기간에 정책 열람·원문 클릭 기록이 없습니다.");
      td.colSpan = 4;
      tr.append(td); body.append(tr);
      $("#policy-ranking-count").textContent = "";
      return;
    }
    for (const [index, row] of rows.entries()) {
      const tr = element("tr");
      tr.append(element("td", "", String(index + 1).padStart(2, "0")));
      const titleCell = element("td");
      const url = safeUrl(row.url);
      const title = element(url ? "a" : "span", "usage-policy-title", row.title || "제목을 확인할 수 없는 발표");
      if (url) { title.href = url; title.target = "_blank"; title.rel = "noopener noreferrer"; title.setAttribute("aria-label", `${row.title || "발표"} 원문 새 창에서 보기`); }
      titleCell.append(title);
      titleCell.append(element("span", "usage-policy-agency", row.agency || "기관 미기록"));
      tr.append(titleCell);
      for (const key of ["views", "opens"]) tr.append(element("td", "usage-policy-count", fmt(row[key])));
      body.append(tr);
    }
    $("#policy-ranking-count").textContent = `집계된 상위 ${fmt(rows.length)}개 발표 · 같은 원문 주소의 기록은 합산합니다.`;
  }

  function dailyRows() {
    const map = new Map();
    for (const row of [...(data?.daily || []), ...(data?.views?.daily || [])]) {
      if (!kinds.includes(row.event) || !isAvailable(row.event) || !/^\d{4}-\d{2}-\d{2}$/.test(row.day_kst || "")) continue;
      const record = map.get(row.day_kst) || { day: row.day_kst };
      record[row.event] = (record[row.event] || 0) + count(row.events);
      map.set(row.day_kst, record);
    }
    return [...map.values()].filter((row) => kinds.some((kind) => count(row[kind]) > 0)).sort((a, b) => a.day.localeCompare(b.day));
  }
  function recordedBy(kind, day) {
    if (!isAvailable(kind)) return false;
    const since = kind === "download" ? data?.all_time?.since : data?.views?.since;
    if (!since) return kind === "download";
    const dayEnd = new Date(`${day}T23:59:59.999+09:00`).getTime();
    return dayEnd >= new Date(since).getTime();
  }
  function svgNode(tag, attrs = {}, text = null) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text != null) node.textContent = text;
    return node;
  }
  function renderTrend() {
    const rows = dailyRows();
    const tbody = $("#usage-daily-body");
    tbody.replaceChildren();
    if (!rows.length) {
      const unavailable = !isActivityAvailable() && !isViewsAvailable();
      empty("#usage-trend-chart", unavailable ? "일별 통계를 불러올 수 없습니다." : "선택한 기간에 기록된 활동이 없습니다.", unavailable ? "새로고침으로 다시 확인해 주세요." : "새 기록이 쌓이면 이곳에 날짜별 추이가 표시됩니다.");
      const tr = element("tr"), td = element("td", "", unavailable ? "집계 확인 불가" : "표시할 일별 기록이 없습니다.");
      td.colSpan = 5; tr.append(td); tbody.append(tr);
      return;
    }
    for (const row of rows.slice().reverse()) {
      const tr = element("tr");
      tr.append(element("td", "", row.day));
      for (const kind of kinds) {
        const available = recordedBy(kind, row.day);
        const td = element("td", "", available ? fmt(row[kind]) : "—");
        if (!available) td.title = "계측 시작 전이거나 통계를 확인할 수 없습니다.";
        tr.append(td);
      }
      tbody.append(tr);
    }
    const width = Math.max(320, $("#usage-trend-chart").clientWidth);
    const height = width < 600 ? 220 : 240, left = 40, right = 15, top = 12, bottom = 39;
    const plotHeight = height - top - bottom;
    const plotWidth = width - left - right;
    const peak = Math.max(...rows.map((row) => kinds.reduce((sum, kind) => sum + count(row[kind]), 0)), 1);
    const ceiling = peak < 4 ? 4 : Math.ceil(peak / 4) * 4;
    const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-labelledby": "usage-chart-title usage-chart-description" });
    svg.append(svgNode("title", { id: "usage-chart-title" }, "기록이 있는 날짜별 활동 횟수"));
    svg.append(svgNode("desc", { id: "usage-chart-description" }, `선택 기간 중 기록이 있는 ${rows.length}일의 다운로드, 차트 열람, 정책 상세 열람, 원문 클릭을 누적 막대로 표시했습니다. 바로 아래 일별 수치 보기에서 같은 값을 확인할 수 있습니다.`));
    for (let step = 0; step <= 4; step++) {
      const value = ceiling * step / 4, y = top + plotHeight * (1 - step / 4);
      svg.append(svgNode("line", { x1: left, x2: width - right, y1: y, y2: y, class: "usage-chart-grid" }));
      svg.append(svgNode("text", { x: left - 10, y: y + 4, "text-anchor": "end", class: "usage-chart-label" }, fmt(value)));
    }
    const slot = plotWidth / rows.length, barWidth = Math.min(52, Math.max(3, slot * .64));
    const labelEvery = Math.max(1, Math.ceil(rows.length / (width < 600 ? 4 : 7)));
    for (const [index, row] of rows.entries()) {
      const x = left + slot * (index + .5);
      let running = 0;
      const group = svgNode("g");
      const details = kinds.filter((kind) => recordedBy(kind, row.day)).map((kind) => `${names[kind]} ${fmt(row[kind])}회`).join(", ");
      group.append(svgNode("title", {}, `${row.day}: ${details}`));
      for (const kind of kinds) {
        const value = count(row[kind]);
        if (!value) continue;
        const h = value / ceiling * plotHeight;
        const color = { download: "download", indicator_view: "indicator", policy_view: "policy", policy_open: "open" }[kind];
        group.append(svgNode("rect", { x: x - barWidth / 2, y: top + plotHeight - (running + value) / ceiling * plotHeight, width: barWidth, height: Math.max(.6, h), fill: `var(--usage-${color})` }));
        running += value;
      }
      svg.append(group);
      if (index % labelEvery === 0 || index === rows.length - 1) {
        // 끝 날짜가 직전 눈금과 겹치면 직전 눈금을 생략한다.
        if (index !== rows.length - 1 && rows.length - 1 - index < labelEvery * .65) continue;
        svg.append(svgNode("text", { x, y: height - 14, "text-anchor": "middle", class: "usage-chart-label" }, row.day.slice(5).replace("-", ".")));
      }
    }
    $("#usage-trend-chart").replaceChildren(svg);
  }

  function render(dataValue) {
    data = dataValue;
    renderKpis();
    renderRankings();
    renderPolicies();
    renderTrend();
    const start = data?.period?.start_at, end = data?.period?.end_at;
    $("#usage-period-label").textContent = start && end
      ? `${formattedDate(start)} ~ ${formattedDate(end)} · KST · 오늘 포함 ${days}일`
      : `한국 시간(KST) · 오늘 포함 최근 ${days}일`;
    $("#usage-checked").textContent = data?.checked_at ? `집계 기준 ${formattedDate(data.checked_at, true)} KST` : "집계 시각 확인 불가";
    $("#usage-extra-notes").textContent = (data?.notes || []).filter((note) => typeof note === "string").join(" ");
    const available = isActivityAvailable() || isViewsAvailable();
    $("#usage-export").disabled = !available;
    if (!available) setStatus(data?.reason || "이용 통계를 아직 확인할 수 없습니다. 집계 저장소 연결 후 다시 확인해 주세요.", "error");
    else if (!isActivityAvailable() || !isViewsAvailable()) setStatus(`${!isActivityAvailable() ? "다운로드" : "열람"} 통계는 현재 확인할 수 없습니다. 확인 가능한 항목만 표시합니다.`, "error");
    else setStatus("선택한 기간의 집계입니다. 기록은 캐시 갱신 후 반영되므로 방금 한 활동이 바로 보이지 않을 수 있습니다.", "success");
  }

  function resetDuringLoad() {
    data = null;
    for (const kind of kinds) {
      $(`#kpi-${kind}`).textContent = "—";
      $(`#kpi-${kind}-note`).textContent = "통계 조회 중";
    }
    for (const target of ["#download-ranking", "#indicator-ranking", "#format-ranking", "#region-ranking", "#usage-trend-chart"]) empty(target, "통계 조회 중");
    for (const target of ["#download-ranking-count", "#indicator-ranking-count", "#policy-ranking-count"]) $(target).textContent = "";
    $("#policy-ranking").replaceChildren();
    $("#usage-daily-body").replaceChildren();
    for (const [target, colspan] of [["#policy-ranking", 4], ["#usage-daily-body", 5]]) {
      const tr = element("tr"), td = element("td", "", "통계 조회 중");
      td.colSpan = colspan; tr.append(td); $(target).append(tr);
    }
    $("#usage-coverage").textContent = "다운로드와 열람 통계는 기록을 시작한 시점이 서로 다를 수 있습니다.";
    $("#usage-period-label").textContent = `한국 시간(KST) · 오늘 포함 최근 ${days}일`;
    $("#usage-checked").textContent = "통계 조회 중";
  }
  async function load() {
    const currentRequest = ++requestId;
    if (controller) controller.abort();
    controller = new AbortController();
    const requestController = controller;
    loading = true;
    document.documentElement.dataset.usageReady = "false";
    resetDuringLoad();
    $("#usage-refresh").disabled = true;
    $("#usage-export").disabled = true;
    $("#usage-content").setAttribute("aria-busy", "true");
    setStatus("선택한 기간의 이용 기록을 불러오고 있습니다.");
    const wake = setTimeout(() => {
      if (currentRequest === requestId) setStatus("서버가 통계를 준비하고 있습니다. 처음 접속할 때는 잠시 걸릴 수 있습니다.");
    }, 4000);
    const timeout = setTimeout(() => requestController.abort(), 70000);
    try {
      const response = await fetch(`${API_BASE_URL}/usage?days=${days}&top=50`, { signal: requestController.signal, cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      if (!result || typeof result !== "object" || typeof result.available !== "boolean") throw new Error("INVALID_RESPONSE");
      if (currentRequest === requestId) render(result);
    } catch (error) {
      if (currentRequest !== requestId) return;
      render({ available: false, activity_available: false, views: { available: false }, reason: "통계를 불러오지 못했습니다. 네트워크 연결을 확인한 뒤 새로고침해 주세요." });
      $("#usage-checked").textContent = "통계 조회 실패";
      $("#usage-coverage").textContent = "조회 실패로 확인할 수 없는 값은 —로 표시합니다. 이용 기록이 0이라는 뜻이 아닙니다.";
    } finally {
      clearTimeout(wake);
      clearTimeout(timeout);
      if (currentRequest === requestId) {
        loading = false;
        $("#usage-refresh").disabled = false;
        $("#usage-content").setAttribute("aria-busy", "false");
        document.documentElement.dataset.usageReady = "true";
      }
    }
  }

  // 스프레드시트가 외부 제목을 수식으로 실행하지 않게 보호하고, 한 파일에는 집계 순위만 담는다.
  function csvCell(value) {
    let text = value == null ? "" : String(value);
    if (/^[\s\u0000-\u001f]*[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  }
  function exportCsv() {
    if (!data || loading) return;
    const period = `최근 ${days}일`;
    const rows = [["구분", "순위", "항목", "범위·기관", "다운로드", "차트 열람", "정책 상세 열람", "원문 클릭", "집계 시작", "집계 종료", "기간", "집계 기준 시각"]];
    const append = (category, index, label, scope, counts) => rows.push([category, index + 1, label, scope, ...counts, data.period?.start_at || "", data.period?.end_at || "", period, data.checked_at || ""]);
    if (isActivityAvailable()) downloadTargets().slice().sort((a, b) => count(b.downloads) - count(a.downloads)).forEach((row, index) => append("지표 다운로드", index, row.label || row.target, scopeLabel(row.scope), [count(row.downloads), "", "", ""]));
    if (isViewsAvailable()) (data.views.indicators || []).slice().sort((a, b) => count(b.views) - count(a.views)).forEach((row, index) => append("지표 차트 열람", index, row.label || row.target, scopeLabel(row.scope), ["", count(row.views), "", ""]));
    if (isViewsAvailable()) policyRows().forEach((row, index) => append("정책·발표", index, row.title || "제목 미확인", row.agency || "", ["", "", count(row.views), count(row.opens)]));
    if (isActivityAvailable()) {
      for (const [key, category, labelKey] of [["formats", "다운로드 형식", "format"], ["regions", "다운로드 지역", "region"]]) {
        (data.download_details?.[key] || []).slice().sort((a, b) => count(b.downloads) - count(a.downloads)).forEach((row, index) => append(category, index, row[labelKey] || "미기록", "", [count(row.downloads), "", "", ""]));
      }
    }
    const content = "\ufeff" + rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = element("a");
    anchor.href = url;
    anchor.download = `KHMI_이용통계_${days}일_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  for (const button of document.querySelectorAll("[data-days]")) {
    button.addEventListener("click", () => {
      const next = Number(button.dataset.days);
      if (days === next) return;
      days = next;
      for (const item of document.querySelectorAll("[data-days]")) item.setAttribute("aria-pressed", String(item === button));
      load();
    });
  }
  $("#usage-refresh").addEventListener("click", load);
  $("#usage-export").addEventListener("click", exportCsv);
  $("#policy-sort").addEventListener("change", () => { if (data) renderPolicies(); });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (data) renderTrend(); }, 100);
  });
  load();
})();
