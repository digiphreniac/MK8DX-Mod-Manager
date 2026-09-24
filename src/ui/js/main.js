window.addEventListener("pywebviewready", async () => {
  const dirStatus = await pywebview.api.get_master_dir_status();
  if (!dirStatus.configured) {
    document.getElementById("setup-overlay").hidden = false;
    return;
  }
  loadMods();
  loadSettings();
  // A folder being configured isn't the same as setup being DONE - the wizard only opens itself
  // right after picking a folder for the first time (runMasterDirSetup()); if the app was closed
  // or reloaded before finishing it (required, no skip), that moment is gone, so check here too on
  // every launch instead of silently treating "a folder is set" as "setup is done".
  flow.status = await pywebview.api.get_flow_status();
  if (!flow.status.setup.done) openSetupWizard(0, false);
  renderStepBar();
  renderNextButton();
  // read the menu files quietly in the background so Menu look cards open instantly
  setTimeout(() => { pywebview.api.warm_ui_analysis().catch(() => {}); }, 2500);
});

