// ===== UI components: icons =====
// The app's small line icons, drawn as inline SVG so they look the same whatever fonts the computer has and take the text's colour.
// ui.icon("warning") returns an <svg> element to add; add a new icon here, once, rather than pasting its SVG where it is used.
ui.icons = {
  warning: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  todo: '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="m12 16 4-4-4-4"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
};

ui.icon = function (name, { size = 18 } = {}) {
  const inner = ui.icons[name];
  if (!inner) throw new Error("No icon called " + name);
  const holder = document.createElement("template");
  holder.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" ` +
    `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  return holder.content.firstElementChild;
};
