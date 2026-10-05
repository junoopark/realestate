// 탭 전환 (Overview ↔ 6개 동인) + 동인 탭 화면 그리기 (index.html 전용)
// 동인·변수 정보는 data/drivers.json (데이터사전 엑셀의 동인분류_가이드·Driver_Map·Variable_Master 에서 추출)
// 주소 끝의 #id 로 탭을 고른다: #overview, #demand, #supply, #finance, #rental, #trigger, #macro

const viewNav = document.querySelector("#view-nav");
const overviewView = document.querySelector("#view-overview");
const factorView = document.querySelector("#view-factor");

let drivers = [];
let variables = [];

// 태그·클래스·글자로 요소를 만든다 (글자는 textContent 로 넣어 HTML 로 해석되지 않게 한다)
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const NUMS = ["①", "②", "③", "④", "⑤", "⑥"];
const driverLabel = (d) => `${NUMS[d.no - 1]} ${d.name}`;

// 예상 부호: + 는 월세 리스크를 키우는 방향, - 는 낮추는 방향, ± 는 방향이 상황에 따라 다름
function signClass(sign) {
  if (sign === "+") return "sign-up";
  if (sign === "-") return "sign-down";
  return "sign-mixed";
}

function variableCard(v) {
  const card = el("article", "var-card");

  const head = el("header", "var-head");
  head.append(el("h3", "var-name", v.name), el("span", "var-id", v.id));
  card.append(head);

  const badges = el("div", "var-badges");
  if (v.sign) {
    const b = el("span", `badge ${signClass(v.sign)}`, v.sign);
    b.title = t("factor.sign");
    badges.append(b);
  }
  if (v.lead) badges.append(el("span", "badge", v.lead));
  if (v.freq) badges.append(el("span", "badge", v.freq));
  if (v.leakage && v.leakage !== "낮음") {
    badges.append(el("span", "badge badge-warn", t("factor.leakage", { level: v.leakage })));
  }
  if (v.driver2) {
    const d2 = drivers.find((d) => d.id === v.driver2);
    if (d2) badges.append(el("span", "badge badge-ghost", `${t("factor.secondary")} ${NUMS[d2.no - 1]}`));
  }
  card.append(badges);

  const chart = el("div", "var-chart", t("factor.chart"));
  card.append(chart);
  renderVariableChart(chart, v);

  const meta = el("dl", "var-meta");
  for (const [key, value] of [
    ["factor.source", v.source],
    ["factor.region", v.region],
    ["factor.period", v.period],
    ["factor.release", v.release],
    ["factor.transform", v.transform],
  ]) {
    if (!value) continue;
    meta.append(el("dt", null, t(key)), el("dd", null, value));
  }
  card.append(meta);
  return card;
}

// 변수 카드의 차트: indicators.js 로 data/indicators/<id>.json 을 읽어 선택 지역의 최신값·변화·스파크라인을 그린다.
// 항목이 여럿이면(예: 고용률·취업자) 작은 선택 상자를 둔다. 자료가 없으면 "차트 준비 중"을 그대로 둔다.
async function renderVariableChart(box, v) {
  const I = window.Indicators;
  if (!I) return;
  let variable;
  try {
    variable = await I.loadVariable(v.id);
  } catch (err) {
    box.classList.add("ind-none");
    return;
  }
  const itemKeys = Object.keys(variable.items);
  if (!itemKeys.length) {
    box.classList.add("ind-none");
    return;
  }
  let itemKey = itemKeys[0];
  const draw = () => {
    const item = variable.items[itemKey];
    const picked = I.pick(item, I.region());
    box.replaceChildren();
    box.classList.add("ind-ready");
    if (itemKeys.length > 1) {
      const select = el("select");
      select.setAttribute("aria-label", "항목 선택");
      for (const key of itemKeys) {
        const opt = el("option", null, key);
        opt.value = key;
        opt.selected = key === itemKey;
        select.append(opt);
      }
      select.addEventListener("change", () => { itemKey = select.value; draw(); });
      box.append(select);
    }
    if (!picked) {
      box.append(el("span", null, t("factor.chart")));
      return;
    }
    box.append(I.seriesBlock({ label: itemKey, unit: item.unit, series: picked.series, regionName: picked.name, points: 60, name: v.name }));
  };
  draw();
  I.onRegionChange(() => { if (box.isConnected) draw(); });
}

function renderFactor(driver) {
  const list = variables.filter((v) => v.driver === driver.id);
  factorView.replaceChildren();

  const hero = el("section", "factor-hero");
  const top = el("div", "factor-top");
  top.append(el("h2", "factor-title", driverLabel(driver)), el("span", "badge badge-ghost", driver.position));
  hero.append(top);
  hero.append(el("p", "factor-question", driver.question));
  if (driver.description) hero.append(el("p", "factor-desc", driver.description));

  const facts = el("dl", "factor-facts");
  const chips = el("dd", "chips");
  for (const s of driver.subareas) chips.append(el("span", "chip", s));
  facts.append(el("dt", null, t("factor.subareas")), chips);
  facts.append(el("dt", null, t("factor.principle")), el("dd", null, driver.principle));
  hero.append(facts);
  factorView.append(hero);

  const section = el("section", "factor-vars");
  section.setAttribute("aria-label", t("factor.variables", { n: list.length }));
  section.append(el("h3", "factor-count", t("factor.variables", { n: list.length })));
  const grid = el("div", "var-grid");
  for (const v of list) grid.append(variableCard(v));
  section.append(grid);
  factorView.append(section);
}

// 현재 주소(#id)에 맞는 화면을 보여준다
function showView() {
  const id = location.hash.slice(1) || "overview";
  const driver = drivers.find((d) => d.id === id);
  const view = driver ? id : "overview";

  document.body.classList.toggle("frame", view === "overview"); // Overview 만 한 화면 고정, 동인 탭은 스크롤
  overviewView.hidden = view !== "overview";
  factorView.hidden = view === "overview";
  const note = document.querySelector("#tiles-note");
  if (note) note.hidden = view !== "overview";
  if (driver) renderFactor(driver);

  for (const a of viewNav.querySelectorAll("a")) {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  const current = viewNav.querySelector('[aria-current="page"]');
  if (current) current.scrollIntoView({ block: "nearest", inline: "nearest" }); // 좁은 화면에서 선택한 탭이 보이게
  window.scrollTo(0, 0);
}

async function initFactors() {
  try {
    const res = await fetch("data/drivers.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    drivers = data.drivers;
    variables = data.variables;
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
}

window.addEventListener("hashchange", showView);
initFactors();
