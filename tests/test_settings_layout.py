"""The Settings window: wide, two columns when there is room, and the list of conflicts and left-out files in a modal of its own.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def read(*parts):
    return UI.joinpath(*parts).read_text(encoding="utf-8")


def modals():
    """js/app-modals.js: the windows as specs."""
    return read("js", "app-modals.js")


def settings_spec():
    js = modals()
    return js[js.index("const settingsModal = ui.modal({"):js.index("const conflictsModal")]


def conflicts_spec():
    js = modals()
    return js[js.index("const conflictsModal = ui.modal({"):js.index("const helpModal")]


def titles(spec):
    """The cards' titles in the order the window lists them (the App experience card is made above the window, and listed by name)."""
    found = re.findall(r'title: "([^"]*)"|(appExperienceCard),', spec[spec.index("ui.columns(["):])
    return [title or "App experience" for title, named in found]


class TheLayout(unittest.TestCase):
    def test_the_cards_are_in_their_natural_order_in_one_balanced_container(self):
        spec = settings_spec()
        self.assertEqual(spec.count("ui.columns("), 1)
        self.assertIn('"settings-columns"', read("js", "ui", "section.js"))
        self.assertNotIn("settings-col\"", spec)       # (no hand-made columns any more)
        self.assertEqual(titles(spec), ["Data folder", "Staging folder", "Game language", "UI Icon Worklist", "Game version", "App experience",
                                        "Conflicts and omitted files", "Maintenance"])

    def test_the_window_is_wide_and_the_columns_balance_themselves(self):
        self.assertIn('size: "wide"', settings_spec())
        modal_css = read("css", "components", "modal.css")
        self.assertRegex(modal_css, r"\.ui-modal--wide \{ --ui-modal-w: 1040px")
        self.assertRegex(modal_css, r"\.ui-modal \{[^}]*width: min\(var\(--ui-modal-w\), calc\(100vw - 40px\)\)")
        css = read("css", "settings.css")
        columns = re.search(r"\.settings-columns \{([^}]*)\}", css).group(1)
        self.assertIn("column-count: 2", columns)
        self.assertRegex(columns, r"column-width: \d+px")
        self.assertIn("break-inside: avoid", css)
        self.assertNotIn("display: grid", re.search(r"\.ui-modal-body \{([^}]*)\}", modal_css).group(1))

    def test_the_body_scrolls_and_does_not_have_the_columns_itself(self):
        # (columns on the scrolling box would spill sideways: they go in a box of automatic height inside it)
        css = read("css", "components", "modal.css")
        body = re.search(r"\.ui-modal-body \{([^}]*)\}", css).group(1)
        self.assertIn("overflow-y: auto", body)
        self.assertNotIn("column", body)

    def test_every_id_the_scripts_use_is_still_there(self):
        spec = settings_spec()
        for needed in ("ui-setup-settings-body", "ui-icon-worklist-body", "btn-clear-all-mods", "btn-open-conflicts", "conflicts-summary"):
            self.assertIn(f'id: "{needed}"', spec, needed)
        modal = read("js", "ui", "modal.js")
        for part in ("${id}-backdrop", "${id}-header", "${id}-body", "btn-${id}-close"):       # (settings-modal-body, btn-settings-modal-close ...)
            self.assertIn(part, modal, part)

