"""Game versions and build ids: the known-version table, and matching a patch's build id on its first 16 hex characters.

Run from the repo root:  python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

FULL_303 = "6A85262F21B903649BD7C62628D26E43"   # a 32-hex build id, as a patch's file name has it


class Matching(unittest.TestCase):
    def test_a_short_and_a_full_id_are_the_same_build(self):
        self.assertTrue(mm.build_in("6a85262f21b90364", [FULL_303]))
        self.assertTrue(mm.build_in(FULL_303, ["6A85262F21B90364"]))
        self.assertTrue(mm.build_in(" " + FULL_303.lower() + " ", [FULL_303]))

    def test_another_build_does_not_match(self):
        self.assertFalse(mm.build_in("9EF5CAA2D5B933C7", [FULL_303]))
        self.assertFalse(mm.build_in("", [FULL_303]))

    def test_a_patch_for_several_builds_matches_if_any_does(self):
        self.assertTrue(mm.build_in("9EF5CAA2D5B933C7", [FULL_303, "9EF5CAA2D5B933C7AAAAAAAAAAAAAAAA"]))

    def test_known_versions_are_found_from_a_full_id(self):
        self.assertEqual(mm.KNOWN_BUILD_IDS.get(mm.build_key(FULL_303)), "3.0.3")
        self.assertIn("v3.0.3", mm.Api._build_id_label(FULL_303))


class VersionList(unittest.TestCase):
    def setUp(self):
        self.api = mm.Api(Path(tempfile.mkdtemp(prefix="mk8dx-ids-")))

    def test_every_version_is_listed_once_newest_first(self):
        versions = [v["version"] for v in self.api.get_game_versions()]
        self.assertEqual(len(versions), len(set(versions)))
        self.assertEqual(versions, sorted(versions, key=lambda v: [int(x) for x in v.split(".")], reverse=True))
        self.assertIn("3.0.3", versions)
        self.assertIn("4.0.0", versions)

    def test_choosing_a_version_sets_the_build_id_it_matches_on(self):
        for entry in self.api.get_game_versions():
            self.assertEqual(len(entry["build_id"]), mm.BUILD_ID_LEN)
            result = self.api.set_game_version(entry["version"])
            self.assertEqual(result["game_build_id"], entry["build_id"])
        self.assertEqual(self.api.set_game_version("")["game_build_id"], "")


if __name__ == "__main__":
    unittest.main()
