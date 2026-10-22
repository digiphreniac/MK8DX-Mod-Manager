"""Writing the app's own JSON files without ever leaving a half-written one where a reader (or the next launch) could find it.

`Path.write_text()` empties the file first and fills it after, so anything that reads it in between - another call the page
made a moment earlier, or the next launch after a crash - sees an empty file. The app's readers treat an unreadable file as
"nothing there", which for the ticked mods meant every tick was gone. Here the new content goes to a temporary file next to the
real one and replaces it in one step (`os.replace`), so the file is always either the old content or the new content.

The ticked-mods file also keeps the previous good copy as `<name>.bak`, and reading it falls back to that copy when the file
itself can't be read - so even a damaged file costs at most the last change.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path


def _replace(tmp: Path, path: Path) -> None:
    """`os.replace`, which on Windows fails with PermissionError for as long as another thread or program (a virus scanner, the
    indexer) has the target open - for a moment only, so it is tried again a few times before giving up."""
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == 49:
                raise
            time.sleep(0.005 * (attempt + 1))


def write_text_atomic(path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    finally:
        try:
            tmp.unlink()   # (only still there when the replace didn't happen)
        except FileNotFoundError:
            pass


def write_json_atomic(path, data, keep_backup: bool = False, **dump_kwargs) -> None:
    """Writes `data` as JSON (indented, keys sorted) in one step. `keep_backup`: the file's previous content is first kept as
    `<name>.bak` - but only when it is itself a readable, non-empty JSON object, so a damaged file never replaces a good copy."""
    path = Path(path)
    dump_kwargs.setdefault("indent", 2)
    dump_kwargs.setdefault("sort_keys", True)
    if keep_backup:
        try:
            old = path.read_text(encoding="utf-8")
            if isinstance(json.loads(old), dict) and json.loads(old):
                write_text_atomic(path.with_name(path.name + ".bak"), old)
        except (OSError, ValueError):
            pass
    write_text_atomic(path, json.dumps(data, **dump_kwargs))


def read_json_with_backup(path, default):
    """The JSON in `path`; when the file is missing, `default`. When it exists but can't be read, the `.bak` copy (with a
    line on stderr saying so), and only when that is unreadable too, `default`."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        for attempt in range(10):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except PermissionError:   # (Windows: opening a file fails for a moment while it is being replaced)
                if sys.platform != "win32" or attempt == 9:
                    raise
                time.sleep(0.005 * (attempt + 1))
    except (ValueError, OSError) as e:
        print(f"[safe_io] {path.name} couldn't be read ({type(e).__name__}: {e}); trying {path.name}.bak", file=sys.stderr, flush=True)
    try:
        return json.loads(path.with_name(path.name + ".bak").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        print(f"[safe_io] {path.name}.bak couldn't be read either; treating it as empty", file=sys.stderr, flush=True)
        return default
