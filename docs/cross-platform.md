# Linux and macOS (as well as Windows)

The app runs on Windows, Linux and macOS. The code is the same on all three; this page is what differs by system, why, and what has and
has not been tested. (User-facing install steps are in the `README.md`; building each package is in `docs/DEVELOPERS.md`.)

## What differs, and where it is handled

| Thing | How | Where |
| --- | --- | --- |
| The window | Windows: pywebview with WebView2. macOS: pywebview with the system's own WebKit (Cocoa). Linux: **none** - it serves its page to the user's own browser instead (`docs/browser-mode.md`), which is why the Linux package is about 18 MB rather than 123 MB. `MK8DX_GUI=qt` still opens a pywebview window there for whoever installs `pywebview[qt]` themselves. | `mod_manager.window_library()`, `web_server.py`, `requirements.txt` (no pywebview on Linux) |
| File and folder dialogs | Windows and macOS: the window's own (pywebview). Linux: `zenity`, or `kdialog` on a KDE desktop. Where there is neither, `Api.can_pick_folders()` is false and the page offers a box to type a path into instead of a button that would do nothing. | `host_tools.py`, `settings-panels.js` (`folderPathRow`) |
| Starting another program | Everything that opens a browser or a dialog goes through `host_tools`, which puts back the library search path PyInstaller replaced (`LD_LIBRARY_PATH_ORIG`). Without that, `xdg-open` and the browser it picks load the bundle's libstdc++ and GLib instead of their own and die on a symbol lookup. | `host_tools.original_environ()`, `system_env()` |
| Where the app keeps its files | From source: as before (the repository folder). Windows package: the folder holding the `.exe` (portable). **Linux and macOS packages: the user's app-data folder** (`~/.local/share/mk8dx-mod-manager` or `$XDG_DATA_HOME/...`; `~/Library/Application Support/MK8DX Mod Manager`), because the package is a `.app` bundle or a folder that is replaced on update. That folder holds `app-config.json`, the log and the default `data` folder. | `app_paths.APP_ROOT`, `user_data_dir()` |
| 7-Zip | Bundled in every package: `7z.exe` on Windows, the official static `7zz` on Linux/macOS (`tools/fetch_7zip.py`, version and SHA-256 pinned). From source it is found in the usual install folders and on the PATH (Homebrew's folder is looked in explicitly: a `.app` started from Finder has a minimal PATH). | `gamebanana_api.find_7zip()`, `sevenzip_install_hint()` |
| Windows-made archives | A zip made on Windows stores paths with backslashes. Windows (and 7-Zip there) reads them as folders; on Linux/macOS both `7zz` and `zipfile` make ONE file called `Model\Mario.bfres`. After every extraction, `fix_backslash_names()` turns those names into folders (never outside the mod's folder). Checked against the real `7zz` on Linux. | `gamebanana_api.extract_archive()` |
| Folder-name case | Linux is case-sensitive; macOS usually is not but keeps case. The code joins `romfs`/`exefs` onto a mod's folder in about 40 places, and mods made on Windows are often spelled `Romfs`. So `normalize_case()` renames those two folder names to lowercase when a mod is unpacked, and once on every start on macOS/Linux for a data folder that came from Windows (`_normalize_library_case()`). A rename goes through a temporary name (a case-only rename is a rename onto itself on a case-insensitive file system). Other names are looked up case-insensitively (`_ci_child`, `_ci_descend`). | `mod_manager.py` |
| Start-up failure | Windows: a message box. macOS: an `osascript` alert. Linux: `zenity`, `kdialog` or `notify-send` when one is installed. Never raises. | `report_startup_failure()` |
| Launchers | `Run Mod Manager.bat` / `.sh` / `.command` (and `(Dev)` variants): make `.venv`, install `requirements.txt` when it changed, start the app. The shell scripts must keep LF line endings (`.gitattributes`). | repository root |
| Packages | Windows: PyInstaller folder, zipped. Linux: PyInstaller folder with every web view excluded (the spec stops the build if one is collected anyway), `tar.xz`, built on Ubuntu 22.04 for glibc 2.35 - it needs nothing installed on the build machine. macOS: PyInstaller `.app`, ad-hoc signed by PyInstaller, zipped with `ditto` (keeps symlinks and permissions), Apple Silicon only. | `tools/mk8dx-mod-manager.spec`, `tools/build_release.py`, `.github/workflows/release.yml` |
| Fonts, example paths | The font stacks name a system font for each system. The game-data guide shows the example paths of the system the page is on (`examplePath()` in `menu-icons-text.js`). | `base.css`, `menu-icons-text.js` |
| Notices | The notices file lists the packages of one system (pythonnet on Windows, pyobjc on macOS; the Linux one has neither those nor pywebview, and says that no browser is included) - `third_party_notices.build(system=...)`. | `tools/third_party_notices.py` |
| HTTPS to GameBanana | Every request passes an explicit `ssl.SSLContext` built from certifi's CA bundle. Without it, a packaged **macOS** build failed every request with `CERTIFICATE_VERIFY_FAILED`: its Python has no system trust store, and OpenSSL's compiled-in default verify path is a folder on whatever machine built it, which doesn't exist on the end user's Mac. Windows (schannel) and Linux (`/etc/ssl/certs`, present on the systems the package targets) didn't show this, but the explicit context is used everywhere for one code path. | `gamebanana_api._ssl_context()`, `requirements.txt` (`certifi`) |

## Not signed on macOS

The macOS app is not signed with an Apple developer identity and not notarized (that costs money). PyInstaller signs it ad hoc, which Apple
Silicon needs to run it at all. A copy downloaded with a browser carries a quarantine mark, so macOS asks the user to allow it once
(System Settings > Privacy & Security > Open Anyway, or `xattr -dr com.apple.quarantine`). That is explained in `release/README-macos.md` and the
README. Running from source has no such step. Intel Macs have no download (the `macos-latest` runner is Apple Silicon and an Intel
runner label is not relied on): they run from source.

## Linux notes

- The package needs nothing installed beyond glibc 2.35 or newer and a browser. It carries no web view, so the NSS/xcb/xkb/GTK
  list that used to be here - and the Chromium "No usable sandbox" workaround on Ubuntu 24.04+ - are both gone.
- `zenity` or `kdialog` gives the app your desktop's folder picker. Without one it still works: the page offers a box to type a
  path into (`Api.can_pick_folders()`, `folderPathRow` in `settings-panels.js`).
- The Linux package is x86_64 only (an arm64 build needs an arm64 runner) - though with no Qt wheels involved, an arm64 build
  would now be a much smaller problem than it was.

## Package size

Windows and macOS lend the app their own web view (WebView2, WebKit), so their packages are about 20 MB. Linux has none to lend.
Carrying one meant carrying Qt WebEngine, which is Chromium, and that set the floor for the whole package:

| Linux package | download | unpacked |
| --- | --- | --- |
| 0.4.2 - Qt WebEngine, gzip | 211 MB | 597 MB |
| 0.4.3 development - Qt trimmed (`tools/linux_trim.py`), xz | 123 MB | 417 MB |
| **now - no web view, the page goes to the user's browser** | **18 MB** | **49 MB** |

Trimming Qt had already taken out everything that could go (QML modules, translations, Chromium's other languages and its
developer tools), and what was left could not be made smaller: `libQt6WebEngineCore.so.6` was 194 MB on its own, already
stripped, 169 MB of it executable code, and `libicudata.so.73` another 31 MB. Nor could more of Qt be dropped - Qt WebEngine is
built on Qt Quick, so `libQt6WebEngineWidgets` links `Quick`, `QuickWidgets`, `Qml`, `QmlModels`, `QmlMeta`, `QmlWorkerScript`,
`OpenGL`, `Positioning` and `PrintSupport` directly. About 120 MB was the floor for a packaged Qt window.

Browser mode has no such floor, because the browser is already on the machine: `docs/browser-mode.md`. `tools/linux_trim.py` and
its tests went with Qt (they are in the history if a Qt package is ever wanted again). What is left is mostly Pillow and its
bundled picture libraries (19 MB, of which `libavif` is 4.7 MB), Python itself (11 MB) and the bundled `7zz` (3.6 MB). **xz
instead of gzip** stays, and now costs seconds rather than minutes.

## What has been tested

Written and tested on Windows. On Linux it was also exercised in **WSL2 (Ubuntu 24.04, Python 3.12) on a case-sensitive ext4 file system**:

- the whole unit-test suite passes there;
- `Run Mod Manager.sh` from nothing (made `.venv`, installed the requirements, started the app);
- the real `7zz` unpacking a `.7z`, a zip with backslash paths and a zip with no 7-Zip, and the "no 7-Zip" message;
- `tools/build_release.py` built the Linux package; unpacked on its own it passes `--self-check`, starts and keeps its files in
  `~/.local/share/mk8dx-mod-manager`.

It was also built and run in a **real Ubuntu 22.04 x86_64 container** (Docker on an Apple Silicon Mac, under QEMU emulation),
back when the package carried Qt - that caught a real bug, `libXdamage.so.1` missing from the Linux job's `apt-get install` list,
which made the packaged app crash on startup outside `--self-check`'s offscreen mode. That whole class of problem is gone with Qt
itself: the package now links nothing but glibc and what Python needs.

### Browser mode, on a real Fedora 43 desktop (GNOME/Wayland, Python 3.14)

This is the first time any of it has been checked on a real Linux desktop with a real display rather than Xvfb or an emulated
container:

- the whole unit-test suite passes (535 tests, including `tests/test_web_server.py` - a real server on a real loopback socket);
- `tools/build_release.py` built the package: **18 MB**, 49 MB unpacked, and the spec's guard confirms no web view is in it;
- the packaged app passes `--self-check` (which now also checks it can listen on 127.0.0.1 and finds a folder picker);
- the packaged app, run from a terminal, served its page and **opened it in the user's real Firefox 152**; the page's own
  `page-start` line reached the log, so the scripts ran and called back into Python over the bridge;
- the same page loaded and painted in **headless Chromium 150** (screenshot taken after its startup calls had settled): the
  first-run Data-folder step renders correctly, with "Change folder…" and the new "Or paste a path instead" row;
- **with `zenity` and `kdialog` both off the PATH**, `can_pick_folders()` goes false and the page drops the button and opens the
  typed-path box instead - checked by screenshot;
- the lifecycle: the app quit 7 seconds after the browser closed ("stopping: the page was closed"), and `_Lifecycle` is unit-tested
  on a fake clock for the heartbeat, the reload grace period and never quitting mid-call.

Before browser mode, the same machine ran the **Qt package** (123 MB) once as a comparison: it started as a native Wayland client
and its page loaded, so the Qt build was working - it was simply seven times the size.

On an Apple Silicon Mac (Homebrew Python 3.12, `/opt/homebrew/bin/7zz` already on the PATH):


- the whole unit-test suite passes there;
- `Run Mod Manager.command`/running from source starts the app, finds the existing `7zz`, and loads the page in the system WebKit view;
- `tools/build_release.py` built the macOS package; the unpacked `.app` passes `--self-check`, and `hook-certifi.py` bundles
  `certifi`'s `cacert.pem` into `Contents/Resources/certifi/` as expected;
- the HTTPS fix (`gamebanana_api._ssl_context()`) was checked against the real GameBanana API with the default trust store
  deliberately broken (`SSL_CERT_FILE`/`SSL_CERT_DIR` pointed at nonexistent paths): without a context the handshake fails with
  `CERTIFICATE_VERIFY_FAILED`, exactly the error a user hit running a GitHub Actions-built package; with `_ssl_context()` it succeeds.

**Not tested on macOS**: the Gatekeeper/quarantine steps on a package actually downloaded with a browser; the real window's look
compared with WebView2; a full browse-and-download-a-mod run through the packaged `.app` (only the HTTPS handshake itself, not the
whole GameBanana flow, was exercised against the packaged build's bundled `certifi` data); the release workflow's GitHub-hosted
`macos-latest` runner itself (its Python is a different build than Homebrew's, which is what produced the original bug - see above).

**Not tested at all**: a full browse-download-commit run through the packaged Linux build (only that the page loads and talks to
Python); the `zenity`/`kdialog` dialogs actually opening and returning a path (only that they are found, and that the page falls
back correctly when they are not); `kdialog` on a KDE desktop at all; `.rar` extraction with `7zz` (no RAR file could be made
here); running the Linux package on distributions other than Fedora 43 and Ubuntu; the Eden/Ryujinx example paths shown on Linux
and macOS; how the page looks in a browser other than Firefox and Chromium.
