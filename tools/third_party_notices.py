"""Writes THIRD-PARTY-NOTICES.txt: the notices and license texts of everything other people made that the release contains.

    python tools/third_party_notices.py path/to/THIRD-PARTY-NOTICES.txt

tools/build_release.py runs this with the build environment's Python, so the Python packages' license texts are the ones of the versions that
are really in the release. The texts that do not come from a package (the icons, libffi, Apache-2.0) are in release/licenses/.
The release also carries LICENSE.txt (this app's own license) and _internal/7zip/License.txt (7-Zip's).
"""
import importlib.metadata as metadata
import re
import sys
from pathlib import Path

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
    ("setuptools", "used by the packaged app; it carries the licenses of its own bundled parts in its folder", "MIT", None),
]


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


def rule(title):
    return "\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78 + "\n\n"


def build(strict=True):
    """The text of the notices file. With strict, a package that is missing or has no license text is an error (the build must not ship
    without it); without, it is just left out (the tests run where not every package is installed)."""
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

    out.append(rule("7-Zip - unpacking .rar and .7z downloads (7zip\\7z.exe, 7zip\\7z.dll)"))
    out.append("7-Zip, Copyright (C) 1999-2025 Igor Pavlov (https://www.7-zip.org/), is included unmodified as a separate program that this app\n"
               "runs to unpack downloads. It is licensed under the GNU LGPL, with the unRAR license restriction for its RAR code. The license text\n"
               "is in 7zip\\License.txt (in the _internal folder); 7-Zip's source code is available from https://www.7-zip.org/.\n")

    missing = []
    for name, purpose, spdx, note in PACKAGES:
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
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        out.append(python_license.read_text(encoding="utf-8", errors="replace").strip("\n") + "\n")
    elif strict:
        raise SystemExit(f"Python's LICENSE.txt wasn't found in {sys.base_prefix}")
    else:
        out.append("(Python's license text is added when the release is built)\n")

    out.append(rule("OpenSSL - libcrypto and libssl, part of the Python build (Apache License 2.0)"))
    out.append("Python for Windows includes OpenSSL (https://www.openssl.org/), licensed under the Apache License, version 2.0:\n\n"
               + (LICENSES / "apache-2.0.txt").read_text(encoding="utf-8"))

    out.append(rule("libffi - part of the Python build (MIT)"))
    out.append((LICENSES / "libffi.txt").read_text(encoding="utf-8"))

    out.append(rule("Microsoft Visual C++ runtime (VCRUNTIME140*.dll)"))
    out.append("Redistributed with the program under Microsoft's Visual C++ redistributable terms.\n")
    return "".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    Path(sys.argv[1]).write_text(build(strict=True), encoding="utf-8", newline="\n")
    print("Wrote", sys.argv[1])
