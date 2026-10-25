"""The component layer in src/ui/js/ui (docs/ui-components.md): it loads before everything that uses it, everything the page calls on `ui`
exists, and the old hand-made patterns it replaced (native confirm() / alert(), the "above Settings" z-index, a window's own backdrop
wiring) are gone.

These read the page's files as text; the behaviour (stacking, Escape, focus, a busy button, a confirm that waits for a job) was exercised in
the browser against the real page, which no test here does.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "src" / "ui"
JS = UI / "js"
COMPONENTS = ("core", "icons", "button", "disclosure", "modal", "section", "confirm", "callout", "chip", "menu", "tabs", "asyncbox", "list", "progress", "folder", "tile", "tilegrid")


def read(*parts):
    return UI.joinpath(*parts).read_text(encoding="utf-8")


def code(text):
    """Source without its // comments (a comment may name confirm() or alert() in words)."""
    return "\n".join(re.sub(r"(?<!:)//.*", "", line) for line in text.splitlines())


def all_scripts():
    return sorted(JS.rglob("*.js"))


class LoadOrder(unittest.TestCase):
    def test_the_components_load_first_in_dependency_order_then_the_app_windows_then_the_rest(self):
        bootstrap = read("js", "bootstrap.js")
        scripts = bootstrap[bootstrap.index("const SCRIPTS = ["):]
        order = [f"js/ui/{name}.js" for name in COMPONENTS] + ["js/app-modals.js", "js/api-coalesce.js", "js/state-and-helpers.js"]
        positions = [scripts.index(f'"{path}"') for path in order]
        self.assertEqual(positions, sorted(positions))

    def test_every_script_that_is_loaded_exists_and_every_ui_script_is_loaded(self):
        bootstrap = read("js", "bootstrap.js")
        loaded = re.findall(r'"(js/[^"]+\.js)"', bootstrap)
        for path in loaded:
            self.assertTrue((UI / path).is_file(), path)
        for path in (JS / "ui").glob("*.js"):
            self.assertIn(f"js/ui/{path.name}", loaded, path.name)

    def test_the_stylesheet_is_linked_after_the_base_and_before_the_screens(self):
        html = read("index.html")
        self.assertLess(html.index("css/base.css"), html.index("css/components/modal.css"))
        self.assertLess(html.index("css/components/modal.css"), html.index("css/layout.css"))
        for path in (UI / "css" / "components").glob("*.css"):
            self.assertIn(f"css/components/{path.name}", html, path.name)

    def test_the_four_windows_are_specs_not_markup_files(self):
        bootstrap = read("js", "bootstrap.js")
        for name in ("help", "settings", "conflicts", "guessed-names"):
            self.assertNotIn(f"{name}-modal.html", bootstrap)
            self.assertFalse((UI / "html" / f"{name}-modal.html").exists(), name)


