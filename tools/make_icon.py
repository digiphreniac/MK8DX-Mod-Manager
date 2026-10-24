"""Makes the app's icon from a picture.

    python tools/make_icon.py path/to/picture.png

Writes tools/app-icon.png (square, transparent, 512 px: the source of the icon) and tools/app-icon.ico (16 to 256 px in one file),
which tools/mk8dx-mod-manager.spec embeds in the exe. Windows shows that icon on the file, the taskbar, alt-tab and the window's title bar
(pywebview takes the window's icon from the exe). The picture is cropped to what is drawn in it, with a small margin, and centred on a square
canvas, so a wide or padded picture still fills the icon.
"""
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SIZES = [16, 24, 32, 48, 64, 128, 256]
MARGIN = 0.05          # of the longer side, around what is drawn
VISIBLE = 40           # alpha above which a pixel counts as drawn (a soft glow around the picture doesn't)


def square_icon(path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    box = img.getchannel("A").point(lambda v: 255 if v > VISIBLE else 0).getbbox() or (0, 0, *img.size)
    drawn = img.crop(box)
    side = round(max(drawn.size) * (1 + 2 * MARGIN))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(drawn, ((side - drawn.width) // 2, (side - drawn.height) // 2), drawn)
    return canvas.resize((512, 512), Image.LANCZOS)


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    icon = square_icon(argv[1])
    icon.save(HERE / "app-icon.png")
    icon.save(HERE / "app-icon.ico", sizes=[(s, s) for s in SIZES])
    print(f"Wrote {HERE / 'app-icon.png'} and {HERE / 'app-icon.ico'} ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    main(sys.argv)
