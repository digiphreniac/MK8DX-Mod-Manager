# PyInstaller spec for the Windows release build (folder layout, no console window).
# Run it through tools/build_release.py, which sets up the build environment and finds 7-Zip.
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

# Read-only files the app loads at runtime (see src/app_paths.py - they land under the bundle's
# resource folder, so the code finds them at the same relative paths as when run from source).
datas = [(str(SRC / "ui"), "ui")]
datas += [(str(SRC / name), ".") for name in ("roster.json", "known-shared-files.json", "name-labels.json")]

# 7-Zip's command-line tool, so .rar / .7z mods unpack without the user installing anything.
sevenzip_dir = os.environ.get("MK8DX_7ZIP_DIR")
if sevenzip_dir:
    for name in ("7z.exe", "7z.dll", "License.txt"):
        datas.append((str(Path(sevenzip_dir) / name), "7zip"))

a = Analysis(
    [str(SRC / "mod_manager.py")],
    pathex=[str(SRC)],
    datas=datas,
    excludes=["tkinter", "unittest", "pydoc_data", "test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MK8DX Mod Manager",
    console=False,
    # The icon of the file, the taskbar, alt-tab and the window (pywebview takes the window's icon from the exe). Made by tools/make_icon.py.
    icon=str(ROOT / "tools" / "app-icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="MK8DX Mod Manager",
)
