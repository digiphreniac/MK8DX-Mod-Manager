"""
Where the app's own files are, whether it runs from source or as a PyInstaller build.

  RESOURCE_DIR - read-only files shipped with the app (ui/, roster.json, ...). From source that is
                 src/; in a frozen build PyInstaller unpacks them under sys._MEIPASS.
  APP_ROOT     - the app's install root, where app-config.json lives. From source that is the
                 folder above src/; in a frozen build it is the folder holding the .exe.
"""

import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    APP_ROOT = RESOURCE_DIR.parent

# Folder of the bundled 7-Zip command-line tool (release builds only; see tools/build_release.py).
BUNDLED_7ZIP_DIR = RESOURCE_DIR / "7zip"

LOG_FILENAME = "mod-manager.log"
LOG_MAX_BYTES = 1_000_000     # when the log is bigger than this at start-up, the oldest entries are cut...
LOG_KEEP_BYTES = 500_000      # ...down to about this much of the newest
LOG_FELL_BACK = False   # True when the log couldn't go next to the app and is in the temp folder instead
_log_path = None        # set once the output has been pointed at the log (see redirect_output_to_log)


def _trim_log(path):
    """Keeps a log that every run adds to from growing for ever: past LOG_MAX_BYTES only the newest LOG_KEEP_BYTES stay, cut at a line."""
    import os
    try:
        if path.stat().st_size <= LOG_MAX_BYTES:
            return
        with open(path, "rb") as f:
            f.seek(-LOG_KEEP_BYTES, 2)
            data = f.read()
        newline = data.find(b"\n")
        data = data[newline + 1:] if newline >= 0 else data
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(b"[older entries were cut to keep this file small]\n" + data)
        os.replace(tmp, path)
    except OSError:
        pass   # (a log that can't be trimmed is still a log)


class _Tee:
    """Stands in for stdout/stderr when the app is run from source: everything goes to the log file and, as before, to the console (if there
    is one). A character the console can't show must not cost the line in the log, so the file is written first and the console's errors
    are ignored."""

    def __init__(self, console, log):
        self._console, self._log = console, log

    def write(self, text):
        self._log.write(text)
        if self._console is not None:
            try:
                self._console.write(text)
            except (UnicodeError, OSError):
                pass
        return len(text)

    def flush(self):
        for stream in (self._log, self._console):
            try:
                if stream is not None:
                    stream.flush()
            except (OSError, ValueError):
                pass

    def __getattr__(self, name):   # (isatty, encoding, fileno... answer as the console would)
        return getattr(self._console if self._console is not None else self._log, name)


def current_log_path():
    """The log's path if redirect_output_to_log() has run in this process, else None."""
    return _log_path


def redirect_output_to_log(tee=False):
    """A packaged (windowed) build has no console, so stdout/stderr are None. Point them at
    mod-manager.log next to the app (the temp folder if that isn't writable) so messages from
    the app and its libraries are kept - the file is what to attach to a bug report. Every run adds to the file (a line
    marks where each starts), so relaunching to "try once more" doesn't destroy the evidence; the oldest entries are cut when it
    grows past LOG_MAX_BYTES. Returns the log's path.

    `tee=True` (the app run from source, which has a console): the console keeps getting everything too. If no log file can be opened
    then, nothing is changed and None is returned (the packaged build falls back to discarding its output instead).

    Done once per process: the app runs as `__main__` and some modules import it again by name (game_files does, late), which runs its
    top level a second time - without this the second call would add a second "started" line and open the file again."""
    import os
    from datetime import datetime
    global LOG_FELL_BACK, _log_path
    if _log_path is not None:
        return _log_path
    stream = None
    for folder in (APP_ROOT, Path(os.environ.get("TEMP") or ".")):
        try:
            _trim_log(folder / LOG_FILENAME)
            stream = open(folder / LOG_FILENAME, "a", encoding="utf-8", buffering=1)
            stream.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} - Mod Manager started ===\n")
            LOG_FELL_BACK = folder != APP_ROOT
            break
        except OSError:
            continue
    if stream is None:
        if tee:
            return None
        stream = open(os.devnull, "w")
    try:
        import faulthandler
        faulthandler.enable(file=stream)   # (a crash inside a native library still leaves where Python was)
    except Exception:   # noqa: BLE001
        pass
    if tee:
        sys.stdout, sys.stderr = _Tee(sys.stdout, stream), _Tee(sys.stderr, stream)
    else:
        sys.stdout = sys.stderr = stream
    _log_path = stream.name
    return _log_path


def unblock_downloaded_files():
    """Windows marks every file extracted from a downloaded zip as "from the Internet" (a hidden Zone.Identifier stream) and
    .NET refuses to load a DLL that carries the mark. The app's window library (pythonnet) is one, so without this the app
    cannot open its window. Clearing the mark from the app's own bundled files is the same as Properties > Unblock.
    Returns how many files had it."""
    import os
    if sys.platform != "win32":
        return 0
    cleared = 0
    for folder, _dirs, names in os.walk(RESOURCE_DIR):
        for name in names:
            try:
                os.remove(os.path.join(folder, name) + ":Zone.Identifier")
                cleared += 1
            except OSError:
                pass   # (no mark on this file, or it can't be changed)
    return cleared
