# UI components

**Status: Phases 0 to 5, the tile shell and the tile grids are built** (the foundation, `Button`, `Modal`, `Section`, `confirm` / `alert`; `Callout`,
`hint`, `Chip`, `Disclosure`; `Menu`, `Tabs` / `Segmented`, `AsyncBox` / `loading`, `List` / `Row`; Settings, Conflicts, Help, Guessed
names, Clear All Mods, the Commit notes, the card chips, the main tabs and the "..." menus use them). The rest is still plan; "What is built" below says where the code differs from the sketches and what Phase 2 left for later.
Each phase turns its part of this page from plan into "how it works".

The frontend stays plain HTML/CSS/JS with no build step and no framework. This page is about building our own small component
layer so that screens describe *what* they show (a title, a list, a button with a callback) and the components decide *how* it is
drawn and wired.

## Why

What the code does today (counts are from grep, so approximate):

- **Modals.** 10 hand-written partials in `html/`, several repeating the same open / close / backdrop-click / Close-button
  wiring (settings, conflicts, guessed names, help). Five more dialogs are built in JS on a `gate-backdrop` div (`voice.js`,
  `refile.js`, `unit-pictures.js`, `tiles-and-review.js`), each with its own Escape handler. "Clear All Mods?" borrows the
  character modal and stacks it with an `above-settings` class because nothing manages stacking.
- **Confirmations.** 4 native `confirm()` and 4 `alert()` calls, unstyled and each a one-off.
- **Cards and sections.** `.modal-card` + header is copy-pasted in `settings-modal.html` and `help-modal.html`. A header button
  ("Reset to default") is a hard-coded `data-reset-group` hook wired by hand.
- **Small elements.** About a dozen near-identical note / hint classes (`cg-note`, `cl-hint`, `cc-hint`, `ve-note`, `uis-note`,
  `pics-note`, ...) and about ten chip / badge classes (`cc-chip`, `ve-chip`, `packed-badge`, `gb-target-badge`, `part-badge`,
  `wiz-pill`, ...).
- **Helpers in odd places (before).** `button()` lived in `flow.js`, `cgEl()` in `data-and-conflicts.js`; both loaded late, so earlier
  files can't use them. Inline SVG strings are pasted into several files.

Already good, and the model for the rest: the **settings registry** (`settings-registry.js`: one definition drawn identically in
Settings and Setup) and the **tooltip** (one shared element). Both are declarative; the plan extends that style.

## Goals and non-goals

Goals

