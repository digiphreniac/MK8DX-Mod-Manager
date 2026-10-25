// --- Add a mod (Full List tab's "+") - paste a link, gb_identify_mod()
// guesses what it's for (a specific character, a specific-ish course, or
// neither), the user confirms or overrides that guess, then either lands
// in that character/course's usual modal (same as adding it from the grid)
// or - for a mod that isn't either - gets downloaded straight into a new
// "other" category, alongside characters/courses in Full List. See
// Api.gb_identify_mod()'s docstring for how the guess itself works. ---
let addModIdentified = null; // the last successful gb_identify_mod() result

function resetAddModModal() {
  addModIdentified = null;
  document.getElementById("add-mod-link-input").value = "";
  document.getElementById("add-mod-identify-error").hidden = true;
  document.getElementById("add-mod-confirm-error").hidden = true;
  document.getElementById("add-mod-result").hidden = true;
  document.getElementById("add-mod-guess-note").hidden = true;
  document.getElementById("add-mod-result").classList.remove("summary-mode");
  document.getElementById("add-mod-summary-panel").hidden = true;
  document.getElementById("add-mod-files-panel").hidden = true;
  document.getElementById("add-mod-files-list").innerHTML = "";
  document.getElementById("add-mod-vehicle-select").disabled = false;
  const identifyBtn = document.getElementById("btn-add-mod-identify");
  identifyBtn.disabled = false;
  identifyBtn.textContent = "Identify";
  const confirmBtn = document.getElementById("btn-add-mod-confirm");
  confirmBtn.disabled = false;
  confirmBtn.textContent = "Add this mod";
}

function openAddModModal() {
  resetAddModModal();
  addModModal.open();
  document.getElementById("add-mod-link-input").focus();
}
function closeAddModModal() {
  addModModal.close();
}
document.getElementById("btn-add-mod-fab").addEventListener("click", openAddModModal);

function populateAddModSelects(result) {
  const charSelect = document.getElementById("add-mod-character-select");
  charSelect.innerHTML = "";
  const characterNames = state.roster.map(r => r.name).sort((a, b) => a.localeCompare(b));
  for (const name of characterNames) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    charSelect.appendChild(opt);
  }
  if (result.guess_category === "characters" && result.guess_target) {
    charSelect.value = result.guess_target;
  }

  const courseSelect = document.getElementById("add-mod-course-select");
  courseSelect.innerHTML = "";
  const allCourseNames = state.cups.flatMap(cup => cup.courses.map(c => c.name));
  const candidates = result.course_candidates || [];
  if (candidates.length > 0) {
    const suggestedGroup = document.createElement("optgroup");
    suggestedGroup.label = "Suggested";
    for (const name of candidates) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      suggestedGroup.appendChild(opt);
    }
    courseSelect.appendChild(suggestedGroup);
    const allGroup = document.createElement("optgroup");
    allGroup.label = "All courses";
    for (const name of allCourseNames) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      allGroup.appendChild(opt);
    }
    courseSelect.appendChild(allGroup);
  } else {
    for (const name of allCourseNames) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      courseSelect.appendChild(opt);
    }
  }
  if (result.guess_category === "courses" && result.guess_target) {
    courseSelect.value = result.guess_target;
  }

  const vehicleSelect = document.getElementById("add-mod-vehicle-select");
  vehicleSelect.innerHTML = "";
  // No part is preselected unless the mod's text named one - a default like
  // "Standard Kart" would look like a suggestion it isn't.
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "— pick a part —";
  vehicleSelect.appendChild(placeholder);
  for (const group of result.all_vehicle_parts || []) {
    const og = document.createElement("optgroup");
    og.label = group.label;
    for (const name of group.items) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      og.appendChild(opt);
    }
    vehicleSelect.appendChild(og);
  }
  vehicleSelect.value = isVehicleGuess(result.guess_category) && result.guess_target ? result.guess_target : "";

  const itemSelect = document.getElementById("add-mod-item-select");
  itemSelect.innerHTML = "";
  const itemPlaceholder = document.createElement("option");
  itemPlaceholder.value = "";
  itemPlaceholder.textContent = "— pick an item —";
  itemSelect.appendChild(itemPlaceholder);
  for (const name of result.all_items || []) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name === ITEMS_OTHER ? ITEMS_OTHER_LABEL : name;
    itemSelect.appendChild(opt);
  }
  itemSelect.value = result.guess_category === ITEMS_CATEGORY && result.guess_target ? result.guess_target : "";

  const otherSelect = document.getElementById("add-mod-other-select");
  const otherLabelInput = document.getElementById("add-mod-other-label");
  const simpleGuess = SIMPLE_CATEGORIES.find(c => c.key === result.guess_category);
  otherSelect.value = simpleGuess ? simpleGuess.key : "custom";
  otherLabelInput.value = result.mod.name || "";
  updateAddModOtherVisibility();
}

