# Mario Kart 8 Deluxe Mod Manager (macOS)

## Using the app:
### 1. Launch the app
Drag `MK8DX Mod Manager.app` to your Applications folder (or anywhere you like) and open it.

The first time, macOS says it "can't be opened" because the app isn't signed with an Apple developer account (that costs money, and this app is free).
You only have to allow it once:
* Open **System Settings > Privacy & Security**, scroll down to the message about "MK8DX Mod Manager" and click **Open Anyway** (then confirm).
* Or, in Terminal: `xattr -dr com.apple.quarantine "/Applications/MK8DX Mod Manager.app"` and open it again.

This build is for Apple Silicon or Intel Macs as named in the file (`macos-arm64` or `macos-x86_64`), macOS 11 or newer.

Where the app keeps its files: your data folder (downloaded mods and settings; you choose it on first run, the suggested one is
`~/Library/Application Support/MK8DX Mod Manager/data`), `app-config.json` and the log file `mod-manager.log` in
`~/Library/Application Support/MK8DX Mod Manager/`. Attach the log when you report a problem.

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
is someone else's (BNTX Editor, 7-Zip, pywebview, Pillow, Python and more) with its license. Full credits: https://github.com/digiphreniac/MK8DX-Mod-Manager#about-license-and-credits