class WhatThePageCalls(unittest.TestCase):
    def test_everything_called_on_ui_is_defined_by_a_component(self):
        defined = set()
        for name in COMPONENTS:
            defined.update(re.findall(r"(?<![\w.])ui\.(\w+) = ", read("js", "ui", f"{name}.js")))
        self.assertTrue({"el", "icon", "button", "modal", "section", "confirm", "alert", "disclosure", "callout", "hint", "chip", "menu", "tabs", "segmented", "loading", "asyncBox", "row", "list", "progress", "folderCard", "tile", "tileGrid", "fitTiles"} <= defined)
        for path in all_scripts():
            for used in re.findall(r"(?<![\w.])ui\.(\w+)", code(path.read_text(encoding="utf-8"))):
                self.assertIn(used, defined, f"{path.name} uses ui.{used}")

    def test_every_icon_asked_for_is_in_the_registry(self):
        registry = set(re.findall(r"^  \"?([\w-]+)\"?: '<", read("js", "ui", "icons.js"), re.M))
        self.assertGreaterEqual(len(registry), 25)
        asked = set()
        for path in all_scripts():
            asked.update(re.findall(r'ui\.icon\("([\w-]+)"', path.read_text(encoding="utf-8")))
        for path in [UI / "index.html"] + list((UI / "html").glob("*.html")):
            asked.update(re.findall(r'data-icon="([\w-]+)"', path.read_text(encoding="utf-8")))
        callout = read("js", "ui", "callout.js")
        asked.update(re.findall(r': "([\w-]+)"', callout[callout.index("ui.icon({"):callout.index("}[tone]", callout.index("ui.icon({"))]))
        asked.update(re.findall(r'"([\w-]+)"', read("js", "views.js")[read("js", "views.js").index("const MORE_ICON_NAMES"):][:260]))
        flow = read("js", "flow.js")
        asked.update(re.findall(r'icon: "([\w-]+)"', flow))
        asked.update(["speaker", "speaker-muted", "play", "stop", "trash", "pencil", "photo", "grid", "list", "more"])     # (named inside helpers)
        self.assertTrue(asked <= registry, asked - registry)

    def test_the_icons_are_one_open_licensed_set_and_nothing_is_drawn_by_hand(self):
        icons = read("js", "ui", "icons.js")
        self.assertIn("Tabler Icons", icons)
        self.assertIn("MIT license", icons)
        self.assertIn("Paweł Kuna", icons)
        for path in all_scripts():
            text = path.read_text(encoding="utf-8")
            if path.name == "icons.js":
                continue
            self.assertNotIn("createElementNS", text, f"{path.name} draws an SVG by hand: add the icon to ui/icons.js")
            self.assertNotIn("<svg", code(text), f"{path.name} has an SVG written in it: use ui.icon")
        for path in [UI / "index.html"] + list((UI / "html").glob("*.html")):
            self.assertNotIn("<svg", path.read_text(encoding="utf-8"), f"{path.name}: use <span data-icon=...>")

    def test_markup_strings_are_only_made_in_the_two_places_that_own_them(self):
        for path in (JS / "ui").glob("*.js"):
            uses = code(path.read_text(encoding="utf-8")).count("innerHTML")
            self.assertEqual(uses, 1 if path.name in ("core.js", "icons.js") else 0, path.name)       # (ui.html and ui.icon, from source literals)

    def test_each_window_part_has_one_id_and_no_two_windows_share_one(self):
        ids = re.findall(r'\bid: "([\w-]+)"', read("js", "app-modals.js"))
        self.assertEqual(len(ids), len(set(ids)))


class OldPatternsAreGone(unittest.TestCase):
    def test_no_native_confirm_or_alert(self):
        for path in all_scripts():
            text = code(path.read_text(encoding="utf-8"))
            for call in re.findall(r"(?<![\w.])(confirm|alert)\(", text):
                self.fail(f"{path.name} calls the browser's {call}(): use ui.confirm / ui.alert")

    def test_no_above_settings_stacking_trick(self):
        for path in list(JS.rglob("*.js")) + list((UI / "css").rglob("*.css")):
            self.assertNotIn("above-settings", path.read_text(encoding="utf-8"), path.name)

    def test_the_four_windows_are_opened_and_closed_only_through_their_handles(self):
        for path in all_scripts():
            text = path.read_text(encoding="utf-8")
            for name in ("settings", "conflicts", "help", "guessed-names"):
                self.assertNotRegex(text, rf'getElementById\("{name}-modal-backdrop"\)', f"{path.name} reaches into the {name} window's backdrop")
        for name in ("settings", "conflicts", "help", "guessed-names"):
            for css in (UI / "css").glob("*.css"):
                self.assertNotRegex(css.read_text(encoding="utf-8"), rf"#{name}-modal(-backdrop|-header)? \{{", f"{css.name}: #{name}-modal")


