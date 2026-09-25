// ---- waiting: placeholders shaped like what is coming, and a spinner for the wait itself ----
function loadingNote(text) {
  const n = document.createElement("div");
  n.className = "load-note";
  const sp = document.createElement("span");
  sp.className = "spin";
  n.appendChild(sp);
  n.appendChild(document.createTextNode(text));
  return n;
}
function skeleton(w, h, radius) {
  const d = document.createElement("div");
  d.className = "sk";
  d.style.width = typeof w === "number" ? w + "px" : (w || "100%");
  d.style.height = (h || 16) + "px";
  if (radius) d.style.borderRadius = radius;
  return d;
}
function skeletonGrid(n) {
  const g = document.createElement("div");
  g.className = "gb-browse-grid";
  for (let i = 0; i < n; i++) { const t = document.createElement("div"); t.className = "sk sk-tile"; g.appendChild(t); }
  return g;
}
// "itemName::recordType::modId" keys for individual mod blocks (within an
// otherwise-expanded section) that should render collapsed - set after that
// specific mod's download succeeds, so a companion mod fetched afterward
// (voice, UI icons, ...) stays visible instead of the whole section
// vanishing out from under it.
const gbModBlockCollapsed = new Set();

function buildTile(displayName, units, onClick, gbAttempted, opts) {
  opts = opts || {};
  const overlayCount = !!opts.overlayCount;
  const total = units.length;
  const checkedUnits = units.filter(k => state.checked[k]);
  const selected = checkedUnits.length;
  const tile = document.createElement("div");
  tile.className = "char-tile";
  tile.dataset.char = displayName;
  if (selected > 0) tile.classList.add("has-selected");
  if (total === 0) tile.classList.add("no-mods");
  if (opts.gradientColors) {
    tile.classList.add("has-gradient");
    tile.style.backgroundImage = buildCornerGradient(opts.gradientColors);
  }
  tile.addEventListener("click", onClick);

  // Means a GameBanana download was actually attempted for this item but
  // produced zero usable merge units (needs manual fix / missing romfs
  // folder / etc.) - without this, that state looked identical to "nobody
  // has touched this yet" on the grid, so it was easy to lose track of
  // while scanning for what's left.
  if (gbAttempted && total === 0) {
    tile.classList.add("needs-attention");
    const dot = document.createElement("div");
    dot.className = "char-attention-dot";
    dot.title = "Downloaded, but couldn't be auto-merged - open it to see why";
    tile.appendChild(dot);
  }

  let badge = null;
  if (!opts.hideBadge) {
    badge = document.createElement("div");
    badge.className = "char-badge";
    badge.textContent = initials(displayName);
    tile.appendChild(badge);
  }

  const name = document.createElement("div");
  name.className = "char-name";
  name.textContent = displayName;
  tile.appendChild(name);

  if (total === 0) {
    if (gbAttempted) {
      const count = document.createElement("div");
      count.className = "char-count count-attention";
      count.textContent = "needs attention";
      tile.appendChild(count);
    } else {
      // No visible text for the plain "nothing downloaded yet" case - the tile is already
      // faded (.no-mods, below) to say so at a glance; the words live in the tooltip instead.
      // Set directly (courses/vehicles stop here) AND as countNote (characters' applyCharacterLook
      // reads that back and folds it in alongside whatever the tile's icon note says).
      tile.title = tile.dataset.countNote = "No mods yet";
    }
  } else if (overlayCount && opts.showCount === false) {
    // Counts are switched off (Settings > Character Select). One state is still worth a quiet cue:
    // mods are downloaded but none is ticked yet. The numbers stay in the tile's tooltip.
    tile.dataset.countNote = `${selected} of ${total} mod${total === 1 ? "" : "s"} ticked`;
    if (selected === 0) {
      const ring = document.createElement("div");
      ring.className = "tile-pending-dot";
      ring.title = `${total} mod${total === 1 ? "" : "s"} downloaded - none ticked yet`;
      tile.appendChild(ring);
    }
  } else if (overlayCount) {
    // Notification-style bubble instead of a bottom-of-tile line, so it can
    // sit on top of a course preview image rather than pushing it down.
    const bubble = document.createElement("div");
    bubble.className = "tile-count-bubble";
    bubble.textContent = `${selected}/${total}`;
    bubble.title = `${selected}/${total} selected`;
    tile.appendChild(bubble);
  } else {
    const count = document.createElement("div");
    count.className = "char-count";
    count.textContent = `${selected}/${total} selected`;
    tile.appendChild(count);
  }

  return { tile, checkedUnits, selected, badge, nameEl: name };
}

