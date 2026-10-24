# Menu look: your own icons and names

The Menu look card of a character, course, vehicle part or item: the icons and names you supply, the Name and Icons steps, and how each is read from the ticked mods.

## Menu look: your own icons and names

For a mod that ships no menu icon or new name, a character/course popup's
**Menu look** card (`get_menu_look()`) shows what the select, map and results
icons and the name will be - and whether each is the game's own, a mod's, or
yours. You can pick a picture (one of the mod's GameBanana screenshots or a file
from your computer; the existing crop dialog, square) or type a name.

**The card is never stale.** It has no cache: it is re-read every time the popup opens, a
mod is ticked/unticked, or a download finishes (`refreshBehindModal()` -> debounced
reload of the open card). When exactly one ticked mod ships the packed menu files and
there are no game files to compare with, nothing can be diffed - so if that mod is filed
under this character its icons are labelled "In a mod's files" (not "Normal"), and its
name is recognised by comparing its text at the character's entry with the game's name.

**Choices are intent, saved without any game data.** Menu look works the moment a
mod is added, with no game files and no mod shipping the shared menu files:
`get_menu_look()` reads only `ui-overrides.json` (pictures by slot; names by
`"<kind>|<item>"` -> text, in `names`), the automatic loose-picture picks, and - only
when some ticked mod ships packed menu files, or game files are chosen - the analysis
of those (to say what a packed mod changes and show the game's own thumbnails).
Nothing is resolved against a base until the next commit builds it: that is when a
picture is resized to the target texture and a name is matched to its text entry
(`apply_overrides()`), and when anything that doesn't fit is reported ("couldn't find
'X' in the game's text"). Base game files are required at Setup, so there's always
something to build against by the time this runs; the only real risk left is a dump
that's missing a specific locale, which `game_files.status()`'s `problems` list
already surfaces in Settings. Name overrides saved by label in older versions
(`strings`) still apply.

They're stored in `ui-overrides.json` and enter the UI plan as one more "mod"
called *Your changes* (`ui_setup.apply_overrides()`); its picks always win, so
building, verifying and the review screen treat them like any mod's change. An
icon is resized to the target texture's exact size, converted to RGBA8 and
swizzled with `bntx_encode._swizzle` (checked to be the exact inverse of the
previews' decode) so it's the same same-length byte swap as any other icon. A
name is matched to its numeric label in `Common.msbt` (characters 1000-1099,
courses 1400-1599 - the short and cup-line variants), from an English message
archive of the plan. Building needs the game's own menu files (see [Base game files](base-game-files.md#base-game-files-a-required-local-copy)) or, failing that, a ticked
mod that ships them to use as the base copy - but choosing does not.

**Character Select layout.** On a window at least 1100 px wide (`DOCK_MIN_WIDTH` in `src/ui/js/character-select-layout.js`) the
screen is: the character grid on the left (55% of the width) and the card of the selected character - mods
to merge, menu look, GameBanana mods - on the right (45%), two equal-height columns, and under them a
bottom row with the character's **name plate** in the middle and the Next button at the right end. The
proportions are fixed, so the screen looks the same at every window size. The grid always shows every
character with no scrolling: `fitCharacterGrid()` picks the biggest square tile that fits the column by
width AND height (a wide-but-short window gets smaller tiles, not a taller grid), the gaps and type scale
with the tile, and the grid is centred in its column. The board behind the grid is only as tall as the grid (it
is not stretched to fill the column) and is centred vertically in the space, so the room the grid has is
measured from the layout, not from the board. The 8 columns (the in-game arrangement) never change. (The
tabs are called **Characters** and **Courses**.) A character tile with an icon is just its icon - no fill, no
shadow and no coloured ring - while a tile without one keeps a grey border (2 px) (a conflict still shows a red one, on either) - and the icon fills nearly the whole tile in
the wide layout.
There is always a character selected - Mario when the app opens, afterwards the one you last viewed - so
there is no empty state and no Close button. The selected tile gets the same pulsing yellow corner brackets
as the selected cup on Course Select, and a group tile (Inkling, Villager) stays marked while you choose
between its two characters in the card. The name plate shows the name as the menus will show it (the mod's or
your name from the Menu look, else the game's own; for a group tile under the mouse, each variant's: "Boy: Yoda · Girl: Pinkie
Pie") in white on a
black plate that fades to transparent at both ends. Below 1100 px there is no card and no plate: clicking
a character opens the pop-up as before (nothing pops up by itself when the window shrinks), and growing
the window past the threshold moves an open pop-up into the card. It is the same card-building code
(`openCharacterModal()` builds into whichever container `beginDetail()` picks); the
other tabs and the Settings pop-ups are unchanged.

The grid sits on a board (a light translucent panel, `rgba(219,219,219,.25)`, slightly rounded, with a ridge border of the same colour and opacity)
and is centred in it both ways. Hovering a tile doesn't move it; instead one white corner-bracket frame
(`makeHoverFrame()`) slides smoothly to whichever tile the mouse is over and fades out when it leaves the
grid (the yellow brackets of the selected tile stay on top). Course Select uses the same helper for its cup
tiles and course tiles, replacing their old lift-on-hover.
The four course tiles are rectangles with angled (chamfered) corners, not circles, drawn in two layers
because a clip-path can't carry a border, and all four sit in one large container with a white-to-grey
gradient (`#course-strip`). In the wide layout the card has no title of its
own: the game's character name is on the name plate, after the modded name, smaller and dimmer -
"Pizza (Kamek)" (nothing extra for an unmodded character); the pop-up on small windows keeps its title.

**Names we guessed.** The Commit page shows a "names were guessed" warning card whenever a guessed
name (see "Ticking a character mod tries to name the character") hasn't been confirmed yet; its
**Review names** button opens a small dedicated modal (`openGuessedNamesModal()` /
`drawGuessedNamesModal()` in `src/ui/js/menu-icons-text.js` - reusing the same row-building logic the old standalone
page used) - one row per character: the name in an editable box, **Confirm** (which becomes **Save
name** once the box is edited) and **Use the game's name**, plus **Confirm all as shown**. A wrong
guess would otherwise be built into the game's menus. A guess counts as confirmed once the Name task
itself is confirmed for that character's current set of ticked mods - either here, or with the
card's own **Use this name** - since Name and Icons are independent tasks (see "Name and Icons"
above): Icons' "Looks right" no longer settles it. Confirming here (or on the card) settles only
Name, so the tile's check mark (which needs both Name and Icons) is unchanged if Icons is still
open. Saving an edited name makes it the user's own (it leaves the list),
"Use the game's name" drops the guess for good (`declined_names`), and ticking a different set of
mods brings a changed guess back for another look. The record is the `names` part of
`look-reviews.json` (`get_guessed_names()`, `confirm_guessed_name()`; `set_item_name()` /
`clear_item_name()` take `mark_reviewed=False` for this list).

**The character card.** A character's card (docked beside the grid, or the pop-up on a small window) keeps
everything about that character in view at once. At the top: the name it will have in the game (when a mod
changed it), a sentence saying where things stand ("2 mods in use - appearance needs a look") and a status chip
(*No mod yet*, *Choose a mod*, *Needs a look*, *Done*).

* **Mods** - the mods in use are always shown as rows, never folded into a sentence: the mod's whole name
  (long ones wrap), what it replaces (*Character*, *Kart*, *Wheels*, *Glider* - `unit_parts()`) and, with a speaker icon,
  *Voice* when it ships voice files (see below), the character's
  own mod first. The chips beside a name never share the row's fill (a checked or hovered row is tinted): what a mod replaces is an
  outline, and the chips that do something (pictures, voice) are filled with the card's colour, outlined in the accent, and fill in on
  hover. Open folder, Files and Remove are behind the **...** button on each row, which opens a small popup menu (the same kind as in the Icons table; Remove, in red, still asks first). The mods that aren't
  in use, and the tick boxes, are behind **Manage** (it becomes **Done**); with nothing ticked yet the whole list
  is open. Variants of the same files (colours, menu-sound options) are pick-one, and so are mods that each
  replace the same character's model: ticking one unticks the other, and "Select All" ticks only one of them
  (`modelGroup()` - the mod's *Character* tag plus the slot it writes to). Companions (kart, glider, voices)
  are never affected. Underneath sits a quiet
  "+ Add another mod" row that opens the GameBanana section (paste a link or browse) in place; with nothing
  downloaded the card is just that section, open, as "Find a mod". Clash cards are always visible, above.
  A UI-icons-only companion download filed under this character (no romfs, so it can't be ticked - see
  "Which texture a loose picture goes to" above) still gets its own row here rather than being invisible just
  because there's no checkbox for it: `Api.get_icon_only_mods()` lists it with which of the three icons it's
  currently supplying, if any, and a **Use game default** button when it is. Such a download that would
  otherwise land on a bare numbered `(2)` name because it collided with a sibling mod's folder is instead
  named `<mod> (icon pictures)` at download time (`_download_and_extract_one`), so this row - and the tile's
  own hover tooltip - reads as what it is rather than looking like an accidental duplicate.
* **Name** and **Icons** - two independent tasks, each its own row (like **Voice** below them), greyed out
  until a mod is ticked. Confirming one never marks the other: a mod that only changes the name (or only
  changes the icons, or only swaps the 3D model with neither) leaves the *other* row reading "Nothing to
  check", and a character only counts as finished once *every task that applies to it* is confirmed -
  `mod_manager.py`'s `_review_state()` returns `name_applicable`/`name_done` and `icons_applicable`/`icons_done`
  as two separate pairs; `reviewFinished()` in `src/ui/js/tiles-and-review.js` is the one place that combines them (both true,
  or not applicable, for each). Each row is a short walkthrough the first time, and a **read-only summary**
  (status "Completed", with **Edit** right beside the title) afterwards:
  - **Name** - "What should Birdo be called in the game?": the preview (the icon and the name plate as the
    game's select screen shows them) where the plate is the name box, already filled in with the guess (or the
    mod's own name; empty means the game's own). **Use this name** (or Enter) confirms it - `confirm_guessed_name()`,
    so a guess confirmed here no longer appears in the Commit page's guessed-names review. It reads "Keep the
    game's name" when the box is empty. A name typed but not confirmed is kept as a draft (`nameDrafts`, per
    character and tied to the saved name it was typed over), so leaving the card never throws it away - the
    row shows it again with "You had started typing this name - it wasn't saved yet.". Afterwards, the summary
    is just the name plate and where it came from.
  - **Icons** - "Do these icons look right?", one plain line for where they come from, and the three icons as a
    small table (icon | name | description) - **Select screen** (shown when you pick your character), **Mini
    map** (the marker on the course map during a race) and **Results screen** (next to your name in the race
    results). The picture is the button: hovering (or tabbing to) an icon puts a pencil over it, and clicking it
    opens the picture window for that icon alone (for a character with colours, the colour shown). A small tag
    by the name says where the picture is from - *Mod*, *Yours* or *Made from Select*. A picture the mod
    doesn't have shows a dashed "+" and a line "Not in the mod. Use the Select screen one" (see below). A row
    gets a **...** menu only when there is something more to do to it - *Undo my picture* (back to the mod's
    picture, or the game default if it has none), *Use game default* (turns the mod's picture down) or *Undo*
    for a made picture - and the **...** in the table's header holds what applies to all three ("Use one
    picture for all three...", "Use game defaults"). **Looks right** confirms it. When a mod ships several sets
    of icon pictures, picking one comes first; when no mod supplies an icon, a nudge offers "Add a picture"; a
    character with no icons at all but a model-swap mod (nothing to preview) just gets a plain confirm button -
    "give it a glance in-game". Afterwards, the summary is the colour strip if there is one, and the same table
    with a **Source** column ("King Dedede UI", "Made from the Select screen", "Your picture", "Game default")
    and no pencils or menus.
  The picture window lists **Icons from the mod** first - the pictures the mods provide for the character (what
  they already bring into its menu icons, plus other loose pictures in mods filed under it or named for it;
  `get_mod_icon_pictures()`), then any a mod filed under this character has for **another character**
  (named for someone else; a deliberate choice to use one) - used as they are when clicked
  (`use_mod_icon_picture()`, no cropping); then the screenshots and "Choose a picture from your computer..." (a
  tile the size of a screenshot), which go through the crop step. Changing, picking or resetting an icon never
  counts as confirming Icons: the walkthrough stays open so you see the result - and setting or clearing a name
  from outside the Name row's own buttons (the Commit page's guessed-names review, "back to normal name") only
  ever confirms Name, never Icons.
  A character can be left half-way on either task independently; its tile keeps the amber dot until both are
  confirmed (or not applicable). Leaving is never blocked - clicking another tile or tab is fine - but
  unfinished work stays visible and is asked about once: the tile keeps its amber dot, the Choose mods stage
  reads "6 mods ticked - 2 to finish" (amber) and the Next button's tooltip says how many, and pressing **Next** (or
  the Commit / UI / Switch stage buttons) while any character is unfinished opens a gate - "2 characters aren't
  finished", the names, and "If you continue, they're used as they are now - and a name that was only a guess is built
  into the game's menus without being confirmed" - with **Review them** (a guided pass, below) and
  **Continue anyway**; Escape or a click outside stays put (`passUnfinishedGate()`, which asks the backend afresh via
  `get_character_tile_view()`). **Review them** walks through the unfinished characters one after another
  (`startReviewQueue()`): a bar on top of each card says "Reviewing unfinished characters - 2 of 3" with **Skip** and **Stop**;
  finishing the last thing it needed shows the completed summary for a moment and then opens the next one; at the end the bar reads
  "All done - every character is finished." with the next stage's button (or "Done - 2 skipped, still unfinished."; the
  button then goes on without asking again) and **Close**. A character whose mods change nothing visible has neither row's
  walkthrough ("Nothing to check" on both; Edit is still there, though it does nothing since there's nothing to walk
  through). On a narrow card the Icons table's rows stack (picture left; name and description right, the menu at
  the corner). (`clKebab()` is the small popup menu: it closes on any click elsewhere and on Escape.)

