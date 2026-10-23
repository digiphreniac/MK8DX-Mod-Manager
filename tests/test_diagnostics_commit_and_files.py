"""Phase 2 of the diagnostics work: the places that used to fail without a word now say what happened (and don't leave half-done work
behind) - the commit's copy into the staging folder, the menu icons build's reasons, the game-files copy, downloads and extraction,
and settings files that can't be read.

Run from the repo root:  python -m unittest discover -s tests
"""
import contextlib
import errno
import io
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import game_files  # noqa: E402
import gamebanana_api as gb  # noqa: E402
import mod_manager as mm  # noqa: E402
import ui_setup  # noqa: E402


def captured(fn, *args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def tmp_dir(case):
    folder = Path(tempfile.mkdtemp(prefix="mk8dx-p2-"))
    case.addCleanup(shutil.rmtree, folder, True)
    return folder


# ----------------------------------------------------------------------------------------------- the icons build explains itself
class IconBuildReasons(unittest.TestCase):
    def test_a_change_that_cant_be_used_is_listed_with_its_reason(self):
        lines = mm.describe_ui_build([
            {"archive": "common", "nothing": True, "dropped": [{"mods": ["Plush Mario"], "what": "Mario", "reason": "its picture is a different shape"}]},
            {"archive": "menu", "nothing": True}])
        self.assertIn("1 change(s) in the selected mods can't be used", lines[0])
        self.assertIn("Plush Mario: Mario - its picture is a different shape", lines[1])
        self.assertIn("menu.sarc: not made - no selected mod changes anything in it", lines[2])

    def test_a_built_file_says_how_many_changes_went_in_and_what_was_left_out(self):
        report = {"applied": [{}, {}, {}], "skipped": [{"mods": ["A"], "what": "Toad", "reason": "not in your base file"}]}
        lines = mm.describe_ui_build([{"archive": "common", "report": report}, {"archive": "menu", "nothing": True}])
        self.assertEqual(lines[0], "  common.sarc: built (3 change(s) applied, 1 left out).")
        self.assertIn("A: Toad - not in your base file", lines[1])

    def test_a_long_list_is_cut(self):
        many = [{"mods": ["M"], "what": f"c{i}", "reason": "r"} for i in range(20)]
        lines = mm.describe_ui_build([{"archive": "common", "nothing": True, "dropped": many}, {"archive": "menu", "nothing": True}])
        self.assertTrue(any("... and 12 more" in line for line in lines))

    def test_the_language_file_is_described_too(self):
        lines = mm.describe_ui_build([{"archive": "common", "nothing": True}, {"archive": "menu", "nothing": True},
                                      {"archive": "message:USen", "report": {"applied": [{}], "skipped": []}}])
        self.assertIn("message.sarc (USen): built (1 change(s) applied)", "\n".join(lines))

    def test_dropped_changes_lists_unmergeable_ones_and_set_aside_ones_but_not_the_bases(self):
        analysis = {"base": 0, "variants": [
            {"labels": ["Your game's own files"], "changes": [{"entry": "e", "name": "t", "character": "Mario", "mergeable": False, "reason": "x"}]},
            {"labels": ["Mod A"], "changes": [{"entry": "e", "name": "t", "character": "Peach", "mergeable": False, "reason": "wrong shape"},
                                              {"entry": "e", "name": "u", "character": "Toad", "mergeable": True}], "other": 3}]}
        dropped = ui_setup.dropped_changes(analysis)
        self.assertEqual([(d["mods"], d["what"], d["reason"]) for d in dropped], [
            (["Mod A"], "Peach", "wrong shape"), (["Mod A"], "3 other entries", "set aside as unrelated to what the mod is filed under")])


# ----------------------------------------------------------------------------------------------- a commit that stops halfway says so
class FailedCopy(unittest.TestCase):
    KEY = "characters/Mario/Plain Skin"

    def setUp(self):
        parent = tmp_dir(self)
        self.master = parent / "data"
        self.api = mm.Api(self.master)
        mod = self.master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
        mod.mkdir(parents=True)
        (mod / "Mario.bfres").write_bytes(b"x")
        self.api._update_state(lambda state: state.update({self.KEY: True}))

    def test_a_good_commit_is_recorded_and_a_failed_one_clears_that_record(self):
        self.assertTrue(self.api.merge([self.KEY])["staged"])
        self.assertTrue(self.api.get_settings()["last_commit"])
        with mock.patch.object(shutil, "copy2", side_effect=OSError(errno.ENOSPC, "No space left on device", "X:/staging/Mario.bfres")):
            result, log = captured(self.api.merge, [self.KEY])
        self.assertFalse(result["staged"])
        self.assertFalse(result["conflict"])
        text = "\n".join(result["lines"])
        self.assertIn("Commit FAILED", text)
        self.assertIn("The copy stopped at: X:/staging/Mario.bfres", text)
        self.assertIn("No space left on device", text)
        self.assertFalse(self.api.get_settings()["last_commit"])
        self.assertFalse(self.api.preview_commit([self.KEY])["already"])
        self.assertIn("copying into the staging folder failed", log)

    def test_the_commit_log_goes_to_the_log_file_too(self):
        _, log = captured(self.api.merge, [self.KEY])
        self.assertIn("commit: Mod Manager ", log)
        self.assertIn("=== Commit complete ===", log)

    def test_the_commit_log_lists_the_notes_the_commit_page_shows(self):
        lines = self.api.merge([self.KEY])["lines"]
        self.assertIn("Notes shown on the Commit page:", lines)
        self.assertIn("  - No menu icons or names will change", lines)


# ----------------------------------------------------------------------------------------------- the copy of the game's files
def make_dump(folder: Path):
    for rel in ("UI/cmn/common.sarc", "UI/cmn/menu.sarc", "UI/USen/message.sarc"):
        path = folder / "romfs" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"SARC" + b"\0" * 64)
    return folder / "romfs"


