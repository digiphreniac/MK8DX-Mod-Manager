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

// Settings' "Game language" card: a normal commit builds these automatically (see merge() in
// mod_manager.py), so this is language (a set-once, rarely-touched preference - not worth a card
// of its own on the Commit page every time) and the rare pick-which-mod-wins conflict. A preview of what
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

  // the language (and the English variant) are settings like any other: drawn by settings-registry.js. The one thing worth saying about the
  // mods here is when they would do nothing: none of them change the chosen language, but some change another.
  const languageHost = document.createElement("div");
  body.appendChild(languageHost);
  await renderSettingsGroup("ui-text", languageHost);
  const chosen = state.settings.ui_setup_extra_english && (d.locale === "USen" || d.locale === "EUen") ? ["USen", "EUen"] : [d.locale];   // (English (unspecified) builds both)
  const others = d.locales.filter(l => !chosen.includes(l.code)).map(l => l.label);
  if (others.length && !d.locales.some(l => chosen.includes(l.code))) {
    const shown = others.slice(0, 3).join(", ") + (others.length > 3 ? ` and ${others.length - 3} more` : "");
    body.appendChild(uisEl("p", "uis-note", `None of your mods change this language - they change ${shown}.`));
  }

  const conflictEls = d.archives.map(renderUiArchiveConflicts).filter(Boolean);
  if (conflictEls.length) {
    body.appendChild(uisEl("p", "uis-note", "Two of your selected mods change the exact same icon or name - pick which one should win (otherwise the first one, alphabetically, is used):"));
    for (const el of conflictEls) body.appendChild(el);
  }

  // (what was built, file by file, isn't listed: nothing here can be done about it - a commit builds it, and the step bar says when one is due.
  // A file that is damaged is the one thing worth saying.)
  const damaged = d.archives.filter(a => a.verify && a.verify.problems && a.verify.problems.length).map(a => uisArchiveTitle(a)[1]);
  if (damaged.length) body.appendChild(uisEl("div", "uis-warn", `A built menu file has a problem (${damaged.join(", ")}) - commit again to build it fresh.`));
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

