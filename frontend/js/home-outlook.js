// Home '부동산 시장 동향 및 전망' 카드 (MOCK)
// - 실제 서비스에서는 부동산 대시보드 지표를 LLM 에 넘겨 자동으로 만들 자리다. 지금은 LLM 호출 없이,
//   같은 지표(sample)로 규칙 계산 + 문장 틀을 채워 "LLM 이 쓴 것처럼" 보이는 가상 결과를 만든다.
// - 지역(17개 시도)과 기간(최근 1·3·6·12·24개월)을 바꾸면 다시 '생성'한다. 기본값은 서울 · 최근 3개월.
// - 숫자는 모두 대시보드 계열에서 계산한 값이다. 월세 압력 규칙 중 '데이터사전' 표시가 없는 것은 mock 가정이다.
// factors.js(el·sample) · charts.js(fmt·svgEl·niceTicks) 다음, home.js 앞에 읽는다. renderHome()이 renderOutlook()을 부른다.

const OL_MONTHS = [1, 3, 6, 12, 24];
const OL_HORIZON = 3; // 전망 기간(개월)
const olState = { region: "서울", months: 3 };
let olToken = 0;
let olBuilt = false;
let olStamp = null;

// 근거 지표. kind: 변화를 %로 볼지(pct) 차이(diff)로 볼지. thr: 1개월 기준 '의미 있는 변화' 크기.
// w·sign: 월세 상승 압력 점수에 넣는 가중치와 방향(+1: 오르면 압력↑). basis: 방향 규칙의 근거.
const OL_INDICATORS = [
  { id: "V001", name: "월세통합가격지수", kind: "pct", target: true },
  { id: "V026", name: "전세가격지수", kind: "pct", thr: 0.1, w: 1, sign: 1, basis: "데이터사전(+)" },
  { id: "V005", name: "월세 수급동향", kind: "pct", thr: 0.4, w: 1, sign: 1, basis: "데이터사전(+)" },
  { id: "V037", name: "주택시장 소비심리지수", kind: "pct", thr: 1, w: 0.5, sign: 1, basis: "데이터사전(+)" },
  { id: "V002", name: "매매가격지수", kind: "pct", thr: 0.1, w: 0.5, sign: 1, basis: "mock 가정" },
  { id: "V003", name: "전세가율", kind: "diff", thr: 0.3, w: 0.5, sign: 1, basis: "mock 가정" },
  { id: "V038", name: "미분양주택", kind: "pct", thr: 2, w: 0.5, sign: -1, basis: "mock 가정" },
  { id: "V056", name: "주택담보대출 금리", kind: "diff", thr: 0.05, w: 0.5, sign: 1, basis: "mock 가정", nation: true },
];

const olClamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
// 숫자 뒤 조사: 0·3·6 으로 끝나면(영·삼·육) '으로', 그 밖은 '로'
const olRo = (s) => (/[036]$/.test(String(s)) ? "으로" : "로");
const olReduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// ── 숫자 표기 ─────────────────────────────────────────
function olPct(v, d = 1) {
  const abs = Math.abs(v);
  const rounded = Math.round(abs * 10 ** d) / 10 ** d;
  const sign = rounded === 0 ? "±" : v > 0 ? "+" : "−";
  return `${sign}${rounded.toFixed(d)}%`;
}
function olPp(v) {
  const rounded = Math.round(Math.abs(v) * 100) / 100;
  return `${rounded === 0 ? "±" : v > 0 ? "+" : "−"}${rounded.toFixed(2)}%p`;
}
const olChangeText = (row) => (row.change == null ? "–" : row.spec.kind === "pct" ? olPct(row.change) : olPp(row.change));

function olAddMonths(period, k) {
  const ord = periodOrdinal(period).ord + k;
  return `${Math.floor(ord / 12)}-${String((ord % 12) + 1).padStart(2, "0")}`;
}

// ── 데이터 고르기 ─────────────────────────────────────
// 변수 하나에서 그 지역 값이 있는 월 계열 중 가장 최근까지 있는 것
function olMetric(varId, region) {
  const id = sample.aliases?.[varId] || varId;
  const list = sample.metrics.filter((m) => m.var === id && m.freq === "M" && m.series[region]);
  list.sort((a, b) => (a.periods[a.periods.length - 1] < b.periods[b.periods.length - 1] ? 1 : -1));
  return list[0] || null;
}

