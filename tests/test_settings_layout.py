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

    def test_app_experience_holds_the_four_options_in_order_and_only_the_last_two_explain_themselves(self):
        html = read("html", "settings-modal.html")
        card = html[html.index("App experience"):html.index('id="conflicts-card"')]
        ids = re.findall(r'<input type="checkbox" id="([^"]+)"', card)
        self.assertEqual(ids, ["setting-show-tile-counts", "setting-play-select-voice", "setting-show-nsfw", "setting-advanced-mode"])
        self.assertIn("Play character-select sounds", card)
        self.assertEqual(card.count('class="settings-hint"'), 2)
        self.assertLess(card.index("setting-show-nsfw"), card.index('class="settings-hint"'))      # (no hint before the NSFW option)

    def test_app_experience_can_be_reset_and_the_defaults_match_the_backends(self):
        html = read("html", "settings-modal.html")
        header = html[html.index("App experience"):]
        header = header[:header.index("</div>")]
        self.assertIn('id="btn-reset-app-experience"', header)
        self.assertIn("Reset to default", header)
        js = read("js", "settings-panels.js")
        found = dict(re.findall(r"(\w+): (true|false)", re.search(r"const APP_EXPERIENCE_DEFAULTS = \{([^}]*)\}", js).group(1)))
        source = (UI.parent / "mod_manager.py").read_text(encoding="utf-8")
        for key, value in found.items():
            self.assertRegex(source, rf'"{key}": {value.capitalize()},', key)      # (DEFAULT_SETTINGS says the same)
        self.assertEqual(sorted(found), ["advanced_mode", "play_select_voice", "show_nsfw", "show_tile_counts"])

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
        for needed in ("ui-setup-settings-body", "ui-icon-worklist-body", "setting-game-version", "setting-game-build-id", "setting-show-nsfw",
                       "setting-advanced-mode", "btn-clear-all-mods", "btn-change-master-dir", "setting-master-dir-path", "btn-open-conflicts",
                       "conflicts-summary"):
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


if __name__ == "__main__":
    unittest.main()
