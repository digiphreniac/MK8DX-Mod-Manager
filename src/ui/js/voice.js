// ================= The character card (Character Select) =================
// Two steps - Mod (find / choose / ticked) and Look (icons and name, checked with "Looks right") - and only
// the step that needs the user is open; a finished one is a single line with a "Change" button. Everything the
// old card had is still here (mod rows with their Files panel, clashes, GameBanana, the icon-picture window).
const gbDefaulted = new Set();   // characters whose GameBanana section has already been folded away once

// ---- Playing a mod's voice files. One sound at a time: starting another (or opening another card) stops the first.
// The .wav is made by the backend (voice_audio.py) and comes back as base64; `clipId` is an id from get_voice_clips().
const voiceNow = { audio: null, btn: null, token: 0, speaking: null };   // speaking: the character whose select sound plays
// the speaker on the tile of the character whose select sound is playing (if any) lights up; the rest are plain
function markSpeaking() {
  for (const tile of document.querySelectorAll("#char-grid .char-tile")) {
    const on = !!voiceNow.speaking && !!tile._lookNames && tile._lookNames.includes(voiceNow.speaking);
    const mark = tile.querySelector(".tile-voice-mark");
    if (mark) mark.classList.toggle("speaking", on);
  }
}
function voiceGlyph(kind) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", kind === "stop" ? "M3.5 3.5h9v9h-9z" : "M4 2.2v11.6L13.6 8z");
  svg.appendChild(p);
  return svg;
}
// A small trash-can icon for a line's own delete/remove-edit button - a dedicated control, separate from the chip
// that just says what's currently on the line, so "what is this" and "undo it" aren't the same clickable thing.
function trashGlyph() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = '<rect x="3" y="4" width="10" height="1.4" rx="0.7"/><rect x="6.2" y="1.6" width="3.6" height="1.4" rx="0.7"/>'
    + '<path d="M4.2 5.6h7.6l-.6 8.2a1 1 0 01-1 .9H5.8a1 1 0 01-1-.9L4.2 5.6z"/>';
  return svg;
}
function delButton(title, onClick) {
  const b = cgEl("button", "ve-del");
  b.type = "button";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.appendChild(trashGlyph());
  b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
  return b;
}
function setPlayState(btn, state, msg) {
  btn.dataset.state = state;
  btn.replaceChildren(voiceGlyph(state === "playing" ? "stop" : "play"));
  const text = state === "playing" ? "Stop" : state === "loading" ? "Getting the sound ready" : state === "error" ? (msg || "Couldn't play this") : `Play ${btn._what || "this sound"}`;
  btn.title = text;
  btn.setAttribute("aria-label", text);
}
function voiceStop() {
  voiceNow.token++;
  if (voiceNow.speaking) { voiceNow.speaking = null; markSpeaking(); }
  if (voiceNow.audio) { try { voiceNow.audio.pause(); } catch (e) { /* (already gone) */ } voiceNow.audio = null; }
  if (voiceNow.btn) { if (voiceNow.btn.dataset.state !== "error") setPlayState(voiceNow.btn, "idle"); voiceNow.btn = null; }
}
function voiceError(host, msg) {
  if (!host) return;
  host.querySelectorAll(":scope > .voice-err").forEach(e => e.remove());
  if (msg) host.appendChild(cgEl("div", "reveal-error voice-err", msg));
}
async function voicePlay(unitKey, clipId, btn, host) {
  return voicePlayWith(() => pywebview.api.get_voice_clip(unitKey, clipId), btn, host);
}
// `fetch` gives {success, wav (base64), error, silent}; a silent sound says so instead of playing nothing
async function voicePlayWith(fetch, btn, host) {
  const wasBusy = voiceNow.btn === btn && (btn.dataset.state === "playing" || btn.dataset.state === "loading");
  voiceStop();
  voiceError(host, null);
  if (wasBusy) return;                              // a second click on the button that is playing stops it
  const token = voiceNow.token;
  voiceNow.btn = btn;
  setPlayState(btn, "loading");
  let r;
  try { r = await fetch(); } catch (e) { r = { success: false, error: "Couldn't play this: " + e }; }
  if (token !== voiceNow.token) return;             // stopped, or something else was started, while it was being made
  const fail = (msg) => { setPlayState(btn, "error", msg); voiceError(host, msg); voiceNow.btn = null; };
  if (!r || !r.success) return fail((r && r.error) || "Couldn't play this sound.");
  if (r.silent) {
    setPlayState(btn, "idle");
    voiceNow.btn = null;
    voiceError(host, "This sound is silent - there is nothing to hear.");
    return;
  }
  const audio = new Audio("data:audio/wav;base64," + r.wav);
  audio.volume = 0.7;                               // (some mods' voices are mastered very loud)
  voiceNow.audio = audio;
  audio.addEventListener("ended", () => { if (voiceNow.audio === audio) voiceStop(); });
  try { await audio.play(); } catch (e) { if (token === voiceNow.token) fail("Couldn't play this sound here."); return; }
  if (token === voiceNow.token) setPlayState(btn, "playing");
}
function voicePlayButton(unitKey, clipId, what, host) {
  const b = cgEl("button", "voice-play");
  b.type = "button";
  b._what = what;
  setPlayState(b, "idle");
  b.addEventListener("click", (e) => { e.stopPropagation(); voicePlay(unitKey, clipId, b, host); });
  return b;
}

// The character-select sound: the voice the game plays when the character is picked, from the character's ticked mods
// (Api.get_select_voice). Played whenever the character is picked (its tile, or its side of the Villager / Inkling
// switch) and when its appearance becomes finished; the speaker on its tile lights up while it plays. It shares the
// one-sound-at-a-time player above, and says nothing at all when there is no such sound or it can't play.
async function playSelectVoice(name) {
  if (state.settings && state.settings.play_select_voice === false) return;
  voiceStop();
  const token = voiceNow.token;
  let res;
  try { res = await pywebview.api.get_select_voice(name); } catch (e) { return; }
  if (token !== voiceNow.token || !res || !res.success) return;
  const audio = new Audio("data:audio/wav;base64," + res.wav);
  audio.volume = 0.7;                                // (some mods' voices are mastered very loud)
  voiceNow.audio = audio;
  audio.addEventListener("ended", () => { if (voiceNow.audio === audio) voiceStop(); });
  try { await audio.play(); } catch (e) { return; /* (not allowed to start here - nothing to say) */ }
  if (token === voiceNow.token) { voiceNow.speaking = name; markSpeaking(); }
}

