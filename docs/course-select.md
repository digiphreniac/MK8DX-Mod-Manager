# Course Select and course icons

The Course Select screen (the game's Prix, sized to fit), the course card, and how a course-select icon is previewed or generated from a screenshot.

## Course Select: the game's Prix, sized to fit

The Courses tab shows the 24 Grand Prix as the game's own medallions on a board (like Character Select's), the selected
Prix's four courses under it, and a name plate along the bottom.

- **The medallions** come from the base game files (no mod needed): `menu.sarc` -> `mn_L_CupSlctBtn_00.szs` -> one 200x200
  `ym_CupIcon<Name>^h` texture per cup. They are 16-bit blue-green-red 5-6-5 with no alpha - a round medallion on a square
  backdrop - so `cup_icons.py` unpacks them, swaps red and blue, and cuts the circle. `Api.get_cup_icons()` returns
  `{cup name: PNG data URI}` (decoded once, about a second, then kept in `image-cache/` until `menu.sarc` changes). The base game's
  cups are named after their emblem (Mushroom ... Thunder) or, for the four DLC-wave cups, `DLC02`..`DLC05`; the Booster
  Course Pass cups are `Charger00`..`Charger11`, in the pass's order - `cup_icons.CUP_TEXTURES` is that mapping, checked
  against the decoded pictures. Before Setup has copied the game's files there is no artwork, and the tiles keep the old
  gold-rimmed emoji look until there is.
- **The name plate** is Character Select's (same look): the selected Prix, or - after you click a course - that course
  with its Prix small and dim beside it; while the mouse is over a tile it shows that tile's cup or course instead, and
  goes back when the mouse leaves. Choosing another Prix (or clicking the selected one again) drops the course selection.
  Course tiles keep their yellow brackets while selected; the white hover frame works as on the character grid.
- **Two pages, nothing scrolls.** The 24 cups are on two pages - the game's 12 and the Booster Course Pass's 12 - with an
  arrow beside the board to turn between them and a small caption ("Mario Kart 8 Deluxe - 1 of 2"). A dot on the arrow says
  the page it leads to has modded courses. Selecting a cup on the other page (or jumping to a course from a conflict) turns
  to its page. `fitCourseScreen()` (`views.js`) sizes everything from the room there is: cups per row (`--cols`; it tries
  6, 4, 12 and 3), a cup (`--cup`) and a course tile (`--course-w`, 16:9 pictures), keeping the layout where the smaller of
  "cup size" and "course tile size", each against a comfortable reference, is biggest. It re-runs when the window resizes
  and whenever the tab is shown. A cup with no modded course is faded (like an untouched character); a bubble shows how many
  of its courses are modded. All of it is in `css/course-screen.css`, which comes last so it overrides the shared tile
  rules. (An earlier version showed all 24 at once, four rows of six, when the window was big enough; two pages at every
  size won out: bigger cups and course tiles, and one layout to reason about.)
- **The game's own course pictures.** A course tile with no picture from a mod shows the game's own course-select picture (from
  the base game copy - `Api.get_course_default_pictures()`, decoded like a mod's and cropped to the same visible window, under
  the same white name banner), faded like any untouched tile; a ticked mod that ships its own picture replaces it. Base-game
  courses are found by their internal id (`Gu_FirstCircuit`; Animal Crossing's four seasons share `Du_Animal`); the Booster
  Course Pass's 48 are `DLC01`..`DLC48` in the pass's order (their internal ids, `Cnsw_NN`, are in a different order - the
  mapping was checked against the pictures). The course card's Icons step shows the same picture when the mod brings none.

### The course card

Clicking a course opens the same kind of guided card as a character (`course-card.js`; the mods list, "Find a mod" /
"Add another mod" and conflicts are built by `openCharacterModal()` for both): a head with the course's (modded) name, its
Prix and a status chip, the mods in use with **Manage**, then two steps.

- **Name** - asked when something wants the course called other than the game's own name: the mod's own text, a name you
  typed, or a guess from the mod's name or folder (`get_course_look()` -> `name.suggestion`; you use it, change it, or keep
  the game's). Nothing to check otherwise.
- **Icons** - the course-select picture. A ticked mod that bundles its own `ym_CoursePict_*.bntx` needs no check; otherwise the
  game's own shows, or a picture you make from one of the mod's saved screenshots (the existing crop tool,
  `generate_course_icon()`), and you settle it once ("Keep the game's picture" / "Use this picture").

Each is confirmed for the SET of ticked mods and remembered in `look-reviews.json` (`course_names`, `course_icons`, next to the
characters' two records - `_ticked_by_course()`, `_mark_course()`, `confirm_course_name()`,
`mark_course_icon_reviewed()`); typing or clearing a name confirms the Name step. `get_course_tile_view()` gives the course
tiles their marker (amber = something needs a look, green = done - `refreshCourseReview()` / `applyCourseMarkers()` in
`views.js`, cached in `courseReview`).

**Unfinished courses count like unfinished characters.** A course with ticked mods is unfinished until its Name and Icons steps
are *explicitly* confirmed (where they apply - see above). They feed the same three things: the step bar's "N to finish", the
Next button's hint, and the prompt when leaving Choose mods ("2 characters and 1 course aren't finished" - `freshUnfinished()`,
`showUnfinishedGate()` in `tiles-and-review.js`). "Review them" is one guided pass over both kinds (`reviewQueue.items` are
`{kind, name}`): characters first, then courses; a course opens with its Prix and the course selected (`openCourseCard()`), the
bar on top says "Reviewing unfinished courses (or characters, or characters and courses) - 2 of 3", and finishing a card moves
on after a moment (`onItemFinished()`).

