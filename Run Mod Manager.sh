#!/usr/bin/env bash
# Starts the Mod Manager from source on Linux or macOS (the counterpart of "Run Mod Manager.bat").
# First run: makes a private Python environment (.venv) next to the app and installs the libraries; again whenever
# requirements.txt changes. Needs Python 3.9 or newer.
cd "$(dirname "$0")" || exit 1

VENV=".venv"
VPY="$VENV/bin/python"
STAMP="$VENV/requirements.installed"

fail() {
  echo
  echo "The Mod Manager could not start. The messages above say why."
  if [ -t 0 ]; then read -r -p "Press Enter to close. " _; fi
  exit 1
}

if [ ! -x "$VPY" ]; then
  PY=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Python 3.9 or newer was not found."
    if [ "$(uname -s)" = "Darwin" ]; then
      echo "Install it from https://www.python.org/downloads/ (or: brew install python), then run this file again."
    else
      echo "Install it with your package manager (for example: sudo apt install python3 python3-venv), then run this file again."
    fi
    fail
  fi
  echo "Setting up the Mod Manager for the first time..."
  if ! "$PY" -m venv "$VENV"; then
    if [ "$(uname -s)" != "Darwin" ]; then
      echo "Making the environment failed. On Debian and Ubuntu it needs: sudo apt install python3-venv"
    fi
    rm -rf "$VENV"
    fail
  fi
fi

# Install the libraries on first run, and again whenever requirements.txt changes.
if ! cmp -s requirements.txt "$STAMP"; then
  echo "Installing required libraries (needs an internet connection)..."
  "$VPY" -m pip install --disable-pip-version-check -r requirements.txt || fail
  cp requirements.txt "$STAMP"
fi

# Not required to start, but .rar / .7z mods can't be unpacked without it.
if ! command -v 7zz >/dev/null 2>&1 && ! command -v 7z >/dev/null 2>&1 \
   && [ ! -x /opt/homebrew/bin/7zz ] && [ ! -x /usr/local/bin/7zz ]; then
  echo
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "Note: 7-Zip was not found. Mods packed as .rar or .7z can't be unpacked without it (brew install sevenzip)."
  else
    echo "Note: 7-Zip was not found. Mods packed as .rar or .7z can't be unpacked without it (sudo apt install 7zip, or p7zip-full)."
  fi
  echo "The app still starts without it."
  echo
fi

"$VPY" src/mod_manager.py || fail
