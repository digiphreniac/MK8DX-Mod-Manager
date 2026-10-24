# Look and feel, and the guided flow

Tooltips, scrollbars and waiting states; the four-step flow (Setup, Choose mods, Commit, Copy to Switch) and what makes the Commit step stale.

## Look and feel

- **Tooltips** are one custom element instead of the browser's own. Every `title="..."` in the app (in the markup or set from
  code, on anything that appears later too) shows it, so nothing had to be rewritten: while the mouse is over an element its
  title is taken off (that is what stops the browser's own tooltip) and put back when the mouse leaves. It is a dark card with
  an arrow, appears after a short pause over each element (moving on to the next one starts the wait again), goes under the element (above it when
  there is no room), stays inside the window, and disappears on click, scroll, key press or window resize. Lines of a title
  become lines of the tooltip and a "Label: text" line gets its label picked out. Tab to an element and it shows too.
- **Scrollbars** are slim and use the app's colours (light and dark). The window's content is capped at 1800px wide
  (`--app-max` in the stylesheet): on a wider window the extra room goes to the sides, and the header, tabs, pages and
  footer stay lined up.
- **Settings are defined once** in `js/settings-registry.js` (`SETTINGS`, in groups = the cards; the groups with a `showInSetup` setting
  are also the Setup steps). Each setting has a key, kind (toggle / select / text / folder), label, description, `showInSetup`, and what
  changing it does (`write`, `after`); `renderSettingsGroup()` draws it identically in both places and `changeSetting()` saves it. How
  each starts comes from `Api.get_default_settings()` (= `DEFAULT_SETTINGS`), which the cards' **Reset to default** uses too. Nothing in
  `setup-wizard.js` or `settings-panels.js` may know about one particular setting.
- **Settings** is a wide window (up to 1040px) with two columns of cards when there is room for two (each at least 420px), one when there
  isn't. The cards (`.settings-columns` in `html/settings-modal.html`) keep their order and the browser balances the columns by height
  (CSS multi-column, `break-inside: avoid`), so the split moves by itself as cards fill in or grow. The columns sit in a box of automatic
  height inside the scrolling body: multi-column inside a scrolling box of fixed height would spill sideways. The "App experience" card (the four on/off options) has a **Reset to default** button at the right of its header (`data-reset-group`), enabled only while an option differs from its default.
  "Conflicts and omitted files" is a **Review** button with a
  one-line summary beside it; the list itself is in `html/conflicts-modal.html`, a modal opened from Settings (`openConflictsModal()`; Escape closes it first).
  The modal is kept short: a bar under its header always shows the count ("3 need settling - 104 files left out", or "All settled ..."),
  the cards that need a decision come first, and everything already done is one line each inside a "Settled / left out" section that is
  folded away while anything above still needs settling (the user's own open/close is remembered while the window stays open). File lists
  (`cgFileList()`) show the file's name first and its folder dim, in a box of at most 240px. With nothing to show, the list says so (a
  check mark and one line) and "How this works" stays folded under it. The wide `.cg-*` card rules are shared with the Commit page and the
  mod popup; the one-line rows (`.cg-row`) are only built here.
- **Drop-down lists and fold-away sections** have one look each, in `css/layout.css`: a `select` is drawn like a button or a text box (panel
  colour, thin border, its arrow made from two CSS triangles so it follows the theme), and a `details` has no box: its `summary` is dim text with a
  small chevron that turns when it opens, instead of the browser's own triangle, and what is inside is indented under it with a line down
  its left (a single wrapper child gives one unbroken line; a child with vertical margins would break it). A list with its own class only changes size (keep room on the
  right for the arrow, and write `background-color`, not `background:`, which would wipe the arrow). The opened list of a drop-down is drawn by the system.
- **Waiting is shown, not hidden.** A character tile with ticked mods pulses until the app has read what those mods change
  (the icon and name) - on opening the app, and again after a tick. In a character's card, ticking or unticking a mod turns
  the Name and Icons sections into a loading state at once (the status line says "reading the appearance...", the chip says
  "Reading...") until the new answer is drawn; a course's Menu look card does the same ("Reading the mod's menu files...").

## The guided flow: step bar, Next button, Commit page

The app walks you through four steps, shown in the header itself - one row holding the title, the four steps and
two icon buttons (Refresh, the circular arrow, which turns while it reloads; Settings, the gear) - and a
**Next** button in the bottom-right corner - flush with the window's right edge, a rectangle with barely rounded corners
and a slanted left side (bottom-left sticks out further than top-left), like the game's own (`get_flow_status()` in
`mod_manager.py` is the single source of truth; the frontend just renders it):

