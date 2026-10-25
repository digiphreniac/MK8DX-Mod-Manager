// ===== UI components: Tabs and Segmented =====
//   ui.tabs({ el, id, items: [{ id, label }], active, onChange(id), label })  ->  { el, setActive(id), setCount(id, n), active }
//     A row of tab buttons (the app's main Characters / Courses / ... tabs); a button's id is "tab-<item id>".
//     `el` (optional) is an element already on the page to fill instead of making a new one. setCount(id, n) shows "Label (n)" (nothing
//     when n is 0). onChange runs when a tab is clicked, also when it is the one already showing (the page redraws its screen then).
//   ui.segmented({ el, items: [{ id, icon, title }], value, onChange(id), label, class })  ->  { el, setValue(id), value }
//     Two or three icon buttons of which one is on (the GameBanana window's grid / list switch). onChange runs only when the value changes.
ui.tabs = function (spec) {
  const el = spec.el || ui.el("div", { id: spec.id });
  el.replaceChildren();
  el.setAttribute("role", "tablist");
  if (spec.label) el.setAttribute("aria-label", spec.label);
  const buttons = new Map();
  let active = null;
  const handle = {
    el,
    get active() { return active; },
    setActive(id) {
      active = id;
      for (const [key, b] of buttons) {
        b.classList.toggle("active", key === id);
        b.setAttribute("aria-selected", key === id ? "true" : "false");
      }
    },
    setCount(id, n) {
      const item = spec.items.find(i => i.id === id);
      buttons.get(id).textContent = n ? `${item.label} (${n})` : item.label;
    },
  };
  for (const item of spec.items) {
    const b = ui.el("button", { id: "tab-" + item.id, text: item.label, attrs: { type: "button", role: "tab" }, on: { click: () => spec.onChange(item.id) } });
    buttons.set(item.id, b);
    el.append(b);
  }
  handle.setActive(spec.active !== undefined ? spec.active : null);
  return handle;
};

ui.segmented = function (spec) {
  const el = spec.el || ui.el("div", { class: spec.class });
  el.replaceChildren();
  el.setAttribute("role", "group");
  if (spec.label) el.setAttribute("aria-label", spec.label);
  const buttons = new Map();
  let value = null;
  const handle = {
    el,
    get value() { return value; },
    setValue(id) {
      value = id;
      for (const [key, b] of buttons) {
        b.classList.toggle("on", key === id);
        b.setAttribute("aria-pressed", key === id ? "true" : "false");
      }
    },
  };
  for (const item of spec.items) {
    const b = ui.el("button", {
      title: item.title, attrs: { type: "button", "data-view": item.id },
      on: { click: () => { if (value === item.id) return; handle.setValue(item.id); spec.onChange(item.id); } },
    }, typeof item.icon === "string" ? ui.html(item.icon) : item.icon);
    buttons.set(item.id, b);
    el.append(b);
  }
  handle.setValue(spec.value !== undefined ? spec.value : null);
  return handle;
};
