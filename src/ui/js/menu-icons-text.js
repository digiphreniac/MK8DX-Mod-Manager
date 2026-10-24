// ===== Menu icons & text =====
// Reviewing and combining the packed UI archives (common.sarc, menu.sarc, message.sarc) that a
// commit can't merge straight in - the actual build runs automatically inside merge() (see
// mod_manager.py); this is the Commit page's review card, the Settings card (Open the folder /
// Undo / manual rebuild / advanced-by-hand), and the guessed-names modal.
// `lastBuild` is only for the Settings card's own manual "Rebuild now" (a normal commit doesn't
// go through here - its result lines already say what got built).
const uiSetup = { data: null, lastBuild: null, guessed: [] };
const UI_KIND_LABEL = { Chara: "select-screen icon", edChara: "results-screen icon", MapChara: "map icon", Part: "parts-menu picture" };

function uisEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// "Names we guessed": one row per guess - the name in an editable box, Confirm (or Save name if it was
// edited), and "Use the game's name". Confirming settles only the name; the icons are checked on the
// character's card. Opened from the Commit page's "names were guessed" warning.
async function openGuessedNamesModal() {
  uiSetup.guessed = await pywebview.api.get_guessed_names();
  if (!uiSetup.guessed.length) return;   // the warning that opened this was already stale
  document.getElementById("guessed-names-modal-backdrop").hidden = false;
  drawGuessedNamesModal();
}
function closeGuessedNamesModal() {
  document.getElementById("guessed-names-modal-backdrop").hidden = true;
}
document.getElementById("btn-guessed-names-modal-close").addEventListener("click", closeGuessedNamesModal);
document.getElementById("guessed-names-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "guessed-names-modal-backdrop") closeGuessedNamesModal();
});

function drawGuessedNamesModal() {
  const body = document.getElementById("guessed-names-modal-body");
  body.replaceChildren();
  const list = uiSetup.guessed;
  if (!list.length) { closeGuessedNamesModal(); return; }
  body.appendChild(uisEl("p", "uis-p", "These names were worked out from your mods' names, because the mods don't say what their character should be called. A wrong guess would end up in the game's menus, so confirm each one or change it."));

  const rows = [];
  async function settle(r, action) {
    const typed = r.input.value.trim();
    const useGame = action === "game" || typed === "";   // an emptied box means "keep the game's name"
    const edited = !useGame && typed !== r.g.name;
    if (useGame) {
      await pywebview.api.clear_item_name(r.g.item, "characters", false);
    } else if (edited) {
      const res = await pywebview.api.set_item_name(r.g.item, "characters", typed, false);
      if (!res.success) { r.err.textContent = res.error; return false; }
    } else {
      await pywebview.api.confirm_guessed_name(r.g.item);
    }
    return useGame || edited;   // true when what will be built changed
  }
  async function finish(changedBuild) {
    uiSetup.guessed = await pywebview.api.get_guessed_names();
    renderCharacterGrid();
    if (changedBuild) uiSetup.data = null;   // Settings' "UI icons & text" card must re-read next time it's opened
    drawGuessedNamesModal();
    refreshFlow();
    if (flow.step === "commit") renderCommitPage();
  }

  for (const g of list) {
    const row = uisEl("div", "gn-row");
    const r = { g, row };
    row.appendChild(uisEl("span", "gn-game", g.item));
    r.input = document.createElement("input");
    r.input.type = "text";
    r.input.maxLength = 40;
    r.input.value = g.name;
    r.input.setAttribute("aria-label", "Name for " + g.item);
    r.ok = button("Confirm", "primary small", async () => { await finish(await settle(r, "confirm")); });
    r.input.addEventListener("input", () => { r.ok.textContent = r.input.value.trim() !== g.name && r.input.value.trim() !== "" ? "Save name" : "Confirm"; });
    row.appendChild(r.input);
    row.appendChild(r.ok);
    row.appendChild(button("Use the game's name", "ghost small", async () => { await finish(await settle(r, "game")); }));
    r.err = uisEl("span", "gb-mod-error");
    row.appendChild(r.err);
    row.appendChild(uisEl("div", "gn-hint", `Guessed from ${g.source}${g.mod && g.source.indexOf(g.mod) < 0 ? ": " + g.mod : ""}.`));
    body.appendChild(row);
    rows.push(r);
  }
  if (list.length > 1) {
    const all = uisEl("div", "uis-actions");
    all.appendChild(button("Confirm all as shown", "ghost small", async () => {
      let changedBuild = false;
      for (const r of rows) if (await settle(r, "confirm")) changedBuild = true;
      await finish(changedBuild);
    }));
    body.appendChild(all);
  }
}