class PhaseTwoOldPatternsAreGone(unittest.TestCase):
    def test_the_note_hint_chip_and_disclosure_classes_the_components_replaced_are_gone(self):
        gone = ("uis-warn", "uis-note", "cc-chip", "ve-chip", "gate-chip", "pg-warn", "pg-sr", "pg-list", "pg-icon")
        for path in list(JS.rglob("*.js")) + list((UI / "css").rglob("*.css")):
            text = path.read_text(encoding="utf-8")
            for name in gone:
                self.assertNotRegex(text, rf"(?<![\w-]){name}(?![\w-])", f"{path.name} still has {name}")

    def test_the_notes_chips_and_folds_are_made_by_the_components(self):
        for name in ("flow.js", "data-and-conflicts.js", "app-modals.js"):
            self.assertNotIn('createElement("details")', read("js", name), name)
        voice = read("js", "voice.js")
        self.assertNotIn('"ve-chip', voice)
        self.assertEqual(voice.count("ui.chip({"), 5)
        for name in ("character-card.js", "course-card.js", "item-card.js", "vehicle-card.js"):
            text = read("js", name)
            self.assertIn('const chip = ui.chip({ size: "md" });', text, name)
            self.assertIn('chip.set(chipText, chipCls || "neutral");', text, name)

    def test_the_chip_has_a_tone_for_each_look_it_replaced(self):
        css = read("css", "components", "chip.css")
        for rule in (".ui-chip {", ".ui-chip--md", ".ui-chip--ok", ".ui-chip--warn", ".ui-chip--accent", ".ui-chip--bold", ".ui-chip--solid", ".ui-chip--caps"):
            self.assertIn(rule, css, rule)
        chip = read("js", "ui", "chip.js")
        self.assertIn("set(text, nextTone)", chip)

    def test_the_hint_has_a_quiet_tone_and_a_warning_tone(self):
        css = read("css", "components", "callout.css")
        self.assertIn(".ui-hint {", css)
        self.assertIn(".ui-hint--warn {", css)
        self.assertRegex(css, r"\.ui-hint--warn \{[^}]*background: var\(--warn-soft\)")

    def test_the_components_and_their_styles_are_loaded(self):
        html = read("index.html")
        for sheet in ("modal", "callout", "chip", "menu", "list"):
            self.assertIn(f"css/components/{sheet}.css", html)


