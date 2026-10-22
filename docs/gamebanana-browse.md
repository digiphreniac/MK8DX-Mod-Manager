# Browsing GameBanana

The Browse GameBanana window: one window for every kind of mod.

## Browsing GameBanana: one window for every kind of mod

"Browse GameBanana" (`js/gb-browse.js`, markup in `html/gb-browse-modal.html`, styles in `css/gb-browse.css`) is the same window
whatever card opens it - a character, a course, a vehicle part, an item, or one of the plain categories. Only where the list
comes from differs (`fetchPage()`): `gb_browse` (a character's subcategory), `gb_browse_simple`, `gb_browse_vehicle`,
`gb_browse_item` - all sortable categories - or `gb_browse_course`, a search - and `gb_search` when the user has typed one.

- **The list loads as you scroll** (no pages). `checkFill()` asks for the next batch whenever the end of the list is within
  `GB_LOOKAHEAD` (500 px) of the window's bottom edge - after each batch, on scroll, on resize, and when the layout changes - so a
  tall window fills itself and a short one loads on demand, and a row is never left half-empty until the very end. Every backend
  browse call returns `{records, total, done, next_page}`; the window asks for `next_page` (a course search advances by three
  search pages per call), drops mods it already has (GameBanana repeats a few across pages in its Most Liked order), and ignores a
  reply that arrives after the sort changed or the window closed (`S.gen`).
- **Grid or list**: one set of tiles, with `.as-list` on the container switching to small pictures beside the text (plus the
  author and date). Under the "looks like it replaces X" filter, batches that add nothing stop the automatic loading after
  `GB_EMPTY_RUN_LIMIT` (2), because each batch costs a GameBanana request per mod.
- **Remembered**: the layout and the sort are settings (`gb_browse_view`, `gb_browse_sort` in `settings.json`, saved when the user
  changes them). Before any choice, vehicle parts and items start on Most Viewed, the rest on Most Liked. A course has no sort:
  GameBanana's search endpoint ignores every sort parameter (tried several spellings), so its results are always best match first
  and the sort box says so.
- **Courses** have no category per course, so they search by the base course name (`search_course_mods()`: three search pages at
  once, kept to the Course Edits / Course Retextures / Custom Race Courses subcategories - most results are something else).
  Each mod comes with a snippet of its description around the course's name and `mentions_course` (named in its title or
  description), shown as a badge like the "Replaces X" ones on vehicles and items; an "only mods that name this course" filter
  is there too, off by default. Descriptions are fetched through `_descriptions()` and cached (`_gb_desc_cache`, and on disk - see `gamebanana-descriptions.json`); a browse or search of courses, vehicle parts or items answers in two steps (`quick=True` gives the list at once with the descriptions already known and `pending`; the same call without it reads the rest, one batch at a time), and the window shows a note on each mod until its description is in. Shared with the
  vehicle and item lists, which now show a snippet too.
- **Search** (the box in the window's header): searches all of Mario Kart 8 Deluxe through the same full-text search the course
  list uses (`gb_search(category, query, page)` -> `search_filtered()`), then keeps the kind of mod the card is for. The kind is
  read from the GameBanana category each result is filed in (`_search_kind()`: the vehicle-part and item category ids, the course
  subcategories, a subcategory named after a roster character, or a plain category) - so a search from a character's card lists
  character mods of *any* character (each tile says which one it is filed under; green when it is this card's own - the download
  moves it to the right card if its files say otherwise, see below), and one from a tire card lists any vehicle part, with the
  usual "Replaces / Mentions" badges read against the roster of the result's own section. Results are best match first (no sort),
  are shown with a snippet around the words searched for, and load as you scroll like everything else; a batch that has none of the
  kind wanted counts towards a pause after `GB_SEARCH_EMPTY_RUN_LIMIT` (4). Emptying the box (the x, or Esc - a second Esc closes
  the window) goes back to browsing with the remembered sort. A search with nothing found offers to search gamebanana.com itself.
  The card's paste field is the shortcut into it: a link or id is fetched as before (`looksLikeModRef()`), anything else opens this
  window already searching for it - the field's button changes from "Fetch" to "Search" as you type.
- **The More tab's categories** (`SIMPLE_MOD_CATEGORIES`, mirrored by `SIMPLE_CATEGORIES` in `state-and-helpers.js`): Mechanics, UI,
  Code patches (GameBanana's own category for exefs `.ips` mods), Modpacks and Battle courses (the Custom Battle Courses
  subcategory - the course roster has no cards for battle arenas, so those mods get one place of their own instead of showing up in
  a race course's search). Each is one fixed pseudo-item that browses, searches and adds links like any card. A modpack stays filed
  under Modpacks, but `get_pack_links()` lists it (with its "Pack" badge) on every character / course / part / item card it
  replaces - the same mechanism as any other pack. Adding one of these needs an entry in both lists and an `<option>` in
  `add-mod-modal.html`. The tab (`renderMoreList()` in `views.js`, styles in `full-list.css`) is a responsive grid of tiles - one per
  category: a line icon (`MORE_ICONS`), its name, a one-line `blurb` (in `SIMPLE_CATEGORIES`), how many mods it holds and how many are
  ticked (with a bar), and a "Browse GameBanana" button that opens the category's card and its GameBanana window in one go
  (`openMoreCard()`; primary while the category is empty). A category whose download left nothing usable is outlined in red with a
  sentence saying so. A new category needs an icon in `MORE_ICONS` and a blurb.
- **What a card's search keeps** (`_search_kind()`): its own kind; for characters, vehicle parts and items also GameBanana's
  Skins > Packs and Skins > Other/Misc (mods of those kinds that no single roster entry names); for Modpacks also Skins > Packs.
  Custom Lighting counts as a course kind (`COURSE_SEARCH_SUBCATEGORIES`). The search endpoint also returns WIPs, questions and
  requests, which `search_mods()` drops - none can be downloaded.
- **Tags**: a mod's own page gives tags as `{"_sTitle", "_sValue"}` objects (the list gives strings) - `tag_names()` turns both
  into "Title: Value" strings.
- **Links in descriptions**: `gamebanana_api.html_to_runs()` turns a description's HTML into runs (`{text}` / `{text, href}`;
  http(s) and GameBanana-relative links only, everything else is plain text) and the record keeps them as `description_runs`
  beside the plain `description` that the guessing uses. `renderRichText()` builds the text nodes and `<a class="gb-link">` itself
  (never markup from the mod); a click calls `open_external_url()`, which opens http(s) addresses only, and the tooltip shows where
  it goes. A mod saved before runs existed, or text with no link markup, still gets bare `https://...` addresses linked.
