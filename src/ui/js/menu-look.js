// ---- What each mod unit really writes to (Api.get_unit_slots) ----
// A unit can replace ANOTHER character's slot (Sunshine "over Metal Mario", Shrek "over
// Donkey Kong") or be one of several identical-slot variants of the same mod (ten Luma
// colours, twelve menu-sound options). "Select All" leaves both kinds out: ticking them
// all would make them clash with each other or with the mods of other characters.
const unitSlots = {};
async function loadUnitSlots(keys) {
  const need = keys.filter(k => !(k in unitSlots));
  if (!need.length) return;
  try { Object.assign(unitSlots, await pywebview.api.get_unit_slots(need)); } catch (e) { /* the buttons still work without it */ }
}
// Of several identical-slot variants "Select All" ticks ONE: the one already ticked, else the first.
function twinRepresentative(key) {
  const u = unitSlots[key];
  if (!u || u.twins < 2) return key;
  const mates = Object.keys(unitSlots).filter(k => unitSlots[k].twin_group === u.twin_group);
  return mates.find(k => state.checked[k]) || mates.find(k => unitSlots[k].twin_first) || key;
}
// Mods that each replace the character's MODEL (Driver files) for the same slot can't be used together:
// they are pick-one, like the colours / options of a single mod. `null` when this one isn't such a mod.
function modelGroup(key) {
  const u = unitSlots[key];
  if (!u || !(u.parts || []).includes("Character") || !(u.characters || []).length) return null;
  return key.split("/")[1] + "|" + u.characters.join(",");
}
function modelRepresentative(key) {
  const g = modelGroup(key);
  const entry = findRosterEntry(key.split("/")[1]);
  const mates = entry ? entry.units.filter(k => modelGroup(k) === g) : [key];
  return mates.find(k => state.checked[k]) || mates[0] || key;
}
function skipsSelectAll(key) {
  const u = unitSlots[key];
  if (!u) return false;
  if (u.mismatch) return true;
  if (modelGroup(key) && modelRepresentative(key) !== key) return true;
  return u.twins > 1 && twinRepresentative(key) !== key;
}
function unitSlotBadges(key, itemName) {
  const u = unitSlots[key];
  const out = [];
  if (!u) return out;
  if (u.mismatch) {
    const b = cgEl("span", "packed-badge", "replaces " + u.characters.join(" / "));
    b.title = `This one replaces ${u.characters.join(" / ")}'s slot, not ${itemName}'s. "Select All" skips it - select it yourself if that's what you want.`;
    out.push(b);
  } else if (u.twins > 1) {
    const b = cgEl("span", "packed-badge", `one of ${u.twins} variants`);
    b.title = `${u.twins} versions of this mod write exactly the same files (colours / options) - they'd clash if selected together. "Select All" selects only the first.`;
    out.push(b);
  }
  return out;
}

// Which file of a multi-file mod to tick first: the newest / fullest / the one named for this
// item, not an old, alternate or optional one. Only a suggestion - the rest stay unticked.
function suggestFiles(files, itemName) {
  if (files.length < 2 || files.some(f => f.download_status === "downloaded")) return new Set();
  const tokens = itemName.toLowerCase().split(/[^a-z0-9]+/).filter(t => t.length >= 3);
  const ver = f => { const m = ((f.name || "") + " " + (f.description || "")).match(/(\d+(?:\.\d+)+)/); return m ? parseFloat(m[1]) : null; };
  const versions = files.map(ver);
  const maxVer = Math.max(...versions.map(v => v == null ? -1 : v));
  const score = (f, i) => {
    const n = (f.name || "").toLowerCase();
    const t = n + " " + (f.description || "").toLowerCase();
    let sc = 0;
    if (/current|latest|newest|updated|fixed|final/.test(t)) sc += 3;
    if (/full (mod)?pack|complete/.test(t)) sc += 2;
    if (tokens.some(x => t.includes(x))) sc += 2;
    if (versions[i] != null && versions[i] === maxVer && new Set(versions).size > 1) sc += 1;
    if (/\bold\b|old version|outdated|legacy|deprecated/.test(t)) sc -= 4;
    if (/optional|\balt\b|alternate|recolou?r|famicom|lite\b|victory|music/.test(t)) sc -= 2;
    if (f.other_character_hint) sc -= 3;
    return sc;
  };
  const scored = files.map((f, i) => [score(f, i), f]);
  const best = Math.max(...scored.map(x => x[0]));
  const top = scored.filter(x => x[0] === best);
  return new Set((top.length === files.length ? [files[0]] : top.map(x => x[1])).map(f => f.file_id));
}

