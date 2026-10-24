// ---- Settings: each one is defined ONCE, here ----
// A setting is one thing wherever it shows up. Its name, description, control and what happens when it changes are all defined in
// SETTINGS below, and both places draw it with the same code (renderSettingsGroup): the Settings window (a card per group) and the Setup
// wizard (a step per group). `showInSetup` is the only thing that makes a setting appear in Setup; nothing in setup-wizard.js or
// settings-panels.js knows about any one setting. To add a setting, add it here (and its default to DEFAULT_SETTINGS in mod_manager.py -
// Reset to default reads the defaults from there, through get_default_settings()).
//
// A setting: { key, group, kind, label, description, showInSetup, ... }
//   description  plain text; a newline in it (a backslash and an n, inside the quotes) starts a new line.
//   kind      "toggle" (a checkbox), "select" (needs options()), "text" (optional validate()/normalize()/datalist()), "folder" (the data
//             folder) or "path" (any other folder: status(), choose(path) and reset() say how).
//   label     text, or a function returning the text (a label that depends on another setting).
//   read()    the current value (default: state.settings[key], else the default); write(value) saves it (default: save_settings).
//   after()   what else has to happen once it changed (redraw something, refresh the flow bar ...).
//   visibleWhen()  a setting that only applies sometimes. refreshGroup: its change alters the other settings of its group.
// A group: { title, setupOrder, setupTitle?, setupLead?, setupSkip?, resettable? } - the Settings card, and the Setup step, it makes.

const SETTING_GROUPS = {
  "data-folder": { title: "Data folder", setupOrder: 0 },
  "staging-folder": { title: "Staging folder" },
  "game-version": { title: "Game version", setupOrder: 1, setupSkip: { key: "game_version", value: "" } },
  // (Setup's step 2 is the Game files step: required, not a setting - see setup-wizard.js)
  "app-experience": { title: "App experience", setupOrder: 3, setupLead: "You can change these any time in Settings.", resettable: true },
  "ui-text": { title: "Game language", setupOrder: 4 },
};

// "English (unspecified)": the user doesn't know which English their Switch is set to, so both are built. It is stored as the two things
// merge() reads - ui_setup_locale (USen) and ui_setup_extra_english (true) - and shown as one choice in the list.
const ENGLISH_LOCALES = ["USen", "EUen"];
const ENGLISH_EITHER = "en-either";

