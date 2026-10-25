// ===== UI components: Section (a card with a title) =====
//   const card = ui.section({
//     id, title,
//     actions: [ { label, variant, size, title, id, onClick, disabled } ],    header buttons: ui.button() specs, any label and callback.
//                                                                             `disabled` may be a function: it is asked again by card.refresh()
//     body,                    an element (used as it is), or text / nodes / an array of them (put in a box)
//   })  ->  { el, titleEl, body, buttons, refresh(), setTitle(text) }
// It is the `.modal-card` the Settings and Help windows have always used, so it looks the same wherever it is put.
ui.section = function (spec) {
  const titleEl = ui.el("span", { class: "modal-card-title", text: spec.title });
  const buttons = (spec.actions || []).map(a => ui.button({ size: "small", ...a, disabled: typeof a.disabled === "function" ? false : a.disabled }));
  const header = ui.el("div", "modal-card-header", titleEl, buttons.map(b => b.el));
  let body = spec.body;
  if (!(body instanceof Element)) body = ui.el("div", null, body);
  body.classList.add("settings-body");
  const el = ui.el("div", { class: "modal-card ui-section" + (spec.class ? " " + spec.class : ""), id: spec.id }, header, body);
  return {
    el, titleEl, body, buttons,
    refresh() {
      (spec.actions || []).forEach((a, i) => { if (typeof a.disabled === "function") buttons[i].setDisabled(a.disabled()); });
    },
    setTitle(text) { titleEl.textContent = text; },
  };
};

// The cards of a window, in the order given, balanced into columns by the browser (two when there is room for two).
ui.columns = function (sections) {
  return ui.el("div", "settings-columns", sections.map(s => s.el));
};

// The box a group of the settings registry is drawn into (renderSettingsGroup fills any element carrying data-settings-group).
ui.settingsGroup = function (group) {
  return ui.el("div", { class: "settings-body", attrs: { "data-settings-group": group } });
};
