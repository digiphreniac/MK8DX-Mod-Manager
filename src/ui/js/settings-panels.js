async function renderUiIconWorklist() {
  const container = document.getElementById("ui-icon-worklist-body");
  const entries = await pywebview.api.ui_icon_worklist();
  container.innerHTML = "";
  if (entries.length === 0) {
    container.innerHTML = '<div class="ui-icon-worklist-empty">None downloaded yet - a GameBanana file recognized as UI art or a packed .sarc (no romfs) will show up here automatically.</div>';
    return;
  }
  const byChar = new Map();
  for (const e of entries) {
    if (!byChar.has(e.character)) byChar.set(e.character, []);
    byChar.get(e.character).push(e);
  }
  for (const [character, mods] of byChar) {
    const group = document.createElement("div");
    group.className = "ui-icon-worklist-group";
    const heading = document.createElement("div");
    heading.className = "ui-icon-worklist-char";
    heading.textContent = character;
    group.appendChild(heading);
    for (const m of mods) {
      const row = document.createElement("div");
      row.className = "ui-icon-worklist-row";
      const nameEl = document.createElement("div");
      nameEl.className = "ui-icon-worklist-name";
      nameEl.textContent = m.mod_name;
      const pathEl = document.createElement("div");
      pathEl.className = "ui-icon-worklist-path";
      pathEl.textContent = m.path;
      nameEl.appendChild(pathEl);
      row.appendChild(nameEl);
      const openBtn = document.createElement("button");
      openBtn.className = "ghost small";
      openBtn.textContent = "Open folder";
      openBtn.addEventListener("click", () => pywebview.api.reveal_path(m.path));
      row.appendChild(openBtn);
      group.appendChild(row);
    }
    container.appendChild(group);
  }
}

