// Full List's section headers are literally the mods/extracted/<category>/
// folder name (see discover_mods() - it's fully generic, so any new
// category, including the SIMPLE_CATEGORIES ones, shows up here on its
// own with zero extra wiring) - this just maps the raw lowercase folder
// name to the same display label used everywhere else in the app, instead
// of printing "mechanics"/"ui" as-is.
function categoryDisplayName(key) {
  if (key === "characters") return "Characters";
  if (key === "courses") return "Courses";
  if (key === "other") return "Other";
  const simple = SIMPLE_CATEGORIES.find(c => c.key === key);
  if (simple) return simple.label;
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function renderListView() {
  const container = document.getElementById("checklist");
  container.innerHTML = "";
  const cats = Object.keys(state.categories);
  if (cats.length === 0) {
    container.innerHTML = '<div id="empty-msg">No mods found. Expected mods/extracted/&lt;category&gt;/&lt;mod name&gt;/romfs/ under your master directory.</div>';
    return;
  }
  // Code-patch (exefs) unit keys, filled in asynchronously below. Like the
  // per-item modal's Select All, a category's Select All skips these - a code
  // patch is always a deliberate individual tick.
  const exefsKeys = new Set();
  const categoryToggles = []; // { toggleBtn, checkboxes: [{ key, cb }] } per category
  const selectableOf = (checkboxes) => checkboxes.filter(({ key }) => !exefsKeys.has(key) && !skipsSelectAll(key));
  loadUnitSlots(Object.keys(state.categories).flatMap(c => state.categories[c].map(u => c + "/" + u))).then(() => refreshToggleLabels());
  function refreshToggleLabels() {
    for (const { toggleBtn, checkboxes } of categoryToggles) {
      const selectable = selectableOf(checkboxes);
      const allChecked = selectable.length > 0 && selectable.every(({ cb }) => cb.checked);
      toggleBtn.textContent = allChecked ? "Deselect All" : "Select All";
      toggleBtn.disabled = selectable.length === 0;
    }
  }

  for (const cat of cats) {
    const box = document.createElement("div");
    box.className = "category";
    const h2 = document.createElement("h2");
    h2.className = "category-header-with-action";
    const h2Text = document.createElement("span");
    h2Text.textContent = categoryDisplayName(cat);
    h2.appendChild(h2Text);
    const toggleBtn = document.createElement("button");
    toggleBtn.className = "ghost small";
    h2.appendChild(toggleBtn);
    box.appendChild(h2);
    const checkboxes = [];
    categoryToggles.push({ toggleBtn, checkboxes });
    toggleBtn.addEventListener("click", () => {
      const selectable = selectableOf(checkboxes);
      const target = !(selectable.length > 0 && selectable.every(({ cb }) => cb.checked));
      // Select All ticks the sensible ones; Deselect All unticks everything in the category
      for (const { key, cb } of (target ? selectable : checkboxes.filter(({ key }) => !exefsKeys.has(key)))) {
        cb.checked = target;
        state.checked[key] = target;
      }
      pywebview.api.save_checked(state.checked);
      refreshToggleLabels();
      refreshBehindModal();
    });
    for (const unit of state.categories[cat]) {
      const key = cat + "/" + unit;
      const row = document.createElement("div");
      row.className = "mod-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.checked[key];
      cb.id = "cb_" + key;
      checkboxes.push({ key, cb });
      cb.addEventListener("change", () => {
        state.checked[key] = cb.checked;
        pywebview.api.save_checked(state.checked);
        refreshToggleLabels();
        refreshBehindModal();
      });
      const label = document.createElement("label");
      label.textContent = unit;
      label.setAttribute("for", cb.id);
      row.appendChild(cb);
      row.appendChild(label);
      const alsoBadge = buildAlsoShipsBadge(key);
      if (alsoBadge) row.appendChild(alsoBadge);
      row.appendChild(buildRemoveModButton(key, loadMods));
      box.appendChild(row);
    }
    container.appendChild(box);
  }
  refreshToggleLabels();

  const allKeys = cats.flatMap(cat => state.categories[cat].map(unit => cat + "/" + unit));
  pywebview.api.get_exefs_unit_info(allKeys).then(info => {
    for (const key of Object.keys(info || {})) exefsKeys.add(key);
    refreshToggleLabels();
  });
}

function renderAll() {
  scheduleFlowRefresh();
  updateTabCounts();
  renderCharacterGrid();
  renderCupOrCourseGrid();
  renderVehiclesView();
  renderMoreList();
  renderListView();
  refreshStats();
}

// A mod's "also ships" badge: this mod (filed under a character, course, or a
// different part) also includes model files for one or more vehicle parts -
// see Api.get_vehicle_links(). Read-only attribution: the mod stays a single
// unit where it was downloaded; clicking the badge opens the part it also
// ships. Returns null when there's nothing to show.
function buildAlsoShipsBadge(key) {
  const parts = state.vehicleLinks.by_unit[key];
  if (!parts || parts.length === 0) return null;
  const badge = document.createElement("span");
  badge.className = "linked-badge";
  badge.textContent = parts.length === 1 ? `also ships: ${parts[0]}` : `also ships ${parts.length} vehicle parts`;
  badge.title = `This mod also includes model files for: ${parts.join(", ")}. Click to open ${parts[0]}.`;
  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    switchView("vehicles");
    openCharacterModal(parts[0]);
  });
  return badge;
}