// The look of each character tile: the first available of the select-screen, results and map
// icons - the game's own once base files are set up, or a mod's/the user's if something changes
// it - and its name (Api.get_character_tile_view). Remembered between renders so a tile redrawn
// after a tick doesn't flash back to blank while the fresh answer loads.
let characterLooks = {};
let characterReview = {};   // name -> {applicable, reviewed} for characters with ticked mods
let courseReview = {};      // name -> {applicable, finished} for courses with ticked mods (Api.get_course_tile_view)
let partReview = {};        // name -> {applicable, finished, shown, icon} for vehicle parts with ticked mods (Api.get_part_tile_view)
let characterVoice = {};    // name -> {race, menu, from} for characters with a ticked mod that ships voice files
let characterLooksToken = 0;
let characterLooksTimer = null;
let characterLooksFor = {};   // tile name -> the ticked mods the answer above was worked out for

function refreshLooksPending(refs, wanted) {
  // a tile with ticked mods whose answer isn't in yet (the app was just opened, or the ticks changed since) pulses
  for (const r of refs) r.tile.classList.toggle("looks-loading", r.ticked.length > 0 && characterLooksFor[r.displayName] !== wanted.get(r));
}

function applyCharacterLook(ref, looks) {
  const { tile, displayName, names, gradientColors } = ref;
  const found = names.map(n => looks[n] ? { n, ...looks[n] } : null).filter(Boolean);
  tile.querySelectorAll(".char-icon, .variant-ph").forEach(e => e.remove());
  tile.classList.remove("has-icon", "has-pair");
  tile._lookNames = names;   // read by the name plate when the mouse is over this tile
  tile._variants = ref.variants || null;
  const nameEl = tile.querySelector(".char-name");
  nameEl.textContent = displayName;
  const countNote = tile.dataset.countNote || "";
  tile.title = countNote;
  if (gradientColors) tile.style.backgroundImage = buildCornerGradient(gradientColors);
  if (!found.length) return;
  const withIcon = found.find(f => f.icon);
  const notes = [];
  if (ref.variants && withIcon) {
    // both variants, each in its place: its picture, or a placeholder saying which one it is
    const slots = [];
    ref.variants.forEach((v, i) => {
      const f = looks[v.name];
      const pos = i === 0 ? "tl" : "br";
      let el;
      if (f && f.icon) {
        el = document.createElement("img");
        el.className = "char-icon variant " + pos;
        el.src = f.icon;
        el.alt = v.label;
      } else {
        el = cgEl("div", "variant-ph " + pos, v.label);
      }
      el.addEventListener("click", (e) => { e.stopPropagation(); selectCharacter(v.name); });
      slots.push(el);
      if (f && f.name) notes.push(`${v.label}: name ${f.name}${f.guessed ? " (guessed from the mod)" : ""}`);
    });
    tile.prepend(...slots);   // (in order: the second variant is drawn over the first where they overlap)
    tile.classList.add("has-icon", "has-pair");
  } else if (withIcon) {
    const img = document.createElement("img");
    img.className = "char-icon";
    img.src = withIcon.icon;
    img.alt = "";
    tile.insertBefore(img, tile.firstChild);
    tile.classList.add("has-icon");
  }
  const named = found.filter(f => f.name);
  if (named.length) {
    nameEl.textContent = named.map(f => f.name).join(" / ");
    if (!(ref.variants && withIcon)) notes.push(`Name: ${named.map(f => f.name + (f.guessed ? " (guessed from the mod)" : "")).join(", ")} - the game's own name is ${found.length === 1 ? found[0].n : displayName}`);
  }
  if (countNote) notes.push(countNote);
  tile.title = notes.join("\n");
}

