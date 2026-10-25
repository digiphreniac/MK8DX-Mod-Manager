# Merge rules and conflicts

What a commit never copies in (`BGM.bars`, packed `UI/*.sarc`), and how clashes between mods are settled by leaving files out.

## Merge behavior: `Audio/Static/BGM.bars` is never merged in

`romfs/Audio/Static/BGM.bars` is a single, game-wide table of short music
"prefetch" clips - one per track - that plays for the first second or so of
a course while the real, full-length music streams in separately from its
own `.bfstm` file in `Audio/Resource/Stream/`. It isn't a per-course file,
even though plenty of course mods bundle a full rebuilt copy of it just to
patch their own track's prefetch entry.

That makes it the single biggest source of merge conflicts between mods for
*different* courses in the same cup: two course mods that have nothing else
to do with each other can still collide the moment both happen to include
their own copy of this shared table. Before excluding it, every currently
downloaded course mod that bundles it was checked, and all of them also ship
their actual music as their own uniquely-named `.bfstm` stream file - so none
of them actually depend on `BGM.bars` to play their music; it only buys back
that ~1 second of prefetch polish (several, including the mod behind N64
Bowser's Castle, turned out to just be redistributing
[ThatOneMartini's "Tiny BGM.bars"](https://gamebanana.com/mods/456533)
verbatim, byte-for-byte, which does the same thing on purpose game-wide).

Given that, `mod_manager.py` (`_MERGE_SKIP_RELPATHS`) never copies this path
in from *any* mod, in either Merge & Stage or the live conflict checker - the
base game's own vanilla `BGM.bars` is always left in place. This is a
heuristic based on everything downloaded so far, not a guarantee: a course
mod that delivered its music *only* through a `BGM.bars` prefetch entry, with
no separate stream file, would have its music silently dropped rather than
flagged as a conflict. None of the mods checked so far do this - the "tiny
bars + stream files" approach is clearly the community-standard convention -
but it's worth knowing the failure mode exists if a future download behaves
differently.

## Merge behavior: packed `UI/*.sarc` archives are never merged in, loose UI textures are

Course and character mods commonly bundle their own copy of `romfs/UI/...`
content alongside their real mod files. Two very different things hide under
that same folder, and `mod_manager.py` (`_compute_claims()`) treats them
differently on purpose:

- **Packed archives** (`common.sarc`/`menu.sarc` for character-select icons,
  `message.sarc` for a locale's entire text table - including every course's
  display name) bundle *every* character's icon, or *every* string, in one
  file - never just the one entry a mod actually changed. Merging a mod's own
  copy in directly would silently wipe out every other character/course's
  icon, or every other piece of text, not also present in that mod's own
  rebuild. These are always skipped, exactly like `BGM.bars` - the base
  game's own copy is left in place. The safe way to update them is to build
  **one** combined file from all ticked mods - [Menu icons & text](menu-icons-and-text.md#menu-icons--text-combined-character-icons-and-coursecharacter-names) does
  that automatically, as part of every commit (hand-injecting with Switch
  Toolbox still works but is only the fallback; see the in-app Help page and
  "UI Icon Worklist" in Settings).
- **A folder named like an archive** (`UI/cmn/common.sarc/Icon_X.bntx`, ...): some mods ship an
  archive's contents *unpacked*, as a folder with the archive's name. It is skipped exactly like
  the archive (`_packed_ui_archive_root()` returns the `.sarc` part of the path; one entry per
  folder in `ui_archives_skipped`, marked "a folder, not an archive"), and the Commit page shows a
  warning naming the mod. Copying it would leave a *directory* where the game expects the archive
  *file*, and the combined archive the app builds under that name would land inside it
  (`common.sarc/common.sarc`) - the game then aborts before the title screen. The loose pictures
  are not used (the app does not read them); the rest of the mod is copied.
- **Two claims that can't share a place** (one mod's file is another's folder, any mod or the
  app's own combined files): `merge()` refuses before touching the staging folder
  (`_layout_clashes()`), naming both files. After every copy `_verify_staged()` checks the staged
  `romfs` against the claims (missing, wrong size, a folder named like an archive, a file nothing
  claimed); on a mismatch the commit fails loudly and `last_commit` is cleared, so the page never
  shows a staging folder that doesn't match what was selected as done.
- **Loose, individually-named UI textures** - most commonly a course's own
  `UI/cmn/menu/ym_CoursePict_<internal id>.bntx` select-screen thumbnail and
  `UI/cmn/ending/ym_AwardBG_<internal id>.bntx` results-screen background,
  or a character mod's own kart-select portrait textures - are a completely
  different, safe case: the internal id baked into the filename means nothing
  else can plausibly claim that exact path, so they're merged in normally
  like any other romfs file.

This used to be a single blanket rule (skip *everything* under `UI/`,
regardless of file type), inherited from the character-icon case without
being re-checked for courses - which meant every course mod's own select-
screen icon and results background was being silently dropped on every
merge, even though it was perfectly safe to include. Confirmed by scanning
every currently downloaded course mod's own `UI/` folder: the packed-archive
convention (`.sarc`) and the loose-per-course-texture convention (`.bntx`)
never overlap, so the fix is a plain file-extension check, not a per-category
guess.

Nothing skipped this way is silent any more: the merge log lists every skipped
`.sarc` by mod, warns when a mod contained *only* packed archives (so ticking
it did nothing), and such mods carry a "packed archive only" badge in the
"Mods to merge" list (`Api.get_packed_only_units()`). In the **UI** category,
downloads with no romfs that are UI art (PNG/texture icon sets, a bare
`.sarc` - `looks_like_ui_art()`) are classed `ui_assets` and listed in
Settings' UI Icon Worklist under "UI mods", same as character icon dumps.

## Conflicts: leaving files out

Two mods writing different bytes to the same romfs path clash. A clash is
settled by leaving the file **out of the loser** - stored in
`excluded-files.json` as `{mod key: {normalised path: {path, reason, kept_from,
added}}}`, applied in `_compute_claims()` before any claim is recorded. So the
same mechanism covers "keep Steve's emblem", "use the game's own file" and a
plain "don't copy this file from this mod" (a mod popup's **Files** button lists
everything a mod ships with a checkbox each).

* `_conflict_groups()` groups clashes per *set of mods* (one decision for 40
  files), classifies the files (`path_kind()`), reports how much of each mod is
  affected (`4 of 37 files`) and suggests keeping the mod that belongs in that
  slot (a mod filed under Funky Kong that really replaces Donkey Kong's model loses
  to the actual Donkey Kong mod - `_slot_mismatch()`), then the one that relies on
  the files most, then the name that sorts first.
* `resolve_conflict_group(mods, paths, keep)` excludes the paths from every
  mod but `keep` (skipping byte-identical copies); `keep=None` = the game's own
  file. Code patches (`exefs/...` pseudo-paths) can't be split - only "untick".
* Cards are `buildConflictCard()` in the frontend and appear in the mod popup
  (clashes with *any* ticked mod, not just the same item's), the Commit page and
  Settings > "Conflicts and omitted files" (a Review button with a one-line summary beside it, which opens the full list in a modal of its own, since it
  can grow long; always available, Advanced mode no longer gates it). The older `conflict-resolutions.json` priority list is
  still honoured when present but nothing writes to it any more.
* Exclusions of a mod that is no longer downloaded are dropped lazily.
