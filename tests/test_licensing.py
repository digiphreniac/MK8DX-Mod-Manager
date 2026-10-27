"""The app's own license, and the credits and license notices for what it contains: GPL for the app (it includes GPL code), the icon set's and
every library's notice in the release, and the AI disclosure in the places people read.

Run from the repo root:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import third_party_notices  # noqa: E402


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class TheAppsOwnLicense(unittest.TestCase):
    def test_it_is_the_gpl_version_3(self):
        text = read("LICENSE")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)
        self.assertIn("Version 3, 29 June 2007", text)
        self.assertNotIn("MIT License", text)

    def test_the_gpl_code_it_includes_keeps_its_copyright_and_license_notice(self):
        header = read("src", "_bntx_structs.py")[:600]
        self.assertIn("BNTX Editor", header)
        self.assertIn("AboodXD", header)
        self.assertIn("GNU GPL v3", header)

    def test_the_readmes_say_so_and_say_who_made_what(self):
        for name in (("README.md",), ("release", "README.md"), ("release", "README-linux.md"), ("release", "README-macos.md")):
            text = read(*name)
            self.assertIn("GNU General Public License", text, name)
            self.assertIn("Claude Code", text, name)
            self.assertIn("No AI was used for generating artwork or assets", text, name)
            self.assertIn("THIRD-PARTY-NOTICES.txt", text, name)
        readme = read("README.md")
        self.assertIn("## About, license and credits", readme)            # (the Credits button links to its anchor, #about-license-and-credits)
        for credited in ("Tabler Icons", "BNTX Editor", "7-Zip", "pywebview", "Pillow", "Information Dump", "Wave 1", "Wave 2"):
            self.assertIn(credited, readme, credited)


class TheNoticesInTheRelease(unittest.TestCase):
    def test_the_build_copies_the_license_and_writes_the_notices_into_the_release(self):
        build = read("tools", "build_release.py")
        self.assertIn('shutil.copy2(ROOT / "LICENSE", folder / "LICENSE.txt")', build)
        self.assertIn('"third_party_notices.py", folder / "THIRD-PARTY-NOTICES.txt"', build)
        self.assertIn("add_documents(", build)
        self.assertIn('"License.txt"', read("tools", "mk8dx-mod-manager.spec"))            # (7-Zip's own license goes in as well)

    def test_the_texts_that_do_not_come_from_a_package_are_kept_in_the_repository(self):
        for name, marker in (("tabler-icons.txt", "Paweł Kuna"), ("apache-2.0.txt", "Apache License"), ("libffi.txt", "libffi")):
            self.assertIn(marker, read("release", "licenses", name), name)
        self.assertIn("MIT License", read("release", "licenses", "tabler-icons.txt"))

    def test_the_notices_name_what_is_in_the_release_and_carry_the_texts_that_ask_for_them(self):
        text = third_party_notices.build(strict=False, system="windows")      # (the other systems' notices: tests/test_cross_platform.py)
        for heading in ("Tabler Icons", "BNTX Editor", "7-Zip", "pywebview", "pillow", "bottle", "proxy_tools", "pythonnet", "clr_loader",
                        "cffi", "pycparser", "typing_extensions", "setuptools", "Python - the interpreter", "OpenSSL", "libffi"):
            self.assertIn(heading, text, heading)
        self.assertIn("Copyright (c) 2020-2026 Paweł Kuna", text)               # (the icon set's license asks for its notice in every copy)
        self.assertIn("Apache License", text)
        self.assertIn("GNU General Public License", text)
        self.assertIn("7zip\\License.txt", text)

    def test_every_package_in_the_notices_that_is_installed_here_has_its_license_text(self):
        for name, _purpose, _spdx, note in third_party_notices.PACKAGES:
            files = third_party_notices.license_files(name)
            if files is None or note:
                continue                  # (not installed in this environment: the build runs the generator strictly, where it must be)
            if name == "setuptools" and not files:
                continue
            self.assertTrue(files, f"{name} is installed but its license text wasn't found")


class TheIconsAreOneOpenLicensedSet(unittest.TestCase):
    def test_the_credit_is_where_the_icons_are_and_in_the_ui(self):
        self.assertIn("Tabler Icons", read("src", "ui", "js", "ui", "icons.js"))
        self.assertIn("Tabler Icons", read("src", "ui", "js", "app-modals.js"))        # (the Help window's About section)

    def test_help_has_an_about_section_with_a_credits_button(self):
        modals = read("src", "ui", "js", "app-modals.js")
        about = modals[modals.index('title: "About"'):modals.index("const guessedNamesModal")]
        self.assertIn("AI-assisted code", about)
        self.assertIn("GNU GPL v3 or later", about)
        self.assertIn('id: "btn-open-credits"', about)
        self.assertIn('GITHUB_URL + "#about-license-and-credits"', about)


if __name__ == "__main__":
    unittest.main()