**Characters with colours (Birdo, Yoshi, Shy Guy...).** The game keeps one set of pictures per colour, so the
Icons row shows a strip of colour dots (each one that has a picture from a mod shows it; a "!" marks a
colour with a missing picture) and the three icons of the colour picked. The count of pictures a mod ships is
given as colours ("9 colours (26 of 27 pictures)") rather than a bare number. `get_menu_look()` carries a `per`
list (one entry per colour) on each icon slot for such characters.

**Filling in a missing Mini map or Results picture.** Mods often ship a Select screen picture but not the other
two, which would leave the game's own Mini map / Results picture next to a modded Select screen. All three
icons are square (128, 64 and 52 px), so the Select screen picture can stand in for the others - it is scaled
down when the menus are built, the same way the user's own pictures are. A missing icon's row says "Not in the mod" and
offers **Use Select screen picture**; when several are missing (in any colour) a line above **Looks right** offers
to fill them all. It is an offer, never automatic, and nothing is "checked" by it - the row then says "Made from
the Select screen" with an **Undo**. `fill_missing_icons(name, colour, kinds)` / `unfill_icons()`. A made
picture is stored with a fingerprint of the picture it was made from (`fill_sig` in `ui-overrides.json`) and goes
away by itself when that Select screen picture changes or its mod is unticked; a picture a mod really ships
always wins over a made one. Colour-variant `per` data carries the private `src` only inside the backend.

