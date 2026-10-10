(() => {
  "use strict";
  const title = document.getElementById("callback-title");
  const status = document.getElementById("callback-status");
  const retry = document.getElementById("callback-retry");
  const back = document.getElementById("callback-back");
  const params = new URLSearchParams(location.search);
  const fragment = new URLSearchParams(location.hash.slice(1));
  const code = params.get("code");
  const denied = params.has("error") || fragment.has("error");
  // Remove the authorization code before any further navigation.
  history.replaceState(null, "", location.pathname);
  retry.addEventListener("click", async () => {
    retry.disabled = true;
    try {
      if (MemberAuth.state.status !== "ready") await MemberAuth.retry();
      await MemberAuth.login("popular.html");
    } catch (error) { status.textContent = error.message; retry.disabled = false; }
  });
  void (async () => {
    try {
      if (denied) throw new Error("Google 로그인이 취소되었거나 허용되지 않았습니다. 원하시면 다시 시도해 주세요.");
      await MemberAuth.completeLogin(code);
      title.textContent = "로그인되었습니다.";
      status.textContent = "이전 페이지로 이동합니다.";
      location.replace(MemberAuth.returnTo());
    } catch (error) {
      title.textContent = "로그인을 완료하지 못했어요.";
      status.textContent = error.message;
      retry.hidden = false;
      back.hidden = false;
    }
  })();
})();