class PhaseThreeOldPatternsAreGone(unittest.TestCase):
    def test_the_menu_the_waiting_line_and_the_rows_come_from_the_components(self):
        for path in all_scripts():
            text = path.read_text(encoding="utf-8")
            for gone in ("clKebab", "closeClMenus", "loadingNote", "cl-menu", "cl-kebab"):
                self.assertNotIn(gone, text, f"{path.name} still has {gone}")
            self.assertNotRegex(text, r"(?<![\w-])cg-row(-[\w-]+)?(?![\w-])", path.name)       # (cg-rows, the list's own class, is fine)
        for path in (UI / "css").rglob("*.css"):
            text = path.read_text(encoding="utf-8")
            for gone in ("cl-menu", "cl-kebab"):
                self.assertNotIn(gone, text, f"{path.name} still has {gone}")
            self.assertNotRegex(text, r"\.cg-row(-[\w-]+)?(?![\w-])", path.name)
        for path in all_scripts():
            if path.name != "menu.js":
                self.assertNotIn(".ui-menu", code(path.read_text(encoding="utf-8")).replace(".ui-menu-btn", ""), path.name)

    def test_the_menu_is_one_button_that_asks_for_its_entries_each_time_it_opens(self):
        menu = read("js", "ui", "menu.js")
        self.assertIn("for (const item of spec.items())", menu)
        for entry in ("onClick", "danger", "disabled"):
            self.assertIn(f"item.{entry}", menu)
        for rule in (".ui-menu-btn {", ".ui-menu {", ".ui-menu-item {", ".ui-menu-sep {"):
            self.assertIn(rule, read("css", "components", "menu.css"))
        card = read("js", "character-card.js")
        self.assertEqual(card.count("ui.menu({"), 3)
        self.assertNotRegex(card, r"\brun: ")             # (an entry's callback is onClick, like every other component's)

    def test_the_main_tabs_are_made_by_ui_tabs_and_the_counts_by_setCount(self):
        self.assertNotIn("<button", read("index.html")[read("index.html").index('id="tabs"'):][:60])
        views = read("js", "views.js")
        self.assertIn("const mainTabs = ui.tabs({", views)
        self.assertNotIn('getElementById("tab-', views)
        self.assertIn("mainTabs.setActive(mode);", views)
        self.assertIn("mainTabs.setCount(k, n)", read("js", "flow.js"))
        tabs = read("js", "ui", "tabs.js")
        self.assertIn('"tab-" + item.id', tabs)            # (the button ids other code and the stylesheet knew)

    def test_the_grid_and_list_switch_is_a_segmented_control(self):
        browse = read("js", "gb-browse.js")
        self.assertIn("ui.segmented({", browse)
        self.assertNotIn("viewButtons", browse)
        self.assertIn('id="gb-browse-modal-view" class="gb-view-toggle"></div>', read("html", "gb-browse-modal.html"))       # (the buttons are made, not written)

    def test_the_lists_that_load_are_async_boxes_and_the_settled_rows_are_rows(self):
        panels = read("js", "settings-panels.js")
        self.assertIn("ui.asyncBox({", panels)
        self.assertIn("pywebview.api.ui_icon_worklist()", panels)
        self.assertNotIn("innerHTML", panels[panels.index("const uiIconWorklist"):panels.index("function renderUiIconWorklist")])
        asyncbox = read("js", "ui", "asyncbox.js")
        self.assertIn("if (mine !== latest) return;", asyncbox)            # (an old answer arriving late is ignored)
        conflicts = read("js", "data-and-conflicts.js")
        self.assertIn("ui.list({", conflicts)
        self.assertIn("ui.row(spec)", conflicts)


class PhaseFourDialogsJoinTheStack(unittest.TestCase):
    DIALOGS = (("refile.js", 1), ("tiles-and-review.js", 1), ("unit-pictures.js", 1), ("voice.js", 3))

    def test_the_hand_made_backdrops_and_their_classes_are_gone(self):
        for path in list(JS.rglob("*.js")) + list((UI / "css").rglob("*.css")):
            text = path.read_text(encoding="utf-8")
            for name in ("gate-backdrop", "gate-card", "gate-actions", "mv-backdrop", "mv-actions", "ve-sub"):
                self.assertNotRegex(text, rf"(?<![\w-]){name}(?![\w-])", f"{path.name} still has {name}")

    def test_each_of_them_is_a_card_modal_and_has_no_escape_or_backdrop_wiring_of_its_own(self):
        for name, count in self.DIALOGS:
            text = code(read("js", name))
            self.assertEqual(text.count('variant: "card"'), count, name)
            self.assertNotIn('"Escape"', text, name)                         # (the stack closes the top window, so a sub-dialog needs no rule of its own)
            self.assertNotIn("keydown", text, name)
            self.assertNotIn("document.body.appendChild(back", text, name)
            self.assertNotRegex(text, r"\bback\.(appendChild|remove|isConnected|addEventListener|querySelector)", name)

    def test_the_voice_editor_and_its_sub_dialog_close_one_at_a_time_through_the_stack(self):
        voice = read("js", "voice.js")
        self.assertIn('class: "voice-editor"', voice)
        self.assertIn('class: "ve-custom"', voice)
        self.assertIn("function cleanup()", voice)                           # (what closing the sound dialog undoes, however it closes)
        self.assertIn("onClose: () => cleanup()", voice)
        self.assertIn("modal.dialog.classList.add(\"drop-target\")", voice)       # (the highlight goes on the dialog, not on its body)
        self.assertNotIn("backdrop", code(voice))

    def test_the_question_that_waits_for_an_answer_resolves_once_however_it_closes(self):
        gate = read("js", "tiles-and-review.js")
        gate = gate[gate.index("function showUnfinishedGate("):]
        gate = gate[:gate.index("\n}\n")]
        self.assertIn("onClose: () => done(false)", gate)
        self.assertIn("if (finished) return;", gate)
        self.assertLess(gate.index("finished = true;"), gate.index("modal.close();"))       # (closing it from "done" does not answer twice)

    def test_the_card_variant_is_in_the_modal_and_its_styles(self):
        modal = read("js", "ui", "modal.js")
        for needed in ('spec.variant === "card"', "spec.destroyOnClose", "spec.footer", '"ui-modal-body ui-modal-body--part"', 'spec.id || "ui-modal-"'):
            self.assertIn(needed, modal, needed)
        css = read("css", "components", "modal.css")
        for rule in (".ui-modal-backdrop--card {", ".ui-modal--card {", ".ui-modal-body--part { display: contents; }"):
            self.assertIn(rule, css, rule)
        self.assertIn("destroyOnClose: true", read("js", "ui", "confirm.js"))