function speakerSvg() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const cone = document.createElementNS(NS, "path");
  cone.setAttribute("class", "speaker-cone");
  cone.setAttribute("d", "M1.5 5.8h2.7L8 2.6v10.8l-3.8-3.2H1.5z");
  const near = document.createElementNS(NS, "path");
  near.setAttribute("class", "speaker-wave w1");
  near.setAttribute("d", "M10.2 5.5a3.6 3.6 0 0 1 0 5");
  const far = document.createElementNS(NS, "path");
  far.setAttribute("class", "speaker-wave w2");
  far.setAttribute("d", "M12.3 3.4a6.6 6.6 0 0 1 0 9.2");
  svg.append(cone, near, far);
  return svg;
}
function voiceWhat(race, menu) {
  return race && menu ? "in-race voice lines and menu voice" : race ? "in-race voice lines" : "menu voice";
}

// A ticked mod that ships voice files for the character: a small speaker on its tile (and a line in the tile's tooltip).
function applyVoiceMarker(ref, voice) {
  const tile = ref.tile;
  tile.querySelectorAll(".tile-voice-mark").forEach(e => e.remove());
  const found = ref.names.map(n => voice[n]).filter(Boolean);
  if (!found.length) return;
  const from = [...new Set(found.flatMap(f => f.from))];
  const note = `Voice files: ${voiceWhat(found.some(f => f.race), found.some(f => f.menu))} (from ${from.join(", ")})`
    + (found.some(f => f.select) ? "\nSelect sound: click to hear it" : "");
  const mark = cgEl("div", "tile-voice-mark");
  if (voiceNow.speaking && ref.names.includes(voiceNow.speaking)) mark.classList.add("speaking");
  mark.setAttribute("role", "img");
  mark.setAttribute("aria-label", note);
  mark.appendChild(speakerSvg());
  tile.appendChild(mark);
  tile.title = tile.title ? tile.title + "\n" + note : note;
}

// Name and Icons are two independent tasks (each its own dot, confirmed separately - see
// mod_manager.py's _review_state()); a character counts as "applicable"/"finished" from the two
// combined: applicable if either task has something to look at, finished once every applicable
// one of them is done. Voice is never part of this - it's the one optional task, never gating.
function reviewApplicable(r) { return !!(r && (r.name_applicable || r.icons_applicable)); }
function reviewFinished(r) {
  if (!r) return true;
  return (!r.name_applicable || r.name_done) && (!r.icons_applicable || r.icons_done);
}

function applyReviewMarker(ref, review) {
  const tile = ref.tile;
  tile.querySelectorAll(".tile-review-mark").forEach(e => e.remove());
  const rs = ref.names.map(n => review[n]).filter(reviewApplicable);
  if (!rs.length) return;
  const todo = rs.some(r => !reviewFinished(r));
  const mark = document.createElement("div");
  mark.className = "tile-review-mark " + (todo ? "todo" : "done");
  mark.title = todo ? "Ticked - open it to finish its name and icons" : "Completed";
  if (!todo) mark.textContent = "\u2713";
  tile.appendChild(mark);
}

