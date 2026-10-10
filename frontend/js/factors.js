// 탭 전환 (Overview ↔ 6개 동인) + Overview(코멘터리·이달의 차트·동인 브리프) + 동인 탭(리서치 노트) (index.html 전용)
// - data/drivers.json      : 동인·변수 설명 (데이터사전 엑셀의 동인분류_가이드·Driver_Map·Variable_Master)
// - data/factor_sample.json: 실제 값 샘플 (DFMBA 전처리본, scripts/build_factor_sample.py 로 생성)
// 주소 끝의 #id 로 탭을 고른다: #overview, #demand, #supply, #finance, #rental, #trigger, #macro
// 숫자 표시·차트 함수는 charts.js, 설명 문장은 notes.js 에 있다.

const viewNav = document.querySelector("#view-nav");
const overviewView = document.querySelector("#view-overview");
const factorView = document.querySelector("#view-factor");

let drivers = [];
let variables = [];
let sample = null; // { regions, metrics, aliases, generated }

// 사용자가 고른 보기 설정 (브라우저에만 저장)
const state = { mode: "sido", range: "5", view: "level", rentChange: "yoy" };
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

// 동인별 대표 지표 (변수 ID): Overview 의 동인별 코멘터리·동인 브리프 카드와 동인 탭의 다른 동인 목록에 쓴다
const HEADLINES = { demand: "V012", supply: "V023", finance: "V003", rental: "V005", trigger: "V037", macro: "V043" };
const RENT_INDEX = "V001"; // Overview 맨 위 시장 코멘터리: 월세가격지수

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

// 보기 설정 줄. keys 로 필요한 묶음만 고른다 (동인 탭: 지역·기간·값, Overview: 기간)
function filterBar(keys = ["mode", "range", "view"]) {
  const bar = el("div", "filter-bar");
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "보기 설정");
  const groups = [
    ["mode", "지역", [["sido", `시도 (${sample.regions.sido.join("·")})`], ["gu", `서울 구 (${sample.regions.gu.join("·")})`]]],
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
        const y = window.scrollY;
        showView();
        window.scrollTo(0, y); // 설정만 바꿀 때는 보던 위치를 지킨다
      });
      seg.append(b);
    }
    g.append(seg);
    bar.append(g);
  }
  return bar;
}

