// index.html 의 화면 전환과 '부동산 대시보드' (Overview + 6개 동인)
// - data/drivers.json      : 동인·변수 설명 (데이터사전 엑셀의 동인분류_가이드·Driver_Map·Variable_Master)
// - data/factor_sample.json: 실제 값 샘플 (DFMBA 전처리본, scripts/build_factor_sample.py 로 생성)
// 주소 끝의 #id 로 화면을 고른다: #home(기본), #overview, #demand, #supply, #finance, #rental, #trigger, #macro
// Home 화면은 home.js, 숫자 표시·차트는 charts.js, 설명 문장은 notes.js 에 있다.

const viewNav = document.querySelector("#view-nav");
const homeView = document.querySelector("#view-home");
const dashView = document.querySelector("#view-dash");

let drivers = [];
let variables = [];
let sample = null; // { regions, metrics, aliases, generated }

// 사용자가 고른 보기 설정 (브라우저에만 저장)
// sidoSlots: 비교할 시도 3칸. 색은 칸 번호를 따르므로 다른 시도를 빼도 남은 시도의 색은 그대로다
const state = { mode: "sido", range: "5", view: "level", rentChange: "yoy", sidoSlots: ["서울", "경기", "부산"], sidoNext: 0 };
try {
  Object.assign(state, JSON.parse(localStorage.getItem("factorView") || "{}"));
} catch (e) {}
function saveState() {
  try {
    localStorage.setItem("factorView", JSON.stringify(state));
  } catch (e) {}
}

// 태그·클래스·글자로 요소를 만든다 (글자는 textContent 로 넣어 HTML 로 해석되지 않게 한다)
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const NUMS = ["①", "②", "③", "④", "⑤", "⑥"];
const FREQ = { M: "월", Q: "분기", H: "반기", A: "연" };
const RANGE_YEARS = { 3: 3, 5: 5, all: Infinity };
const MAX_SIDO = 3; // 한 차트에 겹쳐 그리는 시도 수 (색약 구분 검증을 통과한 계열 색이 3개)

// 동인별 대표 지표 (변수 ID): 대시보드 Overview 의 동인별 코멘터리와 Home 목록에 쓴다
const HEADLINES = { demand: "V012", supply: "V023", finance: "V003", rental: "V005", trigger: "V037", macro: "V043" };
const RENT_INDEX = "V001"; // Home 시장 코멘터리: 월세가격지수

// ── 데이터 고르기 ─────────────────────────────────────
// 지역 단위(시도/서울 구)에 맞는 계열을 고른다. 없으면 다른 단위로 대신하고 그 사실을 알린다.
function metricsFor(varId, mode) {
  const id = sample.aliases?.[varId] || varId;
  const all = sample.metrics.filter((m) => m.var === id);
  const prefer = mode === "gu" ? ["gu", "seoul", "nation"] : ["sido", "nation"];
  const fallback = mode === "gu" ? ["sido"] : ["seoul", "gu"];
  let list = all.filter((m) => prefer.includes(m.scope));
  let substituted = false;
  if (!list.length) {
    list = all.filter((m) => fallback.includes(m.scope));
    substituted = list.length > 0;
  }
  const last = (m) => m.periods[m.periods.length - 1];
  list = [...list].sort((a, b) => (last(a) < last(b) ? 1 : last(a) > last(b) ? -1 : 0));
  return { list, substituted, alias: id !== varId ? id : null };
}

// 차트에 그릴 지역과 색 번호: 시도 계열이면 고른 시도(칸 순서), 그 밖에는 계열에 있는 지역 그대로
function regionsOf(m) {
  const keys = Object.keys(m.series);
  if (m.scope !== "sido") return keys.map((r, k) => ({ r, slot: k }));
  const picked = state.sidoSlots.map((r, slot) => ({ r, slot })).filter((x) => x.r && keys.includes(x.r));
  return picked.length ? picked : [{ r: keys[0], slot: 0 }];
}

