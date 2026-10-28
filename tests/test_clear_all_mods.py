"""The "Clear All Mods" button must leave the app as if no mod had ever been added: no ticks, no records about mods, nothing built
from them, the step bar back at "Choose mods" - while settings, setup and the game's files stay. A ticked mod whose folder vanished
some other way is not counted by the step bar either.

    python -m unittest discover -s tests
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager  # noqa: E402

_real_app_root = mod_manager.APP_ROOT


def setUpModule():
    mod_manager.APP_ROOT = Path(tempfile.mkdtemp(prefix="mk8dx-approot-"))   # (never touch the real app-config.json)


def tearDownModule():
    mod_manager.APP_ROOT = _real_app_root


DOWNLOADED = ["characters/Mario/Gold Mario", "characters/Luigi/Blue Luigi"]
MANUAL = "characters/Peach/Hand Made"
ALL = DOWNLOADED + [MANUAL]

# Every record about mods the master folder can hold (each with a .bak where the app keeps one).
MOD_RECORDS = ["mod-manager-state.json", "mod-manager-state.json.bak", "gamebanana-mods.json", "gamebanana-mods.json.bak",
               "conflict-resolutions.json", "excluded-files.json", "excluded-files.json.bak", "mod-notes.json",
               "mod-notes.json.bak", "look-reviews.json", "voice-edits.json", "ui-overrides.json", "ui-setup-cache.json"]
MOD_FOLDERS = ["voice-custom/Mario", "ui-overrides", "part-icons", "course-icons", "ui-icons/romfs/UI", "ui-icons-backups"]
KEPT = ["game-files/current/marker", "image-cache/marker", "gamebanana-descriptions.json"]
STAGED = "sd-card-staging/atmosphere/contents/" + mod_manager.TITLE_ID + "/romfs/Driver/x.szs"
SIGPATCH = "sd-card-staging/atmosphere/exefs_patches/es_patches/a.ips"   # (not the app's: must stay)


def make_mod(root, key):
    folder = root / "mods" / "extracted" / key / "romfs" / "Model"
    folder.mkdir(parents=True)
    (folder / f"{key.split('/')[-1]}.bfres").write_bytes(b"x")
    return root / "mods" / "extracted" / key


def make_api():
    root = Path(tempfile.mkdtemp(prefix="mk8dx-clear-")) / "data"   # (its own parent: no older install's staging folder beside it)
    root.mkdir()
    gb = {}
    for key in DOWNLOADED:
        folder = make_mod(root, key)
        gb.setdefault(key.split("/")[1], []).append({"files": [{"downloaded_to": str(folder), "download_status": "downloaded"}]})
    make_mod(root, MANUAL)
    (root / "mods" / "downloads" / "characters").mkdir(parents=True)
    (root / "mods" / "downloads" / "characters" / "Gold Mario.zip").write_bytes(b"zip")
    for name in MOD_RECORDS + KEPT + [STAGED, SIGPATCH]:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("{}")
    for name in MOD_FOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "f.png").write_bytes(b"png")
    (root / "gamebanana-mods.json").write_text(json.dumps(gb))
    (root / "mod-manager-state.json").write_text(json.dumps({k: True for k in ALL}))
    (root / "app-settings.json").write_text(json.dumps({
        "setup_done": True, "ui_setup_locale": "EUfr", "show_nsfw": True,
        "last_commit": {"sig": "x", "at": "then", "mods": 3}, "last_ui_build": {"sig": "y"}, "switch_done": {"sig": "z"},
        "ui_setup_choices": {"Mario": "Gold Mario"}}))
    api = mod_manager.Api(root)
    api.sync_auto_names = lambda *a, **k: []
    api.sync_voice_edits = lambda *a, **k: None
    return api, root


def character_units(api):
    return sorted(u for entry in api.get_character_view()["roster"] for u in entry["units"])


class ClearAllMods(unittest.TestCase):
    def test_everything_about_mods_goes_and_settings_and_setup_stay(self):
        api, root = make_api()
        character_units(api)   # (warm the library cache, as the open page would have)
        result = api.clear_all_mods(True)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["deleted"], 3)
        self.assertEqual(list((root / "mods").iterdir()), [])
        for name in MOD_RECORDS + MOD_FOLDERS + [STAGED]:
            self.assertFalse((root / name).exists(), name)
        for name in KEPT + [SIGPATCH]:
            self.assertTrue((root / name).exists(), name)
        settings = api.get_settings()
        self.assertEqual((settings["setup_done"], settings["ui_setup_locale"], settings["show_nsfw"]), (True, "EUfr", True))
        self.assertEqual((settings["last_commit"], settings["last_ui_build"], settings["switch_done"]), (None, None, None))
        self.assertEqual(settings["ui_setup_choices"], {})
        self.assertEqual(api.get_mods()["checked"], {})
        self.assertEqual(character_units(api), [])   # (not a stale cached view that still lists the deleted mods)
        flow = api.get_flow_status()
        self.assertEqual(flow["mods"]["ticked"], 0)
        self.assertFalse(flow["commit"]["done"])

    def test_keeping_the_files_keeps_the_mods_but_none_ticked(self):
        api, root = make_api()
        api.clear_all_mods(False)
        self.assertEqual(character_units(api), sorted(ALL))
        self.assertEqual(api.get_mods()["checked"], {})
        self.assertFalse((root / "gamebanana-mods.json").exists())

    def test_a_chosen_staging_folder_loses_only_what_the_app_built(self):
        api, root = make_api()
        mine = Path(tempfile.mkdtemp(prefix="mk8dx-staging-"))
        (mine / "my-photos").mkdir()
        built = mine / "atmosphere" / "contents" / mod_manager.TITLE_ID / "romfs" / "x"
        built.parent.mkdir(parents=True)
        built.write_bytes(b"x")
        other_game = mine / "atmosphere" / "contents" / "0100000000000000" / "romfs"
        other_game.mkdir(parents=True)
        api.save_settings({"staging_folder": str(mine)})
        api.clear_all_mods(True)
        self.assertFalse((mine / "atmosphere" / "contents" / mod_manager.TITLE_ID).exists())
        self.assertTrue(other_game.is_dir())
        self.assertTrue((mine / "my-photos").is_dir())


class FlowCountsOnlyModsThatAreHere(unittest.TestCase):
    def test_ticked_mods_with_no_folder_are_not_offered_for_commit(self):
        api, root = make_api()
        for key in ALL:
            shutil.rmtree(root / "mods" / "extracted" / key)
        status = api.get_flow_status()
        self.assertEqual(status["mods"]["ticked"], 0)
        self.assertNotEqual(status["recommended"], "commit")
        self.assertEqual(len(api.get_mods()["checked"]), 3)   # (the ticks themselves are kept: the mods may come back)


if __name__ == "__main__":
    unittest.main()