// 마지막 확정 값과, 그 months 개월 전 값
function olPoint(m, region, months) {
  const s = m.series[region];
  let i = provisionalIndex(m) - 1;
  while (i >= 0 && s[i] == null) i--;
  if (i < 0) return null;
  const want = periodOrdinal(m.periods[i]).ord - months;
  const j = m.periods.findIndex((p) => periodOrdinal(p).ord === want);
  const then = j >= 0 ? s[j] : null;
  return { i, now: s[i], period: m.periods[i], then, thenPeriod: j >= 0 ? m.periods[j] : null };
}

// ── 동향 · 전망 계산 (mock 규칙) ───────────────────────
const olScale = (a) =>
  a >= 0.8 ? ["큰 폭 상승", "up"] : a >= 0.3 ? ["상승", "up"] : a >= 0.08 ? ["완만한 상승", "up"] :
  a > -0.08 ? ["보합", "flat"] : a > -0.3 ? ["완만한 하락", "down"] : a > -0.8 ? ["하락", "down"] : ["큰 폭 하락", "down"];

function olCompute(region, months) {
  if (!sample) return null;
  const target = olMetric("V001", region);
  if (!target) return null;

  const rows = [];
  for (const spec of OL_INDICATORS) {
    const reg = spec.nation ? "전국" : region;
    const m = olMetric(spec.id, reg);
    const p = m ? olPoint(m, reg, months) : null;
    if (!p) continue;
    let change = null;
    if (p.then != null) change = spec.kind === "pct" ? (p.now / p.then - 1) * 100 : p.now - p.then;
    const score = change != null && spec.thr ? olClamp(change / (spec.thr * Math.sqrt(months) * 3), -1, 1) * spec.sign : 0;
    rows.push({ spec, m, p, change, score });
  }
  const main = rows.find((r) => r.spec.target);
  if (!main || main.change == null) return null;

  // 월세 상승 압력 점수 (-1 ~ +1)
  const weighted = rows.filter((r) => r.spec.w && r.change != null);
  const wSum = weighted.reduce((a, r) => a + r.spec.w, 0) || 1;
  const pressure = weighted.reduce((a, r) => a + r.spec.w * r.score, 0) / wSum;

  // 월세지수 최근 월별 변화율 → 단순 추세 + 압력 점수로 향후 3개월 예상 (mock)
  const s = target.series[region];
  const end = provisionalIndex(target);
  const vals = [];
  for (let i = 0; i < end; i++) if (s[i] != null) vals.push({ p: target.periods[i], v: s[i] });
  const moms = [];
  for (let i = Math.max(1, vals.length - 12); i < vals.length; i++) moms.push((vals[i].v / vals[i - 1].v - 1) * 100);
  const mean = (a) => a.reduce((x, y) => x + y, 0) / (a.length || 1);
  const recent = mean(moms.slice(-6));
  const std = Math.max(0.1, Math.sqrt(mean(moms.map((x) => (x - mean(moms)) ** 2))));
  const e = 0.7 * recent + 0.3 * pressure * 0.3; // 월 예상 변화율(%)
  const now = vals[vals.length - 1];
  const path = [];
  for (let h = 1; h <= OL_HORIZON; h++) {
    const cum = ((1 + e / 100) ** h - 1) * 100;
    const half = 1.28 * std * Math.sqrt(h); // 80% 범위
    path.push({ period: olAddMonths(now.p, h), v: now.v * (1 + cum / 100), lo: now.v * (1 + (cum - half) / 100), hi: now.v * (1 + (cum + half) / 100), cum });
  }
  const dir = e >= 0.08 ? 1 : e <= -0.08 ? -1 : 0;
  const agreeW = weighted.reduce((a, r) => a + (dir === 0 ? (Math.abs(r.score) < 0.33 ? r.spec.w : 0) : r.score * dir >= 0.33 ? r.spec.w : 0), 0);
  const agree = agreeW / wSum;
  const conf = agree >= 0.6 ? "높음" : agree >= 0.4 ? "보통" : "낮음";

  // 17개 시도 중 같은 기간 월세지수 상승률 순위
  const all = [];
  for (const r of sample.regions.sido) {
    const mm = olMetric("V001", r);
    const pp = mm ? olPoint(mm, r, months) : null;
    if (pp && pp.then != null) all.push([r, (pp.now / pp.then - 1) * 100]);
  }
  all.sort((a, b) => b[1] - a[1]);
  const rank = all.findIndex(([r]) => r === region) + 1;
  const avgAll = all.length ? mean(all.map((x) => x[1])) : null;

  const avg = main.change / months; // 월평균 변화율
  const [trendLabel, trendTone] = olScale(avg);
  const [fcLabel, fcTone] = olScale(e);
  const histN = Math.min(vals.length, Math.max(12, months + 1));
  return {
    region, months, rows, main, pressure, conf, agree, rank, total: all.length, avgAll, avg,
    trend: { label: trendLabel, tone: trendTone },
    fc: { label: fcLabel, tone: fcTone, e, std, path, cum3: path[path.length - 1].cum, now },
    hist: vals.slice(-histN),
    period: main.p.period,
  };
}

