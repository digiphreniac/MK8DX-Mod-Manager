// ===== Guided flow =====
// Setup > Choose mods > Commit > UI icons & text > Copy to Switch. The step bar
// always shows where you are and which steps need you; the Next button says
// what to do next. get_flow_status() (mod_manager.py) is the single source of
// truth for what's done, stale or waiting.
const FLOW_STEPS = [
  { key: "setup", label: "Setup" },
  { key: "mods", label: "Choose mods" },
  { key: "commit", label: "Commit" },
  { key: "switch", label: "Copy to Switch" },
];
const FLOW_PAGES = { commit: "view-commit", switch: "view-switch" };
const flow = { step: "mods", status: null, timer: null, lastModsView: "characters", hintDismissed: false };   // (hintDismissed: only until the app is next started)

function flowStepInfo(key, st) {
  if (!st || !st.commit) return { state: "idle", sub: "" };
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : (/(sh|ch|s|x)$/.test(w) ? "es" : "s")}`;
  if (key === "setup") return { state: st.setup.done ? "done" : "attention", sub: st.game_version === "newer" ? "Newer game version" : st.game_version ? `Game v${st.game_version}` : (st.setup.done ? "Done" : "Start here") };
  if (key === "mods") {
    const left = unfinishedCount();
    return { state: st.mods.ticked > 0 ? (left ? "attention" : "done") : "idle",
             sub: st.mods.ticked > 0 ? plural(st.mods.ticked, "mod") + " selected" + (left ? ` \u00b7 ${left} to finish` : "") : "Select mods you want" };
  }
  if (key === "commit") {
    if (st.mods.conflicts) return { state: "attention", sub: plural(st.mods.conflicts, "clash") + " to settle" };
    if (st.commit.done && st.commit.stale) return { state: "attention", sub: "Changed - commit again" };
    if (st.commit.done) return { state: "done", sub: st.commit.summary ? `${plural(st.commit.summary.mods, "mod")} committed` : "Committed" };
    return { state: "idle", sub: st.mods.ticked ? "Ready when you are" : "" };
  }
  if (st.switch.done) return { state: "done", sub: "Confirmed working" };
  if (st.switch.stale) return { state: "attention", sub: "Changed since" };
  return { state: "idle", sub: "Copy & test" };
}

function updateTabCounts() {
  const counts = { characters: 0, courses: 0, vehicles: 0, items: 0, more: 0 };
  for (const [k, v] of Object.entries(state.checked || {})) {
    if (!v) continue;
    const c = k.split("/")[0];
    if (c === "characters") counts.characters++;
    else if (c === "courses") counts.courses++;
    else if (VEHICLE_SECTION_KEYS.includes(c)) counts.vehicles++;
    else if (c === ITEMS_CATEGORY) counts.items++;
    else counts.more++;
  }
  for (const [k, n] of Object.entries(counts)) {
    const b = document.getElementById("tab-" + k);
    if (!b.dataset.base) b.dataset.base = b.textContent;
    b.textContent = n ? `${b.dataset.base} (${n})` : b.dataset.base;
  }
}

function renderStepBar() {
  const bar = document.getElementById("stepbar");
  bar.replaceChildren();
  const st = flow.status;
  const hint = document.getElementById("step-hint");
  const first = st && st.commit && !st.commit.done;
  hint.hidden = !(flow.step === "mods" && first) || flow.hintDismissed;
  if (!hint.hidden) {
    const close = cgEl("button", "hint-close", "×");
    close.type = "button";
    close.title = "Hide this tip";
    close.setAttribute("aria-label", "Hide this tip");
    close.addEventListener("click", () => { flow.hintDismissed = true; hint.hidden = true; });
    hint.replaceChildren(cgEl("span", "hint-text", "Select the mods you want on each tab. When you're ready, click Next in the bottom right."), close);
  }
  FLOW_STEPS.forEach((s, i) => {
    if (i > 0) bar.appendChild(cgEl("span", "step-sep", "›"));
    const info = flowStepInfo(s.key, st);
    const btn = cgEl("button", "step " + info.state + (flow.step === s.key ? " current" : ""));
    btn.title = info.sub ? `${s.label} - ${info.sub}` : s.label;
    btn.appendChild(cgEl("span", "num", info.state === "done" ? "✓" : String(i + 1)));
    const text = cgEl("span");
    text.appendChild(cgEl("span", "label", s.label));
    if (info.sub) text.appendChild(cgEl("small", null, info.sub));
    btn.appendChild(text);
    btn.addEventListener("click", () => goStep(s.key));
    bar.appendChild(btn);
  });
}

// What "Next" should do from the page the user is on - null (hidden) when the
// page has its own thing to finish first.
function flowNextTarget(step, st) {
  if (!st || !st.commit || !st.setup.done) return null;
  if (step === "mods") {
    if (st.mods.ticked === 0) return null;
    if (st.mods.conflicts) return { to: "commit", label: `Next: Settle ${st.mods.conflicts} clash${st.mods.conflicts === 1 ? "" : "es"}` };
    return { to: "commit", label: `Next: Commit ${st.mods.ticked} mod${st.mods.ticked === 1 ? "" : "s"}` };
  }
  if (step === "commit") {
    if (!st.commit.done || st.commit.stale || st.mods.conflicts) return null;
    return { to: "switch", label: "Next: Copy to your Switch" };
  }
  return null;
}

function renderNextButton() {
  const btn = document.getElementById("btn-next");
  const target = flowNextTarget(flow.step, flow.status);
  btn.hidden = !target;
  if (target) {
    btn.textContent = target.label + "  →";
    btn.onclick = () => goStep(target.to);
    const left = flow.step === "mods" ? unfinishedCount() : 0;
    btn.title = left ? `${left} ${left === 1 ? "character, course or vehicle part still needs its" : "characters, courses or vehicle parts still need their"} name and icons confirmed` : "";
  }
  placeAddButton();
}

// The round "+" (Add a mod) on the Full List normally sits in the corner; while the Next button is showing it goes just above it,
// instead of behind it.
function placeAddButton() {
  const dock = document.getElementById("next-dock");
  const lifted = !document.getElementById("btn-next").hidden;
  const bottom = lifted ? parseFloat(getComputedStyle(dock).bottom) + dock.offsetHeight + 12 : 28;
  document.documentElement.style.setProperty("--add-fab-bottom", bottom + "px");
}
window.addEventListener("resize", placeAddButton);   // (the Next button can wrap or change height on a narrow window)

async function refreshFlow() {
  try {
    flow.status = await pywebview.api.get_flow_status();
  } catch (e) {
    return;
  }
  renderStepBar();
  renderNextButton();
}

function scheduleFlowRefresh() {
  clearTimeout(flow.timer);
  flow.timer = setTimeout(refreshFlow, 350);
}

async function goStep(step, opts) {
  if (step === "setup") {
    openSetupWizard(0, true);
    return;
  }
  if (flow.step === "mods" && step !== "mods" && !(opts && opts.skipGate) && !(await passUnfinishedGate())) return;
  if (step === "mods") {
    switchView(flow.lastModsView || "characters");
    return;
  }
  flow.step = step;
  for (const v of ["characters", "courses", "vehicles", "items", "more", "list"]) document.getElementById("view-" + v).hidden = true;
  for (const id of Object.values(FLOW_PAGES)) document.getElementById(id).hidden = true;
  document.getElementById(FLOW_PAGES[step]).hidden = false;
  document.getElementById("tabs").hidden = true;
  document.getElementById(FLOW_PAGES[step]).scrollTop = 0;
  renderStepBar();
  renderNextButton();
  if (step === "commit") renderCommitPage();
  else if (step === "switch") renderSwitchPage();
}

// ---- page helpers ----
function pageHead(body, title, lead) {
  body.appendChild(cgEl("h2", null, title));
  body.appendChild(cgEl("p", "pg-lead", lead));
}

function statusCard(kind, big, title, sub) {
  const c = cgEl("div", "pg-status " + kind);
  c.appendChild(cgEl("div", "big", big));
  const t = cgEl("div");
  t.appendChild(cgEl("div", "t", title));
  if (sub) t.appendChild(cgEl("div", "s", sub));
  c.appendChild(t);
  return c;
}

function button(text, cls, onclick) {
  const b = cgEl("button", cls, text);
  b.addEventListener("click", onclick);
  return b;
}

function formatWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// ---- Step 3: Commit ----
const commitPage = { preview: null, result: null, busy: false };

async function renderCommitPage() {
  const body = document.getElementById("commit-body");
  body.replaceChildren();
  pageHead(body, "Commit your mods",
    "Committing gathers every selected mod's files into one set, ready to copy to your Switch. Nothing on the Switch changes until you copy it there yourself.");
  body.appendChild(loadingNote("Checking your mods..."));
  const keys = allKeys().filter(k => state.checked[k]);
  const [preview, status] = await Promise.all([pywebview.api.preview_commit(keys), pywebview.api.get_flow_status()]);
  commitPage.preview = preview;
  flow.status = status;
  if (!commitPage.preview.already && !commitPage.busy) commitPage.result = null;
  drawCommitPage();
  renderStepBar();
  renderNextButton();
}

function pgWarnEl(w) {
  const row = cgEl("div", "pg-warn " + w.severity);
  row.appendChild(cgEl("span", "dot"));
  const t = cgEl("div");
  t.appendChild(cgEl("div", "wt", w.title));
  t.appendChild(cgEl("div", "wd", w.detail));
  if ((w.mods && w.mods.length) || (w.items && w.items.length) || w.action === "guessed-names" || w.action === "settings") {
    const m = cgEl("div", "wm");
    if (w.action === "guessed-names") m.appendChild(button("Review names", "ghost small", openGuessedNamesModal));
    if (w.action === "settings") m.appendChild(button("Open Settings", "ghost small", () => openSettingsModal()));
    for (const item of (w.items || []).slice(0, 8)) {
      const a = cgEl("a", null, item);
      a.addEventListener("click", () => { goStep("mods"); if (isItemName(item)) openItemCard(item); else openCharacterModal(item); });
      m.appendChild(a);
    }
    const shown = (w.mods || []).slice(0, 6);
    for (const k of shown) {
      const a = cgEl("a", null, modLabel(k));
      a.addEventListener("click", () => jumpToModKey(k));
      m.appendChild(a);
    }
    if ((w.mods || []).length > shown.length) m.appendChild(cgEl("span", "cg-note", `and ${w.mods.length - shown.length} more`));
    t.appendChild(m);
  }
  row.appendChild(t);
  return row;
}

function drawCommitPage() {
  const body = document.getElementById("commit-body");
  const pv = commitPage.preview;
  body.replaceChildren();
  pageHead(body, "Commit your mods",
    "Committing gathers every selected mod's files into one set, ready to copy to your Switch. Nothing on the Switch changes until you copy it there yourself.");
  if (!pv || pv.empty) {
    body.appendChild(statusCard("wait", "☐", "No mods are selected yet", "Pick the characters, courses and vehicles you want, then come back here."));
    body.appendChild(button("Choose mods", "primary", () => goStep("mods")));
    return;
  }
  const c = pv.counts;
  const res = commitPage.result;
  const committedNow = res && res.staged && pv.already;

  if (pv.groups.length) {
    body.appendChild(statusCard("bad", "!", `${pv.groups.length} thing${pv.groups.length === 1 ? "" : "s"} need${pv.groups.length === 1 ? "s" : ""} your attention`,
      "Some mods change the same files. Settle each one below - it takes one click - and then you can commit."));
  } else if (committedNow) {
    body.appendChild(statusCard("ok", "✓", "Committed",
      `${c.mods} mods, ${c.files} files` + (c.code_patches ? `, ${c.code_patches} code patch${c.code_patches === 1 ? "" : "es"}` : "")
      + (c.left_out ? ` · ${c.left_out} file${c.left_out === 1 ? "" : "s"} left out on purpose` : "") + ` · ${formatWhen(res.at)}`));
  } else if (pv.already) {
    body.appendChild(statusCard("ok", "✓", "Already committed - nothing has changed since",
      `${c.mods} mods, ${c.files} files. Commit again only if you change your mods.`));
  } else {
    body.appendChild(statusCard("wait", "→", `Ready to commit ${c.mods} mod${c.mods === 1 ? "" : "s"}`,
      `${c.files} files will be put together` + (c.code_patches ? `, plus ${c.code_patches} code patch${c.code_patches === 1 ? "" : "es"}` : "") + "."));
  }

  if (pv.groups.length) {
    body.appendChild(cgEl("div", "pg-section", "Needs your attention"));
    const refresh = () => setTimeout(() => { renderAll(); renderCommitPage(); refreshFlow(); }, 900);
    if (pv.groups.length > 1 && pv.groups.every(g => g.can_exclude && g.suggested)) {
      const all = button("Settle all with the suggested choice", "ghost small", async () => {
        const names = pv.groups.map(g => `${cgJoin(g.labels)} -> keep ${g.labels[g.mods.indexOf(g.suggested)]}`).join("\n");
        if (!confirm("Settle every clash by keeping the suggested mod's version?\n\n" + names)) return;
        for (const g of pv.groups) await pywebview.api.resolve_conflict_group(g.mods, g.paths, g.suggested);
        await renderCommitPage();
        refreshFlow();
      });
      const row = cgEl("div", "pg-cta");
      row.appendChild(all);
      body.appendChild(row);
    }
    for (const g of pv.groups) body.appendChild(buildConflictCard(g, { scope: "commit", onSettled: refresh }));
  }

  const cta = cgEl("div", "pg-cta");
  const canCommit = pv.can_commit && !commitPage.busy;
  const commitBtn = button(commitPage.busy ? "Committing..." : (committedNow || pv.already ? "Commit again" : `Commit ${c.mods} mod${c.mods === 1 ? "" : "s"}`),
    (committedNow || pv.already) && !pv.groups.length ? "ghost" : "primary", doCommit);
  commitBtn.disabled = !canCommit;
  if (!pv.can_commit) commitBtn.title = "Settle the clashes above first";
  cta.appendChild(commitBtn);   // (the staging folder is opened from the next page, which walks through what to do with it)
  body.appendChild(cta);

  if (res && res.conflict === false && !res.staged) {
    body.appendChild(statusCard("bad", "!", "Nothing was committed", (res.lines || []).join(" ")));
  }

  if (pv.warnings.length) {
    body.appendChild(cgEl("div", "pg-section", "Good to know"));
    const order = { warn: 0, todo: 1, info: 2 };
    for (const w of pv.warnings.slice().sort((a, b) => order[a.severity] - order[b.severity])) body.appendChild(pgWarnEl(w));
  }

  if (res && res.lines) {
    const det = document.createElement("details");
    const summary = cgEl("summary", "pg-log-summary", "Details (full log)");
    const copy = button("Copy log", "ghost small pg-copy-log", async (e) => {
      e.preventDefault();    // (the button sits in the summary: a click on it must not fold or unfold the log)
      e.stopPropagation();
      try { await navigator.clipboard.writeText(res.lines.join("\n")); copy.textContent = "Copied!"; }
      catch (err) { copy.textContent = "Copy failed"; }
      setTimeout(() => { copy.textContent = "Copy log"; }, 1500);
    });
    summary.appendChild(copy);
    det.appendChild(summary);
    det.appendChild(cgEl("div", "pg-log", res.lines.join("\n")));
    body.appendChild(det);
  }
}

async function doCommit() {
  commitPage.busy = true;
  drawCommitPage();
  const keys = allKeys().filter(k => state.checked[k]);
  let result;
  try {
    result = await pywebview.api.merge(keys);
  } catch (e) {
    result = { lines: ["Commit failed: " + e], conflict: false, staged: false };
  }
  commitPage.busy = false;
  commitPage.result = result;
  uiSetup.data = null;   // merge() may have just (re)built the menu icons & text - Settings must re-read
  await renderCommitPage();
  await refreshFlow();
}

// ---- Step 5: Copy to Switch ----
function buildTroubleshooting() {
  const trouble = document.createElement("details");
  trouble.appendChild(cgEl("summary", null, "Something looks wrong?"));
  const tb = cgEl("div", "uis-note");
  tb.style.fontSize = "12.5px";
  const items = [
    "The game crashes on startup, or the menus are blank. This is usually a file made for a different game version. Open Settings > UI icons & text and click \"Undo\", then commit and copy again. (Tip: hold L while the game starts to turn all mods off for that launch.)",
    "A mod doesn't show up. Make sure it's selected and that you committed after selecting it. Code patches only work on the game version they were made for, so check your version in Setup.",
    "Menu text is in the wrong language. Open Settings > UI icons & text, pick the language your Switch uses, then commit and copy again.",
  ];
  const ul = document.createElement("ul");
  ul.style.margin = "4px 0 0 0";
  ul.style.paddingLeft = "20px";
  for (const t of items) ul.appendChild(cgEl("li", null, t));
  tb.appendChild(ul);
  trouble.appendChild(tb);
  return trouble;
}

async function renderSwitchPage() {
  await refreshFlow();
  const body = document.getElementById("switch-body");
  const st = flow.status;
  body.replaceChildren();
  pageHead(body, "Copy to your Switch", "The last step: put the committed files on your SD card and start the game.");
  if (!st.commit.done) {
    body.appendChild(statusCard("wait", "→", "Nothing is ready to copy yet", "Commit your mods first."));
    body.appendChild(button("Go to Commit", "primary", () => goStep("commit")));
    return;
  }
  if (st.commit.stale || st.mods.conflicts) {
    body.appendChild(statusCard("wait", "!", "You've changed your mods since the last commit", "Commit again so what you copy matches what you picked."));
    body.appendChild(button("Go to Commit", "primary", () => goStep("commit")));
    return;
  }
  if (st.switch.done) {
    // All done: no checklist any more (it's finished). Back goes to the previous step, with a nudge to support the app beside it, and
    // the troubleshooting tips stay here for anyone who finds it isn't working after all.
    body.appendChild(statusCard("ok", "🎉", "All done - your mods work on your Switch",
      "If you change your mods later, the steps above will light up again and you can come back here."));
    const row = cgEl("div", "pg-cta pg-done-actions");
    row.appendChild(button("Back", "ghost", () => goStep("commit")));
    const support = cgEl("div", "pg-support");
    support.appendChild(cgEl("span", null, "Enjoying your mods? This app is free. If it saved you some time, you can chip in for a coffee."));
    support.appendChild(button("Support creator", "ghost small", openSupportPage));
    row.appendChild(support);
    body.appendChild(row);
    body.appendChild(buildTroubleshooting());
    return;
  } else {
    body.appendChild(statusCard("ok", "✓", "Everything is ready to copy",
      `${st.commit.summary ? st.commit.summary.mods + " mods, " + st.commit.summary.files + " files" : ""}` + (st.ui.needed ? " · menu pictures & names included" : "")));
  }

  const card = cgEl("div", "modal-card");
  const head = cgEl("div", "modal-card-header");
  head.appendChild(cgEl("span", "modal-card-title", "Do this"));
  card.appendChild(head);
  const pad = cgEl("div", "uis-pad");
  const ol = cgEl("ol", "pg-checklist");
  const li1 = cgEl("li");
  const t1 = cgEl("div", "pg-step-row");
  t1.appendChild(document.createTextNode("Open the staging folder - it holds everything to copy."));
  t1.appendChild(button("Open staging folder", "ghost small", async () => {
    const r = await pywebview.api.open_staging_folder();
    if (!r.success) alert(r.error);
  }));
  li1.appendChild(t1);
  ol.appendChild(li1);
  ol.appendChild(cgEl("li", null, "Copy everything inside it onto the root of your Switch's SD card (put the SD card in your computer). If asked, say yes to merge folders and replace files."));
  ol.appendChild(cgEl("li", null, "Put the SD card back in your Switch. Fully close Mario Kart 8 Deluxe if it was running (not just the Home button), then start it again."));
  ol.appendChild(cgEl("li", null, st.ui.needed
    ? "Check it: your modded characters and courses should show their new pictures and names on the select screens, and the mods themselves should be in the game."
    : "Check it: start a race and look for your mods."));
  pad.appendChild(ol);
  if (!st.switch.done) {
    const cta = cgEl("div", "pg-cta");
    cta.appendChild(button("It works!", "primary", async () => { await pywebview.api.mark_switch_done(true); renderSwitchPage(); }));
    pad.appendChild(cta);
  }
  pad.appendChild(buildTroubleshooting());
  card.appendChild(pad);
  body.appendChild(card);
}

