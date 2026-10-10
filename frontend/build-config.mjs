// Vercel: set API_BASE_URL separately for Preview and Production environments.
import { writeFileSync } from "node:fs";

const value = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
if (value) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("API_BASE_URL must be an HTTPS origin, e.g. https://your-preview-api.onrender.com");
  }
}
writeFileSync(new URL("./js/runtime-config.js", import.meta.url),
  `// Public API origin only; never put secrets here.\nwindow.DFMBA_DEPLOYMENT = ${JSON.stringify({ apiBaseUrl: value })};\n`);
console.log(value ? "API origin configured for this deployment." : "Using the default API origin.");
