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

- **Windows 10 or 11.** Only Windows has been tested.
- **Python 3.9 or newer**, from [python.org](https://www.python.org/downloads/). Tick
  **"Add python.exe to PATH"** in the installer. (The `py` launcher that the installer adds also works.)
- **[7-Zip](https://www.7-zip.org/)**, which is needed to unpack `.rar` and `.7z` mods. Plain `.zip` mods
  work without it, but many mods on GameBanana are not zips.
- The **Microsoft Edge WebView2 runtime**. It is already included in Windows 11 and up-to-date Windows 10.
- **Your own copy of Mario Kart 8 Deluxe**, dumped from your Switch, with its RomFS extracted (see
  [First run](#first-run)). The app cannot include the game's files because they belong to Nintendo.
- A Switch running **Atmosphere** custom firmware, to use the mods.

## Install and run

1. Download the release and unzip it somewhere you want to keep it, such as `C:\MK8DX-Mod-Manager`.
   Avoid `Program Files`, since the app saves a small settings file next to itself.
2. Double-click **`Run Mod Manager.bat`**.

The first launch creates a private Python environment in a `.venv` folder and downloads the
two libraries the app needs (`pywebview` and `Pillow`). That takes a minute and needs an internet
connection. Later launches start straight away. A console window stays open while the app runs, so
any error messages are visible. Close the app window to end it.

## First run

On first launch, a short setup wizard asks for:

1. **A folder for your mod data.** Pick somewhere with plenty of free space. Downloaded mods,
   settings and caches all live there.
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

The built files appear in a folder called **`sd-card-staging`**, created **next to** the mod
data folder you chose, in `sd-card-staging\atmosphere\contents\0100152000022000\`. The
app can open it for you. Copy the `atmosphere` folder from there onto the root of your SD card,
merging when asked. The in-app **Help** button explains each screen in more detail.

## Troubleshooting

- **"Python was not found"** - install Python from python.org with *Add python.exe to PATH* ticked,
  then run the launcher again.
- **"Can't extract ... 7-Zip isn't installed"** - install 7-Zip with its default settings.
- **The window stays blank or doesn't open** - install the
  [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
- **A mod shows "Needs romfs folder"** - its author packaged it unusually. Open the mod's folder from
  the app and place its files in a folder named `romfs`.
- **Something broke after an update** - delete the `.venv` folder and launch again to rebuild it.
- **Debug mode** - run `Run Mod Manager (Dev).bat` to turn on the browser developer tools.

## Updating

Unzip the new release over the old folder. Your mod data lives in the folder you chose in setup, so
it is not affected. `app-config.json` in the app folder remembers where that is, so keep it.

## Disclaimer

This is an unofficial fan tool. It is not affiliated with or endorsed by Nintendo. Mario Kart is a
trademark of Nintendo. The app does not include or distribute any game files, and mods are
downloaded from GameBanana and belong to their authors. Use mods at your own risk, and only with a
game you legally own.

## Credits

Mods are by their creators on [GameBanana](https://gamebanana.com/). The app builds on
[pywebview](https://pywebview.flowrl.com/) and [Pillow](https://python-pillow.org/), and its
reference data draws on the MK8DX modding community's research, including the MK8DX Information
Dump spreadsheet.

## License

[MIT](LICENSE). The internal design notes for contributors are in
[docs/DEVELOPERS.md](docs/DEVELOPERS.md).
