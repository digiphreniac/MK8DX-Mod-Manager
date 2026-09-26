# MK8DX Mod Manager - notes for coding agents

A local desktop app (Python + pywebview, plain HTML/CSS/JS frontend, no build step) that downloads Mario Kart 8 Deluxe mods
from GameBanana, lets the user tick which to merge, and stages the result for the Switch SD card. `README.md` is the
human-facing overview; the design notes, measurements and rules live in `docs/` (index below).

## Run and check

- Install: `pip install -r requirements.txt` (pywebview, Pillow). Run: `python src/mod_manager.py`; `MK8DX_DEBUG=1` opens the
  webview dev tools. On this machine use the project's `.venv/bin/python` (the system Python has no `webview`).
- The only automated tests are `tests/test_tick_state.py` (`python -m unittest discover -s tests`): they guard the ticked mods
  against loss. Everything else is verified by calling the backend directly (`Api(Path(master_root))` - it takes a
  `Path`, not a `str`) and by loading `src/ui` in a browser with `pywebview.api` stubbed to those calls. State what you
  did and did not exercise; the real pywebview bridge is easy to leave untested.
- The frontend is served from `src/ui/`; everything the page loads must live there.

## Working rules

- Commit only when the user asks. End commit messages with the `Co-Authored-By` trailer the harness gives you.
- `app-config.json` (machine-specific master folder) and `PROMPTS.md` (the user's own scratch prompts) are the user's; don't
  edit or rely on them. Never delete or rewrite anything under the user's master folder except through the app's own code
  paths (`mods/`, `game-files/`, `ui-icons/`, ...). `game-files/original/` is written once and never touched again.
- When you change behaviour that a page in `docs/` describes, update that page in the same change. Put new design notes in
  the matching `docs/` page (or a new one), not in `README.md`, which stays short.
- The in-app **Help** panel (`src/ui/html/help-modal.html`) is the user guide and must stay current with the UI.

## Code map

- `src/mod_manager.py` (~6.8k lines) - the `Api` class (every public method is callable from JS) and most logic: downloading,
  fixing archives (`fix_*`), the mod library, `_compute_claims()`, `merge()`, `preview_commit()`, `get_flow_status()`.
- `src/ui_setup.py` + `ui_archives.py` - reads and builds the game's icon/text archives (SARC/Yaz0) for "Menu icons & text".
- `src/bntx_decode.py` / `bntx_encode.py` / `_bntx_structs.py` - Switch BNTX textures to/from PNG.
- `src/game_files.py` - the app's own copy of the base game's files. `cup_icons.py`, `vehicle_icons.py`, `item_icons.py` read
  the game's pictures out of that copy.
- `src/voice_*.py` - voice archives (`.bars`): read, edit, encode, and the Api side.
- `src/gamebanana_api.py` - GameBanana client. `roster.json` - every character/course/part/item; `name-labels.json` - text ids.
- `src/image_cache.py`, `library_cache.py`, `gb_desc_cache.py` - caches (see below).
- `src/ui/` - `index.html` frame, `html/` modals, `css/`, `js/` scripts (see "Frontend rules").

## Rules that are easy to break

- **Never merge `Audio/Static/BGM.bars` or packed `UI/*.sarc` archives** from a mod (`_MERGE_SKIP_RELPATHS`,
  `_is_packed_ui_archive`, `_compute_claims()`): they are game-wide tables, and one mod's copy wipes everyone else's entries.
  Loose `UI/**/*.bntx` textures are safe and are merged. The app builds one combined archive itself on every commit.
  Details: `docs/merge-rules.md`.
- **Clashes** mean two ticked mods writing *different bytes* to one path. They are settled by leaving the file out of the loser
  (`excluded-files.json`), never by editing a mod's own downloaded files. `docs/merge-rules.md`.
- **The base game's files are Nintendo's.** The app copies what it needs from the user's own dump into
  `<master>/game-files/`; never ship or commit game data. Consumers read `current/`. `docs/base-game-files.md`.
- **`get_flow_status()` is the single source of truth** for the step bar; the frontend only renders it. Commit "staleness"
  compares signatures - change an input and both signatures must include it. `docs/ui-and-flow.md`.
- **The ticked mods (`mod-manager-state.json`) must never be lost.** The page saves only what CHANGED (`saveChecked()` in
  `state-and-helpers.js` -> `Api.save_checked(changes, epoch)`), never its whole picture: an empty or out-of-date page must not be
  able to replace the file (this happened). The epoch names the master folder the page loaded its ticks from, so a page from the
  folder before a switch is refused. Anything in the backend that changes the ticks goes through `_update_state()` (one lock,
  atomic write, `.bak` copy) - never `write_text()`. Every app-owned JSON file is written with `safe_io.write_json_atomic()`.
- **Mods are nested by item**: `mods/extracted/<category>/<item>/<mod name>/romfs/...`, not `<item> - <mod name>`.
  `docs/architecture.md` ("Folder naming").
- **Vehicle parts and items are named by what a mod *replaces***, never "slot" or "filing" in user-facing text.
  `docs/vehicle-parts-and-items.md`, `docs/refiling-mods.md`.

## Caches (details in `docs/caching-and-performance.md`)

- Everything under `<master>/image-cache/`, `ui-setup-cache.json` and `gamebanana-descriptions.json` is derived data that must
  be safe to delete. Never put anything only the cache knows into it.
- Change how a picture is decoded or encoded -> raise `image_cache.VERSION`. Entries are keyed by the source file's
  (size, mtime) stamp; writes are atomic.
- Any `Api` method that changes the mods library (adds, removes, moves, rebuilds a mod) must carry `@mutates_library`
  (`library_cache.py`), or screens will show a stale library for up to a few seconds. `merge()` itself always reads files afresh.
- The backend runs a background warm-up (`Api._warm_up`); code it calls must be thread-safe (`_ui_setup_plan` holds a lock).

## Frontend rules

- Scripts in `src/ui/js/` are ordinary (non-module) scripts sharing **one global scope**, loaded in the order of `SCRIPTS` in
  `js/bootstrap.js`. Top-level code may only use what an *earlier* file declared; add a new file after what it depends on.
- CSS order in `index.html` is the cascade: add a stylesheet after whatever it must override.
- `js/api-coalesce.js` shares identical in-flight calls for the methods in its `SHARED` list. Only **read-only** backend calls
  may be listed there. Conflict badges go through `conflictCount()` (one batched `check_conflict_counts` per draw).
- Screens are drawn lazily (`renderAll()` / `redrawViews()` in `views.js`); a tick that changes one screen should redraw only
  that one (`refreshBehindModal({ ifChanged: true })`). Pictures the page already holds live in `characterIconCache` /
  `courseDefaultPictures` and are emptied by `resetPictureCaches()` when the game's files change.

## Docs index - read the page for the area you are changing

| Area | Page |
| --- | --- |
| Modules, files the app keeps, frontend layout, folder naming | `docs/architecture.md` |
| Caches, warm-up, performance | `docs/caching-and-performance.md` |
| Base game files copy, course internal names / music ids | `docs/base-game-files.md` |
| What is never merged, conflicts and left-out files | `docs/merge-rules.md` |
| Guided flow, Commit staleness, look and feel | `docs/ui-and-flow.md` |
| Browse GameBanana window | `docs/gamebanana-browse.md` |
| Course Select, course card, course-select icons | `docs/course-select.md` |
| Combined character icons / names built on commit | `docs/menu-icons-and-text.md` |
| Menu look card, Name and Icons steps | `docs/menu-look.md` |
| Vehicle parts and items | `docs/vehicle-parts-and-items.md` |
| A mod that belongs to a different card | `docs/refiling-mods.md` |
| Voice editing | `docs/voice-editing.md` |
| `.ips` code patches | `docs/code-patches.md` |
