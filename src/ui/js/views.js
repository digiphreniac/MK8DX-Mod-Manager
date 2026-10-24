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
      saveChecked();
      refreshToggleLabels();
      refreshBehindModal({ ifChanged: true });
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
        saveChecked();
        refreshToggleLabels();
        refreshBehindModal({ ifChanged: true });
      });
      const label = document.createElement("label");
      label.textContent = unit;
      label.setAttribute("for", cb.id);
      row.appendChild(cb);
      row.appendChild(label);
      const alsoBadge = buildPackBadge(key, null);
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

// Every screen is drawn from the same data, so a change (a tick, a download, a move) redraws all of them - but only the one being
// looked at is drawn right away. The others are drawn a moment later, one at a time, so they don't compete with it (each asks the
// backend for its own pictures and checks), and a screen is drawn the instant it is switched to if its turn hasn't come yet.
const VIEW_ORDER = ["characters", "courses", "vehicles", "items", "more", "list"];
const VIEW_DRAWERS = {
  characters: () => renderCharacterGrid(),
  courses: () => renderCupOrCourseGrid(),
  vehicles: () => renderVehiclesView(),
  items: () => renderItemsView(),
  more: () => renderMoreList(),
  list: () => renderListView(),
};
const staleViews = new Set();
let staleViewsTimer = null;

// What a screen is drawn from, as one string: each entry's name, which of its mods are ticked, and whether GameBanana was tried for it.
// A tick changes this for the screen it is on (and for a pack's other screens) and for no other, so redrawing only where it differs
// (redrawViews with ifChanged) skips the rest. Nothing else a screen shows is in it - so it is used for ticks only, never after
// something that changes how a tile looks (an icon, a name, a download).
function entriesSignature(entries) {
  return entries.map(e => `${e.name}:${(e.units || []).map(u => (state.checked[u] ? "1" : "0")).join("")}${e.gb_attempted ? "g" : ""}${notesSignature(e.units || [])}`).join("|");
}
function viewSignature(mode) {
  const counts = state.settings && state.settings.show_tile_counts ? "c" : "";
  switch (mode) {
    case "characters": return counts + entriesSignature(state.roster || []);
    case "courses": return counts + entriesSignature((state.cups || []).flatMap(c => c.courses)) + `@${selectedCup}`;
    case "vehicles": return counts + entriesSignature((state.vehicles || []).flatMap(s => s.items));
    case "items": return counts + entriesSignature(state.items || []);
    case "more": return counts + entriesSignature((state.simpleCategories || []).map(c => ({ name: c.key, units: c.units, gb_attempted: c.gb_attempted })));
    default: return null;   // (never skipped)
  }
}
const drawnSignature = {};
function drawView(mode) {
  drawnSignature[mode] = viewSignature(mode);
  VIEW_DRAWERS[mode]();
}

function drawViewIfStale(mode) {
  if (staleViews.delete(mode)) drawView(mode);
}

function drawStaleViewsSoon() {
  clearTimeout(staleViewsTimer);
  staleViewsTimer = setTimeout(() => {
    const next = VIEW_ORDER.find(m => staleViews.has(m));
    if (next === undefined) return;
    drawViewIfStale(next);
    drawStaleViewsSoon();
  }, 80);
}

// Redraws `modes` (default: all): the current one now, the rest in the background. With ifChanged, a screen whose data is what it
// was drawn from last time (see viewSignature) is left alone.
function redrawViews(modes = VIEW_ORDER, opts = {}) {
  const wanted = opts.ifChanged ? modes.filter(m => staleViews.has(m) || viewSignature(m) === null || viewSignature(m) !== drawnSignature[m]) : modes;
  for (const mode of wanted) if (mode !== viewMode) staleViews.add(mode);
  if (wanted.includes(viewMode)) { staleViews.delete(viewMode); drawView(viewMode); }
  drawStaleViewsSoon();
}

