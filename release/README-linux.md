# Mario Kart 8 Deluxe Mod Manager (Linux)

## Using the app:
### 1. Launch the app
Extract the folder anywhere you like, open a terminal in it and run:

    ./mk8dx-mod-manager

**The app opens in your web browser.** It is not a browser-based service - nothing leaves your computer. Unlike Windows and macOS, Linux has no
web view the app can borrow for a window of its own, and carrying one would have made this download seven times bigger (123 MB instead of 18 MB),
so the app shows its page in the browser you already have. It starts a small server on your own machine (`127.0.0.1`, a different port and a new
one-time key every time), opens the page, and quits once you close it.

If no browser opens by itself, the terminal prints the link to open - it looks like `http://127.0.0.1:41591/?t=...`. The key in it is what lets
the page talk to the app, so open the whole link.

* **Keep the terminal open** while you use the app: closing it stops the app. Closing the page stops the app too.
* It needs a 64-bit distribution with glibc 2.35 or newer (it is built on Ubuntu 22.04). Nothing else needs installing - no Qt, no GTK.
* The "Choose a folder" buttons open your desktop's own folder picker, which needs `zenity` (GNOME and most desktops) or `kdialog` (KDE). If you
  have neither, the app gives you a box to type the path into instead, so everything still works:
  `sudo apt install zenity` / `sudo dnf install zenity` if you would rather have the picker.

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
is someone else's (BNTX Editor, 7-Zip, Pillow, Python and more) with its license. Full credits: https://github.com/digiphreniac/MK8DX-Mod-Manager#about-license-and-credits
