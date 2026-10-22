// ---- A mod that is for something other than the card it came from ----
// GameBanana files mods where the author put them, and the files inside often say something else: a Luigi mod on Mario's page, a
// tire mod on a kart's, a course retexture on the wrong course. One experience covers every kind of thing (a character, a course,
// a vehicle part, an item), and it talks about what a mod *replaces*, never about "slots" or "filing":
//   - after a download, a mod whose files are all for one other thing is moved there by the app (Api._refile_mod) and this opens
//     that thing's card with a note saying so - and an Undo;
//   - any mod's "..." menu has "Move to another <character / course / part / item>..." for when the guess was wrong (or absent);
//   - a mod the app can't place on its own (a pack that is for several things, say) says what it replaces and offers to move it.
// The move itself is Api.gb_move_mod: the folders, archives, tick and everything else remembered about the mod go with it.

const REFILE_NOUN = { characters: "character", courses: "course", vehicles: "part", wheels: "part", gliders: "part", items: "item" };
const REFILE_VIEW = { characters: "characters", courses: "courses", vehicles: "vehicles", wheels: "vehicles", gliders: "vehicles", items: "items" };

// "A, B and C"
function joinNames(names) { return names.length < 2 ? names.join("") : names.slice(0, -1).join(", ") + " and " + names[names.length - 1]; }
function refileLabel(name) { return isItemName(name) ? itemLabel(name) : name; }
function refileNoun(name) { return REFILE_NOUN[resolveItemCategory(name)] || "one"; }

// What a mod on `name`'s card can be moved to: the others of its kind, as [{name, label, group}]
function moveTargetsFor(name) {
  const cat = resolveItemCategory(name);
  if (cat === "characters") return state.roster.filter(r => r.name !== name).map(r => ({ name: r.name, label: r.name }));
  if (cat === "courses") {
    return state.cups.flatMap(cup => cup.courses.filter(c => c.name !== name).map(c => ({ name: c.name, label: c.name, group: cup.cup || cup.name })));
  }
  if (VEHICLE_SECTION_KEYS.includes(cat)) {
    return state.vehicles.flatMap(sec => sec.items.filter(i => i.name !== name).map(i => ({ name: i.name, label: i.name, group: sec.label || sec.key })));
  }
  if (cat === ITEMS_CATEGORY) return state.items.filter(i => i.name !== name).map(i => ({ name: i.name, label: itemLabel(i.name) }));
  return [];
}

// The mod has just been moved: go to where it is now, and say what happened.
// `info` = {from_item, to_item, mod_id, record_type, mod_name, moved_folders}. `auto`: the app did it after a download (the mod
// is new, so - like any fresh download - it is ticked when it is the only one its new home has); otherwise the user asked for it
// and its tick is left as it was.
async function finishRefile(info, opts) {
  const auto = !!(opts && opts.auto);
  await loadMods();   // (not just refreshViewsState: the move renamed the mod's ticked-state key too)
  let ticked = false;
  if (auto) {
    const entry = findRosterEntry(info.to_item);
    const only = entry && entry.units.length === 1 ? entry.units[0] : null;
    if (only && !state.checked[only]) {
      state.checked[only] = true;
      await saveChecked();
      ticked = true;
    }
  }
  const from = refileLabel(info.from_item), to = refileLabel(info.to_item);
  cardNotice = {
    item: info.to_item,
    text: auto
      ? (info.pack && info.pack.length > 1
          ? `"${info.mod_name}" is a pack: it replaces ${joinNames(info.pack.map(refileLabel))}. It's listed on each of their cards - ticking it turns on all of them.`
          : `"${info.mod_name}" replaces ${to}${info.from_item === ITEMS_OTHER ? "" : `, not ${from}`}, so it is now under ${to}.`)
        + (ticked ? " It's ticked - finish setting it up below." : "")
      : `Moved "${info.mod_name}" from ${from} to ${to}.`,
    undo: { ...info, ticked },
  };
  await showRefileTarget(info.to_item);
}

async function showRefileTarget(name) {
  switchView(REFILE_VIEW[resolveItemCategory(name)] || "characters");
  openCharacterModal(name);
  refreshBehindModal();
  // the card opens where the last one was scrolled to: bring the note (and the name above it) into view
  for (let el = document.querySelector(".cc-notice"); el; el = el.parentElement) el.scrollTop = 0;
}

