// ---- Step 1: Setup wizard ----
// The first-run overlay chooses the folder (existing flow), then walks through
// game version, options and language. Also reachable later from the step bar.
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
  for (const v of versions) add(v.version, "Version " + v.version);
}

function wizardFrame(index, title, lead, onBack) {
  const card = document.getElementById("setup-card");
  card.querySelector("h1").textContent = title;
  card.querySelector("p").textContent = lead;
  const body = document.getElementById("setup-overlay-body");
  body.replaceChildren();
  const dots = cgEl("div", "wiz-dots");
  for (let i = 0; i < 5; i++) dots.appendChild(cgEl("span", i <= index ? "on" : ""));
  body.appendChild(dots);
  return body;
}

function closeSetupWizard() {
  const card = document.getElementById("setup-card");
  if (setupCardOriginal.h1 !== null) {
    card.querySelector("h1").textContent = setupCardOriginal.h1;
    card.querySelector("p").textContent = setupCardOriginal.p;
  }
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
  const nav = (body, back, nextLabel, onNext) => {
    const row = cgEl("div", "uis-actions");
    if (back) row.appendChild(button("Back", "ghost", back));
    else if (rerun) row.appendChild(button("Close", "ghost", closeSetupWizard));
    row.appendChild(button(nextLabel, "primary", onNext));
    body.appendChild(row);
  };

  if (index === 0) {
    const body = wizardFrame(0, "Your game version",
      "Some mods (code patches, like most Mechanics mods) only work on the exact version of Mario Kart 8 Deluxe they were made for. Telling the app your version lets it warn you before you copy a mod that won't do anything.");
    const versions = await pywebview.api.get_game_versions();
    const f = cgEl("div", "wiz-field");
    f.appendChild(cgEl("label", "t", "Which version is your game?"));
    const sel = document.createElement("select");
    fillGameVersionOptions(sel, versions);
    sel.value = state.settings.game_version || "";
    f.appendChild(sel);
    f.appendChild(cgEl("div", "wiz-hint", "To find it on your Switch: highlight the game on the Home screen, press +, and look at the top of the page (\"Ver. 3.0.3\"). Not listed here? Choose \"Not listed (probably newer)\" and the app will warn you about code patches made for older versions. Or choose \"I'm not sure\" to skip those checks. You can enter an exact build ID in Settings later."));
    body.appendChild(f);
    nav(body, null, "Next", async () => {
      await pywebview.api.set_game_version(sel.value);
      state.settings = await pywebview.api.get_settings();
      openSetupWizard(1, rerun);
    });
  } else if (index === 1) {
    const body = wizardFrame(1, "Your game's files",
      "This works best done once, from your own copy of the game: menu icons and text, and every character's own default voice, all built from the same files - no mod has to include them, and no character needs its own voice mod ticked just to mute or replace a line. Nothing here is uploaded anywhere.");
    const block = cgEl("div");
    body.appendChild(block);
    const row = cgEl("div", "uis-actions");
    row.appendChild(button("Back", "ghost", () => openSetupWizard(0, rerun)));
    const nextBtn = button("Next", "primary", () => openSetupWizard(2, rerun));
    row.appendChild(nextBtn);
    body.appendChild(row);
    const refresh = async () => { nextBtn.disabled = !(await pywebview.api.get_base_files_status()).done; };
    await renderGameFilesBlock(block, refresh, true);
    await refresh();
  } else if (index === 2) {
    const body = wizardFrame(2, "Options", "You can change these any time in Settings.");
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
    const nsfw = mk("wiz-nsfw", "Show adult (NSFW) mods when browsing GameBanana", "Off by default. Mods GameBanana rates as mature are hidden from search results.", !!state.settings.show_nsfw);
    const adv = mk("wiz-adv", "Advanced mode", "Shows extra technical detail in a few places (for example, the full list of files in a conflict is open by default). Nothing essential is hidden without it.", !!state.settings.advanced_mode);
    nav(body, () => openSetupWizard(1, rerun), "Next", async () => {
      state.settings.show_nsfw = nsfw.checked;
      state.settings.advanced_mode = adv.checked;
      await pywebview.api.save_settings(state.settings);
      openSetupWizard(3, rerun);
    });
  } else if (index === 3) {
    const body = wizardFrame(3, "Your Switch's language",
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
    nav(body, () => openSetupWizard(2, rerun), "Next", async () => {
      state.settings.ui_setup_locale = sel.value;
      await pywebview.api.save_settings(state.settings);
      openSetupWizard(4, rerun);
    });
  } else {
    const body = wizardFrame(4, "You're all set", "Next you'll choose your mods - characters, courses and vehicles. When you've ticked the ones you want, the Next button in the corner takes you through the rest.");
    nav(body, () => openSetupWizard(3, rerun), "Start choosing mods", async () => {
      await pywebview.api.complete_setup();
      closeSetupWizard();
      await loadSettings();
      await loadMods();
      goStep("mods");
      refreshFlow();
    });
  }
}