// Multi-file vehicle mods: one row per file with a part picker, prefilled from
// gb_identify_mod's file_suggestions (see Api.suggest_file_targets).
function buildAddModFilesPanel(result) {
  const list = document.getElementById("add-mod-files-list");
  list.innerHTML = "";
  const suggestions = new Map((result.file_suggestions || []).map(sug => [sug.file_id, sug]));
  for (const file of result.mod.files) {
    const sug = suggestions.get(file.file_id) || {};
    const row = document.createElement("div");
    row.className = "add-mod-file-row";
    row.dataset.fileId = file.file_id;

    const label = document.createElement("label");
    const include = document.createElement("input");
    include.type = "checkbox";
    include.className = "amf-include";
    include.checked = !!(sug.default_include && sug.part);
    const text = document.createElement("span");
    text.className = "amf-text";
    text.textContent = file.name;
    const meta = document.createElement("div");
    meta.className = "amf-meta";
    meta.textContent = [formatFileSize(file.size), file.description, sug.companion ? "UI icons - optional, can't be merged" : null]
      .filter(Boolean).join(" · ");
    text.appendChild(meta);
    label.appendChild(include);
    label.appendChild(text);
    row.appendChild(label);

    const select = document.createElement("select");
    select.className = "amf-part";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "— pick a part —";
    select.appendChild(blank);
    for (const group of result.all_vehicle_parts || []) {
      const og = document.createElement("optgroup");
      og.label = group.label;
      for (const name of group.items) {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        og.appendChild(opt);
      }
      select.appendChild(og);
    }
    select.value = sug.part || "";
    // Choosing a part for a file implies you want it.
    select.addEventListener("change", () => { if (select.value) include.checked = true; });
    row.appendChild(select);
    list.appendChild(row);
  }
}

// The per-file panel only makes sense for a vehicle-part target on a mod with
// more than one file; while it's active the single "whole mod" part dropdown
// is unused.
function updateAddModFilesPanel() {
  const panel = document.getElementById("add-mod-files-panel");
  const eligible = !!addModIdentified && addModIdentified.mod.files.length > 1
    && (addModIdentified.file_suggestions || []).length > 0;
  panel.hidden = !(eligible && document.getElementById("add-mod-radio-vehicle").checked);
  const perFile = !panel.hidden && document.getElementById("add-mod-perfile-toggle").checked;
  panel.classList.toggle("off", !perFile && !panel.hidden);
  document.getElementById("add-mod-vehicle-select").disabled = perFile;
}
document.getElementById("add-mod-perfile-toggle").addEventListener("change", updateAddModFilesPanel);
for (const radio of document.querySelectorAll('input[name="add-mod-target-type"]')) {
  radio.addEventListener("change", updateAddModFilesPanel);
}