// Picking a character: its card (or, for Villager / Inkling, the one you chose), and its select sound
function selectCharacter(name) {
  openCharacterModal(name);
  playSelectVoice(name);
}

// The "Voice lines" window: every sound in the mod's voice files, each with its own play button.
async function openVoiceLines(unitKey, modLabel) {
  ui.menu.closeAll();
  voiceStop();
  const modal = ui.modal({ variant: "card", class: "voice-card", title: "Voice lines", footer: true, destroyOnClose: true, onClose: () => voiceStop() });
  const card = modal.body;
  card.appendChild(cgEl("div", "voice-sub", modLabel));
  const list = cgEl("div", "voice-list");
  list.appendChild(ui.loading("Reading the voice files\u2026"));
  card.appendChild(list);
  const closeBtn = button("Close", "primary", () => modal.close());
  modal.footer.appendChild(closeBtn);
  modal.open();
  closeBtn.focus();
  let r;
  try { r = await pywebview.api.get_voice_clips(unitKey); } catch (e) { r = null; }
  if (!modal.isOpen) return;
  list.replaceChildren();
  const clips = (r && r.clips) || [];
  if (!clips.length) {
    list.appendChild(cgEl("div", "voice-empty", "No voice sounds could be read from this mod." + ((r && r.problems || []).length ? ` (Couldn't read: ${r.problems.join(", ")})` : "")));
    return;
  }
  const GROUPS = { select: "Character select", race: "During the race", horn: "Horn" };
  let last = null;
  for (const c of clips) {
    if (c.group !== last) { list.appendChild(cgEl("div", "voice-group", GROUPS[c.group] || "Other")); last = c.group; }
    const row = cgEl("div", "voice-row");
    row.appendChild(voicePlayButton(unitKey, c.id, c.label, row));
    const label = cgEl("span", "voice-label", c.label);
    label.title = c.raw;                            // the game's own name for it
    row.appendChild(label);
    if (c.seconds != null) row.appendChild(cgEl("span", "voice-len", `${c.seconds.toFixed(1)} s`));
    list.appendChild(row);
  }
}

// ---- Muting a character's voice lines, or using your own sound for them. The Voice row on a character's card says how many
// lines are changed; its button opens this window. Every change writes the character's "Custom voice" mod again (backend:
// voice_api.py) and hands back the new state of the whole editor.
const VE_LINE_WORD = n => `${n} line${n === 1 ? "" : "s"}`;

function voiceLineButton(character, key, which, what, host) {
  const b = cgEl("button", "voice-play");
  b.type = "button";
  b._what = what;
  setPlayState(b, "idle");
  b.addEventListener("click", (e) => { e.stopPropagation(); voicePlayWith(() => pywebview.api.get_voice_line_clip(character, key, which), b, host); });
  return b;
}

