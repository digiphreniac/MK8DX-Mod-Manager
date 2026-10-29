"""The Linux package leaves out the parts of Qt the app never loads (tools/linux_trim.py, docs/cross-platform.md "Package size"), and
nothing the app does load. Run on a made-up package: what each file links is given by hand, as ldd would list it.

Run from the repo root:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import linux_trim  # noqa: E402

Q = "PyQt6/Qt6/"
LINKS = {   # source file -> the libraries it loads
    "PyQt6/QtWebEngineWidgets.abi3.so": ["libQt6WebEngineWidgets.so.6", "libQt6Core.so.6"],
    Q + "lib/libQt6WebEngineWidgets.so.6": ["libQt6WebEngineCore.so.6", "libQt6Core.so.6"],
    Q + "lib/libQt6WebEngineCore.so.6": ["libQt6Core.so.6", "libnss3.so", "libQt6Positioning.so.6"],
    Q + "lib/libQt6Core.so.6": ["libicudata.so.73"],
    Q + "lib/libQt6Positioning.so.6": [],
    Q + "lib/libQt6Quick3D.so.6": ["libQt6Core.so.6", "libpulse.so.0"],
    Q + "lib/libQt6Multimedia.so.6": ["libQt6Core.so.6", "libpulse.so.0"],
    Q + "plugins/platforms/libqxcb.so": ["libQt6XcbQpa.so.6"],
    Q + "lib/libQt6XcbQpa.so.6": ["libQt6Core.so.6", "libxcb.so.1"],
    Q + "plugins/platforms/libqvnc.so": ["libQt6Core.so.6"],
    Q + "plugins/printsupport/libcupsprintersupport.so": ["libcups.so.2"],
    Q + "plugins/platformthemes/libqgtk3.so": ["libgtk-3.so.0"],
    Q + "libexec/QtWebEngineProcess": ["libQt6WebEngineCore.so.6"],
    "libnss3.so": [], "libicudata.so.73": [], "libpulse.so.0": [], "libxcb.so.1": [], "libgtk-3.so.0": [],
    "libcups.so.2": ["libgnutls.so.30"], "libgnutls.so.30": [],
    "nss/libsoftokn3.so": ["libsqlite3.so.0"],   # (loaded by name at run time: nothing links it)
    "libsqlite3.so.0": [],
    "7zip/7zz": [],
}


def toc():
    binaries = [(dest, dest, "EXTENSION" if dest.endswith(".abi3.so") else "BINARY") for dest in LINKS]
    binaries.append(("libQt6Core.so.6", Q + "lib/libQt6Core.so.6", "SYMLINK"))          # (PyInstaller's top-level aliases)
    binaries.append(("libQt6Quick3D.so.6", Q + "lib/libQt6Quick3D.so.6", "SYMLINK"))
    datas = [(Q + "translations/qtwebengine_locales/" + n, "x", "DATA") for n in ("en-US.pak", "de.pak", "fr.pak")]
    datas += [(Q + "translations/qtbase_de.qm", "x", "DATA"), (Q + "qml/QtQuick/qmldir", "x", "DATA"),
              (Q + "resources/qtwebengine_devtools_resources.pak", "x", "DATA"), (Q + "resources/qtwebengine_resources.pak", "x", "DATA"),
              (Q + "resources/icudtl.dat", "x", "DATA"), ("ui/index.html", "x", "DATA")]
    return binaries, datas


class Trim(unittest.TestCase):
    def setUp(self):
        binaries, datas = toc()
        self.binaries, self.datas, self.left_out = linux_trim.trim(binaries, datas, lambda src: LINKS.get(src, []))
        self.kept = {d for d, _s, _k in self.binaries} | {d for d, _s, _k in self.datas}

    def test_what_the_web_view_needs_stays(self):
        for dest in (Q + "lib/libQt6WebEngineCore.so.6", Q + "lib/libQt6WebEngineWidgets.so.6", Q + "lib/libQt6Core.so.6",
                     Q + "lib/libQt6Positioning.so.6", Q + "libexec/QtWebEngineProcess", "libnss3.so", "libicudata.so.73",
                     "libQt6Core.so.6", Q + "resources/qtwebengine_resources.pak", Q + "resources/icudtl.dat", "7zip/7zz"):
            self.assertIn(dest, self.kept, dest)

    def test_the_desktop_plugins_stay_with_what_they_need(self):
        for dest in (Q + "plugins/platforms/libqxcb.so", Q + "lib/libQt6XcbQpa.so.6", "libxcb.so.1",
                     Q + "plugins/platformthemes/libqgtk3.so", "libgtk-3.so.0"):
            self.assertIn(dest, self.kept, dest)

    def test_qt_the_app_never_loads_goes_with_its_aliases(self):
        for dest in (Q + "lib/libQt6Quick3D.so.6", Q + "lib/libQt6Multimedia.so.6", "libQt6Quick3D.so.6",
                     Q + "plugins/platforms/libqvnc.so", Q + "plugins/printsupport/libcupsprintersupport.so"):
            self.assertNotIn(dest, self.kept, dest)

    def test_a_system_library_goes_only_when_just_left_out_qt_needed_it(self):
        self.assertNotIn("libpulse.so.0", self.kept)       # (only Quick 3D and Multimedia)
        self.assertNotIn("libcups.so.2", self.kept)        # (only the printing plugin)
        self.assertNotIn("libgnutls.so.30", self.kept)     # (only libcups)

    def test_a_library_loaded_by_name_stays_with_what_it_needs(self):
        self.assertIn("nss/libsoftokn3.so", self.kept)
        self.assertIn("libsqlite3.so.0", self.kept)

    def test_unused_data_goes_and_english_stays(self):
        loc = Q + "translations/qtwebengine_locales/"
        self.assertIn(loc + "en-US.pak", self.kept)
        for dest in (loc + "de.pak", loc + "fr.pak", Q + "translations/qtbase_de.qm", Q + "qml/QtQuick/qmldir",
                     Q + "resources/qtwebengine_devtools_resources.pak"):
            self.assertNotIn(dest, self.kept, dest)
        self.assertIn("ui/index.html", self.kept)

    def test_it_says_what_it_left_out(self):
        self.assertIn(Q + "lib/libQt6Quick3D.so.6", self.left_out)
        self.assertEqual(len(self.left_out), len(set(self.left_out)))


class TheSpec(unittest.TestCase):
    def test_the_linux_build_trims_and_can_be_told_not_to(self):
        spec = (ROOT / "tools" / "mk8dx-mod-manager.spec").read_text(encoding="utf-8")
        self.assertIn("linux_trim.trim(a.binaries, a.datas", spec)
        self.assertIn('if IS_LINUX and not os.environ.get("MK8DX_NO_TRIM")', spec)


if __name__ == "__main__":
    unittest.main()
