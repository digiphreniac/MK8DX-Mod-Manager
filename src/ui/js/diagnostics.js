// What the page tells the log. The packaged app has no dev tools, so a script error, a failed call to the backend or a page that never
// started would otherwise leave no trace at all. Loaded from index.html BEFORE bootstrap.js, so it also sees the app's own scripts fail.
//   - script errors and unhandled promise rejections are sent to Api.log_client (which writes them to mod-manager.log, capped);
//   - every call to the backend is wrapped: a call that throws, one that answers {error: "..."}, and one slower than 3 s are noted
//     (never the arguments or the answer: they can be big, or private);
//   - if the backend never says it is ready, a message on the page says where to find the log.
// Other scripts use it as  diag.error(kind, message) / diag.warn / diag.info.  Docs: docs/diagnostics.md.
const diag = (function () {
  const MAX_QUEUE = 50, MAX_RECENT = 50, BATCH = 20, FLUSH_MS = 1000, SLOW_MS = 3000, GIVE_UP_MS = 120000, WATCHDOG_MS = 20000;
  const queue = [], recent = [];
  const started = Date.now();
  let timer = null, readyAt = null;

  const clip = (s, n) => { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n) + "..." : s; };
  const baseName = (u) => String(u || "").split(/[\\/]/).pop().split("?")[0];
  const stackTop = (e, n) => (e && e.stack ? String(e.stack).split("\n").slice(0, n + 1).join("\n") : "");

  function record(level, kind, msg) {
    const ev = { level, kind, msg: clip(msg, 1500) };
    recent.push(new Date().toTimeString().slice(0, 8) + " " + kind + ": " + ev.msg);
    if (recent.length > MAX_RECENT) recent.shift();
    queue.push(ev);
    if (queue.length > MAX_QUEUE) queue.shift();
    if (!timer) timer = setTimeout(flush, FLUSH_MS);
  }

  async function flush() {
    timer = null;
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api.log_client !== "function") {   // the backend isn't there yet: keep them for a while
      if (queue.length && Date.now() - started < GIVE_UP_MS) timer = setTimeout(flush, FLUSH_MS);
      return;
    }
    while (queue.length) {
      try { await api.log_client(queue.splice(0, BATCH)); } catch (e) { /* the log itself can't be reached: nothing more to do */ }
    }
  }

  window.addEventListener("error", (e) => {
    const t = e.target;
    if (t && t !== window && (t.tagName === "SCRIPT" || t.tagName === "LINK")) {   // (a picture that is missing is normal: not these)
      record("error", "resource-error", t.tagName.toLowerCase() + " " + baseName(t.src || t.href) + " did not load");
      return;
    }
    record("error", "js-error", e.message + " (" + baseName(e.filename) + ":" + e.lineno + ":" + e.colno + ")" + (e.error ? "\n" + stackTop(e.error, 5) : ""));
  }, true);

  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    record("error", "unhandled-rejection", (r && r.name ? r.name + ": " : "") + (r && r.message ? r.message : String(r)) + (r && r.stack ? "\n" + stackTop(r, 5) : ""));
  });

  // Every backend method gets a thin wrapper. It runs before api-coalesce.js's (which listens for the same event later), so
  // a shared call is noted once.
  function wrapApi() {
    const api = window.pywebview && window.pywebview.api;
    if (!api || api.__diagWrapped) return;
    for (const name of Object.keys(api)) {
      const original = api[name];
      if (typeof original !== "function" || name === "log_client" || name === "get_diagnostics") continue;
      api[name] = function (...args) {
        const t0 = performance.now();
        let call;
        try { call = original.apply(api, args); } catch (e) { record("error", "api_error", name + ": " + e); throw e; }
        return Promise.resolve(call).then((answer) => {
          const ms = performance.now() - t0;
          if (ms > SLOW_MS) record("info", "api_slow", name + " took " + Math.round(ms) + " ms");
          if (answer && typeof answer === "object" && !Array.isArray(answer) && typeof answer.error === "string" && answer.error) record("warn", "api_fail", name + ": " + answer.error);
          return answer;
        }, (e) => {   // (the traceback is in the log already, from the backend's side)
          record("error", "api_error", name + ": " + (e && e.name ? e.name + ": " : "") + (e && e.message ? e.message : e));
          throw e;
        });
      };
    }
    try { Object.defineProperty(api, "__diagWrapped", { value: true }); } catch (e) { api.__diagWrapped = true; }
  }

  function onReady() {
    if (readyAt) return;
    readyAt = Date.now();
    wrapApi();
    record("info", "page-start", navigator.userAgent + "; screen " + screen.width + "x" + screen.height + " @" + window.devicePixelRatio + "x; ready after " + (readyAt - started) + " ms");
  }
  window.addEventListener("pywebviewready", onReady);
  if (window.pywebview && window.pywebview.api) onReady();

  setTimeout(() => {   // the window opened but the backend never answered: say where the log is, instead of an empty page
    if (readyAt) return;
    const box = document.createElement("div");
    box.style.cssText = "margin:24px;padding:16px;border:1px solid #c33;border-radius:8px;font:14px/1.5 sans-serif;";
    box.textContent = "The app didn't finish starting. Close it and open it again. If this keeps happening, send the file mod-manager.log (it sits next to the app).";
    if (document.body) document.body.prepend(box);
  }, WATCHDOG_MS);

  return {
    error: (kind, msg) => record("error", kind, msg),
    warn: (kind, msg) => record("warn", kind, msg),
    info: (kind, msg) => record("info", kind, msg),
    recentText: () => recent.slice(-20).join("\n"),
  };
})();
