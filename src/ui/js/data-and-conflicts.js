// Reloads every roster-backed view's data (characters, courses, the simple
// categories, vehicle parts, items) into state - used after anything that adds or
// removes a downloaded mod.
async function refreshViewsState() {
  const [charResult, courseResult, simpleResult, vehicleResult, linkResult, itemResult] = await Promise.all([
    pywebview.api.get_character_view(),
    pywebview.api.get_course_view(),
    pywebview.api.get_simple_categories_view(),
    pywebview.api.get_vehicles_view(),
    pywebview.api.get_vehicle_links(),
    pywebview.api.get_items_view(),
  ]);
  state.roster = charResult.roster;
  state.cups = courseResult.cups;
  state.simpleCategories = simpleResult.categories;
  state.vehicles = vehicleResult.sections;
  state.vehicleLinks = linkResult;
  state.items = itemResult.items;
}

async function loadMods() {
  const [modsResult] = await Promise.all([pywebview.api.get_mods(), refreshViewsState()]);
  state.categories = modsResult.categories;
  state.checked = modsResult.checked;
  renderAll();
}

document.getElementById("btn-refresh").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  if (btn.classList.contains("busy")) return;
  btn.classList.add("busy");
  try {
    // (held for at least half a second, so a quick reload still visibly happened)
    await Promise.all([loadMods(), new Promise(r => setTimeout(r, 500))]);
  } finally {
    btn.classList.remove("busy");
  }
});

async function loadSettings() {
  state.settings = await pywebview.api.get_settings();
  document.getElementById("setting-show-nsfw").checked = !!state.settings.show_nsfw;
  document.getElementById("setting-game-build-id").value = state.settings.game_build_id || "";
  document.getElementById("setting-advanced-mode").checked = !!state.settings.advanced_mode;
  document.getElementById("setting-show-tile-counts").checked = !!state.settings.show_tile_counts;
  document.getElementById("setting-play-select-voice").checked = state.settings.play_select_voice !== false;
  const dirStatus = await pywebview.api.get_master_dir_status();
  document.getElementById("setting-master-dir-path").textContent = dirStatus.path || "(not set)";
  renderUiIconWorklist();
  renderConflicts();
}

// ---- Conflict cards -------------------------------------------------------
// One card per SET of mods that clash (however many files): the user picks
// which copy stays, or leaves the files out of every mod, or unticks a mod.
// Leaving files out of a mod is how a conflict is "settled" - the rest of that
// mod keeps working. Shared by mod popups, Settings and the Commit page.

function cgEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// "characters/Inkling Girl/Minecraft Alex/inner" -> "Minecraft Alex (Inkling Girl)" (mirrors mod_manager.mod_label)
function modLabel(key, full) {
  const parts = key.split("/");
  if (parts.length < 3) return parts[parts.length - 1];
  const cut = (t, n) => (full || t.length <= n) ? t : t.slice(0, n - 1).trimEnd() + "\u2026";
  let name = parts[2];
  if (parts.length > 3) {
    const unit = parts[parts.length - 1];
    const a = name.toLowerCase(), b = unit.toLowerCase();
    // (the backend also treats a near-identical spelling as "the same name"; here a prefix is enough)
    name = (a.startsWith(b) || b.startsWith(a)) ? cut(name, 60) : `${cut(name, 40)} > ${cut(unit, 32)}`;
  } else {
    name = cut(name, 60);
  }
  return name.toLowerCase().includes(parts[1].toLowerCase()) ? name : `${name} (${parts[1]})`;
}

// A mod's name on a character's card: the whole of it (the card wraps long names), plus the unit's own name
// only when that says something else than the mod's name does.
function charModLabel(key) {
  const parts = key.split("/");
  if (parts.length < 3) return parts[parts.length - 1];
  const bigrams = t => { const g = new Map(); const x = t.toLowerCase(); for (let i = 0; i < x.length - 1; i++) g.set(x.substr(i, 2), (g.get(x.substr(i, 2)) || 0) + 1); return g; };
  const dice = (a, b) => {
    const A = bigrams(a), B = bigrams(b);
    let hit = 0, total = 0;
    for (const [k, n] of A) { hit += Math.min(n, B.get(k) || 0); total += n; }
    for (const n of B.values()) total += n;
    return total ? 2 * hit / total : 1;
  };
  const name = parts[2], unit = parts[parts.length - 1];
  return parts.length > 3 && dice(name, unit) < 0.8 ? `${name} > ${unit}` : name;
}

