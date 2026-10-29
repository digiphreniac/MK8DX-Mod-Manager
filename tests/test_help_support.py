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
    """The Help window's spec (js/app-modals.js): its sections as the source writes them."""
    js = (UI / "js" / "app-modals.js").read_text(encoding="utf-8")
    return js[js.index("const helpModal = ui.modal({"):js.index("const guessedNamesModal")]


def help_section(title):
    """One section of it, up to wherever the next one starts - so a new section in between cannot quietly be read as
    part of this one (the browser-mode section sits between "Known issues" and "More support")."""
    html = help_html()
    start = html.index(f'title: "{title}"')
    # The next top-level entry of the sections list - another ui.section(...), the "..." of a conditional one, or the
    # comment above either (everything inside a section body is indented deeper than these four spaces).
    nxt = re.search(r"\n    (?://|\.\.\.\(|ui\.section\(\{)", html[start:])
    return html[start:start + nxt.start()] if nxt else html[start:]


class TheSupportSection(unittest.TestCase):
    def section(self):
        return help_section("More support")

    def test_it_says_to_ask_on_discord_and_that_the_log_file_will_be_asked_for(self):
        text = self.section()
        self.assertIn("please join the Discord and ask for support there", text)
        self.assertIn("asked for your log file", text)
        self.assertIn("button below", text)

    def test_it_has_a_discord_button_with_the_discord_logo_and_a_show_log_button(self):
        section = self.section()
        discord = section[section.index('id: "btn-open-discord"'):section.index('id: "btn-show-log"')]
        # (Discord's own file, unmodified, beside a link to the app's server - as Discord's brand guidelines allow; see ui.logo())
        self.assertIn('icon: ui.logo("discord"', discord)
        self.assertNotIn("<svg", discord)
        self.assertNotIn("5865F2", discord)                  # (the logo's colour is in its file, never copied into the page)
        self.assertIn("Join the Discord", discord)
        self.assertIn("Show log file", section)

    def test_the_two_buttons_are_real_buttons_not_flat_text(self):
        # (button.ghost is transparent with no border - fine in a toolbar; outside .flow-body nothing gives it a border back, so it read as plain text)
        section = self.section()
        for button_id in ("btn-open-discord", "btn-show-log"):
            at = section.index(f'id: "{button_id}"')
            spec = section[section.rindex("ui.button({", 0, at):section.index("}).el", at)]
            self.assertNotIn("ghost", spec, button_id)

    def test_the_old_buttons_and_text_are_gone(self):
        html = help_html()
        for gone in ("btn-copy-diagnostics", "Copy details", "Stuck, or want to talk"):
            self.assertNotIn(gone, html)
        js = (UI / "js" / "help-and-icon-generator.js").read_text(encoding="utf-8")
        self.assertNotIn("btn-copy-diagnostics", js)
        self.assertIn("openExternal(DISCORD_URL)", js)

    def test_known_issues_keeps_its_three_entries(self):
        issues = help_section("Known issues")
        self.assertEqual(issues.count('class: "help-status-term"'), 3)
        self.assertIn("slow motion on the Switch", issues)
        self.assertIn("comes from the track itself, not the app", issues)
        self.assertNotIn("mkwiiki", issues)                    # (that wiki is about Mario Kart Wii: its advice doesn't apply here)
        self.assertNotIn("Slow Motion Bug", issues)
        self.assertNotIn("physics are tied to the frame rate", issues)   # (not something we could confirm for this game)
        self.assertNotIn("clash", issues.lower())

    def test_the_three_known_issues_are_short_and_say_what_to_do(self):
        issues = help_section("Known issues")
        titles = re.findall(r'class: "help-status-term", text: "((?:[^"\\]|\\.)*)"', issues)
        self.assertEqual(titles, [
            "A modded course feels like it's playing in slow motion",
            "A character's icon or a course's name still looks like the original",
            "A mod I deselected still shows up in the game"])
        answers = re.split(r'ui\.el\("div", (?:\{ class: "help-status-term"|"help-status-term")', issues)[1:]
        self.assertEqual(len(answers), 3)
        for title, text in zip(titles, answers):
            self.assertLess(len(text), 480, title)             # (a few lines, not a paragraph)
        self.assertIn("Commit again after changing your mods", answers[1])
        self.assertIn("atmosphere/contents/0100152000022000/romfs", answers[2])
        self.assertIn("then copy the staging folder again", answers[2])

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
