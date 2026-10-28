# Mario Kart 8 Deluxe Mod Manager

A desktop app for installing Mario Kart 8 Deluxe mods without hand-merging folders. Browse
GameBanana from inside the app, tick the mods you want for each character, course, vehicle part
or item, settle any clashes, and the app builds one combined set of files ready to copy to your
Switch's SD card.

It takes care of the tedious parts:

- Downloads mods from GameBanana and unpacks them, fixing the common packaging mistakes (missing
  `romfs` folder, a whole SD-card tree zipped up, and so on).
- Warns you when two mods change the same file, and lets you pick which one wins.
- Combines character-select icons and menu text from several mods into one working set.
- Lets you mute or replace individual character voice lines.
- Stages everything in the right place for Atmosphere, including code patches (`.ips`).

Your mods stay on your computer. The app only talks to GameBanana to browse and download.

## Requirements

- **Windows 10 or 11**, **Linux** (64-bit, X11 or Wayland) or **macOS 11 or newer**. Windows is the system the app was made
  and tested on; the Linux and macOS builds are newer, so expect rough edges and please report them.
- On Windows, the **Microsoft Edge WebView2 runtime**. It is already included in Windows 11 and up-to-date Windows 10.
- **Your own copy of Mario Kart 8 Deluxe**, dumped from your Switch, with its RomFS extracted (see
  [First run](#first-run)). The app cannot include the game's files because they belong to Nintendo.
- A Switch running **Atmosphere** custom firmware, to use the mods.

## Install and run

Nothing else needs installing: Python and 7-Zip (for `.rar` and `.7z` mods) are included in every download. If you'd rather
check what you're running, the full source is in this repository.

**Windows**

1. Download `MK8DX-Mod-Manager-v<version>-windows.zip` from the releases page.
2. **Extract the whole zip** to a short path you want to keep it in, such as
   `C:\MK8DX-Mod-Manager`. Don't run it from inside the zip, avoid very long folder paths
   (Windows refuses to load the app from them), and avoid `Program Files`, since the app saves its
   data next to itself.
3. Double-click **`MK8DX Mod Manager.exe`**.

Windows may show a "Windows protected your PC" notice the first time because the app isn't
code-signed; choose **More info**, then **Run anyway**.

To update, extract the new zip over your old folder. Your mods and settings live in the `data` folder next to the
app (or the folder you chose in Settings), which isn't part of the zip, so they're kept.

**Linux**

1. Download `MK8DX-Mod-Manager-v<version>-linux-x86_64.tar.gz` and extract it (`tar -xzf <file>`).
2. Run `./mk8dx-mod-manager` in the extracted folder.

The window library (Qt WebEngine) is inside the folder. Your data, settings and the log live in
`~/.local/share/mk8dx-mod-manager` (or under `$XDG_DATA_HOME`), so replacing the folder to update keeps them. If it doesn't start, run it
from a terminal to see why; the folder's `README.md` lists the usual fixes.

**macOS**

1. Download `MK8DX-Mod-Manager-v<version>-macos-arm64.zip` (Apple Silicon) and unzip it.
2. Open `MK8DX Mod Manager.app`. The app isn't signed with an Apple developer account, so macOS blocks it the first time: open
   **System Settings > Privacy & Security** and click **Open Anyway** (or run
   `xattr -dr com.apple.quarantine "MK8DX Mod Manager.app"` in Terminal).

Your data, settings and the log live in `~/Library/Application Support/MK8DX Mod Manager`. Only Apple Silicon Macs have a download;
on an Intel Mac, run from source.

### Running from source (optional)

If you'd rather not use the packaged build, install
[Python 3.9 or newer](https://www.python.org/downloads/) (on Windows tick **"Add python.exe to PATH"**) and
[7-Zip](https://www.7-zip.org/) (needed for `.rar` and `.7z` mods; on macOS `brew install sevenzip`, on Debian and Ubuntu
`sudo apt install 7zip`). Then:

- **Windows:** double-click **`Run Mod Manager.bat`** in the repository.
- **Linux:** run **`./Run Mod Manager.sh`**. On Debian and Ubuntu you may first need `sudo apt install python3-venv`, and the web view
  (Qt WebEngine) needs a few system libraries: `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libnss3 libasound2 libxdamage1`.
- **macOS:** double-click **`Run Mod Manager.command`** (or run `./Run Mod Manager.sh`).

The first launch creates a private Python environment in a `.venv` folder and downloads the libraries the app needs
(`pywebview`, `Pillow` and `certifi`, plus Qt on Linux), which needs an internet connection. A console window stays open while it runs, so any
error messages are visible.

Design notes for contributors, including how to build the release, are in [docs/DEVELOPERS.md](docs/DEVELOPERS.md).

## First run

On first launch, a short setup wizard asks for:

1. **A data folder**, where the app keeps your downloaded mods, settings and caches. The app suggests a
   **`data`** folder next to itself (next to the `.exe` on Windows, in the repository folder when run from source, or
   inside the app's own folder in your home directory on Linux and macOS) and marks it
   as recommended, so most people just click Next. You can pick a different folder here, or later under **Settings**.
   If the app is somewhere it can't write to, there is no suggestion and you choose a folder instead.
2. **Your game version** and a few options (language, adult-content filter, advanced mode).
3. **Your game's files.** Dump Mario Kart 8 Deluxe from your own Switch (for example with NXDumpTool)
   and extract its RomFS (in Ryujinx: right-click the game, then *Extract Data*, then *RomFS*; or use
   `hactool`). Choose the extracted folder, the one that contains `UI/cmn/common.sarc`. The app
   copies only the few hundred MB it needs, so you can delete the extraction afterward.

## Using it

The four steps are shown across the top of the window:

1. **Setup** - the wizard above. Reopen it any time from the step bar.
2. **Choose mods** - open a character, course, vehicle part or item, browse or search GameBanana
   for mods for it (or paste a link), download, and tick the ones you want. Use **Add mod** for
   mods you already have as a file.
3. **Commit** - the app checks for clashes, shows anything that needs your attention, and builds
   the combined files. Nothing on your SD card is touched.
4. **Copy to Switch** - copy the staged files onto your SD card.

The built files appear in a folder called **`sd-card-staging`**, inside the
`data` folder, in `sd-card-staging\atmosphere\contents\0100152000022000\`. (An install that
already had one next to the `data` folder keeps using it until you switch it. **Settings > Staging
folder** can point it somewhere else.) The app can open it for you. Copy the `atmosphere` folder from there onto the root of your SD card,
merging when asked. The in-app **Help** button explains each screen in more detail.

## Troubleshooting

- **The app says it has to close, or nothing opens** - the details are in `mod-manager.log` next to
  the `.exe` (every run is added to it, so it still holds the run that went wrong). Include that file when you report the problem.
  If the app opens, **Help > Show log file** opens the folder with that file selected.
- **"Failed to load Python DLL ... filename or extension is too long"** - move the folder to a
  shorter path such as `C:\MK8DX-Mod-Manager`.
- **"Failed to resolve Python.Runtime.Loader.Initialize" in `mod-manager.log` (version 0.1.0 only)** - Windows blocked the
  app's files because they came from a downloaded zip. Update to 0.1.1 or newer, or right-click the downloaded zip,
  choose **Properties**, tick **Unblock**, click OK, and extract it again.
- **The window stays blank or doesn't open** - install the
  [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
- **Running from source: "Python was not found"** - install Python from python.org with
  *Add python.exe to PATH* ticked, then run the launcher again.
- **Running from source: "Can't extract ... 7-Zip isn't installed"** - install 7-Zip with its default settings.
- **A mod shows "Needs romfs folder"** - its author packaged it unusually. Open the mod's folder from
  the app and place its files in a folder named `romfs`.
- **Running from source: something broke after an update** - delete the `.venv` folder and launch again
  to rebuild it.
- **Debug mode** (from source) - run `Run Mod Manager (Dev).bat` to turn on the browser developer tools.

## Help and community

Questions, a problem the steps above don't fix, or want to work on mods with other people? Join the
[Discord](https://discord.gg/mNShnnu8j8).

## Disclaimer

This is an unofficial fan tool. It is not affiliated with or endorsed by Nintendo. Mario Kart is a
trademark of Nintendo. The app does not include or distribute any game files, and mods are
downloaded from GameBanana and belong to their authors. Use mods at your own risk, and only with a
game you legally own.

## About, license and credits

**AI assistance.** This app was created using [Claude Code](https://claude.com/claude-code) (Anthropic). AI wrote and debugged
a lot of the app's code, under my direction and review. No AI was used for generating artwork or assets.

**License.** MK8DX Mod Manager is free software, licensed under the GNU General Public License, version 3 or (at your option)
any later version (see [`LICENSE`](LICENSE)). Copyright (c) 2026 digiphreniac. The release zip also contains
`THIRD-PARTY-NOTICES.txt`, with the license texts of everything below that is someone else's.

**Credits.**

- Mods are by their creators on [GameBanana](https://gamebanana.com/).
- Icons: [Tabler Icons](https://tabler.io/icons) by Paweł Kuna (MIT license). The Discord and Buy Me a Coffee logos are
  trademarks of their owners, shown only beside links to those services.
- Texture packing: `src/_bntx_structs.py` is from [BNTX Editor](https://github.com/aboood40091/BNTX-Editor) by AboodXD
  (GNU GPL v3 or later), included unmodified.
- The packaged build includes the [7-Zip](https://www.7-zip.org/) command-line tool by Igor Pavlov (GNU LGPL, with the unRAR
  restriction; its license is in the `7zip` folder next to the program's libraries).
- Built with [pywebview](https://pywebview.flowrl.com/) (BSD-3-Clause) and [Pillow](https://python-pillow.org/) (MIT-CMU); the
  Linux build's window is [Qt](https://www.qt.io/) 6 and Qt WebEngine through PyQt6 (LGPL-3.0 and GPL-3.0). The
  packaged build also contains Python and a few small libraries, all listed in `THIRD-PARTY-NOTICES.txt`.
- Reference data draws on the MK8DX modding community's research: the
  [Mario Kart 8 Deluxe Information Dump](https://docs.google.com/spreadsheets/d/1B0XM1LqJxmp5L5pD3xgSSc3nBNcBAgVHL6q9RcIO_8E)
  spreadsheet and GameBanana's course-name tutorials ([Wave 1](https://gamebanana.com/tuts/14836),
  [Wave 2](https://gamebanana.com/tuts/15196)).