function renderAll() {
  scheduleFlowRefresh();
  updateTabCounts();
  redrawViews();
  refreshStats();
}

// A pack's badge on a mod row: this mod replaces more than one thing (see Api.get_pack_links), so it is listed on each of their
// cards. "Pack - also X" on the card of one of them; clicking it opens the next one. Null for a mod that is for just one thing.
function buildPackBadge(key, cardName) {
  const names = (state.packLinks.by_unit || {})[key];
  if (!names || names.length < 2) return null;
  const others = names.filter(n => n !== cardName);
  const badge = document.createElement("span");
  badge.className = "linked-badge";
  badge.textContent = others.length === 1 ? `Pack \u00b7 also ${refileLabel(others[0])}` : `Pack \u00b7 ${names.length} things`;
  badge.title = `This mod replaces ${names.map(refileLabel).join(", ")}. It is listed on each of their cards; selecting it turns on all of them. Click to open ${refileLabel(others[0])}.`;
  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    showRefileTarget(others[0]);
  });
  return badge;
}

// Line icons for the More tab's tiles (24x24, drawn with the text colour) - static markup, nothing from a remote page
const MORE_ICONS = {
  mechanics: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  ui: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18M9 9v11"/>',
  code_patches: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 6l-3 12"/>',
  modpacks: '<path d="M12 3 4 7v10l8 4 8-4V7z"/><path d="m4 7 8 4 8-4M12 11v10"/>',
  battle_courses: '<ellipse cx="12" cy="9.5" rx="5.5" ry="6.5"/><path d="M12 16l-1.6 2.2h3.2zM12 18.2c0 1.6-1.5 1.8-1.5 3.3"/>',
};
const MORE_FALLBACK_ICON = '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>';

// Opens a More category's card; with `browse`, also its GameBanana window (the tile's own button)
function openMoreCard(label, browse) {
  openCharacterModal(label);
  if (browse) {
    const btn = [...document.querySelectorAll(".gb-browse-toggle-row button")].find(b => b.dataset.item === label);
    if (btn) btn.click();
  }
}