// Characters, courses and vehicle parts whose walkthrough isn't finished: ticked mods that change how they look, Name and/or
// Icons not yet confirmed.
function unfinishedNames(review) {
  return Object.entries(review || {}).filter(([, r]) => reviewApplicable(r) && !reviewFinished(r)).map(([n]) => n);
}
// (a course's review is {applicable, finished} - already combined by the backend - rather than the two tasks)
function unfinishedCourseNames() {
  return Object.entries(courseReview || {}).filter(([, r]) => r && r.applicable && !r.finished).map(([n]) => n);
}
function unfinishedPartNames() {
  return Object.entries(partReview || {}).filter(([, r]) => r && r.applicable && !r.finished).map(([n]) => n);
}
function unfinishedCount() { return unfinishedNames(characterReview).length + unfinishedCourseNames().length + unfinishedPartNames().length; }
// Everything unfinished, asked afresh: [{kind: "character" | "course" | "part", name, shown}], characters first.
async function freshUnfinished() {
  try {
    const view = await pywebview.api.get_character_tile_view((state.roster || []).map(r => r.name));
    if (view) { characterLooks = view.looks; characterReview = view.review; characterVoice = view.voice || {}; }
  } catch (e) { /* fall back on what the grid last knew */ }
  try { await refreshCourseReview(true); } catch (e) { /* likewise */ }
  try { await refreshPartReview(true); } catch (e) { /* likewise */ }
  return [
    ...unfinishedNames(characterReview).map(n => ({ kind: "character", name: n, shown: (characterLooks[n] && characterLooks[n].name) || n })),
    ...unfinishedCourseNames().map(n => ({ kind: "course", name: n, shown: (courseReview[n] && courseReview[n].shown) || n })),
    ...unfinishedPartNames().map(n => ({ kind: "part", name: n, shown: (partReview[n] && partReview[n].shown) || n })),
  ];
}
const itemKey = (kind, name) => kind + "|" + name;
// "3 characters", "1 course", "2 characters and 1 course", "1 character, 2 courses and 3 vehicle parts"
function unfinishedPhrase(list) {
  const nc = list.filter(x => x.kind === "character").length, nk = list.filter(x => x.kind === "course").length;
  const np = list.filter(x => x.kind === "part").length;
  const bits = [nc && `${nc} character${nc === 1 ? "" : "s"}`, nk && `${nk} course${nk === 1 ? "" : "s"}`, np && `${np} vehicle part${np === 1 ? "" : "s"}`].filter(Boolean);
  return bits.length > 1 ? bits.slice(0, -1).join(", ") + " and " + bits[bits.length - 1] : bits[0] || "";
}

// A name typed in the walkthrough's first step but not confirmed yet is kept as a draft while the user looks at
// something else, so leaving the card never throws it away. character -> {value, base (the saved name it was typed over)}
const nameDrafts = {};

// Leaving the "Choose mods" stage with characters or courses still unfinished: ask once, at the point it starts to matter.
// Resolves true to carry on, false to stay.
// "Review them": a guided pass through the unfinished characters and courses, one after another. A bar on top of each card says
// where the user is ("2 of 3") and offers Skip and Stop; finishing a character moves on to the next, and at the end the
// bar offers the next stage.
const reviewQueue = { active: false, items: [], skipped: new Set(), current: null, finished: false, el: null, timer: null };

