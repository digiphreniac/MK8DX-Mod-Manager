"""The game's files are chosen in one place: the Game files step of Setup (which the step bar reopens any time). Settings no longer has a card for it,
and nothing sends the user to one.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class SettingsHasNoGameFilesCard(unittest.TestCase):
    def test_the_card_and_its_filling_are_gone(self):
        html = read("src", "ui", "js", "app-modals.js")
        for gone in ("gamefiles-card", "gamefiles-body", "Your game's files", "Your game&#39;s files"):
            self.assertNotIn(gone, html)
        self.assertNotIn("gamefiles-body", read("src", "ui", "js", "views.js"))

    def test_nothing_in_the_app_points_at_a_settings_section_that_is_gone(self):
        for path in list((ROOT / "src").glob("*.py")) + list(UI.rglob("*.js")) + list(UI.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Settings > Your game", text, path.name)
            self.assertNotIn("Your game's files (for menu icons", text, path.name)

    def test_the_messages_that_used_to_point_there_now_point_at_setup(self):
        voice = read("src", "voice_api.py")
        self.assertEqual(voice.count("check the Game files step is done"), 2)
        self.assertIn("the Game files step of Setup", voice)


class SetupStillDoesIt(unittest.TestCase):
    def test_the_setup_step_has_the_block_and_the_update_button(self):
        wizard = read("src", "ui", "js", "setup-wizard.js")
        self.assertIn("await renderGameFilesBlock(block, refresh);", wizard)
        self.assertIn("gameDataInstructions()", wizard)
        text = read("src", "ui", "js", "menu-icons-text.js")
        self.assertIn("Update from a new dump...", text)
        self.assertIn("Choose the folder...", text)

    def test_the_shared_block_no_longer_has_a_settings_only_mode(self):
        text = read("src", "ui", "js", "menu-icons-text.js")
        block = text[text.index("async function renderGameFilesBlock("):]
        signature = block[:block.index("{")]
        self.assertNotIn("compact", signature)
        self.assertNotIn("compact", block[:block.index("\n}\n")])
        self.assertNotIn("Where do I get these?", block[:block.index("\n}\n")])     # (the Setup step shows the guide itself)

    def test_every_caller_passes_what_the_block_takes(self):
        for path in UI.rglob("*.js"):
            for call in re.findall(r"renderGameFilesBlock\(([^;]*)\);", path.read_text(encoding="utf-8")):
                if "container" in call:       # (its own recursive refresh)
                    continue
                self.assertEqual(len([a for a in call.split(",") if a.strip()]), 2, f"{path.name}: {call}")

    def test_the_voice_editor_keeps_its_own_way_to_choose_the_files(self):
        self.assertIn("Choose game files folder", read("src", "ui", "js", "voice.js"))
        self.assertIn("async function chooseGameFiles(", read("src", "ui", "js", "menu-icons-text.js"))


if __name__ == "__main__":
    unittest.main()
