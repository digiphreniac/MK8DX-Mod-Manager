"""The app tells GameBanana who is asking: its name, its version and where the project is.

Run from the repo root:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gamebanana_api  # noqa: E402
from version import VERSION  # noqa: E402


class TheUserAgent(unittest.TestCase):
    def test_it_names_the_app_its_version_and_the_project(self):
        agent = gamebanana_api.USER_AGENT
        self.assertTrue(agent.startswith("MK8DX-Mod-Manager/"))
        self.assertIn(VERSION, agent)
        self.assertIn("https://github.com/digiphreniac/MK8DX-Mod-Manager", agent)
        self.assertNotIn("personal", agent)


if __name__ == "__main__":
    unittest.main()
