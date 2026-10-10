// Home 화면 (index.html #home): ① Overview(시장 코멘터리) ② 시도별 가격 상승률 지도 ③ 이달의 차트 ④ 주요 정책 동향
// factors.js 가 자료를 읽은 뒤 renderHome() 을 부른다. 차트·숫자 함수는 charts.js, 문장은 notes.js 에 있다.
// - data/korea_sido.json : 17개 시도 경계 SVG 경로 (scripts/build_korea_map.py, 통계청 SGIS 2018 경계)
// - data/policies.json   : 부동산 정책 페이지와 같은 정책 정리 자료

let koreaMap = null;
let policyData = null;

// 지도에 칠할 가격지수 (모두 한국부동산원 아파트 지수, 시도 17개)
const MAP_METRICS = [
  ["V002", "매매가격"],
  ["V026", "전세가격"],
  ["V001", "월세가격"],
];
const homeState = { mapVar: "V002", mapChange: "yoy" };

// ── ① Overview: 시장 코멘터리 (월세가격지수) + 동인별 코멘터리 목록 ──────
function renderFeature() {
  const box = document.querySelector("#home-feature");
  const m = metricsFor(RENT_INDEX, "sido").list[0];
  const v = variables.find((x) => x.id === RENT_INDEX);
  box.replaceChildren();
  if (!m || !v) return;
  const regions = regionsOf(m);
  const first = regions[0].r;
  const d = describe(v, m, first);
  const driver = drivers.find((x) => x.id === v.driver);

  box.append(metaLine(regions.map((x) => x.r).join(" · "), d.latest ? `${periodLabel(d.latest.period, true)} 기준` : null));
  box.append(el("h3", "feature-title", d.headline));
  const cols = el("div", "feature-cols");
  const text = el("div", "feature-text");
  const ul = el("ul", "bullets");
  ul.append(el("li", null, d.body[0]));
  for (const { r } of regions.slice(1)) {
    const l = latestOf(m, r);
    if (l) ul.append(el("li", null, `${r}는 ${fmtValue(l.value, m.unit)}로 ${changeName(m)} ${fmtChange(l.change, l.mode, m.unit)}입니다.`));
  }
  const pos = recentPosition(m, first);
  if (pos) ul.append(el("li", null, `${first}의 현재 수준은 ${pos}${pos.endsWith("최고") || pos.endsWith("최저") ? "치" : ""}입니다.`));
  text.append(ul);
  const by = el("p", "byline");
  by.append(document.createTextNode("by: DFMBA 자동 요약 | in: "));
  by.append(moreLink(`${NUMS[driver.no - 1]} ${driver.name}`, `#${driver.id}`));
  text.append(by);

  const chartCol = el("div", "feature-chart");
  const seg = el("div", "text-tabs");
  seg.setAttribute("role", "group");
  seg.setAttribute("aria-label", "차트 값");
  for (const [val, label] of [["level", "수준"], ["yoy", "전년동월 대비"], ["mom", "전월 대비"]]) {
    const b = el("button", null, label);
    b.type = "button";
    b.setAttribute("aria-pressed", String((state.rentChange || "level") === val));
    b.addEventListener("click", () => {
      state.rentChange = val;
      saveState();
      renderFeature();
    });
    seg.append(b);
  }
  const plot = el("div");
  chartCol.append(seg, plot);
  cols.append(text, chartCol);
  box.append(cols);
  const change = state.rentChange === "level" || !state.rentChange ? null : state.rentChange;
  drawMetric(plot, m, regions, { title: "아파트 월세통합가격지수", change, height: 300, source: sourceLine(v, m) });
}

// 동인 목록 (제목 = 대표 지표 헤드라인, 메타 = 동인 이름 | 기준시점)
function driverList(list) {
  const ul = el("ul", "side-list");
  for (const d of list) {
    const h = headlineMetric(HEADLINES[d.id]);
    const li = el("li");
    const a = el("a", "side-title");
    a.href = `#${d.id}`;
    const desc = h ? describe(h.v, h.m, h.region) : null;
    a.textContent = desc ? desc.headline : d.name;
    li.append(a, metaLine(`${NUMS[d.no - 1]} ${d.short}`, desc?.latest ? periodLabel(desc.latest.period, true) : null));
    ul.append(li);
  }
  return ul;
}

// ── ② 시도별 가격 상승률 지도 ───────────────────────────
// 색: 상승은 파랑, 하락은 빨강, 0 근처는 회색. 각 방향 4단계 (단계 폭은 그 달 최대 변화폭으로 정한다)
function divergingColors() {
  const cs = getComputedStyle(document.documentElement);
  const get = (n) => cs.getPropertyValue(n).trim();
  return { zero: get("--div-0"), pos: [1, 2, 3, 4].map((k) => get(`--div-p${k}`)), neg: [1, 2, 3, 4].map((k) => get(`--div-n${k}`)) };
}

