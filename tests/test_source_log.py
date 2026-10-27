"""Run from source, the app keeps mod-manager.log too, and the console still gets everything.

Run from the repo root:  python -m unittest discover -s tests
"""
import faulthandler
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app_paths  # noqa: E402
import mod_manager as mm  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"


class FakeConsole(io.TextIOWrapper):
    """A console that cannot show some characters (a Windows terminal on a legacy code page)."""

    def __init__(self):
        super().__init__(io.BytesIO(), encoding="ascii", errors="strict", line_buffering=True)


class Tee(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="mk8dx-tee-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.real = (app_paths.APP_ROOT, sys.stdout, sys.stderr)
        app_paths.APP_ROOT = self.folder
        app_paths._log_path = None
        self.addCleanup(self.restore)

    def restore(self):
        faulthandler.disable()
        for stream in (sys.stdout, sys.stderr):
            if stream not in (self.real[1], self.real[2]) and hasattr(stream, "_log"):
                stream._log.close()
        app_paths.APP_ROOT, sys.stdout, sys.stderr = self.real
        app_paths._log_path = None

    def log_text(self):
        return (self.folder / app_paths.LOG_FILENAME).read_text(encoding="utf-8")

    def test_everything_goes_to_the_console_and_to_the_file(self):
        out, err = io.StringIO(), io.StringIO()
        sys.stdout, sys.stderr = out, err
        app_paths.redirect_output_to_log(tee=True)
        print("to stdout")
        print("to stderr", file=sys.stderr)
        self.assertEqual((out.getvalue(), err.getvalue()), ("to stdout\n", "to stderr\n"))
        text = self.log_text()
        self.assertIn("to stdout", text)
        self.assertIn("to stderr", text)
        self.assertEqual(len(re.findall(r"Mod Manager started", text)), 1)

    def test_a_character_the_console_cannot_show_does_not_cost_the_line_in_the_log(self):
        sys.stdout = sys.stderr = FakeConsole()
        app_paths.redirect_output_to_log(tee=True)
        print("arrow \u2192 here")        # (the console is ASCII: it refuses)
        self.assertIn("arrow \u2192 here", self.log_text())

    def test_without_a_console_the_file_still_gets_everything(self):
        sys.stdout = sys.stderr = None       # (pythonw)
        app_paths.redirect_output_to_log(tee=True)
        print("no console")
        self.assertIn("no console", self.log_text())

    def test_the_tee_answers_like_the_console(self):
        console = io.StringIO()
        sys.stdout = sys.stderr = console
        app_paths.redirect_output_to_log(tee=True)
        self.assertEqual(sys.stderr.isatty(), console.isatty())
        sys.stderr.flush()

    def test_asking_twice_is_still_one_log_and_one_tee(self):
        sys.stdout = sys.stderr = io.StringIO()
        first = app_paths.redirect_output_to_log(tee=True)
        stream = sys.stderr
        self.assertEqual(app_paths.redirect_output_to_log(tee=True), first)
        self.assertIs(sys.stderr, stream)
        self.assertEqual(app_paths.current_log_path(), first)
        self.assertEqual(len(re.findall(r"Mod Manager started", self.log_text())), 1)

    def test_if_no_log_can_be_opened_the_console_is_left_alone(self):
        (self.folder / app_paths.LOG_FILENAME).mkdir()          # (a folder where the file should be)
        console = io.StringIO()
        sys.stdout = sys.stderr = console
        temp = Path(tempfile.mkdtemp(prefix="mk8dx-tee-temp-"))
        self.addCleanup(shutil.rmtree, temp, True)
        (temp / app_paths.LOG_FILENAME).mkdir()                 # (and in the temp folder too)
        with mock.patch.object(app_paths.tempfile, "gettempdir", return_value=str(temp)):       # (the temp folder is the second place tried)
            self.assertIsNone(app_paths.redirect_output_to_log(tee=True))
        self.assertIs(sys.stderr, console)


class PlainImportChangesNothing(unittest.TestCase):
    def test_importing_the_app_does_not_redirect_anything_or_start_a_log(self):
        self.assertIsNone(mm.LOG_PATH)
        self.assertIsNone(app_paths.current_log_path())
        self.assertFalse(hasattr(sys.stderr, "_log"))


class RunAsTheProgram(unittest.TestCase):
    def test_the_app_run_from_source_writes_the_log_and_still_prints(self):
        folder = Path(tempfile.mkdtemp(prefix="mk8dx-source-"))
        self.addCleanup(shutil.rmtree, folder, True)
        driver = (
            "import sys, runpy\n"
            f"sys.path.insert(0, {str(SRC)!r})\n"
            "import app_paths\nfrom pathlib import Path\n"
            f"app_paths.APP_ROOT = Path({str(folder)!r})\n"
            f"sys.argv = [{str(SRC / 'mod_manager.py')!r}, '--self-check']\n"
            f"runpy.run_path({str(SRC / 'mod_manager.py')!r}, run_name='__main__')\n")
        done = subprocess.run([sys.executable, "-c", driver], capture_output=True, text=True, timeout=120)   # (the exit code depends on 7-Zip: not checked)
        console = done.stdout + done.stderr
        log = (folder / "mod-manager.log").read_text(encoding="utf-8")
        self.assertIn("self-check:", console)                   # (still on the console)
        self.assertIn("self-check:", log)                       # (and in the file)
        self.assertEqual(len(re.findall(r"Mod Manager started", log)), 1)    # (once, though the app imports itself a second time by name)
        self.assertIn("Mod Manager 0.", log)
        self.assertNotIn("Traceback", log)


if __name__ == "__main__":
    unittest.main()
