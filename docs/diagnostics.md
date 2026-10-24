# Diagnostics: the log and "Show log file"

When a user reports a problem, the only things we can ask them for are the log file and some text they can paste. This page is what
those contain and how to keep them useful. (A packaged build has no console and no dev tools; from source the console still gets everything too.)

## The log

- `mod-manager.log` next to the app (the temp folder when the app folder isn't writable - the details say so). Everything the app
  prints goes there: `app_paths.redirect_output_to_log()` points stdout/stderr at it before any library is imported.
- The log is **append-only**: every run adds to it, after a line `=== <date time> - Mod Manager started ===`, so opening the app again to
  "try once more" doesn't destroy the evidence and a report is one file. When it is over 1 MB at start-up (`LOG_MAX_BYTES`) only the newest
  ~500 KB are kept (`_trim_log()`, cut at a line). `faulthandler` is on, so a crash inside a native library still leaves where Python was.
- `diag.py` is the one place that writes to it: `diag.log(kind, message)` gives `[2026-10-23 13:37:06] kind: message`.
  `diag.log_once(key, ...)` is for a problem a reader would hit again on every call (a damaged settings file is read often).
  Every path goes through `diag.scrub()`, which replaces `C:\Users\<name>` (and `/Users/<name>`, `/home/<name>`) with `~`.
  Logging never raises.
- pywebview itself writes the traceback of any `Api` method that raises, so an uncaught error always has one. What it lacks is the
  time and the page's side of the story, which is what the rest of this page adds.

## What the page adds

`src/ui/js/diagnostics.js` (loaded from `index.html` before `bootstrap.js`, so it sees the app's own scripts fail) sends to
`Api.log_client(events)`:

- script errors (with file and line, no query string), scripts that didn't load, and unhandled promise rejections;
- every backend call that throws (`api_error`, by method name), answers `{"error": "..."}` (`api_fail`), or takes more than 3 s
  (`api_slow`). Never the arguments or the answer: they can be big, or private. Pictures that fail to load are not logged;
- one `page-start` line (the WebView2 version is in the user agent, `Edg/<version>`);
- a message on the page if the backend never says it is ready within 20 s, saying where the log is.

The page side is a thin wrapper around every method of `pywebview.api`, installed on `pywebviewready`, before `api-coalesce.js`
wraps its shared calls. `log_client` and `get_diagnostics` are never wrapped, so logging can't log itself.

`diag.ClientLog` keeps the channel from filling the log: 20 events per call, 2000 characters each, 300 lines per run, and the same
message is written once and again at its 10th, 100th and 1000th time (with the count). Anything that isn't a list of dicts is ignored.

New code that catches an error and carries on should say so: `diag.log("warn", ...)` in Python, `diag.warn(kind, message)` in the page.
A `catch` that only sets a fallback leaves nothing to diagnose from.

## The details in the log

- **Help > More support > Show log file** (`Api.show_log_file()`) opens the file manager with `mod-manager.log` selected: it is the file
  support asks for, and the Discord button beside it is where to ask. The log begins every run with the details below, so nothing else has to
  be copied. (From source there is no log file and the button says so.) `Api.get_diagnostics()` - the same details plus the end of the log and the
  page's last messages - is still there, and gives a failed commit its header, but nothing in Help calls it any more. The details are `_diag_lines()` (versions, the data folder and whether it exists and is writable,
  free space, game version / build id / language, the state of the game files copy - what the manifest says *and* whether
  `common.sarc`, `menu.sarc` and the language's `message.sarc` are really on disk - the 7-Zip found, Pillow with WebP, pywebview, the text
  encoding), the end of `mod-manager.log`, and the page's last messages.
- A **commit log** (`merge()`) opens with the four-line short form of the same details, and a commit that throws gets it too, so a
  pasted Copy log says which app version and settings made it.
- The same full details are written to the log at startup.

## When someone reports a problem

Ask for **the log file** (Help > Show log file, or `mod-manager.log` next to the app when it won't open), and for the commit log
(Copy log on the Commit page) when it is about the output. Look first at: the game files lines (a copy that is "complete" in the manifest
but MISSING on disk), `warn: ... couldn't be read` lines (a settings file that was reset), `page-error` lines, and the data folder line
(OneDrive, not writable, no space).

## What the risky paths record

- **The commit** (`merge()`): the log opens with the short details and, besides the existing sections, lists the files in `ui-icons/`
  that were included (with when each was built: an old one is why an icon can show an earlier mod's picture), the clashes settled by saved
  choices (path -> winning mod), and the Commit page's notes (the same cards, as text). The whole commit log is also written to
  `mod-manager.log`. A copy into the staging folder that stops halfway (disk full, a file locked by antivirus or OneDrive, a path too long)
  is a **failed commit**: the log says where it stopped and why, `last_commit` is cleared so the flow doesn't call the folder current, and the
  user is told not to copy it (`_commit_failed()`).
- **The menu icons build** (`describe_ui_build()`): one line per archive - built (changes applied / left out), or not made, and *why*: no selected
  mod changes anything in it, or N changes can't be used (`ui_setup.dropped_changes()`: a picture of another shape, a screen the user's game
  file doesn't have, changes set aside as unrelated), each with the mod, what, and the reason (first 8). Any error while reading the mods' UI
  files names the exception and writes its traceback instead of aborting the commit.
- **The copy of the game's files** (`game_files.copy_both()`): start and end lines, every problem, an all-or-nothing swap (see
  [Base game files](base-game-files.md)), and `status()` checks the files are really there.
- **Downloads** (`_download_and_extract_one()` wraps `_download_and_extract()`): any exception is logged with the mod and file, a folder left
  half-unpacked is removed, and the page gets a `GameBananaError` it shows - not an exception that left the spinner running. A finished download
  logs one line: status, how many mod folders and code patches, **which repairs changed its folders** (`fixers`), slot/music mismatches and the
  top-level contents. `_download_direct()` logs host and path (never the query: it can carry tokens), HTTP status and content type, recognises a
  web page instead of an archive, and a full disk; `extract_archive()` logs 7-Zip's exit code and output, handles a 7-Zip that can't start,
  doesn't wait for a password, and reads its output leniently. A refile (a mod moved to another card) is logged with why.
- **Settings and other app files** (`_load_json()`): a lock for a moment is waited out (up to about a second, on Windows), then the previous good
  copy (`<name>.bak`, kept by every save) is used, and only then the defaults - always with a line. `save_settings()` is under a lock, so two saves
  at once can't lose each other's change. A refused save of selections (the page held another folder's) is logged.
- **Errors that used to vanish** (the warm-up, the GameBanana look-ahead, naming a character after its mod, keeping Custom voice mods up to
  date) are logged once each with their traceback.

## When the page would otherwise be stuck or stale

Every backend call is already logged when it fails (the wrapper above), including the ones whose `catch` only sets a fallback, so those need no
line of their own. What the user can't see is the effect, so:

- `diag.banner(kind, message, retry)` puts a bar across the top of the page (Try again / Dismiss). It is used when the app can't finish starting
  (`main.js`: `startApp()`, and `loadMods()` / `loadSettings()` that used to be started and forgotten, which left "Loading mods..." for ever) and
  when a selection couldn't be saved (`saveChecked()`).
- **Any unhandled promise rejection** shows the same bar (except an interrupted sound): nothing caught it, so nothing told the user - a setting
  that didn't save, a screen that didn't load.
- `diag.attempt(() => call)` returns the answer, or `{success: false, error}` when the call threw, for code that already shows `result.error`:
  downloads and fetching a mod (`gamebanana.js`, `add-mod.js`: the section is enabled again and the message shown), the data-folder change
  (`settings-panels.js`, `setup-wizard.js`) and finishing setup. `diag.describe(e)` is the sentence it uses, with the Python exception's name.
- The Commit page says "Couldn't check your mods" with Try again instead of "Checking your mods..." for ever.

## Changing the data folder

"Bring my files" moves every item in `MASTER_DIR_ITEMS`: besides the mods, caches and settings, that now includes `game-files/` (without it the
setup wizard came back), `voice-edits.json`, `voice-custom/`, `look-reviews.json` and the `.bak` copies. It stops at the first item that can't be
moved and **puts back** what it had already moved, so the data is never split between two folders; the log has the old and new folder and every
error. When you add a file the app keeps in its data folder, add it to that list.

## The packaged app checks itself

`MK8DX Mod Manager.exe --self-check` opens no window and uses a temporary folder: it logs one line per check (version, page files, `roster.json`,
`name-labels.json`, `known-shared-files.json`, Pillow with WebP, 7-Zip runs, the backend starts) and exits non-zero if any failed. The release
workflow runs it on the unzipped package (see `docs/DEVELOPERS.md`). From source: `python src/mod_manager.py --self-check`.

## What each mod contributed, and a commit that has gone stale

- The commit log says, for every selected mod, how many of its files were staged, how many were left out on purpose and how many lost to
  another mod's version (or one of the app's own files): `characters/Mario/Mod B: 1 of 3 file(s) staged, 1 left out, 1 replaced by another
  mod's version ...`. A mod with nothing staged is marked `<-- NOTHING from this mod was staged`, and the Commit page shows an
  "add nothing to the commit" card for it (`_contributions()`).
- A mod changed in place makes the last commit stale (`_commit_content_stamp()`, see [the guided flow](ui-and-flow.md)); a commit
  made before that existed is never called stale for it.

## The log where Pillow fails, the icon cache, the voice rebuild

- `ui_archives`, `bntx_decode` and `cup_icons` write an `error` line at import when Pillow can't be loaded (and `texture_png` one line per
  kind of failure), so "pictures are blank" has a cause in the log where it happens - the details header and `--self-check` report it too.
- `ui-setup-cache.json` doesn't keep failures (see [Caching and performance](caching-and-performance.md)).
- The Custom voice rebuild is atomic and logged (see [Voice editing](voice-editing.md)).

## Not done yet

The self-check step of the release workflow doesn't block a release yet (see `docs/DEVELOPERS.md`): delete its `continue-on-error` line after
it has passed on a runner once. Everything else listed by the audit that started this work has been done.
