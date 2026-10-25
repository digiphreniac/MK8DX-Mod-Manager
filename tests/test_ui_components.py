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
COMPONENTS = ("core", "icons", "button", "disclosure", "modal", "section", "confirm", "callout", "chip")


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
        self.assertTrue({"el", "icon", "button", "modal", "section", "confirm", "alert", "disclosure", "callout", "hint", "chip"} <= defined)
        for path in all_scripts():
            for used in re.findall(r"(?<![\w.])ui\.(\w+)", code(path.read_text(encoding="utf-8"))):
                self.assertIn(used, defined, f"{path.name} uses ui.{used}")

    def test_every_icon_asked_for_is_in_the_registry(self):
        registry = set(re.findall(r"^  (\w+): '<", read("js", "ui", "icons.js"), re.M))
        self.assertEqual(registry, {"warning", "todo", "info", "folder"})
        asked = set()
        for path in all_scripts():
            asked.update(re.findall(r'ui\.icon\("(\w+)"', path.read_text(encoding="utf-8")))
        callout = read("js", "ui", "callout.js")
        asked.update(re.findall(r': "(\w+)"', callout[callout.index("ui.icon({"):callout.index("}[tone]", callout.index("ui.icon({"))]))
        self.assertTrue(asked and asked <= registry, asked - registry)

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
        for sheet in ("modal", "callout", "chip"):
            self.assertIn(f"css/components/{sheet}.css", html)


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
