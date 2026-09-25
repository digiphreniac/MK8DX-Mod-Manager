# Mario Kart 8 Deluxe Mod Manager

A local desktop app for managing MK8DX romfs mods end to end, replacing the
old workflow of manually downloading archives, extracting them, editing
`active-mods.txt`, and hand-merging folders before copying to the SD card.

Given a character or a course, it can:

- Search/browse GameBanana for that character's or course's mods (or fetch
  a mod directly by link), right from the app.
- Download and extract the mod, auto-detecting its `romfs/` folder - and
  auto-fixing the most common ways a downloaded archive turns out to be
  packaged wrong (missing `romfs/` wrapper, a pre-packaged Atmosphere SD-card
  tree, a bare course-slot folder, loose item-model files, and a few others -
  see the comments above each `fix_*` function in `src/mod_manager.py`).
- Let you check off which downloaded mods should actually be merged, per
  character/course, and warn about real conflicts (two checked mods writing
  the same file with *different* content - byte-identical coincidences don't
  count) before you commit to anything.
- Show and fix how a mod looks in the game's own menus (character-select
  icons, course pictures, names), and edit character voices.
- Stage the combined result into `../sd-card-staging/atmosphere/contents/<title id>/`,
  ready to copy onto the Switch SD card.

## Running it

Python 3 with the two dependencies in `requirements.txt` (`pywebview`, `Pillow`):

```
pip install -r requirements.txt
python src/mod_manager.py
```

On Windows you can double-click `Run Mod Manager.bat` instead (`Run Mod Manager (Dev).bat` also turns on the
browser dev tools).

The first launch asks for a **master folder** (where downloads, extracted mods and the app's own data are kept), then walks
you through a short setup, including pointing the app at the game files you extracted from **your own copy** of the game.
The app copies the few files it needs into the master folder; it doesn't ship anything from the game.

## Using it

The app walks you through four steps, shown in its header: **Setup**, **Choose mods**, **Commit**, **Copy to Switch**.
The day-to-day guide is the app's own **Help** panel (top right); it covers the flow, Menu Look, voice editing, conflicts
and known issues, and stays current with the UI because it lives in the UI (`src/ui/html/help-modal.html`).

## Project layout

- `src/mod_manager.py` - the backend (a pywebview JS-API bridge; most of the logic lives here)
- `src/ui/` - the frontend: plain HTML, CSS and JS, no build step
- `src/*.py` - decoders for the game's file formats, the base-game-files copy, the GameBanana client, voice tools and caches
- `src/roster.json` - every character, course, vehicle part and item
- `docs/` - how each part works and why (design notes, measurements, the rules that keep merges safe)

## Documentation

Contributors (and coding agents - see [AGENTS.md](AGENTS.md)) should read the page for the area they are changing:

| Page | What it covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Backend modules, every file the app keeps, frontend file layout, folder naming |
| [docs/caching-and-performance.md](docs/caching-and-performance.md) | Disk and in-memory caches, warm-up, what invalidates them |
| [docs/base-game-files.md](docs/base-game-files.md) | The required local copy of the game's files; course internal names and music ids |
| [docs/merge-rules.md](docs/merge-rules.md) | What a commit never copies in; how clashes are settled |
| [docs/ui-and-flow.md](docs/ui-and-flow.md) | Look and feel; the four-step flow and when "Commit" goes stale |
| [docs/gamebanana-browse.md](docs/gamebanana-browse.md) | The Browse GameBanana window |
| [docs/course-select.md](docs/course-select.md) | Course Select, the course card, course-select icon generation |
| [docs/menu-icons-and-text.md](docs/menu-icons-and-text.md) | The combined character icons and names built on every commit |
| [docs/menu-look.md](docs/menu-look.md) | The Menu look card: your own icons and names, Name and Icons steps |
| [docs/vehicle-parts-and-items.md](docs/vehicle-parts-and-items.md) | Vehicle parts and items: screens, matching a mod to a part, menu pictures |
| [docs/refiling-mods.md](docs/refiling-mods.md) | A mod that replaces something other than the item it was filed under |
| [docs/voice-editing.md](docs/voice-editing.md) | Muting or replacing voice lines |
| [docs/code-patches.md](docs/code-patches.md) | `.ips` code patches (exefs) |
