# Linux and macOS (as well as Windows)

The app runs on Windows, Linux and macOS. The code is the same on all three; this page is what differs by system, why, and what has and
has not been tested. (User-facing install steps are in the `README.md`; building each package is in `docs/DEVELOPERS.md`.)

## What differs, and where it is handled

| Thing | How | Where |
| --- | --- | --- |
| The window | Windows: pywebview with WebView2. macOS: pywebview with the system's own WebKit (Cocoa). Linux: **Qt** (PyQt6 + Qt WebEngine, which is Chromium), chosen in `choose_window_library()` *before* anything asks pywebview for the screens (it would otherwise look for Qt 5 and GTK). `MK8DX_GUI` overrides it. | `mod_manager.py`, `requirements.txt` (`pywebview[qt]` on Linux only) |
| Where the app keeps its files | From source: as before (the repository folder). Windows package: the folder holding the `.exe` (portable). **Linux and macOS packages: the user's app-data folder** (`~/.local/share/mk8dx-mod-manager` or `$XDG_DATA_HOME/...`; `~/Library/Application Support/MK8DX Mod Manager`), because the package is a `.app` bundle or a folder that is replaced on update. That folder holds `app-config.json`, the log and the default `data` folder. | `app_paths.APP_ROOT`, `user_data_dir()` |
| 7-Zip | Bundled in every package: `7z.exe` on Windows, the official static `7zz` on Linux/macOS (`tools/fetch_7zip.py`, version and SHA-256 pinned). From source it is found in the usual install folders and on the PATH (Homebrew's folder is looked in explicitly: a `.app` started from Finder has a minimal PATH). | `gamebanana_api.find_7zip()`, `sevenzip_install_hint()` |
| Windows-made archives | A zip made on Windows stores paths with backslashes. Windows (and 7-Zip there) reads them as folders; on Linux/macOS both `7zz` and `zipfile` make ONE file called `Model\Mario.bfres`. After every extraction, `fix_backslash_names()` turns those names into folders (never outside the mod's folder). Checked against the real `7zz` on Linux. | `gamebanana_api.extract_archive()` |
| Folder-name case | Linux is case-sensitive; macOS usually is not but keeps case. The code joins `romfs`/`exefs` onto a mod's folder in about 40 places, and mods made on Windows are often spelled `Romfs`. So `normalize_case()` renames those two folder names to lowercase when a mod is unpacked, and once on every start on macOS/Linux for a data folder that came from Windows (`_normalize_library_case()`). A rename goes through a temporary name (a case-only rename is a rename onto itself on a case-insensitive file system). Other names are looked up case-insensitively (`_ci_child`, `_ci_descend`). | `mod_manager.py` |
| Start-up failure | Windows: a message box. macOS: an `osascript` alert. Linux: `zenity`, `kdialog` or `notify-send` when one is installed. Never raises. | `report_startup_failure()` |
| Launchers | `Run Mod Manager.bat` / `.sh` / `.command` (and `(Dev)` variants): make `.venv`, install `requirements.txt` when it changed, start the app. The shell scripts must keep LF line endings (`.gitattributes`). | repository root |
| Packages | Windows: PyInstaller folder, zipped. Linux: PyInstaller folder with Qt WebEngine and the system libraries it needs copied in (they are installed on the build machine), `tar.gz`, built on Ubuntu 22.04 for glibc 2.35. macOS: PyInstaller `.app`, ad-hoc signed by PyInstaller, zipped with `ditto` (keeps symlinks and permissions), Apple Silicon only. | `tools/mk8dx-mod-manager.spec`, `tools/build_release.py`, `.github/workflows/release.yml` |
| Fonts, example paths | The font stacks name a system font for each system. The game-data guide shows the example paths of the system the page is on (`examplePath()` in `menu-icons-text.js`). | `base.css`, `menu-icons-text.js` |
| Notices | The notices file lists the packages of one system (pythonnet on Windows, Qt on Linux, pyobjc on macOS) - `third_party_notices.build(system=...)`. The Linux one also names the system libraries copied into the package. | `tools/third_party_notices.py` |

## Not signed on macOS

The macOS app is not signed with an Apple developer identity and not notarized (that costs money). PyInstaller signs it ad hoc, which Apple
Silicon needs to run it at all. A copy downloaded with a browser carries a quarantine mark, so macOS asks the user to allow it once
(System Settings > Privacy & Security > Open Anyway, or `xattr -dr com.apple.quarantine`). That is explained in `release/README-macos.md` and the
README. Running from source has no such step. Intel Macs have no download (the `macos-latest` runner is Apple Silicon and an Intel
runner label is not relied on): they run from source.

## Linux notes

- The package does not need system packages beyond what every desktop has (glibc, libGL/EGL, X11 or Wayland): the NSS, NSPR, xcb and xkb
  libraries are copied into it at build time. Running from source needs them installed (`sudo apt install libxcb-cursor0
  libxkbcommon-x11-0 libnss3 libasound2 ...`).
- Qt WebEngine's sandbox can refuse to start on Ubuntu 24.04+ when AppArmor restricts unprivileged user namespaces ("No usable sandbox").
  The README tells the user the `QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox` workaround; the app does not turn the sandbox off by itself.
- The Linux package is x86_64 only (an arm64 build needs an arm64 runner).

## What has been tested

Written and tested on Windows. On Linux it was also exercised in **WSL2 (Ubuntu 24.04, Python 3.12) on a case-sensitive ext4 file system**:

- the whole unit-test suite passes there;
- `Run Mod Manager.sh` from nothing (made `.venv`, installed Qt, started the app); the app's page loaded in Qt WebEngine (drawing offscreen);
- the real `7zz` unpacking a `.7z`, a zip with backslash paths and a zip with no 7-Zip, and the "no 7-Zip" message;
- `tools/build_release.py` built the Linux package; unpacked on its own it passes `--self-check`, starts, keeps its files in
  `~/.local/share/mk8dx-mod-manager`, and its bundled Qt libraries resolve every system library from inside the package.

**Not tested**: macOS at all (the launcher, the window, the `.app` build, the Gatekeeper steps, Homebrew's 7-Zip); an actual Linux desktop
window (X11 or Wayland) and how the page looks in Qt WebEngine or macOS' WebKit compared with WebView2; the release workflow's new jobs
(they have never run on GitHub); `.rar` extraction with `7zz` (no RAR file could be made here); running the Linux package on other
distributions than Ubuntu; the Chromium sandbox on a stock Ubuntu 24.04 desktop; the Eden/Ryujinx example paths shown on Linux and macOS.
