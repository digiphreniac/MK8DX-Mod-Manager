# Base game files and reference data

The app's own copy of the game's files (the required Setup step), and the fixed reference data (course internal names, music ids) behind the roster.

## Base game files: a required local copy

The app needs a few of the game's own files: the two icon archives, one `message.sarc` per language, and every
character's own default voice archives. It can't ship them itself (they're Nintendo's), so a required Setup step
(`game_files.py`) asks for the folder the user extracted from their own game and copies what it needs from it - not
the whole extraction, just `UI/cmn/common.sarc`, `UI/cmn/menu.sarc`, `UI/<locale>/message.sarc` for every locale
found, and `Audio/Driver/Driver_<slot>.bars` + `Audio/DriverMenu/MenuDriver_<slot>.bars` for every character in
`DRIVER_SLOTS`, plus every course's own select-screen picture (`UI/cmn/menu/ym_CoursePict_<id>_00^u.bntx`, about 105 files,
9 MB) and the 351 loose vehicle-part pictures that aren't inside `menu.sarc` (`UI/cmn/menu/tc_KP_*`, 38 MB - see [Vehicle parts](vehicle-parts-and-items.md#vehicle-parts-bodies-wheels-gliders)); both
kinds are optional: a dump without them, or a copy made before they were added, still counts as done. Real sizes measured: the
whole copy runs well under 300 MB, nowhere near a full RomFS dump.

**Adding the pictures to an older copy.** A copy made before the course pictures (or the vehicle pictures) were part of it has
no `course_pictures` (`vehicle_pictures_all`) in its manifest (a copy from when only 16 of the vehicle pictures were kept has `vehicle_pictures` but not `vehicle_pictures_all`, and gets the rest). The first time Course Select or the Vehicles screen asks for a
picture, `top_up_pictures()` fetches what is missing from the folder the copy was made from - if that still exists - into
BOTH `original/` and `current/` (adding files only; nothing already there is touched) and records the count, so each is
tried once. If the source folder is gone, the pictures come with the next "Update from a new dump" (Settings), and the
screens simply show their plain tiles meanwhile.

**Two copies**, both under `<master root>/game-files/`:
- `original/` - written once (`copy_both()`), never touched again except by "Update from a new dump" (which replaces
  it outright - no history of older game versions is kept). What a corrupted or missing `current/` would be
  restored from, and what "view my original files" (Settings) opens.
- `current/` - what every other consumer actually reads (`find_current()` for icons, `find_current_voice()` for a
  character's voice). Nothing today writes into it in place - the two copies are identical from the moment they're
  made - but keeping them separate is what makes a cheap, blind reset possible without asking the user to
  reconnect their dump.

`manifest.json` records what was found and copied (which icon archives, which locales, which character voice slots,
the source folder shown for reference only - it doesn't need to still exist afterward - and when). `status()` reads
it back for Settings and the Setup step; `done` requires both icon archives plus at least one locale (voice is
best-effort - a dump missing a few characters' files is a warning, not a failure). Each copied file's magic bytes
(`SARC` / `BARS`) are checked before it's trusted; anything that doesn't look right is skipped and reported rather
than copied.

**What this replaced:** an optional per-feature "Your game's files" folder setting (`game_files_dir`) that `ui_setup.py`
read live and `voice_api.py` read live for voice - meaning UI icons/text needed a mod to ship them or that folder to
still be connected, and *muting or replacing a character's default voice needed a ticked voice mod first* if that
optional folder was never set (true of most installs). Requiring the copy up front removes both: `_game_files()` and
`_voice_game_file()` now always resolve to the app's own copy, so every roster character
(all 52 have a `DRIVER_SLOTS` code, verified byte-for-byte
against a real dump; see the comment above `DRIVER_SLOTS`) has a base voice to start from with no voice mod
ticked at all, and UI icons/text work with nothing ticked either. (The card's Voice row still shows only "Comes after you pick a mod" until the
character has a ticked mod - see [Voice editing](voice-editing.md#voice-editing-mute-a-line-or-use-your-own-sound) - but that is a UI choice, not a missing base file.) `get_flow_status()`'s `setup.done` requires the copy
to exist (`game_files.status(mod_root).done`), so an install that's missing it is sent back to Setup rather than
silently degrading somewhere else in the app.

## Reference data: course internal names and music ids

Each MK8DX course has a real, fixed internal folder name inside `romfs/Course/`
(e.g. Water Park is `Gu_WaterPark`) and a real, fixed race-music id embedded
in its BGM filenames (e.g. Water Park's music is `pBGM_WU_WATER_PARK_F/N.bfstm`)
that the game actually uses - neither has anything to do with what a
GameBanana mod happens to be titled. A mod can be correctly *about* one
course while its files (or its music) are wired to replace a *different*
course's slot, which otherwise only shows up as a confusing conflict against
whichever mod really owns that slot, if it shows up at all.

`roster.json` records both, per course, for all 96 courses:
`"internal"` (the `Course/<id>/` folder name) and `"music"` (the BGM id -
for a Booster Course Pass course this is just its own `Cnsw_NN` internal id
reused verbatim; every base-game/Wii-U-DLC course has its own, otherwise
unrelated-looking id instead, e.g. Twisted Mansion's romfs id is
`Gu_HorrorHouse` but its music id is `WU_HAUNTED`). `mod_manager.py`
cross-checks every course download against both independently, flagging a
mismatch right on the file row instead of leaving it to be discovered later
(or never). A mod that bundles no music at all - most don't - isn't treated
as suspicious; only bundled music confirmed to belong to a specific *other*
course is.

Source: the [Mario Kart 8 Deluxe Information Dump](https://docs.google.com/spreadsheets/d/1B0XM1LqJxmp5L5pD3xgSSc3nBNcBAgVHL6q9RcIO_8E)
spreadsheet (a community datamine, linked from
[this GameBanana tutorial](https://gamebanana.com/tuts/16319)), cross-checked
against [GameBanana's Wave 1](https://gamebanana.com/tuts/14836) and
[Wave 2](https://gamebanana.com/tuts/15196) course-name tutorials and against
real downloaded mod content - all three agreed everywhere they overlapped.

The same spreadsheet has two other tabs not used by this app: `Objects` and
`Collisions`/`Coordinates` (MapObj AI behavior, KCL collision-flag, and BYAML
coordinate-system references - all track-*building*-level detail, no use for
a mod *merging* app like this one).