// 기간 필터: 각 계열의 마지막 시점에서 N년 전까지
function sliceRange(metric, values) {
  const years = RANGE_YEARS[state.range];
  if (!Number.isFinite(years)) return { periods: metric.periods, values };
  const lastYear = +metric.periods[metric.periods.length - 1].slice(0, 4);
  const start = metric.periods.findIndex((p) => +p.slice(0, 4) > lastYear - years);
  return { periods: metric.periods.slice(start), values: values.map((v) => v.slice(start)) };
}

function metricTitle(m) {
  const unit = displayUnit(m.unit);
  return unit && !unit.includes("=") ? `${m.label} (${unit})` : m.label;
}

// 차트 눈금·말풍선에 쓰는 값 표기. change: 수준이 아니라 변화(전년동기 대비 등)를 그릴 때
function chartFormatter(m, mode, change) {
  return (val, axis) => {
    if (val == null) return "–";
    if (axis) {
      if (!change) return fmtAxis(scaleValue(val, m.unit));
      const suffix = mode === "pct" ? "%" : mode === "diff-pp" ? "%p" : "";
      return `${val > 0 ? "+" : ""}${fmtAxis(mode === "diff" ? scaleValue(val, m.unit) : val)}${suffix}`;
    }
    if (change) return fmtChange(val, mode, m.unit).replace("±", "");
    return fmtValue(val, m.unit);
  };
}

// 설정을 바꾼 뒤 지금 화면을 다시 그린다 (보던 위치는 지킨다)
function rerender() {
  const y = window.scrollY;
  showView();
  window.scrollTo(0, y);
}

// ── 보기 설정 줄 ─────────────────────────────────────
// keys 로 필요한 묶음만 고른다 (동인 화면: 지역·기간·값, Overview: 기간)
function filterBar(keys = ["mode", "range", "view"]) {
  const bar = el("div", "filter-bar");
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "보기 설정");
  const groups = [
    ["mode", "지역", [["sido", "시도"], ["gu", `서울 구 (${sample.regions.gu.join("·")})`]]],
    ["range", "기간", [["3", "3년"], ["5", "5년"], ["all", "전체"]]],
    ["view", "값", [["level", "수준"], ["yoy", "전년동기 대비"]]],
  ];
  for (const [key, label, options] of groups.filter((g) => keys.includes(g[0]))) {
    const g = el("div", "seg-group");
    g.append(el("span", "seg-label", label));
    const seg = el("div", "seg");
    for (const [value, text] of options) {
      const b = el("button", null, text);
      b.type = "button";
      b.setAttribute("aria-pressed", String(state[key] === value));
      b.addEventListener("click", () => {
        state[key] = value;
        saveState();
        rerender();
      });
      seg.append(b);
    }
    g.append(seg);
    bar.append(g);
  }
  if (keys.includes("mode") && state.mode === "sido") bar.append(sidoPicker());
  return bar;
}

// 17개 시도 토글 (가로 스크롤). 최대 3개, 넘치면 가장 먼저 고른 칸을 바꾼다
function sidoPicker() {
  const wrap = el("div", "sido-picker");
  const head = el("p", "sido-hint", `비교할 시도 (최대 ${MAX_SIDO}개)`);
  wrap.append(head);
  const row = el("div", "chip-row");
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", "비교할 시도");
  const colors = seriesColors();
  for (const r of sample.regions.sido) {
    const slot = state.sidoSlots.indexOf(r);
    const b = el("button", "chip");
    b.type = "button";
    b.setAttribute("aria-pressed", String(slot >= 0));
    const dot = el("span", "chip-dot");
    if (slot >= 0) dot.style.background = colors[slot];
    b.append(dot, document.createTextNode(r));
    b.addEventListener("click", () => {
      const i = state.sidoSlots.indexOf(r);
      if (i >= 0) {
        if (state.sidoSlots.filter(Boolean).length === 1) return; // 하나는 남긴다
        state.sidoSlots[i] = null;
        state.sidoNext = i;
      } else {
        const empty = state.sidoSlots.indexOf(null);
        const target = empty >= 0 ? empty : state.sidoNext;
        state.sidoSlots[target] = r;
        state.sidoNext = (target + 1) % MAX_SIDO;
      }
      saveState();
      rerender();
    });
    row.append(b);
  }
  wrap.append(row);
  return wrap;
}