class TheConflictsModal(unittest.TestCase):
    def test_the_list_moved_out_of_settings_into_its_own_modal(self):
        self.assertNotIn('id: "conflicts-body"', settings_spec())
        modal = conflicts_spec()
        self.assertIn('id: "conflicts-body"', modal)
        self.assertIn('id: "conflicts-modal"', modal)                         # (so its Close button is btn-conflicts-modal-close)
        self.assertIn("When two selected mods change the same file", modal)       # (the explanation went with the list)

    def test_the_modal_is_loaded_and_sits_above_settings(self):
        bootstrap = read("js", "bootstrap.js")
        self.assertIn('"js/app-modals.js"', bootstrap)
        self.assertNotIn("conflicts-modal.html", bootstrap)
        self.assertLess(bootstrap.index('"js/ui/modal.js"'), bootstrap.index('"js/app-modals.js"'))
        # (a window opened while another is showing goes above it: the stack gives each one a higher z-index than the one under it)
        self.assertIn("stack[stack.length - 1].z + STEP", read("js", "ui", "modal.js"))

    def test_escape_closes_it_before_anything_under_it(self):
        modal = read("js", "ui", "modal.js")
        handler = modal[modal.index('window.addEventListener("keydown"'):]
        self.assertIn("const top = stack[stack.length - 1];", handler)       # (only the top window of the stack)
        self.assertIn("top.api.close()", handler)
        legacy = read("js", "help-and-icon-generator.js")
        legacy = legacy[legacy.index('document.addEventListener("keydown"'):]
        for gone in ("closeConflictsModal()", "closeSettingsModal()", "closeHelpModal()", "above-settings"):
            self.assertNotIn(gone, legacy, gone)       # (the page's own Escape handler no longer knows these windows)

    def test_the_modal_stays_short(self):
        modal = conflicts_spec()
        self.assertIn("bar: true", modal)
        self.assertLess(modal.index("bar: true"), modal.index('id: "conflicts-body"'))      # (the count is outside the scrolling part: the bar is above the body)
        self.assertLess(read("js", "ui", "modal.js").index("bar, body, footer"), read("js", "ui", "modal.js").index("document.body.append(backdrop)"))
        self.assertIn('summary: "How this works"', modal[modal.index('"conflicts-howto"'):])
        self.assertGreater(modal.index('"conflicts-howto"'), modal.index('id: "conflicts-body"'))      # (the answer comes before the manual)
        js = read("js", "data-and-conflicts.js")
        draw = js[js.index("async function renderConflicts()"):]
        self.assertIn('"cg-settled"', draw)
        self.assertIn("result.groups.length === 0", draw)      # (folded away while something still needs settling)
        self.assertIn("conflictsSettledOpen", draw)
        self.assertIn('"conflicts-none"', draw)
        css = read("css", "conflicts.css")
        self.assertRegex(css, r"\.cg-file-list \{[^}]*max-height: \d+px; overflow-y: auto")
        self.assertIn("cgFileList(", js[js.index("function buildConflictCard"):js.index("async function renderConflicts()")])

    def test_the_file_list_puts_the_name_first(self):
        js = read("js", "data-and-conflicts.js")
        body = js[js.index("function cgFileList(paths)"):]
        body = body[:body.index("\n}\n")]
        self.assertIn('lastIndexOf("/")', body)
        self.assertLess(body.index('cgEl("b"'), body.index('"cg-dir"'))

    def test_the_summary_is_kept_up_to_date_by_the_same_code_that_draws_the_list(self):
        js = read("js", "data-and-conflicts.js")
        draw = js[js.index("async function renderConflicts()"):]
        self.assertIn("updateConflictsSummary(result);", draw[:300])
        self.assertIn("closeConflictsModal();", js)       # (Open mod from the list leaves both windows)
        self.assertIn('id: "btn-open-conflicts", label: "Review", size: "small", onClick: () => openConflictsModal()', modals())


class TheUiTextCard(unittest.TestCase):
    def test_there_is_no_do_it_by_hand_section_any_more(self):
        # (every commit rebuilds those files and replaces a hand-made copy, so the section advised something the next commit undid)
        js = read("js", "settings-panels.js")
        for gone in ("Check my work", "prefer to do this by hand", "Switch-Toolbox", "gamebanana.com/tuts/15599"):
            self.assertNotIn(gone, js, gone)
        # (what is built, file by file, is not listed and the folder is not offered: nothing there can be acted on)
        for gone in ("Open the folder", "uisBuiltState", "uis-result", "Built automatically", "any_sources"):
            self.assertNotIn(gone, js + read("js", "menu-icons-text.js") + read("css", "flow.css"), gone)
        self.assertNotIn("def open_ui_setup_folder", (UI.parent / "mod_manager.py").read_text(encoding="utf-8"))

    def test_the_card_keeps_the_language_the_conflict_picks_and_a_warning_for_a_damaged_file(self):
        js = read("js", "settings-panels.js")
        card = js[js.index("async function renderUiSetupSettingsCard()"):]
        card = card[:card.index("\n}\n")]
        self.assertIn('renderSettingsGroup("ui-text", languageHost)', card)
        self.assertIn("None of your mods change this language", card)
        self.assertIn("renderUiArchiveConflicts", card)
        self.assertIn("a.verify.problems.length", card)       # (only a damaged file is worth a line)
        self.assertIn("A built menu file has a problem", card)

    def test_there_are_no_rebuild_or_undo_buttons_and_nothing_points_at_them(self):
        # (a commit is the only thing that builds the menu files, and it would make a removed build again)
        card = read("js", "settings-panels.js")
        for gone in ("Rebuild now", "Undo (remove the built files)", "build_ui_setup", "reset_ui_setup", "uiSetup.lastBuild", "Files are saved to"):
            self.assertNotIn(gone, card, gone)
        self.assertNotIn('click \\"Undo\\"', read("js", "flow.js"))       # (the troubleshooting tip no longer sends people to Undo)
        source = (UI.parent / "mod_manager.py").read_text(encoding="utf-8")
        for gone in ("def build_ui_setup", "def reset_ui_setup", "def stage_ui_files"):
            self.assertNotIn(gone, source, gone)

    def test_the_language_picker_has_no_long_note_only_a_warning_when_the_mods_do_nothing(self):
        js = read("js", "settings-panels.js")
        self.assertNotIn("Your mods make", js)
        self.assertNotIn("Other languages they change", js)
        warning = js[js.index("const others = d.locales"):]
        warning = warning[:warning.index("\n  }\n")]
        self.assertIn("!d.locales.some(l => chosen.includes(l.code))", warning)       # (only when none of them change the chosen language - or either English)
        self.assertIn("None of your mods change this language - they change", warning)


if __name__ == "__main__":
    unittest.main()
