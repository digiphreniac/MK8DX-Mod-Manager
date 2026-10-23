# Mario Kart 8 Deluxe Mod Manager - developer overview

> For installing and using the app, see the [README](../README.md). This page is for contributors.

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

## Running it from source

Python 3 with the two dependencies in `requirements.txt` (`pywebview`, `Pillow`):

```
pip install -r requirements.txt
python src/mod_manager.py
```

On Windows you can double-click `Run Mod Manager.bat` instead: it creates a private `.venv`, installs the requirements
and starts the app (`Run Mod Manager (Dev).bat` also turns on the browser dev tools). Packaged releases are built
with PyInstaller - see "Building a release" below.

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
- `src/app_paths.py`, `src/version.py`, `tools/`, `.github/workflows/` - where files live when packaged, the version, and the release build
- `src/roster.json` - every character, course, vehicle part and item
- `docs/` (this folder) - how each part works and why (design notes, measurements, the rules that keep merges safe)

## Documentation

Contributors (and coding agents - see [AGENTS.md](../AGENTS.md)) should read the page for the area they are changing:

| Page | What it covers |
| --- | --- |
| [docs/architecture.md](architecture.md) | Backend modules, every file the app keeps, frontend file layout, folder naming |
| [docs/caching-and-performance.md](caching-and-performance.md) | Disk and in-memory caches, warm-up, what invalidates them |
| [docs/base-game-files.md](base-game-files.md) | The required local copy of the game's files; course internal names and music ids |
| [docs/merge-rules.md](merge-rules.md) | What a commit never copies in; how clashes are settled |
| [docs/ui-and-flow.md](ui-and-flow.md) | Look and feel; the four-step flow and when "Commit" goes stale |
| [docs/gamebanana-browse.md](gamebanana-browse.md) | The Browse GameBanana window |
| [docs/course-select.md](course-select.md) | Course Select, the course card, course-select icon generation |
| [docs/menu-icons-and-text.md](menu-icons-and-text.md) | The combined character icons and names built on every commit |
| [docs/menu-look.md](menu-look.md) | The Menu look card: your own icons and names, Name and Icons steps |
| [docs/vehicle-parts-and-items.md](vehicle-parts-and-items.md) | Vehicle parts and items: screens, matching a mod to a part, menu pictures |
| [docs/refiling-mods.md](refiling-mods.md) | A mod that replaces something other than the item it was filed under |
| [docs/voice-editing.md](voice-editing.md) | Muting or replacing voice lines |
| [docs/mod-notes.md](mod-notes.md) | Your notes on mods |
| [docs/code-patches.md](code-patches.md) | `.ips` code patches (exefs) |

## Building a release

`Build Release.bat` (or `python tools/build_release.py`) makes
`dist/MK8DX-Mod-Manager-v<version>-windows.zip`: a PyInstaller folder build (`tools/mk8dx-mod-manager.spec`,
no console window) holding the app, its Python runtime and 7-Zip's command-line tool, plus the license and a
short readme. Install 7-Zip on the build machine first (or pass `--no-7zip`). The version comes from
`src/version.py`; bump it before building.

- `src/app_paths.py` is the one place that knows where files are: `RESOURCE_DIR` (the read-only `ui/`,
  `roster.json`, `known-shared-files.json`, `name-labels.json`, found under PyInstaller's bundle folder when
  frozen) and `APP_ROOT` (the folder holding the `.exe`, where `app-config.json` goes). A new bundled data
  file needs adding to the spec's `datas` and to be read through `app_paths.RESOURCE_DIR`.
- Files extracted from a downloaded zip carry Windows' "from the Internet" mark, and .NET refuses to load a marked DLL, so
  pythonnet (the window library) fails. `app_paths.unblock_downloaded_files()` clears the mark from the bundled files at
  startup, before `webview` is imported. Test a build by marking its files (see the CI smoke test), not just by extracting a
  local zip, which leaves no mark.
- The zip holds exactly one readme: `release/README.md` (copied in as `README.md`). It is written separately from the
  repository's `README.md` and is the only place to edit the text users see in the download; CI fails if the package ends up
  with more than one.
- First run: with no `app-config.json`, the master folder is `data` next to the app (`default_master_dir()` in
  `mod_manager.py`; `sd-card-staging` is then next to it too). The wizard's first step, "Data folder" (`setup-wizard.js`), shows
  it marked Recommended (`get_master_dir_status()["is_default"]`); Next keeps it, "Change folder..." picks another (written to
  `app-config.json`), and "Use the recommended folder" (`use_default_master_dir()`) deletes that pointer again. When the default
  spot isn't writable the old full-screen folder picker is shown instead. The `data` folder is created at run time, never shipped
  in the zip, so extracting an update over an old install keeps the user's data.
- A packaged build has no console, so `app_paths.redirect_output_to_log()` sends stdout/stderr to
  `mod-manager.log` next to the `.exe`, and an uncaught startup error shows a message box pointing at it.
- Build with a mainstream Python and test the zip on a machine without Python: extract it to a short path,
  run the setup wizard, download a `.7z` mod, commit.

### Publishing a release (GitHub Actions)

`.github/workflows/release.yml` builds the package on GitHub and publishes it as a Release - the zip is never
committed (`dist/` is ignored). It runs on every push to `master`/`main`, but only builds when `src/version.py`
names a version that has no release yet:

1. Bump `VERSION` in `src/version.py` (MAJOR.MINOR.PATCH) in the change you merge.
2. When it lands on `master`, the workflow builds the zip, checks its contents, and creates release `v<version>`
   (tag at that commit, auto-generated notes, the zip plus a `.sha256` file attached).
3. A push that doesn't change the version finds `v<version>` already released and does nothing.

To test the build without releasing, run the workflow by hand (Actions > Release > Run workflow): it builds and
attaches the zip to the run as an artifact only. To redo a release, delete the release and its tag on GitHub,
then re-run the workflow on that commit (or bump the patch version instead).
