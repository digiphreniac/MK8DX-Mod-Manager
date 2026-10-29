"""Leaves out of the Linux package the parts of Qt the app never loads (docs/cross-platform.md, "Package size").

PyQt6's wheels hold the whole of Qt, and PyInstaller copies all of it into the package beside Qt WebEngine: Qt Quick and QML,
Quick 3D, Multimedia, PDF, Sensors, every Chromium language, Chromium's developer tools ... The app's window is one QWebEngineView
(pywebview's Qt backend), so most of that is dead weight - over a fifth of the unpacked package. trim() works on PyInstaller's own
lists of what goes into the package (Analysis.binaries and .datas: entries (path in the package, source file, kind)), before
anything is copied:

- A Qt library or plugin goes when nothing kept loads it. What is kept is everything reachable, through each file's linked
  libraries (ldd, as PyInstaller itself collects them), from the Python extension modules PyInstaller found, the other programs
  in the package, Qt WebEngine's helper program and the plugins a desktop needs (KEEP_PLUGIN_DIRS, KEEP_PLATFORMS).
- A system library goes only when something left out needed it and nothing kept does (libcups, for the printing plugin). One
  nothing names at all is always kept: Chromium loads NSS's libsoftokn3 and libfreeblpriv3 by name at run time (dlopen).
- Qt's QML modules (the app has no QML), Qt's own translations (pywebview loads none), Chromium's languages other than en-US
  (it falls back to en-US; the app's page is English) and Chromium's developer tools (the MK8DX_DEBUG window; run from source
  to use them on Linux).
"""
import os

QT = "PyQt6/Qt6/"
# The Qt plugins a Linux desktop needs: the window on X11 or Wayland (offscreen: the release workflow's check), OpenGL on X11,
# Wayland's window decorations and shells, typing (input methods), pictures and icons, the desktop's look and file dialogs
# (platformthemes), TLS for QtNetwork, and network status. Everything else (eglfs, linuxfb, VNC, printing, location, touch
# input ...) is for kiosks, printers and devices the app is never run on.
KEEP_PLUGIN_DIRS = ("xcbglintegrations", "wayland-decoration-client", "wayland-graphics-integration-client", "wayland-shell-integration",
                    "platforminputcontexts", "imageformats", "iconengines", "platformthemes", "tls", "networkinformation")
KEEP_PLATFORMS = ("libqxcb.so", "libqwayland.so", "libqwayland-egl.so", "libqwayland-generic.so", "libqoffscreen.so")
KEEP_LOCALE = "en-US.pak"
DEVTOOLS = QT + "resources/qtwebengine_devtools_resources.pak"


def _is_library(path):
    name = os.path.basename(path)
    return name.endswith(".so") or ".so." in name


def _kept_plugin(dest):
    parts = dest[len(QT):].split("/")
    if parts[0] != "plugins" or len(parts) < 3:
        return False
    if parts[1] == "platforms":
        return parts[2] in KEEP_PLATFORMS
    return parts[1] in KEEP_PLUGIN_DIRS


def unused_data(dest):
    """True for a data file of Qt the app never reads (see the module's docstring)."""
    if not dest.startswith(QT):
        return False
    rest = dest[len(QT):]
    if rest.startswith("qml/"):
        return True
    if rest.startswith("translations/qtwebengine_locales/"):
        return os.path.basename(rest) != KEEP_LOCALE
    if rest.startswith("translations/"):
        return rest.endswith(".qm")
    return dest == DEVTOOLS


def trim(binaries, datas, linked):
    """(binaries, datas, left out) - PyInstaller's two lists without what the app never loads, and the paths left out.
    `linked(source file)` names the libraries a binary loads (their file names)."""
    files = {dest: src for dest, src, kind in binaries if kind != "SYMLINK"}
    links = {dest: target for dest, target, kind in binaries if kind == "SYMLINK"}
    kinds = {dest: kind for dest, _src, kind in binaries}
    by_name = {}
    for dest in list(files) + list(links):
        by_name.setdefault(os.path.basename(dest), []).append(dest)

    def real(dest):
        seen = set()
        while dest in links and dest not in seen:
            seen.add(dest)
            dest = links[dest]
        return dest

    cache = {}

    def needs(dest):
        dest = real(dest)
        if dest not in cache:
            names = linked(files[dest]) if dest in files else []
            cache[dest] = [d for n in names for d in by_name.get(os.path.basename(n), [])] + ([dest] if dest in files else [])
        return cache[dest]

    def reach(roots):
        seen, todo = set(), list(roots)
        while todo:
            d = todo.pop()
            if d in seen:
                continue
            seen.add(d)
            todo.extend(needs(d))
            if d in links:
                todo.append(links[d])
        return seen

    # A system library nothing in the package links to is there because something loads it by name (dlopen - NSS's modules for
    # Chromium): it is kept, with what it needs.
    named = {d for f in files for d in needs(f) if d != real(f)}
    named |= {links[d] for d in links}

    def is_root(dest):
        if dest in links:
            return False   # (only another name for a file: kept when that file is)
        if dest.startswith(QT):
            return dest.startswith(QT + "libexec/") or _kept_plugin(dest)
        if kinds[dest] in ("EXTENSION", "EXECUTABLE") or not _is_library(dest) or os.path.basename(dest).startswith("libpython"):
            return True
        return dest not in named and real(dest) not in named

    kept = reach(d for d in list(files) + list(links) if is_root(d))
    qt_out = {d for d in list(files) + list(links) if d.startswith(QT) and d not in kept and real(d) not in kept}
    gone = qt_out | {d for d in reach(qt_out) - kept if _is_library(d) and real(d) not in kept}   # (only what left-out Qt needed)
    gone |= {d for d, t in links.items() if real(t) in gone}
    new_binaries = [e for e in binaries if e[0] not in gone]
    new_datas = [e for e in datas if not unused_data(e[0])]
    return new_binaries, new_datas, sorted(gone) + sorted(e[0] for e in datas if unused_data(e[0]))
