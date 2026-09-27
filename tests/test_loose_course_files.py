"""A course mod that ships only its loose files (a "Retextured" mod: course_model.szs and a README, no folders) is filed under the
course it was downloaded for: the course's own internal id (roster.json) names the Course/ folder - see fix_loose_course_files()."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

KNOWN = {"Gu_SnowMountain": "Mount Wario", "Cnsw_26": "Some Course"}


def make(files, sub=""):
    root = Path(tempfile.mkdtemp(prefix="mk8dx-course-"))
    base = root / sub if sub else root
    base.mkdir(parents=True, exist_ok=True)
    for f in files:
        (base / f).parent.mkdir(parents=True, exist_ok=True)
        (base / f).write_bytes(b"x")
    return root


def tree(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


class LooseCourseFiles(unittest.TestCase):
    def test_loose_files_go_into_the_courses_own_slot_and_the_readme_stays(self):
        root = make(["course_model.szs", "README.txt"])
        self.assertTrue(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN))
        self.assertEqual(tree(root), ["README.txt", "romfs/Course/Gu_SnowMountain/course_model.szs"])
        self.assertEqual(len(mm.find_mod_units(root)), 1)

    def test_a_wrapper_folder_named_for_the_mod_is_no_slot_name(self):
        root = make(["course_model.szs", "course_kcl.szs", "coin_muunt.byaml"], sub="Mount Wario Retextured")
        self.assertTrue(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN))
        self.assertEqual(tree(root), ["Mount Wario Retextured/romfs/Course/Gu_SnowMountain/" + n
                                      for n in ("coin_muunt.byaml", "course_kcl.szs", "course_model.szs")])

    def test_a_folder_already_named_for_a_game_course_is_left_to_the_slot_fixer(self):
        root = make(["course_model.szs"], sub="Cnsw_26")
        self.assertFalse(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN))
        self.assertTrue(mm.fix_bare_course_slot(root))
        self.assertIn("romfs/Course/Cnsw_26/course_model.szs", tree(root))

    def test_anything_unrecognised_leaves_the_folder_alone(self):
        for extra in ("cool_new_thing.dll", "Driver_Mario.bars", "BodyK_Cat.szs"):
            root = make(["course_model.szs", extra])
            self.assertFalse(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN), extra)
            self.assertEqual(tree(root), sorted(["course_model.szs", extra]))

    def test_no_course_file_means_nothing_to_do(self):
        root = make(["README.txt", "picture.png"])
        self.assertFalse(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN))

    def test_a_real_romfs_is_never_touched(self):
        root = make(["romfs/Course/Gu_SnowMountain/course_model.szs", "course_model.szs"])
        self.assertFalse(mm.fix_loose_course_files(root, "Gu_SnowMountain", KNOWN))

    def test_every_course_id_in_the_roster_is_a_plain_folder_name(self):
        roster = json.loads((Path(mm.__file__).parent / "roster.json").read_text())["courses"]
        single = [c for cup in roster for c in cup["courses"] if len(c.get("internal") or []) == 1]
        self.assertGreater(len(single), 90)              # (only Animal Crossing's four seasons can't be placed this way)
        for c in single:
            self.assertRegex(c["internal"][0], r"^[A-Za-z0-9_]+$", c["name"])


if __name__ == "__main__":
    unittest.main()
