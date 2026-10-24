"""The Settings window: wide, two columns when there is room, and the list of conflicts and left-out files in a modal of its own.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "src" / "ui"


def read(*parts):
    return UI.joinpath(*parts).read_text(encoding="utf-8")


def titles(html):
    return re.findall(r'modal-card-title">([^<]*)<', html)


class TheLayout(unittest.TestCase):
    def test_the_cards_are_in_their_natural_order_in_one_balanced_container(self):
        html = read("html", "settings-modal.html")
        self.assertEqual(html.count('class="settings-columns"'), 1)
        self.assertNotIn("settings-col\"", html)       # (no hand-made columns any more)
        self.assertEqual(titles(html), ["Data folder", "UI icons &amp; text", "UI Icon Worklist", "Game version", "App experience",
                                        "Conflicts and omitted files", "Maintenance"])
        self.assertEqual(html.count("<div"), html.count("</div>"))

    def test_the_window_is_wide_and_the_columns_balance_themselves(self):
        css = read("css", "settings.css")
        self.assertRegex(css, r"#settings-modal \{[^}]*width: min\(1040px, calc\(100vw - 40px\)\)")
        columns = re.search(r"\.settings-columns \{([^}]*)\}", css).group(1)
        self.assertIn("column-count: 2", columns)
        self.assertRegex(columns, r"column-width: \d+px")
        self.assertIn("break-inside: avoid", css)
        self.assertNotIn("display: grid", re.search(r"#settings-modal-body \{([^}]*)\}", css).group(1))

    def test_the_body_scrolls_and_does_not_have_the_columns_itself(self):
        # (columns on the scrolling box would spill sideways: they go in a box of automatic height inside it)
        css = read("css", "settings.css")
        body = re.search(r"#settings-modal-body \{([^}]*)\}", css).group(1)
        self.assertIn("overflow-y: auto", body)
        self.assertNotIn("column", body)

    def test_every_id_the_scripts_use_is_still_there(self):
        html = read("html", "settings-modal.html")
        for needed in ("ui-setup-settings-body", "ui-icon-worklist-body", "btn-clear-all-mods", "btn-open-conflicts", "conflicts-summary"):
            self.assertIn(f'id="{needed}"', html, needed)


class TheConflictsModal(unittest.TestCase):
    def test_the_list_moved_out_of_settings_into_its_own_modal(self):
        settings = read("html", "settings-modal.html")
        self.assertNotIn('id="conflicts-body"', settings)
        modal = read("html", "conflicts-modal.html")
        self.assertIn('id="conflicts-body"', modal)
        self.assertIn('id="btn-conflicts-modal-close"', modal)
        self.assertIn("When two selected mods change the same file", modal)       # (the explanation went with the list)
        self.assertEqual(modal.count("<div"), modal.count("</div>"))

    def test_the_modal_is_loaded_and_sits_above_settings(self):
        self.assertIn('"html/conflicts-modal.html"', read("js", "bootstrap.js"))
        css = read("css", "settings.css")
        settings_z = int(re.search(r"#settings-modal-backdrop \{[^}]*z-index: (\d+)", css).group(1))
        conflicts_z = int(re.search(r"#conflicts-modal-backdrop \{[^}]*z-index: (\d+)", css).group(1))
        self.assertGreater(conflicts_z, settings_z)

    def test_escape_closes_it_before_anything_under_it(self):
        keys = read("js", "help-and-icon-generator.js")
        handler = keys[keys.index('document.addEventListener("keydown"'):]
        self.assertLess(handler.index("closeConflictsModal()"), handler.index("closeSettingsModal()"))

    def test_the_modal_stays_short(self):
        modal = read("html", "conflicts-modal.html")
        self.assertLess(modal.index('id="conflicts-modal-bar"'), modal.index('id="conflicts-modal-body"'))      # (the count is outside the scrolling part)
        howto = modal[modal.index('class="conflicts-howto"'):]
        self.assertIn("<summary>How this works</summary>", howto)
        self.assertGreater(modal.index('class="conflicts-howto"'), modal.index('id="conflicts-body"'))      # (the answer comes before the manual)
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
        self.assertIn('document.getElementById("btn-open-conflicts").addEventListener("click", openConflictsModal)', js)


class TheUiTextCard(unittest.TestCase):
    def test_there_is_no_do_it_by_hand_section_any_more(self):
        # (every commit rebuilds those files and replaces a hand-made copy, so the section advised something the next commit undid)
        js = read("js", "settings-panels.js")
        for gone in ("Check my work", "prefer to do this by hand", "Switch-Toolbox", "gamebanana.com/tuts/15599"):
            self.assertNotIn(gone, js, gone)
        self.assertIn("Open the folder", js)

    def test_there_are_no_rebuild_or_undo_buttons_and_nothing_points_at_them(self):
        # (a commit is the only thing that builds the menu files, and it would make a removed build again)
        card = read("js", "settings-panels.js")
        for gone in ("Rebuild now", "Undo (remove the built files)", "build_ui_setup", "reset_ui_setup", "uiSetup.lastBuild", "Files are saved to"):
            self.assertNotIn(gone, card, gone)
        self.assertIn("Built automatically when you commit.", card)
        status = read("js", "menu-icons-text.js")
        self.assertIn("changes are in it - commit again", status)
        self.assertNotIn("- rebuild", status)
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
        self.assertIn("!d.locales.some(l => l.code === d.locale)", warning)       # (only when none of them change the chosen language)
        self.assertIn("None of your mods change this language - they change", warning)


if __name__ == "__main__":
    unittest.main()
