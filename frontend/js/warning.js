/* 조기경보 페이지 (warning.html). data/warning.json(정적) → /warning(API) 순으로 읽고, 절 탭(#overview …)별로 그린다.
   필터 줄(패널·과제·지역)은 모든 절에 공통으로 적용된다. */
(() => {
  const { el, list, sectionTitle } = Qual;
  const C = window.WarnCharts;
  const container = document.querySelector("#warning-content");
  const SECTIONS = ["overview", "regions", "models", "drivers", "setup"];
  const SPAN = "2021~2025";
  const MODEL_LABEL = { "로짓": "부분통합 로짓", "ET": "Extra-Trees", "기준(학습빈도)": "기준(학습 구간 사건 빈도)" };
  let data, panel = "서울25구", task = "급락", region = "";
  const active = () => (SECTIONS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview");
  const key = () => `${panel}|${task}`;
  const regionsOf = () => Object.keys(data.timeline[key()] || {});
  function ensureRegion() {
    const rs = regionsOf();
    if (!rs.includes(region)) region = rs.includes("서울") ? "서울" : rs.includes("강남구") ? "강남구" : rs[0] || "";
  }
  const summaryRows = () => data.summary.filter((s) => s.panel === panel && s.task === task && s.span === SPAN);
  const bestRow = () => summaryRows().filter((s) => s.set === "M3").sort((a, b) => (b.auc ?? 0) - (a.auc ?? 0))[0];
  const latest = (reg) => { const t = data.timeline[key()][reg]; return t ? { p: t.p[t.p.length - 1], month: t.month[t.month.length - 1] } : null; };

  function card(title, sub, ...children) {
    const c = el("article", "wz-card");
    c.append(el("h4", null, title));
    if (sub) c.append(el("p", "sub", sub));
    c.append(...children);
    return c;
  }
  function select(labelText, options, value, onChange) {
    const label = el("label", null, labelText), s = el("select");
    for (const o of options) { const opt = el("option", null, o); opt.value = o; opt.selected = o === value; s.append(opt); }
    s.addEventListener("change", () => onChange(s.value));
    label.append(s);
    return label;
  }
  function filters() {
    const row = el("div", "wz-filters");
    row.append(
      select("패널", ["17시도", "서울25구"], panel, (v) => { panel = v; ensureRegion(); render(); }),
      select("과제", ["급락", "급등"], task, (v) => { task = v; ensureRegion(); render(); }),
      select("지역", regionsOf(), region, (v) => { region = v; render(); }),
      el("span", "wz-scope", "아래 모든 수치와 그림에 함께 적용됩니다"),
    );
    return row;
  }

  // ── 핵심 결과 ──
  function overview() {
    container.append(sectionTitle("핵심 결과", "1차 기준선 실험(2026-10-02)의 표본외 성적입니다. 모든 수치는 시험연도 2021~2025에서 모형이 보지 못한 자료로 계산했습니다."));
    const best = bestRow(), m1 = summaryRows().filter((s) => s.set === "M1").sort((a, b) => (b.auc ?? 0) - (a.auc ?? 0))[0], base = summaryRows().find((s) => s.set === "-");
    const now = latest(region);
    const hero = el("div", "wz-hero");
    const heroCard = el("article", "wz-card");
    heroCard.append(el("p", "sub", `${region} · ${now ? C.monthLabel(now.month) : ""} 기준 ${task} 경보 지수`));
    const num = el("p", "wz-hero-num", now && now.p != null ? `${(now.p * 100).toFixed(0)}` : "–"); num.append(el("small", null, "%"));
    heroCard.append(num, el("p", "note", `앞으로 6개월 안에 월세가 ${task === "급락" ? "크게 내릴" : "크게 오를"} 확률의 표본외 추정치(Extra-Trees · M3). 시험 구간 평균 사건 비율은 ${C.pct(base?.rate)}입니다.`));
    const strip = el("dl", "summary-strip");
    for (const [dt, dd] of [["가장 좋은 모형 AUC (M3)", best ? `${best.auc?.toFixed(2)} · ${MODEL_LABEL[best.model] || best.model}` : "–"], ["가격 관성만 쓴 모형 AUC (M1)", m1 ? `${m1.auc?.toFixed(2)} · ${MODEL_LABEL[m1.model] || m1.model}` : "–"], ["시험 행수 · 사건 비율", base ? `${base.n.toLocaleString("ko-KR")}행 · ${C.pct(base.rate, 1)}` : "–"]]) {
      const item = el("div"); item.append(el("dt", null, dt), el("dd", null, dd)); strip.append(item);
    }
    hero.append(heroCard, strip);
    container.append(hero);
    const findings = el("ol", "wz-findings");
    for (const [strong, rest] of [
      ["17개 시도에서는 구조 변수가 가격 관성에 정보를 더합니다.", " 급등 AUC(연도 평균)가 로짓 M1 0.80 → M3 0.87, 급락은 Extra-Trees M1 0.81 → M3 0.94로 올라갑니다."],
      ["서울 25개 구는 가격 관성만으로는 거의 맞히지 못합니다.", " 방향·급락에서 로짓 M1은 0.43~0.50(무작위 수준)이고, 지역 구조·거시 변수를 더한 M2·M3는 0.72~0.93입니다."],
      ["상위 변수 대부분이 전국 공통 변수입니다.", " 물가·임금 수준, M2, 기준금리·CD금리가 맨 위에 옵니다. 물가·임금 '수준'은 계속 오르기만 해서 시점을 외우는 역할을 했을 수 있어 1순위 수정 대상입니다."],
      ["임계값 때문에 채점하지 못한 해가 많습니다.", " 학습 구간(2016~2020)이 조용해 기준선이 낮게 잡혔고, 서울 25개 구는 2021·2024·2025년이 모두 '상승'으로 분류돼 급락 사건이 없습니다. 서울 구의 5년 평균은 사실상 2022~2023년 두 해 값입니다."],
      ["튜닝 없는 기준선입니다.", " 변수 가공과 임계값 방식을 정한 뒤 다시 돌리는 것이 다음 단계이며, 이 화면의 확률은 학습용 추정치입니다."],
    ]) { const li = el("li"); li.append(el("strong", null, strong), document.createTextNode(rest)); findings.append(li); }
    container.append(card("1차 결과에서 읽히는 것", "실험 보고서의 결론을 그대로 옮겼습니다. 패널·과제를 바꿔 위 숫자와 대조해 보세요.", findings));
    const notice = el("aside", "notice-box");
    notice.append(el("h4", null, "이 화면으로 알 수 있는 것과 없는 것"), list(["경보 확률은 '앞으로 6개월 안에 월세지수가 학습 구간 기준으로 큰 폭 움직일 확률'의 추정치이며 가격 예측값이 아닙니다.", "AUC 는 사건이 난 지역·월을 안 난 곳보다 높게 점수 매길 확률입니다. 0.5가 무작위, 1.0이 완벽입니다.", "표본외 결과지만 한 번의 실험이라 재현·튜닝 전에는 '방향과 크기'만 읽습니다. 투자·계약 판단의 근거로 쓰지 않습니다."]));
    container.append(notice);
  }

  // ── 지역별 경보 ──
  function regions() {
    container.append(sectionTitle("지역별 경보", "선(경보 확률)이 오르는데 음영(실제 사건)이 뒤따르면 경보가 맞은 것입니다. 아래 막대는 그 달 확률을 끌어올린(+)·내린(−) 동인별 기여입니다."));
    const t = data.timeline[key()]?.[region];
    const grid = el("div", "wz-grid");
    if (t) {
      const chart = C.timeline(t, { task, region });
      const wide = card(`${region} · ${task} 경보 확률과 동인별 기여`, `Extra-Trees · M3, ${C.monthLabel(t.month[0])}–${C.monthLabel(t.month[t.month.length - 1])}. 마우스를 올리거나 키보드(←→)로 달을 고르면 값이 보입니다.`, chart.legend, chart.svg, chart.table);
      wide.classList.add("wide");
      grid.append(wide);
    } else grid.append(el("p", "empty-state", "이 패널·과제·지역의 시계열이 없습니다."));
    const rows = regionsOf().map((r) => ({ r, v: latest(r)?.p ?? 0 })).sort((a, b) => b.v - a.v);
    const bars = C.hbars(rows.map(({ r, v }) => ({ label: r, value: v, selected: r === region, onClick: () => { region = r; render(); }, tip: [{ value: C.pct(v, 1), label: `${r} 최신 경보 확률`, cls: "brand" }] })), { max: Math.max(0.05, ...rows.map((x) => x.v)) * 1.05, format: (v) => C.pct(v, 0) });
    grid.append(card(`지역별 최신 경보 확률 (${rows[0] ? C.monthLabel(latest(rows[0].r).month) : ""})`, "행을 누르면 그 지역의 시계열로 바뀝니다. 같은 패널·과제 안에서 비교합니다.", bars, C.tableView(["지역", "경보 확률"], rows.map(({ r, v }) => [r, C.pct(v, 1)]))));
    container.append(grid);
  }

  // ── 모형 비교 ──
  function models() {
    container.append(sectionTitle("모형 비교", "변수를 더할수록(M1 → M3) 얼마나 나아지는지, 모형별로 봅니다. 막대는 시험연도별 AUC 의 평균이고 세로선은 기준(0.5, 무작위)입니다."));
    const rows = summaryRows();
    const grid = el("div", "wz-grid");
    for (const model of ["로짓", "ET"]) {
      const mine = ["M1", "M2", "M3"].map((set) => rows.find((s) => s.set === set && s.model === model)).filter(Boolean);
      const bars = C.hbars(mine.map((s) => ({ label: s.set, sub: data.setup.sets[s.set], value: s.auc ?? 0, ref: 0.5, tip: [{ value: s.set, label: data.setup.sets[s.set] }, { value: s.auc?.toFixed(3), label: "AUC 연도 평균", cls: "brand" }, { value: `${s.aucLo?.toFixed(2)}–${s.aucHi?.toFixed(2)}`, label: "연도별 최저–최고" }, { value: s.pooled?.toFixed(3), label: "통합 AUC" }, { value: s.prauc?.toFixed(3) ?? "–", label: "PR-AUC" }, { value: s.ll?.toFixed(3), label: "로그손실" }] })), { max: 1 });
      grid.append(card(MODEL_LABEL[model], `${panel} · ${task} · 시험 ${SPAN}`, bars, C.tableView(["변수 묶음", "AUC 평균", "최저", "최고", "통합 AUC", "PR-AUC", "로그손실"], mine.map((s) => [s.set, s.auc?.toFixed(3), s.aucLo?.toFixed(2), s.aucHi?.toFixed(2), s.pooled?.toFixed(3), s.prauc?.toFixed(3), s.ll?.toFixed(3)]))));
    }
    const base = rows.find((s) => s.set === "-");
    grid.append(card("기준 모형", "학습 구간의 사건 빈도만으로 모든 지역·월에 같은 확률을 매긴 모형입니다. AUC 0.5가 정의상 출발선입니다.", el("p", "note", base ? `PR-AUC ${base.prauc?.toFixed(3) ?? "–"} (= 사건 비율 ${C.pct(base.rate, 1)}) · 로그손실 ${base.ll?.toFixed(3)} · 시험 ${base.n.toLocaleString("ko-KR")}행` : "–")));
    const folds = data.fold.filter((f) => f.panel === panel && f.task === task && f.set !== "-");
    const years = [...new Set(folds.map((f) => f.year))].sort(), cols = [];
    for (const set of ["M1", "M2", "M3"]) for (const model of ["로짓", "ET"]) cols.push({ set, model, label: `${set} ${model}` });
    const heat = C.heatTable(years.map(String), cols.map((c) => c.label), (i, j) => folds.find((f) => f.year === years[i] && f.set === cols[j].set && f.model === cols[j].model)?.auc ?? null, { corner: "시험연도" });
    const rates = years.map((y) => folds.find((f) => f.year === y)?.rate);
    const heatCard = card("시험연도별 AUC", "연도마다 사건이 몰린 정도가 달라 성적이 크게 흔들립니다. '–'는 그 해에 사건이 없거나 모두 사건이라 채점할 수 없는 해입니다.", heat, el("p", "note", `연도별 사건 비율: ${years.map((y, i) => `${y} ${C.pct(rates[i], 0)}`).join(" · ")}`));
    heatCard.classList.add("wide");
    grid.append(heatCard);
    container.append(grid);
  }

  // ── 무엇이 움직였나 ──
  function drivers() {
    container.append(sectionTitle("무엇이 움직였나", "Extra-Trees · M3 모형의 표본외 SHAP 입니다. 동인별 비중은 행별 |기여| 합의 평균, 변수별 비중은 평균 |SHAP| 의 비율입니다."));
    const group = data.shapGroup.filter((s) => s.panel === panel && s.task === task && s.model === "ET");
    const top = data.shapTop.filter((s) => s.panel === panel && s.task === task && s.model === "ET").slice(0, 12);
    const grid = el("div", "wz-grid");
    grid.append(card("동인별 기여 비중", "여섯 동인과 지역 고정효과가 예측을 얼마나 움직였는지.", C.hbars(group.map((g) => ({ label: g.driver, value: g.share, cls: C.driverClass(g.driver), key: C.driverClass(g.driver), tip: [{ value: C.pct(g.share, 1), label: g.driver, cls: C.driverClass(g.driver) }] })), { max: Math.max(...group.map((g) => g.share), 0.01), format: (v) => C.pct(v, 1) }), C.tableView(["동인", "비중"], group.map((g) => [g.driver, C.pct(g.share, 1)]))));
    const varLabel = (v) => { const [name, tf] = v.split("|"); return { name: name.replace(/^서울_/, "서울 ").replace(/_/g, " "), tf: tf || "" }; };
    grid.append(card("상위 12개 변수", "색은 변수가 속한 동인입니다. 평균 SHAP 부호가 +면 그 변수가 커질 때 확률을 높이는 쪽으로 작용했습니다.", C.hbars(top.map((s) => { const { name, tf } = varLabel(s.var); return { label: name, sub: tf, value: s.share, cls: C.driverClass(s.driver), key: C.driverClass(s.driver), tip: [{ value: C.pct(s.share, 1), label: "기여 비중", cls: C.driverClass(s.driver) }, { value: C.signed(s.mean, 4), label: "평균 SHAP(부호)" }, { value: s.driver, label: "동인" }] }; }), { max: Math.max(...top.map((s) => s.share), 0.01), format: (v) => C.pct(v, 1) }), C.driverLegend(C.DRIVERS.filter((d) => top.some((s) => s.driver === d))), C.tableView(["변수", "가공", "동인", "비중", "평균 SHAP"], top.map((s) => { const { name, tf } = varLabel(s.var); return [name, tf, s.driver, C.pct(s.share, 1), C.signed(s.mean, 4)]; }))));
    container.append(grid);
  }

  // ── 실험 설정 · 한계 ──
  function setup() {
    container.append(sectionTitle("실험 설정 · 한계", `${data.experiment}. 자료 내보내기 ${data.generated_at}.`));
    const dl = el("dl", "wz-setup");
    for (const [k, label] of [["input", "입력 자료"], ["sample", "표본"], ["target", "목표 변수"], ["threshold", "임계값"], ["test", "검증 방식"], ["models", "모형"], ["shap_note", "SHAP 단위"]]) dl.append(el("dt", null, label), el("dd", null, data.setup[k]));
    dl.append(el("dt", null, "변수 묶음"), el("dd", null, Object.entries(data.setup.sets).map(([k, v]) => `${k}: ${v}`).join(" · ")));
    const grid = el("div", "wz-grid");
    grid.append(card("설정", null, dl));
    const th = data.thresholds.filter((t) => t["패널"] === panel);
    const used = data.used[panel] || {};
    const usedRows = Object.entries(used).flatMap(([set, byDriver]) => Object.entries(byDriver).map(([d, n]) => [set, d, n]));
    grid.append(card("임계값과 사용 변수", `${panel} 패널. 임계값은 매 시험연도 직전 학습 구간에서만 정합니다(6개월 변화율 %).`, C.tableView(["시험연도", "보합 폭 ε", "급등 δ↑", "급락 δ↓"], th.map((t) => [t["시험연도"], `±${(t.eps).toFixed(2)}%`, `+${t.up.toFixed(2)}%`, `−${t.dn.toFixed(2)}%`]), "임계값 표"), C.tableView(["묶음", "동인", "변수 수"], usedRows, "사용 변수 수(동인별)")));
    const excl = el("p", "wz-excl", (data.excluded[panel] || []).join("  ·  "));
    const exclCard = card("결측·상수로 제외된 변수", `${panel} 패널에서 학습 구간에 값이 없거나 변하지 않아 뺀 변수입니다.`, excl);
    exclCard.classList.add("wide");
    grid.append(exclCard);
    container.append(grid);
  }

  function render() {
    const section = active();
    Qual.setActive(document.querySelector("#warning-tabs"), section);
    if (!data) return;
    ensureRegion();
    container.replaceChildren(filters());
    ({ overview, regions, models, drivers, setup })[section]();
  }
  window.addEventListener("hashchange", render);
  render();
  Qual.loadContent("/warning", "warning.json", (value) => {
    if (!value.summary || !value.timeline || !value.setup) throw new Error("Invalid warning data");
    if (data && data.generated_at === value.generated_at && data.experiment === value.experiment) return;
    data = value; render();
  }, "실험 결과는 학습용 추정치입니다. 확률의 뜻과 한계는 '핵심 결과' 절을 함께 읽으세요.", "generated_at");
})();
