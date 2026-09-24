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
    b.title = `This one replaces ${u.characters.join(" / ")}'s slot, not ${itemName}'s. "Select All" skips it - tick it yourself if that's what you want.`;
    out.push(b);
  } else if (u.twins > 1) {
    const b = cgEl("span", "packed-badge", `one of ${u.twins} variants`);
    b.title = `${u.twins} versions of this mod write exactly the same files (colours / options) - they'd clash if ticked together. "Select All" ticks only the first.`;
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

// A short name a mod could give its character: "Sandy Cheeks in Mario Kart 8 Deluxe" -> "Sandy Cheeks".
function suggestNameFromMod(modName, itemName) {
  let n = (modName || "").replace(/\[[^\]]*\]|\([^)]*\)/g, " ");
  n = n.split(/\s+(?:over|in|for|with|w\/)\s+|\s+[|:]\s+|\s+-\s+/i)[0];
  n = n.replace(/\b(mod|mk8d?x?|deluxe|port|edit|updated|improved|version|v\d[\d.]*)\b/gi, " ").replace(/\s+/g, " ").trim();
  if (n.length < 2 || n.length > 30 || n.toLowerCase() === itemName.toLowerCase()) return null;
  return n;
}

// ---- Menu look: what the menus show for a character/course, and adding an
// icon or name a mod doesn't ship (ui_setup's "Your changes"). ----
// Kept deliberately small: a one-line verdict, the three icons, the name, and a
// "Customize" area for everything optional. When the app needs the user's pick
// (a mod ships several versions of its icons) that is the ONLY thing shown.
// There is deliberately no answer cache: what the card shows depends on which mods
// are ticked and downloaded, and a stale answer is exactly the bug that would cause.
// `reload` re-reads the card that is currently open (set by buildMenuLookCard).
const menuLookState = { cache: new Map(), reload: null, pending: null, timer: null };

