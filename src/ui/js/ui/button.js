// ===== UI components: Button =====
//   ui.button({
//     label, icon, title,        text; an icon (a name from ui.icons, or a node); a tooltip (required when there is no label)
//     variant, size,             "primary" | "ghost" | "danger" | "" ; "small" - the app's existing button styles
//     id, attrs,
//     onClick(event, value),     may be async: the button is disabled (and shows busyLabel) until it settles; a failure is reported
//     busyLabel,
//     confirm,                   options for ui.confirm (or a function returning them): the click asks first, and onClick runs only on a
//                                yes (`value` is the dialog's checkbox, if it has one)
//     disabled,
//   })  ->  { el, setDisabled(bool), setBusy(bool), setLabel(text) }
ui.button = function (spec) {
  const classes = ["ui-btn"];
  if (spec.variant) classes.push(spec.variant);
  if (spec.size) classes.push(spec.size);
  if (spec.class) classes.push(spec.class);
  const el = ui.el("button", { class: classes.join(" "), id: spec.id, title: spec.title, disabled: !!spec.disabled, attrs: { type: "button", ...spec.attrs } });

  let labelEl = el;
  if (spec.icon) {
    const icon = typeof spec.icon === "string" ? ui.icon(spec.icon, { size: 16 }) : spec.icon;
    el.append(icon);
    if (spec.label) { labelEl = ui.el("span", "ui-btn-label"); el.append(labelEl); }
  }
  if (spec.label) labelEl.textContent = spec.label;
  else if (spec.title) el.setAttribute("aria-label", spec.title);

  let label = spec.label || "", busy = false, disabled = !!spec.disabled;
  const handle = {
    el,
    setLabel(text) { label = text; if (!busy && spec.label !== undefined) labelEl.textContent = text; },
    setDisabled(value) { disabled = !!value; if (!busy) el.disabled = disabled; },
    setBusy(value) {
      busy = !!value;
      el.disabled = busy || disabled;
      el.classList.toggle("is-busy", busy);
      if (spec.label !== undefined) labelEl.textContent = busy && spec.busyLabel ? spec.busyLabel : label;
    },
  };

  el.addEventListener("click", async (event) => {
    if (busy || el.disabled) return;
    let value;
    if (spec.confirm) {
      const answer = await ui.confirm(typeof spec.confirm === "function" ? spec.confirm() : spec.confirm);
      if (!answer) return;
      value = answer.value;
    }
    if (!spec.onClick) return;
    try {
      const result = spec.onClick(event, value);
      if (result && typeof result.then === "function") {
        handle.setBusy(true);
        await result;
      }
    } catch (e) {
      const message = e && e.message ? e.message : String(e);
      if (typeof diag !== "undefined") diag.error("button", message);
      ui.alert({ title: "That didn't work", message });
    } finally {
      if (busy) handle.setBusy(false);
    }
  });
  return handle;
};

// The older helper: a plain button with a class string and a click handler. New code uses ui.button.
function button(text, cls, onclick) {
  const b = cgEl("button", cls, text);
  b.addEventListener("click", onclick);
  return b;
}
