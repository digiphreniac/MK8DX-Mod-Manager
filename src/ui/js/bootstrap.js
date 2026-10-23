// Loads the page in pieces. index.html is just the page frame; this file
//   1. fetches the modal / overlay markup (html/*.html) and adds it after the frame, then
//   2. runs the app's scripts (js/*.js) one after another.
// The scripts are plain (non-module) scripts sharing ONE global scope, exactly as when they were a
// single <script>, and top-level code in a later file uses what earlier files declared - so the
// order of SCRIPTS below matters. Add a new file where its dependencies are already loaded.
// (The CSS is linked from index.html, in cascade order - order matters there too.)
(function () {
  const PARTIALS = [
    "html/character-modal.html",
    "html/help-modal.html",
    "html/settings-modal.html",
    "html/add-mod-modal.html",
    "html/gb-browse-modal.html",
    "html/gb-detail-modal.html",
    "html/icon-gen-modal.html",
    "html/guessed-names-modal.html",
    "html/setup-overlay.html",
  ];
  const SCRIPTS = [
    "js/api-coalesce.js",
    "js/state-and-helpers.js",
    "js/mod-notes.js",
    "js/tiles-and-review.js",
    "js/rich-text.js",
    "js/character-select-layout.js",
    "js/gamebanana.js",
    "js/gb-browse.js",
    "js/voice.js",
    "js/unit-pictures.js",
    "js/character-card.js",
    "js/course-card.js",
    "js/help-and-icon-generator.js",
    "js/views.js",
    "js/vehicle-screen.js",
    "js/vehicle-card.js",
    "js/item-screen.js",
    "js/item-card.js",
    "js/refile.js",
    "js/add-mod.js",
    "js/data-and-conflicts.js",
    "js/settings-panels.js",
    "js/menu-icons-text.js",
    "js/menu-look.js",
    "js/flow.js",
    "js/setup-wizard.js",
    "js/main.js",
    "js/tooltips.js",
  ];

  // pywebview fires "pywebviewready" once, as soon as the page has loaded - which can be before the
  // scripts below have run and registered their listener (main.js). Note it, and replay it once they're in.
  let readySeen = false;
  window.addEventListener("pywebviewready", () => { readySeen = true; });

  async function fetchText(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error("Couldn't load " + url + " (" + r.status + ")");
    return r.text();
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Couldn't load " + src));
      document.body.appendChild(s);
    });
  }

  function showError(e) {
    const box = document.createElement("pre");
    box.style.cssText = "margin:24px;padding:16px;border:1px solid #c33;border-radius:8px;white-space:pre-wrap;font:13px/1.4 monospace;";
    box.textContent = "The app's page didn't load.\n\n" + (e && e.message ? e.message : e);
    if (typeof diag !== "undefined") diag.error("page-load", e && e.message ? e.message : e);
    document.body.prepend(box);
  }

  (async () => {
    try {
      const markup = await Promise.all(PARTIALS.map(fetchText));
      document.body.insertAdjacentHTML("beforeend", markup.join("\n"));
      for (const src of SCRIPTS) await loadScript(src);
      if (readySeen) window.dispatchEvent(new CustomEvent("pywebviewready"));
    } catch (e) {
      showError(e);
    }
  })();
})();