const SETTINGS = [
  { key: "data_folder", group: "data-folder", kind: "folder", label: "Data folder", showInSetup: true,
    description: "Choose where the app keeps your downloaded mods and settings. Mods can be large, so pick a place with plenty of free space." },

  { key: "staging_folder", group: "staging-folder", kind: "path", label: "Staging folder", showInSetup: false,
    description: "Where a commit puts the finished files, ready to copy to your Switch. You don't need to change this. If you do, the next commit fills the new folder and the old one is left as it is.",
    status: () => pywebview.api.get_staging_status(),
    choose: (path) => pywebview.api.set_staging_dir(path),
    reset: () => pywebview.api.use_recommended_staging_dir(),
    after: async () => { await refreshFlow(); if (flow.step === "commit") renderCommitPage(); } },

  { key: "game_version", group: "game-version", kind: "select", label: "Which version is your game?", showInSetup: true, refreshGroup: true,
    description: "A few mods (typically only code patches like \"Mechanics\" mods) only work on certain versions of Mario Kart 8 Deluxe. If you know your version, the app will alert you of any known issues before you try copying files onto your Switch. The game version is shown on the title screen on the bottom left.",
    read: () => state.settings.game_version || "",
    options: async () => gameVersionChoices(await pywebview.api.get_game_versions()),
    write: async (value) => { await pywebview.api.set_game_version(value); state.settings = await pywebview.api.get_settings(); },
    after: async () => { flow.status = await pywebview.api.get_flow_status(); renderStepBar(); } },
  { key: "game_build_id", group: "game-version", kind: "text", label: "Game build ID (optional)", showInSetup: false,
    description: "Only needed for code patches (.ips) - it lets the app warn you about patches built for a different game version.",
    placeholder: "32 hex characters (or the first 16), e.g. 6A85262F21B903649BD7C62628D26E43", maxLength: 32,
    read: () => state.settings.game_build_id || "",
    datalist: async () => (await pywebview.api.get_game_versions()).map(v => ({ value: v.build_id, label: "v" + v.version })),
    // Empty (check off), 32 hex characters, or just the first 16 (how the app matches them) - anything else is a typo that would
    // otherwise silently flag every patch as the wrong version.
    normalize: (text) => text.trim().toUpperCase(),
    validate: (value) => value !== "" && !/^([0-9A-F]{16}|[0-9A-F]{32})$/.test(value) ? "A build ID is 32 hex characters (0-9, A-F), or just its first 16." : null },

  { key: "ui_setup_locale", group: "ui-text", kind: "select", label: "Language", showInSetup: true,
    description: "Mods that rename characters or courses change text stored per language, and the game only reads the language your Switch is set to (System Settings → System → Language).\nNot sure which English? Choose English (unspecified) and the menus are built for both.",
    read: () => {
      const locale = state.settings.ui_setup_locale || "USen";
      return state.settings.ui_setup_extra_english && ENGLISH_LOCALES.includes(locale) ? ENGLISH_EITHER : locale;
    },
    options: async () => {
      const list = (await pywebview.api.get_ui_locales()).map(l => ({ value: l.code, label: l.label }));
      list.splice(list.findIndex(l => l.value === "EUen") + 1, 0, { value: ENGLISH_EITHER, label: "English (unspecified)" });
      return list;
    },
    write: async (value) => {
      const either = value === ENGLISH_EITHER;
      state.settings.ui_setup_locale = either ? "USen" : value;
      state.settings.ui_setup_extra_english = either;
      await pywebview.api.save_settings(state.settings);
    },
    after: async () => {
      uiSetup.data = null;
      scheduleFlowRefresh();
      if (!document.getElementById("settings-modal-backdrop").hidden) await renderUiSetupSettingsCard();   // (the card also says what the mods change in it)
    } },

  { key: "show_tile_counts", group: "app-experience", kind: "toggle", label: "Show mod counts on character tiles", description: "", showInSetup: false,
    after: () => renderCharacterGrid() },
  { key: "play_select_voice", group: "app-experience", kind: "toggle", label: "Play character-select sounds", description: "", showInSetup: false,
    after: (value) => { if (!value) voiceStop(); } },
  { key: "show_nsfw", group: "app-experience", kind: "toggle", label: "Show NSFW mods", showInSetup: true,
    description: "When enabled, app will include NSFW-rated mods found in GameBanana queries." },
  { key: "advanced_mode", group: "app-experience", kind: "toggle", label: "Advanced mode", showInSetup: true,
    description: "Shows verbose technical details in a few places. Nothing essential is hidden when disabled.",
    after: () => renderConflicts() },
];
for (const def of SETTINGS) def.read = def.read || (() => settingValue(def));

function settingByKey(key) {
  return SETTINGS.find(s => s.key === key);
}

// The "which version is your game?" choices: "not sure" (no patch checks), "not listed" (game_version "newer": patches made for a listed
// version are flagged as "might not work"), then every version the app knows.
function gameVersionChoices(versions) {
  const out = [];
  const add = (value, text) => out.push({ value, label: text });
  add("", "I'm not sure");
  add("newer", "Not listed (probably newer)");
  for (const v of versions) add(v.version, v.version);   // (just the number: typing "3" or "3.0" in the list jumps straight to it)
  return out;
}

// How each setting starts (the app's own defaults, from mod_manager.DEFAULT_SETTINGS).
let settingDefaults = {};
async function loadSettingDefaults() {
  settingDefaults = await pywebview.api.get_default_settings();
}
function settingValue(def) {
  const saved = state.settings ? state.settings[def.key] : undefined;
  return saved === undefined ? settingDefaults[def.key] : saved;
}

// Saves a new value the one way every setting is saved, then does whatever else that setting needs.
async function changeSetting(def, value) {
  if (def.write) await def.write(value);
  else {
    state.settings[def.key] = value;
    await pywebview.api.save_settings(state.settings);
  }
  if (def.after) await def.after(value);
  if (def.refreshGroup) await refreshSettingHosts(def.group);
  updateResetButtons();
}

