function buildGameBananaCard(itemName, category, opts) {
  const card = document.createElement("div");
  card.className = "modal-card";

  const header = document.createElement("div");
  header.className = "modal-card-header gb-section-header";
  const title = document.createElement("span");
  title.className = "modal-card-title";
  title.textContent = (opts && opts.title) || "GameBanana mods";
  header.appendChild(title);
  const collapseToggle = document.createElement("button");
  collapseToggle.className = "ghost small gb-section-collapse-toggle";
  header.appendChild(collapseToggle);
  card.appendChild(header);

  const sectionBody = document.createElement("div");
  sectionBody.className = "gb-section-body";
  card.appendChild(sectionBody);

  const fetchRow = document.createElement("div");
  fetchRow.className = "gb-fetch-row";
  const fetchInput = document.createElement("input");
  fetchInput.type = "text";
  fetchInput.placeholder = "Paste a GameBanana mod/sound link or ID";
  const fetchBtn = document.createElement("button");
  fetchBtn.className = "primary small";
  fetchBtn.textContent = "Fetch";
  fetchRow.appendChild(fetchInput);
  fetchRow.appendChild(fetchBtn);
  sectionBody.appendChild(fetchRow);

  const fetchError = document.createElement("div");
  fetchError.className = "gb-fetch-error";
  fetchError.hidden = true;
  sectionBody.appendChild(fetchError);

  const browseToggleRow = document.createElement("div");
  browseToggleRow.className = "gb-browse-toggle-row";
  const browseToggleBtn = document.createElement("button");
  browseToggleBtn.className = "ghost small";
  browseToggleBtn.textContent = "Browse GameBanana ↗";
  browseToggleRow.appendChild(browseToggleBtn);
  sectionBody.appendChild(browseToggleRow);

  const modsContainer = document.createElement("div");
  sectionBody.appendChild(modsContainer);

  // Locks every control in the section (fetch/browse/per-mod buttons and
  // checkboxes) while a download is in flight, so nothing else can be
  // clicked mid-download - and gives the whole card a visibly "disabled"
  // look via CSS rather than just the one Download button.
  function setSectionDisabled(disabled) {
    sectionBody.classList.toggle("gb-section-disabled", disabled);
    fetchInput.disabled = disabled;
    fetchBtn.disabled = disabled;
    browseToggleBtn.disabled = disabled;
    for (const el of modsContainer.querySelectorAll("input, button")) {
      el.disabled = disabled;
    }
  }

  function setCollapsed(collapsed) {
    if (collapsed) {
      gbSectionCollapsed.add(itemName);
    } else {
      gbSectionCollapsed.delete(itemName);
    }
    sectionBody.hidden = collapsed;
    collapseToggle.textContent = collapsed ? "Show ▾" : "Hide ▴";
    card.classList.toggle("open", !collapsed);
  }
  collapseToggle.addEventListener("click", () => setCollapsed(!sectionBody.hidden));
  setCollapsed(gbSectionCollapsed.has(itemName));
  if (opts && opts.slim) {
    // a quiet "+ Add another mod" row under the mods; clicking anywhere on it opens the section in place
    card.classList.add("gb-slim");
    title.textContent = "+ Add another mod";
    const hint = document.createElement("span");
    hint.className = "gb-slim-hint";
    hint.textContent = "Paste a link or browse GameBanana";
    header.insertBefore(hint, collapseToggle);
    collapseToggle.hidden = true;
    header.addEventListener("click", (e) => { if (!e.target.closest("button")) collapseToggle.click(); });
  }

  async function refreshAfterChange() {
    await refreshViewsState();
    openCharacterModal(itemName);
    refreshBehindModal();
  }

  // `fresh`: a mod the user just chose (from the browse window or a pasted link). The windows close, and the
  // card it lands on scrolls to it and - when it has a single file - downloads it straight away.
  async function doFetch(idOrUrl, fresh = true) {
    fetchError.hidden = true;
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching...";
    const result = await pywebview.api.gb_fetch_mod(itemName, idOrUrl);
    if (!result.success) {
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Fetch";
      fetchError.textContent = result.error;
      fetchError.hidden = false;
      return false;
    }
    fetchInput.value = "";
    if (fresh) {
      gbJustAdded = { item: itemName, modId: String(result.mod.mod_id), type: result.mod.record_type || "Mod" };
      gbSectionCollapsed.delete(itemName);
      closeGbDetailModal();
      closeGbBrowseModal();
    }
    await refreshAfterChange();
    return true;
  }

  fetchBtn.addEventListener("click", () => {
    const v = fetchInput.value.trim();
    if (v) doFetch(v);
  });
  fetchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = fetchInput.value.trim();
      if (v) doFetch(v);
    }
  });

  browseToggleBtn.addEventListener("click", () => {
    openGbBrowseModal(itemName, category, doFetch);
  });

  function buildFileRow(file, mod) {
    const row = document.createElement("div");
    row.className = "gb-file-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.fileId = file.file_id;
    row.appendChild(cb);
    const nameEl = document.createElement("div");
    nameEl.className = "gb-file-name";
    const nameText = document.createElement("span");
    nameText.textContent = file.name;
    nameEl.appendChild(nameText);
    if (file.description) {
      const descText = document.createElement("span");
      descText.className = "gb-file-desc";
      descText.textContent = file.description;
      nameEl.appendChild(descText);
    }
    if (file.other_character_hint) {
      // GameBanana mods commonly bundle several characters' variants in one
      // listing - this filename matched another roster character's name, so
      // it's very likely meant for them, not the character this card is
      // open on. Soft hint only: nothing is hidden or blocked.
      const warn = document.createElement("span");
      warn.className = "gb-file-warn";
      warn.textContent = `⚠ Filename mentions "${file.other_character_hint}" - double check this file is meant for this character before downloading.`;
      nameEl.appendChild(warn);
    }
    if (file.slot_mismatch) {
      // The download succeeded, but the internal romfs/Course/<id>/ folder
      // it actually wrote doesn't match roster.json's known id(s) for
      // this course - it's a real course, just very likely not this one (see
      // roster.json's "internal" field). Nothing is blocked; this is
      // exactly the kind of mismatch that otherwise only shows up later as a
      // silent commit conflict against whichever course really owns
      // that slot.
      const warn = document.createElement("span");
      warn.className = "gb-file-warn";
      const foundParts = file.slot_mismatch.found_parts || [];
      if (findVehicleItem(itemName) && foundParts.length > 0) {
        // Name the part(s) it really ships instead of internal file ids, and
        // offer to re-file it there in one click.
        const names = foundParts.map(fp => fp.name);
        warn.textContent = `⚠ This mod ships ${names.join(" / ")}'s file (${file.slot_mismatch.found.join(", ")}), not ${itemName}'s - it probably belongs under ${names.length === 1 ? "that part" : "one of those parts"} instead.`;
        nameEl.appendChild(warn);
        const moveRow = document.createElement("span");
        moveRow.className = "gb-move-row";
        for (const fp of foundParts.slice(0, 3)) {
          const moveBtn = document.createElement("button");
          moveBtn.className = "ghost small";
          moveBtn.textContent = `Move to ${fp.name}`;
          moveBtn.title = `Re-file this mod (and its downloaded files) under ${fp.name}`;
          moveBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            moveBtn.disabled = true;
            moveBtn.textContent = "Moving...";
            const result = await pywebview.api.gb_move_mod(itemName, mod.mod_id, fp.name, mod.record_type || "Mod");
            if (!result.success) {
              moveBtn.disabled = false;
              moveBtn.textContent = `Move to ${fp.name}`;
              warn.textContent = `⚠ Couldn't move it: ${result.error}`;
              return;
            }
            await loadMods();   // (not just refreshViewsState: the move renamed the mod's ticked-state key too)
            switchView("vehicles");
            openCharacterModal(fp.name);
            refreshBehindModal();
          });
          moveRow.appendChild(moveBtn);
        }
        nameEl.appendChild(moveRow);
      } else if (file.slot_mismatch.found_characters) {
        const who = file.slot_mismatch.found_characters;
        warn.textContent = `⚠ This mod's driver/voice files are for ${who.join(" / ")}, not ${itemName} - it probably belongs under ${who.length === 1 ? "that character" : "one of those characters"} instead.`;
        nameEl.appendChild(warn);
      } else {
        warn.textContent = findVehicleItem(itemName)
          ? `⚠ This mod ships "${file.slot_mismatch.found.join(", ")}", not this part's own file (${file.slot_mismatch.expected.join(", ")}) - it probably replaces a different part and belongs under that row instead.`
          : `⚠ This mod writes to "${file.slot_mismatch.found.join(", ")}", not this course's known slot (${file.slot_mismatch.expected.join(", ")}) - it may belong under a different course row.`;
        nameEl.appendChild(warn);
      }
    }
    if (file.music_mismatch) {
      // Same idea as slot_mismatch, for the bundled race music instead of
      // the course geometry - independent signal, so this can fire even
      // when the Course/ folder itself was correct.
      const warn = document.createElement("span");
      warn.className = "gb-file-warn";
      warn.textContent = `⚠ This mod's music is "${file.music_mismatch.found.join(", ")}", not this course's known music (${file.music_mismatch.expected.join(", ")}) - it may belong under a different course row.`;
      nameEl.appendChild(warn);
    }
    if (file.download_status === "ui_assets") {
      const hint = document.createElement("span");
      hint.className = "gb-file-desc";
      hint.textContent = "UI art or a packed .sarc, no romfs - not merged automatically. Inject PNGs into common.sarc/menu.sarc yourself (e.g. with Switch Toolbox); a whole-file .sarc replaces your entire icon set.";
      nameEl.appendChild(hint);
    }
    if (file.download_status === "missing_romfs") {
      const hint = document.createElement("span");
      hint.className = "gb-file-desc";
      hint.textContent = "Extracted, but the mod folders (Driver/DriverTex/Audio/Kart/...) sit at the top level instead of under a romfs folder - create a \"romfs\" folder in there and move them into it.";
      nameEl.appendChild(hint);
    }
    row.appendChild(nameEl);
    const sizeEl = document.createElement("span");
    sizeEl.className = "gb-file-size";
    sizeEl.textContent = formatFileSize(file.size);
    row.appendChild(sizeEl);
    const statusEl = document.createElement("span");
    statusEl.className = "gb-file-status status-" + file.download_status;
    statusEl.textContent = FILE_STATUS_LABEL[file.download_status] || file.download_status;
    row.appendChild(statusEl);
    const NEEDS_FOLDER_ACCESS = new Set(["needs_manual_fix", "ui_assets", "missing_romfs"]);
    if (NEEDS_FOLDER_ACCESS.has(file.download_status) && file.downloaded_to) {
      const revealBtn = document.createElement("button");
      revealBtn.className = "ghost small";
      revealBtn.textContent = "Open folder";
      revealBtn.addEventListener("click", async () => {
        const r = await pywebview.api.reveal_path(file.downloaded_to);
        if (!r.success) {
          fetchError.textContent = r.error;
          fetchError.hidden = false;
        }
      });
      row.appendChild(revealBtn);
    }
    return { cb, row };
  }

  function buildModBlock(mod) {
    const block = document.createElement("div");
    block.className = "gb-mod-block";

    if (mod.thumbnail_url) {
      const img = document.createElement("img");
      img.className = "gb-mod-thumb";
      img.src = mod.thumbnail_url;
      img.alt = "";
      img.title = "Open on GameBanana";
      img.addEventListener("click", () => pywebview.api.gb_open_url(mod.profile_url));
      block.appendChild(img);
    }

    const main = document.createElement("div");
    main.className = "gb-mod-main";

    const nameRow = document.createElement("div");
    nameRow.className = "gb-mod-name-row";
    const nameBtn = document.createElement("button");
    nameBtn.className = "gb-mod-name-btn";
    nameBtn.textContent = mod.name;
    nameBtn.title = "Open on GameBanana";
    nameBtn.addEventListener("click", () => pywebview.api.gb_open_url(mod.profile_url));
    nameRow.appendChild(nameBtn);
    const doneTag = document.createElement("span");
    doneTag.className = "gb-mod-done-tag";
    doneTag.textContent = "Downloaded ✓";
    doneTag.hidden = true;
    nameRow.appendChild(doneTag);
    const spacer = document.createElement("div");
    spacer.className = "gb-mod-spacer";
    nameRow.appendChild(spacer);
    // Collapse is scoped to THIS mod block only - a whole-section collapse
    // was hiding other still-pending companion mods (e.g. a voice or UI
    // link fetched after the primary skin) every time one download finished.
    const blockCollapseToggle = document.createElement("button");
    blockCollapseToggle.className = "ghost small";
    nameRow.appendChild(blockCollapseToggle);
    const refetchBtn = document.createElement("button");
    refetchBtn.className = "ghost small";
    refetchBtn.textContent = "Refetch";
    // Refetch by profile_url, not a bare mod_id - a Sound record's id could
    // otherwise be misread as a Mod id of the same number.
    refetchBtn.addEventListener("click", () => doFetch(mod.profile_url, false));
    nameRow.appendChild(refetchBtn);
    const removeBtn = document.createElement("button");
    removeBtn.className = "ghost small";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", async () => {
      await pywebview.api.gb_remove_mod(itemName, mod.mod_id, mod.record_type);
      await refreshAfterChange();
    });
    nameRow.appendChild(removeBtn);
    // Course-select icon generation is course-only (see the Help page's
    // "select-screen icon... is missing" entry) - offered per-mod, using
    // that mod's own screenshots, since a course can have more than one
    // tracked mod and only one is likely to be the checked one.
    if (category === "courses" && (mod.screenshots || []).length > 0) {
      const iconGenBtn = document.createElement("button");
      iconGenBtn.className = "ghost small";
      iconGenBtn.textContent = "Icon from screenshot";
      iconGenBtn.title = "Generate a course-select picture from one of this mod's own screenshots";
      iconGenBtn.addEventListener("click", () => openIconGenModal(itemName, mod.screenshots));
      nameRow.appendChild(iconGenBtn);
    }
    main.appendChild(nameRow);

    const blockBody = document.createElement("div");
    main.appendChild(blockBody);

    if (mod.description) {
      const desc = document.createElement("div");
      desc.className = "gb-mod-desc";
      desc.textContent = mod.description;
      blockBody.appendChild(desc);
    }

    if (mod.game_id && mod.game_id !== MK8DX_GAME_ID) {
      const gameWarn = document.createElement("div");
      gameWarn.className = "gb-file-warn";
      gameWarn.textContent = `⚠ Filed under "${mod.game_name}", not Mario Kart 8 Deluxe - made for a different game, so it very likely won't work on a Switch.`;
      blockBody.appendChild(gameWarn);
    }

    const fileCheckboxes = [];
    for (const file of mod.files) {
      const { cb, row } = buildFileRow(file, mod);
      blockBody.appendChild(row);
      fileCheckboxes.push(cb);
    }
    // Only one download option - no real choice to make, so save the click.
    if (fileCheckboxes.length === 1) {
      fileCheckboxes[0].checked = true;
    } else if (fileCheckboxes.length > 1) {
      // Several files: pre-tick the one most likely wanted (newest / fullest / named for this item).
      const pick = suggestFiles(mod.files, itemName);
      if (pick.size) {
        fileCheckboxes.forEach(cb => { cb.checked = pick.has(Number(cb.dataset.fileId)) || pick.has(cb.dataset.fileId); });
        const note = document.createElement("div");
        note.className = "settings-hint";
        note.textContent = `Suggested file${pick.size === 1 ? "" : "s"} ticked (the newest / fullest / one named for ${itemName}). Tick any others you also want - a mod often has a companion file (audio, UI) as well.`;
        blockBody.appendChild(note);
      }
    }

    const modError = document.createElement("div");
    modError.className = "gb-mod-error";
    modError.hidden = true;
    blockBody.appendChild(modError);

    const blockKey = `${itemName}::${mod.record_type}::${mod.mod_id}`;
    function setBlockCollapsed(collapsed) {
      if (collapsed) {
        gbModBlockCollapsed.add(blockKey);
      } else {
        gbModBlockCollapsed.delete(blockKey);
      }
      blockBody.hidden = collapsed;
      doneTag.hidden = !collapsed;
      blockCollapseToggle.textContent = collapsed ? "Show ▾" : "Hide ▴";
    }
    blockCollapseToggle.addEventListener("click", () => setBlockCollapsed(!blockBody.hidden));

    if (mod.files.length > 0) {
      const actions = document.createElement("div");
      actions.className = "gb-mod-actions";
      const dlBtn = document.createElement("button");
      dlBtn.className = "primary small";
      // A file already showing a real download status (not just "never
      // tried") gets a distinct "Re-download" label when selected, since
      // clicking it now replaces that previous copy in place (see
      // Api._retire_previous_download()) rather than being a no-op - worth
      // being explicit about, since it's still a deliberate action (getting
      // an update, or recovering from a folder deleted outside the app).
      const ALREADY_DOWNLOADED = new Set(["downloaded", "ui_assets", "missing_romfs", "needs_manual_fix"]);
      function dlBtnLabel() {
        const anyRedownload = mod.files.some((f, i) => fileCheckboxes[i].checked && ALREADY_DOWNLOADED.has(f.download_status));
        return anyRedownload ? "Re-download selected" : "Download selected";
      }
      dlBtn.textContent = dlBtnLabel();
      const NO_FILE_TICKED_MSG = "Tick at least one file to download.";
      fileCheckboxes.forEach(cb => cb.addEventListener("change", () => {
        dlBtn.textContent = dlBtnLabel();
        if (modError.textContent === NO_FILE_TICKED_MSG) modError.hidden = true; // they've fixed it
      }));
      dlBtn.addEventListener("click", async () => {
        const fileIds = fileCheckboxes.filter(cb => cb.checked).map(cb => Number(cb.dataset.fileId));
        if (fileIds.length === 0) {
          // A multi-file mod has none pre-ticked, so this is easy to hit -
          // say what's needed instead of doing nothing.
          modError.textContent = NO_FILE_TICKED_MSG;
          modError.hidden = false;
          return;
        }
        modError.hidden = true;
        setSectionDisabled(true);
        const totalSize = mod.files.reduce((n, f, i) => n + (fileCheckboxes[i].checked ? (f.size || 0) : 0), 0);
        dlBtn.replaceChildren(Object.assign(document.createElement("span"), { className: "spin" }), document.createTextNode(" Downloading" + (totalSize ? " " + formatFileSize(totalSize) : "") + "..."));
        const bar = document.createElement("div");
        bar.className = "indet";
        actions.appendChild(bar);
        const result = await pywebview.api.gb_download_files(category, itemName, mod.mod_id, fileIds, mod.record_type);
        bar.remove();
        if (!result.success) {
          setSectionDisabled(false);
          dlBtn.textContent = dlBtnLabel();
          modError.textContent = result.error;
          modError.hidden = false;
          return;
        }
        const failed = result.results.filter(r => r.status === "error");
        if (failed.length > 0) {
          // Something went wrong for at least one file - leave this mod
          // block open so the error (and which file it hit) stays visible,
          // instead of collapsing it away.
          setSectionDisabled(false);
          modError.textContent = failed.map(f => f.error).join(" ");
          modError.hidden = false;
          await refreshAfterChange();
          return;
        }
        // Clean download - tuck just this mod block away, not the whole
        // section, so any other pending companion mod stays visible. Except
        // when a file came back with a slot/music mismatch warning: that
        // warning (and, for vehicle parts, its "Move to..." button) lives in
        // this block, so it stays open - and the mod isn't auto-ticked below,
        // since it probably belongs under a different row.
        const hasWarning = result.results.some(r => r.slot_mismatch || r.music_mismatch);
        setSectionDisabled(false);
        if (hasWarning) gbModBlockCollapsed.delete(blockKey);
        else gbModBlockCollapsed.add(blockKey);
        // the quiet "Add another mod" row folds back away once nothing else is waiting to be downloaded
        if (opts && opts.slim && !hasWarning && ![...modsContainer.querySelectorAll(".gb-mod-block")].some(b => b !== block && b.dataset.fresh)) {
          gbSectionCollapsed.add(itemName);
        }
        await refreshAfterChange();
        if (hasWarning) return;
        // Same reasoning as auto-checking a single download FILE: if this
        // character/course now has exactly one mergeable unit total, there's
        // no real choice to make in "Mods to merge" either, so save the
        // click - but only when it's not already checked/unchecked by hand.
        const freshEntry = findRosterEntry(itemName);
        const onlyUnit = freshEntry.units.length === 1 ? freshEntry.units[0] : null;
        if (onlyUnit && !state.checked[onlyUnit]) {
          state.checked[onlyUnit] = true;
          await pywebview.api.save_checked(state.checked);
          await refreshAfterChange();
        }
      });
      actions.appendChild(dlBtn);
      blockBody.appendChild(actions);
      block._dlBtn = dlBtn;
      block._blockBody = blockBody;
    }
    // a mod nothing has been downloaded from yet
    if (mod.files.length && !mod.files.some(f => ["downloaded", "ui_assets", "missing_romfs", "needs_manual_fix"].includes(f.download_status))) {
      block.dataset.fresh = "1";
    }

    setBlockCollapsed(gbModBlockCollapsed.has(blockKey));
    block.appendChild(main);
    return block;
  }

  async function loadTrackedMods() {
    modsContainer.replaceChildren(loadingNote("Loading your mods..."));
    const mods = await pywebview.api.gb_get_saved_mods(itemName);
    modsContainer.innerHTML = "";
    const target = gbJustAdded && gbJustAdded.item === itemName ? gbJustAdded : null;
    for (const mod of mods) {
      const block = buildModBlock(mod);
      modsContainer.appendChild(block);
      if (target && String(mod.mod_id) === target.modId && (mod.record_type || "Mod") === target.type) {
        gbJustAdded = null;
        focusAddedMod(block, mod);
      }
    }
  }
  loadTrackedMods();

  return card;
}

