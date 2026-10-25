"""Sharing the list of mods: Export writes the ticked GameBanana mods, Import downloads and ticks them (src/mod_list.py and the Api's
build_mod_list / export_mod_list / read_mod_list / import_mod_list_item). The GameBanana calls are replaced by stand-ins that build the
same folders and records the real download does.

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

CATS = {"characters", "courses", "items", "vehicles", "wheels", "gliders"}
DAISY = "characters/Baby Daisy/Mr. AR"
BIRDO = "characters/Birdo/Wii Remotes/pack/Colorful 4.0.0"
HAND = "characters/Mario/Made By Hand"


def make(test):
    parent = Path(tempfile.mkdtemp(prefix="mk8dx-modlist-"))
    test.addCleanup(shutil.rmtree, parent, True)
    return mm.Api(parent / "data"), parent / "data"


def extracted(master, key):
    folder = master / "mods" / "extracted" / Path(*key.split("/"))
    (folder / "romfs").mkdir(parents=True, exist_ok=True)
    (folder / "romfs" / "x.bin").write_bytes(b"x")
    return folder


def record(mod_id, name, files, record_type="Mod"):
    return {"mod_id": mod_id, "record_type": record_type, "name": name, "author": "Someone", "profile_url": f"https://gamebanana.com/mods/{mod_id}",
            "files": files}


def file_entry(file_id, folder, status="downloaded"):
    return {"file_id": file_id, "name": f"f{file_id}.zip", "download_status": status, "downloaded_to": str(folder) if folder else None}


def setup_library(test):
    """Two GameBanana mods (one whose mod folder holds an inner folder), one mod added by hand, all three ticked, one file left out."""
    api, master = make(test)
    daisy = extracted(master, DAISY)
    birdo_folder = master / "mods" / "extracted" / "characters" / "Birdo" / "Wii Remotes"
    extracted(master, BIRDO)
    extracted(master, HAND)
    api._save_gb_mods({
        "Baby Daisy": [record(682993, "Mr. AR", [file_entry(11, daisy)])],
        "Birdo": [record(644576, "Wii Remotes", [file_entry(21, birdo_folder), file_entry(22, None, "not_downloaded")])],
    })
    api.save_checked({DAISY: True, BIRDO: True, HAND: True, "characters/Mario/Not Ticked": False})
    api.exclude_files(DAISY, ["Model/Baby.bfres"], reason="manual")
    return api, master


class Export(unittest.TestCase):
    def test_ticked_gamebanana_mods_are_listed_with_their_ids_files_and_folders(self):
        api, master = setup_library(self)
        doc = api.build_mod_list()["list"]
        self.assertEqual((doc["format"], doc["version"]), (mod_list.FORMAT, mod_list.VERSION))
        by_id = {m["mod_id"]: m for m in doc["mods"]}
        self.assertEqual(sorted(by_id), [644576, 682993])
        daisy = by_id[682993]
        self.assertEqual((daisy["item"], daisy["category"], daisy["url"]), ("Baby Daisy", "characters", "https://gamebanana.com/mods/682993"))
        self.assertEqual([f["file_id"] for f in daisy["files"]], [11])
        self.assertEqual(daisy["units"], [{"file_id": 11, "sub": "", "left_out": [{"path": "Model/Baby.bfres", "reason": "manual", "kept_from": None}]}])
        birdo = by_id[644576]
        self.assertEqual([(u["file_id"], u["sub"]) for u in birdo["units"]], [(21, "pack/Colorful 4.0.0")])     # (the folder inside the mod)

    def test_a_mod_added_by_hand_is_named_not_silently_dropped(self):
        api, master = setup_library(self)
        doc = api.build_mod_list()["list"]
        self.assertEqual([n["key"] for n in doc["not_shared"]], [HAND])
        self.assertEqual(doc["note"], mod_list.NOT_INCLUDED)

    def test_the_file_never_holds_a_path_on_this_computer(self):
        api, master = setup_library(self)
        text = json.dumps(api.build_mod_list()["list"])
        self.assertNotIn(str(master).replace("\\", "\\\\"), text)
        self.assertNotIn(Path(master).drive or "no-drive", text.replace("https://", ""))

    def test_export_writes_a_file_the_import_can_read_back(self):
        api, master = setup_library(self)
        target = master.parent / "list.json"
        result = api.export_mod_list(str(target))
        self.assertTrue(result["success"], result)
        self.assertEqual((result["mods"], result["not_shared"]), (2, [HAND]))
        other, _ = make(self)
        read = other.read_mod_list(str(target))
        self.assertTrue(read["success"], read)
        self.assertEqual(len(read["mods"]), 2)
        self.assertEqual(read["already"], 0)
        self.assertEqual(read["unusable"], [])

    def test_the_list_reads_as_already_here_on_the_computer_it_came_from(self):
        api, master = setup_library(self)
        target = master.parent / "list.json"
        api.export_mod_list(str(target))
        self.assertEqual(api.read_mod_list(str(target))["already"], 2)


class Reading(unittest.TestCase):
    def good(self, **change):
        entry = {"item": "Birdo", "category": "characters", "mod_id": 5, "record_type": "Mod", "name": "N",
                 "files": [{"file_id": 7, "name": "a.zip"}], "units": [{"file_id": 7, "sub": "", "left_out": []}]}
        entry.update(change)
        return entry

    def parse(self, mods, **top):
        doc = {"format": mod_list.FORMAT, "version": 1, "mods": mods, **top}
        return mod_list.parse_mod_list(json.dumps(doc), CATS)

    def test_what_is_not_a_mod_list_is_refused_with_a_reason(self):
        for text in ("not json", "[]", json.dumps({"format": "other", "version": 1, "mods": []}),
                     json.dumps({"format": mod_list.FORMAT, "version": 99, "mods": []}),
                     json.dumps({"format": mod_list.FORMAT, "version": 1, "mods": "x"})):
            doc, why = mod_list.parse_mod_list(text, CATS)
            self.assertIsNone(doc)
            self.assertTrue(why)

    def test_a_good_entry_is_kept(self):
        doc, why = self.parse([self.good()])
        self.assertIsNone(why)
        self.assertEqual(len(doc["mods"]), 1)

    def test_an_entry_that_could_reach_outside_the_mods_folder_is_unusable(self):
        bad = [
            self.good(units=[{"file_id": 7, "sub": "../../evil", "left_out": []}]),
            self.good(units=[{"file_id": 7, "sub": "/abs", "left_out": []}]),
            self.good(units=[{"file_id": 7, "sub": "C:\\Windows", "left_out": []}]),
            self.good(units=[{"file_id": 7, "sub": "", "left_out": [{"path": "../x", "reason": "manual"}]}]),
            self.good(item="../Birdo"), self.good(item="a/b"), self.good(category="../.."), self.good(category="saves"),
            self.good(mod_id="5"), self.good(mod_id=-1), self.good(mod_id=True), self.good(record_type="Other"),
            self.good(files=[]), self.good(files=[{"file_id": "x"}]), self.good(units=[]),
            self.good(units=[{"file_id": 999, "sub": "", "left_out": []}]),                     # (a folder of a file the entry doesn't list)
        ]
        doc, why = self.parse(bad + [self.good()])
        self.assertIsNone(why)
        self.assertEqual(len(doc["mods"]), 1)
        self.assertEqual(len(doc["unusable"]), len(bad))

    def test_one_bad_entry_does_not_lose_the_others(self):
        doc, _ = self.parse([self.good(mod_id=1), "junk", self.good(mod_id=2)])
        self.assertEqual([m["mod_id"] for m in doc["mods"]], [1, 2])
        self.assertEqual(len(doc["unusable"]), 1)

    def test_only_the_fields_the_app_uses_come_through(self):
        doc, _ = self.parse([self.good(extra_field="x", downloaded_to="C:/secret")])
        self.assertNotIn("extra_field", doc["mods"][0])
        self.assertNotIn("downloaded_to", doc["mods"][0])


class Importing(unittest.TestCase):
    """The download is replaced by one that builds the folder and record the real one does."""

    def stand_ins(self, api, master, fetch_files=(11,), folder_name="Mr. AR", status="downloaded"):
        calls = {"fetched": 0, "downloaded": []}

        def fetch(item, ref):
            calls["fetched"] += 1
            return {"success": True, "mod": {"name": folder_name, "files": [{"file_id": i} for i in fetch_files]}}

        def download(category, item, mod_id, file_ids, record_type="Mod"):
            calls["downloaded"].append((category, item, mod_id, list(file_ids)))
            folder = extracted(master, f"{category}/{item}/{folder_name}")
            mods = api._load_gb_mods()
            mods.setdefault(item, []).append(record(mod_id, folder_name, [file_entry(i, folder) for i in file_ids]))
            api._save_gb_mods(mods)
            return {"success": True, "results": [{"file_id": i, "status": status} for i in file_ids]}

        api.gb_fetch_mod, api.gb_download_files = fetch, download
        return calls

    def entry(self, **change):
        entry = {"item": "Baby Daisy", "category": "characters", "mod_id": 682993, "record_type": "Mod", "name": "Mr. AR",
                 "files": [{"file_id": 11, "name": "a.zip"}],
                 "units": [{"file_id": 11, "sub": "", "left_out": [{"path": "Model/Baby.bfres", "reason": "manual", "kept_from": None}]}]}
        entry.update(change)
        return entry

    def test_it_downloads_the_mod_ticks_its_folder_and_leaves_the_file_out(self):
        api, master = make(self)
        calls = self.stand_ins(api, master)
        result = api.import_mod_list_item(self.entry())
        self.assertTrue(result["success"], result)
        self.assertEqual(calls["downloaded"], [("characters", "Baby Daisy", 682993, [11])])
        self.assertTrue(api._load_state()[DAISY])
        self.assertIn("model/baby.bfres", api._load_excluded_files()[DAISY])

    def test_it_never_unticks_what_the_importer_already_has(self):
        api, master = make(self)
        extracted(master, HAND)
        api.save_checked({HAND: True})
        self.stand_ins(api, master)
        api.import_mod_list_item(self.entry())
        self.assertTrue(api._load_state()[HAND])
        self.assertTrue(api._load_state()[DAISY])

    def test_a_mod_already_downloaded_is_not_downloaded_again(self):
        api, master = setup_library(self)
        calls = self.stand_ins(api, master)
        api.save_checked({DAISY: False})
        result = api.import_mod_list_item(self.entry())
        self.assertTrue(result["success"], result)
        self.assertEqual(calls, {"fetched": 0, "downloaded": []})
        self.assertTrue(api._load_state()[DAISY])

    def test_a_mod_renamed_since_the_list_was_made_still_gets_its_folders_ticked(self):
        api, master = make(self)
        self.stand_ins(api, master, folder_name="Mr. AR Renamed")
        entry = self.entry(units=[{"file_id": 11, "sub": "inner", "left_out": []}])
        extracted(master, "characters/Baby Daisy/Mr. AR Renamed/inner")           # (the renamed mod's archive has the same inner folder)
        result = api.import_mod_list_item(entry)
        self.assertTrue(result["success"], result)
        self.assertTrue(api._load_state()["characters/Baby Daisy/Mr. AR Renamed/inner"])

    def test_a_file_gone_from_gamebanana_is_reported_not_hidden(self):
        api, master = make(self)
        calls = self.stand_ins(api, master, fetch_files=(99,))
        result = api.import_mod_list_item(self.entry())
        self.assertFalse(result["success"])
        self.assertEqual(calls["downloaded"], [])
        self.assertTrue(any("no longer on GameBanana" in m for m in result["missing"]))
        self.assertEqual(api._load_state(), {})

    def test_an_unreachable_mod_fails_with_the_reason_and_changes_nothing(self):
        api, master = make(self)
        api.gb_fetch_mod = lambda item, ref: {"success": False, "error": "offline"}
        result = api.import_mod_list_item(self.entry())
        self.assertFalse(result["success"])
        self.assertIn("offline", result["error"])
        self.assertEqual(api._load_state(), {})

    def test_an_entry_that_is_not_safe_is_skipped_before_anything_happens(self):
        api, master = make(self)
        calls = self.stand_ins(api, master)
        result = api.import_mod_list_item(self.entry(category="../.."))
        self.assertFalse(result["success"])
        self.assertEqual(calls, {"fetched": 0, "downloaded": []})


class ThePage(unittest.TestCase):
    def read(self, *parts):
        return ROOT.joinpath("src", "ui", *parts).read_text(encoding="utf-8")

    def test_the_settings_card_and_the_script_are_wired_in(self):
        bootstrap, modals = self.read("js", "bootstrap.js"), self.read("js", "app-modals.js")
        self.assertIn('"js/mod-list.js"', bootstrap)
        self.assertLess(bootstrap.index('"js/ui/modal.js"'), bootstrap.index('"js/mod-list.js"'))
        for needle in ("btn-export-mod-list", "btn-import-mod-list", "exportModList()", "openImportModList()"):
            self.assertIn(needle, modals)

    def test_the_caveat_is_said_where_a_person_decides(self):
        script, modals = self.read("js", "mod-list.js"), self.read("js", "app-modals.js")
        self.assertIn("Custom icons, voices and your notes are not included", script)
        self.assertEqual(modals.count("Custom icons, voices and your notes are not included"), 1)      # (the Settings card)

    def test_the_page_never_uses_a_native_dialog(self):
        self.assertNotRegex(self.read("js", "mod-list.js"), r"(?<![\w.])(confirm|alert)\(")


if __name__ == "__main__":
    unittest.main()
