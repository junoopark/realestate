// 탭 전환 (Overview ↔ 6개 동인) + 동인 탭 화면 + Overview 요약 타일 (index.html 전용)
// - data/drivers.json      : 동인·변수 설명 (데이터사전 엑셀의 동인분류_가이드·Driver_Map·Variable_Master)
// - data/factor_sample.json: 실제 값 샘플 (DFMBA 전처리본, scripts/build_factor_sample.py 로 생성)
// 주소 끝의 #id 로 탭을 고른다: #overview, #demand, #supply, #finance, #rental, #trigger, #macro
// 숫자 표시·차트 함수는 charts.js 에 있다.

const viewNav = document.querySelector("#view-nav");
const overviewView = document.querySelector("#view-overview");
const factorView = document.querySelector("#view-factor");

let drivers = [];
let variables = [];
let sample = null; // { regions, metrics, aliases, generated }

// 사용자가 고른 보기 설정 (브라우저에만 저장)
const state = { mode: "sido", range: "5", view: "level" };
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

// Overview 타일에 보여줄 동인별 대표 지표 (변수 ID, 열 이름에 들어가는 글자)
const HEADLINES = {
  demand: [["V012"], ["V011", "비중"]],
  supply: [["V023"], ["V038"]],
  finance: [["V003"], ["V056"]],
  rental: [["V005"], ["V006", "월세"]],
  trigger: [["V001"], ["V037"]],
  macro: [["V043"], ["V045"]],
};

// 예상 부호: + 는 월세 리스크를 키우는 방향, - 는 낮추는 방향, ± 는 방향이 상황에 따라 다름
function signClass(sign) {
  if (sign === "+") return "sign-up";
  if (sign === "-") return "sign-down";
  return "sign-mixed";
}

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

