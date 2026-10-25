"""The log and the details a user can hand over: timestamped lines with the Windows user name taken out, a capped and de-duplicated
channel for the page's errors, the header of a commit log, the log being added to by every run (and kept small), and a file that can't be read being
said so instead of silently becoming empty.

Run from the repo root:  python -m unittest discover -s tests
"""
import contextlib
import faulthandler
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app_paths  # noqa: E402
import diag  # noqa: E402
import mod_manager as mm  # noqa: E402

UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def captured(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = fn(*args)
    return result, out.getvalue()


class Scrub(unittest.TestCase):
    def test_the_users_folder_becomes_a_tilde(self):
        self.assertEqual(diag.scrub(r"C:\Users\game\Workspace\mods"), r"~\Workspace\mods")
        self.assertEqual(diag.scrub("d:/USERS/bob/Documents/x"), "~/Documents/x")

    def test_a_path_from_another_system_is_cleaned_too(self):
        self.assertEqual(diag.scrub("/Users/digi/Downloads/dump/romfs"), "~/Downloads/dump/romfs")
        self.assertEqual(diag.scrub("source /home/someone/dump"), "source ~/dump")

    def test_other_paths_are_left_alone(self):
        self.assertEqual(diag.scrub(r"D:\Games\MK8DX\data"), r"D:\Games\MK8DX\data")
        self.assertEqual(diag.scrub(r"D:\Games\Users\shared"), r"D:\Games\Users\shared")

    def test_a_line_that_mentions_two_paths_is_cleaned_in_both(self):
        self.assertEqual(diag.scrub(r"moved C:\Users\a\x to E:\Users\b\y"), r"moved ~\x to ~\y")


class Logging(unittest.TestCase):
    def test_a_line_has_a_timestamp_and_a_kind(self):
        _, text = captured(diag.log, "warn", "something odd")
        self.assertRegex(text, r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] warn: something odd\n$")

    def test_usernames_are_removed_from_what_is_logged(self):
        _, text = captured(diag.log, "warn", r"couldn't read C:\Users\game\data\x.json")
        self.assertNotIn("game", text)

    def test_a_multi_line_message_stays_one_entry(self):
        _, text = captured(diag.log, "error", "first\nsecond")
        self.assertIn("error: first\n    second", text)

    def test_log_once_says_it_only_the_first_time(self):
        key = ("test-key", object())
        _, first = captured(diag.log_once, key, "warn", "x")
        _, second = captured(diag.log_once, key, "warn", "x")
        self.assertTrue(first)
        self.assertEqual(second, "")

    def test_logging_never_raises_without_a_stream(self):
        real = sys.stderr
        sys.stderr = None
        try:
            diag.log("warn", "nowhere to write")
        finally:
            sys.stderr = real


class ClientLog(unittest.TestCase):
    def test_garbage_is_ignored_without_an_error(self):
        log = diag.ClientLog()
        for junk in (None, "text", 5, {}, [1, None, "x", {"kind": 5}], [{"msg": None}]):
            captured(log.accept, junk)   # (must not raise)

    def test_a_message_is_written_with_its_kind_and_level(self):
        n, text = captured(diag.ClientLog().accept, [{"level": "error", "kind": "api_error", "msg": "get_mods: boom"}])
        self.assertEqual(n, 1)
        self.assertIn("page-error/api_error: get_mods: boom", text)

    def test_a_kind_cannot_inject_anything_and_an_unknown_level_is_info(self):
        _, text = captured(diag.ClientLog().accept, [{"level": "loud", "kind": "bad kind!\n[x]", "msg": "m"}])
        self.assertIn("page-info/badkindx: m", text)

    def test_the_same_message_is_written_once_then_at_its_10th_time(self):
        log = diag.ClientLog()
        event = [{"level": "error", "kind": "js-error", "msg": "same"}] * 20
        first, text = captured(log.accept, event)
        again, _ = captured(log.accept, event)
        self.assertEqual(first, 2)   # (the 1st and the 10th)
        self.assertIn("(x10)", text)
        self.assertEqual(again, 0)   # (21st to 40th: nothing new to say)

    def test_a_very_long_message_is_cut(self):
        _, text = captured(diag.ClientLog().accept, [{"kind": "k", "msg": "x" * 50000}])
        self.assertLess(len(text), diag.ClientLog.MAX_FIELD + 200)

    def test_at_most_a_batch_is_read_per_call(self):
        events = [{"kind": "k", "msg": f"m{i}"} for i in range(100)]
        n, _ = captured(diag.ClientLog().accept, events)
        self.assertEqual(n, diag.ClientLog.MAX_BATCH)

    def test_a_page_in_a_loop_cannot_fill_the_log(self):
        class Small(diag.ClientLog):
            MAX_PRINTED = 3
        log = Small()
        total, text = 0, ""
        for i in range(10):
            n, t = captured(log.accept, [{"kind": "k", "msg": f"distinct {i}"}])
            total, text = total + n, text + t
        self.assertEqual(total, 3)
        self.assertEqual(text.count("more than 3 page messages"), 1)


class Tail(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mk8dx-diag-"))
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_it_returns_the_last_lines_with_usernames_removed(self):
        path = self.dir / "x.log"
        path.write_text("\n".join(f"line {i}" for i in range(500)) + "\nC:\\Users\\game\\end", encoding="utf-8")
        text = diag.tail(path, lines=3)
        self.assertEqual(text.splitlines(), ["line 498", "line 499", "~\\end"])

    def test_a_missing_file_is_an_empty_string(self):
        self.assertEqual(diag.tail(self.dir / "nope.log"), "")


class Details(unittest.TestCase):
    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-diag-"))
        self.addCleanup(shutil.rmtree, parent, True)
        self.parent = parent
        self.api = mm.Api(parent / "data")

    def test_the_short_form_is_the_few_lines_that_open_a_commit_log(self):
        lines = self.api._diag_lines(short=True)
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Mod Manager "))
        self.assertIn("Data folder:", lines[1])
        self.assertIn("Game version:", lines[2])
        self.assertIn("Selected mods: 0", lines[3])

    def test_the_full_form_adds_the_environment_and_the_game_files(self):
        text = "\n".join(self.api._diag_lines())
        for needle in ("App folder:", "Staging folder:", "Game files copy:", "Game files on disk:", "7-Zip:", "Libraries:"):
            self.assertIn(needle, text)
        self.assertIn("common MISSING", text)   # (nothing was copied in this empty folder)

    def test_no_windows_user_name_is_in_the_details(self):
        text = "\n".join(self.api._diag_lines())
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]+Users[\\/]", text))

    def test_a_folder_not_chosen_yet_is_said_plainly(self):
        lines = mm.Api(None)._diag_lines()
        self.assertEqual(lines[1], "Data folder: not chosen yet")

    def test_the_copied_text_ends_with_the_log_unless_short(self):
        log = self.parent / "mod-manager.log"
        log.write_text("[t] startup: hello from the log\n", encoding="utf-8")
        real = mm.LOG_PATH
        mm.LOG_PATH = str(log)
        self.addCleanup(setattr, mm, "LOG_PATH", real)
        full = self.api.get_diagnostics(False)
        self.assertIn("--- end of mod-manager.log ---", full)
        self.assertIn("hello from the log", full)
        self.assertNotIn("hello from the log", self.api.get_diagnostics(True))

    def test_from_source_there_is_no_log_and_it_says_so(self):
        real = mm.LOG_PATH
        mm.LOG_PATH = None
        self.addCleanup(setattr, mm, "LOG_PATH", real)
        self.assertIn("isn't writing a log file", self.api.get_diagnostics(False))

    def test_a_failure_collecting_the_details_is_a_line_not_an_error(self):
        def boom(short=False):
            raise RuntimeError("nope")
        self.api._diag_lines = boom
        self.assertIn("couldn't collect the details: RuntimeError: nope", self.api.get_diagnostics(True))

    def test_the_page_can_hand_messages_to_the_log(self):
        n, text = captured(self.api.log_client, [{"level": "error", "kind": "js-error", "msg": "x is not defined"}])
        self.assertEqual(n, 1)
        self.assertIn("x is not defined", text)

    def test_a_commit_log_opens_with_the_details(self):
        mod = self.parent / "data" / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
        mod.mkdir(parents=True)
        (mod / "Mario.bfres").write_bytes(b"x")
        key = "characters/Mario/Plain Skin"
        self.api._update_state(lambda state: state.update({key: True}))
        lines = self.api.merge([key])["lines"]
        self.assertTrue(lines[0].startswith("Mod Manager "))
        self.assertIn("Selected mods: 1", "\n".join(lines[:5]))


class UnreadableFiles(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mk8dx-diag-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.api = mm.Api(self.dir / "data")

    def test_a_damaged_settings_file_is_said_once_and_the_defaults_are_used(self):
        bad = self.dir / "damaged-settings.json"
        bad.write_text("{not json", encoding="utf-8")
        result, first = captured(self.api._load_json, bad, {"d": 1})
        _, second = captured(self.api._load_json, bad, {"d": 1})
        self.assertEqual(result, {"d": 1})
        self.assertIn("damaged-settings.json couldn't be read", first)
        self.assertEqual(second, "")

    def test_a_file_in_another_encoding_is_reported_not_raised(self):
        odd = self.dir / "odd-encoding.json"
        odd.write_bytes('{"name": "Coup\u00e9"}'.encode("cp1252"))
        result, text = captured(self.api._load_json, odd, {})
        self.assertEqual(result, {})
        self.assertIn("odd-encoding.json couldn't be read", text)

    def test_utf8_content_is_read_the_same_on_every_system(self):
        good = self.dir / "utf8.json"
        good.write_text('{"name": "Coup\u00e9"}', encoding="utf-8")
        self.assertEqual(self.api._load_json(good, {})["name"], "Coup\u00e9")


class LogFile(unittest.TestCase):
    MARKER = re.compile(r"^=== \d{4}-\d\d-\d\d \d\d:\d\d:\d\d - Mod Manager started ===$", re.MULTILINE)

    def launch(self, folder):
        """What the packaged app does first: open the log. Returns its path; the output streams are put back afterwards."""
        real_root, real_out, real_err = app_paths.APP_ROOT, sys.stdout, sys.stderr
        app_paths.APP_ROOT = folder
        app_paths._log_path = None      # (a new process, as far as the redirect is concerned)
        try:
            path = app_paths.redirect_output_to_log()
            sys.stderr.write("something this run said\n")
            stream = sys.stderr
        finally:
            faulthandler.disable()
            sys.stdout, sys.stderr = real_out, real_err
            app_paths.APP_ROOT = real_root
            app_paths._log_path = None
        stream.close()
        return Path(path)

    def folder(self):
        folder = Path(tempfile.mkdtemp(prefix="mk8dx-log-"))
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    def test_a_first_launch_starts_the_log_with_a_marker(self):
        folder = self.folder()
        path = self.launch(folder)
        self.assertEqual(path, folder / app_paths.LOG_FILENAME)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(len(self.MARKER.findall(text)), 1)
        self.assertIn("something this run said", text)
        self.assertFalse(app_paths.LOG_FELL_BACK)

    def test_every_run_adds_to_the_log_instead_of_replacing_it(self):
        folder = self.folder()
        (folder / app_paths.LOG_FILENAME).write_text("the run that went wrong\n", encoding="utf-8")
        text = self.launch(folder).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("the run that went wrong\n"))
        self.assertLess(text.index("the run that went wrong"), text.index("something this run said"))
        self.assertEqual(len(self.MARKER.findall(text)), 1)
        self.assertFalse(any(p.name != app_paths.LOG_FILENAME for p in folder.iterdir()))   # (no second file to ask for)

    def test_two_runs_are_two_marked_sections(self):
        folder = self.folder()
        self.launch(folder)
        text = self.launch(folder).read_text(encoding="utf-8")
        self.assertEqual(len(self.MARKER.findall(text)), 2)
        self.assertEqual(text.count("something this run said"), 2)

    def test_a_log_past_the_cap_keeps_only_the_newest_part_cut_at_a_line(self):
        folder = self.folder()
        lines = [f"line {i:06d} " + "x" * 80 for i in range(15000)]    # (about 1.4 MB)
        (folder / app_paths.LOG_FILENAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
        size_before = (folder / app_paths.LOG_FILENAME).stat().st_size
        self.assertGreater(size_before, app_paths.LOG_MAX_BYTES)
        path = self.launch(folder)
        text = path.read_text(encoding="utf-8")
        self.assertLess(path.stat().st_size, app_paths.LOG_KEEP_BYTES + 2000)
        self.assertTrue(text.startswith("[older entries were cut to keep this file small]\n"))
        self.assertNotIn("line 000000", text)
        self.assertIn("line 014999", text)
        body = text.split("\n")[1]
        self.assertRegex(body, r"^line \d{6} x{80}$")   # (cut at a line: the first kept line is whole)
        self.assertEqual(len(self.MARKER.findall(text)), 1)

    def test_asking_twice_in_one_process_does_not_start_a_second_section(self):
        # (the packaged app runs as __main__ and game_files imports mod_manager again by name, which runs the redirect a second time)
        folder = self.folder()
        real_root, real_out, real_err = app_paths.APP_ROOT, sys.stdout, sys.stderr
        app_paths.APP_ROOT = folder
        app_paths._log_path = None
        try:
            first = app_paths.redirect_output_to_log()
            stream = sys.stderr
            second = app_paths.redirect_output_to_log()
            same_stream = sys.stderr is stream
        finally:
            faulthandler.disable()
            sys.stdout, sys.stderr = real_out, real_err
            app_paths.APP_ROOT = real_root
            app_paths._log_path = None
        stream.close()
        self.assertEqual(first, second)
        self.assertTrue(same_stream)
        self.assertEqual(len(self.MARKER.findall((folder / app_paths.LOG_FILENAME).read_text(encoding="utf-8"))), 1)

    def test_a_log_under_the_cap_is_left_alone(self):
        folder = self.folder()
        (folder / app_paths.LOG_FILENAME).write_text("small\n", encoding="utf-8")
        self.assertTrue(self.launch(folder).read_text(encoding="utf-8").startswith("small\n"))


class PageFiles(unittest.TestCase):
    def test_the_page_logger_loads_before_the_scripts_it_watches(self):
        html = (UI / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("js/diagnostics.js"), html.index("js/bootstrap.js"))

    def test_the_help_button_the_script_looks_for_exists(self):
        self.assertIn('id: "btn-show-log"', (UI / "js" / "app-modals.js").read_text(encoding="utf-8"))
        self.assertIn("btn-show-log", (UI / "js" / "help-and-icon-generator.js").read_text(encoding="utf-8"))

    def test_the_page_logger_never_logs_its_own_calls(self):
        js = (UI / "js" / "diagnostics.js").read_text(encoding="utf-8")
        self.assertIn('name === "log_client"', js)


if __name__ == "__main__":
    unittest.main()
