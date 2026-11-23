// 백엔드 API 주소. 정적 사이트는 빌드가 없어 환경변수를 쓸 수 없으므로
// 접속한 주소(hostname)를 보고 로컬/배포를 자동으로 고른다.
// - 배포: 같은 주소의 /api → Vercel 이 Render 로 전달(vercel.json rewrite)하고 응답을 CDN 에 캐시한다.
//         화면과 API 가 같은 주소라 CORS 설정이 필요 없다. Render 주소는 vercel.json 한 곳에만 있다.
// - 로컬: FastAPI 를 직접 부른다.
//         백엔드를 띄우지 않고 배포 API 로 화면만 볼 때는 브라우저 콘솔에서 아래를 실행하고 새로고침한다(끄기: removeItem).
//           localStorage.setItem("khmi_api", "prod")
//         이 모드에서는 이용 기록(POST /usage/events)을 보내지 않아 실서비스 통계에 섞이지 않는다.
const IS_LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
const USE_DEPLOYED_API = IS_LOCAL && (() => {
  try { return localStorage.getItem("khmi_api") === "prod"; } catch { return false; }
})();
const API_BASE_URL = !IS_LOCAL ? "/api" : USE_DEPLOYED_API ? "https://www.khmi.kr/api" : "http://127.0.0.1:8000";
// Swagger UI 도 같은 주소의 /api/docs 에서 연다 (명세는 /api/openapi.json — 백엔드가 /api 접두어를 받아 준다).
const API_DOCS_URL = `${API_BASE_URL}/docs`;

// Supabase (Google 로그인 · 사용 기록). 공개(publishable) 키라 화면에 들어가도 된다.
// 데이터는 테이블마다 RLS 로 보호한다. secret / service_role 키는 절대 여기에 넣지 않는다.
const SUPABASE_URL = "https://weqwfxmvzqarblikfvmj.supabase.co";
const SUPABASE_KEY = "sb_publishable_zhUzMa8NNOfDw_AHnYCuKg_07NXULeR";

// Vercel Web Analytics 스크립트 경로 (Vercel 대시보드 Analytics 를 켠 뒤 표시되는 경로)
const VERCEL_ANALYTICS_SRC = "/_vercel/insights/script.js";