function startReviewQueue(list) {
  reviewQueue.active = true;
  reviewQueue.items = list.map(x => ({ kind: x.kind, name: x.name }));
  reviewQueue.skipped = new Set();
  reviewQueue.current = null;
  reviewQueue.finished = false;
  return advanceReviewQueue();
}
function openReviewItem(item) {
  if (item.kind === "course") return openCourseCard(item.name);
  if (item.kind === "part") return openPartCard(item.name);
  switchView("characters");
  return openCharacterModal(item.name);
}
async function advanceReviewQueue() {
  if (!reviewQueue.active) return;
  const list = await freshUnfinished();
  const left = reviewQueue.items.filter(i => list.some(x => x.kind === i.kind && x.name === i.name) && !reviewQueue.skipped.has(itemKey(i.kind, i.name)));
  reviewQueue.remaining = left.length;
  if (!left.length) {
    reviewQueue.finished = true;
    reviewQueue.current = null;
    renderReviewBar();
    if (!reviewQueue.el || !reviewQueue.el.isConnected) openReviewItem(reviewQueue.items[reviewQueue.items.length - 1]);
    return;
  }
  reviewQueue.current = left[0];
  await openReviewItem(left[0]);
  renderReviewBar();
}
function stopReviewQueue() {
  reviewQueue.active = false;
  clearTimeout(reviewQueue.timer);
  if (reviewQueue.el) reviewQueue.el.remove();
  reviewQueue.el = null;
}
// a character, course or part was just finished: on to the next one after a moment (long enough to see "Completed")
function onItemFinished(kind, name) {
  if (!reviewQueue.active || !reviewQueue.items.some(i => i.kind === kind && i.name === name)) return;
  clearTimeout(reviewQueue.timer);
  reviewQueue.timer = setTimeout(advanceReviewQueue, 700);
}
function buildReviewBar() {
  const el = cgEl("div", "review-bar");
  reviewQueue.el = el;
  renderReviewBar();
  return el;
}
function renderReviewBar() {
  const el = reviewQueue.el;
  if (!el || !reviewQueue.active) return;
  el.replaceChildren();
  el.classList.toggle("is-done", reviewQueue.finished);
  if (reviewQueue.finished) {
    const stillOpen = new Set([...unfinishedNames(characterReview).map(n => itemKey("character", n)), ...unfinishedCourseNames().map(n => itemKey("course", n)),
                               ...unfinishedPartNames().map(n => itemKey("part", n))]);
    const skipped = [...reviewQueue.skipped].filter(k => stillOpen.has(k)).length;
    el.appendChild(cgEl("span", "review-text", skipped ? `Done - ${skipped} skipped, still unfinished.` : "All done - everything is finished."));
    const t = flow.status ? flowNextTarget("mods", flow.status) : null;
    if (t) el.appendChild(button(t.label + "  \u2192", "primary small", () => { stopReviewQueue(); goStep(t.to, { skipGate: true }); }));
    el.appendChild(button("Close", "ghost small", stopReviewQueue));
    return;
  }
  const total = reviewQueue.items.length;
  const pos = total - (reviewQueue.remaining || 0) + 1;
  const kinds = new Set(reviewQueue.items.map(i => i.kind));
  const noun = kinds.size > 1 ? "items" : kinds.has("course") ? "courses" : kinds.has("part") ? "vehicle parts" : "characters";
  el.appendChild(cgEl("span", "review-text", `Reviewing unfinished ${noun} \u00b7 ${Math.min(pos, total)} of ${total}`));
  el.appendChild(button("Skip", "ghost small", () => { if (reviewQueue.current) reviewQueue.skipped.add(itemKey(reviewQueue.current.kind, reviewQueue.current.name)); advanceReviewQueue(); }));
  el.appendChild(button("Stop", "ghost small", stopReviewQueue));
}

let gateBusy = false;
async function passUnfinishedGate() {
  if (gateBusy) return false;
  gateBusy = true;
  try {
    const list = await freshUnfinished();
    if (!list.length) return true;
    return await new Promise(resolve => showUnfinishedGate(list, resolve));
  } finally { gateBusy = false; }
}
function showUnfinishedGate(list, resolve) {
  const back = cgEl("div", "gate-backdrop");
  const card = cgEl("div", "gate-card");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-modal", "true");
  const n = list.length;
  card.appendChild(cgEl("h3", null, `${unfinishedPhrase(list)} ${n === 1 ? "isn't" : "aren't"} finished`));
  const chips = cgEl("div", "gate-chips");
  for (const it of list.slice(0, 8)) chips.appendChild(cgEl("span", "gate-chip", it.shown !== it.name ? `${it.shown} (${it.name})` : it.name));
  if (n > 8) chips.appendChild(cgEl("span", "gate-chip more", `and ${n - 8} more`));
  card.appendChild(chips);
  card.appendChild(cgEl("p", null, `${n === 1 ? "Its name or icon hasn't" : "Their names or icons haven't"} been confirmed yet. If you continue, they're used as they are now - and a name that was only a guess is built into the game's menus without being confirmed.`));
  const acts = cgEl("div", "gate-actions");
  let finished = false;
  const done = (value, after) => {
    if (finished) return;
    finished = true;
    back.remove();
    document.removeEventListener("keydown", onKey, true);
    resolve(value);
    if (after) after();
  };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done(false); } };
  document.addEventListener("keydown", onKey, true);
  const review = button("Review them", "primary", () => done(false, () => startReviewQueue(list)));
  acts.appendChild(review);
  acts.appendChild(button("Continue anyway", "ghost", () => done(true)));
  card.appendChild(acts);
  back.appendChild(card);
  back.addEventListener("click", (e) => { if (e.target === back) done(false); });
  document.body.appendChild(back);
  review.focus();
}

