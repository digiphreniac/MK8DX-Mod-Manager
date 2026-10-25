"""Every setting is defined once (js/settings-registry.js) and drawn by the same code in the Settings window and in Setup.

A setting is in Setup because its `showInSetup` flag says so - nothing else. The wizard and the Settings panels know no particular setting,
and the markup has no second copy of a name or description.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"
sys.path.insert(0, str(ROOT / "src"))

import mod_manager as mm  # noqa: E402


def read(*parts):
    return UI.joinpath(*parts).read_text(encoding="utf-8")


def registry():
    """[{key, group, kind, label, description, showInSetup, text}] read out of SETTINGS in settings-registry.js."""
    js = read("js", "settings-registry.js")
    body = js[js.index("const SETTINGS = ["):js.index("\n];\n", js.index("const SETTINGS = ["))]
    entries = []
    for chunk in re.split(r"\n  \{ key: ", body)[1:]:
        text = "key: " + chunk
        entry = {"text": text}
        for field in ("key", "group", "kind"):
            entry[field] = re.search(rf'\b{field}: "([^"]+)"', text).group(1)
        entry["showInSetup"] = re.search(r"showInSetup: (true|false)", text).group(1) == "true"
        entry["has_label"] = bool(re.search(r"label: ", text))
        entry["has_description"] = "description: " in text
        entries.append(entry)
    return entries


class EverySettingIsDefinedOnce(unittest.TestCase):
    def test_each_setting_says_what_it_is_and_whether_it_is_in_setup(self):
        entries = registry()
        self.assertGreaterEqual(len(entries), 9)
        keys = [e["key"] for e in entries]
        self.assertEqual(len(keys), len(set(keys)))
        for e in entries:
            self.assertIn(e["kind"], ("toggle", "select", "text", "folder", "path"), e["key"])
            self.assertTrue(e["has_label"] and e["has_description"], e["key"])

    def test_the_settings_in_setup_are_exactly_those_flagged(self):
        flagged = sorted(e["key"] for e in registry() if e["showInSetup"])
        self.assertEqual(flagged, ["advanced_mode", "data_folder", "game_version", "show_nsfw", "ui_setup_locale"])

    def test_a_setup_step_is_a_group_with_a_flagged_setting(self):
        wizard = read("js", "setup-wizard.js")
        steps = wizard[wizard.index("function setupSteps()"):wizard.index("// `lead` is plain text")]
        self.assertIn("SETTINGS.some(s => s.group === id && s.showInSetup)", steps)
        js = read("js", "settings-registry.js")
        groups = js[js.index("const SETTING_GROUPS = {"):js.index("\n};\n", js.index("const SETTING_GROUPS = {"))]
        for e in registry():
            if e["showInSetup"]:
                self.assertRegex(groups, rf'"{e["group"]}": \{{[^\n]*setupOrder: \d', e["key"])

    def test_every_stored_setting_has_a_default_the_page_can_read(self):
        for e in registry():
            if e["kind"] != "folder":
                self.assertIn(e["key"], mm.DEFAULT_SETTINGS, e["key"])
        self.assertEqual(mm.Api(None).get_default_settings(), mm.DEFAULT_SETTINGS)


class DescriptionsCanBreakLines(unittest.TestCase):
    def test_a_newline_in_a_description_shows_as_a_line_break(self):
        css = read("css", "setting-controls.css")
        self.assertRegex(css, r"\.setting-hint \{[^}]*white-space: pre-line")
        self.assertIn("starts a new line", read("js", "settings-registry.js"))      # (the registry's own notes say so too)


class SetupUsesTheCardsName(unittest.TestCase):
    def test_a_step_has_the_name_of_its_card_and_the_language_one_is_called_game_language(self):
        js = read("js", "settings-registry.js")
        groups = js[js.index("const SETTING_GROUPS = {"):js.index("\n};\n", js.index("const SETTING_GROUPS = {"))]
        self.assertNotIn("setupTitle:", groups)       # (no second name for a group in Setup)
        self.assertIn('"ui-text": { title: "Game language"', groups)
        self.assertIn('title: "Game language"', read("js", "app-modals.js"))
        flow = read("js", "flow.js")
        self.assertIn("Open Settings > Game language, pick the language", flow)      # (the tip names the card as it is now)
        self.assertNotIn("Settings > UI icons & text", flow)


class TheLanguageList(unittest.TestCase):
    def test_not_knowing_which_english_is_a_choice_in_the_list_not_a_second_setting(self):
        js = read("js", "settings-registry.js")
        self.assertNotIn('key: "ui_setup_extra_english"', js)        # (it is stored, but it is not a setting of its own)
        language = registry()[[e["key"] for e in registry()].index("ui_setup_locale")]["text"]
        self.assertIn('label: "English (unspecified)"', language)
        self.assertIn("ui_setup_extra_english = either", language)
        self.assertIn('ui_setup_locale = either ? "USen" : value', language)
        self.assertRegex(language, r'findIndex\(l => l.value === "EUen"\) \+ 1')       # (right after the two Englishes)
        self.assertIn("state.settings.ui_setup_extra_english", language)               # (an earlier choice of both shows as this one)


class NoPlaceKnowsAParticularSetting(unittest.TestCase):
    NAMES = ("show_nsfw", "advanced_mode", "show_tile_counts", "play_select_voice", "game_version", "game_build_id", "data_folder")

    def test_neither_the_wizard_nor_the_settings_panels_name_one(self):
        for name in ("setup-wizard.js", "settings-panels.js"):
            text = read("js", name)
            for key in self.NAMES:
                self.assertNotIn(key, text, f"{name} mentions {key}")

    def test_no_name_or_description_is_written_a_second_time(self):
        for e in registry():
            for field in ("label", "description"):
                if field == "label" and e["kind"] in ("folder", "path"):
                    continue       # (a folder setting has no label of its own on the page: its card, and its Setup step, carry the name)
                found = re.search(rf'\b{field}: "((?:[^"\\]|\\.)*)"', e["text"])
                if not found or len(found.group(1)) < 12:
                    continue
                text = found.group(1).replace('\\"', '"')
                for place in (read("js", "app-modals.js"), read("js", "setup-wizard.js"), read("js", "settings-panels.js")):
                    self.assertNotIn(text, place, f"{e['key']}: {field} appears outside the registry")

    def test_the_settings_window_has_no_controls_of_its_own_for_them(self):
        html = read("js", "app-modals.js")
        self.assertNotRegex(html, r'<input type="(checkbox|text)"')
        self.assertNotIn("<select", html)
        self.assertNotIn('type: "checkbox"', html)
        for group in ("data-folder", "game-version", "app-experience"):
            self.assertIn(f'ui.settingsGroup("{group}")', html)

    def test_the_registry_is_loaded_and_both_places_use_the_one_drawing_function(self):
        self.assertIn('"js/settings-registry.js"', read("js", "bootstrap.js"))
        self.assertIn("renderSettingsGroup(step.group, host, { setup: true", read("js", "setup-wizard.js"))
        self.assertIn("renderAllSettingsGroups()", read("js", "data-and-conflicts.js"))
        self.assertIn('renderSettingsGroup("ui-text", languageHost)', read("js", "settings-panels.js"))


class ResetToDefault(unittest.TestCase):
    def test_the_button_is_on_the_card_and_reads_the_backends_defaults(self):
        modals = read("js", "app-modals.js")
        card = modals[modals.index("const appExperienceCard = ui.section({"):modals.index("const settingsModal")]
        self.assertIn('label: "Reset to default"', card)                        # (a header action of the card: a label and a callback)
        self.assertIn('groupDiffersFromDefaults("app-experience")', card)       # (enabled only while an option differs)
        self.assertIn('resetGroupToDefaults("app-experience")', card)
        js = read("js", "settings-registry.js")
        self.assertIn("get_default_settings()", js)
        self.assertNotIn("APP_EXPERIENCE_DEFAULTS", js)       # (no copy of the defaults in the page)
        self.assertNotIn("data-reset-group", js + modals)       # (no per-button hook any more)

    def test_the_four_options_are_in_the_order_the_card_shows_them(self):
        order = [e["key"] for e in registry() if e["group"] == "app-experience"]
        self.assertEqual(order, ["show_tile_counts", "play_select_voice", "show_nsfw", "advanced_mode"])
        js = read("js", "settings-registry.js")
        self.assertIn('label: "Play character-select sounds"', js)
        by_key = {e["key"]: e for e in registry()}
        self.assertNotRegex(by_key["show_tile_counts"]["text"], r'description: "[^"]')       # (these two explain nothing)
        self.assertNotRegex(by_key["play_select_voice"]["text"], r'description: "[^"]')
        self.assertRegex(by_key["show_nsfw"]["text"], r'description: "[^"]')
        self.assertRegex(by_key["advanced_mode"]["text"], r'description: "[^"]')


if __name__ == "__main__":
    unittest.main()
