// ===== UI components: waiting, and a box filled from something that takes a while =====
//   ui.loading(text)   a spinner and a line ("Reading the mod's menu files...")
//   ui.asyncBox({ el, load, render, isEmpty, emptyText, emptyClass, errorText })  ->  { el, reload() }
//     el          the element to fill (made when not given)
//     load()      returns a promise of the data
//     render(data)  returns what to show (a node)
//     isEmpty(data) / emptyText   shown instead of render() when there is nothing, as a quiet line (emptyClass: an extra class for it)
//     errorText   shown when load() fails (the failure is also logged)
//   reload() asks again. What is showing stays until the new answer arrives, and an answer to an older reload() that comes in late
//   is ignored, so a quick second call can never be overwritten by the first.
ui.loading = function (text) {
  return ui.el("div", "load-note", ui.el("span", "spin"), text);
};

ui.asyncBox = function (spec) {
  const el = spec.el || ui.el("div", "ui-async");
  let latest = 0;
  async function reload() {
    const mine = ++latest;
    let data;
    try {
      data = await spec.load();
    } catch (e) {
      if (mine !== latest) return;
      if (typeof diag !== "undefined") diag.error("async-box", e && e.message ? e.message : String(e));
      el.replaceChildren(ui.hint(spec.errorText || "That didn't load.", { tone: "warn" }));
      return;
    }
    if (mine !== latest) return;
    if (spec.isEmpty && spec.isEmpty(data)) {
      el.replaceChildren(ui.el("div", { class: "ui-async-empty" + (spec.emptyClass ? " " + spec.emptyClass : ""), text: spec.emptyText || "Nothing here yet." }));
      return;
    }
    el.replaceChildren(spec.render(data));
  }
  return { el, reload };
};
