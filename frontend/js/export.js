// 차트 데이터 내려받기: 차트 제목 줄 오른쪽 위 아이콘 → 엑셀(.xlsx) / CSV
// - 화면에 보이는 그대로(기간 범위, 지역, 수준·전년동월 대비)를 저장한다.
// - 로그인한 사용자만 내려받는다. 로그인 전에는 안내와 로그인 버튼을 보여 준다.
// - 내려받으면 Supabase activity_logs('download')와 Vercel 이벤트를 남긴다.
// charts.js 의 figure() 가 KHMI_EXPORT.button(payload) 를 부른다. payload 는 factors.js drawMetric() 이 만든다.
// 설계: docs/설계서_로그인_데이터다운로드.md 5.2장

(function () {
  const SHEETJS_SRC = "https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js";
  const SITE = "https://www.khmi.kr";
  const VIEW_NAME = { level: "수준", yoy: "전년동기 대비", mom: "전월 대비" };
  const recent = new Map(); // 같은 차트·형식 연속 클릭(3초 안) 중복 방지

  const ICON =
    '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="2.5" width="15" height="15" rx="2.5" fill="#1D6F42"/>' +
    '<path d="M6.6 6.2l2.2 3.6-2.3 3.9h1.7l1.5-2.7 1.5 2.7h1.7l-2.3-3.9 2.2-3.6h-1.7L9.7 8.7 8.3 6.2z" fill="#fff"/></svg>';

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ── 표 만들기 ─────────────────────────────────────────
  function rowsOf(p) {
    const provisional = p.provisionalAt != null && p.provisionalAt >= 0 && p.provisionalAt < p.periods.length;
    const head = ["기간", ...p.series.map((s) => s.name)];
    if (provisional) head.push("잠정");
    const rows = p.periods.map((period, i) => {
      // 계산 과정의 부동소수점 꼬리를 정리한다 (소수 6자리)
      const row = [period, ...p.series.map((s) => (s.values[i] == null || Number.isNaN(s.values[i]) ? null : Math.round(s.values[i] * 1e6) / 1e6))];
      if (provisional) row.push(i >= p.provisionalAt ? "잠정" : "");
      return row;
    });
    // 모든 지역이 빈 기간은 뺀다 (화면에도 선이 없는 구간)
    return [head, ...rows.filter((r) => r.slice(1, 1 + p.series.length).some((v) => v != null))];
  }

  function kstNow() {
    const d = new Date(Date.now() + 9 * 3600 * 1000);
    return d.toISOString().replace("T", " ").slice(0, 16) + " (KST)";
  }

  function infoRows(p, table) {
    const periods = table.slice(1).map((r) => r[0]);
    return [
      ["항목", "내용"],
      ["제목", p.title],
      ["단위 · 주기", p.subtitle],
      ["지역", p.series.map((s) => s.name).join(", ")],
      ["기간", periods.length ? `${periods[0]} ~ ${periods[periods.length - 1]}` : ""],
      ["보기", p.viewLabel || VIEW_NAME[p.view] || p.view],
      ["출처", p.source || ""],
      ["원 통계표", p.sourceTable || ""],
      ["전처리 방법", p.method || ""],
      ["공표 시기", p.release || ""],
      ["잠정값", table[0].includes("잠정") ? "'잠정' 표시된 기간은 신고기한 등으로 바뀔 수 있는 값입니다." : "없음"],
      ["변수 ID", p.varId || ""],
      ["내려받은 시각", kstNow()],
      ["제공", `KHMI — Korea Housing Market Intelligence (${SITE})`],
      ["이용 안내", "공공 통계를 정리한 참고 자료이며 투자 권유나 가격 예측이 아닙니다. 각 통계의 저작권은 원 작성기관에 있습니다."],
    ];
  }

  function fileName(p, ext) {
    const ymd = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, "");
    const regions = p.series.map((s) => s.name).join("-");
    const parts = ["KHMI", p.varId, p.title, regions, p.view !== "level" ? p.viewLabel || VIEW_NAME[p.view] : null, ymd];
    return (
      parts
        .filter(Boolean)
        .join("_")
        .replace(/[\\/:*?"<>|]/g, "")
        .replace(/[\s·]+/g, "")
        .slice(0, 120) + "." + ext
    );
  }

  // ── 파일 저장 ─────────────────────────────────────────
  function save(blob, name) {
    const a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function toCsv(table) {
    const cell = (v) => {
      if (v == null) return "";
      const s = String(v);
      return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    // 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM 을 붙인다
    return "﻿" + table.map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";
  }

  let sheetjs = null;
  function loadSheetJs() {
    if (window.XLSX) return Promise.resolve(window.XLSX);
    if (!sheetjs) {
      sheetjs = new Promise((resolve, reject) => {
        const s = el("script");
        s.src = SHEETJS_SRC;
        s.onload = () => (window.XLSX ? resolve(window.XLSX) : reject(new Error("SheetJS 로드 실패")));
        s.onerror = () => {
          sheetjs = null;
          reject(new Error("SheetJS 로드 실패"));
        };
        document.head.append(s);
      });
    }
    return sheetjs;
  }

  async function toXlsx(table, info) {
    const XLSX = await loadSheetJs();
    const wb = XLSX.utils.book_new();
    const data = XLSX.utils.aoa_to_sheet(table);
    data["!cols"] = table[0].map((h, i) => ({ wch: i === 0 ? 10 : Math.max(10, String(h).length * 2 + 2) }));
    data["!freeze"] = { xSplit: 1, ySplit: 1 };
    const meta = XLSX.utils.aoa_to_sheet(info);
    meta["!cols"] = [{ wch: 14 }, { wch: 90 }];
    XLSX.utils.book_append_sheet(wb, data, "데이터");
    XLSX.utils.book_append_sheet(wb, meta, "정보");
    return new Blob([XLSX.write(wb, { bookType: "xlsx", type: "array" })], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
  }

  async function download(p, format) {
    const key = `${p.varId}:${p.scope}:${p.view}:${format}`;
    if (Date.now() - (recent.get(key) || 0) < 3000) return;
    recent.set(key, Date.now());

    const table = rowsOf(p);
    const name = fileName(p, format);
    if (format === "xlsx") save(await toXlsx(table, infoRows(p, table)), name);
    else save(new Blob([toCsv(table)], { type: "text/csv;charset=utf-8" }), name);

    const t = window.KHMI_TELEMETRY;
    if (t) {
      const regions = p.series.map((s) => s.name);
      t.log("download", {
        target: `${p.varId}:${p.scope}`.slice(0, 80),
        detail: { format, rows: table.length - 1, regions, range: String(p.range), view: p.view },
      });
      t.track("download", { chart: p.varId, scope: p.scope, view: p.view, range: String(p.range), rows: table.length - 1, format });
    }
  }

  // ── 아이콘 버튼과 메뉴 ─────────────────────────────────
  function closeAll(except) {
    for (const m of document.querySelectorAll(".fig-dl-pop:not([hidden])")) {
      if (m !== except) {
        m.hidden = true;
        m.previousElementSibling.setAttribute("aria-expanded", "false");
      }
    }
  }
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".fig-dl-wrap")) closeAll();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
  });

  function fillPop(pop, p) {
    pop.replaceChildren();
    const auth = window.KHMI_AUTH;
    if (!auth || !auth.user) {
      pop.append(el("p", "fig-dl-msg", "로그인 후 내려받을 수 있습니다."));
      const b = el("button", "fig-dl-login", "Google로 로그인");
      b.type = "button";
      b.disabled = !auth || !auth.client;
      b.addEventListener("click", () => auth.signIn());
      pop.append(b);
      if (window.KHMI_TELEMETRY) window.KHMI_TELEMETRY.track("download_blocked", { chart: p.varId });
      return;
    }
    for (const [format, label] of [["xlsx", "엑셀 (.xlsx)"], ["csv", "CSV (.csv)"]]) {
      const b = el("button", "fig-dl-opt", label);
      b.type = "button";
      b.setAttribute("role", "menuitem");
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          await download(p, format);
          pop.hidden = true;
          pop.previousElementSibling.setAttribute("aria-expanded", "false");
        } catch (err) {
          console.warn("내려받기 실패:", err);
          pop.replaceChildren(el("p", "fig-dl-msg", "파일을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."));
        } finally {
          b.disabled = false;
        }
      });
      pop.append(b);
    }
  }

  function button(p) {
    const wrap = el("div", "fig-dl-wrap");
    const btn = el("button", "fig-dl");
    btn.type = "button";
    btn.innerHTML = ICON;
    btn.title = "데이터 내려받기";
    btn.setAttribute("aria-label", `${p.title} 데이터 내려받기`);
    btn.setAttribute("aria-haspopup", "menu");
    btn.setAttribute("aria-expanded", "false");
    const pop = el("div", "fig-dl-pop");
    pop.setAttribute("role", "menu");
    pop.hidden = true;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = pop.hidden;
      closeAll(pop);
      if (open) fillPop(pop, p);
      pop.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      if (open) {
        const first = pop.querySelector("button");
        if (first) first.focus({ preventScroll: true });
      }
    });
    wrap.append(btn, pop);
    return wrap;
  }

  window.KHMI_EXPORT = { button, rowsOf, toCsv, fileName };
})();