function scheduleCharacterLooks(refs) {
  const wanted = new Map(refs.map(r => [r, [...r.ticked].sort().join("|")]));
  for (const r of refs) { applyCharacterLook(r, characterLooks); applyReviewMarker(r, characterReview); applyVoiceMarker(r, characterVoice); }
  refreshLooksPending(refs, wanted);
  if (variantSwitchRefresh) variantSwitchRefresh();   // (the ticks in it may have changed)
  const token = ++characterLooksToken;
  clearTimeout(characterLooksTimer);
  // the tick that caused this render is saved by a call that isn't awaited - give it a moment to land
  characterLooksTimer = setTimeout(async () => {
    let view = null;
    try { view = await pywebview.api.get_character_tile_view([...new Set(refs.flatMap(r => r.names))]); } catch (e) { /* no answer: stop pulsing below */ }
    if (token !== characterLooksToken) return;   // (a newer render is waiting for its own answer)
    if (!view) { for (const r of refs) r.tile.classList.remove("looks-loading"); return; }
    characterLooks = view.looks;
    characterReview = view.review;
    characterVoice = view.voice || {};
    for (const [r, sig] of wanted) characterLooksFor[r.displayName] = sig;
    for (const r of refs) if (r.tile.isConnected) { applyCharacterLook(r, characterLooks); applyReviewMarker(r, characterReview); applyVoiceMarker(r, characterVoice); }
    refreshLooksPending(refs, wanted);
    if (variantSwitchRefresh) variantSwitchRefresh();
    updateNameBar();
    try { if (flow.status) { renderStepBar(); renderNextButton(); } } catch (e) { /* (the flow bar isn't up yet) */ }
  }, 400);
}

// The white corner frame: one element that slides to whichever tile the mouse is over. It is placed
// without animation the first time (so it doesn't fly in from a corner) and glides after that.
// `host` is a stable, positioned element the frame lives in (it must not be the grid that gets rebuilt);
// `roots` are the elements whose tiles it follows; `tileSelector` says what counts as a tile.
function makeHoverFrame(host, roots, tileSelector) {
  const frame = document.createElement("div");
  frame.className = "hover-frame";
  host.appendChild(frame);
  let shown = false;
  function hide() {
    frame.classList.remove("show");
    shown = false;
  }
  function move(tile) {
    const hr = host.getBoundingClientRect(), tr = tile.getBoundingClientRect();
    const pad = 4;   // same margin as the yellow brackets
    const x = tr.left - hr.left + host.scrollLeft - host.clientLeft - pad;
    const y = tr.top - hr.top + host.scrollTop - host.clientTop - pad;
    if (!shown) frame.style.transition = "none";
    frame.style.transform = `translate(${x}px, ${y}px)`;
    frame.style.width = (tr.width + 2 * pad) + "px";
    frame.style.height = (tr.height + 2 * pad) + "px";
    if (!shown) { void frame.offsetWidth; frame.style.transition = ""; }
    frame.classList.add("show");
    shown = true;
  }
  for (const root of roots) {
    root.addEventListener("mouseover", (e) => {
      const tile = e.target.closest(tileSelector);
      if (tile && root.contains(tile)) move(tile);
    });
    root.addEventListener("mouseleave", hide);
  }
  return { hide };
}
const characterHover = makeHoverFrame(document.getElementById("char-grid-col"), [document.getElementById("char-grid")], ".char-tile");
const courseHover = makeHoverFrame(document.getElementById("view-courses"),
  [document.getElementById("cup-grid"), document.getElementById("course-strip")], ".cup-tile, .char-tile");

