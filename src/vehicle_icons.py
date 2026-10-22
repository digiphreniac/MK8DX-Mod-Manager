"""The game's own pictures of its vehicle parts (bodies, tires, gliders), read from the app's copy of the game files
(see game_files.py).

Where they live - every picture is a 200x128 RGBA texture named "tc_KP_<kind>_<part>^l":
  * menu.sarc -> "mn_L_KartParts_00.szs" (the parts-menu layout) -> its BNTX package: one picture for most parts
    (tc_KP_K_Ufo = the Mach 8, tc_KP_T_Std = the Standard tires, tc_KP_G_Wlo = the Wario Wing).
  * Parts that come in several colours or outfits are not in that package but loose, one file per variant, in
    UI/cmn/menu/ as "tc_KP_<kind>_<part>_<variant>^l.bntx": the Standard Kart / Bike / ATV / Super Glider once per
    character (..._Mro = Mario's red), the rest numbered (..._00). The Vehicles screen shows each part's default (the 16 in
    LOOSE_DEFAULTS); the base-game copy keeps all 351 (38 MB), because putting your own picture on a part means writing
    every variant of it (see ui_setup.build_part_pictures()).

<kind> is K (kart body), B (bike), V (ATV), T (tire) or G (glider); <part> is the id the roster's "internal" already holds
(BodyK_Ufo -> K_Ufo, Wing_Wlo -> G_Wlo, and a tire's own id, Std -> T_Std). Every mapping was checked against the pictures.
"""
import json
import re
from pathlib import Path

import app_paths
import bntx_decode
import ui_archives

SARC_ENTRY = "mn_L_KartParts_00.szs"
PREFIX = "tc_KP_"
SUFFIX = "^l"

# texture key -> which loose variant is the part's default picture (the parts that live outside menu.sarc)
LOOSE_DEFAULTS = {
    "K_Std": "Mro", "K_Skl": "Mro", "B_Std": "Mro", "V_Atv": "Mro", "G_Std": "Mro",
    "K_Gla": "00", "K_Shp": "00", "K_Kpc": "00", "K_Ten": "00", "K_Snk": "00", "K_Fml": "00",
    "B_Sct": "00", "B_Mgp": "00", "V_Tnd": "00", "V_Spl": "00", "G_Umb": "00",
}
# roster "internal" -> texture key, where the two differ (the game's Master Cycle files call it "Zld")
KEY_ALIASES = {"BodyB_Zlb": "B_Zld"}


def texture_key(section: str, internal: str):
    """The texture key ("K_Ufo", "T_Std", "G_Wlo") of a roster part, or None when its id isn't one this understands."""
    if not internal:
        return None
    if section == "vehicles":
        if internal in KEY_ALIASES:
            return KEY_ALIASES[internal]
        return internal[len("Body"):] if internal.startswith("Body") else None
    if section == "wheels":
        return "T_" + internal
    if section == "gliders":
        return "G_" + internal.split("_", 1)[1] if "_" in internal else None
    return None


def loose_filename(key: str):
    """File name (in UI/cmn/menu/) of a loose part's default picture, or None for a part that lives in menu.sarc."""
    variant = LOOSE_DEFAULTS.get(key)
    return f"{PREFIX}{key}_{variant}{SUFFIX}.bntx" if variant else None


LOOSE_FILENAMES = tuple(sorted(loose_filename(k) for k in LOOSE_DEFAULTS))
LOOSE_FILE_RE = re.compile(r"^tc_KP_([KBVG]_[A-Za-z]+)_[A-Za-z0-9]+\^l\.bntx$", re.IGNORECASE)   # every loose part picture (351 in the game)


def loose_family(file_name: str):
    """The texture key ("K_Std") a loose part-picture file belongs to, or None when it isn't one of the game's."""
    m = LOOSE_FILE_RE.match(file_name)
    if not m:
        return None
    return next((k for k in LOOSE_DEFAULTS if k.lower() == m.group(1).lower()), None)   # (whatever case a mod's file is spelled in)


_KEY_NAMES = None


def key_names() -> dict:
    """{texture key: part name} for every part in roster.json - the inverse of texture_key()."""
    global _KEY_NAMES
    if _KEY_NAMES is None:
        _KEY_NAMES = {}
        try:
            roster = json.loads((app_paths.RESOURCE_DIR / "roster.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            roster = {}
        for section in ("vehicles", "wheels", "gliders"):
            for item in roster.get(section, []):
                key = texture_key(section, item.get("internal"))
                if key:
                    _KEY_NAMES[key] = item["name"]
    return _KEY_NAMES


def _sarc_pictures(menu_sarc_path) -> dict:
    """{texture key: PNG bytes} of every part picture in menu.sarc's parts layout; {} when it isn't readable."""
    try:
        with open(menu_sarc_path, "rb") as f:
            top = ui_archives.parse_sarc(f.read())
        textures = ui_archives.entry_textures(top[SARC_ENTRY])
    except (OSError, KeyError, ui_archives.ArchiveError):
        return {}
    found = {}
    for tex in textures:
        name = tex["name"]
        if not (name.startswith(PREFIX) and name.endswith(SUFFIX)):
            continue
        png = ui_archives.texture_png(tex)
        if png:
            found[name[len(PREFIX):-len(SUFFIX)]] = png
    return found


def load(menu_sarc_path, parts, find_loose) -> dict:
    """{part name: PNG bytes} for every part that has a picture. `parts` is [(section, part name, internal id)];
    `find_loose(file name)` gives the path of a copied loose picture, or None. {} when nothing could be read (the
    caller then keeps its plain tiles). One unreadable picture doesn't cost the others."""
    if menu_sarc_path is None:
        return {}
    in_sarc = _sarc_pictures(menu_sarc_path)
    icons = {}
    for section, name, internal in parts:
        key = texture_key(section, internal)
        if key is None:
            continue
        png = in_sarc.get(key)
        if png is None:
            fname = loose_filename(key)
            path = find_loose(fname) if fname else None
            if path is not None:
                try:
                    png = bntx_decode.decode_to_png(path)
                except (bntx_decode.UnsupportedBNTXError, OSError):
                    png = None
        if png:
            icons[name] = png
    return icons