function uisArchiveTitle(a) {
  if (a.id === "common") return ["Map & results icons", "common.sarc"];
  if (a.id === "menu") return ["Character-select icons", "menu.sarc"];
  return [`Names & menu text - ${uiSetup.data.locale_label}`, "message.sarc"];
}

function uisBuiltState(a) {
  const v = a.verify;
  if (a.nothing) return { kind: "ok", text: "nothing to change - the game's own file is used" };
  if (!v.exists) return { kind: "todo", text: "not built yet" };
  if (v.problems && v.problems.length) return { kind: "warn", text: "there's a problem with this file" };
  if (v.total === 0) return { kind: "ok", text: "built" };
  if (v.ok === v.total) return { kind: "ok", text: `built - all ${v.total} changes in place` };
  return { kind: "warn", text: `built, but only ${v.ok} of ${v.total} changes are in it - rebuild` };
}

// The (rare) case of two different ticked mods changing the exact same icon or name entry to
// different values - _winners() (ui_setup.py) already has a sane default (the first mod,
// alphabetically), so this is an optional override, never something that blocks a commit. Only
// the pick-which-one-wins control is rendered; everything this function used to also show (a
// preview of every mod's icon/text changes) is redundant with what the character/course card's own
// Menu look already shows, and that's a better place to see it - reviewed right where you're
// already looking at that character, not a second time here.
function renderUiArchiveConflicts(a) {
  if (!a.conflicts.length) return null;
  const wrap = uisEl("div", "uis-archive");
  const [title] = uisArchiveTitle(a);
  wrap.appendChild(uisEl("div", "uis-archive-title", title));
  for (const c of a.conflicts) {
    const box = uisEl("div", "uis-conflict");
    box.appendChild(uisEl("div", null, `Two mods both change “${c.what}”. Which one do you want?`));
    for (const opt of c.options) {
      const lab = document.createElement("label");
      const r = document.createElement("input");
      r.type = "radio";
      r.name = "uis-conflict-" + a.id + "-" + c.item;
      r.checked = opt.id === c.chosen;
      r.addEventListener("change", async () => {
        state.settings.ui_setup_choices = { ...(state.settings.ui_setup_choices || {}), [c.item]: opt.id };
        await pywebview.api.save_settings(state.settings);
        uiSetup.data = null;
        refreshFlow();
        await renderUiSetupSettingsCard();
      });
      lab.appendChild(r);
      lab.appendChild(document.createTextNode(" " + opt.labels.join(" / ")));
      box.appendChild(lab);
    }
    wrap.appendChild(box);
  }
  return wrap;
}

// ---- The user's own game files: the base every menu icon/name is built on ----
// Icons and names live in the game's shared menu files; the app can't ship those
// (they're Nintendo's), so the user points it once at files extracted from their
// own copy of the game.
// Copies the app's local base-game-files folder from a user-chosen folder (game_files.py does the actual copying,
// on the Python side) - used by both the required Setup step and Settings' "Update from a new dump".
async function chooseGameFiles(after) {
  const r = await pywebview.api.pick_base_files_source();
  if (r.cancelled) return null;
  if (!r.success) { alert(r.error); return null; }
  resetPictureCaches();   // (a new copy of the game's files: its pictures may differ)
  invalidateMenuLook();
  if (after) after(r.status);
  return r.status;
}

