"""The game's own pictures of its items (Banana, Green Shell, Super Horn ...), read from the app's copy of the game files
(see game_files.py).

Where they live: menu.sarc -> "mn_L_ItemSwitch_Item_00.szs" (the layout of the Item Switch screen, where a custom race picks
which items appear) -> its BNTX package: one 192x192 RGBA texture per item, named "tc_Item_<icon>^l" (tc_Item_Koura = the
Green Shell, tc_Item_PKinoko = the Golden Mushroom). Each item's <icon> is written into the roster ("icon" in roster.json's
"items"); an item that has no picture there (the Item Box, the Rupee and the Bell are models only) has no "icon" and keeps its
name on its tile.

The same textures are also in race.sarc (rc_L_ItemBox_00.szs, the item slot in a race, where the triple / double forms and the
Rupee's picture are as well); the app's copy has no race.sarc, and the Item Switch set is every picture the Items screen shows.
"""
import ui_archives

SARC_ENTRY = "mn_L_ItemSwitch_Item_00.szs"
PREFIX = "tc_Item_"
SUFFIX = "^l"


def _sarc_pictures(menu_sarc_path) -> dict:
    """{icon key ("Koura", "PKinoko"): PNG bytes} of every item picture in menu.sarc's Item Switch layout; {} when it isn't
    readable."""
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


def load(menu_sarc_path, items) -> dict:
    """{item name: PNG bytes} for every item that has a picture. `items` is the roster's list of {"name", "icon", ...}.
    {} when nothing could be read (the caller then keeps its plain tiles). One unreadable picture doesn't cost the others."""
    if menu_sarc_path is None:
        return {}
    pictures = _sarc_pictures(menu_sarc_path)
    return {i["name"]: pictures[i["icon"]] for i in items if i.get("icon") and i["icon"] in pictures}
