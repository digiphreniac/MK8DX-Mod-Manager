"""The game's own Grand Prix (cup) medallions, read from the app's copy of menu.sarc (see game_files.py).

Where they live: menu.sarc -> "mn_L_CupSlctBtn_00.szs" (the cup-select button layout) -> its BNTX package, one 200x200
texture per cup named "ym_CupIcon<Name>^h". Measured against a real dump:

  * The format is 0x0701 - 16 bits per pixel, blue-green-red 5-6-5, no alpha: a round medallion on a square backdrop
    (the game's layout masks it round). So decoding = deswizzle, unpack 565, swap red/blue, and cut the circle here.
  * The 12 base-game cups are named after their emblem (Mushroom, Flower, Star, Special, Shell, Banana, Leaf, Thunder)
    or, for the four added by the game's first two DLC waves, "DLC02".."DLC05" (Egg, Triforce, Crossing, Bell).
    The 12 Booster Course Pass cups are "Charger00".."Charger11", in the pass's order (Golden Dash ... Spiny).
    Every mapping below was checked by looking at the decoded pictures.
"""
import io

import bntx_decode
import ui_archives

import diag

try:
    from PIL import Image, ImageDraw
except ImportError as _e:  # no pictures, and the screen falls back to its plain tiles
    Image = None
    diag.log("error", f"Pillow couldn't be loaded ({_e}): cup pictures can't be drawn, so the screen uses plain tiles")

ENTRY = "mn_L_CupSlctBtn_00.szs"
TEXTURE_NAME = "ym_CupIcon{}^h"
FORMAT_BGR565 = 0x07

# roster.json cup name -> texture suffix
CUP_TEXTURES = {
    "Mushroom Cup": "Mushroom", "Flower Cup": "Flower", "Star Cup": "Star", "Special Cup": "Special",
    "Shell Cup": "Shell", "Banana Cup": "Banana", "Leaf Cup": "Leaf", "Lightning Cup": "Thunder",
    "Egg Cup": "DLC02", "Triforce Cup": "DLC03", "Crossing Cup": "DLC04", "Bell Cup": "DLC05",
    "Golden Dash Cup": "Charger00", "Lucky Cat Cup": "Charger01", "Turnip Cup": "Charger02",
    "Propeller Cup": "Charger03", "Rock Cup": "Charger04", "Moon Cup": "Charger05",
    "Fruit Cup": "Charger06", "Boomerang Cup": "Charger07", "Feather Cup": "Charger08",
    "Cherry Cup": "Charger09", "Acorn Cup": "Charger10", "Spiny Cup": "Charger11",
}

_SUPERSAMPLE = 4   # the round cut-out is drawn this much larger, then shrunk, so its edge is smooth
_MARGIN = 2        # px between the medallion's rim and the edge of the picture (of 200)


def _medallion_png(tex: dict):
    """PNG bytes of one decoded medallion, or None if this texture isn't the expected 5-6-5 shape."""
    w, h = tex["width"], tex["height"]
    if (tex["format"] >> 8) != FORMAT_BGR565 or w != h:
        return None
    raw = bntx_decode._deswizzle(w, h, 1, 2, tex["layout"] & 7, tex["data"])
    img = Image.frombuffer("RGB", (w, h), bytes(raw), "raw", "BGR;16", 0, 1)   # (Pillow's name for 5-6-5, red/blue swapped)
    r, g, b = img.split()
    img = Image.merge("RGB", (b, g, r)).convert("RGBA")
    big = w * _SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    m = _MARGIN * _SUPERSAMPLE
    ImageDraw.Draw(mask).ellipse((m, m, big - m - 1, big - m - 1), fill=255)
    img.putalpha(mask.resize((w, w), Image.LANCZOS))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def load(menu_sarc_path) -> dict:
    """{cup name: PNG bytes} for every cup whose medallion could be read from menu.sarc, or {} when the archive isn't
    readable (the caller then keeps its plain tiles)."""
    if Image is None or menu_sarc_path is None:
        return {}
    try:
        with open(menu_sarc_path, "rb") as f:
            top = ui_archives.parse_sarc(f.read())
        textures = {t["name"]: t for t in ui_archives.entry_textures(top[ENTRY])}
    except (OSError, KeyError, ui_archives.ArchiveError):
        return {}
    icons = {}
    for cup, suffix in CUP_TEXTURES.items():
        tex = textures.get(TEXTURE_NAME.format(suffix))
        if tex is None:
            continue
        try:
            png = _medallion_png(tex)
        except Exception:   # one odd texture shouldn't cost the other 23
            png = None
        if png:
            icons[cup] = png
    return icons