// ---- drawing ----
// Every place a group is drawn is remembered, so a change that affects the group (a version that sets the build ID) redraws them all.
const settingHosts = new Map();      // host element -> { group, ctx }
let settingListSeq = 0;

async function renderSettingsGroup(group, host, ctx = {}) {
  if (!Object.keys(settingDefaults).length) await loadSettingDefaults();
  for (const h of [...settingHosts.keys()]) if (!h.isConnected && h !== host) settingHosts.delete(h);
  settingHosts.set(host, { group, ctx });
  const parts = document.createDocumentFragment();
  for (const def of SETTINGS) {
    if (def.group !== group) continue;
    if (ctx.setup && !def.showInSetup) continue;
    if (def.visibleWhen && !def.visibleWhen()) continue;
    parts.appendChild(await buildSettingControl(def, ctx));
  }
  host.replaceChildren(parts);
  updateResetButtons();
}

async function refreshSettingHosts(group) {
  for (const [host, info] of [...settingHosts]) if (info.group === group && host.isConnected) await renderSettingsGroup(group, host, info.ctx);
}

// The groups the Settings window shows itself (the language group is drawn inside the "Game language" card, which fills itself).
async function renderAllSettingsGroups() {
  for (const host of document.querySelectorAll("[data-settings-group]")) await renderSettingsGroup(host.dataset.settingsGroup, host);
}