// After a per-file add: what happened to each file, with a Move button for any
// that turned out to belong under a different part.
function showAddModSummary(result) {
  const panel = document.getElementById("add-mod-summary-panel");
  panel.innerHTML = "";
  const title = document.createElement("div");
  title.className = "add-mod-summary-title";
  title.textContent = `Added "${result.mod_name || "this mod"}"`;
  panel.appendChild(title);

  const NOT_MERGEABLE_LABEL = {
    needs_manual_fix: "downloaded, but needs a manual fix",
    missing_romfs: "downloaded, but has no romfs folder",
    ui_assets: "downloaded, but is UI art only",
  };
  const openTargets = [];
  for (const part of result.parts) {
    if (part.error) {
      const line = document.createElement("div");
      line.className = "add-mod-summary-line err";
      line.textContent = `✗ ${part.part}: ${part.error}`;
      panel.appendChild(line);
      continue;
    }
    openTargets.push(part.part);
    for (const f of part.files) {
      const line = document.createElement("div");
      const text = document.createElement("span");
      if (f.status === "error") {
        line.className = "add-mod-summary-line err";
        text.textContent = `✗ ${part.part} — ${f.name}: ${f.error}`;
      } else if (f.slot_mismatch && (f.slot_mismatch.found_parts || []).length > 0) {
        line.className = "add-mod-summary-line warn";
        const names = f.slot_mismatch.found_parts.map(fp => fp.name);
        text.textContent = `⚠ ${part.part} — ${f.name} actually ships ${names.join(" / ")}'s file`;
      } else if (f.companion && f.status === "ui_assets") {
        // Expected: an optional icons file can't be merged (it lands under UI
        // art only) - not something to warn about.
        line.className = "add-mod-summary-line ok";
        text.textContent = `✓ ${part.part} — ${f.name} (UI icons: can't be merged - see the UI Icon Worklist in Settings)`;
      } else if (NOT_MERGEABLE_LABEL[f.status]) {
        line.className = "add-mod-summary-line warn";
        text.textContent = `⚠ ${part.part} — ${f.name}: ${NOT_MERGEABLE_LABEL[f.status]}`;
      } else {
        line.className = "add-mod-summary-line ok";
        text.textContent = `✓ ${part.part} — ${f.name}`;
      }
      line.appendChild(text);
      if (f.slot_mismatch) {
        for (const fp of (f.slot_mismatch.found_parts || []).slice(0, 3)) {
          const moveBtn = document.createElement("button");
          moveBtn.className = "ghost small";
          moveBtn.textContent = `Move to ${fp.name}`;
          moveBtn.addEventListener("click", async () => {
            moveBtn.disabled = true;
            moveBtn.textContent = "Moving...";
            const moved = await pywebview.api.gb_move_mod(part.part, part.mod_id, fp.name, part.record_type);
            if (!moved.success) {
              moveBtn.disabled = false;
              moveBtn.textContent = `Move to ${fp.name}`;
              text.textContent = `⚠ Couldn't move it: ${moved.error}`;
              return;
            }
            await loadMods();   // (not just refreshViewsState: the move renamed the mod's ticked-state key too)
            refreshBehindModal();
            line.className = "add-mod-summary-line ok";
            text.textContent = `✓ ${f.name} moved to ${fp.name}`;
            line.querySelectorAll("button").forEach(b => b.remove());
          });
          line.appendChild(moveBtn);
        }
      }
      panel.appendChild(line);
    }
  }

  const actions = document.createElement("div");
  actions.className = "add-mod-summary-actions";
  for (const partName of [...new Set(openTargets)]) {
    const openBtn = document.createElement("button");
    openBtn.className = "ghost small";
    openBtn.textContent = `Open ${partName}`;
    openBtn.addEventListener("click", () => {
      closeAddModModal();
      switchView("vehicles");
      openCharacterModal(partName);
    });
    actions.appendChild(openBtn);
  }
  const done = document.createElement("button");
  done.className = "primary";
  done.textContent = "Done";
  done.addEventListener("click", () => { closeAddModModal(); switchView("vehicles"); });
  actions.appendChild(done);
  panel.appendChild(actions);

  document.getElementById("add-mod-result").classList.add("summary-mode");
  panel.hidden = false;
}