## Course-select icon preview & generation

The Course Select strip shows each checked course mod's actual in-game
select-screen picture (its `ym_CoursePict_<internal id>.bntx`, if it has
one) inline, so it's obvious at a glance which courses do or don't have
one - not just a guess from file names.

**Decoding** (`bntx_decode.py`) parses the `.bntx` header itself, undoes the
Switch's block-linear GPU texture tiling (the documented Tegra X1 GOB
addressing scheme), and hands the actual BC7 block decompression off to
Pillow's own DDS reader rather than reimplementing it - BC7 is one of the
fiddlier block formats to get exactly right by hand, and Pillow already
ships a tested decoder for it.

**Generating** an icon for a course whose mod doesn't bundle one ("Icon
from screenshot" on that mod's card, using its own GameBanana screenshots)
works the other direction (`bntx_encode.py`): the chosen screenshot is
cropped and composited into the fixed 304x256 canvas and written as a
plain **RGBA8** texture, not BC7 - deliberately, since that avoids needing
a BC7
*encoder* (a much harder, lossy problem than the decoder), and RGBA8 is a
standard, universally-supported baseline GPU format; the only real cost is
a larger file (roughly 300KB instead of 80KB) for one UI image, which is
immaterial. Rather than building a new `.bntx` container's string table/
name-lookup tree/relocation table from scratch, the generator loads a real,
already-working `CoursePict.bntx` from any of your own downloaded course
mods (via the vendored `_bntx_structs.py`, unmodified from
[BNTX-Editor](https://github.com/aboood40091/BNTX-Editor), GPL - see that
file's own docstring for why it's left unmodified rather than
hand-transcribed) and mutates only the handful of fields that actually
need to change - everything else keeps the exact structure a real, working
file already has. Generated icons live in `course-icons/` (see [architecture.md](architecture.md)),
never inside the mod's own downloaded folder, so they survive a
re-download/update of that mod and are easy to tell apart from what the
mod itself actually shipped.

**The 304x256 texture isn't fully "visible" picture** - every real
mod-provided CoursePict checked (four different mods, different authors)
leaves a near-identical black border baked into the raw file: an 8px
margin on each side, 29px on top, and 65px on the bottom, framing a
288x162 (exactly 16:9) visible window. That's not per-author styling
(the numbers land within 1px of each other across completely unrelated
mods) - it's the real template, and the lopsided bottom margin is almost
certainly reserved for the course name/mode text the game's own UI draws
over this texture at render time. `generate_course_icon()`
(`_COURSE_PICT_CONTENT_*` in `mod_manager.py`) composites into that exact
same window rather than filling the full canvas, and the crop tool's
aspect ratio (`ICON_GEN_COURSE_ASPECT` in `src/ui/js/help-and-icon-generator.js`) targets that 16:9 content
window directly - a typical 16:9 screenshot needs no letterboxing at all
before the app adds the matching border around it.

This can't be verified on real hardware from here, only structurally (the
generator's own round-trip: write, then re-parse and confirm every field
matches what was intended) - which is exactly why it's built on a real
file's proven structure rather than one built from scratch.
