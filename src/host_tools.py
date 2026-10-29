"""Programs of the system the app asks for things a window would otherwise give it: the user's browser and
file/folder dialogs.

Needed because the Linux package has no window of its own - it serves its page to the user's browser
(docs/browser-mode.md), so the three native dialogs (`pick_master_dir`, the mod list's Save and Open) cannot
come from pywebview. They come from `zenity` or `kdialog` here instead.

`system_env()` is the other half, and matters to every program the app starts, window or no window: a
PyInstaller build runs with LD_LIBRARY_PATH (DYLD_LIBRARY_PATH on macOS) pointing at the bundle's own
copies of glibc's neighbours - libstdc++, GLib, OpenSSL and, in the old Qt package, the whole of Qt. A
program started from inside that build inherits the variable and loads OUR libraries instead of its own,
which is how `xdg-open` or Firefox ends up dying with a symbol-lookup error. PyInstaller keeps what the
variable was in <NAME>_ORIG for exactly this; `system_env()` puts it back.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import webbrowser

import diag

# The search paths PyInstaller's bootloader points at the bundle. It saves what each one was in <NAME>_ORIG -
# and leaves no _ORIG at all when the variable was unset before, in which case it has to go again.
_BUNDLE_VARS = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES", "LIBPATH")
DIALOG_TIMEOUT = 15 * 60        # a dialog waits on a person; long, but not for ever (a lost process would hang the call)


def original_environ(environ=None, frozen=None):
    """A copy of the environment as it was before PyInstaller changed it, for a program we start.
    (The arguments are for the tests.)"""
    source = os.environ if environ is None else environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    env = dict(source)
    for name in _BUNDLE_VARS:
        was = env.pop(name + "_ORIG", None)
        if was is not None:
            env[name] = was            # it had a value of its own: put it back
        elif frozen:
            env.pop(name, None)        # no _ORIG in a frozen build: it was unset, and what is there now is ours
    return env


@contextlib.contextmanager
def system_env():
    """Runs the block with the environment a program of the system expects (see original_environ). For code that
    starts something without letting us pass an environment - `webbrowser.open()`."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(original_environ(saved))
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def open_browser(url):
    """Opens a link in the user's own browser. True if one took it; the reason goes to the log if not.

    Everything that opens a link goes through here, so it happens with the system's environment and not the
    bundle's (see the module docstring): started with ours, `xdg-open` or the browser it picks loads our
    libstdc++ and GLib instead of its own and dies on a symbol lookup."""
    try:
        with system_env():
            return bool(webbrowser.open(url))
    except (OSError, webbrowser.Error) as e:
        diag.log("browser", f"couldn't open {url.split('://')[0]}://...: {type(e).__name__}: {e}")
        return False


def _tool(name):
    """The full path of a system program, looked up with the system's own PATH (not the bundle's)."""
    return shutil.which(name, path=original_environ().get("PATH"))


def dialog_tool():
    """Which dialog program this system has: "zenity", "kdialog", "osascript" (macOS) or None."""
    if sys.platform == "darwin":
        return "osascript" if _tool("osascript") else None
    if sys.platform == "win32":
        return None          # (Windows always has a pywebview window; it never comes here)
    # KDE first on a KDE desktop, so the dialog looks like the rest of the desktop; zenity otherwise.
    order = ("kdialog", "zenity") if "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() else ("zenity", "kdialog")
    for name in order:
        if _tool(name):
            return name
    return None


def available():
    """True when this system can show a file/folder dialog without a window of our own."""
    return dialog_tool() is not None


def _run(argv):
    """Runs a dialog program and returns its output, or None when the user cancelled or it couldn't run.
    A dialog that fails must never take the app down with it: every failure is a cancel, with a line in the log."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=DIALOG_TIMEOUT,
                              env=original_environ(), check=False)
    except (OSError, subprocess.SubprocessError) as e:
        diag.log("dialog", f"{argv[0]} couldn't run: {type(e).__name__}: {e}")
        return None
    if done.returncode != 0:
        if done.returncode not in (1, 255):     # 1 (zenity/kdialog) and 255 (osascript) are "the user cancelled"
            diag.log("dialog", f"{argv[0]} exited {done.returncode}: {done.stderr.strip()[:200]}")
        return None
    chosen = done.stdout.strip()
    return chosen or None


def _osascript(script):
    return _run(["osascript", "-e", script])


def pick_folder(title="Choose a folder"):
    """The user picks a folder. Its path, or None if they cancelled or this system has no dialog program."""
    tool = dialog_tool()
    if tool == "zenity":
        return _run(["zenity", "--file-selection", "--directory", f"--title={title}"])
    if tool == "kdialog":
        return _run(["kdialog", "--getexistingdirectory", os.path.expanduser("~"), "--title", title])
    if tool == "osascript":
        return _osascript(f'POSIX path of (choose folder with prompt "{_quote(title)}")')
    return None


def save_file(title="Save as", default_name="", file_type=("JSON file", "*.json")):
    """The user picks where to write a file. Its path, or None."""
    tool = dialog_tool()
    label, pattern = file_type
    if tool == "zenity":
        return _run(["zenity", "--file-selection", "--save", "--confirm-overwrite", f"--title={title}",
                     f"--filename={default_name}", f"--file-filter={label} | {pattern}"])
    if tool == "kdialog":
        return _run(["kdialog", "--getsavefilename", default_name or os.path.expanduser("~"),
                     f"{pattern}|{label}", "--title", title])
    if tool == "osascript":
        return _osascript(f'POSIX path of (choose file name with prompt "{_quote(title)}" '
                          f'default name "{_quote(default_name)}")')
    return None


def open_file(title="Open", file_type=("JSON file", "*.json")):
    """The user picks a file to read. Its path, or None."""
    tool = dialog_tool()
    label, pattern = file_type
    if tool == "zenity":
        return _run(["zenity", "--file-selection", f"--title={title}", f"--file-filter={label} | {pattern}"])
    if tool == "kdialog":
        return _run(["kdialog", "--getopenfilename", os.path.expanduser("~"), f"{pattern}|{label}", "--title", title])
    if tool == "osascript":
        return _osascript(f'POSIX path of (choose file with prompt "{_quote(title)}")')
    return None


def _quote(text):
    """AppleScript string contents (the text comes from the app, not the user, but a stray quote would still break the script)."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')
