# Mario Kart 8 Deluxe Mod Manager (Linux)

## Using the app:
### 1. Launch the app
Extract the folder anywhere you like, open a terminal in it and run:

    ./mk8dx-mod-manager

(or double-click `mk8dx-mod-manager` in your file manager and choose "Run").

It needs a 64-bit desktop (X11 or Wayland) and a reasonably recent distribution (it is built on Ubuntu 22.04, so glibc 2.35 or newer). The window
(Qt WebEngine) and the helper libraries it needs are inside the folder; nothing else needs installing. If the window doesn't open, start it from
a terminal to see why. A missing system library is named there; on Debian and Ubuntu these are the usual ones:

    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libnss3 libasound2

On a few systems (Ubuntu 24.04 and newer with AppArmor's restriction on user namespaces) the web view stops with "No usable sandbox". Starting the
app once with `QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox ./mk8dx-mod-manager` works around it (that turns off the web view's own sandbox, which
only matters for web pages the app does not show).

Where the app keeps its files: your data folder (downloaded mods and settings; you choose it on first run, the suggested one is
`~/.local/share/mk8dx-mod-manager/data`), `app-config.json` and the log file `mod-manager.log` in `~/.local/share/mk8dx-mod-manager/`
(or under `$XDG_DATA_HOME`). Attach the log when you report a problem.

### 2. Complete the first-time setup
The first time you open the app you'll need to complete the following items:
* Selecting a data-folder - Where the all will keep your downloaded mods and settings
* Pick your game version
* Point your app at your game files.
  * You can get your game files by doing the following:
  * Dump Mario Kart 8 Deluxe from your Switch (I recommend using a tool like NXDumpTool)
  * Extract the game's RomFS. This can be done easily in Ryujinx or Eden. Alternatively hactool can be used.

From there you can follow the instructions inside the app to install your first mods! After you've installed enough mods, you can then "commit" them (this just means the app checks for conflicts and moves them into a staging folder for you to easily copy/paste) and move them onto your SD card to play without any issues. On an emulator, copy the staging folder's `atmosphere/contents/0100152000022000/romfs` into the emulator's mod folder for the game instead.

## About, license and credits
This app was created using Claude Code (Anthropic). AI wrote and debugged a lot of the app's code, under the author's direction and review.
No AI was used for generating artwork or assets.

It is free software under the GNU General Public License, version 3 or later (LICENSE.txt); its source code is at
https://github.com/digiphreniac/MK8DX-Mod-Manager. The icons are Tabler Icons (MIT). THIRD-PARTY-NOTICES.txt lists everything else in this folder that
is someone else's (BNTX Editor, 7-Zip, Qt, pywebview, Pillow, Python and more) with its license. Full credits: https://github.com/digiphreniac/MK8DX-Mod-Manager#about-license-and-credits
