# Diagnostics: the log and "Copy details"

When a user reports a problem, the only things we can ask them for are the log file and some text they can paste. This page is what
those contain and how to keep them useful. (A packaged build has no console and no dev tools.)

## The log

- `mod-manager.log` next to the app (the temp folder when the app folder isn't writable - the details say so). Everything the app
  prints goes there: `app_paths.redirect_output_to_log()` points stdout/stderr at it before any library is imported.
- The run before is kept as `mod-manager.previous.log`, so opening the app again to "try once more" doesn't destroy the evidence.
  `faulthandler` is on, so a crash inside a native library still leaves where Python was.
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

## The details a user can copy

- **Help > Copy details** calls `Api.get_diagnostics()`: `_diag_lines()` (versions, the data folder and whether it exists and is writable,
  free space, game version / build id / language, the state of the game files copy - what the manifest says *and* whether
  `common.sarc`, `menu.sarc` and the language's `message.sarc` are really on disk - the 7-Zip found, Pillow with WebP, pywebview, the text
  encoding), the end of `mod-manager.log`, and the page's last messages.
- A **commit log** (`merge()`) opens with the four-line short form of the same details, and a commit that throws gets it too, so a
  pasted Copy log says which app version and settings made it.
- The same full details are written to the log at startup.

## When someone reports a problem

Ask for **Help > Copy details** (or `mod-manager.log` and `mod-manager.previous.log` when the app won't open), and for the commit log
(Copy log on the Commit page) when it is about the output. Look first at: the game files lines (a copy that is "complete" in the manifest
but MISSING on disk), `warn: ... couldn't be read` lines (a settings file that was reset), `page-error` lines, and the data folder line
(OneDrive, not writable, no space).

## Not done yet

The commit and download paths still swallow some failures without a line: the staging copy has no `try`, the `fix_*` functions report only true/false, skipped icons keep their reasons to themselves, and
`_load_json` falls back to defaults instead of the `.bak` copy. Each is a small, local addition of a `diag.log` line.