function cgJoin(labels) {
  if (labels.length <= 2) return labels.join(" and ");
  return labels.slice(0, -1).join(", ") + " and " + labels[labels.length - 1];
}

function buildConflictCard(group, opts) {
  const onSettled = (opts && opts.onSettled) || (() => {});
  const card = cgEl("div", "cg-card" + (group.can_exclude ? "" : " code"));
  const n = group.paths.length;
  const labelOf = (m) => group.labels[group.mods.indexOf(m)];

  if (group.can_exclude) {
    const title = cgEl("div", "cg-title",
      `${cgJoin(group.labels)} both change the same ${n === 1 ? "file" : n + " files"}`);
    if (group.full_labels) title.title = group.full_labels.join("\n");
    card.appendChild(title);
    card.appendChild(cgEl("div", "cg-sub", group.summary ? `That's ${group.summary}.` : ""));
  } else {
    card.appendChild(cgEl("div", "cg-title",
      `${cgJoin(group.labels)} both patch the same part of the game's code`));
    card.appendChild(cgEl("div", "cg-sub",
      "Half of a code patch can't be dropped, so only one of these can be used."));
  }
  const parts = group.mods.map(m => {
    const imp = group.impact[m];
    return imp && imp.total ? `${labelOf(m)}: ${imp.shared} of its ${imp.total} files` : null;
  }).filter(Boolean);
  if (parts.length && group.can_exclude) {
    card.appendChild(cgEl("div", "cg-impact",
      "How much each mod is affected - " + parts.join(" · ") + ". Either way, the rest of each mod still works."));
  }
  for (const k of group.known || []) {
    card.appendChild(cgEl("div", "cg-note", `${k.label} - ${k.note}`));
  }

  // Choices
  const choices = cgEl("div", "cg-choices");
  const radios = [];
  let idx = 0;
  const addChoice = (value, title, sub, isDefault, tag) => {
    const row = cgEl("label", "cg-choice");
    const r = document.createElement("input");
    r.type = "radio";
    r.name = "cg-" + group.id + "-" + (opts && opts.scope || "x");
    r.value = value;
    row.appendChild(r);
    const text = cgEl("span", "cg-choice-text");
    text.appendChild(document.createTextNode(title));
    if (tag) text.appendChild(cgEl("span", "cg-tag", tag));
    if (sub) text.appendChild(cgEl("small", null, sub));
    row.appendChild(text);
    r.addEventListener("change", () => {
      for (const x of radios) x.row.classList.toggle("selected", x.r.checked);
    });
    radios.push({ r, row });
    choices.appendChild(row);
    if (isDefault) r.checked = true;
    idx++;
  };
  if (group.can_exclude) {
    for (const m of group.mods) {
      const others = group.mods.filter(x => x !== m).map(labelOf);
      addChoice("keep:" + m, `Keep ${labelOf(m)}'s version`,
        `${cgJoin(others)} ${others.length === 1 ? "leaves" : "leave"} ${n === 1 ? "this file" : "these files"} out`,
        group.suggested === m, group.suggested === m ? "suggested" : null);
    }
    addChoice("none", "Use the game's own files",
      `${n === 1 ? "This file is" : "These files are"} left out of ${group.mods.length === 2 ? "both mods" : "every mod"}`,
      !group.suggested);
  }
  for (const m of group.mods) {
    addChoice("untick:" + m, `Don't use ${labelOf(m)} at all`, "Unticks that mod", !group.can_exclude && m === group.mods[group.mods.length - 1]);
  }
  for (const x of radios) x.row.classList.toggle("selected", x.r.checked);
  card.appendChild(choices);

  const actions = cgEl("div", "cg-actions");
  const apply = cgEl("button", "primary small", "Apply");
  const status = cgEl("span", "cg-note");
  apply.addEventListener("click", async () => {
    const pick = radios.find(x => x.r.checked);
    if (!pick) return;
    apply.disabled = true;
    const v = pick.r.value;
    try {
      if (v.startsWith("keep:")) {
        await pywebview.api.resolve_conflict_group(group.mods, group.paths, v.slice(5));
      } else if (v === "none") {
        await pywebview.api.resolve_conflict_group(group.mods, group.paths, null);
      } else if (v.startsWith("untick:")) {
        state.checked[v.slice(7)] = false;
        await pywebview.api.save_checked(state.checked);
      }
    } catch (e) {
      status.textContent = "Something went wrong: " + e;
      apply.disabled = false;
      return;
    }
    card.replaceChildren(cgEl("div", "cg-done", "✓ Settled - " + (
      v.startsWith("keep:") ? `keeping ${labelOf(v.slice(5))}'s version.`
        : v === "none" ? "using the game's own files."
        : `${labelOf(v.slice(7))} is unticked.`)));
    card.classList.remove("code");
    card.classList.add("settled");
    onSettled();
  });
  actions.appendChild(apply);
  actions.appendChild(status);
  card.appendChild(actions);

  const files = document.createElement("details");
  files.className = "cg-files";
  files.open = !!(state.settings && state.settings.advanced_mode);
  files.appendChild(cgEl("summary", null, `Show the ${n === 1 ? "file" : n + " files"}`));
  for (const p of group.paths) files.appendChild(cgEl("code", null, p));
  card.appendChild(files);
  return card;
}

