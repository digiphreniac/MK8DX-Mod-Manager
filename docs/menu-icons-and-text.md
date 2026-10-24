# Menu icons and text

The combined character icons and course/character names the app builds automatically on every commit.

## Menu icons & text: combined character icons and course/character names

Not a step of its own (it used to be - see the [Phase 3 note](ui-and-flow.md) at the end of
[The guided flow](ui-and-flow.md#the-guided-flow-step-bar-next-button-commit-page)) - `_build_ui_archives()` (`mod_manager.py`, on top of `ui_setup.py` + `ui_archives.py`) runs
automatically inside `merge()`, right before its own file-copy pass, whenever anything needs
combining (`_ui_build_needed()`: a ticked mod's own `common.sarc`/`menu.sarc`/`message.sarc` for the
current language, or the user's own icon/name overrides). No outside tools, and nothing to run
first - committing is enough.

**Saying what happened.** No `common.sarc`/`menu.sarc` in the output is normal when no selected mod changes anything in
them (the game's own are used), but it looks the same as a failed build, so the commit log always says which it was:
`describe_ui_build()` adds one line per file ("built", "not made - no selected mod changes anything in it", "not made - no copy of
the game's own to start from"), and when `_ui_build_needed()` is false the log says "nothing to build" (and how many files built
earlier in `ui-icons/` are still included). The Commit page shows an info card, `"no-menu-icons"`, when character mods are selected
but none changes a menu picture or name the app can use. When someone reports missing icons, ask for the commit log (the Copy log
button on the Commit page), not only `mod-manager.log`.

The Commit page itself only shows a lightweight, informational warning when there's something to
combine (`"ui-archives"` in `_commit_summary()`) - no card, no controls. Language is a set-once,
rarely-touched preference (already asked once during the Setup wizard), not something worth a
dedicated section competing for space on Commit every single time; the warning's **Open Settings**
button (`"action": "settings"`) is there for the rare time someone does want to change it.

Everything about menu icons & text that isn't "just commit" lives in Settings' **"Game language"**
card (`renderUiSetupSettingsCard()` in `src/ui/js/settings-panels.js`) instead:
- **Language** (`ui_setup_locale`; `message.sarc` is per language, icons are not). The list has an
  **English (unspecified)** choice for someone who doesn't know which English their Switch uses: it is stored as
  `ui_setup_locale` = USen plus `ui_setup_extra_english` = true (so both Englishes are built), and shown as that one choice.
  Both are persisted settings, read by `merge()` at commit time.
- **The rare pick-which-mod-wins conflict** (`renderUiArchiveConflicts()`) - only when two different
  ticked mods change the exact same icon or text entry to different values (`_conflicts()` in
  `ui_setup.py`); `_winners()` already has a sane default (the first mod, alphabetically) so this is
  an optional override, never something that blocks a commit, and it's the only piece of the old
  per-mod diff view that survived - everything else it used to also show (a preview of every mod's
  icon/text changes, one archive at a time) was dropped: it's redundant with what the character/
  course card's own Menu look already shows, in the context of that one character, which is a
  better place to review it than a second, decontextualized copy here.
- Nothing about the built files themselves: no status line per archive and no Open-the-folder button, since there is nothing to do
  with them - the step bar says when a commit is due. The one exception is a single warning line when a built file is damaged
  (its re-read check found a problem). There are no Rebuild or Undo buttons and no "do it by hand in another program" route: the files are built by every commit (and by
  nothing else - downloading or ticking a mod only updates the page's own reading of its menu files), and a commit replaces the three
  built archives (the old file is kept in `ui-icons-backups/`), so a hand-made copy saved at the same path would not survive the next
  one, and a removed build would be made again by the next commit. To drop a mod's menu changes, deselect the mod. Loose UI art a mod
  ships that can't be merged is what the UI Icon Worklist is for.

**Guessed names** (`_guessed_names()`, `"guessed-names"` Commit-page warning) still opens its own
small modal to confirm or edit each one (`openGuessedNamesModal()`) - that one stayed a Commit-page
warning rather than moving to Settings, since it's tied to the mods currently ticked, not a
standing preference. An **icon pick needed** (`_auto_icons()`, `"icon-choice"` warning) still links
straight to the character's own card, same as before.

The actual build - writing the files into `ui-icons/`, backing up anything it replaces to
`ui-icons-backups/`, then re-reading each built file to check every change is really in it (a green
tick per file) - happens inside `merge()`, so its result is just part of the normal commit log. A
commit calls `_build_ui_archives()` directly (no separate staging step - the copy pass right after
already picks up `ui-icons/romfs`); it is the only caller.

`_ui_signature()` is what "has anything changed since the last build" means: every checked mod's
packed UI archive (path/size/mtime), the language + "also build the other English" choice, the
conflict picks, the user's overrides, and the base game files' own mtimes. A commit's own
staleness (`commit.stale` in `get_flow_status()`) folds this in too - so changing only the
language, with no mods re-ticked, still makes a re-commit necessary, exactly as if a mod had
changed. (This used to be tracked as a separate "ui" step's own done/stale, with its own gate on
`recommended` - folding it into `commit.stale` was the real fix here, not just a rename, since the
old `_ui_signature()` never actually included the language choice despite its docstring claiming it
did.)

**Your game's own files (required).** The finished `common.sarc` / `menu.sarc` /
`message.sarc` are the game's own file with the changes swapped in, so the app
needs a complete copy of them to start from - and it can't ship one (they are
Nintendo's files, and a copy built from mods wouldn't be the game's own anyway).
A required Setup step copies them once from a folder extracted from the user's
own game into the app's own local copy - see [Base game files](base-game-files.md#base-game-files-a-required-local-copy)
(`game_files.py`, `find_current()`). Those files join the analysis as a source
flagged `vanilla`: they are the truth for "what the game has", so a mod's
change is simply what differs from them, the base of every build is the user's
own game version, and icons/names work even when no mod ships these files. The
older "borrow a mod's copy, or do nothing at all when none ships one" analysis
still exists in `collect_sources()` for the case `_game_files()` comes back
empty, but that should now only happen before Setup finishes. An archive
nothing changes is not built (a stale built file is removed), so the game's
own file is used as it is.

How it works, since there's no per-mod "diff" to read (the comparison below is
what is used when no game files are given): every mod ships a full
copy of the same game file, so each copy = the game's file + that mod's
changes. The analysis compares all copies; the value most copies agree on is
"vanilla", a value unique to one copy is that mod's deliberate change. Two
noise rules keep it honest: strings whose visible text matches vanilla (only
hidden control codes differ - a different game region/version) are ignored,
and a copy with lots of unrelated differences (built from another game
version) only contributes changes related to what the mod is filed under. The
base file is the copy with the most entries / newest game version. Anything
that can't be inserted safely (a screen the base copy doesn't have, a picture of another
shape or format) is reported and left vanilla. A plain RGBA picture that is only a different
size (same proportions, within 5%) is scaled to the game's size (`ui_setup.rescale_texture`).

Format notes (measured, `ui_archives.py`): `common.sarc`/`menu.sarc` are SARCs
of Yaz0 `.szs` entries; the character-icon entries (`cm_L_CharaIcon_00.szs`,
`mn_L_CharaIcon_00.szs`) are nameless SARCs holding a small layout blob and one
BNTX with every icon as uncompressed RGBA8, so an icon change is an in-place
same-length pixel swap. `message.sarc` is a plain SARC of MSBT files; names
are labelled strings. Writers reproduce the original bytes exactly when
nothing changes (tested on the real files). Caveats: the rebuilt entries are
Yaz0 "stored" (valid, but ~12% larger, no compressor), and none of this has
been run on Switch hardware.