// ---- Menu look: what the menus show for a character, and adding an
// icon or name a mod doesn't ship (ui_setup's "Your changes"). (A course's card is
// course-card.js.) When the app needs the user's pick
// (a mod ships several versions of its icons) that is the ONLY thing shown.
// There is deliberately no answer cache: what the card shows depends on which mods
// are ticked and downloaded, and a stale answer is exactly the bug that would cause.
// `reload` re-reads the card that is currently open (set by buildMenuLookCard).
const menuLookState = { cache: new Map(), reload: null, pending: null, timer: null };

// The game's own pictures kept by the page (the game's files changed, so they may have): asked for afresh next time.
function resetPictureCaches() {
  for (const k of Object.keys(characterIconCache)) delete characterIconCache[k];
  for (const k of Object.keys(courseDefaultPictures)) delete courseDefaultPictures[k];
  cupIcons = {};
  vehicleIcons = {};
  itemIcons = {};
}

function invalidateMenuLook() {
  menuLookState.cache.clear();
  uiSetup.data = null; // Settings' "Game language" card must re-read
  scheduleFlowRefresh();
}

// The three icons of a version/slot, in the order a player meets them.
const ML_KINDS = [
  ["Chara", "Select screen", "Shown when you pick your character"],
  ["MapChara", "Mini map", "The marker on the course map during a race"],
  ["edChara", "Results screen", "Shown next to your name in the race results"],
];

function mlThumb(src, caption, slot) {
  const t = cgEl("div", "ml-tile");
  if (src) {
    const img = document.createElement("img");
    img.src = src;
    img.alt = caption;
    t.appendChild(img);
  } else {
    t.appendChild(cgEl("div", "ml-blank", "game's own"));
  }
  if (caption) t.appendChild(cgEl("div", "ml-label", caption));
  if (slot && slot.variants > 1 && slot.changed > 0) {
    t.appendChild(cgEl("div", "ml-sub", slot.changed === slot.variants ? `all ${slot.variants} colours` : `${slot.changed} of ${slot.variants} colours`));
  }
  if (slot && slot.resized) {
    const r = cgEl("div", "ml-sub", "resized to fit");
    r.title = "The mod's picture is a different size than the game's own, so the app scales it to fit.";
    t.appendChild(r);
  }
  if (slot && slot.blocked) {
    const b = cgEl("div", "ml-sub warn", "can't apply");
    b.title = slot.blocked.reason || "";
    t.appendChild(b);
  }
  return t;
}

// One version of a mod's loose icon pictures, as a card with a real button.
function mlVersionCard(name, mod, set, changed, primary) {
  const card = cgEl("div", "ml-choice");
  const thumbs = cgEl("div", "ml-row");
  for (const [kind, caption] of ML_KINDS) {
    const k = set.kinds[kind];
    if (k) thumbs.appendChild(mlThumb(k.preview, caption));
  }
  card.appendChild(thumbs);
  const foot = cgEl("div", "ml-choice-foot");
  const cols = set.colours || 1;
  foot.appendChild(cgEl("span", "ml-choice-label", set.label + (set.complete ? "" : " - only " + Object.keys(set.kinds).length + " of 3 icons")
    + (cols > 1 ? ` \u00b7 ${cols} colours` + (set.count < cols * 3 ? ` (${set.count} of ${cols * 3} pictures)` : "")
                : (set.count > 3 ? ` (${set.count} pictures)` : ""))));
  if (set.for) card.appendChild(cgEl("div", "cg-note", `These pictures are named for ${set.for}, not ${name} - they were not applied automatically.`));
  const use = button(set.for ? `Use these for ${name} anyway` : "Use these for " + name, primary && !set.for ? "primary small" : "small", async () => {
    use.disabled = true;
    const r = await pywebview.api.use_loose_icon_set(name, mod.mod, set.id);
    if (!r.success) { use.textContent = r.error; return; }
    changed();
  });
  foot.appendChild(use);
  card.appendChild(foot);
  return card;
}