function niceStep(x) {
  const mag = 10 ** Math.floor(Math.log10(x));
  return [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= x);
}

// 그 지표의 지역별 변화: 모든 시도에 값이 있는 마지막 확정 기간 기준
function mapValues(varId, change) {
  const m = metricsFor(varId, "sido").list.find((x) => x.scope === "sido");
  if (!m) return null;
  const end = provisionalIndex(m);
  const mode = yoyMode(m);
  const lag = change === "mom" ? 1 : YOY_LAG[m.freq];
  const regions = sample.regions.sido.filter((r) => m.series[r]);
  let i = end - 1;
  for (; i >= lag; i--) {
    if (regions.every((r) => m.series[r][i] != null && m.series[r][i - lag] != null)) break;
  }
  if (i < lag) return null;
  const values = {};
  for (const r of regions) {
    const now = m.series[r][i];
    const prev = m.series[r][i - lag];
    values[r] = mode === "pct" ? (now / prev - 1) * 100 : now - prev;
  }
  return { m, period: m.periods[i], values, mode };
}

function renderMap() {
  const box = document.querySelector("#home-map");
  box.replaceChildren();
  if (!koreaMap) {
    box.append(el("p", "chart-empty", "지도 경계 자료를 불러오지 못했습니다 (data/korea_sido.json)"));
    return;
  }
  const res = mapValues(homeState.mapVar, homeState.mapChange);
  if (!res) {
    box.append(el("p", "chart-empty", "이 지표는 시도별 자료가 없습니다"));
    return;
  }
  const { m, period, values, mode } = res;
  const changeLabel = homeState.mapChange === "mom" ? "전월 대비" : changeName(m);
  const unit = mode === "pct" ? "%" : "%p";
  const fmt = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}${unit}`;

  // 단계 나누기: 단계 폭(step)의 1/10 미만은 0 근처로 보고 회색, 나머지는 방향마다 4단계
  const maxAbs = Math.max(...Object.values(values).map(Math.abs)) || 1;
  const step = niceStep(maxAbs / 4);
  const zeroBand = step / 10;
  const colors = divergingColors();
  const colorOf = (v) => {
    if (Math.abs(v) < zeroBand) return colors.zero;
    const k = Math.min(3, Math.floor(Math.abs(v) / step));
    return v > 0 ? colors.pos[k] : colors.neg[k];
  };
  const metaName = MAP_METRICS.find(([id]) => id === homeState.mapVar)[1];

  const layout = el("div", "map-layout");
  const mapCol = el("div", "map-col");
  const caption = el("p", "map-caption");
  caption.append(el("strong", null, `아파트 ${metaName}지수 ${changeLabel} 상승률`), el("span", null, ` · ${periodLabel(period, true)} 기준`));
  mapCol.append(caption);

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", koreaMap.viewBox);
  svg.setAttribute("class", "korea-map");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `시도별 ${metaName}지수 ${changeLabel} 상승률 지도 (값은 옆 순위표에 있음)`);
  const tip = el("div", "chart-tip map-tip");
  tip.hidden = true;
  const shapes = {};
  for (const reg of koreaMap.regions) {
    const v = values[reg.name];
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", reg.d);
    path.setAttribute("fill", v == null ? "transparent" : colorOf(v));
    path.setAttribute("class", "map-region");
    path.dataset.region = reg.name;
    svg.append(path);
    shapes[reg.name] = path;
  }
  // 큰 도만 지도 위에 이름을 적는다 (작은 광역시는 겹치므로 순위표와 말풍선으로 읽는다)
  const LABELED = ["경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"];
  for (const reg of koreaMap.regions.filter((r) => LABELED.includes(r.name))) {
    const t = document.createElementNS(svgNS, "text");
    t.setAttribute("x", reg.cx);
    t.setAttribute("y", reg.cy);
    t.setAttribute("class", "map-label");
    t.textContent = reg.name;
    svg.append(t);
  }
  const plotBox = el("div", "map-plot");
  plotBox.append(svg, tip);
  mapCol.append(plotBox);

  // 범례: 단계별 색과 범위
  const legend = el("div", "map-legend");
  const swatch = (color, text) => {
    const s = el("span", "legend-item");
    const c = el("span", "legend-swatch");
    c.style.background = color;
    s.append(c, document.createTextNode(text));
    return s;
  };
  // 범위 글자: 첫 단계는 0 근처 구간(±zeroBand) 바깥부터
  const lo = (k) => fmtAxis(k === 0 ? zeroBand : step * k);
  for (let k = 3; k >= 0; k--) legend.append(swatch(colors.neg[k], k === 3 ? `≤ −${fmtAxis(step * 3)}` : `−${lo(k)}~${fmtAxis(step * (k + 1))}`));
  legend.append(swatch(colors.zero, `±${fmtAxis(zeroBand)} 미만`));
  for (let k = 0; k <= 3; k++) legend.append(swatch(colors.pos[k], k === 3 ? `≥ +${fmtAxis(step * 3)}` : `+${lo(k)}~${fmtAxis(step * (k + 1))}`));
  mapCol.append(legend);
  mapCol.append(el("p", "fig-source", `단위 ${unit}. 상승 파랑 · 하락 빨강. 자료: 한국부동산원 R-ONE, DFMBA 전처리본(1차_결측보완). 지도: ${koreaMap.source}`));

  // 순위표: 17개 시도 막대 (0 기준 좌우)
  const rankCol = el("div", "rank-col");
  rankCol.append(el("p", "map-caption", "시도 순위"));
  const list = el("ol", "rank-list");
  const sorted = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const rows = {};
  for (const [r, v] of sorted) {
    const li = el("li", "rank-row");
    li.tabIndex = 0;
    li.dataset.region = r;
    li.append(el("span", "rank-name", r));
    const bar = el("span", "rank-bar");
    const fill = el("span", "rank-fill");
    fill.style.background = colorOf(v);
    fill.style.width = `${(Math.abs(v) / maxAbs) * 50}%`;
    fill.style[v >= 0 ? "left" : "right"] = "50%";
    bar.append(fill);
    li.append(bar, el("span", "rank-value", fmt(v)));
    list.append(li);
    rows[r] = li;
  }
  rankCol.append(list);
  layout.append(mapCol, rankCol);
  box.append(layout);

  // 지도·순위표 서로 강조 + 말풍선
  const highlight = (r, on, evt) => {
    shapes[r]?.classList.toggle("is-on", on);
    rows[r]?.classList.toggle("is-on", on);
    if (!on) {
      tip.hidden = true;
      return;
    }
    tip.replaceChildren(el("div", "chart-tip-head", `${r} · ${periodLabel(period, true)}`));
    const row = el("div", "chart-tip-row");
    row.append(el("strong", null, fmt(values[r])), el("span", null, `${metaName}지수 ${changeLabel}`));
    tip.append(row);
    tip.hidden = false;
    const pb = plotBox.getBoundingClientRect();
    let x, y;
    if (evt?.clientX != null && evt.type.startsWith("pointer")) {
      x = evt.clientX - pb.left + 12;
      y = evt.clientY - pb.top + 12;
    } else {
      const sb = shapes[r].getBoundingClientRect();
      x = sb.right - pb.left + 6;
      y = sb.top - pb.top;
    }
    tip.style.left = `${Math.min(Math.max(0, x), pb.width - tip.offsetWidth)}px`;
    tip.style.top = `${Math.max(0, y)}px`;
  };
  for (const [r, path] of Object.entries(shapes)) {
    if (values[r] == null) continue;
    path.addEventListener("pointermove", (e) => highlight(r, true, e));
    path.addEventListener("pointerleave", () => highlight(r, false));
  }
  for (const [r, li] of Object.entries(rows)) {
    li.addEventListener("pointerenter", (e) => highlight(r, true, e));
    li.addEventListener("pointerleave", () => highlight(r, false));
    li.addEventListener("focus", () => highlight(r, true));
    li.addEventListener("blur", () => highlight(r, false));
  }
}

function mapTools() {
  const box = document.querySelector("#home-map-tools");
  box.replaceChildren();
  const groups = [
    ["mapVar", "지표", MAP_METRICS.map(([id, name]) => [id, name])],
    ["mapChange", "기준", [["yoy", "전년동월 대비"], ["mom", "전월 대비"]]],
  ];
  for (const [key, label, options] of groups) {
    const g = el("div", "seg-group");
    g.append(el("span", "seg-label", label));
    const seg = el("div", "seg");
    for (const [value, text] of options) {
      const b = el("button", null, text);
      b.type = "button";
      b.setAttribute("aria-pressed", String(homeState[key] === value));
      b.addEventListener("click", () => {
        homeState[key] = value;
        mapTools();
        renderMap();
      });
      seg.append(b);
    }
    g.append(seg);
    box.append(g);
  }
}

// ── ③ 이달의 차트 + 최근 기준시점 지표 ─────────────────────
// 기간이 끝나는 달의 순번 (월·분기·반기·연을 한 줄로 비교하려고)
function periodEndMonth(p) {
  const { perYear, ord } = periodOrdinal(p);
  const year = Math.floor(ord / perYear);
  const k = ord % perYear;
  return year * 12 + (k + 1) * (12 / perYear) - 1;
}

function renderReleases() {
  const ul = document.querySelector("#home-releases");
  ul.replaceChildren();
  const rows = [];
  for (const v of variables) {
    const h = headlineMetric(v.id);
    if (!h) continue;
    const l = latestOf(h.m, h.region);
    if (!l) continue;
    rows.push({ v, h, l, key: periodEndMonth(l.period) });
  }
  rows.sort((a, b) => b.key - a.key);
  for (const { v, h, l } of rows.slice(0, 6)) {
    const li = el("li");
    const a = el("a", "side-title", `${v.name.replace(/_/g, " ")} (${periodLabel(l.period)})`);
    a.href = `#${v.driver}`;
    const meta = el("p", "meta");
    meta.append(el("span", "src", (h.m.source || v.source || "").split(/\s*[\/|]\s*/)[0] || "출처 미기재"));
    meta.append(document.createTextNode(` | ${h.region} ${fmtValue(l.value, h.m.unit)}`));
    li.append(a, meta);
    ul.append(li);
  }
}

