"""The "It works!" confirmation on the Copy to Switch page: it is cleared when the user leaves the Commit page, so Back to Commit and Next again
shows the steps (with the "Open staging folder" button) instead of jumping straight to All done.

Run from the repo root:  python -m unittest discover -s tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

JS = Path(__file__).resolve().parent.parent / "src" / "ui" / "js"
KEY = "characters/Mario/Plain Skin"


class Confirmation(unittest.TestCase):
    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-switch-"))
        self.addCleanup(shutil.rmtree, parent, True)
        master = parent / "data"
        master.mkdir()
        self.api = mm.Api(master)
        mod = master / "mods" / "extracted" / "characters" / "Mario" / "Plain Skin" / "romfs" / "Model"
        mod.mkdir(parents=True)
        (mod / "Mario.bfres").write_bytes(b"x")
        self.api._update_state(lambda state: state.update({KEY: True}))
        self.assertTrue(self.api.merge([KEY])["staged"])

    def switch(self):
        return self.api.get_flow_status()["switch"]

    def test_confirming_makes_the_page_all_done(self):
        self.assertFalse(self.switch()["done"])
        self.api.mark_switch_done(True)
        self.assertTrue(self.switch()["done"])

    def test_clearing_it_brings_the_steps_back_without_calling_anything_stale(self):
        self.api.mark_switch_done(True)
        self.api.mark_switch_done(False)
        self.assertEqual((self.switch()["done"], self.switch()["stale"]), (False, False))
        self.assertTrue(self.switch()["staged"])   # (what to copy is still there)

    def test_clearing_it_twice_is_harmless(self):
        self.api.mark_switch_done(False)
        self.api.mark_switch_done(False)
        self.assertFalse(self.switch()["done"])


class PageClearsItOnLeavingCommit(unittest.TestCase):
    def go_step(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        return flow[flow.index("async function goStep(step, opts) {"):flow.index("// ---- page helpers ----")]

    def test_leaving_the_commit_page_clears_the_confirmation_before_anything_is_drawn(self):
        body = self.go_step()
        reset = body.index("mark_switch_done(false)")
        self.assertIn('flow.step === "commit" && step !== "commit"', body[:reset])
        self.assertLess(reset, body.index("renderSwitchPage()"))
        self.assertLess(reset, body.index('if (step === "mods")'))   # (also when the way out is back to choosing mods)

    def test_going_to_setup_does_not_clear_it(self):
        body = self.go_step()
        self.assertLess(body.index('if (step === "setup")'), body.index("mark_switch_done(false)"))

    def test_the_checklist_with_the_staging_button_is_what_a_page_without_confirmation_shows(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        page = flow[flow.index("async function renderSwitchPage()"):]
        self.assertLess(page.index("if (st.switch.done) {"), page.index("Open staging folder"))
        self.assertIn('"It works!"', page)


if __name__ == "__main__":
    unittest.main()
