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
LOG_PREVIOUS_FILENAME = "mod-manager.previous.log"
LOG_FELL_BACK = False   # True when the log couldn't go next to the app and is in the temp folder instead


def redirect_output_to_log():
    """A packaged (windowed) build has no console, so stdout/stderr are None. Point them at
    mod-manager.log next to the app (the temp folder if that isn't writable) so messages from
    the app and its libraries are kept - the file is what to attach to a bug report. The previous run's log is kept
    beside it as mod-manager.previous.log. Returns the log's path."""
    import os
    global LOG_FELL_BACK
    stream = None
    for folder in (APP_ROOT, Path(os.environ.get("TEMP") or ".")):
        try:
            try:   # (the run before is kept: opening the app again to "try once more" must not wipe the evidence)
                if (folder / LOG_FILENAME).stat().st_size > 0:
                    os.replace(folder / LOG_FILENAME, folder / LOG_PREVIOUS_FILENAME)
            except OSError:
                pass
            stream = open(folder / LOG_FILENAME, "w", encoding="utf-8", buffering=1)
            LOG_FELL_BACK = folder != APP_ROOT
            break
        except OSError:
            continue
    if stream is None:
        stream = open(os.devnull, "w")
    try:
        import faulthandler
        faulthandler.enable(file=stream)   # (a crash inside a native library still leaves where Python was)
    except Exception:   # noqa: BLE001
        pass
    sys.stdout = sys.stderr = stream
    return stream.name


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
