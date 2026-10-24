"""The app's icon: a square, transparent picture in the sizes Windows asks for, embedded in the exe by the build.

Run from the repo root:  python -m unittest discover -s tests
"""
import importlib.util
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def load_maker():
    spec = importlib.util.spec_from_file_location("make_icon", TOOLS / "make_icon.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheIconFiles(unittest.TestCase):
    def test_the_ico_has_every_size_windows_asks_for(self):
        with Image.open(TOOLS / "app-icon.ico") as ico:
            sizes = set(ico.info.get("sizes", []))
        self.assertTrue({(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= sizes, sorted(sizes))

    def test_the_source_picture_is_square_and_transparent_round_the_edge(self):
        with Image.open(TOOLS / "app-icon.png") as png:
            self.assertEqual(png.size[0], png.size[1])
            self.assertEqual(png.mode, "RGBA")
            self.assertEqual(png.getpixel((0, 0))[3], 0)

    def test_the_picture_fills_the_icon_but_is_not_cut_off(self):
        with Image.open(TOOLS / "app-icon.png") as png:
            box = png.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        self.assertGreater(box[0], 0)
        self.assertGreater(box[1], 0)
        self.assertLess(box[2], png.size[0])
        self.assertLess(box[3], png.size[1])
        self.assertGreater((box[2] - box[0]) / png.size[0], 0.8)   # (a small margin, not a small picture)

    def test_the_build_embeds_it(self):
        spec = (TOOLS / "mk8dx-mod-manager.spec").read_text(encoding="utf-8")
        self.assertIn('icon=str(ROOT / "tools" / "app-icon.ico")', spec)


class TheMaker(unittest.TestCase):
    def test_the_maker_crops_to_the_drawing_and_centres_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "wide.png"
            wide = Image.new("RGBA", (700, 300), (0, 0, 0, 0))
            wide.paste(Image.new("RGBA", (200, 100), (255, 0, 0, 255)), (400, 150))
            wide.save(src)
            icon = load_maker().square_icon(src)
        self.assertEqual(icon.size, (512, 512))
        box = icon.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        self.assertAlmostEqual(centre[0], 256, delta=3)
        self.assertAlmostEqual(centre[1], 256, delta=3)

    def test_a_soft_glow_does_not_make_the_icon_smaller(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "glow.png"
            img = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
            img.paste(Image.new("RGBA", (500, 500), (0, 0, 255, 12)), (50, 50))       # a faint glow over most of the picture
            img.paste(Image.new("RGBA", (200, 200), (255, 0, 0, 255)), (200, 200))    # the drawing
            img.save(src)
            icon = load_maker().square_icon(src)
        box = icon.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        self.assertGreater((box[2] - box[0]) / 512, 0.8)


if __name__ == "__main__":
    unittest.main()
