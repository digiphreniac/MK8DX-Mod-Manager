"""
Builds the Windows release: dist/MK8DX-Mod-Manager-v<version>-windows.zip

    python tools/build_release.py             (or double-click "Build Release.bat")
    python tools/build_release.py --no-7zip   (skip bundling 7-Zip; .rar/.7z mods then need the user to install it)

What it does: makes a private build environment (.build-venv) with the app's requirements plus
PyInstaller, runs PyInstaller on tools/mk8dx-mod-manager.spec, adds the license, THIRD-PARTY-NOTICES.txt (written by
tools/third_party_notices.py from the build environment's packages) and release/README.md (the only readme in the
zip; it is not the repository's README.md) to the output folder, and zips it.
7-Zip's command-line files are copied from this machine's 7-Zip install (or the folder in
MK8DX_7ZIP_DIR), so install 7-Zip before building.

Build with a mainstream Python (3.11-3.13 is the safe range for PyInstaller and pywebview's
dependencies); the release then runs on any Windows 10/11 machine with no Python installed.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from version import VERSION   # noqa: E402

BUILD_VENV = ROOT / ".build-venv"
APP_NAME = "MK8DX Mod Manager"
SEVENZIP_FILES = ("7z.exe", "7z.dll", "License.txt")


def run(cmd, **kwargs):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def find_sevenzip_dir():
    candidates = [os.environ.get("MK8DX_7ZIP_DIR"),
                  os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip"),
                  os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "7-Zip")]
    for folder in candidates:
        if folder and all((Path(folder) / name).is_file() for name in SEVENZIP_FILES):
            return Path(folder)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-7zip", action="store_true", help="don't bundle 7-Zip")
    args = parser.parse_args()

    env = dict(os.environ)
    env.pop("MK8DX_7ZIP_DIR", None)
    if not args.no_7zip:
        sevenzip = find_sevenzip_dir()
        if sevenzip is None:
            sys.exit("7-Zip (7z.exe, 7z.dll, License.txt) wasn't found. Install it from https://www.7-zip.org/, "
                     "set MK8DX_7ZIP_DIR to its folder, or pass --no-7zip.")
        print(f"Bundling 7-Zip from {sevenzip}")
        env["MK8DX_7ZIP_DIR"] = str(sevenzip)

    vpy = BUILD_VENV / "Scripts" / "python.exe"
    if not vpy.is_file():
        run([sys.executable, "-m", "venv", BUILD_VENV])
    run([vpy, "-m", "pip", "install", "--disable-pip-version-check", "-r", ROOT / "requirements.txt", "pyinstaller"])

    dist = ROOT / "dist"
    work = ROOT / "build"
    out = dist / APP_NAME
    if out.exists():
        shutil.rmtree(out)
    run([vpy, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", dist, "--workpath", work,
         ROOT / "tools" / "mk8dx-mod-manager.spec"], env=env, cwd=ROOT)

    shutil.copy2(ROOT / "LICENSE", out / "LICENSE.txt")
    # the notices and license texts of everything in the release that is someone else's (the icon set, libraries, 7-Zip, Python ...)
    run([vpy, ROOT / "tools" / "third_party_notices.py", out / "THIRD-PARTY-NOTICES.txt"])
    shutil.copy2(ROOT / "release" / "README.md", out / "README.md")   # the one readme users get (not the repository's)

    archive = shutil.make_archive(str(dist / f"MK8DX-Mod-Manager-v{VERSION}-windows"), "zip", dist, APP_NAME)
    size_mb = Path(archive).stat().st_size / 1e6
    print(f"\nBuilt {archive} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
