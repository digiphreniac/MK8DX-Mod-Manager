# PyInstaller spec for the release builds: a Windows folder build (no console window), a Linux folder build with Qt WebEngine inside,
# and a macOS .app bundle. Run it through tools/build_release.py, which sets up the build environment and finds or downloads 7-Zip.
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from version import VERSION  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Read-only files the app loads at runtime (see src/app_paths.py - they land under the bundle's
# resource folder, so the code finds them at the same relative paths as when run from source).
datas = [(str(SRC / "ui"), "ui")]
datas += [(str(SRC / name), ".") for name in ("roster.json", "known-shared-files.json", "name-labels.json")]
binaries = []
hiddenimports = []
excludes = ["tkinter", "unittest", "pydoc_data", "test"]

# 7-Zip's command-line tool, so .rar / .7z mods unpack without the user installing anything. Windows: 7z.exe and its dll from a 7-Zip
# install. Linux and macOS: the `7zz` that tools/fetch_7zip.py downloaded - a program, so it goes in as a binary (PyInstaller then signs
# it with the rest on macOS and keeps its execute permission).
sevenzip_dir = os.environ.get("MK8DX_7ZIP_DIR")
if sevenzip_dir and IS_WINDOWS:
    for name in ("7z.exe", "7z.dll", "License.txt"):
        datas.append((str(Path(sevenzip_dir) / name), "7zip"))
elif sevenzip_dir:
    binaries.append((str(Path(sevenzip_dir) / "7zz"), "7zip"))
    datas.append((str(Path(sevenzip_dir) / "License.txt"), "7zip"))

if IS_LINUX or IS_MAC:
    datas.append((str(ROOT / "tools" / "app-icon.png"), "."))      # (the window's icon on Linux; see window_icon() in mod_manager.py)

if IS_LINUX:
    # The window is Qt (PyQt6 + QtWebEngine, chosen in mod_manager.choose_window_library); pywebview imports it by name at run time,
    # so PyInstaller cannot see it. The system libraries Qt needs (NSS, xcb ...) must be installed where this is built: PyInstaller
    # copies the ones it finds into the package.
    hiddenimports += ["webview.platforms.qt", "qtpy", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtNetwork",
                      "PyQt6.QtWebChannel", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets"]
    excludes += ["PyQt5", "PySide2", "PySide6", "gi"]

a = Analysis(
    [str(SRC / "mod_manager.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
if IS_LINUX and not os.environ.get("MK8DX_NO_TRIM"):
    # PyQt6 brings the whole of Qt; leave out what the app never loads (tools/linux_trim.py). MK8DX_NO_TRIM=1 builds it all, to compare.
    sys.path.insert(0, str(ROOT / "tools"))
    import linux_trim  # noqa: E402
    from PyInstaller.depend import bindepend  # noqa: E402

    def _linked(path):
        # (no fallback: a file whose libraries can't be listed would have them left out, so the build stops instead)
        return [name for name, _full in bindepend.get_imports(path)]

    before = len(a.binaries) + len(a.datas)
    a.binaries, a.datas, _left_out = linux_trim.trim(a.binaries, a.datas, _linked)
    print(f"linux_trim: left out {len(_left_out)} of {before} files Qt brought that the app never loads")
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # (a program name with no spaces on Linux, where it is typed in a terminal)
    name="mk8dx-mod-manager" if IS_LINUX else "MK8DX Mod Manager",
    console=False,
    # The icon of the file, the taskbar, alt-tab and the window (pywebview takes the window's icon from the exe). Made by tools/make_icon.py.
    # Windows only: the macOS app's icon is the BUNDLE's below, and Linux has none on its program (the window's comes from app-icon.png).
    icon=str(ROOT / "tools" / "app-icon.ico") if IS_WINDOWS else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="MK8DX Mod Manager",
)
if IS_MAC:
    # No code-signing identity: PyInstaller signs the bundle ad hoc (which Apple Silicon needs to run it at all). It is not notarized, so a
    # downloaded copy asks the user to allow it once - see docs/cross-platform.md and release/README-macos.md.
    app = BUNDLE(
        coll,
        name="MK8DX Mod Manager.app",
        icon=str(ROOT / "tools" / "app-icon.icns"),
        bundle_identifier="io.github.digiphreniac.mk8dx-mod-manager",
        version=VERSION,
        info_plist={
            "CFBundleName": "MK8DX Mod Manager",
            "CFBundleDisplayName": "MK8DX Mod Manager",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