// Moves a tracked mod and goes to it. Resolves to Api.gb_move_mod's result (nothing has happened when it failed).
async function refileMod({ from, to, modId, recordType, modName, auto }) {
  const r = await pywebview.api.gb_move_mod(from, modId, to, recordType || "Mod");
  if (!r.success) return r;
  await finishRefile({ from_item: from, to_item: to, mod_id: modId, record_type: recordType || "Mod", mod_name: modName, moved_folders: r.moved_folders }, { auto });
  return r;
}

// "Undo" on the note: put the mod back where it was (and, if the app ticked it, untick it again).
async function undoRefile(info) {
  const r = await pywebview.api.gb_move_mod(info.to_item, info.mod_id, info.from_item, info.record_type || "Mod");
  if (!r.success) {
    cardNotice = { item: info.to_item, text: `Couldn't undo that: ${r.error}` };
    await showRefileTarget(info.to_item);
    return;
  }
  await loadMods();
  if (info.ticked) {
    for (const folder of r.moved_folders || []) {
      for (const key of Object.keys(state.checked)) {
        if (key === folder || key.startsWith(folder + "/")) state.checked[key] = false;
      }
    }
    await saveChecked();
  }
  cardNotice = { item: info.from_item, text: `Put "${info.mod_name}" back under ${refileLabel(info.from_item)}.` };
  await showRefileTarget(info.from_item);
}

// The note at the top of a card (see cardNotice): built by openCharacterModal for whichever card is opening.
function buildCardNotice(name) {
  if (cardNotice && cardNotice.item !== name) cardNotice = null;   // (it was for another card)
  if (!cardNotice) return null;
  const shown = cardNotice;
  const note = cgEl("div", "cc-notice");
  note.appendChild(cgEl("span", null, shown.text));
  if (shown.undo) note.appendChild(button("Undo", "small", () => undoRefile(shown.undo)));
  note.appendChild(button("✕", "ghost small", () => { if (cardNotice === shown) cardNotice = null; note.remove(); }));
  return note;
}

// "Move to another <thing>..." from a mod's "..." menu: pick where, then go there.
function openMoveDialog({ from, modName, modId, recordType }) {
  const noun = refileNoun(from);
  const backdrop = cgEl("div", "mv-backdrop");
  const dialog = cgEl("div", "mv-dialog");
  dialog.setAttribute("role", "dialog");
  dialog.appendChild(cgEl("h3", null, `Move "${modName}" to another ${noun}`));
  dialog.appendChild(cgEl("p", "mv-note", `It is under ${refileLabel(from)} now. Pick the ${noun} it replaces - its files, its tick and its GameBanana record all move with it.`));
  const select = document.createElement("select");
  select.appendChild(new Option(`Choose a ${noun}...`, ""));
  const groups = new Map();
  for (const t of moveTargetsFor(from)) {
    let parent = select;
    if (t.group) {
      if (!groups.has(t.group)) {
        const g = document.createElement("optgroup");
        g.label = t.group;
        select.appendChild(g);
        groups.set(t.group, g);
      }
      parent = groups.get(t.group);
    }
    parent.appendChild(new Option(t.label, t.name));
  }
  dialog.appendChild(select);
  const err = cgEl("div", "gb-mod-error");
  const close = () => backdrop.remove();
  const go = button("Move", "primary", async () => {
    if (!select.value) return;
    go.disabled = true;
    go.textContent = "Moving...";
    const r = await refileMod({ from, to: select.value, modId, recordType, modName, auto: false });
    if (r.success) { close(); return; }
    go.disabled = false;
    go.textContent = "Move";
    err.textContent = r.error;
  });
  go.disabled = true;
  select.addEventListener("change", () => { go.disabled = !select.value; });
  const actions = cgEl("div", "mv-actions");
  actions.appendChild(button("Cancel", "ghost", close));
  actions.appendChild(go);
  dialog.appendChild(err);
  dialog.appendChild(actions);
  backdrop.appendChild(dialog);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  backdrop.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } });
  document.body.appendChild(backdrop);
  select.focus();
}