// Builds text nodes with the first occurrence of `needle` wrapped in <b> -
// DOM-built, never innerHTML, since the text itself comes from a remote mod
// description and must never be treated as markup.
function highlightFirstMatch(text, needle) {
  const frag = document.createDocumentFragment();
  if (!needle) {
    frag.appendChild(document.createTextNode(text));
    return frag;
  }
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx === -1) {
    frag.appendChild(document.createTextNode(text));
    return frag;
  }
  frag.appendChild(document.createTextNode(text.slice(0, idx)));
  const b = document.createElement("b");
  b.textContent = text.slice(idx, idx + needle.length);
  frag.appendChild(b);
  frag.appendChild(document.createTextNode(text.slice(idx + needle.length)));
  return frag;
}

function openGbBrowseModal(itemName, category, onUseMod) {
  const backdrop = document.getElementById("gb-browse-modal-backdrop");
  const titleEl = document.getElementById("gb-browse-modal-title");
  const resultsEl = document.getElementById("gb-browse-modal-results");
  const sortSelect = document.getElementById("gb-browse-modal-sort");
  const isCourse = category === "courses";
  const isSimple = SIMPLE_CATEGORIES.some(c => c.key === category);
  const isVehicle = VEHICLE_SECTION_KEYS.includes(category);
  titleEl.textContent = `Browse GameBanana — ${itemName}`;
  sortSelect.hidden = isCourse; // course search has no sort support, relevance-ordered only
  // GameBanana's "Most Liked" paging repeats/skips mods in the big vehicle
  // categories (verified), so vehicle parts default to Most Viewed instead.
  sortSelect.value = isVehicle ? "most_viewed" : "most_liked";

  let page = 1;
  let likelyOnly = false; // vehicle parts only: hide mods not matched to this part

  function renderCharacterGridResults(result) {
    if (result.subcategory_id === null) {
      resultsEl.innerHTML = '<div class="gb-browse-status">No matching GameBanana category found for this character - paste a link instead.</div>';
      return;
    }
    if (result.records.length === 0) {
      resultsEl.innerHTML = '<div class="gb-browse-status">No mods found.</div>';
      return;
    }
    let records = result.records;
    if (isVehicle) {
      // GameBanana has no per-part subcategory, so this lists every mod of
      // this KIND; each tile's badge is the part its description says it
      // replaces - a guess from the text, confirmed for real only once the
      // download's own files are checked.
      const toolbar = document.createElement("label");
      toolbar.className = "gb-target-toolbar";
      const likelyBox = document.createElement("input");
      likelyBox.type = "checkbox";
      likelyBox.checked = likelyOnly;
      likelyBox.addEventListener("change", () => { likelyOnly = likelyBox.checked; render(); });
      toolbar.appendChild(likelyBox);
      toolbar.appendChild(document.createTextNode(
        `Only show mods that look like they replace ${itemName} (badges are guessed from each mod's description)`
      ));
      resultsEl.appendChild(toolbar);
      if (likelyOnly) records = records.filter(r => (r.targets || []).includes(itemName));
      if (records.length === 0) {
        const none = document.createElement("div");
        none.className = "gb-browse-status";
        none.textContent = "No mods on this page look like they replace this part - try the next page, or untick the filter.";
        resultsEl.appendChild(none);
        return;
      }
    }
    const grid = document.createElement("div");
    grid.className = "gb-browse-grid";
    for (const rec of records) {
      const tile = document.createElement("div");
      tile.className = "gb-browse-tile";
      tile.title = "View details";
      tile.addEventListener("click", () => openGbDetailModal(rec.mod_id, onUseMod));
      if (rec.thumbnail_url) {
        const img = document.createElement("img");
        img.src = rec.thumbnail_url;
        img.alt = "";
        tile.appendChild(img);
      }
      const nameEl = document.createElement("div");
      nameEl.className = "gb-browse-name";
      nameEl.textContent = rec.name;
      tile.appendChild(nameEl);
      const metaEl = document.createElement("div");
      metaEl.className = "gb-browse-meta";
      metaEl.textContent = `${rec.like_count} ♥ · ${rec.view_count} views`;
      tile.appendChild(metaEl);
      if (isVehicle && (rec.targets || []).length > 0) {
        const isThisPart = rec.targets.includes(itemName);
        const verb = rec.target_strength >= 2 ? "Replaces" : "Mentions";
        const badge = document.createElement("span");
        badge.className = "gb-target-badge" + (isThisPart ? " match" : "");
        badge.textContent = isThisPart
          ? `✓ ${verb} ${itemName}`
          : `${verb} ${rec.targets.slice(0, 2).join(", ")}${rec.targets.length > 2 ? "…" : ""}`;
        badge.title = rec.target_strength >= 2
          ? "Guessed from a 'goes over / replaces' phrase or a file name in the mod's description."
          : "Only mentioned in the title or description - a weaker guess.";
        tile.appendChild(badge);
      }
      grid.appendChild(tile);
    }
    resultsEl.appendChild(grid);
  }

  function renderCourseSearchResults(result) {
    if (result.records.length === 0) {
      resultsEl.innerHTML = '<div class="gb-browse-status">No matching course mods found. GameBanana search can miss mods whose description phrases things differently - try browsing gamebanana.com directly, or paste a link if you already found one.</div>';
      return;
    }
    const hint = document.createElement("div");
    hint.className = "gb-browse-status";
    hint.textContent = "Read each snippet (or open it) to confirm what it actually replaces before using it - titles are often unrelated to the real target course.";
    resultsEl.appendChild(hint);

    const list = document.createElement("div");
    list.className = "gb-search-list";
    for (const rec of result.records) {
      const row = document.createElement("div");
      row.className = "gb-search-row";
      row.title = "View details";
      row.addEventListener("click", () => openGbDetailModal(rec.mod_id, onUseMod));

      if (rec.thumbnail_url) {
        const img = document.createElement("img");
        img.className = "gb-search-thumb";
        img.src = rec.thumbnail_url;
        img.alt = "";
        row.appendChild(img);
      }

      const main = document.createElement("div");
      main.className = "gb-search-main";

      const nameRow = document.createElement("div");
      nameRow.className = "gb-search-name-row";
      const nameEl = document.createElement("span");
      nameEl.className = "gb-search-name";
      nameEl.textContent = rec.name;
      nameRow.appendChild(nameEl);
      if (rec.subcategory) {
        const badge = document.createElement("span");
        badge.className = "gb-search-subcat";
        badge.textContent = rec.subcategory;
        nameRow.appendChild(badge);
      }
      main.appendChild(nameRow);

      const metaEl = document.createElement("div");
      metaEl.className = "gb-browse-meta";
      metaEl.textContent = `${rec.like_count} ♥ · ${rec.view_count} views`;
      main.appendChild(metaEl);

      if (rec.description_snippet) {
        const snippet = document.createElement("div");
        snippet.className = "gb-search-snippet";
        snippet.appendChild(highlightFirstMatch(rec.description_snippet, result.query));
        main.appendChild(snippet);
      }

      row.appendChild(main);
      list.appendChild(row);
    }
    resultsEl.appendChild(list);
  }

  async function render() {
    resultsEl.replaceChildren(loadingNote(isCourse ? "Searching GameBanana for this course..." : "Loading mods from GameBanana..."), skeletonGrid(8));
    const result = isCourse
      ? await pywebview.api.gb_browse_course(itemName, page)
      : isSimple
        ? await pywebview.api.gb_browse_simple(category, page, sortSelect.value)
        : isVehicle
          ? await pywebview.api.gb_browse_vehicle(itemName, page, sortSelect.value)
          : await pywebview.api.gb_browse(itemName, page, sortSelect.value);
    resultsEl.innerHTML = "";
    if (result.error) {
      resultsEl.innerHTML = `<div class="gb-browse-status">Couldn't load: ${result.error}</div>`;
      return;
    }

    if (isCourse) {
      renderCourseSearchResults(result);
    } else {
      renderCharacterGridResults(result);
    }

    const pager = document.createElement("div");
    pager.className = "gb-browse-pager";
    const prevBtn = document.createElement("button");
    prevBtn.className = "ghost small";
    prevBtn.textContent = "← Prev";
    prevBtn.disabled = page <= 1;
    prevBtn.addEventListener("click", () => { page -= 1; render(); });
    const pageInfo = document.createElement("span");
    const totalPages = Math.max(1, Math.ceil(result.total / result.per_page));
    pageInfo.textContent = `Page ${page} of ${totalPages} · ${result.total} mods`;
    const nextBtn = document.createElement("button");
    nextBtn.className = "ghost small";
    nextBtn.textContent = "Next →";
    nextBtn.disabled = result.is_complete || page >= totalPages;
    nextBtn.addEventListener("click", () => { page += 1; render(); });
    pager.appendChild(prevBtn);
    pager.appendChild(pageInfo);
    pager.appendChild(nextBtn);
    resultsEl.appendChild(pager);
  }

  sortSelect.onchange = () => { page = 1; render(); };
  render();

  backdrop.hidden = false;
}