class GameFilesCopy(unittest.TestCase):
    def setUp(self):
        self.parent = tmp_dir(self)
        self.master = self.parent / "data"
        self.master.mkdir()
        self.dump = make_dump(self.parent / "dump")

    def test_a_good_copy_is_done_and_leaves_no_scraps(self):
        res = game_files.copy_both(self.dump, self.master)
        self.assertTrue(res["success"])
        status = game_files.status(self.master)
        self.assertTrue(status["done"])
        self.assertEqual(status["missing_on_disk"], [])
        names = sorted(p.name for p in (self.master / game_files.DIRNAME).iterdir())
        self.assertEqual(names, ["current", "manifest.json", "original"])

    def test_a_copy_that_fails_leaves_the_previous_one_in_place(self):
        game_files.copy_both(self.dump, self.master)
        marker = self.master / game_files.DIRNAME / "current" / "marker.txt"
        marker.write_text("the old copy")
        with mock.patch.object(game_files, "_copy_into", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            res, log = captured(game_files.copy_both, self.dump, self.master)
        self.assertFalse(res["success"])
        self.assertIn("Nothing was changed", res["error"])
        self.assertTrue(marker.is_file())
        self.assertTrue(game_files.status(self.master)["done"])
        self.assertFalse((self.master / game_files.DIRNAME / "current.new").exists())
        self.assertIn("game-files: copy failed", log)

    def test_a_required_file_that_would_not_copy_fails_the_whole_copy(self):
        real = game_files._copy_one

        def refuse_common(dest_root, relpath, src, magic, problems):
            if relpath.endswith("common.sarc"):
                problems.append(f"{relpath}: couldn't copy - locked")
                return False
            return real(dest_root, relpath, src, magic, problems)
        with mock.patch.object(game_files, "_copy_one", refuse_common):
            res, _ = captured(game_files.copy_both, self.dump, self.master)
        self.assertFalse(res["success"])
        self.assertIn("locked", res["error"])
        self.assertFalse((self.master / game_files.DIRNAME / "current").exists())

    def test_done_means_the_files_are_there_not_just_the_manifest(self):
        game_files.copy_both(self.dump, self.master)
        (self.master / game_files.DIRNAME / "current" / "UI" / "cmn" / "common.sarc").unlink()
        status = game_files.status(self.master)
        self.assertFalse(status["done"])
        self.assertEqual(status["missing_on_disk"], ["common"])

    def test_the_details_name_what_is_missing(self):
        game_files.copy_both(self.dump, self.master)
        (self.master / game_files.DIRNAME / "current" / "UI" / "cmn" / "menu.sarc").unlink()
        text = "\n".join(mm.Api(self.master)._diag_lines(short=True))
        self.assertIn("NOT complete (missing on disk: menu)", text)

    def test_the_start_and_the_end_of_a_copy_are_in_the_log(self):
        _, log = captured(game_files.copy_both, self.dump, self.master)
        self.assertIn("game-files: copy starting from", log)
        self.assertIn("game-files: copy finished", log)


# ----------------------------------------------------------------------------------------------- downloads and unpacking
class FakeResponse(io.BytesIO):
    def __init__(self, body, content_type="text/html", status=200):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}
        self.status = status


