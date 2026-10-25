// ===== UI components: Tile (a picture, a name and how many of its mods are selected) =====
// The tile of the character, course, vehicle and item screens and of a course's cup. The page turns what it knows (which mods are selected,
// whether a download was tried) into the options; the tile draws them and knows nothing about mods.
//   const t = ui.tile({
//     key,              what the tile is called (data-char: the page finds the tile again by it)
//     label,            the name under the picture
//     badge,            the letters shown until a picture is there (null: none)
//     selected, total,  how many of its mods are ticked, out of how many it has
//     count,            how that is shown: "line" (a line at the bottom), "bubble" (a bubble on top of the picture) or "quiet" (no numbers,
//                       a small dot only while mods are downloaded and none is ticked; the numbers are in its tooltip)
//     attention,        a download was tried and gave nothing usable: the tile says it needs a look instead of "no mods"
//     background,       a CSS background-image (the corner colours of a character)
//     note,             a node to add last (a pencil when one of its ticked mods has a note)
//     onClick,
//   })  ->  { el, badge, nameEl }
//   ui.tile.markConflict(tile, title)      the red "!" for two ticked mods that write the same file
//   ui.tile({ variant: "cup", key, label, page, selected, bubble, active, onClick })      a cup on the Courses screen: a button with
//     the cup's picture (the page paints it: paintCupTile), a bubble ("3/4": its modded courses), and no name line - the name plate has it
// The classes (char-tile, char-badge, char-name, char-count, tile-count-bubble ...) and tiles-and-grids.css are how the screens style and find
// tiles; they were kept as they were.
ui.tile = function (spec) {
  if (spec.variant === "cup") return cupTile(spec);
  const total = spec.total || 0, selected = spec.selected || 0;
  const el = ui.el("div", "char-tile");
  el.dataset.char = spec.key;
  if (selected > 0) el.classList.add("has-selected");
  if (total === 0) el.classList.add("no-mods");
  if (spec.background) {
    el.classList.add("has-gradient");
    el.style.backgroundImage = spec.background;
  }
  if (spec.onClick) el.addEventListener("click", spec.onClick);

  // A download was tried but produced nothing that can be merged (needs a manual fix, no romfs folder ...). Without this that looked the same as
  // "nobody has touched this yet", so it was easy to lose track of while scanning the grid for what is left.
  if (spec.attention && total === 0) {
    el.classList.add("needs-attention");
    el.append(ui.el("div", { class: "char-attention-dot", title: "Downloaded, but couldn't be auto-merged - open it to see why" }));
  }

  let badge = null;
  if (spec.badge !== null && spec.badge !== undefined) {
    badge = ui.el("div", { class: "char-badge", text: spec.badge });
    el.append(badge);
  }
  const nameEl = ui.el("div", { class: "char-name", text: spec.label });
  el.append(nameEl);

  if (total === 0) {
    if (spec.attention) {
      el.append(ui.el("div", { class: "char-count count-attention", text: "needs attention" }));
    } else {
      // No visible text for the plain "nothing downloaded yet" case: the tile is faded (.no-mods) to say so at a glance, and the words are in
      // its tooltip. Also kept as data-count-note, which the character screen reads back and folds in with whatever its picture's note says.
      el.title = el.dataset.countNote = "No mods yet";
    }
  } else if (spec.count === "quiet") {
    el.dataset.countNote = `${selected} of ${total} mod${total === 1 ? "" : "s"} selected`;
    if (selected === 0) el.append(ui.el("div", { class: "tile-pending-dot", title: `${total} mod${total === 1 ? "" : "s"} downloaded - none selected yet` }));
  } else if (spec.count === "bubble") {
    // like a notification, so it can sit on top of a course picture instead of pushing it down
    el.append(ui.el("div", { class: "tile-count-bubble", text: `${selected}/${total}`, title: `${selected}/${total} selected` }));
  } else {
    el.append(ui.el("div", { class: "char-count", text: `${selected}/${total} selected` }));
  }

  if (spec.note) el.append(spec.note);
  return { el, badge, nameEl };
};

function cupTile(spec) {
  const el = ui.el("div", { class: "cup-tile", attrs: { role: "button", "aria-label": spec.label || spec.key } });
  el.dataset.cup = spec.key;
  el.dataset.page = spec.page;
  el.classList.add(spec.selected > 0 ? "has-selected" : "no-mods");
  if (spec.active) el.classList.add("active");
  if (spec.onClick) el.addEventListener("click", spec.onClick);
  if (spec.bubble) el.append(ui.el("div", { class: "tile-count-bubble", text: spec.bubble }));
  return { el, badge: null, nameEl: null };
}

ui.tile.markConflict = function (tile, title) {
  tile.classList.add("has-conflict");
  tile.append(ui.el("div", { class: "char-conflict-badge", text: "!", title }));
};
