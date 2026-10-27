"""Writes THIRD-PARTY-NOTICES.txt: the notices and license texts of everything other people made that the release contains.

    python tools/third_party_notices.py path/to/THIRD-PARTY-NOTICES.txt

tools/build_release.py runs this with the build environment's Python, so the Python packages' license texts are the ones of the versions that
are really in the release. The texts that do not come from a package (the icons, libffi, Apache-2.0) are in release/licenses/.
The release also carries LICENSE.txt (this app's own license) and _internal/7zip/License.txt (7-Zip's).

The packages differ by system (pythonnet on Windows, Qt on Linux, pyobjc on macOS): build(system=...) writes the notices for one of them,
by default the system this runs on.
"""
import importlib.metadata as metadata
import re
import sys
from pathlib import Path

SYSTEMS = ("windows", "linux", "macos")

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ROOT / "release" / "licenses"

# (package on PyPI, what it is for, license as the package says, where its license file is not in the package: what to say instead)
PACKAGES = [
    ("pywebview", "the app's window and the bridge between the page and Python", "BSD-3-Clause", None),
    ("pillow", "reading and writing pictures", "MIT-CMU (HPND)", None),
    ("bottle", "pywebview's local web server", "MIT", None),
    ("proxy_tools", "used by pywebview", "MIT",
     "Author: Jonathan Tushman (https://github.com/jtushman/proxy_tools). The package declares the MIT license but ships no license file."),
    ("pythonnet", "pywebview's link to Windows' .NET (WebView2)", "MIT", None),
    ("clr_loader", "used by pythonnet", "MIT", None),
    ("cffi", "used by pywebview's dependencies", "MIT", None),
    ("pycparser", "used by cffi", "BSD-3-Clause", None),
    ("typing_extensions", "used by pywebview", "PSF-2.0", None),
    ("certifi", "a root-certificate bundle, used to verify HTTPS connections to GameBanana", "MPL-2.0", None),
    ("setuptools", "used by the packaged app; it carries the licenses of its own bundled parts in its folder", "MIT", None),
    # Linux: the window is Qt (PyQt6 and QtWebEngine - the GPL-3.0 bindings; the Qt libraries themselves are LGPL-3.0)
    ("PyQt6", "the Linux window: Python bindings for Qt 6", "GPL-3.0-only", None),
    ("PyQt6-Qt6", "the Qt 6 libraries inside PyQt6", "LGPL-3.0", None),
    ("PyQt6-sip", "used by PyQt6", "BSD-2-Clause", None),
    ("PyQt6-WebEngine", "the Linux window's web view: Python bindings for Qt WebEngine", "GPL-3.0-only", None),
    ("PyQt6-WebEngine-Qt6", "Qt WebEngine (Chromium) and its libraries", "LGPL-3.0 and others (see below)", None),
    ("QtPy", "lets pywebview use PyQt6", "MIT", None),
    # macOS: the window is the system's own WebKit, reached through pyobjc
    ("pyobjc-core", "pywebview's link to macOS", "MIT",
     "pyobjc (https://github.com/ronaldoussoren/pyobjc), MIT license, Copyright (c) 2002-2026 Ronald Oussoren, Bill Bumgarner, Steve Majewski, "
     "Lele Gaifax and contributors."),
    ("pyobjc-framework-Cocoa", "pywebview's link to macOS", "MIT", "pyobjc (https://github.com/ronaldoussoren/pyobjc), MIT license; see pyobjc-core above."),
    ("pyobjc-framework-Quartz", "pywebview's link to macOS", "MIT", "pyobjc (https://github.com/ronaldoussoren/pyobjc), MIT license; see pyobjc-core above."),
    ("pyobjc-framework-WebKit", "pywebview's link to macOS' web view", "MIT", "pyobjc (https://github.com/ronaldoussoren/pyobjc), MIT license; see pyobjc-core above."),
    ("pyobjc-framework-Security", "pywebview's link to macOS", "MIT", "pyobjc (https://github.com/ronaldoussoren/pyobjc), MIT license; see pyobjc-core above."),
]
# Packages that are in the release of one system only (every other package is in all of them).
SYSTEM_ONLY = {
    "windows": {"pythonnet", "clr_loader", "cffi", "pycparser"},
    "linux": {"PyQt6", "PyQt6-Qt6", "PyQt6-sip", "PyQt6-WebEngine", "PyQt6-WebEngine-Qt6", "QtPy"},
    "macos": {"pyobjc-core", "pyobjc-framework-Cocoa", "pyobjc-framework-Quartz", "pyobjc-framework-WebKit", "pyobjc-framework-Security"},
}


def current_system():
    return "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"


def packages_for(system):
    """The PACKAGES entries that are in the release for `system`."""
    other = set().union(*(names for key, names in SYSTEM_ONLY.items() if key != system))
    return [entry for entry in PACKAGES if entry[0] not in other]


