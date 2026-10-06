/* 조기경보 페이지 차트 모듈 (warning.html 전용). 인라인 SVG·HTML 로 그리고, 모든 차트에 툴팁과 표 보기를 붙인다.
   동인 ①~⑥은 고정 순서의 계열색(d1~d6), 지역 고정효과는 회색(dx). 글자는 항상 텍스트 색, 색은 마크에만 쓴다. */
window.WarnCharts = (() => {
  const { el } = Qual;
  const NS = "http://www.w3.org/2000/svg";
  const DRIVERS = ["① 임차수요 압력", "② 주택공급·재고 여건", "③ 금융여건·상대가격", "④ 임대시장 수급·전환 구조", "⑤ 시장과열·단기 트리거", "⑥ 거시경기·금융시장 여건", "지역 고정효과"];
  const CLASSES = ["d1", "d2", "d3", "d4", "d5", "d6", "dx"];
  const driverClass = (name) => CLASSES[DRIVERS.indexOf(name)] ?? "dx";
  const monthLabel = (m) => `${String(m).slice(0, 4)}.${String(m).slice(4)}`;
  const pct = (v, d = 0) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
  const signed = (v, d = 3) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`);
  function svg(tag, attrs = {}) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  }
  function text(x, y, content, cls, anchor) {
    const t = svg("text", { x: x.toFixed(1), y: y.toFixed(1), class: cls });
    if (anchor) t.setAttribute("text-anchor", anchor);
    t.textContent = content;
    return t;
  }

  // ── 툴팁 하나를 모든 차트가 같이 쓴다. 값이 굵게 앞, 이름이 뒤. ──
  const tip = el("div", "wz-tip");
  document.body.append(tip);
  function showTip(rows, x, y) {
    tip.replaceChildren();
    for (const r of rows) {
      const line = el("div", "wz-tip-row");
      if (r.cls) line.append(el("i", `wz-key ${r.cls}`));
      line.append(el("strong", null, r.value), el("span", null, r.label));
      tip.append(line);
    }
    tip.classList.add("on");
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.max(8, Math.min(x + 14, window.innerWidth - w - 8))}px`;
    tip.style.top = `${y - h - 12 < 8 ? y + 18 : y - h - 12}px`;
  }
  const hideTip = () => tip.classList.remove("on");
  function hoverable(node, rowsFor) {
    node.addEventListener("pointermove", (ev) => showTip(rowsFor(), ev.clientX, ev.clientY));
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("focus", () => { const b = node.getBoundingClientRect(); showTip(rowsFor(), b.left + b.width / 2, b.top); });
    node.addEventListener("blur", hideTip);
  }

  function legend(items) {
    const box = el("div", "wz-legend");
    for (const it of items) {
      const s = el("span", "wz-legend-item");
      s.append(el("i", `wz-sw ${it.cls}`), el("span", null, it.label));
      box.append(s);
    }
    return box;
  }
  function driverLegend(names) {
    return legend(names.map((n) => ({ cls: driverClass(n), label: n })));
  }

  // 표 보기: 차트의 모든 값을 색 없이 읽을 수 있는 짝. rows 의 첫 칸은 행 머리글.
  function tableView(headers, rows, caption = "표로 보기") {
    const d = el("details", "wz-table");
    d.append(el("summary", null, caption));
    const wrap = el("div", "wz-table-wrap"), table = el("table"), thead = el("thead"), tbody = el("tbody"), tr = el("tr");
    for (const h of headers) tr.append(el("th", null, h));
    thead.append(tr);
    for (const r of rows) {
      const row = el("tr");
      r.forEach((c, i) => row.append(el(i ? "td" : "th", null, c == null ? "–" : String(c))));
      tbody.append(row);
    }
    table.append(thead, tbody); wrap.append(table); d.append(wrap);
    return d;
  }

  // ── 가로 막대 (HTML). rows: [{label, value, cls, sub, ref, tip, selected, onClick}] ──
  function hbars(rows, { max, format = (v) => v.toFixed(2), cls = "brand" } = {}) {
    const box = el("div", "wz-hbars");
    const m = max ?? (Math.max(...rows.map((r) => Math.abs(r.value) || 0)) || 1);
    for (const r of rows) {
      const row = el("div", `wz-hrow${r.selected ? " selected" : ""}${r.onClick ? " clickable" : ""}`);
      row.tabIndex = 0;
      const label = el("div", "wz-hlabel");
      if (r.key) label.append(el("i", `wz-sw ${r.key}`));
      label.append(el("span", null, r.label));
      if (r.sub) label.append(el("small", null, r.sub));
      const track = el("div", "wz-htrack"), bar = el("div", `wz-hbar ${r.cls || cls}`);
      bar.style.width = `${(Math.max(0, r.value) / m) * 100}%`;
      track.append(bar);
      if (r.ref != null) { const ref = el("i", "wz-href"); ref.style.left = `${(r.ref / m) * 100}%`; track.append(ref); }
      row.append(label, track, el("div", "wz-hval", format(r.value)));
      hoverable(row, () => r.tip || [{ value: format(r.value), label: r.label, cls: r.cls || cls }]);
      if (r.onClick) {
        row.addEventListener("click", r.onClick);
        row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); r.onClick(); } });
      }
      box.append(row);
    }
    return box;
  }

  // ── 히트맵 표: 값(0.5~1)을 한 가지 색의 밝기 단계로. 값은 칸 안에 그대로 적는다. ──
  function heatClass(v) {
    if (v == null) return null;
    const step = Math.min(8, Math.max(1, Math.ceil(((v - 0.5) / 0.5) * 8)));
    return `h${v <= 0.5 ? 1 : step}`;
  }
  function heatTable(rowLabels, colLabels, cell, { format = (v) => v.toFixed(2), corner = "" } = {}) {
    const table = el("table", "wz-heat"), thead = el("thead"), tbody = el("tbody"), tr = el("tr");
    tr.append(el("th", null, corner));
    for (const c of colLabels) tr.append(el("th", null, c));
    thead.append(tr);
    rowLabels.forEach((r, i) => {
      const row = el("tr");
      row.append(el("th", null, r));
      colLabels.forEach((c, j) => {
        const v = cell(i, j);
        const td = el("td", v == null ? "none" : `v ${heatClass(v)}`, v == null ? "–" : format(v));
        td.tabIndex = 0;
        hoverable(td, () => [{ value: v == null ? "채점 불가" : format(v), label: `${r} · ${c}` }]);
        row.append(td);
      });
      tbody.append(row);
    });
    table.append(thead, tbody);
    const ramp = el("div", "wz-ramp");
    ramp.append(el("span", null, "0.5 이하"));
    for (let i = 1; i <= 8; i++) ramp.append(el("i", `h${i}`));
    ramp.append(el("span", null, "1.0"));
    const wrap = el("div", "wz-table-wrap"); wrap.append(table, ramp);
    return wrap;
  }

  // ── 지역 시계열: 위 경보 확률(선) + 실제 사건(음영), 아래 동인별 기여(누적 막대) ──
  function timeline(t, { task, region }) {
    const W = 760, PL = 40, PR = 14, H1 = 150, GAP = 30, H2 = 140, AX = 22, H = H1 + GAP + H2 + AX;
    const n = t.month.length, slot = (W - PL - PR) / n, bw = Math.min(24, slot - 2);
    const x = (i) => PL + (i + 0.5) * slot;
    const y1 = (p) => H1 - 6 - p * (H1 - 24);
    const drivers = DRIVERS.filter((d) => t.contrib[d]);
    let span = 0.01;
    for (let i = 0; i < n; i++) {
      let up = 0, dn = 0;
      for (const d of drivers) { const v = t.contrib[d][i] || 0; if (v > 0) up += v; else dn -= v; }
      span = Math.max(span, up, dn);
    }
    const zero = H1 + GAP + H2 / 2, half = H2 / 2 - 6;
    const y2 = (v) => zero - (v * half) / span;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "wz-timeline", role: "img" });
    const title = svg("title"); title.textContent = `${region} ${task} 경보 확률과 동인별 기여, ${monthLabel(t.month[0])}–${monthLabel(t.month[n - 1])}`; root.append(title);
    for (let i = 0; i < n; i++) if (t.y[i]) root.append(svg("rect", { x: (x(i) - slot / 2).toFixed(1), y: 0, width: slot.toFixed(1), height: H1 + GAP + H2, class: "wz-event" }));
    for (const g of [0, 0.5, 1]) {
      root.append(svg("line", { x1: PL, x2: W - PR, y1: y1(g).toFixed(1), y2: y1(g).toFixed(1), class: "wz-grid-line" }));
      root.append(text(PL - 6, y1(g) + 4, `${g * 100}%`, "wz-axis", "end"));
    }
    root.append(text(PL, 12, `${task} 경보 확률 (앞으로 6개월)`, "wz-plot-label"));
    root.append(text(PL, H1 + GAP - 8, "동인별 기여 (확률 변화, 표본외 SHAP)", "wz-plot-label"));
    root.append(svg("line", { x1: PL, x2: W - PR, y1: zero, y2: zero, class: "wz-axis-line" }));
    root.append(text(PL - 6, zero + 4, "0", "wz-axis", "end"));
    root.append(text(PL - 6, y2(span) + 4, signed(span, 2), "wz-axis", "end"));
    root.append(text(PL - 6, y2(-span) + 4, signed(-span, 2), "wz-axis", "end"));
    for (let i = 0; i < n; i++) {
      let up = 0, dn = 0;
      for (const d of drivers) {
        const v = t.contrib[d][i];
        if (!v) continue;
        const h = (Math.abs(v) * half) / span;
        let yy;
        if (v > 0) { yy = y2(up + v); up += v; } else { yy = y2(dn); dn += v; }
        root.append(svg("rect", { x: (x(i) - bw / 2).toFixed(1), y: yy.toFixed(1), width: bw.toFixed(1), height: Math.max(h, 0.5).toFixed(1), class: `wz-seg ${driverClass(d)}` }));
      }
    }
    const pts = t.p.map((p, i) => (p == null ? null : `${x(i).toFixed(1)},${y1(p).toFixed(1)}`)).filter(Boolean).join(" ");
    root.append(svg("polyline", { points: pts, class: "wz-line" }));
    const last = n - 1;
    if (t.p[last] != null) {
      root.append(svg("circle", { cx: x(last).toFixed(1), cy: y1(t.p[last]).toFixed(1), r: 4, class: "wz-dot" }));
      root.append(text(x(last) - 8, y1(t.p[last]) - 8, pct(t.p[last]), "wz-end-label", "end"));
    }
    t.month.forEach((m, i) => { if (String(m).endsWith("01")) root.append(text(x(i), H - 6, String(m).slice(0, 4), "wz-axis", "middle")); });
    const cross = svg("line", { x1: 0, x2: 0, y1: 0, y2: H1 + GAP + H2, class: "wz-cross" });
    cross.style.opacity = "0";
    const hit = svg("rect", { x: PL, y: 0, width: W - PL - PR, height: H1 + GAP + H2, class: "wz-hit", tabindex: 0 });
    root.append(cross, hit);
    let current = last;
    const rowsAt = (i) => [
      { value: monthLabel(t.month[i]), label: t.y[i] ? `실제 ${task} 발생` : "사건 없음" },
      { value: pct(t.p[i], 1), label: "경보 확률", cls: "ink" },
      ...drivers.map((d) => ({ value: signed(t.contrib[d][i]), label: d, cls: driverClass(d) })),
    ];
    const focusAt = (i, cx, cy) => {
      current = i;
      cross.setAttribute("x1", x(i).toFixed(1)); cross.setAttribute("x2", x(i).toFixed(1)); cross.style.opacity = "1";
      if (cx == null) { const b = root.getBoundingClientRect(); cx = b.left + (x(i) * b.width) / W; cy = b.top + (y1(t.p[i] ?? 0) * b.height) / H; }
      showTip(rowsAt(i), cx, cy);
    };
    hit.addEventListener("pointermove", (ev) => {
      const b = root.getBoundingClientRect();
      const px = ((ev.clientX - b.left) * W) / b.width;
      focusAt(Math.max(0, Math.min(n - 1, Math.floor((px - PL) / slot))), ev.clientX, ev.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.style.opacity = "0"; hideTip(); });
    hit.addEventListener("focus", () => focusAt(current));
    hit.addEventListener("blur", () => { cross.style.opacity = "0"; hideTip(); });
    hit.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft") { ev.preventDefault(); focusAt(Math.max(0, current - 1)); }
      if (ev.key === "ArrowRight") { ev.preventDefault(); focusAt(Math.min(n - 1, current + 1)); }
    });
    const table = tableView(["월", "경보 확률", "실제 사건", ...drivers], t.month.map((m, i) => [monthLabel(m), pct(t.p[i], 1), t.y[i] ? "발생" : "", ...drivers.map((d) => signed(t.contrib[d][i]))]));
    return { svg: root, legend: legend([{ cls: "ink line", label: "경보 확률" }, { cls: "event", label: `실제 ${task} 발생 월` }, ...drivers.map((d) => ({ cls: driverClass(d), label: d }))]), table };
  }

  return { DRIVERS, driverClass, monthLabel, pct, signed, legend, driverLegend, tableView, hbars, heatTable, timeline };
})();
