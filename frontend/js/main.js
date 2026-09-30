// 공통 동작: 다크모드 · 언어 전환 버튼 (index.html, demo.html 공용)
// theme-init.js(테마 초기값)와 i18n.js(문구 사전)가 먼저 로드되어 있어야 한다.

const themeBtn = document.querySelector("#theme-btn");
const langBtn = document.querySelector("#lang-btn");

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

// 버튼에는 "누르면 바뀔 상태"를 보여준다 (라이트일 때 '다크', 한국어일 때 'EN')
function renderControls() {
  const dark = currentTheme() === "dark";
  themeBtn.querySelector(".ico").textContent = dark ? "☀️" : "🌙";
  themeBtn.querySelector(".lbl").textContent = t(dark ? "theme.toLight" : "theme.toDark");
  themeBtn.setAttribute("aria-label", t(dark ? "theme.aria.toLight" : "theme.aria.toDark"));
  langBtn.lang = getLang() === "ko" ? "en" : "ko"; // 버튼 글자의 언어를 스크린 리더에 알린다
}

themeBtn.addEventListener("click", () => {
  setTheme(currentTheme() === "dark" ? "light" : "dark", { save: true });
});

langBtn.addEventListener("click", () => {
  setLang(getLang() === "ko" ? "en" : "ko");
});

// 언어가 바뀌면 (data-i18n 요소는 setLang 이 이미 바꿨으므로) 테마 버튼 글자만 다시 그린다
document.addEventListener("langchange", renderControls);

// 사용자가 직접 고른 적이 없다면 OS 의 다크/라이트 설정 변경을 따라간다
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  if (!savedTheme()) setTheme(e.matches ? "dark" : "light", { save: false });
});

applyI18n();
renderControls();
