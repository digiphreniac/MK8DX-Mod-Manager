// ===== UI components: Modal =====
//   const m = ui.modal({
//     id,                          "settings-modal": the window; its parts are <id>-backdrop, <id>-header, <id>-title, <id>-bar,
//                                  <id>-body and <id>-footer, and its Close button is btn-<id>-close
//     title, size,                 size: "narrow" | "normal" (default) | "wide"
//     body,                        a node, an array of nodes, or a function returning one (the scrolling part) ...
//     sections,                    ... or ui.section() handles, one after another
//     bar,                         true: a line under the header that stays in view while the body scrolls (m.bar)
//     actions,                     ui.button() specs, drawn in a footer at the right
//     closeLabel, closeOnBackdrop,
//     beforeClose(),               return false to keep it open (a job is running)
//     onOpen(), onClose(),
//     onEscape(event),             return true when Escape was used for something else (it then does not close the window)
//     role,                        "dialog" (default) or "alertdialog"
//     variant, class, footer,      variant "card": a small centred dialog with the title in it (no header bar and no Close button: it has
//                                  buttons of its own), for the app's own questions and tools. `class` adds a class to the dialog, `footer: true`
//                                  makes the footer even without `actions` (add your own buttons to m.footer). In a card the body is laid
//                                  out as part of the dialog itself (display: contents), so a dialog that scrolls one part keeps working.
//     destroyOnClose,              remove it from the page when it closes (a dialog made for one use)
//     adopt,                       the id of a window whose markup is already on the page (html/*.html: <id>-backdrop, <id>, <id>-body ...
//                                  and a btn-<id>-close button): nothing is built, the window just joins the stack and gets the same
//                                  open / close / Escape / backdrop-click / focus behaviour. `title` is not used then.
//   })  ->  { el, dialog, body, bar, footer, actions, isOpen, open(), close(), setTitle(text), setBody(content), destroy() }
//
// The windows that are open form a stack. Opening one puts it above everything already showing (z-order is worked out from what is on
// the page, so no window needs its own z-index), Escape closes only the top one, Tab stays inside it, and focus goes back to what opened
// it. The window is built once, hidden, and shown by open(): scripts may look its parts up by id at any time.
(function () {
  const BASE_Z = 20, STEP = 5;
  let nextId = 0;
  const stack = [];          // open windows, the lowest first: { api, z, spec }

  // The highest z-index among windows the page drew by itself (the older popups and the Setup overlay): ours go above them.
  function otherWindowsZ() {
    let top = 0;
    for (const el of document.querySelectorAll('[class*="backdrop"], [id$="-backdrop"], #setup-overlay')) {
      if (el.classList.contains("ui-modal-backdrop") || el.hidden) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.position !== "fixed") continue;
      top = Math.max(top, parseInt(style.zIndex, 10) || 0);
    }
    return top;
  }

  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

  window.addEventListener("keydown", (e) => {
    const top = stack[stack.length - 1];
    if (!top || (e.key !== "Escape" && e.key !== "Tab")) return;
    if (otherWindowsZ() > top.z) return;             // (a window the page drew by itself is above: its own handler deals with the key)
    if (e.key === "Escape") {
      e.stopPropagation();
      e.preventDefault();
      if (top.spec.onEscape && top.spec.onEscape(e) === true) return;
      top.api.close();
      return;
    }
    const items = [...top.api.dialog.querySelectorAll(FOCUSABLE)].filter(x => x.offsetParent !== null);
    if (!items.length) { e.preventDefault(); top.api.dialog.focus(); return; }
    const first = items[0], last = items[items.length - 1], now = document.activeElement;
    if (!top.api.dialog.contains(now) || now === top.api.dialog) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
    else if (e.shiftKey && now === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && now === last) { e.preventDefault(); first.focus(); }
  }, true);

  ui.modal = function (spec) {
    if (spec.adopt) return adopt(spec);
    const id = spec.id || "ui-modal-" + (++nextId);
    const card = spec.variant === "card";
    const size = card ? "card" : (spec.size || "normal");
    const closeButton = card ? null : ui.el("button", { class: "ghost", id: `btn-${id}-close`, text: spec.closeLabel || "Close", attrs: { type: "button" }, on: { click: () => api.close() } });
    const titleEl = ui.el(card ? "h3" : "h2", { id: `${id}-title`, text: spec.title || "" });
    const header = card ? titleEl : ui.el("div", { class: "ui-modal-header", id: `${id}-header` }, titleEl, closeButton);
    const bar = spec.bar ? ui.el("div", { class: "ui-modal-bar", id: `${id}-bar`, hidden: true }) : null;
    const body = ui.el("div", { class: card ? "ui-modal-body ui-modal-body--part" : "ui-modal-body", id: `${id}-body` });
    const actions = (spec.actions || []).map(a => ui.button(a));
    const footer = actions.length || spec.footer ? ui.el("div", { class: "ui-modal-footer", id: `${id}-footer` }, actions.map(a => a.el)) : null;
    const dialog = ui.el("div", {
      class: `ui-modal ui-modal--${size}` + (spec.class ? " " + spec.class : ""), id,
      attrs: { role: spec.role || "dialog", "aria-modal": "true", "aria-labelledby": `${id}-title`, tabindex: "-1" },
    }, header, bar, body, footer);
    const backdrop = ui.el("div", {
      class: "ui-modal-backdrop" + (card ? " ui-modal-backdrop--card" : ""), id: `${id}-backdrop`, hidden: true,
      on: { click: (e) => { if (e.target === backdrop && spec.closeOnBackdrop !== false) api.close(); } },
    }, dialog);

    const api = makeApi(spec, { backdrop, dialog, body, bar, footer, actions, titleEl });
    if (spec.sections) api.setBody(spec.sections.map(s => s.el || s));
    else if (spec.body) api.setBody(spec.body);
    document.body.append(backdrop);
    return api;
  };

  function adopt(spec) {
    const id = spec.adopt;
    const backdrop = document.getElementById(`${id}-backdrop`);
    const dialog = document.getElementById(id);
    if (!backdrop || !dialog) throw new Error("No window on the page called " + id);
    const closeButton = document.getElementById(`btn-${id}-close`);
    const parts = { backdrop, dialog, body: document.getElementById(`${id}-body`), bar: null, footer: null, actions: [], titleEl: document.getElementById(`${id}-title`) };
    const api = makeApi(spec, parts);
    if (closeButton) closeButton.addEventListener("click", () => api.close());
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop && spec.closeOnBackdrop !== false) api.close(); });
    return api;
  }

  function makeApi(spec, { backdrop, dialog, body, bar, footer, actions, titleEl }) {
    let opener = null;
    const api = {
      el: backdrop, dialog, body, bar, footer, actions,
      get isOpen() { return !backdrop.hidden; },
      open() {
        if (!backdrop.hidden) return;
        opener = document.activeElement;
        const above = stack.length ? stack[stack.length - 1].z + STEP : BASE_Z;
        const z = Math.max(above, otherWindowsZ() + 1, BASE_Z);
        backdrop.style.zIndex = z;
        backdrop.hidden = false;
        stack.push({ api, z, spec });
        if (spec.onOpen) spec.onOpen();
        dialog.focus({ preventScroll: true });
      },
      close() {
        if (backdrop.hidden) return true;
        if (spec.beforeClose && spec.beforeClose() === false) return false;
        backdrop.hidden = true;
        const at = stack.findIndex(x => x.api === api);
        if (at >= 0) stack.splice(at, 1);
        if (opener && opener.isConnected && opener.focus) opener.focus({ preventScroll: true });
        opener = null;
        if (spec.onClose) spec.onClose();
        if (spec.destroyOnClose) setTimeout(api.destroy);
        return true;
      },
      setTitle(text) { if (titleEl) titleEl.textContent = text; },
      setBody(content) {
        const parts = typeof content === "function" ? content() : content;
        body.replaceChildren();
        ui.append(body, [parts]);
      },
      destroy() { api.close(); backdrop.remove(); },
    };
    return api;
  }

  // How many of our windows are open (the page can ask before it does something that needs a quiet screen).
  ui.modal.openCount = () => stack.length;
})();
