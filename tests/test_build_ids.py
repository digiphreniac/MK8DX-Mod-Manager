"""Game versions and build ids: the known-version table, and matching a patch's build id on its first 16 hex characters.

Run from the repo root:  python -m unittest discover -s tests
"""
import shutil
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


class PatchFit(unittest.TestCase):
    def test_a_patch_for_another_build_is_wrong_once_your_build_is_known(self):
        self.assertEqual(mm.patch_fit("9EF5CAA2D5B933C7", "3.0.1", [FULL_303]), "wrong")
        self.assertIsNone(mm.patch_fit("6A85262F21B90364", "3.0.3", [FULL_303]))

    def test_not_listed_flags_patches_made_for_a_listed_build_as_maybe(self):
        self.assertEqual(mm.patch_fit("", mm.NEWER_VERSION, [FULL_303]), "maybe")

    def test_not_listed_says_nothing_about_a_patch_for_an_unlisted_build(self):
        self.assertIsNone(mm.patch_fit("", mm.NEWER_VERSION, ["0123456789ABCDEF0123456789ABCDEF"]))
        self.assertIsNone(mm.patch_fit("", mm.NEWER_VERSION, [FULL_303, "0123456789ABCDEF0123456789ABCDEF"]))

    def test_not_sure_checks_nothing(self):
        self.assertIsNone(mm.patch_fit("", "", [FULL_303]))
        self.assertIsNone(mm.patch_fit("", mm.NEWER_VERSION, []))

    def test_a_build_id_beats_not_listed(self):
        self.assertIsNone(mm.patch_fit("6A85262F21B90364", mm.NEWER_VERSION, [FULL_303]))
        self.assertEqual(mm.patch_fit("9EF5CAA2D5B933C7", mm.NEWER_VERSION, [FULL_303]), "wrong")


class WhatTheUserSees(unittest.TestCase):
    """A real patch unit (a minimal valid .ips) with each choice of game version: the mod's badge, the Commit page, the commit log."""
    KEY = "characters/Mario/Speed Patch"

    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-fit-"))   # (the commit stages next to the master folder: keep that inside here)
        self.addCleanup(shutil.rmtree, parent, True)
        unit = parent / "data" / "mods" / "extracted" / "characters" / "Mario" / "Speed Patch"
        unit.mkdir(parents=True)
        ips = b"PATCH" + (0x100).to_bytes(3, "big") + (2).to_bytes(2, "big") + b"\x01\x02" + b"EOF"
        (unit / (FULL_303.lower() + ".ips")).write_bytes(ips)
        self.api = mm.Api(parent / "data")

    def look(self, version):
        self.api.set_game_version(version)
        info = self.api.get_exefs_unit_info([self.KEY])[self.KEY]
        kinds = [w["kind"] for w in self.api.preview_commit([self.KEY])["warnings"]]
        log = "\n".join(self.api.merge([self.KEY])["lines"])
        return info, kinds, log

    def test_not_listed_gets_the_soft_warning(self):
        info, kinds, log = self.look(mm.NEWER_VERSION)
        self.assertEqual((info["inert"], info["maybe"]), (False, True))
        self.assertIn("exefs-version-maybe", kinds)
        self.assertNotIn("exefs-version-unknown", kinds)
        self.assertIn("might not work", log)
        self.assertNotIn("WARNING", log)

    def test_a_different_known_version_gets_the_hard_warning(self):
        info, kinds, log = self.look("3.0.1")
        self.assertEqual((info["inert"], info["maybe"]), (True, False))
        self.assertIn("exefs-version", kinds)
        self.assertNotIn("exefs-version-maybe", kinds)
        self.assertIn("will do nothing", log)

    def test_the_matching_version_gets_none(self):
        info, kinds, log = self.look("3.0.3")
        self.assertEqual((info["inert"], info["maybe"]), (False, False))
        self.assertFalse({"exefs-version", "exefs-version-maybe", "exefs-version-unknown"} & set(kinds))
        self.assertNotIn("WARNING", log)
        self.assertNotIn("might not work", log)

    def test_not_sure_only_suggests_setting_the_version(self):
        info, kinds, log = self.look("")
        self.assertEqual((info["inert"], info["maybe"]), (False, False))
        self.assertIn("exefs-version-unknown", kinds)
        self.assertNotIn("exefs-version-maybe", kinds)


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

    def test_not_listed_is_remembered_with_no_build_id(self):
        self.assertEqual(self.api.set_game_version(mm.NEWER_VERSION), {"game_version": "newer", "game_build_id": ""})
        self.assertEqual(self.api.get_settings()["game_version"], "newer")


if __name__ == "__main__":
    unittest.main()