async function renderCharacterGrid() {
  const grid = document.getElementById("char-grid");
  grid.innerHTML = "";
  characterHover.hide();   // the tile under the mouse was just replaced
  const conflictChecks = [];
  const coveredNames = new Set();
  const lookRefs = [];
  const showCount = !!(state.settings && state.settings.show_tile_counts);
  hoverTileEl = null;

  for (const item of CHARACTER_GRID_LAYOUT) {
    let tile, checkedUnits, selected;

    if (typeof item === "string") {
      coveredNames.add(item);
      const entry = findRosterEntry(item);
      ({ tile, checkedUnits, selected } = buildTile(
        item, entry.units,
        () => selectCharacter(item), entry.gb_attempted,
        { overlayCount: true, hideBadge: true, showCount, gradientColors: CHARACTER_COLORS[item] }
      ));
      lookRefs.push({ tile, displayName: item, names: [item], gradientColors: CHARACTER_COLORS[item], ticked: checkedUnits });
    } else {
      // Group tile (e.g. Villager, Inkling) - combine both options' stats.
      const entries = item.options.map(opt => { coveredNames.add(opt); return findRosterEntry(opt); });
      const units = entries.flatMap(e => e.units);
      const gbAttempted = entries.some(e => e.gb_attempted);
      ({ tile, checkedUnits, selected } = buildTile(
        item.group, units,
        () => selectCharacter(defaultVariant(item)), gbAttempted,
        { overlayCount: true, hideBadge: true, showCount, gradientColors: CHARACTER_COLORS[item.group] }
      ));
      lookRefs.push({ tile, displayName: item.group, names: item.options, gradientColors: CHARACTER_COLORS[item.group], ticked: checkedUnits,
                      variants: item.options.map(o => ({ name: o, label: groupOptionLabel(o, item.group) })) });
    }

    if (selected >= 2) {
      conflictChecks.push(
        pywebview.api.check_conflicts(checkedUnits).then(result => {
          if (result.conflicts && result.conflicts.length > 0) {
            tile.classList.add("has-conflict");
            const badge = document.createElement("div");
            badge.className = "char-conflict-badge";
            badge.textContent = "!";
            badge.title = `${result.conflicts.length} conflicting file(s) among selected mods`;
            tile.appendChild(badge);
          }
        })
      );
    }

    grid.appendChild(tile);
  }

  // Defensive: show any roster entries not covered by the fixed grid layout
  // (e.g. a newly added character not yet placed) rather than hiding them.
  const leftovers = state.roster.filter(r => !coveredNames.has(r.name));
  if (leftovers.length > 0) {
    const otherHeading = document.createElement("div");
    otherHeading.className = "char-grid-other-heading";
    otherHeading.textContent = "Other";
    grid.appendChild(otherHeading);
    for (const entry of leftovers) {
      const { tile, checkedUnits, selected } = buildTile(
        entry.name, entry.units,
        () => selectCharacter(entry.name), entry.gb_attempted,
        { overlayCount: true, hideBadge: true, showCount, gradientColors: CHARACTER_COLORS[entry.name] }
      );
      lookRefs.push({ tile, displayName: entry.name, names: [entry.name], gradientColors: CHARACTER_COLORS[entry.name], ticked: checkedUnits });
      if (selected >= 2) {
        conflictChecks.push(
          pywebview.api.check_conflicts(checkedUnits).then(result => {
            if (result.conflicts && result.conflicts.length > 0) {
              tile.classList.add("has-conflict");
              const badge = document.createElement("div");
              badge.className = "char-conflict-badge";
              badge.textContent = "!";
              tile.appendChild(badge);
            }
          })
        );
      }
      grid.appendChild(tile);
    }
  }
  scheduleCharacterLooks(lookRefs);
  markActiveTile();
  fitCharacterGrid();
  ensureDockedSelection();
  await Promise.all(conflictChecks);
}

function closeModal() {
  document.getElementById("modal-backdrop").classList.remove("above-settings");
  document.getElementById("modal-backdrop").hidden = true;
  openCharacter = null;
  markActiveTile();
}