// ── 문장 만들기 (LLM 대신 문장 틀) ─────────────────────
function olNarrative(c) {
  const { region, months, main, rows, fc } = c;
  const row = (id) => rows.find((r) => r.spec.id === id);
  const fmt = (r) => fmtValue(r.p.now, r.m.unit);
  const move = (v) => (v > 0.04 ? "올랐습니다" : v < -0.04 ? "내렸습니다" : "거의 변하지 않았습니다");
  const span = months === 1 ? "전월보다" : `최근 ${months}개월 동안`;

  const trend = [];
  const p1 = [`${region} 아파트 월세통합가격지수는 ${periodLabel(c.period, true)} 기준 ${fmtNumber(main.p.now, 1)}${olRo(fmtNumber(main.p.now, 1))}, ${span} ${olPct(main.change)} ${move(main.change)}.`];
  if (months >= 3) p1.push(`월평균으로는 ${olPct(c.avg)} 수준입니다.`);
  if (c.rank) {
    const gap = c.avgAll != null ? main.change - c.avgAll : null;
    p1.push(`17개 시도 중 같은 기간 상승률 ${c.rank}위${gap != null ? `이며, 시도 평균(${olPct(c.avgAll)})보다 ${gap >= 0 ? "높은" : "낮은"} 편` : ""}입니다.`);
  }
  trend.push(p1.join(" "));

  const p2 = [];
  const jeonse = row("V026");
  const sale = row("V002");
  if (jeonse?.change != null || sale?.change != null) {
    const parts = [];
    if (jeonse?.change != null) parts.push(`전세가격지수는 ${olPct(jeonse.change)}`);
    if (sale?.change != null) parts.push(`매매가격지수는 ${olPct(sale.change)}`);
    p2.push(`같은 기간 ${parts.join(", ")} 변했습니다.`);
    if (jeonse?.change != null) p2.push(`월세 상승률이 전세보다 ${main.change > jeonse.change ? "높아" : "낮아"} 임대시장 안에서 월세가 ${main.change > jeonse.change ? "더 빠르게" : "상대적으로 더디게"} 움직인 모습입니다.`);
  }
  const supply = row("V005");
  if (supply?.p.then != null) p2.push(`월세 수급동향은 ${fmtNumber(supply.p.now, 1)}${olRo(fmtNumber(supply.p.now, 1))} ${months}개월 전(${fmtNumber(supply.p.then, 1)})보다 ${supply.p.now >= supply.p.then ? "높습니다" : "낮습니다"}.`);
  if (p2.length) trend.push(p2.join(" "));

  const last = fc.path[fc.path.length - 1];
  const outlook = [];
  const lead = fc.tone === "up" ? `${fc.label} 흐름이 이어질 것으로` : fc.tone === "down" ? `${fc.label} 흐름으로 돌아설 것으로` : "보합권에서 움직일 것으로";
  outlook.push(`향후 ${OL_HORIZON}개월 ${region} 월세는 ${lead} 예상합니다. 월세통합가격지수는 ${fmtNumber(fc.now.v, 1)}에서 ${fmtNumber(last.v, 1)}(80% 범위 ${fmtNumber(last.lo, 1)}~${fmtNumber(last.hi, 1)}) 수준으로, 현재 대비 ${olPct(fc.cum3)} 변동이 예상됩니다.`);
  const ups = rows.filter((r) => r.spec.w && r.score >= 0.33).sort((a, b) => b.score - a.score).slice(0, 3).map((r) => r.spec.name);
  const downs = rows.filter((r) => r.spec.w && r.score <= -0.33).sort((a, b) => a.score - b.score).slice(0, 3).map((r) => r.spec.name);
  const why = [];
  if (ups.length) why.push(`월세 상승 압력을 높이는 지표는 ${ups.join(", ")}`);
  if (downs.length) why.push(`낮추는 지표는 ${downs.join(", ")}`);
  outlook.push(`${why.length ? `${why.join(", ")}입니다. ` : "뚜렷한 방향을 가리키는 지표가 많지 않습니다. "}지표 방향 일치도는 ${Math.round(c.agree * 100)}%로 신뢰도는 ${c.conf}입니다.`);

  const watch = [];
  const pool = rows.filter((r) => r.spec.w && r.change != null && ["V056", "V037", "V038", "V003", "V005"].includes(r.spec.id));
  pool.sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  for (const r of pool.slice(0, 3)) {
    const effect = r.score >= 0.33 ? "월세 상승 압력으로 작용합니다" : r.score <= -0.33 ? "월세 상승 압력을 낮추는 요인입니다" : "아직 뚜렷한 방향성은 없습니다";
    watch.push(`${r.spec.name} ${fmt(r)}(${olChangeText(r)}) — ${effect}.`);
  }
  return { trend, outlook, watch };
}

