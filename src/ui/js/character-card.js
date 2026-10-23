// Name and Icons are the character card's two independent review tasks: a short walkthrough the
// first time each is needed (Name: what to call it; Icons: do its menu pictures look right - or,
// for a model-swap mod with no icon of its own, just a glance) and a read-only summary afterwards
// ("Edit" walks through it again). Confirming one never marks the other done (mod_manager.py's
// _review_state()/confirm_guessed_name()/mark_icons_reviewed()). Both read the same get_menu_look()
// data, loaded once. `onLook(look, mode)` tells the card which is showing: mode is
// {name: "walk"|"summary", icons: "walk"|"summary"}.
function buildCharacterLook(name, onLook) {
  const nameWrap = cgEl("div", "cl-look");
  const iconsWrap = cgEl("div", "cl-look");
  let wrap = null;         // whichever of the two the shared drawing helpers below append into right now
  let colour = null;       // which colour of a colour-variant character is shown (0-based)
  let nameView = null;     // "walk" forces the name editor open (Edit); null: follow the data
  let iconsView = null;    // same, for the icons editor
  let lastLook = null;
  let nameMode = "summary", iconsMode = "summary";

  // the wait: shapes where the name plate / icon table will be (before the first answer, and again
  // from the moment a mod is ticked or unticked until the new answer is drawn)
  function buildNameSkeleton() {
    const sk = cgEl("div", "cl-sk");
    sk.appendChild(loadingNote("Reading the mod's menu files..."));
    sk.appendChild(cgEl("div", "sk cl-sk-prev"));
    sk.appendChild(skeleton("50%", 12));
    return sk;
  }
  function buildIconsSkeleton() {
    const sk = cgEl("div", "cl-sk");
    const tbl = cgEl("div", "cl-sk-table");
    const head = cgEl("div", "cl-sk-row cl-sk-head");
    const hc = (cls, w) => { const c = cgEl("div", cls); c.appendChild(skeleton(w, 9)); return c; };
    head.appendChild(hc("cl-sk-icwrap", 34));
    head.appendChild(hc("cl-sk-name", 40));
    head.appendChild(hc("cl-sk-desc", 70));
    tbl.appendChild(head);
    for (let i = 0; i < 3; i++) {
      const r = cgEl("div", "cl-sk-row");
      const icw = cgEl("div", "cl-sk-icwrap");
      icw.appendChild(cgEl("div", "sk cl-sk-ic"));
      const nm = cgEl("div", "cl-sk-name");
      nm.appendChild(skeleton(92, 13));
      nm.appendChild(skeleton(42, 14, "6px"));
      const ds = cgEl("div", "cl-sk-desc");
      ds.appendChild(skeleton("90%", 12));
      ds.appendChild(skeleton("55%", 12));
      r.append(icw, nm, ds, skeleton(26, 26, "50%"));
      tbl.appendChild(r);
    }
    sk.appendChild(tbl);
    return sk;
  }
  nameWrap.appendChild(buildNameSkeleton());
  iconsWrap.appendChild(buildIconsSkeleton());

  let loadToken = 0;
  async function load() {
    const mine = ++loadToken;
    await new Promise(r => setTimeout(r, 0));
    const look = await pywebview.api.get_menu_look(name, "characters");
    if (!look.error) {
      try { look.loose = await pywebview.api.get_loose_icon_sets(name); } catch (e) { look.loose = []; }
    }
    if (!nameWrap.isConnected && !iconsWrap.isConnected) return;   // (closed)
    if (mine !== loadToken) return;                                 // (a newer answer is on its way)
    draw(look);
  }
  // ticking a mod or finishing a download changes the answer: `pending` shows the wait at once, `reload` reads it
  menuLookState.pending = () => { if (nameWrap.isConnected || iconsWrap.isConnected) pending(); };
  menuLookState.reload = () => { if (nameWrap.isConnected || iconsWrap.isConnected) load(); };
  function pending() {
    loadToken++;                                  // whatever was being read is out of date now
    nameWrap.replaceChildren(buildNameSkeleton());
    iconsWrap.replaceChildren(buildIconsSkeleton());
    nameMode = iconsMode = "summary";
    if (onLook) onLook(null, { name: nameMode, icons: iconsMode });   // (the card's status lines say they are getting ready)
  }

  function changed() {
    invalidateMenuLook();
    load();
    renderCharacterGrid();
  }

  async function openPictureWindow(opts) {
    if (opts instanceof Event) opts = null;   // (used as a click handler too)
    const saved = await pywebview.api.gb_get_saved_mods(name);
    openIconGenModal(name, (saved || []).flatMap(m => m.screenshots || []), "character", changed, opts || null);
  }

  // what both tasks share: the colours, which pictures exist, which are missing
  function analyse(look) {
    const A = { look, nm: look.name && look.name.available ? look.name : null, icons: look.icons, slots: look.icons ? look.icons.slots : [] };
    A.bySlot = {};
    for (const sl of A.slots) A.bySlot[sl.kind] = sl;
    A.nCol = A.bySlot.Chara && A.bySlot.Chara.per ? A.bySlot.Chara.per.length : 1;
    A.multi = A.nCol > 1;
    A.entryOf = (kind, i) => {
      const sl = A.bySlot[kind];
      if (!sl) return null;
      return A.multi ? sl.per[i] : { state: sl.state, preview: sl.preview, filled: !!sl.filled, blocked: !!sl.blocked, who: sl.who };
    };
    A.isModded = e => !!e && e.state !== "vanilla";
    A.colourHasPictures = i => ML_KINDS.some(([k]) => A.isModded(A.entryOf(k, i)));
    if (colour === null || colour >= A.nCol) {
      const first = [...Array(A.nCol).keys()].find(A.colourHasPictures);
      colour = first === undefined ? 0 : first;
    }
    A.gaps = [];   // pictures the mod doesn't have while it does have the Select screen one (in any colour)
    for (let i = 0; i < A.nCol; i++) {
      if (!A.isModded(A.entryOf("Chara", i))) continue;
      for (const k of ["MapChara", "edChara"]) {
        const e = A.entryOf(k, i);
        if (e && e.state === "vanilla" && !e.blocked) A.gaps.push({ i, kind: k });
      }
    }
    A.kindName = k => ML_KINDS.find(x => x[0] === k)[1];
    A.mods = [...new Set(A.slots.filter(sl => sl.state === "mod" || sl.state === "auto" || sl.state === "included").flatMap(sl => sl.who.map(w => w.replace(" (icon pictures)", ""))))];
    A.mine = A.slots.some(sl => (sl.state === "you" && !sl.filled) || sl.state === "auto");
    A.anyModded = A.slots.some(sl => sl.state !== "vanilla");
    return A;
  }

  function draw(look) {
    lastLook = look;
    if (look.error) {
      nameWrap.replaceChildren(cgEl("div", "uis-warn", look.error));
      iconsWrap.replaceChildren();
      nameMode = iconsMode = "summary";
      if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
      return;
    }
    const A = analyse(look);
    if (!look.review) {   // nothing ticked: the card hides both rows
      nameWrap.replaceChildren();
      iconsWrap.replaceChildren();
      nameMode = iconsMode = "summary";
      if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
      return;
    }
    drawNameTask(A);
    drawIconsTask(A);
    if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
  }

  function drawNameTask(A) {
    wrap = nameWrap;
    wrap.replaceChildren();
    const r = A.look.review;
    if (!A.nm || !r.name_applicable) {
      nameMode = "summary";
      wrap.appendChild(cgEl("div", "cg-note", `Nothing to check: nothing changes what ${name} is called.`));
      return;
    }
    const walk = nameView === "walk" || (nameView === null && !r.name_done);
    nameMode = walk ? "walk" : "summary";
    if (walk) drawNameStep(A); else drawNameSummary(A);
  }

  function drawIconsTask(A) {
    wrap = iconsWrap;
    wrap.replaceChildren();
    const r = A.look.review;
    if (!r.icons_applicable) {
      iconsMode = "summary";
      wrap.appendChild(cgEl("div", "cg-note", "Nothing to check: the selected mods don't change how " + name + " looks in the menus."));
      return;
    }
    const walk = iconsView === "walk" || (iconsView === null && !r.icons_done);
    iconsMode = walk ? "walk" : "summary";
    if (walk) drawIconsStep(A); else drawIconsSummary(A);
  }

  // ------------------------------------------------------------------ small pieces (shared by the walkthrough and summary)
  function colourStrip(A, redraw, note) {
    if (!A.multi) return;
    const box = cgEl("div", "cl-colours");
    const have = [...Array(A.nCol).keys()].filter(A.colourHasPictures).length;
    const hint = cgEl("div", "cl-hint", have
      ? `${name} has ${A.nCol} colours in the game. ${have === A.nCol ? "Your mods give every one of them its own pictures" : "Your mods give " + have + " of them their own pictures"}${note}`
      : `${name} has ${A.nCol} colours in the game. None of them has a picture from your mods.`);
    hint.style.margin = "0";
    box.appendChild(hint);
    const strip = cgEl("div", "cl-colour-strip");
    for (let i = 0; i < A.nCol; i++) {
      const e = A.entryOf("Chara", i);
      const c = cgEl("button", "cl-colour");
      c.type = "button";
      const gap = A.gaps.some(g => g.i === i);
      c.title = `Colour ${i + 1}` + (A.colourHasPictures(i) ? "" : " - the game's own pictures") + (gap ? " - a picture is missing" : "");
      c.setAttribute("aria-label", c.title);
      if (e && e.preview) { const im = document.createElement("img"); im.src = e.preview; im.alt = ""; c.appendChild(im); }
      else c.appendChild(cgEl("span", "cl-colour-n", String(i + 1)));
      c.classList.toggle("is-sel", i === colour);
      c.classList.toggle("is-plain", !A.colourHasPictures(i));
      c.classList.toggle("is-gap", gap);
      c.addEventListener("click", () => { colour = i; redraw(); });
      strip.appendChild(c);
    }
    box.appendChild(strip);
    wrap.appendChild(box);
  }

  // the icon and the name plate, as the game's select screen shows them (`input`: the plate is the name box)
  function previewBox(A, input) {
    const shown = ["Chara", "edChara", "MapChara"].map(k => A.entryOf(k, colour)).find(e => A.isModded(e) && e.preview) || A.entryOf("Chara", colour);
    const box = cgEl("div", "cl-preview");
    if (shown && shown.preview) { const img = document.createElement("img"); img.src = shown.preview; img.alt = ""; box.appendChild(img); }
    else box.appendChild(cgEl("div", "cl-noicon", "no icon"));
    const plate = cgEl("div", "cl-plate");
    if (input) {
      plate.classList.add("is-edit");
      const base = cgEl("span", "np-base", "");
      const sync = () => {
        const t = input.value.trim();
        base.textContent = t && t !== name ? "(" + name + ")" : "";
        input.style.width = (Math.max(input.value.length || A.nm.vanilla.length, 4) + 1) + "ch";
      };
      input.addEventListener("input", sync);
      plate.addEventListener("click", () => input.focus());
      plate.append(input, base);
      sync();
    } else {
      const t = A.nm ? A.nm.text : name;
      plate.append(t);
      if (t !== name) plate.appendChild(cgEl("span", "np-base", "(" + name + ")"));
    }
    box.appendChild(plate);
    wrap.appendChild(box);
  }

  const sourceOf = (e) => e.filled ? "Made from the Select screen"
    : e.state === "you" ? "Your picture"
    : (e.state === "mod" || e.state === "auto" || e.state === "included") ? ((e.who || []).map(w => w.replace(" (icon pictures)", "")).join(", ") || "The mod")
    : "Game default";

  // ------------------------------------------------------------------ the Name task
  function drawNameStep(A) {
    const nm = A.nm;
    wrap.appendChild(cgEl("div", "cl-q", `What should ${name} be called in the game?`));
    wrap.appendChild(cgEl("div", "cl-sub",
      nm.state === "you" ? (nm.auto ? `We guessed this from ${nm.source || "the mod"}. Change it if you like.` : "This is the name you chose. Change it if you like.")
      : nm.state === "mod" ? `The mod (${nm.who.join(", ")}) gives it this name. Change it if you like.`
      : "The mod doesn't say. Give it a name, or keep the game's own."));
    const input = document.createElement("input");
    input.type = "text";
    input.id = "cl-name-input";
    input.className = "cl-plate-input";
    input.maxLength = 40;
    input.spellcheck = false;
    input.placeholder = nm.vanilla;
    input.setAttribute("aria-label", "Name for " + name + " (leave empty to keep the game's name)");
    const baseline = nm.state === "vanilla" ? "" : nm.text;
    const draft = nameDrafts[name] && nameDrafts[name].base === baseline ? nameDrafts[name].value : null;
    input.value = draft !== null ? draft : baseline;
    if (draft !== null && draft !== baseline) wrap.appendChild(cgEl("div", "cl-sub", "You had started typing this name - it wasn't saved yet."));
    previewBox(A, input);
    const err = cgEl("span", "gb-mod-error");
    wrap.appendChild(err);

    const row = cgEl("div", "ml-review");
    const go = button(input.value.trim() ? "Use this name" : "Keep the game's name", "primary small", async () => {
      go.disabled = true;
      const typedName = input.value.trim();
      const current = nm.state === "vanilla" ? "" : nm.text;
      let r = { success: true };
      if (typedName !== current) {
        r = typedName === "" ? (nm.state === "you" ? await pywebview.api.clear_item_name(name, "characters", false) : { success: true })
                             : await pywebview.api.set_item_name(name, "characters", typedName, false);
      }
      if (!r.success) { go.disabled = false; err.textContent = r.error; return; }
      delete nameDrafts[name];
      await pywebview.api.confirm_guessed_name(name);
      nameView = null;
      changed();
    });
    input.addEventListener("input", () => {
      nameDrafts[name] = { value: input.value, base: baseline };
      go.textContent = input.value.trim() ? "Use this name" : "Keep the game's name";
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } });
    row.appendChild(go);
    row.appendChild(cgEl("span", "cg-note", "Or type a different one above."));
    wrap.appendChild(row);
    setTimeout(() => { if (input.isConnected) { input.focus(); const n = input.value.length; input.setSelectionRange(n, n); } }, 30);
  }

  function drawNameSummary(A) {
    const nm = A.nm;
    const top = cgEl("div", "cl-sum-name");
    const plate = cgEl("div", "cl-plate");
    const t = nm ? nm.text : name;
    plate.append(t);
    if (t !== name) plate.appendChild(cgEl("span", "np-base", "(" + name + ")"));
    top.appendChild(plate);
    if (nm) {
      top.appendChild(cgEl("span", "cl-hint", nm.state === "you" ? (nm.auto ? "Name guessed from " + (nm.source || "the mod") : "Your name")
        : nm.state === "mod" ? "Name from " + nm.who.join(", ") : "The game's own name"));
    }
    wrap.appendChild(top);
  }

  // ------------------------------------------------------------------ the Icons task
  function drawIconsStep(A) {
    const look = A.look;

    // A real decision comes first: a mod ships several sets of icon pictures.
    if (A.icons && A.icons.needs_choice) {
      wrap.appendChild(cgEl("div", "cl-q", `Which pictures should ${name} use?`));
      wrap.appendChild(cgEl("div", "cl-sub", "A mod includes several sets of icon pictures (often one per costume). Until you pick, the game's normal icons are used."));
      for (const m of (look.loose || []).filter(x => x.here)) {
        for (const set of m.sets.filter(x => !x.for)) wrap.appendChild(mlVersionCard(name, m, set, changed, true));
      }
      const alt = cgEl("div", "cg-actions");
      alt.appendChild(button("Use my own picture", "small", openPictureWindow));
      wrap.appendChild(alt);
      return;
    }
    if (!A.icons) {   // (a character the app has no icons for)
      wrap.appendChild(cgEl("div", "cl-sub", "There are no icons to check for this character."));
      finishIconsRow();
      return;
    }
    const slots = A.slots;
    const own = ML_KINDS.filter(([k]) => { const sl = A.bySlot[k]; return sl && sl.state === "you" && !sl.filled; }).map(k => k[1]);
    const made = ML_KINDS.filter(([k]) => { const sl = A.bySlot[k]; return sl && sl.filled; }).map(k => k[1]);
    const list = (a) => a.length > 1 ? a.slice(0, -1).join(", ") + " and " + a[a.length - 1] : a[0];
    let prov;
    if (A.mods.length) {
      prov = "Icons from " + A.mods.join(", ")
        + (own.length ? `; the ${list(own)} ${own.length === 1 ? "is" : "are"} your own` : "")
        + (made.length ? `; the ${list(made)} ${made.length === 1 ? "is" : "are"} made from the Select screen` : "") + ".";
    } else if (own.length || made.length) {
      prov = own.length ? "These are your own pictures." : "Made from the Select screen picture.";
    } else prov = "None of your mods brings icons for this character.";
    wrap.appendChild(cgEl("div", "cl-q", "Do these icons look right?"));
    wrap.appendChild(cgEl("div", "cl-sub", prov + " Click a picture to change it."));

    colourStrip(A, () => draw(look), " - pick a colour to check it.");
    iconTable(A, false);
    gapNotes(A);
    if (!A.anyModded) {
      // No mod supplies an icon: encourage a picture of the user's own.
      const nudge = cgEl("div", "cl-nudge");
      nudge.appendChild(cgEl("b", null, "No icon comes with this mod"));
      nudge.appendChild(cgEl("span", null, "Add a picture so it stands out in the menus. Pick one of the mod's screenshots or a file of your own - it's resized for you."));
      nudge.appendChild(button("Add a picture", "primary small", openPictureWindow));
      wrap.appendChild(nudge);
    }
    finishIconsRow();
  }

  function finishIconsRow() {
    const row = cgEl("div", "ml-review");
    row.appendChild(button("Looks right", "primary small", async () => {
      await pywebview.api.mark_icons_reviewed(name);
      iconsView = null;
      changed();
    }));
    wrap.appendChild(row);
  }

  // notes under the table: a gap in another colour, pictures that can't be applied, pictures named for someone else
  function gapNotes(A) {
    const { gaps, multi } = A;
    if (gaps.length > 1 || (multi && gaps.some(x => x.i !== colour))) {   // (one gap in the colour shown is already said in its row)
      const g = cgEl("div", "cl-gap");
      const what = [...new Set(gaps.map(x => A.kindName(x.kind)))].join(" and ");
      const text = multi
        ? `${gaps.length === 1 ? "One picture is" : gaps.length + " pictures are"} missing from the mod: ${gaps.slice(0, 4).map(x => `${A.kindName(x.kind)} for colour ${x.i + 1}`).join(", ")}${gaps.length > 4 ? ", ..." : ""}. Until you fill ${gaps.length === 1 ? "it" : "them"} in, the game's own ${gaps.length === 1 ? "picture shows" : "pictures show"} there.`
        : `The mod has no ${what} picture, so the game's own would show next to its Select screen one. You can reuse the Select screen picture, scaled down.`;
      g.appendChild(cgEl("span", "cl-gap-text", text));
      if (gaps.length > 1) {
        g.appendChild(button("Fill them all", "small", async () => { await pywebview.api.fill_missing_icons(name, null, null); changed(); }));
      }
      wrap.appendChild(g);
    }
    const blocked = A.slots.filter(sl => sl.blocked);
    if (blocked.length) {
      const who = [...new Set(blocked.flatMap(sl => sl.blocked.who))].join(", ");
      const why = [...new Set(blocked.map(sl => sl.blocked.reason).filter(Boolean))].join("; ");
      wrap.appendChild(cgEl("div", "uis-warn", `${blocked.length === 1 ? "One icon" : blocked.length + " icons"} from ${who} can't be applied - ${why}. The game's own ${blocked.length === 1 ? "picture is" : "pictures are"} used there.`));
    }
    for (const m of (A.look.loose || []).filter(x => x.here)) {
      for (const set of m.sets.filter(x => x.for)) {
        wrap.appendChild(cgEl("div", "cg-note", `${m.label} also includes icon pictures named for ${set.for} - they aren't used here (choose "Change picture" on an icon to use one for ${name} anyway).`));
      }
    }
  }

  // The three icons, as a table. Walkthrough (`summary` false): the picture is the button (hover: a pencil; click:
  // choose a picture for that icon alone), a row's "..." holds what else can be done to it and the header's "..."
  // what applies to all three. Summary: just the pictures and where each is from.
  function iconTable(A, summary) {
    const { multi } = A;
    const colArg = multi ? colour : null;
    const scope = multi ? ` (colour ${colour + 1})` : "";
    const table = document.createElement("table");
    table.className = "cl-table" + (summary ? " is-summary" : "");
    const headRow = document.createElement("tr");
    for (const h of ["Icon", "Name", summary ? "Source" : "Description"]) headRow.appendChild(cgEl("th", null, h));
    if (!summary) {
      const thMenu = cgEl("th", "cl-th-menu");
      thMenu.appendChild(clKebab("Options for all three icons", () => {
        const items = [{ label: "Use one picture for all three...", run: () => openPictureWindow() }];
        if (A.mine) items.push({ label: "Use game defaults", run: async () => { await pywebview.api.clear_character_icons(name); changed(); } });
        return items;
      }));
      headRow.appendChild(thMenu);
    }
    const thead = document.createElement("thead");
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const [kind, caption, hint] of ML_KINDS) {
      const e = A.entryOf(kind, colour);
      if (!e) continue;
      const gap = A.gaps.some(g => g.i === colour && g.kind === kind);
      const slot = A.bySlot[kind];
      const change = () => openPictureWindow({ kinds: [kind], colour: colArg, label: caption + scope });
      const tr = document.createElement("tr");

      const tdIcon = cgEl("td", "cl-t-icon");
      const ic = cgEl(summary ? "div" : "button", "cl-ic" + (summary ? " is-static" : ""));
      if (!summary) {
        ic.type = "button";
        ic.title = `Change the ${caption} picture${scope}`;
        ic.setAttribute("aria-label", ic.title);
      }
      if (e.preview) { const im = document.createElement("img"); im.src = e.preview; im.alt = ""; ic.appendChild(im); }
      else { ic.classList.add("is-blank"); ic.classList.toggle("is-gap", gap && !summary); ic.appendChild(cgEl("span", "cl-ic-blank", gap && !summary ? "+" : "game default")); }
      if (!summary) { ic.appendChild(cgEl("span", "cl-ic-ov", "✎")); ic.addEventListener("click", change); }
      tdIcon.appendChild(ic);
      tr.appendChild(tdIcon);

      const tdName = cgEl("td", "cl-t-name");
      tdName.appendChild(cgEl("div", null, caption));
      if (!summary) {
        if (e.filled) { const t = cgEl("span", "cl-src", "Made from Select"); t.title = "Made from the Select screen picture, scaled down"; tdName.appendChild(t); }
        else if (e.state === "you") tdName.appendChild(cgEl("span", "cl-src you", "Yours"));
        else if (e.state === "mod" || e.state === "auto" || e.state === "included") {
          const t = cgEl("span", "cl-src", "Mod");
          t.title = e.state === "auto" ? "Picked automatically from the mod's pictures" : "From the mod";
          tdName.appendChild(t);
        }
      }
      tr.appendChild(tdName);

      const tdDesc = cgEl("td", "cl-t-desc");
      if (summary) {
        tdDesc.appendChild(cgEl("div", null, sourceOf(e)));
        if (e.blocked) tdDesc.appendChild(cgEl("div", "cl-tile-tag", "Can't be applied - the game default is used"));
      } else {
        tdDesc.appendChild(cgEl("div", null, hint));
        if (gap) {
          const line = cgEl("div", "cl-tile-tag", "Not in the mod. ");
          const use = cgEl("button", "cl-link", "Use the Select screen one");
          use.type = "button";
          use.title = "Use the Select screen picture for this one, scaled down";
          use.addEventListener("click", async () => { await pywebview.api.fill_missing_icons(name, colArg, [kind]); changed(); });
          line.appendChild(use);
          tdDesc.appendChild(line);
        } else if (e.blocked) {
          const t = cgEl("div", "cl-tile-tag", "Can't apply");
          t.title = (slot && slot.blocked && slot.blocked.reason) || "";
          tdDesc.appendChild(t);
        } else if (slot && slot.resized && A.isModded(e)) {
          const t = cgEl("div", "cl-tile-tag info", "Resized to fit");
          t.title = "The mod's picture is a different size than the game's own, so the app scales it to fit.";
          tdDesc.appendChild(t);
        }
      }
      tr.appendChild(tdDesc);

      if (!summary) {
        // what else can be done here (nothing else: no menu - the picture itself changes it)
        const extra = [];
        if (e.filled) extra.push({ label: "Undo", title: "Take back the picture made from the Select screen", run: async () => { await pywebview.api.unfill_icons(name, [kind], colArg); changed(); } });
        else if (e.state === "you") extra.push({ label: "Undo my picture", title: "Go back to the mod's picture (or the game default, when the mod has none)", run: async () => { await pywebview.api.clear_character_icons(name, [kind], colArg); changed(); } });
        else if (e.state === "auto") extra.push({ label: "Use game default", title: "Stop using the mod's picture here", run: async () => { await pywebview.api.clear_character_icons(name, [kind], colArg); changed(); } });
        const tdMenu = cgEl("td", "cl-t-menu");
        if (extra.length) tdMenu.appendChild(clKebab(`More for the ${caption} icon${scope}`, () => [{ label: "Change picture", run: change }, "-", ...extra]));
        tr.appendChild(tdMenu);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    const tableBox = cgEl("div", "cl-table-box");   // (its width decides between the columns and the stacked rows)
    tableBox.appendChild(table);
    wrap.appendChild(tableBox);
  }

  function drawIconsSummary(A) {
    if (!A.icons) return;   // nothing to preview (only a model-swap mod) - nothing extra to show once confirmed
    colourStrip(A, () => draw(lastLook), ".");
    iconTable(A, true);
    gapNotes(A);
  }

  load();
  return {
    nameRoot: nameWrap, iconsRoot: iconsWrap,
    editName: () => { if (!lastLook || !lastLook.review) return; nameView = "walk"; draw(lastLook); },
    editIcons: () => { if (!lastLook || !lastLook.review) return; iconsView = "walk"; draw(lastLook); },
  };
}