**After "Use this mod" (GameBanana).** Choosing a mod in the browse window (or pasting a link and pressing Fetch)
closes the browse and detail windows and lands on the character's card, scrolled to the mod. A mod with a single
file is downloaded straight away (with a progress bar); a mod with several says "Choose which files to download"
with the newest / fullest ticked; a single file that mentions another character in its name isn't downloaded
without a look. Once a download is finished and nothing else waits, the "Add another mod" row folds shut, and a
lone mergeable mod is ticked as before.

**Waiting.** Where content is coming (the appearance step, GameBanana results and details, the UI files being
read) grey placeholder shapes sit where it will appear, next to a spinner and a plain sentence; downloads and
builds show an indeterminate bar. (`loadingNote()`, `skeleton()`, `skeletonGrid()`; they stand still when the
system asks for reduced motion.)

**Menu pictures.** A character mod row that brings pictures for the menus gets a picture tag (a small picture icon, before the
speaker): the tooltip says which of *Select screen*, *Mini map* and *Results* it has ("... (no Results)"), how many versions
and colours, and - when its pictures are named for a different game character - which one. Clicking it opens a window showing them at their real sizes, one block per source: the mod's loose picture
files (one per version) and the pictures in its packed menu files, with a dashed "Not included" where one is missing (a
missing Mini map or Results can be made from the Select screen in the Icons row). The window only shows; you choose which to use in
the Icons row. It replaces the old *icon* tag on character rows (which meant "any .png/.jpg anywhere in the mod folder" -
screenshots counted, packed pictures didn't, and it opened Explorer); courses, vehicles and the other cards keep that tag. The
tag follows what the Icons row itself would find: `Api.get_unit_pictures(unit_keys)` (per unit: `kinds`, `versions`, `loose`,
`packed`, `colours`, `for`) and `Api.get_unit_picture_sets(unit_key, siblings)` (the previews), both over `_unit_pictures()`.
Loose pictures count for the unit they sit in, or for every unit of the mod when they sit beside the units (`siblings` says
which units the card has); packed ones count when the unit's `common`/`menu` file holds this character's icon textures (the
same reading `get_menu_look()` gives a mod's own packed file - it can't say which of them the mod changed).

**Voice files.** A mod that ships character voices is tagged *Voice* (speaker icon) on its row - ticked or not, so it
helps you choose - and a character whose ticked mods ship voice files gets a small speaker badge in the top-left of
its tile (the review dot is top right); the tile's tooltip says which kind and from which mod. The files are the
in-race voice (`romfs/Audio/Driver/Driver_<name>.bars`) and the menu voice (`romfs/Audio/DriverMenu/MenuDriver_<name>.bars`),
found by `unit_voice()`; `get_unit_slots()` returns `voice: {race, menu}` per mod and `get_character_tile_view()` returns
`voice: {name: {race, menu, from}}`. A mod whose voice files are for somebody else's slot (the *Replaces ...* badge) gets
the row tag but not the tile badge. The tag means "voice files are there", not "the voice is different from the game's":
telling those apart would mean comparing against the game's own audio, which the app doesn't have.

**Playing the voice.** On a mod row the *Voice* tag is just a speaker icon (ticked or not - handy for choosing between
menu-sound options). Clicking it opens a window listing every sound in
the mod's voice files - character select, during the race, horn - each with its own round Play button and length;
pressing a button again stops it, and only one sound plays at a time (another line, closing the window or opening
another card stops it). The tooltip on a line is the game's own name for it (`pVO_CPC_OVTAK2`). The readable names are the
app's own guess at the game's abbreviations (`voice_audio.clip_label()`); the ones that aren't clear are left as spelled.
How: `voice_audio.py` reads the `.bars` archive (a table of sounds with their names), and decodes each sound - a
BFWAV, which for the game's voices is DSP-ADPCM in mono or stereo at any sample rate; 8/16-bit PCM also works - into a
16-bit `.wav` in plain Python, no audio libraries. `Api.get_voice_clips(unit_key)` lists a mod's sounds and
`Api.get_voice_clip(unit_key, clip_id)` returns one as base64 (`clip_id` is a place in the mod's voice files, never a
path); the page plays it with an `<audio>` element at 70% volume, because a
few mods' voices are mastered so loud they clip. A file the app can't read (cut short, another encoding) is said so in
words under the row. Nothing is written anywhere.

Only characters get this card; courses, vehicles and the More tab keep the old one. (`buildCharacterLook()`,
`assembleCharacterCard()`; the mod rows, Files panel, clash cards and GameBanana section are the existing
ones, recomposed.)

**Checking a character's look.** A character with ticked mods gets a marker on its tile until Name and Icons
are both confirmed (each only for the task that applies to it - see "Name and Icons" above): an amber dot =
"ticked, something not checked", a green tick = both checked or not applicable (no marker = no mods; the
hollow ring = mods downloaded, none ticked). Icons has its own **Looks right** button (with **Undo** once
checked) confirming the icons shown above it; Name has its own **Use this name**. The two never mark each
other - using your own picture, or choosing "back to normal" for icons, only ever confirms Icons; setting a
name, or choosing "back to normal" for the name, only ever confirms Name. Icons needs checking for a
character with a model mod of its own (not another character's slot) or any changed icon; Name needs
checking for one with an actual name change (typed, the mod's own, or a guess) - a mod with only voices or
kart parts leaves neither to look at. What was checked is stored in `look-reviews.json` (`characters` bucket
for Icons, `names` bucket for Name) as a signature of the character's ticked mods, and every signature ever
checked is kept: ticking a mod off and on again is still checked, while a different set of mods (a new one
ticked) needs looking at again, for both tasks. Everything starts unchecked (`get_character_tile_view()`,
`_review_state()`, `confirm_guessed_name()`, `mark_icons_reviewed()`, `unmark_icons_reviewed()`).

**Keeping the tiles quiet.** In the wide layout a tile that shows a picture has no name label - which is
most of them once base files are set up, not just modded ones: the name plate under the grid follows the
mouse (hover any tile and it shows that character's name, plus the game's name in brackets for a modded
one), and falls back to the selected character when the mouse is elsewhere. A tile with no picture at all
(no base files yet, or nothing to compute one from) keeps its name, and on a small window (no plate) every
tile keeps its name. The
"1/4" (ticked / downloaded) badge is off by default (`show_tile_counts`, Settings > App experience): a tile
with mods downloaded but none ticked gets a small hollow ring instead, and the tile's tooltip still says
"3 of 14 mods ticked". The red "!" conflict badge and the attention dots are unchanged. Course and vehicle
tiles keep their badges.

**The character grid shows every tile's actual look, not just the modded ones.** Once base game
files are set up, an untouched character's tile shows the game's own select-screen icon - the same
picture `get_menu_look()` already draws on the Character screen, just reused rather than thrown
away (`get_character_tile_view()`/`get_character_looks()`, one pass over the plan for every tile).
A character a mod (or you) actually changes shows that icon instead - the first available of the
select-screen, results and map ones, preferring an actually-modded kind over a merely-vanilla one
so a mod that only touches, say, the map icon still wins the tile - with the modded name under it
instead of the game's. A tile with nothing ticked stays faded (`.no-mods`, unchanged) so it's still
obvious at a glance which characters you haven't touched; before base files are set up, or for a
character with nothing to compute a picture from at all, the tile falls back to its plain badge and
name as before. Hover a tile to see where the name came from (the tooltip no longer mentions the icon - the
tile's picture shows that, and clicking the tile shows the rest), and "No mods yet" for one with
nothing downloaded (no gray text on the tile itself for that anymore; it only lives in the tooltip).

**The character's select sound.** Clicking a character's tile plays the character-select voice its ticked mods bring (the
"Character select" sound in a `MenuDriver_*.bars`: `Api.get_select_voice()`) - whether or not its appearance is finished -
and so does the picture on the Villager / Inkling tile or that card's Boy | Girl switch, and the moment a character's
appearance becomes finished (its look checked, or a mod with nothing to check ticked). While it plays, the speaker on the tile
lights up and its two waves pulse. A tile that has such a sound says so in its tooltip ("Select sound: click to hear it";
`get_character_tile_view()` reports it as `voice[name].select`). The speaker itself is still about voice files in general:
a mod with only in-race voice gets it too, and clicking that tile plays nothing. Not a mod whose voice files are for another
character's slot, and not a voice file that was left out of the merge; with several mods that bring one, the first ticked one.
It uses the same one-at-a-time player as the Voice lines window (a new sound stops the last), at 70 % volume. Off with
Settings > App experience > "Play character-select sounds".

**Villager, Inkling, Link and Metal / Gold Mario (one slot in-game, two characters).** Clicking their tile opens a card straight away - there is no
"which one?" step. At the top of the card a two-part switch moves between the two (Boy | Girl, Girl | Boy for Inkling): each side
shows its own picture, its mod's name (or "1/2 ticked", "no mods yet") and its review dot / tick, and it redraws as you tick
mods. The card opens on the one that still needs its appearance looked at, else the one with ticked mods, else the one you used
last (clicking the tile again while one is showing keeps it). On the grid the tile shows both: when either has a picture
(the game's own counts too, so this is now the common case once base files are set up), two smaller pictures sit on the
diagonal (first option top left, second bottom right), and a variant with nothing to show a picture from at all is a dashed
placeholder with its label; clicking a picture opens that variant. The tile does not cycle between them - half the information
would be missing at any moment, and motion means "loading" on the grid. With no picture on either, the tile is the normal
gradient one. Hovering the tile puts "Boy: Yoda · Girl: Pinkie Pie" on the name plate.

**Link** is the same, with the switch reading **Classic | Breath of the Wild**. The game has two full sets of Link files - `Link` and
`LinkBotw`: models, race and menu voices, and select / results / map icons - that share one select-screen slot (the Breath of the
Wild one is the default once it is downloaded; the classic one is based on Skyward Sword). So they are two roster characters:
"Link" (the classic one, keeping its old folder and settings) and "Link (Breath of the Wild)" (`DRIVER_SLOTS["LinkBotw"]`). Each has
its own model group (a mod for one is not pick-one with a mod for the other), voice editor and icons; a mod that replaces both is a
pack, listed on both cards; a download or mod filed under Link that only replaces `LinkBotw` files is flagged as replacing the other
version (GameBanana downloads are moved there on their own, see [Refiling mods](refiling-mods.md)). Mods already filed under Link
are not moved automatically. The game has one "Link" name text for both, so a name given to either applies to both (`NAME_ALIASES`).

**Metal Mario | Gold Mario** is the same again (the tile is named for Metal Mario; its gradient is silver and gold). Here each has its
own name text (`Common.msbt` 1019 and 1054), icons (`tc_Chara_MetalMario`, `tc_Chara_GoldMario`, and the results / map ones) and voice
archives (`MetalMario`, `GoldMario`), so nothing is shared and each is fully its own character; Gold Mario becomes the default once it
is unlocked in the game, which the app doesn't need to know.

**Ticking a character mod tries to name the character** (`sync_auto_names()`, run by every
`save_checked()`, so every way of ticking is covered). Only mods that replace the character's
MODEL (`Driver/*.szs`) and belong in that character's slot count - voice-only, kart-only and
"replaces another character" mods don't. In order: (1) the mod's own text - a `message.sarc`
with a different name at the character's entry - in which case nothing is stored (the UI step
applies it); (2) the mod's name (GameBanana's, else its folder's), cleaned by
`suggest_name_from_mod()` ("Sandy Cheeks in Mario Kart 8 Deluxe" -> "Sandy Cheeks"; a name that is just
the character's own, too long for the menus (> 24 characters) or only noise words is dropped);
(3) the folder inside the mod. The guess is stored in `ui-overrides.json` flagged `"auto"`, so it
disappears when the mod is unticked, never replaces a name you typed, and once you use "Back to
normal name" on it, it is never guessed again (`declined_names`). The Menu look card says
"guessed from ...". Like any name it takes effect when the UI step is rebuilt.

**Packed menu files beside `romfs/`.** Some mods put `UI/cmn/common.sarc` etc. (or
`icons/common.sarc`, `Character name change files/message.sarc`) NEXT TO their `romfs/`
instead of inside it. `ui_setup.unit_extra_archives()` finds them by what they are, not by
folder name: `common.sarc`/`menu.sarc` files that really hold the character-icon entry; a
`message.sarc` in a language folder, or - with none - one whose text is English (it counts
for USen and EUen; a non-English one with no language folder is not guessed). The ones
inside `romfs/UI` win; the others only fill in what is missing. They are never staged
(a packed archive can't be copied straight in), but they count toward the Commit page's
"N mods change menu pictures or names" and are combined in the UI step like any other.

**Loose icon pictures.** Many mods don't ship the packed `common.sarc`/`menu.sarc`
at all but a folder of PNGs named `tc_Chara_<name>^l.png`, `tc_MapChara_...`,
`tc_edChara_...` (meant to be injected by hand with Switch Toolbox). The UI
analysis never read those, so such a mod looked "Unchanged". They now show up
under the Menu look card (`get_loose_icon_sets()`; a mod's own folder is
scanned, skipping `romfs/`) grouped into versions by the suffix Windows added to
duplicate names (`^l`, `^l1`, `^l2` - a mod often ships one per costume).

* **One version -> automatic.** For a character with exactly one ticked mod that
  ships pictures, and exactly one version of them, `gather_auto_icons()` uses
  them for that character (the pictures are named for the mod's own character,
  so the mod's *filed-under* character decides where they go). They enter the
  plan as their own variant, "<mod> (icon pictures)" (`is_auto`), shown in Menu
  look as "Automatic". Never applied where a packed archive already changes that
  icon, where the user chose icons, or where the user turned them down ("Back to
  normal" is remembered in `ui-overrides.json` > `declined`).
* **Several versions -> asked.** The character lands in `needs_choice`: its Menu
  look card shows the versions with thumbnails and a **Use for <character>**
  button (`use_loose_icon_set()`), the UI step and the Commit page list every
  character still waiting, and the step bar turns amber. Until picked, the
  game's normal icons are used.
* Pictures are recognised by name (`tc_..._<name>.png`, with or without the `^l`;
  "... Map.png"/"... Menu.png"/"... Common.png"), or - in a folder whose name says
  `UI` or `icon(s)` - by exact size when they have no telling name: 128x128 is the
  select icon, 64x64 the map icon, 52x52 the results icon (at least two of the
  three must be there). A single picture beside a `tc_` set fills the kind it lacks.
  Pictures told apart in *different* ways count together when they sit in the same folder: `UI images/Menu.png`
  (by its name), `Race Mini Map.png` (by its name) and `Race end.png` (only by its size) are one set - two or more
  different icons in a folder called `UI`/`icons`, or every one exactly the game's size for what it is (Pikachu in
  MK8D). One picture per icon (the first by name). As a last resort - only when the mod has no set at all - a folder
  holding all three exact icon sizes is icons whatever it is called (`Image Files Used/128.png, Race.png, 52.png`);
  next to a real set those are copies and are ignored, so they aren't a second version.
  Pictures inside a mod's `romfs/UI` count too (some authors leave the pictures they made there - Iggy's
  `romfs/UI/Common/tc_MapChara_Iggy^l.png`, Toad's `romfs/UI/Menu.PNG` / `Map.PNG` / `EdMenu.png`); nothing else inside a
  `romfs/` is looked at (`_icon_walk()`). `EdMenu` / `Ed Menu` is the Results icon, not a second Menu.
  **Colour packs** (`_colour_pack()`, Fall Guys): pictures named by colour - `Map Light Blue.png`, `Menu Black.png`, `Ed Menu Pink.png`,
  in any folders - for a character whose icons come in colours. The colour name is matched to the game's own slot for it
  (`COLOUR_WORDS`). That order differs per character and was read off the game's own icon textures (`COLOUR_SLOT_NAMES`):
  Yoshi green, red, dark blue, light blue, yellow, pink, black, white, orange; Shy Guy red, green, blue, light blue, yellow, pink, black,
  white, orange; Birdo (named by her body, the bow is another colour) pink, red, blue, light blue, yellow, green, black, white, orange;
  Inkling Boy blue, purple, teal; Inkling Girl orange, lime, pink. Only words that mean one slot are listed ("blue"/"navy" = the dark blue,
  "cyan"/"aqua"/"sky blue" = the light blue; Shy Guy's "grey"/"silver" = his white). One colour the game has no slot for ("Purple" for Yoshi)
  takes the single slot left over - so Fall Guys' Purple goes to Yoshi's dark blue slot, a reasonable reading but not something the files
  prove; two or more such colours, or a name that could be two slots (Birdo's "Purple": her blue or...), are left out rather than guessed.
  The set's pictures carry the slot's name (`Yoshi02`), so they reach exactly that colour.
  **Numbered colours** (`_numbered_colours()`, Shy Guy Ninja's `tc_Chara_shy0.png` .. `shy8.png`, results `shy0k.png`, map `shy0kk.png`): a
  name the game doesn't have, with a number in it, is that colour's own picture when the numbers of a kind are exactly the character's colours -
  0..n-1 (the game's slot numbers) or 1..n. Checked on Shy Guy Ninja against the game's own icons: shy0..shy8 are slots 00..08. Fewer, or a gap:
  left alone (they would all go to every colour, and the last would win). One-colour characters keep their made-up names.
* Small pictures are kept at their exact size (a 64x64 map icon is
  byte-identical in the built file). An icon the base file doesn't have (a
  character added in a newer game version than the base copy) is listed as
  "can't be added" like any other.

**Colour-variant characters.** The game keeps one icon texture per *colour* for Yoshi
(`Yoshi00..08`), Shy Guy (`Heyho00..08`), Birdo (`Catherine00..08`) and the Inklings
(`SplatoonBoy00..02`, `SplatoonGirl00..02`) and has no plain `Yoshi`. `ui_setup.COLOR_VARIANTS`
records the counts; `slot_items()` gives every texture of a character's icon, and the Menu
look card treats them as one slot ("all 9 colours" / "8 of 9 colours"). A picture the user
supplies goes to every colour.

**Which texture a loose picture goes to** (`resolve_pictures()`): a picture named for a real
game texture (`tc_Chara_SplatoonGirl02^l`) goes exactly there; one named for something the
mod made up (`MarioSunshine`) or by purpose goes to all of the character's textures; one
named for a *different* game character (Vanellope UI's `BbRosetta` filed under Wendy) is
**not** applied automatically - the card says so, the pictures show up in Baby Rosalina's
Customize list ("filed under Wendy, but named for Baby Rosalina"), and "Use these for X
anyway" overrides the rule. Pictures named by purpose (`King Dedede Map.png`, `... Menu.png`,
`... Common.png` = map / select screen / results; at least two kinds, small images) form a
set too. UI-only downloads (a folder with no `romfs/` anywhere - a "UI icons" companion) can't
be ticked, so `gather_auto_icons()` considers them regardless of ticks.

**Icons a mod ships but that can't be applied** (a picture of another shape or format, an icon
the base file lacks) are shown as "can't apply" on the card with the reason, not as "from a mod".
A picture that is only a different size (Dr. Mario's 40x40 map icon vs the game's 64x64) is
scaled to fit (LANCZOS, alpha-safe, re-laid-out for the GPU like the base texture) and marked
"resized to fit" on the card and "resized from 40x40" in the guide; the build check
resizes the mod's picture the same way to compare.

**Long labels.** `mod_label()` shows a mod folder's unit name only when it adds something (a
re-spelling of the mod's own name doesn't), cuts the mod name to 40 characters and the unit to 32,
and the conflict card's tooltip carries the full names (`full_labels`).

**Adding many mods.** `get_unit_slots()` / `slot_characters()` read each unit's `Driver/*.szs`
and voice/menu-sound files (`DRIVER_SLOTS`: driver name -> character, verified against the
mods downloaded for each character; unknown ones such as Larry/Isabelle/Mii/Birdo/Diddy/Funky
Kong are never claimed) to badge a unit "replaces Donkey Kong" and warn at download time
(`_character_slot_mismatch()`, shown like the course/vehicle slot warnings). "Select All"
(per item and per Full List category) skips units that replace another character's slot and
ticks only one of several units that write exactly the same files (colour variants,
menu-sound options - the already-ticked one, else the first); "Deselect All" clears
everything. In the fetch card, a multi-file mod gets its most likely file pre-ticked
(`suggestFiles()`: newest / fullest / named for the item; not old, alternate or optional).
`gb_download_files()` fetches several files at once (`gamebanana_api.prefetch_files()`, 4
connections; GameBanana serves ~100-150 KB/s per connection) before the usual one-by-one
extract. The Menu look card offers "Use "Sandy Cheeks"" chips built from the mods' own names.

Caveat: "Unchanged" means no mod changes it relative to the *consensus* of your
mods' copies - if every copy already carries the same custom icon it counts as
unchanged and is what's shown.
