"""When no menu icons are built, the commit log and the Commit page say so (and why), instead of leaving a missing common.sarc /
menu.sarc to be guessed at.

Run from the repo root:  python -m unittest discover -s tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

KEY = "characters/Mario/Plain Skin"


class Describe(unittest.TestCase):
    def test_a_file_nothing_changes_is_reported_as_the_games_own(self):
        lines = mm.describe_ui_build([{"archive": "common", "nothing": True}, {"archive": "menu", "nothing": True}])
        self.assertEqual(len(lines), 2)
        self.assertIn("common.sarc: not made", lines[0])
        self.assertIn("the game's own is used", lines[0])

    def test_a_built_file_is_reported_as_built(self):
        lines = mm.describe_ui_build([{"archive": "common", "report": {}}, {"archive": "menu", "nothing": True}])
        self.assertEqual(lines[0], "  common.sarc: built.")
        self.assertIn("menu.sarc: not made", lines[1])

    def test_a_file_the_app_could_not_start_from_points_at_the_game_files_step(self):
        lines = mm.describe_ui_build([])
        self.assertTrue(all("Game files step" in line for line in lines))

    def test_a_failure_points_at_the_warning(self):
        lines = mm.describe_ui_build([{"archive": "common", "error": "boom"}, {"archive": "menu", "nothing": True}])
        self.assertIn("could not be made", lines[0])


class NothingToBuild(unittest.TestCase):
    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-uinotes-"))
        self.addCleanup(shutil.rmtree, parent, True)
        self.master = parent / "data"
        self.api = mm.Api(self.master)
        mod = self.master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
        mod.mkdir(parents=True)
        (mod / "Mario.bfres").write_bytes(b"x")

    def kinds(self):
        return [w["kind"] for w in self.api.preview_commit([KEY])["warnings"]]

    def test_the_commit_page_says_no_menu_icons_will_change(self):
        self.assertIn("no-menu-icons", self.kinds())

    def test_the_card_is_not_shown_for_a_selection_without_characters(self):
        course = self.master / "mods" / "extracted" / "courses" / "Some Cup" / "Some Course" / "romfs" / "Course"
        course.mkdir(parents=True)
        (course / "course_model.szs").write_bytes(b"x")
        warnings = self.api.preview_commit(["courses/Some Cup/Some Course"])["warnings"]
        self.assertNotIn("no-menu-icons", [w["kind"] for w in warnings])

    def test_the_commit_log_says_nothing_was_built_and_why(self):
        self.api._update_state(lambda state: state.update({KEY: True}))
        log = "\n".join(self.api.merge([KEY])["lines"])
        self.assertIn("Menu icons & text: nothing to build", log)
        self.assertIn("no common.sarc or menu.sarc is made", log)


if __name__ == "__main__":
    unittest.main()
