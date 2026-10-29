"""The All done page's "Enjoying your mods?" card: like on GameBanana, star on GitHub, buy a coffee.

These check the page's files as text (nothing is run or opened): that the addresses are what they should be and that the backend would open
them, and that the card is what the All done page shows.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

JS = Path(__file__).resolve().parent.parent / "src" / "ui" / "js"


def constant(name):
    text = (JS / "state-and-helpers.js").read_text(encoding="utf-8")
    found = re.search(rf'^const {name} = "([^"]*)";', text, re.MULTILINE)
    assert found, f"{name} is not defined"
    return found.group(1)


class SupportCard(unittest.TestCase):
    def test_the_github_address_is_the_projects_page(self):
        self.assertEqual(constant("GITHUB_URL"), "https://github.com/digiphreniac/MK8DX-Mod-Manager")

    def test_the_discord_invite_is_the_communitys(self):
        self.assertEqual(constant("DISCORD_URL"), "https://discord.gg/mNShnnu8j8")

    def test_the_donation_address_is_unchanged(self):
        self.assertEqual(constant("SUPPORT_URL"), "https://buymeacoffee.com/digiphreniac")

    def test_the_gamebanana_address_is_empty_or_a_gamebanana_page(self):
        url = constant("GAMEBANANA_PAGE_URL")
        self.assertTrue(url == "" or re.fullmatch(r"https://gamebanana\.com/(tools|mods)/\d+", url), url)

    def test_the_backend_opens_each_address_and_nothing_odd(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-support-"))
        self.addCleanup(shutil.rmtree, parent, True)
        api = mm.Api(parent)
        urls = [constant("GITHUB_URL"), constant("SUPPORT_URL"), constant("DISCORD_URL")] + ([constant("GAMEBANANA_PAGE_URL")] if constant("GAMEBANANA_PAGE_URL") else [])
        # Every link goes through host_tools.open_browser, which gives the browser the system's own library path
        # instead of the PyInstaller bundle's (docs/browser-mode.md).
        with mock.patch.object(mm.host_tools, "open_browser", return_value=True) as opened:
            for url in urls:
                self.assertTrue(api.open_external_url(url)["success"], url)
        self.assertEqual([c.args[0] for c in opened.call_args_list], urls)

    def test_a_browser_that_will_not_open_is_reported_and_does_not_raise(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-support-"))
        self.addCleanup(shutil.rmtree, parent, True)
        api = mm.Api(parent)
        with mock.patch.object(mm.host_tools, "open_browser", return_value=False):
            result = api.open_external_url(constant("GITHUB_URL"))
        self.assertFalse(result["success"])
        self.assertIn("browser", result["error"].lower())

    def test_the_all_done_page_shows_the_card_and_no_longer_the_single_button(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        done = flow[flow.index("if (st.switch.done) {"):flow.index("body.appendChild(buildTroubleshooting());")]
        self.assertIn("body.appendChild(supportCard());", done)
        self.assertNotIn("openSupportPage", done)

    def test_the_card_offers_like_star_and_donate_in_that_order_and_hides_a_missing_address(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        card = flow[flow.index("function supportCard()"):flow.index("async function renderSwitchPage()")]
        self.assertLess(card.index("Like it on GameBanana"), card.index("Star it on GitHub"))
        self.assertLess(card.index("Star it on GitHub"), card.index("Buy me a coffee"))
        self.assertIn("GAMEBANANA_PAGE_URL &&", card)
        self.assertIn(".filter(Boolean)", card)
        self.assertIn("The more likes the page has", card)

    def test_the_discord_row_comes_last_and_help_and_the_readme_have_the_link_too(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        card = flow[flow.index("function supportCard()"):flow.index("async function renderSwitchPage()")]
        self.assertLess(card.index("Buy me a coffee"), card.index("Join the Discord"))
        root = JS.parent.parent.parent
        self.assertIn('id: "btn-open-discord"', (JS / "app-modals.js").read_text(encoding="utf-8"))
        self.assertIn("openExternal(DISCORD_URL)", (JS / "help-and-icon-generator.js").read_text(encoding="utf-8"))
        self.assertIn(constant("DISCORD_URL"), (root / "README.md").read_text(encoding="utf-8"))

    def test_the_coffee_row_is_worded_as_an_invitation(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        self.assertIn("If you feel so inclined.", flow)
        self.assertNotIn("Optional, and it keeps the updates coming", flow)

    def test_each_row_has_its_icon_and_the_brands_with_a_logo_show_it(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        registry = (JS / "ui" / "icons.js").read_text(encoding="utf-8")
        for name in ("like", "star"):
            self.assertIn(f'icon: "{name}"', flow)
            self.assertIn(f"  {name}: '<", registry)          # (generic Tabler icons for GameBanana and GitHub)
        self.assertIn('logo: "buy-me-a-coffee", label: "Buy me a coffee"', flow)
        self.assertIn('logo: "discord", label: "Join the Discord"', flow)
        self.assertNotIn("<svg", flow)
        self.assertIn("ui.logo(way.logo", flow)
        self.assertIn("pg-support-icon", (JS.parent / "css" / "flow.css").read_text(encoding="utf-8"))

    def test_help_s_discord_button_shows_the_discord_logo(self):
        modals = (JS / "app-modals.js").read_text(encoding="utf-8")
        button = modals[modals.index('id: "btn-open-discord"'):]
        self.assertIn('icon: ui.logo("discord"', button[:200])

    def test_the_logos_are_the_brands_own_files_and_carry_nothing_but_drawing(self):
        registry = (JS / "ui" / "icons.js").read_text(encoding="utf-8")
        for name, file in (("discord", "discord.svg"), ("buy-me-a-coffee", "buy-me-a-coffee.svg")):
            self.assertIn(f'img/{file}', registry)
            svg = (JS.parent / "img" / file).read_text(encoding="utf-8")
            self.assertTrue(svg.lstrip().startswith(("<svg", "<?xml")), file)
            for unsafe in ("<script", "href", "<image", "url(", "onload", "foreignObject"):
                self.assertNotIn(unsafe, svg, f"{file}: {unsafe}")

    def test_the_footer_no_longer_asks_for_a_donation(self):
        html = (JS.parent / "index.html").read_text(encoding="utf-8")
        footer = html[html.index('<footer id="stats-footer">'):html.index("</footer>")]
        self.assertNotIn("support-link", footer)
        self.assertNotIn("Donate", footer)
        self.assertNotIn("support-link", (JS / "help-and-icon-generator.js").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
