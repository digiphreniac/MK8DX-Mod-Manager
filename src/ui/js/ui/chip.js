// ===== UI components: Chip (a small rounded label) =====
//   ui.chip({ text, tone, size, bold, solid, caps, class, title })  ->  { el, set(text, tone) }
//     tone    "neutral" (default) | "ok" | "warn" | "accent"
//     size    "sm" (default) | "md"
//     bold    heavier text;  solid  a filled "ok" chip (white text);  caps  small bold capitals (a pill like "RECOMMENDED")
// set() changes the text and/or the tone of a chip that is already on the page (a card's status chip as the mod list changes).
ui.chip = function (spec = {}) {
  const el = ui.el("span", { title: spec.title });
  let tone = spec.tone || "neutral";
  const paint = () => {
    el.className = ["ui-chip", `ui-chip--${spec.size || "sm"}`, `ui-chip--${tone}`, spec.bold && "ui-chip--bold", spec.solid && "ui-chip--solid",
      spec.caps && "ui-chip--caps", spec.class].filter(Boolean).join(" ");
  };
  if (spec.text !== undefined) el.textContent = spec.text;
  paint();
  return {
    el,
    set(text, nextTone) {
      if (text !== undefined) el.textContent = text;
      if (nextTone) tone = nextTone;
      paint();
    },
  };
};
