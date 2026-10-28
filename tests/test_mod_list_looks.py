"""A mod list carries each character's name and whether its icons were approved as the mods ship them (Api._mod_list_looks), and an
import gives those names and marks them approved, and marks the icons approved where the sharer did (Api.import_mod_list_looks) - so
the importer doesn't approve again what the sharer already looked at. Icons the sharer changed themselves are never marked, and an item
that also has mods of the importer's own is left alone.

Run from the repo root:  python -m unittest discover -s tests
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mod_list  # noqa: E402
import mod_manager as mm  # noqa: E402
import ui_setup  # noqa: E402

TOAD = "characters/Toad/Toadsworth"
MARIO = "characters/Mario/Gold Mario"
PEACH_OWN = "characters/Peach/My Own Peach"
PEACH = "characters/Peach/Pink Peach"


def make(test):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-looks-"))
    test.addCleanup(shutil.rmtree, parent, True)
    api = mm.Api(parent / "data")
    api.sync_auto_names = lambda *a, **k: []     # (no guesses: the names under test are set by hand)
    api.sync_voice_edits = lambda *a, **k: None
    return api, parent / "data"


def downloaded(api, master, mods):
    """`mods`: {key: (mod id, file id)} - each as a finished GameBanana download."""
    gb = {}
    for key, (mod_id, file_id) in mods.items():
        folder = master / "mods" / "extracted" / Path(*key.split("/"))
        (folder / "romfs").mkdir(parents=True, exist_ok=True)
        (folder / "romfs" / "x.bin").write_bytes(b"x")
        gb.setdefault(key.split("/")[1], []).append({
            "mod_id": mod_id, "record_type": "Mod", "name": key.split("/")[2], "author": "Someone", "profile_url": "",
            "files": [{"file_id": file_id, "name": "f.zip", "download_status": "downloaded", "downloaded_to": str(folder)}]})
    api._save_gb_mods(gb)


SHARED = {TOAD: (1, 11), MARIO: (2, 21), PEACH: (3, 31)}


def sharer(test):
    """Toad: a guessed name, icons approved as the mod ships them. Mario: a typed name, icons approved - but one is the sharer's own
    picture. Peach: approved, but one of her ticked mods was added by hand (not in the list)."""
    api, master = make(test)
    downloaded(api, master, SHARED)
    own = master / "mods" / "extracted" / Path(*PEACH_OWN.split("/")) / "romfs"
    own.mkdir(parents=True)
    api.save_checked({TOAD: True, MARIO: True, PEACH: True, PEACH_OWN: True})
    ov = ui_setup.load_overrides(master)
    ov["names"]["characters|Toad"] = {"text": "Toadsworth", "auto": True, "from": TOAD}
    ov["names"]["characters|Mario"] = {"text": "Golden Mario"}
    ov["textures"][ui_setup.slot_item("Chara", ui_setup.code_for_character("Mario"))] = {"png": "ui-overrides/a.png", "who": "Mario"}
    ui_setup.save_overrides(master, ov)
    for name in ("Toad", "Mario", "Peach"):
        api.mark_icons_reviewed(name)
    return api


def reviewed(api, bucket, item):
    keys = api._ticked_by_char().get(item)
    return bool(keys) and api._review_sig(keys) in api._review_data()[bucket].get(item, [])


def import_into(api, doc):
    for entry in mod_list.parse_mod_list(json.dumps(doc), api._mod_list_categories())[0]["mods"]:
        result = api.import_mod_list_item(entry)
        assert result["success"], result
    return api.import_mod_list_looks(doc["mods"], doc["looks"])


class Export(unittest.TestCase):
    def test_names_and_icons_approved_as_the_mods_ship_them_are_in_the_list(self):
        looks = {(lk["kind"], lk["item"]): lk for lk in sharer(self).build_mod_list()["list"]["looks"]}
        self.assertEqual(looks[("characters", "Toad")], {"kind": "characters", "item": "Toad", "name": "Toadsworth", "icons_confirmed": True})
        self.assertEqual(looks[("characters", "Mario")]["name"], "Golden Mario")
        self.assertFalse(looks[("characters", "Mario")]["icons_confirmed"])     # (the sharer's own picture: the importer won't have it)
        self.assertNotIn(("characters", "Peach"), looks)                        # (approved with a mod the list doesn't carry)


class Import(unittest.TestCase):
    def setUp(self):
        self.doc = sharer(self).build_mod_list()["list"]
        self.api, master = make(self)
        downloaded(self.api, master, SHARED)        # (already here: nothing is fetched from GameBanana)

    def test_names_come_in_approved_and_icons_approved_where_the_sharer_did(self):
        result = import_into(self.api, self.doc)
        self.assertEqual((result["names"], result["icons"]), (2, 1))
        names = ui_setup.load_overrides(self.api.mod_root)["names"]
        self.assertEqual(names["characters|Toad"]["text"], "Toadsworth")
        self.assertEqual(names["characters|Mario"]["text"], "Golden Mario")
        self.assertTrue(reviewed(self.api, "names", "Toad"))
        self.assertTrue(reviewed(self.api, "names", "Mario"))
        self.assertTrue(reviewed(self.api, "characters", "Toad"))
        self.assertFalse(reviewed(self.api, "characters", "Mario"))
        self.assertFalse(reviewed(self.api, "names", "Peach"))

    def test_a_character_with_mods_of_the_importers_own_is_left_to_them(self):
        own = self.api.mod_root / "mods" / "extracted" / "characters" / "Toad" / "Mine" / "romfs"
        own.mkdir(parents=True)
        self.api.save_checked({"characters/Toad/Mine": True})
        import_into(self.api, self.doc)
        self.assertFalse(reviewed(self.api, "names", "Toad"))
        self.assertFalse(reviewed(self.api, "characters", "Toad"))

    def test_looks_that_are_not_safe_are_dropped(self):
        looks = mod_list.clean_looks([{"kind": "characters", "item": "../x", "name": "A"}, {"kind": "bogus", "item": "Toad"},
                                      {"kind": "characters", "item": "Toad", "name": "x" * 41},
                                      {"kind": "characters", "item": "Toad", "name": "Ok", "icons_confirmed": "yes"}])
        self.assertEqual(looks, [{"kind": "characters", "item": "Toad", "name": "Ok", "icons_confirmed": False}])


SUNSHINE = "characters/Mario/Mario Sunshine"


def two_icon_versions(folder):
    """A mod that ships two versions of Mario's loose icon pictures: "^l" (red) and "^l1" (blue), as Windows numbers a second save."""
    from PIL import Image
    for suffix, colour in (("", (200, 0, 0, 255)), ("1", (0, 0, 200, 255))):
        for kind in ("Chara", "MapChara", "edChara"):
            Image.new("RGBA", (64, 64), colour).save(folder / f"tc_{kind}_Mario^l{suffix}.png")


