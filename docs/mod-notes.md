# Notes on mods

The user's own memory aid: a free-text **note** on a mod. Nothing here reaches the merge or the Switch - it is only for the person
using the app.

## What the user sees

* Every mod row on a card (character, course, vehicle part, item, ...) has a small pencil button: faint when the mod has no note,
  in the accent colour when it has one. Clicking it opens a text box under the row. The note saves half a second after typing stops
  and when the box loses focus.
* The tile of whatever the mod belongs to shows a small round pencil at its top left (under the voice mark on a character) when one of
  its **ticked** mods has a note - a note on a mod that is not in use doesn't mark the tile. Hovering the pencil lists the notes with
  their mods' names.

## How it is kept

* `<master>/mod-notes.json` = `{unit key: {"note": str}}`, keyed like the ticks (`category/item/mod/...`). A mod with no note has no
  entry. Written with `safe_io.write_json_atomic(keep_backup=True)` under one lock (`ModNotesMixin._notes_update`), read with the
  `.bak` fallback. It is one of `MASTER_DIR_ITEMS`, so it moves with the folder. (An earlier version also stored flags; those are
  ignored on reading, and an entry with only flags is dropped.)
* Like the ticks, the page sends **one mod's** note at a time (`Api.set_mod_note(unit_key, note, epoch)`), never its whole map, and a
  page whose `epoch` isn't the backend's current one (the master folder was switched) is refused with `{"success": False, "stale":
  True}`; the page then reloads. `get_mods()` returns `notes` = `{unit key: text}`.
* Life cycle: a mod's note **follows it** when its folder moves (`_rekey_unit_prefix` -> `_notes_rekey`), is **kept** when the mod is
  downloaded again (the folder name is the key), and is **forgotten** when the user removes the mod (`remove_mod_unit`).
* A screen's signature (`entriesSignature` in `views.js`) includes the notes of its ticked units (`notesSignature`), so a change to a
  note - or ticking a noted mod - redraws the tiles behind the card and nothing else.

Tests: `tests/test_mod_notes.py`.
