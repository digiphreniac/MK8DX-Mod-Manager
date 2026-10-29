// Browser mode: makes `window.pywebview.api` out of HTTP calls to the app (src/web_server.py, docs/browser-mode.md).
//
// The Linux package has no window of its own - it serves this page to the user's browser - so there is no
// pywebview to inject the bridge the page is written against. This puts an object with the same shape in its
// place: one real function per method of the Python Api, each posting its arguments to /api/<method>. Every
// `pywebview.api.<method>(...)` in the rest of the page carries on working, untouched.
//
// NOT one of bootstrap.js's SCRIPTS: the server adds it to <head>, before the page's own scripts, because
// api-coalesce.js and main.js expect `window.pywebview.api` to be there the moment they run. In a pywebview
// window the server never runs, `window.__mk8dxServer` is absent and this file does nothing (it isn't even
// loaded).
(function () {
  const config = window.__mk8dxServer;
  if (!config) return;            // a real pywebview window: it has already put the bridge in place
  delete window.__mk8dxServer;    // (out of reach of the rest of the page; the closure keeps what we need)

  const TOKEN = config.token;
  const HEARTBEAT_MS = (config.heartbeat || 20) * 1000;

  // ---- the calls ----

  async function call(method, args) {
    let response;
    try {
      response = await fetch("api/" + encodeURIComponent(method), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-MK8DX-Token": TOKEN },
        body: JSON.stringify({ args: args }),
      });
    } catch (e) {
      // The app is gone (quit, crashed, or the machine slept): every call from here on would fail the same way.
      lostTheApp();
      throw new Error("The Mod Manager stopped answering. " + (e && e.message ? e.message : e));
    }
    if (!response.ok) throw new Error("The Mod Manager answered " + response.status + " to " + method + "().");
    const payload = await response.json();
    if (payload && payload.error) throw new Error(payload.error);   // (a failed call rejects, exactly as under pywebview)
    return payload ? payload.result : undefined;
  }

  const api = {};
  for (const name of config.methods) {
    api[name] = function (...args) { return call(name, args); };
  }
  window.pywebview = { api: api, platform: "browser", token: undefined };

  // ---- "the page is still here" ----
  // The app quits once the page has gone, so it doesn't sit in the background for ever after the tab is closed.
  // A hidden tab has its timers throttled to about once a minute, which is why the app waits minutes, not seconds.

  function ping() {
    fetch("alive", { method: "POST", headers: { "X-MK8DX-Token": TOKEN } }).catch(() => {});
  }
  setInterval(ping, HEARTBEAT_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) ping(); });

  window.addEventListener("pagehide", () => {
    // keepalive lets this finish after the page is gone - and, unlike sendBeacon, still carries our header.
    // A reload sends it too; the app waits a few seconds for the page to come back before it acts on it.
    try {
      fetch("closing", { method: "POST", headers: { "X-MK8DX-Token": TOKEN }, keepalive: true }).catch(() => {});
    } catch (e) { /* on the way out: nothing useful to do */ }
  });

  // ---- the app went away ----

  let lost = false;
  function lostTheApp() {
    if (lost) return;
    lost = true;
    const box = document.createElement("div");
    box.setAttribute("role", "alert");
    box.style.cssText = "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;" +
      "background:rgba(14,16,22,.88);color:#fff;font:15px/1.5 system-ui,sans-serif;text-align:center;padding:32px;";
    box.innerHTML = "<div><h2 style='margin:0 0 8px'>The Mod Manager has stopped</h2>" +
      "<p style='margin:0;opacity:.8'>Nothing on this page will work now.<br>" +
      "Start the Mod Manager again and open the new link it prints.</p></div>";
    document.body.appendChild(box);
  }

  // ---- "the bridge is ready" ----
  // pywebview fires this once the page has loaded, and bootstrap.js replays it for the scripts it loads after.
  // Firing it before bootstrap.js has run its own top level would be firing it at nobody, so: at DOMContentLoaded,
  // by which time every ordinary script in the page has run and registered its listener.

  function ready() { window.dispatchEvent(new CustomEvent("pywebviewready")); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else ready();
})();
