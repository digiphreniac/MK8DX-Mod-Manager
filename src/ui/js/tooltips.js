// ===== Tooltips =====
// One tooltip element that replaces the browser's own `title` one, so every title="..." in the app (set in the
// markup or from code, on anything that appears later too) gets the same look without being touched. While the
// mouse is over an element its title is taken off it (that is what keeps the browser's tooltip from also showing) and
// put back when the mouse leaves. Lines of a title (\n) become lines of the tooltip; a "Label: text" line gets its
// label picked out. It appears after a short pause over each new element (moving on to the next one starts the wait again) - flips
// above when there is no room below, stays inside the window, and goes on any click, scroll, key or focus change.
// Keyboard focus (Tab) shows it too.
(function tooltips() {
  const SHOW_DELAY = 380, GAP = 9, MARGIN = 8;
  const el = document.createElement("div");
  el.id = "app-tip";
  el.setAttribute("role", "tooltip");
  const bodyEl = document.createElement("div");
  const arrow = document.createElement("span");
  arrow.className = "tip-arrow";
  el.append(bodyEl, arrow);
  document.body.appendChild(el);

  let current = null, timer = null, watch = null, mouseX = 0;

  function fill(text) {
    bodyEl.replaceChildren();
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      const row = document.createElement("div");
      row.className = "tip-line";
      const m = line.match(/^([A-Za-z][A-Za-z ]{0,18}): (.+)$/);
      if (m) {
        const b = document.createElement("b");
        b.textContent = m[1] + ":";
        row.append(b, " " + m[2]);
      } else {
        row.textContent = line;
      }
      bodyEl.appendChild(row);
    }
  }

  function place() {
    if (!current || !current.isConnected) { hide(); return; }
    const r = current.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    // under the middle of a small thing; under the mouse (kept within the thing) for a wide one
    const ax = r.width <= 220 ? r.left + r.width / 2 : Math.min(Math.max(mouseX, r.left + 14), r.right - 14);
    const left = Math.min(Math.max(ax - w / 2, MARGIN), Math.max(MARGIN, vw - w - MARGIN));
    const fitsBelow = r.bottom + GAP + h <= vh - MARGIN;
    const fitsAbove = r.top - GAP - h >= MARGIN;
    const below = fitsBelow || !fitsAbove;
    el.dataset.side = below ? "below" : "above";
    el.style.left = left + "px";
    el.style.top = Math.max(MARGIN, below ? r.bottom + GAP : r.top - GAP - h) + "px";
    arrow.style.left = Math.min(Math.max(ax - left, 14), Math.max(14, w - 14)) + "px";
  }

  function show() {
    if (!current) return;
    fill(current.__tip);
    place();
    el.classList.add("show");
    if (!current.hasAttribute("aria-describedby")) { current.setAttribute("aria-describedby", "app-tip"); current.__tipDesc = true; }
    clearInterval(watch);
    watch = setInterval(() => { if (!current || !current.isConnected) hide(); else place(); }, 300);
  }

  function hide() {
    clearTimeout(timer);
    clearInterval(watch);
    el.classList.remove("show");
    const t = current;
    current = null;
    if (!t) return;
    t.removeAttribute("data-tipped");
    if (t.__tipDesc) { t.removeAttribute("aria-describedby"); delete t.__tipDesc; }
    if (t.__tip != null) {
      if (!t.hasAttribute("title")) t.setAttribute("title", t.__tip);
      delete t.__tip;
    }
  }

  // Take the tooltip away but stay "on" the element: its title stays off until the mouse leaves it, so the browser's
  // own tooltip doesn't take over after a click or a scroll.
  function dismiss() {
    clearTimeout(timer);
    clearInterval(watch);
    el.classList.remove("show");
  }

  function begin(target, immediate) {
    if (target === current) return;
    hide();
    if (!target) return;
    const own = target.getAttribute("title");
    const text = own || target.__tip || "";
    if (!text) return;
    if (own) { target.__tip = own; target.removeAttribute("title"); }
    target.setAttribute("data-tipped", "");
    current = target;
    timer = setTimeout(show, immediate ? 0 : SHOW_DELAY);
  }

  const tippedOf = (node) => (node instanceof Element ? node.closest("[title], [data-tipped]") : null);

  document.addEventListener("mouseover", (e) => { mouseX = e.clientX; begin(tippedOf(e.target), false); }, true);
  document.addEventListener("mouseout", (e) => { if (!e.relatedTarget) hide(); }, true);   // (the mouse left the window)
  document.addEventListener("focusin", (e) => {
    const t = tippedOf(e.target);
    if (t && e.target.matches(":focus-visible")) begin(t, true);
  });
  document.addEventListener("focusout", () => hide());
  for (const ev of ["mousedown", "keydown", "wheel", "touchstart"]) document.addEventListener(ev, dismiss, true);
  window.addEventListener("scroll", dismiss, true);
  window.addEventListener("blur", hide);
  window.addEventListener("resize", dismiss);

  // a title changed while its tooltip is up (the tile under the mouse is redrawn, say): take the new one
  new MutationObserver((muts) => {
    if (!current) return;
    for (const m of muts) {
      if (m.target !== current) continue;
      const t = current.getAttribute("title");
      if (t === null) continue;               // (our own removal)
      if (t === "") { delete current.__tip; hide(); return; }
      current.__tip = t;
      current.removeAttribute("title");
      if (el.classList.contains("show")) { fill(t); place(); }
    }
  }).observe(document.body, { attributes: true, attributeFilter: ["title"], subtree: true });
})();