// "Files" panel for one mod: every file it ships, with a checkbox to leave a
// single file out of the merge. `onChange` runs after any change.
function buildFilesPanel(modKey, onChange) {
  const panel = cgEl("div", "files-panel");
  const head = cgEl("div", "files-panel-head");
  const summary = cgEl("span", null, "Loading...");
  const filter = document.createElement("input");
  filter.type = "text";
  filter.placeholder = "Filter files...";
  const includeAll = cgEl("button", "ghost small", "Include all again");
  includeAll.hidden = true;
  head.appendChild(summary);
  head.appendChild(filter);
  head.appendChild(includeAll);
  panel.appendChild(head);
  panel.appendChild(cgEl("div", "cg-note",
    "Untick a file to leave it out of the merge - handy when it clashes with another mod and you'd rather keep the other one's. The rest of the mod is unaffected."));
  const list = cgEl("div", "files-list");
  panel.appendChild(list);
  let data = null;
  let reasons = {};

  function draw() {
    list.replaceChildren();
    const q = filter.value.trim().toLowerCase();
    const leftOut = data.files.filter(f => f.left_out).length;
    summary.textContent = `${data.total - leftOut} of ${data.total} files included` + (leftOut ? ` · ${leftOut} left out` : "");
    includeAll.hidden = leftOut === 0;
    const shown = data.files
      .filter(f => !q || f.path.toLowerCase().includes(q))
      .sort((a, b) => (b.left_out - a.left_out) || a.path.localeCompare(b.path));
    for (const f of shown.slice(0, 300)) {
      const row = cgEl("label", "files-row" + (f.left_out ? " left-out" : ""));
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !f.left_out;
      cb.disabled = f.skipped_anyway;
      cb.addEventListener("change", async () => {
        if (cb.checked) await pywebview.api.include_files(modKey, [f.path]);
        else await pywebview.api.exclude_files(modKey, [f.path], "manual", null);
        f.left_out = !cb.checked;
        draw();
        onChange();
      });
      row.appendChild(cb);
      row.appendChild(cgEl("code", null, f.path));
      const why = reasons[f.path.toLowerCase()];
      const note = f.skipped_anyway ? "never copied (see README)"
        : f.left_out ? (why && why.kept_label ? `kept ${why.kept_label}'s instead` : why && why.reason === "conflict" ? "game's own file used" : "you left this out")
        : f.kind;
      row.appendChild(cgEl("small", null, note));
      list.appendChild(row);
    }
    if (shown.length > 300) list.appendChild(cgEl("div", "cg-note", `... and ${shown.length - 300} more - use the filter to find a file.`));
    if (data.truncated) list.appendChild(cgEl("div", "cg-note", `Only the first ${data.files.length} of ${data.total} files are listed.`));
  }
  filter.addEventListener("input", draw);
  includeAll.addEventListener("click", async () => {
    await pywebview.api.include_files(modKey, null);
    for (const f of data.files) f.left_out = false;
    draw();
    onChange();
  });
  Promise.all([pywebview.api.get_mod_files(modKey), pywebview.api.get_excluded_files(modKey)]).then(([files, excl]) => {
    data = files;
    reasons = {};
    for (const e of (excl[modKey] || [])) reasons[e.path.toLowerCase()] = e;
    draw();
  });
  return panel;
}