function closeGbBrowseModal() {
  document.getElementById("gb-browse-modal-backdrop").hidden = true;
}

document.getElementById("btn-gb-browse-modal-close").addEventListener("click", closeGbBrowseModal);
document.getElementById("gb-browse-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "gb-browse-modal-backdrop") closeGbBrowseModal();
});

async function openGbDetailModal(modId, onUseMod) {
  const backdrop = document.getElementById("gb-detail-modal-backdrop");
  const titleEl = document.getElementById("gb-detail-modal-title");
  const bodyEl = document.getElementById("gb-detail-modal-body");
  const viewMoreBtn = document.getElementById("btn-gb-detail-view-more");
  const useBtn = document.getElementById("btn-gb-detail-use-mod");

  titleEl.textContent = "Loading...";
  bodyEl.replaceChildren(loadingNote("Getting the mod's page..."), skeleton("100%", 180, "10px"), skeleton("70%", 14), skeleton("55%", 14));
  viewMoreBtn.disabled = true;
  useBtn.disabled = true;
  useBtn.textContent = "Use this mod";
  backdrop.hidden = false;

  const result = await pywebview.api.gb_preview_mod(modId);
  if (!result.success) {
    titleEl.textContent = "Couldn't load mod";
    bodyEl.innerHTML = `<div class="gb-browse-status">${result.error}</div>`;
    return;
  }

  const mod = result.mod;
  titleEl.textContent = mod.name;
  bodyEl.innerHTML = "";

  const layout = document.createElement("div");
  layout.className = "gb-detail-layout";

  const main = document.createElement("div");
  main.className = "gb-detail-main";
  const thumbUrl = mod.thumbnail_url_large || mod.thumbnail_url;
  if (thumbUrl) {
    const img = document.createElement("img");
    img.className = "gb-detail-thumb";
    img.src = thumbUrl;
    img.alt = "";
    main.appendChild(img);
  }
  const desc = document.createElement("div");
  desc.className = "gb-detail-desc";
  desc.textContent = mod.description || "No description provided.";
  main.appendChild(desc);
  layout.appendChild(main);

  const side = document.createElement("div");
  side.className = "gb-detail-side";
  const statEntries = [
    ["Author", mod.author, false],
    ["Last Updated", mod.updated_at, false],
    ["Downloads", mod.download_count, true],
    ["Views", mod.view_count, true],
    ["Likes", mod.like_count, true],
  ];
  if (mod.version) {
    statEntries.splice(1, 0, ["Version", mod.version, false]);
  }
  for (const [label, value, numeric] of statEntries) {
    const stat = document.createElement("div");
    stat.className = "gb-detail-stat";
    const num = document.createElement("div");
    num.className = "gb-detail-stat-num";
    num.textContent = numeric ? (value || 0).toLocaleString() : (value || "?");
    const lbl = document.createElement("div");
    lbl.className = "gb-detail-stat-label";
    lbl.textContent = label;
    stat.appendChild(num);
    stat.appendChild(lbl);
    side.appendChild(stat);
  }

  if (mod.tags && mod.tags.length > 0) {
    const tagsBox = document.createElement("div");
    tagsBox.className = "gb-detail-stat gb-detail-tags-box";
    const lbl = document.createElement("div");
    lbl.className = "gb-detail-stat-label";
    lbl.textContent = "Tags";
    tagsBox.appendChild(lbl);
    const list = document.createElement("div");
    list.className = "gb-tag-list";
    for (const tag of mod.tags.slice(0, 6)) {
      const chip = document.createElement("span");
      chip.className = "gb-tag-chip";
      chip.textContent = tag;
      list.appendChild(chip);
    }
    if (mod.tags.length > 6) {
      const more = document.createElement("div");
      more.className = "gb-tag-more";
      more.textContent = `+${mod.tags.length - 6} more`;
      list.appendChild(more);
    }
    tagsBox.appendChild(list);
    side.appendChild(tagsBox);
  }

  layout.appendChild(side);

  bodyEl.appendChild(layout);

  viewMoreBtn.disabled = false;
  viewMoreBtn.onclick = () => pywebview.api.gb_open_url(mod.profile_url);

  useBtn.disabled = false;
  useBtn.onclick = async () => {
    useBtn.disabled = true;
    useBtn.textContent = "Adding...";
    const ok = await onUseMod(String(mod.mod_id));
    if (ok) {
      useBtn.textContent = "Added ✓";
    } else {
      useBtn.disabled = false;
      useBtn.textContent = "Use this mod";
    }
  };
}

function closeGbDetailModal() {
  document.getElementById("gb-detail-modal-backdrop").hidden = true;
}

document.getElementById("btn-gb-detail-modal-close").addEventListener("click", closeGbDetailModal);
document.getElementById("gb-detail-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "gb-detail-modal-backdrop") closeGbDetailModal();
});

