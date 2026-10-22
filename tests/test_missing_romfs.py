"""A course mod zipped without its romfs/ (Course/, Audio/ and UI/cmn/ side by side) is wrapped, and the UI/cmn/Menu folder inside it
is the game's own loose menu textures - not a raw UI-archive dump (which is what "ui_assets" means)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402


def make(files):
    root = Path(tempfile.mkdtemp(prefix="mk8dx-romfs-"))
    for f in files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_bytes(b"x")
    return root


def tree(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


MUSHROOM = ["Course/G64_KinopioHighway/course_model.szs", "Audio/Static/BGM.bars",
            "Audio/Resource/Stream/pBGM_N64_KINOPIO_HIGHWAY_F.bfstm", "UI/cmn/Menu/ym_CoursePict_G64_KinopioHighway_00^u.bntx"]


class MissingRomfs(unittest.TestCase):
    def test_course_audio_and_ui_are_wrapped_together(self):
        root = make(MUSHROOM)
        self.assertFalse(mm.looks_like_ui_assets(root))          # (UI/cmn/Menu is the game's own place for loose menu textures)
        self.assertTrue(mm.looks_like_missing_romfs_wrapper(root))
        self.assertTrue(mm.fix_missing_romfs_wrapper(root))
        self.assertEqual(tree(root), sorted("romfs/" + f for f in MUSHROOM))
        self.assertEqual(len(mm.find_mod_units(root)), 1)

    def test_a_ui_folder_alone_is_not_taken_for_a_mods_romfs_content(self):
        root = make(["UI/cmn/Menu/x.bntx"])
        self.assertFalse(mm.looks_like_missing_romfs_wrapper(root))
        root = make(["Course/G/course_model.szs", "UI/notes/readme.txt"])     # (a UI folder without the game's cmn/)
        self.assertFalse(mm.looks_like_missing_romfs_wrapper(root))

    def test_a_raw_menu_dump_is_still_a_ui_dump(self):
        self.assertTrue(mm.looks_like_ui_assets(make(["menu/tc_KP_B_Std_Kno^l.bntx"])))
        self.assertTrue(mm.looks_like_ui_assets(make(["Some mod/common/x.bntx"])))


if __name__ == "__main__":
    unittest.main()
