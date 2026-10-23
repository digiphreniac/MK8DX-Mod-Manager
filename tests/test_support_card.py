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

    def test_the_donation_address_is_unchanged(self):
        self.assertEqual(constant("SUPPORT_URL"), "https://buymeacoffee.com/digiphreniac")

    def test_the_gamebanana_address_is_empty_or_a_gamebanana_page(self):
        url = constant("GAMEBANANA_PAGE_URL")
        self.assertTrue(url == "" or re.fullmatch(r"https://gamebanana\.com/(tools|mods)/\d+", url), url)

    def test_the_backend_opens_each_address_and_nothing_odd(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-support-"))
        self.addCleanup(shutil.rmtree, parent, True)
        api = mm.Api(parent)
        urls = [constant("GITHUB_URL"), constant("SUPPORT_URL")] + ([constant("GAMEBANANA_PAGE_URL")] if constant("GAMEBANANA_PAGE_URL") else [])
        with mock.patch.object(mm.webbrowser, "open") as opened:
            for url in urls:
                self.assertTrue(api.open_external_url(url)["success"], url)
        self.assertEqual([c.args[0] for c in opened.call_args_list], urls)

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

    def test_the_footer_link_still_goes_to_the_donation_page(self):
        self.assertIn("openSupportPage", (JS / "help-and-icon-generator.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