// 맨 위 요약표: 변수마다 지역별 최신값과 전년동기 대비 (차트를 보지 않아도 숫자를 읽을 수 있게)
function summaryTable(list) {
  const regions = state.mode === "gu" ? sample.regions.gu : sample.regions.sido;
  const wrap = el("div", "summary-wrap");
  const table = el("table", "summary");
  const cap = el("caption", null, "최신값 (괄호: 전년동기 대비)");
  table.append(cap);
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
    const lasts = Object.keys(m.series).map((r) => latestOf(m, r)).filter(Boolean);
    tr.append(el("td", "muted", lasts[0] ? periodLabel(lasts[0].period, true) : "–"));
    const keys = Object.keys(m.series);
    if (substituted) {
      const td = el("td", "num span muted", state.mode === "gu" ? "구 단위 자료 없음 — 카드에 시도 기준 표시" : "시도 단위 자료 없음 — 카드에 서울 구 기준 표시");
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

// 변수 하나의 대표 계열과 지역 (Overview 는 시도 기준, 서울 우선)
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

// 계열 → 리서치 차트. change: null(수준) | "yoy" | "mom"
function drawMetric(box, m, regions, opts = {}) {
  const colors = seriesColors();
  const mode = yoyMode(m);
  const lag = opts.change === "mom" ? 1 : YOY_LAG[m.freq];
  const raw = regions.map((r) => m.series[r]);
  const shown = opts.change ? raw.map((s) => yoySeries(s, lag, mode)) : raw;
  const { periods, values } = sliceRange(m, shown);
  figure(box, {
    title: opts.title || metricTitle(m),
    subtitle: opts.subtitle || subtitleOf(m, opts.change),
    unitLabel: unitMark(m, opts.change),
    source: opts.source,
    periods,
    provisionalAt: provisionalIndex(m, periods),
    series: regions.map((r, k) => ({ name: r, values: values[k], color: colors[k] })),
    valueFmt: chartFormatter(m, mode, !!opts.change),
    zeroLine: !!opts.change,
    height: opts.height ?? 240,
    label: `${m.label} ${regions.join("·")} 추이`,
  });
}

// ── 동인 탭: 변수 카드 (메타 → 헤드라인 → 차트 → 설명) ──────
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
    card.append(el("p", "card-prose", "샘플 데이터에 이 변수의 계열이 없습니다. " + variableProse(v)));
    card.append(metaList(v, null));
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
  card.append(chartBox, prose, metaBox);

  function draw() {
    const m = list[active];
    const regions = Object.keys(m.series);
    const d = describe(v, m, regions[0]);
    headline.textContent = d.headline;
    drawMetric(chartBox, m, regions, { change: state.view === "yoy" ? "yoy" : null, source: sourceLine(v, m) });

    prose.replaceChildren();
    const p1 = el("p", null, d.body.join(" "));
    // 다른 지역 최신값 한 줄
    const others = regions.slice(1).map((r) => {
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

// 카드 아래 접는 상세: 데이터사전 정보 + 전처리본의 처리 방법
function metaList(v, m) {
  const details = el("details", "var-more");
  details.append(el("summary", null, "출처·처리 방법"));
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
  details.append(dl);
  return details;
}

// 동인 핵심 포인트: 최근 3년 최고·최저인 지표를 먼저, 나머지는 사전 순서대로 최대 5개
function keyPoints(list) {
  const items = [];
  for (const v of list) {
    const m = metricsFor(v.id, state.mode).list[0];
    if (!m) continue;
    const region = Object.keys(m.series)[0];
    const d = describe(v, m, region);
    if (!d.latest) continue;
    const pos = recentPosition(m, region);
    items.push({ text: d.headline, rank: pos === "최근 3년 최고" || pos === "최근 3년 최저" ? 0 : 1, id: v.id });
  }
  return items.sort((a, b) => a.rank - b.rank).slice(0, 5);
}

// ── 동인 탭 화면 (리서치 노트 형식) ─────────────────────
function renderFactor(driver) {
  const list = variables.filter((v) => v.driver === driver.id);
  factorView.replaceChildren();
  const wrap = el("div", "container");

  // 주택시장 지표 > 동인 하위 탭 (현재 동인 표시)
  const sub = el("nav", "subnav");
  sub.setAttribute("aria-label", "주택시장 지표 동인");
  sub.append(el("span", "subnav-label", "주택시장 지표"));
  for (const d of drivers) {
    const a = el("a", null, `${NUMS[d.no - 1]} ${d.short}`);
    a.href = `#${d.id}`;
    a.title = d.name;
    if (d.id === driver.id) a.setAttribute("aria-current", "page");
    sub.append(a);
  }
  wrap.append(sub);

  const split = el("div", "split");
  const note = el("article", "note-main");
  note.append(metaLine(driver.position, `변수 ${list.length}개`, `자료 ${sample.generated.split("|")[0].trim()} 생성`));
  note.append(el("h2", "note-title", `${NUMS[driver.no - 1]} ${driver.name}`));
  note.append(el("p", "note-dek", driver.question));
  note.append(el("p", null, `${driver.description}. 데이터사전에서 이 동인은 '${driver.position}'으로 분류되며, 주요 하위영역은 ${driver.subareas.join(", ")}입니다. 분류 원칙: ${driver.principle}.`));
  note.append(el("h3", "note-sub", "핵심 포인트"));
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
  note.append(ul);
  note.append(el("p", "byline", `기준: ${state.mode === "gu" ? "서울 구 " + sample.regions.gu[0] : "시도 " + sample.regions.sido[0]} 첫 계열 · 최근 3년 최고·최저인 지표를 먼저 보여줍니다`));
  split.append(note);

  // 오른쪽: 다른 동인 코멘터리 목록
  const side = el("aside", "side");
  const sh = el("div", "sec-head");
  sh.append(el("h2", "sec-title sm", "다른 동인"));
  side.append(sh);
  side.append(driverList(drivers.filter((d) => d.id !== driver.id)));
  split.append(side);
  wrap.append(split);

  wrap.append(el("hr", "rule"));
  const th = el("div", "sec-head");
  th.append(el("h2", "sec-title", "주요 지표"));
  wrap.append(th);
  wrap.append(filterBar());
  wrap.append(summaryTable(list));

  wrap.append(el("hr", "rule"));
  const ch = el("div", "sec-head");
  ch.append(el("h2", "sec-title", "차트와 해설"));
  wrap.append(ch);
  const grid = el("div", "var-grid");
  const cards = list.map(variableCard);
  grid.append(...cards);
  wrap.append(grid);
  wrap.append(el("p", "data-note", `자료: ${sample._source}. 생성 ${sample.generated.split("|")[0].trim()}. 전처리본의 보완값이 포함되어 있으며 각 카드의 '출처·처리 방법'에서 방법을 확인할 수 있습니다. 해설 문장은 수치에서 자동으로 만들며, 방향 해석은 데이터사전의 예상 부호만 근거로 합니다.`));
  factorView.append(wrap);

  // 너비가 정해진 뒤에 그린다
  for (const c of cards) c._draw?.();
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

// ── Overview ─────────────────────────────────────────
// 맨 위 시장 코멘터리: 월세가격지수 (서울·경기·부산)
function renderFeature() {
  const box = document.querySelector("#ov-feature");
  const m = metricsFor(RENT_INDEX, "sido").list[0];
  const v = variables.find((x) => x.id === RENT_INDEX);
  box.replaceChildren();
  if (!m || !v) return;
  const regions = Object.keys(m.series);
  const d = describe(v, m, regions[0]);
  const driver = drivers.find((x) => x.id === v.driver);

  box.append(metaLine(regions.join(" · "), d.latest ? `${periodLabel(d.latest.period, true)} 기준` : null));
  box.append(el("h3", "feature-title", d.headline));
  const cols = el("div", "feature-cols");
  const text = el("div", "feature-text");
  const ul = el("ul", "bullets");
  ul.append(el("li", null, d.body[0]));
  for (const r of regions.slice(1)) {
    const l = latestOf(m, r);
    if (l) ul.append(el("li", null, `${r}는 ${fmtValue(l.value, m.unit)}로 ${changeName(m)} ${fmtChange(l.change, l.mode, m.unit)}입니다.`));
  }
  const pos = recentPosition(m, regions[0]);
  if (pos) ul.append(el("li", null, `${regions[0]}의 현재 수준은 ${pos}${pos.endsWith("최고") || pos.endsWith("최저") ? "치" : ""}입니다.`));
  if (v.role) ul.append(el("li", null, `데이터사전에서 이 지수의 역할은 '${v.role}'입니다.`));
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

// 기간이 끝나는 달의 순번 (월·분기·반기·연을 한 줄로 비교하려고)
function periodEndMonth(p) {
  const { perYear, ord } = periodOrdinal(p);
  const year = Math.floor(ord / perYear);
  const k = ord % perYear;
  return year * 12 + (k + 1) * (12 / perYear) - 1;
}

// 최근 기준시점 지표: 변수별 최신 기준시점이 늦은 순
function renderReleases() {
  const ul = document.querySelector("#ov-releases");
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
  for (const { v, h, l } of rows.slice(0, 7)) {
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
  const box = document.querySelector("#ov-gow");
  const note = document.querySelector("#ov-gow-note");
  const ids = [["V043", "기준금리"], ["V045", "국고채 3년"], ["V056", "주택담보대출(신규)"]];
  const ms = ids.map(([id]) => metricsFor(id, "sido").list[0]);
  if (ms.some((m) => !m)) return;
  // 기간을 합쳐 맞춘다
  const periods = [...new Set(ms.flatMap((m) => m.periods))].sort();
  const fake = { ...ms[0], periods, series: {} };
  ids.forEach(([, name], k) => {
    const m = ms[k];
    const s = m.series[Object.keys(m.series)[0]];
    fake.series[name] = periods.map((p) => s[m.periods.indexOf(p)] ?? null);
  });
  fake.provisional_from = null;
  drawMetric(box, fake, ids.map(([, n]) => n), {
    title: "금리: 기준금리 · 국고채 3년 · 주택담보대출",
    subtitle: "연% · 월 · 전국",
    height: 300,
    source: "자료: 한국은행, DFMBA 전처리본(1차_결측보완)",
  });
  const lasts = ids.map(([, n]) => latestOf(fake, n));
  const [base, ktb, mort] = lasts;
  const parts = ids.map(([, n], k) => (lasts[k] ? `${n} ${fmtValue(lasts[k].value, "연%")}(${periodLabel(lasts[k].period)})` : null)).filter(Boolean);
  let text = `최신값은 ${parts.join(", ")}입니다.`;
  if (mort && ktb) {
    const i = fake.periods.indexOf(mort.period);
    const k3 = fake.series["국고채 3년"][i];
    if (k3 != null) text += ` 같은 달(${periodLabel(mort.period, true)}) 주택담보대출 금리와 국고채 3년의 차이는 ${fmtNumber(mort.value - k3, 2)}%p입니다.`;
  }
  note.textContent = text;
}

// 동인 브리프 카드 (작은 차트 + 메타 + 헤드라인 + 한 줄 설명)
function renderBriefs() {
  const row = document.querySelector("#ov-briefs");
  row.replaceChildren();
  const cards = [];
  for (const d of drivers) {
    const h = headlineMetric(HEADLINES[d.id]);
    const card = el("article", "brief");
    const plot = el("div", "brief-plot");
    card.append(plot);
    const desc = h ? describe(h.v, h.m, h.region) : null;
    card.append(metaLine(`${NUMS[d.no - 1]} ${d.short}`, desc?.latest ? periodLabel(desc.latest.period, true) : null));
    const t = el("a", "brief-title", desc ? desc.headline : d.name);
    t.href = `#${d.id}`;
    card.append(el("h3", null), el("p", "brief-dek", d.question));
    card.querySelector("h3").append(t);
    const by = el("p", "byline");
    by.append(document.createTextNode("in: "), moreLink(`${d.name} »`, `#${d.id}`));
    card.append(by);
    row.append(card);
    cards.push([plot, h]);
  }
  for (const [plot, h] of cards) {
    if (h) drawMetric(plot, h.m, [h.region], { title: shortTitle(h.m), height: 200, source: sourceLine(h.v, h.m) });
  }
}
const shortTitle = (m) => m.label.replace(/^(국토부실거래|주민등록인구|인구이동|주택건설|소비자동향조사|부동산원)\s*/, "").replace(/\((구지수연결|권역역산 학습용)\)$/, "");

function renderOverview() {
  document.querySelector("#ov-range").replaceChildren(filterBar(["range"]));
  renderFeature();
  document.querySelector("#ov-recent").replaceChildren(...driverList(drivers).children);
  renderReleases();
  renderGraphOfMonth();
  renderBriefs();
}

// 동인 브리프 좌우 넘기기
for (const b of document.querySelectorAll("[data-scroll]")) {
  b.addEventListener("click", () => {
    const row = document.querySelector("#ov-briefs");
    const card = row.querySelector(".brief");
    row.scrollBy({ left: (card ? card.offsetWidth + 24 : 300) * (b.dataset.scroll === "next" ? 1 : -1), behavior: "smooth" });
  });
}

// ── 화면 전환 ─────────────────────────────────────────
// 현재 주소(#id)에 맞는 화면을 보여준다
function showView() {
  const id = location.hash.slice(1) || "overview";
  const driver = drivers.find((d) => d.id === id);
  const view = driver ? id : "overview";

  overviewView.hidden = view !== "overview";
  factorView.hidden = view === "overview";
  if (driver && sample) renderFactor(driver);
  if (!driver && sample) renderOverview();

  // 머리 메뉴: Overview 또는 '주택시장 지표'(동인 화면일 때)에 현재 위치 표시, 하위 메뉴는 해당 동인
  for (const a of viewNav.querySelectorAll("a[data-view], a[data-nav='indicators']")) {
    const on = a.dataset.view ? a.dataset.view === view : !!driver;
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
  } catch (err) {
    console.error(err);
    document.querySelector(".site-header").after(el("p", "factor-error", t("factor.loadError")));
    return;
  }

  showView();
  window.scrollTo(0, 0);
}

document.querySelector(".site-header h1 a")?.addEventListener("click", () => {
  if (location.hash === "#overview") window.scrollTo(0, 0);
});

window.addEventListener("hashchange", () => {
  showView();
  window.scrollTo(0, 0);
});

// 창 너비가 바뀌거나 테마가 바뀌면 차트를 다시 그린다 (색·크기가 달라지므로)
let redrawTimer;
function redraw() {
  clearTimeout(redrawTimer);
  redrawTimer = setTimeout(() => {
    if (!sample) return;
    if (!factorView.hidden) factorView.querySelectorAll(".var-card").forEach((c) => c._draw?.());
    else renderOverview();
  }, 150);
}
window.addEventListener("resize", redraw);
new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

initFactors();