class Downloads(unittest.TestCase):
    def setUp(self):
        self.dir = tmp_dir(self)

    def test_a_web_page_instead_of_an_archive_is_recognised(self):
        with mock.patch.object(gb.urllib.request, "urlopen", return_value=FakeResponse(b"<html>Please log in</html>")):
            with self.assertRaises(gb.GameBananaError) as ctx:
                captured(gb._download_direct, "https://gamebanana.com/dl/123?token=secret", self.dir / "mod.zip", expected_size=5000)
        self.assertIn("looks like a web page", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [])   # (no .part file left)

    def test_the_log_has_the_host_and_status_but_not_the_query(self):
        with mock.patch.object(gb.urllib.request, "urlopen", return_value=FakeResponse(b"<html>no</html>")):
            _, log = captured(lambda: self._swallow(gb._download_direct, "https://gamebanana.com/dl/123?token=secret", self.dir / "mod.zip", 5000))
        self.assertIn("gamebanana.com/dl/123", log)
        self.assertNotIn("secret", log)
        self.assertIn("content type text/html", log)

    @staticmethod
    def _swallow(fn, *args):
        try:
            fn(*args)
        except gb.GameBananaError:
            pass

    def test_a_full_disk_is_said_plainly(self):
        with mock.patch.object(gb.urllib.request, "urlopen", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with self.assertRaises(gb.GameBananaError) as ctx:
                captured(gb._download_direct, "https://gamebanana.com/dl/1", self.dir / "m.zip", expected_size=10)
        self.assertIn("the disk is full", str(ctx.exception))

    def test_an_empty_address_is_a_download_error_not_a_crash(self):
        with self.assertRaises(gb.GameBananaError):
            captured(gb._download_direct, "", self.dir / "m.zip", expected_size=10)

    def test_a_damaged_zip_is_named_as_such(self):
        bad = self.dir / "bad.zip"
        bad.write_bytes(b"this is not a zip")
        with mock.patch.object(gb, "find_7zip", return_value=None):
            with self.assertRaises(gb.GameBananaError) as ctx:
                captured(gb.extract_archive, bad, self.dir / "out")
        self.assertIn("isn't a valid zip", str(ctx.exception))

    def test_a_7zip_that_cannot_start_is_reported_for_a_rar(self):
        rar = self.dir / "mod.rar"
        rar.write_bytes(b"Rar!")
        with mock.patch.object(gb, "find_7zip", return_value="C:/7z.exe"), \
                mock.patch.object(gb.subprocess, "run", side_effect=OSError(225, "blocked by antivirus")):
            with self.assertRaises(gb.GameBananaError) as ctx:
                _, log = captured(gb.extract_archive, rar, self.dir / "out")
        self.assertIn("antivirus", str(ctx.exception))

    def test_a_zip_still_unpacks_when_7zip_cannot_start(self):
        archive = self.dir / "mod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("romfs/a.txt", "hello")
        with mock.patch.object(gb, "find_7zip", return_value="C:/7z.exe"), \
                mock.patch.object(gb.subprocess, "run", side_effect=OSError(225, "blocked")):
            captured(gb.extract_archive, archive, self.dir / "out")
        self.assertTrue((self.dir / "out" / "romfs" / "a.txt").is_file())

    def test_7zip_is_run_without_a_console_to_ask_for_a_password(self):
        archive = self.dir / "mod.7z"
        archive.write_bytes(b"7z")
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(gb, "find_7zip", return_value="C:/7z.exe"), mock.patch.object(gb.subprocess, "run", return_value=done) as run:
            gb.extract_archive(archive, self.dir / "out")
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["errors"], "replace")