async function renderConflicts() {
  const container = document.getElementById("conflicts-body");
  const result = await pywebview.api.get_all_conflicts();
  container.replaceChildren();
  const shortName = (k) => k.split("/").slice(1).join("/");
  const again = async () => { await renderConflicts(); await loadMods(); };
  let any = false;

  if (result.groups.length) {
    any = true;
    container.appendChild(cgEl("div", "cg-section-title", `Needs settling (${result.groups.length})`));
    for (const g of result.groups) container.appendChild(buildConflictCard(g, { scope: "settings", onSettled: () => setTimeout(again, 900) }));
  }

  const settled = result.settled || [];
  const manualByMod = Object.entries(result.left_out || {})
    .map(([mod, entries]) => [mod, entries.filter(e => e.reason !== "conflict")])
    .filter(([, entries]) => entries.length);
  if (settled.length || manualByMod.length || result.resolved.length) {
    any = true;
    container.appendChild(cgEl("div", "cg-section-title", "Settled / left out"));
    for (const s of settled) {
      const card = cgEl("div", "cg-card settled");
      card.appendChild(cgEl("div", "cg-title",
        `${s.label} leaves out ${s.paths.length} file${s.paths.length === 1 ? "" : "s"}`));
      card.appendChild(cgEl("div", "cg-sub", s.kept_label ? `Kept ${s.kept_label}'s version instead.` : "The game's own file is used instead."));
      const acts = cgEl("div", "cg-actions");
      const back = cgEl("button", "ghost small", "Include again");
      back.addEventListener("click", async () => { await pywebview.api.include_files(s.mod, s.paths); await again(); });
      acts.appendChild(back);
      const open = cgEl("button", "ghost small", "Open mod");
      open.addEventListener("click", () => { closeSettingsModal && closeSettingsModal(); jumpToModKey(s.mod); });
      acts.appendChild(open);
      card.appendChild(acts);
      const files = document.createElement("details");
      files.className = "cg-files";
      files.appendChild(cgEl("summary", null, "Show the files"));
      for (const p of s.paths) files.appendChild(cgEl("code", null, p));
      card.appendChild(files);
      container.appendChild(card);
    }
    for (const [mod, entries] of manualByMod) {
      const card = cgEl("div", "cg-card settled");
      card.appendChild(cgEl("div", "cg-title", `${shortName(mod)}: ${entries.length} file${entries.length === 1 ? "" : "s"} left out by you`));
      const acts = cgEl("div", "cg-actions");
      const back = cgEl("button", "ghost small", "Include again");
      back.addEventListener("click", async () => { await pywebview.api.include_files(mod, entries.map(e => e.path)); await again(); });
      acts.appendChild(back);
      card.appendChild(acts);
      container.appendChild(card);
    }
    for (const r of result.resolved) {
      const card = cgEl("div", "cg-card settled");
      card.appendChild(cgEl("div", "cg-title", r.path));
      card.appendChild(cgEl("div", "cg-sub", `Using ${shortName(r.preferred)} (saved earlier)`));
      const acts = cgEl("div", "cg-actions");
      const clear = cgEl("button", "ghost small", "Clear");
      clear.addEventListener("click", async () => { await pywebview.api.clear_conflict_resolution(r.path); await again(); });
      acts.appendChild(clear);
      card.appendChild(acts);
      container.appendChild(card);
    }
  }
  if (!any) container.appendChild(cgEl("div", "conflicts-empty", "No conflicts right now, and no files left out."));
}

