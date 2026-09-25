"""A disk cache for pictures the app has to decode from the game's own texture formats (BNTX / SARC), so each is decoded once
and every later launch just reads a PNG.

Nothing in here is precious: every entry is rebuilt from the game files or a mod's files whenever it is missing or stale, so
the whole folder can be deleted at any time. An entry is stale when the file it came from changed (its size or modification
time - "stamp"), or when VERSION is raised because the decoding itself changed.

Two shapes:
  picture(name, stamp, build)  one image, kept as <root>/pictures/<hash of name>.<hash of stamp>.png; older stamps of the same
                               name are removed when a new one is written.
  group(name, stamp, build)    a whole set at once (all the cup medallions, all the vehicle pictures, ...) kept as one JSON file,
                               {picture name: PNG data URI}, because that is what the screens ask for in one go.
A build that gives nothing (the file was unreadable) is never stored - the next call tries again.
"""
import base64
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path

DIRNAME = "image-cache"
VERSION = 1


def digest(*parts) -> str:
    """A short fingerprint of anything printable - the "stamp" for a cache entry."""
    h = hashlib.sha1(repr((VERSION,) + tuple(parts)).encode("utf-8"))
    return h.hexdigest()[:16]


def file_stamp(path) -> tuple:
    """(size, modification time) of a file, or None when it can't be read."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _write_atomic(path: Path, data: bytes) -> None:
    """Never leaves a half-written file where a reader could find it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


class ImageCache:
    def __init__(self, root):
        self.root = Path(root) if root is not None else None

    def picture(self, name: str, stamp, build):
        """PNG bytes for `name`: from disk when its stamp still matches, else `build()` (PNG bytes or None) and store it.
        Any trouble with the cache folder just means the picture is built each time - never an error."""
        if self.root is None or stamp is None:
            return build()
        key = hashlib.sha1(name.encode("utf-8")).hexdigest()[:20]
        path = self.root / "pictures" / f"{key}.{digest(stamp)}.png"
        try:
            if path.is_file():
                return path.read_bytes()
        except OSError:
            pass
        png = build()
        if png:
            try:
                for old in path.parent.glob(f"{key}.*.png"):
                    old.unlink(missing_ok=True)
                _write_atomic(path, png)
            except OSError:
                pass
        return png

    def group(self, name: str, stamp, build) -> dict:
        """{picture name: PNG data URI}: from disk when the stamp still matches, else `build()` ({picture name: PNG bytes},
        {} when nothing could be read) and store it."""
        if self.root is None:
            return {n: data_uri(p) for n, p in build().items()}
        path = self.root / f"{name}.json"
        stamp = digest(stamp)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("stamp") == stamp and isinstance(saved.get("icons"), dict):
                return saved["icons"]
        except (OSError, ValueError):
            pass
        icons = {n: data_uri(p) for n, p in build().items()}
        if icons:
            try:
                _write_atomic(path, json.dumps({"stamp": stamp, "icons": icons}).encode("utf-8"))
            except OSError:
                pass
        return icons

    def clear(self) -> None:
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
