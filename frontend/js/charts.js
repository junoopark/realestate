// 동인 탭·Overview 공용: 숫자 표시 규칙, 시계열 변환, SVG 선 차트·스파크라인 (라이브러리 없이 그린다)
// 색은 css/style.css 의 --series-1~3 (지역 비교는 최대 3개 계열, 다크모드는 따로 정한 색)

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

// ── 단위·숫자 표시 ────────────────────────────────────
// 큰 단위는 읽기 쉬운 단위로 바꿔 보여준다 (값 자체는 바꾸지 않고 표시만)
const UNIT_SCALE = {
  십억원: { div: 1000, unit: "조원" },
  천불: { div: 100000, unit: "억달러" },
  원: { div: 10000, unit: "만원" },
};

function displayUnit(unit) {
  return UNIT_SCALE[unit]?.unit ?? unit;
}

function scaleValue(v, unit) {
  if (v == null) return null;
  return UNIT_SCALE[unit] ? v / UNIT_SCALE[unit].div : v;
}

function fmtNumber(v, digits) {
  if (v == null || Number.isNaN(v)) return "–";
  const abs = Math.abs(v);
  // 건수·인구처럼 정수인 값은 소수점 없이, 그 밖은 크기에 따라 0~2자리
  const d = digits ?? (Number.isInteger(v) || abs >= 1000 ? 0 : abs >= 100 ? 1 : 2);
  return v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtValue(v, unit) {
  const u = displayUnit(unit);
  const s = fmtNumber(scaleValue(v, unit));
  if (s === "–" || !u || u.includes("=")) return s; // 2020=100 같은 기준 표기는 값 옆에 붙이지 않는다
  return `${s}${u.startsWith("연%") ? "%" : u === "%" ? "%" : " " + u}`;
}

// ── 변환: 전년동기 대비 ───────────────────────────────
const YOY_LAG = { M: 12, Q: 4, H: 2, A: 1 };

// 비율(%)·음수가 있는 계열은 차이(%p 또는 같은 단위), 그 밖은 증감률(%)
function yoyMode(metric) {
  if (metric.unit === "%" || metric.unit === "연%") return "diff-pp";
  const hasNonPositive = Object.values(metric.series).some((s) => s.some((v) => v != null && v <= 0));
  return hasNonPositive ? "diff" : "pct";
}

function yoySeries(values, lag, mode) {
  return values.map((v, i) => {
    const prev = values[i - lag];
    if (v == null || prev == null) return null;
    if (mode === "pct") return prev === 0 ? null : (v / prev - 1) * 100;
    return v - prev;
  });
}

function fmtChange(v, mode, unit) {
  if (v == null) return "–";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  const abs = Math.abs(v);
  if (mode === "pct") return `${sign}${fmtNumber(abs, 1)}%`;
  if (mode === "diff-pp") return `${sign}${fmtNumber(abs, 2)}%p`;
  return `${sign}${fmtValue(abs, unit)}`;
}

// 잠정 구간이 시작되는 위치 (없으면 계열 길이). 실거래 신고건수처럼 최근 값이 아직 바뀌는 계열
function provisionalIndex(metric, periods = metric.periods) {
  if (!metric.provisional_from) return periods.length;
  const i = periods.indexOf(metric.provisional_from);
  return i < 0 ? periods.length : i;
}

// 마지막 확정 값과 그 시점, 전년동기 대비 변화 (잠정 구간은 건너뛴다)
function latestOf(metric, region) {
  const values = metric.series[region] || [];
  for (let i = provisionalIndex(metric) - 1; i >= 0; i--) {
    if (values[i] == null) continue;
    const lag = YOY_LAG[metric.freq];
    const prev = values[i - lag];
    const mode = yoyMode(metric);
    let change = null;
    if (prev != null) change = mode === "pct" ? (prev === 0 ? null : (values[i] / prev - 1) * 100) : values[i] - prev;
    return { value: values[i], period: metric.periods[i], change, mode };
  }
  return null;
}

// ── 축 눈금 ───────────────────────────────────────────
function niceTicks(min, max, count = 4) {
  if (min === max) {
    const pad = Math.abs(min) * 0.05 || 1;
    min -= pad;
    max += pad;
  }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

// 기간 표기 (짧게/길게): 2026-08 → 26.08 / 2026년 8월, 2026Q2 → 26.2Q / 2026년 2분기,
//                       2026H1 → 26.상 / 2026년 상반기, 2024 → 2024 / 2024년
function periodLabel(p, long = false) {
  if (/^\d{4}-\d{2}$/.test(p)) return long ? `${p.slice(0, 4)}년 ${+p.slice(5)}월` : `${p.slice(2, 4)}.${p.slice(5)}`;
  if (/Q\d$/.test(p)) return long ? `${p.slice(0, 4)}년 ${p.slice(-1)}분기` : `${p.slice(2, 4)}.${p.slice(-1)}Q`;
  if (/H\d$/.test(p)) {
    const half = p.endsWith("1") ? "상" : "하";
    return long ? `${p.slice(0, 4)}년 ${half}반기` : `${p.slice(2, 4)}.${half}`;
  }
  return long ? `${p}년` : p;
}

// 축 눈금 글자: 눈금이 깔끔한 값이므로 필요한 만큼만 소수점을 쓴다
function fmtAxis(v) {
  return v.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

// ── 선 차트 ───────────────────────────────────────────
// opts: { periods, series: [{name, values, color}], valueFmt(v, axis), height, zeroLine, provisionalAt }
// provisionalAt: 이 위치부터는 잠정값 → 점선으로 이어 그리고 말풍선에 '잠정' 표시
function lineChart(container, opts) {
  container.replaceChildren();
  container.classList.add("chart");
  const width = Math.max(container.clientWidth, 240);
  const height = opts.height ?? 200;
  const m = { top: 10, right: 12, bottom: 22, left: 52 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;
  const n = opts.periods.length;

  const all = opts.series.flatMap((s) => s.values).filter((v) => v != null);
  if (!all.length) {
    container.append(Object.assign(document.createElement("p"), { className: "chart-empty", textContent: "선택한 기간에 자료가 없습니다" }));
    return;
  }
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (opts.zeroLine) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  const ticks = niceTicks(lo, hi);
  const y0 = ticks[0];
  const y1 = ticks[ticks.length - 1];
  const x = (i) => m.left + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => m.top + ih - ((v - y0) / (y1 - y0)) * ih;

  const svg = svgEl("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img" });
  svg.setAttribute("aria-label", opts.label || "시계열 차트");

  // 눈금선·y축 글자 (옅게)
  const grid = svgEl("g", { class: "chart-grid" });
  for (const t of ticks) {
    grid.append(svgEl("line", { x1: m.left, x2: width - m.right, y1: y(t), y2: y(t), class: t === 0 && opts.zeroLine ? "zero" : "" }));
    const label = svgEl("text", { x: m.left - 6, y: y(t), "text-anchor": "end", "dominant-baseline": "middle" });
    label.textContent = opts.valueFmt ? opts.valueFmt(t, true) : fmtNumber(t);
    grid.append(label);
  }
  svg.append(grid);

  // x축 글자: 글자가 겹치지 않도록 폭 64px 마다 하나
  const xg = svgEl("g", { class: "chart-axis" });
  const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 64))));
  for (let i = 0; i < n; i += step) {
    const t = svgEl("text", { x: x(i), y: height - 6, "text-anchor": i === 0 ? "start" : "middle" });
    t.textContent = periodLabel(opts.periods[i]);
    xg.append(t);
  }
  svg.append(xg);

  // 선: 빈칸은 끊어서 그린다. 잠정 구간은 마지막 확정점에서 이어지는 점선
  const pAt = opts.provisionalAt ?? n;
  const pathOf = (values, from, to) => {
    let d = "";
    let pen = false;
    for (let i = from; i < to; i++) {
      const v = values[i];
      if (v == null) {
        pen = false;
        continue;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  if (pAt < n) {
    svg.append(svgEl("rect", { x: x(Math.max(pAt - 0.5, 0)), y: m.top, width: x(n - 1) - x(Math.max(pAt - 0.5, 0)) + 4, height: ih, class: "chart-prov-band" }));
  }
  for (const s of opts.series) {
    svg.append(svgEl("path", { d: pathOf(s.values, 0, Math.min(pAt, n)), class: "chart-line", stroke: s.color }));
    if (pAt < n) svg.append(svgEl("path", { d: pathOf(s.values, Math.max(pAt - 1, 0), n), class: "chart-line chart-line-prov", stroke: s.color }));
    // 마지막 값에 점
    const last = s.values.findLastIndex((v) => v != null);
    if (last >= 0) svg.append(svgEl("circle", { cx: x(last), cy: y(s.values[last]), r: 3, fill: s.color, class: "chart-end" }));
  }

  // 마우스·키보드로 읽는 층: 세로선 + 점 + 말풍선
  const cross = svgEl("line", { y1: m.top, y2: m.top + ih, class: "chart-cross", visibility: "hidden" });
  const dots = opts.series.map((s) => svgEl("circle", { r: 4, fill: s.color, class: "chart-dot", visibility: "hidden" }));
  svg.append(cross, ...dots);
  const hit = svgEl("rect", { x: m.left, y: m.top, width: iw, height: ih, fill: "transparent" });
  svg.append(hit);
  container.append(svg);

  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  container.append(tip);

  let current = -1;
  function show(i) {
    current = Math.max(0, Math.min(n - 1, i));
    const cx = x(current);
    cross.setAttribute("x1", cx);
    cross.setAttribute("x2", cx);
    cross.setAttribute("visibility", "visible");
    tip.replaceChildren();
    const head = document.createElement("div");
    head.className = "chart-tip-head";
    head.textContent = periodLabel(opts.periods[current], true) + (current >= pAt ? " · 잠정" : "");
    tip.append(head);
    opts.series.forEach((s, k) => {
      const v = s.values[current];
      if (v == null) {
        dots[k].setAttribute("visibility", "hidden");
      } else {
        dots[k].setAttribute("cx", cx);
        dots[k].setAttribute("cy", y(v));
        dots[k].setAttribute("visibility", "visible");
      }
      const row = document.createElement("div");
      row.className = "chart-tip-row";
      const key = document.createElement("span");
      key.className = "chart-tip-key";
      key.style.background = s.color;
      const val = document.createElement("strong");
      val.textContent = opts.valueFmt ? opts.valueFmt(v) : fmtNumber(v);
      const name = document.createElement("span");
      name.textContent = s.name;
      row.append(key, val, name);
      tip.append(row);
    });
    tip.hidden = false;
    const left = cx + 12 + tip.offsetWidth > width ? cx - tip.offsetWidth - 12 : cx + 12;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${m.top}px`;
  }
  function hide() {
    current = -1;
    cross.setAttribute("visibility", "hidden");
    dots.forEach((d) => d.setAttribute("visibility", "hidden"));
    tip.hidden = true;
  }
  function indexAt(evt) {
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * width;
    return n === 1 ? 0 : Math.round(((px - m.left) / iw) * (n - 1));
  }
  hit.addEventListener("pointermove", (e) => show(indexAt(e)));
  hit.addEventListener("pointerleave", hide);
  svg.setAttribute("tabindex", "0");
  svg.addEventListener("focus", () => show(n - 1));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      show((current < 0 ? n - 1 : current) + (e.key === "ArrowRight" ? 1 : -1));
    }
  });
}

// ── 스파크라인 (Overview 타일) ─────────────────────────
function sparkline(values, color, width = 120, height = 32) {
  const svg = svgEl("svg", { width, height, viewBox: `0 0 ${width} ${height}`, class: "spark", "aria-hidden": "true" });
  const pts = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (pts.length < 2) return svg;
  const lo = Math.min(...pts.map((p) => p[1]));
  const hi = Math.max(...pts.map((p) => p[1]));
  const n = values.length - 1;
  const x = (i) => 2 + (i / n) * (width - 6);
  const y = (v) => (hi === lo ? height / 2 : 3 + (1 - (v - lo) / (hi - lo)) * (height - 6));
  svg.append(svgEl("path", { d: pts.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(""), class: "spark-line", stroke: color }));
  const [li, lv] = pts[pts.length - 1];
  svg.append(svgEl("circle", { cx: x(li), cy: y(lv), r: 2.5, fill: color }));
  return svg;
}

// 현재 테마의 계열 색 (CSS 변수)
function seriesColors() {
  const cs = getComputedStyle(document.documentElement);
  return [1, 2, 3].map((k) => cs.getPropertyValue(`--series-${k}`).trim());
}
