"""The data folder: the app's recommended default (`data` next to the app), telling whether it is the one in use, and going back to it.

Run from the repo root:  python -m unittest discover -s tests

The app's own folder is replaced by a temporary one, so the real app-config.json is never touched.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402


class DataFolder(unittest.TestCase):
    def setUp(self):
        self.app_root = Path(tempfile.mkdtemp(prefix="mk8dx-approot-"))
        self.addCleanup(shutil.rmtree, self.app_root, True)
        self._real_root = mm.APP_ROOT
        mm.APP_ROOT = self.app_root
        self.addCleanup(setattr, mm, "APP_ROOT", self._real_root)
        self.default = self.app_root / "data"

    def api(self):
        return mm.Api(mm.load_master_dir_pointer() or mm.default_master_dir())

    # -- the recommended default ------------------------------------------------------------------------------------------
    def test_the_default_is_a_data_folder_next_to_the_app_and_is_created(self):
        self.assertEqual(mm.default_master_dir(), self.default)
        self.assertTrue(self.default.is_dir())

    def test_with_no_choice_made_the_default_is_the_one_in_use(self):
        status = self.api().get_master_dir_status()
        self.assertEqual((status["configured"], status["is_default"]), (True, True))
        self.assertEqual(Path(status["path"]), self.default)
        self.assertEqual(Path(status["default_path"]), self.default)

    def test_a_place_the_app_cannot_write_to_has_no_default(self):
        (self.app_root / "data").write_text("a file where the folder should be")
        self.assertIsNone(mm.default_master_dir())

    # -- choosing another folder, and coming back -------------------------------------------------------------------------
    def test_a_chosen_folder_is_not_the_default(self):
        other = self.app_root.parent / (self.app_root.name + "-other")
        self.addCleanup(shutil.rmtree, other, True)
        api = self.api()
        self.assertTrue(api.set_master_dir(str(other), False)["success"])
        status = api.get_master_dir_status()
        self.assertEqual((Path(status["path"]), status["is_default"]), (other, False))
        self.assertEqual(Path(json.loads((self.app_root / mm.APP_CONFIG_FILENAME).read_text())["master_dir"]), other)

    def test_going_back_to_the_recommended_folder(self):
        other = self.app_root.parent / (self.app_root.name + "-other")
        self.addCleanup(shutil.rmtree, other, True)
        api = self.api()
        api.set_master_dir(str(other), False)
        self.assertTrue(api.use_default_master_dir()["success"])
        status = api.get_master_dir_status()
        self.assertEqual((Path(status["path"]), status["is_default"]), (self.default, True))
        self.assertFalse((self.app_root / mm.APP_CONFIG_FILENAME).exists())   # (so moving the app folder takes its data with it)
        self.assertIsNone(mm.load_master_dir_pointer())

    def test_going_back_leaves_the_other_folders_files_alone(self):
        other = self.app_root.parent / (self.app_root.name + "-other")
        self.addCleanup(shutil.rmtree, other, True)
        api = self.api()
        api.set_master_dir(str(other), False)
        (other / "mod-notes.json").write_text("{}")
        api.use_default_master_dir()
        self.assertTrue((other / "mod-notes.json").is_file())

    def test_going_back_when_already_on_the_default_is_harmless(self):
        api = self.api()
        self.assertTrue(api.use_default_master_dir()["success"])
        self.assertTrue(api.get_master_dir_status()["is_default"])

    def test_going_back_says_so_when_the_app_has_no_writable_default(self):
        api = self.api()
        shutil.rmtree(self.default)
        self.default.write_text("a file where the folder should be")
        result = api.use_default_master_dir()
        self.assertFalse(result["success"])
        self.assertIn("recommended", result["error"])


if __name__ == "__main__":
    unittest.main()