// Same as chooseGameFiles, but for a path typed/pasted in directly instead of picked with the
// native folder dialog - for folders that are awkward to click through (e.g. an emulator's dump,
// buried several levels deep in AppData).
async function useGameFilesPath(path) {
  const r = await pywebview.api.set_base_files_source(path);
  if (!r.success) { alert(r.error); return null; }
  resetPictureCaches();
  invalidateMenuLook();
  return r.status;
}

// "Or paste a path instead": a button added to the row of the folder button (`actions`, to the right of it, with a little space between), and
// the row it reveals - returned, for the caller to put under `actions`. `onUse` is called (and expected to re-render) after a successful
// copy, same as the "Choose the folder..." button.
function gameFilesPathRow(onUse, actions) {
  const inputRow = cgEl("div", "uis-path-row");
  inputRow.hidden = true;
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Path to the extracted romfs folder";
  const go = button("Use this path", "small", async () => {
    const path = input.value.trim();
    if (!path) { input.focus(); return; }
    go.disabled = true;
    const status = await useGameFilesPath(path);
    go.disabled = false;
    if (status) onUse(status); else input.focus();
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go.click(); });
  inputRow.append(input, go);
  const toggle = button("Or paste a path instead", "ghost small uis-paste-toggle", () => {
    toggle.hidden = true;
    inputRow.hidden = false;
    input.focus();
  });
  actions.appendChild(toggle);
  return inputRow;
}

// ---- "Where do I get these?": how to get the game's files, shared by the Setup step and Settings ----
// A small element builder: wizEl("p", "cls", "text", node, ...) - strings become text nodes.
function wizEl(tag, cls, ...kids) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids) e.append(k);
  return e;
}
// A link that opens in the user's browser (http/https only - the backend refuses anything else).
function wizExtLink(text, url) {
  const a = wizEl("a", "wiz-link", text);
  a.href = "#";
  a.title = url;
  a.addEventListener("click", (e) => { e.preventDefault(); pywebview.api.open_external_url(url); });
  return a;
}
// A link that opens a folder in the file manager.
function wizFolderLink(text, path) {
  const a = wizEl("a", "wiz-link", text);
  a.href = "#";
  a.title = path;
  a.addEventListener("click", async (e) => {
    e.preventDefault();
    const r = await pywebview.api.reveal_path(path);
    if (!r.success) alert(r.error);
  });
  return a;
}

// The tools the guide covers, and the one chosen last (kept until the app is closed, so Settings shows the same one as Setup).
const GAME_DATA_TOOLS = [["ryujinx", "Ryujinx"], ["eden", "Eden"], ["hactool", "hactool"]];
let gameDataTool = "ryujinx";

// Steps 2 and 3 of the guide for one tool: how to extract the RomFS, and what the folder to select looks like.
function gameDataToolSteps(tool) {
  const tree = wizEl("pre", null, "romfs\n├─ Audio\n├─ Course\n├─ UI\n│  └─ cmn\n│     └─ common.sarc\n└─ ...");
  const holds = "It should hold folders like Audio, Course and UI:";
  if (tool === "eden") {
    return [
      wizEl("li", null, "Extract the game data's RomFS in ", wizExtLink("Eden", "https://eden-emu.dev"),
        ": right click the game > Dump RomFS, and choose the Full dump mode when asked. Eden puts the result in ",
        wizEl("code", null, "%APPDATA%\\eden\\dump\\<title id>\\romfs"), "."),
      wizEl("li", null, "Select the extracted folder. With Eden it might look something like ",
        wizEl("code", null, "C:\\Users\\<you>\\AppData\\Roaming\\eden\\dump\\0100152000022000\\romfs"), ". " + holds, tree),
    ];
  }
  if (tool === "hactool") {
    return [
      wizEl("li", null, "Extract the game data's RomFS with ", wizExtLink("hactool", "https://github.com/SciresM/hactool"),
        " (it needs your Switch's keys file): ", wizEl("code", null, "hactool -k prod.keys -t nca --romfsdir=C:\\mk8d\\romfs <the game's .nca file>"),
        ". If the game has an update, extract the update's .nca file instead and add ", wizEl("code", null, "--basenca=<the base game's .nca file>"), "."),
      wizEl("li", null, "Select the extracted folder. With hactool, it is the folder you gave to ", wizEl("code", null, "--romfsdir"),
        ", for example ", wizEl("code", null, "C:\\mk8d\\romfs"), ". " + holds, tree),
    ];
  }
  return [
    wizEl("li", null, "Extract the game data's RomFS in ", wizExtLink("Ryujinx", "https://ryujinx.app"), ": right click the game > Extract Data > RomFS."),
    wizEl("li", null, "Select the extracted folder. With Ryujinx, that is the folder you chose to extract into, for example ",
      wizEl("code", null, "C:\\Users\\<you>\\Documents\\MK8D\\romfs"), ". " + holds, tree),
  ];
}