// Settings' "UI icons & text" card: a normal commit builds these automatically (see merge() in
// mod_manager.py), so this is language (a set-once, rarely-touched preference - not worth a card
// of its own on the Commit page every time), the rare pick-which-mod-wins conflict, and everything
// for looking at the result without committing, undoing it, or doing it by hand. A preview of what
// each ticked mod actually changes deliberately isn't rebuilt here - that's what the character/
// course card's own Menu look already shows, in context, which is a better place for it than a
// second copy here.
async function renderUiSetupSettingsCard() {
  const body = document.getElementById("ui-setup-settings-body");
  if (!uiSetup.data) body.replaceChildren(loadingNote("Reading your mods' menu files..."));
  let d;
  try { d = await pywebview.api.get_ui_setup(); } catch (e) { d = { error: String(e) }; }
  uiSetup.data = d;
  body.replaceChildren();
  if (d.error) { body.appendChild(uisEl("div", "uis-warn", d.error)); return; }

  // the language (and the English variant) are settings like any other: drawn by settings-registry.js. What the mods change in it is
  // information about the mods, so it is said here.
  const languageHost = document.createElement("div");
  body.appendChild(languageHost);
  await renderSettingsGroup("ui-text", languageHost);
  const names = new Map(d.all_locales.map(l => [l.code, l.label]));
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const here = d.locales.find(l => l.code === d.locale);
  let note = here ? `Your mods make ${plural(here.changes, "name/text change")} in this language, from ${plural(here.mods, "mod")}.` : "None of your mods change this language.";
  const others = d.locales.filter(l => l.code !== d.locale).map(l => `${names.get(l.code)} (${l.changes})`);
  if (others.length) note += " Other languages they change: " + others.join(", ") + ".";
  body.appendChild(uisEl("p", "uis-note", note));

  const conflictEls = d.archives.map(renderUiArchiveConflicts).filter(Boolean);
  if (conflictEls.length) {
    body.appendChild(uisEl("p", "uis-note", "Two of your selected mods change the exact same icon or name - pick which one should win (otherwise the first one, alphabetically, is used):"));
    for (const el of conflictEls) body.appendChild(el);
  }

  if (!d.any_sources) {
    body.appendChild(uisEl("div", "settings-hint", "None of your currently selected mods change menu icons or names, so there's nothing built right now. Select one and this fills in."));
    return;
  }

  const states = d.archives.map(a => ({ a, st: uisBuiltState(a) }));
  for (const { a, st } of states) {
    const [title, file] = uisArchiveTitle(a);
    const row = uisEl("div", "uis-result");
    row.appendChild(uisEl("span", "st " + st.kind, st.kind === "ok" ? "✓" : st.kind === "warn" ? "⚠" : "•"));
    row.appendChild(uisEl("span", null, `${file} (${title}) - ${st.text}`));
    body.appendChild(row);
  }
  body.appendChild(uisEl("p", "uis-note", "Built automatically the next time you commit. Files are saved to: " + d.ui_folder));

  const acts = uisEl("div", "uis-actions");
  const rebuildBtn = uisEl("button", "ghost small", "Rebuild now");
  rebuildBtn.title = "Builds without waiting for a commit - useful to inspect the files, or if you undid them and want them back without re-committing.";
  rebuildBtn.addEventListener("click", async () => {
    rebuildBtn.disabled = true;
    rebuildBtn.textContent = "Building...";
    const locales = [d.locale];
    if (state.settings.ui_setup_extra_english && (d.locale === "USen" || d.locale === "EUen")) {
      locales.push(d.locale === "USen" ? "EUen" : "USen");
    }
    uiSetup.lastBuild = await pywebview.api.build_ui_setup(locales);
    uiSetup.data = null;
    await renderUiSetupSettingsCard();
    scheduleFlowRefresh();
  });
  acts.appendChild(rebuildBtn);
  const folderBtn = uisEl("button", "ghost small", "Open the folder");
  folderBtn.addEventListener("click", () => pywebview.api.open_ui_setup_folder());
  acts.appendChild(folderBtn);
  if (states.some(x => x.st.kind !== "todo")) {
    const undoBtn = uisEl("button", "ghost small", "Undo (remove the built files)");
    undoBtn.title = "Puts the game back to its own menus - your built files are kept in a backup folder";
    undoBtn.addEventListener("click", async () => {
      if (!confirm("Remove the built UI files? The game will use its own menu icons and text again (a backup copy is kept).")) return;
      await pywebview.api.reset_ui_setup([d.locale, "USen", "EUen"]);
      uiSetup.data = null;
      await renderUiSetupSettingsCard();
      scheduleFlowRefresh();
    });
    acts.appendChild(undoBtn);
  }
  body.appendChild(acts);

  const lb = uiSetup.lastBuild;
  if (lb) {
    if (!lb.success) {
      body.appendChild(uisEl("div", "uis-warn", lb.error));
    } else {
      for (const r of lb.results) {
        if (r.error) body.appendChild(uisEl("div", "uis-warn", `${r.archive}: ${r.error}`));
      }
    }
  }

  const adv = document.createElement("details");
  adv.appendChild(uisEl("summary", null, "Advanced: prefer to do this by hand in another program?"));
  const advBody = uisEl("div", "uis-note");
  advBody.style.fontSize = "12.5px";
  advBody.appendChild(uisEl("p", null, "You don't need to - committing does everything. If you'd still rather use a tool such as Switch Toolbox (github.com/KillzXGaming/Switch-Toolbox), know that: the icons are inside nested archives (common.sarc → cm_L_CharaIcon_00.szs → timg/__Combined.bntx, and menu.sarc → mn_L_CharaIcon_00.szs → the same); a whole-file swap would wipe out other mods' icons, so textures have to be copied one at a time; and community guides report that editing message.sarc's text inside Switch Toolbox itself can corrupt it (a separate MSBT editor is recommended). We couldn't test those steps ourselves."));
  advBody.appendChild(uisEl("p", null, "Whichever way you make them, save the finished files at the paths shown above, then click Check my work - it compares them against each mod's changes and shows exactly what's in and what's missing."));
  const guides = uisEl("p");
  guides.appendChild(document.createTextNode("Community guides: "));
  for (const [label, url] of [["Adding custom character icons", "https://gamebanana.com/tuts/15599"], ["Editing message.sarc", "https://gamebanana.com/tuts/15589"]]) {
    const a2 = uisEl("a", "help-ext-link", label);
    a2.dataset.url = url;
    a2.style.marginRight = "12px";
    a2.style.cursor = "pointer";
    a2.addEventListener("click", () => pywebview.api.open_help_link(url));
    guides.appendChild(a2);
  }
  advBody.appendChild(guides);
  const check = uisEl("button", "ghost small", "Check my work");
  check.addEventListener("click", async () => { check.disabled = true; check.textContent = "Checking..."; uiSetup.data = null; await renderUiSetupSettingsCard(); });
  advBody.appendChild(check);
  adv.appendChild(advBody);
  body.appendChild(adv);
}

