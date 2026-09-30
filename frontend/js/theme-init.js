// <head> 에서 가장 먼저 실행되어, 화면이 그려지기 전에 테마를 정한다 (깜빡임 방지).
// 저장된 선택이 있으면 그것을, 없으면 OS 의 다크/라이트 설정을 따른다.
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("theme");
  } catch (e) {}
  if (theme !== "dark" && theme !== "light") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