class PhaseFiveTidy(unittest.TestCase):
    ADOPTED = {"add-mod-modal": "addModModal", "gb-detail-modal": "gbDetailModal", "icon-gen-modal": "iconGenModal",
               "gb-browse-modal": "gbBrowseModal", "modal": "characterModal"}

    def test_the_older_element_helpers_are_ui_el(self):
        for path in all_scripts():
            text = path.read_text(encoding="utf-8")
            for gone in ("cgEl", "uisEl", "wizEl"):
                self.assertNotRegex(text, rf"(?<![\w-]){gone}(?![\w-])", f"{path.name} still has {gone}")

    def test_every_window_is_on_the_stack_and_the_page_has_no_escape_handler_of_its_own(self):
        modals = read("js", "app-modals.js")
        for markup_id, handle in self.ADOPTED.items():
            self.assertRegex(modals, rf'const {handle} = ui\.modal\(\{{\s*adopt: "{markup_id}"')
        for path in all_scripts():
            text = code(path.read_text(encoding="utf-8"))
            if path.name in ("modal.js", "tooltips.js", "menu.js"):
                continue
            self.assertNotIn('"Escape"', text, path.name)                 # (Escape is the stack's job; the menu and the tooltip close themselves)
            for markup_id in self.ADOPTED:
                self.assertNotRegex(text, rf'getElementById\("{markup_id}-backdrop"\)', f"{path.name} reaches into {markup_id}'s backdrop")

    def test_what_closing_the_adopted_windows_undoes_is_in_one_place(self):
        modals = read("js", "app-modals.js")
        self.assertIn("onClose: () => { openCharacter = null; markActiveTile(); }", modals)
        self.assertIn("onClose: () => { if (gbBrowse) gbBrowse.stop(); gbBrowse = null; }", modals)
        self.assertIn("onEscape: () => !!(gbBrowseClearSearch && gbBrowseClearSearch())", modals)
        modal = read("js", "ui", "modal.js")
        self.assertIn("function adopt(spec)", modal)
        self.assertIn("btn-${id}-close", modal)

    def test_the_progress_bars_and_the_folder_card_are_components(self):
        progress = read("js", "ui", "progress.js")
        self.assertIn("ui.progress.formatElapsed", progress)
        self.assertIn("units", progress)
        flow = read("js", "flow.js")
        self.assertNotIn("function formatElapsed", flow)
        self.assertNotRegex(flow, r"[\"']cp-")
        folder = read("js", "ui", "folder.js")
        self.assertIn("ui-folder-open", folder)
        registry = read("js", "settings-registry.js")
        self.assertNotIn("wiz-folder", registry)
        for sheet in ("progress", "folder"):
            self.assertIn(f"css/components/{sheet}.css", read("index.html"))

    def test_the_unused_styles_are_gone(self):
        css = "\n".join(p.read_text(encoding="utf-8") for p in (UI / "css").rglob("*.css"))
        for name in ("conflict-group", "conflict-option-row", "cl-step-btn", "cl-step-bar", "cl-edit-btn", "ml-chip", "ml-custom", "ml-verdict", "leftout-badge",
                     "uis-icons", "uis-mod-name", "uis-step-head", "help-link-list", "wiz-hint", "modal-side-col", "wiz-folder", "wiz-pill"):
            self.assertNotRegex(css, rf"\.{name}(?![\w-])", name)


