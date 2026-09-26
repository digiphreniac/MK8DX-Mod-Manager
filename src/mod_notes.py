"""The user's own notes on their mods.

Each mod (a row on a card, keyed by its unit key like the ticks: "characters/Toad/Some mod/sub") can carry a free-text note. The
page shows it on the mod's row and marks the tile of the character / course / part whose ticked mod has one. Stored in
`<master>/mod-notes.json` as {unit key: {"note": str}}; a mod with no note has no entry. Like the ticks, the page sends one mod's
note at a time - never its whole picture - and a page that loaded another master folder is refused (the epoch from get_mods).
"""
from pathlib import Path

import safe_io

NOTES_FILENAME = "mod-notes.json"
MAX_NOTE_CHARS = 4000


class ModNotesMixin:
    def _notes_path(self):
        return None if self.mod_root is None else Path(self.mod_root) / NOTES_FILENAME

    def _notes_load(self) -> dict:
        path = self._notes_path()
        data = safe_io.read_json_with_backup(path, {}) if path is not None else {}
        return data if isinstance(data, dict) else {}

    def _notes_update(self, change):
        """Runs `change(notes)` on the file's current content and writes the result, all under one lock."""
        path = self._notes_path()
        if path is None:
            return None
        with self._notes_lock:
            notes = self._notes_load()
            result = change(notes)
            safe_io.write_json_atomic(path, notes, keep_backup=True)
            return result

    def _notes_payload(self) -> dict:
        """What get_mods hands the page: {unit key: note text} for every mod that has a note."""
        out = {}
        for key, entry in self._notes_load().items():
            note = entry.get("note") if isinstance(entry, dict) else None
            if isinstance(note, str) and note.strip():
                out[key] = note
        return out

    def set_mod_note(self, unit_key, note, epoch=None):
        """Sets one mod's note (replacing its earlier one; nothing else changes). An empty note removes the entry. Returns
        {"success": True, "note": the saved text}, or {"success": False, "stale": True} for a page that loaded another master
        folder (it reloads), or {"success": False, "error": ...}."""
        if epoch is not None and epoch != self._root_epoch:
            return {"success": False, "stale": True}
        if self.mod_root is None:
            return {"success": False, "error": "No master folder is set up yet."}
        if (not isinstance(unit_key, str) or not unit_key or len(unit_key) > 600 or unit_key.startswith("/")
                or ".." in unit_key.split("/")):
            return {"success": False, "error": "That isn't a mod."}
        note = (note if isinstance(note, str) else "").strip()[:MAX_NOTE_CHARS]

        def change(notes):
            if note:
                notes[unit_key] = {"note": note}
            else:
                notes.pop(unit_key, None)
        self._notes_update(change)
        return {"success": True, "note": note}

    def _notes_clear_prefix(self, prefix):
        """Forgets the notes of a mod that was removed (`prefix` is "category/item/mod")."""
        def clear(notes):
            for k in [k for k in notes if k == prefix or k.startswith(prefix + "/")]:
                del notes[k]
        self._notes_update(clear)

    def _notes_rekey(self, old_rel, new_rel):
        """A mod's folder moved from `old_rel` to `new_rel`: its notes (and those of anything beneath it) follow."""
        def rekey(notes):
            for k in [k for k in notes if k == old_rel or k.startswith(old_rel + "/")]:
                notes[new_rel + k[len(old_rel):]] = notes.pop(k)
        if self.mod_root is not None and self._notes_path().is_file():
            self._notes_update(rekey)
