/* KHMI presentation controls. The document remains readable without JavaScript. */
(() => {
  "use strict";

  function initialize() {
    const body = document.body;
    const stage = document.getElementById("stage");
    const deck = document.getElementById("deck");
    const slides = deck ? [...deck.querySelectorAll("section.slide")] : [];
    if (!stage || !slides.length) return;

    const byId = (id) => document.getElementById(id);
    const previousButton = byId("prev-slide");
    const nextButton = byId("next-slide");
    const viewButton = byId("view-btn");
    const notesButton = byId("notes-btn");
    const notesPanel = byId("presenter-notes");
    const contentsDialog = byId("contents-dialog");
    const contentsButton = byId("contents-btn");
    const fullscreenButton = byId("fullscreen-btn");
    const wideScreen = window.matchMedia("(min-width: 900px)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reading = !wideScreen.matches;
    let manualView = false;
    let current = indexFromHash();
    let scrollFrame = 0;
    let resizeFrame = 0;
    let scrollTarget = null;
    let scrollTargetTimer = 0;
    let printView = null;
    let contentsReturnFocus = null;
    const contentsEntries = [];

    function indexFromHash() {
      let slug;
      try {
        slug = decodeURIComponent(window.location.hash.slice(1));
      } catch (_) {
        slug = "";
      }
      const found = slides.findIndex((slide) => slide.id === slug);
      return found >= 0 ? found : 0;
    }

    function announce(message) {
      const announcement = byId("slide-announcement");
      if (announcement) announcement.textContent = message;
    }

    function writeLocation(method = "replace") {
      const hash = `#${encodeURIComponent(slides[current].id)}`;
      if (window.location.hash === hash) return;
      const nextUrl = `${window.location.pathname}${window.location.search}${hash}`;
      try {
        window.history[method === "push" ? "pushState" : "replaceState"](null, "", nextUrl);
      } catch (_) {
        // Some local file viewers restrict History API access. Navigation still works.
      }
    }

    function updateNotes() {
      const title = byId("notes-title");
      const copy = byId("notes-copy");
      const note = slides[current].querySelector(".speaker-note");
      if (title) title.textContent = `${current + 1}. ${slides[current].dataset.title || "발표 메모"}`;
      if (copy) copy.textContent = note ? note.textContent.trim() : "이 장에는 별도 발표 메모가 없습니다.";
    }

    function render(shouldAnnounce = true) {
      slides.forEach((slide, index) => {
        const active = index === current;
        slide.classList.toggle("active", active);
        slide.inert = !reading && !active;
        if (!reading && !active) slide.setAttribute("aria-hidden", "true");
        else slide.removeAttribute("aria-hidden");
      });
      if (previousButton) previousButton.disabled = current === 0;
      if (nextButton) nextButton.disabled = current === slides.length - 1;
      const counter = byId("slide-counter");
      if (counter) counter.textContent = `${current + 1} / ${slides.length}`;
      const progress = byId("progress-bar");
      if (progress) {
        progress.style.width = `${((current + 1) / slides.length) * 100}%`;
        progress.setAttribute("aria-valuenow", String(current + 1));
        progress.setAttribute("aria-valuemin", "1");
        progress.setAttribute("aria-valuemax", String(slides.length));
        progress.setAttribute("aria-valuetext", `${slides.length}장 중 ${current + 1}장`);
      }
      contentsEntries.forEach((entry, index) => {
        if (index === current) entry.setAttribute("aria-current", "step");
        else entry.removeAttribute("aria-current");
      });
      updateNotes();
      if (shouldAnnounce) announce(`${current + 1} / ${slides.length}. ${slides[current].dataset.title || ""}`);
    }

    function fitDeck() {
      resizeFrame = 0;
      if (reading) return;
      const width = stage.clientWidth || window.innerWidth;
      const height = stage.clientHeight || window.innerHeight;
      const scale = Math.min(width / 1440, height / 810);
      document.documentElement.style.setProperty("--deck-scale", String(Math.max(0.1, scale)));
    }

    function scheduleFit() {
      if (!resizeFrame) resizeFrame = window.requestAnimationFrame(fitDeck);
    }

    function releaseScrollTarget() {
      scrollTarget = null;
      window.clearTimeout(scrollTargetTimer);
      if (reading) onScroll();
    }

    function scrollToCurrent(smooth) {
      scrollTarget = current;
      window.clearTimeout(scrollTargetTimer);
      const animated = smooth && !reducedMotion.matches;
      slides[current].scrollIntoView({
        block: "start",
        behavior: animated ? "smooth" : "instant",
      });
      // Keep intermediate slides in a smooth scroll from replacing the destination hash.
      scrollTargetTimer = window.setTimeout(releaseScrollTarget, animated ? 1400 : 120);
    }

    function focusCurrent() {
      slides[current].setAttribute("tabindex", "-1");
      slides[current].focus({ preventScroll: true });
    }

    function goTo(index, options = {}) {
      current = Math.max(0, Math.min(slides.length - 1, index));
      render();
      if (options.history !== false) writeLocation(options.history || "push");
      if (reading) scrollToCurrent(options.smooth !== false);
      if (options.focus) window.requestAnimationFrame(focusCurrent);
    }

    function setView(nextReading, options = {}) {
      reading = nextReading;
      releaseScrollTarget();
      body.classList.toggle("reading-mode", reading);
      body.classList.toggle("deck-mode", !reading);
      if (viewButton) {
        viewButton.textContent = reading ? "발표 보기" : "전체 보기";
        viewButton.setAttribute("aria-pressed", String(reading));
        viewButton.setAttribute("aria-label", reading ? "슬라이드 발표 보기로 전환 (O)" : "전체 페이지 읽기로 전환 (O)");
      }
      render(false);
      scheduleFit();
      if (reading && options.scroll !== false) {
        window.requestAnimationFrame(() => scrollToCurrent(false));
      }
    }

    function toggleView() {
      manualView = true;
      setView(!reading);
      announce(reading ? "전체 페이지 읽기 모드입니다." : "슬라이드 발표 모드입니다.");
    }

    function observeReadingPosition() {
      scrollFrame = 0;
      if (!reading || scrollTarget !== null || printView !== null) return;
      const anchor = Math.min(window.innerHeight * 0.28, 220);
      let index = 0;
      slides.forEach((slide, candidate) => {
        if (slide.getBoundingClientRect().top <= anchor) index = candidate;
      });
      if (index !== current) {
        current = index;
        render(false);
        writeLocation("replace");
      }
    }

    function onScroll() {
      if (!scrollFrame) scrollFrame = window.requestAnimationFrame(observeReadingPosition);
    }

    function toggleNotes(show = notesPanel ? notesPanel.hidden : false) {
      if (!notesPanel) return;
      notesPanel.hidden = !show;
      if (notesButton) notesButton.setAttribute("aria-expanded", String(show));
      updateNotes();
      if (show) announce("발표 메모를 열었습니다. N 키로 닫을 수 있습니다.");
    }

    function closeContents() {
      if (contentsDialog && contentsDialog.open) contentsDialog.close();
    }

    function openContents() {
      if (!contentsDialog || contentsDialog.open) return;
      contentsReturnFocus = document.activeElement;
      contentsDialog.showModal();
      if (contentsButton) contentsButton.setAttribute("aria-expanded", "true");
      contentsEntries[current]?.focus();
    }

    const contentsList = byId("contents-list");
    if (contentsList) {
      slides.forEach((slide, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "contents-item";
        button.dataset.slideId = slide.id;
        const chapter = slide.dataset.chapter ? `${slide.dataset.chapter} · ` : "";
        button.textContent = `${String(index + 1).padStart(2, "0")}  ${chapter}${slide.dataset.title || slide.id}`;
        button.addEventListener("click", () => {
          closeContents();
          goTo(index, { focus: true });
        });
        if (["UL", "OL"].includes(contentsList.tagName)) {
          const item = document.createElement("li");
          item.append(button);
          contentsList.append(item);
        } else contentsList.append(button);
        contentsEntries.push(button);
      });
    }

    if (contentsDialog) {
      contentsDialog.addEventListener("close", () => {
        if (contentsButton) contentsButton.setAttribute("aria-expanded", "false");
        if (contentsReturnFocus?.isConnected) contentsReturnFocus.focus({ preventScroll: true });
      });
      contentsDialog.addEventListener("click", (event) => {
        if (event.target !== contentsDialog) return;
        const box = contentsDialog.getBoundingClientRect();
        if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeContents();
      });
    }

    function updateFullscreenButton() {
      if (!fullscreenButton) return;
      const fullscreen = Boolean(document.fullscreenElement);
      fullscreenButton.textContent = fullscreen ? "전체화면 종료" : "전체화면";
      fullscreenButton.setAttribute("aria-pressed", String(fullscreen));
    }

    async function toggleFullscreen() {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
        else announce("이 브라우저는 전체화면 기능을 지원하지 않습니다. 발표 보기를 이용해 주세요.");
      } catch (_) {
        announce("전체화면을 열 수 없습니다. 브라우저 설정을 확인하거나 발표 보기를 이용해 주세요.");
      }
      updateFullscreenButton();
      scheduleFit();
    }

    previousButton?.addEventListener("click", () => goTo(current - 1));
    nextButton?.addEventListener("click", () => goTo(current + 1));
    viewButton?.addEventListener("click", toggleView);
    notesButton?.addEventListener("click", () => toggleNotes());
    byId("close-notes")?.addEventListener("click", () => {
      toggleNotes(false);
      notesButton?.focus();
    });
    contentsButton?.addEventListener("click", openContents);
    byId("close-contents")?.addEventListener("click", closeContents);
    fullscreenButton?.addEventListener("click", toggleFullscreen);
    byId("print-btn")?.addEventListener("click", () => window.print());

    window.addEventListener("beforeprint", () => {
      printView = reading;
      setView(true, { scroll: false });
    });
    window.addEventListener("afterprint", () => {
      if (printView === null) return;
      const restore = printView;
      printView = null;
      setView(restore, { scroll: restore });
    });

    document.addEventListener("keydown", (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || contentsDialog?.open) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable]:not([contenteditable='false']), [role='slider'], [role='combobox'], [role='listbox']")) return;
      const key = event.key.toLowerCase();
      let handled = true;
      if (key === "arrowright" || key === "pagedown") goTo(current + 1);
      else if (key === "arrowleft" || key === "pageup") goTo(current - 1);
      else if (key === "home") goTo(0);
      else if (key === "end") goTo(slides.length - 1);
      else if (key === "n") toggleNotes();
      else if (key === "f") toggleFullscreen();
      else if (key === "o") toggleView();
      else if (key === "escape" && notesPanel && !notesPanel.hidden) toggleNotes(false);
      else handled = false;
      // Enter and Space keep their native button/link behavior.
      if (handled) event.preventDefault();
    });

    function readHistory() {
      goTo(indexFromHash(), { history: false, smooth: false });
    }
    window.addEventListener("popstate", readHistory);
    window.addEventListener("hashchange", readHistory);
    window.addEventListener("resize", scheduleFit);
    window.addEventListener("scroll", onScroll, { passive: true });
    // A manual scroll takes precedence over a pending smooth navigation.
    window.addEventListener("wheel", releaseScrollTarget, { passive: true });
    window.addEventListener("touchstart", releaseScrollTarget, { passive: true });
    document.addEventListener("fullscreenchange", () => {
      updateFullscreenButton();
      scheduleFit();
    });
    wideScreen.addEventListener("change", () => {
      if (!manualView) setView(!wideScreen.matches);
      scheduleFit();
    });
    if (window.ResizeObserver) new ResizeObserver(scheduleFit).observe(stage);

    const demos = {
      home: { href: "index.html#home", title: "홈", description: "가격 흐름·지역 비교·주요 정책을 한눈에" },
      dashboard: { href: "index.html#overview", title: "부동산 대시보드", description: "6개 동인으로 지표를 살펴보고 지역과 기간을 비교" },
      policies: { href: "policies.html#briefs", title: "부동산 정책", description: "공식 발표의 자동 요약과 검토 자료를 함께 확인" },
      learn: { href: "learn.html", title: "부동산 기초", description: "용어·거래 절차·개발 흐름부터 차근차근" },
    };
    const demoButtons = [...document.querySelectorAll("button.demo-tab[data-demo]")];
    function selectDemo(key) {
      const demo = demos[key];
      if (!demo) return;
      demoButtons.forEach((button) => {
        const selected = button.dataset.demo === key;
        button.setAttribute("aria-pressed", String(selected));
        button.classList.toggle("active", selected);
      });
      const demoImage = byId("demo-image");
      if (demoImage) {
        demoImage.src = `assets/presentation/${key}.jpg`;
        demoImage.alt = `KHMI ${demo.title} 화면: ${demo.description}. 2026년 10월 20일 운영 화면.`;
      }
      const caption = byId("demo-caption");
      if (caption) caption.textContent = `${demo.title} · ${demo.description} | 실제 운영 화면 2026.10.20`;
      const link = byId("demo-link");
      if (link) {
        link.href = demo.href;
        link.textContent = `${demo.title} 직접 열기 ↗`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
    }
    demoButtons.forEach((button) => button.addEventListener("click", () => selectDemo(button.dataset.demo)));
    const selectedDemo = demoButtons.find((button) => button.getAttribute("aria-pressed") === "true");
    if (demoButtons.length) selectDemo(selectedDemo?.dataset.demo || demoButtons[0].dataset.demo);

    setView(reading);
    writeLocation("replace");
    updateFullscreenButton();
    if (notesButton) notesButton.setAttribute("aria-expanded", String(notesPanel ? !notesPanel.hidden : false));
    if (contentsButton) contentsButton.setAttribute("aria-expanded", "false");
    document.documentElement.dataset.presentationReady = "true";
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