const VEHICLE_BODY_GROUPS = [
  { type: "kart", label: "Karts" },
  { type: "bike", label: "Bikes" },
  { type: "atv", label: "ATVs" },
];

function renderVehiclesView() {
  const container = document.getElementById("vehicle-sections");
  container.innerHTML = "";
  for (const section of state.vehicles) {
    const box = document.createElement("div");
    box.className = "vehicle-section";
    const withMods = section.items.filter(i => i.units.length > 0).length;
    const heading = document.createElement("div");
    heading.className = "vehicle-section-heading";
    heading.appendChild(document.createTextNode(section.label));
    const summary = document.createElement("span");
    summary.className = "vehicle-section-summary";
    summary.textContent = `${withMods}/${section.items.length} with mods`;
    heading.appendChild(summary);
    box.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "vehicle-grid";
    const buildItemTile = (item) => {
      const { tile, checkedUnits } = buildTile(
        item.name, item.units, () => openCharacterModal(item.name), item.gb_attempted,
        { overlayCount: true, hideBadge: true }
      );
      // Mods filed elsewhere that also ship this part's model file. Shown as
      // a small marker only - never added to the X/Y count, the section
      // summary, or any footer stat, which stay about mods chosen for this part.
      const linked = state.vehicleLinks.by_item[item.name] || [];
      if (linked.length > 0) {
        tile.classList.add("has-linked");
        const mark = document.createElement("div");
        mark.className = "char-linked-mark";
        mark.textContent = `${linked.length} linked mod${linked.length === 1 ? "" : "s"}`;
        mark.title = "Also ships this part's model file: " + linked.map(k => k.split("/").slice(1).join("/")).join("; ");
        tile.appendChild(mark);
      }
      const conflictPool = checkedUnits.concat(linked.filter(k => state.checked[k]));
      if (conflictPool.length >= 2) {
        pywebview.api.check_conflicts(conflictPool).then(result => {
          if (result.conflicts && result.conflicts.length > 0) {
            tile.classList.add("has-conflict");
            const badge = document.createElement("div");
            badge.className = "char-conflict-badge";
            badge.textContent = "!";
            badge.title = `${result.conflicts.length} conflicting file(s) among selected mods`;
            tile.appendChild(badge);
          }
        });
      }
      return tile;
    };
    if (section.key === "vehicles") {
      // Bodies split into Karts / Bikes / ATVs, the way the game's own parts
      // menu does.
      for (const group of VEHICLE_BODY_GROUPS) {
        const groupItems = section.items.filter(i => i.type === group.type);
        if (groupItems.length === 0) continue;
        const sub = document.createElement("div");
        sub.className = "vehicle-subheading";
        sub.textContent = group.label;
        grid.appendChild(sub);
        for (const item of groupItems) grid.appendChild(buildItemTile(item));
      }
    } else {
      for (const item of section.items) grid.appendChild(buildItemTile(item));
    }
    box.appendChild(grid);
    container.appendChild(box);
  }
}

