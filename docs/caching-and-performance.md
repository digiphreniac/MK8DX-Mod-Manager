# Caching and performance

What the app remembers so it doesn't redo work. Every cache here is derived data: it is rebuilt from the game files or the mods' files when missing or stale, so any of it can be deleted at any time.

How the pieces fit: pictures decoded from the game's textures go to the disk cache (`image_cache.py`); a background pass (`Api._warm_up`) fills it and the in-memory caches shortly after launch; `library_cache.py` remembers what was worked out about the mods folder until something changes it (`@mutates_library`); the page keeps the pictures it already has and shares identical read-only backend calls (`js/api-coalesce.js`, see [Frontend file layout](architecture.md#frontend-file-layout) in [architecture.md](architecture.md)); GameBanana browse lists fill in in two steps (see [gamebanana-browse.md](gamebanana-browse.md)).

The entries below were moved here from the file list in [architecture.md](architecture.md).

- `src/image_cache.py` - the disk cache for everything decoded from a game texture (see `image-cache/` below), so a
  picture is decoded once, not on every launch. `ui_archives.py` keeps decompressed icon archives the same way
  (`image-cache/archives/`), and `src/gb_desc_cache.py` keeps GameBanana descriptions (`gamebanana-descriptions.json`).
- `src/library_cache.py` - remembers what the app works out about the mods folder (the list of mods, pack links, folder
  sizes, the read-only conflict check) while nothing it read has changed, so the many calls one screen makes don't each walk
  the whole library. It is dropped when the app changes the library (`@mutates_library`), on Refresh (`Api.get_mods`), when
  a mod folder is added or removed by hand, and after a few seconds at most. The commit itself always reads the files afresh.

- `ui-setup-cache.json` - cache of the icons/text read out of your mods'
  archives (safe to delete; it just makes the next build faster)
- `image-cache/` - pictures decoded from the game's textures (kept as WebP, quality 90 - 3 to 5 times smaller than PNG, which
  is what crosses into the page): the cup medallions, vehicle and item pictures (one JSON file
  each) and each course/part/character-menu picture (`pictures/`), including the previews of mods' own course pictures;
  and `archives/`, the decompressed icon archives (the ~12 that are opened over and over, ~60 MB; at most 24 files, the
  least recently used are dropped). An entry is
  rebuilt whenever the file it came from changes, and "Update from a new dump" clears it; safe to delete at any time.
  A background pass (`Api._warm_up`, started shortly after launch and after a new dump) fills it, plus this run's memory
  caches, before you open the screens - about 5 seconds on a fresh folder, under a second once it is filled.
- `gamebanana-descriptions.json` - the descriptions of the mods GameBanana listed in a browse or search, so seeing the
  same list again (or after a restart) needs no requests; an entry is used for 14 days, at most 3000 are kept. Safe to delete.

## Rules for changing caches

- Everything in `image-cache/`, `ui-setup-cache.json` and `gamebanana-descriptions.json` is derived data: it must always be
  safe to delete, so never store anything in it that only it knows.
- Change how a picture is decoded or encoded -> raise `image_cache.VERSION`. Entries are keyed by the source file's
  (size, modification time) stamp, and are written atomically.
- Any `Api` method that changes the mods library (adds, removes, moves or rebuilds a mod) carries `@mutates_library`
  (`library_cache.py`); otherwise screens keep showing the old library for up to a few seconds. `merge()` always reads the files afresh.
- Code the background warm-up calls must be thread-safe (`_ui_setup_plan` holds a lock).
