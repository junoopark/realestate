// 백엔드 API 주소. 정적 사이트는 빌드가 없어 환경변수를 쓸 수 없으므로
// 접속한 주소(hostname)를 보고 로컬/배포를 자동으로 고른다.
const API_BASE_URL = ["localhost", "127.0.0.1"].includes(location.hostname)
  ? "http://127.0.0.1:8000"
  : "https://realestate-qr7h.onrender.com"; // Render 백엔드 주소 (끝에 / 없이)

// Supabase (Google 로그인 · 사용 기록). 공개(publishable) 키라 화면에 들어가도 된다.
// 데이터는 테이블마다 RLS 로 보호한다. secret / service_role 키는 절대 여기에 넣지 않는다.
const SUPABASE_URL = "https://qpzuqpaqullrgxgegdaw.supabase.co";
const SUPABASE_KEY = "sb_publishable_Detst8I9KIFWYXXFAEKVJA_QSqgIeQK";

// Vercel Web Analytics 스크립트 경로 (Vercel 대시보드 Analytics 를 켠 뒤 표시되는 경로)
const VERCEL_ANALYTICS_SRC = "/_vercel/insights/script.js";
