"""A mod that ships a packed UI archive UNPACKED - a folder named UI/cmn/common.sarc/ holding loose pictures - must not put a
directory where the game expects the archive file (the game aborts before the title screen). The folder is skipped like the archive,
a file/folder clash between two claims is refused before anything is copied, and the staged folder is checked after the copy.

Run from the repo root:  python -m unittest discover -s tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mod_manager as mm  # noqa: E402

SKYPE = "characters/Diddy Kong/Skype"
PLAIN = "characters/Mario/Plain Skin"


def make_mod(master, key, files):
    category, item, name = key.split("/")
    romfs = master / "mods" / "extracted" / category / item / name / "romfs"
    for f in files:
        (romfs / f).parent.mkdir(parents=True, exist_ok=True)
        (romfs / f).write_bytes(f.encode())


def make(test, mods):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-looseSarc-"))
    test.addCleanup(shutil.rmtree, parent, True)
    master = parent / "data"
    for key, files in mods.items():
        make_mod(master, key, files)
    return mm.Api(master), master


def staged(master):
    root = master / "sd-card-staging"
    found = sorted(root.rglob("romfs")) if root.exists() else []
    return found[0] if found else None


SKYPE_FILES = ["Model/Diddy.bfres", "UI/cmn/common.sarc/Bg_Diddy.bntx", "UI/cmn/common.sarc/Icon_Diddy.bntx",
               "UI/cmn/menu.sarc/Menu_Diddy.bntx", "UI/cmn/Menu/ym_Loose.bntx"]


class TheHelper(unittest.TestCase):
    def test_a_folder_named_like_an_archive_is_one_with_its_contents(self):
        root = mm._packed_ui_archive_root
        self.assertEqual(root(Path("UI/cmn/common.sarc")), Path("UI/cmn/common.sarc"))
        self.assertEqual(root(Path("UI/cmn/common.sarc/Bg.bntx")), Path("UI/cmn/common.sarc"))
        self.assertEqual(root(Path("ui/CMN/Menu.SARC/a/b.bntx")), Path("ui/CMN/Menu.SARC"))
        self.assertIsNone(root(Path("UI/cmn/Menu/ym_x.bntx")))
        self.assertIsNone(root(Path("Model/common.sarc")))             # (only under UI/)
        self.assertIsNone(root(Path("UI")))
        self.assertTrue(mm._is_packed_ui_archive(Path("UI/cmn/menu.sarc/x.bntx")))


class TheClaims(unittest.TestCase):
    def test_the_contents_of_an_archive_folder_are_not_claimed(self):
        api, master = make(self, {SKYPE: SKYPE_FILES})
        res = api._compute_claims([SKYPE])
        self.assertEqual(sorted(res.claims), ["model/diddy.bfres", "ui/cmn/menu/ym_loose.bntx"])
        # one entry per folder, not one per picture in it
        self.assertEqual(sorted(rel for _k, rel in res.ui_archives_skipped),
                         ["UI/cmn/common.sarc/ (a folder, not an archive)", "UI/cmn/menu.sarc/ (a folder, not an archive)"])

    def test_a_real_archive_is_still_listed_once_by_its_own_name(self):
        api, master = make(self, {PLAIN: ["Model/Mario.bfres", "UI/cmn/common.sarc"]})
        res = api._compute_claims([PLAIN])
        self.assertEqual(res.ui_archives_skipped, [(PLAIN, "UI/cmn/common.sarc")])
        self.assertEqual(sorted(res.claims), ["model/mario.bfres"])


class TheCommit(unittest.TestCase):
    def test_a_commit_with_the_skype_shape_stages_no_folder_named_like_an_archive(self):
        api, master = make(self, {SKYPE: SKYPE_FILES, PLAIN: ["Model/Mario.bfres"]})
        result = api.merge([SKYPE, PLAIN])
        self.assertTrue(result["staged"], "\n".join(result["lines"]))
        out = staged(master)
        self.assertIsNotNone(out)
        self.assertEqual(sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()),
                         ["Model/Diddy.bfres", "Model/Mario.bfres", "UI/cmn/Menu/ym_Loose.bntx"])
        self.assertEqual([p for p in out.rglob("*") if p.is_dir() and p.name.lower().endswith(".sarc")], [])

    def test_the_commit_page_says_which_mods_ship_loose_folders(self):
        api, master = make(self, {SKYPE: SKYPE_FILES, PLAIN: ["Model/Mario.bfres"]})
        notes = [w for w in api.preview_commit([SKYPE, PLAIN])["warnings"] if w["kind"] == "unpacked-archive-folders"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["mods"], [SKYPE])
        self.assertEqual(notes[0]["severity"], "warn")

    def test_a_file_and_a_folder_in_one_place_are_refused_before_anything_is_copied(self):
        a, b = "characters/Mario/Wants A File", "characters/Luigi/Wants A Folder"
        api, master = make(self, {a: ["Model/thing"], b: ["Model/thing/inner.bin"]})
        first = api.merge([a])                                          # (a good commit first: it must survive the refused one)
        self.assertTrue(first["staged"])
        before = sorted(p.relative_to(master).as_posix() for p in (master / "sd-card-staging").rglob("*"))
        result = api.merge([a, b])
        self.assertFalse(result["staged"])
        self.assertFalse(result["conflict"])
        text = "\n".join(result["lines"])
        self.assertIn("Model/thing", text)
        self.assertIn("Model/thing/inner.bin", text)
        self.assertEqual(before, sorted(p.relative_to(master).as_posix() for p in (master / "sd-card-staging").rglob("*")))

    def test_a_staged_folder_that_does_not_match_is_caught_and_the_last_commit_forgotten(self):
        api, master = make(self, {PLAIN: ["Model/Mario.bfres"]})
        real_copy = shutil.copy2

        def bad_copy(src, dest, *a, **kw):
            Path(dest).mkdir(parents=True, exist_ok=True)             # a directory where the file should be
            return None

        shutil.copy2 = bad_copy
        try:
            result = api.merge([PLAIN])
        finally:
            shutil.copy2 = real_copy
        self.assertFalse(result["staged"])
        self.assertIn("doesn't match", "\n".join(result["lines"]))
        self.assertIsNone(api._load_settings().get("last_commit"))

    def test_the_checker_names_each_kind_of_difference(self):
        out = Path(tempfile.mkdtemp(prefix="mk8dx-verify-"))
        self.addCleanup(shutil.rmtree, out, True)
        src = out / "src.bin"
        src.write_bytes(b"abcd")
        (out / "r" / "UI" / "cmn" / "x.sarc").mkdir(parents=True)
        (out / "r" / "wrongsize").write_bytes(b"ab")
        (out / "r" / "stray").write_bytes(b"1")
        claims = {"missing": {"rel": Path("missing"), "src": src}, "wrongsize": {"rel": Path("wrongsize"), "src": src}}
        problems = "\n".join(mm.Api._verify_staged(out / "r", claims))
        for expected in ("missing: not a file", "wrongsize: the copy is a different size", "UI/cmn/x.sarc: a folder where the game expects",
                         "stray: staged but not from any selected mod"):
            self.assertIn(expected, problems)


if __name__ == "__main__":
    unittest.main()
