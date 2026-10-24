// ---- Step 1: Setup wizard ----
// The first-run wizard: the data folder (the app's default is recommended), game version, game files, options and language.
// Also reachable later from the step bar.
const setupCardOriginal = { h1: null, p: null };

// The "which version is your game?" choices, shared by this wizard and Settings: "not sure" (no patch checks), "not listed"
// (game_version "newer": patches made for a listed version are flagged as "might not work"), then every version the app knows.
function fillGameVersionOptions(sel, versions) {
  sel.replaceChildren();
  const add = (value, text) => {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = text;
    sel.appendChild(o);
  };
  add("", "I'm not sure");
  add("newer", "Not listed (probably newer)");
  for (const v of versions) add(v.version, v.version);   // (just the number: typing "3" or "3.0" in the list jumps straight to it)
}

// `lead` is plain text, or a list of elements (shown in the same place, above the progress dots) for a page that needs more
// than a paragraph. `wide` gives the page a roomier card.
function wizardFrame(index, title, lead, wide) {
  const card = document.getElementById("setup-card");
  card.querySelector("h1").textContent = title;
  const p = card.querySelector("p");
  const rich = Array.isArray(lead);
  p.hidden = rich;
  p.textContent = rich ? "" : lead;
  card.classList.toggle("wide", !!wide);
  const body = document.getElementById("setup-overlay-body");
  body.replaceChildren();
  if (rich) body.appendChild(wizEl("div", "wiz-lead", ...lead));
  const dots = cgEl("div", "wiz-dots");
  for (let i = 0; i < 6; i++) dots.appendChild(cgEl("span", i <= index ? "on" : ""));
  body.appendChild(dots);
  return body;
}

function closeSetupWizard() {
  const card = document.getElementById("setup-card");
  if (setupCardOriginal.h1 !== null) {
    card.querySelector("h1").textContent = setupCardOriginal.h1;
    card.querySelector("p").textContent = setupCardOriginal.p;
  }
  card.querySelector("p").hidden = false;
  card.classList.remove("wide");
  document.getElementById("setup-overlay").hidden = true;
}

