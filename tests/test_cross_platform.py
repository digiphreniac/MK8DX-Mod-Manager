"""Running on Linux and macOS as well as Windows (docs/cross-platform.md): where the app keeps its files, finding 7-Zip, the window library, the
start-up error dialog, the folder-name fixes for archives made on Windows, the release packages' names, and the workflows.

Everything here runs on every system (what depends on the real file system of one is skipped on the others).

Run from the repo root:  python -m unittest discover -s tests
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import app_paths  # noqa: E402
import build_release  # noqa: E402
import fetch_7zip  # noqa: E402
import gamebanana_api  # noqa: E402
import mod_manager as mm  # noqa: E402


def scratch(test):
    folder = Path(tempfile.mkdtemp(prefix="mk8dx-xplat-"))
    test.addCleanup(shutil.rmtree, folder, True)
    return folder


class WhereTheAppKeepsItsFiles(unittest.TestCase):
    def test_macos_uses_application_support(self):
        self.assertEqual(app_paths.user_data_dir("darwin", {}, "/Users/me"), Path("/Users/me/Library/Application Support/MK8DX Mod Manager"))

    def test_linux_uses_xdg_data_home_or_local_share(self):
        self.assertEqual(app_paths.user_data_dir("linux", {}, "/home/me"), Path("/home/me/.local/share/mk8dx-mod-manager"))
        xdg = str(Path(tempfile.gettempdir()) / "xdg")
        self.assertEqual(app_paths.user_data_dir("linux", {"XDG_DATA_HOME": xdg}, "/home/me"), Path(xdg) / "mk8dx-mod-manager")

    def test_a_relative_xdg_data_home_is_ignored_as_the_standard_says(self):
        self.assertEqual(app_paths.user_data_dir("linux", {"XDG_DATA_HOME": "relative/dir"}, "/home/me"),
                         Path("/home/me/.local/share/mk8dx-mod-manager"))

    def test_running_from_source_keeps_the_folder_above_src(self):
        if not app_paths.FROZEN:
            self.assertEqual(app_paths.APP_ROOT, ROOT)

    def test_the_log_falls_back_to_the_temp_folder_the_system_names(self):
        source = (ROOT / "src" / "app_paths.py").read_text(encoding="utf-8")
        self.assertIn("tempfile.gettempdir()", source)
        self.assertNotIn('os.environ.get("TEMP")', source)


class FindingSevenZip(unittest.TestCase):
    def setUp(self):
        self.folder = scratch(self)
        self.bundle = self.folder / "bundle"
        self.bundle.mkdir()
        patches = [mock.patch.object(app_paths, "BUNDLED_7ZIP_DIR", self.bundle), mock.patch.object(app_paths, "SEVENZIP_NAME", "7zz"),
                   mock.patch.object(gamebanana_api.shutil, "which", return_value=None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_the_bundled_copy_comes_first(self):
        (self.bundle / "7zz").write_bytes(b"x")
        self.assertEqual(gamebanana_api.find_7zip("linux"), str(self.bundle / "7zz"))

    def test_a_bundled_copy_that_lost_its_execute_permission_gets_it_back(self):
        if sys.platform == "win32":
            self.skipTest("Windows has no execute permission")
        tool = self.bundle / "7zz"
        tool.write_bytes(b"x")
        tool.chmod(0o644)
        gamebanana_api.find_7zip("linux")
        self.assertTrue(os.access(tool, os.X_OK))

    def test_the_homebrew_folder_is_looked_in_because_finder_gives_apps_a_small_path(self):
        homebrew = self.folder / "opt-homebrew-bin"
        homebrew.mkdir()
        (homebrew / "7zz").write_bytes(b"x")
        with mock.patch.dict(gamebanana_api._SEVENZIP_DIRS, {"darwin": (str(homebrew),)}):
            self.assertEqual(gamebanana_api.find_7zip("darwin"), str(homebrew / "7zz"))

    def test_the_path_is_searched_for_every_name_it_goes_by(self):
        seen = []

        def which(name):
            seen.append(name)
            return "/somewhere/7z" if name == "7z" else None

        with mock.patch.dict(gamebanana_api._SEVENZIP_DIRS, {"linux": ()}), mock.patch.object(gamebanana_api.shutil, "which", side_effect=which):
            self.assertEqual(gamebanana_api.find_7zip("linux"), "/somewhere/7z")
        self.assertEqual(seen[:2], ["7zz", "7z"])             # (the newest first: it reads RAR5, the old p7zip 7z does not)

    def test_nothing_found_is_none(self):
        with mock.patch.dict(gamebanana_api._SEVENZIP_DIRS, {"linux": (), "darwin": (), "win32": ()}):
            for platform in ("linux", "darwin", "win32"):
                self.assertIsNone(gamebanana_api.find_7zip(platform))

    def test_the_install_hint_names_the_right_tool_for_each_system(self):
        self.assertIn("7-zip.org", gamebanana_api.sevenzip_install_hint("win32"))
        self.assertIn("brew install sevenzip", gamebanana_api.sevenzip_install_hint("darwin"))
        self.assertIn("apt install 7zip", gamebanana_api.sevenzip_install_hint("linux"))
        for platform in ("darwin", "linux"):
            self.assertNotIn("antivirus", gamebanana_api.sevenzip_install_hint(platform).lower())


class TheWindow(unittest.TestCase):
    def test_linux_asks_for_qt_and_the_others_for_their_own(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MK8DX_GUI", None)
            with mock.patch.object(mm.sys, "platform", "linux"):
                self.assertEqual(mm.window_library(), "qt")
            with mock.patch.object(mm.sys, "platform", "darwin"):
                self.assertIsNone(mm.window_library())
            with mock.patch.object(mm.sys, "platform", "win32"):
                self.assertIsNone(mm.window_library())

    def test_the_choice_can_be_overridden(self):
        with mock.patch.dict(os.environ, {"MK8DX_GUI": "GTK"}):
            self.assertEqual(mm.window_library(), "gtk")

    def test_pywebview_is_told_before_anything_asks_it_for_the_screens(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PYWEBVIEW_GUI", "QT_API", "MK8DX_GUI")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(mm.sys, "platform", "linux"):
            self.assertEqual(mm.choose_window_library(), "qt")
            self.assertEqual(os.environ["PYWEBVIEW_GUI"], "qt")
            self.assertEqual(os.environ["QT_API"], "pyqt6")
        source = (ROOT / "src" / "mod_manager.py").read_text(encoding="utf-8")
        main = source[source.index("def main():"):]
        self.assertLess(main.index("choose_window_library()"), main.index("default_window_size()"))

    def test_the_icon_is_only_for_linux(self):
        with mock.patch.object(mm.sys, "platform", "win32"):
            self.assertIsNone(mm.window_icon())
        with mock.patch.object(mm.sys, "platform", "linux"):
            self.assertTrue(mm.window_icon().endswith("app-icon.png"))

    def test_requirements_install_qt_on_linux_only(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn('pywebview[qt]>=5; sys_platform == "linux"', text)
        self.assertIn('pywebview>=5; sys_platform != "linux"', text)


class WhenStartingFails(unittest.TestCase):
    TEXT = 'It said "no"\nDetails: /tmp/mod-manager.log'

    def test_macos_shows_an_alert_with_the_text_quoted_safely(self):
        command = mm.startup_failure_command(self.TEXT, "darwin", lambda name: None)
        self.assertEqual(command[:2], ["osascript", "-e"])
        self.assertIn('display alert "Mod Manager"', command[2])
        self.assertIn('It said \\"no\\"', command[2])

    def test_linux_uses_the_first_dialog_tool_it_finds(self):
        have = {"zenity": "/usr/bin/zenity", "kdialog": "/usr/bin/kdialog", "notify-send": "/usr/bin/notify-send"}
        self.assertEqual(mm.startup_failure_command(self.TEXT, "linux", have.get)[0], "zenity")
        del have["zenity"]
        self.assertEqual(mm.startup_failure_command(self.TEXT, "linux", have.get)[0], "kdialog")
        del have["kdialog"]
        self.assertEqual(mm.startup_failure_command(self.TEXT, "linux", have.get)[0], "notify-send")

    def test_linux_with_none_of_them_shows_nothing_and_does_not_fail(self):
        self.assertIsNone(mm.startup_failure_command(self.TEXT, "linux", lambda name: None))
        with mock.patch.object(mm.sys, "platform", "linux"), mock.patch.object(mm.shutil, "which", return_value=None), \
                mock.patch.object(mm.subprocess, "run") as run:
            mm.report_startup_failure("/tmp/log")
        run.assert_not_called()

    def test_a_dialog_that_cannot_be_started_is_swallowed(self):
        with mock.patch.object(mm.sys, "platform", "linux"), mock.patch.object(mm.shutil, "which", return_value="/usr/bin/zenity"), \
                mock.patch.object(mm.subprocess, "run", side_effect=OSError("no display")):
            mm.report_startup_failure("/tmp/log")          # (must not raise: the app is already failing)


class ArchivesMadeOnWindows(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "Windows reads a backslash as a folder separator itself")
    def test_a_zip_with_backslash_paths_comes_out_as_folders(self):
        folder = scratch(self)
        archive = folder / "mod.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("Mod\\romfs\\Model\\Mario.bfres", b"model")
            zf.writestr("Mod/readme.txt", b"readme")
        dest = folder / "out"
        with mock.patch.object(gamebanana_api, "find_7zip", return_value=None):
            gamebanana_api.extract_archive(archive, dest)
        self.assertEqual((dest / "Mod" / "romfs" / "Model" / "Mario.bfres").read_bytes(), b"model")
        self.assertEqual((dest / "Mod" / "readme.txt").read_bytes(), b"readme")
        self.assertEqual([p.name for p in dest.iterdir() if "\\" in p.name], [])

    @unittest.skipIf(sys.platform == "win32", "Windows cannot make a file with a backslash in its name")
    def test_the_fixer_keeps_a_file_that_is_already_there_and_never_leaves_the_folder(self):
        folder = scratch(self)
        (folder / "a").mkdir()
        (folder / "a" / "b.bin").write_bytes(b"first")
        (folder / "a\\b.bin").write_bytes(b"second")
        (folder / "..\\..\\evil.bin").write_bytes(b"x")
        gamebanana_api.fix_backslash_names(folder)
        self.assertEqual((folder / "a" / "b.bin").read_bytes(), b"first")
        self.assertFalse((folder.parent / "evil.bin").exists())
        self.assertEqual([p.name for p in folder.rglob("*") if "\\" in p.name], [])

    def test_the_fixer_does_nothing_on_windows(self):
        folder = scratch(self)
        (folder / "x.bin").write_bytes(b"x")
        with mock.patch.object(gamebanana_api.sys, "platform", "win32"):
            self.assertEqual(gamebanana_api.fix_backslash_names(folder), 0)


class FolderNamesInDifferentCase(unittest.TestCase):
    def make(self, *names):
        folder = scratch(self)
        for name in names:
            (folder / name).mkdir(parents=True, exist_ok=True)
        return folder

    def names(self, folder):
        return sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*") if p.is_dir())

    def test_romfs_and_exefs_are_renamed_to_lowercase(self):
        folder = self.make("Mod/Romfs/Model", "Mod/ExeFS/patches", "Pack/Variant A/ROMFS/UI")
        self.assertEqual(mm.normalize_case(folder), 3)
        self.assertEqual(self.names(folder), sorted(["Mod", "Mod/romfs", "Mod/romfs/Model", "Mod/exefs", "Mod/exefs/patches", "Pack",
                                                     "Pack/Variant A", "Pack/Variant A/romfs", "Pack/Variant A/romfs/UI"]))

    def test_nothing_inside_a_romfs_is_touched(self):
        folder = self.make("Mod/romfs/Romfs/Deep", "Mod/romfs/UI")
        self.assertEqual(mm.normalize_case(folder), 0)
        self.assertIn("Mod/romfs/Romfs/Deep", self.names(folder))

    def test_already_lowercase_is_left_alone_and_a_second_pass_changes_nothing(self):
        folder = self.make("Mod/Romfs")
        self.assertEqual(mm.normalize_case(folder), 1)
        self.assertEqual(mm.normalize_case(folder), 0)

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "needs a file system that tells romfs and Romfs apart")
    def test_when_both_spellings_exist_neither_is_lost(self):
        folder = self.make("Mod/romfs/a", "Mod/Romfs/b")
        self.assertEqual(mm.normalize_case(folder), 0)
        self.assertEqual(self.names(folder), sorted(["Mod", "Mod/romfs", "Mod/romfs/a", "Mod/Romfs", "Mod/Romfs/b"]))

    def test_a_course_picture_is_found_whatever_the_case_of_the_folders_above_it(self):
        folder = self.make("ui/Cmn/MENU")
        found = mm._ci_descend(folder, "UI", "cmn", "menu")
        self.assertTrue(found.is_dir())
        self.assertEqual(found.name, "MENU")
        self.assertFalse(mm._ci_descend(folder, "UI", "nothing", "menu").exists())

    @unittest.skipIf(sys.platform == "win32", "only macOS and Linux check the library when it is opened")
    def test_opening_a_data_folder_made_on_windows_fixes_its_mods(self):
        master = scratch(self) / "data"
        mod = master / "mods" / "extracted" / "characters" / "Mario" / "Skin" / "Romfs" / "Model"
        mod.mkdir(parents=True)
        (mod / "Mario.bfres").write_bytes(b"x")
        mm.Api(master)
        self.assertTrue((master / "mods" / "extracted" / "characters" / "Mario" / "Skin" / "romfs" / "Model" / "Mario.bfres").is_file())


class TheReleasePackages(unittest.TestCase):
    def test_the_file_names_say_the_system_and_the_processor(self):
        self.assertEqual(build_release.package_name("1.2.3", "windows"), "MK8DX-Mod-Manager-v1.2.3-windows.zip")
        with mock.patch.object(build_release, "SYSTEM", "linux"):
            self.assertEqual(build_release.package_name("1.2.3", "linux", "x86_64"), "MK8DX-Mod-Manager-v1.2.3-linux-x86_64.tar.gz")
            self.assertEqual(build_release.package_name("1.2.3", "linux", "arm64"), "MK8DX-Mod-Manager-v1.2.3-linux-aarch64.tar.gz")
        with mock.patch.object(build_release, "SYSTEM", "macos"):
            self.assertEqual(build_release.package_name("1.2.3", "macos", "arm64"), "MK8DX-Mod-Manager-v1.2.3-macos-arm64.zip")
            self.assertEqual(build_release.package_name("1.2.3", "macos", "x86_64"), "MK8DX-Mod-Manager-v1.2.3-macos-x86_64.zip")

    def test_each_system_has_its_own_readme_in_the_package(self):
        for system, name in build_release.README_FOR.items():
            self.assertTrue((ROOT / "release" / name).is_file(), system)

    def test_the_downloaded_7zip_is_pinned_by_version_and_hash(self):
        for key, (name, sha, program) in fetch_7zip.BUILDS.items():
            self.assertRegex(sha, r"^[0-9a-f]{64}$", key)
            self.assertIn(fetch_7zip.VERSION.replace(".", ""), name)
        self.assertEqual(fetch_7zip.build_key("linux", "x86_64"), "linux-x64")
        self.assertEqual(fetch_7zip.build_key("linux", "aarch64"), "linux-arm64")
        self.assertEqual(fetch_7zip.build_key("darwin", "arm64"), "mac")
        self.assertIsNone(fetch_7zip.build_key("linux", "riscv64"))

    def test_a_download_that_does_not_match_its_hash_is_refused_and_not_unpacked(self):
        import io

        class Answer(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        folder = scratch(self)
        with mock.patch.object(fetch_7zip.urllib.request, "urlopen", return_value=Answer(b"not the archive")):
            with self.assertRaises(SystemExit):
                fetch_7zip.fetch("linux-x64", folder / "out", folder)
        self.assertFalse((folder / "out" / "7zz").exists())
        self.assertFalse((folder / fetch_7zip.BUILDS["linux-x64"][0]).exists())      # (and the bad file is not kept)

    def test_a_kept_download_is_checked_again_before_it_is_used(self):
        folder = scratch(self)
        (folder / fetch_7zip.BUILDS["linux-x64"][0]).write_bytes(b"damaged since it was downloaded")
        with mock.patch.object(fetch_7zip.urllib.request, "urlopen", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                fetch_7zip.fetch("linux-x64", folder / "out", folder)       # (it tried to fetch it again: it did not trust the kept file)

    def test_the_spec_bundles_7zz_as_a_program_on_linux_and_macos(self):
        spec = (ROOT / "tools" / "mk8dx-mod-manager.spec").read_text(encoding="utf-8")
        self.assertIn('binaries.append((str(Path(sevenzip_dir) / "7zz"), "7zip"))', spec)
        self.assertIn("BUNDLE(", spec)
        self.assertIn("app-icon.icns", spec)
        self.assertIn('"webview.platforms.qt"', spec)
        self.assertTrue((ROOT / "tools" / "app-icon.icns").is_file())

    def test_the_notices_of_each_system_name_what_is_in_its_package(self):
        import third_party_notices
        windows = third_party_notices.build(strict=False, system="windows")
        linux = third_party_notices.build(strict=False, system="linux")
        macos = third_party_notices.build(strict=False, system="macos")
        self.assertIn("pythonnet", windows)
        self.assertNotIn("pythonnet", linux + macos)
        for heading in ("PyQt6", "Qt 6 and Qt WebEngine", "QtPy"):
            self.assertIn(heading, linux)
            self.assertNotIn(heading, windows + macos)
        self.assertIn("pyobjc-core", macos)
        self.assertNotIn("pyobjc-core", windows + linux)
        self.assertIn("7zip/7zz", linux)
        self.assertIn("7zip/7zz", macos)
        self.assertIn("VCRUNTIME", windows)
        self.assertNotIn("VCRUNTIME", linux + macos)


class TheLaunchers(unittest.TestCase):
    NAMES = ("Run Mod Manager.sh", "Run Mod Manager.command", "Run Mod Manager (Dev).sh")

    def test_they_are_shell_scripts_with_unix_line_endings(self):
        for name in self.NAMES:
            raw = (ROOT / name).read_bytes()
            self.assertTrue(raw.startswith(b"#!/usr/bin/env bash\n"), name)
            self.assertNotIn(b"\r", raw, name)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", attributes)
        self.assertIn("*.command text eol=lf", attributes)

    def test_the_main_one_makes_the_environment_and_installs_what_changed(self):
        text = (ROOT / "Run Mod Manager.sh").read_text(encoding="utf-8")
        for needle in ('".venv"', "-m venv", "requirements.txt", "pip install", "src/mod_manager.py", "7zz"):
            self.assertIn(needle, text)

    # (Not on Windows: there `bash` can be the WSL launcher in System32, which fails when no distribution is installed - as on the CI
    # runner - and the launchers are for macOS and Linux anyway. The Linux and macOS test runs check them.)
    @unittest.skipIf(sys.platform == "win32", "the launchers are for macOS and Linux; Windows' bash may be only the WSL launcher")
    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_they_have_no_syntax_errors(self):
        for name in self.NAMES:
            done = subprocess.run(["bash", "-n", str(ROOT / name)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")


class TheWorkflows(unittest.TestCase):
    @staticmethod
    def load(name):
        if importlib.util.find_spec("yaml") is None:
            raise unittest.SkipTest("PyYAML is not installed here")
        import yaml
        return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))

    def test_the_tests_run_on_all_three_systems(self):
        matrix = self.load("tests.yml")["jobs"]["tests"]["strategy"]["matrix"]["os"]
        self.assertEqual(sorted(matrix), ["macos-latest", "ubuntu-latest", "windows-latest"])
        self.assertFalse(self.load("tests.yml")["jobs"]["tests"]["strategy"]["fail-fast"])

    def test_only_the_windows_package_can_stop_a_release(self):
        jobs = self.load("release.yml")["jobs"]
        self.assertEqual(sorted(jobs), ["gate", "linux", "macos", "publish", "windows"])
        for name in ("linux", "macos"):
            self.assertEqual(jobs[name]["continue-on-error"], "${{ github.event_name == 'push' }}", name)      # (tolerant on a push, strict on a pull request)
        self.assertFalse(jobs["windows"].get("continue-on-error"))
        self.assertIn("needs.windows.result == 'success'", jobs["publish"]["if"])
        self.assertIn("always()", jobs["publish"]["if"])
        self.assertEqual(sorted(jobs["publish"]["needs"]), ["gate", "linux", "macos", "windows"])

    def test_the_linux_package_is_built_on_the_oldest_supported_ubuntu(self):
        self.assertEqual(self.load("release.yml")["jobs"]["linux"]["runs-on"], "ubuntu-22.04")

    def test_a_manual_run_builds_without_publishing(self):
        jobs = self.load("release.yml")["jobs"]
        self.assertIn("github.event_name == 'push'", jobs["publish"]["if"])

    def test_a_pull_request_builds_every_package_but_can_publish_nothing(self):
        workflow = self.load("release.yml")
        triggers = workflow.get("on") or workflow.get(True)          # (YAML reads a bare `on` as true)
        self.assertIn("pull_request", triggers)
        self.assertIn("tools/**", triggers["pull_request"]["paths"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})        # (only the publish job may write)
        self.assertEqual(workflow["jobs"]["publish"]["permissions"], {"contents": "write"})
        self.assertNotIn("contents", str(workflow["jobs"]["windows"].get("permissions", "")))
        for name in ("windows", "linux", "macos"):
            self.assertNotIn("publish", str(workflow["jobs"][name]).lower().replace("publish the", ""), name)


if __name__ == "__main__":
    unittest.main()