// ── 차트: 월세통합가격지수 + 3개월 예상 구간 ───────────
// 카드 안 차트 폭: 화면 폭에 맞춰 그려야 좁은 화면에서도 글자가 줄어들지 않는다 (폭이 바뀌면 renderHome 이 다시 그린다)
function olChartWidth() {
  const bodyW = document.querySelector("#home-outlook-body")?.clientWidth || 800;
  const pad = innerWidth <= 640 ? 32 : 48;
  const w = innerWidth <= 900 ? bodyW - pad : bodyW / 2.1 - pad;
  return olClamp(Math.round(w), 260, 640);
}

function olChart(c) {
  const W = olChartWidth(), H = W < 400 ? 220 : 250, L = 42, R = W < 400 ? 50 : 58, T = 18, B = 28;
  const hist = c.hist;
  const fcs = c.fc.path;
  const total = hist.length + fcs.length;
  const x = (i) => L + (i * (W - L - R)) / (total - 1);
  const vals = [...hist.map((h) => h.v), ...fcs.flatMap((f) => [f.lo, f.hi])];
  const ticks = niceTicks(Math.min(...vals), Math.max(...vals), 3);
  const y0 = ticks[0];
  const y1 = ticks[ticks.length - 1];
  const y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "ol-chart", role: "img", "aria-label": `${c.region} 아파트 월세통합가격지수 최근 ${hist.length}개월 추이와 향후 ${OL_HORIZON}개월 예상(mock). 현재 ${fmtNumber(c.fc.now.v, 1)}, ${OL_HORIZON}개월 뒤 ${fmtNumber(fcs[fcs.length - 1].v, 1)}` });

  for (const t of ticks) {
    svg.append(svgEl("line", { class: "ol-grid-line", x1: L, x2: W - R, y1: y(t), y2: y(t) }));
    const lab = svgEl("text", { x: L - 6, y: y(t) + 4, "text-anchor": "end" });
    lab.textContent = fmtAxis(t);
    svg.append(lab);
  }
  const labels = [...hist, ...fcs].map((d) => d.period ?? d.p);
  const step = Math.max(1, Math.ceil(total / 5));
  let lastLabeled = 0;
  for (let i = 0; i < total; i += step) {
    const t = svgEl("text", { x: x(i), y: H - 8, "text-anchor": i === 0 ? "start" : "middle" });
    t.textContent = periodLabel(labels[i]);
    svg.append(t);
    lastLabeled = i;
  }
  // 마지막 달 라벨은 앞 라벨과 글자가 겹치지 않을 만큼 떨어져 있을 때만 붙인다
  if (x(total - 1) - x(lastLabeled) >= 56) {
    const t = svgEl("text", { x: x(total - 1), y: H - 8, "text-anchor": "end" });
    t.textContent = periodLabel(labels[total - 1]);
    svg.append(t);
  }

  const lastI = hist.length - 1;
  svg.append(svgEl("line", { class: "ol-split", x1: x(lastI), x2: x(lastI), y1: T - 4, y2: H - B }));
  const fcLabel = svgEl("text", { class: "ol-fclabel", x: x(lastI) + 6, y: T + 6 });
  fcLabel.textContent = "예상(mock) →";
  svg.append(fcLabel);

  // 예상 구간(80%) → 실제 선 → 예상 선
  const bandUp = [`${x(lastI)},${y(hist[lastI].v)}`, ...fcs.map((f, k) => `${x(lastI + 1 + k)},${y(f.hi)}`)];
  const bandDn = [...fcs.map((f, k) => `${x(lastI + 1 + k)},${y(f.lo)}`)].reverse();
  svg.append(svgEl("polygon", { class: "ol-band", points: [...bandUp, ...bandDn].join(" ") }));
  svg.append(svgEl("path", { class: "ol-hist", d: hist.map((h, i) => `${i ? "L" : "M"}${x(i)},${y(h.v)}`).join("") }));
  svg.append(svgEl("path", { class: "ol-fc", d: `M${x(lastI)},${y(hist[lastI].v)}${fcs.map((f, k) => `L${x(lastI + 1 + k)},${y(f.v)}`).join("")}` }));
  svg.append(svgEl("circle", { class: "ol-dot", cx: x(lastI), cy: y(hist[lastI].v), r: 4 }));
  const end = fcs[fcs.length - 1];
  svg.append(svgEl("circle", { class: "ol-dot-fc", cx: x(total - 1), cy: y(end.v), r: 4.5 }));
  const endLab = svgEl("text", { class: "ol-end", x: x(total - 1) + 9, y: y(end.v) + 4 });
  endLab.textContent = fmtNumber(end.v, 1);
  svg.append(endLab);

  // 마우스를 올리면 그 달의 값을 위쪽에 보여 준다
  const cursor = svgEl("line", { class: "ol-cursor", y1: T - 4, y2: H - B, visibility: "hidden" });
  const readout = svgEl("text", { class: "ol-readout", x: L, y: 10 });
  const hit = svgEl("rect", { x: L, y: 0, width: W - L - R + 1, height: H - B, fill: "transparent" });
  const show = (evt) => {
    const box = svg.getBoundingClientRect();
    const px = ((evt.clientX - box.left) / box.width) * W;
    const i = olClamp(Math.round(((px - L) / (W - L - R)) * (total - 1)), 0, total - 1);
    cursor.setAttribute("x1", x(i));
    cursor.setAttribute("x2", x(i));
    cursor.setAttribute("visibility", "visible");
    const isFc = i > lastI;
    const d = isFc ? fcs[i - hist.length] : hist[i];
    readout.textContent = isFc
      ? `${periodLabel(d.period, true)} 예상 ${fmtNumber(d.v, 1)} (${fmtNumber(d.lo, 1)}~${fmtNumber(d.hi, 1)})`
      : `${periodLabel(d.p, true)} ${fmtNumber(d.v, 1)}`;
  };
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerleave", () => {
    cursor.setAttribute("visibility", "hidden");
    readout.textContent = "";
  });
  svg.append(cursor, readout, hit);
  return svg;
}

