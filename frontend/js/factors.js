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

  card.append(el("div", "var-chart", t("factor.chart")));

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
    viewNav.append(a);
  }
  showView();
}

window.addEventListener("hashchange", showView);
initFactors();
