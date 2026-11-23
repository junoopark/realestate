// Home 우측 상단 'KHMI에게 물어보세요' 질문창 (MOCK)
// - 실제 서비스에서는 홈페이지 정보(지표 · 정책 · 부동산 기초)를 근거로 LLM 이 답할 자리다. 지금은 LLM 호출 없이,
//   질문의 단어를 보고 사이트 안 자료(지표 계열, data/policies.json, data/knowledge.json, 메뉴 구성)에서 답을 골라 문장으로 만든다.
// - 답은 textContent 로만 넣어 질문 글이 HTML 로 해석되지 않는다.
// 전역(sample · variables · drivers · describe · el)은 factors.js·notes.js, 동향 계산은 home-outlook.js 에서 온다. 호출 시점에 읽는다.

(() => {
  const form = document.querySelector("#ask-form");
  if (!form) return;
  const input = document.querySelector("#ask-input");
  const send = document.querySelector("#ask-send");
  const panel = document.querySelector("#ask-panel");
  const body = document.querySelector("#ask-body");
  const wrap = document.querySelector("#ask-wrap");

  const SUGGESTIONS = ["서울 월세 요즘 어때?", "부산 최근 6개월 동향과 전망", "전세가율이 뭐야?", "최근 주요 정책은?", "데이터는 어디서 가져오나요?"];
  const DEFAULT_REGION = "서울";
  const MOCK_NOTE = "mock 응답입니다. 실제 서비스에서는 LLM이 홈페이지 정보를 근거로 답변합니다.";
  const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  let knowledge = null;
  let knowledgeTried = false;
  let token = 0;
  let lastAnswered = false;

  async function loadKnowledge() {
    if (knowledge || knowledgeTried) return knowledge;
    knowledgeTried = true;
    knowledge = await fetch("data/knowledge.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
    return knowledge;
  }

  // ── 질문 읽기 ───────────────────────────────────────
  const norm = (s) => s.replace(/\s+/g, "").toLowerCase();
  const has = (qn, ...words) => words.some((w) => qn.includes(w));
  const REGION_ALIAS = { 충청북도: "충북", 충청남도: "충남", 전라북도: "전북", 전라남도: "전남", 경상북도: "경북", 경상남도: "경남", 제주도: "제주" };
  function findRegion(qn) {
    for (const [k, v] of Object.entries(REGION_ALIAS)) if (qn.includes(k)) return v;
    return sample?.regions.sido.find((r) => qn.includes(r)) || null;
  }
  function findMonths(qn) {
    const near = (n) => [1, 3, 6, 12, 24].reduce((a, b) => (Math.abs(b - n) < Math.abs(a - n) ? b : a));
    let m = qn.match(/(\d+)개월/);
    if (m) return near(+m[1]);
    m = qn.match(/(\d+)년/);
    if (m) return near(+m[1] * 12);
    if (has(qn, "반년", "반기")) return 6;
    if (has(qn, "지난달", "이번달", "한달")) return 1;
    return null;
  }
  const METRIC_KEYS = [
    { id: "V003", words: ["전세가율"] },
    { id: "V004", words: ["전월세전환율", "전환율"] },
    { id: "V005", words: ["수급"] },
    { id: "V037", words: ["심리"] },
    { id: "V038", words: ["미분양"] },
    { id: "V026", words: ["전세"] },
    { id: "V001", words: ["월세"] },
    { id: "V002", words: ["매매", "집값", "아파트값"] },
    { id: "V056", words: ["대출금리", "주담대", "주택담보"], nation: true },
    { id: "V043", words: ["기준금리", "금리"], nation: true },
  ];

  // ── 답 만들기: 각 함수는 { paras, bullets, links, src } 또는 null ──
  const needData = () => ({ paras: ["지표 데이터를 아직 불러오는 중이에요. 잠시 후 다시 물어봐 주세요."], links: [] });

  function answerOutlook(q, qn) {
    if (!has(qn, "전망", "동향", "예측", "예상", "앞으로", "오를까", "내릴까", "시장상황", "요즘", "분위기", "어때", "어떄")) return null;
    // '어때/요즘'만 있는 질문은 지표를 짚은 경우(예: 서울 전세 어때)에는 지표 답으로 넘긴다
    const metricHit = METRIC_KEYS.find((k) => has(qn, ...k.words));
    if (metricHit && !has(qn, "전망", "동향", "예측", "예상", "앞으로", "오를까", "내릴까", "시장상황")) return null;
    if (!sample) return needData();
    const region = findRegion(qn) || DEFAULT_REGION;
    const months = findMonths(qn) || 3;
    const c = KHMI_OUTLOOK.compute(region, months);
    if (!c) return { paras: [`${region}은 월세 지수 자료가 없어 동향과 전망을 만들지 못했어요.`], links: [] };
    const n = KHMI_OUTLOOK.narrative(c);
    return {
      paras: [
        `**${region} · 최근 ${c.months}개월** 동향은 **${c.trend.label}(${olPct(c.main.change)})**, 향후 3개월 전망은 **${c.fc.label}(${olPct(c.fc.cum3)})**으로 계산됩니다.`,
        n.trend[0],
        n.outlook[0],
      ],
      links: [{ label: "동향·전망 카드에서 자세히 보기", run: () => KHMI_OUTLOOK.show(region, months) }],
      src: "근거: 월세통합가격지수 · 전세·매매가격지수 · 월세 수급동향 등 대시보드 지표",
    };
  }

  function answerPolicy(q, qn) {
    if (!has(qn, "정책", "대책", "규제", "세제", "발표")) return null;
    const items = (typeof policyData !== "undefined" && policyData?.policies ? policyData.policies : [])
      .slice().sort((a, b) => (a.published_at < b.published_at ? 1 : -1)).slice(0, 3);
    const links = [{ label: "부동산 정책 »", href: "policies.html" }, { label: "정책 히스토리", href: "policies.html#history" }];
    if (!items.length) return { paras: ["정책 자료를 아직 불러오지 못했어요. 부동산 정책 페이지에서 직접 확인할 수 있어요."], links };
    return {
      paras: ["홈페이지에 정리된 **최근 주요 정책**입니다."],
      bullets: items.map((p) => `**${p.title}** (${p.agency}, ${p.published_at}) — ${p.summary.length > 90 ? `${p.summary.slice(0, 90).trim()}…` : p.summary}`),
      links,
      src: "근거: 부동산 정책 페이지의 주요 정책 정리",
    };
  }

  function answerGuide(q, qn) {
    const links = [];
    let paras = null;
    if (has(qn, "로그인", "계정", "회원", "구글")) {
      paras = ["화면 오른쪽 위의 **로그인** 버튼으로 Google 계정에 로그인합니다. 로그인하면 차트·지도의 데이터를 내려받을 수 있어요."];
    } else if (has(qn, "다운로드", "내려받", "엑셀", "csv")) {
      paras = ["차트와 지도 오른쪽 위의 **내려받기** 버튼에서 표 형태 파일로 받을 수 있어요. 로그인 후에 사용할 수 있습니다."];
    } else if (has(qn, "출처", "어디서", "기관")) {
      paras = ["지표는 **한국부동산원 R-ONE, 한국은행 ECOS, 통계청 KOSIS, 국토교통부(실거래가 공개시스템·공공데이터포털), 행정안전부, 국토연구원**의 공공 통계를 모아 보여줍니다."];
      links.push({ label: "데이터·방법", href: "about.html#data" });
    } else if (has(qn, "이용통계", "조회수", "인기")) {
      paras = ["이용 통계 페이지에서 기간별 다운로드·지표 조회·정책 클릭 순위를 볼 수 있어요. 개인 식별 정보는 없습니다."];
      links.push({ label: "이용 통계", href: "usage.html" });
    } else if (has(qn, "동인")) {
      paras = ["임대시장에 영향을 주는 지표를 **6개 동인**으로 나눕니다."];
      return { paras, bullets: (drivers || []).map((d) => `**${NUMS[d.no - 1]} ${d.name}** — ${d.question}`), links: [{ label: "부동산 대시보드 »", href: "#overview" }] };
    } else if (has(qn, "메뉴", "기능", "페이지", "사이트", "소개", "kh", "뭐하는", "무슨서비스")) {
      paras = ["KHMI는 흩어진 주택시장 공공 통계를 한곳에 모아 차트와 짧은 해설로 보여주는 서비스예요."];
      return {
        paras,
        bullets: ["**Home** — 가격 동향 · 이달의 차트 · 주요 정책 · 시도별 상승률 지도", "**부동산 대시보드** — 6개 동인별 지표와 시계열 차트", "**부동산 정책** — 주요 정책 정리 · 새 발표 모니터링 · 정책 히스토리", "**About · 부동산 기초** — 사이트 소개와 용어·계약 절차 학습 자료"],
        links: [{ label: "사이트 소개", href: "about.html#intro" }],
      };
    }
    return paras ? { paras, links } : null;
  }

  function answerMetric(q, qn) {
    const key = METRIC_KEYS.find((k) => has(qn, ...k.words));
    if (!key) return null;
    if (!sample) return needData();
    const region = key.nation ? "전국" : findRegion(qn) || DEFAULT_REGION;
    const m = olMetric(key.id, region);
    const v = variables.find((x) => x.id === (sample.aliases?.[key.id] || key.id));
    if (!m || !v) return { paras: [`${region}의 해당 지표 자료는 없어요. 지표는 17개 시도 단위로 제공됩니다.`], links: [] };
    const d = describe(v, m, region);
    const driver = drivers.find((x) => x.id === v.driver);
    const paras = [`**${d.headline}**`, ...d.body.slice(0, 2)];
    if (!key.nation && !findRegion(qn)) paras.push("지역을 말씀하지 않아 서울 기준으로 답했어요. 다른 지역은 시도 이름을 함께 물어봐 주세요.");
    return {
      paras,
      links: driver ? [{ label: `${NUMS[driver.no - 1]} ${driver.name} 보기`, href: `#${driver.id}` }] : [],
      src: `근거: ${m.source || v.source} · ${periodLabel(m.periods[m.periods.length - 1], true)}까지`,
    };
  }

  function answerDriver(q, qn) {
    const d = (drivers || []).find((x) => has(qn, x.name.replace(/\s|·/g, ""), x.short.replace(/\s/g, ""), ...x.subareas.filter((s) => s.length > 1)));
    const link = (x) => ({ label: `${NUMS[x.no - 1]} ${x.name} 보기`, href: `#${x.id}` });
    if (d) {
      const vars = variables.filter((v) => v.driver === d.id).slice(0, 5).map((v) => v.name);
      return {
        paras: [`**${NUMS[d.no - 1]} ${d.name}** 동인 — 핵심 질문: “${d.question}”`, `${d.description}.`, vars.length ? `대표 지표: ${vars.join(", ")} 등.` : ""].filter(Boolean),
        links: [link(d)],
        src: "근거: 부동산 대시보드 동인 분류(데이터사전)",
      };
    }
    const v = (variables || []).find((x) => norm(x.name).length > 2 && qn.includes(norm(x.name)));
    if (!v) return null;
    const driver = drivers.find((x) => x.id === v.driver);
    return {
      paras: [`**${v.name}** — ${v.source}에서 ${v.freq === "월" || v.freq === "월간" ? "월" : v.freq} 단위로 공표하는 지표입니다. 제공 지역은 ${v.region}이에요.`, variableProse(v)].filter(Boolean),
      links: driver ? [link(driver)] : [],
      src: "근거: 부동산 대시보드 데이터사전",
    };
  }

  async function answerGlossary(q, qn) {
    const k = await loadKnowledge();
    if (!k?.glossary) return null;
    let best = null;
    for (const g of k.glossary) {
      const tokens = g.term.split(/[·()（）]/).map((s) => s.trim().toLowerCase()).filter((s) => s.length >= 2);
      for (const tk of tokens) if (qn.includes(tk) && (!best || tk.length > best.len)) best = { g, len: tk.length };
    }
    if (!best) return null;
    const g = best.g;
    return {
      paras: [`**${g.term}** (${g.category})`, g.definition, g.why ? `왜 중요한가요? ${g.why}` : ""].filter(Boolean),
      links: [{ label: "부동산 기초 »", href: "learn.html" }],
      src: "근거: 부동산 기초 용어 정리",
      len: best.len,
    };
  }

  // '전세가율이 뭐야?'처럼 지표의 뜻을 묻는 질문: 데이터사전의 변수 설명으로 답한다
  function answerVariable(key) {
    const v = variables.find((x) => x.id === (sample?.aliases?.[key.id] || key.id));
    if (!v) return null;
    const driver = drivers.find((x) => x.id === v.driver);
    const freq = /월/.test(v.freq) ? "월" : v.freq;
    return {
      paras: [`**${v.name}** — ${v.source}에서 ${freq} 단위로 공표하는 지표예요. 제공 지역은 ${v.region}입니다.`, variableProse(v)].filter(Boolean),
      links: driver ? [{ label: `${NUMS[driver.no - 1]} ${driver.name} 보기`, href: `#${driver.id}` }] : [],
      src: "근거: 부동산 대시보드 데이터사전",
    };
  }

  async function answer(q) {
    const qn = norm(q);
    const explain = has(qn, "뭐야", "뭔가요", "뭐예요", "무엇", "뜻", "의미", "설명", "란?", "이란");
    if (explain) {
      // 더 긴 단어를 맞춘 쪽이 이긴다: '전세가율'(지표)이 '전세'(용어)보다 우선
      const key = METRIC_KEYS.find((k) => has(qn, ...k.words));
      const keyLen = key ? Math.max(...key.words.filter((w) => qn.includes(w)).map((w) => w.length)) : 0;
      const g = await answerGlossary(q, qn);
      if (g && g.len >= keyLen) return g;
      const found = (key && answerVariable(key)) || (await answerDriver(q, qn)) || g;
      if (found) return found;
    }
    for (const fn of [answerOutlook, answerPolicy, answerGuide, answerMetric, answerDriver, answerGlossary]) {
      const res = await fn(q, qn);
      if (res) return res;
    }
    return null;
  }

  // ── 화면 ────────────────────────────────────────────
  function rich(text) {
    const frag = document.createDocumentFragment();
    text.split("**").forEach((part, i) => {
      if (part) frag.append(i % 2 ? el("strong", null, part) : document.createTextNode(part));
    });
    return frag;
  }
  function openPanel() {
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }
  function closePanel() {
    panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }
  function chips() {
    const box = el("div", "ask-chips");
    for (const s of SUGGESTIONS) {
      const b = el("button", null, s);
      b.type = "button";
      b.addEventListener("click", () => {
        input.value = s;
        sync();
        ask(s);
      });
      box.append(b);
    }
    return box;
  }
  function showIdle() {
    token++;
    lastAnswered = false;
    body.replaceChildren(el("p", "ask-hint", "이런 걸 물어볼 수 있어요"), chips());
    openPanel();
  }
  function sync() {
    form.classList.toggle("has-text", input.value.trim() !== "");
    send.disabled = input.value.trim() === "";
  }

  async function ask(raw) {
    const q = raw.trim().slice(0, 120);
    if (!q) return;
    const my = ++token;
    lastAnswered = true;
    openPanel();
    const typing = el("div", "ask-typing");
    typing.setAttribute("role", "status");
    typing.setAttribute("aria-label", "KHMI가 답변을 찾는 중");
    typing.append(el("i"), el("i"), el("i"));
    body.replaceChildren(el("div", "ask-q", q), typing);
    const [res] = await Promise.all([answer(q), new Promise((r) => setTimeout(r, reduced() ? 0 : 700))]);
    if (my !== token) return;

    const a = el("div", `ask-a${reduced() ? "" : " ol-reveal"}`);
    let i = 0;
    const put = (node) => {
      node.style.setProperty("--i", i++ * 1.6);
      a.append(node);
    };
    if (!res) {
      const p = el("p");
      p.append(rich("질문의 뜻을 정확히 찾지 못했어요. **지역·지표·정책·용어**를 넣어 다시 물어봐 주세요."));
      put(p);
      put(chips());
    } else {
      for (const text of res.paras) {
        const p = el("p");
        p.append(rich(text));
        put(p);
      }
      if (res.bullets?.length) {
        const ul = el("ul");
        for (const text of res.bullets) {
          const li = el("li");
          li.append(rich(text));
          ul.append(li);
        }
        put(ul);
      }
      if (res.src) put(el("p", "ask-src", res.src));
      if (res.links?.length) {
        const box = el("div", "ask-links");
        for (const l of res.links) {
          let node;
          if (l.run) {
            node = el("button", null, l.label);
            node.type = "button";
            node.addEventListener("click", () => {
              closePanel();
              l.run();
            });
          } else {
            node = el("a", null, l.label);
            node.href = l.href;
            node.addEventListener("click", closePanel);
          }
          box.append(node);
        }
        put(box);
      }
    }
    body.replaceChildren(el("div", "ask-q", q), a, el("p", "ask-foot", `※ ${MOCK_NOTE}`));
    body.parentElement.scrollTop = 0;
  }

  // ── 이벤트 ──────────────────────────────────────────
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    ask(input.value);
  });
  input.addEventListener("input", sync);
  input.addEventListener("focus", () => {
    if (panel.hidden) lastAnswered ? openPanel() : showIdle();
  });
  document.querySelector("#ask-close").addEventListener("click", () => {
    closePanel();
    input.focus({ preventScroll: true });
  });
  document.addEventListener("pointerdown", (e) => {
    if (!panel.hidden && !wrap.contains(e.target)) closePanel();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !panel.hidden) closePanel();
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && !document.querySelector("#view-home")?.hidden) {
      e.preventDefault();
      input.focus();
    }
  });
  sync();
})();