class PhaseTwoLeftovers(unittest.TestCase):
    HINTS = ("cg-note", "cl-hint", "ve-note", "mv-note", "pics-hint", "setting-hint", "wiz-error")

    def test_the_small_notes_and_the_error_line_are_ui_hint_and_nothing_builds_them_by_hand(self):
        for path in all_scripts():
            text = path.read_text(encoding="utf-8")
            for name in self.HINTS:
                # (as the class of an element made by ui.el: the class is only passed on to ui.hint now, as `class: "..."`)
                self.assertNotRegex(text, rf'ui\.el\("(div|span|p)", "{name}"', f"{path.name} builds a {name} by hand")
        self.assertGreaterEqual(sum(path.read_text(encoding="utf-8").count("ui.hint(") for path in all_scripts()), 40)

    def test_what_is_left_of_those_classes_is_only_where_they_sit(self):
        css = read("css", "conflicts.css") + read("css", "character-card.css")
        for rule in (".cg-note { margin: 4px 0 6px; }", ".pics-hint { margin: 14px 0 0 0; }", ".ve-note { margin: 0 0 8px 0; }", ".cl-hint { margin: -4px 0 0 2px; }"):
            self.assertIn(rule, css, rule)
        self.assertNotIn(".setting-hint", read("css", "setting-controls.css"))
        self.assertNotIn(".wiz-error", read("css", "setup-overlay.css"))
        hint = read("css", "components", "callout.css")
        for rule in (".ui-hint--md {", ".ui-hint--error {"):
            self.assertIn(rule, hint, rule)

    def test_the_badges_on_a_row_are_chips(self):
        for name, needed in (("character-card.js", ('class: "packed-badge"', 'class: "patch-badge"')), ("menu-look.js", ('class: "packed-badge"',)),
                             ("views.js", ('class: "linked-badge"',)), ("gb-browse.js", ('class: "gb-pending-pill"', "outline: true"))):
            text = read("js", name)
            for item in needed:
                self.assertIn(item, text, f"{name}: {item}")
            self.assertNotRegex(text, r'className = "(packed|patch|linked)-badge"', name)
            self.assertNotIn('"gb-target-badge', text, name)
        css = "\n".join(p.read_text(encoding="utf-8") for p in (UI / "css").glob("*.css"))
        self.assertNotIn("gb-target-badge", css)
        for name in ("packed-badge", "patch-badge", "linked-badge"):
            self.assertEqual(css.count(name), 1, name)       # (only the one rule that stops the badge shrinking in a row: no look of its own)
            self.assertRegex(css, rf"\.mod-row \.{name}[^{{]*\{{ flex: 0 0 auto; \}}", name)
        chip = read("css", "components", "chip.css")
        for rule in (".ui-chip--xs {", ".ui-chip--outline {", ".ui-chip--dashed {", ".ui-chip--help {", ".ui-chip--pointer {"):
            self.assertIn(rule, chip, rule)
        self.assertLess(chip.index(".ui-chip--caps {"), chip.index(".ui-chip--xs {"))       # (the badge size wins over the capitals' size)