async function openVoiceEditor(character, onClose) {
  ui.menu.closeAll();
  voiceStop();
  let changed = false;
  const modal = ui.modal({
    variant: "card", class: "voice-editor", title: `Voice \u2013 ${character}`, footer: true, destroyOnClose: true,
    onClose: () => { voiceStop(); if (changed && onClose) onClose(); },
  });
  const card = modal.body;
  const status = cgEl("div", "ve-status", "\u2026");
  card.appendChild(status);
  card.appendChild(cgEl("div", "ve-note", "Mute a line or use your own sound for it. Your changes are saved as a mod called \u201cCustom voice\u201d that Commit merges like any other."));
  const baseBox = cgEl("div");
  card.appendChild(baseBox);
  const sizeBox = cgEl("div");
  card.appendChild(sizeBox);
  const errBox = cgEl("div");
  card.appendChild(errBox);
  // a search box (filters every line below by label/description) and, once lines are in, one pill per category to
  // narrow "All voice lines" further - both stand in for the several separate collapsed sections this used to be
  const searchWrap = cgEl("div", "ve-search");
  const searchInput = cgEl("input");
  searchInput.type = "text";
  searchInput.placeholder = "Search lines by name or what they mean\u2026";
  searchWrap.hidden = true;
  searchWrap.appendChild(searchInput);
  card.appendChild(searchWrap);
  const catPills = cgEl("div", "ve-catbar");
  catPills.hidden = true;
  card.appendChild(catPills);
  const thead = cgEl("div", "ve-thead");
  thead.hidden = true;
  thead.appendChild(cgEl("span", null, "Sound"));
  thead.appendChild(cgEl("span", null, "Description"));
  thead.appendChild(cgEl("span", null, "Actions"));
  card.appendChild(thead);
  const list = cgEl("div", "ve-list");
  list.appendChild(ui.loading("Reading the voice files\u2026"));
  card.appendChild(list);
  const noMatch = cgEl("div", "voice-empty");
  noMatch.hidden = true;
  let activeCat = null;
  const acts = modal.footer;
  const close = () => modal.close();
  const resetBtn = button("Undo all changes", "ghost", async () => {
    resetBtn.disabled = true;
    try { render(await pywebview.api.voice_reset_all(character)); changed = true; } finally { resetBtn.disabled = false; }
  });
  resetBtn.hidden = true;
  const muteAllBtn = button("Mute all", "ghost", async () => {
    muteAllBtn.disabled = true;
    showError(null);
    let r;
    try { r = await pywebview.api.voice_mute_all(character); } catch (e) { r = { success: false, error: String(e) }; }
    muteAllBtn.disabled = false;
    if (!modal.isOpen) return;
    if (!r || !r.success) { showError((r && r.error) || "That didn't work."); return; }
    changed = true;
    render(r);
    if (r.build_problems && r.build_problems.length) showError(r.build_problems.join(" "));
  });
  muteAllBtn.title = "Silence every line of this character's voice (lines with your own sound are kept). Undo one line at a time, or use Undo all changes.";
  muteAllBtn.hidden = true;
  const boostAllBtn = button("Boost quiet lines", "ghost", async () => {
    boostAllBtn.disabled = true;
    showError(null);
    let r;
    try { r = await pywebview.api.voice_boost_all(character); } catch (e) { r = { success: false, error: String(e) }; }
    boostAllBtn.disabled = false;
    if (!modal.isOpen) return;
    if (!r || !r.success) { showError((r && r.error) || "That didn't work."); return; }
    changed = true;
    render(r);
    if (r.build_problems && r.build_problems.length) showError(r.build_problems.join(" "));
  });
  boostAllBtn.title = "Re-gain every custom line the app measures as noticeably quieter than the game's own average.";
  boostAllBtn.hidden = true;
  acts.appendChild(muteAllBtn);
  acts.appendChild(boostAllBtn);
  acts.appendChild(resetBtn);
  const closeBtn = button("Close", "primary", close);
  acts.appendChild(closeBtn);
  modal.open();
  closeBtn.focus();

  const showError = (msg) => { errBox.replaceChildren(); if (msg) errBox.appendChild(cgEl("div", "ve-err", msg)); };

  // Search text narrows every row, moments included; a category pill is a stronger "just this" filter, so picking
  // one hides Important moments entirely - none of those four belong to any one category, so leaving them pinned
  // there would mean "Getting hit" still showed "Finish first" at the top, which reads as a bug, not a feature.
  // Runs after every render() too - a mute/replace rebuilds the whole list, so the filter has to be re-applied,
  // not just set once. The list is flat (see render()): the first .ve-head is "Important moments", every one after
  // it is a category - walked in DOM order, so each row's visibility can fold up into its own heading's.
  function applyFilter() {
    const q = searchInput.value.trim().toLowerCase();
    const matches = (row) => {
      const label = row.querySelector(".ve-label")?.textContent.toLowerCase() || "";
      const desc = row.querySelector(".ve-desc")?.textContent.toLowerCase() || "";
      return !q || label.includes(q) || desc.includes(q);
    };
    let anyVisible = false, seenHead = false, curHead = null, curHeadAny = false;
    const flushHead = () => { if (curHead) curHead.hidden = !curHeadAny; };
    for (const child of [...list.children]) {
      if (child === noMatch) continue;
      if (child.classList.contains("ve-head")) {
        flushHead();
        curHead = child;
        curHeadAny = false;
        const wasFirst = !seenHead;
        seenHead = true;
        curHead._isMoments = wasFirst;   // stash on the node itself - simplest way to carry it to its rows below
        continue;
      }
      if (child.classList.contains("ve-row")) {
        const isMoments = curHead && curHead._isMoments;
        const show = isMoments ? (!activeCat && matches(child)) : (matches(child) && (!activeCat || child.dataset.category === activeCat));
        child.hidden = !show;
        curHeadAny = curHeadAny || show;
        anyVisible = anyVisible || show;
      }
    }
    flushHead();
    list.appendChild(noMatch);   // re-parent to the end (render() rebuilds everything else from scratch)
    noMatch.hidden = !(q || activeCat) || anyVisible;
    noMatch.textContent = q ? `No voice lines match “${searchInput.value.trim()}”.` : "No lines in this category.";
  }
  searchInput.addEventListener("input", applyFilter);

  // one pill per category, to narrow "All voice lines" without having to type - "All" clears it
  function buildCatPills(cats) {
    catPills.replaceChildren();
    catPills.hidden = !cats.length;
    if (!cats.length) return;
    if (activeCat && !cats.some(c => c.name === activeCat)) activeCat = null;
    const pill = (label, val) => button(label, "small" + (activeCat === val ? " primary" : ""), () => { activeCat = val; buildCatPills(cats); applyFilter(); });
    catPills.appendChild(pill("All", null));
    for (const c of cats) catPills.appendChild(pill(c.name, c.name));
  }

  async function setLine(l, mode, row) {
    showError(null);
    row.classList.add("busy");
    let r;
    try { r = await pywebview.api.voice_set_line(character, l.key, mode); } catch (e) { r = { success: false, error: String(e) }; }
    if (!modal.isOpen) return;
    if (!r || !r.success) { row.classList.remove("busy"); showError((r && r.error) || "That didn't work."); return; }
    changed = true;
    render(r);
    if (r.build_problems && r.build_problems.length) showError(r.build_problems.join(" "));
  }

  function lineRow(l) {
    const row = cgEl("div", "ve-row" + (l.available ? "" : " off"));
    row.dataset.category = l.category || "";   // read by applyFilter() for the category pills
    // column 1: Sound - the play button and the line's label/length, together (what you'd click to hear it)
    const sound = cgEl("div", "ve-sound");
    const playBtn = l.available ? voiceLineButton(character, l.key, "current", l.label, row) : cgEl("span", "ve-play-spacer");
    if (l.available) playBtn.title = l.count > 1 ? `Plays one of ${l.count} sounds sharing this line (they're always changed together)` : "Play this sound";
    sound.appendChild(playBtn);
    const soundText = cgEl("div", "ve-sound-text");
    const labelEl = cgEl("span", "ve-label", l.label);
    labelEl.title = l.key;   // the line's internal name (e.g. "GOL_TOP", "STR_FAIL") - for modders who know it by that
    soundText.appendChild(labelEl);
    if (l.available && l.seconds > 0) soundText.appendChild(cgEl("span", "ve-count", `${l.seconds.toFixed(1)}s`));
    sound.appendChild(soundText);
    row.appendChild(sound);
    // column 2: Description - what the line means (dimmed when nobody's traced what it actually is)
    row.appendChild(cgEl("div", "ve-desc" + (l.description === "Unknown." ? " unknown" : ""), l.description));
    // column 3: Actions - its current state and what you can do to it, as one row: a "pressed" chip says what's
    // currently on the line (Muted / the file name), and its own trash-can button undoes it - kept apart so the
    // one destructive action here (deleting a saved custom sound) is never a side effect of reading what it is.
    const a = cgEl("div", "ve-acts");
    if (!l.available) {
      a.appendChild(ui.chip({ text: l.state === "normal" ? (l.reason === "file" ? "not in this voice file" : "needs a voice file") : (l.state === "mute" ? "muted (paused)" : "replaced (paused)") }).el);
    } else {
      if (l.state === "mute" || l.state === "custom") {
        const o = button("\u25B6 original", "ve-orig", () => {});
        o.type = "button";
        const ob = voiceLineButton(character, l.key, "original", "the original", row);
        o.addEventListener("click", (e) => { e.stopPropagation(); ob.click(); });
        a.appendChild(o);
      }
      if (l.state === "silent") a.appendChild(ui.chip({ text: "Already silent" }).el);
      if (l.state === "custom" && l.loud_level === "quiet") {
        const chip = ui.chip({ text: `Quiet (${l.loud_dbfs} dBFS)`, tone: "warn", bold: true }).el;
        chip.title = `Measured at ${l.loud_dbfs} dBFS; the game's own lines average about ${LOUD_TARGET_DBFS.toFixed(1)} dBFS.`;
        a.appendChild(chip);
        a.appendChild(button("Boost", "small", async () => {
          showError(null);
          row.classList.add("busy");
          let r;
          try { r = await pywebview.api.voice_boost_line(character, l.key); } catch (e) { r = { success: false, error: String(e) }; }
          if (!modal.isOpen) return;
          if (!r || !r.success) { row.classList.remove("busy"); showError((r && r.error) || "That didn't work."); return; }
          changed = true;
          render(r);
        }));
      }
      if (l.state === "mute") {
        a.appendChild(ui.chip({ text: "Muted", tone: "warn", bold: true }).el);
        a.appendChild(delButton("Undo the mute", () => setLine(l, "normal", row)));
      } else if (l.state === "custom") {
        const label = (l.custom && l.custom.name ? l.custom.name : "Your sound") + (l.custom && l.custom.seconds ? ` \u00b7 ${l.custom.seconds} s` : "");
        a.appendChild(ui.chip({ text: label, tone: "accent", bold: true }).el);
        a.appendChild(delButton("Delete this sound", async () => {
          const sure = await ui.confirm({
            title: "Delete your sound?", confirmLabel: "Delete", danger: true,
            message: `Delete your sound for \u201c${l.label}\u201d? This removes the saved audio file and can't be undone.`,
          });
          if (!sure) return;
          setLine(l, "normal", row);
        }));
      } else {
        a.appendChild(button("Mute", "small", () => setLine(l, "mute", row)));
      }
      if (typeof openCustomAudio === "function") a.appendChild(button(l.state === "custom" ? "Change\u2026" : "Use my own\u2026", "small", () => openCustomAudio(character, l, (r) => { changed = true; render(r); })));
    }
    row.appendChild(a);
    return row;
  }

  function render(st) {
    const scroll = list.scrollTop;
    showError(null);
    baseBox.replaceChildren();
    sizeBox.replaceChildren();
    if (!st || !st.success) {
      status.hidden = thead.hidden = searchWrap.hidden = catPills.hidden = muteAllBtn.hidden = boostAllBtn.hidden = true;
      list.replaceChildren(cgEl("div", "voice-empty", (st && st.error) || "Couldn't read this character's voice."));
      return;
    }
    if (!st.known) {
      status.hidden = thead.hidden = searchWrap.hidden = catPills.hidden = muteAllBtn.hidden = boostAllBtn.hidden = true;
      list.replaceChildren(cgEl("div", "voice-empty", "The app doesn't know this character's voice files yet, so their voice can't be edited."));
      return;
    }
    // where the voice comes from
    const noBase = !st.bases.length;
    const box = cgEl("div", "ve-base" + (noBase || st.suspended ? " warn" : ""));
    if (st.suspended) {
      box.appendChild(document.createTextNode("Your changes are saved but paused: the voice mod they were made from isn't selected any more, and there's no other voice file to start from. Select a voice mod for this character, or choose your game's files folder, and they come back."));
    } else if (noBase) {
      box.appendChild(document.createTextNode("The app has no copy of this character's voice to start from. Choose your game's files folder (the \u2018romfs\u2019 you extracted from your game) so it can start from the game's own sound, or select a voice mod for this character."));
    } else {
      const from = [...new Set(st.bases.map(b => b.source === "game" ? "the game's own files" : b.label))];
      box.appendChild(document.createTextNode(`Starting from: ${from.join(" and ")}. If you select a different voice mod for this character, your changes move onto it.`));
    }
    if (noBase || st.suspended) {
      const act = cgEl("div", "ve-base-act");
      act.appendChild(button("Choose game files folder\u2026", "small", async () => {
        if (await chooseGameFiles()) { changed = true; render(await pywebview.api.get_voice_editor(character)); }
      }));
      box.appendChild(act);
    }
    baseBox.appendChild(box);
    for (const p of st.problems || []) baseBox.appendChild(cgEl("div", "ve-err", p));

    // the archive size: always shown (how much of the game's own largest-ever archive this character is using), so
    // it's visible well before it becomes a problem, not just once it's close. A rebuilt archive bigger than the
    // largest one the game itself ships with plays nothing at all in-game (confirmed on hardware/Eden - see project
    // notes) - that's the "over" tier below; "warn" is the same number while there's still time to do something about it.
    const SIZE_KIND_LABEL = { race: "Race voice file", menu: "Character-select voice file" };
    const mb = (n) => (n / (1024 * 1024)).toFixed(2) + " MB";
    for (const s of st.sizes || []) {
      if (s.ceiling == null) continue;
      const pct = Math.round(s.fraction * 100);
      const sb = cgEl("div", "ve-size " + s.level);
      const base = `${SIZE_KIND_LABEL[s.kind] || s.kind}: ${mb(s.bytes)} of ${mb(s.ceiling)} (${pct}%) – the largest the game itself ships for one character's voice`;
      sb.appendChild(document.createTextNode(s.level === "over"
        ? `${base}. An archive this size is known to go completely silent in-game, even on lines you didn't touch - mute or shorten a few lines to bring it back under that.`
        : s.level === "warn"
        ? `${base}. Getting close to the size where the game has been seen to stop playing it at all; worth trimming a line or two for some margin.`
        : base));
      sizeBox.appendChild(sb);
    }

    thead.hidden = searchWrap.hidden = !st.lines.length;
    status.hidden = false;
    const mutedCount = st.lines.filter(l => l.state === "mute").length;
    const customCount = st.lines.filter(l => l.state === "custom").length;
    const quietCount = st.lines.filter(l => l.loud_level === "quiet").length;
    status.textContent = (mutedCount || customCount)
      ? [mutedCount ? `${VE_LINE_WORD(mutedCount)} muted` : "", customCount ? `${VE_LINE_WORD(customCount)} replaced` : "",
         quietCount ? `${VE_LINE_WORD(quietCount)} quiet` : ""].filter(Boolean).join(" · ")
      : "Nothing changed yet";

    list.replaceChildren();
    const moments = st.lines.filter(l => l.moment);
    list.appendChild(cgEl("div", "ve-head", "Important moments"));
    for (const l of moments) list.appendChild(lineRow(l));
    const rest = st.lines.filter(l => !l.moment && l.available);
    const cats = [];
    for (const l of rest) { let c = cats.find(x => x.name === l.category); if (!c) { c = { name: l.category, lines: [] }; cats.push(c); } c.lines.push(l); }
    buildCatPills(cats);
    // every category sits in the open, one after another, instead of behind its own collapsed section - search and
    // the category pills above are what narrows this down now, so there's nothing left for a collapse to earn its
    // keep hiding
    for (const c of cats) {
      list.appendChild(cgEl("div", "ve-head", c.name));
      for (const l of c.lines) list.appendChild(lineRow(l));
    }
    applyFilter();
    list.scrollTop = scroll;
    resetBtn.hidden = !st.lines.some(l => l.state === "mute" || l.state === "custom");
    muteAllBtn.hidden = !st.lines.some(l => l.available);
    muteAllBtn.disabled = !st.lines.some(l => l.available && l.state === "normal");
    boostAllBtn.hidden = !quietCount;
  }

  let st;
  try { st = await pywebview.api.get_voice_editor(character); } catch (e) { st = { success: false, error: String(e) }; }
  if (!modal.isOpen) return;
  render(st);
}

