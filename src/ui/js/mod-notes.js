// ---- The user's own notes on mods (backend: mod_notes.py). A mod's row on its card has a pencil button; it opens a small editor
// under the row. The tile of the character / course / part shows a pencil when one of its TICKED mods has a note. `state.notes` is
// {unit key: note text}, loaded with the mods; a change goes to the backend for that one mod (never the whole map - see
// saveChecked() for why), and is refused when the page's folder isn't the backend's current one.
const MN_SAVE_DELAY = 500;   // (ms of quiet after typing before a note is saved)

// A pencil (it takes its colour from the text around it).
function pencilSvg() {
  return ui.icon("pencil", { size: null, class: "mn-pencil" });
}

function unitNote(key) { return (state.notes && state.notes[key]) || ""; }

// The notes on the ticked mods among `units` - what a tile marks: [[mod name, note], ...].
function tickedNotes(units) {
  return units.filter(k => state.checked[k] && unitNote(k)).map(k => [k.split("/")[2] || k, unitNote(k)]);
}

// (goes into a screen's signature, so adding or changing a note on a ticked mod redraws the tiles - see entriesSignature)
function notesSignature(units) {
  let out = "";
  for (const k of units) {
    const n = state.checked[k] ? unitNote(k) : "";
    if (!n) continue;
    let h = 5381;
    for (const ch of n) h = ((h * 33) ^ ch.charCodeAt(0)) >>> 0;
    out += `${k.length}:${h}`;
  }
  return out ? "n" + out : "";
}

// The pencil on a tile (top left, under the voice mark), or null when none of its ticked mods has a note. Hovering it shows the notes.
function buildTileNote(units) {
  const notes = tickedNotes(units);
  if (!notes.length) return null;
  const mark = document.createElement("div");
  mark.className = "tile-note";
  mark.appendChild(pencilSvg());
  mark.title = "Your notes:\n" + notes.map(([mod, note]) => `${mod}: ${note.replace(/\s+/g, " ").slice(0, 160)}`).join("\n");
  mark.setAttribute("role", "img");
  mark.setAttribute("aria-label", mark.title);
  return mark;
}

// Saves go one at a time, in order (a slow one must not land after a newer one).
let modNoteChain = Promise.resolve();
function saveModNote(key, note) {
  const trimmed = note.trim();
  if (trimmed) state.notes[key] = trimmed; else delete state.notes[key];
  const run = async () => {
    if (state.epoch == null) return { success: false, error: "Still loading - try again in a moment." };
    let r;
    try { r = await pywebview.api.set_mod_note(key, note, state.epoch); } catch (e) { r = { success: false, error: String(e) }; }
    if (r && r.stale) loadMods();   // (this page is showing another folder's mods: reload it)
    return r || { success: false, error: "That didn't save." };
  };
  const result = modNoteChain.then(run, run);
  modNoteChain = result.then(() => {}, () => {});
  return result;
}

// Redraw the tiles behind the card after a change (only screens whose signature changed - see viewSignature).
function refreshTilesForNotes() {
  redrawViews(["characters", "courses", "vehicles", "items", "more"], { ifChanged: true });
}

// The pencil button on a mod's row and the editor it opens under the row. Returns the button - the caller puts it in the row.
// It is faint when the mod has no note and in the accent colour when it has one.
function buildModNoteControl(key, row) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mn-btn";
  btn.appendChild(pencilSvg());
  let panel = null, timer = null;

  function paintButton() {
    const n = unitNote(key);
    btn.classList.toggle("has-note", !!n);
    btn.title = n ? n + "\n(click to edit your note)" : "Add a note to this mod (only you see it)";
  }

  function buildPanel() {
    const p = document.createElement("div");
    p.className = "mn-panel";
    const status = document.createElement("span");
    status.className = "mn-status";
    const text = document.createElement("textarea");
    text.className = "mn-text";
    text.rows = 3;
    text.maxLength = 4000;
    text.placeholder = "Notes about this mod - only you see them (what it changes, what to check, where you found it...)";
    text.value = unitNote(key);

    async function save() {
      clearTimeout(timer);
      timer = null;
      status.textContent = "Saving...";
      status.classList.remove("bad");
      const r = await saveModNote(key, text.value);
      status.textContent = r.success ? "Saved" : (r.error || "Couldn't save");
      status.classList.toggle("bad", !r.success);
      paintButton();
      refreshTilesForNotes();
    }

    p.appendChild(text);
    text.addEventListener("input", () => { status.textContent = ""; clearTimeout(timer); timer = setTimeout(save, MN_SAVE_DELAY); });
    text.addEventListener("blur", () => { if (timer !== null) save(); });
    const foot = document.createElement("div");
    foot.className = "mn-foot";
    foot.appendChild(status);
    p.appendChild(foot);
    p._text = text;
    return p;
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (panel) { if (timer !== null) panel._text.dispatchEvent(new Event("blur")); panel.remove(); panel = null; row.classList.remove("mn-open"); return; }
    panel = buildPanel();
    row.after(panel);
    row.classList.add("mn-open");
    panel._text.focus();
  });
  paintButton();
  return btn;
}
