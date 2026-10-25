// ---- Step 1: Setup wizard ----
// The first-run wizard: one step for each settings group that has a `showInSetup` setting (the data folder, game version, options and
// language - see settings-registry.js, which draws them exactly as Settings does), plus the required Game files step and a closing page.
// Also reachable later from the step bar.
const setupCardOriginal = { h1: null, p: null };

// The steps, in order: a group of settings per step, the Game files step (a required copy, not a setting) between the game version and the
// options, and the closing page.
function setupSteps() {
  const steps = [];
  for (const [id, group] of Object.entries(SETTING_GROUPS)) {
    if (SETTINGS.some(s => s.group === id && s.showInSetup)) steps.push({ id, group: id, order: group.setupOrder });
  }
  steps.push({ id: "game-files", order: 2 }, { id: "done", order: 99 });
  return steps.sort((a, b) => a.order - b.order);
}

// `lead` is plain text, or a list of elements (shown in the same place, above the progress dots) for a page that needs more
// than a paragraph. `wide` gives the page a roomier card.
function wizardFrame(index, title, lead, wide) {
  document.getElementById("setup-import")?.remove();        // (only the closing page has it)
  const card = document.getElementById("setup-card");
  card.querySelector("h1").textContent = title;
  const p = card.querySelector("p");
  const rich = Array.isArray(lead);
  p.hidden = rich || !lead;
  p.textContent = rich ? "" : (lead || "");
  card.classList.toggle("wide", !!wide);
  const body = document.getElementById("setup-overlay-body");
  body.replaceChildren();
  if (rich) body.appendChild(ui.el("div", "wiz-lead", ...lead));
  const dots = ui.el("div", "wiz-dots");
  const count = setupSteps().length;
  for (let i = 0; i < count; i++) dots.appendChild(ui.el("span", i <= index ? "on" : ""));
  body.appendChild(dots);
  return body;
}

function closeSetupWizard() {
  document.getElementById("setup-import")?.remove();
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
  if (!state.settings || !Object.keys(state.settings).length) state.settings = await pywebview.api.get_settings();
  const nav = (body, back, nextLabel, onNext, skip) => {
    const row = ui.el("div", "uis-actions");
    if (back) row.appendChild(button("Back", "ghost", back));
    else if (rerun) row.appendChild(button("Close", "ghost", closeSetupWizard));
    if (skip) row.appendChild(button("Skip", "ghost", skip));
    row.appendChild(button(nextLabel, "primary", onNext));
    body.appendChild(row);
  };
  const steps = setupSteps();
  const step = steps[index];
  const go = (i) => () => openSetupWizard(i, rerun);

  if (step.group) {
    // A group of settings, drawn by the same code as the Settings window: same names, descriptions and controls, saved as they change.
    const group = SETTING_GROUPS[step.group];
    const body = wizardFrame(index, group.setupTitle || group.title, group.setupLead || "");
    const host = ui.el("div");
    body.appendChild(host);
    await renderSettingsGroup(step.group, host, { setup: true, afterFolderChange: go(index) });
    // Skip = the setting's "don't know" answer (for the game version: "I'm not sure", no version checks), whatever the list says.
    const skip = group.setupSkip && (async () => { await changeSetting(settingByKey(group.setupSkip.key), group.setupSkip.value); go(index + 1)(); });
    nav(body, index > 0 ? go(index - 1) : null, "Next", go(index + 1), skip);
  } else if (step.id === "game-files") {
    const body = wizardFrame(index, "Game files", [
      ui.el("p", null, ui.el("strong", null, "This is a required step."), document.createElement("br"),
        "This tool will not work properly unless it first has a copy of a few Mario Kart 8 Deluxe game files. These files include:"),
      ui.el("ul", null,
        ui.el("li", null, "Character Icons"),
        ui.el("li", null, "Character voice-lines"),
        ui.el("li", null, "Character and course names (the game's menu text, in every language)"),
        ui.el("li", null, "Course pictures"),
        ui.el("li", null, "Vehicle part and item pictures")),
      ui.el("p", null, "The app needs these files to work properly. Including these files make it incredibly easy to modify things like character names, icons, voice lines."),
    ], true);
    body.appendChild(gameDataInstructions());
    const block = ui.el("div");
    body.appendChild(block);
    const row = ui.el("div", "uis-actions");
    row.appendChild(button("Back", "ghost", go(index - 1)));
    const nextBtn = button("Next", "primary", go(index + 1));
    row.appendChild(nextBtn);
    body.appendChild(row);
    const refresh = async () => { nextBtn.disabled = !(await pywebview.api.get_base_files_status()).done; };
    await renderGameFilesBlock(block, refresh);
    await refresh();
  } else {
    const body = wizardFrame(index, "You're all set", "App config complete. Next up, you'll browse and select the mods you want to install.");
    nav(body, go(index - 1), "Start choosing mods", async () => {
      const done = await diag.attempt(() => pywebview.api.complete_setup());
      if (done && done.success === false) { diag.banner("setup", "Setup couldn't be finished. " + done.error); return; }
      closeSetupWizard();
      await loadSettings();
      await loadMods();
      goStep("mods");
      refreshFlow();
    });
    // Most people won't have a list: just a small link at the bottom of the screen, under the card, that opens a short explanation and the Import button (mod-list.js).
    const explain = ui.el("div", { class: "wiz-import-more", hidden: true },
      ui.el("p", { text: "A mod list is a small file someone saves from Settings to share the mods they use. Importing one downloads those mods from GameBanana and selects them for you. Skip this if you don't have one." }),
      ui.button({ id: "btn-setup-import-mod-list", label: "Choose a mod list…", size: "small", onClick: () => openImportModList() }).el);
    const link = ui.el("button", { class: "wiz-import-link", text: "Import mod list", attrs: { type: "button", "aria-expanded": "false" } });
    link.addEventListener("click", () => {
      explain.hidden = !explain.hidden;
      link.setAttribute("aria-expanded", String(!explain.hidden));
    });
    document.getElementById("setup-overlay").appendChild(ui.el("div", { id: "setup-import" }, explain, link));       // (under the card, at the bottom of the screen)
  }
}