// ---- "Use my own sound" for one line. The page does the audio work the browser is good at - reading the file (mp3, wav, ogg,
// m4a, flac... whatever the browser plays) and bringing it to 32 kHz - and shows it as a waveform to trim; the app turns what
// is left into the game's own sound format (Api.voice_set_line, voice_dsp.py).
const CUSTOM_RATE = 32000;          // the rate the sound is kept at (most of the game's own voice lines are 32 kHz)
const CUSTOM_MAX_SECONDS = 8;       // what the app accepts for one line (the longest voice line in the game's own files and the mods checked is 6.7 s)
async function decodeAudioFile(file) {
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const data = await file.arrayBuffer();
  return await new Ctx(2, 1, CUSTOM_RATE).decodeAudioData(data);     // (comes back at CUSTOM_RATE)
}
function pcmToBase64(int16) {
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
// the chosen part of the file as 16-bit samples, interleaved; faded a few milliseconds in and out so a cut doesn't click
// Loudness: the game's own race voice lines were measured (on the user's real mods) at a median -14.7 dBFS RMS and a
// crest factor (peak / average) of about 4.7 - they are mastered/compressed, not just loud at their single loudest instant.
// A plain "bring the peak up to -1 dB" normalise leaves ordinary speech about 9-11 dB QUIETER than that (confirmed on a
// Switch: two hardware tests came back "a bit too quiet" / "almost too quiet to hear over the music"), because speech's
// peak-to-average ratio is much higher than compressed game audio's. matchGameLoudness() fixes that the same way real
// mastering does: (1) a soft compressor - one shared envelope from whichever channel is louder at each instant, so stereo
// content isn't pulled out of balance - brings the peak-to-average ratio down near the game's own, (2) the gain that
// follows is searched for (not computed once), because the limiter in step 3 eats into a single-shot gain guess, (3) a
// smooth (tanh) limiter, not a hard clip, catches whatever peaks remain - it bends the loudest instants toward the
// ceiling instead of flattening them, so a few over-hot samples don't turn into an audible crackle.
const LOUD_TARGET_RMS = 0.185, LOUD_CEILING = 0.97, LOUD_THRESHOLD = 0.07, LOUD_RATIO = 8, LOUD_ATTACK_MS = 3, LOUD_RELEASE_MS = 70, LOUD_MAX_GAIN = 14;
function rmsOf(chans) {
  let sum = 0, count = 0;
  for (const c of chans) { for (let i = 0; i < c.length; i++) sum += c[i] * c[i]; count += c.length; }
  return count ? Math.sqrt(sum / count) : 0;
}
const LOUD_TARGET_DBFS = 20 * Math.log10(LOUD_TARGET_RMS);   // ~ -14.65 dBFS - see voice_dsp.py's copy of this number
// The loudness of an already-interleaved int16 clip (what customPcm() hands back), for the live meter in "Use your own
// sound" - the same target every custom line is measured against once it's saved (voice_api.get_voice_editor's "quiet" flag).
function pcmRmsDbfs(int16) {
  if (!int16.length) return null;
  let sum = 0;
  for (let i = 0; i < int16.length; i++) { const v = int16[i] / 32768; sum += v * v; }
  const rms = Math.sqrt(sum / int16.length);
  return rms > 1e-6 ? 20 * Math.log10(rms) : null;
}
function softLimitChan(chan, gain, ceiling) {
  const out = new Float32Array(chan.length);
  for (let i = 0; i < chan.length; i++) out[i] = ceiling * Math.tanh((chan[i] * gain) / ceiling);
  return out;
}
function matchGameLoudness(chans, n0, n1, rate) {
  const nch = chans.length, len = Math.max(0, n1 - n0);
  if (!len) return chans.map(() => new Float32Array(0));
  const attack = Math.exp(-1 / (rate * LOUD_ATTACK_MS / 1000)), release = Math.exp(-1 / (rate * LOUD_RELEASE_MS / 1000));
  const comp = chans.map(() => new Float32Array(len));
  let env = 0;
  for (let i = 0; i < len; i++) {
    let a = 0;
    for (let c = 0; c < nch; c++) { const v = Math.abs(chans[c][n0 + i]); if (v > a) a = v; }
    env = a > env ? a + (env - a) * attack : a + (env - a) * release;
    const g = env > LOUD_THRESHOLD ? (LOUD_THRESHOLD + (env - LOUD_THRESHOLD) / LOUD_RATIO) / env : 1;
    for (let c = 0; c < nch; c++) comp[c][i] = chans[c][n0 + i] * g;
  }
  const rms0 = rmsOf(comp);
  let gain = rms0 > 1e-6 ? Math.min(LOUD_MAX_GAIN, LOUD_TARGET_RMS / rms0) : 1;
  let out = comp.map(c => softLimitChan(c, gain, LOUD_CEILING));
  for (let iter = 0; iter < 5; iter++) {
    const r1 = rmsOf(out);
    if (Math.abs(r1 - LOUD_TARGET_RMS) < 0.003 || gain >= LOUD_MAX_GAIN) break;
    gain = Math.min(LOUD_MAX_GAIN, gain * (LOUD_TARGET_RMS / Math.max(r1, 1e-6)));
    out = comp.map(c => softLimitChan(c, gain, LOUD_CEILING));
  }
  return out;
}
// extraGainDb: the manual volume control, as an ALTERNATIVE to `normalise` - never both. Ignored whenever normalise
// is on (the UI disables the slider then too, but this is the actual guarantee: whichever produced the level is the
// only one that did). 0 by default, so nothing changes unless the user has both turned matching off and moved the
// slider. Only soft-limited (instead of hard-clamped) when it's pushing volume UP past the raw level, so turning it
// down never sounds different from a plain volume drop, and turning it up clips the way matchGameLoudness's own
// limiter does rather than as a harsh digital clip.
function customPcm(buf, start, end, normalise, extraGainDb) {
  const n0 = Math.max(0, Math.floor(start * CUSTOM_RATE)), n1 = Math.min(buf.length, Math.ceil(end * CUSTOM_RATE));
  const n = Math.max(0, n1 - n0);
  const nch = Math.min(2, buf.numberOfChannels);
  const chans = [];
  for (let c = 0; c < nch; c++) chans.push(buf.getChannelData(c));
  let peak = 0;
  for (let c = 0; c < nch; c++) for (let i = n0; i < n1; i++) { const a = Math.abs(chans[c][i]); if (a > peak) peak = a; }
  const matched = normalise ? matchGameLoudness(chans, n0, n1, buf.sampleRate) : null;
  const extraGain = normalise ? 1 : Math.pow(10, (extraGainDb || 0) / 20);
  const out = new Int16Array(n * nch);
  const fade = Math.min(160, n >> 1);
  for (let i = 0; i < n; i++) {
    const f = i < fade ? i / fade : (n - 1 - i) < fade ? (n - 1 - i) / fade : 1;
    for (let c = 0; c < nch; c++) {
      const raw = (matched ? matched[c][i] : chans[c][n0 + i]) * extraGain;
      const v = extraGain > 1 ? LOUD_CEILING * Math.tanh((raw * f) / LOUD_CEILING) : Math.max(-1, Math.min(1, raw * f));
      out[i * nch + c] = Math.round(v * 32767);
    }
  }
  return { pcm: out, nch, n, peak };
}
function wavBlob(pcm, nch) {
  const head = new ArrayBuffer(44), v = new DataView(head);
  const str = (o, t) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + pcm.byteLength, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, nch, true); v.setUint32(24, CUSTOM_RATE, true);
  v.setUint32(28, CUSTOM_RATE * 2 * nch, true); v.setUint16(32, 2 * nch, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, pcm.byteLength, true);
  return new Blob([head, pcm], { type: "audio/wav" });
}

