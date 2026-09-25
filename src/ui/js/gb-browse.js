// ---- Browse GameBanana ----
// The window that lists what GameBanana has for whatever card opened it: a character, a course, a vehicle part, an item, or one
// of the plain categories. It works the same for all of them:
//   - the mods come as one list that keeps loading as you scroll (and loads on its own until the window is full, however tall it
//     is), rather than in pages - so there is never a half-empty last row;
//   - as a grid of pictures or as a list of small ones (the last choice is remembered, as is the sort);
//   - a mod of a kind that has no category per item (a vehicle part, an item) or none per course is tagged with what it seems to
//     replace, and the list can be narrowed to the ones that look right.
//   - a search box in the header searches GameBanana (all of Mario Kart 8 Deluxe) for the words typed, keeping the kind of mod
//     the card is for; emptying it goes back to browsing. The paste field on a card hands anything that isn't a link or an id
//     to this box (see buildGameBananaCard).
// What differs is where the list comes from (see fetchPage): a category browsed with a sort, a search - which GameBanana can
// only rank by best match - or, for a course, a search for its name.

const GB_SORTS = [["most_liked", "Most Liked"], ["most_downloaded", "Most Downloaded"], ["most_viewed", "Most Viewed"], ["newest", "Newest"]];
// pages in a row that bring nothing to show (under the "looks like it replaces" filter) before the list stops asking for more
// by itself - each one costs GameBanana a request per mod
const GB_EMPTY_RUN_LIMIT = 2;
// the same for a search, where a batch can well hold none of the kind wanted (most of what a search finds is something else)
const GB_SEARCH_EMPTY_RUN_LIMIT = 4;
// what a card's search keeps, for "Nothing found among ... mods"
const GB_SEARCH_KIND_NOUN = { characters: "character", courses: "course", vehicles: "vehicle-part", wheels: "vehicle-part", gliders: "vehicle-part", items: "item", mechanics: "Mechanics", ui: "UI" };
// how far below the window's bottom edge (px) the end of the list may be before the next batch is fetched
const GB_LOOKAHEAD = 500;

let gbBrowse = null;   // the open window's session ({checkFill, stop}), null while it is closed

function saveBrowsePref(key, value) {
  state.settings = { ...(state.settings || {}), [key]: value };
  pywebview.api.save_settings({ [key]: value }).catch(() => {});
}

