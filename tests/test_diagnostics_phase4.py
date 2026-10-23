"""The last diagnostics leftovers: what each mod contributed to a commit, a commit made stale by a mod changed in place, a voice rebuild that
can't lose the previous one, an icon cache that doesn't keep failures, and Pillow failing out loud.

Run from the repo root:  python -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402
import ui_setup  # noqa: E402
import voice_api  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def captured(fn, *args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def make_library(case, mods):
    """An Api over a temporary data folder holding `mods`: {key: {relative file: bytes}}, all selected."""
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-p4-"))
    case.addCleanup(shutil.rmtree, parent, True)
    master = parent / "data"
    master.mkdir()
    api = mm.Api(master)
    for key, files in mods.items():
        for rel, data in files.items():
            path = master / "mods" / "extracted" / Path(key) / "romfs" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    api._update_state(lambda state: state.update({key: True for key in mods}))
    return api


A, B, C = "characters/Mario/Mod A", "characters/Mario/Mod B", "characters/Mario/Mod C"


# ----------------------------------------------------------------------------------------------- per-mod counts
class WhatEachModContributed(unittest.TestCase):
    def test_the_log_says_how_many_files_each_mod_staged(self):
        api = make_library(self, {A: {"Model/a1.bfres": b"1", "Model/a2.bfres": b"2"}, B: {"Model/b1.bfres": b"3"}})
        lines = api.merge([A, B])["lines"]
        self.assertIn(f"  - {A}: 2 of 2 file(s) staged", lines)
        self.assertIn(f"  - {B}: 1 of 1 file(s) staged", lines)

    def test_files_left_out_and_files_lost_to_another_mod_are_counted(self):
        api = make_library(self, {A: {"Model/shared.bfres": b"from A", "Model/a.bfres": b"a"},
                                  B: {"Model/shared.bfres": b"from B", "Model/b.bfres": b"b", "Model/skip.bfres": b"s"}})
        api.exclude_files(B, ["Model/skip.bfres"])
        api._save_conflict_resolutions({"Model/shared.bfres": [A]})   # an earlier saved choice: A's version of that file wins
        lines = api.merge([A, B])["lines"]
        self.assertIn(f"  - {A}: 2 of 2 file(s) staged", lines)
        self.assertIn(f"  - {B}: 1 of 3 file(s) staged, 1 left out, 1 replaced by another mod's version or one of the app's own files", lines)

    def test_a_mod_that_adds_nothing_is_flagged_in_the_log_and_on_the_commit_page(self):
        api = make_library(self, {A: {"Model/a.bfres": b"a"}, C: {"Model/c.bfres": b"c"}})
        api.exclude_files(C, ["Model/c.bfres"])
        result = api.merge([A, C])
        self.assertIn(f"  - {C}: 0 of 1 file(s) staged, 1 left out  <-- NOTHING from this mod was staged", result["lines"])
        kinds = [w["kind"] for w in api.preview_commit([A, C])["warnings"]]
        self.assertIn("adds-nothing", kinds)

    def test_a_mod_that_adds_something_is_not_flagged(self):
        api = make_library(self, {A: {"Model/a.bfres": b"a"}})
        self.assertNotIn("adds-nothing", [w["kind"] for w in api.preview_commit([A])["warnings"]])


# ----------------------------------------------------------------------------------------------- stale when a mod changes in place
class StaleWhenAModChanges(unittest.TestCase):
    def setUp(self):
        self.api = make_library(self, {A: {"Model/a.bfres": b"version one"}})
        self.file = self.api.mod_root / "mods" / "extracted" / "characters" / "Mario" / "Mod A" / "romfs" / "Model" / "a.bfres"
        self.assertTrue(self.api.merge([A])["staged"])

    def stale(self):
        self.api._library.bump()    # (what the Refresh button does: don't wait for the few seconds a stamp is remembered)
        return self.api.get_flow_status()["commit"]["stale"], self.api.preview_commit([A])["already"]

    def test_nothing_changed_is_not_stale(self):
        self.assertEqual(self.stale(), (False, True))

    def test_a_file_replaced_in_place_makes_the_commit_stale(self):
        self.file.write_bytes(b"the author's version two, which is longer")
        self.assertEqual(self.stale(), (True, False))

    def test_a_new_file_in_the_mod_makes_it_stale(self):
        (self.file.parent / "new.bfres").write_bytes(b"x")
        self.assertEqual(self.stale(), (True, False))

    def test_committing_again_makes_it_current_again(self):
        self.file.write_bytes(b"changed and longer than before")
        self.assertEqual(self.stale(), (True, False))
        self.api.merge([A])
        self.assertEqual(self.stale(), (False, True))

    def test_a_commit_made_before_stamps_existed_is_not_called_stale(self):
        last = dict(self.api.get_settings()["last_commit"])
        last.pop("content")
        self.api.save_settings({"last_commit": last})
        self.file.write_bytes(b"changed and longer than before")
        self.assertEqual(self.stale(), (False, True))


# ----------------------------------------------------------------------------------------------- the voice rebuild can't lose the old one
class ReplaceDir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mk8dx-p4-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name, text in (("romfs", "old"), ("romfs.new", "new")):
            (self.dir / name).mkdir()
            (self.dir / name / "f.txt").write_text(text)

    def test_the_new_folder_takes_the_place_of_the_old_one_and_nothing_is_left_beside_it(self):
        voice_api._replace_dir(self.dir / "romfs.new", self.dir / "romfs", self.dir / "romfs.old")
        self.assertEqual((self.dir / "romfs" / "f.txt").read_text(), "new")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["romfs"])

    def test_a_swap_that_fails_puts_the_old_folder_back(self):
        real = os.replace
        calls = []

        def second_fails(src, dst):
            calls.append(src)
            if len(calls) == 2:
                raise PermissionError(5, "Access is denied")
            return real(src, dst)
        with mock.patch.object(os, "replace", second_fails):
            with self.assertRaises(PermissionError):
                voice_api._replace_dir(self.dir / "romfs.new", self.dir / "romfs", self.dir / "romfs.old")
        self.assertEqual((self.dir / "romfs" / "f.txt").read_text(), "old")

    def test_it_works_when_there_is_no_old_folder_yet(self):
        shutil.rmtree(self.dir / "romfs")
        voice_api._replace_dir(self.dir / "romfs.new", self.dir / "romfs", self.dir / "romfs.old")
        self.assertEqual((self.dir / "romfs" / "f.txt").read_text(), "new")


# ----------------------------------------------------------------------------------------------- the icon cache
class IconCache(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mk8dx-p4-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / "ui-setup-cache.json"

    def test_a_picture_that_could_not_be_made_is_not_remembered(self):
        cache = ui_setup.Cache(self.path)
        self.assertIsNone(cache.preview("abc", lambda: None))
        cache.preview("fine", lambda: b"x")   # (something worth saving, so the file is written)
        cache.save()
        self.assertEqual(list(json.loads(self.path.read_text(encoding="utf-8"))["previews"]), ["fine"])
        self.assertTrue(ui_setup.Cache(self.path).preview("abc", lambda: b"PNGDATA").startswith("data:image/png;base64,"))

    def test_a_failure_is_tried_once_per_run_not_over_and_over(self):
        cache = ui_setup.Cache(self.path)
        makes = []
        for _ in range(3):
            cache.preview("abc", lambda: makes.append(1))
        self.assertEqual(len(makes), 1)

    def test_an_entry_that_cannot_be_read_is_not_saved_and_is_tried_again_next_run(self):
        calls = []

        def broken(blob):
            calls.append(1)
            raise ui_setup.ua.ArchiveError("truncated")
        with mock.patch.object(ui_setup.ua, "entry_textures", broken):
            cache = ui_setup.Cache(self.path)
            _, log = captured(lambda: (cache.textures(b"entry"), cache.textures(b"entry")))
            cache.save()
            self.assertEqual(len(calls), 1)
            self.assertIn("couldn't be read", log)
            captured(ui_setup.Cache(self.path).textures, b"entry")
        self.assertEqual(len(calls), 2)

    def test_an_older_file_loses_its_empty_answers_and_keeps_the_rest(self):
        self.path.write_text(json.dumps({"summaries": {"good": [{"name": "t", "md5": "m", "w": 1, "h": 1, "fmt": 1}], "empty": []},
                                         "previews": {"p1": "QUJD", "p2": ""}}), encoding="utf-8")
        cache = ui_setup.Cache(self.path)
        self.assertEqual(list(cache.summaries), ["good"])
        self.assertEqual(list(cache.previews), ["p1"])
        cache.save()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["version"], ui_setup.Cache.VERSION)
        self.assertEqual(list(saved["summaries"]), ["good"])

    def test_a_current_file_is_kept_whole(self):
        self.path.write_text(json.dumps({"version": ui_setup.Cache.VERSION, "summaries": {"none": []}, "previews": {}}), encoding="utf-8")
        self.assertEqual(list(ui_setup.Cache(self.path).summaries), ["none"])   # (an entry that really has no textures is an answer)

    def test_saving_leaves_no_temporary_file(self):
        cache = ui_setup.Cache(self.path)
        cache.preview("abc", lambda: b"x")
        cache.save()
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["ui-setup-cache.json"])


# ----------------------------------------------------------------------------------------------- Pillow
class PillowMissing(unittest.TestCase):
    def test_each_module_says_so_when_pillow_cannot_be_loaded(self):
        for module in ("ui_archives", "bntx_decode", "cup_icons"):
            with self.subTest(module=module):
                code = f"import sys; sys.modules['PIL'] = None; sys.path.insert(0, r'{ROOT / 'src'}'); import {module}"
                done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn("Pillow couldn't be loaded", done.stderr)


if __name__ == "__main__":
    unittest.main()
