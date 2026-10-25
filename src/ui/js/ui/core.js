// ===== UI components: the base =====
// Everything in js/ui/ hangs off one global, `ui` (ui.el, ui.icon, ui.button, ui.modal, ui.section, ui.confirm ...). These files load
// first, so any other script may use them. docs/ui-components.md says what a component is and what each one does.
const ui = {};

// Makes an element. `props` is a class name (string) or an object:
//   class, id, title, text (set as text, never as HTML), hidden, disabled, checked, value   - set on the element
//   attrs   { name: value }       - setAttribute (null / false skips one)
//   on      { click: fn, ... }    - addEventListener
// Children may be elements, strings, arrays of them, or nothing (null / false / undefined are skipped).
ui.el = function (tag, props, ...children) {
  const e = document.createElement(tag);
  if (typeof props === "string") props = { class: props };
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null) continue;
    if (key === "class") { if (value) e.className = value; }
    else if (key === "text") e.textContent = value;
    else if (key === "attrs") { for (const [n, v] of Object.entries(value)) if (v !== null && v !== false && v !== undefined) e.setAttribute(n, v === true ? "" : v); }
    else if (key === "on") { for (const [n, fn] of Object.entries(value)) e.addEventListener(n, fn); }
    else e[key] = value;
  }
  ui.append(e, children);
  return e;
};

ui.append = function (parent, children) {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) ui.append(parent, c);
    else parent.append(c);       // (a string becomes a text node; an element or fragment is added as it is)
  }
  return parent;
};

// Markup the app itself wrote, as a node to add. For string literals in the source only (a brand icon, say) - never anything that came
// from a mod, a file name or a message, which go in as text.
ui.html = function (markup) {
  const t = document.createElement("template");
  t.innerHTML = markup;
  return t.content;
};

// The older helper the screens still use: an element with a class and text. Same as ui.el(tag, { class, text }).
function cgEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
