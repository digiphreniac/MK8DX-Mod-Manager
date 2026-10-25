// ===== UI components: Disclosure (a section that folds away) =====
//   ui.disclosure({ summary, class, id, open, onToggle }, ...children)  ->  { el, summary, open }
// A <details> with its <summary> and the children after it, as they have always been laid out (the page's `details` rules in
// base.css draw the chevron, the indent and the line down the left, so this adds no styles of its own). `summary` is text, or a
// <summary> element you made (one with a button in it, say). onToggle(isOpen) runs when it opens or closes.
ui.disclosure = function (spec, ...children) {
  const el = ui.el("details", { class: spec.class, id: spec.id });
  if (spec.open) el.open = true;
  const summary = spec.summary instanceof Element ? spec.summary : ui.el("summary", { text: spec.summary });
  el.append(summary);
  ui.append(el, children);
  if (spec.onToggle) el.addEventListener("toggle", () => spec.onToggle(el.open));
  return { el, summary, get open() { return el.open; }, set open(value) { el.open = !!value; } };
};