1. **Setup** - first run: a required wizard. Every step but one is a group of *settings*, drawn by the same code as the Settings window
   (`settings-registry.js`: a setting's name, description, control and what it does are defined once, and a setting is in Setup only
   because its `showInSetup` flag is set): the data folder, game version (`set_game_version()`; a known version also sets
   `game_build_id`, which the code-patch "wrong version" checks use), the options (NSFW, Advanced mode) and Switch language
   (`ui_setup_locale`). The odd one out is **your game's files** (a required copy, not a setting, no skip - see
   [Base game files](base-game-files.md#base-game-files-a-required-local-copy)). `setup.done`
   (`get_flow_status()`) is true only once both the `setup_done` flag is set AND the base-files
   copy exists (`game_files.status().done`) - a base-files copy that goes missing sends the step
   bar back to "Setup" even if the wizard was completed before. Reopen from the step bar. The
   `pywebviewready` startup handler checks this too, not just whether a master folder is configured -
   a folder being picked (which happens immediately, before the wizard even opens) isn't the same as
   setup being finished, so closing/reloading the app mid-wizard used to silently drop straight into
   the main app on the next launch instead of resuming it; it now reopens the wizard (with no Close
   button, same as a genuine first run) whenever `setup.done` is false.
2. **Choose mods** - the Character / Course / Vehicles / More / Full List tabs,
   with per-tab tick counts.
3. **Commit** (was "Merge & Stage"). The page asks `preview_commit()` (a dry
   run: claims, clashes, warnings) as soon as it opens, shows every clash as a
   settle-it-here card, and blocks the Commit button until none are left. When
   there's menu icons/text to combine, that's just a lightweight warning here
   (linking to Settings) - the actual `merge()` call itself builds it
   automatically, right before its own file-copy pass. The result comes
   back structured (`counts`, `warnings`) with the old text log (now including
   what got built) kept under "Details (full log)". The sidebar Output log was
   removed.
4. **Copy to Switch** - checklist + "It works!" (`mark_switch_done()`).

**Phase 3** (2026-09-22) removed what used to be its own fifth step, "UI icons & text" - a whole
page just for picking a language and pressing Build, when the analysis and the build were already
fast and automatic underneath it. Checking guessed names and picking between conflicting icon
versions moved onto the Commit page itself as warning cards; language, the (rare) pick-which-mod-
wins conflict, and Open the folder/Undo/manual rebuild/"do this by hand" all moved to Settings
instead - deliberately not a Commit-page card of its own, since language is a set-once preference,
not something to review at every commit. See [Menu icons & text](menu-icons-and-text.md#menu-icons--text-combined-character-icons-and-coursecharacter-names) for the full picture.

"Done"/"stale": a commit records `last_commit` (a signature of the ticked
mods + every left-out file) and, when anything needed combining, `last_ui_build`
(see [Menu icons & text](menu-icons-and-text.md#menu-icons--text-combined-character-icons-and-coursecharacter-names) for what's in that signature) - `commit.stale`
is true if *either* no longer matches, so a language change alone (no mods
re-ticked) still calls for a re-commit. The Switch confirmation ("It works!", which turns
the Copy to Switch page into All done) is tied to both signatures together, and is also cleared whenever the user leaves the Commit page
(`goStep()` calls `mark_switch_done(false)`), so Back to Commit and Next again shows the steps with the "Open staging folder" button, not All done. Change any input and the step turns amber again.

The Commit page and the Commit button send `selectedKeys()` (every key marked selected in `state.checked`), not "the mods in the page's own
list (`state.categories`) that are selected": that list is only reloaded by `loadMods()`, so a mod downloaded and selected in the same session
wasn't in it and the page said "No mods are selected yet" while the step bar (which asks the backend) counted it. The backend reports a
selected mod that is gone from the disk.

A mod changed **in place** (the author's new version over the old one, a regenerated course icon) leaves the list of ticked mods as it
was, so `last_commit` also records `content`: a fingerprint of the name, size and modification time of every file of the ticked mods
(`_commit_content_stamp()`, remembered for up to a minute - a full pass over 30,000 files takes about a second - see `library_cache.py`; the Refresh button forces a fresh look). `commit.stale` and the Commit page's "already
committed" are false once it differs. It is a separate field, not part of `sig`, so a commit made before it existed (no `content`)
is never called stale because of it.
`flowNextTarget()` in the frontend decides what Next says from the page you're on.

The **All done** page (Copy to Switch, once the user has said it worked) ends with an "Enjoying your mods?" card (`supportCard()` in
`flow.js`): like the page on GameBanana (the more likes it has, the more people see it), star the repository on GitHub, buy a coffee, join the Discord
(`DISCORD_URL`; Help has the same link as a button). Each
row opens its address in the browser (`open_external_url`). The addresses are constants in `state-and-helpers.js` (`GAMEBANANA_PAGE_URL`,
`GITHUB_URL`, `SUPPORT_URL`); an empty `GAMEBANANA_PAGE_URL` hides the GameBanana row. The footer's "Donate" link (its tooltip says it opens Buy Me a Coffee) still goes to
the donation page.
