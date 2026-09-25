"""Remembers what the app works out about the mod library, so the many calls a screen makes at once (the footer's numbers, the
flow bar, the pack badges, every card) don't each walk the whole mods folder again.

An answer is reused while ALL of these hold:
  - the library generation is the same: it goes up whenever the app itself changes the library (a download, a move, a delete, a
    voice edit - see mutates_library) and whenever the page asks to reload it (Api.get_mods, i.e. the Refresh button);
  - its "token" is the same: a cheap fingerprint of the folders' modification times (tree_token), which notices a mod folder
    added or removed by hand without listing a single file;
  - it is younger than max_age, when one is given - so a change the two checks above can't see (a file edited inside a mod) is
    picked up within seconds.
Nothing here is precious: anything can be worked out again, and a wrong reuse is bounded by those three.
"""
import functools
import os
import threading
import time


def tree_token(root, depth=3):
    """A fingerprint of the modification times of the folders under `root`, `depth` levels down (the root is level 0). A folder's
    time changes when something in it is added, removed or renamed, so this notices new or gone mods (root/category/item/mod)
    without looking at any file. Different whenever anything it covers changed."""
    seen = []

    def visit(path, level):
        try:
            seen.append((path, os.stat(path).st_mtime_ns))
        except OSError:
            seen.append((path, None))
            return
        if level == 0:
            return
        try:
            with os.scandir(path) as entries:
                for e in entries:
                    if e.is_dir(follow_symlinks=False):
                        visit(e.path, level - 1)
        except OSError:
            pass

    visit(str(root), depth)
    return hash(tuple(sorted(seen)))


class LibraryCache:
    MAX_ENTRIES = 64

    def __init__(self):
        self._lock = threading.RLock()
        self._gen = 0
        self._entries = {}   # name -> (generation, key, token, when, value)

    def bump(self):
        """The library was (or may have been) changed: everything remembered is out of date."""
        with self._lock:
            self._gen += 1
            self._entries.clear()

    def get(self, name, key, compute, *, token=None, max_age=None, copy=None):
        """`compute()`'s answer for (name, key), reused while it is still good (see the module note). `token` is a function
        giving the current fingerprint; `copy` makes the private copy each caller gets, so nobody's changes leak into the
        remembered one (default: hand out the value itself - only for answers nobody changes)."""
        with self._lock:
            gen = self._gen
            entry = self._entries.get(name)
        tok = token() if token else None
        now = time.monotonic()
        if entry and entry[0] == gen and entry[1] == key and entry[2] == tok and (max_age is None or now - entry[3] <= max_age):
            value = entry[4]
        else:
            value = compute()
            with self._lock:
                if self._gen == gen:   # (not changed while it was being worked out)
                    self._entries[name] = (gen, key, tok, now, value)
                    while len(self._entries) > self.MAX_ENTRIES:
                        self._entries.pop(next(iter(self._entries)))   # (the oldest)
        return copy(value) if copy else value


def mutates_library(method):
    """For an Api method that changes the mods folder: the remembered answers are dropped when it is done (and if it fails
    half way)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        finally:
            self._library.bump()
    return wrapper
