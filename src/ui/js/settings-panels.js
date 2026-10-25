// The worklist: every downloaded mod that is UI art or a packed .sarc with no romfs, grouped by character, each with a button to open its folder.
const uiIconWorklist = ui.asyncBox({
  el: document.getElementById("ui-icon-worklist-body"),
  load: () => pywebview.api.ui_icon_worklist(),
  isEmpty: (entries) => entries.length === 0,
  emptyText: "None downloaded yet - a GameBanana file recognized as UI art or a packed .sarc (no romfs) will show up here automatically.",
  emptyClass: "ui-icon-worklist-empty",
  errorText: "Couldn't read the list.",
  render: (entries) => {
    const byChar = new Map();
    for (const e of entries) {
      if (!byChar.has(e.character)) byChar.set(e.character, []);
      byChar.get(e.character).push(e);
    }
    return ui.el("div", null, [...byChar].map(([character, mods]) => ui.el("div", "ui-icon-worklist-group",
      ui.el("div", { class: "ui-icon-worklist-char", text: character }),
      mods.map(m => ui.el("div", "ui-icon-worklist-row",
        ui.el("div", "ui-icon-worklist-name", m.mod_name, ui.el("div", { class: "ui-icon-worklist-path", text: m.path })),
        ui.button({ label: "Open folder", variant: "ghost", size: "small", onClick: () => pywebview.api.reveal_path(m.path) }).el)))));
  },
});
function renderUiIconWorklist() { return uiIconWorklist.reload(); }

// Settings' "Game language" card: a normal commit builds these automatically (see merge() in
// mod_manager.py), so this is language (a set-once, rarely-touched preference - not worth a card
// of its own on the Commit page every time) and the rare pick-which-mod-wins conflict. A preview of what
// each ticked mod actually changes deliberately isn't rebuilt here - that's what the character/
// course card's own Menu look already shows, in context, which is a better place for it than a
// second copy here.
async function renderUiSetupSettingsCard() {
  const body = document.getElementById("ui-setup-settings-body");
  if (!uiSetup.data) body.replaceChildren(ui.loading("Reading your mods' menu files..."));
  let d;
  try { d = await pywebview.api.get_ui_setup(); } catch (e) { d = { error: String(e) }; }
  uiSetup.data = d;
  body.replaceChildren();
  if (d.error) { body.appendChild(ui.hint(d.error, { tone: "warn" })); return; }

  // the language (and the English variant) are settings like any other: drawn by settings-registry.js. The one thing worth saying about the
  // mods here is when they would do nothing: none of them change the chosen language, but some change another.
  const languageHost = document.createElement("div");
  body.appendChild(languageHost);
  await renderSettingsGroup("ui-text", languageHost);
  const chosen = state.settings.ui_setup_extra_english && (d.locale === "USen" || d.locale === "EUen") ? ["USen", "EUen"] : [d.locale];   // (English (unspecified) builds both)
  const others = d.locales.filter(l => !chosen.includes(l.code)).map(l => l.label);
  if (others.length && !d.locales.some(l => chosen.includes(l.code))) {
    const shown = others.slice(0, 3).join(", ") + (others.length > 3 ? ` and ${others.length - 3} more` : "");
    body.appendChild(ui.hint(`None of your mods change this language - they change ${shown}.`, { tag: "p" }));
  }

  const conflictEls = d.archives.map(renderUiArchiveConflicts).filter(Boolean);
  if (conflictEls.length) {
    body.appendChild(ui.hint("Two of your selected mods change the exact same icon or name - pick which one should win (otherwise the first one, alphabetically, is used):", { tag: "p" }));
    for (const el of conflictEls) body.appendChild(el);
  }

  // (what was built, file by file, isn't listed: nothing here can be done about it - a commit builds it, and the step bar says when one is due.
  // A file that is damaged is the one thing worth saying.)
  const damaged = d.archives.filter(a => a.verify && a.verify.problems && a.verify.problems.length).map(a => uisArchiveTitle(a)[1]);
  if (damaged.length) body.appendChild(ui.hint(`A built menu file has a problem (${damaged.join(", ")}) - commit again to build it fresh.`, { tone: "warn" }));
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

// The "Clear All Mods" question (the Maintenance card's button in app-modals.js asks it): a tick box for the downloaded files, and the
// clearing itself runs inside the dialog, which then says what it did.
function clearAllModsConfirm() {
  return {
    title: "Clear All Mods?",
    message: "This forgets every GameBanana mod link and file status tracked for every character. This can't be undone.",
    extra: {
      label: "Also delete mod download files", checked: true,
      hint: "Deletes the extracted mod folders (and their downloaded archives) that this app downloaded from GameBanana. Mods you added manually, outside the app, are never touched.",
    },
    confirmLabel: "Clear All Mods", busyLabel: "Clearing...", danger: true,
    onConfirm: async (deleteFiles) => {
      const result = await pywebview.api.clear_all_mods(deleteFiles);
      if (!result.success) return { error: result.error || "Something went wrong." };
      await loadMods();
      let msg = result.deleted > 0
        ? `Done \u2014 forgot every tracked mod and deleted ${result.deleted} file${result.deleted === 1 ? "" : "s"}/folder${result.deleted === 1 ? "" : "s"}.`
        : "Done \u2014 there was nothing tracked to clear.";
      const failed = result.errors && result.errors.length > 0;
      if (failed) msg += ` ${result.errors.length} item(s) couldn't be deleted: ${result.errors.join("; ")}`;
      return { message: msg, tone: failed ? "err" : "ok" };
    },
  };
}

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

