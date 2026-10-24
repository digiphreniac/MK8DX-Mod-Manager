"""The "Which version is your game?" list shows just the version numbers, so typing one jumps to it.

A drop-down selects the first option whose text STARTS with what is typed; with a "Version " in front of every number, typing "3.0.3" matched
nothing. The first two entries ("I'm not sure", "Not listed (probably newer)") start with letters, which no version number does.

Run from the repo root:  python -m unittest discover -s tests
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mod_manager as mm  # noqa: E402

JS = Path(__file__).resolve().parent.parent / "src" / "ui" / "js"


class GameVersionList(unittest.TestCase):
    def test_each_version_is_listed_by_its_number_alone(self):
        registry = (JS / "settings-registry.js").read_text(encoding="utf-8")
        function = registry[registry.index("function gameVersionChoices("):]
        function = function[:function.index("\n}\n")]
        self.assertIn("add(v.version, v.version);", function)
        self.assertNotIn('"Version "', function)

    def test_the_two_other_choices_come_first_and_start_with_a_letter(self):
        registry = (JS / "settings-registry.js").read_text(encoding="utf-8")
        function = registry[registry.index("function gameVersionChoices("):]
        function = function[:function.index("\n}\n")]
        labels = re.findall(r'add\("[^"]*", "([^"]*)"\)', function)
        self.assertEqual(labels, ["I'm not sure", "Not listed (probably newer)"])
        self.assertFalse(any(label[0].isdigit() for label in labels))

    def test_the_numbers_the_list_gets_are_plain_dotted_versions(self):
        api = mm.Api(None)
        for entry in api.get_game_versions():
            self.assertRegex(entry["version"], r"^\d+(\.\d+)+$")


if __name__ == "__main__":
    unittest.main()