// Shared by the first-run setup overlay and the Settings "Change..." flow:
// renders the "here's what you picked, bring your files or start fresh?"
// step into `container`, given a folder the user just chose via the native
// picker. onSuccess runs after set_master_dir() actually succeeds;
// onChooseAgain re-runs the picker (e.g. if this folder turns out unsuitable).
function renderMasterDirConfirmStep(container, chosenPath, onSuccess, onChooseAgain) {
  container.innerHTML = "";

  const pathLine = document.createElement("p");
  pathLine.className = "clear-all-warning";
  pathLine.appendChild(document.createTextNode("Folder selected:"));
  pathLine.appendChild(document.createElement("br"));
  const pathCode = document.createElement("code");
  pathCode.textContent = chosenPath;
  pathLine.appendChild(pathCode);
  container.appendChild(pathLine);

  const question = document.createElement("p");
  question.className = "clear-all-warning";
  question.textContent = "Bring your existing mods and settings along to this folder, or start fresh there?";
  container.appendChild(question);

  const resultBox = document.createElement("div");
  resultBox.className = "clear-all-result";
  resultBox.hidden = true;

  const actions = document.createElement("div");
  actions.className = "links-actions";

  const backBtn = document.createElement("button");
  backBtn.className = "ghost small";
  backBtn.textContent = "← Choose a different folder";
  backBtn.addEventListener("click", onChooseAgain);

  const startFreshBtn = document.createElement("button");
  startFreshBtn.className = "ghost small";
  startFreshBtn.textContent = "Start Fresh";

  const bringBtn = document.createElement("button");
  bringBtn.className = "primary small";
  bringBtn.textContent = "Bring My Files";

  async function commit(moveExisting) {
    backBtn.disabled = true;
    startFreshBtn.disabled = true;
    bringBtn.disabled = true;
    resultBox.hidden = true;
    (moveExisting ? bringBtn : startFreshBtn).textContent = moveExisting ? "Moving files..." : "Setting up...";
    const result = await diag.attempt(() => pywebview.api.set_master_dir(chosenPath, moveExisting));
    if (!result.success) {
      resultBox.className = "clear-all-result err";
      resultBox.textContent = result.error;
      resultBox.hidden = false;
      backBtn.disabled = false;
      startFreshBtn.disabled = false;
      bringBtn.disabled = false;
      startFreshBtn.textContent = "Start Fresh";
      bringBtn.textContent = "Bring My Files";
      return;
    }
    state.epoch = null;   // (this page's ticks belong to the folder it just left: nothing may be saved until loadMods() has loaded the new one's)
    for (const k of Object.keys(checkedPending)) delete checkedPending[k];
    onSuccess();
  }

  startFreshBtn.addEventListener("click", () => commit(false));
  bringBtn.addEventListener("click", () => commit(true));
  actions.appendChild(backBtn);
  actions.appendChild(startFreshBtn);
  actions.appendChild(bringBtn);
  container.appendChild(actions);
  container.appendChild(resultBox);
}

async function runMasterDirSetup() {
  const chosen = await pywebview.api.pick_master_dir();
  if (!chosen) return;
  const body = document.getElementById("setup-overlay-body");
  renderMasterDirConfirmStep(body, chosen, async () => {
    await loadMods();
    await loadSettings();
    openSetupWizard(1, false);
  }, runMasterDirSetup);
}
document.getElementById("btn-setup-choose-folder").addEventListener("click", runMasterDirSetup);

