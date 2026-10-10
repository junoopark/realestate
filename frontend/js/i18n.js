// 한국어 / English 문구 사전과 번역 적용 함수.
// HTML 에서는 data-i18n="키" 로 연결하고, JS 에서는 t("키") 로 가져온다.
//   data-i18n="키"                  → 요소의 글자(textContent)를 바꾼다
//   data-i18n-html="키"             → 굵은 글씨 등 태그가 든 문구 (사전은 우리가 쓴 고정 문구라 안전)
//   data-i18n-attr="속성:키;속성:키" → title, aria-label, content 같은 속성을 바꾼다

const I18N = {
  ko: {
    // 공통
    "theme.toDark": "다크",
    "theme.toLight": "라이트",
    "theme.aria.toDark": "다크 모드로 전환",
    "theme.aria.toLight": "라이트 모드로 전환",

    // 동인 탭 (factors.js)
    "factor.loadError": "동인 데이터를 불러오지 못했습니다 (data/drivers.json)",

    // 대시보드 페이지
    "index.title": "DFMBA 한국 주택시장 101",
    "index.desc": "주요 부동산 지표를 한 화면에 모아 보는 대시보드",
    "index.h1": "DFMBA 한국 주택시장 101",

    // 연동 실습 페이지
    "demo.title": "API 연동 실습 — DFMBA 한국 주택시장 101",
    "demo.desc": "FastAPI 백엔드 API를 호출하고 결과를 보여주는 연동 실습 페이지",
    "demo.h1": "API 연동 실습",
    "demo.lead":
      "이 페이지는 <strong>Vercel</strong>에 배포된 화면이 <strong>Render</strong>의 FastAPI 서버를 호출해 결과를 보여줍니다.",
    "demo.apiServer": "API 서버:",
    "demo.p1.title": "1. 서버 상태 확인",
    "demo.p2.title": "2. 지표 목록",
    "demo.p3.title": "3. 지표 데이터",
    "demo.call": "호출하기",
    "demo.out.empty": "아직 호출하지 않았습니다.",
    "demo.out.healthAria": "서버 상태 응답",
    "demo.out.listAria": "지표 목록 응답",
    "demo.out.seriesAria": "지표 데이터 응답",
    "demo.form.key": "지표 key",
    "demo.hint": "key 는 2번 지표 목록에서 확인할 수 있습니다.",
    "demo.back": "← 대시보드로",

    // 요청 상태
    "status.ready": "준비됨",
    "status.requesting": "{label} 요청 중…",
    "status.success": "{label} 성공",
    "status.failure": "{label} 실패: {reason}",
    "status.waking":
      "서버를 깨우는 중입니다… 무료 서버라 첫 응답은 최대 1분 걸릴 수 있어요",
    "label.health": "서버 상태 확인",
    "label.list": "지표 목록 조회",
    "label.series": "지표 데이터 조회",
    "err.network": "서버에 연결할 수 없습니다 (서버가 꺼져 있거나 CORS 설정을 확인하세요)",
    "err.validation": "입력값 오류: {detail}",
    "err.detail": "{detail} (HTTP {status})",
    "err.http": "요청 실패 (HTTP {status})",
  },

  en: {
    // Common
    "theme.toDark": "Dark",
    "theme.toLight": "Light",
    "theme.aria.toDark": "Switch to dark mode",
    "theme.aria.toLight": "Switch to light mode",

    // Driver tabs (factors.js)
    "factor.loadError": "Failed to load driver data (data/drivers.json)",

    // Dashboard page
    "index.title": "DFMBA Korea Housing Market 101",
    "index.desc": "A dashboard that gathers key real estate indicators on one screen",
    "index.h1": "DFMBA Korea Housing Market 101",

    // API demo page
    "demo.title": "API Demo — DFMBA Korea Housing Market 101",
    "demo.desc": "A demo page that calls a FastAPI backend and displays the results",
    "demo.h1": "API Integration Demo",
    "demo.lead":
      "This page, deployed on <strong>Vercel</strong>, calls a FastAPI server on <strong>Render</strong> and shows the results.",
    "demo.apiServer": "API server:",
    "demo.p1.title": "1. Server health check",
    "demo.p2.title": "2. Indicator list",
    "demo.p3.title": "3. Indicator data",
    "demo.call": "Call",
    "demo.out.empty": "Not called yet.",
    "demo.out.healthAria": "Server health response",
    "demo.out.listAria": "Indicator list response",
    "demo.out.seriesAria": "Indicator data response",
    "demo.form.key": "Indicator key",
    "demo.hint": "Find the key in the indicator list (step 2).",
    "demo.back": "← Back to Dashboard",

    // Request status
    "status.ready": "Ready",
    "status.requesting": "{label}: requesting…",
    "status.success": "{label}: success",
    "status.failure": "{label}: failed — {reason}",
    "status.waking":
      "Waking up the server… On the free plan the first response can take up to a minute.",
    "label.health": "Health check",
    "label.list": "Indicator list",
    "label.series": "Indicator data",
    "err.network": "Cannot reach the server (it may be down, or check the CORS settings)",
    "err.validation": "Invalid input: {detail}",
    "err.detail": "{detail} (HTTP {status})",
    "err.http": "Request failed (HTTP {status})",
  },
};

// 언어 결정: 언어 전환 버튼을 없애 한국어로 고정한다. (English 사전은 다시 켤 때를 위해 남겨 둔다)
function detectLang() {
  return "ko";
}

let currentLang = detectLang();

// 문구 조회. "{이름}" 자리는 params 로 채운다. 없는 키는 한국어 → 키 이름 순으로 대신한다.
function t(key, params = {}) {
  const text = I18N[currentLang][key] ?? I18N.ko[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? params[name] : match));
}

// 페이지 안의 data-i18n* 속성이 붙은 요소를 현재 언어로 바꾼다
function applyI18n() {
  document.documentElement.lang = currentLang;
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of document.querySelectorAll("[data-i18n-html]")) {
    el.innerHTML = t(el.dataset.i18nHtml);
  }
  for (const el of document.querySelectorAll("[data-i18n-attr]")) {
    for (const pair of el.dataset.i18nAttr.split(";")) {
      const [attr, key] = pair.split(":");
      el.setAttribute(attr.trim(), t(key.trim()));
    }
  }
}

// 언어를 바꾸고 저장한 뒤, 동적으로 그린 화면이 다시 그릴 수 있도록 알린다
function setLang(lang) {
  if (!I18N[lang]) return;
  currentLang = lang;
  try {
    localStorage.setItem("lang", lang);
  } catch (e) {}
  applyI18n();
  document.dispatchEvent(new CustomEvent("langchange", { detail: { lang } }));
}
