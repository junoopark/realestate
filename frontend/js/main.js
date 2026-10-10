// 공통 동작: 다크모드 전환 버튼 + 머리 메뉴의 하위 메뉴 열고 닫기 + 머리띠 높이 알림 (모든 페이지 공용)
// theme-init.js(테마 초기값)와 i18n.js(문구 사전)가 먼저 로드되어 있어야 한다.

const themeBtn = document.querySelector("#theme-btn");

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function savedTheme() {
  try {
    return localStorage.getItem("theme");
  } catch (e) {
    return null;
  }
}

function setTheme(theme, { save }) {
  document.documentElement.dataset.theme = theme;
  if (save) {
    try {
      localStorage.setItem("theme", theme);
    } catch (e) {}
  }
  renderControls();
}

// 버튼에는 "누르면 바뀔 상태"를 보여준다 (라이트일 때 '다크')
const ICONS = {
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
};

function renderControls() {
  const dark = currentTheme() === "dark";
  themeBtn.querySelector(".ico").innerHTML = dark ? ICONS.sun : ICONS.moon;
  themeBtn.querySelector(".lbl").textContent = t(dark ? "theme.toLight" : "theme.toDark");
  themeBtn.setAttribute("aria-label", t(dark ? "theme.aria.toLight" : "theme.aria.toDark"));
}

themeBtn.addEventListener("click", () => {
  setTheme(currentTheme() === "dark" ? "light" : "dark", { save: true });
});

// 언어가 바뀌면 (data-i18n 요소는 setLang 이 이미 바꿨으므로) 테마 버튼 글자만 다시 그린다
document.addEventListener("langchange", renderControls);

// 사용자가 직접 고른 적이 없다면 OS 의 다크/라이트 설정 변경을 따라간다
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  if (!savedTheme()) setTheme(e.matches ? "dark" : "light", { save: false });
});

applyI18n();
renderControls();

// 머리 메뉴 하위 메뉴: 마우스를 올리거나 키보드로 들어가면 CSS 가 연다.
// 터치 화면처럼 올릴 수 없는 경우를 위해 ▾ 버튼으로도 열고 닫는다.
for (const btn of document.querySelectorAll(".nav-caret")) {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = btn.getAttribute("aria-expanded") !== "true";
    document.querySelectorAll(".nav-caret").forEach((b) => b.setAttribute("aria-expanded", "false"));
    btn.setAttribute("aria-expanded", String(open));
  });
}
document.addEventListener("click", () => {
  document.querySelectorAll(".nav-caret[aria-expanded='true']").forEach((b) => b.setAttribute("aria-expanded", "false"));
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".nav-caret[aria-expanded='true']").forEach((b) => b.setAttribute("aria-expanded", "false"));
});
// 하위 메뉴에서 같은 페이지 안의 동인을 고르면 메뉴를 닫는다
window.addEventListener("hashchange", () => {
  document.querySelectorAll(".nav-caret[aria-expanded='true']").forEach((b) => b.setAttribute("aria-expanded", "false"));
  if (document.activeElement?.closest(".nav-menu")) document.activeElement.blur();
});

// 머리띠 높이를 CSS 변수(--header-h)로 알려준다. 머리띠 아래에 붙는 요소(동인 탭의 보기 설정 줄,
// demo.html 의 상태 줄, 앵커 이동 위치)가 이 값을 쓴다. 화면 폭에 따라 머리띠 높이가 바뀌므로 계속 따라간다
const siteHeader = document.querySelector(".site-header");
if (siteHeader) {
  new ResizeObserver(([entry]) => {
    document.documentElement.style.setProperty("--header-h", `${Math.ceil(entry.target.getBoundingClientRect().height)}px`);
  }).observe(siteHeader);
}
