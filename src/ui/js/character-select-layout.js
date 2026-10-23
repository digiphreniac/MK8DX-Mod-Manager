// ---- Character Select: the card docked beside the grid, or a pop-up on a small window ----
// A character's card (mods to merge, menu look, GameBanana) is built by openCharacterModal() into
// whichever container this picks. `dockedKey` is what the docked card shows; `openCharacter` stays the pop-up's
// own state. (A group tile like Villager stays marked while either of its two characters is shown - see tileKeyFor.)
const DOCK_MIN_WIDTH = 1100;   // narrower than this, the card is a pop-up
let dockedKey = null;

function dockedLayout() { return window.innerWidth >= DOCK_MIN_WIDTH; }
function wantsDock(name) {
  if (!dockedLayout()) return false;
  if (viewMode === "items") return name === null || isItemName(name);   // (Items has its own card: item-screen.js)
  return viewMode === "characters" && (name === null || isCharacterName(name));
}

// The grid item that a character is one of two of (Villager: Boy and Girl), or undefined.
function variantItemOf(name) {
  return CHARACTER_GRID_LAYOUT.find(it => typeof it !== "string" && it.options.includes(name));
}

// Which of a group's two characters its tile opens: the one already in the card; else one that still needs its
// appearance looked at, else one with ticked mods, else either - and among those, the one used last.
const variantLast = {};   // group -> the option last shown
function defaultVariant(item) {
  const cur = dockedKey !== null ? dockedKey : openCharacter;
  if (cur && item.options.includes(cur)) return cur;
  const needs = item.options.filter(o => { const r = characterReview[o]; return reviewApplicable(r) && !reviewFinished(r); });
  const ticked = item.options.filter(o => findRosterEntry(o).units.some(k => state.checked[k]));
  const pool = needs.length ? needs : ticked.length ? ticked : item.options;
  return pool.includes(variantLast[item.group]) ? variantLast[item.group] : pool[0];
}

// The two-way switch at the top of a Villager / Inkling card. It redraws when the looks or ticks change
// (variantSwitchRefresh, called from scheduleCharacterLooks).
let variantSwitchRefresh = null;
function buildVariantSwitch(item, current) {
  const bar = cgEl("div", "variant-switch");
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", `${item.group}: which one you are working on`);
  function draw() {
    bar.replaceChildren();
    for (const opt of item.options) {
      const entry = findRosterEntry(opt);
      const look = characterLooks[opt] || {};
      const rev = characterReview[opt];
      const total = entry.units.length;
      const ticked = entry.units.filter(k => state.checked[k]).length;
      const label = groupOptionLabel(opt, item.group);
      const btn = cgEl("button", "variant-opt" + (opt === current ? " on" : ""));
      btn.type = "button";
      btn.setAttribute("aria-pressed", opt === current ? "true" : "false");
      if (look.icon) {
        const img = document.createElement("img");
        img.className = "variant-thumb";
        img.src = look.icon;
        img.alt = "";
        btn.appendChild(img);
      } else {
        btn.appendChild(cgEl("span", "variant-thumb ph"));
      }
      const text = cgEl("span", "variant-text");
      text.appendChild(cgEl("b", null, label));
      let sub = look.name || (total === 0 ? (entry.gb_attempted ? "needs attention" : "no mods yet") : `${ticked}/${total} selected`);
      const small = cgEl("small", total === 0 && entry.gb_attempted && !look.name ? "attention" : null, sub);
      text.appendChild(small);
      btn.appendChild(text);
      if (reviewApplicable(rev)) {
        const todo = !reviewFinished(rev);
        const mark = cgEl("span", "variant-mark " + (todo ? "todo" : "done"), todo ? "" : "\u2713");
        mark.title = todo ? "Mod selected - open it to finish its name and icons" : "Completed";
        btn.appendChild(mark);
      }
      btn.title = `${item.group} (${label})` + (look.name ? ` - shown in the menus as ${look.name}` : "");
      btn.addEventListener("click", () => { if (opt !== current) selectCharacter(opt); });
      bar.appendChild(btn);
    }
  }
  draw();
  variantSwitchRefresh = () => { if (bar.isConnected) draw(); };
  return bar;
}

