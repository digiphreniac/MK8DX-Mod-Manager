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
  // The "It works!" confirmation belongs to the copy the user just tested. Leaving the Commit page means they are about to copy again (or
  // change their mods), so it is reset: otherwise Next would land straight on "All done" instead of the steps with the staging folder.
  if (flow.step === "commit" && step !== "commit") {
    try { await pywebview.api.mark_switch_done(false); } catch (e) { /* (the call wrapper has logged it; going on is still right) */ }
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

// ---- how far a commit is (merge() is one long call; the page asks get_commit_progress() every moment) ----
// One bar for each phase of the commit: done ones are full, the one it is in fills as it goes (or slides, when it can't say how many
// things there are yet), the rest are empty - with what it is doing and how long it has been going underneath.
const COMMIT_COUNTED = { claims: "mods", copy: "files" };       // (the phases that say "x of y <these>")
const commitProgress = { timer: null, last: null };

function commitProgressPanel() {
  const panel = cgEl("div", "cp");
  panel.id = "commit-progress";
  const head = cgEl("div", "cp-head");
  head.append(cgEl("span", "cp-title", "Putting your mods together..."), cgEl("span", "cp-elapsed", "0:00"));
  panel.append(head, cgEl("div", "cp-phases"), cgEl("div", "cp-detail", "Starting..."),
    cgEl("div", "cp-note", "This can take a few minutes with a lot of mods. The app hasn't stopped - you can leave this page and the commit carries on."));
  return panel;
}

function formatElapsed(seconds) {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function updateCommitProgress(p) {
  const panel = document.getElementById("commit-progress");
  if (!panel || !p || !p.active) return;
  const phases = panel.querySelector(".cp-phases");
  const signature = p.phases.map(x => x.id).join(",");
  if (phases.dataset.signature !== signature) {
    phases.dataset.signature = signature;
    phases.replaceChildren(...p.phases.map(x => {
      const phase = cgEl("div", "cp-phase");
      phase.dataset.phase = x.id;
      const fill = cgEl("div", "cp-fill");
      const bar = cgEl("div", "cp-bar");
      bar.appendChild(fill);
      phase.append(bar, cgEl("div", "cp-name", x.label));
      return phase;
    }));
  }
  const at = p.phases.findIndex(x => x.id === p.phase);
  p.phases.forEach((x, i) => {
    const phase = phases.children[i];
    const state = i < at ? "done" : i === at ? "now" : "todo";
    const known = state === "now" && p.total;
    phase.className = "cp-phase " + state + (state === "now" && !known ? " cp-unknown" : "");
    // (the one it is in always shows a little, so a phase that has only just begun doesn't look like it hasn't)
    phase.querySelector(".cp-fill").style.width = state === "done" ? "100%" : known ? `${Math.max(4, Math.min(100, Math.round(100 * p.done / p.total)))}%` : "";
    phase.querySelector(".cp-name").textContent = (state === "done" ? "\u2713 " : "") + x.label;
  });
  const label = p.phases[at].label;
  const unit = COMMIT_COUNTED[p.phase];
  panel.querySelector(".cp-detail").textContent = unit && p.total ? `${label}: ${p.done.toLocaleString()} of ${p.total.toLocaleString()} ${unit}`
    : p.detail ? `${label}: ${p.detail}` : `${label}...`;
  panel.querySelector(".cp-elapsed").textContent = formatElapsed(p.elapsed);
}

function startCommitProgress() {
  clearInterval(commitProgress.timer);
  commitProgress.last = null;
  let asked = 0, shown = 0;
  const poll = async () => {
    const mine = ++asked;
    let p;
    try { p = await pywebview.api.get_commit_progress(); } catch (e) { return; }      // (a missed look costs nothing: the next one is soon)
    if (mine < shown || !commitPage.busy) return;       // (an older answer that arrived after a newer one would move the bars backwards)
    shown = mine;
    commitProgress.last = p;
    updateCommitProgress(p);
  };
  commitProgress.timer = setInterval(poll, 250);
  poll();
}

function stopCommitProgress() {
  clearInterval(commitProgress.timer);
  commitProgress.timer = null;
  commitProgress.last = null;
}

async function renderCommitPage() {
  const body = document.getElementById("commit-body");
  body.replaceChildren();
  pageHead(body, "Commit your mods",
    "Committing gathers every selected mod's files into one set, ready to copy to your Switch. Nothing on the Switch changes until you copy it there yourself.");
  const loading = loadingNote("Checking your mods...");
  body.appendChild(loading);
  const keys = selectedKeys();
  let preview, status;
  try {
    [preview, status] = await Promise.all([pywebview.api.preview_commit(keys), pywebview.api.get_flow_status()]);
  } catch (e) {   // (without this the page said "Checking your mods..." for ever)
    const failed = cgEl("div");
    failed.appendChild(statusCard("bad", "!", "Couldn't check your mods", diag.describe(e)));
    failed.appendChild(button("Try again", "ghost", renderCommitPage));
    loading.replaceWith(failed);
    return;
  }
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
  if (commitPage.busy) {
    body.appendChild(commitProgressPanel());
    updateCommitProgress(commitProgress.last);      // (the page was drawn again part-way: show where it is at once, not after the next look)
  }

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
  startCommitProgress();
  const keys = selectedKeys();
  let result;
  try {
    result = await pywebview.api.merge(keys);
  } catch (e) {
    let header = "";
    try { header = await pywebview.api.get_diagnostics(true); } catch (e2) { /* (the details are a bonus) */ }
    result = { lines: (header ? [header, ""] : []).concat(["Commit failed: " + e]), conflict: false, staged: false };
  }
  commitPage.busy = false;
  stopCommitProgress();
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
    "The game crashes on startup, or the menus are blank. This is usually a file made for a different game version. Deselect the mods that change menu pictures or names (all of them, to find out), then commit and copy again. (Tip: hold L while the game starts to turn all mods off for that launch.)",
    "A mod doesn't show up. Make sure it's selected and that you committed after selecting it. Code patches only work on the game version they were made for, so check your version in Setup.",
    "Menu text is in the wrong language. Open Settings > UI icons & text, pick the language your Switch uses, then commit and copy again.",
    "A course or character still shows its old picture or name after you deselected its mod. Copying onto an SD card only adds and replaces files, so the old ones stay behind. Delete atmosphere/contents/0100152000022000/romfs on the SD card (or your emulator's mod folder), then copy the staging folder over fresh.",
  ];
  const ul = document.createElement("ul");
  ul.style.margin = "4px 0 0 0";
  ul.style.paddingLeft = "20px";
  for (const t of items) ul.appendChild(cgEl("li", null, t));
  tb.appendChild(ul);
  trouble.appendChild(tb);
  return trouble;
}

// Plain pictures for the ways to help (a thumbs-up, a star, a cup of coffee, a speech bubble), drawn for this app: not the logos of GameBanana,
// GitHub, Buy Me a Coffee or Discord, which are theirs and come with rules about who may show them. They take the colour of the text around them.
const SUPPORT_ICONS = {
  like: '<svg viewBox="0 0 24 24" aria-hidden="true"><g fill="currentColor"><rect x="3" y="10" width="4" height="10" rx="1"/>'
    + '<path d="M9 20V10.5l3.2-6.2c.3-.6 1-.8 1.6-.5.6.3.9 1 .7 1.6L14 9h4.6c1.2 0 2 1.1 1.7 2.2l-1.6 6.6c-.2.8-.9 1.2-1.7 1.2H9z"/></g></svg>',
  star: '<svg viewBox="0 0 24 24" aria-hidden="true"><polygon fill="currentColor" points="12,2.5 14.9,8.9 21.8,9.6 16.6,14.2 18.1,21 12,17.5 5.9,21 7.4,14.2 2.2,9.6 9.1,8.9"/></svg>',
  chat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-7l-4.5 3.5V17H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>',
  coffee: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9z"/>'
    + '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5v2M11 3.5v2M14 3.5v2"/></svg>',
};

// The "enjoying your mods?" card on the All done page: three quick ways to help, each with why it matters (see state-and-helpers.js).
function supportCard() {
  const card = cgEl("div", "modal-card pg-support-card");
  const head = cgEl("div", "modal-card-header");
  head.appendChild(cgEl("span", "modal-card-title", "Enjoying your mods?"));
  card.appendChild(head);
  const pad = cgEl("div", "uis-pad");
  pad.appendChild(cgEl("div", "pg-support-intro", "This app is free and made by one person. If it saved you some time, these take a few seconds and help a lot:"));
  const ways = [
    GAMEBANANA_PAGE_URL && { icon: "like", label: "Like it on GameBanana", why: "The more likes the page has, the more people find it.", open: "Open GameBanana", url: GAMEBANANA_PAGE_URL },
    { icon: "star", label: "Star it on GitHub", why: "It helps other modders find the project.", open: "Open GitHub", url: GITHUB_URL },
    { icon: "coffee", label: "Buy me a coffee", why: "If you feel so inclined.", open: "Open Buy Me a Coffee", url: SUPPORT_URL },
    { icon: "chat", label: "Join the Discord", why: "Get help, share ideas, or work on mods together.", open: "Open Discord", url: DISCORD_URL },
  ].filter(Boolean);
  for (const way of ways) {
    const row = cgEl("div", "pg-support-way");
    const left = cgEl("div", "pg-support-left");
    const icon = cgEl("span", "pg-support-icon");
    icon.innerHTML = SUPPORT_ICONS[way.icon];   // (fixed pictures defined above, nothing from outside)
    left.appendChild(icon);
    const text = cgEl("div", "pg-support-text");
    text.appendChild(cgEl("div", "pg-support-label", way.label));
    text.appendChild(cgEl("div", "pg-support-why", way.why));
    left.appendChild(text);
    row.appendChild(left);
    row.appendChild(button(way.open, "ghost small", () => openExternal(way.url)));
    pad.appendChild(row);
  }
  card.appendChild(pad);
  return card;
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
    // All done: no checklist any more (it's finished). Back goes to the previous step, then the ways to support the app (like, star,
    // donate), and the troubleshooting tips stay here for anyone who finds it isn't working after all.
    body.appendChild(statusCard("ok", "🎉", "All done - your mods work on your Switch",
      "If you change your mods later, the steps above will light up again and you can come back here."));
    const row = cgEl("div", "pg-cta pg-done-actions");
    row.appendChild(button("Back", "ghost", () => goStep("commit")));
    body.appendChild(row);
    body.appendChild(supportCard());
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
  ol.appendChild(cgEl("li", null, "On the SD card, delete atmosphere/contents/0100152000022000/romfs if it's already there from an earlier copy - don't just copy on top of it. (A mod you've since deselected would leave its old files behind otherwise, which is why a deselected course or character can keep showing its old picture or name in-game.)"));
  ol.appendChild(cgEl("li", null, "Copy everything inside the staging folder onto the root of your Switch's SD card. If asked, say yes to merge folders and replace files - that's fine now that the old romfs folder is gone."));
  ol.appendChild(cgEl("li", null, "Plug the SD card back in your Switch. Fully close Mario Kart 8 Deluxe if it was running (not just the Home button), then start it again."));
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

