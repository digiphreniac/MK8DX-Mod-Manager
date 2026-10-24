async function startApp() {
  pywebview.api.get_app_version().then(v => { document.getElementById("app-version").textContent = "v" + v; }).catch(() => {});
  const dirStatus = await pywebview.api.get_master_dir_status();
  if (!dirStatus.configured) {
    document.getElementById("setup-overlay").hidden = false;
    return;
  }
  // (not waited for: the flow status below is asked at the same time - but a failure must not go unseen)
  loadMods().catch(e => diag.banner("load-mods", "The mods couldn't be loaded. " + diag.describe(e), loadMods));
  loadSettings().catch(e => diag.banner("load-settings", "Your settings couldn't be loaded. " + diag.describe(e), loadSettings));
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
}

window.addEventListener("pywebviewready", () => {
  startApp().catch(e => diag.banner("startup", "The app couldn't finish starting. " + diag.describe(e), startApp));
});
