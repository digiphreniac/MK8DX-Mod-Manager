// ===== UI components: Callout and hint =====
// ui.callout - a note that asks something of the user (the Commit page's notes). The shape says what it is as well as the colour (a warning
// triangle, an arrow for "your move", an "i"; drawn as pictures), a stripe down the left repeats it, a hidden word says it to a screen
// reader, and one action is a button at the right.
//   ui.callout({
//     tone,                        "warn" | "todo" | "info"
//     title, detail,
//     action: { label, onClick },
//     items: [{ label, onClick }], names the thing is about (mods, characters): behind one line, in a box of limited height, each a link
//     itemsLabel,                  that line ("Show the 3 mods")
//   })  ->  { el }
//
// ui.hint(text, { tone, size, tag, class }) - one small line of explanation. Tone "dim" (the default) is a quiet grey note, "warn" a boxed
// warning, "error" red text; size "md" is a little larger. `class` adds a class for what is particular to where it sits (a margin). A new
// kind of small note is a tone or a size here, not a new class of its own. A newline in the text starts a new line.
ui.callout = function (spec) {
  const tone = spec.tone || "info";
  const word = { warn: "Check: ", todo: "To do: ", info: "Note: " }[tone] || "";
  const icon = ui.el("span", { class: "ui-callout-icon", attrs: { "aria-hidden": "true" } }, ui.icon({ warn: "warning", todo: "todo", info: "info" }[tone] || "info"));
  const text = ui.el("div", "ui-callout-text",
    ui.el("div", "ui-callout-title", ui.el("span", { class: "ui-sr", text: word }), spec.title),
    spec.detail ? ui.el("div", { class: "ui-callout-detail", text: spec.detail }) : null);
  if (spec.items && spec.items.length) {
    text.append(ui.disclosure({ class: "ui-callout-list", summary: spec.itemsLabel || `Show ${spec.items.length}` },
      ui.el("div", "ui-callout-list-body", spec.items.map(item => ui.el("a", { text: item.label, on: { click: item.onClick } }))),
    ).el);
  }
  const el = ui.el("div", "ui-callout ui-callout--" + tone, icon, text);
  if (spec.action) el.append(ui.button({ label: spec.action.label, size: "small", class: "ui-callout-act", onClick: spec.action.onClick }).el);
  return { el };
};

ui.hint = function (text, { tone = "dim", tag = "div", size, class: extra } = {}) {
  return ui.el(tag, { class: `ui-hint ui-hint--${tone}` + (size ? ` ui-hint--${size}` : "") + (extra ? " " + extra : ""), text });
};
