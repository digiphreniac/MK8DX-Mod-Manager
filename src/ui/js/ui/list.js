// ===== UI components: List and Row =====
//   ui.row({ mark, title, detail, actions, below, class })  ->  { el }
//     One line of a list: a mark (a tick), the title in bold, a quiet detail after it, buttons at the right, and something under the line
//     (a fold-away list of files) over the full width. The line keeps to one row and ends in "..." when it is too long (its title attribute
//     says all of it).
//   ui.list({ class, renderItem(item) -> node, items, empty })  ->  { el, add(item), setItems(items) }
//     Rows one under another. `empty` is the line shown while there are none.
ui.row = function (spec) {
  const text = ui.el("div", { class: "ui-row-text", title: spec.detail ? `${spec.title} - ${spec.detail}` : spec.title },
    spec.mark ? ui.el("span", { class: "ui-row-mark", text: spec.mark }) : null,
    ui.el("b", { text: spec.title }),
    spec.detail ? ui.el("span", { class: "ui-row-detail", text: " - " + spec.detail }) : null);
  return { el: ui.el("div", "ui-row" + (spec.class ? " " + spec.class : ""), text, ui.el("div", "ui-row-actions", spec.actions || []), spec.below || null) };
};

ui.list = function (spec) {
  const el = ui.el("div", "ui-list" + (spec.class ? " " + spec.class : ""));
  const handle = {
    el,
    add(item) { empty.remove(); el.append(spec.renderItem(item)); },
    setItems(items) {
      el.replaceChildren();
      if (!items.length && spec.empty) el.append(empty);
      for (const item of items) el.append(spec.renderItem(item));
    },
  };
  const empty = spec.empty ? ui.hint(spec.empty) : ui.el("span");
  handle.setItems(spec.items || []);
  return handle;
};