class TheTileShell(unittest.TestCase):
    def test_every_tile_is_a_ui_tile_and_buildtile_only_turns_what_it_knows_into_options(self):
        review = read("js", "tiles-and-review.js")
        build = review[review.index("function buildTile("):]
        build = build[:build.index("\n}\n")]
        self.assertIn("ui.tile({", build)
        self.assertIn("state.checked[k]", build)                      # (the page's part: which mods are ticked)
        for hand_made in ("document.createElement", "tile-count-bubble", "char-count", "char-badge"):
            self.assertNotIn(hand_made, build, hand_made)
        for name in all_scripts():
            if name.name == "tile.js":
                continue
            text = name.read_text(encoding="utf-8")
            self.assertNotIn("char-conflict-badge", text, name.name)         # (the red "!" is ui.tile.markConflict)
            self.assertNotIn('classList.add("has-conflict")', text, name.name)

    def test_the_conflict_mark_is_made_in_one_place_by_the_six_screens(self):
        uses = {name: read("js", name).count("ui.tile.markConflict(") for name in ("item-screen.js", "tiles-and-review.js", "views.js", "vehicle-screen.js")}
        self.assertEqual(uses, {"item-screen.js": 1, "tiles-and-review.js": 2, "views.js": 2, "vehicle-screen.js": 1})
        tile = read("js", "ui", "tile.js")
        self.assertIn("ui.tile.markConflict = function (tile, title)", tile)

    def test_the_tile_draws_the_three_ways_of_counting_and_the_no_mods_states(self):
        tile = read("js", "ui", "tile.js")
        for needed in ('spec.count === "quiet"', 'spec.count === "bubble"', "needs attention", "No mods yet", "char-attention-dot", "tile-pending-dot",
                       "el.dataset.countNote", "el.dataset.char = spec.key"):
            self.assertIn(needed, tile, needed)
        self.assertLess(tile.index('"char-badge"'), tile.index('"char-name"'))          # (the order the children have always had)


class TheTileGrids(unittest.TestCase):
    SCREENS = (("character-select-layout.js", "characterGrid", "char-name-plate"), ("item-screen.js", "itemGrid", "item-name-plate"),
               ("vehicle-screen.js", "vehicleGrid", "vehicle-name-plate"), ("views.js", "courseGrid", "course-name-plate"))

    def test_each_screen_has_one_tile_grid_and_keeps_only_its_layout_and_what_its_plate_says(self):
        for name, grid, plate in self.SCREENS:
            text = read("js", name)
            self.assertRegex(text, rf"const {grid} = ui\.tileGrid\(\{{", name)
            self.assertIn(f'plate: document.getElementById("{plate}")', text, name)
            self.assertIn("frameHost:", text, name)
            self.assertIn("fit:", text, name)
            self.assertIn(f"{grid}.markActive(", text, name)
            for gone in ("HoverEl", "makeHoverFrame", 'addEventListener("mouseover"', 'addEventListener("mouseleave"', "new ResizeObserver"):
                self.assertNotIn(gone, code(text).replace("ui.tileGrid", ""), f"{name} still has {gone}")

    def test_the_plates_say_what_they_said_and_only_return_it(self):
        for name, fn in (("character-select-layout.js", "resolveCharacterPlate"), ("item-screen.js", "resolveItemPlate"),
                         ("vehicle-screen.js", "resolveVehiclePlate"), ("views.js", "resolveCoursePlate")):
            text = read("js", name)
            body = text[text.index(f"function {fn}("):]
            body = body[:body.index("\n}\n")]
            self.assertIn("return", body, fn)
            self.assertNotIn("plate.", body, fn)               # (drawing the plate is the grid's job)
            self.assertNotIn("replaceChildren", body, fn)

    def test_the_grid_draws_the_plate_and_the_frame_and_marks_the_active_tile(self):
        grid = read("js", "ui", "tilegrid.js")
        for needed in ('"np-base"', "plate.classList.remove(\"show\")", 'frame = ui.el("div", "hover-frame")', "t.classList.toggle(\"active\", key != null && t.dataset[keyAttr] === key)",
                       "new ResizeObserver(() => spec.fit())", "reset() { hideFrame(); hoverEl = null; }"):
            self.assertIn(needed, grid, needed)

    def test_characters_and_items_are_sized_by_the_shared_fit(self):
        self.assertIn("ui.fitTiles({", read("js", "character-select-layout.js"))
        item = read("js", "item-screen.js")
        self.assertIn("ui.fitTiles({", item)
        self.assertNotIn("for (let c = 1", item)
        grid = read("js", "ui", "tilegrid.js")
        self.assertIn("ui.fitTiles = function", grid)
        self.assertIn("preferCols", grid)

    def test_a_cup_is_a_ui_tile(self):
        views = read("js", "views.js")
        cups = views[views.index("async function renderCupGrid()"):views.index("async function renderCourseStrip(")]
        self.assertIn('variant: "cup"', cups)
        self.assertNotIn('className = "cup-tile"', views)
        tile = read("js", "ui", "tile.js")
        self.assertIn("function cupTile(spec)", tile)
        for needed in ('"aria-label"', "el.dataset.cup = spec.key", "el.dataset.page = spec.page", "tile-count-bubble"):
            self.assertIn(needed, tile, needed)


