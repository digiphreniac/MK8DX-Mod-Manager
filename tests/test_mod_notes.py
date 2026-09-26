"""Notes on mods (src/mod_notes.py): stored per mod, merged one mod at a time, and never lost to a stale page."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager  # noqa: E402
import mod_notes    # noqa: E402

_real_app_root = mod_manager.APP_ROOT


def setUpModule():
    mod_manager.APP_ROOT = Path(tempfile.mkdtemp(prefix="mk8dx-approot-"))   # (set_master_dir writes app-config.json here)


def tearDownModule():
    mod_manager.APP_ROOT = _real_app_root


KEY = "characters/Toad/Some mod/Unit"


def make_api():
    root = Path(tempfile.mkdtemp(prefix="mk8dx-notes-"))
    api = mod_manager.Api(root)
    return api, root, api.get_mods()["epoch"]


def on_disk(root):
    return json.loads((root / mod_notes.NOTES_FILENAME).read_text())


class Notes(unittest.TestCase):
    def test_a_note_is_saved_and_comes_back_with_the_mods(self):
        api, root, epoch = make_api()
        r = api.set_mod_note(KEY, "  check the horn  ", epoch)
        self.assertEqual((r["success"], r["note"]), (True, "check the horn"))
        self.assertEqual(api.get_mods()["notes"], {KEY: "check the horn"})

    def test_one_mods_change_leaves_every_other_mod_alone(self):
        api, root, epoch = make_api()
        api.set_mod_note("characters/A/B/C", "a", epoch)
        api.set_mod_note("characters/A/D/E", "b", epoch)
        api.set_mod_note("characters/A/B/C", "changed", epoch)
        self.assertEqual(on_disk(root), {"characters/A/B/C": {"note": "changed"}, "characters/A/D/E": {"note": "b"}})

    def test_clearing_the_note_removes_the_entry(self):
        api, root, epoch = make_api()
        api.set_mod_note(KEY, "x", epoch)
        api.set_mod_note(KEY, "   ", epoch)
        self.assertEqual(on_disk(root), {})

    def test_bad_keys_are_refused(self):
        api, root, epoch = make_api()
        for bad in ("", "/etc/passwd", "characters/../x", None, 5):
            self.assertFalse(api.set_mod_note(bad, "x", epoch)["success"])

    def test_a_page_from_another_master_folder_is_refused(self):
        api, root, epoch = make_api()
        other = Path(tempfile.mkdtemp(prefix="mk8dx-notes-other-"))
        api.set_master_dir(str(other), False)
        r = api.set_mod_note(KEY, "stale", epoch)
        self.assertEqual((r["success"], r.get("stale")), (False, True))
        self.assertFalse((other / mod_notes.NOTES_FILENAME).exists())

    def test_notes_follow_a_mod_whose_folder_moves(self):
        api, root, epoch = make_api()
        api.set_mod_note("characters/Toad/Mod/Unit", "keep me", epoch)
        api._notes_rekey("characters/Toad/Mod", "characters/Wario/Mod")
        self.assertEqual(on_disk(root), {"characters/Wario/Mod/Unit": {"note": "keep me"}})

    def test_removing_a_mod_forgets_only_its_notes(self):
        api, root, epoch = make_api()
        api.set_mod_note("characters/Toad/Mod/Unit", "a", epoch)
        api.set_mod_note("characters/Toad/Mod2/Unit", "b", epoch)
        api._notes_clear_prefix("characters/Toad/Mod")
        self.assertEqual(list(on_disk(root)), ["characters/Toad/Mod2/Unit"])

    def test_an_unreadable_file_falls_back_to_the_backup(self):
        api, root, epoch = make_api()
        api.set_mod_note(KEY, "one", epoch)
        api.set_mod_note(KEY, "two", epoch)      # (the first is now the .bak)
        (root / mod_notes.NOTES_FILENAME).write_text("{oops")
        self.assertEqual(api.get_mods()["notes"][KEY], "one")

    def test_an_entry_left_over_from_the_flags_version_still_reads(self):
        api, root, epoch = make_api()
        (root / mod_notes.NOTES_FILENAME).write_text(json.dumps({
            "characters/A/B/C": {"note": "kept", "flags": ["favorite"]}, "characters/A/D/E": {"note": "", "flags": ["later"]}}))
        self.assertEqual(api.get_mods()["notes"], {"characters/A/B/C": "kept"})


if __name__ == "__main__":
    unittest.main()