// 지역별 최신값 표: 변수마다 고른 지역의 최신값과 전년동기 대비
function summaryTable(list) {
  const regions = state.mode === "gu" ? sample.regions.gu : state.sidoSlots.filter(Boolean);
  const wrap = el("div", "summary-wrap");
  const table = el("table", "summary");
  table.append(el("caption", null, "최신값 (괄호: 전년동기 대비)"));
  const thead = el("thead");
  const hr = el("tr");
  hr.append(el("th", null, "변수"), el("th", null, "기준시점"));
  for (const r of regions) hr.append(el("th", "num", r));
  thead.append(hr);
  table.append(thead);
  const tbody = el("tbody");
  for (const v of list) {
    const { list: ms, substituted } = metricsFor(v.id, state.mode);
    const tr = el("tr");
    const name = el("th");
    name.scope = "row";
    const a = el("a", null, v.name);
    a.href = `#${v.driver}`;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      document.getElementById(`card-${v.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    name.append(a);
    tr.append(name);
    const m = ms[0];
    if (!m) {
      tr.append(el("td", "muted", "–"));
      for (const _ of regions) tr.append(el("td", "num muted", "–"));
      tbody.append(tr);
      continue;
    }
    const keys = Object.keys(m.series);
    const first = latestOf(m, keys.includes(regions[0]) ? regions[0] : keys[0]);
    tr.append(el("td", "muted", first ? periodLabel(first.period, true) : "–"));
    if (substituted) {
      const td = el("td", "num span muted", state.mode === "gu" ? "구 단위 자료 없음 — 차트에 시도 기준 표시" : "시도 단위 자료 없음 — 차트에 서울 구 기준 표시");
      td.colSpan = regions.length;
      tr.append(td);
    } else if (keys.length === 1) {
      // 전국 공통값(금리 등)이나 서울 단일값은 지역 칸을 합쳐 한 번만 쓴다
      const l = latestOf(m, keys[0]);
      const td = el("td", "num span");
      td.colSpan = regions.length;
      td.append(el("span", "scope-tag", keys[0] === "전국" ? "전국 공통" : m.scope === "nation" ? `${keys[0]} · 지역 공통` : `${keys[0]} 기준`));
      td.append(el("span", "v", l ? fmtValue(l.value, m.unit) : "–"));
      if (l?.change != null) td.append(el("span", "chg", ` (${fmtChange(l.change, l.mode, m.unit)})`));
      tr.append(td);
    } else {
      for (const r of regions) {
        const td = el("td", "num");
        const l = keys.includes(r) ? latestOf(m, r) : null;
        td.append(el("span", "v", l ? fmtValue(l.value, m.unit) : "–"));
        if (l?.change != null) td.append(el("span", "chg", ` (${fmtChange(l.change, l.mode, m.unit)})`));
        tr.append(td);
      }
    }
    tbody.append(tr);
  }
  table.append(tbody);
  wrap.append(table);
  return wrap;
}

// ── 공용 조각 ─────────────────────────────────────────
// 메타 줄: '서울 · 경기 · 부산 | 2026년 8월'
function metaLine(...parts) {
  return el("p", "meta", parts.filter(Boolean).join(" | "));
}

// '자세히 »' 같은 파란 링크
function moreLink(text, href) {
  const a = el("a", "more", text);
  a.href = href;
  return a;
}

// 접었다 펴는 설명 상자
function foldBox(summary, ...children) {
  const d = el("details", "fold");
  d.append(el("summary", null, summary), ...children);
  return d;
}

// 변수 하나의 대표 계열과 지역 (Overview·Home 은 시도 기준, 서울 우선)
function headlineMetric(varId) {
  const m = metricsFor(varId, "sido").list[0];
  if (!m) return null;
  const region = m.series["서울"] ? "서울" : Object.keys(m.series)[0];
  return { m, region, v: variables.find((x) => x.id === varId) };
}

// 차트 부제: 단위 · 주기 (변화를 그리면 변화 종류)
function subtitleOf(m, change) {
  const mode = yoyMode(m);
  const unit = displayUnit(m.unit);
  if (change) {
    const name = change === "mom" ? "전월 대비" : changeName(m);
    return `${name} ${mode === "pct" ? "증감률(%)" : mode === "diff-pp" ? "차이(%p)" : "증감"} · ${FREQ[m.freq]}`;
  }
  return `${unit || "지수"} · ${FREQ[m.freq]}`;
}

// 축 위 단위 표기
function unitMark(m, change) {
  if (change) return yoyMode(m) === "pct" ? "%" : yoyMode(m) === "diff-pp" ? "%p" : displayUnit(m.unit);
  const u = displayUnit(m.unit);
  return u.includes("=") ? "" : u.replace("연%", "%");
}

// 계열 → 리서치 차트. regions: [{r, slot}] (slot = 색 번호). change: null(수준) | "yoy" | "mom"
function drawMetric(box, m, regions, opts = {}) {
  const colors = seriesColors();
  const mode = yoyMode(m);
  const lag = opts.change === "mom" ? 1 : YOY_LAG[m.freq];
  const raw = regions.map(({ r }) => m.series[r]);
  const shown = opts.change ? raw.map((s) => yoySeries(s, lag, mode)) : raw;
  const { periods, values } = sliceRange(m, shown);
  figure(box, {
    title: opts.title || metricTitle(m),
    subtitle: opts.subtitle || subtitleOf(m, opts.change),
    unitLabel: unitMark(m, opts.change),
    source: opts.source,
    periods,
    provisionalAt: provisionalIndex(m, periods),
    series: regions.map(({ r, slot }, k) => ({ name: r, values: values[k], color: colors[slot % colors.length] })),
    valueFmt: chartFormatter(m, mode, !!opts.change),
    zeroLine: !!opts.change,
    height: opts.height ?? 240,
    label: `${m.label} ${regions.map((x) => x.r).join("·")} 추이`,
  });
}

// 대시보드 하위 탭 줄 (Overview + 6개 동인)
function dashNav(current) {
  const sub = el("nav", "subnav");
  sub.setAttribute("aria-label", "부동산 대시보드");
  sub.append(el("span", "subnav-label", "부동산 대시보드"));
  const items = [["overview", "Overview", "Overview"], ...drivers.map((d) => [d.id, `${NUMS[d.no - 1]} ${d.short}`, d.name])];
  for (const [id, text, title] of items) {
    const a = el("a", null, text);
    a.href = `#${id}`;
    a.title = title;
    if (id === current) a.setAttribute("aria-current", "page");
    sub.append(a);
  }
  return sub;
}

// ── 동인 화면: 변수 카드 (메타 → 헤드라인 → 차트, 해설은 접어 둔다) ──────
function variableCard(v) {
  const card = el("article", "var-card");
  card.id = `card-${v.id}`;
  const { list, substituted, alias } = metricsFor(v.id, state.mode);

  const meta = el("p", "meta");
  meta.textContent = [v.id, v.name.replace(/_/g, " "), v.sign ? `예상 부호 ${v.sign}` : null, v.lead ? `선행 ${v.lead}` : null].filter(Boolean).join(" | ");
  const headline = el("h3", "card-headline");
  card.append(meta, headline);

  if (!list.length) {
    headline.textContent = v.name;
    card.append(el("p", "chart-empty", "샘플 데이터에 이 변수의 계열이 없습니다."));
    card.append(foldBox("해설·출처", el("p", "card-prose", variableProse(v)), metaList(v, null)));
    return card;
  }

  // 같은 변수 안의 여러 열(예: 월세·전세·전체 건수)은 글자 탭으로 고른다
  let active = 0;
  const tabs = el("div", "metric-tabs");
  if (list.length > 1) {
    list.forEach((m, k) => {
      const b = el("button", null, metricTitle(m).replace(/^(국토부실거래|부동산원|주민등록인구|경제활동인구조사|임대주택공급|소비자동향조사|주택건설)\s*/, ""));
      b.type = "button";
      b.title = metricTitle(m);
      b.setAttribute("aria-pressed", String(k === 0));
      b.addEventListener("click", () => {
        active = k;
        tabs.querySelectorAll("button").forEach((x, j) => x.setAttribute("aria-pressed", String(j === k)));
        draw();
      });
      tabs.append(b);
    });
    card.append(tabs);
  }
  const chartBox = el("div", "chart-box");
  const prose = el("div", "card-prose");
  const metaBox = el("div");
  card.append(chartBox, foldBox("해설·출처", prose, metaBox));

  function draw() {
    const m = list[active];
    const regions = regionsOf(m);
    const d = describe(v, m, regions[0].r);
    headline.textContent = d.headline;
    drawMetric(chartBox, m, regions, { change: state.view === "yoy" ? "yoy" : null, source: sourceLine(v, m) });

    prose.replaceChildren();
    const p1 = el("p", null, d.body.join(" "));
    const others = regions.slice(1).map(({ r }) => {
      const l = latestOf(m, r);
      return l ? `${r} ${fmtValue(l.value, m.unit)}${l.change != null ? `(${fmtChange(l.change, l.mode, m.unit)})` : ""}` : null;
    }).filter(Boolean);
    if (others.length) p1.textContent += ` 같은 시점 ${others.join(", ")}입니다.`;
    prose.append(p1, el("p", "muted", variableProse(v)));
    const notes = [];
    if (alias) notes.push(`${alias}와 같은 원표(R-ONE)라 ${alias} 계열을 보여줍니다.`);
    if (substituted) notes.push(state.mode === "gu" ? "서울 구 단위 자료가 없어 시도 기준으로 보여줍니다." : "시도 단위 자료가 없어 서울 구 기준으로 보여줍니다.");
    if (m.provisional_from) notes.push(`최근 3개월(${periodLabel(m.provisional_from)}~)은 신고기한(계약 후 30일)·해제 시차로 아직 바뀌는 잠정값이라 점선으로 표시하고, 문장의 최신값은 확정 월 기준입니다.`);
    for (const n of notes) prose.append(el("p", "note", n));
    metaBox.replaceChildren(metaList(v, m));
  }
  card._draw = draw;
  return card;
}

// 출처·처리 방법 목록: 데이터사전 정보 + 전처리본의 처리 방법
function metaList(v, m) {
  const dl = el("dl", "var-meta");
  for (const [k, val] of [
    ["출처", m?.source || v.source],
    ["지역 범위", v.region],
    ["발표 시점", m?.release || v.release],
    ["전처리", m?.method],
    ["보완 셀", m?.filled ? `${m.filled.toLocaleString("ko-KR")}개 (패널 전체 기준)` : null],
    ["권장 가공", v.transform],
    ["원자료 열", m?.column],
  ]) {
    if (!val) continue;
    dl.append(el("dt", null, k), el("dd", null, val));
  }
  return dl;
}

// 동인 핵심 포인트: 최근 3년 최고·최저인 지표를 먼저, 나머지는 사전 순서대로 최대 5개
function keyPoints(list) {
  const items = [];
  for (const v of list) {
    const m = metricsFor(v.id, state.mode).list[0];
    if (!m) continue;
    const region = regionsOf(m)[0].r;
    const d = describe(v, m, region);
    if (!d.latest) continue;
    const pos = recentPosition(m, region);
    items.push({ text: d.headline, rank: pos === "최근 3년 최고" || pos === "최근 3년 최저" ? 0 : 1, id: v.id });
  }
  return items.sort((a, b) => a.rank - b.rank).slice(0, 5);
}

// 동인 화면: 차트가 먼저, 개요·핵심 포인트·지표 표는 접어 둔다
function renderFactor(driver) {
  const list = variables.filter((v) => v.driver === driver.id);
  dashView.replaceChildren();
  const wrap = el("div", "container");
  wrap.append(dashNav(driver.id));

  const head = el("div", "factor-head");
  head.append(el("h2", "note-title", `${NUMS[driver.no - 1]} ${driver.name}`));
  head.append(el("p", "note-dek", driver.question));
  wrap.append(head);

  // 개요·핵심 포인트 (접힘)
  const about = el("div", "fold-body");
  about.append(el("p", null, `${driver.description}. 데이터사전에서 이 동인은 '${driver.position}'으로 분류되며, 주요 하위영역은 ${driver.subareas.join(", ")}입니다. 분류 원칙: ${driver.principle}.`));
  about.append(el("h3", "note-sub", "핵심 포인트"));
  const ul = el("ul", "bullets");
  for (const k of keyPoints(list)) {
    const li = el("li");
    const a = el("a", null, k.text);
    a.href = `#${driver.id}`;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      document.getElementById(`card-${k.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    li.append(a);
    ul.append(li);
  }
  about.append(ul, el("p", "byline", "최근 3년 최고·최저인 지표를 먼저 보여줍니다 (첫 번째로 고른 지역 기준)"));
  const folds = el("div", "fold-row");
  folds.append(foldBox(`동인 개요·핵심 포인트 (변수 ${list.length}개)`, about));
  folds.append(foldBox("지역별 최신값 표", summaryTable(list)));
  wrap.append(folds);

  wrap.append(filterBar());

  const grid = el("div", "var-grid");
  const cards = list.map(variableCard);
  grid.append(...cards);
  wrap.append(grid);
  wrap.append(el("p", "data-note", `자료: ${sample._source}. 생성 ${sample.generated.split("|")[0].trim()}. 전처리본의 보완값이 포함되어 있으며 각 차트의 '해설·출처'에서 방법을 확인할 수 있습니다. 해설 문장은 수치에서 자동으로 만들며, 방향 해석은 데이터사전의 예상 부호만 근거로 합니다.`));
  dashView.append(wrap);

  // 너비가 정해진 뒤에 그린다
  for (const c of cards) c._draw?.();
}

// ── 대시보드 Overview: 동인별 코멘터리 (헤드라인 + 차트 + 짧은 설명) ──────
function renderDashOverview() {
  dashView.replaceChildren();
  const wrap = el("div", "container");
  wrap.append(dashNav("overview"));
  const head = el("div", "sec-head");
  head.append(el("h2", "sec-title", "동인별 코멘터리"));
  head.append(el("span", "sec-sub", "동인마다 대표 지표 하나 · 서울 기준"));
  const tools = el("div", "sec-tools");
  tools.append(filterBar(["range"]));
  head.append(tools);
  wrap.append(head);

  const grid = el("div", "ov-grid");
  const toDraw = [];
  for (const d of drivers) {
    const h = headlineMetric(HEADLINES[d.id]);
    const item = el("article", "ov-item");
    const desc = h ? describe(h.v, h.m, h.region) : null;
    item.append(metaLine(`${NUMS[d.no - 1]} ${d.name}`, desc?.latest ? periodLabel(desc.latest.period, true) : null));
    const t = el("a", "ov-title", desc ? desc.headline : d.name);
    t.href = `#${d.id}`;
    const h3 = el("h3");
    h3.append(t);
    item.append(h3);
    const plot = el("div", "chart-box");
    item.append(plot);
    if (desc) item.append(el("p", "ov-body", desc.body.join(" ")));
    item.append(el("p", "ov-q", d.question));
    const by = el("p", "byline");
    by.append(moreLink(`${NUMS[d.no - 1]} ${d.short} 전체 지표 »`, `#${d.id}`));
    item.append(by);
    grid.append(item);
    if (h) toDraw.push([plot, h]);
  }
  wrap.append(grid);
  wrap.append(el("p", "data-note", `자료: ${sample._source}. 해설 문장은 수치에서 자동으로 만들며, 방향 해석은 데이터사전의 예상 부호만 근거로 합니다.`));
  dashView.append(wrap);
  for (const [plot, h] of toDraw) {
    drawMetric(plot, h.m, [{ r: h.region, slot: 0 }], { title: shortTitle(h.m), height: 220, source: sourceLine(h.v, h.m) });
  }
}
const shortTitle = (m) => m.label.replace(/^(국토부실거래|주민등록인구|인구이동|주택건설|소비자동향조사|부동산원)\s*/, "").replace(/\((구지수연결|권역역산 학습용)\)$/, "");

// ── 화면 전환 ─────────────────────────────────────────
// 현재 주소(#id)에 맞는 화면을 보여준다
function showView() {
  const id = location.hash.slice(1) || "home";
  const driver = drivers.find((d) => d.id === id);
  const view = driver ? id : id === "overview" ? "overview" : "home";

  homeView.hidden = view !== "home";
  dashView.hidden = view === "home";
  if (sample) {
    if (driver) renderFactor(driver);
    else if (view === "overview") renderDashOverview();
    else renderHome();
  }

  // 머리 메뉴: Home 또는 '부동산 대시보드'(Overview·동인 화면)에 현재 위치 표시, 하위 메뉴는 해당 항목
  for (const a of viewNav.querySelectorAll("a[data-view], a[data-nav='dashboard']")) {
    const on = a.dataset.view ? a.dataset.view === view : view !== "home";
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

async function initFactors() {
  try {
    const [d, s] = await Promise.all(
      ["data/drivers.json", "data/factor_sample.json"].map(async (url) => {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
        return res.json();
      }),
    );
    drivers = d.drivers;
    variables = d.variables;
    sample = s;
    // 예전에 저장된 시도 선택이 지금 자료에 없으면 기본값으로
    state.sidoSlots = state.sidoSlots.slice(0, MAX_SIDO).map((r) => (sample.regions.sido.includes(r) ? r : null));
    while (state.sidoSlots.length < MAX_SIDO) state.sidoSlots.push(null);
    if (!state.sidoSlots.some(Boolean)) state.sidoSlots = ["서울", "경기", "부산"];
  } catch (err) {
    console.error(err);
    document.querySelector(".site-header").after(el("p", "factor-error", t("factor.loadError")));
    return;
  }
  showView();
  window.scrollTo(0, 0);
}

// 이미 같은 화면에 있을 때 로고를 눌러도 맨 위로 (같은 주소면 hashchange 가 일어나지 않는다)
document.querySelector(".site-header h1 a")?.addEventListener("click", () => {
  if (location.hash === "#home" || !location.hash) window.scrollTo(0, 0);
});

window.addEventListener("hashchange", () => {
  showView();
  window.scrollTo(0, 0);
});

// 창 너비가 바뀌거나 테마가 바뀌면 다시 그린다 (색·크기가 달라지므로)
let redrawTimer;
let lastWidth = window.innerWidth;
function redraw(themeChanged) {
  if (!themeChanged && window.innerWidth === lastWidth) return; // 모바일 주소창이 접힐 때(높이만 변함)는 건너뛴다
  lastWidth = window.innerWidth;
  clearTimeout(redrawTimer);
  redrawTimer = setTimeout(() => {
    if (!sample) return;
    // 동인 화면에서 폭만 바뀌면 차트만 다시 그린다 (펼쳐 둔 해설이 접히지 않게)
    const cards = dashView.hidden ? [] : [...dashView.querySelectorAll(".var-card")];
    if (!themeChanged && cards.length) cards.forEach((c) => c._draw?.());
    else rerender();
  }, 150);
}
window.addEventListener("resize", () => redraw(false));
new MutationObserver(() => redraw(true)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

initFactors();
