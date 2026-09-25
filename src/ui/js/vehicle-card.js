// The vehicle-part card - the pop-up that opens when you click a body, wheel or glider on the Vehicles screen - built like
// the character and course cards: a status head (the part's picture, its name and where it stands), the mods in use (with
// "Find a mod" / "Add another mod" under them), then three guided steps. openCharacterModal() builds the mods part for all
// of them; this file adds what is specific to a part.
//
//   Right part - a mod is filed under a part by where it was found on GameBanana, but what matters is which model file it
//                ships. A ticked mod whose model file is for a DIFFERENT part changes nothing on this one; the step says so
//                and offers to move the mod to the part it is really for (or untick it). Nothing to confirm otherwise, so
//                the step needs no remembered answer - it is done when nothing is out of place. (Not part of "finished".)
//   Name       - what the game's menus call the part. Asked when a mod (or you) wants it called something other than the
//                game's own name - the mod's own text, a name you typed, or a guess from the mod's name (a suggestion you
//                accept, change, or decline). Nothing to check when nothing does.
//   Icons      - the part's picture in the parts menu. A mod that ships its own needs no check; otherwise the game's own
//                shows, or one you chose (a mod screenshot, or a file from your computer) - and you say once which you want.
//
// Name and Icons are confirmed per SET of ticked mods and remembered (Api.get_part_look() / confirm_part_name() /
// mark_part_icon_reviewed() - see mod_manager.py), so the part's tile can show "still to do" or "done" (markPartTiles()).

function vehicleKindOf(name) {
  const found = findVehicleItem(name);
  if (!found) return "";
  if (found.section === "wheels") return "Wheels";
  if (found.section === "gliders") return "Glider";
  return { kart: "Kart", bike: "Bike", atv: "ATV" }[found.item.type] || "Body";
}