// which grid tile stands for a character (the Inkling tile stands for Inkling Boy and Girl)
function tileKeyFor(name) {
  for (const item of CHARACTER_GRID_LAYOUT) {
    if (typeof item !== "string" && (item.group === name || item.options.includes(name))) return item.group;
  }
  return name;
}

function markActiveTile() {
  const key = dockedKey !== null ? tileKeyFor(dockedKey) : (viewMode === "characters" && openCharacter !== null ? tileKeyFor(openCharacter) : null);
  for (const tile of document.querySelectorAll("#char-grid .char-tile")) tile.classList.toggle("active", key !== null && tile.dataset.char === key);
  updateNameBar();
  markActiveVehicle();
  markActiveItem();
}

function applyCharacterLayout() {
  const docked = dockedLayout();
  document.getElementById("char-layout").classList.toggle("docked", docked);
  document.getElementById("view-characters").classList.toggle("docked", docked);
  fitCharacterGrid();
}

// The biggest square tile at which the whole grid (8 columns, however many rows there are, gaps
// 12% of a tile) fits its column - by width or by height, whichever runs out first.
function fitCharacterGrid() {
  const col = document.getElementById("char-grid-col");
  const grid = document.getElementById("char-grid");
  if (!dockedLayout() || !col.clientWidth) return;
  const cs = getComputedStyle(col);
  const W = col.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  // (the board hugs its grid, so the room there is is the layout's height, less the board's own padding and border)
  const H = document.getElementById("char-layout").clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)
    - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth);
  const rows = Math.max(1, Math.ceil(grid.querySelectorAll(".char-tile").length / 8)) + (grid.querySelector(".char-grid-other-heading") ? 1 : 0);
  const K = 0.12;
  const t = Math.floor(Math.min(W / (8 + 7 * K), H / (rows + (rows - 1) * K)));
  if (t >= 24) grid.style.setProperty("--tile", t + "px");
}
new ResizeObserver(fitCharacterGrid).observe(document.getElementById("char-grid-col"));
new ResizeObserver(fitCharacterGrid).observe(document.getElementById("char-layout"));

// Character Select always has a character in the card (no empty state): the one last viewed, else Mario.
let lastDockedKey = null;
function ensureDockedSelection() {
  if (!dockedLayout() || viewMode !== "characters" || dockedKey !== null) return;
  if (!state.roster || !state.roster.length) return;
  openCharacterModal(lastDockedKey && findRosterEntry(lastDockedKey) ? lastDockedKey : "Mario");
}

// The name plate: the viewed character's name as the menus will show it - the modded name when a mod
// (or you) changed it, else the game's own. (For a group tile under the mouse: each variant's, "Boy: Yoda - Girl: Pinkie Pie".)
// While the mouse is over a tile the plate shows THAT character (as the game's select screen does as the
// cursor moves); otherwise it shows the selected one.
let hoverTileEl = null;
function updateNameBar() {
  const plate = document.getElementById("char-name-plate");
  let display = null, keys = null;
  if (hoverTileEl && hoverTileEl.isConnected) {
    display = hoverTileEl.dataset.char;
    keys = hoverTileEl._lookNames || [display];
  } else if (dockedKey !== null) {
    display = dockedKey;
    keys = [dockedKey];
  }
  plate.replaceChildren();
  if (display === null) { plate.classList.remove("show"); return; }
  const vs = hoverTileEl && hoverTileEl.isConnected ? hoverTileEl._variants : null;
  const names = vs
    ? vs.map(v => { const n = (characterLooks[v.name] || {}).name; return n ? `${v.label}: ${n}` : null; }).filter(Boolean)
    : keys.map(k => (characterLooks[k] || {}).name).filter(Boolean);
  const shown = names.length ? names.join(vs ? " \u00b7 " : " / ") : display;
  plate.append(shown);
  if (shown !== display) {   // a modded name: the game's own follows, smaller and dimmer
    const base = document.createElement("span");
    base.className = "np-base";
    base.textContent = `(${display})`;
    plate.appendChild(base);
  }
  plate.classList.add("show");
}
document.getElementById("char-grid").addEventListener("mouseover", (e) => {
  const tile = e.target.closest(".char-tile");
  if (tile && tile !== hoverTileEl) { hoverTileEl = tile; updateNameBar(); }
});
document.getElementById("char-grid").addEventListener("mouseleave", () => { hoverTileEl = null; updateNameBar(); });