// ── 카드 그리기 ───────────────────────────────────────
function olStampText() {
  const d = olStamp || new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} 생성`;
}

function olHead(c, busy) {
  const head = el("div", "ol-head");
  head.append(el("h3", "ol-title", `${olState.region} · 최근 ${olState.months}개월 동향 및 전망`));
  head.append(el("span", "ol-badge", "AI 자동 생성 · mock"));
  if (c) head.append(el("span", "ol-asof", `${periodLabel(c.period, true)} 기준 · ${olStampText()}`));
  const b = el("button", `ol-regen${busy ? " is-busy" : ""}`);
  b.type = "button";
  b.disabled = !!busy;
  b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>';
  b.append(document.createTextNode(busy ? "분석 중" : "다시 생성"));
  b.addEventListener("click", () => renderOutlook({ animate: true }));
  head.append(b);
  return head;
}

function olEvidence(c) {
  const det = el("details", "ol-evidence");
  det.append(el("summary", null, `근거 지표 ${c.rows.length}개 보기`));
  const wrap = el("div", "ol-table-wrap");
  const table = el("table", "ol-table");
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["지표", "최신", `${c.months}개월 변화`, "월세 압력", "규칙"]) hr.append(el("th", null, h));
  thead.append(hr);
  const tb = el("tbody");
  for (const r of c.rows) {
    const tr = el("tr");
    tr.append(el("td", null, r.spec.name), el("td", null, fmtValue(r.p.now, r.m.unit)), el("td", null, olChangeText(r)));
    const effect = r.spec.target ? ["–", ""] : r.score >= 0.33 ? ["▲ 상승", "up"] : r.score <= -0.33 ? ["▼ 완화", "down"] : ["– 중립", ""];
    tr.append(el("td", effect[1], effect[0]), el("td", "src", r.spec.target ? "분석 대상" : r.spec.basis));
    tb.append(tr);
  }
  table.append(thead, tb);
  wrap.append(table);
  det.append(wrap);
  det.append(el("p", "ol-chart-sub", "월세 압력 = 지표 변화가 월세 상승 쪽인지(▲) 완화 쪽인지(▼). '데이터사전(+)'은 변수 정의서의 예상 부호, 'mock 가정'은 이 데모용 가정입니다."));
  return det;
}

function olLoading(c) {
  const box = el("div", "ol-card");
  box.append(olHead(null, true));
  const body = el("div", "ol-loading");
  body.setAttribute("role", "status");
  body.append(el("p", "ol-loading-msg", `${olState.region} 대시보드 지표 ${OL_INDICATORS.length}개를 분석하고 있습니다…`));
  for (const w of ["w90", "w75", "w90", "w60", "w40"]) body.append(el("div", `ol-skel ${w}`));
  box.append(body);
  return box;
}

function olCard(c, reveal) {
  const n = olNarrative(c);
  const card = el("article", "ol-card");
  card.append(olHead(c, false));
  const grid = el("div", "ol-grid");

  // 왼쪽: 판정 두 칸 + 문장
  const left = el("div", "ol-left");
  const verdicts = el("div", `ol-verdicts${reveal ? " ol-reveal" : ""}`);
  const tile = (label, tone, main, small, sub, idx) => {
    const t = el("div", `ol-verdict tone-${tone}`);
    t.style.setProperty("--i", idx);
    t.append(el("span", "ol-vlabel", label));
    const m = el("div", "ol-vmain");
    m.append(el("strong", null, main), el("span", "meta", small));
    t.append(m, el("div", "ol-vsub", sub));
    return t;
  };
  verdicts.append(
    tile(`동향 평가 (최근 ${c.months}개월)`, c.trend.tone, c.trend.label, olPct(c.main.change), `월평균 ${olPct(c.avg)}${c.rank ? ` · 17개 시도 중 ${c.rank}위` : ""}`, 0),
    tile(`향후 ${OL_HORIZON}개월 전망`, c.fc.tone, c.fc.label, olPct(c.fc.cum3), `${fmtNumber(c.fc.now.v, 1)} → ${fmtNumber(c.fc.path[OL_HORIZON - 1].v, 1)} · 신뢰도 ${c.conf}`, 1),
  );
  left.append(verdicts);

  const text = el("div", `ol-text${reveal ? " ol-reveal" : ""}`);
  let idx = 2;
  const add = (node) => {
    node.style.setProperty("--i", idx++);
    text.append(node);
  };
  add(el("h4", null, "동향 평가"));
  n.trend.forEach((s) => add(el("p", null, s)));
  add(el("h4", null, `전망 (향후 ${OL_HORIZON}개월)`));
  n.outlook.forEach((s) => add(el("p", null, s)));
  if (n.watch.length) {
    add(el("h4", null, "점검할 변수"));
    const ul = el("ul");
    n.watch.forEach((s) => ul.append(el("li", null, s)));
    add(ul);
  }
  left.append(text);

  // 오른쪽: 차트 + 근거
  const right = el("div", `ol-right${reveal ? " ol-reveal" : ""}`);
  const chartBox = el("div");
  chartBox.style.setProperty("--i", 3);
  chartBox.append(el("div", "ol-chart-title", `아파트 월세통합가격지수 · ${c.region}`));
  chartBox.append(el("div", "ol-chart-sub", `지수 · 월 · 최근 ${c.hist.length}개월 + 향후 ${OL_HORIZON}개월 예상`));
  chartBox.append(olChart(c));
  const legend = el("div", "ol-legend");
  for (const [cls, text2] of [["", "실제값"], ["dash", "예상(mock)"], ["band", "80% 범위"]]) {
    const s = el("span");
    s.append(el("i", cls), document.createTextNode(text2));
    legend.append(s);
  }
  chartBox.append(legend);
  const ev = olEvidence(c);
  ev.style.setProperty("--i", 4);
  right.append(chartBox, ev);

  grid.append(left, right);
  card.append(grid);
  card.append(el("p", "ol-foot", "※ mock(예시) 화면입니다. 실제 서비스에서는 부동산 대시보드 지표를 근거로 LLM이 이 평가를 자동으로 작성합니다. 지금 보이는 숫자는 대시보드 데이터에서 규칙으로 계산한 가상 결과이며, 투자 권유나 가격 보장이 아닙니다. 자료: 한국부동산원 R-ONE · 한국은행 ECOS · 국토연구원."));
  return card;
}

// ── 선택 줄(지역 · 기간) ──────────────────────────────
function olBuildTools() {
  const box = document.querySelector("#home-outlook-tools");
  if (!box) return;
  const regions = sample.regions.sido;
  if (!olBuilt || !box.querySelector(".ol-select")) {
    box.replaceChildren();
    const g1 = el("div", "seg-group");
    g1.append(el("label", "seg-label", "지역"));
    const sel = el("select", "ol-select");
    sel.id = "ol-region";
    g1.firstChild.setAttribute("for", "ol-region");
    for (const r of regions) sel.append(new Option(r, r));
    sel.addEventListener("change", () => {
      olState.region = sel.value;
      renderOutlook({ animate: true });
    });
    g1.append(sel);

    const g2 = el("div", "seg-group");
    g2.append(el("span", "seg-label", "기간"));
    const seg = el("div", "seg");
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "분석 기간");
    for (const m of OL_MONTHS) {
      const b = el("button", null, `${m}개월`);
      b.type = "button";
      b.dataset.months = m;
      b.addEventListener("click", () => {
        if (olState.months === m) return;
        olState.months = m;
        renderOutlook({ animate: true });
      });
      seg.append(b);
    }
    g2.append(seg);
    box.append(g1, g2);
    olBuilt = true;
  }
  box.querySelector(".ol-select").value = regions.includes(olState.region) ? olState.region : regions[0];
  for (const b of box.querySelectorAll(".seg button")) b.setAttribute("aria-pressed", String(+b.dataset.months === olState.months));
}

function renderOutlook({ animate = false } = {}) {
  const box = document.querySelector("#home-outlook-body");
  if (!box || !sample) return;
  if (!sample.regions.sido.includes(olState.region)) olState.region = sample.regions.sido[0];
  olBuildTools();
  const token = ++olToken;
  const c = olCompute(olState.region, olState.months);
  if (!c) {
    box.replaceChildren(el("p", "chart-empty", "이 지역은 월세 지수 자료가 없어 동향·전망을 만들지 못했습니다"));
    return;
  }
  const paint = (reveal) => {
    if (token !== olToken) return;
    box.replaceChildren(olCard(c, reveal));
  };
  if (!olStamp) olStamp = new Date();
  if (!animate) return paint(false);
  box.replaceChildren(olLoading(c));
  setTimeout(() => {
    olStamp = new Date();
    paint(!olReduced());
  }, olReduced() ? 0 : 1100);
}

// 질문창 등 다른 모듈이 같은 계산을 쓰도록 연다
window.KHMI_OUTLOOK = {
  compute: olCompute,
  narrative: olNarrative,
  state: olState,
  // 카드의 지역·기간을 바꾸고 카드 위치로 이동
  show(region, months) {
    if (region && sample?.regions.sido.includes(region)) olState.region = region;
    if (months && OL_MONTHS.includes(months)) olState.months = months;
    renderOutlook({ animate: true });
    document.querySelector("#home-outlook")?.scrollIntoView({ behavior: olReduced() ? "auto" : "smooth", block: "start" });
  },
};
