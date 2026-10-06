// 정량 지표 공용 모듈 (index.html 전용). tiles.js(Overview 타일)와 factors.js(동인 탭 변수 카드)가 함께 쓴다.
// 데이터는 data/indicators/index.json(변수 목록)과 data/indicators/<변수id>.json(시계열)에서 읽는다.
// 이 파일들은 dfmba-dashboard 파이프라인의 export/export_indicators.py 가 만든다.
//
//   변수 파일 모양: { id, name, items: { 항목명: { unit, regions: { 지역명: { freq, dates, values } } } } }
//   freq: M 월 / Q 분기 / H 반기 / Y 연.  dates 는 "2026-08", "2026Q2", "2026H1", "2025" 꼴.

window.Indicators = (() => {
  const BASE = "data/indicators";
  const DEFAULT_REGION = "서울";
  const REGION_KEY = "indicator-region";
  // 지수·비율 단위는 전기 대비를 차이(p)로, 금액·건수는 변화율(%)로 보여 준다.
  const POINT_UNITS = new Set(["지수", "%", "연%", "연리%", "2020=100", "1980.01.04=100", ""]);
  const FREQ_LABEL = { M: "전월", Q: "전분기", H: "전반기", Y: "전년" };
  const FREQ_STEPS_PER_YEAR = { M: 12, Q: 4, H: 2, Y: 1 };

  let index = null;
  const cache = new Map();
  const listeners = new Set();

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  async function json(url) {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
    return res.json();
  }

  async function loadIndex() {
    if (!index) index = await json(`${BASE}/index.json`);
    return index;
  }

  // 정적 JSON(빠름, 배포와 함께 갱신)을 먼저 읽고, 없으면 백엔드 API(/indicators/{id}, DB)에서 받는다. 두 응답은 모양이 같다.
  function loadVariable(id) {
    if (!cache.has(id)) {
      const request = json(`${BASE}/${id}.json`)
        .catch(() => (typeof API_BASE_URL === "string" ? json(`${API_BASE_URL}/indicators/${encodeURIComponent(id)}`) : Promise.reject(new Error("no data"))))
        .catch((err) => { cache.delete(id); throw err; });
      cache.set(id, request);
    }
    return cache.get(id);
  }

  // 백엔드 지표 API 상태: { count, storage: {type, source, available} } 또는 실패 시 null. 화면 표시용이라 느려도 기다리지 않는다.
  async function serverStatus() {
    if (typeof API_BASE_URL !== "string") return null;
    try {
      const res = await json(`${API_BASE_URL}/indicators`);
      return { count: res.count, updated_at: res.updated_at, storage: res.storage };
    } catch {
      return null;
    }
  }

  // ── 지역 선택 (헤더의 <select id="region-select">) ───────────────
  function region() {
    try { return localStorage.getItem(REGION_KEY) || DEFAULT_REGION; } catch { return DEFAULT_REGION; }
  }
  function setRegion(name) {
    try { localStorage.setItem(REGION_KEY, name); } catch {}
    for (const fn of listeners) fn(name);
  }
  function onRegionChange(fn) { listeners.add(fn); }

  function isSeoulGu(name) { return !!index && index.seoul_gu.includes(name); }

  // 선택한 지역이 이 계열에 없으면 서울 구 → 서울 → 전국 순으로 대체한다. 실제 쓴 지역명을 함께 돌려준다.
  function pick(item, wanted) {
    const regions = item.regions;
    const order = [wanted];
    if (isSeoulGu(wanted)) order.push("서울");
    order.push("전국");
    for (const name of order) if (regions[name]) return { name, series: regions[name] };
    const first = Object.keys(regions)[0];
    return first ? { name: first, series: regions[first] } : null;
  }

  // ── 숫자·변화량 ───────────────────────────────────────────────
  function fmt(value, unit) {
    if (value == null) return "–";
    const abs = Math.abs(value);
    const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
    const isRate = !!unit && unit.includes("%");   // 금리·비율은 3 → 3.00 처럼 자릿수를 고정한다
    return value.toLocaleString("ko-KR", { minimumFractionDigits: isRate ? digits : 0, maximumFractionDigits: digits });
  }
  function unitLabel(unit) {
    if (!unit || unit === "지수" || unit.includes("=100")) return "";
    return unit;
  }

  // 마지막 값과 k 기간 전 값을 비교한다. 지수·비율은 차이(p), 나머지는 변화율(%).
  function change(series, unit, stepsBack) {
    const v = series.values, n = v.length - 1;
    if (n - stepsBack < 0) return null;
    const last = v[n], prev = v[n - stepsBack];
    if (last == null || prev == null) return null;
    if (POINT_UNITS.has(unit)) return { diff: last - prev, kind: "p" };
    if (prev === 0) return null;
    return { diff: (last / prev - 1) * 100, kind: "%" };
  }
  function changeChip(ch, label) {
    const chip = el("span", "ind-chip");
    if (!ch) { chip.classList.add("ind-neu"); chip.textContent = `${label} –`; return chip; }
    const sign = ch.diff > 0.0005 ? "+" : ch.diff < -0.0005 ? "−" : "";
    chip.classList.add(sign === "+" ? "ind-pos" : sign === "−" ? "ind-neg" : "ind-neu");
    chip.textContent = `${label} ${sign}${Math.abs(ch.diff).toFixed(ch.kind === "p" && Math.abs(ch.diff) < 10 ? 2 : 1)}${ch.kind}`;
    return chip;
  }

  function periodLabel(date) {
    return date.replace(/^(\d{4})-(\d{2})$/, "$1.$2").replace(/^(\d{4})Q(\d)$/, "$1 $2분기").replace(/^(\d{4})H(\d)$/, "$1 $2반기");
  }

  // ── 스파크라인 (인라인 SVG) ──────────────────────────────────
  function sparkline(series, { points = 36, height = 64, name = "" } = {}) {
    const dates = series.dates.slice(-points), values = series.values.slice(-points);
    const W = 300, H = height, PAD = 4;
    const nums = values.filter((v) => v != null);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "ind-spark");
    svg.setAttribute("role", "img");
    svg.setAttribute("preserveAspectRatio", "none");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${name} ${periodLabel(dates[0])}–${periodLabel(dates.at(-1))}`;
    svg.append(title);
    if (nums.length < 2) return svg;
    const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
    const x = (i) => PAD + (i / (values.length - 1)) * (W - PAD * 2);
    const y = (v) => H - PAD - ((v - min) / span) * (H - PAD * 2);
    const pts = values.map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
    const area = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    area.setAttribute("points", `${pts[0].split(",")[0]},${H} ${pts.join(" ")} ${pts.at(-1).split(",")[0]},${H}`);
    area.setAttribute("class", "ind-spark-area");
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", pts.join(" "));
    line.setAttribute("class", "ind-spark-line");
    const lastIdx = values.length - 1 - [...values].reverse().findIndex((v) => v != null);
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", x(lastIdx).toFixed(1)); dot.setAttribute("cy", y(values[lastIdx]).toFixed(1)); dot.setAttribute("r", "3");
    dot.setAttribute("class", "ind-spark-dot");
    svg.append(area, line, dot);
    return svg;
  }

  function sparkAxis(series, points) {
    const dates = series.dates.slice(-points);
    const row = el("div", "ind-axis");
    row.append(el("span", null, periodLabel(dates[0])), el("span", null, periodLabel(dates.at(-1))));
    return row;
  }

  // ── 카드 한 장: 값 + 변화 + 스파크라인 ───────────────────────
  // opts: { label, unit, series, regionName, points, compact }
  function seriesBlock({ label, unit, series, regionName, points, compact = false, name }) {
    const freq = series.freq;
    const n = points || (freq === "M" ? 36 : freq === "Q" ? 16 : freq === "H" ? 10 : 12);
    const box = el("div", compact ? "ind-block ind-compact" : "ind-block");
    const head = el("div", "ind-head");
    head.append(el("span", "ind-label", label));
    head.append(el("span", "ind-region", `${regionName} · ${periodLabel(series.dates.at(-1))}`));
    box.append(head);
    const valueRow = el("div", "ind-value-row");
    const value = el("span", "ind-value", fmt(series.values.at(-1), unit));
    const u = unitLabel(unit);
    if (u) value.append(el("small", "ind-unit", u));
    valueRow.append(value);
    const chips = el("span", "ind-chips");
    chips.append(changeChip(change(series, unit, 1), FREQ_LABEL[freq] || "전기"));
    if (freq !== "Y") chips.append(changeChip(change(series, unit, FREQ_STEPS_PER_YEAR[freq]), "전년동기"));
    valueRow.append(chips);
    box.append(valueRow);
    box.append(sparkline(series, { points: n, height: compact ? 28 : 56, name: name || label }));
    if (!compact) box.append(sparkAxis(series, n));
    return box;
  }

  // 두 항목의 비율(예: 월세 건수 / 전체 건수)을 새 계열로 만든다. 날짜가 같은 지점만 쓴다.
  function ratioSeries(num, den, scale = 100) {
    const byDate = new Map(den.dates.map((d, i) => [d, den.values[i]]));
    const dates = [], values = [];
    num.dates.forEach((d, i) => {
      const a = num.values[i], b = byDate.get(d);
      if (a != null && b) { dates.push(d); values.push((a / b) * scale); }
    });
    return { freq: num.freq, dates, values };
  }

  return { el, loadIndex, loadVariable, serverStatus, region, setRegion, onRegionChange, isSeoulGu, pick, fmt, change, changeChip,
           periodLabel, sparkline, sparkAxis, seriesBlock, ratioSeries, DEFAULT_REGION };
})();
