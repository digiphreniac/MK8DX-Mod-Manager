"""The notes on the Commit page: the ones that ask for something first and open, the rest behind "Notes (N)", short words, and the notes only
the log needs kept off the page.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mod_manager as mm  # noqa: E402

KEY = "characters/Mario/Plain Skin"


def make(test, with_bgm=False):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-notes-"))
    test.addCleanup(shutil.rmtree, parent, True)
    master = parent / "data"
    romfs = master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs"
    (romfs / "Model").mkdir(parents=True)
    (romfs / "Model" / "Mario.bfres").write_bytes(b"x")
    if with_bgm:
        (romfs / "Audio" / "Static").mkdir(parents=True)
        (romfs / "Audio" / "Static" / "BGM.bars").write_bytes(b"x")
    api = mm.Api(master)
    api._update_state(lambda state: state.update({KEY: True}))
    return api


class WhatTheBackendSays(unittest.TestCase):
    def test_a_note_only_the_log_needs_is_marked_and_still_in_the_log(self):
        api = make(self, with_bgm=True)
        warnings = api.preview_commit([KEY])["warnings"]
        bgm = [w for w in warnings if w["kind"] == "bgm-bars"]
        self.assertEqual(len(bgm), 1)
        self.assertTrue(bgm[0]["log_only"])
        lines = api.merge([KEY])["lines"]
        self.assertTrue(any("bundle the shared music file" in line and "(not shown on the page)" in line for line in lines))

    def test_a_note_that_asks_for_something_is_not_log_only(self):
        api = make(self)
        warnings = api.preview_commit([KEY, "characters/Mario/Gone/Mod"])["warnings"]
        missing = [w for w in warnings if w["kind"] == "missing"][0]
        self.assertFalse(missing.get("log_only"))
        self.assertEqual(missing["title"], "1 selected mod is missing from your computer")
        self.assertEqual(missing["detail"], "They're not in this commit. Deselect them or download them again.")

    def test_the_stale_sentence_about_the_built_files_in_settings_is_gone(self):
        source = (ROOT / "src" / "mod_manager.py").read_text(encoding="utf-8")
        self.assertNotIn("the built files themselves", source)
        self.assertIn("The language it's built for is in Settings.", source)

    def test_every_note_is_a_title_and_a_single_sentence(self):
        source = (ROOT / "src" / "mod_manager.py").read_text(encoding="utf-8")
        summary = source[source.index("def _commit_summary("):source.index("def preview_commit(")]
        for detail in re.findall(r'"detail": f?"((?:[^"\\]|\\.)*)"', summary):
            text = re.sub(r"\{[^}]*\}", "x", detail)
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
            self.assertLessEqual(len(sentences), 2, detail)       # (no more than two short sentences, never a paragraph)
            self.assertLessEqual(len(text), 150, detail)


class WhatThePageShows(unittest.TestCase):
    def test_two_groups_the_first_open_and_the_second_behind_one_line(self):
        flow = (ROOT / "src" / "ui" / "js" / "flow.js").read_text(encoding="utf-8")
        draw = flow[flow.index("function drawCommitPage()"):]
        draw = draw[:draw.index("\n}\n")]
        self.assertIn("filter(w => !w.log_only)", draw)
        self.assertIn('w.severity !== "info"', draw)
        self.assertIn('"Needs your attention"', draw)
        self.assertIn("`Notes (${notes.length})`", draw)
        self.assertIn('document.createElement("details")', draw)
        self.assertNotIn("Good to know", flow)
        self.assertIn("thing${attention.length === 1", draw)       # (the Committed card says how many things to check)

    def test_a_note_has_an_icon_and_an_action_button_and_its_mods_are_behind_a_disclosure(self):
        flow = (ROOT / "src" / "ui" / "js" / "flow.js").read_text(encoding="utf-8")
        card = flow[flow.index("function pgWarnEl(w)"):flow.index("function drawCommitPage()")]
        self.assertIn("PG_WARN_ICON[w.severity]", card)
        icons = flow[flow.index("const PG_WARN_ICON = {"):flow.index("const PG_WARN_WORD")]
        self.assertNotIn("<svg", icons)                                 # (the pictures live in the icon registry, once)
        self.assertNotIn("u2610", icons)                                # (pictures, not text characters: they look the same on any computer)
        registry = (ROOT / "src" / "ui" / "js" / "ui" / "icons.js").read_text(encoding="utf-8")
        for name in ("warning", "todo", "info"):
            self.assertIn(f'"{name}"', icons)
            self.assertIn(f"  {name}: '<", registry)
        self.assertIn("pg-sr", card)                                    # (read out as well, for someone who can't see the colour)
        self.assertIn('"Review names"', card)
        self.assertIn('"Open Settings"', card)
        self.assertIn('`Show the ${names.length === 1 ? noun : names.length + " " + noun + "s"}`', card)
        self.assertNotIn(".slice(0, 6)", card)                          # (no more "and 55 more")

    def test_the_styles(self):
        css = (ROOT / "src" / "ui" / "css" / "flow.css").read_text(encoding="utf-8")
        for rule in (".pg-warn.warn {", ".pg-warn.todo {", ".pg-warn-text {", ".pg-list-body {", ".pg-notes[open] > .pg-notes-body"):
            self.assertIn(rule, css)
        self.assertRegex(css, r"\.pg-list-body \{[^}]*max-height: \d+px; overflow-y: auto")
        self.assertRegex(css, r"\.pg-warn \{[^}]*border-left: 4px solid")


if __name__ == "__main__":
    unittest.main()
