"""Help no longer lists what the labels on a mod mean: each label explains itself where the app shows it.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def read(*parts):
    return (UI.joinpath(*parts)).read_text(encoding="utf-8")


class HelpPopup(unittest.TestCase):
    def test_the_labels_section_is_gone_and_the_others_are_still_there(self):
        modals = read("js", "app-modals.js")
        help_html = modals[modals.index("const helpModal = ui.modal({"):modals.index("const guessedNamesModal")]
        titles = re.findall(r'ui\.section\(\{\s*title: "([^"]*)"', help_html)
        # "Running in your browser" is only built when the app is serving this page to the user's own browser (how it
        # runs on Linux - docs/browser-mode.md); in a pywebview window it is not in the list at all.
        self.assertEqual(titles, ["Known issues", "Running in your browser", "More support", "About"])
        self.assertIn('window.pywebview.platform === "browser" ?', help_html)
        for gone in ("What the labels on a mod mean", "UI art only", "Needs romfs folder", "Needs manual fix", "Slot / music mismatch",
                     "Voice: mute a line", "Two mods clash", "If something goes wrong"):
            self.assertNotIn(gone, help_html)

    def test_nothing_in_the_app_sends_the_user_to_help_for_a_label(self):
        for name in ("character-card.js", "gamebanana.js", "add-mod.js", "flow.js"):
            self.assertNotIn("See Help", read("js", name), name)


class LabelsExplainThemselves(unittest.TestCase):
    def test_needs_manual_fix_has_a_note_like_the_other_two_states(self):
        js = read("js", "gamebanana.js")
        note = js[js.index('if (file.download_status === "needs_manual_fix") {'):js.index("row.appendChild(nameEl);", js.index('"needs_manual_fix") {'))]
        self.assertIn("couldn't tell what is in it", note)
        self.assertIn("gb-file-desc", note)
        for other in ('"ui_assets"', '"missing_romfs"'):
            self.assertIn(f'file.download_status === {other}', js)

    def test_the_code_patch_badge_says_select_all_skips_it(self):
        js = read("js", "character-card.js")
        self.assertIn("Select All skips code patches, so select each one yourself.", js)

    def test_the_packed_archive_badge_explains_itself(self):
        js = read("js", "character-card.js")
        badge = js[js.index('badge.textContent = "packed archive only";'):js.index("row.insertBefore(badge", js.index('"packed archive only"'))]
        self.assertIn("a commit never copies in directly", badge)
        self.assertNotIn("See Help", badge)


if __name__ == "__main__":
    unittest.main()