// 이달의 차트: 금리 3종 (모두 연%라 한 축에 그릴 수 있다)
function renderGraphOfMonth() {
  const box = document.querySelector("#home-gow");
  const note = document.querySelector("#home-gow-note");
  const ids = [["V043", "기준금리"], ["V045", "국고채 3년"], ["V056", "주택담보대출(신규)"]];
  const ms = ids.map(([id]) => metricsFor(id, "sido").list[0]);
  if (ms.some((m) => !m)) return;
  const periods = [...new Set(ms.flatMap((m) => m.periods))].sort();
  const merged = { ...ms[0], periods, series: {}, provisional_from: null };
  ids.forEach(([, name], k) => {
    const m = ms[k];
    const s = m.series[Object.keys(m.series)[0]];
    merged.series[name] = periods.map((p) => s[m.periods.indexOf(p)] ?? null);
  });
  drawMetric(box, merged, ids.map(([, n], k) => ({ r: n, slot: k })), {
    title: "금리: 기준금리 · 국고채 3년 · 주택담보대출",
    subtitle: "연% · 월 · 전국",
    height: 300,
    source: "자료: 한국은행, DFMBA 전처리본(1차_결측보완)",
  });
  const lasts = ids.map(([, n]) => latestOf(merged, n));
  const [, ktb, mort] = lasts;
  const parts = ids.map(([, n], k) => (lasts[k] ? `${n} ${fmtValue(lasts[k].value, "연%")}(${periodLabel(lasts[k].period)})` : null)).filter(Boolean);
  let text = `최신값은 ${parts.join(", ")}입니다.`;
  if (mort && ktb) {
    const k3 = merged.series["국고채 3년"][merged.periods.indexOf(mort.period)];
    if (k3 != null) text += ` 같은 달(${periodLabel(mort.period, true)}) 주택담보대출 금리와 국고채 3년의 차이는 ${fmtNumber(mort.value - k3, 2)}%p입니다.`;
  }
  note.textContent = text;
}