// ---- the Name and Icons walkthroughs ----
// `onLook(look, {name, icons})` tells the card which of walk / summary each step is showing.
function buildPartLook(name, onLook) {
  const section = findVehicleItem(name).section;   // (the kind the name is filed under: "vehicles" | "wheels" | "gliders")
  const nameWrap = cgEl("div", "cl-look");
  const iconsWrap = cgEl("div", "cl-look");
  let nameView = null;     // "walk" forces the name editor open (Edit); null: follow the data
  let iconsView = null;    // same, for the picture
  let nameMode = "summary", iconsMode = "summary";
  let shots = [];          // the ticked mod's saved screenshots (what a picture can be made from)
  const draftKey = "part|" + name;

  function skeleton_() {
    const sk = cgEl("div", "cl-sk");
    sk.appendChild(loadingNote("Reading the mod's menu files..."));
    return sk;
  }
  nameWrap.appendChild(skeleton_());
  iconsWrap.appendChild(skeleton_());

  let loadToken = 0;
  async function load() {
    const mine = ++loadToken;
    await new Promise(r => setTimeout(r, 0));
    let look;
    try {
      look = await pywebview.api.get_part_look(name);
      if (!look.error && look.review) {
        try { shots = ((await pywebview.api.gb_get_saved_mods(name)) || []).flatMap(m => m.screenshots || []); } catch (e) { shots = []; }
      }
    } catch (e) {
      look = { error: "Couldn't read this part's menu files: " + e };
    }
    if (!nameWrap.isConnected && !iconsWrap.isConnected) return;   // (closed)
    if (mine !== loadToken) return;                                 // (a newer answer is on its way)
    draw(look);
  }
  // ticking a mod or finishing a download changes the answer: `pending` shows the wait at once, `reload` reads it
  menuLookState.pending = () => { if (nameWrap.isConnected || iconsWrap.isConnected) pending(); };
  menuLookState.reload = () => { if (nameWrap.isConnected || iconsWrap.isConnected) load(); };
  function pending() {
    loadToken++;
    nameWrap.replaceChildren(skeleton_());
    iconsWrap.replaceChildren(skeleton_());
    nameMode = iconsMode = "summary";
    if (onLook) onLook(null, { name: nameMode, icons: iconsMode });
  }
  function changed() {
    invalidateMenuLook();
    load();
    markPartTiles();
  }

  function draw(look) {
    if (look.error) {
      nameWrap.replaceChildren(cgEl("div", "uis-warn", look.error));
      iconsWrap.replaceChildren();
      nameMode = iconsMode = "summary";
      if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
      return;
    }
    if (!look.review) {   // nothing ticked: the card hides both rows
      nameWrap.replaceChildren();
      iconsWrap.replaceChildren();
      nameMode = iconsMode = "summary";
      if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
      return;
    }
    drawNameTask(look);
    drawIconsTask(look);
    if (onLook) onLook(look, { name: nameMode, icons: iconsMode });
  }

  // ------------------------------------------------------------------ the Name task
  function drawNameTask(look) {
    nameWrap.replaceChildren();
    const r = look.review, nm = look.name;
    if (!nm || !r.name_applicable) {
      nameMode = "summary";
      nameWrap.appendChild(cgEl("div", "cg-note", `Nothing to check: nothing changes what ${name} is called.`));
      return;
    }
    const walk = nameView === "walk" || (nameView === null && !r.name_done);
    nameMode = walk ? "walk" : "summary";
    if (walk) drawNameStep(look); else drawNameSummary(look);
  }

  function plateOf(text, input) {
    const box = cgEl("div", "cl-sum-name");
    const plate = cgEl("div", "cl-plate");
    if (input) {
      plate.classList.add("is-edit");
      const base = cgEl("span", "np-base", "");
      const sync = () => {
        const t = input.value.trim();
        base.textContent = t && t !== name ? "(" + name + ")" : "";
        input.style.width = (Math.max(input.value.length || name.length, 4) + 1) + "ch";
      };
      input.addEventListener("input", sync);
      plate.addEventListener("click", () => input.focus());
      plate.append(input, base);
      sync();
    } else {
      plate.append(text);
      if (text !== name) plate.appendChild(cgEl("span", "np-base", "(" + name + ")"));
    }
    box.appendChild(plate);
    return box;
  }

  function drawNameStep(look) {
    const nm = look.name, wrap = nameWrap;
    const guess = nm.state === "vanilla" ? nm.suggestion : null;
    wrap.appendChild(cgEl("div", "cl-q", `What should ${name} be called in the game?`));
    wrap.appendChild(cgEl("div", "cl-sub",
      guess ? `We guessed this from ${guess.source}. Change it if you like, or keep the game's name.`
      : nm.state === "you" ? "This is the name you chose. Change it if you like."
      : nm.state === "mod" ? `The mod (${(nm.who || []).join(", ")}) gives it this name. Change it if you like.`
      : "The mod doesn't say. Give it a name, or keep the game's own."));
    const input = document.createElement("input");
    input.type = "text";
    input.className = "cl-plate-input";
    input.maxLength = 40;
    input.spellcheck = false;
    input.placeholder = nm.vanilla;
    input.setAttribute("aria-label", "Name for " + name + " (leave empty to keep the game's name)");
    const baseline = nm.state === "vanilla" ? (guess ? guess.text : "") : nm.text;
    const draft = nameDrafts[draftKey] && nameDrafts[draftKey].base === baseline ? nameDrafts[draftKey].value : null;
    input.value = draft !== null ? draft : baseline;
    if (draft !== null && draft !== baseline) wrap.appendChild(cgEl("div", "cl-sub", "You had started typing this name - it wasn't saved yet."));
    wrap.appendChild(plateOf(null, input));
    const err = cgEl("span", "gb-mod-error");
    wrap.appendChild(err);

    const row = cgEl("div", "ml-review");
    const go = button(input.value.trim() ? "Use this name" : "Keep the game's name", "primary small", async () => {
      go.disabled = true;
      const typed = input.value.trim();
      const current = nm.state === "vanilla" ? "" : nm.text;
      let r = { success: true };
      if (typed !== current) {
        r = typed === "" ? (nm.state === "you" ? await pywebview.api.clear_item_name(name, section, false) : { success: true })
                         : await pywebview.api.set_item_name(name, section, typed, false);
      }
      if (!r.success) { go.disabled = false; err.textContent = r.error; return; }
      delete nameDrafts[draftKey];
      await pywebview.api.confirm_part_name(name);
      nameView = null;
      changed();
    });
    input.addEventListener("input", () => {
      nameDrafts[draftKey] = { value: input.value, base: baseline };
      go.textContent = input.value.trim() ? "Use this name" : "Keep the game's name";
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } });
    row.appendChild(go);
    row.appendChild(cgEl("span", "cg-note", "Or type a different one above."));
    wrap.appendChild(row);
    setTimeout(() => { if (input.isConnected) { input.focus(); const n = input.value.length; input.setSelectionRange(n, n); } }, 30);
  }

  function drawNameSummary(look) {
    const nm = look.name;
    const top = plateOf(nm ? nm.text : name);
    if (nm) {
      top.appendChild(cgEl("span", "cl-hint", nm.state === "you" ? (nm.auto ? "Name guessed from " + (nm.source || "the mod") : "Your name")
        : nm.state === "mod" ? "Name from " + (nm.who || []).join(", ") : "The game's own name"));
    }
    nameWrap.appendChild(top);
  }

  // ------------------------------------------------------------------ the Icons task
  // the picture as the parts menu shows it: `src` (default: the mod's or the chosen one)
  function pictureBox(look, src) {
    const p = look.picture;
    src = src === undefined ? (p && p.preview) : src;
    if (!src) return null;
    const box = cgEl("div", "cl-part-pict");
    const img = document.createElement("img");
    img.src = src;
    img.alt = "";
    box.appendChild(img);
    return box;
  }

  function drawIconsTask(look) {
    iconsWrap.replaceChildren();
    const r = look.review, p = look.picture;
    if (!r.icons_applicable) {
      iconsMode = "summary";
      const box = pictureBox(look);
      if (box) iconsWrap.appendChild(box);
      iconsWrap.appendChild(cgEl("div", "cg-note", p.state === "mod"
        ? `Nothing to check: ${p.mod ? "the mod " + p.mod : "the mod"} brings its own picture.`
        : "Nothing to check: this part's picture can't be changed."));
      return;
    }
    const walk = iconsView === "walk" || (iconsView === null && !r.icons_done);
    iconsMode = walk ? "walk" : "summary";
    if (walk) drawIconsStep(look); else drawIconsSummary(look);
  }

  // "Choose a picture": a mod screenshot or a file from the computer, cropped to the part's shape (the dialog offers both)
  function choose(label, primary) {
    return button(label, primary ? "primary small" : "small", () => {
      openIconGenModal(name, shots, "part", async () => {
        await pywebview.api.mark_part_icon_reviewed(name);
        iconsView = null;
        changed();
      });
    });
  }

  function drawIconsStep(look) {
    const p = look.picture, wrap = iconsWrap;
    wrap.appendChild(cgEl("div", "cl-q", `Which picture should ${name} have in the parts menu?`));
    if (p.state === "you") {
      wrap.appendChild(cgEl("div", "cl-sub", "The picture you chose. Keep it, choose a different one, or go back to the game's."));
      const box = pictureBox(look);
      if (box) wrap.appendChild(box);
      leftNote(p, wrap);
      const row = cgEl("div", "ml-review");
      row.appendChild(button("Use this picture", "primary small", async () => { await pywebview.api.mark_part_icon_reviewed(name); iconsView = null; changed(); }));
      row.appendChild(choose("Choose a different one", false));
      row.appendChild(button("Back to the game's picture", "small", async () => {
        await pywebview.api.clear_part_icon(name);
        await pywebview.api.mark_part_icon_reviewed(name);
        iconsView = null;
        changed();
      }));
      wrap.appendChild(row);
      return;
    }
    wrap.appendChild(cgEl("div", "cl-sub", "The mod doesn't bring a picture, so the game's own picture for this part shows (below), and it may not look like the mod's model. You can choose your own instead."));
    const own = pictureBox(look, p.default);
    if (own) wrap.appendChild(own);
    const row = cgEl("div", "ml-review");
    row.appendChild(choose("Choose a picture", true));
    row.appendChild(button("Keep the game's picture", "small", async () => { await pywebview.api.mark_part_icon_reviewed(name); iconsView = null; changed(); }));
    wrap.appendChild(row);
  }

  // a part that comes in outfits (the Standard Kart has one picture per character): a ticked mod that supplies its own
  // outfit pictures - a character's - keeps them; yours is used for the rest
  function leftNote(p, wrap) {
    if (p.left_to_mods) wrap.appendChild(cgEl("div", "cg-note", `${p.left_to_mods} outfit picture${p.left_to_mods === 1 ? " comes" : "s come"} from other mods you ticked (a character's, for instance) and ${p.left_to_mods === 1 ? "is" : "are"} left as ${p.left_to_mods === 1 ? "it is" : "they are"} - yours is used for all the others.`));
  }

  function drawIconsSummary(look) {
    const p = look.picture, wrap = iconsWrap;
    const box = pictureBox(look, p.state === "vanilla" ? p.default : undefined);
    if (box) wrap.appendChild(box);
    wrap.appendChild(cgEl("div", "cl-hint", p.state === "you" ? "A picture you chose" : "The game's own picture"));
    leftNote(p, wrap);
  }

  load();
  return {
    nameRoot: nameWrap, iconsRoot: iconsWrap,
    editName() { nameView = "walk"; if (nameWrap.isConnected) load(); },
    editIcons() { iconsView = "walk"; if (iconsWrap.isConnected) load(); },
    load,
  };
}