// ── 동인 탭 ───────────────────────────────────────────
function filterBar() {
  const bar = el("div", "filter-bar");
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "보기 설정");
  const groups = [
    ["mode", "지역", [["sido", `시도 (${sample.regions.sido.join("·")})`], ["gu", `서울 구 (${sample.regions.gu.join("·")})`]]],
    ["range", "기간", [["3", "3년"], ["5", "5년"], ["all", "전체"]]],
    ["view", "값", [["level", "수준"], ["yoy", "전년동기 대비"]]],
  ];
  for (const [key, label, options] of groups) {
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

function variableCard(v) {
  const card = el("article", "var-card");
  card.id = `card-${v.id}`;

  const head = el("header", "var-head");
  head.append(el("h3", "var-name", v.name), el("span", "var-id", v.id));
  card.append(head);

  const badges = el("div", "var-badges");
  if (v.sign) {
    const b = el("span", `badge ${signClass(v.sign)}`, `부호 ${v.sign}`);
    b.title = "예상 부호 (+: 월세 리스크를 키우는 방향)";
    badges.append(b);
  }
  if (v.lead) badges.append(el("span", "badge", `선행 ${v.lead}`));
  if (v.leakage && v.leakage !== "낮음") badges.append(el("span", "badge badge-warn", `Leakage ${v.leakage}`));
  if (v.driver2) {
    const d2 = drivers.find((d) => d.id === v.driver2);
    if (d2) badges.append(el("span", "badge badge-ghost", `2차 ${NUMS[d2.no - 1]} ${d2.short}`));
  }
  card.append(badges);

  const { list, substituted, alias } = metricsFor(v.id, state.mode);
  if (alias) card.append(el("p", "var-note", `${alias}와 같은 원표(R-ONE)라 ${alias} 계열을 보여줍니다.`));
  if (substituted) {
    card.append(el("p", "var-note", state.mode === "gu" ? "서울 구 단위 자료가 없어 시도 기준으로 보여줍니다." : "시도 단위 자료가 없어 서울 구 기준으로 보여줍니다."));
  }
  if (!list.length) {
    card.append(el("p", "chart-empty", "샘플 데이터에 이 변수의 계열이 없습니다."));
    card.append(metaList(v, null));
    return card;
  }

  // 같은 변수 안의 여러 열(예: 월세·전세·전체 건수)은 버튼으로 고른다
  let active = 0;
  const tabs = el("div", "metric-tabs");
  const readout = el("div", "readout");
  const chartBox = el("div", "chart-box");
  const metaBox = el("div");
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
  const unitLine = el("p", "var-unit");
  card.append(unitLine, readout, chartBox);
  if (list.some((m) => m.provisional_from)) {
    card.append(el("p", "var-note", `최근 3개월(${periodLabel(list[0].provisional_from)}~)은 신고기한(계약 후 30일)·해제 시차로 아직 바뀌는 잠정값입니다. 점선으로 표시하고, 최신값·전년동기 대비는 확정 월 기준입니다.`));
  }
  card.append(metaBox);

  function draw() {
    const m = list[active];
    const colors = seriesColors();
    const regions = Object.keys(m.series);
    const mode = yoyMode(m);
    const yoy = state.view === "yoy";
    const raw = regions.map((r) => m.series[r]);
    const shown = yoy ? raw.map((s) => yoySeries(s, YOY_LAG[m.freq], mode)) : raw;
    const { periods, values } = sliceRange(m, shown);

    const unit = displayUnit(m.unit);
    unitLine.textContent = yoy
      ? `${metricTitle(m)} · 전년동기 대비 ${mode === "pct" ? "증감률(%)" : mode === "diff-pp" ? "차이(%p)" : "증감"} · ${FREQ[m.freq]}`
      : `${metricTitle(m)} · ${FREQ[m.freq]}${unit.includes("=") ? ` · ${unit}` : ""}`;

    // 지역별 최신값 (범례 겸용: 색 표시 + 지역 이름 + 값)
    readout.replaceChildren();
    regions.forEach((r, k) => {
      const l = latestOf(m, r);
      const item = el("div", "readout-item");
      const key = el("span", "readout-key");
      key.style.background = colors[k];
      item.append(key, el("span", "readout-region", r));
      item.append(el("strong", "readout-value", l ? fmtValue(l.value, m.unit) : "–"));
      if (l?.change != null) item.append(el("span", "readout-chg", `${l.change > 0 ? "▲" : l.change < 0 ? "▼" : ""} ${fmtChange(l.change, l.mode, m.unit)}`));
      if (l) item.append(el("span", "readout-period", periodLabel(l.period)));
      readout.append(item);
    });

    const fmt = (val, axis) => {
      if (val == null) return "–";
      if (axis) {
        if (!yoy) return fmtAxis(scaleValue(val, m.unit));
        const suffix = mode === "pct" ? "%" : mode === "diff-pp" ? "%p" : "";
        return `${val > 0 ? "+" : ""}${fmtAxis(mode === "diff" ? scaleValue(val, m.unit) : val)}${suffix}`;
      }
      if (yoy) return fmtChange(val, mode, m.unit).replace("±", "");
      return fmtValue(val, m.unit);
    };
    lineChart(chartBox, {
      periods,
      provisionalAt: provisionalIndex(m, periods),
      series: regions.map((r, k) => ({ name: r, values: values[k], color: colors[k] })),
      valueFmt: fmt,
      zeroLine: yoy,
      label: `${v.name} ${regions.join("·")} ${yoy ? "전년동기 대비" : ""} 추이`,
    });
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

function renderFactor(driver) {
  const list = variables.filter((v) => v.driver === driver.id);
  factorView.replaceChildren();

  const hero = el("section", "factor-hero");
  const top = el("div", "factor-top");
  top.append(el("h2", "factor-title", `${NUMS[driver.no - 1]} ${driver.name}`), el("span", "badge badge-ghost", driver.position));
  hero.append(top);
  hero.append(el("p", "factor-question", driver.question));
  const sub = el("p", "factor-desc");
  sub.textContent = `${driver.description} · 하위영역: ${driver.subareas.join(", ")} · 변수 ${list.length}개`;
  hero.append(sub);
  factorView.append(hero);

  factorView.append(filterBar());
  factorView.append(summaryTable(list));

  const grid = el("div", "var-grid");
  const cards = list.map(variableCard);
  grid.append(...cards);
  factorView.append(grid);
  factorView.append(el("p", "data-note", `자료: ${sample._source}. 생성 ${sample.generated.split("|")[0].trim()}. 전처리본의 보완값이 포함되어 있으며 각 카드의 '출처·처리 방법'에서 방법을 확인할 수 있습니다.`));

  // 너비가 정해진 뒤에 그린다
  for (const c of cards) c._draw?.();
}

// ── Overview 타일 ─────────────────────────────────────
function renderOverview() {
  const colors = seriesColors();
  for (const d of drivers) {
    const body = document.querySelector(`[data-tile="${d.id}"]`);
    if (!body) continue;
    body.replaceChildren();
    body.append(el("p", "tile-question", d.question));
    for (const [vid, hint] of HEADLINES[d.id]) {
      const { list } = metricsFor(vid, "sido");
      const m = (hint && list.find((x) => x.column.includes(hint))) || list[0];
      const v = variables.find((x) => x.id === vid);
      if (!m || !v) continue;
      const region = m.series["서울"] ? "서울" : Object.keys(m.series)[0];
      const l = latestOf(m, region);
      const row = el("a", "kpi");
      row.href = `#${d.id}`;
      const text = el("div", "kpi-text");
      text.append(el("span", "kpi-name", `${m.label.replace(/^(국토부실거래|주민등록인구|인구이동|주택건설|소비자동향조사)\s*/, "")} · ${region}`));
      text.append(el("strong", "kpi-value", l ? fmtValue(l.value, m.unit) : "–"));
      const meta = el("span", "kpi-meta");
      meta.textContent = l ? `${periodLabel(l.period)} · 전년동기 ${fmtChange(l.change, l.mode, m.unit)}` : "";
      text.append(meta);
      row.append(text, sparkline(m.series[region].slice(-36), colors[0]));
      body.append(row);
    }
  }
}

// ── 화면 전환 ─────────────────────────────────────────
// 현재 주소(#id)에 맞는 화면을 보여준다
function showView() {
  const id = location.hash.slice(1) || "overview";
  const driver = drivers.find((d) => d.id === id);
  const view = driver ? id : "overview";

  document.body.classList.toggle("frame", view === "overview"); // Overview 만 한 화면 고정, 동인 탭은 스크롤
  overviewView.hidden = view !== "overview";
  factorView.hidden = view === "overview";
  if (driver && sample) renderFactor(driver);
  if (!driver && sample) renderOverview();

  for (const a of viewNav.querySelectorAll("a")) {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  const current = viewNav.querySelector('[aria-current="page"]');
  if (current) current.scrollIntoView({ block: "nearest", inline: "nearest" }); // 좁은 화면에서 선택한 탭이 보이게
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

  for (const d of drivers) {
    const a = el("a", null, `${NUMS[d.no - 1]} ${d.short}`);
    a.href = `#${d.id}`;
    a.dataset.view = d.id;
    a.title = d.name;
    viewNav.insertBefore(a, viewNav.querySelector("[data-page-link]"));
  }
  showView();
  window.scrollTo(0, 0);
}

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

// 보기 설정 줄이 헤더 바로 아래에 붙도록 헤더 높이를 CSS 변수로 알려준다
new ResizeObserver(([entry]) => {
  document.documentElement.style.setProperty("--header-h", `${Math.ceil(entry.target.getBoundingClientRect().height)}px`);
}).observe(document.querySelector(".site-header"));

initFactors();