// The More tab: one tile per category (Mechanics, UI, ...) - what it is for, how far along it is, and a way straight into
// GameBanana. A tile opens the same card characters and courses use.
function renderMoreList() {
  const container = document.getElementById("more-list");
  container.innerHTML = "";
  for (const c of SIMPLE_CATEGORIES) {
    const entry = state.simpleCategories.find(sc => sc.key === c.key) || { units: [], gb_attempted: false };
    const total = entry.units.length;
    const selected = entry.units.filter(k => state.checked[k]).length;
    const attention = entry.gb_attempted && total === 0;

    const tile = document.createElement("div");
    tile.className = "more-tile" + (selected ? " has-selected" : "") + (attention ? " needs-attention" : "");
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");
    tile.addEventListener("click", () => openMoreCard(c.label, false));
    tile.addEventListener("keydown", (e) => {
      if (e.target === tile && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openMoreCard(c.label, false); }
    });

    const head = document.createElement("div");
    head.className = "more-tile-head";
    const icon = document.createElement("div");
    icon.className = "more-icon";
    icon.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${MORE_ICONS[c.key] || MORE_FALLBACK_ICON}</svg>`;
    head.appendChild(icon);
    const name = document.createElement("div");
    name.className = "more-name";
    name.textContent = c.label;
    head.appendChild(name);
    tile.appendChild(head);

    const blurb = document.createElement("div");
    blurb.className = "more-blurb";
    blurb.textContent = c.blurb || "";
    tile.appendChild(blurb);

    const status = document.createElement("div");
    status.className = "more-status";
    if (attention) {
      status.classList.add("attention");
      status.textContent = "A mod was added here but has no usable files yet - open it to finish or fix.";
    } else if (total === 0) {
      status.textContent = "Nothing here yet.";
    } else {
      const text = document.createElement("div");
      text.className = "more-status-text";
      text.textContent = `${total} ${total === 1 ? "mod" : "mods"} · ${selected} selected`;
      status.appendChild(text);
      const bar = document.createElement("div");
      bar.className = "more-bar";
      const fill = document.createElement("div");
      fill.className = "more-bar-fill";
      fill.style.width = `${Math.round(100 * selected / total)}%`;
      bar.appendChild(fill);
      status.appendChild(bar);
    }
    tile.appendChild(status);

    const actions = document.createElement("div");
    actions.className = "more-actions";
    actions.appendChild(button("Browse GameBanana ↗", total === 0 && !attention ? "primary small" : "ghost small", (e) => {
      e.stopPropagation();
      openMoreCard(c.label, true);
    }));
    tile.appendChild(actions);
    container.appendChild(tile);
  }
}

// ---- Course Select ----
// The Prix (cup) medallions on a board, the selected cup's four courses under it, and - like Character Select - a
// name plate along the bottom: the selected cup (or the selected course), or whatever tile the mouse is over. The
// whole screen is sized to fit the window with no scrolling (fitCourseScreen).

// The game's own medallions, {cup name: PNG data URI}, from the app's copy of the game files (Api.get_cup_icons).
// {} when that copy isn't there yet: the tiles then keep their emoji until it is.
let cupIcons = {};
let cupIconsPending = null;
function loadCupIcons() {
  if (Object.keys(cupIcons).length) return Promise.resolve();
  if (!cupIconsPending) {
    cupIconsPending = pywebview.api.get_cup_icons()
      .then(r => { cupIcons = r || {}; }, () => { cupIcons = {}; })
      .finally(() => { cupIconsPending = null; });
  }
  return cupIconsPending;
}

function paintCupTile(tile) {
  const src = cupIcons[tile.dataset.cup];
  tile.classList.toggle("no-art", !src);
  const art = tile.querySelector(".cup-icon, .cup-emoji");
  let el;
  if (src) {
    if (art && art.tagName === "IMG") { if (art.src !== src) art.src = src; return; }
    el = document.createElement("img");
    el.className = "cup-icon";
    el.src = src;
    el.alt = "";
    el.draggable = false;
  } else {
    if (art && art.classList.contains("cup-emoji")) return;
    el = document.createElement("div");
    el.className = "cup-emoji";
    el.textContent = CUP_EMOJI[tile.dataset.cup] || "\u{1F3C1}";
    el.setAttribute("aria-hidden", "true");
  }
  if (art) art.replaceWith(el); else tile.prepend(el);
}

let cupGridToken = 0, courseStripToken = 0;   // a newer render supersedes an older one that is still waiting on the backend

async function renderCupOrCourseGrid() {
  const icons = loadCupIcons();
  await renderCupGrid();
  await renderCourseStrip(selectedCup);
  fitCourseScreen();
  refreshCourseReview();
  icons.then(() => { for (const t of document.querySelectorAll("#cup-grid .cup-tile")) paintCupTile(t); });
}

async function renderCupGrid() {
  const grid = document.getElementById("cup-grid");
  const token = ++cupGridToken;
  courseHover.hide();   // the tile under the mouse was just replaced
  const conflictChecks = [];
  const tiles = [];

  for (const cup of state.cups) {
    const units = cup.courses.flatMap(c => c.units);
    const checkedUnits = units.filter(k => state.checked[k]);
    const selected = checkedUnits.length;
    const moddedCourses = cup.courses.filter(c => c.units.some(u => state.checked[u])).length;
    const tile = document.createElement("div");
    tile.className = "cup-tile";
    tile.dataset.cup = cup.cup;
    tile.setAttribute("role", "button");
    tile.setAttribute("aria-label", cup.cup);
    tile.dataset.page = cupPageOf(cup.cup);
    if (selected > 0) tile.classList.add("has-selected");
    else tile.classList.add("no-mods");
    if (cup.cup === selectedCup) tile.classList.add("active");
    tile.addEventListener("click", () => {
      if (selectedCup === cup.cup) {
        if (selectedCourse !== null) { selectedCourse = null; markActiveCourse(); }   // back to the cup itself
        return;
      }
      document.querySelectorAll("#cup-grid .cup-tile.active").forEach(t => t.classList.remove("active"));
      tile.classList.add("active");
      selectedCourse = null;
      renderCourseStrip(cup.cup);
    });
    paintCupTile(tile);

    if (moddedCourses > 0) {
      const bubble = document.createElement("div");
      bubble.className = "tile-count-bubble";
      bubble.textContent = `${moddedCourses}/${cup.courses.length}`;
      tile.appendChild(bubble);
    }

    if (selected >= 2) {
      conflictChecks.push(
        conflictCount(checkedUnits).then(n => {
          if (n > 0) {
            tile.classList.add("has-conflict");
            const conflictBadge = document.createElement("div");
            conflictBadge.className = "char-conflict-badge";
            conflictBadge.textContent = "!";
            conflictBadge.title = `${n} conflicting file(s) among selected mods in this cup`;
            tile.appendChild(conflictBadge);
          }
        })
      );
    }
    tiles.push(tile);
  }
  await Promise.all(conflictChecks);
  if (token !== cupGridToken) return;   // a newer render is under way; let that one fill the board
  for (const t of tiles) t.classList.toggle("active", t.dataset.cup === selectedCup);   // (it may have changed while this waited)
  grid.replaceChildren(...tiles);
  cupPages.current = cupPageOf(selectedCup);   // (a re-render follows the selected cup to its page)
  applyCupPage();
  updateCourseNameBar();
}

// The game's own course pictures, kept once fetched (they only change when the game's files do - resetPictureCaches); a course
// that has none yet is asked for again next time, since they may appear once the game's files are set up.
const courseDefaultPictures = {};
async function loadCourseDefaults(names) {
  const missing = names.filter(n => !courseDefaultPictures[n]);
  if (missing.length) {
    let got = null;
    try { got = await pywebview.api.get_course_default_pictures(missing); } catch (e) { got = null; }
    for (const n of missing) if (got && got[n]) courseDefaultPictures[n] = got[n];
  }
  const out = {};
  for (const n of names) if (courseDefaultPictures[n]) out[n] = courseDefaultPictures[n];
  return out;
}

async function renderCourseStrip(cupName) {
  const cup = state.cups.find(c => c.cup === cupName) || state.cups[0];
  if (!cup) return;
  selectedCup = cup.cup;
  if (selectedCourse !== null && !cup.courses.some(c => c.name === selectedCourse)) selectedCourse = null;
  const token = ++courseStripToken;
  courseHover.hide();
  updateCourseNameBar();

  const strip = document.getElementById("course-strip");

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
  // ...and the game's own picture for every course, for the ones with no picture from a mod (the base game files hold them)
  const defaultsCheck = loadCourseDefaults(cup.courses.map(c => c.name));
  const previews = await Promise.all(previewChecks);
  const defaults = (await defaultsCheck) || {};
  if (token !== courseStripToken) return;   // a newer render (another cup, say) is under way; let that one fill the strip

  const tiles = cup.courses.map((course, i) => {
    const { tile, checkedUnits, badge, nameEl } = buildTile(
      course.name, course.units,
      () => { selectCourse(course.name); openCharacterModal(course.name); }, course.gb_attempted,
      { overlayCount: true }
    );
    if (course.name === selectedCourse) tile.classList.add("active");
    if (checkedUnits.some(u => conflictingUnits.has(u))) {
      tile.classList.add("has-conflict");
      const conflictBadge = document.createElement("div");
      conflictBadge.className = "char-conflict-badge";
      conflictBadge.textContent = "!";
      conflictBadge.title = "This course's selected mod conflicts with another selected mod in this cup - open a course here to see which files.";
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
    const shown = previews[i] || defaults[course.name];
    if (shown) {
      // Badge and plain name text are redundant once the picture + its own
      // title banner are showing - drop them instead of stacking on top.
      badge.remove();
      nameEl.remove();
      const wrap = document.createElement("div");
      wrap.className = "course-pict-wrap";
      const img = document.createElement("img");
      img.className = "course-pict-preview";
      img.src = shown;
      img.alt = "";
      img.title = previews[i] ? "This mod's own in-game course-select picture" : "The game's own course-select picture";
      if (!previews[i]) tile.classList.add("default-pict");
      wrap.appendChild(img);
      const titleBanner = document.createElement("div");
      titleBanner.className = "course-pict-title";
      titleBanner.textContent = course.name;
      wrap.appendChild(titleBanner);
      tile.prepend(wrap);
    }
    return tile;
  });
  strip.replaceChildren(...tiles);
  updateCourseNameBar();
  applyCourseMarkers();
}

// What each course with ticked mods still needs (Api.get_course_tile_view -> courseReview): the small marker on its tile
// (amber = its name and/or picture still needs a look, green tick = done; nothing for a course with nothing to check),
// the "N to finish" on the step bar, and what the "aren't finished" prompt lists. `now` skips the short wait that lets
// the tick which caused a re-render reach the disk.
let courseReviewTimer = null, courseReviewToken = 0;
function refreshCourseReview(now) {
  const token = ++courseReviewToken;
  clearTimeout(courseReviewTimer);
  const run = async () => {
    const names = state.cups.flatMap(c => c.courses).filter(c => c.units.some(u => state.checked[u])).map(c => c.name);
    let view = {};
    if (names.length) {
      try { view = await pywebview.api.get_course_tile_view(names) || {}; } catch (e) { return; }
    }
    if (token !== courseReviewToken) return;   // (a newer render is waiting for its own answer)
    courseReview = view;
    applyCourseMarkers();
    try { if (flow.status) { renderStepBar(); renderNextButton(); } } catch (e) { /* (the flow bar isn't up yet) */ }
  };
  if (now) return run();
  courseReviewTimer = setTimeout(run, 400);
}
function markCourseTiles() { refreshCourseReview(true); }   // (after a step of a course card was settled)
function applyCourseMarkers() {
  for (const tile of document.querySelectorAll("#course-strip .char-tile")) {
    tile.querySelectorAll(".tile-review-mark").forEach(e => e.remove());
    const r = courseReview[tile.dataset.char];
    if (!r || !r.applicable) continue;
    const mark = document.createElement("div");
    mark.className = "tile-review-mark " + (r.finished ? "done" : "todo");
    mark.title = r.finished ? "Completed" : "Selected - open it to finish its name and picture";
    if (r.finished) mark.textContent = "\u2713";
    tile.appendChild(mark);
  }
}

// Opens a course's card on Course Select: the right Prix selected, the course selected, its card up.
async function openCourseCard(courseName) {
  const cup = state.cups.find(c => c.courses.some(x => x.name === courseName));
  if (!cup) return;
  switchView("courses");
  selectedCup = cup.cup;
  selectedCourse = courseName;
  await renderCupOrCourseGrid();
  openCharacterModal(courseName);
}

// ---- the selected course ----
// Clicking a course selects it (yellow corner brackets, its name on the plate) and opens its card. Choosing another
// cup, or clicking the selected cup again, goes back to showing the cup.
function selectCourse(name) {
  selectedCourse = name;
  markActiveCourse();
}
function markActiveCourse() {
  for (const t of document.querySelectorAll("#course-strip .char-tile")) t.classList.toggle("active", t.dataset.char === selectedCourse);
  updateCourseNameBar();
}

// ---- the name plate ----
// While the mouse is over a tile the plate shows THAT cup or course (as the game's select screen does as the cursor
// moves); otherwise the selected course, else the selected cup. A course also shows its cup, small and dim.
let courseHoverEl = null;
function updateCourseNameBar() {
  const plate = document.getElementById("course-name-plate");
  let main = null, context = null;
  const el = courseHoverEl && courseHoverEl.isConnected ? courseHoverEl : null;
  if (el && el.classList.contains("cup-tile")) main = el.dataset.cup;
  else if (el) { main = el.dataset.char; context = selectedCup; }
  else if (selectedCourse !== null) { main = selectedCourse; context = selectedCup; }
  else main = selectedCup;
  plate.replaceChildren();
  if (!main) { plate.classList.remove("show"); return; }
  plate.append(main);
  if (context) {
    const base = document.createElement("span");
    base.className = "np-base";
    base.textContent = `(${context})`;
    plate.appendChild(base);
  }
  plate.classList.add("show");
}
for (const root of [document.getElementById("cup-grid"), document.getElementById("course-strip")]) {
  root.addEventListener("mouseover", (e) => {
    const tile = e.target.closest(".cup-tile, .char-tile");
    if (tile && tile !== courseHoverEl) { courseHoverEl = tile; updateCourseNameBar(); }
  });
  root.addEventListener("mouseleave", () => { courseHoverEl = null; updateCourseNameBar(); });
}

// ---- fitting the screen ----
// Everything on Course Select is sized from the room there is, so nothing scrolls: the cups (one square tile size
// --cup, in --cols columns) and the four course tiles (16:9 pictures, --course-w wide) share the height.
// The cups are on two pages - the game's 12 and the Booster Course Pass's 12 - with an arrow beside the board to turn
// between them. Of the layouts that fit (6, 4, 12 or 3 cups per row) it takes the one where the smaller of "cup size"
// and "course tile size", each against a comfortable reference, is largest.
const COURSE_FIT = {
  K: 0.12,             // gap between cups, as a fraction of a cup
  BOARD: 30,           // the board's own padding + border, per axis
  STRIP: 32,           // the course strip's padding, per axis
  STRIP_GAP: 10,       // between course tiles
  TILE_PAD: 12,        // a course tile's padding, both sides together (the picture sits inside it)
  GAP: 16,             // between the board and the strip
  ARROWS: 112,         // the two page arrows beside the board: 44 wide + a 12 gap, each side
  PAGE_LABEL: 24,      // the "1 of 2" caption under the board
  RATIO: 9 / 16,
  MIN_CUP: 24, MAX_CUP: 130, MIN_W: 96, MAX_W: 400,
  REF_CUP: 110, REF_W: 300,
};
const cupPages = { current: "base" };
function cupPageOf(cupName) {
  const dlcAt = state.cups.findIndex(c => c.cup === DLC_CUP_START);
  const at = state.cups.findIndex(c => c.cup === cupName);
  return dlcAt > 0 && at >= dlcAt ? "dlc" : "base";
}
// Shows the current page's cups, and the arrow and caption that go with it.
function applyCupPage() {
  for (const t of document.querySelectorAll("#cup-grid .cup-tile")) t.hidden = t.dataset.page !== cupPages.current;
  const onDlc = cupPages.current === "dlc";
  document.getElementById("cup-prev").style.visibility = onDlc ? "visible" : "hidden";
  document.getElementById("cup-next").style.visibility = onDlc ? "hidden" : "visible";
  // a dot on the arrow when the page it leads to has modded courses (progress you can't see from here)
  const modded = page => [...document.querySelectorAll(`#cup-grid .cup-tile[data-page="${page}"]`)].some(t => t.querySelector(".tile-count-bubble"));
  document.getElementById("cup-prev").classList.toggle("has-mods", onDlc && modded("base"));
  document.getElementById("cup-next").classList.toggle("has-mods", !onDlc && modded("dlc"));
  document.getElementById("cup-page-label").textContent = onDlc ? "Booster Course Pass \u00b7 2 of 2" : "Mario Kart 8 Deluxe \u00b7 1 of 2";
  courseHover.hide();
}
function turnCupPage(page) {
  cupPages.current = page;
  applyCupPage();
  fitCourseScreen();
}
document.getElementById("cup-prev").addEventListener("click", () => turnCupPage("base"));
document.getElementById("cup-next").addEventListener("click", () => turnCupPage("dlc"));

function fitCourseScreen() {
  const layout = document.getElementById("course-layout");
  if (!layout || !layout.clientWidth || !layout.clientHeight) return;
  const C = COURSE_FIT;
  const W = layout.clientWidth, H = layout.clientHeight;
  const total = state.cups.length || 24;
  const dlcAt = state.cups.findIndex(c => c.cup === DLC_CUP_START);
  const first = dlcAt > 0 ? dlcAt : total, second = total - first;
  const perPage = Math.max(first, second);

  let best = null;
  for (const cols of [6, 4, 12, 3]) {
    const rows = Math.ceil(perPage / cols);
    const cupByWidth = (W - C.ARROWS - C.BOARD) / (cols + (cols - 1) * C.K);
    const wByWidth = Math.min(C.MAX_W, (W - C.STRIP - 3 * C.STRIP_GAP) / 4);
    for (let w = Math.floor(wByWidth); w >= C.MIN_W; w -= 2) {
      const stripH = (w - C.TILE_PAD) * C.RATIO + C.TILE_PAD + C.STRIP;
      const cupByHeight = (H - C.PAGE_LABEL - C.GAP - stripH - C.BOARD) / (rows + (rows - 1) * C.K);
      const cup = Math.floor(Math.min(cupByWidth, cupByHeight, C.MAX_CUP));
      if (cup < C.MIN_CUP) continue;
      const score = Math.min(cup / C.REF_CUP, w / C.REF_W) + 0.001 * (cup + w);
      if (!best || score > best.score) best = { cols, cup, w, score };
    }
  }
  if (!best) best = { cols: 6, cup: C.MIN_CUP, w: C.MIN_W };   // too small for anything: the view scrolls as a last resort
  layout.style.setProperty("--cols", best.cols);
  layout.style.setProperty("--cup", best.cup + "px");
  layout.style.setProperty("--course-w", best.w + "px");
}
new ResizeObserver(fitCourseScreen).observe(document.getElementById("course-layout"));

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
  document.getElementById("view-items").hidden = mode !== "items";
  document.getElementById("view-more").hidden = mode !== "more";
  document.getElementById("view-list").hidden = mode !== "list";
  document.getElementById("tab-characters").classList.toggle("active", mode === "characters");
  document.getElementById("tab-courses").classList.toggle("active", mode === "courses");
  document.getElementById("tab-vehicles").classList.toggle("active", mode === "vehicles");
  document.getElementById("tab-items").classList.toggle("active", mode === "items");
  document.getElementById("tab-more").classList.toggle("active", mode === "more");
  document.getElementById("tab-list").classList.toggle("active", mode === "list");
  applyCharacterLayout();
  drawViewIfStale(mode);   // (its redraw was still waiting for its turn)
  if (mode === "courses") fitCourseScreen();   // (it was hidden, so it hasn't been measured since the window last changed)
  if (mode === "vehicles") fitVehicleScreen();
  if (mode === "items") showItemsView();
  else if (itemDockedKey !== null) closeItemDetail();
  if (mode === "characters") {
    if (dockedLayout()) ensureDockedSelection();
    else if (dockedKey !== null) closeDetail();
  }
  markActiveTile();
}
document.getElementById("tab-characters").addEventListener("click", () => switchView("characters"));
document.getElementById("tab-courses").addEventListener("click", () => switchView("courses"));
document.getElementById("tab-vehicles").addEventListener("click", () => { switchView("vehicles"); renderVehiclesView(); });
document.getElementById("tab-items").addEventListener("click", () => { switchView("items"); renderItemsView(); });
document.getElementById("tab-more").addEventListener("click", () => { switchView("more"); renderMoreList(); });
document.getElementById("tab-list").addEventListener("click", () => switchView("list"));

function openSettingsModal() {
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

