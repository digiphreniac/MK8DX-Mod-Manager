"""The ticked mods (mod-manager-state.json) must never be lost to a partial, empty, stale or torn write.

Run from the repo root with the project's Python (it needs pywebview installed, like the app):

    python -m unittest discover -s tests

Each test is one way the ticks were, or could have been, wiped - see safe_io.py and Api.save_checked().
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager  # noqa: E402
import safe_io      # noqa: E402

_real_app_root = mod_manager.APP_ROOT


def setUpModule():
    # Api.set_master_dir() writes <APP_ROOT>/app-config.json - the user's own pointer to their master folder. Never let a test
    # do that to the real one (it did once: the app then started at Setup again, pointing at a temp folder).
    mod_manager.APP_ROOT = Path(tempfile.mkdtemp(prefix="mk8dx-approot-"))


def tearDownModule():
    mod_manager.APP_ROOT = _real_app_root


TICKS = {f"characters/Char {i}/Mod {i}/Unit": True for i in range(150)}


def make_api(ticks=None):
    root = Path(tempfile.mkdtemp(prefix="mk8dx-ticks-"))
    if ticks is not None:
        (root / "mod-manager-state.json").write_text(json.dumps(ticks))
    api = mod_manager.Api(root)
    api.sync_auto_names = lambda *a, **k: []   # (naming from mods is not what is under test)
    api.sync_voice_edits = lambda *a, **k: None
    return api, root


def on_disk(root):
    return json.loads((root / "mod-manager-state.json").read_text(encoding="utf-8"))


class SaveChecked(unittest.TestCase):
    def test_an_empty_save_removes_nothing(self):
        api, root = make_api(TICKS)
        self.assertTrue(api.save_checked({}, api.get_mods()["epoch"]))
        self.assertEqual(on_disk(root), TICKS)

    def test_a_save_carrying_one_change_leaves_every_other_tick(self):
        api, root = make_api(TICKS)
        epoch = api.get_mods()["epoch"]
        api.save_checked({"characters/Toad/Red/Unit": True}, epoch)
        saved = on_disk(root)
        self.assertEqual(len(saved), len(TICKS) + 1)
        self.assertTrue(all(saved[k] for k in TICKS))

    def test_unticking_is_recorded_as_false_not_forgotten(self):
        api, root = make_api(TICKS)
        key = next(iter(TICKS))
        api.save_checked({key: False}, api.get_mods()["epoch"])
        self.assertIs(on_disk(root)[key], False)

    def test_a_page_from_another_master_folder_is_refused(self):
        api, root = make_api(TICKS)
        stale_epoch = api.get_mods()["epoch"]
        other = Path(tempfile.mkdtemp(prefix="mk8dx-other-"))
        api.set_master_dir(str(other), False)     # (the folder is switched under the page)
        self.assertIs(api.save_checked({"characters/A/B/C": True}, stale_epoch), False)
        self.assertFalse((other / "mod-manager-state.json").exists(), "the old page's tick reached the new folder")

    def test_every_load_of_a_folder_has_the_epoch_a_save_needs(self):
        api, root = make_api(TICKS)
        first = api.get_mods()["epoch"]
        self.assertEqual(first, api.get_mods()["epoch"])   # (stable while the folder stays the same)
        self.assertTrue(first)


class Files(unittest.TestCase):
    def test_no_reader_ever_sees_a_half_written_file(self):
        root = Path(tempfile.mkdtemp())
        path = root / "state.json"
        safe_io.write_json_atomic(path, TICKS)
        stop, bad = threading.Event(), []

        def reader():
            while not stop.is_set():
                try:
                    if len(safe_io.read_json_with_backup(path, None)) != len(TICKS):
                        bad.append("partial")
                except TypeError:   # (None: the file could not be read and there is no .bak)
                    bad.append("unreadable")
                time.sleep(0.001)   # (Windows can't replace a file while it is open: readers that never pause would starve the writer)

        readers = [threading.Thread(target=reader) for _ in range(4)]
        [t.start() for t in readers]
        for _ in range(1500):
            safe_io.write_json_atomic(path, TICKS)
        stop.set()
        [t.join() for t in readers]
        self.assertEqual(bad, [])

    def test_a_damaged_ticks_file_falls_back_to_the_previous_good_copy(self):
        api, root = make_api(TICKS)
        api.save_checked({"characters/Toad/Red/Unit": True}, api.get_mods()["epoch"])   # (writes .bak = the 150 before it)
        (root / "mod-manager-state.json").write_text("")                                 # (a crash mid-write on an older version)
        recovered = api._load_state()
        self.assertGreaterEqual(len(recovered), len(TICKS))

    def test_a_damaged_file_is_not_allowed_to_replace_the_good_backup(self):
        api, root = make_api(TICKS)
        api.save_checked({"characters/Toad/Red/Unit": True}, api.get_mods()["epoch"])
        (root / "mod-manager-state.json").write_text("{not json")
        api.save_checked({"characters/Toad/Blue/Unit": True}, api.get_mods()["epoch"])
        bak = json.loads((root / "mod-manager-state.json.bak").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(bak), len(TICKS))

    def test_removing_a_mod_clears_only_its_own_ticks(self):
        api, root = make_api(TICKS)
        api._clear_state_prefix("characters/Char 3/Mod 3")
        saved = on_disk(root)
        self.assertNotIn("characters/Char 3/Mod 3/Unit", saved)
        self.assertEqual(len(saved), len(TICKS) - 1)


if __name__ == "__main__":
    unittest.main()