class TheModalStack(unittest.TestCase):
    def test_escape_tab_focus_and_z_order_are_the_stacks_job(self):
        modal = read("js", "ui", "modal.js")
        self.assertIn('window.addEventListener("keydown"', modal)
        self.assertIn("}, true);", modal)                                          # (capture: before the page's own handlers)
        self.assertIn("top.api.close()", modal)
        self.assertIn("opener.focus", modal)                                        # (focus goes back to what opened it)
        self.assertIn('e.key !== "Escape" && e.key !== "Tab"', modal)
        self.assertIn("otherWindowsZ()", modal)                                    # (above, and not above, the page's own windows)
        self.assertNotIn("zIndex = 9", modal)

    def test_a_window_that_is_busy_can_refuse_to_close(self):
        modal = read("js", "ui", "modal.js")
        self.assertIn("spec.beforeClose() === false", modal)
        confirm = read("js", "ui", "confirm.js")
        self.assertIn("beforeClose: () => !busy", confirm)

    def test_the_styles_the_components_use_exist(self):
        css = read("css", "components", "modal.css")
        for selector in (".ui-modal-backdrop {", ".ui-modal {", ".ui-modal--narrow", ".ui-modal--wide", ".ui-modal-header", ".ui-modal-body {",
                         ".ui-modal-bar", ".ui-modal-footer {", ".ui-confirm-message", ".ui-result.err", ".ui-result.ok"):
            self.assertIn(selector, css, selector)


class Buttons(unittest.TestCase):
    def test_an_async_click_is_busy_until_it_settles_and_a_failure_is_reported(self):
        button = read("js", "ui", "button.js")
        self.assertIn("handle.setBusy(true)", button)
        self.assertIn("if (busy) handle.setBusy(false)", button)
        self.assertIn('diag.error("button"', button)
        self.assertIn("ui.alert(", button)

    def test_a_confirm_option_asks_before_the_click_runs(self):
        button = read("js", "ui", "button.js")
        self.assertLess(button.index("await ui.confirm("), button.index("spec.onClick(event, value)"))

    def test_clear_all_mods_is_a_confirm_with_a_tick_box_and_a_job(self):
        panels = read("js", "settings-panels.js")
        ask = panels[panels.index("function clearAllModsConfirm()"):]
        ask = ask[:ask.index("\n}\n")]
        for needed in ('title: "Clear All Mods?"', "extra: {", "Also delete mod download files", "danger: true", "pywebview.api.clear_all_mods(deleteFiles)",
                       "return { error:", "return { message: msg"):
            self.assertIn(needed, ask, needed)
        modals = read("js", "app-modals.js")
        self.assertIn('id: "btn-clear-all-mods"', modals)
        self.assertIn("confirm: () => clearAllModsConfirm()", modals)


if __name__ == "__main__":
    unittest.main()