// ---- the card ----
function assembleVehicleCard(ctx) {
  const { name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard } = ctx;
  const hasMods = entry.units.length > 0;
  const modsCard = mainCol.querySelector(".modal-card");
  const kind = vehicleKindOf(name);
  let fit = null;          // {unit key: what is wrong} for this part's mods, once read (null: not yet)
  let look = null, nameMode = "summary", iconsMode = "summary", manage = false;
  let wasFinished = null;   // whether Name + Icons were both settled the last time an answer was in (null: none yet)
  variantSwitchRefresh = null;
  if (reviewQueue.active) body.appendChild(buildReviewBar());   // the guided pass through what is unfinished

  // what this part is now, always in view: its picture, its (modded) name, where it stands
  const pic = cgEl("img", "cc-vehicle-pic");
  pic.alt = "";
  pic.hidden = true;
  const chip = cgEl("span", "cc-chip");
  const headName = cgEl("div", "cc-headname", name);
  const headSub = cgEl("div", "cc-headsub");
  const headText = cgEl("div", "cc-headtext");
  headText.appendChild(headName);
  headText.appendChild(headSub);
  const head = cgEl("div", "cc-head");
  head.appendChild(pic);
  head.appendChild(headText);
  head.appendChild(chip);
  body.appendChild(head);
  const showPicture = () => {
    const p = look && look.picture;
    const src = (p && p.state !== "vanilla" && p.preview) || vehicleIcons[name];
    pic.hidden = !src;
    if (src && pic.src !== src) pic.src = src;
  };
  loadVehicleIcons().then(() => { if (pic.isConnected) showPicture(); });
  body.appendChild(conflictBox);   // clash warnings are never folded away

  // The mods: the ones in use stay on screen as rows; the rest sit behind "Manage"; adding another is a quiet row under.
  const modPanel = cgEl("div", "cc-panel");
  let manageBtn = null, modHint = null;
  if (hasMods && modsCard) {
    modsCard.classList.add("cc-mods");
    const hdr = modsCard.querySelector(".modal-card-header");
    manageBtn = button("Manage", "ghost small cc-manage", () => { manage = !manage; refresh(); });
    hdr.appendChild(manageBtn);
    modHint = cgEl("div", "cc-hint");
    hdr.after(modHint);
  }
  if (hasMods) modPanel.appendChild(mainCol);
  modPanel.appendChild(secondaryCard);
  body.appendChild(modPanel);

  const fitStep = makeCardStep("Right part");
  fitStep.root.classList.add("cc-step-inline");
  const nameStep = makeCardStep("Name");
  nameStep.root.classList.add("cc-step-inline");   // ("Edit" sits right beside the title and status, not at the far edge)
  const iconsStep = makeCardStep("Icons");
  iconsStep.root.classList.add("cc-step-inline");
  const lookTasks = buildPartLook(name, (l, mode) => { look = l; nameMode = mode.name; iconsMode = mode.icons; refresh(); });
  nameStep.content.appendChild(lookTasks.nameRoot);
  iconsStep.content.appendChild(lookTasks.iconsRoot);
  body.appendChild(fitStep.root);
  body.appendChild(nameStep.root);
  body.appendChild(iconsStep.root);

  async function loadFit() {
    if (!hasMods) { fit = {}; refresh(); return; }
    try { fit = (await pywebview.api.get_vehicle_fit(name, entry.units)) || {}; } catch (e) { fit = {}; }
    if (fitStep.root.isConnected) refresh();
  }

  // the ticked mods whose model file is for another part
  const wrongOnes = () => entry.units.filter(k => state.checked[k] && fit && fit[k]);

  function drawFitBody(wrong) {
    fitStep.content.replaceChildren();
    if (!wrong.length) {
      fitStep.content.appendChild(cgEl("div", "cg-note", `Nothing looks out of place: no ticked mod's model file is for a different part than ${name}.`));
      return;
    }
    for (const key of wrong) {
      const f = fit[key];
      const modName = key.split("/").slice(2).join("/");
      const others = (f.found_parts || []).slice(0, 3);
      const row = cgEl("div", "cc-fit-row");
      const names = others.map(p => p.name);
      row.appendChild(cgEl("div", "cl-sub", others.length
        ? `⚠ ${modName} replaces ${names.join(" / ")}, not ${name}.`
        : `⚠ ${modName} replaces something other than ${name} (its model file is "${f.found.join(", ")}").`));
      const err = cgEl("span", "gb-mod-error");
      const actions = cgEl("div", "ml-review");
      if (f.mod_id !== null && f.mod_id !== undefined) {
        for (const p of others) {
          const mv = button(`Move it to ${p.name}`, "primary small", async () => {
            mv.disabled = true;
            mv.textContent = "Moving...";
            const r = await refileMod({ from: name, to: p.name, modId: f.mod_id, recordType: f.record_type, modName, auto: false });
            if (!r.success) { mv.disabled = false; mv.textContent = `Move it to ${p.name}`; err.textContent = r.error; }
          });
          mv.title = `Re-file this mod (and its downloaded files) under ${p.name}`;
          actions.appendChild(mv);
        }
      }
      const untick = button("Untick it", "small", () => {
        const row_ = modCheckboxes.find(x => x.key === key);
        state.checked[key] = false;
        if (row_) { row_.cb.checked = false; row_.row.classList.remove("checked"); }
        pywebview.api.save_checked(state.checked);
        refreshBehindModal();
        ctx.refreshConflicts();
        ctx.refreshCount();
        refresh();
      });
      actions.appendChild(untick);
      actions.appendChild(err);
      row.appendChild(actions);
      fitStep.content.appendChild(row);
    }
  }

  function refresh() {
    const ticked = entry.units.filter(k => state.checked[k]);
    const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

    // --- the mods panel
    if (modsCard && manageBtn) {
      const some = ticked.length > 0;
      modsCard.classList.toggle("show-all", manage || !some);
      modHint.hidden = some && !manage;
      modHint.textContent = !some
        ? `None of these is in use yet. Tick the one${entry.units.length > 1 ? "s" : ""} you want for ${name}.`
        : "Tick a mod to use it, untick it to stop. Two mods that replace the same part clash - the app shows you which files.";
      manageBtn.hidden = !(some && (entry.units.length > ticked.length || manage));
      manageBtn.textContent = manage ? "Done" : "Manage";
    }

    // --- Right part: worked out from the files, nothing to confirm
    const wrong = wrongOnes();
    let fitState, fitSum;
    if (!ticked.length) { fitState = "pending"; fitSum = "Comes after you pick a mod"; }
    else if (fit === null) { fitState = "current"; fitSum = "Checking the mod's files..."; }
    else if (wrong.length) { fitState = "current"; fitSum = `${plural(wrong.length, "mod")} for a different part`; }
    else { fitState = "done"; fitSum = "Nothing to fix"; }
    setCardStepDot(fitStep, fitState);
    fitStep.sum.textContent = fitSum;
    fitStep.act.hidden = true;
    fitStep.content.hidden = !(ticked.length > 0 && fit !== null);
    if (!fitStep.content.hidden) drawFitBody(wrong);

    // --- Name and Icons: a walkthrough the first time, a summary (with Edit) afterwards
    function taskState(applicableKey, doneKey) {
      if (!ticked.length) return { state: "pending", sum: "Comes after you pick a mod" };
      if (!look) return { state: "current", sum: "Getting it ready..." };   // (also from a tick until the new answer)
      if (look.error) return { state: "current", sum: look.error };
      const review = look.review;
      if (!review) return { state: "current", sum: "Getting it ready..." };
      if (!review[applicableKey]) return { state: "done", sum: "Nothing to check" };
      if (review[doneKey]) return { state: "done", sum: "Completed" };
      return { state: "current", sum: "" };
    }
    const ns = taskState("name_applicable", "name_done");
    setCardStepDot(nameStep, ns.state);
    nameStep.sum.textContent = ns.sum;
    nameStep.content.hidden = !(ticked.length > 0);
    nameStep.act.hidden = !(ticked.length > 0 && ns.state === "done" && nameMode === "summary" && look && look.review && look.review.name_applicable);
    nameStep.act.textContent = "Edit";
    nameStep.act.onclick = () => lookTasks.editName();

    const is_ = taskState("icons_applicable", "icons_done");
    setCardStepDot(iconsStep, is_.state);
    iconsStep.sum.textContent = is_.sum;
    iconsStep.content.hidden = !(ticked.length > 0);
    iconsStep.act.hidden = !(ticked.length > 0 && is_.state === "done" && iconsMode === "summary" && look && look.review && look.review.icons_applicable);
    iconsStep.act.textContent = "Edit";
    iconsStep.act.onclick = () => lookTasks.editIcons();

    // --- the headline: the name it will have, its picture, and a sentence saying where things stand
    showPicture();
    const nm = look && look.name && look.name.available ? look.name : null;
    headName.replaceChildren();
    const modded = ticked.length && nm && nm.state !== "vanilla" && nm.text !== name;
    headName.append(modded ? nm.text : name);
    if (modded) headName.appendChild(cgEl("span", "np-base", "(" + name + ")"));
    const bothDone = ns.state === "done" && is_.state === "done";
    // it just became finished: if a guided review is walking through unfinished items, on to the next. Opening a card that
    // is already finished doesn't count - only a change from not finished to finished.
    if (look && !look.error && look.review) {
      if (wasFinished === false && bothDone) onItemFinished("part", name);
      wasFinished = bothDone;
    }
    const needing = [ns.state === "current" && "name", is_.state === "current" && "picture"].filter(Boolean);
    const where = kind ? kind + " · " : "";
    let sub;
    if (!hasMods) sub = where + "No mod yet - find one below.";
    else if (!ticked.length) sub = where + `${plural(entry.units.length, "mod")} downloaded, none in use yet.`;
    else {
      sub = where + `${plural(ticked.length, "mod")} in use`;
      if (wrong.length) sub += " · a mod is for a different part";
      if (!look) sub += " · reading its name and picture...";
      else if (needing.length) sub += ` · ${needing.join(" and ")} need${needing.length === 1 && needing[0] === "name" ? "s" : ""} a look`;
      else sub += " · name and picture confirmed";
    }
    headSub.textContent = sub;

    // --- the chip
    let chipText, chipCls = "";
    if (!hasMods) chipText = "No mod yet";
    else if (!ticked.length) { chipText = "Choose a mod"; chipCls = "warn"; }
    else if (ticked.length && !look) { chipText = "Reading..."; chipCls = ""; }
    else if (wrong.length || (ticked.length && !bothDone)) { chipText = "Needs a look"; chipCls = "warn"; }
    else { chipText = ticked.length ? "Done" : "In use"; chipCls = "ok"; }
    chip.textContent = chipText;
    chip.className = "cc-chip " + chipCls;
  }

  // Ticking inside the list: the list stays open while the user works in it - "Done" folds it back to the mods in use.
  mainCol.addEventListener("change", (e) => {
    const cb = e.target;
    if (!(cb instanceof HTMLInputElement) || cb.type !== "checkbox") return;
    if (modCheckboxes.find(x => x.cb === cb)) manage = true;
    refresh();
  });
  mainCol.addEventListener("click", () => setTimeout(refresh, 0));   // ("Select All" ticks without a change event)
  refresh();
  loadFit();
}
