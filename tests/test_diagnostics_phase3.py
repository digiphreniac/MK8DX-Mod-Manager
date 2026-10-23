"""Phase 3 of the diagnostics work: changing the data folder brings every file along (and puts everything back if it can't), the app can
check its own pieces without a window (`--self-check`), and the page shows a message where a failure used to leave it stuck.

Run from the repo root:  python -m unittest discover -s tests
"""
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import game_files  # noqa: E402
import gamebanana_api  # noqa: E402
import mod_manager as mm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"


def captured(fn, *args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


class MoveDataFolder(unittest.TestCase):
    ITEMS = ["game-files/current/UI/cmn/common.sarc", "voice-edits.json", "voice-custom/Mario/line.wav", "look-reviews.json",
             "mod-manager-state.json", "mod-manager-state.json.bak", "app-settings.json", "app-settings.json.bak",
             "mods/extracted/characters/Mario/Plain/romfs/a.bin"]

    def setUp(self):
        self.parent = Path(tempfile.mkdtemp(prefix="mk8dx-move-"))
        self.addCleanup(shutil.rmtree, self.parent, True)
        self.app_root = self.parent / "app"
        self.app_root.mkdir()
        real = mm.APP_ROOT
        mm.APP_ROOT = self.app_root
        self.addCleanup(setattr, mm, "APP_ROOT", real)
        self.old = self.parent / "old"
        self.old.mkdir()
        self.api = mm.Api(self.old)
        for rel in self.ITEMS:
            path = self.old / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rel, encoding="utf-8")
        self.new = self.parent / "new"

    def test_everything_the_app_keeps_is_brought_along(self):
        result, _ = captured(self.api.set_master_dir, str(self.new), True)
        self.assertTrue(result["success"], result)
        for rel in self.ITEMS:
            self.assertTrue((self.new / rel).is_file(), f"{rel} was left behind")
            self.assertFalse((self.old / rel).exists(), f"{rel} is in both folders")
        self.assertEqual(mm.load_master_dir_pointer(), self.new)

    def test_the_wizard_does_not_come_back_after_a_move(self):
        make = self.old / "game-files"
        self.assertTrue(make.is_dir())
        captured(self.api.set_master_dir, str(self.new), True)
        self.assertTrue((self.new / game_files.DIRNAME / "current" / "UI" / "cmn" / "common.sarc").is_file())

    def test_a_move_that_fails_puts_back_what_it_moved(self):
        real_move = shutil.move
        calls = []

        def flaky(src, dst, *args, **kwargs):
            calls.append(src)
            if len(calls) == 4 and "rollback" not in str(dst):
                raise OSError(5, "Access is denied", src)
            return real_move(src, dst, *args, **kwargs)
        with mock.patch.object(shutil, "move", flaky):
            result, log = captured(self.api.set_master_dir, str(self.new), True)
        self.assertFalse(result["success"])
        self.assertIn("put back", result["error"])
        for rel in self.ITEMS:
            self.assertTrue((self.old / rel).is_file(), f"{rel} is not back")
            self.assertFalse((self.new / rel).exists(), f"{rel} was left in the new folder")
        self.assertIsNone(mm.load_master_dir_pointer())   # (the app still points at the old folder)
        self.assertIn("data-folder: moving", log)

    def test_the_list_covers_what_the_app_writes_beside_its_mods(self):
        for name in (game_files.DIRNAME, "voice-edits.json", "voice-custom", "look-reviews.json", "app-settings.json.bak",
                     "mod-manager-state.json.bak", "gamebanana-mods.json.bak", "mod-notes.json.bak"):
            self.assertIn(name, mm.MASTER_DIR_ITEMS)


class SelfCheck(unittest.TestCase):
    def test_it_passes_when_everything_is_there(self):
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(gamebanana_api, "find_7zip", return_value="7z.exe"), mock.patch.object(mm.subprocess, "run", return_value=done):
            failed, log = captured(mm.self_check)
        self.assertEqual(failed, 0, log)
        self.assertIn("all checks passed", log)

    def test_a_missing_7zip_is_the_one_failure(self):
        with mock.patch.object(gamebanana_api, "find_7zip", return_value=None):
            failed, log = captured(mm.self_check)
        self.assertEqual(failed, 1, log)
        self.assertIn("FAILED 7-Zip", log)

    def test_a_missing_data_file_is_found(self):
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(gamebanana_api, "find_7zip", return_value="7z.exe"), mock.patch.object(mm.subprocess, "run", return_value=done), \
                mock.patch.object(mm, "SCRIPT_DIR", Path(tempfile.gettempdir()) / "no-such-app-folder"):
            failed, log = captured(mm.self_check)
        self.assertGreaterEqual(failed, 3, log)
        self.assertIn("FAILED roster.json", log)
        self.assertIn("FAILED page files", log)

    def test_it_touches_none_of_the_users_data(self):
        before = sorted(p.name for p in mm.APP_ROOT.iterdir())
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(gamebanana_api, "find_7zip", return_value="7z.exe"), mock.patch.object(mm.subprocess, "run", return_value=done):
            captured(mm.self_check)
        self.assertEqual(sorted(p.name for p in mm.APP_ROOT.iterdir()), before)


class Workflows(unittest.TestCase):
    def test_the_release_workflow_runs_the_packaged_apps_self_check(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("--self-check", text)
        self.assertLess(text.index("--self-check"), text.index("name: Keep the package with this run"))

    def test_the_tests_run_on_pull_requests(self):
        text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request", text)
        self.assertIn("unittest discover -s tests", text)


class PageShowsFailures(unittest.TestCase):
    def read(self, rel):
        return (UI / "js" / rel).read_text(encoding="utf-8")

    def test_starting_the_app_can_fail_visibly_and_be_tried_again(self):
        main = self.read("main.js")
        self.assertIn("diag.banner(\"startup\"", main)
        self.assertIn("loadMods().catch", main)

    def test_a_download_that_throws_re_enables_the_page(self):
        self.assertIn("diag.attempt(() => pywebview.api.gb_download_files", self.read("gamebanana.js"))
        self.assertEqual(self.read("add-mod.js").count("diag.attempt(() => pywebview.api.gb_"), 4)

    def test_the_commit_page_does_not_wait_for_ever(self):
        self.assertIn("Couldn't check your mods", self.read("flow.js"))

    def test_a_lost_selection_is_shown(self):
        self.assertIn("diag.banner(\"tick-save\"", self.read("state-and-helpers.js"))

    def test_the_banner_has_a_style(self):
        self.assertIn(".diag-banner", (UI / "css" / "layout.css").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
