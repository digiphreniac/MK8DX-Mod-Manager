// ===== Sharing the list of mods (Settings → "Share your mod list"; docs/mod-list.md) =====
// Export saves the selected GameBanana mods to one file. Import reads such a file, then the page asks the backend for ONE mod at a time
// (import_mod_list_item), so it can show where it is, stop between mods, and say at the end what could not be installed. Import only ever
// adds mods and selections; nothing already selected is changed. Once every mod is in, the names in the list are given and marked approved,
// and so are icons the sharer approved as the mods ship them (import_mod_list_looks). Closing the window then goes to Choose mods.

const MOD_LIST_NOT_INCLUDED = "Custom icons, voices and your notes are not included.";

async function exportModList() {
  const result = await pywebview.api.export_mod_list();
  if (result.cancelled) return;
  if (!result.success) {
    await ui.alert({ title: "Couldn't export the list", message: result.error || "Something went wrong." });
    return;
  }
  const skipped = result.not_shared.length;
  await ui.alert({
    title: "Mod list saved",
    message: `${result.mods} mod${result.mods === 1 ? "" : "s"} saved to\n${result.path}\n\n` +
      (skipped ? `${skipped} selected mod${skipped === 1 ? " was" : "s were"} added by hand rather than downloaded through the app, so ${skipped === 1 ? "it isn't" : "they aren't"} in the file.\n\n` : "") +
      MOD_LIST_NOT_INCLUDED,
  });
}

async function openImportModList() {
  const read = await pywebview.api.read_mod_list();
  if (read.cancelled) return;
  if (!read.success) {
    await ui.alert({ title: "Couldn't read that file", message: read.error || "Something went wrong." });
    return;
  }
  const mods = read.mods;
  if (!mods.length) {
    await ui.alert({ title: "Nothing to import", message: "That list has no mods that can be installed." });
    return;
  }

  const toGet = mods.length - read.already;
  const summary = ui.el("p", {
    class: "ui-confirm-message",
    text: `This list has ${mods.length} mod${mods.length === 1 ? "" : "s"}` +
      (read.already ? ` (${read.already} already here)` : "") +
      `. ${toGet ? `${toGet} will be downloaded from GameBanana, which can take a few minutes. ` : ""}They are then selected for you, ` +
      "with the names they have in the list and the icons the other person approved; nothing you have selected is changed.",
  });
  const note = ui.hint(MOD_LIST_NOT_INCLUDED + " Mods the other person added by hand aren't in the list.", { class: "mod-list-note" });
  const progress = ui.progress({ title: "Adding mods...", startText: "Starting...", units: { mods: "mods" } });
  progress.el.hidden = true;
  const current = ui.el("div", { class: "settings-hint", hidden: true });
  const report = ui.el("div", { class: "mod-list-report", hidden: true });

  let running = false, stop = false, ran = false;
  const modal = ui.modal({
    id: "import-mod-list-modal", title: "Import a mod list", size: "narrow", destroyOnClose: true,
    body: [summary, note, progress.el, current, report],
    beforeClose: () => !running,
    onClose: () => { if (ran) showImportedMods(); },
    actions: [
      { label: "Cancel", variant: "ghost", size: "small", onClick: () => {
        if (!running) { modal.close(); return; }
        stop = true;
        modal.actions[0].setLabel("Stopping after this mod...");
        modal.actions[0].setDisabled(true);
      } },
      { label: "Import", variant: "primary", size: "small", onClick: () => run() },
    ],
  });
  modal.open();

  async function run() {
    const [cancel, go] = modal.actions;
    running = true;
    ran = true;
    go.el.hidden = true;
    cancel.setLabel("Stop");
    progress.el.hidden = false;
    current.hidden = false;
    const started = Date.now();
    const added = [], failed = [], partly = [];
    let done = 0;
    for (const m of mods) {
      if (stop) break;
      progress.update({ active: true, phases: [{ id: "mods", label: "Adding mods" }], phase: "mods", done, total: mods.length, elapsed: (Date.now() - started) / 1000 });
      current.textContent = `${m.name} (${m.item})`;
      let r;
      try { r = await pywebview.api.import_mod_list_item(m); }
      catch (e) { r = { success: false, name: m.name, error: e && e.message ? e.message : String(e) }; }
      done++;
      if (!r.success) failed.push(`${r.name || m.name}: ${r.error || (r.missing || []).join("; ")}`);
      else {
        added.push(r);
        if (r.missing && r.missing.length) partly.push(`${r.name || m.name}: ${r.missing.join("; ")}`);
      }
    }
    progress.update({ active: true, phases: [{ id: "mods", label: "Adding mods" }], phase: "mods", done, total: mods.length, elapsed: (Date.now() - started) / 1000 });
    current.hidden = true;
    if (added.length) {
      try { await pywebview.api.import_mod_list_looks(mods, read.looks || []); }
      catch (e) { /* (the mods are in; their names and icons are just left for the user to approve) */ }
    }
    try { await loadMods(); await refreshFlow(); } catch (e) { /* (the page redraws on the next look; the mods are already added) */ }
    running = false;
    cancel.setDisabled(false);
    cancel.setLabel("Close");

    const left = mods.length - done;
    report.hidden = false;
    report.replaceChildren(
      ui.el("div", { class: "ui-result " + (failed.length || partly.length ? "err" : "ok"),
        text: `Added ${added.length} of ${mods.length} mod${mods.length === 1 ? "" : "s"}` + (left ? ` (stopped; ${left} not tried)` : "") +
          (failed.length || partly.length ? ". Some could not be fully installed:" : ".") }),
      ...[...failed, ...partly, ...read.unusable.map(u => `${u.name}: ${u.reason}`)].map(line => ui.el("div", { class: "settings-hint", text: "• " + line })),
    );
  }
}

// After an import the user looks over what came in, on Choose mods - whether it was started from Settings or from Setup's closing page
// (where it finishes Setup, as that page's "Start choosing mods" button does).
async function showImportedMods() {
  if (!document.getElementById("setup-overlay").hidden) {
    const done = await diag.attempt(() => pywebview.api.complete_setup());
    if (done && done.success === false) { diag.banner("setup", "Setup couldn't be finished. " + done.error); return; }
    closeSetupWizard();
    await loadSettings();
  }
  if (settingsModal.isOpen) closeSettingsModal();
  await goStep("mods", { skipGate: true });
  refreshFlow();
}