function renderMoreList() {
  const container = document.getElementById("more-list");
  container.innerHTML = "";
  const card = document.createElement("div");
  card.className = "category";
  for (const c of SIMPLE_CATEGORIES) {
    const entry = state.simpleCategories.find(sc => sc.key === c.key) || { units: [], gb_attempted: false };
    const total = entry.units.length;
    const selected = entry.units.filter(k => state.checked[k]).length;

    const row = document.createElement("div");
    row.className = "more-row";
    row.addEventListener("click", () => openCharacterModal(c.label));

    const name = document.createElement("div");
    name.className = "more-row-name";
    name.textContent = c.label;
    row.appendChild(name);

    const count = document.createElement("div");
    count.className = "more-row-count";
    if (entry.gb_attempted && total === 0) count.classList.add("count-attention");
    count.textContent = total === 0
      ? (entry.gb_attempted ? "needs attention" : "no mods yet")
      : `${selected}/${total} selected`;
    row.appendChild(count);

    const arrow = document.createElement("div");
    arrow.className = "more-row-arrow";
    arrow.textContent = "›";
    row.appendChild(arrow);

    card.appendChild(row);
  }
  container.appendChild(card);
}

async function renderCupOrCourseGrid() {
  await renderCupGrid();
  await renderCourseStrip(selectedCup);
}

async function renderCupGrid() {
  const grid = document.getElementById("cup-grid");
  grid.innerHTML = "";
  courseHover.hide();   // the tile under the mouse was just replaced
  const conflictChecks = [];

  for (const cup of state.cups) {
    if (cup.cup === DLC_CUP_START) {
      const heading = document.createElement("div");
      heading.className = "cup-grid-dlc-heading";
      heading.textContent = "DLC Courses";
      grid.appendChild(heading);
    }

    const units = cup.courses.flatMap(c => c.units);
    const checkedUnits = units.filter(k => state.checked[k]);
    const selected = checkedUnits.length;
    const moddedCourses = cup.courses.filter(c => c.units.some(u => state.checked[u])).length;
    const tile = document.createElement("div");
    tile.className = "cup-tile";
    if (selected > 0) tile.classList.add("has-selected");
    if (cup.cup === selectedCup) tile.classList.add("active");
    tile.addEventListener("click", () => {
      if (selectedCup === cup.cup) return;
      document.querySelectorAll("#cup-grid .cup-tile.active").forEach(t => t.classList.remove("active"));
      tile.classList.add("active");
      renderCourseStrip(cup.cup);
    });

    const emoji = document.createElement("div");
    emoji.className = "cup-emoji";
    emoji.textContent = CUP_EMOJI[cup.cup] || "\u{1F3C1}";
    emoji.setAttribute("aria-hidden", "true");
    tile.appendChild(emoji);

    const name = document.createElement("div");
    name.className = "cup-name";
    name.textContent = cup.cup;
    tile.appendChild(name);

    const count = document.createElement("div");
    count.className = "cup-count";
    count.textContent = `${moddedCourses}/${cup.courses.length} courses modded`;
    tile.appendChild(count);

    if (selected >= 2) {
      conflictChecks.push(
        pywebview.api.check_conflicts(checkedUnits).then(result => {
          if (result.conflicts && result.conflicts.length > 0) {
            tile.classList.add("has-conflict");
            const conflictBadge = document.createElement("div");
            conflictBadge.className = "char-conflict-badge";
            conflictBadge.textContent = "!";
            conflictBadge.title = `${result.conflicts.length} conflicting file(s) among selected mods in this cup`;
            tile.appendChild(conflictBadge);
          }
        })
      );
    }

    grid.appendChild(tile);
  }
  await Promise.all(conflictChecks);
}