- Screens build UI from a small set of components that take plain data (text, lists, callbacks) and return DOM elements.
- One place owns each behaviour: modal open/close/Escape/stacking/focus, busy buttons, confirmations, loading/empty/error states.
- Looks the same as today. A migration step must not change what the user sees or does (except where this page says so: the
  native `confirm()` / `alert()` dialogs become the app's own).
- Each step is small, testable and committed on its own.

Non-goals

- No React / Vue / build tooling, no virtual DOM, no templating language.
- No automatic re-rendering. Components are built once and updated by calling a method; screens that redraw keep redrawing.
- The large domain screens (`character-card.js`, `voice.js`, course / vehicle / item cards) are not rewritten as components. They
  *use* components. Rewriting the voice editor would cost a lot and prove little.
- No big-bang rewrite. Old and new code live side by side until each screen is migrated.

## Conventions

**Where things live**

- `src/ui/js/ui/*.js` - the component layer, loaded **first** in `SCRIPTS` in `js/bootstrap.js` (before `state-and-helpers.js`),
  because every other file may use it. Within the folder, files load in dependency order: `core.js` -> `icons.js` -> the rest.
- `src/ui/css/components/*.css` - one stylesheet per component family, linked in `index.html` after `base.css` and **before** the
  screen stylesheets, so a screen can still override. Components use the existing CSS variables (light and dark), never raw colours.
- Everything hangs off one global, `ui` (e.g. `ui.modal(...)`, `ui.button(...)`). The scripts share one global scope, so a
  single namespace avoids collisions with the ~hundreds of existing top-level names.

**What a component is**

A component is a function that takes one options object and returns a **handle**: `{ el, ...methods }`.

- `el` is the root DOM element. The caller inserts it (`parent.append(handle.el)`) or, for overlays, calls `handle.open()`.
- Methods are named verbs: `update(opts)`, `setBusy(bool)`, `open()`, `close()`, `destroy()`. Only add what a caller needs.
- Options are plain data plus callbacks named `onSomething`. Text is always set with `textContent`; HTML strings are never
  accepted from data. The only `innerHTML` is the icon registry's own trusted SVG strings.
- A component never reads global state or calls `pywebview.api` itself. The caller passes callbacks; callbacks may be async and
  the component handles the pending state (see Button).
- Class names are `ui-<component>` and `ui-<component>--<variant>` (e.g. `ui-btn--danger`). Existing screen classes are untouched
  until their screen is migrated; then the old duplicates are deleted.
- Accessibility is part of the component, not the caller: dialogs get `role="dialog"`, `aria-modal`, `aria-labelledby`; icon-only
  buttons require a `label`; severity is conveyed by shape and hidden text as well as colour (as the Commit notes already do).

**Spec vs. imperative**

Every component accepts a declarative spec. Where a screen needs something custom (a draggable grid, a canvas), a section body
or modal body can be **any element or a function returning one**, so components never block custom content.

## What is built (Phases 0 to 5, the tile shell and the tile grids)

Code: `js/ui/core.js` (`ui.el`, `ui.append`, `ui.html`, and the older `cgEl`), `js/ui/icons.js` (`ui.icons`, `ui.icon`), `js/ui/button.js`
(`ui.button`, and the older `button(text, cls, fn)`), `js/ui/modal.js`, `js/ui/section.js` (`ui.section`, `ui.columns`,
`ui.settingsGroup`), `js/ui/confirm.js` (`ui.confirm`, `ui.alert`); styles in `css/components/modal.css`; the app's own windows as specs in
`js/app-modals.js` (`settingsModal`, `conflictsModal`, `helpModal`, `guessedNamesModal`, `appExperienceCard`).

Phase 2 added `js/ui/disclosure.js`, `js/ui/callout.js` (`ui.callout` and `ui.hint`) and `js/ui/chip.js`, with `css/components/callout.css`
and `chip.css`:

- **`ui.callout`** draws the Commit page's notes (`pgWarnEl` in `flow.js` just maps a note to its options): tone `warn` / `todo` / `info`
  (icon, stripe, and a hidden word for a screen reader), a title and detail, one action button, and a list of names behind "Show the N mods".
- **`ui.hint(text, { tone, tag })`** is one small line of explanation: tone `dim` (the default) is the quiet grey note, `warn` is the boxed
  warning. It replaced `uis-note` and `uis-warn` (Settings' Game language card, the character / course / vehicle cards' name and icon
  problems, the Menu Look copy results).
- **`ui.chip`** has tones `neutral` / `ok` / `warn` / `accent`, sizes `sm` / `md`, and `bold`, `solid` and `caps`; `chip.set(text, tone)`
  changes a chip already on the page. It replaced `cc-chip` (the status chip at the top of the character, course, vehicle and item cards),
  `ve-chip` (the voice editor's row labels), `gate-chip` (the "isn't finished" list), `cg-tag` (the "recommended" tag in a clash) and the
  `wiz-pill` look (the Recommended / Custom folder label).
- **`ui.disclosure({ summary, class, open }, ...children)`** is the `<details>` + `<summary>` + children as they were laid out, so the page's
  `details` rules still draw the chevron and the indent. It replaced every hand-built `details` on the Commit page, the Copy to Switch
  page's "Something looks wrong?", the Conflicts window and its "How this works".
- Small looks that moved onto the components: the chips take the page's `--thumb-bg` for "neutral" (the folder label used `--divider`
  before), and the hint's sizes are the two it had (12px quiet, 12.5px boxed).
- **Phase 3** added `js/ui/menu.js`, `tabs.js`, `asyncbox.js` and `list.js` (styles in `css/components/menu.css` and `list.css`):
  - **`ui.menu({ label, items, class })`** is the "..." button and its popup (it was `clKebab` / `closeClMenus` in `unit-pictures.js`). `items` is
    a function asked each time it opens; an entry is `{ label, title, onClick, danger, disabled }` or `"-"`. `ui.menu.closeAll()` closes it
    (the voice and picture windows do that before they open). The three menus on the character card use it.
  - **`ui.tabs({ el, items, active, onChange })`** draws the row of main tabs into the existing `#tabs` element (buttons keep the ids
    `tab-<id>`); `setActive(id)` is what `switchView()` calls, and `setCount(id, n)` is the "Characters (49)" count (`flow.js`).
    **`ui.segmented`** is the two-icon switch (the GameBanana window's grid / list), on only when its value changes.
  - **`ui.loading(text)`** is the spinner line (it was `loadingNote`). **`ui.asyncBox({ el, load, render, isEmpty, emptyText, errorText })`**
    fills a box from a promise, keeps what is showing until the new answer arrives, and ignores an answer that comes in late; the UI icon
    worklist in Settings is the first user.
  - **`ui.row({ mark, title, detail, actions, below })`** and **`ui.list({ renderItem, items, empty })`** are the one-line rows of the "Settled /
    left out" section of the Conflicts window (they were `cg-row*`).
  - Not done: the step bar (`renderStepBar` still builds its own buttons: it is drawn from `get_flow_status()` and has its own states), the
    other places that show "Loading..." with a hand-written line, and the voice and Guessed names lists.
- **Phase 4** put the dialogs the page used to build by hand (the move dialog, the "isn't finished" question, the Menu pictures window, the
  Voice lines window, the voice editor and its "Use your own sound" window) on `ui.modal`, so they stack with everything else. What it added to
  `ui.modal`:
  - **`variant: "card"`** is the small centred dialog they all had: the title is in the card (no header bar, no Close button: the dialog has its
    own buttons), the backdrop is the darker one, and the body is laid out as part of the dialog (`display: contents`) so the voice editor's
    scrolling list still gets its height from the dialog. `class` adds the dialog's own class (`voice-editor`, `ve-custom`, `pics-card`, `mv-dialog`),
    `footer: true` makes a footer for buttons added later (`modal.footer`), `destroyOnClose: true` removes a one-use dialog when it closes, and `id`
    may be left out (one is made). `ui.confirm` and `ui.alert` use `destroyOnClose` too.
  - What went away: `gate-backdrop`, `gate-card`, `gate-actions`, `mv-backdrop`, `mv-actions`, the five hand-written Escape handlers and click-outside
    handlers, and the voice editor's "not while a sub-dialog is open" rule (the stack closes only the top window, so the sound dialog closes first).
  - Small visible changes: these dialogs now fade and pop in like the others, a confirm opened from inside them (deleting your own sound) sits above
    them (it was hidden behind at z-index 9000 before the stack), and the move dialog has the card border.
  - The windows whose markup is still in `html/*.html` were handled in Phase 5 (below).
- **Phase 5** tidied up:
  - **Every window is on the stack.** `ui.modal({ adopt: "<id>" })` takes a window whose markup is already on the page (`<id>-backdrop`, `<id>`,
    `<id>-body`, `btn-<id>-close`) and gives it the stack's behaviour without rebuilding it: the Add a mod, GameBanana detail, icon generator,
    GameBanana browse and the character / course / vehicle / item pop-up (`html/*.html`, adopted in `js/app-modals.js`). Their open / close /
    backdrop-click code and the page's own Escape handler (`help-and-icon-generator.js`) are gone; what closing one undoes is its `onClose`
    (`characterModal` clears `openCharacter`, `gbBrowseModal` stops its search), and the GameBanana browser's "Esc clears the search box first" is its
    `onEscape`. Only the Setup overlay (shown before anything else can be) is still its own thing.
  - **`cgEl`, `uisEl` and `wizEl` are gone**: all 480 calls are `ui.el(tag, "class", "text")`, which does the same (a string is the class, strings after
    it are text). `button(text, class, onClick)` stays as the short form for a plain button with a class string; `ui.button` is the full one.
  - **`ui.progress`** (`js/ui/progress.js`, `css/components/progress.css`) draws the commit's bars; `flow.js` only asks `get_commit_progress()` and
    passes the answer to `update()`. **`ui.folderCard`** (`js/ui/folder.js`, `folder.css`) is the folder box; a setting turns what its folder says
    (`is_default`, `is_recommended`, `label`) into its options (`folderCard()` in `settings-registry.js`). The field renderers
    (`fillFolderControl`, `fillPathControl`) stayed in the registry: they are about settings, not generic.
  - **Unused styles removed**: about 70 rules for classes nothing names any more (the old Menu look rows, the Setup guide's step list, the clash
    list of the old Add a mod window, ...), found by checking every class in the stylesheets against the page's HTML and scripts.
- **The tile shell** (`js/ui/tile.js`): the tile of the character, course, vehicle and item screens was already one function, `buildTile()` in
  `tiles-and-review.js`, that read `state.checked` and built the picture, name, badge and count by hand. It is now the page's adapter
  (which units are ticked -> `selected` / `total`, the look of the numbers, the corner colours, the pencil for a note) over **`ui.tile`**, which
  draws a tile from plain options and knows nothing about mods; the six hand-copied blocks that added the red "!" to a tile with a clash are
  `ui.tile.markConflict(tile, title)`. The classes (`char-tile`, `char-badge`, `char-name`, `char-count` ...) and `tiles-and-grids.css` were kept
  as they were: the screens style and find tiles by them.
- **The cup tile and the grids** (`js/ui/tile.js`, `js/ui/tilegrid.js`):
  - **`ui.tile({ variant: "cup", ... })`** is the cup on the Courses screen (a button with the cup's picture, the "3/4" bubble and no name line;
    the page paints the picture with `paintCupTile`).
  - **`ui.tileGrid({ roots, tileSelector, frameHost, plate, resolve, fit, observe })`** is what the four screens that show tiles (Character Select,
    Course Select, Vehicles, Items) did four times: the yellow frame that follows the tile under the mouse, the tile that is `.active`, the name
    plate (it shows what `resolve(hover)` says about the tile under the mouse, else about the viewed one: `{ main, dim }`), and calling `fit()` when
    the screen changes size. `markActive(key)`, `active()`, `refresh()`, `reset()` and `hideFrame()` are what the screens call; the old
    `markActiveTile`, `updateItemNameBar` ... remain as thin names over them. `makeHoverFrame` and the four `*HoverEl` variables are gone.
  - **`ui.fitTiles({ W, H, n, K, cols, extraRows, minT, maxT, preferCols })`** is the "biggest square tile that fits" sum. Character Select calls it
    with 8 fixed columns and Items with every column count (it takes the one nearest 6); the result was compared with the old formulas on 2000
    random sizes and is identical. The layouts stay with each screen: Vehicles (three board arrangements) and Courses (cups on two pages beside
    a strip) keep their own fitting, which is bespoke maths, not a repeated sum.
- **The rest of Phase 2** (done later):
  - **Small notes are `ui.hint`** with a size (`md` is a little larger) and a tone (`dim`, `warn`, `error`). `cg-note`, `cl-hint`, `ve-note`, `mv-note`,
    `pics-hint`, a setting's description (`setting-hint`) and the Setup folder error (`wiz-error`) are all made by it; what is left of those classes
    is the margin where each one sits (`class` is passed on to the hint). A newline in a hint's text is a line break.
  - **The badges on a row are `ui.chip`**: `packed archive only`, `code patch`, `wrong game version`, `Pack - also ...`, the GameBanana "Replaces
    ..." tags and the "reading its description" pill, with the chip's new `size: "xs"`, `outline`, `dashed` and `cursor` options. Their old classes
    stay only as hooks the page looks a badge up by (`row.querySelector(".packed-badge")`) and, for the row layout, one rule that stops them shrinking.
  - **Left as they are, on purpose:** `settings-hint`, `gb-mod-error` and `gb-fetch-error` (static markup in `html/*.html` uses them too), `cc-hint`
    (a bar with a line under it, not a note), `voice-empty` / `conflicts-empty` (empty states of their own lists), and the clickable badges
    (`part-badge` Voice / Picture and `icon-badge`: they are buttons with a hover, and the page finds them by class).

Where Phase 1 differs from the sketches below:

- **A window is built when its script loads and left hidden**, not on first `open()`. Every part has the id the old markup gave it
  (`<id>`, `<id>-backdrop`, `<id>-header`, `<id>-title`, `<id>-bar`, `<id>-body`, `btn-<id>-close`), so code can still look them up at any
  time. The openers keep their names (`openSettingsModal()`, `openConflictsModal()`, `openHelpModal()`, `openGuessedNamesModal()`).
- **The stack.** `open()` puts the window above everything showing: its z-index is the stack's top + 5, or one above the highest of the
  page's own windows (the older popups and the Setup overlay), so no window has a z-index of its own. Escape closes only the top window,
  unless one of the page's own windows is above it (its handler in `help-and-icon-generator.js` deals with that). Tab stays inside the
  window and focus goes back to what opened it. Not done: locking the page's scroll (the page does not scroll under a window today).
- **`ui.confirm` resolves `false` or `{ value }`** (the tick box's state when it has one), so `if (!answer) return;` works. `ui.alert`
  resolves when closed. Both build a small `ui.modal` and take the whole stack's rules. There is no `ui.notify` yet.
- **`ui.button`'s `confirm`** takes the options of `ui.confirm` (or a function returning them: the Maintenance card's button asks
  `clearAllModsConfirm()`, which lives with the code that clears). A failure inside an async `onClick` goes to the log (`diag`) and shows a
  `ui.alert`.
- **`ui.section`** takes `title`, `id`, `actions` (button specs; `disabled` may be a function, asked again by `card.refresh()`) and `body`. The
  `hint` and `collapsible` options in the sketch are left out until something needs them. "Reset to default" is a header action of
  `appExperienceCard`; `updateResetButtons()` just calls its `refresh()`.
- **`ui.html(markup)`** is for markup the source wrote itself (the Discord logo). Everything that came from data goes in as text.
- The Help window's two buttons keep the click handlers they have always had in `help-and-icon-generator.js` (found by id); moving them
  into the spec is a later tidy.
- Gone: `html/help-modal.html`, `settings-modal.html`, `conflicts-modal.html`, `guessed-names-modal.html`; the per-window CSS in
  `settings.css`, `flow.css`, `icon-generator.css`; `#modal-backdrop.above-settings`; every native `confirm()` / `alert()`; the Escape
  branches for these windows in the page's own handler.

## The component catalog

Sketches, not final signatures. They fix the *shape* so the review can happen before code.

### Foundation (`ui/core.js`, `ui/icons.js`)

- `ui.el(tag, props, ...children)` - `props`: `class`, `text`, `attrs`, `on: { click: fn }`, `hidden`. Children can be elements,
  strings, or arrays (falsy skipped). It replaced `cgEl()`, `uisEl()` and `wizEl()` (the same call: `ui.el("div", "class", "text")`).
- `ui.icon(name, { size, stroke, class })` - returns an inline SVG from one registry, `ui.icons` in `js/ui/icons.js`. Every icon in it is a
  [Tabler Icons](https://tabler.io/icons) outline icon (MIT license: the notice is in `THIRD-PARTY-NOTICES.txt` in the release, and
  Tabler is credited in the README and Help). Nothing is drawn by hand any more: to use another icon, copy its drawing from Tabler into the
  registry. Pages written in HTML use `<span data-icon="name" data-size=".." data-stroke=".."></span>`, which `ui.fillIcons()` turns into the
  icon when the page loads (a test fails on an `<svg>` written in the page or in a script).
- `ui.logo(name, { size, class })` - a brand's own logo, for a button or row that leads to that brand (Discord, Buy Me a Coffee): an
  `<img>` of the brand's unmodified file in `ui/img/`, from the registry `ui.logos` (`{src, ratio}`), sized to fit a `size` square like an
  icon. Usable wherever an icon node is (`ui.button({ icon: ui.logo("discord", { size: 16 }) })`). A logo drawn with a dark outline names a `plate` (a light
  colour: white for Buy Me a Coffee) and sits on it on the dark theme (`.ui-logo-plate` in `components/modal.css`) - Buy Me a Coffee's cup would otherwise
  vanish there; the file itself is never recoloured. Logos are trademarks, not Tabler
  icons: each needs its line in `tools/third_party_notices.py` and the README's credits.
- `ui.on(el, event, fn)` / `ui.mount(parent, handle)` helpers only if repeated code shows the need. No more than that.

### Button (`ui/button.js`)

```js
ui.button({
  label: "Reset to default",         // or icon + required `title` for an icon-only button
  variant: "ghost",                  // primary | ghost | danger   (+ size: "small")
  icon: "folder",                    // optional
  onClick: async () => { ... },      // may be async
  confirm: { title, message, confirmLabel, danger: true, extra },   // optional, see ConfirmDialog
  busyLabel: "Clearing...",          // shown while onClick's promise is pending
  disabled: false,
});
// handle: { el, setDisabled(b), setBusy(b), setLabel(s) }
```

- While an async `onClick` is pending the button is disabled and shows `busyLabel`; it re-enables on settle. A thrown error is
  reported through `diag` and shown with `ui.notify` rather than lost.
- `confirm` makes the click open a `ConfirmDialog` first; `onClick` runs only on confirm. This is the "button that requires a
  confirmation, with a custom callback" case.
- Replaces `button()` and the many `createElement("button")` blocks.

### Modal (`ui/modal.js`) + the modal stack

```js
const m = ui.modal({
  id: "settings",                    // optional; used for tests and the stack
  title: "Settings",
  size: "wide",                      // narrow | normal | wide
  sections: [ ...Section specs ],    // or `body`: element | () => element
  actions: [ ...Button specs ],      // footer buttons (right-aligned); omit for a Close-only window
  closeOnBackdrop: true,
  onOpen: () => {}, onClose: () => {},
});
m.open(); m.close(); m.setTitle(s); m.setSections([...]); m.body;   // body element for custom drawing
```

- **One modal stack** (`ui/modal.js` owns it): opening pushes, closing pops. The stack sets z-order (replaces `above-settings`,
  `gate-backdrop` z-index 9000, `mv-backdrop` z-index 45), routes **Escape to the topmost modal only**, returns focus to the
  element that opened it, traps Tab inside, and locks page scroll. The five hand-rolled Escape handlers go away.
- A Close button / backdrop click / Escape all call the same `close()`, which runs `onClose` (and may be vetoed by returning
  `false`, for "unsaved changes").
- Modals are made from a spec, not from `html/*.html` partials (built at load, hidden until `open()`: see "What is built"). The partial
  and its entry in `PARTIALS` are deleted when a modal migrates. Existing element ids that other code or tests rely on are kept.

### Section (`ui/section.js`) - the card with a header

```js
ui.section({
  title: "App experience",
  actions: [                                      // header buttons, any label, any callback
    { label: "Reset to default", variant: "ghost", size: "small", onClick: resetGroup, disabled: () => !differs() },
  ],
  body: element | () => element | ui.list({...}) | ui.settingsGroup("app-experience"),
});
// handle: { el, titleEl, body, buttons, refresh(), setTitle(s) }      (hint and collapsible: later, when something needs them)
```

- This is the replacement for `.modal-card` + `.modal-card-header` + `.settings-body`. Header actions are data, so adding a
  button to any section is one array entry; no more per-button `data-*` hooks.
- `ui.settingsGroup(groupKey)` wraps the existing `renderSettingsGroup()` so registry groups drop straight into a section.
- `ui.columns([...sections])` is the balanced multi-column container from `.settings-columns`.

### List and rows (`ui/list.js`)

```js
ui.list({ items, empty: "Nothing here yet", renderItem: (item) => ui.row({ title, detail, badges, actions }) });
```

- `ui.row({ icon, title, detail, badges, actions, onClick })` - one line of a list, with trailing actions or a `Menu`.
- Handles the empty state through `AsyncBox` (below). Optional `maxHeight` gives the scroll-capped list the Commit page uses.

### ConfirmDialog and notify (`ui/confirm.js`)

```js
const answer = await ui.confirm({ title, message, confirmLabel: "Delete", danger: true, extra: { label, checked, hint } });
// answer: false when cancelled, otherwise { value } (the tick box, when `extra` is used)
await ui.alert({ title, message });          // replaces alert(); one OK button
ui.notify({ message, tone: "error" });        // non-blocking line/toast for failures that don't need a click
```

- Built on `ui.modal`, so it stacks above whatever is open. Replaces all `confirm()` / `alert()` calls and the hand-built
  "Clear All Mods?" dialog (its checkbox is `extra`).
- A busy confirm (the "Clearing..." state, an error line inside the dialog) is supported by letting `onConfirm` be async: the
  dialog stays open and busy until it settles, and shows a returned error instead of closing.

### Callout (`ui/callout.js`)

```js
ui.callout({ tone: "info" | "todo" | "warn" | "error", title, detail, action: { label, onClick }, items, itemsLabel, collapsed })
```

- Built, with these options: `tone` (`warn` / `todo` / `info`), `title`, `detail`, `action`, `items`, `itemsLabel`. Error lines and plain
  hints are not part of it: plain hints are `ui.hint()`, and error lines are still to do (see "What is built").

### Chip / Badge (`ui/chip.js`)

`ui.chip({ text, tone: "neutral" | "good" | "warn" | "accent", icon, onClick, title })` - the ten badge/chip classes become tones of
one component. Toggle chips (`ve-chip toggle-on`) are `ui.chip({ pressed })`.

### Disclosure (`ui/disclosure.js`)

`ui.disclosure({ summary, body, open, onToggle })` - the shared `details`/`summary` look and the indent rule we keep re-fixing
(`details[open] > :not(summary)`). Section `collapsible` and Callout `items` use it.

### Menu (`ui/menu.js`)

Built as `ui.menu({ label, items, class })`: the button and its popup in one (see "What is built"). It closes on outside click / Escape /
scroll and opens upward near the window bottom, as the old code did.

### Tabs / Segmented (`ui/tabs.js`)

`ui.tabs({ items: [{ id, label, badge }], active, onChange })` and a `segmented` variant. For the main view tabs, the GameBanana
grid/list toggle, and the Setup/step bar's click behaviour. The step bar keeps `get_flow_status()` as its only source of truth
(`renderStepBar()` just passes data in).

### AsyncBox (`ui/asyncbox.js`)

`ui.asyncBox({ load: () => Promise, render: (data) => element, empty: (data) => bool, emptyText, errorText })` - the
"Loading... / nothing here / couldn't load" wrapper repeated in the worklist, conflicts, guessed names, voice lists.
Stale-reply safe (a late answer from an older `load` is ignored, as the commit progress poll already does).

### FolderCard (built, Phase 5)

`ui.folderCard({ path, label, recommended, onOpen })`. The field renderers stay in `settings-registry.js` (they are about settings).

### Progress (built, Phase 5)

`ui.progress({ id, title, startText, note, units })` returns `{ el, update(state) }`: one bar per phase, the detail line and the elapsed time. The
commit's polling stays in `flow.js`.

### Tile (built, after Phase 5)

`ui.tile({ key, label, badge, selected, total, count, attention, background, note, onClick })` and `ui.tile.markConflict(tile, title)`.

## Migration order

Each phase is one or more commits on `refactor/ui-modularity-improvements`; each step keeps the app working and is checked in the
scratch harness (real UI against scratch data, `pywebview.api` stubbed) at desktop and phone-ish widths, light and dark.

**Phase 0 - Foundation (done).** `ui/core.js` (`ui.el`), `ui/icons.js`, bootstrap load order, `components` CSS folder, tests for load
order. Move the existing SVGs into the registry; `cgEl` becomes an alias. No visible change.

**Phase 1 - Modal, Section, Button, ConfirmDialog (done).** The core of the request.
1. `ui.modal` + stack, `ui.button` (busy + `confirm`), `ui.section` (header actions), `ui.confirm` / `ui.alert`.
2. Migrate **Clear All Mods** (hand-built dialog -> `ui.confirm`, removes `above-settings`).
3. Migrate the **Settings** modal: partial -> `ui.modal` with `ui.section`s; "Reset to default" becomes a normal section action.
4. Migrate **Conflicts**, **Help**, **Guessed names** (the partials with copy-pasted wiring).
5. Replace the 4 native `confirm()` and 4 `alert()` calls.
Done when: no native `confirm()` / `alert()`, no `*-modal-backdrop` open/close boilerplate for those modals, Escape closes only the
topmost modal, and Settings looks the same.

**Phase 2 - Callout, Chip, Disclosure, hints (done; "What is built" lists what was left as it is).** Commit page notes (`pgWarnEl` -> `ui.callout`), Settings warnings, error lines,
the `*-note` / `*-hint` classes, the badge/chip classes. Delete the superseded CSS as each goes.

**Phase 3 - Menu, Tabs, AsyncBox, List/Row (done, apart from the step bar and the other hand-written "Loading..." lines).** `cl-kebab` menu, view tabs and the GameBanana toggle, loading/empty wrappers, the
worklist and conflicts lists, guessed-names rows.

**Phase 4 - The JS-built dialogs (done; the markup-file windows are not part of it).** `gate-backdrop` / `mv-backdrop` dialogs (`refile.js` move dialog, `tiles-and-review.js` gate,
`unit-pictures.js`, the three in `voice.js`) onto `ui.modal`, so they join the stack. Their bodies stay custom; only the shell,
Escape, focus and z-order change. `voice.js` has a sub-dialog (`ve-sub`) whose Escape rule ("not while a sub-dialog is open") the
stack must express naturally.

**Phase 5 - Move and tidy (done).** `ui.folderCard`, `ui.progress`, the windows adopted onto the stack, `cgEl` gone, unused CSS gone, the docs
(`AGENTS.md`, `docs/architecture.md`) brought up to date. The Tile shell and the Phase 2 leftovers followed.

## Testing

The repo's tests are Python (`python -m unittest discover -s tests`) and read the JS/CSS source, plus browser checks through the
scratch harness. Same approach here:

- **Static tests** (`tests/test_ui_components.py`): `ui/` files are in `SCRIPTS` before everything that uses them; every `ui.*`
  call in the code exists; after each phase, "the old pattern is gone" checks (no `confirm(` / `alert(`, no `above-settings`, no
  `gate-backdrop` outside `modal.js`, no new copies of removed classes). Existing tests that read markup moved into specs (e.g.
  `test_settings_layout.py`) are updated to read the new place, as was done for the settings registry.
- **Behaviour checks in the browser pane** (scratch harness, not committed): open Settings -> Clear All Mods -> Escape closes only
  the top one; Tab stays inside; busy button disables and recovers on error; confirm cancel does not run the callback.
- Real pywebview bridge, real folder picker and the packaged build are not exercised by any of this; say so in each hand-back.

## Risks and how we handle them

- **Shared global scope.** Everything is one scope, so `ui/` loads first and exposes only `ui` (plus the short `button()` helper).
- **Ids and hooks other code or tests rely on.** Specs take `id` / `attrs`; migrate a modal together with its tests and its
  callers, one at a time.
- **Focus / Escape regressions** in dialogs that exist today (voice editor sub-dialogs, GameBanana browse's Esc-clears-search-first
  rule). The stack supports a per-modal `onEscape` that can consume the key; these keep their rule.
- **Visual drift.** Components reuse the current look (spacing, colours, variables). Compare before/after screenshots per migrated
  screen in light and dark.
- **Scope creep.** Phases are independent: stop after any phase and the app is consistent.

## Decisions (settled in review)

1. The native `confirm()` / `alert()` are replaced by the app's own dialogs (`await ui.confirm(...)`).
2. The `html/*.html` partials of migrated modals are deleted; specs in JS replace them.
3. The namespace is `ui`.
4. Phase 1 (modals, sections, buttons, confirmations) came first, as the request describes.
5. The Tile shell was left until after Phase 4, then built (below).
