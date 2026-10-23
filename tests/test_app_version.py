"""The version shown in the app's footer comes from src/version.py through Api.get_app_version().

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402
import version            # noqa: E402


class AppVersion(unittest.TestCase):
    def test_the_footer_gets_the_version_from_version_py(self):
        root = Path(tempfile.mkdtemp(prefix="mk8dx-ver-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(mm.Api(root).get_app_version(), version.VERSION)

    def test_it_is_a_plain_major_minor_patch_number(self):
        # (the release workflow only accepts this form, and the footer shows it as "v" + this)
        self.assertRegex(version.VERSION, r"^[0-9]+\.[0-9]+\.[0-9]+$")


if __name__ == "__main__":
    unittest.main()
