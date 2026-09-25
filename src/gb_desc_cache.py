"""GameBanana mod descriptions, kept on disk between runs.

A browse or search list has no descriptions, so the app asks GameBanana for each result's page (one request each, and it may only
send a few at a time). A mod's description hardly ever changes, so what was fetched is written to one small JSON file in the
master folder and reused: the second browse of a category, or the same search after a restart, needs no requests at all.
An entry is used for MAX_AGE_DAYS and is then fetched again; the oldest entries are dropped past MAX_ENTRIES. The file can be
deleted at any time.
"""
import json
import os
import threading
import time
from pathlib import Path

MAX_AGE_DAYS = 14
MAX_ENTRIES = 3000


class DescriptionCache:
    def __init__(self, path):
        self.path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._entries = None    # {mod id (text): [saved at (seconds), description]}, read on first use
        self._dirty = False

    def _load(self):
        if self._entries is not None:
            return
        entries = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[1], str):
                        entries[str(k)] = v
        except (OSError, ValueError):
            pass
        self._entries = entries

    def get(self, mod_id):
        """The remembered description of a mod, or None (never fetched, or fetched too long ago)."""
        with self._lock:
            self._load()
            entry = self._entries.get(str(mod_id))
            if entry is None or time.time() - entry[0] > MAX_AGE_DAYS * 86400:
                return None
            return entry[1]

    def put_many(self, found: dict) -> None:
        """Remembers {mod id: description} and writes the file (once, however many)."""
        if not found:
            return
        with self._lock:
            self._load()
            now = time.time()
            for mod_id, text in found.items():
                self._entries[str(mod_id)] = [now, text]
            if len(self._entries) > MAX_ENTRIES:
                keep = sorted(self._entries.items(), key=lambda kv: kv[1][0], reverse=True)[:MAX_ENTRIES]
                self._entries = dict(keep)
            self._write()

    def _write(self):
        if self.path is None:
            return
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps(self._entries), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass    # (not remembered between runs - nothing else is affected)
        finally:
            tmp.unlink(missing_ok=True)