function gameDataInstructions() {
  const guide = wizEl("div", "wiz-guide");
  guide.append(wizEl("p", null, "These files will come from your copy of Mario Kart 8 Deluxe (they can't be included in the app, since they belong to Nintendo)."));
  guide.append(wizEl("h3", null, "Getting the game data"));

  const pick = wizEl("div", "wiz-field");
  const toolSelect = document.createElement("select");
  for (const [key, label] of GAME_DATA_TOOLS) toolSelect.append(new Option(label, key));
  toolSelect.value = gameDataTool;
  pick.append(wizEl("label", "t", "Which tool will you use to extract the RomFS?"), toolSelect);
  guide.append(pick);

  const steps = wizEl("ol");
  const drawSteps = () => {
    steps.replaceChildren(
      wizEl("li", null, "Dump the game data from your Switch using a tool like ",
        wizExtLink("NXDumpTool", "https://github.com/DarkMatterCore/nxdumptool"), "."),
      ...gameDataToolSteps(gameDataTool));
  };
  toolSelect.addEventListener("change", () => { gameDataTool = toolSelect.value; drawSteps(); });
  drawSteps();
  guide.append(steps);
  return guide;
}

// The Game files block of the required Setup step - the one place the game's files are chosen (Setup can be reopened any time from the step
// bar; the voice editor has its own button for the case where they are missing). When the copy exists it says so plainly and offers to
// update it from a new dump; the guide on how to get the files is shown above it by the step itself.
async function renderGameFilesBlock(container, onChange) {
  const st = await pywebview.api.get_base_files_status();
  container.replaceChildren();
  const refresh = async () => { await renderGameFilesBlock(container, onChange); if (onChange) onChange(); };
  const row = cgEl("div", "uis-actions");
  if (st.done) {
    // Say plainly that the original isn't needed any more, with links to both folders.
    const msg = wizEl("div", "uis-good", "The app has created a ");
    msg.append(st.copy_dir ? wizFolderLink("copy", st.copy_dir) : "copy",
      " of the necessary game files. Feel free to delete your ",
      st.source_exists ? wizFolderLink("original game dump", st.source) : "original game dump", ".");
    container.appendChild(msg);
    if (st.problems.length) container.appendChild(cgEl("div", "uis-warn", `${st.problems.length} file${st.problems.length === 1 ? "" : "s"} in that copy looked wrong and ${st.problems.length === 1 ? "was" : "were"} skipped: ${st.problems.join("; ")}`));
    if (st.voice_found < st.voice_total) container.appendChild(cgEl("div", "uis-note", `${st.voice_total - st.voice_found} character${st.voice_total - st.voice_found === 1 ? "" : "s"}' voice ${st.voice_total - st.voice_found === 1 ? "wasn't" : "weren't"} found in that folder - muting/replacing their default voice needs a selected voice mod for now instead.`));
    row.appendChild(button("Update from a new dump...", "small", async () => { if (await chooseGameFiles()) await refresh(); }));
  } else {
    row.appendChild(button("Choose the folder...", "primary small", async () => { if (await chooseGameFiles()) await refresh(); }));
  }
  container.appendChild(row);
  container.appendChild(gameFilesPathRow(refresh, row));
}

