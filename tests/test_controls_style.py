"""Drop-down lists and fold-away sections share one look (css/layout.css), in the app's colours, light and dark.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "src" / "ui" / "css"


def read(name):
    return (CSS / name).read_text(encoding="utf-8")


def rules(text):
    """[(selector, declarations)] of the plain rules of a stylesheet (no nesting: this app's CSS has none)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text)]


def block(selector):
    for sel, body in rules(read("layout.css")):
        if sel == selector:
            return body
    raise AssertionError(f"no rule for {selector} in layout.css")


class Select(unittest.TestCase):
    def test_the_native_look_is_replaced_and_the_arrow_is_drawn_in_the_apps_colours(self):
        body = block("select")
        self.assertIn("appearance: none", body)
        self.assertIn("var(--text-dim)", body)            # (the arrow: two triangles, so it follows the theme)
        self.assertEqual(body.count("linear-gradient"), 2)
        for needed in ("var(--panel)", "var(--panel-border)", "var(--text)", "border-radius", "cursor: pointer"):
            self.assertIn(needed, body)

    def test_it_reacts_to_the_mouse_and_the_keyboard_and_when_it_is_off(self):
        for selector in ("select:hover:not(:disabled)", "select:focus-visible", "select:disabled", "select option"):
            block(selector)

    def test_no_rule_for_a_select_hides_the_arrow_with_the_background_shorthand(self):
        # (`background:` resets background-image, which is where the arrow is; a select's rules use background-color)
        for path in CSS.glob("*.css"):
            for selector, body in rules(path.read_text(encoding="utf-8")):
                if selector.endswith("option"):
                    continue                      # (the rows of the opened list: they have a background of their own)
                if re.search(r"(^|[\s,>+~])select\b|\.gb-sort-select|\.settings-text-input", selector):
                    self.assertNotRegex(body, r"(^|;|\s)background\s*:", f"{path.name}: {selector}")

    def test_the_lists_with_their_own_class_keep_room_for_the_arrow(self):
        sort = next(body for sel, body in rules(read("gamebanana-card.css")) if sel == ".gb-sort-select")
        self.assertRegex(sort, r"padding:\s*\d+px 2\d+px")
        self.assertIn("select.settings-text-input", read("add-mod.css"))
        self.assertIn(".add-mod-choice-row select { padding-right: 30px; }", read("add-mod.css"))


class Details(unittest.TestCase):
    def test_the_browsers_triangle_is_replaced_by_a_chevron_that_turns_when_it_opens(self):
        self.assertIn("list-style: none", block("details > summary"))
        self.assertIn("display: none", block("details > summary::-webkit-details-marker"))
        chevron = block("details > summary::before")
        self.assertIn("currentColor", chevron)               # (it takes the summary's colour: accent for a link-like one)
        self.assertIn("rotate(-45deg)", chevron)
        self.assertIn("rotate(45deg)", block("details[open] > summary::before"))

    def test_the_box_has_the_apps_colours_and_the_summary_can_be_reached_by_keyboard(self):
        box = block("details")
        for needed in ("var(--panel-border)", "var(--bg-soft)", "border-radius"):
            self.assertIn(needed, box)
        self.assertIn("var(--accent)", block("details > summary:focus-visible"))
        self.assertIn("var(--text)", block("details > summary:hover"))

    def test_the_ones_that_sit_inside_a_line_of_text_keep_the_chevron_but_not_the_box(self):
        conflicts = read("conflicts.css")
        for selector in (".cg-files", ".ml-custom", ".ml-custom-body details"):
            body = next(b for s, b in rules(conflicts) if s == selector)
            self.assertIn("background: none", body, selector)
            self.assertIn("border: 0", body, selector)

    def test_the_places_that_had_their_own_box_no_longer_repeat_it(self):
        flow = read("flow.css")
        self.assertNotIn("border-radius: 10px; padding: 8px 12px; margin: 0 0 10px 0", flow)
        self.assertNotIn("cursor: pointer; padding: 2px 0; font-size: 13px; font-weight: 600", flow)
        item = next(b for s, b in rules(read("item-screen.css")) if s == ".cc-move")
        self.assertNotIn("border:", item)


if __name__ == "__main__":
    unittest.main()