// The card goes away (the window became too small for it, or Character Select was left at a small size).
function closeDetail() {
  dockedKey = null;
  document.getElementById("char-detail-title").textContent = "";
  document.getElementById("char-detail-body").innerHTML = "";
  markActiveTile();
}

// Called at the start of building a card: decides pop-up vs. docked and returns where to build it.
function beginDetail(docked, key) {
  const backdrop = document.getElementById("modal-backdrop");
  backdrop.classList.remove("above-settings");
  if (docked && viewMode === "items") return beginItemDetail(key);
  if (docked) {
    backdrop.hidden = true;   // a pop-up left open for a character gives way to the docked card
    openCharacter = null;
    dockedKey = key;
    if (isCharacterName(key)) lastDockedKey = key;
    applyCharacterLayout();
    return { title: document.getElementById("char-detail-title"), body: document.getElementById("char-detail-body") };
  }
  dockedKey = null;
  openCharacter = key;
  return { title: document.getElementById("modal-title"), body: document.getElementById("modal-body") };
}

// ...and at the end: show the pop-up, or mark the tile and scroll the docked card to its top.
function endDetail(docked) {
  if (docked && viewMode === "items") {
    document.getElementById("item-detail-body").scrollTop = 0;
  } else if (docked) {
    document.getElementById("char-detail-body").scrollTop = 0;
  } else {
    document.getElementById("modal-backdrop").hidden = false;
  }
  markActiveTile();
}

applyCharacterLayout();

// The window was resized across the threshold: a pop-up that is open for a character moves into the card
// (and the card always has a character); shrinking just takes the card away - nothing pops up by itself.
let dockResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(dockResizeTimer);
  dockResizeTimer = setTimeout(() => {
    const was = document.getElementById("char-layout").classList.contains("docked");
    applyCharacterLayout();
    const now = dockedLayout();
    if (was === now || viewMode !== "characters") return;
    if (now && openCharacter !== null && isCharacterName(openCharacter)) {   // pop-up -> docked
      const n = openCharacter;
      closeModal();
      openCharacterModal(n);
    } else if (now) {
      ensureDockedSelection();
    } else if (dockedKey !== null) {
      closeDetail();
    }
  }, 150);
});

// Several things that change what is behind a card often follow one another within moments (a tick, then a conflict check settling,
// then the file list closing); each used to redraw everything. The redraw is now started once, shortly after the last of them:
// `ifChanged` (a plain tick - see viewSignature) only if EVERY one of them said so.
const behindRedraw = { timer: null, ifChanged: true };
function runBehindRedraw() {
  const ifChanged = behindRedraw.ifChanged;
  behindRedraw.timer = null;
  behindRedraw.ifChanged = true;
  redrawViews(["characters", "courses", "vehicles", "items", "more"], { ifChanged });
}

function refreshBehindModal(opts) {
  scheduleFlowRefresh();
  menuLookState.cache.clear();
  if (menuLookState.pending) menuLookState.pending();   // the open card's Appearance shows it is reading again, right away
  // the tick that caused this is saved by now (its call was made first); re-read the open Menu look card
  clearTimeout(menuLookState.timer);
  menuLookState.timer = setTimeout(() => { if (menuLookState.reload) menuLookState.reload(); }, 450);
  behindRedraw.ifChanged = behindRedraw.ifChanged && !!(opts && opts.ifChanged);
  if (behindRedraw.timer === null) behindRedraw.timer = setTimeout(runBehindRedraw, 60);
}

// The mod "Use this mod" just added: bring it into view; with one file, download it right away - with
// several, say what to do (the newest / fullest is already ticked).
function focusAddedMod(block, mod) {
  block.classList.add("gb-just-added");
  setTimeout(() => block.scrollIntoView({ block: "nearest", behavior: "smooth" }), 60);
  const dl = block._dlBtn;
  if (!dl) return;
  const one = mod.files.length === 1 ? mod.files[0] : null;
  if (one && one.download_status === "not_downloaded" && !one.other_character_hint) {
    setTimeout(() => { if (dl.isConnected) dl.click(); }, 250);
  } else if (block._blockBody) {
    const note = document.createElement("div");
    note.className = "gb-choose-note";
    note.textContent = mod.files.length > 1 ? "Choose which files to download, then press Download." : "Check the file, then press Download.";
    block._blockBody.prepend(note);
  }
}