class ChosenIconVersion(unittest.TestCase):
    """A mod with several versions of its own icon pictures: the one the sharer chose (and approved) comes along, and is chosen and
    approved on import too - the importer has the same files."""

    def sharer(self, remembered=True):
        api, master = make(self)
        downloaded(api, master, {SUNSHINE: (5, 51)})
        two_icon_versions(master / "mods" / "extracted" / "characters" / "Mario" / "Mario Sunshine")
        api.save_checked({SUNSHINE: True})
        sets = [s["suffix"] for s in api._loose_icon_sets(master / "mods" / "extracted" / "characters" / "Mario" / "Mario Sunshine", "Mario")]
        self.assertEqual(len(sets), 2, sets)
        self.assertTrue(api.use_loose_icon_set("Mario", "characters/Mario/Mario Sunshine", sets[1])["success"])
        if not remembered:   # (chosen before the app remembered which version: recognised by its pictures)
            ov = ui_setup.load_overrides(master)
            for entry in ov["textures"].values():
                entry.pop("set", None)
            ui_setup.save_overrides(master, ov)
        api.mark_icons_reviewed("Mario")
        return api, sets[1]

    def check_round_trip(self, remembered):
        sharer, chosen = self.sharer(remembered)
        doc = sharer.build_mod_list()["list"]
        look = next(lk for lk in doc["looks"] if lk["item"] == "Mario")
        self.assertTrue(look["icons_confirmed"])
        self.assertEqual(look["icon_set"], {"mod_id": 5, "record_type": "Mod", "set": chosen})
        api, master = make(self)
        downloaded(api, master, {SUNSHINE: (5, 51)})
        two_icon_versions(master / "mods" / "extracted" / "characters" / "Mario" / "Mario Sunshine")
        self.assertEqual(import_into(api, doc)["icons"], 1)
        self.assertTrue(reviewed(api, "characters", "Mario"))
        self.assertEqual(sorted(e["png"] for e in ui_setup.load_overrides(master)["textures"].values()),
                         sorted(e["png"] for e in ui_setup.load_overrides(sharer.mod_root)["textures"].values()))   # (the same pictures)

    def test_the_chosen_version_is_chosen_and_approved_on_import(self):
        self.check_round_trip(remembered=True)

    def test_a_version_chosen_before_it_was_remembered_is_recognised(self):
        self.check_round_trip(remembered=False)

    def test_pictures_of_the_importers_own_are_never_replaced(self):
        sharer, _chosen = self.sharer()
        doc = sharer.build_mod_list()["list"]
        api, master = make(self)
        downloaded(api, master, {SUNSHINE: (5, 51)})
        two_icon_versions(master / "mods" / "extracted" / "characters" / "Mario" / "Mario Sunshine")
        ov = ui_setup.load_overrides(master)
        mine = ui_setup.slot_item("Chara", "Mario")
        ov["textures"][mine] = {"png": "ui-overrides/mine.png", "who": "Mario"}
        ui_setup.save_overrides(master, ov)
        import_into(api, doc)
        self.assertEqual(ui_setup.load_overrides(master)["textures"][mine]["png"], "ui-overrides/mine.png")
        self.assertFalse(reviewed(api, "characters", "Mario"))


class ThePage(unittest.TestCase):
    def test_the_last_button_says_import(self):
        js = (ROOT / "src" / "ui" / "js" / "mod-list.js").read_text(encoding="utf-8")
        self.assertIn('{ label: "Import", variant: "primary"', js)
        self.assertNotIn("Download and select", js)

    def test_closing_the_import_goes_to_choose_mods_and_the_looks_are_applied(self):
        js = (ROOT / "src" / "ui" / "js" / "mod-list.js").read_text(encoding="utf-8")
        self.assertIn("pywebview.api.import_mod_list_looks(mods, read.looks", js)
        self.assertIn("onClose: () => { if (ran) showImportedMods(); }", js)
        finish = js[js.index("async function showImportedMods()"):]
        for needed in ("complete_setup()", "closeSetupWizard()", "closeSettingsModal()", 'goStep("mods"'):
            self.assertIn(needed, finish)


if __name__ == "__main__":
    unittest.main()