// One row of a guided card (Name, Icons): a status dot, the title with a one-line summary, an action button, and the
// body the walkthrough draws into. Shared by the character and the course card.
function makeCardStep(title) {
  const root = cgEl("div", "cc-step");
  const row = cgEl("div", "cc-step-row");
  const dot = cgEl("span", "cc-dot pending");
  const text = cgEl("div", "cc-step-text");
  const t = cgEl("b", null, title);
  const sum = cgEl("span", null, "");
  text.appendChild(t);
  text.appendChild(sum);
  const act = button("Change", "small", () => {});
  row.appendChild(dot);
  row.appendChild(text);
  row.appendChild(act);
  const content = cgEl("div", "cc-step-body");
  root.appendChild(row);
  root.appendChild(content);
  return { root, dot, sum, act, content };
}
function setCardStepDot(step, kind) {
  step.dot.className = "cc-dot " + kind;
  step.dot.textContent = kind === "done" ? "\u2713" : "";
  step.root.classList.toggle("is-pending", kind === "pending");
}

function assembleCharacterCard(ctx) {
  const { name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard, refreshCount, refreshToggle, refreshConflicts } = ctx;
  const hasMods = entry.units.length > 0;
  const modsCard = mainCol.querySelector(".modal-card");
  let look = null, nameMode = "summary", iconsMode = "summary", manage = false;
  let wasFinished = null;   // whether Name+Icons were both finished the last time an answer was in (null: none yet)

  // Villager / Inkling: the switch to the other one comes first
  const variantItem = variantItemOf(name);
  if (variantItem) {
    variantLast[variantItem.group] = name;
    body.appendChild(buildVariantSwitch(variantItem, name));
  } else {
    variantSwitchRefresh = null;
  }
  // what this character is now: its (modded) name and where it stands - always in view
  if (reviewQueue.active) body.appendChild(buildReviewBar());
  const chip = cgEl("span", "cc-chip");
  const headName = cgEl("div", "cc-headname");
  const headSub = cgEl("div", "cc-headsub");
  const headText = cgEl("div", "cc-headtext");
  headText.appendChild(headName);
  headText.appendChild(headSub);
  const head = cgEl("div", "cc-head");
  head.appendChild(headText);
  head.appendChild(chip);
  body.appendChild(head);
  body.appendChild(conflictBox);   // clash warnings are never folded away

  // The mods: the ones in use stay on screen as rows - they are never folded into a sentence. The rest sit
  // behind "Manage", and adding another is a quiet row underneath.
  const modPanel = cgEl("div", "cc-panel");
  let manageBtn = null, modHint = null;
  if (hasMods && modsCard) {
    modsCard.classList.add("cc-mods");
    const hdr = modsCard.querySelector(".modal-card-header");
    manageBtn = button("Manage", "ghost small cc-manage", () => { manage = !manage; refresh(); });
    hdr.appendChild(manageBtn);
    modHint = cgEl("div", "cc-hint");
    hdr.after(modHint);
    modPanel.appendChild(mainCol);
  }
  modPanel.appendChild(secondaryCard);
  body.appendChild(modPanel);

  const makeStep = makeCardStep;
  const nameStep = makeStep("Name");
  nameStep.root.classList.add("cc-step-inline");   // ("Edit" sits right beside the title and status, not at the far edge)
  const iconsStep = makeStep("Icons");
  iconsStep.root.classList.add("cc-step-inline");
  const lookTasks = buildCharacterLook(name, (l, mode) => { look = l; nameMode = mode.name; iconsMode = mode.icons; refresh(); });
  nameStep.content.appendChild(lookTasks.nameRoot);
  iconsStep.content.appendChild(lookTasks.iconsRoot);
  body.appendChild(nameStep.root);
  body.appendChild(iconsStep.root);
  const voiceRow = attachVoiceRow(body, name);

  const setDot = setCardStepDot;

  function refresh() {
    const ticked = entry.units.filter(k => state.checked[k]);
    // (the Custom voice mod is made by the Voice row itself, so it can't be what unlocks that row)
    voiceRow.setEnabled(ticked.some(k => !k.endsWith("/Custom voice")));
    const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

    // --- the mods panel
    if (modsCard && manageBtn) {
      const some = ticked.length > 0;
      modsCard.classList.toggle("show-all", manage || !some);
      modHint.hidden = some && !manage;
      modHint.textContent = !some
        ? `None of these is in use yet. Select the one${entry.units.length > 1 ? "s" : ""} you want for ${name}.`
        : "Select a mod to use it, deselect it to stop. Mods that replace the same character, and variants of the same files (colours or options), are pick-one: selecting one deselects the other.";
      manageBtn.hidden = !(some && (entry.units.length > ticked.length || manage));
      manageBtn.textContent = manage ? "Done" : "Manage";
    }

    // --- Name and Icons: each its own walkthrough the first time, a summary (with Edit) afterwards.
    // Identical shape, just fed different fields of the same review object - see mod_manager.py's
    // _review_state(). ("pending" only happens with nothing ticked, so it never reaches the chip/sub
    // logic below - that's already behind its own !ticked.length check.)
    function taskState(applicableKey, doneKey) {
      if (!ticked.length) return { state: "pending", sum: "Comes after you pick a mod" };
      if (!look) return { state: "current", sum: "Getting it ready..." };   // (also from a tick until the new answer)
      if (look.error) return { state: "current", sum: look.error };
      const review = look.review;
      if (review && !review[applicableKey]) return { state: "done", sum: "Nothing to check" };
      if (review && review[doneKey]) return { state: "done", sum: "Completed" };
      return { state: "current", sum: "" };
    }
    const ns = taskState("name_applicable", "name_done");
    setDot(nameStep, ns.state);
    nameStep.sum.textContent = ns.sum;
    nameStep.content.hidden = !(ticked.length > 0);
    nameStep.act.hidden = !(ticked.length > 0 && ns.state === "done" && nameMode === "summary");
    nameStep.act.textContent = "Edit";
    nameStep.act.onclick = () => lookTasks.editName();

    const is_ = taskState("icons_applicable", "icons_done");
    setDot(iconsStep, is_.state);
    iconsStep.sum.textContent = is_.sum;
    iconsStep.content.hidden = !(ticked.length > 0);
    iconsStep.act.hidden = !(ticked.length > 0 && is_.state === "done" && iconsMode === "summary");
    iconsStep.act.textContent = "Edit";
    iconsStep.act.onclick = () => lookTasks.editIcons();

    // it just became finished (both tasks done, or neither applicable): the character's select sound,
    // and - if a guided review queue is walking through unfinished characters - its advance. Opening a
    // card that is already finished doesn't count - only a change from not finished to finished.
    if (look && !look.error) {
      const finished = ns.state === "done" && is_.state === "done";
      if (wasFinished === false && finished) { playSelectVoice(name); onItemFinished("character", name); }
      wasFinished = finished;
    }

    // --- the headline: the name it will have, and a sentence saying where things stand
    const nm = look && look.name && look.name.available ? look.name : null;
    headName.replaceChildren();
    headName.hidden = !(ticked.length && nm && nm.text !== name);
    if (!headName.hidden) {
      headName.append(nm.text);
      headName.appendChild(cgEl("span", "np-base", "(" + name + ")"));
    }
    const bothDone = ns.state === "done" && is_.state === "done";
    // say exactly which of Name/Icons still needs a look, rather than the vague "appearance" -
    // the two are independent tasks now (see "Name and Icons" in docs/menu-look.md), so naming them here
    // says at a glance which row below to open.
    const needing = [ns.state === "current" && "name", is_.state === "current" && "icons"].filter(Boolean);
    let sub;
    if (!hasMods) sub = "No mod yet - find one below.";
    else if (!ticked.length) sub = `${plural(entry.units.length, "mod")} downloaded, none in use yet.`;
    else {
      sub = `${plural(ticked.length, "mod")} in use`;
      if (!look) sub += " \u00b7 reading its name and icons...";
      else if (needing.length) sub += ` \u00b7 ${needing.join(" and ")} need${needing.length === 1 && needing[0] === "name" ? "s" : ""} a look`;
      else sub += " \u00b7 name and icons confirmed";
    }
    headSub.textContent = sub;

    // --- the chip
    let chipText, chipCls = "";
    if (!hasMods) chipText = "No mod yet";
    else if (!ticked.length) { chipText = "Choose a mod"; chipCls = "warn"; }
    else if (!look) { chipText = "Reading..."; chipCls = ""; }
    else if (!bothDone) { chipText = "Needs a look"; chipCls = "warn"; }
    else { chipText = "Done"; chipCls = "ok"; }
    chip.textContent = chipText;
    chip.className = "cc-chip " + chipCls;
  }

  // Ticking inside the list: variants (colours / options of the same files) are pick-one. The list stays
  // open while the user works in it - "Done" folds it back to the mods in use.
  mainCol.addEventListener("change", (e) => {
    const cb = e.target;
    if (!(cb instanceof HTMLInputElement) || cb.type !== "checkbox") return;
    const me = modCheckboxes.find(x => x.cb === cb);
    if (me) {
      manage = true;
      const u = unitSlots[me.key];
      if (cb.checked && u) {
        // pick-one: the other colours / options of this mod, and the other mods that replace the same character
        const mg = modelGroup(me.key);
        let cleared = 0;
        for (const o of modCheckboxes) {
          const ou = unitSlots[o.key];
          if (o === me || !ou || !o.cb.checked) continue;
          if ((u.twins > 1 && ou.twin_group === u.twin_group) || (mg && modelGroup(o.key) === mg)) {
            o.cb.checked = false;
            state.checked[o.key] = false;
            o.row.classList.remove("checked");
            cleared++;
          }
        }
        if (cleared) {
          saveChecked();
          refreshBehindModal({ ifChanged: true });
          if (refreshCount) refreshCount();
          if (refreshToggle) refreshToggle();
          if (refreshConflicts) refreshConflicts();
        }
      }
    }
    refresh();
  });
  mainCol.addEventListener("click", () => setTimeout(refresh, 0));   // ("Select All" ticks without a change event)

  // a note above the list when some mods are variants
  loadUnitSlots(entry.units).then(() => {
    if (entry.units.some(k => unitSlots[k] && unitSlots[k].twins > 1)) {
      const hdr = modsCard && modsCard.querySelector(".modal-card-header");
      if (hdr && !modsCard.querySelector(".cc-variant-note")) {
        hdr.after(cgEl("div", "cc-variant-note", "Some of these are variants of the same files (colours or options): pick one of each."));
      }
    }
  });
  refresh();
}

