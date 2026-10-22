# A mod for something other than its card

What happens when a downloaded mod turns out to replace something other than the item it was filed under.

## A mod for something other than its card: one experience for every kind

GameBanana files a mod where its author put it, and the files inside often say something else - a Luigi mod on Mario's page, a tire
mod on a kart's, a course retexture on the wrong course, an item pack. This works the same for characters, courses, vehicle parts
and items, and the app talks about what a mod *replaces* (never "slots" or "filing").

**What the files say** (`_download_slot_mismatch()` -> a mismatch dict with `targets`, the things the files are for, and
`unresolved`, how many of the files' ids the app can't place): a character's `Driver/` and `Audio/Driver*` files
(`slot_characters()`), a course's `Course/<id>/` folder (`_course_slot_mismatch()`), a vehicle part's `Kart/{Body,Tire,Wing}/`
model - across kinds too, so a tire mod on a kart's page counts - and an item's `RaceCommon/Item/<model>/` folder
(`_item_slot_mismatch()`). A mod with no such file (a texture pack) says nothing and is never moved.

**After a download** (`gb_download_files()` -> `_refile_mod()`): if every downloaded file's files are for something other than the
card it came from and the app can place all of them, the mod is moved there (`gb_move_mod()`): one thing -> that thing; several
(a pack) -> the first of them in the app's order (`_refile_rank()`), where it is filed, and it is listed on the others (below).
The page then runs `finishRefile()` (`js/refile.js`): the destination's card opens (pop-up or docked) with a note - *"X" replaces
Mach 8, not Standard Kart, so it is now under Mach 8* / *"X" is a pack: it replaces A and B...* - the mod is ticked when it is the
only one that card has (the rule for any fresh download), and the note has an **Undo** (`undoRefile()`: the same move back, and it
unticks what the app ticked). Nothing is guessed: a file that fits the card, or names something unrecognised, leaves the mod where
it is, with a warning that names what it replaces and a "Move to X" button (`buildFileRow()`); a move that fails (the mod is
already tracked under the target) says so on the card.

**Moving one by hand**: every mod's "..." menu has "Move to another character / course / part / item..." (`openMoveDialog()`),
enabled for mods that came through GameBanana (`get_mod_ids()`; a mod added by hand has no record to move). A mod can only move
between things of its own kind (a character to a character, a part to a part). "Other items" - where item mods that name no
single item pile up - also lists each of its mods with a picker.

**What a move moves** (`gb_move_mod()`): the extracted folders, the archives, the tracking entry, the ticks, and everything else
the app remembers by the mod's path - the files left out of it, the clash priorities, voice edits, look reviews and menu picture
choices (`_rekey_unit_prefix()` rewrites those files). It returns `moved_folders`, which is how an undo finds the ticks. A failed
move is rolled back with nothing recorded.

**Packs** (`get_pack_links()`): a mod whose files replace more than one thing is listed on the card of each one. The pack stays one
mod filed in one place (never copied); its keys join the other entries' `units` on the page (`refreshViewsState()`, `packUnits`
marks them), so it is an ordinary row there - counted in the card and on the tile, in the footer totals (`get_stats()`), and in
conflict checks - with a "Pack . also X" badge (`buildPackBadge()`; click it to open the next card), and its menu says "Open where
it's filed" instead of "Move". One tick is shared everywhere, so ticking it on any card turns on everything in it, and the badge
and note say so. Wording is deliberately "replaces", read from the files: authors sometimes bundle stock files unchanged, and there
is no vanilla copy to compare against. This replaces the old vehicle-only, read-only "Also ships this part" card.
