"""What Setup's "Game files" step needs to know about the app's copy of the game's files: where it is, and whether the folder it
was made from is still there (so the app can say "feel free to delete your original game dump" and link to both).

Run from the repo root:  python -m unittest discover -s tests
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import game_files  # noqa: E402
import mod_manager as mm  # noqa: E402


class Status(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp(prefix="mk8dx-gf-"))
        self.addCleanup(shutil.rmtree, self.parent, True)
        self.master = self.parent / "data"
        self.api = mm.Api(self.master)

    def test_before_any_copy_it_says_where_the_copy_will_be_and_that_there_is_no_source(self):
        st = self.api.get_base_files_status()
        self.assertFalse(st["done"])
        self.assertEqual(st["copy_dir"], str(self.master / game_files.DIRNAME))
        self.assertFalse(st["source_exists"])

    def _write_manifest(self, source):
        folder = self.master / game_files.DIRNAME
        (folder / "current").mkdir(parents=True)
        (folder / game_files.MANIFEST_FILENAME).write_text(json.dumps({"source": str(source), "icons": []}), encoding="utf-8")

    def test_the_original_folder_counts_while_it_still_exists(self):
        dump = self.parent / "dump" / "romfs"
        dump.mkdir(parents=True)
        self._write_manifest(dump)
        self.assertTrue(self.api.get_base_files_status()["source_exists"])

    def test_the_original_folder_stops_counting_once_it_is_gone(self):
        self._write_manifest(self.parent / "deleted" / "romfs")
        self.assertFalse(self.api.get_base_files_status()["source_exists"])

    def test_a_path_from_another_computer_is_not_an_existing_source(self):
        self._write_manifest("/Users/someone/Downloads/dump/0100152000022000/romfs")
        self.assertFalse(self.api.get_base_files_status()["source_exists"])


if __name__ == "__main__":
    unittest.main()
