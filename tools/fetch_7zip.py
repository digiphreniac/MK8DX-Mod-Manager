"""Downloads 7-Zip's official command-line program for Linux or macOS, so a release build can carry it (tools/build_release.py runs this).

    python tools/fetch_7zip.py [--dest FOLDER]      prints the folder it put 7zz and License.txt in

The archives come from https://www.7-zip.org/ at a pinned version, and each is checked against the SHA-256 below before anything is
unpacked. Those hashes were taken from the files downloaded from 7-zip.org when this version was pinned (trust on first use: 7-Zip
publishes no signatures of its own for these archives), so a changed file is noticed, but a file that was already wrong then was not. To
move to a newer 7-Zip, change VERSION and the three hashes together. Windows builds use the installed 7-Zip instead (see build_release.py).
"""
import argparse
import hashlib
import platform
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "25.01"
BASE_URL = "https://www.7-zip.org/a/"
# build key -> (file name, SHA-256 of the file, the program inside it to bundle as `7zz`)
BUILDS = {
    "linux-x64": ("7z2501-linux-x64.tar.xz", "4ca3b7c6f2f67866b92622818b58233dc70367be2f36b498eb0bdeaaa44b53f4", "7zzs"),
    "linux-arm64": ("7z2501-linux-arm64.tar.xz", "39c5140f02ce4436599303c59a149f654cb1bbc47cdc105a942120d747ae040d", "7zzs"),
    "mac": ("7z2501-mac.tar.xz", "26aa75bc262bb10bf0805617b95569c3035c2c590a99f7db55c7e9607b2685e0", "7zz"),
}
# (Linux: the statically linked 7zzs, which needs nothing from the system, is what is bundled; it is saved as `7zz`, the name the app looks for.)


def build_key(system=None, machine=None):
    """Which BUILDS entry matches this computer ("linux-x64", "linux-arm64", "mac"), or None for a system there is no build for."""
    system = (system or sys.platform).lower()
    machine = (machine or platform.machine()).lower()
    if system == "darwin":
        return "mac"
    if system.startswith("linux"):
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
        if machine in ("aarch64", "arm64"):
            return "linux-arm64"
    return None


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(key, dest: Path, cache: Path = None) -> Path:
    """Puts 7zz and License.txt for `key` in `dest` (made if needed) and returns it. The download is kept in `cache` (default: next to dest)
    and checked against the pinned hash every time, so a damaged or changed file never gets unpacked."""
    name, expected, program = BUILDS[key]
    cache = cache or dest.parent
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / name
    if not archive.is_file() or sha256_of(archive) != expected:
        print(f"Downloading {BASE_URL}{name}", flush=True)
        request = urllib.request.Request(BASE_URL + name, headers={"User-Agent": "MK8DX-Mod-Manager-build"})
        with urllib.request.urlopen(request, timeout=120) as response, open(archive, "wb") as out:
            out.write(response.read())
    actual = sha256_of(archive)
    if actual != expected:
        archive.unlink(missing_ok=True)
        raise SystemExit(f"{name} doesn't match its pinned SHA-256 (got {actual}, expected {expected}). Not using it.")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as tar:
        for member, target in ((program, "7zz"), ("License.txt", "License.txt")):
            source = tar.extractfile(member)
            if source is None:
                raise SystemExit(f"{name} has no {member}")
            (dest / target).write_bytes(source.read())
    (dest / "7zz").chmod(0o755)
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", type=Path, help="where to put 7zz and License.txt (default: .build-cache/7zip-<build> in the repository)")
    args = parser.parse_args(argv)
    key = build_key()
    if key is None:
        sys.exit(f"There is no official 7-Zip build for {sys.platform} / {platform.machine()}.")
    dest = args.dest or ROOT / ".build-cache" / f"7zip-{key}"
    print(fetch(key, dest, ROOT / ".build-cache"))


if __name__ == "__main__":
    main()
