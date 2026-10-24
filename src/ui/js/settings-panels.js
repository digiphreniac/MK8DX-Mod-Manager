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

  const sel = document.createElement("select");
  const byCode = new Map(d.locales.map(l => [l.code, l]));
  for (const l of d.all_locales) {
    const o = document.createElement("option");
    o.value = l.code;
    const info = byCode.get(l.code);
    o.textContent = info ? `${l.label} - ${info.changes} name/text change${info.changes === 1 ? "" : "s"} from ${info.mods} mod${info.mods === 1 ? "" : "s"}` : `${l.label} - none of your mods change this language`;
    sel.appendChild(o);
  }
  sel.value = d.locale;
  sel.addEventListener("change", async () => {
    state.settings.ui_setup_locale = sel.value;
    await pywebview.api.save_settings(state.settings);
    uiSetup.data = null;
    scheduleFlowRefresh();
    await renderUiSetupSettingsCard();
  });
  body.appendChild(sel);
  if (d.locale === "USen" || d.locale === "EUen") {
    const lab = uisEl("label", "uis-note");
    lab.style.display = "block";
    lab.style.cursor = "pointer";
    lab.style.marginBottom = "4px";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!state.settings.ui_setup_extra_english;
    cb.style.marginRight = "6px";
    cb.addEventListener("change", async () => {
      state.settings.ui_setup_extra_english = cb.checked;
      await pywebview.api.save_settings(state.settings);
      scheduleFlowRefresh();
    });
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(
      `My Switch is set to English but I'm not sure which kind - also build ${d.locale === "USen" ? "European/UK English (EUen)" : "American English (USen)"}, so it works either way`));
    body.appendChild(lab);
  }

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

document.getElementById("setting-show-nsfw").addEventListener("change", async (e) => {
  state.settings.show_nsfw = e.target.checked;
  await pywebview.api.save_settings(state.settings);
});

document.getElementById("setting-game-version").addEventListener("change", async (e) => {
  await pywebview.api.set_game_version(e.target.value);
  state.settings = await pywebview.api.get_settings();
  document.getElementById("setting-game-build-id").value = state.settings.game_build_id || "";
  document.getElementById("setting-game-build-id-error").hidden = true;
  flow.status = await pywebview.api.get_flow_status();
  renderStepBar();
});

document.getElementById("setting-game-build-id").addEventListener("change", async (e) => {
  const errEl = document.getElementById("setting-game-build-id-error");
  const value = e.target.value.trim().toUpperCase();
  // Empty (check off), 32 hex characters, or just the first 16 (how the app matches them) - anything else is a typo
  // that would otherwise silently flag every patch as the wrong version.
  if (value !== "" && !/^([0-9A-F]{16}|[0-9A-F]{32})$/.test(value)) {
    errEl.textContent = "A build ID is 32 hex characters (0-9, A-F), or just its first 16.";
    errEl.hidden = false;
    return;
  }
  errEl.hidden = true;
  e.target.value = value;
  state.settings.game_build_id = value;
  await pywebview.api.save_settings(state.settings);
});

document.getElementById("setting-show-tile-counts").addEventListener("change", async (e) => {
  state.settings.show_tile_counts = e.target.checked;
  await pywebview.api.save_settings(state.settings);
  renderCharacterGrid();
});

document.getElementById("setting-play-select-voice").addEventListener("change", async (e) => {
  state.settings.play_select_voice = e.target.checked;
  await pywebview.api.save_settings(state.settings);
  if (!e.target.checked) voiceStop();
});

document.getElementById("setting-advanced-mode").addEventListener("change", async (e) => {
  state.settings.advanced_mode = e.target.checked;
  await pywebview.api.save_settings(state.settings);
  renderConflicts();
});

// "App experience" > Reset to default: the four options back to how they start (these match DEFAULT_SETTINGS in mod_manager.py).
// The button is only available while something differs, and each option's own side effect is repeated for the ones that changed.
const APP_EXPERIENCE_DEFAULTS = { show_tile_counts: false, play_select_voice: true, show_nsfw: false, advanced_mode: false };
const APP_EXPERIENCE_BOXES = {
  show_tile_counts: "setting-show-tile-counts", play_select_voice: "setting-play-select-voice",
  show_nsfw: "setting-show-nsfw", advanced_mode: "setting-advanced-mode",
};
function updateAppExperienceReset() {
  const differs = Object.entries(APP_EXPERIENCE_DEFAULTS).some(([key, value]) => document.getElementById(APP_EXPERIENCE_BOXES[key]).checked !== value);
  document.getElementById("btn-reset-app-experience").disabled = !differs;
}
document.getElementById("btn-reset-app-experience").closest(".modal-card").addEventListener("change", updateAppExperienceReset);
document.getElementById("btn-reset-app-experience").addEventListener("click", async () => {
  const changed = Object.keys(APP_EXPERIENCE_DEFAULTS).filter(k => document.getElementById(APP_EXPERIENCE_BOXES[k]).checked !== APP_EXPERIENCE_DEFAULTS[k]);
  for (const key of changed) {
    state.settings[key] = APP_EXPERIENCE_DEFAULTS[key];
    document.getElementById(APP_EXPERIENCE_BOXES[key]).checked = APP_EXPERIENCE_DEFAULTS[key];
  }
  updateAppExperienceReset();
  await pywebview.api.save_settings(state.settings);
  if (changed.includes("show_tile_counts")) renderCharacterGrid();
  if (changed.includes("advanced_mode")) renderConflicts();
});

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

function openChangeMasterDirModal() {
  document.getElementById("modal-backdrop").classList.add("above-settings");
  openCharacter = null;
  document.getElementById("modal-title").textContent = "Change Master Directory";
  const body = document.getElementById("modal-body");
  body.innerHTML = "";

  const container = document.createElement("div");
  body.appendChild(container);

  async function start() {
    const chosen = await pywebview.api.pick_master_dir();
    if (!chosen) return;
    renderMasterDirConfirmStep(container, chosen, async () => {
      closeModal();
      await loadMods();
      await loadSettings();
    }, start);
  }

  const intro = document.createElement("p");
  intro.className = "clear-all-warning";
  intro.textContent = "Choose a new folder for your mods, downloads, and settings.";
  container.appendChild(intro);
  const chooseBtn = document.createElement("button");
  chooseBtn.className = "primary small";
  chooseBtn.textContent = "Choose Folder…";
  chooseBtn.addEventListener("click", start);
  container.appendChild(chooseBtn);

  document.getElementById("modal-backdrop").hidden = false;
}
document.getElementById("btn-change-master-dir").addEventListener("click", openChangeMasterDirModal);

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