// ── ④ 주요 정책 동향 (부동산 정책 페이지의 정리 자료에서 최근 발표 순) ─────
function renderPolicies() {
  const box = document.querySelector("#home-policies");
  box.replaceChildren();
  const items = (policyData?.policies || []).slice().sort((a, b) => (a.published_at < b.published_at ? 1 : -1)).slice(0, 4);
  if (!items.length) {
    box.append(el("p", "chart-empty", "정책 자료를 불러오지 못했습니다 (data/policies.json)"));
    return;
  }
  for (const p of items) {
    const card = el("article", "policy-item");
    card.append(metaLine(p.agency, p.published_at, p.category));
    const h = el("h3");
    const a = el("a", null, p.title);
    a.href = "policies.html#briefs";
    h.append(a);
    card.append(h);
    if (p.summary) card.append(el("p", "policy-sum", p.summary));
    if (p.status) card.append(el("p", "byline", `상태: ${p.status}`));
    box.append(card);
  }
  document.querySelector("#home-policy-note").textContent = policyData.verified_at ? `공식 발표 원문 확인일 ${policyData.verified_at}. 전체 목록과 적용 조건은 부동산 정책 페이지에서 봅니다.` : "";
}

// ── Home 그리기 ──────────────────────────────────────
function renderHome() {
  renderFeature();
  document.querySelector("#home-recent").replaceChildren(...driverList(drivers).children);
  mapTools();
  renderMap();
  renderGraphOfMonth();
  renderReleases();
  renderPolicies();
}

// 지도 경계·정책 자료는 Home 에서만 쓰므로 따로 읽는다 (실패해도 나머지 화면은 그린다)
(async () => {
  const load = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  [koreaMap, policyData] = await Promise.all([load("data/korea_sido.json"), load("data/policies.json")]);
  if (sample && !homeView.hidden) {
    mapTools();
    renderMap();
    renderPolicies();
  }
})();
