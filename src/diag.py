"""What the app writes to its log, and how a user hands it over.

A packaged build has no console, so everything the app says goes to `mod-manager.log` next to it (app_paths.redirect_output_to_log).
This module is the one place that writes to it: timestamped lines, usernames taken out of paths, and a cap on how much the page
(the JavaScript side) may add. It never raises - logging must not be the thing that breaks the app.

  log(kind, message)        one timestamped line
  log_once(key, kind, msg)  the same, but only the first time for that key (for things that would repeat on every read)
  scrub(text)               "C:\\Users\\name\\..." -> "~\\..."
  ClientLog                 what Api.log_client() hands to: batches of page errors, capped and de-duplicated
  tail(path, lines)         the end of the log, for "Copy diagnostics"

See docs/diagnostics.md.
"""
import collections
import locale
import platform
import re
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

LOG_PATH = None   # mod-manager.log (set by mod_manager when the app runs as the program, packaged or from source); None otherwise

# C:\Users\name (any drive), and /Users/name or /home/name written without a drive (a path from another system, kept in a manifest)
_USER_DIR = re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:|(?<![\w\\/.]))[\\/]+(?:Users|home)[\\/]+[^\\/\s\"'<>|:*?]+", re.IGNORECASE)
_seen_once = set()
_seen_lock = threading.Lock()


def scrub(text) -> str:
    """Replaces the Windows user's folder (C:\\Users\\<name>) with ~ so a shared log doesn't carry the username."""
    return _USER_DIR.sub("~", str(text))


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(kind: str, message) -> None:
    try:
        if sys.stderr is None:   # (print(file=None) would use stdout instead)
            return
        text = scrub(message).replace("\n", "\n    ")
        print(f"[{stamp()}] {kind}: {text}", file=sys.stderr, flush=True)
    except Exception:   # noqa: BLE001 - (no stderr, a closed stream, ...: nothing sensible left to do)
        pass


def log_once(key, kind: str, message) -> None:
    """`log()`, but only the first time `key` is seen - for a problem a reader would hit again on every call."""
    with _seen_lock:
        if key in _seen_once:
            return
        _seen_once.add(key)
    log(kind, message)


# --------------------------------------------------------------------------------------------------- page messages
class ClientLog:
    """Batches of messages from the page (errors, failed or slow calls). Capped so a page stuck in a loop can't fill the log:
    at most MAX_BATCH events per call, MAX_FIELD characters each, MAX_PRINTED lines per run, and the same message is printed
    once (then again at its 10th, 100th and 1000th time, with the count)."""
    MAX_BATCH = 20
    MAX_FIELD = 2000
    MAX_PRINTED = 300
    LEVELS = ("error", "warn", "info")

    def __init__(self):
        self._lock = threading.Lock()
        self._counts = collections.Counter()
        self._printed = 0
        self._capped = False

    def accept(self, events) -> int:
        """Prints what is new. Returns how many lines were printed. Never raises, whatever it is given."""
        try:
            if not isinstance(events, list):
                return 0
            printed = 0
            for ev in events[:self.MAX_BATCH]:
                if not isinstance(ev, dict):
                    continue
                kind = re.sub(r"[^A-Za-z0-9_-]", "", str(ev.get("kind") or "page"))[:40] or "page"
                level = ev.get("level") if ev.get("level") in self.LEVELS else "info"
                msg = str(ev.get("msg") or "")[:self.MAX_FIELD]
                with self._lock:
                    key = (kind, msg[:200])
                    self._counts[key] += 1
                    n = self._counts[key]
                    if n > 1 and n not in (10, 100, 1000):
                        continue
                    if self._printed >= self.MAX_PRINTED:
                        if not self._capped:
                            self._capped = True
                            log("page", f"(more than {self.MAX_PRINTED} page messages this run; the rest are not written)")
                        continue
                    self._printed += 1
                log(f"page-{level}/{kind}", msg + (f"  (x{n})" if n > 1 else ""))
                printed += 1
            return printed
        except Exception:   # noqa: BLE001
            return 0


client_log = ClientLog()


# --------------------------------------------------------------------------------------------------- reading it back
def tail(path, lines: int = 150, max_bytes: int = 65536) -> str:
    """The last `lines` lines of a text file (usernames taken out), or "" when it can't be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
        return scrub("\n".join(data.decode("utf-8", errors="replace").splitlines()[-lines:]))
    except OSError:
        return ""


# --------------------------------------------------------------------------------------------------- the environment
def system_line() -> str:
    try:
        return f"{platform.system()} {platform.release()} ({platform.version()}), {platform.machine()}"
    except Exception:   # noqa: BLE001
        return "unknown system"


def free_gb(path) -> str:
    try:
        return f"{shutil.disk_usage(path).free / 1e9:.1f} GB free"
    except OSError:
        return "free space unknown"


def library_line() -> str:
    """Versions of the libraries whose absence or breakage shows up only as 'pictures missing' or 'window won't open'."""
    parts = []
    try:
        import PIL
        from PIL import features
        parts.append(f"Pillow {PIL.__version__} (WebP {'yes' if features.check('webp') else 'NO'})")
    except Exception as e:   # noqa: BLE001
        parts.append(f"Pillow NOT AVAILABLE ({type(e).__name__}: {e})")
    try:
        from importlib import metadata
        parts.append(f"pywebview {metadata.version('pywebview')}")
    except Exception:   # noqa: BLE001
        # Not a problem in browser mode, which is how Linux runs: the package carries no pywebview at all.
        parts.append("pywebview not installed")
    parts.append(f"text encoding {locale.getpreferredencoding(False)}")
    return ", ".join(parts)