function openClearAllConfirmModal() {
  document.getElementById("modal-backdrop").classList.add("above-settings");
  openCharacter = null;
  document.getElementById("modal-title").textContent = "Clear All Mods?";
  const body = document.getElementById("modal-body");
  body.innerHTML = "";

  const warning = document.createElement("p");
  warning.className = "clear-all-warning";
  warning.textContent = "This forgets every GameBanana mod link and file status tracked for every character. This can't be undone.";
  body.appendChild(warning);

  const label = document.createElement("label");
  label.className = "settings-checkbox-label";
  const deleteFilesCb = document.createElement("input");
  deleteFilesCb.type = "checkbox";
  deleteFilesCb.checked = true;
  label.appendChild(deleteFilesCb);
  label.appendChild(document.createTextNode("Also delete mod download files"));
  body.appendChild(label);

  const hint = document.createElement("div");
  hint.className = "settings-hint";
  hint.textContent = "Deletes the extracted mod folders (and their downloaded archives) that this app downloaded from GameBanana. Mods you added manually, outside the app, are never touched.";
  body.appendChild(hint);

  const resultBox = document.createElement("div");
  resultBox.className = "clear-all-result";
  resultBox.hidden = true;
  body.appendChild(resultBox);

  const actions = document.createElement("div");
  actions.className = "links-actions";
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "ghost small";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", closeModal);
  const confirmBtn = document.createElement("button");
  confirmBtn.className = "danger small";
  confirmBtn.textContent = "Clear All Mods";
  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    cancelBtn.disabled = true;
    confirmBtn.textContent = "Clearing...";
    const result = await pywebview.api.clear_all_mods(deleteFilesCb.checked);
    if (!result.success) {
      resultBox.className = "clear-all-result err";
      resultBox.textContent = result.error || "Something went wrong.";
      resultBox.hidden = false;
      confirmBtn.disabled = false;
      cancelBtn.disabled = false;
      confirmBtn.textContent = "Clear All Mods";
      return;
    }
    await loadMods();

    let msg = result.deleted > 0
      ? `Done — forgot every tracked mod and deleted ${result.deleted} file${result.deleted === 1 ? "" : "s"}/folder${result.deleted === 1 ? "" : "s"}.`
      : "Done — there was nothing tracked to clear.";
    if (result.errors && result.errors.length > 0) {
      msg += ` ${result.errors.length} item(s) couldn't be deleted: ${result.errors.join("; ")}`;
      resultBox.className = "clear-all-result err";
    } else {
      resultBox.className = "clear-all-result ok";
    }
    resultBox.textContent = msg;
    resultBox.hidden = false;
    confirmBtn.hidden = true;
    cancelBtn.disabled = false;
    cancelBtn.textContent = "Close";
  });
  actions.appendChild(cancelBtn);
  actions.appendChild(confirmBtn);
  body.appendChild(actions);

  document.getElementById("modal-backdrop").hidden = false;
}

document.getElementById("btn-clear-all-mods").addEventListener("click", openClearAllConfirmModal);

// Jumps from a mod key printed in the Output log straight to that mod's
// modal - Course Select for a course key (selecting its cup first, same as
// clicking the cup then the course tile), Character Select for a character
// key - so a conflict listing doubles as a set of shortcuts to go fix it.
async function jumpToModKey(key) {
  const category = key.split("/")[0];
  if (category === "characters") {
    const entry = state.roster.find(r => r.units.includes(key));
    if (!entry) return;
    switchView("characters");
    openCharacterModal(entry.name);
    return;
  }
  if (category === "courses") {
    for (const cup of state.cups) {
      const course = cup.courses.find(c => c.units.includes(key));
      if (course) {
        await openCourseCard(course.name);
        return;
      }
    }
    return;
  }
  const vehicleSection = state.vehicles.find(sec => sec.key === category);
  if (vehicleSection) {
    const item = vehicleSection.items.find(i => i.units.includes(key));
    if (!item) return;
    switchView("vehicles");
    openCharacterModal(item.name);
    return;
  }
  if (category === ITEMS_CATEGORY) {
    const item = state.items.find(i => i.units.includes(key));
    if (item) await openItemCard(item.name);
    return;
  }
  const simple = SIMPLE_CATEGORIES.find(c => c.key === category);
  if (simple) {
    switchView("more");
    await renderMoreList();
    openCharacterModal(simple.label);
  }
}