async function renderCourseStrip(cupName) {
  const cup = state.cups.find(c => c.cup === cupName) || state.cups[0];
  selectedCup = cup.cup;
  document.getElementById("course-strip-title").textContent = cup.cup;

  const strip = document.getElementById("course-strip");
  strip.innerHTML = "";
  courseHover.hide();

  // Checked once across the whole cup, not per course - a conflict can be
  // between mods checked under two *different* courses in the same cup (e.g.
  // a whole-wave bundle mod filed under one course also writing another
  // course's files), which a per-course-only check would never catch even
  // though it's exactly the kind of conflict that blocks committing.
  const allCupUnits = cup.courses.flatMap(c => c.units);
  const allCupChecked = allCupUnits.filter(k => state.checked[k]);
  const conflictingUnits = new Set();
  if (allCupChecked.length >= 2) {
    const result = await pywebview.api.check_conflicts(allCupChecked);
    for (const c of result.conflicts || []) {
      conflictingUnits.add(c.mods[0]);
      conflictingUnits.add(c.mods[1]);
    }
  }

  // One checked unit's course-select icon per course, fetched in parallel -
  // each course has at most one checked unit in practice, so this is a
  // small, bounded batch of calls per cup, not per course.
  const previewChecks = cup.courses.map(course => {
    const checkedUnits = course.units.filter(k => state.checked[k]);
    return checkedUnits.length
      ? pywebview.api.get_course_icon_preview(checkedUnits[0])
      : Promise.resolve(null);
  });
  const previews = await Promise.all(previewChecks);

  cup.courses.forEach((course, i) => {
    const { tile, checkedUnits, badge, nameEl } = buildTile(
      course.name, course.units,
      () => openCharacterModal(course.name), course.gb_attempted,
      { overlayCount: true }
    );
    if (checkedUnits.some(u => conflictingUnits.has(u))) {
      tile.classList.add("has-conflict");
      const conflictBadge = document.createElement("div");
      conflictBadge.className = "char-conflict-badge";
      conflictBadge.textContent = "!";
      conflictBadge.title = "This course's checked mod conflicts with another checked mod in this cup - open a course here to see which files.";
      tile.appendChild(conflictBadge);
    }
    // Shows the mod's own actual course-select picture when it has one, so
    // it's obvious at a glance which courses do/don't provide one - see the
    // Help page's "select-screen icon or results-screen background is
    // missing" entry for why plenty legitimately don't. The image comes
    // back already cropped to the visible content window (the backend
    // strips the black border every real CoursePict bakes in for the
    // game's own name-banner overlay to sit on top of), so we reproduce
    // that same banner here instead - see .course-pict-title above.
    if (previews[i]) {
      // Badge and plain name text are redundant once the picture + its own
      // title banner are showing - drop them instead of stacking on top.
      badge.remove();
      nameEl.remove();
      const wrap = document.createElement("div");
      wrap.className = "course-pict-wrap";
      const img = document.createElement("img");
      img.className = "course-pict-preview";
      img.src = previews[i];
      img.alt = "";
      img.title = "This mod's own in-game course-select picture";
      wrap.appendChild(img);
      const titleBanner = document.createElement("div");
      titleBanner.className = "course-pict-title";
      titleBanner.textContent = course.name;
      wrap.appendChild(titleBanner);
      tile.prepend(wrap);
    }
    strip.appendChild(tile);
  });
}

function switchView(mode) {
  viewMode = mode;
  flow.step = "mods";
  flow.lastModsView = mode;
  for (const id of Object.values(FLOW_PAGES)) document.getElementById(id).hidden = true;
  document.getElementById("tabs").hidden = false;
  renderStepBar();
  renderNextButton();
  document.getElementById("view-characters").hidden = mode !== "characters";
  document.getElementById("view-courses").hidden = mode !== "courses";
  document.getElementById("view-vehicles").hidden = mode !== "vehicles";
  document.getElementById("view-more").hidden = mode !== "more";
  document.getElementById("view-list").hidden = mode !== "list";
  document.getElementById("tab-characters").classList.toggle("active", mode === "characters");
  document.getElementById("tab-courses").classList.toggle("active", mode === "courses");
  document.getElementById("tab-vehicles").classList.toggle("active", mode === "vehicles");
  document.getElementById("tab-more").classList.toggle("active", mode === "more");
  document.getElementById("tab-list").classList.toggle("active", mode === "list");
  applyCharacterLayout();
  if (mode === "characters") {
    if (dockedLayout()) ensureDockedSelection();
    else if (dockedKey !== null) closeDetail();
  }
  markActiveTile();
}
document.getElementById("tab-characters").addEventListener("click", () => switchView("characters"));
document.getElementById("tab-courses").addEventListener("click", () => switchView("courses"));
document.getElementById("tab-vehicles").addEventListener("click", () => { switchView("vehicles"); renderVehiclesView(); });
document.getElementById("tab-more").addEventListener("click", () => { switchView("more"); renderMoreList(); });
document.getElementById("tab-list").addEventListener("click", () => switchView("list"));

function openSettingsModal() {
  renderGameFilesBlock(document.getElementById("gamefiles-body"), scheduleFlowRefresh);
  document.getElementById("settings-modal-backdrop").hidden = false;
  renderUiIconWorklist();
  renderUiSetupSettingsCard();
  renderConflicts();
}
function closeSettingsModal() {
  document.getElementById("settings-modal-backdrop").hidden = true;
}
document.getElementById("btn-settings").addEventListener("click", openSettingsModal);
document.getElementById("btn-settings-modal-close").addEventListener("click", closeSettingsModal);
document.getElementById("settings-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "settings-modal-backdrop") closeSettingsModal();
});

