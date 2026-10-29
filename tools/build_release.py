"""
Builds the release package for the system it runs on (a PyInstaller build cannot be made for another system):

    Windows  dist/MK8DX-Mod-Manager-v<version>-windows.zip
    Linux    dist/MK8DX-Mod-Manager-v<version>-linux-<x86_64|aarch64>.tar.xz   (Qt WebEngine inside; see docs/cross-platform.md)
    macOS    dist/MK8DX-Mod-Manager-v<version>-macos-<arm64|x86_64>.zip         (an unsigned .app)

    python tools/build_release.py             (on Windows also: double-click "Build Release.bat")
    python tools/build_release.py --no-7zip   (skip bundling 7-Zip; .rar/.7z mods then need the user to install it)

What it does: makes a private build environment (.build-venv) with the app's requirements plus
PyInstaller, runs PyInstaller on tools/mk8dx-mod-manager.spec, adds the license, THIRD-PARTY-NOTICES.txt (written by
tools/third_party_notices.py from the build environment's packages) and the readme for the system (release/README.md for Windows,
release/README-linux.md, release/README-macos.md; each is the only readme in the package, not the repository's README.md) to the output
folder, and packs it. 7-Zip's command-line files are copied from this machine's 7-Zip install on Windows (or the folder in
MK8DX_7ZIP_DIR), so install 7-Zip before building there; on Linux and macOS tools/fetch_7zip.py downloads the official `7zz`
(checked against a pinned SHA-256). On Linux install the system libraries Qt WebEngine needs first (the list is in docs/DEVELOPERS.md):
PyInstaller copies the ones it finds into the package, which is what makes it self-contained.

Build with a mainstream Python (3.11-3.13 is the safe range for PyInstaller and pywebview's
dependencies); the release then runs without Python installed.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from version import VERSION   # noqa: E402

BUILD_VENV = ROOT / ".build-venv"
APP_NAME = "MK8DX Mod Manager"
SEVENZIP_FILES = ("7z.exe", "7z.dll", "License.txt")        # (what a Windows 7-Zip install provides)

SYSTEM = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
README_FOR = {"windows": "README.md", "linux": "README-linux.md", "macos": "README-macos.md"}


def arch_name(machine=None):
    """The name of this computer's processor in a package's file name."""
    machine = (machine or platform.machine()).lower()
    if SYSTEM == "macos":
        return "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    return "aarch64" if machine in ("arm64", "aarch64") else "x86_64"


def package_name(version=VERSION, system=None, machine=None):
    """The file name of the finished package, without a folder."""
    system = system or SYSTEM
    if system == "windows":
        return f"MK8DX-Mod-Manager-v{version}-windows.zip"
    if system == "macos":
        return f"MK8DX-Mod-Manager-v{version}-macos-{arch_name(machine)}.zip"
    return f"MK8DX-Mod-Manager-v{version}-linux-{arch_name(machine)}.tar.xz"


def build_python():
    return BUILD_VENV / ("Scripts/python.exe" if SYSTEM == "windows" else "bin/python")


def run(cmd, **kwargs):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def find_sevenzip_dir():
    """Windows: the folder of a 7-Zip install that has the files to bundle."""
    candidates = [os.environ.get("MK8DX_7ZIP_DIR"),
                  os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip"),
                  os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "7-Zip")]
    for folder in candidates:
        if folder and all((Path(folder) / name).is_file() for name in SEVENZIP_FILES):
            return Path(folder)
    return None


def prepare_sevenzip(env):
    """Sets MK8DX_7ZIP_DIR for the spec: this machine's 7-Zip install on Windows, the downloaded `7zz` elsewhere."""
    if SYSTEM == "windows":
        sevenzip = find_sevenzip_dir()
        if sevenzip is None:
            sys.exit("7-Zip (7z.exe, 7z.dll, License.txt) wasn't found. Install it from https://www.7-zip.org/, "
                     "set MK8DX_7ZIP_DIR to its folder, or pass --no-7zip.")
    else:
        import fetch_7zip
        key = fetch_7zip.build_key()
        if key is None:
            sys.exit(f"There is no official 7-Zip build for this system ({sys.platform} / {platform.machine()}); pass --no-7zip.")
        sevenzip = fetch_7zip.fetch(key, ROOT / ".build-cache" / f"7zip-{key}", ROOT / ".build-cache")
    print(f"Bundling 7-Zip from {sevenzip}")
    env["MK8DX_7ZIP_DIR"] = str(sevenzip)


def add_documents(folder: Path, vpy):
    shutil.copy2(ROOT / "LICENSE", folder / "LICENSE.txt")
    # the notices and license texts of everything in the release that is someone else's (the icon set, libraries, 7-Zip, Python ...)
    run([vpy, ROOT / "tools" / "third_party_notices.py", folder / "THIRD-PARTY-NOTICES.txt"])
    shutil.copy2(ROOT / "release" / README_FOR[SYSTEM], folder / "README.md")   # the one readme users get (not the repository's)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-7zip", action="store_true", help="don't bundle 7-Zip")
    args = parser.parse_args()

    env = dict(os.environ)
    env.pop("MK8DX_7ZIP_DIR", None)
    if not args.no_7zip:
        prepare_sevenzip(env)

    vpy = build_python()
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

    archive_path = dist / package_name()
    if SYSTEM == "macos":
        # The .app holds symbolic links and execute permissions that a plain zip loses: ditto keeps them.
        stage = dist / "macos-package" / APP_NAME
        if stage.parent.exists():
            shutil.rmtree(stage.parent)
        stage.mkdir(parents=True)
        shutil.copytree(dist / f"{APP_NAME}.app", stage / f"{APP_NAME}.app", symlinks=True)
        add_documents(stage, vpy)
        archive_path.unlink(missing_ok=True)
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", stage, archive_path])
        shutil.rmtree(stage.parent)
        archive = str(archive_path)
    elif SYSTEM == "linux":
        add_documents(out, vpy)
        archive_path.unlink(missing_ok=True)
        # xz at its strongest: about a third smaller than gzip for this package (Qt WebEngine compresses well), for a few minutes
        # more here and a few seconds more to unpack (docs/cross-platform.md, "Package size"). Keeps execute permissions and links.
        with tarfile.open(archive_path, "w:xz", preset=9) as tar:
            tar.add(out, arcname=APP_NAME)
        archive = str(archive_path)
    else:
        add_documents(out, vpy)
        archive = shutil.make_archive(str(archive_path)[: -len(".zip")], "zip", dist, APP_NAME)
    size_mb = Path(archive).stat().st_size / 1e6
    print(f"\nBuilt {archive} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