function openCustomAudio(character, line, onDone) {
  voiceStop();
  const modal = ui.modal({ variant: "card", class: "ve-custom", title: "Use your own sound", footer: true, destroyOnClose: true, onClose: () => cleanup() });
  const card = modal.body;
  card.appendChild(cgEl("div", "ve-note", `For \u201c${line.label}\u201d` + (line.count > 1 ? ` \u2013 it is used for all ${line.count} sounds of this line.` : ".")
    + " Choose an audio file (mp3, wav, ogg, m4a...). The app converts it to the game's sound format and keeps it, so it can be used again if the voice file it goes into changes."));
  const drop = cgEl("div", "ve-drop");
  drop.appendChild(document.createTextNode("Drop an audio file here, or "));
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "audio/*,.mp3,.wav,.ogg,.oga,.m4a,.aac,.flac,.opus,.webm";
  input.hidden = true;
  const pick = button("Choose a file\u2026", "small", () => input.click());
  drop.append(pick, input);
  card.appendChild(drop);
  const fileInfo = cgEl("div", "ve-file");
  const wave = cgEl("div", "ve-wave");
  const canvas = document.createElement("canvas");
  wave.appendChild(canvas);
  const range = cgEl("div", "ve-range");
  const startIn = document.createElement("input"), endIn = document.createElement("input");
  for (const i of [startIn, endIn]) { i.type = "number"; i.min = "0"; i.step = "0.01"; }
  const lenEl = cgEl("span", "ve-len");
  const l1 = cgEl("label", null, "Start (s)"); l1.appendChild(startIn);
  const l2 = cgEl("label", null, "End (s)"); l2.appendChild(endIn);
  range.append(l1, l2, lenEl);
  const opts = cgEl("div", "ve-opts");
  const mkOpt = (text, on) => { const l = cgEl("label"); const c = document.createElement("input"); c.type = "checkbox"; c.checked = on; l.append(c, document.createTextNode(text)); opts.appendChild(l); return c; };
  const trimOpt = mkOpt("Cut the quiet parts at the start and end", true);
  const normOpt = mkOpt("Match the game's own voice volume (fixes a quiet recording)", true);
  // A live readout of how loud the chosen part will actually be, next to the same number every saved custom line is
  // later measured against (see voice_api.get_voice_editor's "quiet" flag) - so a still-too-quiet result is visible
  // before it's saved, not discovered later in the editor or, worse, in the game itself.
  const loudBox = cgEl("div", "ve-loud");
  // Manual control, as an alternative to "Match the game's own voice volume" above - not on top of it. Only one
  // of the two ever sets the level: the slider is disabled while auto-matching is on (see its "change" handler
  // below), so there's never a question of which number actually won. A slider instead of a plain number so it
  // can be nudged by ear: drag, release, hear it, drag again. Auto-plays on release (not while dragging, which
  // would overlap a new sound every few pixels).
  const gainRow = cgEl("div", "ve-gain");
  const gainLabel = cgEl("span", null, "Volume");
  const gainSlider = document.createElement("input");
  gainSlider.type = "range";
  gainSlider.min = "-12";
  gainSlider.max = "12";
  gainSlider.step = "0.5";
  gainSlider.value = "0";
  const fmtDb = (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`;
  const gainVal = cgEl("span", "ve-gain-val", fmtDb(0));
  const gainReset = button("Reset", "ve-orig", () => {
    if (gainSlider.value === "0") return;
    gainSlider.value = "0";
    gainSlider.dispatchEvent(new Event("input"));
    gainSlider.dispatchEvent(new Event("change"));
  });
  const setGainEnabled = (on) => {
    gainSlider.disabled = gainReset.disabled = !on;
    gainRow.classList.toggle("disabled", !on);
    gainRow.title = on ? "" : "Turn off “Match the game's own voice volume” above to set this by hand instead.";
  };
  gainRow.append(gainLabel, gainSlider, gainVal, gainReset);
  const errBox = cgEl("div");
  const mid = cgEl("div");
  mid.hidden = true;
  mid.append(fileInfo, wave, range, loudBox, gainRow, opts);
  card.append(mid, errBox);

  const acts = modal.footer;
  let buf = null, fileName = "", start = 0, end = 0, previewUrl = null, gainDb = 0;
  const cancel = () => modal.close();
  // (runs however it closes: Cancel, Escape, a click outside, or "Use this sound")
  function cleanup() {
    voiceStop(); if (previewUrl) URL.revokeObjectURL(previewUrl);
    window.removeEventListener("dragover", winOver);
    window.removeEventListener("dragenter", winEnter);
    window.removeEventListener("dragleave", winLeave);
    window.removeEventListener("drop", winDrop);
    window.removeEventListener("resize", onResize);
  }
  const isFiles = (e) => !!e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files");
  // The whole dialog is a drop target, not just the dashed box - it's just the one place a file could usefully go
  // while this is open, so there's no reason to make the user aim for a small rectangle. dragDepth counts entries
  // vs. leaves (dragenter/dragleave bubble in matching pairs while the pointer moves between descendants of the
  // same listener) so the highlight doesn't flicker off between child elements, only when the drag actually leaves.
  let dragDepth = 0;
  const winOver = (e) => { if (isFiles(e)) e.preventDefault(); };
  const winEnter = (e) => { if (isFiles(e)) { dragDepth++; modal.dialog.classList.add("drop-target"); } };
  const winLeave = (e) => { if (isFiles(e) && --dragDepth <= 0) { dragDepth = 0; modal.dialog.classList.remove("drop-target"); } };
  const winDrop = (e) => {
    if (!isFiles(e)) return;
    e.preventDefault();
    dragDepth = 0; modal.dialog.classList.remove("drop-target");
    load(e.dataTransfer.files[0]);
  };
  window.addEventListener("dragover", winOver);
  window.addEventListener("dragenter", winEnter);
  window.addEventListener("dragleave", winLeave);
  window.addEventListener("drop", winDrop);
  function playPreview() {
    voiceStop();
    if (!buf) return;
    const r = customPcm(buf, start, end, normOpt.checked, gainDb);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(wavBlob(r.pcm, r.nch));
    const audio = new Audio(previewUrl);
    audio.volume = 0.7;
    voiceNow.audio = audio;
    audio.addEventListener("ended", () => { if (voiceNow.audio === audio) voiceStop(); });
    audio.play().catch(() => showError("Couldn't play the preview here."));
  }
  const previewBtn = button("\u25B6 Preview", "", playPreview);
  const useBtn = button("Use this sound", "primary", async () => {
    if (!buf) return;
    showError(null);
    useBtn.disabled = true;
    const r = customPcm(buf, start, end, normOpt.checked, gainDb);
    let res;
    try {
      res = await pywebview.api.voice_set_line(character, line.key, "custom", { rate: CUSTOM_RATE, channels: r.nch, pcm: pcmToBase64(r.pcm), name: fileName });
    } catch (e) { res = { success: false, error: String(e) }; }
    useBtn.disabled = false;
    if (!res || !res.success) { showError((res && res.error) || "That didn't work."); return; }
    cancel();
    onDone(res);
  });
  // Equal RMS doesn't guarantee equal perceived loudness - a TTS or movie clip can measure the same average level as
  // real game dialogue and still sound thinner over engine noise and music. The meter above catches the former; this
  // catches the latter, letting the ear judge directly against the real thing instead of trusting a number alone.
  const compareBtn = button("▶ Compare with the original", "ve-orig");
  compareBtn.type = "button";
  const compareInner = voiceLineButton(character, line.key, "original", "the original line", errBox);
  compareBtn.addEventListener("click", (e) => { e.stopPropagation(); compareInner.click(); });
  previewBtn.hidden = true;
  useBtn.hidden = true;
  acts.append(previewBtn, compareBtn, button("Cancel", "ghost", cancel), useBtn);
  modal.open();

  function showError(msg) { errBox.replaceChildren(); if (msg) errBox.appendChild(cgEl("div", "ve-err", msg)); }

  // ---- the waveform (the whole file, the chosen part lit) and the start / end
  let peaks = null;
  function computePeaks() {
    const w = Math.max(200, Math.floor(wave.clientWidth || 560));
    const ch = buf.getChannelData(0), per = Math.max(1, Math.floor(buf.length / w));
    peaks = new Float32Array(w);
    for (let x = 0; x < w; x++) {
      let m = 0;
      for (let i = x * per; i < Math.min(buf.length, (x + 1) * per); i++) { const a = Math.abs(ch[i]); if (a > m) m = a; }
      peaks[x] = m;
    }
  }
  function draw() {
    if (!buf) return;
    const dpr = window.devicePixelRatio || 1, w = wave.clientWidth || 560, h = wave.clientHeight || 84;
    canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr);
    const g = canvas.getContext("2d");
    g.scale(dpr, dpr);
    const dur = buf.duration, x0 = (start / dur) * w, x1 = (end / dur) * w;
    const cs = getComputedStyle(document.documentElement);
    g.fillStyle = cs.getPropertyValue("--accent-soft").trim() || "#eef3ff";
    g.fillRect(x0, 0, Math.max(1, x1 - x0), h);
    for (let x = 0; x < w; x++) {
      const a = peaks[Math.min(peaks.length - 1, Math.floor(x / w * peaks.length))] * (h / 2 - 3);
      g.fillStyle = x >= x0 && x <= x1 ? (cs.getPropertyValue("--accent").trim() || "#2563eb") : (cs.getPropertyValue("--text-dim").trim() || "#888");
      g.fillRect(x, h / 2 - a, 1, Math.max(1, a * 2));
    }
  }
  function refreshRange() {
    startIn.value = start.toFixed(2);
    endIn.value = end.toFixed(2);
    endIn.max = startIn.max = buf.duration.toFixed(2);
    const len = end - start;
    lenEl.textContent = `${len.toFixed(2)} s selected of ${buf.duration.toFixed(2)} s`;
    const bad = len > CUSTOM_MAX_SECONDS || len < 0.05;
    lenEl.classList.toggle("bad", bad);
    if (len > CUSTOM_MAX_SECONDS) lenEl.textContent += ` \u2013 at most ${CUSTOM_MAX_SECONDS} s: drag on the waveform to choose the part you want`;
    else if (len < 0.05) lenEl.textContent += " \u2013 too short";
    useBtn.disabled = bad;
    draw();
    refreshLoudness();
  }
  function refreshLoudness() {
    if (!buf || end <= start) { loudBox.replaceChildren(); return; }
    const dbfs = pcmRmsDbfs(customPcm(buf, start, end, normOpt.checked, gainDb).pcm);
    if (dbfs == null) { loudBox.textContent = "This part is silent."; loudBox.className = "ve-loud"; return; }
    const gap = dbfs - LOUD_TARGET_DBFS;
    loudBox.textContent = `Loudness: ${dbfs.toFixed(1)} dBFS \u00b7 the game's own lines average about ${LOUD_TARGET_DBFS.toFixed(1)} dBFS`;
    loudBox.className = "ve-loud" + (gap < -6 ? " quiet" : "");
    if (gap < -6) loudBox.textContent += " \u2013 likely to sound quiet in the game; \u201cMatch the game's own voice volume\u201d fixes this";
  }
  function autoTrim() {
    // the first and last moment louder than a whisper (-40 dB), with a little room around it
    const nch = Math.min(2, buf.numberOfChannels), chans = [];
    for (let c = 0; c < nch; c++) chans.push(buf.getChannelData(c));
    let a = 0, b = buf.length - 1;
    const loud = (i) => { for (let c = 0; c < nch; c++) if (Math.abs(chans[c][i]) > 0.01) return true; return false; };
    while (a < b && !loud(a)) a++;
    while (b > a && !loud(b)) b--;
    const pad = 0.03 * CUSTOM_RATE;
    return [Math.max(0, a - pad) / CUSTOM_RATE, Math.min(buf.length, b + pad) / CUSTOM_RATE];
  }
  function applyTrimOption() {
    [start, end] = trimOpt.checked ? autoTrim() : [0, buf.duration];
    if (end - start > CUSTOM_MAX_SECONDS && !trimOpt.checked) end = start + CUSTOM_MAX_SECONDS;
    refreshRange();
  }
  trimOpt.addEventListener("change", () => { if (buf) applyTrimOption(); });
  normOpt.addEventListener("change", () => { setGainEnabled(!normOpt.checked); if (buf) refreshLoudness(); });
  setGainEnabled(!normOpt.checked);
  gainSlider.addEventListener("input", () => {
    gainDb = parseFloat(gainSlider.value) || 0;
    gainVal.textContent = fmtDb(gainDb);
    if (buf) refreshLoudness();
  });
  gainSlider.addEventListener("change", () => { if (buf) playPreview(); });
  const setRange = () => {
    const a = parseFloat(startIn.value), b = parseFloat(endIn.value);
    if (!(isFinite(a) && isFinite(b))) return;
    start = Math.max(0, Math.min(a, buf.duration)); end = Math.max(start, Math.min(b, buf.duration));
    refreshRange();
  };
  startIn.addEventListener("change", setRange);
  endIn.addEventListener("change", setRange);
  // dragging on the waveform picks the part
  let dragFrom = null;
  const timeAt = (e) => { const r = wave.getBoundingClientRect(); return Math.max(0, Math.min(buf.duration, (e.clientX - r.left) / r.width * buf.duration)); };
  wave.addEventListener("pointerdown", (e) => { if (!buf) return; dragFrom = timeAt(e); wave.setPointerCapture(e.pointerId); });
  wave.addEventListener("pointermove", (e) => { if (dragFrom === null) return; const t = timeAt(e); start = Math.min(dragFrom, t); end = Math.max(dragFrom, t); refreshRange(); });
  wave.addEventListener("pointerup", () => { dragFrom = null; });
  const onResize = () => { if (buf && modal.isOpen) { computePeaks(); draw(); } };
  window.addEventListener("resize", onResize);

  async function load(file) {
    showError(null);
    voiceStop();
    if (!file) return;
    fileName = file.name;
    gainDb = 0; gainSlider.value = "0"; gainVal.textContent = fmtDb(0);   // a new file starts from no manual boost
    mid.hidden = true; useBtn.hidden = true; previewBtn.hidden = true;
    fileInfo.textContent = "Reading " + file.name + "\u2026";
    mid.hidden = false;
    try {
      buf = await decodeAudioFile(file);
    } catch (e) {
      buf = null;
      mid.hidden = true;
      showError(`Couldn't read \u201c${file.name}\u201d as audio. Try an mp3, wav, ogg or m4a file.`);
      return;
    }
    if (!modal.isOpen) return;
    fileInfo.textContent = `${file.name} \u00b7 ${buf.duration.toFixed(2)} s \u00b7 ${buf.numberOfChannels === 1 ? "mono" : "stereo"}`;
    useBtn.hidden = false; previewBtn.hidden = false;
    computePeaks();
    applyTrimOption();
  }
  input.addEventListener("change", () => load(input.files && input.files[0]));
  // no separate drag handling on `drop` itself: the window-level listeners above already cover the whole dialog,
  // including this box, and a second set here would either double-load a file dropped exactly on it or (with
  // stopPropagation to prevent that) leave the whole-dialog highlight stuck on - simpler for this box to just be
  // the visual instructions, not its own drop target.
  card._load = load;           // (the tests drive the dialog through this)
  pick.focus();
}

