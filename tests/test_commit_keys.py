"""The Commit page sends every selected mod, including one downloaded and selected in the same session.

The page used to send "the mods in its own list that are selected". That list (state.categories) is only reloaded by loadMods(), so on a
fresh data folder a mod downloaded and selected during the session was not in it: the Commit page said "No mods are selected yet" while the
step bar (which asks the backend) said "1 mod selected", and Refresh didn't help because it doesn't redraw the Commit page.

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


class PageSendsTheSelectedKeys(unittest.TestCase):
    def test_the_commit_page_and_the_commit_button_use_the_selection_not_the_pages_list(self):
        flow = (JS / "flow.js").read_text(encoding="utf-8")
        self.assertNotIn("allKeys()", flow)
        render = flow[flow.index("async function renderCommitPage()"):flow.index("function pgWarnEl(")]
        commit = flow[flow.index("async function doCommit()"):flow.index("// ---- Step 5: Copy to Switch ----")]
        self.assertIn("selectedKeys()", render)
        self.assertIn("selectedKeys()", commit)

    def test_selectedkeys_is_every_key_marked_true_and_nothing_else(self):
        helpers = (JS / "state-and-helpers.js").read_text(encoding="utf-8")
        body = helpers[helpers.index("function selectedKeys()"):helpers.index("function allKeys()")]
        self.assertIn("Object.keys(state.checked || {}).filter(k => state.checked[k])", body)


class BackendCopesWithAKeyItDoesNotKnow(unittest.TestCase):
    """Now that the page sends what is selected, a selected mod that is no longer on the disk reaches the backend: it says so, it doesn't fail."""

    def setUp(self):
        parent = Path(tempfile.mkdtemp(prefix="mk8dx-keys-"))
        self.addCleanup(shutil.rmtree, parent, True)
        master = parent / "data"
        master.mkdir()
        self.api = mm.Api(master)

    def test_the_preview_reports_a_selected_mod_that_is_gone(self):
        preview = self.api.preview_commit(["characters/Mario/Gone/Mod"])
        self.assertFalse(preview["empty"])
        self.assertIn("missing", [w["kind"] for w in preview["warnings"]])

    def test_a_commit_of_only_a_gone_mod_says_so_and_stages_nothing_from_it(self):
        lines = self.api.merge(["characters/Mario/Gone/Mod"])["lines"]
        self.assertTrue(any(line.startswith("SKIPPED (romfs not found): characters/Mario/Gone/Mod") for line in lines))
        self.assertIn("Mods merged: 0", lines)


if __name__ == "__main__":
    unittest.main()