def license_files(name):
    """[(file name, text)] of the license files inside an installed package's metadata, or [] when it is not installed / has none."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    found = []
    for f in dist.files or []:
        if "dist-info" in str(f) and re.search(r"licen[cs]e|copying|notice", f.name, re.I) and "_vendor" not in str(f):
            found.append((f.name, Path(f.locate()).read_text(encoding="utf-8", errors="replace")))
    return found


def python_license_candidates():
    """Where Python's own license text can be: the root of a Windows install, or the standard library's folder elsewhere."""
    import sysconfig
    yield Path(sys.base_prefix) / "LICENSE.txt"
    stdlib = sysconfig.get_paths().get("stdlib")
    if stdlib:
        yield Path(stdlib) / "LICENSE.txt"
    yield Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt"


def rule(title):
    return "\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78 + "\n\n"


def build(strict=True, system=None):
    """The text of the notices file for `system` (default: this one). With strict, a package that is missing or has no license text is an
    error (the build must not ship without it); without, it is just left out (the tests run where not every package is installed)."""
    system = system or current_system()
    out = [
        "THIRD-PARTY NOTICES\n\n"
        "MK8DX Mod Manager is free software, licensed under the GNU General Public License, version 3 or (at your option) any later version\n"
        "(see LICENSE.txt). It contains, or is built with, the work of others, listed here with the notices their licenses ask for.\n"
        "The program was written with the help of an AI coding assistant (Claude Code, by Anthropic), under the author's direction and review.\n",
    ]

    out.append(rule("Tabler Icons - the app's icons"))
    out.append("Tabler Icons (https://tabler.io/icons), outline icons, version 3.49.0. Used under the MIT license:\n\n"
               + (LICENSES / "tabler-icons.txt").read_text(encoding="utf-8"))

    out.append(rule("BNTX Editor - Nintendo .bntx texture packing (src/_bntx_structs.py)"))
    out.append("src/_bntx_structs.py is taken, unmodified, from BNTX Editor by AboodXD (https://github.com/aboood40091/BNTX-Editor),\n"
               "Copyright (c) 2018 AboodXD, licensed under the GNU General Public License, version 3 or later. This program is\n"
               "distributed under the same license (LICENSE.txt), and its complete source code is at\n"
               "https://github.com/digiphreniac/MK8DX-Mod-Manager\n")

    if system == "windows":
        out.append(rule("7-Zip - unpacking .rar and .7z downloads (7zip\\7z.exe, 7zip\\7z.dll)"))
        out.append("7-Zip, Copyright (C) 1999-2025 Igor Pavlov (https://www.7-zip.org/), is included unmodified as a separate program that this app\n"
                   "runs to unpack downloads. It is licensed under the GNU LGPL, with the unRAR license restriction for its RAR code. The license text\n"
                   "is in 7zip\\License.txt (in the _internal folder); 7-Zip's source code is available from https://www.7-zip.org/.\n")
    else:
        out.append(rule("7-Zip - unpacking .rar and .7z downloads (7zip/7zz)"))
        out.append("7-Zip, Copyright (C) 1999-2025 Igor Pavlov (https://www.7-zip.org/), is included unmodified as a separate program (the official\n"
                   "command-line build, 7zz) that this app runs to unpack downloads. It is licensed under the GNU LGPL, with the unRAR license\n"
                   "restriction for its RAR code. The license text is in 7zip/License.txt (with the program's libraries); 7-Zip's source code is\n"
                   "available from https://www.7-zip.org/.\n")
    if system == "linux":
        out.append(rule("Qt 6 and Qt WebEngine - the Linux window"))
        out.append("The window on Linux is Qt 6 (the LGPL-3.0 libraries from the PyQt6-Qt6 and PyQt6-WebEngine-Qt6 packages, listed below with their\n"
                   "licenses), shown through PyQt6 (GPL-3.0, like this program). The Qt libraries are in this folder as separate files that the\n"
                   "program loads, so you can replace them with your own build of Qt. Qt's source code is at https://download.qt.io/ and\n"
                   "https://code.qt.io/. Qt WebEngine is built on Chromium and contains code under other licenses, listed at\n"
                   "https://doc.qt.io/qt-6/qtwebengine-attribution.html.\n\n"
                   "The package also carries a few system libraries copied from the machine that built it, so that it runs without installing them\n"
                   "(NSS and NSPR, MPL-2.0 or GPL/LGPL; libxcb and its helper libraries and libxkbcommon/libxkbfile, MIT/X11). Their source code is\n"
                   "available from the distribution that built the package (for Ubuntu: https://packages.ubuntu.com/) and from the projects'\n"
                   "own sites (https://www.mozilla.org/projects/security/pki/nss/, https://xcb.freedesktop.org/).\n")

    missing = []
    for name, purpose, spdx, note in packages_for(system):
        files = license_files(name)
        out.append(rule(f"{name} - {purpose} ({spdx})"))
        if files:
            for fname, text in files:
                out.append(text.strip("\n") + "\n\n")
        elif note:
            out.append(note + "\n")
        else:
            missing.append(name)
            out.append("(license text not available in this environment)\n")
    if strict and missing:
        raise SystemExit("No license text found for: " + ", ".join(missing) + ". Install the build requirements first.")

    out.append(rule("Python - the interpreter inside the app (Python Software Foundation License)"))
    python_license = next((p for p in python_license_candidates() if p.is_file()), None)
    if python_license is not None:
        out.append(python_license.read_text(encoding="utf-8", errors="replace").strip("\n") + "\n")
    elif strict:
        raise SystemExit(f"Python's LICENSE.txt wasn't found in {sys.base_prefix}")
    else:
        out.append("(Python's license text is added when the release is built)\n")

    out.append(rule("OpenSSL - libcrypto and libssl, part of the Python build (Apache License 2.0)"))
    out.append("The Python build includes or links OpenSSL (https://www.openssl.org/), licensed under the Apache License, version 2.0:\n\n"
               + (LICENSES / "apache-2.0.txt").read_text(encoding="utf-8"))

    out.append(rule("libffi - part of the Python build (MIT)"))
    out.append((LICENSES / "libffi.txt").read_text(encoding="utf-8"))

    if system == "windows":
        out.append(rule("Microsoft Visual C++ runtime (VCRUNTIME140*.dll)"))
        out.append("Redistributed with the program under Microsoft's Visual C++ redistributable terms.\n")
    return "".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    Path(sys.argv[1]).write_text(build(strict=True), encoding="utf-8", newline="\n")
    print("Wrote", sys.argv[1])
