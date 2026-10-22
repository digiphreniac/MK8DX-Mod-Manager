# Vehicle parts and items

Bodies, wheels, gliders and items: the screens, how a mod is matched to a part, and the names and pictures shown in the game's menus.

## Vehicle parts: bodies, wheels, gliders

The **Vehicles** tab has three sections - Vehicles (41 bodies, split into
karts / bikes / ATVs), Wheels (22 tires) and Gliders (15) - each a fixed roster
from `src/roster.json` (name, internal id, aliases; researched against the
wiki, mk8dxbuilder.com and real mod archives, unchanged through game 4.0.0).

**The screen** works like Character Select and Course Select: the three sections are boards, every part is the game's own
picture of it (no name on the tile), and it is sized to fit the window without scrolling. The part being viewed - the one
whose card is (or was last) open - has the yellow corner brackets and its name on the plate along the bottom, with its kind
small beside it ("Mach 8 (Kart)"); while the mouse is over a tile, the plate shows that one instead and a white frame follows
the mouse. Tick counts (a pack counts on every tile it is listed on - see [A mod for something other than its card](refiling-mods.md#a-mod-for-something-other-than-its-card-one-experience-for-every-kind)) and the red conflict "!" are as before; a hovered tile gets only the white frame (no accent border).

Fitting (`fitVehicleScreen()` in `js/vehicle-screen.js`): one tile size for all 78 parts (a 200:128 picture), found by
trying every size from big to small and every way of laying the boards out - `a` [bodies | wheels over gliders], `b` [bodies
over (wheels | gliders)], `c` [bodies | wheels | gliders] - with every count of tiles per row for each board; the first size
at which one fits wins, and of the fits at that size the one that takes the least room. The sizes it counts with (a board's
padding, heading and sub-headings) are the CSS's own, so the prediction is exact; a board is never narrower than its heading
text, which is measured once. Only a window too small for even 36 px tiles scrolls. `css/vehicle-screen.css` comes last.

**The pictures** (`vehicle_icons.py`, `Api.get_vehicle_icons()`): every one is a 200x128 RGBA texture named
`tc_KP_<kind>_<part>^l` (K kart, B bike, V ATV, T tire, G glider; `<part>` is the roster's own internal id - `BodyK_Ufo` ->
`K_Ufo`, `Wing_Wlo` -> `G_Wlo`, a tire's `Std` -> `T_Std`). Most (62 parts) are one texture inside `menu.sarc` ->
`mn_L_KartParts_00.szs`. The 16 families that come in outfits - the Standard Kart, Standard Bike, Pipe Frame, Standard ATV
and Super Glider once per character, the rest numbered - are **351 loose files** in `UI/cmn/menu/` (each 110,696 bytes, one
texture, its internal name equal to its file name); the screen shows each family's default (Mario's red, or `_00`). Master
Cycle's picture is `B_Zld` (its roster id spells it `Zlb`). Every mapping was checked by looking at the decoded pictures.
Before Setup - or if a picture is missing - the tile shows the part's name.

**The card** is guided like the character and course cards: a head with the part's picture, its name, its kind and where it
stands ("Kart · 2 mods in use"), and a chip (No mod yet / Choose a mod / Needs a look / Done); then the mods in use (the
rest behind "Manage"), with "Find a mod" / "Add another mod" under them (packs that replace this part are ordinary rows here);
then three steps:
- **Right part** - a mod is filed under a part by where it was found, but what counts is the model file it ships: a ticked
  mod whose file is for a *different* part changes nothing on this one, so the step says which part it is really for and
  offers "Move it to <part>" (`gb_move_mod()`, which takes the tick with it) or "Untick it". Worked out from the files
  (`Api.get_vehicle_fit()`, reusing `_vehicle_slot_mismatch()`), so nothing is confirmed or remembered, and it is not part
  of "finished". (`gb_move_mod` callers reload the ticked state too - the move renames the mod's key, and a stale one would
  have been written back.)
- **Name** and **Icons** - the same two steps as a course, confirmed per set of ticked mods and remembered
  (`look-reviews.json` buckets `part_names` / `part_icons`; `Api.get_part_look()`, `confirm_part_name()`,
  `mark_part_icon_reviewed()`). Vehicle parts count in the "N aren't finished" prompt and the review queue.

Each section is its own on-disk category (`vehicles/`, `wheels/`, `gliders/`),
nested `<category>/<part>/<mod>` like everything else, and reuses the
character modal / GameBanana card / conflict machinery unchanged.

- **GameBanana has no per-part subcategory**, only section categories under
  Vehicles (10530): bodies by type - Kart 10571, Bikes (Outward = standard)
  10572, Bikes (Inward = sport) 10573, ATVs 10574 - Tires 10577, Gliders 10578
  (`Api._vehicle_gb_category_id()`). Browsing a part lists every mod of its
  *kind* (`gb_browse_vehicle()`), starting on Most Viewed (until the user picks another sort, which is then remembered) because
  GameBanana's "Most Liked" paging repeats/skips mods in these large
  categories - the window drops the repeats. Roughly 4% of body mods are misfiled under the wrong subcategory,
  and some tire/glider mods sit directly in Vehicles with no subcategory.
- **Which part a mod replaces is read from its text**, not its category
  (`match_vehicle_targets()`): an internal id (`BodyK_Cat`, `Wing_Pap`,
  `TireK_Zst`) beats an "over / replaces <name>" phrase, which beats a bare
  mention; single common words (Standard, Metal, Comet, ...) never count as a
  plain mention. Measured against real archives, "goes over" phrases agree with
  the files ~98% of the time when present; titles alone are unreliable. The
  listing has no descriptions, so each browsed batch fetches its mods' profiles
  (3 at a time, cached - GameBanana rate-limits bursts with HTTP 429) and tiles
  get a "Replaces X" / "Mentions X" badge plus an "only likely matches"
  filter, on by default (for items too, except the "Other items" tile). The list keeps loading until enough likely ones
  fill the window; after two batches in a row with none it pauses and offers "Keep searching" / "Show every mod". It's a
  guess, never a filter you can't turn off.
- **The downloaded files are the real check**: the model files a mod ships
  (`Kart/Body/BodyK_*.szs`, `Kart/Tire/TireK_*.szs`, `Kart/Wing/Wing_*.szs`)
  name the exact part they replace, so a download whose files don't include the
  part it was filed under gets the same "slot mismatch" warning courses do
  (`find_vehicle_part_ids()`). That includes a different *kind* of part: a tire or glider mod filed under a body, say (a mod
  with no model file at all, such as a texture pack, is never flagged).
- **Loose files are auto-wrapped**: about half of body mods ship
  `BodyK_Cat.szs` etc. with no folders at all; `fix_loose_kart_parts()` moves
  each into `romfs/Kart/<Body|BodyTex|Tire|Wing|WingTex|Emblem>/` by its file
  name, all-or-nothing like the loose item-file fixer.
- The **Add a mod** flow can suggest a vehicle part from the mod's category +
  description.
- **Packs and misfiled mods** (a character mod that also ships a body, a body mod filed under the wrong part...) are handled
  the same way for every kind of thing - see [A mod for something other than its card](refiling-mods.md#a-mod-for-something-other-than-its-card-one-experience-for-every-kind). Only the real load locations count
  for a vehicle part (`romfs/Kart/{Body,Tire,Wing}/`); per-character paint (`BodyTex`/`WingTex`) and `Emblem` files don't, since
  those are a character's own colors on a stock part, not a replacement of it.
- **Add a mod**: a mod that's unmistakably a vehicle part but whose text names
  no part (`guess_category == "vehicle_unsorted"`, typically filed directly
  under GameBanana's Vehicles) opens with "- pick a part -" selected instead of
  an arbitrary default. The roster carries common alternate spellings as
  aliases (e.g. "Sneaker" for Sneeker, which real mods use).
- **Multi-file mods, one step**: plenty of vehicle mods bundle files that each
  belong under a *different* part - one download per glider/kart ("Streetle
  Ver" / "Prancer Ver"), or a companion tires file next to the body. For a
  vehicle mod with more than one file, Add a mod shows a per-file part picker,
  prefilled by `suggest_file_targets()`: the file's own name/caption first
  (GameBanana's random 5-hex upload suffix and separators stripped), then, for
  a file that names nothing itself, the mod's text restricted to the kind of
  part the file is (so a `tires_....zip` file resolves "...tires replace Wood"
  to Wood). By default every file that names its own part is ticked, plus only
  the first file per part that merely inherits the mod's target (a second one
  is normally an alternative variant, not something to download too). An
  optional **icons companion** (`ui-...`/"icons" file - UI art the app can't
  merge) is never the default when a real mod file covers the part, is labelled
  as such, shows as fine rather than a warning in the summary, and doesn't
  stop the real file from being auto-ticked (`is_companion_file()`). "Add this
  mod" then files each group under its part and downloads it in one call
  (`gb_add_vehicle_mod_files()`), so all the usual safeguards still run, and a
  summary lists each file's outcome - with a **Move to** button for any whose
  real part differs. A part that ends up with exactly one clean mod is ticked,
  as after a single download. Untick "File each file under its own part" for
  the old single-target flow.
- **Wrong game**: GameBanana keeps "Mario Kart 8" (Wii U, game 5709) and
  "Mario Kart 8 Deluxe" (Switch, 6507) as separate games with parallel category
  trees (the Wii U vehicle tree is category 7442, ~600 mods, not included in
  browsing). A pasted link to a Wii U mod is flagged in the Add a mod dialog and
  on its card (`game_id` is stored with every fetched mod) - it very likely
  won't load on a Switch. Re-fetching a mod also keeps its recorded slot
  warnings and archive location now (it used to drop them).

## Items

**Items** has its own tab (it used to be a row on the More tab, one fixed pseudo-item with a plain list). It is a fixed roster from
`src/roster.json`'s `"items"` - 22 items (Banana, Green Shell, Red Shell, Spiny Shell, Bob-omb, Mushroom, Golden Mushroom, Super
Star, Lightning, Boomerang Flower, Fire Flower, Piranha Plant, Bullet Bill, Blooper, Boo, Super Horn, Crazy Eight, Feather, Coin,
Rupee, Bell, Item Box) plus a last tile, **Other items**. Each entry has a `name`, `aliases`, an optional `internal` (the model
folder under `RaceCommon/Item/`, e.g. `ItemKoura` - left out where two items share one, the Green and Red Shell, which are both in
`ItemKoura.bfres`) and an optional `icon`.

**The pictures** (`item_icons.py`, `Api.get_item_icons()`): 19 of the 22 have a 192x192 RGBA texture `tc_Item_<icon>^l` in
`menu.sarc` -> `mn_L_ItemSwitch_Item_00.szs` (the Item Switch screen of a custom race: `Koura` = Green Shell, `PKinoko` = Golden
Mushroom, `SP8` = Crazy Eight ...), so nothing new is copied into the base-game copy. The same textures are in `race.sarc`
(`rc_L_ItemBox_00.szs`, the race HUD's item slot, along with the double / triple forms and the Rupee's), which the copy doesn't
have. The Item Box, Rupee and Bell are models only, so their tiles keep their name. Every picture was checked by looking at it.

**The screen** is laid out like Character Select: on a wide window (`DOCK_MIN_WIDTH`, 1100 px) the board is the left 55% and the
picked item's card is docked on the right, always with an item in it (the last viewed, else the first with a mod); on a small
one the board takes the width and the card is a pop-up, and resizing across the threshold moves an open card between the two
(`js/item-screen.js`; `beginDetail()` / `endDetail()` / `wantsDock()` in `character-select-layout.js` hand the card to the Items
view when it is showing). The name plate along the bottom shows the viewed item - or the one under the mouse, with a white
frame following - and how its mods stand. Nothing scrolls: `fitItemGrid()` takes the biggest square tile at which the whole
grid fits its board, over whichever number of columns gives the biggest (the count isn't tied to the game's 8), capped at 150 px;
`css/item-screen.css` comes after `vehicle-screen.css`.

**Mods and GameBanana.** Mods are filed under `mods/extracted/items/<item name>/<mod name>/`. GameBanana has one flat Items category
(10579), so - like tires and gliders - browsing it lists every item mod and marks each with the item its text says it replaces
(`gb_browse_item()`, reusing `match_vehicle_targets()` with the roster's names, aliases and model-folder ids; common one-word names
like "star" or "coin" only count after a "replaces / goes over" phrase). "Add a mod" has an **Item** target, prefilled from the
same guess; a mod naming no single item (or several: an item pack) is suggested for **Other items**. A mod that lands under the
wrong item, or in Other items, is moved from the mod's "..." menu like any other (see [A mod for something other than its card](refiling-mods.md#a-mod-for-something-other-than-its-card-one-experience-for-every-kind); "Other items"
also lists its mods with a picker each). What was filed before items had a roster sits in `items/Items/` (the old
fixed pseudo-item): it isn't moved - the catch-all tile (name `Items`, shown as "Other items") collects it, along with anything in
a folder that matches no item.

An item mod's files say which item it replaces: the folders under `RaceCommon/Item/` (`ItemBanana`, `ItemPowerKinoko`, ...), matched to
the roster's `internal` ids (`_item_folder_owners()`; a folder that only extends an item - `ItemKoura_FX`, `ItemBomheiBomb`, `ItemCoinB`
- belongs to the longest id it starts with, and the Green and Red Shell share `ItemKoura`, so a mod shipping it replaces both).
Folders the app can't place (`ItemCommon`, which every item uses) leave the mod where it is.

Not done for items (unlike vehicle parts): the **Name and Icons steps** - an item's picture (`tc_Item_*`, in both `menu.sarc` and
`race.sarc`) has no override yet, and where the game's text names the items hasn't been found.

## Vehicle parts: names and pictures in the menus

The user has the same control over a part's UI as over a character's: its **name** and its **picture in the parts menu**, from
a mod or from themselves.

**Names.** All 78 part names are entries in `Common.msbt` (bodies 1101-1186, tires 1201-1222, gliders 1251-1265; one label
each, none shared), so they go through the same pipeline as characters and courses: `name-labels.json` has `vehicles`,
`wheels` and `gliders` sections, `ui_setup.NAME_LABEL_RANGES` the three kinds, `set_item_name(part, kind, text)` stores the
wish by name, and the text is written into every language's `message.sarc` at commit. A mod's own text is read the same way
(`get_menu_look()`), and a name can be guessed from the mod's name, which is only a suggestion until confirmed.

**Pictures.** The picture source is one of, in this order: what the user chose, what a ticked mod brings, the game's own.
- A part whose picture is a texture in `menu.sarc` (62 parts): a chosen picture is a texture override
  (`mn_L_KartParts_00.szs|tc_KP_K_Ufo^l` in `ui-overrides.json`) and goes through the same build as a character's icon
  (`apply_overrides()` -> `menu.sarc`, checked by `verify_archive()`). A mod's own is found by the same diff of packed archives
  (`describe_texture()` names a part texture after its part, so it is attributed to the right one).
- A part whose picture is loose files (16 families, 351 files): a chosen picture is stored once (`loose|K_Std`), and
  `ui_setup.build_part_pictures()` writes **every variant file** of the family into `part-icons/romfs/UI/cmn/menu/` (always
  merged in, like `course-icons/`) - each the game's own file from the base copy with the picture swapped in place (the file
  keeps its name, size and layout; re-encoding the game's own picture reproduces it byte for byte). `Api.sync_part_pictures()`
  runs when a picture is set or cleared and at the start of every commit, and deletes files no longer wanted. A mod's own
  loose files count as its picture when the mod is filed under that part.
- **Precedence:** a picture you chose replaces the files of a mod filed under the same part, but a ticked mod filed
  *elsewhere* that ships the same file - a character mod's per-outfit `tc_KP_K_Std_MroM` - keeps it (`left_to_mods`; the
  Icons step says how many).
- Pictures are cropped in the icon dialog ("part" mode, 200:128) from a mod screenshot or **a file from the user's computer**,
  stored at up to 400 px in their own shape, and a picture of another shape is fitted inside the part's (never stretched).

Not verified in a running game: that the console shows the loose files and the new names (only the built files and text
were decoded and compared) - try it in an emulator or on hardware.