async function buildSettingControl(def, ctx) {
  const box = cgEl("div", "setting setting-" + def.kind);
  box.dataset.setting = def.key;
  const label = typeof def.label === "function" ? def.label() : def.label;
  if (def.kind === "folder") {
    await fillFolderControl(def, box, ctx);
    return box;
  }
  if (def.kind === "path") {
    await fillPathControl(def, box);
    return box;
  }
  if (def.kind === "toggle") {
    const row = cgEl("label", "settings-checkbox-label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!def.read();
    cb.addEventListener("change", () => changeSetting(def, cb.checked));
    row.append(cb, document.createTextNode(label));
    box.appendChild(row);
  } else if (def.kind === "select") {
    box.appendChild(cgEl("label", "setting-label", label));
    const sel = document.createElement("select");
    sel.className = "settings-text-input";
    for (const o of await def.options()) sel.appendChild(new Option(o.label, o.value));
    sel.value = String(def.read());
    sel.addEventListener("change", () => changeSetting(def, sel.value));
    box.appendChild(sel);
  } else if (def.kind === "text") {
    box.appendChild(cgEl("label", "setting-label", label));
    const input = document.createElement("input");
    input.type = "text";
    input.className = "settings-text-input";
    input.spellcheck = false;
    if (def.maxLength) input.maxLength = def.maxLength;
    if (def.placeholder) input.placeholder = def.placeholder;
    input.value = def.read();
    box.appendChild(input);
    if (def.datalist) {
      const list = document.createElement("datalist");
      list.id = "setting-list-" + (++settingListSeq);
      for (const o of await def.datalist()) list.appendChild(new Option(o.label, o.value));
      input.setAttribute("list", list.id);
      box.appendChild(list);
    }
    const problem = cgEl("div", "setting-hint setting-error");
    problem.hidden = true;
    box.appendChild(problem);
    input.addEventListener("change", async () => {
      const value = def.normalize ? def.normalize(input.value) : input.value.trim();
      const wrong = def.validate ? def.validate(value) : null;
      problem.textContent = wrong || "";
      problem.hidden = !wrong;
      if (wrong) return;
      input.value = value;
      await changeSetting(def, value);
    });
  }
  if (def.description) box.appendChild(cgEl("div", "setting-hint", def.description));
  return box;
}

// Where a folder is: its path, marked Recommended when it is the recommended one (status says is_recommended, or is_default for the data
// folder), and by its own `label` when it has one ("Existing folder").
function folderCard(dir) {
  const recommended = dir.is_recommended !== undefined ? dir.is_recommended : dir.is_default;
  const where = cgEl("div", "wiz-folder" + (recommended ? " is-default" : ""));
  where.appendChild(cgEl("span", "wiz-pill" + (recommended ? " rec" : ""), dir.label || (recommended ? "Recommended" : "Custom folder")));
  where.appendChild(cgEl("code", "wiz-folder-path", dir.path || dir.default_path || "(not set)"));
  return where;
}

// Any other folder setting (a "path"): where it is, a button to choose another, and one to go back to the default. Nothing here knows
// which folder it is - the setting's status(), choose() and reset() do.
async function fillPathControl(def, box) {
  const dir = await def.status();
  box.replaceChildren(folderCard(dir));
  if (def.description) box.appendChild(cgEl("div", "setting-hint", def.description));
  const errorBox = cgEl("div", "wiz-error");
  errorBox.hidden = true;
  box.appendChild(errorBox);
  const done = async (result) => {
    if (!result.success) { errorBox.textContent = result.error; errorBox.hidden = false; return; }
    state.settings = await pywebview.api.get_settings();
    if (def.after) await def.after();
    await fillPathControl(def, box);
  };
  const row = cgEl("div", "uis-actions");
  row.appendChild(button("Change folder...", "small", async () => {
    const chosen = await pywebview.api.pick_folder();
    if (chosen) await done(await def.choose(chosen));
  }));
  if (!dir.is_recommended) row.appendChild(button("Use the recommended folder", "ghost small", async () => done(await def.reset())));
  box.appendChild(row);
}

// The data folder: where it is, and how to change it. Before setup has been finished there is nothing to bring along, so a new folder is
// simply used; afterwards the user is asked whether to bring their mods and settings (renderMasterDirConfirmStep).
async function fillFolderControl(def, box, ctx) {
  const dir = await pywebview.api.get_master_dir_status();
  const firstRun = !(state.settings && state.settings.setup_done);
  box.replaceChildren();
  box.appendChild(folderCard(dir));
  if (def.description) box.appendChild(cgEl("div", "setting-hint", def.description));
  const errorBox = cgEl("div", "wiz-error");
  errorBox.hidden = true;
  box.appendChild(errorBox);
  const failed = (message) => { errorBox.textContent = message; errorBox.hidden = false; };

  // the folder under the app changed: the page's ticks and lists belong to the old one
  const afterChanged = async () => {
    state.epoch = null;
    for (const k of Object.keys(checkedPending)) delete checkedPending[k];
    await loadMods();
    await loadSettings();
    if (ctx.afterFolderChange) ctx.afterFolderChange();
  };
  const change = async () => {
    const chosen = await pywebview.api.pick_master_dir();
    if (!chosen) return;
    if (!firstRun) {
      box.replaceChildren();
      renderMasterDirConfirmStep(box, chosen, afterChanged, () => fillFolderControl(def, box, ctx));
      return;
    }
    const result = await diag.attempt(() => pywebview.api.set_master_dir(chosen, false));
    if (!result.success) { failed(result.error); return; }
    await afterChanged();
  };
  const useRecommended = async () => {
    const result = await diag.attempt(() => pywebview.api.use_default_master_dir());
    if (!result.success) { failed(result.error); return; }
    await afterChanged();
  };
  const row = cgEl("div", "uis-actions");
  row.appendChild(button("Change folder...", "small", change));
  if (!dir.is_default && firstRun) row.appendChild(button("Use the recommended folder", "ghost small", useRecommended));
  box.appendChild(row);
}

// ---- "Reset to default" on a group's header (a card with data-reset-group): only available while something differs ----
function groupDiffersFromDefaults(group) {
  return SETTINGS.some(d => d.group === group && d.kind === "toggle" && !!d.read() !== !!settingDefaults[d.key]);
}
function updateResetButtons() {
  for (const btn of document.querySelectorAll("[data-reset-group]")) btn.disabled = !groupDiffersFromDefaults(btn.dataset.resetGroup);
}
for (const btn of document.querySelectorAll("[data-reset-group]")) {
  btn.addEventListener("click", async () => {
    const group = btn.dataset.resetGroup;
    for (const def of SETTINGS) {
      if (def.group === group && def.kind === "toggle" && !!def.read() !== !!settingDefaults[def.key]) await changeSetting(def, !!settingDefaults[def.key]);
    }
    await refreshSettingHosts(group);
  });
}
