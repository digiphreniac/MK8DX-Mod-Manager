// ===== UI components: Menu (a "..." button that opens a small popup) =====
//   ui.menu({ label, items, class })  ->  { el }          el is the button; add it where the menu belongs
//     label    what the button is for (its tooltip and its name for a screen reader)
//     items    a function returning the entries each time it opens: { label, title, onClick, danger, disabled } or "-" for a line
//     class    extra class(es) for the button
//   ui.menu.closeAll()
// The popup is fixed to the window beside the button: it opens downward, or upward when there is no room below, and closes on any click
// elsewhere, on Escape, and when the window is resized or scrolled. Its first entry takes the keyboard focus.
(function () {
  function closeAll() {
    document.querySelectorAll(".ui-menu").forEach(m => {
      if (m._btn) m._btn.removeAttribute("aria-expanded");
      m.remove();
    });
  }
  document.addEventListener("click", closeAll);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });
  window.addEventListener("resize", closeAll);
  window.addEventListener("scroll", closeAll, true);

  ui.menu = function (spec) {
    const btn = ui.el("button", {
      class: "ui-menu-btn" + (spec.class ? " " + spec.class : ""), text: "⋯", title: spec.label,
      attrs: { type: "button", "aria-label": spec.label, "aria-haspopup": "menu" },
    });
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = btn.getAttribute("aria-expanded") === "true";
      closeAll();
      if (wasOpen) return;
      const menu = ui.el("div", { class: "ui-menu", attrs: { role: "menu" } });
      for (const item of spec.items()) {
        if (item === "-") { menu.append(ui.el("div", "ui-menu-sep")); continue; }
        menu.append(ui.el("button", {
          class: "ui-menu-item" + (item.danger ? " danger" : ""), text: item.label, title: item.title, disabled: !!item.disabled,
          attrs: { type: "button", role: "menuitem" },
          on: { click: (ev) => { ev.stopPropagation(); if (item.disabled) return; closeAll(); item.onClick(); } },
        }));
      }
      menu._btn = btn;
      document.body.append(menu);
      const r = btn.getBoundingClientRect();
      let top = r.bottom + 4;
      if (top + menu.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - menu.offsetHeight - 4);
      menu.style.top = top + "px";
      menu.style.left = Math.max(8, Math.min(window.innerWidth - menu.offsetWidth - 8, r.right - menu.offsetWidth)) + "px";
      btn.setAttribute("aria-expanded", "true");
      const first = menu.querySelector(".ui-menu-item");
      if (first) first.focus({ preventScroll: true });
    });
    return { el: btn };
  };
  ui.menu.closeAll = closeAll;
})();