class DownloadWrapper(unittest.TestCase):
    def setUp(self):
        master = tmp_dir(self) / "data"
        master.mkdir()
        self.api = mm.Api(master)
        self.entry = {"name": "mod.zip", "size": 10}

    def test_an_unexpected_error_becomes_a_download_error_and_the_half_unpacked_folder_goes(self):
        half = self.api.mod_root / "half"

        def fails(category, item, mod, entry, trace):
            half.mkdir()
            (half / "a.txt").write_text("x")
            trace["dest"] = half
            raise KeyError("download_url")
        with mock.patch.object(self.api, "_download_and_extract", fails):
            with self.assertRaises(gb.GameBananaError) as ctx:
                _, log = captured(self.api._download_and_extract_one, "characters", "Mario", "Plain Skin", self.entry)
        self.assertIn("KeyError", str(ctx.exception))
        self.assertFalse(half.exists())

    def test_the_log_says_which_mod_and_file(self):
        def fails(category, item, mod, entry, trace):
            raise ValueError("boom")
        with mock.patch.object(self.api, "_download_and_extract", fails):
            out = io.StringIO()
            with contextlib.redirect_stderr(out), self.assertRaises(gb.GameBananaError):
                self.api._download_and_extract_one("characters", "Mario", "Plain Skin", self.entry)
        self.assertIn("characters/Mario/Plain Skin (mod.zip, 10 bytes)", out.getvalue())
        self.assertIn("ValueError: boom", out.getvalue())

    def test_an_expected_download_error_passes_through_unchanged(self):
        def fails(category, item, mod, entry, trace):
            raise gb.GameBananaError("Download failed: nope")
        with mock.patch.object(self.api, "_download_and_extract", fails):
            with self.assertRaises(gb.GameBananaError) as ctx:
                captured(self.api._download_and_extract_one, "characters", "Mario", "Plain Skin", self.entry)
        self.assertEqual(str(ctx.exception), "Download failed: nope")

    def test_a_finished_download_is_not_cleaned_up_after_the_fact(self):
        done = self.api.mod_root / "done"
        done.mkdir()

        def succeeds(category, item, mod, entry, trace):
            trace["dest"] = None
            return {"status": "downloaded"}
        with mock.patch.object(self.api, "_download_and_extract", succeeds):
            self.assertEqual(self.api._download_and_extract_one("characters", "Mario", "Plain Skin", self.entry), {"status": "downloaded"})
        self.assertTrue(done.exists())


# ----------------------------------------------------------------------------------------------- files that can't be read
class UnreadableSettings(unittest.TestCase):
    def setUp(self):
        master = tmp_dir(self) / "data"
        master.mkdir()
        self.api = mm.Api(master)

    def test_the_previous_copy_is_used_when_the_file_is_damaged(self):
        self.api.save_settings({"a": 1})
        self.api.save_settings({"b": 2})      # (the first save is now the .bak)
        self.api.settings_path.write_text("{broken", encoding="utf-8")
        settings, log = captured(self.api.get_settings)
        self.assertEqual(settings["a"], 1)
        self.assertIn("using its previous copy", log)

    def test_every_save_keeps_the_one_before_as_a_backup(self):
        self.api.save_settings({"a": 1})
        self.api.save_settings({"a": 2})
        self.assertIn('"a": 1', self.api.settings_path.with_name(self.api.settings_path.name + ".bak").read_text(encoding="utf-8"))

    def test_saves_from_several_threads_do_not_lose_each_other(self):
        def work(n):
            for i in range(15):
                self.api.save_settings({f"key{n}": i})
        threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        settings = self.api.get_settings()
        self.assertEqual([settings.get(f"key{n}") for n in range(6)], [14] * 6)

    def test_a_refused_save_of_selections_says_so(self):
        self.api._root_epoch = "this-folder"
        result, log = captured(self.api.save_checked, {"characters/A/b": True}, "another-folder")
        self.assertFalse(result)
        self.assertIn("a save was refused", log)


if __name__ == "__main__":
    unittest.main()
