// Overview 3 x 2 타일 (index.html 전용). indicators.js 가 먼저 로드되어 있어야 한다.
// 타일마다 "주 지표" 하나(큰 숫자 + 스파크라인)와 "보조 지표" 두세 개(작은 숫자 + 스파크라인)를 보여 준다.
// 지역은 헤더의 지역 선택을 따르고, 그 지역에 없는 계열은 서울 → 전국 순으로 대체해 실제 지역명을 표시한다.

(() => {
  const I = window.Indicators;
  const { el } = I;

  // ratio: 분자 항목 / 분모 항목 × 100 을 새 계열로 만든다 (월세 비중 등)
  const TILES = {
    prices: {
      primary: { id: "V002", item: "지수", label: "아파트 매매가격지수" },
      secondary: [
        { id: "V026", item: "지수", label: "전세가격지수" },
        { id: "V001", item: "지수", label: "월세통합가격지수" },
      ],
    },
    transactions: {
      primary: { id: "V036", item: "동(호)수", label: "아파트 매매거래량", unit: "호" },
      secondary: [
        { id: "V035", item: "동(호)수", label: "전체 거래량(매매·증여 등)", unit: "호" },
        { id: "V007", item: "거래(해제 제외)", label: "서울 매매 실거래 신고", unit: "건" },
      ],
    },
    rent: {
      primary: { id: "V003", item: "매매가격 대비 전세가격", label: "아파트 전세가율" },
      secondary: [
        { id: "V004", item: "전월세 전환율", label: "전월세전환율" },
        { id: "V006", item: "월세(보증부 포함)", ratio: "전체", label: "월세 비중(전월세 신고 중)", unit: "%" },
      ],
    },
    supply: {
      primary: { id: "V023", item: "준공", label: "아파트 준공", unit: "호" },
      secondary: [
        { id: "V021", item: "인허가", label: "아파트 인허가", unit: "호" },
        { id: "V022", item: "착공", label: "아파트 착공", unit: "호" },
        { id: "V038", item: "미분양현황", label: "미분양 주택", unit: "호" },
      ],
    },
    finance: {
      primary: { id: "V056", item: "주택담보대출", label: "주택담보대출 금리(신규)" },
      secondary: [
        { id: "V043", item: "한국은행 기준금리", label: "기준금리" },
        { id: "V057", item: null, label: "전세자금대출 금리(신규)" },
        { id: "V050", item: "주택관련대출-예금은행", label: "지역 주택관련대출 잔액", unit: "십억원" },
      ],
    },
    sentiment: {
      primary: { id: "V037", item: "지수", label: "주택시장 소비심리지수" },
      secondary: [
        { id: "V031", item: "지수", label: "매매수급동향" },
        { id: "V032", item: "지수", label: "전세수급동향" },
        { id: "V005", item: "지수", label: "월세수급동향" },
      ],
    },
  };

  function pickItem(variable, key) {
    if (key && variable.items[key]) return variable.items[key];
    return Object.values(variable.items)[0];
  }

  // 한 지표 설정 -> { series, unit, regionName } (없으면 null)
  async function resolve(spec, region) {
    const variable = await I.loadVariable(spec.id);
    const item = pickItem(variable, spec.item);
    if (!item) return null;
    const picked = I.pick(item, region);
    if (!picked) return null;
    let series = picked.series, unit = spec.unit ?? item.unit;
    if (spec.ratio) {
      const den = variable.items[spec.ratio]?.regions[picked.name];
      if (!den) return null;
      series = I.ratioSeries(series, den);
      unit = "%";
    }
    return { series, unit, regionName: picked.name };
  }

  async function renderTile(key, region) {
    const body = document.querySelector(`.tile-body[data-tile="${key}"]`);
    if (!body) return;
    const cfg = TILES[key];
    body.classList.add("ind-tile");
    try {
      const [primary, ...secondary] = await Promise.all([
        resolve(cfg.primary, region),
        ...cfg.secondary.map((s) => resolve(s, region).catch(() => null)),
      ]);
      body.replaceChildren();
      if (!primary) throw new Error("주 지표 없음");
      body.append(I.seriesBlock({ ...primary, label: cfg.primary.label }));
      const list = el("div", "ind-secondary");
      secondary.forEach((s, i) => {
        if (s) list.append(I.seriesBlock({ ...s, label: cfg.secondary[i].label, compact: true }));
      });
      body.append(list);
    } catch (err) {
      console.error(key, err);
      body.replaceChildren(el("p", "tile-placeholder", t("tile.error")));
    }
  }

  function renderAll(region) {
    for (const key of Object.keys(TILES)) renderTile(key, region);
  }

  // 헤더 지역 선택: 17개 시도 + 서울 25개 구
  function buildRegionSelect(index) {
    const select = document.querySelector("#region-select");
    if (!select) return;
    const groups = [["시도", index.sido], ["서울 자치구", index.seoul_gu]];
    for (const [label, names] of groups) {
      const group = el("optgroup"); group.label = label;
      for (const name of names) { const opt = el("option", null, name); opt.value = name; group.append(opt); }
      select.append(group);
    }
    select.value = I.region();
    if (!select.value) select.value = I.DEFAULT_REGION;
    select.addEventListener("change", () => I.setRegion(select.value));
  }

  async function init() {
    try {
      const index = await I.loadIndex();
      buildRegionSelect(index);
      const note = document.querySelector("#tiles-note");
      if (note) note.textContent = `자료 갱신 ${index.generated_at} · 출처: KOSIS · 한국부동산원 R-ONE · 한국은행 ECOS · 국토부 실거래 (DFMBA 파이프라인)`;
    } catch (err) {
      console.error(err);
      for (const body of document.querySelectorAll(".tile-body")) body.replaceChildren(el("p", "tile-placeholder", t("tile.error")));
      return;
    }
    renderAll(I.region());
    I.onRegionChange(renderAll);
  }

  init();
})();