// Builds text nodes with the first occurrence of `needle` wrapped in <b> -
// DOM-built, never innerHTML, since the text itself comes from a remote mod
// description and must never be treated as markup.
function highlightFirstMatch(text, needle) {
  const frag = document.createDocumentFragment();
  const idx = needle ? text.toLowerCase().indexOf(needle.toLowerCase()) : -1;
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

function openGbBrowseModal(itemName, category, onUseMod, opts) {
  closeGbBrowseModal();
  const backdrop = document.getElementById("gb-browse-modal-backdrop");
  const bodyEl = document.getElementById("gb-browse-modal-body");
  const resultsEl = document.getElementById("gb-browse-modal-results");
  const sortSelect = document.getElementById("gb-browse-modal-sort");
  const viewButtons = [...document.querySelectorAll("#gb-browse-modal-view button")];
  const searchInput = document.getElementById("gb-browse-modal-search");
  const searchClear = document.getElementById("gb-browse-modal-search-clear");

  const isCourse = category === "courses";
  const isSimple = SIMPLE_CATEGORIES.some(c => c.key === category);
  const isItem = category === ITEMS_CATEGORY;
  // vehicle parts and items: one flat GameBanana category each, no per-part subcategory - each mod is tagged with what it looks
  // like it replaces (a guess from its text, confirmed for real only once its files are checked)
  const tagged = VEHICLE_SECTION_KEYS.includes(category) || isItem;
  const catchAll = isItem && itemName === ITEMS_OTHER;   // "Other items": the item mods that name no single item
  const shownName = itemLabel(itemName);
  const settings = state.settings || {};
  document.getElementById("gb-browse-modal-title").textContent = `Browse GameBanana — ${shownName}`;

  const S = {
    gen: 0,            // bumped whenever the list starts over (or the window closes): a reply from an older one is dropped
    page: 1,           // what to ask for next
    records: [],       // every mod loaded so far, in order
    seen: new Set(),   // their ids (GameBanana can list one twice across pages)
    shown: 0,          // how many of those the list is showing (the filter hides some)
    total: null,
    done: false,
    loading: false,
    paused: false,     // stopped asking by itself (see GB_EMPTY_RUN_LIMIT)
    emptyRun: 0,
    error: null,
    notice: null,
    skeleton: false,
    query: "",         // what the course browse searched for (its own name)
    search: ((opts && opts.search) || "").trim(),   // what the user searched for; "" = browsing
    // Vehicle parts have always started on Most Viewed (GameBanana's Most Liked repeats mods between pages in its big
    // categories); whatever the user picked last wins over either
    sort: GB_SORTS.some(([k]) => k === settings.gb_browse_sort) ? settings.gb_browse_sort : (tagged ? "most_viewed" : "most_liked"),
    view: settings.gb_browse_view === "list" ? "list" : "grid",
    // narrowing to the likely ones: on by default where the category holds every mod of its kind (not for "Other items", which
    // is for what matches no single item), off for a course (a search already narrows it)
    likelyOnly: tagged && !catchAll,
  };
  const hasFilter = tagged || isCourse;
  const likelyFor = (r) => isCourse ? !!r.mentions_course
    : catchAll ? (r.targets || []).length !== 1
    : (r.targets || []).includes(itemName);
  const visible = (r) => S.search || !S.likelyOnly || likelyFor(r);   // (a search has narrowed it already)
  const searchNoun = GB_SEARCH_KIND_NOUN[category] || "";

  // ---- the frame: a bar (filter, count), the list, and the foot (what is happening at the end of it) ----
  const bar = cgEl("div", "gb-browse-bar");
  const countEl = cgEl("span", "gb-browse-count");
  let likelyBox = null;
  const hint = cgEl("div", "gb-browse-status", "Read each snippet (or open the mod) to confirm what it actually replaces before using it - titles are often unrelated to the real target course.");
  const list = cgEl("div", "gb-browse-grid");
  const foot = cgEl("div", "gb-browse-foot");
  resultsEl.replaceChildren(bar, hint, list, foot);

  // the bar and the hint differ between browsing and searching: a search has no "looks right" filter (it has narrowed the list
  // already) and no advice about reading snippets
  function buildBar() {
    likelyBox = null;
    bar.replaceChildren();
    if (hasFilter && !S.search) {
      const label = cgEl("label", "gb-target-toolbar");
      likelyBox = document.createElement("input");
      likelyBox.type = "checkbox";
      likelyBox.checked = S.likelyOnly;
      likelyBox.addEventListener("change", () => {
        S.likelyOnly = likelyBox.checked;
        S.paused = false;
        S.emptyRun = 0;
        rebuildList();
        bodyEl.scrollTop = 0;
        renderFoot();
        renderCount();
        checkFill();
      });
      label.appendChild(likelyBox);
      label.appendChild(document.createTextNode(
        isCourse ? "Only show mods that name this course in their title or description"
        : catchAll ? "Only show mods that don't look like they replace one single listed item - packs, and ones that name none (badges are guessed from each mod's description)"
        : `Only show mods that look like they replace ${shownName} (badges are guessed from each mod's description)`
      ));
      bar.appendChild(label);
    }
    bar.appendChild(countEl);
    hint.hidden = !isCourse || !!S.search;
  }
  buildBar();

  // ---- the controls in the header ----
  sortSelect.hidden = false;
  // GameBanana's search takes no sort (every parameter for one is ignored) - the best matches come first; that goes for
  // a course's browse (a search for its name) as much as for the user's own search
  function applySortControl() {
    if (isCourse || S.search) {
      sortSelect.replaceChildren(new Option("Sort: Best match", "best"));
      sortSelect.disabled = true;
      sortSelect.title = S.search ? "GameBanana's search can't be sorted - the best matches come first." : "GameBanana's search can't be sorted - the best matches for this course come first.";
    } else {
      sortSelect.replaceChildren(...GB_SORTS.map(([k, label]) => new Option("Sort: " + label, k)));
      sortSelect.disabled = false;
      sortSelect.title = "";
      sortSelect.value = S.sort;
    }
  }
  applySortControl();
  sortSelect.onchange = () => {
    S.sort = sortSelect.value;
    saveBrowsePref("gb_browse_sort", S.sort);
    restart();
  };
  function applyView() {
    list.classList.toggle("as-list", S.view === "list");
    for (const b of viewButtons) {
      const on = b.dataset.view === S.view;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }
  for (const b of viewButtons) {
    b.onclick = () => {
      if (S.view === b.dataset.view) return;
      S.view = b.dataset.view;
      saveBrowsePref("gb_browse_view", S.view);
      applyView();
      checkFill();   // (a list is shorter than a grid, so more may be needed)
    };
  }
  applyView();

  // ---- the search box ----
  let searchTimer = null;
  function setSearch(text) {
    text = text.trim();
    clearTimeout(searchTimer);
    searchClear.hidden = !searchInput.value;
    if (text === S.search) return;
    S.search = text;
    buildBar();
    applySortControl();
    restart();
  }
  searchInput.value = S.search;
  searchClear.hidden = !S.search;
  // as you type (once you pause), and at once on Enter
  searchInput.oninput = () => {
    searchClear.hidden = !searchInput.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => setSearch(searchInput.value), 450);
  };
  searchInput.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); setSearch(searchInput.value); }
    else if (e.key === "Escape" && searchInput.value) {   // (Esc clears the box first; the window closes on the next one)
      e.preventDefault();
      e.stopPropagation();
      searchInput.value = "";
      setSearch("");
    }
  };
  searchClear.onclick = () => { searchInput.value = ""; setSearch(""); searchInput.focus(); };

  // ---- one mod ----
  function buildBrowseTile(rec) {
    const tile = cgEl("div", "gb-browse-tile");
    tile.title = "View details";
    tile.addEventListener("click", () => openGbDetailModal(rec.mod_id, onUseMod));
    const thumb = cgEl("div", "gb-thumb");
    if (rec.thumbnail_url) {
      const img = document.createElement("img");
      img.src = rec.thumbnail_url;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      thumb.appendChild(img);
    }
    tile.appendChild(thumb);

    const body = cgEl("div", "gb-tile-body");
    body.appendChild(cgEl("div", "gb-browse-name", rec.name));
    const meta = cgEl("div", "gb-browse-meta");
    meta.appendChild(cgEl("span", null, `${(rec.like_count || 0).toLocaleString()} ♥ · ${(rec.view_count || 0).toLocaleString()} views`));
    const extra = [rec.submitter && rec.submitter !== "?" ? `by ${rec.submitter}` : null, rec.added ? `added ${rec.added}` : null].filter(Boolean);
    if (extra.length) meta.appendChild(cgEl("span", "gb-meta-extra", " · " + extra.join(" · ")));   // (the list has the room for these)
    body.appendChild(meta);

    const pills = cgEl("div", "gb-pills");
    if (S.search && rec.kind === "characters" && rec.character) {
      // what the author filed it under: green when it is this card's own character (others move to theirs on download)
      const mine = category === "characters" && rec.character === itemName;
      const badge = cgEl("span", "gb-target-badge" + (mine ? " match" : ""), mine ? `✓ ${rec.character}` : rec.character);
      badge.title = mine ? "Filed under this character on GameBanana." : `Filed under ${rec.character} on GameBanana.`;
      pills.appendChild(badge);
    } else if (rec.subcategory) {
      pills.appendChild(cgEl("span", "gb-search-subcat", rec.subcategory));
    }
    if (tagged && (rec.targets || []).length > 0) {
      const isThis = rec.targets.includes(itemName);
      const verb = rec.target_strength >= 2 ? "Replaces" : "Mentions";
      // green: its text says it replaces this one; amber: it only mentions it (a weaker guess); grey: it is about another one
      const badge = cgEl("span", "gb-target-badge" + (isThis ? (rec.target_strength >= 2 ? " match" : " match weak") : ""),
        isThis ? `✓ ${verb} ${shownName}` : `${verb} ${rec.targets.slice(0, 2).join(", ")}${rec.targets.length > 2 ? "…" : ""}`);
      badge.title = rec.target_strength >= 2
        ? "Guessed from a 'goes over / replaces' phrase or a file name in the mod's description."
        : "Only mentioned in the title or description - a weaker guess.";
      pills.appendChild(badge);
    }
    if (isCourse && !S.search && rec.mentions_course) pills.appendChild(cgEl("span", "gb-target-badge match weak", `✓ Mentions ${S.query || shownName}`));
    if (pills.childElementCount) body.appendChild(pills);

    if (rec.description_snippet) {
      const snippet = cgEl("div", "gb-search-snippet");
      snippet.appendChild(highlightFirstMatch(rec.description_snippet, S.search || (isCourse ? S.query : "")));
      body.appendChild(snippet);
    }
    tile.appendChild(body);
    return tile;
  }

  function appendTiles(recs) {
    const frag = document.createDocumentFragment();
    for (const rec of recs) frag.appendChild(buildBrowseTile(rec));
    list.appendChild(frag);
  }

  function rebuildList() {
    list.replaceChildren();
    S.skeleton = false;
    const recs = S.records.filter(visible);
    S.shown = recs.length;
    appendTiles(recs);
  }

  function showSkeleton() {
    list.replaceChildren();
    for (let i = 0; i < 8; i++) list.appendChild(cgEl("div", "sk sk-tile"));
    S.skeleton = true;
  }

  // ---- what is under and above the list ----
  function renderCount() {
    const loaded = S.records.length;
    if (S.error || (!loaded && !S.done)) { countEl.textContent = ""; return; }
    if (S.search) {
      if (!loaded && S.done) { countEl.textContent = ""; return; }   // (the foot says nothing was found)
      countEl.textContent = `${loaded} ${loaded === 1 ? "mod" : "mods"} for “${S.search}”${S.done ? "" : " so far"}`;
      return;
    }
    const of = S.total ? ` of ${S.total.toLocaleString()}` : "";   // (a search has no count of its own to give)
    countEl.textContent = S.likelyOnly
      ? `${S.shown} that look right · ${loaded}${of} checked`
      : `${loaded}${of} mods${isCourse && !S.done ? " so far" : ""}`;
  }

  function showEverything() {
    if (likelyBox) likelyBox.checked = false;
    S.likelyOnly = false;
    S.paused = false;
    S.emptyRun = 0;
    rebuildList();
    renderFoot();
    renderCount();
    checkFill();
  }

  function renderFoot() {
    foot.replaceChildren();
    if (S.error) {
      foot.appendChild(cgEl("div", "gb-browse-status", `Couldn't load: ${S.error}`));
      foot.appendChild(button("Try again", "ghost small", () => { S.error = null; loadMore(); }));
    } else if (S.loading) {
      foot.appendChild(loadingNote(S.records.length ? "Loading more mods..." : S.search || isCourse ? `Searching GameBanana for ${S.search ? `“${S.search}”` : "this course"}...` : "Loading mods from GameBanana..."));
    } else if (S.paused) {
      foot.appendChild(cgEl("div", "gb-browse-status", S.search
        ? `The last ${GB_SEARCH_EMPTY_RUN_LIMIT} batches of results held no ${searchNoun} mods.`
        : `Nothing on the last ${GB_EMPTY_RUN_LIMIT} batches looked like a match (${S.records.length} mods checked so far).`));
      const row = cgEl("div", "gb-foot-actions");
      row.appendChild(button("Keep searching", "ghost small", () => { S.paused = false; S.emptyRun = 0; loadMore(); }));
      if (!S.search) row.appendChild(button("Show every mod", "ghost small", showEverything));
      foot.appendChild(row);
    } else if (S.done && S.shown === 0 && S.search) {
      foot.appendChild(cgEl("div", "gb-browse-status", `No ${searchNoun} mods found for “${S.search}”. GameBanana's search matches the words in a mod's title and description - try fewer or different ones.`));
      foot.appendChild(button("Search gamebanana.com instead ↗", "ghost small", () => {
        pywebview.api.open_external_url("https://gamebanana.com/search?" + new URLSearchParams({ _idGameRow: "6507", _sSearchString: S.search }));
      }));
    } else if (S.done && S.shown === 0) {
      if (S.notice) {
        foot.appendChild(cgEl("div", "gb-browse-status", S.notice));
      } else if (S.likelyOnly && S.records.length) {
        const none = cgEl("div", "gb-browse-status", isCourse
          ? `None of the ${S.records.length} mods found name this course - `
          : `None of the ${S.records.length} mods listed look like they replace this ${isItem ? "item" : "part"} - `);
        const showAll = document.createElement("a");
        showAll.href = "#";
        showAll.textContent = "show every mod";
        showAll.addEventListener("click", (e) => { e.preventDefault(); showEverything(); });
        none.appendChild(showAll);
        none.appendChild(document.createTextNode("."));
        foot.appendChild(none);
      } else {
        foot.appendChild(cgEl("div", "gb-browse-status", isCourse
          ? "No matching course mods found. GameBanana search can miss mods whose description phrases things differently - try browsing gamebanana.com directly, or paste a link if you already found one."
          : "No mods found."));
      }
    } else if (S.done) {
      foot.appendChild(cgEl("div", "gb-browse-end", S.search ? "That's everything GameBanana found." : "That's everything."));
    }
  }

  // ---- loading ----
  function checkFill() {
    if (gbBrowse !== session || S.done || S.loading || S.paused || S.error) return;
    const room = foot.getBoundingClientRect().top - bodyEl.getBoundingClientRect().bottom;
    if (room < GB_LOOKAHEAD) loadMore();
  }

  function fetchPage(page) {
    if (S.search) return pywebview.api.gb_search(category, S.search, page);
    if (isCourse) return pywebview.api.gb_browse_course(itemName, page);
    if (isSimple) return pywebview.api.gb_browse_simple(category, page, S.sort);
    if (isItem) return pywebview.api.gb_browse_item(itemName, page, S.sort);
    if (tagged) return pywebview.api.gb_browse_vehicle(itemName, page, S.sort);
    return pywebview.api.gb_browse(itemName, page, S.sort);
  }

  async function loadMore() {
    if (S.loading || S.done || S.paused || S.error) return;
    const gen = S.gen;
    S.loading = true;
    renderFoot();
    let res;
    try { res = await fetchPage(S.page); } catch (e) { res = { error: String((e && e.message) || e) }; }
    if (gen !== S.gen) return;   // the list started over (a new sort) or the window closed while this was on its way
    S.loading = false;
    if (S.skeleton) { list.replaceChildren(); S.skeleton = false; }
    if (res.error) { S.error = res.error; renderFoot(); renderCount(); return; }
    if (res.subcategory_id === null) {
      S.notice = "No matching GameBanana category found for this character - paste a link instead.";
      S.done = true;
      renderFoot();
      return;
    }
    if (res.query) S.query = res.query;
    if (!isCourse && !S.search && res.total != null) S.total = res.total;   // (a search's own count includes things that aren't mods)
    S.page = res.next_page || S.page + 1;
    const fresh = [];
    for (const rec of res.records) {
      if (!S.seen.has(rec.mod_id)) { S.seen.add(rec.mod_id); fresh.push(rec); }
    }
    S.records.push(...fresh);
    S.done = !!res.done;
    const show = fresh.filter(visible);
    appendTiles(show);
    S.shown += show.length;
    S.emptyRun = show.length ? 0 : S.emptyRun + 1;
    if (S.emptyRun >= (S.search ? GB_SEARCH_EMPTY_RUN_LIMIT : GB_EMPTY_RUN_LIMIT) && !S.done) S.paused = true;
    renderFoot();
    renderCount();
    checkFill();
  }

  function restart() {
    S.gen++;
    S.page = 1;
    S.records = [];
    S.seen = new Set();
    S.shown = 0;
    S.total = null;
    S.done = S.loading = S.paused = false;
    S.emptyRun = 0;
    S.error = S.notice = null;
    showSkeleton();
    bodyEl.scrollTop = 0;
    renderCount();
    loadMore();
  }

  const session = { checkFill, stop: () => { S.gen++; clearTimeout(searchTimer); } };
  gbBrowse = session;
  backdrop.hidden = false;
  restart();
}

function closeGbBrowseModal() {
  if (gbBrowse) gbBrowse.stop();
  gbBrowse = null;
  document.getElementById("gb-browse-modal-backdrop").hidden = true;
}

// Scrolling (or the window being resized) may bring the end of the list near: fetch what comes next.
document.getElementById("gb-browse-modal-body").addEventListener("scroll", () => { if (gbBrowse) gbBrowse.checkFill(); }, { passive: true });
new ResizeObserver(() => { if (gbBrowse) gbBrowse.checkFill(); }).observe(document.getElementById("gb-browse-modal-body"));

document.getElementById("btn-gb-browse-modal-close").addEventListener("click", closeGbBrowseModal);
document.getElementById("gb-browse-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "gb-browse-modal-backdrop") closeGbBrowseModal();
});
