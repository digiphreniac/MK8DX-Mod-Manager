"""While a commit runs the page shows how far it is: merge() keeps a small record that get_commit_progress() hands out.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mod_manager as mm  # noqa: E402

KEY = "characters/Mario/Plain Skin"


def make_api(test, files=3):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-progress-"))
    test.addCleanup(shutil.rmtree, parent, True)
    master = parent / "data"
    mod = master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
    mod.mkdir(parents=True)
    for i in range(files):
        (mod / f"part_{i}.bfres").write_bytes(b"x" * (i + 1))
    api = mm.Api(master)
    api._update_state(lambda state: state.update({KEY: True}))
    return api


def recording(api):
    """Every look at the progress that a phase change or a tick makes, in order (a snapshot taken right after each one)."""
    seen = []
    for name in ("_progress_phase", "_progress_tick"):
        original = getattr(api, name)

        def wrapper(*args, _original=original, **kwargs):
            _original(*args, **kwargs)
            seen.append(api.get_commit_progress())
        setattr(api, name, wrapper)
    return seen


class TheRecord(unittest.TestCase):
    def test_nothing_is_running_until_a_commit_starts_and_after_it_ends(self):
        api = make_api(self)
        self.assertEqual(api.get_commit_progress(), {"active": False})
        api.merge([KEY])
        self.assertEqual(api.get_commit_progress(), {"active": False})

    def test_a_commit_goes_through_its_phases_in_order_and_counts_the_files(self):
        api = make_api(self, files=25)
        seen = recording(api)
        self.assertTrue(api.merge([KEY])["staged"])
        order = ["prepare", "claims", "copy", "finish"]
        phases = [s["phase"] for s in seen]
        self.assertEqual(sorted(set(phases), key=order.index), order[1:])       # (it is already in "prepare" when the first change is made)
        self.assertEqual(phases, sorted(phases, key=order.index))               # (never back to an earlier one)
        self.assertEqual([p["id"] for p in seen[0]["phases"]], order)           # (no menu build: no such phase)
        copies = [s for s in seen if s["phase"] == "copy" and s["total"]]
        self.assertEqual((copies[-1]["done"], copies[-1]["total"]), (25, 25))
        self.assertEqual([s["done"] for s in copies], sorted(s["done"] for s in copies))
        self.assertTrue(all(s["elapsed"] >= 0 for s in seen))

    def test_the_mods_checked_are_counted_too(self):
        api = make_api(self)
        calls = []
        api._compute_claims([KEY], progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls, [(0, 1)])

    def test_a_commit_that_stops_early_or_fails_leaves_no_record_behind(self):
        api = make_api(self)
        api.merge([])
        self.assertFalse(api.get_commit_progress()["active"])
        with mock.patch.object(mm.shutil, "copy2", side_effect=OSError("disk full")):
            self.assertFalse(api.merge([KEY])["staged"])
        self.assertFalse(api.get_commit_progress()["active"])

    def test_a_menu_build_adds_its_phase_before_the_file_check(self):
        api = make_api(self)
        with mock.patch.object(api, "_ui_build_needed", return_value=True), \
                mock.patch.object(api, "_build_ui_archives", return_value={"success": True, "results": []}):
            seen = recording(api)
            api.merge([KEY])
        self.assertEqual([p["id"] for p in seen[0]["phases"]], ["prepare", "icons", "claims", "copy", "finish"])
        self.assertEqual(seen[0]["phase"], "icons")

    def test_the_menu_build_counts_steps_from_the_start_and_only_ever_forwards(self):
        # (a bar that slid while the count was unknown and then started over from empty looked like it had jumped back)
        api = make_api(self)
        plan = {"common": {"base": 0}, "menu": {"base": 0}, "message:USen": {"base": 0}}
        with mock.patch.object(api, "_ui_build_needed", return_value=True),                 mock.patch.object(api, "_ui_setup_plan", return_value=plan),                 mock.patch.object(mm.ui_setup, "_winners", return_value={}),                 mock.patch.object(mm.ui_setup, "dropped_changes", return_value=[]):
            seen = recording(api)
            api.merge([KEY])
        icons = [s for s in seen if s["phase"] == "icons"]
        self.assertTrue(icons and all(s["total"] for s in icons), "the menu build was ever without a total")
        self.assertEqual((icons[0]["done"], icons[0]["total"]), (0, 4))                       # (reading the mods' files, then three archives)
        self.assertEqual((icons[-1]["done"], icons[-1]["total"]), (4, 4))
        self.assertEqual([s["done"] for s in icons], sorted(s["done"] for s in icons))
        self.assertGreaterEqual(min(s["done"] / s["total"] for s in icons[1:]), icons[0]["done"] / icons[0]["total"])

    def test_the_copy_phase_knows_its_total_before_it_clears_the_old_copy(self):
        api = make_api(self, files=5)
        seen = recording(api)
        api.merge([KEY])
        copies = [s for s in seen if s["phase"] == "copy"]
        self.assertTrue(all(s["total"] == 5 for s in copies))
        self.assertEqual(copies[0]["detail"], "Clearing the previous copy")

    def test_ticks_from_somewhere_else_are_ignored(self):
        api = make_api(self)
        api._progress_tick("icons", 1, 3, "x")       # (no commit is running: Settings' own build calls the same code)
        self.assertFalse(api.get_commit_progress()["active"])
        api._progress_begin(["prepare", "copy"])
        api._progress_tick("copy", 5, 9)              # (not in that phase yet)
        self.assertEqual(api.get_commit_progress()["done"], 0)


class AskingDoesNotWaitForTheCommit(unittest.TestCase):
    def test_the_page_can_ask_while_a_file_is_being_copied(self):
        api = make_api(self)
        inside, release = threading.Event(), threading.Event()
        real = shutil.copy2

        def slow_copy(src, dest, *a, **k):
            inside.set()
            release.wait(10)
            return real(src, dest, *a, **k)

        result = {}
        with mock.patch.object(mm.shutil, "copy2", slow_copy):
            worker = threading.Thread(target=lambda: result.update(api.merge([KEY])), daemon=True)
            worker.start()
            self.assertTrue(inside.wait(10))
            asked = {}
            ask = threading.Thread(target=lambda: asked.update(api.get_commit_progress()), daemon=True)
            ask.start()
            ask.join(3)
            self.assertFalse(ask.is_alive(), "the answer waited for the commit")
            release.set()
            worker.join(10)
        self.assertEqual((asked["active"], asked["phase"]), (True, "copy"))
        self.assertTrue(result["staged"])


class ThePage(unittest.TestCase):
    def test_the_page_shows_the_phases_and_stops_asking_when_the_commit_ends(self):
        flow = (ROOT / "src" / "ui" / "js" / "flow.js").read_text(encoding="utf-8")
        do_commit = flow[flow.index("async function doCommit()"):]
        do_commit = do_commit[:do_commit.index("\n}\n")]
        self.assertLess(do_commit.index("startCommitProgress()"), do_commit.index("pywebview.api.merge("))
        self.assertLess(do_commit.index("pywebview.api.merge("), do_commit.index("stopCommitProgress()"))
        self.assertIn("get_commit_progress()", flow)
        self.assertIn("if (mine < shown || !commitPage.busy) return;", flow)      # (a late answer must not move the bars back)
        self.assertIn("if (commitPage.busy) {", flow)               # (the panel is part of the page while busy, so a redraw keeps it)
        self.assertIn("ui.progress({", flow)                          # (the bars are a component; the page only asks and passes the answer on)
        css = (ROOT / "src" / "ui" / "css" / "components" / "progress.css").read_text(encoding="utf-8")
        unknown = css[css.index(".ui-progress-phase--unknown .ui-progress-bar::after {"):]
        self.assertNotIn(".ui-progress-fill", unknown[:unknown.index("}")])      # (the sliding block is not the fill: the fill never shrinks back from it)
        for rule in (".ui-progress-phase--done .ui-progress-fill", ".ui-progress-phase--unknown .ui-progress-bar::after", ".ui-progress-detail"):
            self.assertIn(rule, css)

    def test_every_phase_the_backend_names_has_a_label(self):
        source = (ROOT / "src" / "mod_manager.py").read_text(encoding="utf-8")
        used = set(re.findall(r'_progress_(?:phase|tick)\("(\w+)"', source)) | {"prepare"}
        self.assertEqual(used, set(mm.Api._COMMIT_PHASES))


if __name__ == "__main__":
    unittest.main()
