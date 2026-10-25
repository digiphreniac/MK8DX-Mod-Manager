// The item card - what opens when you click an item on the Items screen (docked beside the grid on a wide window, else a
// pop-up) - built like the character, course and vehicle cards: a status head (the item's picture, its name and where it
// stands), the mods in use (with "Find a mod" / "Add another mod" under them), and - since GameBanana files every item mod in one
// flat category, so a download often lands under the wrong item, or under "Other items" - moving one is every mod's "..." menu (see
// refile.js), and "Other items" lists its mods with a picker each. openCharacterModal() builds the mods part for all the cards;
// this file adds what is specific to an item.

function assembleItemCard(ctx) {
  const { name, entry, body, mainCol, conflictBox, modCheckboxes, secondaryCard } = ctx;
  const hasMods = entry.units.length > 0;
  const modsCard = mainCol.querySelector(".modal-card");
  const catchAll = !!entry.catch_all;
  const label = itemLabel(name);
  let manage = false;
  variantSwitchRefresh = null;
  if (reviewQueue.active) body.appendChild(buildReviewBar());   // the guided pass through what is unfinished

  // what this item is now, always in view: its picture, its name, where it stands
  const pic = ui.el("img", "cc-item-pic");
  pic.alt = "";
  pic.hidden = true;
  const chip = ui.chip({ size: "md" });
  const headName = ui.el("div", "cc-headname", label);
  const headSub = ui.el("div", "cc-headsub");
  const headText = ui.el("div", "cc-headtext");
  headText.appendChild(headName);
  headText.appendChild(headSub);
  const head = ui.el("div", "cc-head");
  head.appendChild(pic);
  head.appendChild(headText);
  head.appendChild(chip.el);
  body.appendChild(head);
  const showPicture = () => {
    const src = itemIcons[name];
    pic.hidden = !src;
    if (src && pic.src !== src) pic.src = src;
  };
  showPicture();
  loadItemIcons().then(() => { if (pic.isConnected) showPicture(); });
  body.appendChild(conflictBox);   // clash warnings are never folded away

  // The mods: the ones in use stay on screen as rows; the rest sit behind "Manage"; adding another is a quiet row under.
  const modPanel = ui.el("div", "cc-panel");
  let manageBtn = null, modHint = null;
  if (hasMods && modsCard) {
    modsCard.classList.add("cc-mods");
    const hdr = modsCard.querySelector(".modal-card-header");
    manageBtn = button("Manage", "ghost small cc-manage", () => { manage = !manage; refresh(); });
    hdr.appendChild(manageBtn);
    modHint = ui.el("div", "cc-hint");
    hdr.after(modHint);
  }
  if (hasMods) modPanel.appendChild(mainCol);
  modPanel.appendChild(secondaryCard);
  body.appendChild(modPanel);

  // ---- "Other items": give each mod its item ----
  // Every mod's "..." menu can move it (see refile.js); "Other items" is where mods that name no single item pile up, so it also
  // lists each one with a picker right here, open by default.
  const moveBox = ui.el("details", "cc-move");
  moveBox.hidden = true;
  const moveHead = ui.el("summary", null, "Give a mod its item");
  const moveBody = ui.el("div", "cc-move-body");
  moveBox.appendChild(moveHead);
  moveBox.appendChild(moveBody);
  if (catchAll) body.appendChild(moveBox);

  async function loadMoveRows() {
    if (!hasMods || !catchAll) return;
    let ids = {};
    try { ids = (await pywebview.api.get_mod_ids(name, entry.units)) || {}; } catch (e) { ids = {}; }
    if (!moveBox.isConnected) return;
    const keys = entry.units.filter(k => ids[k]);
    if (!keys.length) return;
    moveBody.replaceChildren();
    moveBody.appendChild(ui.hint(`These mods don't replace one single listed item. Pick the item each one replaces and move it there - its files, its selection and its GameBanana record all move with it.`, { class: "cg-note" }));
    for (const key of keys) {
      const row = ui.el("div", "cc-move-row");
      const modName = key.split("/").slice(2).join("/");
      row.appendChild(ui.el("span", "cc-move-name", modName));
      const sel = document.createElement("select");
      sel.appendChild(new Option("Move to...", ""));
      for (const it of state.items) if (it.name !== name) sel.appendChild(new Option(itemLabel(it.name), it.name));
      const err = ui.el("span", "gb-mod-error");
      const go = button("Move", "small", async () => {
        if (!sel.value) return;
        go.disabled = true;
        go.textContent = "Moving...";
        const r = await refileMod({ from: name, to: sel.value, modId: ids[key].mod_id, recordType: ids[key].record_type, modName, auto: false });
        if (!r.success) { go.disabled = false; go.textContent = "Move"; err.textContent = r.error; }
      });
      row.appendChild(sel);
      row.appendChild(go);
      row.appendChild(err);
      moveBody.appendChild(row);
    }
    moveBox.hidden = false;
    moveBox.open = true;
  }

  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  function refresh() {
    const ticked = entry.units.filter(k => state.checked[k]);

    // --- the mods panel
    if (modsCard && manageBtn) {
      const some = ticked.length > 0;
      modsCard.classList.toggle("show-all", manage || !some);
      modHint.hidden = some && !manage;
      modHint.textContent = !some
        ? `None of these is in use yet. Select the one${entry.units.length > 1 ? "s" : ""} you want${catchAll ? "" : ` for ${label}`}.`
        : "Select a mod to use it, deselect it to stop. Two mods that replace the same item clash - the app shows you which files.";
      manageBtn.hidden = !(some && (entry.units.length > ticked.length || manage));
      manageBtn.textContent = manage ? "Done" : "Manage";
    }

    // --- the headline: its name, and a sentence saying where things stand
    let sub;
    if (!hasMods) sub = catchAll ? "Nothing here - a mod that fits none of the listed items, or several of them (an item pack), goes here." : "No mod yet - find one below.";
    else if (!ticked.length) sub = `${plural(entry.units.length, "mod")} downloaded, none in use yet.`;
    else sub = `${plural(ticked.length, "mod")} in use.`;
    headSub.textContent = sub;

    // --- the chip
    let chipText, chipCls = "";
    if (!hasMods) chipText = "No mod yet";
    else if (!ticked.length) { chipText = "Choose a mod"; chipCls = "warn"; }
    else { chipText = "In use"; chipCls = "ok"; }
    chip.set(chipText, chipCls || "neutral");
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
  loadMoveRows();
}