// The Voice row at the bottom of a character's card: how many lines are changed, and the button that opens the editor.
// Greyed out until the character has a ticked mod (like Name and Icons); the card calls setEnabled() from its refresh().
function attachVoiceRow(body, name) {
  let enabled = false;
  const root = cgEl("div", "cc-step cc-step-inline");
  root.hidden = true;
  const row = cgEl("div", "cc-step-row");
  const dot = cgEl("span", "cc-dot pending");
  const text = cgEl("div", "cc-step-text");
  text.appendChild(cgEl("b", null, "Voice"));
  const sum = cgEl("span", null, "");
  text.appendChild(sum);
  const edit = button("Edit voice lines", "small", () => openVoiceEditor(name, afterChange));
  edit.hidden = true;
  root.classList.add("is-pending");
  row.append(dot, text, edit);
  root.appendChild(row);
  body.appendChild(root);
  async function refresh() {
    let r;
    try { r = (await pywebview.api.get_voice_summary([name]))[name]; } catch (e) { return; }
    if (!root.isConnected || !r || !r.known) return;
    root.hidden = false;
    const n = enabled ? r.muted + r.custom : 0;   // (greyed out like Name and Icons: no ticks, no summary)
    dot.className = "cc-dot " + (n ? "done" : "pending");
    dot.textContent = n ? "\u2713" : "";
    sum.textContent = !enabled ? "Comes after you pick a mod"
                    : n ? [r.muted ? `${VE_LINE_WORD(r.muted)} muted` : "", r.custom ? `${VE_LINE_WORD(r.custom)} replaced` : ""].filter(Boolean).join(" \u00b7 ")
                    : "Mute a line, or use your own sound";
  }
  // a change writes the Custom voice mod: the mod list, the tiles and the commit step all need to hear about it
  async function afterChange() {
    await loadMods();          // (the Custom voice mod is new and ticked: the app's own list of ticks has to hear about it too)
    refreshBehindModal();
    if (root.isConnected) {
      const key = viewMode === "characters" && dockedKey !== null ? dockedKey : openCharacter;
      if (key === name) { openCharacterModal(name); return; }
    }
    refresh();
  }
  refresh();
  return {
    setEnabled(on) {
      if (on === enabled) return;
      enabled = on;
      edit.hidden = !on;
      root.classList.toggle("is-pending", !on);
      refresh();
    },
  };
}