async function confirmAddModPerFile(link, errEl, confirmBtn) {
  const groups = new Map();
  for (const row of document.querySelectorAll("#add-mod-files-list .add-mod-file-row")) {
    if (!row.querySelector(".amf-include").checked) continue;
    const part = row.querySelector(".amf-part").value;
    if (!part) {
      errEl.textContent = "Pick a part for every selected file (or deselect the ones you don't want).";
      errEl.hidden = false;
      return;
    }
    if (!groups.has(part)) groups.set(part, []);
    groups.get(part).push(Number(row.dataset.fileId));
  }
  if (groups.size === 0) {
    errEl.textContent = "Select at least one file to add.";
    errEl.hidden = false;
    return;
  }
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Adding & downloading...";
  const result = await pywebview.api.gb_add_vehicle_mod_files(
    link, [...groups].map(([part, file_ids]) => ({ part, file_ids })));
  confirmBtn.disabled = false;
  confirmBtn.textContent = "Add this mod";
  await refreshViewsState();
  // Same convenience as a single download: a part that now has exactly one
  // mergeable mod, from a file with no warnings, is ticked for you.
  let ticked = false;
  for (const part of result.parts) {
    const realFiles = part.files.filter(f => !f.companion);
    const clean = !part.error && realFiles.length > 0 && realFiles.every(f => f.status === "downloaded" && !f.slot_mismatch);
    const item = findVehicleItem(part.part);
    if (clean && item && item.item.units.length === 1 && !state.checked[item.item.units[0]]) {
      state.checked[item.item.units[0]] = true;
      ticked = true;
    }
  }
  if (ticked) await saveChecked();
  refreshBehindModal();
  showAddModSummary(result);
}

function updateAddModOtherVisibility() {
  const isCustom = document.getElementById("add-mod-other-select").value === "custom";
  document.getElementById("add-mod-other-label").hidden = !isCustom;
}
document.getElementById("add-mod-other-select").addEventListener("change", updateAddModOtherVisibility);

