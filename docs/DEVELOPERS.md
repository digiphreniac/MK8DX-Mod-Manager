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
- Stage the combined result into `<data folder>/sd-card-staging/atmosphere/contents/<title id>/` (or the folder chosen in Settings),
  ready to copy onto the Switch SD card.

## Running it from source

Python 3.9+ with the dependencies in `requirements.txt` (`pywebview`, `Pillow`, `certifi`; on Linux `pywebview[qt]`, which brings PyQt6 and
Qt WebEngine):

```
pip install -r requirements.txt
python src/mod_manager.py
```

Or use a launcher: on Windows double-click `Run Mod Manager.bat`; on Linux run `./Run Mod Manager.sh`; on macOS double-click
`Run Mod Manager.command`. Each creates a private `.venv`, installs the requirements (again when `requirements.txt` changes)
and starts the app (the `(Dev)` variants also turn on the web view's dev tools). On Linux the web view needs a few system
libraries (`libxcb-cursor0 libxkbcommon-x11-0 libnss3 libasound2 ...`, see [Linux and macOS](cross-platform.md)). Packaged
releases are built with PyInstaller - see "Building a release" below.

The first launch asks for a **master folder** (where downloads, extracted mods and the app's own data are kept), then walks
you through a short setup, including pointing the app at the game files you extracted from **your own copy** of the game.
The app copies the few files it needs into the master folder; it doesn't ship anything from the game.

## Using it

The app walks you through four steps, shown in its header: **Setup**, **Choose mods**, **Commit**, **Copy to Switch**.
The day-to-day guide is the app's own **Help** panel (top right); it covers the flow, Menu Look, voice editing, conflicts
and known issues, and stays current with the UI because it lives in the UI (the `helpModal` spec in `src/ui/js/app-modals.js`).

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

`Build Release.bat` (or `python tools/build_release.py`) makes the package for the system it runs on - a PyInstaller build cannot be
made for another one: `dist/MK8DX-Mod-Manager-v<version>-windows.zip` (a PyInstaller folder build, `tools/mk8dx-mod-manager.spec`, no console
window), `...-linux-<x86_64|aarch64>.tar.gz` (Qt WebEngine inside) or `...-macos-<arm64|x86_64>.zip` (an unsigned `.app`). Each holds the app,
its Python runtime and 7-Zip's command-line tool, plus the license, a `THIRD-PARTY-NOTICES.txt` and a short readme. On Windows install
7-Zip on the build machine first (or pass `--no-7zip`); on Linux and macOS `tools/fetch_7zip.py` downloads the official `7zz` (pinned
version and SHA-256). On Linux install the system libraries Qt WebEngine needs first, so PyInstaller copies them into the package
(Debian/Ubuntu: `libnss3 libnspr4 libasound2 libegl1 libgl1 libfontconfig1 libdbus-1-3 libxkbfile1 libxcb-cursor0 libxcb-icccm4 libxcb-image0
libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-util1 libxcb-xkb1 libxkbcommon-x11-0`). The version comes from
`src/version.py`; bump it before building. What differs by system, and what was and was not tested: [Linux and macOS](cross-platform.md).

- **Licensing.** The app is GPL-3.0-or-later (`LICENSE`): `src/_bntx_structs.py` is GPL code (BNTX Editor), so everything that ships with it
  is distributed under the GPL. Everything of someone else's that the release contains must have its notice in the zip:
  `tools/third_party_notices.py` writes `THIRD-PARTY-NOTICES.txt` from the build environment's installed packages (a missing license text
  fails the build) plus the texts kept in `release/licenses/` (the icon set, Apache-2.0 for OpenSSL, libffi). Add a bundled library to
  its `PACKAGES` list; add an icon only by copying its drawing from Tabler Icons into `src/ui/js/ui/icons.js`. Credits go in the README's
  "About, license and credits", and the AI disclosure stays in the README, `release/README.md`, Help's About section and the GameBanana page.
- `src/app_paths.py` is the one place that knows where files are: `RESOURCE_DIR` (the read-only `ui/`,
  `roster.json`, `known-shared-files.json`, `name-labels.json`, found under PyInstaller's bundle folder when
  frozen) and `APP_ROOT` (where `app-config.json`, the log and the default `data` folder go: the folder holding the `.exe` on
  Windows, the user's app-data folder in a Linux or macOS build, `user_data_dir()`). A new bundled data
  file needs adding to the spec's `datas` and to be read through `app_paths.RESOURCE_DIR`.
- Files extracted from a downloaded zip carry Windows' "from the Internet" mark, and .NET refuses to load a marked DLL, so
  pythonnet (the window library) fails. `app_paths.unblock_downloaded_files()` clears the mark from the bundled files at
  startup, before `webview` is imported. Test a build by marking its files (see the CI smoke test), not just by extracting a
  local zip, which leaves no mark.
- Each package holds exactly one readme, copied in as `README.md`: `release/README.md` (Windows), `release/README-linux.md` or
  `release/README-macos.md`. They are written separately from the repository's `README.md` and are the only place to edit the text
  users see in the download; CI fails if a package ends up with more than one.
- First run: with no `app-config.json`, the master folder is `data` next to the app (`default_master_dir()` in
  `mod_manager.py`; `sd-card-staging` is then inside it - see `_staging_dir()`). The wizard's first step, "Data folder" (a setting of `settings-registry.js`, drawn the same in Settings), shows
  it marked Recommended (`get_master_dir_status()["is_default"]`); Next keeps it, "Change folder..." picks another (written to
  `app-config.json`), and "Use the recommended folder" (`use_default_master_dir()`) deletes that pointer again. When the default
  spot isn't writable the old full-screen folder picker is shown instead. The `data` folder is created at run time, never shipped
  in the zip, so extracting an update over an old install keeps the user's data.
- A packaged build has no console, so `app_paths.redirect_output_to_log()` sends stdout/stderr to
  `mod-manager.log` next to the `.exe` (every run adds to it; see `docs/diagnostics.md`), and an uncaught startup error shows a
  message box pointing at it. Run from source (`python src/mod_manager.py`) the same file is written in the repository folder (git-ignored)
  and the console still gets everything: `redirect_output_to_log(tee=True)`. That happens only when the file is run as the program,
  never on a plain import, so the tests and scripts that import `mod_manager` are untouched. What goes in the log, and Help > Show log file: `docs/diagnostics.md`.
- Build with a mainstream Python and test the zip on a machine without Python: extract it to a short path,
  run the setup wizard, download a `.7z` mod, commit.

### The app's icon

The exe carries `tools/app-icon.ico` (the spec's `icon=`): Windows shows it on the file, the taskbar, alt-tab and the window's title bar, because
pywebview takes the window's icon from the exe. The macOS `.app` carries `tools/app-icon.icns`; on Linux the window's icon is
`app-icon.png` (`window_icon()` in `mod_manager.py`; it is bundled in the package). From source on Windows the window shows Python's icon instead.
To change it, run `python tools/make_icon.py path/to/picture.png`: it crops the picture to what is drawn, centres it on a square, and rewrites
`tools/app-icon.png` (512 px), `tools/app-icon.ico` (16 to 256 px) and `tools/app-icon.icns`.

### Publishing a release (GitHub Actions)

`.github/workflows/release.yml` builds the packages on GitHub and publishes them as one Release - they are never
committed (`dist/` is ignored). It runs on every push to `master`/`main`, but only builds when `src/version.py`
names a version that has no release yet:

1. Bump `VERSION` in `src/version.py` (MAJOR.MINOR.PATCH) in the change you merge.
2. When it lands on `master`, the workflow builds the Windows zip, the Linux tarball (Ubuntu 22.04) and the macOS zip (Apple Silicon),
   checks their contents, and creates release `v<version>` (tag at that commit, auto-generated notes, every package that was built plus a
   `.sha256` file for each). The Windows package decides: the Linux and macOS jobs are `continue-on-error`, so if one fails the release
   still goes out with the others, and the failed job's log says why.
3. A push that doesn't change the version finds `v<version>` already released and does nothing.
4. A pull request that touches what a package is made of (`tools/`, `requirements.txt`, `release/`, `src/app_paths.py`, `src/version.py`, the
   workflow) builds all three packages too, with nothing published and read-only permissions. There a failed Linux or macOS job fails the
   check (`continue-on-error` is only for pushes), so a broken build is seen before merging. Its artifacts are kept for 3 days.

The workflow also runs the packaged app with `--self-check` (no window; `mod_manager.self_check()`): it checks the page files, the data files,
Pillow with WebP, 7-Zip and the backend, and exits non-zero if one is missing from the package. That step is `continue-on-error` until it has
passed on a runner once - then delete that line in `release.yml` so a broken package stops the release. `.github/workflows/tests.yml` runs the
unit tests on Windows, Linux and macOS on every pull request and push to `master`.

To test the build without releasing, run the workflow by hand (Actions > Release > Run workflow): it builds and
attaches the packages to the run as artifacts only. To redo a release, delete the release and its tag on GitHub,
then re-run the workflow on that commit (or bump the patch version instead).
