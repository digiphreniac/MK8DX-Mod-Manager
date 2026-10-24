"""Where a commit builds its files: inside the data folder by default (an older install keeps the folder it already has next to it), or
a folder the user chose in Settings. Nothing is chosen in Setup.

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

KEY = "characters/Mario/Plain Skin"


def make(test, files=2):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-staging-"))
    test.addCleanup(shutil.rmtree, parent, True)
    master = parent / "data"
    mod = master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
    mod.mkdir(parents=True)
    for i in range(files):
        (mod / f"part_{i}.bfres").write_bytes(b"x" * (i + 1))
    api = mm.Api(master)
    api._update_state(lambda state: state.update({KEY: True}))
    return api, parent, master


class TheDefault(unittest.TestCase):
    def test_a_new_install_stages_inside_the_data_folder(self):
        api, parent, master = make(self)
        status = api.get_staging_status()
        self.assertEqual(Path(status["path"]), master / "sd-card-staging")
        self.assertEqual((status["is_recommended"], status["label"]), (True, "Recommended"))
        result = api.merge([KEY])
        self.assertTrue(result["staged"])
        self.assertEqual(Path(result["staging_path"]), master / "sd-card-staging")
        self.assertTrue((master / "sd-card-staging" / "atmosphere" / "contents" / mm.TITLE_ID / "romfs" / "Model" / "part_0.bfres").is_file())
        self.assertFalse((parent / "sd-card-staging").exists())

    def test_an_install_that_already_has_one_next_to_the_data_folder_keeps_it(self):
        api, parent, master = make(self)
        (parent / "sd-card-staging").mkdir()
        status = api.get_staging_status()
        self.assertEqual(Path(status["path"]), parent / "sd-card-staging")
        self.assertEqual((status["is_recommended"], status["label"]), (False, "Existing folder"))       # (not called Recommended: the inside one is)
        self.assertEqual(Path(status["recommended_path"]), master / "sd-card-staging")
        api.merge([KEY])
        self.assertTrue((parent / "sd-card-staging" / "atmosphere").is_dir())
        self.assertFalse((master / "sd-card-staging").exists())

    def test_it_goes_along_when_the_data_folder_is_moved(self):
        self.assertIn("sd-card-staging", mm.MASTER_DIR_ITEMS)

    def test_setup_does_not_ask(self):
        registry = (ROOT / "src" / "ui" / "js" / "settings-registry.js").read_text(encoding="utf-8")
        entry = registry[registry.index('key: "staging_folder"'):]
        entry = entry[:entry.index("\n\n")]
        self.assertIn("showInSetup: false", entry)


class AChosenFolder(unittest.TestCase):
    def test_commits_go_there_and_the_last_commit_stops_counting(self):
        api, parent, master = make(self)
        api.merge([KEY])
        self.assertTrue(api.get_settings()["last_commit"])
        chosen = parent / "elsewhere" / "stage"
        self.assertEqual(api.set_staging_dir(str(chosen)), {"success": True, "error": None})
        self.assertFalse(api.get_settings()["last_commit"])       # (its files are not in the new place: commit again)
        status = api.get_staging_status()
        self.assertEqual((Path(status["path"]), status["is_recommended"], status["label"]), (chosen, False, "Custom folder"))
        api.merge([KEY])
        self.assertTrue((chosen / "atmosphere" / "contents" / mm.TITLE_ID / "romfs" / "Model" / "part_1.bfres").is_file())
        self.assertTrue((master / "sd-card-staging").is_dir())       # (the old one is left as it was)

    def test_going_back_to_the_recommended_folder(self):
        api, parent, master = make(self)
        api.set_staging_dir(str(parent / "stage"))
        self.assertTrue(api.use_recommended_staging_dir()["success"])
        status = api.get_staging_status()
        self.assertEqual((Path(status["path"]), status["is_recommended"], status["label"]), (master / "sd-card-staging", True, "Recommended"))

    def test_an_older_install_can_switch_to_the_one_inside_the_data_folder(self):
        api, parent, master = make(self)
        (parent / "sd-card-staging").mkdir()
        api.merge([KEY])
        self.assertTrue(api.get_settings()["last_commit"])
        self.assertTrue(api.use_recommended_staging_dir()["success"])
        status = api.get_staging_status()
        self.assertEqual((Path(status["path"]), status["is_recommended"]), (master / "sd-card-staging", True))      # (not the older one again)
        self.assertEqual(api.get_settings()["staging_folder"], "@data")
        self.assertFalse(api.get_settings()["last_commit"])       # (the files are not in the new place)
        self.assertTrue((parent / "sd-card-staging" / "atmosphere").is_dir())       # (the older one is left as it was)

    def test_the_inside_choice_follows_the_data_folder_instead_of_being_a_fixed_path(self):
        api, parent, master = make(self)
        api.use_recommended_staging_dir()
        moved = parent / "moved-data"
        api._configure_root(moved)
        self.assertEqual(api._staging_dir(), moved / "sd-card-staging")

    def test_choosing_the_recommended_folder_by_hand_is_the_same_choice(self):
        api, parent, master = make(self)
        self.assertTrue(api.set_staging_dir(str(master / "sd-card-staging"))["success"])
        self.assertTrue(api.get_staging_status()["is_recommended"])
        self.assertEqual(api.get_settings()["staging_folder"], "@data")

    def test_a_choice_that_changes_nothing_does_not_cancel_the_last_commit(self):
        api, parent, master = make(self)
        api.merge([KEY])
        api.use_recommended_staging_dir()       # (already there)
        self.assertTrue(api.get_settings()["last_commit"])

    def test_the_apps_own_folders_and_nothing_at_all_are_refused(self):
        api, parent, master = make(self)
        for bad in ("", "   ", str(master), str(master / "mods"), str(master / "mods" / "extracted" / "characters"), str(master / "ui-icons")):
            result = api.set_staging_dir(bad)
            self.assertFalse(result["success"], bad)
            self.assertTrue(result["error"], bad)
        self.assertTrue(api.get_staging_status()["is_recommended"])

    def test_a_folder_that_cannot_be_made_says_so(self):
        api, parent, master = make(self)
        blocker = parent / "a-file"
        blocker.write_text("x", encoding="utf-8")
        result = api.set_staging_dir(str(blocker / "inside"))
        self.assertFalse(result["success"])
        self.assertIn("Couldn't create or open that folder", result["error"])


class TheSettingsCard(unittest.TestCase):
    def test_the_card_is_a_setting_drawn_from_the_registry(self):
        html = (ROOT / "src" / "ui" / "html" / "settings-modal.html").read_text(encoding="utf-8")
        self.assertIn('data-settings-group="staging-folder"', html)
        self.assertIn('modal-card-title">Staging folder<', html)
        js = (ROOT / "src" / "ui" / "js" / "settings-registry.js").read_text(encoding="utf-8")
        self.assertIn('kind: "path"', js)
        self.assertIn("pywebview.api.set_staging_dir(path)", js)


if __name__ == "__main__":
    unittest.main()