async function identifyAddMod() {
  const link = document.getElementById("add-mod-link-input").value.trim();
  const errEl = document.getElementById("add-mod-identify-error");
  errEl.hidden = true;
  if (!link) {
    errEl.textContent = "Paste a GameBanana link or mod id first.";
    errEl.hidden = false;
    return;
  }
  const btn = document.getElementById("btn-add-mod-identify");
  btn.disabled = true;
  btn.textContent = "Identifying...";
  const result = await pywebview.api.gb_identify_mod(link);
  btn.disabled = false;
  btn.textContent = "Identify";
  if (!result.success) {
    errEl.textContent = result.error;
    errEl.hidden = false;
    return;
  }
  addModIdentified = result;
  document.getElementById("add-mod-result").classList.remove("summary-mode");
  document.getElementById("add-mod-summary-panel").hidden = true;

  document.getElementById("add-mod-thumb").src = result.mod.thumbnail_url || "";
  document.getElementById("add-mod-name").textContent = result.mod.name;
  document.getElementById("add-mod-author").textContent = result.mod.author ? `by ${result.mod.author}` : "";

  populateAddModSelects(result);

  const gameWarnEl = document.getElementById("add-mod-game-warning");
  const wrongGame = result.mod.game_id && result.mod.game_id !== MK8DX_GAME_ID;
  gameWarnEl.hidden = !wrongGame;
  if (wrongGame) {
    gameWarnEl.textContent = `⚠ This mod is filed under "${result.mod.game_name}", not Mario Kart 8 Deluxe - it was made for a different game (for "Mario Kart 8" that's the Wii U version), so it very likely won't work on a Switch. Add it only if you know it's been ported.`;
  }

  const noteEl = document.getElementById("add-mod-guess-note");
  const simpleGuess = SIMPLE_CATEGORIES.find(c => c.key === result.guess_category);
  if (result.guess_category === "characters") {
    noteEl.textContent = `GameBanana lists this under "${result.mod.category_name}" - looks like a mod for ${result.guess_target}.`;
    noteEl.hidden = false;
  } else if (result.guess_category === "courses" && result.guess_target) {
    noteEl.textContent = `This looks like a course mod, possibly for ${result.guess_target} - double-check before confirming, course guesses are less certain than character ones.`;
    noteEl.hidden = false;
  } else if (result.guess_category === "courses") {
    noteEl.textContent = `This looks like a course mod, but couldn't guess which course - pick one below.`;
    noteEl.hidden = false;
  } else if (isVehicleGuess(result.guess_category)) {
    noteEl.textContent = result.guess_target
      ? `GameBanana lists this under "${result.mod.category_name}" - its description suggests it replaces ${result.guess_target}. That's a guess from the text, so double-check before confirming.`
      : `GameBanana lists this under "${result.mod.category_name}" - it's a vehicle part mod, but its text doesn't say which part. Pick one below (after downloading, the app checks the files and tells you if it's under the wrong part).`;
    noteEl.hidden = false;
  } else if (result.guess_category === ITEMS_CATEGORY) {
    noteEl.textContent = result.guess_target && result.guess_target !== ITEMS_OTHER
      ? `GameBanana lists this under "${result.mod.category_name}" - its description suggests it replaces ${result.guess_target}. That's a guess from the text, so double-check before confirming.`
      : `GameBanana lists this under "${result.mod.category_name}" - it's an item mod, but its text doesn't name a single one of the listed items (or names several, like an item pack). It goes under "${ITEMS_OTHER_LABEL}" unless you pick an item below.`;
    noteEl.hidden = false;
  } else if (simpleGuess) {
    noteEl.textContent = `GameBanana lists this under "${result.mod.category_name}" - looks like a ${simpleGuess.label} mod.`;
    noteEl.hidden = false;
  } else {
    noteEl.textContent = `Couldn't tell if this is a character or course mod - pick one below, or save it as a general mod.`;
    noteEl.hidden = false;
  }

  // A wrong-game mod's category isn't one this app knows, so the generic
  // "couldn't tell what this is" fallback would just be noise next to the warning.
  if (wrongGame && !result.guess_category) noteEl.hidden = true;

  const radioValue = result.guess_category === "characters" ? "character"
    : result.guess_category === "courses" ? "course"
    : isVehicleGuess(result.guess_category) ? "vehicle"
    : result.guess_category === ITEMS_CATEGORY ? "item"
    : "other";
  document.querySelector(`input[name="add-mod-target-type"][value="${radioValue}"]`).checked = true;
  buildAddModFilesPanel(result);
  updateAddModFilesPanel();

  document.getElementById("add-mod-result").hidden = false;
}

document.getElementById("btn-add-mod-identify").addEventListener("click", identifyAddMod);
document.getElementById("add-mod-link-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); identifyAddMod(); }
});

// Interacting with a row's own control implies you mean that row, so it
// checks the radio for you instead of making you click both.
document.getElementById("add-mod-character-select").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-character").checked = true;
});
document.getElementById("add-mod-course-select").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-course").checked = true;
});
document.getElementById("add-mod-vehicle-select").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-vehicle").checked = true;
  updateAddModFilesPanel();
});
document.getElementById("add-mod-item-select").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-item").checked = true;
});
document.getElementById("add-mod-other-select").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-other").checked = true;
});
document.getElementById("add-mod-other-label").addEventListener("focus", () => {
  document.getElementById("add-mod-radio-other").checked = true;
});