function invalidateMenuLook() {
  menuLookState.cache.clear();
  uiSetup.data = null; // Settings' "UI icons & text" card must re-read
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

function buildMenuLookCard(name, category) {
  const card = cgEl("div", "modal-card");
  const head = cgEl("div", "modal-card-header");
  head.appendChild(cgEl("span", "modal-card-title", "Menu look"));
  const chip = cgEl("span", "ml-chip");
  chip.hidden = true;
  head.appendChild(chip);
  card.appendChild(head);
  const body = cgEl("div", "uis-pad");
  card.appendChild(body);
  body.appendChild(loadingNote("Reading the mod's menu files..."));
  const kind = category === "courses" ? "courses" : "characters";

  let loadToken = 0;
  async function load(force) {
    const mine = ++loadToken;
    await new Promise(r => setTimeout(r, 0));  // let the popup attach this card first
    const look = await pywebview.api.get_menu_look(name, kind);
    if (!look.error && kind === "characters") {
      try { look.loose = await pywebview.api.get_loose_icon_sets(name); } catch (e) { look.loose = []; }
    }
    if (!body.isConnected || mine !== loadToken) return;   // (closed, or a newer answer is on its way)
    draw(look);
  }

  // Ticking/unticking a mod or finishing a download changes the answer: `pending` shows the wait at once
  // (the card is shown even if it was hidden - draw() hides it again when there turns out to be nothing to say),
  // `reload` re-reads.
  menuLookState.pending = () => {
    if (!body.isConnected) return;
    loadToken++;                                  // whatever was being read is out of date now
    card.hidden = false;
    setChip("");
    body.replaceChildren(loadingNote("Reading the mod's menu files..."));
  };
  menuLookState.reload = () => { if (body.isConnected) load(true); };

  function changed() {
    invalidateMenuLook();
    load(true);
  }

  function setChip(text, cls) {
    chip.hidden = !text;
    chip.textContent = text || "";
    chip.className = "ml-chip " + (cls || "");
  }

  // "Looks right" confirms the icons above; it is what turns the tile's amber dot into a tick. (Currently
  // unreachable: get_menu_look() only fills in "review" for characters, never courses - kept correct
  // rather than deleted, in case courses ever get their own review model.)
  function reviewRow(review) {
    const row = cgEl("div", "ml-review");
    if (review.icons_done) {
      row.appendChild(cgEl("span", "ml-checked", "\u2713 Checked"));
      row.appendChild(button("Undo", "small", async () => { await pywebview.api.unmark_icons_reviewed(name); changed(); renderCharacterGrid(); }));
    } else {
      row.appendChild(button("Looks right", "primary small", async () => { await pywebview.api.mark_icons_reviewed(name); changed(); renderCharacterGrid(); }));
      row.appendChild(cgEl("span", "cg-note", "Confirms the icons above."));
    }
    return row;
  }

  // Everything optional lives in here.
  function customizeArea(look, canIcons, mine, others) {
    const det = document.createElement("details");
    det.className = "ml-custom";
    det.appendChild(cgEl("summary", null, "Customize..."));
    const inner = cgEl("div", "ml-custom-body");
    det.appendChild(inner);
    if (canIcons) {
      const row = cgEl("div", "cg-actions");
      row.appendChild(button("Use my own picture", "small", async () => {
        const saved = await pywebview.api.gb_get_saved_mods(name);
        openIconGenModal(name, (saved || []).flatMap(m => m.screenshots || []), "character", changed);
      }));
      if (mine) row.appendChild(button("Back to normal icons", "small", async () => { await pywebview.api.clear_character_icons(name); changed(); }));
      inner.appendChild(row);
      const pool = look.loose || [];
      if (pool.length) {
        const d2 = document.createElement("details");
        d2.appendChild(cgEl("summary", null, "Pictures included in your mods (" + pool.reduce((n, m) => n + m.sets.length, 0) + ")"));
        for (const m of pool) {
          d2.appendChild(cgEl("div", "ml-loose-mod", m.here ? m.label : `${m.label} (filed under ${m.filed}, but its pictures are named for ${name})`));
          for (const s of m.sets) d2.appendChild(mlVersionCard(name, m, s, changed, false));
        }
        inner.appendChild(d2);
      }
    }
    const nm = look.name;
    if (nm && nm.available) {
      const row = cgEl("div", "ml-name");
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "New name for " + nm.vanilla;
      input.maxLength = 40;
      row.appendChild(input);
      const err = cgEl("span", "gb-mod-error");
      if (nm.state !== "you") {
        pywebview.api.gb_get_saved_mods(name).then(saved => {
          const seen = new Set();
          for (const mod of (saved || [])) {
            const sug = suggestNameFromMod(mod.name, nm.vanilla || name);
            if (!sug || seen.has(sug.toLowerCase()) || !row.isConnected) continue;
            seen.add(sug.toLowerCase());
            const chip = button(`Use "${sug}"`, "small", () => { input.value = sug; input.focus(); });
            chip.title = `From the mod "${mod.name}"`;
            row.insertBefore(chip, input.nextSibling);
          }
        }).catch(() => {});
      }
      row.appendChild(button("Set name", "small", async () => {
        const r = await pywebview.api.set_item_name(name, kind, input.value);
        if (!r.success) { err.textContent = r.error; return; }
        changed();
      }));
      if (nm.state === "you") row.appendChild(button("Back to normal name", "small", async () => { await pywebview.api.clear_item_name(name, kind); changed(); }));
      row.appendChild(err);
      inner.appendChild(row);
    }
    return det;
  }

  function draw(look) {
    body.replaceChildren();
    card.hidden = false;
    setChip("");
    if (look.error) {
      body.appendChild(cgEl("div", "uis-warn", look.error));
      return;
    }
    const nm = look.name && look.name.available ? look.name : null;
    const icons = look.icons;
    const slots = icons ? icons.slots : [];
    const canIcons = !!icons;

    if (icons && icons.needs_choice) {
      // The one thing the user has to do: pick a version.
      setChip("Needs your pick", "warn");
      body.appendChild(cgEl("div", "ml-ask", "A mod includes several sets of icon pictures (often one per costume). Which set belongs to " + name + "?"));
      for (const m of (look.loose || []).filter(x => x.here)) {
        for (const s of m.sets.filter(x => !x.for)) body.appendChild(mlVersionCard(name, m, s, changed, true));
      }
      body.appendChild(cgEl("div", "cg-note", "Until you pick, the game's normal icons are used."));
      body.appendChild(customizeArea(look, canIcons, false, true));
      return;
    }

    if (icons) {
      const states = new Set(slots.map(s => s.state));
      const mods = [...new Set(slots.filter(s => s.state === "mod" || s.state === "auto" || s.state === "included").flatMap(s => s.who.map(w => w.replace(" (icon pictures)", ""))))];
      let verdict, chipText, chipCls;
      if (states.has("you")) { verdict = "Using your own picture."; chipText = "Yours"; chipCls = "ok"; }
      else if (states.has("auto")) { verdict = "Using the icons from " + mods.join(", ") + " - picked automatically, it only has one set."; chipText = "Automatic"; chipCls = "ok"; }
      else if (states.has("mod")) { verdict = "Using the icons from " + mods.join(", ") + "."; chipText = "From a mod"; chipCls = "ok"; }
      else if (states.has("included")) { verdict = "The icons shown are in " + mods.join(", ") + "'s menu files and will be used as they are. (It's the only mod with menu files here, so the app can't tell which of them it actually changes.)"; chipText = "In a mod's files"; chipCls = "ok"; }
      else { verdict = "Normal game icons - none of your mods changes them."; chipText = ""; chipCls = ""; }
      const multi = slots.find(s => s.variants > 1 && s.changed > 0);
      if (multi) verdict = verdict.replace(/\.$/, "") + (multi.changed === multi.variants ? ` (all ${multi.variants} colours).` : ` (${multi.changed} of ${multi.variants} colours).`);
      setChip(chipText, chipCls);
      const row = cgEl("div", "ml-row");
      for (const s of slots) row.appendChild(mlThumb(s.preview, ML_KINDS.find(k => k[0] === s.kind)[1], s));
      body.appendChild(row);
      body.appendChild(cgEl("div", "ml-verdict", verdict));
      const blockedSlots = slots.filter(s => s.blocked);
      if (blockedSlots.length) {
        const who = [...new Set(blockedSlots.flatMap(s => s.blocked.who))].join(", ");
        const why = [...new Set(blockedSlots.map(s => s.blocked.reason).filter(Boolean))].join("; ");
        body.appendChild(cgEl("div", "uis-warn", `${blockedSlots.length === 1 ? "One icon" : blockedSlots.length + " icons"} from ${who} can't be applied - ${why}. The game's own ${blockedSlots.length === 1 ? "picture is" : "pictures are"} used there.`));
      }
      for (const m of (look.loose || []).filter(x => x.here)) {
        for (const set of m.sets.filter(x => x.for)) {
          body.appendChild(cgEl("div", "cg-note", `${m.label} also includes icon pictures named for ${set.for} - they aren't used here (see Customize... to use them for ${name} anyway).`));
        }
      }
    }
    if (nm) {
      const line = cgEl("div", "ml-namerow");
      line.appendChild(cgEl("span", "ml-name-label", "Name in menus: "));
      line.appendChild(cgEl("strong", null, nm.text));
      if (nm.state === "mod") line.appendChild(cgEl("span", "cg-note", " (from " + nm.who.join(", ") + ")"));
      if (nm.state === "you") line.appendChild(cgEl("span", "cg-note", nm.auto
        ? ` (guessed from ${nm.source || "the mod"} - change it below, or go back to the normal name)` : " (yours)"));
      body.appendChild(line);
    }
    if (icons || nm) {
      const mine = slots.some(s => s.state === "you" || s.state === "auto");
      if (look.review && look.review.icons_applicable) body.appendChild(reviewRow(look.review));
      body.appendChild(customizeArea(look, canIcons, mine, false));
    } else if (look.review && look.review.icons_applicable) {
      body.appendChild(cgEl("div", "ml-verdict", "Nothing here changes how " + name + " looks in the menus."));
      body.appendChild(reviewRow(look.review));
    } else {
      card.hidden = true;
    }
  }

  load(false);
  return card;
}

