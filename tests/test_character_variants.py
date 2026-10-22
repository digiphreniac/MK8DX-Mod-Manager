"""Some select-screen tiles stand for two characters (Villager Boy / Girl, Inkling, Link and Link (Breath of the Wild), Metal Mario and
Gold Mario): each has its own model, voices and icons, so each is its own roster entry, and mods for one must not be pick-one with
mods for the other."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager  # noqa: E402
import ui_setup     # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"
BOTW = "Link (Breath of the Wild)"


def make_api():
    root = Path(tempfile.mkdtemp(prefix="mk8dx-link-"))
    for name, files in (("Classic only", ["Link.szs"]), ("BotW only", ["LinkBotw.szs"]), ("Both", ["Link.szs", "LinkBotw.szs"])):
        d = root / "mods" / "extracted" / "characters" / "Link" / name / "romfs" / "Driver"
        d.mkdir(parents=True)
        for f in files:
            (d / f).write_bytes(b"x")
    api = mod_manager.Api(root)
    api.sync_auto_names = lambda *a, **k: []
    return api, root


class LinkVariants(unittest.TestCase):
    def test_both_versions_are_roster_characters_with_their_own_slots(self):
        api, _ = make_api()
        roster = api._load_roster()
        self.assertIn("Link", roster)
        self.assertIn(BOTW, roster)
        self.assertEqual(api._voice_stems("Link"), ["Link"])
        self.assertEqual(api._voice_stems(BOTW), ["LinkBotw"])

    def test_a_mod_is_for_the_version_whose_files_it_replaces(self):
        api, _ = make_api()
        got = api.get_unit_slots(["characters/Link/Classic only", "characters/Link/BotW only", "characters/Link/Both"])
        self.assertEqual(got["characters/Link/Classic only"]["characters"], ["Link"])
        self.assertEqual(got["characters/Link/BotW only"]["characters"], [BOTW])
        self.assertEqual(got["characters/Link/Both"]["characters"], ["Link", BOTW])

    def test_a_mod_for_the_other_version_is_flagged_and_a_mod_for_both_is_a_pack(self):
        api, _ = make_api()
        got = api.get_unit_slots(["characters/Link/Classic only", "characters/Link/BotW only", "characters/Link/Both"])
        self.assertFalse(got["characters/Link/Classic only"]["mismatch"])
        self.assertTrue(got["characters/Link/BotW only"]["mismatch"])       # (filed under Link, replaces the other one)
        self.assertFalse(got["characters/Link/Both"]["mismatch"])
        packs = api.get_pack_links()
        self.assertEqual(packs["by_unit"]["characters/Link/Both"], ["Link", BOTW])
        self.assertNotIn("characters/Link/Classic only", packs["by_unit"])

    def test_they_share_one_name_entry(self):
        for name in ("Link", BOTW):
            found = ui_setup.find_name_labels({}, name, "characters")
            self.assertEqual((found["labels"], found["vanilla"]), (["1034"], "Link"))

    def test_metal_and_gold_mario_are_two_characters_with_their_own_slots_and_names(self):
        api, _ = make_api()
        roster = api._load_roster()
        self.assertIn("Metal Mario", roster)
        self.assertIn("Gold Mario", roster)
        self.assertEqual(api._voice_stems("Metal Mario"), ["MetalMario"])
        self.assertEqual(api._voice_stems("Gold Mario"), ["GoldMario"])
        self.assertEqual(ui_setup.find_name_labels({}, "Metal Mario", "characters")["labels"], ["1019"])
        self.assertEqual(ui_setup.find_name_labels({}, "Gold Mario", "characters")["labels"], ["1054"])   # (each has its own text)
        self.assertEqual(ui_setup.code_for_character("Gold Mario"), "GoldMario")

    def test_the_select_screen_has_one_metal_mario_tile_for_both(self):
        js = (SRC / "ui" / "js" / "state-and-helpers.js").read_text(encoding="utf-8")
        self.assertIn('{ group: "Metal Mario", options: ["Metal Mario", "Gold Mario"] }', js)

    def test_the_select_screen_has_one_link_tile_for_both(self):
        js = (SRC / "ui" / "js" / "state-and-helpers.js").read_text(encoding="utf-8")
        layout = js[js.index("const CHARACTER_GRID_LAYOUT"):js.index("];", js.index("const CHARACTER_GRID_LAYOUT"))]
        self.assertIn('{ group: "Link", options: ["Link", "Link (Breath of the Wild)"] }', layout)
        shown = set(re.findall(r'"([^"]+)"', layout)) - {"group", "options"}
        missing = [n for n in json.loads((SRC / "roster.json").read_text(encoding="utf-8"))["characters"] if n not in shown]
        self.assertEqual(missing, [], "characters the select-screen grid doesn't place")


if __name__ == "__main__":
    unittest.main()