async function confirmAddMod() {
  if (!addModIdentified) return;
  const link = document.getElementById("add-mod-link-input").value.trim();
  const errEl = document.getElementById("add-mod-confirm-error");
  errEl.hidden = true;
  const targetType = document.querySelector('input[name="add-mod-target-type"]:checked').value;
  const confirmBtn = document.getElementById("btn-add-mod-confirm");

  if (targetType === "vehicle"
      && !document.getElementById("add-mod-files-panel").hidden
      && document.getElementById("add-mod-perfile-toggle").checked) {
    return confirmAddModPerFile(link, errEl, confirmBtn);
  }

  if (targetType === "character" || targetType === "course" || targetType === "vehicle" || targetType === "item") {
    const target = targetType === "character"
      ? document.getElementById("add-mod-character-select").value
      : targetType === "course"
        ? document.getElementById("add-mod-course-select").value
        : targetType === "item"
          ? document.getElementById("add-mod-item-select").value
          : document.getElementById("add-mod-vehicle-select").value;
    if (!target) {
      errEl.textContent = "Pick one from the dropdown first.";
      errEl.hidden = false;
      return;
    }
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Adding...";
    const result = await diag.attempt(() => pywebview.api.gb_fetch_mod(target, link));
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Add this mod";
    if (!result.success) {
      errEl.textContent = result.error;
      errEl.hidden = false;
      return;
    }
    await refreshViewsState();
    closeAddModModal();
    if (targetType === "item") {
      await openItemCard(target);
    } else {
      switchView(targetType === "character" ? "characters" : targetType === "course" ? "courses" : "vehicles");
      openCharacterModal(target);
    }
    refreshBehindModal();
    return;
  }

  const otherKey = document.getElementById("add-mod-other-select").value;
  const simpleTarget = SIMPLE_CATEGORIES.find(c => c.key === otherKey);
  if (simpleTarget) {
    // A simple category (Mechanics, UI, Code patches...) behaves exactly like
    // a character/course target above - fetch metadata, then hand off into
    // its own modal (reached via the More tab) so files get picked the
    // normal way, not auto-downloaded.
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Adding...";
    const result = await diag.attempt(() => pywebview.api.gb_fetch_mod(simpleTarget.label, link));
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Add this mod";
    if (!result.success) {
      errEl.textContent = result.error;
      errEl.hidden = false;
      return;
    }
    const simpleResult = await pywebview.api.get_simple_categories_view();
    state.simpleCategories = simpleResult.categories;
    closeAddModModal();
    switchView("more");
    await renderMoreList();
    openCharacterModal(simpleTarget.label);
    refreshBehindModal();
    return;
  }

  // Genuinely custom - not tied to a specific character/course/simple
  // category, so there's no per-item modal to hand off into like above.
  // Simpler instead of building a whole separate file-picker UI for this
  // one path: fetch the metadata, then download every file straight away
  // (most GameBanana mods only have one anyway) into a new "other"
  // category, which shows up in Full List exactly like the rest do.
  const label = document.getElementById("add-mod-other-label").value.trim() || addModIdentified.mod.name;
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Adding...";
  const fetchResult = await diag.attempt(() => pywebview.api.gb_fetch_mod(label, link));
  if (!fetchResult.success) {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Add this mod";
    errEl.textContent = fetchResult.error;
    errEl.hidden = false;
    return;
  }
  const fileIds = fetchResult.mod.files.map(f => f.file_id);
  if (fileIds.length === 0) {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Add this mod";
    errEl.textContent = "This mod has no downloadable files on GameBanana.";
    errEl.hidden = false;
    return;
  }
  const dlResult = await diag.attempt(() => pywebview.api.gb_download_files("other", label, fetchResult.mod.mod_id, fileIds, fetchResult.mod.record_type));
  confirmBtn.disabled = false;
  confirmBtn.textContent = "Add this mod";
  if (dlResult.success === false) {
    errEl.textContent = dlResult.error;
    errEl.hidden = false;
    return;
  }
  const failed = (dlResult.results || []).filter(r => r.status === "error");
  if (failed.length > 0) {
    errEl.textContent = `Fetched, but ${failed.length} file(s) failed to download: ${failed.map(f => f.error).join("; ")}`;
    errEl.hidden = false;
    return;
  }
  closeAddModModal();
  switchView("list");
  await loadMods();
}
document.getElementById("btn-add-mod-confirm").addEventListener("click", confirmAddMod);

