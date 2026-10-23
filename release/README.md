<!--
  This is the ONLY readme inside the downloaded zip (tools/build_release.py copies it to README.md in the
  release folder). It is separate from the repository's README.md.
  PLACEHOLDER: replace this whole file with your own text.
-->

# Mario Kart 8 Deluxe Mod Manager

(Placeholder - replace with your own text. Facts the final text may want to cover are below.)

- Run **MK8DX Mod Manager.exe**. Nothing needs installing; Python and 7-Zip are included.
- Extract the whole zip first (not from inside it), to a short folder path such as `C:\MK8DX`. Avoid `Program Files`.
- Windows may say "Windows protected your PC" because the app isn't code-signed: **More info**, then **Run anyway**.
- Your mods and settings live in a **`data`** folder created next to the `.exe` on first launch. The finished SD card
  files are built in **`sd-card-staging`**, also next to the `.exe`. Deleting the app folder deletes both.
  (A different data folder can be chosen under Settings.)
- On first launch the app asks for a folder extracted from your own copy of the game (the RomFS, containing
  `UI\cmn\common.sarc`). It copies the few hundred MB it needs. The files belong to Nintendo and are never included.
- To update: extract the new zip over the old folder. `data` and `sd-card-staging` are not in the zip, so they stay.
- If something goes wrong, `mod-manager.log` (next to the `.exe`) says why.
- Needs the Microsoft Edge WebView2 runtime (already on Windows 11 and up-to-date Windows 10).