async function openSetupWizard(index, rerun) {
  const card = document.getElementById("setup-card");
  if (setupCardOriginal.h1 === null) {
    setupCardOriginal.h1 = card.querySelector("h1").textContent;
    setupCardOriginal.p = card.querySelector("p").textContent;
  }
  document.getElementById("setup-overlay").hidden = false;
  if (!state.settings || state.settings.game_version === undefined) state.settings = await pywebview.api.get_settings();
  const nav = (body, back, nextLabel, onNext, skip) => {
    const row = cgEl("div", "uis-actions");
    if (back) row.appendChild(button("Back", "ghost", back));
    else if (rerun) row.appendChild(button("Close", "ghost", closeSetupWizard));
    if (skip) row.appendChild(button("Skip", "ghost", skip));
    row.appendChild(button(nextLabel, "primary", onNext));
    body.appendChild(row);
  };

  if (index === 0) {
    // The folder the app keeps its data in. The app already has a good default (a "data" folder next to itself), so this step says so
    // plainly and the usual answer is just Next; the user can still pick any folder.
    const dir = await pywebview.api.get_master_dir_status();
    const body = wizardFrame(0, "Data folder",
      "Choose where the app keeps your downloaded mods and settings. Mods can be large, so pick a place with plenty of free space.");
    const card = cgEl("div", "wiz-folder" + (dir.is_default ? " is-default" : ""));
    card.appendChild(cgEl("span", "wiz-pill" + (dir.is_default ? " rec" : ""), dir.is_default ? "Recommended" : "Custom folder"));
    card.appendChild(cgEl("code", "wiz-folder-path", dir.path || dir.default_path));
    body.appendChild(card);
    body.appendChild(cgEl("div", "wiz-hint", dir.is_default
      ? "The app picked this folder for you: a folder called \"data\" next to the app. It's a good choice for most people, so you can just click Next. Choose a different folder only if you'd like your mods stored somewhere else, such as another drive."
      : "You chose a different folder. The recommended one is a folder called \"data\" next to the app."));
    const errorBox = cgEl("div", "wiz-error");
    errorBox.hidden = true;
    body.appendChild(errorBox);

    // the folder under the app changed: the page's ticks and lists belong to the old one
    const afterRootChanged = async () => {
      state.epoch = null;
      for (const k of Object.keys(checkedPending)) delete checkedPending[k];
      await loadMods();
      await loadSettings();
      openSetupWizard(0, rerun);
    };
    const failed = (message) => { errorBox.textContent = message; errorBox.hidden = false; };
    const change = async () => {
      const chosen = await pywebview.api.pick_master_dir();
      if (!chosen) return;
      if (rerun) {   // there may be mods in the folder it is leaving: ask whether to bring them along
        body.replaceChildren();
        renderMasterDirConfirmStep(body, chosen, afterRootChanged, () => openSetupWizard(0, rerun));
        return;
      }
      const result = await diag.attempt(() => pywebview.api.set_master_dir(chosen, false));
      if (!result.success) { failed(result.error); return; }
      await afterRootChanged();
    };
    const useRecommended = async () => {
      const result = await diag.attempt(() => pywebview.api.use_default_master_dir());
      if (!result.success) { failed(result.error); return; }
      await afterRootChanged();
    };
    const row = cgEl("div", "uis-actions");
    if (rerun) row.appendChild(button("Close", "ghost", closeSetupWizard));
    row.appendChild(button("Change folder...", "ghost", change));
    if (!dir.is_default && !rerun) row.appendChild(button("Use the recommended folder", "ghost", useRecommended));
    row.appendChild(button("Next", "primary", () => openSetupWizard(1, rerun)));
    body.appendChild(row);
  } else if (index === 1) {
    const body = wizardFrame(1, "Game version",
      "A few mods (typically only code patches like \"Mechanics\" mods) only work on certain versions of Mario Kart 8 Deluxe. If you know your version, the app will alert you of any known issues before you try copying files onto your Switch."); 
    const versions = await pywebview.api.get_game_versions();
    const f = cgEl("div", "wiz-field");
    f.appendChild(cgEl("label", "t", "Which version is your game?"));
    const sel = document.createElement("select");
    fillGameVersionOptions(sel, versions);
    sel.value = state.settings.game_version || "";
    f.appendChild(sel);
    f.appendChild(cgEl("div", "wiz-hint", "The game version is shown on the title screen on the bottom left."));
    body.appendChild(f);
    const saveVersion = async (value) => {
      await pywebview.api.set_game_version(value);
      state.settings = await pywebview.api.get_settings();
      openSetupWizard(2, rerun);
    };
    // Skip = "I'm not sure" (no version checks), whatever the dropdown says.
    nav(body, () => openSetupWizard(0, rerun), "Next", () => saveVersion(sel.value), () => saveVersion(""));
  } else if (index === 2) {
    const body = wizardFrame(2, "Game files", [
      wizEl("p", null, wizEl("strong", null, "This is a required step."), document.createElement("br"),
        "This tool will not work properly unless it first has a copy of a few Mario Kart 8 Deluxe game files. These files include:"),
      wizEl("ul", null,
        wizEl("li", null, "Character Icons"),
        wizEl("li", null, "Character voice-lines"),
        wizEl("li", null, "Character and course names (the game's menu text, in every language)"),
        wizEl("li", null, "Course pictures"),
        wizEl("li", null, "Vehicle part and item pictures")),
      wizEl("p", null, "The app needs these files to work properly. Including these files make it incredibly easy to modify things like character names, icons, voice lines."),
    ], true);
    body.appendChild(gameDataInstructions());
    const block = cgEl("div");
    body.appendChild(block);
    const row = cgEl("div", "uis-actions");
    row.appendChild(button("Back", "ghost", () => openSetupWizard(1, rerun)));
    const nextBtn = button("Next", "primary", () => openSetupWizard(3, rerun));
    row.appendChild(nextBtn);
    body.appendChild(row);
    const refresh = async () => { nextBtn.disabled = !(await pywebview.api.get_base_files_status()).done; };
    await renderGameFilesBlock(block, refresh);
    await refresh();
  } else if (index === 3) {
    const body = wizardFrame(3, "Options", "You can change these any time in Settings.");
    const mk = (id, label, hint, checked) => {
      const f = cgEl("div", "wiz-field");
      const l = cgEl("label", "settings-checkbox-label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = id;
      cb.checked = checked;
      l.appendChild(cb);
      l.appendChild(document.createTextNode(" " + label));
      f.appendChild(l);
      f.appendChild(cgEl("div", "wiz-hint", hint));
      body.appendChild(f);
      return cb;
    };
    const nsfw = mk("wiz-nsfw", "Show adult (NSFW) mods when browsing GameBanana", "Off by default. When enabled, app will include NSFW-rated mods found in GameBanana queries.", !!state.settings.show_nsfw);
    const adv = mk("wiz-adv", "Advanced mode", "Shows verbose technical details in a few places. Nothing essential is hidden when disabled", !!state.settings.advanced_mode);
    nav(body, () => openSetupWizard(2, rerun), "Next", async () => {
      state.settings.show_nsfw = nsfw.checked;
      state.settings.advanced_mode = adv.checked;
      await pywebview.api.save_settings(state.settings);
      openSetupWizard(4, rerun);
    });
  } else if (index === 4) {
    const body = wizardFrame(4, "Your Switch's language",
      "Mods that rename characters or courses change text stored per language, and the game only reads the language your Switch is set to (System Settings → System → Language).");
    const locales = await pywebview.api.get_ui_locales();
    const f = cgEl("div", "wiz-field");
    f.appendChild(cgEl("label", "t", "Language"));
    const sel = document.createElement("select");
    for (const l of locales) {
      const o = document.createElement("option");
      o.value = l.code;
      o.textContent = l.label;
      sel.appendChild(o);
    }
    sel.value = state.settings.ui_setup_locale || "USen";
    f.appendChild(sel);
    body.appendChild(f);
    nav(body, () => openSetupWizard(3, rerun), "Next", async () => {
      state.settings.ui_setup_locale = sel.value;
      await pywebview.api.save_settings(state.settings);
      openSetupWizard(5, rerun);
    });
  } else {
    const body = wizardFrame(5, "You're all set", "App config complete. Next up, you'll browse and select the mods you want to install.");
    nav(body, () => openSetupWizard(4, rerun), "Start choosing mods", async () => {
      const done = await diag.attempt(() => pywebview.api.complete_setup());
      if (done && done.success === false) { diag.banner("setup", "Setup couldn't be finished. " + done.error); return; }
      closeSetupWizard();
      await loadSettings();
      await loadMods();
      goStep("mods");
      refreshFlow();
    });
  }
}


