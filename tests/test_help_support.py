"""The Help pop-up's two sections - Known issues, and More support (join the Discord, show the log file) - and the button that shows the log.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def help_html():
    return (UI / "html" / "help-modal.html").read_text(encoding="utf-8")


class TheSupportSection(unittest.TestCase):
    def section(self):
        html = help_html()
        return html[html.index("More support"):]

    def test_it_says_to_ask_on_discord_and_that_the_log_file_will_be_asked_for(self):
        text = re.sub(r"<[^>]+>", "", self.section())
        self.assertIn("please join the Discord and ask for support there", text)
        self.assertIn("asked for your log file", text)
        self.assertIn("button below", text)

    def test_it_has_a_discord_button_with_the_discord_symbol_and_a_show_log_button(self):
        section = self.section()
        discord = section[section.index('id="btn-open-discord"'):section.index('id="btn-show-log"')]
        self.assertIn("<svg", discord)
        self.assertIn('fill="#5865F2"', discord)              # (the symbol in Discord's own colour, not recoloured to the page's)
        self.assertIn("Join the Discord", discord)
        self.assertIn("Show log file", section)

    def test_the_two_buttons_are_real_buttons_not_flat_text(self):
        # (button.ghost is transparent with no border - fine in a toolbar; outside .flow-body nothing gives it a border back, so it read as plain text)
        section = self.section()
        for button_id in ("btn-open-discord", "btn-show-log"):
            tag = section[section.rindex("<button", 0, section.index(f'id="{button_id}"')):section.index(">", section.index(f'id="{button_id}"'))]
            self.assertNotIn("ghost", tag, button_id)

    def test_the_old_buttons_and_text_are_gone(self):
        html = help_html()
        for gone in ("btn-copy-diagnostics", "Copy details", "Stuck, or want to talk"):
            self.assertNotIn(gone, html)
        js = (UI / "js" / "help-and-icon-generator.js").read_text(encoding="utf-8")
        self.assertNotIn("btn-copy-diagnostics", js)
        self.assertIn("openExternal(DISCORD_URL)", js)

    def test_known_issues_keeps_its_three_entries(self):
        html = help_html()
        issues = html[html.index("Known issues"):html.index("More support")]
        self.assertEqual(issues.count('class="help-status-term"'), 3)
        self.assertIn("slow motion on the Switch", issues)
        self.assertIn("comes from the track itself, not the app", issues)
        self.assertNotIn("mkwiiki", issues)                    # (that wiki is about Mario Kart Wii: its advice doesn't apply here)
        self.assertNotIn("Slow Motion Bug", issues)
        self.assertNotIn("physics are tied to the frame rate", issues)   # (not something we could confirm for this game)
        self.assertNotIn("clash", issues.lower())

    def test_the_three_known_issues_are_short_and_say_what_to_do(self):
        html = help_html()
        issues = html[html.index("Known issues"):html.index("More support")]
        entries = re.findall(r'<div class="help-status-term">(.*?)</div>\s*<div class="help-status-def">(.*?)</div>', issues, re.S)
        self.assertEqual([title for title, _ in entries], [
            "A modded course feels like it's playing in slow motion",
            "A character's icon or a course's name still looks like the original",
            "A mod I deselected still shows up in the game"])
        for title, text in entries:
            self.assertLess(len(re.sub(r"<[^>]+>", "", text)), 260, title)       # (a few lines, not a paragraph)
        self.assertIn("Commit again after changing your mods", entries[1][1])
        self.assertIn("atmosphere/contents/0100152000022000/romfs", entries[2][1])
        self.assertIn("then copy the staging folder again", entries[2][1])

    def test_the_page_never_points_to_a_button_that_is_gone(self):
        for path in (UI / "js").glob("*.js"):
            self.assertNotIn("Help > Copy details", path.read_text(encoding="utf-8"), path.name)


class ShowLogFile(unittest.TestCase):
    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-showlog-"))
        self.addCleanup(shutil.rmtree, parent, True)
        self.parent = parent
        self.api = mm.Api(parent)

    def test_from_source_there_is_no_log_and_it_says_so(self):
        with mock.patch.object(mm, "LOG_PATH", None):
            result = self.api.show_log_file()
        self.assertFalse(result["success"])
        self.assertIn("isn't writing a log file", result["error"])

    def test_it_opens_the_file_manager_with_the_log_selected(self):
        log = self.parent / "mod-manager.log"
        log.write_text("x", encoding="utf-8")
        with mock.patch.object(mm, "LOG_PATH", str(log)), mock.patch.object(mm, "show_in_file_manager") as show:
            result = self.api.show_log_file()
        self.assertTrue(result["success"])
        show.assert_called_once_with(log, select=True)

    def test_a_log_that_is_not_there_is_said_plainly_and_nothing_is_opened(self):
        with mock.patch.object(mm, "LOG_PATH", str(self.parent / "gone.log")), mock.patch.object(mm, "show_in_file_manager") as show:
            result = self.api.show_log_file()
        self.assertFalse(result["success"])
        self.assertIn("isn't there", result["error"])
        show.assert_not_called()

    def test_a_file_manager_that_cannot_start_is_an_error_not_a_crash(self):
        log = self.parent / "mod-manager.log"
        log.write_text("x", encoding="utf-8")
        with mock.patch.object(mm, "LOG_PATH", str(log)), mock.patch.object(mm, "show_in_file_manager", side_effect=OSError("no explorer")):
            result = self.api.show_log_file()
        self.assertFalse(result["success"])
        self.assertIn("no explorer", result["error"])


if __name__ == "__main__":
    unittest.main()