function openCharacterModal(name) {
  voiceStop();
  const docked = wantsDock(name);
  const t = beginDetail(docked, name);
  const entry = findRosterEntry(name);
  t.title.textContent = isItemName(name) ? itemLabel(name) : name;
  const body = t.body;
  body.innerHTML = "";
  const refileNote = buildCardNotice(name);   // (a mod was just moved here - see refile.js)
  if (refileNote) body.appendChild(refileNote);
  const isCharCard = resolveItemCategory(name) === "characters";
  const isCourseCard = resolveItemCategory(name) === "courses";
  const isVehicleCard = VEHICLE_SECTION_KEYS.includes(resolveItemCategory(name));
  const isItemCard = isItemName(name);
  const guided = isCharCard || isCourseCard || isVehicleCard || isItemCard;   // the guided cards: a status head, the mods in use, then their steps

  const mainCol = document.createElement("div");
  mainCol.className = "modal-main-col";
  const twoCol = document.createElement("div");
  twoCol.className = "modal-two-col";
  twoCol.appendChild(mainCol);

  // --- Mods to merge card ---
  const modsCard = document.createElement("div");
  modsCard.className = "modal-card";

  const modsHeader = document.createElement("div");
  modsHeader.className = "modal-card-header";
  const modsTitle = document.createElement("span");
  modsTitle.className = "modal-card-title";
  modsTitle.textContent = guided ? "Mods" : "Mods to merge";
  const modsCount = document.createElement("span");
  modsCount.className = "modal-card-count";
  modsHeader.appendChild(modsTitle);
  modsHeader.appendChild(modsCount);
  modsCard.appendChild(modsHeader);

  // Conflicts among the ticked mods, as settle-it-here cards (full width, above
  // the mod list - see buildConflictCard).
  const conflictBox = document.createElement("div");
  conflictBox.id = "modal-conflict-box-wrap";
  conflictBox.hidden = true;

  // A mod can clash with one checked under a completely different item (a
  // whole-wave course bundle, an Inkling Boy mod vs an Inkling Girl one), so
  // this asks about every checked mod in the app, then keeps just the clashes
  // that involve one of THIS item's mods.
  async function updateModalConflicts() {
    const mine = new Set(entry.units);
    if (![...mine].some(k => state.checked[k])) {
      conflictBox.hidden = true;
      conflictBox.replaceChildren();
      return;
    }
    const result = await pywebview.api.get_all_conflicts();
    const relevant = (result.groups || []).filter(g => g.mods.some(m => mine.has(m)));
    conflictBox.replaceChildren();
    if (relevant.length === 0) {
      conflictBox.hidden = true;
      return;
    }
    conflictBox.hidden = false;
    for (const g of relevant) {
      conflictBox.appendChild(buildConflictCard(g, {
        scope: "popup",
        onSettled: () => { refreshBehindModal(); setTimeout(() => { updateModalConflicts(); refreshLeftOutBadges(); }, 900); },
      }));
    }
  }

  const modCheckboxes = [];
  // which of this card's mods came through GameBanana (only those can be moved - see Api.get_mod_ids), once read
  let movableIds = null;
  if (guided && entry.units.length) pywebview.api.get_mod_ids(name, entry.units).then(r => { movableIds = r || {}; }, () => { movableIds = {}; });

  // "Files" buttons say how many of a mod's files are currently left out.
  function refreshLeftOutBadges() {
    pywebview.api.get_excluded_files().then(all => {
      for (const { key, filesBtn } of modCheckboxes) {
        const n = (all[key] || []).length;
        filesBtn.dataset.leftOut = n;
        filesBtn.textContent = n ? `Files · ${n} left out` : "Files";
        filesBtn.classList.toggle("has-leftout", n > 0);
      }
    });
  }

  function refreshModsCount() {
    const selected = entry.units.filter(k => state.checked[k]).length;
    modsCount.textContent = entry.units.length ? `${selected}/${entry.units.length} selected` : "";
    modsCount.classList.toggle("some-selected", selected > 0);
  }

  function refreshModsToggleBtn() {
    if (!modsToggleBtn) return;
    const selectable = selectableUnits();
    const allChecked = selectable.length > 0 && selectable.every(k => state.checked[k]);
    modsToggleBtn.textContent = allChecked ? "Deselect All" : "Select All";
  }

  // Unit keys that are exefs code patches (filled in asynchronously below).
  // "Select All" deliberately skips these - a code patch changes the game's
  // executable and only works on one exact game version, so it's always an
  // individual, deliberate tick rather than something a bulk toggle sweeps in.
  const exefsKeys = new Set();
  const selectableUnits = () => entry.units.filter(k => !exefsKeys.has(k) && !skipsSelectAll(k));

  let modsToggleBtn = null;
  if (entry.units.length > 1) {
    modsToggleBtn = document.createElement("button");
    modsToggleBtn.className = "ghost small";
    modsToggleBtn.addEventListener("click", () => {
      const selectable = selectableUnits();
      const target = !(selectable.length > 0 && selectable.every(k => state.checked[k]));
      for (const { key, cb, row } of modCheckboxes) {
        if (exefsKeys.has(key)) continue;
        if (target && skipsSelectAll(key)) continue;   // Select All leaves out other characters' slots and duplicate variants
        state.checked[key] = target;
        cb.checked = target;
        row.classList.toggle("checked", target);
      }
      saveChecked();
      refreshBehindModal({ ifChanged: true });
      updateModalConflicts();
      refreshModsCount();
      refreshModsToggleBtn();
    });
    modsHeader.insertBefore(modsToggleBtn, modsCount);
  }

  if (entry.units.length === 0) {
    const p = document.createElement("div");
    p.className = "modal-empty";
    const emptyCategory = resolveItemCategory(name);
    const emptyNoun = emptyCategory === "characters" ? "this character"
      : emptyCategory === "courses" ? "this course"
      : itemLabel(name);
    p.textContent = `Nothing downloaded for ${emptyNoun} yet.`;
    modsCard.appendChild(p);
    // A download that extracted fine but has no romfs/ folder (a loose-file
    // archive, or an exefs-only patch like most Mechanics mods) is never
    // discovered as a mergeable unit, so this list stays empty even though the
    // file IS downloaded - say so instead of "nothing downloaded".
    pywebview.api.gb_get_saved_mods(name).then(saved => {
      const NOT_MERGEABLE = new Set(["needs_manual_fix", "missing_romfs", "ui_assets"]);
      const stuck = (saved || []).reduce(
        (n, m) => n + (m.files || []).filter(f => NOT_MERGEABLE.has(f.download_status)).length, 0);
      if (stuck === 0 || !p.isConnected) return;
      p.textContent = `${stuck} downloaded file${stuck === 1 ? "" : "s"} for ${emptyNoun === name ? name : emptyNoun} `
        + `can't be merged yet - no romfs folder was found in ${stuck === 1 ? "it" : "them"} `
        + `(an unrecognized layout, or UI art). See the status under "GameBanana mods" below.`;
    });
  } else {
    for (const key of entry.units) {
      const row = document.createElement("div");
      row.className = "mod-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.checked[key];
      if (cb.checked) row.classList.add("checked");
      const label = document.createElement("label");
      label.textContent = isCharCard ? charModLabel(key) : key.split("/").slice(isCourseCard || isVehicleCard || isItemCard ? 2 : 1).join("/");
      if (isCharCard) label.title = modLabel(key, true);
      const isPackRow = (entry.packUnits || []).includes(key);   // (a pack filed under another thing, listed here too)
      if (isPackRow) label.title = `Pack - filed under ${key.split("/")[1]}`;
      cb.addEventListener("change", () => {
        state.checked[key] = cb.checked;
        row.classList.toggle("checked", cb.checked);
        saveChecked();
        refreshBehindModal({ ifChanged: true });
        updateModalConflicts();
        refreshModsCount();
        refreshModsToggleBtn();
      });
      row.appendChild(cb);
      row.appendChild(label);
      const alsoBadge = buildPackBadge(key, name);
      if (alsoBadge) row.appendChild(alsoBadge);
      const noteBtn = buildModNoteControl(key, row);
      const openFolderBtn = document.createElement("button");
      openFolderBtn.className = "ghost small";
      openFolderBtn.textContent = "Open folder";
      openFolderBtn.title = "Open this mod's folder";
      openFolderBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const result = await pywebview.api.reveal_mod_folder(key);
        if (!result.success) {
          const note = document.createElement("div");
          note.className = "reveal-error";
          note.textContent = result.error;
          row.appendChild(note);
        }
      });
      const filesBtn = document.createElement("button");
      filesBtn.className = "ghost small files-btn";
      filesBtn.textContent = "Files";
      filesBtn.title = "See every file in this mod and leave single files out of the merge";
      let filesPanelEl = null;
      filesBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (filesPanelEl) { filesPanelEl.remove(); filesPanelEl = null; return; }
        filesPanelEl = buildFilesPanel(key, () => { refreshLeftOutBadges(); updateModalConflicts(); refreshBehindModal(); });
        row.after(filesPanelEl);
      });
      const removeBtn = buildRemoveModButton(key, async () => {
        await refreshViewsState();
        openCharacterModal(name);
        refreshBehindModal();
      });
      if (guided) {
        // folder / files / remove sit behind the row's "..." as a small menu (the buttons themselves are never shown;
        // the menu runs them, and its files entry carries the left-out count). The mod's voice lines and menu pictures
        // are not in here: each has its own icon on the row.
        const kb = clKebab(`More for ${label.textContent}`, () => [
          { label: "Open folder", title: openFolderBtn.title, run: () => openFolderBtn.click() },
          { label: Number(filesBtn.dataset.leftOut) ? `Edit included files \u00b7 ${filesBtn.dataset.leftOut} left out` : "Edit included files",
            title: "Choose which of this mod's files are used - leave single files out of the merge", run: () => filesBtn.click() },
          "-",
          isPackRow ? {
            label: "Open where it's filed",
            title: `This pack is filed under ${key.split("/")[1]} and listed here because it replaces ${refileLabel(name)} too.`,
            run: () => jumpToModKey(key),
          } : (() => {
            const tracked = movableIds && movableIds[key];
            return {
              label: `Move to another ${refileNoun(name)}...`,
              title: tracked ? `This mod replaces something else than ${refileLabel(name)}? Move it there.` : "Only mods downloaded through GameBanana can be moved.",
              disabled: !tracked,
              run: () => openMoveDialog({ from: name, modName: label.textContent, modId: tracked.mod_id, recordType: tracked.record_type }),
            };
          })(),
          { label: "Remove", title: removeBtn.title, danger: true, run: () => removeBtn.click() },
        ]);
        kb.classList.add("mod-more");
        row.appendChild(noteBtn);
        row.appendChild(kb);
      } else {
        row.appendChild(noteBtn);
        row.appendChild(openFolderBtn);
        row.appendChild(filesBtn);
        row.appendChild(removeBtn);
      }
      modsCard.appendChild(row);
      modCheckboxes.push({ key, cb, row, filesBtn });

      if (!guided) pywebview.api.has_mod_icon(key).then(iconPath => {
        if (!iconPath) return;
        const badge = document.createElement("button");
        badge.className = "icon-badge";
        badge.textContent = "icon";
        badge.title = "Click to reveal this mod's UI icon file";
        badge.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await pywebview.api.reveal_icon(key);
          if (!result.success) {
            const note = document.createElement("div");
            note.className = "reveal-error";
            note.textContent = result.error;
            row.appendChild(note);
          }
        });
        row.insertBefore(badge, row.querySelector(".mod-more"));   // (appends when there is no "..." button)
      });
    }

    // UI-icons-only companion downloads: no romfs, so they never got a checkbox
    // above, but ui_setup.gather_auto_icons() folds their loose pictures into
    // this character's tile regardless of whether anything here is ticked (see
    // "Icon pictures only" in Api._download_and_extract_one). Shown so that
    // isn't a surprise, with a one-click way to turn a still-active one off.
    if (isCharCard) pywebview.api.get_icon_only_mods(name).then(iconMods => {
      const KIND_LABEL = { Chara: "Select screen", edChara: "Results screen", MapChara: "Mini map" };
      for (const im of (iconMods || [])) {
        const row = document.createElement("div");
        row.className = "mod-row icon-only-row";
        row.appendChild(cgEl("span", "icon-only-mark", "🖼️"));
        row.appendChild(cgEl("span", "icon-only-label", im.mod));
        row.appendChild(cgEl("span", "icon-only-note", im.kinds.length
          ? `Icon pictures only - can't be added to the merge. Currently used for: ${im.kinds.map(k => KIND_LABEL[k] || k).join(", ")}.`
          : "Icon pictures only - can't be added to the merge. Not currently used (a better picture took over, or this was turned down)."));
        if (im.kinds.length) {
          const btn = button("Use game default", "small", async () => {
            await pywebview.api.clear_character_icons(name, im.kinds);
            refreshBehindModal();
            openCharacterModal(name);
          });
          btn.title = "Stop using this download's pictures here";
          row.appendChild(btn);
        }
        modsCard.appendChild(row);
      }
    });

    // Which mods bring menu pictures (and which of the three): a picture tag that opens them
    if (isCharCard) pywebview.api.get_unit_pictures(entry.units).then(found => {
      Object.assign(unitPics, found || {});
      for (const { key, row } of modCheckboxes) {
        const p = unitPics[key];
        if (!p || row.querySelector(".part-badge.picture")) continue;
        const rowLabel = row.querySelector("label");
        const tag = cgEl("button", "part-badge picture");
        tag.type = "button";
        tag.appendChild(pictureSvg());
        const summary = pictureSummary(p);
        tag.title = summary + ". Click to see them.";
        tag.setAttribute("aria-label", summary);
        tag.addEventListener("click", (e) => { e.stopPropagation(); openUnitPictures(key, entry.units, rowLabel ? rowLabel.textContent : key.split("/")[2]); });
        row.insertBefore(tag, row.querySelector(".part-badge.voice") || row.querySelector(".mod-more") || row.querySelector("button"));
      }
    });

    // Say what each unit really replaces, and which are look-alike variants.
    loadUnitSlots(entry.units).then(() => {
      if (isCharCard) {
        // say what each one replaces, and list the character's own mod first
        for (const { key, row } of modCheckboxes) {
          const u = unitSlots[key];
          if (!u || row.querySelector(".part-badge")) continue;
          for (const p of (u.parts || [])) {
            const anchor = row.querySelector(".mod-more") || row.querySelector("button");
            if (p !== "Voice") { row.insertBefore(cgEl("span", "part-badge", p), anchor); continue; }
            // Voice: just the speaker; it opens the list of lines to listen to
            const rowLabel = row.querySelector("label");
            const modName = rowLabel ? rowLabel.textContent : key.split("/")[2];
            const what = voiceWhat(u.voice && u.voice.race, u.voice && u.voice.menu);
            const tag = cgEl("button", "part-badge voice");
            tag.type = "button";
            tag.appendChild(speakerSvg());
            tag.title = `This mod includes voice files: ${what}. Click to listen to them.`;
            tag.setAttribute("aria-label", `Voice lines (${what})`);
            tag.addEventListener("click", (e) => { e.stopPropagation(); openVoiceLines(key, modName); });
            row.insertBefore(tag, anchor);
          }
        }
        const rank = k => ((unitSlots[k] && unitSlots[k].parts) || []).includes("Character") ? 0 : 1;
        [...modCheckboxes].sort((a, b) => rank(a.key) - rank(b.key)).forEach(x => x.row.parentNode.appendChild(x.row));
      }
      for (const { key, row } of modCheckboxes) {
        if (row.querySelector(".slot-badge")) continue;
        for (const b of unitSlotBadges(key, name)) {
          b.classList.add("slot-badge");
          row.insertBefore(b, row.querySelector("button"));
        }
      }
      refreshModsToggleBtn();
    });

    // Flag mods whose romfs is nothing but packed .sarc archives - the merge
    // never copies those in, so ticking one does nothing (see
    // Api.get_packed_only_units()).
    pywebview.api.get_packed_only_units(entry.units).then(packedKeys => {
      const packed = new Set(packedKeys || []);
      for (const { key, row } of modCheckboxes) {
        if (!packed.has(key) || row.querySelector(".packed-badge")) continue;
        const badge = document.createElement("span");
        badge.className = "packed-badge";
        badge.textContent = "packed archive only";
        badge.title = "Every file in this mod is a packed .sarc (common/menu/message), which a commit never copies in directly - it takes effect through the UI icons & text step. See Help.";
        row.insertBefore(badge, row.querySelector("button"));
      }
    });

    // Code patches (exefs .ips) get a badge naming the game build they
    // target - a patch for a different build silently does nothing.
    pywebview.api.get_exefs_unit_info(entry.units).then(info => {
      for (const { key, row } of modCheckboxes) {
        const patch = info && info[key];
        if (!patch || row.querySelector(".patch-badge")) continue;
        exefsKeys.add(key);
        const builds = patch.ids.map(i => i.version ? `v${i.version}` : `build ${i.id.slice(0, 8)}…`).join(" / ");
        const badge = document.createElement("span");
        badge.className = "patch-badge";
        badge.textContent = "code patch" + (builds ? ` · ${builds}` : "");
        badge.title = "An exefs code patch: it patches the game's executable and only works on the exact game version (build id) it was made for. Build id(s): "
          + patch.ids.map(i => i.id).join(", ") + ".";
        const firstButton = row.querySelector("button");
        row.insertBefore(badge, firstButton);
        if (patch.inert) {
          const warn = document.createElement("span");
          warn.className = "packed-badge";
          warn.textContent = "wrong game version";
          warn.title = "None of this patch's build ids match the game build id set in Settings - it would do nothing on your game.";
          row.insertBefore(warn, firstButton);
        } else if (patch.maybe) {
          const warn = document.createElement("span");
          warn.className = "packed-badge";
          warn.textContent = "might not match your game";
          warn.title = "This patch was made for an older game version than yours (you chose \"Not listed, probably newer\"). A game update often leaves the executable alone, so it may still work - if it does nothing, look for a newer version of the mod. Entering your exact build ID in Settings lets the app check for sure.";
          row.insertBefore(warn, firstButton);
        }
      }
      refreshModsToggleBtn();
    });
  }
  refreshModsCount();
  refreshModsToggleBtn();
  refreshLeftOutBadges();
  mainCol.appendChild(modsCard);

  // Mods filed under something else (a character, a course, another part)
  // that also ship this part's model file. A separate card on purpose: they
  // don't count toward "selected" above, and each is a whole mod - ticking one
  // enables everything in it, wherever it's filed (the checkbox shares the
  // same state as its own row).

  updateModalConflicts();

  // The GameBanana card is deliberately kept OUTSIDE .modal-two-col so it
  // always spans the modal's full width, even while the conflict sidebar is
  // narrowing the "Mods to merge" column next to it.
  const category = resolveItemCategory(name);
  if (guided) {
    // Nothing downloaded yet: finding a mod IS the task, so its section is open. Once there are mods it is folded
    // away (once - if the user opens it, it stays open) under the title "Add another mod".
    if (!entry.units.length) gbSectionCollapsed.delete(name);
    else if (!gbDefaulted.has(name)) { gbSectionCollapsed.add(name); gbDefaulted.add(name); }
  }
  const secondaryCard = buildGameBananaCard(name, category, guided ? { title: entry.units.length ? "Add another mod" : "Find a mod", slim: entry.units.length > 0 } : undefined);

  if (isCharCard) {
    assembleCharacterCard({ name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard,
      refreshCount: refreshModsCount, refreshToggle: refreshModsToggleBtn, refreshConflicts: updateModalConflicts });
    endDetail(docked);
    return;
  }
  if (isCourseCard) {
    assembleCourseCard({ name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard,
      refreshCount: refreshModsCount, refreshToggle: refreshModsToggleBtn, refreshConflicts: updateModalConflicts });
    endDetail(docked);
    return;
  }

  if (isItemCard) {
    assembleItemCard({ name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard,
      refreshCount: refreshModsCount, refreshToggle: refreshModsToggleBtn, refreshConflicts: updateModalConflicts });
    endDetail(docked);
    return;
  }

  if (isVehicleCard) {
    assembleVehicleCard({ name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard,
      refreshCount: refreshModsCount, refreshToggle: refreshModsToggleBtn, refreshConflicts: updateModalConflicts });
    endDetail(docked);
    return;
  }

  body.appendChild(conflictBox);
  body.appendChild(twoCol);
  body.appendChild(secondaryCard);

  endDetail(docked);
}

document.getElementById("btn-modal-close").addEventListener("click", closeModal);
document.getElementById("modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "modal-backdrop") closeModal();
});

