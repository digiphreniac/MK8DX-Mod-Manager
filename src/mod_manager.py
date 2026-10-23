#!/usr/bin/env python3
"""
Mod Manager GUI - checklist for which downloaded mods should be merged into
a single SD-card-ready romfs tree, replacing manual active-mods.txt editing
and Mod Alchemy's per-mod enable/disable dance.

Run with:  python3 mod_manager.py
(or double-click "Run Mod Manager.bat" on Windows, which launches this via WSL)
"""

import base64
import copy
import difflib
import filecmp
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import app_paths
# A packaged (windowed) build has no console: send output to a log file before the libraries
# below are imported, since some of them (pywebview) set up their logging when first imported.
LOG_PATH = app_paths.redirect_output_to_log() if app_paths.FROZEN else None
if app_paths.FROZEN:   # (also before the import below: pythonnet is refused by Windows while the zip's "downloaded" mark is on it)
    print(f"Cleared the downloaded-file mark from {app_paths.unblock_downloaded_files()} bundled files")

import webview

import bntx_decode
import bntx_encode
import cup_icons
import image_cache
import library_cache
import safe_io
from library_cache import mutates_library
import item_icons
import vehicle_icons
import gamebanana_api
import ui_setup
import voice_audio
import voice_edit
import game_files
import gb_desc_cache
from version import VERSION as APP_VERSION
from voice_api import VoiceEditMixin, VOICE_EDITS_FILENAME
from mod_notes import ModNotesMixin, NOTES_FILENAME

TITLE_ID = "0100152000022000"  # Mario Kart 8 Deluxe
STATE_FILENAME = "mod-manager-state.json"
ROSTER_FILENAME = "roster.json"
GB_CATEGORIES_CACHE_FILENAME = "gamebanana-categories-cache.json"
DLC_FIRST_CUP = "Golden Dash Cup"   # the first Booster Course Pass cup (its courses' pictures are DLC01..DLC48)
GB_MODS_FILENAME = "gamebanana-mods.json"
GB_DESCRIPTIONS_FILENAME = "gamebanana-descriptions.json"
CONFLICT_RESOLUTIONS_FILENAME = "conflict-resolutions.json"
# Files a mod must NOT contribute to the merge ("leave this file out of this
# mod") - the way conflicts get settled, and also a plain per-mod choice. See
# Api.exclude_files() / _compute_claims().
EXCLUDED_FILES_FILENAME = "excluded-files.json"
# Static app data (curated, shipped next to the script) explaining common
# cross-course shared-asset conflicts in plain English - shown alongside a
# conflict in Advanced mode's resolver. Not user data - same category as
# roster.json below.
KNOWN_SHARED_FILES_FILENAME = "known-shared-files.json"
SETTINGS_FILENAME = "app-settings.json"
APP_CONFIG_FILENAME = "app-config.json"
# Layout under the master directory: mods/downloads/<category>/ holds the raw
# downloaded archives, mods/extracted/<category>/<mod folder>/romfs/... holds
# what they unpack to (what discover_mods()/find_mod_units() scan).
MODS_DIRNAME = "mods"
LOOK_REVIEWS_FILENAME = "look-reviews.json"
DOWNLOADS_DIRNAME = "downloads"
EXTRACTED_DIRNAME = "extracted"
# Holds app-generated course-select icons (see Api.generate_course_icon()) -
# always merged in, same idea as ui-icons/ for character icons, but kept
# separate from it so app-generated files never mix with the user's own
# hand-curated ui-icons/ content.
COURSE_ICONS_DIRNAME = "course-icons"
# The same for the user's own pictures for vehicle parts that are loose files (see ui_setup.build_part_pictures()).
PART_ICONS_DIRNAME = "part-icons"
# MK8DX's own CoursePict template convention, measured directly across four
# different real mod-provided ym_CoursePict.bntx files (different courses,
# different authors) - all landed within 1px of each other: the visible
# photo sits in a 288x162 (exactly 16:9) window inset from the full 304x256
# texture, not centered - 8px on each side, 29px on top, 65px on the
# bottom. The lopsided bottom margin is almost certainly reserved for the
# course name/mode text the game's own UI draws over this texture at
# render time. generate_course_icon() composites into this same window so
# a generated icon looks consistent with a real one instead of filling the
# whole canvas edge to edge.
_COURSE_PICT_CONTENT_LEFT = 8
_COURSE_PICT_CONTENT_TOP = 29
_COURSE_PICT_CONTENT_W = 288
_COURSE_PICT_CONTENT_H = 162
# Same window, as a (left, top, right, bottom) crop box - used to strip the
# black padding back out of a CoursePict when previewing it in the app (the
# padding is only there for the real game's own UI to draw over; showing it
# raw in our own UI just looks like a rendering bug).
_COURSE_PICT_CROP_BOX = (
    _COURSE_PICT_CONTENT_LEFT,
    _COURSE_PICT_CONTENT_TOP,
    _COURSE_PICT_CONTENT_LEFT + _COURSE_PICT_CONTENT_W,
    _COURSE_PICT_CONTENT_TOP + _COURSE_PICT_CONTENT_H,
)
CHARACTERS_CATEGORY_ID = 10529
VEHICLES_CATEGORY_ID = 10530  # parent of the vehicle-part section categories, see VEHICLE_SECTIONS
# "Simple" mod categories - unlike characters/courses these have no roster
# to show per-item tiles for, so the app just tracks one fixed pseudo-item
# per category (its own label, e.g. "Mechanics") the same way it would any
# single character/course, and gives it a plain list screen instead of a
# grid. gb_category_id is the real GameBanana category id - verified live
# that Mod/Index's Generic_Category filter accepts a top-level category id
# and returns mods from every subcategory beneath it, so no per-subcategory
# resolution (like characters need) is necessary here.
SIMPLE_MOD_CATEGORIES = {
    "mechanics": {"label": "Mechanics", "gb_category_id": 5088},
    "ui": {"label": "UI", "gb_category_id": 2162},
    # Code patches (exefs .ips files) have a GameBanana category of their own besides Mechanics
    "code_patches": {"label": "Code patches", "gb_category_id": 26513},
    # A pack has no one card: it is listed on every card of what it replaces too (see get_pack_links)
    "modpacks": {"label": "Modpacks", "gb_category_id": 16881},
    # Custom battle courses replace battle arenas, which the course roster has no cards for - subcategory of Courses
    "battle_courses": {"label": "Battle courses", "gb_category_id": 31808},
}
# GameBanana's Skins > Packs and Skins > Other/Misc subcategories: mods of a character / vehicle / item kind that no single
# roster entry names. A search from a card of those kinds lists them too (see _search_kind).
SKINS_PACKS_CATEGORY_ID = 10562
SKINS_MISC_CATEGORY_ID = 10528
# Items got their own screen and a fixed per-item roster (roster.json's "items": Banana, Green Shell, Super Horn ...) like
# vehicle parts. GameBanana has one flat "Items" category (no subcategory per item), so - as with tires and gliders - it lists
# every item mod and each is annotated with the item its text says it replaces (see match_vehicle_targets, which reads the
# roster's names / aliases / model-folder ids). Mods are filed under mods/extracted/items/<item name>/. Anything filed before
# items had a roster sits in items/Items/ (the one fixed pseudo-item they used to be): it stays where it is, and shows as the
# last tile, "Other items" - the place for a mod that fits none of the listed items too (or several of them: an item pack).
ITEMS_CATEGORY = "items"
ITEMS_GB_CATEGORY_ID = 10579
ITEMS_OTHER = "Items"          # the catch-all's name (its folder, its download records); shown as ITEMS_OTHER_LABEL
ITEMS_OTHER_LABEL = "Other items"
# Vehicle parts get their own tab and a fixed per-item roster (roster.json:
# 41 bodies, 22 tires, 15 gliders) instead of a single pseudo-item. GameBanana
# has no per-part subcategory, only these section categories under Vehicles
# (10530): bodies are split by type (Kart / Bikes (Outward = standard) / Bikes
# (Inward = sport) / ATVs), tires and gliders each have one flat category.
# Each section is also its own on-disk category folder.
VEHICLE_SECTIONS = {
    "vehicles": {"label": "Vehicles", "roster_key": "vehicles"},
    "wheels": {"label": "Wheels", "roster_key": "wheels", "gb_category_id": 10577},
    "gliders": {"label": "Gliders", "roster_key": "gliders", "gb_category_id": 10578},
}
VEHICLE_BODY_CATEGORY_IDS = {
    ("kart", None): 10571,
    ("bike", "standard"): 10572,
    ("bike", "sport"): 10573,
    ("atv", None): 10574,
}
# Platform prefixes used in roster.json's courses to disambiguate ports (e.g.
# "Wii Moo Moo Meadows") - stripped before searching GameBanana, since mods
# describe the base course by its own name ("Moo Moo Meadows"), not the
# prefixed disambiguated label this app displays it under.
COURSE_NAME_PREFIXES = ("Wii ", "GBA ", "DS ", "N64 ", "GCN ", "SNES ", "3DS ", "Tour ")
# Where the app's own read-only files live (ui/, roster.json, ...) - fixed, never moves.
SCRIPT_DIR = app_paths.RESOURCE_DIR
# The app's install root (one level above src/ from source; the folder holding the .exe in a
# packaged build). app-config.json (the bootstrap pointer to the user-chosen master directory)
# lives here rather than next to the code, since it can't live inside the directory it's pointing at.
APP_ROOT = app_paths.APP_ROOT
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_SETTINGS = {
    "show_nsfw": False,
    "advanced_mode": False,
    # Character Select: show the "1/4" (ticked / downloaded) badge on every character tile. Off by
    # default - the header, the card and the tile's tooltip already carry the numbers.
    "show_tile_counts": False,
    # Browse GameBanana: how the mods are listed ("grid" or "list") and how they are sorted - the last ones chosen, so the
    # window opens the way the user left it. "" = not chosen yet (each kind of mod then has its own starting sort).
    "gb_browse_view": "grid",
    "gb_browse_sort": "",
    # Character Select: play a character's select sound (the voice the game plays when it is picked, from its ticked
    # mods) when its mod is finished and each time its tile is clicked afterwards - see Api.get_select_voice().
    "play_select_voice": True,
    # Optional: the exefs build id (32 hex chars) of the user's own game
    # version. When set, code patches built for a different build are flagged
    # as inert (they'd silently do nothing) - see Api.get_exefs_unit_info().
    "game_build_id": "",
    # Menu icons & text (built automatically on Commit - see Api.merge()): which language's
    # message.sarc to build, whether to also build the other English variant, and which mod
    # wins where two changed the same icon/text ({item id: variant id}).
    "ui_setup_locale": "USen",
    "ui_setup_extra_english": False,
    "ui_setup_choices": {},
    # Guided-flow bookkeeping (see Api.get_flow_status()): what the last
    # commit / UI build was made from, so the app can tell when a step has gone
    # stale, and whether the user has confirmed it works on their Switch.
    "last_commit": None,     # {"sig", "at", "mods", "files", "left_out"}
    "last_ui_build": None,   # {"sig", "at"}
    "switch_done": None,     # {"sig", "at"}
    # First-run wizard: null = never shown. Required (see Api.get_flow_status()'s "setup" -
    # also needs the base-game-files copy to exist), no grandfathering for older installs.
    "setup_done": None,
    # The user's game version label (e.g. "3.0.3"); game_build_id above is the
    # exact identifier the code-patch checks use - choosing a known version
    # fills it in.
    "game_version": "",
}
# Everything that lives under the configurable master directory - moved as a
# unit when the user changes it with "bring my existing files along". This is
# strictly user data (downloads, checked/desired-mod state, caches) - it does
# NOT include roster.json, which is a static app resource (the fixed
# roster/cup/vehicle-part definitions) shipped next to the script and
# always read from there, the same as the UI's files in ui/ - a "start fresh" master
# directory must never leave the app without a roster to render. Same reason
# KNOWN_SHARED_FILES_FILENAME isn't here either.
MASTER_DIR_ITEMS = [
    STATE_FILENAME,
    GB_CATEGORIES_CACHE_FILENAME, GB_MODS_FILENAME, GB_DESCRIPTIONS_FILENAME, CONFLICT_RESOLUTIONS_FILENAME,
    EXCLUDED_FILES_FILENAME, SETTINGS_FILENAME, MODS_DIRNAME, "ui-icons", COURSE_ICONS_DIRNAME, PART_ICONS_DIRNAME,
    "ui-icons-backups", "ui-setup-cache.json", image_cache.DIRNAME,
    ui_setup.OVERRIDES_FILENAME, ui_setup.OVERRIDES_DIRNAME, NOTES_FILENAME,
]
_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*]')


def load_master_dir_pointer():
    """Reads app-config.json from the app root. Returns the master directory
    the user chose as a Path, or None when they never changed it (the app then
    uses default_master_dir())."""
    config_path = APP_ROOT / APP_CONFIG_FILENAME
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    raw = data.get("master_dir")
    return Path(raw) if raw else None


DEFAULT_DATA_DIRNAME = "data"


def default_master_dir():
    """The folder used until the user picks another: `data` inside the app's own folder (next to the .exe in a packaged build),
    created when missing. None when that place can't be written to (say the app sits in Program Files) - the app then asks
    the user to choose a folder, as it always did."""
    folder = APP_ROOT / DEFAULT_DATA_DIRNAME
    try:
        folder.mkdir(exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("")
        probe.unlink()
    except OSError:
        return None
    return folder


def save_master_dir_pointer(path: Path):
    config_path = APP_ROOT / APP_CONFIG_FILENAME
    safe_io.write_json_atomic(config_path, {"master_dir": str(path)})
def show_in_file_manager(path: Path, select: bool = False):
    """Opens the system file manager at a folder, or (select=True) on a file with
    it highlighted. Finder on macOS, Explorer on Windows and under WSL, the desktop's
    default handler elsewhere. Raises OSError if it couldn't be launched."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)] if select else ["open", str(path)], check=True)
    elif sys.platform == "win32" or (hasattr(os, "uname") and "microsoft" in os.uname().release.lower()):
        # explorer.exe's /select switch needs quotes around just the path,
        # not the whole "/select,path" argument (which is what Python's
        # normal list-based quoting produces) - so build the command line
        # ourselves and pass it as a single string.
        # It's also well known to return a non-zero exit code even on
        # success, so we only treat "couldn't launch it at all" as failure.
        subprocess.run(f'explorer.exe /select,"{path}"' if select else f'explorer.exe "{path}"')
    else:
        subprocess.run(["xdg-open", str(path.parent if select else path)], check=True)


def normalize_char_name(name: str) -> str:
    """Loosely match names like 'Bowser Jr.' / 'Bowser Jr' or 'Villager (Boy)' /
    'Villager Boy' which differ only in punctuation used in folder names."""
    name = name.replace(".", "").replace("(", "").replace(")", "")
    return " ".join(name.split()).lower()


def strip_course_prefix(name: str) -> str:
    for prefix in COURSE_NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def sanitize_filename(name: str) -> str:
    # Windows silently strips trailing dots/spaces from folder names at the
    # Win32 API layer, but 7-Zip creates the literal path it's given - so a
    # mod name ending in "." (e.g. "Wonder Bowser Jr.") makes 7-Zip's actual
    # output folder disagree with what Python's own path/exists checks see,
    # and find_mod_units() ends up looking in an empty phantom folder while
    # the real content sits one character over. Stripping trailing dots/
    # spaces here avoids the whole class of mismatch.
    #
    # Path separators and colons are written as " - " rather than dropped:
    # dropping them glued words together ("Parafoil/MKTV Parafoil: The Freedom
    # Special" became "ParafoilMKTV Parafoil The Freedom Special"). The other
    # invalid characters (<>"|?*) are just removed.
    cleaned = re.sub(r"\s*[/\\:](?:\s*[/\\:])*\s*", " - ", name)
    cleaned = _INVALID_FS_CHARS.sub("", cleaned)
    cleaned = re.sub(r"^(?: - )+|(?: - )+$", "", cleaned)  # a separator at either end
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().rstrip(". ")
    return cleaned or "mod"


def unique_path(path: Path) -> Path:
    """Returns path unchanged if nothing exists there yet, otherwise appends
    ' (2)', ' (3)', ... until it finds one that doesn't collide. For files
    (name.ext) only - splits on the last '.' to keep the extension, which is
    wrong for directory names that contain a period themselves (e.g. an
    abbreviation like "Jr."). Use unique_dir_path() for those."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def unique_dir_path(path: Path) -> Path:
    """Like unique_path(), but for directories - appends ' (2)', ' (3)', ...
    to the end of the whole name rather than splitting stem/suffix, since a
    folder name may contain a period that isn't a file extension."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.name} ({n})")
        if not candidate.exists():
            return candidate
        n += 1


def find_mod_units(extracted_root: Path):
    """Find every folder that directly contains a 'romfs' subfolder, without
    descending into it further (so a mod's own romfs/ contents, and any of
    its other subfolders, never get mistaken for separate mod units).
    Returns paths relative to extracted_root.

    Matches "romfs" case-insensitively - some GameBanana archives ship it as
    "Romfs"/"RomFS"/etc. Windows' filesystem is case-insensitive for actual
    file access, but os.walk()'s dirnames list preserves on-disk casing, so a
    literal "romfs" in dirnames check misses those and would otherwise flag a
    perfectly good mod as needing manual fixing."""
    units = []
    for dirpath, dirnames, _filenames in os.walk(extracted_root):
        if any(d.lower() == "romfs" for d in dirnames):
            units.append(Path(dirpath).relative_to(extracted_root))
            dirnames[:] = []  # don't recurse into this mod's own subfolders
    return sorted(units, key=lambda p: str(p).lower())


# --- exefs code patches -----------------------------------------------------
# Some mods (most "Mechanics" ones - a coin cap, a version backport, ...) don't
# change any romfs data at all; they patch the game's executable with one or
# more IPS files named after the exact game build they're made for. Atmosphere
# loads these from atmosphere/exefs_patches/<any patch-set name>/<BUILDID>.ips
# (verified against its own docs/loader source): every set is scanned, only a
# file whose name matches the running game's build id applies, and several
# sets stack. Only lowercase ".ips" is read - ".ips32"/".pchtxt"/".IPS" and
# non-hex names are silently ignored by the loader, so they're never staged.
#
# A "patch unit" is the folder that directly holds such files (the mod's own
# "exefs/" folder in Ryujinx-style packaging, an "exefs/<name>/" subfolder, or
# an author-shipped "atmosphere/exefs_patches/<name>/") - its key is that
# folder's path, exactly like a romfs unit's key is the folder holding romfs/.
_EXEFS_PATCH_RE = re.compile(r"^(?:[0-9a-f]{2})+\.ips$", re.IGNORECASE)
EXEFS_PATCHES_DIRNAME = "exefs_patches"
# Prefix on every patch-set folder this app writes into the staging tree, so
# a re-merge clears exactly its own previous output and never touches other
# patch sets (sigpatches, ...) already on the user's SD card.
EXEFS_STAGING_PREFIX = "mk8dxmm_"
# Build id -> game version, keyed by the build id's first BUILD_ID_LEN hex characters (the way cheat databases and
# version tables name a build; use build_key()). An id missing from this table is shown as just its raw id rather
# than guessed at.
BUILD_ID_LEN = 16
KNOWN_BUILD_IDS = {
    # Confirmed by a source (a mod's own readme / a cheat database):
    "6A85262F21B90364": "3.0.3",
    "9EF5CAA2D5B933C7": "3.0.1",
    # Inferred, not confirmed: the ids come from HamletDuFromage/switch-cheats-db (versions/0100152000022000.json), which
    # pairs each with a Nintendo update number (one per release, in steps of 65536). The versions are those releases counted
    # in order from the Mario Wiki's update history, with the China-only 3.0.2 taking no number - which is what makes the two
    # confirmed ids above come out right. Releases with no exefs change have no id of their own here.
    "B5C39B5B7C62A88E": "1.0.0",   # update 0
    "FE1B230800D4933C": "1.7.1",   # update 589824
    "4792ABA465F04534": "1.7.2",   # 655360
    "937E57FF64D21ECD": "2.0.0",   # 720896
    "BDA8F5E6A0F87F36": "2.1.0",   # 786432
    "60C8343AFBA2588F": "2.2.0",   # 851968
    "381F6BF6894F3C33": "2.2.1",   # 917504
    "13296B64DFA7A131": "2.3.0",   # 983040
    "4B7A0BB5AE57E627": "2.4.0",   # 1048576
    "FE941ED5BA14BE5D": "3.0.5",   # 1376256
    "2C336A9BCF79C304": "4.0.0",   # 1441792
}


def build_key(build_id):
    """The part of a build id that is compared: its first BUILD_ID_LEN hex characters, upper-case."""
    return (build_id or "").strip().upper()[:BUILD_ID_LEN]


def build_in(mine, build_ids):
    """Whether `mine` (the user's build id, either length) is one of `build_ids` (a patch's ids, usually 32 hex long)."""
    return any(build_key(b) == build_key(mine) for b in build_ids)


# game_version value for "Not listed (probably newer)": the user's build is none of KNOWN_BUILD_IDS.
NEWER_VERSION = "newer"


def patch_fit(mine, game_version, build_ids):
    """How a code patch's build ids fit the user's game: "wrong" (their build id is set and none of these is it), "maybe" (they
    said their game is newer than any listed version, and every id here is a listed - so older - build: it may or may not still
    work, since a game update often leaves the executable alone), or None (fits, or nothing is known to say otherwise)."""
    if not build_ids:
        return None
    if mine:
        return None if build_in(mine, build_ids) else "wrong"
    if game_version == NEWER_VERSION and all(build_key(b) in KNOWN_BUILD_IDS for b in build_ids):
        return "maybe"
    return None


def find_exefs_units(extracted_root: Path):
    """Relative paths of every folder under extracted_root that directly
    holds at least one <hex build id>.ips file. Never descends into a romfs/
    (mod data, not patches) - but does keep walking a romfs unit's siblings,
    since a Ryujinx-style mod puts exefs/ right next to its romfs/."""
    units = []
    for dirpath, dirnames, filenames in os.walk(extracted_root):
        has_romfs_child = any(d.lower() == "romfs" for d in dirnames)
        dirnames[:] = [d for d in dirnames if d.lower() != "romfs"]
        # A folder that itself holds a romfs/ is already a romfs unit - its
        # key would collide with this one's, so it's never also a patch unit.
        if not has_romfs_child and any(_EXEFS_PATCH_RE.match(f) for f in filenames):
            units.append(Path(dirpath).relative_to(extracted_root))
    return sorted(units, key=lambda p: str(p).lower())


def parse_ips(data: bytes):
    """Decodes an IPS ("PATCH"/"EOF") or IPS32 ("IPS32"/"EEOF") file into
    [(offset, bytes), ...] with RLE records expanded. Raises ValueError for
    anything malformed."""
    if data[:5] == b"PATCH":
        off_len, eof = 3, b"EOF"
    elif data[:5] == b"IPS32":
        off_len, eof = 4, b"EEOF"
    else:
        raise ValueError("not an IPS/IPS32 file")
    pos = 5
    records = []
    while pos < len(data):
        chunk = data[pos:pos + off_len]
        if chunk == eof:
            return records
        if len(chunk) < off_len or pos + off_len + 2 > len(data):
            raise ValueError("truncated record header")
        offset = int.from_bytes(chunk, "big")
        size = int.from_bytes(data[pos + off_len:pos + off_len + 2], "big")
        pos += off_len + 2
        if size == 0:  # RLE: 2-byte run length, 1 byte value
            if pos + 3 > len(data):
                raise ValueError("truncated RLE record")
            run = int.from_bytes(data[pos:pos + 2], "big")
            records.append((offset, data[pos + 2:pos + 3] * run))
            pos += 3
        else:
            if pos + size > len(data):
                raise ValueError("truncated record data")
            records.append((offset, data[pos:pos + size]))
            pos += size
    raise ValueError("missing end-of-patch marker")


def first_ips_clash(a_records, b_records):
    """Offset of the first byte range two parsed patches both write with
    DIFFERENT bytes, or None. Identical bytes at the same place are fine (two
    mods bundling the same fix), mirroring the romfs merge's own dedupe."""
    for a_off, a_data in a_records:
        for b_off, b_data in b_records:
            lo = max(a_off, b_off)
            hi = min(a_off + len(a_data), b_off + len(b_data))
            if lo < hi and a_data[lo - a_off:hi - a_off] != b_data[lo - b_off:hi - b_off]:
                return lo
    return None


def find_course_slot_names(folder: Path) -> set:
    """Collects every internal course-slot id a downloaded course mod
    actually writes to (the name of each folder directly inside a "Course/"
    directory, anywhere in the tree - handles a multi-variant pack's own
    nested Course/ just as well as a plain romfs/Course/<id>/). Used to cross-
    check a download against roster.json's known internal id(s) for
    that course - see Api._course_internal_names()."""
    names = set()
    for dirpath, dirnames, _filenames in os.walk(folder):
        if Path(dirpath).name.lower() == "course":
            names.update(dirnames)
    return names


# Race BGM files follow a fixed "..._F.bfstm"/"..._N.bfstm" naming convention
# (final-lap and normal variants) with the course's music id sandwiched in the
# middle - e.g. "pBGM_WU_WATER_PARK_F.bfstm", "BGM_N64_KINOPIO_HIGHWAY_N.bfstm".
# Deliberately narrow (requires that exact _F/_N suffix) so it never matches
# the many *other* BGM_*.bfstm files a course mod can bundle alongside its own
# race music - menu/result/system stingers like "BGM_FINAL_LAP.bfstm" or
# "BGM_SYS_FLAGOPEN.bfstm" don't end in "_F"/"_N" and are correctly ignored.
_COURSE_BGM_RE = re.compile(r"BGM_(.+?)_(?:F|N)\.bfstm$", re.IGNORECASE)

# Audio/Static/BGM.bars is a single game-wide table of short music "prefetch"
# clips (one per track), not a per-course file - every downloaded course mod
# observed to bundle it also ships its actual music as its own uniquely-named
# .bfstm in Audio/Resource/Stream/, and only rebuilds this whole shared table
# to shave the ~1s of stale prefetch audio off the very start of the course.
# Two course mods bundling their own full copy of it collide constantly (it's
# the single biggest source of cross-course merge conflicts), for a payoff
# that's cosmetic at best - so it's never merged in from any mod, full stop.
_MERGE_SKIP_RELPATHS = {"audio/static/bgm.bars"}


def _is_packed_ui_archive(rel: Path) -> bool:
    """True for a packed .sarc directly under romfs/UI/ - see the long comment
    in Api._compute_claims() for why the merge never copies these in."""
    return bool(rel.parts) and rel.parts[0].lower() == "ui" and rel.suffix.lower() == ".sarc"


def path_kind(path: str) -> str:
    """A plain-language kind for a romfs-relative (or exefs pseudo-) path, so a
    conflict can say "4 menu pictures" instead of listing raw paths."""
    low = path.lower().replace("\\", "/")
    if low.startswith("exefs/"):
        return "code patch"
    ext = low.rsplit(".", 1)[-1] if "." in low.rsplit("/", 1)[-1] else ""
    if low.startswith("ui/") or ext in ("bntx", "png", "dds"):
        return "menu picture"
    if low.startswith("audio/") or ext in ("bwav", "bfstm", "bars", "bfwav", "bfsar", "bfwsd", "bfgrp"):
        return "sound"
    if low.startswith("mapobj/"):
        return "course object"
    if low.startswith("course/"):
        return "course file"
    if "emblem" in low:
        return "kart emblem"
    if low.startswith("kart/"):
        return "kart file"
    if ext in ("bfres", "bfmda", "gsh"):
        return "model or texture"
    return "game file"


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "\u2026"


def mod_label(key: str, full: bool = False) -> str:
    """"characters/Inkling Girl/Minecraft Alex/inner" -> "Minecraft Alex (Inkling Girl)".

    A mod folder holding several units keeps the unit's own name too ("Sunshine >
    over Metal Mario") - unless it's just the mod's name again (spelled a little
    differently: "Custom Glidder..." / "Custom Glider..."). The mod's name is cut to 40
    characters and the unit's to 32 so a card never has to show a whole sentence; `full=True` keeps
    everything (used for tooltips)."""
    parts = key.split("/")
    if len(parts) < 3:
        return parts[-1]
    cut = (lambda t, n: t) if full else _short
    name = parts[2]
    if len(parts) > 3:
        unit = parts[-1]
        a, b = name.lower(), unit.lower()
        if not (a.startswith(b) or b.startswith(a) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.7):
            name = f"{cut(name, 40)} > {cut(unit, 32)}"
        else:
            name = cut(name, 60)
    else:
        name = cut(name, 60)
    return name if parts[1].lower() in name.lower() else f"{name} ({parts[1]})"


# A name a mod could give its character, cleaned out of the mod's (or its folder's) name:
# "Sandy Cheeks in Mario Kart 8 Deluxe" -> "Sandy Cheeks", "Freddy Fazbear over King Boo" ->
# "Freddy Fazbear", "Wreck-it-Ralph Mod For DK" -> "Wreck-it-Ralph". Used by sync_auto_names() for
# characters and by get_course_look() for the name suggested on a course card.
_NAME_SPLIT_RE = re.compile(r"\s+(?:over|in|for|with|from|w/)\s+|\s+[|:]\s+|\s+-\s+", re.IGNORECASE)
_NAME_NOISE_RE = re.compile(r"\b(mod|mk8d?x?|deluxe|port|edit|updated|improved|version|v\d[\d.]*)\b", re.IGNORECASE)
# folder names that say nothing about who the character is
_JUNK_NAME_WORDS = {"romfs", "copytosd", "preinjected", "pack", "option", "over", "files", "data", "main", "default",
                    "base", "standard", "ui", "icons", "icon", "voice", "sound", "audio", "kart", "glider", "bike", "atv"}


def suggest_name_from_mod(mod_name: str, item_name: str, max_len: int = 24):
    """A short character name taken from a mod/folder name, or None when nothing usable is left
    (empty, too long for the menus, only noise words, or just the character's own game name)."""
    n = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", (mod_name or "").replace("_", " "))
    n = _NAME_SPLIT_RE.split(n)[0]
    n = _NAME_NOISE_RE.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"\s+w$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"^(?:over|for)\s+", "", n, flags=re.IGNORECASE).strip(" -_!,")   # a folder called "over Mario"
    if len(n) < 2 or len(n) > max_len or len(re.findall(r"[A-Za-z]", n)) < 2:
        return None
    words = {w.lower() for w in re.split(r"\W+", n) if w and not w.isdigit()}   # "Option 8" is as empty as "Option"
    if _name_key(n) == _name_key(item_name) or words <= _JUNK_NAME_WORDS:
        return None
    return n


def unit_has_driver_model(unit: Path) -> bool:
    """Whether a mod unit replaces a character's MODEL (Driver/*.szs under its romfs) - as
    opposed to only voices, menu sounds, kart parts or menu pictures. Only those name a character."""
    for dirpath, dirnames, _files in os.walk(unit):
        romfs = [d for d in dirnames if d.lower() == "romfs"]
        if not romfs:
            continue
        dirnames[:] = []
        driver = _ci_child(Path(dirpath) / romfs[0], "Driver")
        if driver is not None and any(f.suffix.lower() == ".szs" for f in driver.iterdir() if f.is_file()):
            return True
    return False


def unit_voice_files(unit: Path) -> list:
    """[(kind, path)] - the voice archives a mod unit ships: the menu ones ("menu", romfs/Audio/DriverMenu/MenuDriver_*.bars)
    first, then the in-race ones ("race", romfs/Audio/Driver/Driver_*.bars), each sorted by name. The order is fixed so
    a sound can be named by its place in it (see Api.get_voice_clips)."""
    found = {"menu": [], "race": []}
    for dirpath, dirnames, _files in os.walk(unit):
        romfs = [d for d in dirnames if d.lower() == "romfs"]
        if not romfs:
            continue
        dirnames[:] = []
        base = Path(dirpath) / romfs[0]
        for parts, prefix, key in ((("Audio", "DriverMenu"), "menudriver_", "menu"), (("Audio", "Driver"), "driver_", "race")):
            d = base
            for part in parts:
                d = _ci_child(d, part)
                if d is None:
                    break
            if d is not None:
                found[key] += [f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".bars" and f.name.lower().startswith(prefix)]
    return [(k, f) for k in ("menu", "race") for f in sorted(found[k], key=lambda p: (p.parent.as_posix().lower(), p.name.lower()))]


def unit_voice(unit: Path) -> dict:
    """{"race": bool, "menu": bool}: whether a mod unit ships character voice files - the in-race ones
    (romfs/Audio/Driver/Driver_<name>.bars) and the menu ones (romfs/Audio/DriverMenu/MenuDriver_<name>.bars).
    Only that they are there: a file that is an untouched copy of the game's own can't be told from a new voice
    without decoding the audio."""
    found = {"race": False, "menu": False}
    for dirpath, dirnames, _files in os.walk(unit):
        romfs = [d for d in dirnames if d.lower() == "romfs"]
        if not romfs:
            continue
        dirnames[:] = []
        base = Path(dirpath) / romfs[0]
        for parts, prefix, key in ((("Audio", "Driver"), "driver_", "race"), (("Audio", "DriverMenu"), "menudriver_", "menu")):
            d = base
            for part in parts:
                d = _ci_child(d, part)
                if d is None:
                    break
            if d is not None and any(f.is_file() and f.suffix.lower() == ".bars" and f.name.lower().startswith(prefix)
                                     for f in d.iterdir()):
                found[key] = True
    return found


def unit_parts(unit: Path) -> list:
    """What a mod unit replaces, in words for the character card's mod rows:
    "Character" (its model), "Kart", "Wheels", "Glider", "Voice" (voice files)."""
    out = []
    if unit_has_driver_model(unit):
        out.append("Character")
    ids = find_vehicle_part_ids(unit)
    for kind, label in (("Body", "Kart"), ("Tire", "Wheels"), ("Wing", "Glider")):
        if ids[kind]:
            out.append(label)
    if any(unit_voice(unit).values()):
        out.append("Voice")
    return out


def find_course_music_slugs(folder: Path) -> set:
    """Collects every course music id a downloaded course mod's bundled BGM
    files reference. Same cross-check role as find_course_slot_names(), just
    for roster.json's "music" field instead of "internal" - a mod
    with no bundled music at all (very common - most only touch geometry)
    returns an empty set, which the caller treats as "nothing to check", not
    a mismatch."""
    slugs = set()
    for dirpath, _dirnames, filenames in os.walk(folder):
        for name in filenames:
            m = _COURSE_BGM_RE.search(name)
            if m:
                slugs.add(m.group(1).upper())
    return slugs


# GameBanana character mods very commonly ship a companion "ui-<character>"
# file alongside the actual romfs mod: a raw dump of common.sarc/menu.sarc
# (the kart-select icon textures), meant to be hand-injected with a tool like
# Switch Toolbox - not a folder this app can merge on its own. It has no
# romfs at all, but is recognizable by the same top-level folder names those
# SARCs always extract to.
UI_ASSET_DIRNAMES = {"common", "menu"}


def looks_like_ui_assets(folder: Path) -> bool:
    # Checked anywhere in the tree, not just the top level - see the same
    # note on looks_like_missing_romfs_wrapper() below; these SARC dump
    # folders are sometimes wrapped in a mod-name folder of their own too.
    # A "Menu" / "Common" folder inside UI/cmn/ is not such a dump: that is
    # where the game itself keeps its loose menu textures (a course's
    # CoursePict picture, say), so a romfs mod that shipped UI/cmn/Menu/...
    # without its romfs/ around it is a missing wrapper, not a UI dump.
    for dirpath, dirnames, _filenames in os.walk(folder):
        if Path(dirpath).name.lower() == "cmn":
            continue
        if {d.lower() for d in dirnames} & UI_ASSET_DIRNAMES:
            return True
    return False


# UI-category downloads (the "UI" simple category) that aren't romfs mods are
# overwhelmingly icon/texture art or a packed .sarc replacement - PNG icon
# sets (Booster Icon Pass++, Pac-Man/Sonic icons), a loading screen's
# common.sarc - rather than the raw common/menu dump looks_like_ui_assets()
# was built to spot. Same handling either way: not mergeable, needs a manual
# tool (Switch Toolbox) - so they get the same "ui_assets" status and show up
# in the UI Icon Worklist. Only applied to the UI category (see
# _download_and_extract_one) - a PNG in, say, a vehicle download means nothing
# by itself - and deliberately excludes .jpg/.psd so non-game things like a
# Home-menu icon (config.ini + icon.jpg) or source art stay "needs manual fix".
UI_ART_EXTS = {".png", ".tga", ".dds", ".bntx", ".bftex", ".sarc", ".szs"}


def looks_like_ui_art(folder: Path) -> bool:
    for _dirpath, _dirnames, filenames in os.walk(folder):
        if any(Path(f).suffix.lower() in UI_ART_EXTS for f in filenames):
            return True
    return False


# The other common no-romfs packaging mistake: some modders zip up their
# Driver/DriverTex/Audio/Kart/... folders directly, skipping the romfs/
# wrapper those need to actually be a romfs mod. Unlike looks_like_ui_assets
# (content that genuinely isn't a romfs mod), this content IS a normal mod -
# it's one folder-move away from working, so it gets its own status with a
# specific fix instruction rather than the generic "needs manual fix".
#
# "racecommon" is the game-wide shared-data folder (AI tables, item models,
# ...) - real Mechanics mods (e.g. AI-difficulty tweaks) ship it bare as
# "RaceCommon/AI/*.byaml" with no romfs/ around it. Like the others here it's
# a distinctive romfs top-level name, never a mod author's own folder name.
MISSING_ROMFS_WRAPPER_DIRNAMES = {
    "driver", "drivertex", "driverparts", "audio", "kart", "karttex", "kartparts",
    "racecommon",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list:
    return _WORD_RE.findall(text.lower())


def flag_cross_character_files(files, current_character, roster):
    """Sets an "other_character_hint" key on each file dict when its filename
    looks like it's built for a DIFFERENT roster character than the one
    it's being viewed/tracked under. GameBanana mods very commonly bundle
    several characters' variants in one listing (e.g.
    "king_dedede_star_allies_over_morton_v3.7z" sitting right next to the
    "over_wario" file in the same mod) - downloading the wrong one because
    the file list gives no hint happened repeatedly during a real batch run.
    This is a soft hint, not a filter - nothing is hidden or blocked, just
    flagged so a human can double-check before downloading.

    Only trusts a character name found immediately after an "over" token
    (i.e. "..._over_<character>_..."), which is the actual, consistent
    naming convention behind every real multi-character file seen so far -
    matching a character's name anywhere in the filename is too loose in
    practice: "wart_mario_k8dx_by_orbots" contains "mario" only as part of
    "Mario Kart 8 Deluxe", not a reference to the character, and a bare
    substring/anywhere match flagged it as likely-Mario every time, drowning
    out the real over_isabelle/over_morton signal in the same mod. Roster
    entries whose tokens are a subset of the current character's own tokens
    are skipped (e.g. viewing "Baby Mario", "over_mario" is expected, not a
    hint that it's actually meant for "Mario")."""
    current_tokens = set(_tokenize(current_character))
    candidates = []
    for name in roster:
        if name == current_character:
            continue
        tokens = _tokenize(name)
        if not tokens or set(tokens) <= current_tokens:
            continue
        candidates.append((name, tokens))

    for f in files:
        name_tokens = _tokenize(Path(f["name"]).stem)
        hint = None
        if "over" in name_tokens:
            after = name_tokens[name_tokens.index("over") + 1:]
            for other_name, other_tokens in candidates:
                if after[:len(other_tokens)] == other_tokens:
                    hint = other_name
                    break
        f["other_character_hint"] = hint
    return files


def looks_like_missing_romfs_wrapper(folder: Path) -> bool:
    # Checked anywhere in the tree, not just the top level - these folders
    # are just as often one level down, wrapped in a mod-name folder of
    # their own (e.g. "<mod>/Driver/..." rather than "Driver/..." directly),
    # and this is only ever called after find_mod_units() already confirmed
    # there's no "romfs" anywhere in the tree, so a Driver/Kart/Audio/...
    # folder anywhere is a reliable signal regardless of depth.
    for _dirpath, dirnames, _filenames in os.walk(folder):
        if {d.lower() for d in dirnames} & MISSING_ROMFS_WRAPPER_DIRNAMES:
            return True
    return False


def fix_missing_romfs_wrapper(folder: Path) -> bool:
    """Auto-fixes the missing-romfs-wrapper packaging mistake in place: for
    every directory anywhere in the tree whose direct children include
    Driver/DriverTex/Audio/Kart/... (i.e. exactly the folders a romfs/ is
    supposed to contain), creates a "romfs" subfolder there and moves just
    those matching children into it - leaving anything else in that
    directory (a readme, a license file, ...) untouched. There's nothing
    ambiguous about where romfs/ belongs once you've found Driver/Kart/etc.,
    so this is applied automatically rather than just telling the user
    where to look. Returns True if anything was moved."""
    # Snapshot every site first - moving folders while os.walk is still
    # iterating the same tree can make it skip or double-visit directories.
    # Stops descending into a matched site (dirnames[:] = []), same as
    # find_mod_units() - a real romfs Driver/ can itself contain an unrelated
    # nested "Driver" folder (audio driver sound banks, not a 3D model
    # folder), which would otherwise get mistaken for a second wrapper site
    # one level inside the first one already being fixed.
    sites = []
    for dirpath, dirnames, _filenames in os.walk(folder):
        matches = [d for d in dirnames if d.lower() in MISSING_ROMFS_WRAPPER_DIRNAMES]
        if matches:
            sites.append((Path(dirpath), matches))
            dirnames[:] = []

    fixed_any = False
    for site_dir, matches in sites:
        romfs_dir = site_dir / "romfs"
        romfs_dir.mkdir(exist_ok=True)
        # A course pack often ships Audio/ (a music swap) AND Course/ + MapObj/ bare side by
        # side: Course/MapObj alone aren't a safe signal (see COURSE_WRAPPER_DIRNAMES), but
        # next to a folder that is one, they belong in the same romfs - leaving them behind
        # would stage the music and silently drop the track itself.
        # The same goes for a UI/ that holds the game's own cmn/ folder (a course's CoursePict picture, say): alone it could be
        # a modder's own folder, next to Audio/ or Driver/ it is the mod's UI textures.
        matches = matches + [d.name for d in site_dir.iterdir()
                             if d.is_dir() and d.name not in matches
                             and (d.name.lower() in COURSE_WRAPPER_DIRNAMES or (d.name.lower() == "ui" and _ci_child(d, "cmn") is not None))]
        for dirname in matches:
            src = site_dir / dirname
            dest = romfs_dir / dirname
            if src.is_dir() and not dest.exists():
                shutil.move(str(src), str(dest))
                fixed_any = True
    return fixed_any


# Course mods have their own version of the missing-romfs-wrapper mistake:
# some packs ship "Course/" (and sometimes a sibling "MapObj/", for a
# skybox/background addon) sitting bare at the top level instead of inside
# romfs/. Unlike MISSING_ROMFS_WRAPPER_DIRNAMES above, "Course" alone isn't a
# safe unconditional signal - a real course-slot folder can itself be named
# "Course" one level down (see find_bare_course_slot_sites below), so this
# only fires when a site's direct children are ALL drawn from this small,
# known-romfs set (never a partial match) - that guarantees nothing gets left
# behind unwrapped next to what did get moved.
COURSE_WRAPPER_DIRNAMES = {"course", "mapobj"}


def looks_like_bare_course_wrapper(folder: Path) -> bool:
    for _dirpath, dirnames, _filenames in os.walk(folder):
        lower = {d.lower() for d in dirnames}
        if lower and lower <= COURSE_WRAPPER_DIRNAMES:
            return True
    return False


def fix_bare_course_wrapper(folder: Path) -> bool:
    """All-or-nothing counterpart to fix_missing_romfs_wrapper(): only wraps
    a site when every direct child directory is recognized, so a course mod
    that also bundles something unrecognized alongside Course/MapObj is left
    for manual review rather than silently merging half of it."""
    sites = []
    for dirpath, dirnames, _filenames in os.walk(folder):
        lower = {d.lower() for d in dirnames}
        if lower and lower <= COURSE_WRAPPER_DIRNAMES:
            sites.append((Path(dirpath), list(dirnames)))
            dirnames[:] = []
    fixed_any = False
    for site_dir, matches in sites:
        romfs_dir = site_dir / "romfs"
        romfs_dir.mkdir(exist_ok=True)
        for dirname in matches:
            src = site_dir / dirname
            dest = romfs_dir / dirname
            if src.is_dir() and not dest.exists():
                shutil.move(str(src), str(dest))
                fixed_any = True
    return fixed_any


# An even barer course-mod packaging mistake: just the innermost course-slot
# folder itself (e.g. "Cnsw_26/", holding course_model.szs, course_muunt.byaml,
# ...) with no "Course/" wrapper and no "romfs/" - the archive was zipped
# starting one level too deep. The slot folder's own name is exactly the
# internal course id, so where it belongs (romfs/Course/<name>/) is
# unambiguous - unlike a mod that drops course_*.* files bare at the archive
# root with no named folder at all, which gives up that id entirely (the "root
# itself" guard below): fix_loose_course_files() takes the id from the course
# the download was made for instead.
_COURSE_SLOT_FILE_RE = re.compile(r"^course", re.IGNORECASE)


def find_bare_course_slot_sites(folder: Path):
    sites = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirpath = Path(dirpath)
        if dirpath == folder:
            continue  # the archive root has no course-id to take the name from
        if filenames and not dirnames and all(_COURSE_SLOT_FILE_RE.match(f) for f in filenames):
            sites.append(dirpath)
            dirnames[:] = []
    return sites


def fix_bare_course_slot(folder: Path) -> bool:
    fixed_any = False
    for site in find_bare_course_slot_sites(folder):
        dest_parent = site.parent / "romfs" / "Course"
        dest_parent.mkdir(parents=True, exist_ok=True)
        dest = dest_parent / site.name
        if not dest.exists():
            shutil.move(str(site), str(dest))
            fixed_any = True
    return fixed_any


# ...and the barest of all: a course's own files with NO folder named for the course - "Retextured" mods that ship only
# course_model.szs (and a README) at the archive root, or inside a wrapper named for the mod. That gives up the internal id, but the
# download was made from a known course's page (roster.json says "Wii Grumble Volcano" is Course/Wii_..., one id), so the id is known
# from the course, not from the archive. Only where the course has exactly ONE id (Animal Crossing's four seasons can't be told
# apart), and all-or-nothing per folder: every file must be one a course slot holds (course*.* files and their .bars/.barslist,
# *_muunt.byaml, enemy_path*.bin), plus docs and pictures, and at least one of course_model.szs / course_kcl.szs /
# course_muunt.byaml / course.bgenv / course_maptexture.bntx must be there. A folder named for an id the game has is left to
# fix_bare_course_slot(), which already knows what to do with it.
_LOOSE_COURSE_CORE_FILES = {"course_model.szs", "course_kcl.szs", "course_muunt.byaml", "course.bgenv", "course_maptexture.bntx"}
_LOOSE_COURSE_FILE_RE = re.compile(r"^(course.*|.*_muunt\.byaml|enemy_path.*\.bin)$", re.IGNORECASE)


def find_loose_course_sites(folder: Path, known_slots=()):
    """[dir, ...] - every folder in the tree holding a course's files loose (no romfs/, no subfolders, nothing this doesn't
    recognise) that isn't itself named for one of `known_slots` (the game's internal course ids)."""
    known = {s.lower() for s in known_slots}
    sites = []
    for dirpath, dirnames, filenames in os.walk(folder):
        if any(d.lower() == "romfs" for d in dirnames):
            dirnames[:] = []
            continue
        if dirnames or Path(dirpath).name.lower() in known:
            continue
        lower = [f.lower() for f in filenames]
        if not _LOOSE_COURSE_CORE_FILES & set(lower):
            continue
        if all(_LOOSE_COURSE_FILE_RE.match(f) or Path(f).suffix.lower() in _ITEM_IGNORABLE_EXTS or f == ".DS_Store" for f in filenames):
            sites.append(Path(dirpath))
    return sites


def fix_loose_course_files(folder: Path, slot: str, known_slots=()) -> bool:
    """Moves each loose course folder's course files into romfs/Course/<slot>/ beside them (docs and pictures stay where
    they are). `slot` is the internal id of the course the download is for."""
    fixed_any = False
    for site in find_loose_course_sites(folder, known_slots):
        dest = site / "romfs" / "Course" / slot
        dest.mkdir(parents=True, exist_ok=True)
        for f in list(site.iterdir()):
            if f.is_file() and _LOOSE_COURSE_FILE_RE.match(f.name) and not (dest / f.name).exists():
                shutil.move(str(f), str(dest / f.name))
                fixed_any = True
    return fixed_any


# Item mods have their own, barer version of the same mistake: the author zips
# just the replacement item's loose files (e.g. Diamond Sword ships
# "Boomerang.bars", "Boomerang.barslist" and "ItemBoomerang.bfres" with no
# folders around them at all). Every real item mod checked puts these at
# romfs/RaceCommon/Item/<bfres name>/ - the model's own filename is exactly
# its folder name (ItemBoomerang.bfres -> ItemBoomerang/, ItemBoomerang_FX.bfres
# -> ItemBoomerang_FX/, DL_ItemRupee.bfres -> DL_ItemRupee/) - so where the
# files belong is unambiguous whenever a folder holds exactly one such model.
# Deliberately all-or-nothing, like fix_bare_course_wrapper(): a folder with
# several item models (the .bars/.barslist then can't be told apart), any
# subfolders, or any file this doesn't recognize is left for manual review
# rather than half-merged. ItemBox.bfres is the one known exception - it lives
# at RaceCommon/ItemBox/, not under Item/ - so it's never guessed at.
_ITEM_BFRES_RE = re.compile(r"^(?:DL_)?Item[A-Za-z0-9_]*\.bfres$", re.IGNORECASE)
_ITEM_FILE_EXTS = {".bfres", ".bars", ".barslist"}
_ITEM_IGNORABLE_EXTS = {".txt", ".md", ".rtf", ".pdf", ".url", ".html", ".htm",
                        ".png", ".jpg", ".jpeg", ".gif"}


def find_loose_item_sites(folder: Path):
    """Returns [(dir, model_stem, [filenames_to_move]), ...] for every folder
    in the tree that qualifies for fix_loose_item_files()."""
    sites = []
    for dirpath, dirnames, filenames in os.walk(folder):
        if any(d.lower() == "romfs" for d in dirnames):
            dirnames[:] = []  # already a real mod - not this mistake
            continue
        if dirnames:
            continue
        models = [f for f in filenames if _ITEM_BFRES_RE.match(f)]
        if len(models) != 1:
            continue
        stem = Path(models[0]).stem
        if stem.lower().startswith("itembox"):
            continue
        suffixes = {f: Path(f).suffix.lower() for f in filenames}
        if any(s not in _ITEM_FILE_EXTS | _ITEM_IGNORABLE_EXTS for s in suffixes.values()):
            continue
        movable = [f for f, s in suffixes.items() if s in _ITEM_FILE_EXTS]
        sites.append((Path(dirpath), stem, movable))
    return sites


def fix_loose_item_files(folder: Path) -> bool:
    fixed_any = False
    for site_dir, stem, movable in find_loose_item_sites(folder):
        dest_dir = site_dir / "romfs" / "RaceCommon" / "Item" / stem
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in movable:
            dest = dest_dir / name
            if not dest.exists():
                shutil.move(str(site_dir / name), str(dest))
                fixed_any = True
    return fixed_any


# --- vehicle parts (bodies / tires / gliders) -------------------------------
# All three live as .szs files under romfs/Kart/: the model is
# Kart/Body/Body<K|B|V>_<id>.szs (kart/bike/atv), Kart/Tire/Tire<K|B|T>_<id>.szs
# or Kart/Wing/Wing_<id>.szs, with per-character texture variants in
# Kart/BodyTex|WingTex (<part>_<char>_Alb.szs) and Kart/Emblem. Roughly half of
# the body mods surveyed on GameBanana ship these loose at the archive root with
# no folders at all - the same "author zipped one level too deep" mistake as the
# loose item files above - so where each belongs is fully determined by its
# own file name.
_KART_PART_DIRS = (
    (re.compile(r"^Body[KBV]_[A-Za-z0-9]+\.szs$", re.IGNORECASE), "Body"),
    (re.compile(r"^Body[KBV]_[A-Za-z0-9]+_[A-Za-z0-9]+_Alb\.szs$", re.IGNORECASE), "BodyTex"),
    (re.compile(r"^Tire[KBT]_[A-Za-z0-9]+\.szs$", re.IGNORECASE), "Tire"),
    (re.compile(r"^Wing_[A-Za-z0-9]+\.szs$", re.IGNORECASE), "Wing"),
    (re.compile(r"^Wing_[A-Za-z0-9]+_[A-Za-z0-9]+_Alb\.szs$", re.IGNORECASE), "WingTex"),
    (re.compile(r"^Emblem_[A-Za-z0-9]+\.szs$", re.IGNORECASE), "Emblem"),
)


def _kart_part_subdir(filename: str):
    for pattern, subdir in _KART_PART_DIRS:
        if pattern.match(filename):
            return subdir
    return None


def find_loose_kart_part_sites(folder: Path):
    """Returns [(dir, [(filename, romfs/Kart subfolder), ...]), ...] for every
    folder holding loose vehicle-part .szs files and nothing this doesn't
    recognize (docs/preview images are ignored) - all-or-nothing, like
    find_loose_item_sites(), so a folder with anything unfamiliar in it is left
    for manual review instead of being half-merged."""
    sites = []
    for dirpath, dirnames, filenames in os.walk(folder):
        if any(d.lower() == "romfs" for d in dirnames):
            dirnames[:] = []  # already a real mod - not this mistake
            continue
        if dirnames:
            continue
        parts = []
        clean = True
        for f in filenames:
            subdir = _kart_part_subdir(f)
            if subdir:
                parts.append((f, subdir))
            elif Path(f).suffix.lower() not in _ITEM_IGNORABLE_EXTS:
                clean = False
                break
        if clean and parts:
            sites.append((Path(dirpath), parts))
    return sites


def fix_loose_kart_parts(folder: Path) -> bool:
    fixed_any = False
    for site_dir, parts in find_loose_kart_part_sites(folder):
        for name, subdir in parts:
            dest_dir = site_dir / "romfs" / "Kart" / subdir
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if not dest.exists():
                shutil.move(str(site_dir / name), str(dest))
                fixed_any = True
    return fixed_any


# --- a character's own files (model, voice, menu sound), loose ---------------
# Some character mods (a Baby Rosalina "Vanellope" swap, for one) are zipped one folder too deep with no romfs/ or
# Driver/Audio folders either: just <Slot>.szs, Driver_<Slot>.bars and MenuDriver_<Slot>.bars side by side. Like the item
# and vehicle-part files above, each file's name says exactly where it goes - the slot part has to be one the game
# really has (DRIVER_SLOTS) - so this is safe to fix by name. All-or-nothing per folder, like the others.
_LOOSE_DRIVER_FILE_RES = (
    (re.compile(r"^Driver_(.+)\.bars$", re.IGNORECASE), ("Audio", "Driver")),
    (re.compile(r"^MenuDriver_(.+)\.bars$", re.IGNORECASE), ("Audio", "DriverMenu")),
    (re.compile(r"^(.+)\.szs$", re.IGNORECASE), ("Driver",)),
)


def _loose_character_file_dest(filename: str):
    """The romfs-relative folder parts a loose character file belongs in (("Audio", "Driver"), ("Kart", "Emblem"), ...), or None
    when the name isn't one of a character's own files."""
    for pattern, parts in _LOOSE_DRIVER_FILE_RES:
        m = pattern.match(filename)
        if m:
            if re.sub(r"suit$", "", m.group(1).lower()) in _DRIVER_SLOTS_LOWER:
                return parts
    subdir = _kart_part_subdir(filename)
    return ("Kart", subdir) if subdir == "Emblem" else None


def find_loose_character_sites(folder: Path):
    """[(dir, [(filename, romfs-relative parts), ...]), ...] for every folder holding loose character files (at least one
    model or voice file) and nothing else this doesn't recognise - docs/preview images are ignored."""
    sites = []
    for dirpath, dirnames, filenames in os.walk(folder):
        if any(d.lower() == "romfs" for d in dirnames):
            dirnames[:] = []
            continue
        if dirnames:
            continue
        files, clean = [], True
        for f in filenames:
            parts = _loose_character_file_dest(f)
            if parts:
                files.append((f, parts))
            elif Path(f).suffix.lower() not in _ITEM_IGNORABLE_EXTS and f != ".DS_Store":
                clean = False
                break
        if clean and any(parts[0] in ("Driver", "Audio") for _f, parts in files):
            sites.append((Path(dirpath), files))
    return sites


def fix_loose_character_files(folder: Path) -> bool:
    fixed_any = False
    for site_dir, files in find_loose_character_sites(folder):
        for name, parts in files:
            dest_dir = site_dir.joinpath("romfs", *parts)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if not dest.exists():
                shutil.move(str(site_dir / name), str(dest))
                fixed_any = True
    return fixed_any


_PART_FILE_RES = (
    ("Body", re.compile(r"^(Body[KBV]_[A-Za-z0-9]+)\.szs$", re.IGNORECASE)),
    ("Tire", re.compile(r"^Tire[KBT]_([A-Za-z0-9]+)\.szs$", re.IGNORECASE)),
    ("Wing", re.compile(r"^(Wing_[A-Za-z0-9]+)\.szs$", re.IGNORECASE)),
)


def find_vehicle_part_ids(folder: Path) -> dict:
    """{"Body": {"BodyK_Cat", ...}, "Tire": {"Tire_Std", ...}, "Wing": {...}}
    - the main model files a downloaded mod actually ships, anywhere in its
    tree, keyed the same way roster.json's vehicle-part "internal" ids are compared
    (see Api._vehicle_expected_key). Texture variants aren't counted."""
    found = {"Body": set(), "Tire": set(), "Wing": set()}
    for _dirpath, _dirnames, filenames in os.walk(folder):
        for f in filenames:
            for kind, regex in _PART_FILE_RES:
                m = regex.match(f)
                if m:
                    key = m.group(1) if kind != "Tire" else f"Tire_{m.group(1)}"
                    found[kind].add(key)
    return found


# Target matching for vehicle-part mods: GameBanana has no per-vehicle
# subcategory (a whole section's mods share one category), and mod titles
# usually name the NEW model rather than the replaced part - so a mod's
# target has to be read from its description. Measured against real
# archives, "goes over / replaces <name>" phrases agree with the files
# actually shipped ~98% of the time when present, an explicit internal id
# (BodyK_Cat, Wing_Pap, TireK_Zst) is stronger still, and a bare mention in
# the title is a weak hint. Bare single common words (Standard, Metal, Wood,
# Comet, ...) are too generic to count as a plain mention - they only count
# after an "over/replaces" phrase or, for tires, followed by tire/wheel.
_GENERIC_PART_WORDS = {
    "standard", "monster", "roller", "slim", "slick", "metal", "button", "sponge", "wood",
    "cushion", "leaf", "leaf tires", "ancient", "gold", "comet", "parachute", "parasol",
    "triforce",
    # items (roster.json's "items"): single words that turn up in any description
    "star", "bell", "coin", "killer", "bomb", "ghost", "squid", "bullet",
}
_OVER_PREFIX = (
    r"(?:\bover\b|\breplaces\b|\breplace\b|\breplacing\b|\binstead of\b|\bin place of\b|"
    r"\bswaps? out\b|\bon top of\b)\s+(?:the\s+|original\s+|default\s+|vanilla\s+|base\s+|mkd?8d?\s+){0,3}"
)


def _part_name_variants(name: str):
    """A name plus the spellings mods actually use for it (with/without the
    generic noun, punctuation-insensitive)."""
    variants = {name}
    for suffix in (" Tires", " Tire"):
        if name.endswith(suffix):
            variants.add(name[: -len(suffix)])
    return {v for v in variants if v}


def _name_regex(name: str) -> str:
    # Spaces/hyphens interchangeable ("Off-Road"/"Off Road"/"Offroad"), dots optional.
    parts = re.split(r"[\s\-.]+", name.strip())
    return r"[\s\-.]*".join(re.escape(p) for p in parts if p)


def match_vehicle_targets(section: str, roster_items, title: str, description: str):
    """Best-guess target part(s) for a mod within one section. Returns
    [(item name, score)] for the top-scoring item(s) only (an empty list when
    nothing matched): score 3 = an internal id in the text, 2 = an
    "over/replaces <name>" phrase, 1 = a plain mention (distinctive names
    only; for tires, a name followed by tire/wheel). A longer name that
    already matched claims its text first, so "Blue Standard" never also
    counts as "Standard"."""
    text = f"{title or ''}\n{description or ''}"
    scores = {}
    candidates = []  # (item name, variant string, item)
    for item in roster_items:
        for variant in _part_name_variants(item["name"]) | set(item.get("aliases", [])):
            candidates.append((item["name"], variant, item))
    candidates.sort(key=lambda c: -len(c[1]))
    working = text
    for item in roster_items:
        internal = item.get("internal")
        if not internal:
            continue
        if section == "wheels":
            id_re = rf"\bTire[KBT]_{re.escape(internal)}\b"
        else:
            id_re = rf"\b{re.escape(internal)}\b"
        if re.search(id_re, working, re.IGNORECASE):
            scores[item["name"]] = max(scores.get(item["name"], 0), 3)
    for item_name, variant, _item in candidates:
        rx = _name_regex(variant)
        generic = variant.lower() in _GENERIC_PART_WORDS
        best = 0
        over = re.compile(_OVER_PREFIX + rx + r"(?![A-Za-z0-9])", re.IGNORECASE)
        if over.search(working):
            best = 2
            working = over.sub(lambda m: " " * len(m.group(0)), working)
        else:
            if section == "wheels":
                plain = re.compile(rf"(?<![A-Za-z0-9]){rx}\s+(?:tires?|tyres?|wheels?)\b", re.IGNORECASE)
            elif generic:
                plain = None
            else:
                plain = re.compile(rf"(?<![A-Za-z0-9]){rx}(?![A-Za-z0-9])", re.IGNORECASE)
            if plain and plain.search(working):
                best = 1
                working = plain.sub(lambda m: " " * len(m.group(0)), working)
        if best:
            scores[item_name] = max(scores.get(item_name, 0), best)
    if not scores:
        return []
    top = max(scores.values())
    return [(n, s) for n, s in scores.items() if s == top]


# Per-file targets for a vehicle mod. Plenty of mods bundle several files that
# each belong under a DIFFERENT part - a separate download per glider/kart
# ("Streetle Ver" / "Prancer Ver"), or a companion tires file next to the
# body - and only the file's own name/caption says which. This reads those:
# the file's name (GameBanana's random upload suffix and separators removed) and
# caption first, then - for a file that names nothing itself - the mod's own
# text, restricted to the kind of part the file is (a "tires" file can only be a
# wheels part, so "...tires replace Wood" in the mod description resolves it).
_FILE_TIRE_RE = re.compile(r"\b(?:tires?|tyres?|wheels?)\b", re.IGNORECASE)
_FILE_GLIDER_RE = re.compile(r"\b(?:gliders?|wings?|kites?|parafoil|parachute|parasol)\b", re.IGNORECASE)


def _file_match_text(f) -> str:
    stem = re.sub(r"\.(?:zip|rar|7z)$", "", f.get("name") or "", flags=re.IGNORECASE)
    stem = re.sub(r"[_\-]+", " ", stem)
    # GameBanana appends a random 5-hex-digit suffix to many upload names
    # ("tires_5222d.zip"); requiring a digit keeps real words like "added".
    stem = re.sub(r"\b(?=[0-9a-f]*\d)[0-9a-f]{5}\b", " ", stem, flags=re.IGNORECASE)
    return f"{stem} {f.get('description') or ''}".strip()


# An optional extra shipped next to the real mod - a "ui-..." icon dump or an
# icon pack - rather than the mod itself. These are UI art the app can't merge
# (it lands as "UI icons only" and is listed in the UI Icon Worklist), so they
# never make a good default choice.
_COMPANION_NAME_RE = re.compile(r"^ui[-_ ]|\bicons?\b", re.IGNORECASE)
_COMPANION_DESC_RE = re.compile(r"\bicons?\b", re.IGNORECASE)


def is_companion_file(f) -> bool:
    return bool(
        _COMPANION_NAME_RE.search((f.get("name") or "").strip())
        or _COMPANION_DESC_RE.search(f.get("description") or "")
    )


def suggest_file_targets(files, title, description, roster, mod_section=None):
    """One dict per file, in order: {file_id, section, part, strength, source,
    candidates, default_include}. `source` is "file" (the file's own name/caption
    names the part), "mod" (only the mod's text does) or None (no idea);
    `part` is None when nothing matched or several parts tied.

    default_include picks a sensible starting set: every file that names its
    own part, plus - for files that only inherit the mod-level target - just the
    FIRST one per part (a second file for the same part is normally an
    alternative variant, e.g. a different logo, not something to download too)."""
    out = []
    for f in files:
        text = _file_match_text(f)
        if _FILE_TIRE_RE.search(text):
            sections = ["wheels"]
        elif _FILE_GLIDER_RE.search(text):
            sections = ["gliders"]
        else:
            sections = [mod_section] if mod_section else list(VEHICLE_SECTIONS)

        def best_for(title_text, desc_text):
            best = []
            for sec in sections:
                for name, score in match_vehicle_targets(sec, roster[sec], title_text, desc_text):
                    best.append((score, sec, name))
            if not best:
                return None, []
            top = max(b[0] for b in best)
            tied = [b for b in best if b[0] == top]
            return top, tied

        source = "file"
        score, tied = best_for("", text)
        if not tied:
            source = "mod"
            score, tied = best_for(title, description)
        entry = {"file_id": f["file_id"], "section": None, "part": None, "strength": 0,
                 "source": None, "candidates": [], "default_include": False,
                 "companion": is_companion_file(f)}
        if tied:
            entry["source"] = source
            entry["strength"] = score
            entry["candidates"] = [t[2] for t in tied]
            if len(tied) == 1:
                entry["section"], entry["part"] = tied[0][1], tied[0][2]
        out.append(entry)

    # The real mod files decide first; a companion (icons) file is only a
    # default when nothing else covers its part.
    real = [e for e in out if not e["companion"]]
    covered = {e["part"] for e in real if e["part"] and e["source"] == "file"}
    for e in real:
        if not e["part"]:
            continue
        if e["source"] == "file":
            e["default_include"] = True
        elif e["part"] not in covered:
            e["default_include"] = True
            covered.add(e["part"])
    for e in out:
        if e["companion"] and e["part"] and e["part"] not in covered:
            e["default_include"] = True
            covered.add(e["part"])
    return out


# The sneakiest course-packaging mistake found so far: a mod ships a real
# "romfs/" folder (so find_mod_units() happily calls it a valid, complete
# unit) that turns out to hold nothing but an author's readme - while the
# actual Course/MapObj content sits bare right next to it, unwrapped, and
# silently never gets merged. (Real example: an "Audio/readme.txt" inside
# romfs/ telling the user to go patch BGM.bars by hand, sitting next to a
# perfectly good bare Course/<slot>/ that never got picked up.) Since a
# romfs/ already exists here, this doesn't create a new one - it folds the
# stray Course/MapObj siblings into the one that's already there.
def find_stray_course_content_sites(folder: Path):
    sites = []
    for dirpath, dirnames, _filenames in os.walk(folder):
        lower = {d.lower(): d for d in dirnames}
        if "romfs" not in lower:
            continue
        stray = [lower[name] for name in ("course", "mapobj") if name in lower]
        if stray:
            sites.append((Path(dirpath) / lower["romfs"], [Path(dirpath) / d for d in stray]))
    return sites


def fix_stray_course_content(folder: Path) -> bool:
    fixed_any = False
    for romfs_dir, stray_dirs in find_stray_course_content_sites(folder):
        for src in stray_dirs:
            dest = romfs_dir / src.name
            if src.is_dir() and not dest.exists():
                shutil.move(str(src), str(dest))
                fixed_any = True
    return fixed_any


# Some GameBanana archives ship pre-packaged as a ready-to-copy SD card tree
# ("atmosphere/contents/<title id>/romfs/...") rather than a bare romfs/ -
# this app reconstructs that exact path itself at merge/staging time from
# TITLE_ID, so a source archive shipping its own copy of it is pure noise:
# it only makes unit keys long and ugly (e.g.
# "Mod/atmosphere/contents/0100152000022000") for no benefit. The wrapper
# shows up inconsistently between mods though - sometimes the full
# "atmosphere/contents/<id>", sometimes just "contents/<id>", sometimes the
# id folder sitting bare with no wrapper folder at all - so stripping has to
# walk upward from the id folder consuming only the generic, known wrapper
# names, and stop the moment it hits a folder the mod author actually named
# something meaningful (a voice-pack folder, a color-variant name, ...).
#
# "titles" is Atmosphere's older name for "contents" (atmosphere/titles/<id>/),
# still common in older mods, so it's accepted in the same position.
_ATMOSPHERE_WRAPPER_NAMES = (("contents", "titles"), ("atmosphere",))


def find_atmosphere_wrapper_sites(folder: Path):
    """Finds every directory named exactly TITLE_ID anywhere in the tree.
    Returns [(title_id_dir, outermost_wrapper_dir), ...] - outermost_wrapper_dir
    is title_id_dir itself, or a "contents"/"titles"/"atmosphere" ancestor of it
    if those specific generic names are what's actually wrapping it here."""
    sites = []
    for dirpath, dirnames, _filenames in os.walk(folder):
        for d in dirnames:
            if d.lower() == TITLE_ID.lower():
                title_dir = Path(dirpath) / d
                outer = title_dir
                for expected in _ATMOSPHERE_WRAPPER_NAMES:
                    if outer.parent.name.lower() in expected:
                        outer = outer.parent
                    else:
                        break
                sites.append((title_dir, outer))
    return sites


_ATMOSPHERE_GENERIC_DIRS = {"contents", "titles", "atmosphere"}


def find_bare_atmosphere_sites(folder: Path):
    """The same packaging noise with the title-id folder missing altogether -
    e.g. atmosphere/titles/romfs/... (the author zipped the wrapper but left
    the id out). Returns [(dir_holding_romfs, outermost_wrapper_dir), ...]: a
    "contents"/"titles" folder that directly holds a romfs/ (or exefs/), plus
    whatever generic wrapper folders sit above it. Never looks inside a romfs/
    (a real mod's own data can contain any folder name)."""
    sites = []
    for dirpath, dirnames, _filenames in os.walk(folder):
        here = Path(dirpath)
        lower = {d.lower() for d in dirnames}
        if here != folder and here.name.lower() in ("contents", "titles") and lower & {"romfs", "exefs"}:
            outer = here
            while outer.parent != folder and outer.parent.name.lower() in _ATMOSPHERE_GENERIC_DIRS:
                outer = outer.parent
            sites.append((here, outer))
        dirnames[:] = [d for d in dirnames if d.lower() != "romfs"]
    return sites


def fix_atmosphere_wrapper(folder: Path) -> bool:
    """Strips the atmosphere/contents/<TITLE_ID> packaging noise described
    above, in place. Moves the title-id folder's own children (romfs,
    possibly exefs/cheats/...) up to replace the wrapper, then removes the
    now-empty wrapper. Returns True if anything was moved."""
    fixed_any = False
    for title_dir, outer in find_atmosphere_wrapper_sites(folder):
        if not title_dir.is_dir():
            continue  # already handled as part of an earlier site
        dest_parent = outer.parent
        for child in list(title_dir.iterdir()):
            dest = dest_parent / child.name
            if not dest.exists():
                shutil.move(str(child), str(dest))
                fixed_any = True
        shutil.rmtree(outer, ignore_errors=True)
    # ...and the id-less variant (see find_bare_atmosphere_sites), which also
    # picks up whatever wrapper the id-based pass above just reduced to
    # atmosphere/titles/ by moving the id folder's children up one level.
    for here, outer in find_bare_atmosphere_sites(folder):
        if not here.is_dir():
            continue  # already handled as part of an earlier site
        dest_parent = outer.parent
        for child in list(here.iterdir()):
            dest = dest_parent / child.name
            if not dest.exists():
                shutil.move(str(child), str(dest))
                fixed_any = True
        shutil.rmtree(outer, ignore_errors=True)
    return fixed_any


def discover_mods(mod_downloads_root: Path):
    """Returns {category_name: [relative_unit_path, ...]} for every
    mods/extracted/<category>/ folder under mod_downloads_root."""
    categories = {}
    extracted_root = mod_downloads_root / MODS_DIRNAME / EXTRACTED_DIRNAME
    if not extracted_root.is_dir():
        return categories
    for child in sorted(extracted_root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            units = sorted(
                find_mod_units(child) + find_exefs_units(child), key=lambda p: str(p).lower()
            )
            if units:
                categories[child.name] = units
    return categories


def ui_icons_status_text(mod_root: Path):
    ui_icons_romfs = mod_root / "ui-icons" / "romfs"
    count = sum(1 for f in ui_icons_romfs.rglob("*") if f.is_file()) if ui_icons_romfs.is_dir() else 0
    if count:
        return f"Combined UI icons & text: {count} file(s) in ui-icons/romfs/ — always included, not a checkbox"
    return "Combined UI icons & text: none yet — built automatically the next time you commit, if any selected mod needs it"


# The game's internal "Driver" names (romfs/Driver/<name>.szs, and the voice/menu-sound
# files Audio/Driver/Driver_<name>.bars, Audio/DriverMenu/MenuDriver_<name>.bars) and the
# character each belongs to - checked against the mods downloaded for each character. The
# DrvChrNN ones follow the mods filed under Kamek, Petey Piranha, Wiggler, Birdo (DrvChr01: two
# separate Birdo mods ship Driver/DrvChr01.szs, one with the matching voice files), Peachette and
# Pauline - the Booster Course Pass's generic guest-slot scheme, also how DrvChr05/06 (Diddy Kong,
# Funky Kong) were filled in below. ("...Suit" - the bike/ATV outfit - is stripped before the lookup.)
#
# Every entry below (59 slot codes, 52 distinct character voices - all 52 roster characters - Link and Link (Breath of the Wild), Metal Mario
# and Gold Mario are two each) is confirmed byte-for-byte against a real MK8DX dump's
# Audio/Driver + Audio/DriverMenu folders (game_files.py's discover()/copy_both() will refuse a
# dump that doesn't have UI/cmn/common.sarc + menu.sarc + a message.sarc, so any dump that gets this
# far is the real thing) - not a guess or an asset-rip filename fit like the earlier research this
# replaced. Two things that research got wrong, corrected once a real dump was available: Mii isn't
# one slot per gender ("MiiM"/"MiiF" don't exist) - it's one per gender/hairstyle combo actually
# shipped (Mii_F01..Mii_F04, Mii_M01..Mii_M04, eight in total); Diddy Kong and Funky Kong's slots
# really are DrvChr05/DrvChr06, confirming the earlier asset-rip-based guess.
DRIVER_SLOTS = {
    "Mario": "Mario", "Luigi": "Luigi", "Peach": "Peach", "Daisy": "Daisy", "Rosetta": "Rosalina",
    "TanukiMario": "Tanooki Mario", "CatPeach": "Cat Peach", "Yoshi": "Yoshi", "Kinopio": "Toad",
    "Nokonoko": "Koopa Troopa", "Heyho": "Shy Guy", "Jugem": "Lakitu", "Kinopico": "Toadette",
    "BbMario": "Baby Mario", "BbLuigi": "Baby Luigi", "BbPeach": "Baby Peach", "BbDaisy": "Baby Daisy",
    "BbRosetta": "Baby Rosalina", "MetalMario": "Metal Mario", "MetalPeach": "Pink Gold Peach",
    "GoldMario": "Gold Mario", "Wario": "Wario", "Waluigi": "Waluigi", "DK": "Donkey Kong",
    "Koopa": "Bowser", "Karon": "Dry Bones", "KoopaJr": "Bowser Jr.", "KingTeresa": "King Boo",
    "HoneKoopa": "Dry Bowser", "Lemmy": "Lemmy", "Wendy": "Wendy", "Ludwig": "Ludwig", "Iggy": "Iggy",
    "Roy": "Roy", "Morton": "Morton", "SplatoonGirl": "Inkling Girl", "SplatoonBoy": "Inkling Boy",
    "Link": "Link", "LinkBotw": "Link (Breath of the Wild)", "AnimalBoyA": "Villager (Boy)", "AnimalGirlA": "Villager (Girl)",
    "DrvChr01": "Birdo", "DrvChr02": "Kamek", "DrvChr03": "Petey Piranha", "DrvChr04": "Wiggler", "DrvChr07": "Peachette",
    "DrvChr08": "Pauline", "Larry": "Larry", "Shizue": "Isabelle",
    "DrvChr05": "Diddy Kong", "DrvChr06": "Funky Kong",
    # Mii isn't one slot per gender - it's one per gender/hairstyle combo actually shipped in Audio/Driver
    # (confirmed against a real dump: Mii_F01..Mii_F04, Mii_M01..Mii_M04, no plain "MiiF"/"MiiM" files exist).
    "Mii_F01": "Mii", "Mii_F02": "Mii", "Mii_F03": "Mii", "Mii_F04": "Mii",
    "Mii_M01": "Mii", "Mii_M02": "Mii", "Mii_M03": "Mii", "Mii_M04": "Mii",
}


_DRIVER_SLOTS_LOWER = {k.lower(): v for k, v in DRIVER_SLOTS.items()}


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _ci_child(parent, name: str):
    if parent is None or not parent.is_dir():
        return None
    return next((c for c in parent.iterdir() if c.name.lower() == name.lower()), None)


def slot_characters(folder: Path) -> set:
    """The characters whose slots a mod folder writes to (Driver models, voices
    and menu sounds under any romfs/ in it), by the names DRIVER_SLOTS knows."""
    found = set()
    for dirpath, dirnames, _files in os.walk(folder):
        romfs = [d for d in dirnames if d.lower() == "romfs"]
        if not romfs:
            continue
        dirnames[:] = []
        base = Path(dirpath) / romfs[0]
        for parts, prefix, pattern in ((("Driver",), "", ".szs"), (("Audio", "Driver"), "Driver_", ".bars"),
                                       (("Audio", "DriverMenu"), "MenuDriver_", ".bars")):
            d = base
            for part in parts:
                d = _ci_child(d, part)
                if d is None:
                    break
            if d is None:
                continue
            for f in d.iterdir():
                if f.suffix.lower() == pattern and f.name.lower().startswith(prefix.lower()):
                    stem = re.sub(r"suit$", "", f.stem[len(prefix):].lower())
                    if stem in _DRIVER_SLOTS_LOWER:
                        found.add(_DRIVER_SLOTS_LOWER[stem])
    return found


class Api(VoiceEditMixin, ModNotesMixin):
    def __init__(self, mod_root: Path | None):
        # Leading underscore matters: pywebview's inject_pywebview() auto-exposes
        # JS API methods by recursing into every non-underscore-prefixed,
        # non-callable attribute of this object (to support nested API
        # namespaces). Without the underscore it would recurse straight into
        # the full pywebview Window/WebView2 object graph on every page load,
        # firing cross-thread COM property getters (get_CoreWebView2(),
        # get_AllowExternalDrop(), get_CanGoBack(), get_ZoomFactor(), ...) -
        # exactly the exception signature from the earlier freeze debugging.
        self._window = None  # set by main() right after webview.create_window()
        self._library = library_cache.LibraryCache()
        self._notes_lock = threading.RLock()   # (the notes and flags on mods: see mod_notes.py)
        self._state_lock = threading.RLock()   # (every read-modify-write of the ticked mods happens under it)
        self._root_epoch = ""                   # (names the folder a page loaded its ticks from - see save_checked)
        self._desc_fetch_lock = threading.Lock()
        self._prefetch_lock = threading.Lock()     # (guards the four below - see gb_prefetch)
        self._prefetch_pending = None              # the newest request waiting its turn: (category, item name)
        self._prefetch_busy = False                # a worker thread is running
        self._prefetched = {}                      # what was fetched ahead and when: key -> time.monotonic()
        self._gb_desc_cache = {}  # mod id -> description, for the browse lists that read the text (vehicles, items, courses)
        self._configure_root(mod_root)

    def _configure_root(self, mod_root: Path | None):
        """(Re)points every data path at mod_root. Called at construction and
        again after set_master_dir() succeeds, so a running app can switch
        roots with no restart. mod_root is None only pre-first-run-setup.

        The roster file is the exception - it's a static app resource (not
        user data), always read from next to the script regardless of the
        configured master directory, same as the UI files in ui/."""
        self.roster_path = SCRIPT_DIR / ROSTER_FILENAME
        self.known_shared_files_path = SCRIPT_DIR / KNOWN_SHARED_FILES_FILENAME

        self.mod_root = mod_root
        self._root_epoch = uuid.uuid4().hex   # (a page that loaded the ticks of the folder before this is now out of date)
        if mod_root is None:
            self.state_path = None
            self.gb_categories_cache_path = None
            self.gb_mods_path = None
            self._gb_desc_store = gb_desc_cache.DescriptionCache(None)
            self.conflict_resolutions_path = None
            self.excluded_files_path = None
            self.settings_path = None
            ui_setup.ua.set_cache_dir(None)
            return
        ui_setup.ua.set_cache_dir(mod_root / image_cache.DIRNAME / "archives")
        self.state_path = mod_root / STATE_FILENAME
        self.gb_categories_cache_path = mod_root / GB_CATEGORIES_CACHE_FILENAME
        self.gb_mods_path = mod_root / GB_MODS_FILENAME
        self._gb_desc_store = gb_desc_cache.DescriptionCache(mod_root / GB_DESCRIPTIONS_FILENAME)
        self.conflict_resolutions_path = mod_root / CONFLICT_RESOLUTIONS_FILENAME
        self.excluded_files_path = mod_root / EXCLUDED_FILES_FILENAME
        self.settings_path = mod_root / SETTINGS_FILENAME
        self._migrate_flat_mod_folders()

    @mutates_library
    def _migrate_flat_mod_folders(self):
        """One-time-per-launch, idempotent migration from the old flat
        "<item> - <mod name>" folder/archive naming to the current nested
        "<item>/<mod name>" layout (see docs/architecture.md). Runs on every startup and
        master-dir switch - a no-op beyond a quick path-depth check per
        tracked file once everything's already migrated.

        Driven primarily off gamebanana-mods.json, since it already knows
        exactly which item+mod each downloaded_to/archive_path belongs to -
        the authoritative source, not the folder name itself (Windows can
        silently drop a trailing period from a folder name, the same
        Windows quirk sanitize_filename() already has to account for). A
        second pass over extracted/<category>/ then catches anything left
        over that gamebanana-mods.json doesn't know about (a mod placed by
        hand, outside the GameBanana flow) - matched against the roster by
        an exact "<item> - " prefix, never guessed if nothing matches."""
        extracted_root = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        downloads_root = self.mod_root / MODS_DIRNAME / DOWNLOADS_DIRNAME

        # (category, old top-level folder name) -> new "item/mod" relative
        # path, collected as extracted/ folders are moved so mod-manager-
        # state.json's checked-unit keys can be rewritten to match after.
        renamed = {}

        def migrate_extracted_folder(category, item_name, old_folder: Path):
            item_dir = extracted_root / category / sanitize_filename(item_name)
            item_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"{item_name} - "
            mod_part = old_folder.name[len(prefix):] if old_folder.name.startswith(prefix) else old_folder.name
            target = unique_dir_path(item_dir / mod_part)
            shutil.move(str(old_folder), str(target))
            renamed[(category, old_folder.name)] = f"{sanitize_filename(item_name)}/{target.name}"
            return target

        def migrate_archive_file(category, item_name, old_file: Path):
            item_dir = downloads_root / category / sanitize_filename(item_name)
            item_dir.mkdir(parents=True, exist_ok=True)
            target = unique_path(item_dir / old_file.name)
            shutil.move(str(old_file), str(target))
            return target

        gb_mods = self._load_gb_mods()
        gb_changed = False
        if extracted_root.is_dir() or downloads_root.is_dir():
            for item_name, mods in gb_mods.items():
                for mod in mods:
                    for file_entry in mod.get("files", []):
                        downloaded_to = file_entry.get("downloaded_to")
                        if downloaded_to:
                            old_folder = Path(downloaded_to)
                            try:
                                rel = old_folder.relative_to(extracted_root)
                            except ValueError:
                                rel = None
                            if rel is not None and len(rel.parts) == 2 and old_folder.is_dir():
                                new_folder = migrate_extracted_folder(rel.parts[0], item_name, old_folder)
                                file_entry["downloaded_to"] = str(new_folder)
                                gb_changed = True

                        archive_path = file_entry.get("archive_path")
                        if archive_path:
                            old_file = Path(archive_path)
                            try:
                                rel = old_file.relative_to(downloads_root)
                            except ValueError:
                                rel = None
                            if rel is not None and len(rel.parts) == 2 and old_file.is_file():
                                new_file = migrate_archive_file(rel.parts[0], item_name, old_file)
                                file_entry["archive_path"] = str(new_file)
                                gb_changed = True

        if gb_changed:
            self._save_gb_mods(gb_mods)

        # Fallback pass: anything still sitting directly under extracted/
        # <category>/ that isn't itself a roster-name item folder wasn't
        # covered above (untracked in gamebanana-mods.json, or the JSON was
        # stale) - match it against the roster the same way the old code
        # built these folder names in the first place.
        roster_names = sorted(
            set(self._load_roster()) | {c["name"] for cup in self._load_course_roster() for c in cup["courses"]},
            key=len, reverse=True,  # longest name first, so a longer name always wins a prefix match
        )
        for category in ("characters", "courses"):
            cat_dir = extracted_root / category
            if not cat_dir.is_dir():
                continue
            for child in list(cat_dir.iterdir()):
                if not child.is_dir() or child.name in roster_names:
                    continue
                match = next(
                    (n for n in roster_names if child.name == n or child.name.startswith(n + " - ")), None
                )
                if match is not None:
                    migrate_extracted_folder(category, match, child)

        if not renamed:
            return

        def rekey(state):
            new_state = {}
            for key, value in state.items():
                parts = key.split("/", 2)
                if len(parts) >= 2 and (parts[0], parts[1]) in renamed:
                    new_top = renamed[(parts[0], parts[1])]
                    remainder = "/" + parts[2] if len(parts) == 3 else ""
                    key = f"{parts[0]}/{new_top}{remainder}"
                new_state[key] = value
            state.clear()
            state.update(new_state)
        self._update_state(rekey)

    def get_master_dir_status(self):
        return {
            "configured": self.mod_root is not None,
            "path": str(self.mod_root) if self.mod_root else None,
            "default_path": str(APP_ROOT / DEFAULT_DATA_DIRNAME),
        }

    def pick_master_dir(self):
        """Opens a native folder-picker. Returns the chosen path, or None if
        the window isn't ready yet or the user cancelled."""
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def set_master_dir(self, new_path_str, move_existing):
        new_path = Path(new_path_str)
        try:
            new_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return {"success": False, "error": f"Couldn't create/access that folder: {e}"}

        # Before this setting existed, all data implicitly lived next to the
        # app - so on first run (nothing configured yet) that's the "old"
        # location to move data out of, even though it was never recorded as
        # such anywhere.
        old_root = self.mod_root if self.mod_root is not None else APP_ROOT
        same_dir = old_root.resolve() == new_path.resolve()

        if move_existing and not same_dir:
            conflicts = [item for item in MASTER_DIR_ITEMS if (new_path / item).exists()]
            if conflicts:
                return {
                    "success": False,
                    "error": (
                        "That folder already has " + ", ".join(conflicts) + " in it - "
                        "pick an empty folder, or one that doesn't already have mod data, to move into."
                    ),
                }
            moved = []
            errors = []
            for item in MASTER_DIR_ITEMS:
                src = old_root / item
                if not src.exists():
                    continue
                try:
                    shutil.move(str(src), str(new_path / item))
                    moved.append(item)
                except OSError as e:
                    errors.append(f"{item}: {e}")
            if errors:
                return {
                    "success": False,
                    "error": "Some items couldn't be moved: " + "; ".join(errors),
                    "moved": moved,
                }

        save_master_dir_pointer(new_path)
        self._configure_root(new_path)
        return {"success": True, "error": None}

    def _load_json(self, path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return default
        return default

    def _load_state(self):
        """The ticked mods, {unit key: True/False}. Never raises: a file that can't be read gives its .bak copy (see safe_io.py)."""
        state = safe_io.read_json_with_backup(self.state_path, {})
        return state if isinstance(state, dict) else {}

    def _write_state(self, state):
        """Replaces the ticks file in one step, keeping the previous good copy as .bak. Callers hold _state_lock."""
        safe_io.write_json_atomic(self.state_path, state, keep_backup=True)

    def _update_state(self, change):
        """Read-modify-write of the ticks under one lock, so two changes at once can't overwrite each other. `change(state)`
        edits the dict in place; what it returns is returned. The only way (besides save_checked) anything writes the ticks."""
        with self._state_lock:
            state = self._load_state()
            result = change(state)
            self._write_state(state)
            return result

    def _load_roster_data(self):
        """roster.json in full: {"characters": [...], "courses": [...],
        "vehicles"/"wheels"/"gliders": [...]} - static app resource, not user
        data (see _configure_root)."""
        return self._load_json(self.roster_path, {})

    def _load_roster(self):
        return list(self._load_roster_data().get("characters", []))

    def _load_course_roster(self):
        return list(self._load_roster_data().get("courses", []))

    def _load_vehicle_roster(self):
        """{"vehicles": [...], "wheels": [...], "gliders": [...]} - each item
        {name, internal, aliases, ...}; missing sections come back empty."""
        data = self._load_roster_data()
        return {key: list(data.get(key, [])) for key in VEHICLE_SECTIONS}

    def _load_item_roster(self):
        """roster.json's items: [{name, icon, internal, aliases}] (the icon and internal id are optional)."""
        return list(self._load_roster_data().get("items", []))

    def _vehicle_item(self, item_name):
        """(section key, roster item) for a vehicle-part name, or (None, None)."""
        for section, items in self._load_vehicle_roster().items():
            for item in items:
                if item["name"] == item_name:
                    return section, item
        return None, None

    @staticmethod
    def _vehicle_expected_key(section, item):
        """The key find_vehicle_part_ids() would report for this item's own
        model file (tires drop the K/B/T vehicle-class letter)."""
        return f"Tire_{item['internal']}" if section == "wheels" else item["internal"]

    def _vehicle_key_map(self):
        """{find_vehicle_part_ids() key: (section, item name)} for every part
        in roster.json."""
        return {
            self._vehicle_expected_key(section, item): (section, item["name"])
            for section, items in self._load_vehicle_roster().items()
            for item in items
            if item.get("internal")
        }

    def _unit_vehicle_parts(self, unit_key, key_map):
        """The set of (section, part name) whose MODEL file this unit's
        romfs/Kart/{Body,Tire,Wing}/ ships. Only the real load locations
        count (a stray copy elsewhere in the tree is never read by the game),
        and per-character paint variants (BodyTex/WingTex/Emblem) don't - those
        are a character's own colors on a stock part, not a replacement of the
        part itself."""
        category, unit_rel = unit_key.split("/", 1)
        romfs = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / category / Path(*unit_rel.split("/")) / "romfs"
        if not romfs.is_dir():
            return set()

        def child_dir(parent, name):
            return next((d for d in parent.iterdir() if d.is_dir() and d.name.lower() == name), None)

        kart = child_dir(romfs, "kart")
        if kart is None:
            return set()
        parts = set()
        for sub, kind in (("body", "Body"), ("tire", "Tire"), ("wing", "Wing")):
            folder = child_dir(kart, sub)
            if folder is None:
                continue
            regex = dict(_PART_FILE_RES)[kind]
            for f in folder.iterdir():
                m = regex.match(f.name) if f.is_file() else None
                if m:
                    key = m.group(1) if kind != "Tire" else f"Tire_{m.group(1)}"
                    if key in key_map:
                        parts.add(key_map[key])
        return parts

    def _unit_replaces(self, key, key_map, characters, course_owners, item_owners):
        """The names of everything a mod's files replace - the characters whose driver / voice files it ships, the courses whose
        Course/ slot it writes, the vehicle parts and the items whose model files it ships - as one set (they are all different names). What
        makes a mod a "pack" is that this has more than one in it."""
        unit = self._unit_dir(key)
        if not unit.is_dir():
            return set()
        names = {name for _section, name in self._unit_vehicle_parts(key, key_map)}
        names |= {characters[_name_key(c)] for c in slot_characters(unit) if _name_key(c) in characters}
        course_dir = _ci_child(_ci_child(unit, "romfs") or unit / "romfs", "course")
        if course_dir is not None:
            names |= {course_owners[d.name] for d in course_dir.iterdir() if d.is_dir() and d.name in course_owners}
        item_dir = _ci_child(_ci_child(_ci_child(unit, "romfs"), "racecommon"), "item")   # (the exact place only - this runs for every mod)
        if item_dir is not None:
            for d in item_dir.iterdir():
                if d.is_dir():
                    names.update(self._items_of_folder(d.name, item_owners))
        return names

    def _home_names(self):
        """{(category, normalized item folder name): item name} - to tell which thing a mod is filed under."""
        homes = {}
        def add(category, names):
            for n in names:
                homes[(category, normalize_char_name(sanitize_filename(n)))] = n
        add("characters", self._load_roster())
        add("courses", [c["name"] for cup in self._load_course_roster() for c in cup["courses"]])
        for section, items in self._load_vehicle_roster().items():
            add(section, [i["name"] for i in items])
        add(ITEMS_CATEGORY, [i["name"] for i in self._load_item_roster()] + [ITEMS_OTHER])
        return homes

    def get_pack_links(self):
        """Which mods are for more than the one thing they are filed under - a pack. {"by_item": {name: [unit keys]}, "by_unit":
        {unit key: [every name it replaces]}}: `by_item` lists, for each character / course / part, the packs filed under
        something else that replace it too - the card shows them as ordinary rows (and they count), so a pack is listed on every
        card it affects; `by_unit` is every pack, with all the names it replaces, for its badge.

        "Replaces" is read from the files (see _unit_replaces) and is deliberately all this claims: authors sometimes bundle
        stock files unchanged, and there is no vanilla copy to compare against. A mod stays a single unit filed in one place -
        these are listings of it, never copies - and ticking it turns on everything in it."""
        return self._library.get("pack_links", None, self._compute_pack_links, token=self._extracted_token, max_age=30,
                                 copy=copy.deepcopy)

    def _compute_pack_links(self):
        key_map = self._vehicle_key_map()
        characters = {_name_key(n): n for n in self._load_roster()}
        course_owners = self._course_names_by_internal()
        item_owners = self._item_folder_owners()
        homes = self._home_names()
        by_item, by_unit = {}, {}
        for category, units in self._discover_mods().items():
            for unit in units:
                key = f"{category}/{unit.as_posix()}"
                names = self._unit_replaces(key, key_map, characters, course_owners, item_owners)
                if not names:
                    continue
                first = unit.parts[0]   # (the item's folder; an older layout named it "<item> - <mod>")
                home = homes.get((category, normalize_char_name(first))) or homes.get((category, normalize_char_name(first.split(" - ", 1)[0].strip())))
                for name in names - {home}:
                    by_item.setdefault(name, []).append(key)
                if len(names) >= 2:
                    by_unit[key] = sorted(names)
        for keys in by_item.values():
            keys.sort()
        return {"by_item": by_item, "by_unit": by_unit}

    def gb_add_vehicle_mod_files(self, mod_id_or_url, assignments):
        """Files and downloads a vehicle mod's files under several parts in one
        go - `assignments` is [{"part": part name, "file_ids": [...]}, ...],
        each group tracked under its own part (the same mod can be tracked
        under several, as the manual flow already allows) and downloaded
        through the normal path, so every safeguard still runs: the fixers for
        loose files, and the slot check that flags a file whose real part
        differs from the one it was filed under. Returns per-part results with
        each file's status and slot_mismatch for the caller to summarize."""
        parts = []
        mod_name = None
        for assignment in assignments:
            part = assignment.get("part")
            file_ids = assignment.get("file_ids") or []
            section, item = self._vehicle_item(part)
            if item is None:
                parts.append({"part": part, "error": "That isn't a vehicle part."})
                continue
            fetched = self.gb_fetch_mod(part, mod_id_or_url)
            if not fetched["success"]:
                parts.append({"part": part, "error": fetched["error"]})
                continue
            mod = fetched["mod"]
            mod_name = mod["name"]
            downloaded = self.gb_download_files(section, part, mod["mod_id"], file_ids, mod.get("record_type", "Mod"))
            if not downloaded["success"]:
                parts.append({"part": part, "error": downloaded["error"]})
                continue
            by_id = {f["file_id"]: f for f in mod["files"]}
            parts.append({
                "part": part,
                "section": section,
                "mod_id": mod["mod_id"],
                "record_type": mod.get("record_type", "Mod"),
                "files": [
                    {
                        "file_id": r["file_id"],
                        "name": by_id.get(r["file_id"], {}).get("name", "?"),
                        "status": r["status"],
                        "error": r.get("error"),
                        "slot_mismatch": r.get("slot_mismatch"),
                        # an optional icons file, not the mod itself
                        "companion": is_companion_file(by_id.get(r["file_id"], {})),
                    }
                    for r in downloaded["results"]
                ],
            })
        return {"success": True, "mod_name": mod_name, "parts": parts}

    def _character_slot_mismatch(self, item_name, folder):
        """None unless every character this download's driver/voice files are for
        is somebody else: {"expected": [item], "found": [...], "found_characters": [...]}."""
        chars = slot_characters(folder)
        if not chars or any(_name_key(c) == _name_key(item_name) for c in chars):
            return None
        roster = {_name_key(n): n for n in self._load_roster()}
        targets = sorted({roster[_name_key(c)] for c in chars if _name_key(c) in roster})
        return {"expected": [item_name], "found": sorted(chars), "found_characters": sorted(chars),
                "targets": [{"name": n, "category": "characters"} for n in targets],
                "unresolved": sum(1 for c in chars if _name_key(c) not in roster)}

    # Model folders under RaceCommon/Item/ that two items share (the Green and Red Shell are both ItemKoura), or that the roster
    # holds no "internal" id for - {folder name (lower case): [item names]}
    _SHARED_ITEM_FOLDERS = {"itemkoura": ["Green Shell", "Red Shell"]}

    def _item_folder_owners(self):
        """{model folder (lower case): [item names]} for RaceCommon/Item/ - roster.json's "internal" ids plus the shared ones."""
        owners = {i["internal"].lower(): [i["name"]] for i in self._load_item_roster() if i.get("internal")}
        owners.update(self._SHARED_ITEM_FOLDERS)
        return owners

    def _items_of_folder(self, folder_name, owners):
        """The item(s) a RaceCommon/Item/<folder_name> model folder belongs to: its own id, or - for the extras an item brings
        (ItemKoura_FX, ItemBomheiBomb, ItemCoinB) - the longest id it starts with. [] for one the app can't place
        (ItemCommon, which every item shares, say)."""
        low = folder_name.lower()
        best = max((k for k in owners if low.startswith(k)), key=len, default=None)
        return owners[best] if best else []

    def _unit_item_folders(self, unit):
        """The names of the model folders a mod folder ships under romfs/RaceCommon/Item/ (anywhere in it)."""
        found = set()
        for dirpath, dirnames, _files in os.walk(unit):
            if Path(dirpath).name.lower() == "item" and Path(dirpath).parent.name.lower() == "racecommon":
                found.update(dirnames)
                dirnames[:] = []
        return found

    def _item_slot_mismatch(self, item_name, folder):
        """None when a download's item model folders include one of `item_name`'s (or it ships none - a texture-only mod says
        nothing), else {"expected", "found", "targets": [{name, category}], "unresolved"}: what its folders say it replaces.
        For the "Other items" catch-all nothing fits, so a mod whose models the app can place is sorted into its item."""
        found = self._unit_item_folders(folder)
        if not found:
            return None
        owners = self._item_folder_owners()
        names, unresolved = set(), 0
        for f in found:
            owner = self._items_of_folder(f, owners)
            names.update(owner)
            unresolved += 0 if owner else 1
        if item_name in names:
            return None
        return {"expected": [item_name], "found": sorted(found),
                "targets": [{"name": n, "category": ITEMS_CATEGORY} for n in sorted(names)], "unresolved": unresolved}

    def _course_names_by_internal(self):
        """{internal Course/-slot id: course name} for every course roster.json knows an id for."""
        return {i: c["name"] for cup in self._load_course_roster() for c in cup["courses"] for i in c.get("internal") or []}

    def _course_slot_mismatch(self, item_name, folder):
        """None unless the Course/ slot(s) a download writes to are all somebody else's than this course's (a course with
        no known id, or a download with no Course/ folder, isn't checked): {"expected", "found", "targets": [{name,
        category}], "unresolved"} - `targets` are the courses those slots belong to."""
        expected = self._course_internal_names(item_name)
        if not expected:
            return None
        actual = find_course_slot_names(folder)
        if not actual or actual & expected:
            return None
        owners = self._course_names_by_internal()
        return {"expected": sorted(expected), "found": sorted(actual),
                "targets": [{"name": n, "category": "courses"} for n in sorted({owners[i] for i in actual if i in owners})],
                "unresolved": sum(1 for i in actual if i not in owners)}

    def _download_slot_mismatch(self, category, item_name, folder):
        """What a download's own files say about where it belongs (see the three checks above): None when they agree with
        `item_name` (or say nothing), else the mismatch dict, whose `targets` name what the files are for."""
        if category == "courses":
            return self._course_slot_mismatch(item_name, folder)
        if category == "characters":
            return self._character_slot_mismatch(item_name, folder)
        if category in VEHICLE_SECTIONS:
            return self._vehicle_slot_mismatch(item_name, folder)
        if category == ITEMS_CATEGORY:
            return self._item_slot_mismatch(item_name, folder)
        return None

    def _slot_mismatch(self, unit_key) -> bool:
        """True when this unit's driver/voice files are all for OTHER characters than the
        one it's filed under (see slot_characters) - the "replaces Donkey Kong" badge."""
        unit = self._unit_dir(unit_key)
        chars = slot_characters(unit) if unit.is_dir() else set()
        item = unit_key.split("/")[1] if "/" in unit_key else ""
        return bool(chars) and not any(_name_key(c) == _name_key(item) for c in chars)

    def get_unit_slots(self, unit_keys):
        """Per unit: which characters' slots it writes to ("characters"), whether
        that leaves out the character it's filed under ("mismatch"), and whether it
        is one of several units of the same mod that write exactly the same files
        (colour variants, menu-sound options): "twins" = how many, "twin_first" =
        whether this is the first. Drives the badge on a mod row and what
        "Select All" ticks."""
        out, groups = {}, {}
        for key in unit_keys:
            unit = self._unit_dir(key)
            chars = slot_characters(unit) if unit.is_dir() else set()
            item = key.split("/")[1] if "/" in key else ""
            romfs = unit / "romfs"
            sig = tuple(sorted(p.relative_to(romfs).as_posix().lower() for p in romfs.rglob("*") if p.is_file())) if romfs.is_dir() else None
            out[key] = {"characters": sorted(chars), "mismatch": bool(chars) and not any(_name_key(c) == _name_key(item) for c in chars),
                        "twins": 1, "twin_first": True, "twin_group": None,
                        "parts": unit_parts(unit) if unit.is_dir() else [],
                        "voice": unit_voice(unit) if unit.is_dir() else {"race": False, "menu": False}}
            if sig:
                groups.setdefault(("/".join(key.split("/")[:3]), hash(sig)), []).append(key)
        for keys in groups.values():
            gid = "|".join(keys[0].split("/")[:3]) + "#" + str(len(keys[0]))
            for i, k in enumerate(keys):
                out[k]["twins"], out[k]["twin_first"], out[k]["twin_group"] = len(keys), i == 0, gid + str(id(keys))
        return out

    # --- playing a mod's voice files --------------------------------------------------------------------
    _VOICE_CACHE_MAX = 12

    def _character_unit(self, unit_key):
        """The unit's folder, or None when the key doesn't name a downloaded character mod."""
        root = (self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME).resolve()
        if not isinstance(unit_key, str) or not unit_key.startswith("characters/") or unit_key.count("/") < 2:
            return None
        unit = self._unit_dir(unit_key).resolve()
        return unit if unit.is_dir() and (root in unit.parents) else None

    def get_voice_clips(self, unit_key):
        """The sounds in a mod's voice files, for the "Voice lines" list:
        {"clips": [{"id", "label", "raw", "group" ("select" | "race" | "horn"), "seconds"}],
        "problems": [file names that couldn't be read]}."""
        unit = self._character_unit(unit_key)
        if unit is None:
            return {"clips": [], "problems": []}
        clips, problems = [], []
        for fi, (kind, path) in enumerate(unit_voice_files(unit)):
            try:
                data = path.read_bytes()
                entries = voice_audio.read_bars(data)
            except (OSError, voice_audio.VoiceError):
                problems.append(path.name)
                continue
            for ci, x in enumerate(entries):
                try:
                    seconds, _ch = voice_audio.sound_length(data[x["offset"]:x["offset"] + x["size"]])
                except voice_audio.VoiceError:
                    seconds = None
                label, group = voice_audio.clip_label(x["name"])
                if kind == "menu":
                    group = "select"
                clips.append({"id": f"{fi}:{ci}", "label": label, "raw": x["name"], "group": group,
                              "seconds": round(seconds, 2) if seconds is not None else None})
        rank = {"select": 0, "race": 1, "horn": 2}
        clips.sort(key=lambda c: (rank.get(c["group"], 3), c["label"].lower(), c["raw"].lower()))
        return {"clips": clips, "problems": problems}

    def get_voice_clip(self, unit_key, clip_id):
        """One sound as a playable .wav: {"success": True, "wav": base64, "seconds"} or {"success": False, "error"}.
        `clip_id` is an id from get_voice_clips()."""
        unit = self._character_unit(unit_key)
        try:
            fi, ci = (int(p) for p in str(clip_id).split(":"))
        except ValueError:
            return {"success": False, "error": "That sound isn't in this mod any more."}
        files = unit_voice_files(unit) if unit else []
        if unit is None or not (0 <= fi < len(files)) or ci < 0:
            return {"success": False, "error": "That sound isn't in this mod any more."}
        path = files[fi][1]
        try:
            stamp = path.stat().st_mtime_ns
            cache = self.__dict__.setdefault("_voice_cache", {})
            hit = cache.get((str(path), stamp, ci))
            if hit is None:
                data = path.read_bytes()
                entries = voice_audio.read_bars(data)
                if ci >= len(entries):
                    return {"success": False, "error": "That sound isn't in this mod any more."}
                x = entries[ci]
                rate, _n, channels = voice_audio.decode_bfwav(data[x["offset"]:x["offset"] + x["size"]])
                hit = (voice_audio.to_wav(rate, channels), len(channels[0]) / rate)
                if len(cache) >= self._VOICE_CACHE_MAX:
                    cache.pop(next(iter(cache)))
                cache[(str(path), stamp, ci)] = hit
        except OSError as e:
            return {"success": False, "error": f"Couldn't read the voice file: {e}"}
        except voice_audio.VoiceError as e:
            return {"success": False, "error": f"Couldn't play this sound: {e}."}
        return {"success": True, "wav": base64.b64encode(hit[0]).decode("ascii"), "seconds": round(hit[1], 2)}

    def _select_voice_source(self, item_name):
        """(mod key, clip id) of the character-select sound - "Character select" in a menu voice file - that a character's
        ticked mods bring, or None. The first ticked mod that has one; not a mod whose voice files are for somebody else's
        slot (they would not be this character's voice), and not a file that was left out of the merge."""
        excluded = self._excluded_norms()
        for key in self._ticked_by_char().get(self._canon_char(item_name), []):
            unit = self._character_unit(key)
            if unit is None or self._slot_mismatch(key):
                continue
            for fi, (kind, path) in enumerate(unit_voice_files(unit)):
                if kind != "menu":
                    continue
                parts = [p.lower() for p in path.parts]
                rel = "/".join(path.parts[len(parts) - parts[::-1].index("romfs"):])   # (relative to the romfs folder)
                if self._norm_rel(rel) in excluded.get(key, ()):
                    continue
                try:
                    data = path.read_bytes()
                    entries = voice_audio.read_bars(data)
                except (OSError, voice_audio.VoiceError):
                    continue
                for ci, x in enumerate(entries):
                    if voice_audio.clip_label(x["name"])[0] == "Character select":
                        if voice_edit.is_silent(voice_edit.sound_bytes(data, dict(x, index=ci))):
                            return None      # this is the sound the game will play, and it has been muted
                        return key, f"{fi}:{ci}"
        return None

    def get_select_voice(self, item_name):
        """The character-select sound of a character's ticked mods as a playable .wav: {"success": True, "wav": base64,
        "seconds", "from": the mod's name}. {"success": False, "none": True} when no ticked mod brings one (nothing to
        play - not an error), {"success": False, "error"} when it can't be read."""
        src = self._select_voice_source(item_name)
        if src is None:
            return {"success": False, "none": True}
        out = self.get_voice_clip(*src)
        if out.get("success"):
            out["from"] = src[0].split("/")[2] if src[0].count("/") >= 2 else src[0]
        return out

    # --- the menu pictures a mod unit brings for its character ---------------------------------------
    # (the picture tag on a mod row says which of Select screen / Mini map / Results a mod has, and clicking it shows them)
    _PIC_KINDS = ("Chara", "MapChara", "edChara")

    def _packed_texture_names(self, path, entry):
        """The texture names in one entry (the character icons) of a packed menu file; remembered per file."""
        memo = self.__dict__.setdefault("_pic_memo", {})
        try:
            st = path.stat()
        except OSError:
            return set()
        k = (str(path), st.st_mtime_ns, st.st_size, entry)
        if k not in memo:
            try:
                blob = ui_setup.ua.parse_sarc(path.read_bytes()).get(entry)
                memo[k] = {t["name"] for t in ui_setup.ua.entry_textures(blob)} if blob else set()
            except (OSError, KeyError, ValueError, ui_setup.ua.ArchiveError):
                memo[k] = set()
        return memo[k]

    def _unit_pictures(self, key, siblings=()):
        """What one mod unit brings for the character it is filed under, as sets:
        [{"source": "loose" | "packed", "for": another character's name or None, "kinds": {kind: {"path": file}
        or {"packed": (archive, entry, texture)}, plus "colours": how many colours of it}}]. Loose pictures count
        for the unit they sit in (or for every unit of the mod, when they sit beside the units); pictures in the
        unit's packed menu files count when they hold this character's icons - the same reading get_menu_look() gives
        a mod's packed file ("included"). Pictures named for a different game character are kept apart ("for")."""
        parts = key.split("/")
        code = ui_setup.code_for_character(parts[1]) if len(parts) > 2 else None
        if not code:
            return []
        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        unit_dir, mod_dir = self._unit_dir(key), self._mod_folder(key)
        others = [self._unit_dir(k) for k in siblings if k != key and k.split("/")[:3] == parts[:3]]

        def mine(path):
            if unit_dir == mod_dir or unit_dir in path.parents:
                return True
            return not any(o in path.parents for o in others)       # beside the units: for all of them

        sets = []
        for st in ui_setup.find_loose_icon_sets(mod_dir, code):
            good, theirs, colours, other = {}, {}, set(), []
            for p in st["pictures"]:
                path = Path(p["path"])
                if not mine(path):
                    continue
                cls = ui_setup.classify_code(p["code"]) if p.get("code") else None
                if cls and cls[0] != code:
                    theirs.setdefault(p["kind"], path)
                    other.append(ui_setup.CHARACTER_CODES.get(cls[0]) or cls[0])
                    continue
                idx = int(cls[1]) if cls and cls[1] is not None else 0
                if cls and cls[1] is not None:
                    colours.add(idx)
                if p["kind"] not in good or idx < good[p["kind"]][0]:
                    good[p["kind"]] = (idx, path)
            if good:
                sets.append({"source": "loose", "for": None,
                             "kinds": {k: {"path": str(v[1]), "colours": max(1, len(colours))} for k, v in good.items()}})
            elif theirs:
                sets.append({"source": "loose", "for": other[0], "kinds": {k: {"path": str(v), "colours": 1} for k, v in theirs.items()}})
        kinds = {}
        for archive_id, sources in ui_setup.collect_sources(extracted, [key]).items():
            if archive_id not in ("menu", "common"):
                continue
            for src in sources:
                for kind, slot_archive, entry, _label in ui_setup.CHARACTER_SLOTS:
                    if slot_archive != archive_id or kind in kinds:
                        continue
                    names = self._packed_texture_names(src["path"], entry)
                    have = [stem for stem in ui_setup.item_textures(code) if f"tc_{kind}_{stem}^l" in names]
                    if have:
                        kinds[kind] = {"packed": (str(src["path"]), entry, f"tc_{kind}_{have[0]}^l"), "colours": len(have)}
        if kinds:
            sets.append({"source": "packed", "for": None, "kinds": kinds})
        return sets

    def get_unit_pictures(self, unit_keys):
        """For the picture tag on each character mod row: {unit key: {"kinds": ["Chara", "MapChara", "edChara" - the ones
        it has], "versions": n, "loose": bool, "packed": bool, "colours": n, "for": another character's name (its pictures
        are named for somebody else) or None}} - only units that bring pictures are listed."""
        keys = [k for k in (unit_keys or []) if self._character_unit(k) is not None]
        out = {}
        for key in keys:
            sets = self._unit_pictures(key, keys)
            use = [x for x in sets if not x["for"]] or sets
            if not use:
                continue
            out[key] = {"kinds": [k for k in self._PIC_KINDS if any(k in x["kinds"] for x in use)],
                        "versions": len(use), "loose": any(x["source"] == "loose" for x in use),
                        "packed": any(x["source"] == "packed" for x in use),
                        "colours": max(v["colours"] for x in use for v in x["kinds"].values()),
                        "for": use[0]["for"]}
        return out

    def get_unit_picture_sets(self, unit_key, siblings=None):
        """The pictures themselves, for the "Menu pictures" window: {"sets": [{"label", "source", "for", "colours",
        "kinds": {kind: {"preview" (data: URL), "size"}}}]} (for a character with colours, the first colour's).
        `siblings` are the other units of the same card, so pictures that sit in another unit aren't counted."""
        if self._character_unit(unit_key) is None:
            return {"sets": []}
        sibs = [k for k in (siblings or []) if isinstance(k, str) and self._character_unit(k) is not None]
        sets = self._unit_pictures(unit_key, sibs)
        loose_n = sum(1 for x in sets if x["source"] == "loose")
        out, n = [], 0
        for x in sets:
            kinds = {}
            for kind, info in x["kinds"].items():
                try:
                    if "path" in info:
                        preview = self._thumb_uri(Path(info["path"]), 128)
                        from PIL import Image
                        with Image.open(info["path"]) as im:
                            size = f"{im.size[0]}x{im.size[1]}"
                    else:
                        archive, entry, tex_name = info["packed"]
                        memo = self.__dict__.setdefault("_ui_base_tex", {})
                        path = Path(archive)
                        mk = (str(path), path.stat().st_mtime_ns, entry)
                        if mk not in memo:
                            memo[mk] = ui_setup.ua.entry_texture_map(ui_setup.ua.parse_sarc(path.read_bytes())[entry])
                        png = ui_setup.ua.texture_png(memo[mk][tex_name])
                        preview = "data:image/png;base64," + base64.b64encode(png).decode("ascii") if png else None
                        from PIL import Image
                        with Image.open(io.BytesIO(png)) as im:
                            size = f"{im.size[0]}x{im.size[1]}"
                except Exception:
                    continue
                if preview:
                    kinds[kind] = {"preview": preview, "size": size}
            if x["source"] == "packed":
                label = "In the mod's menu files"
            elif loose_n > 1:
                n += 1
                label = f"Version {n}"
            else:
                label = "In the mod's folder"
            out.append({"label": label, "source": x["source"], "for": x["for"],
                        "colours": max(v["colours"] for v in x["kinds"].values()), "kinds": kinds})
        return {"sets": out}

    def _vehicle_slot_mismatch(self, item_name, folder):
        """None if this download's model files (BodyK_Cat.szs, Wing_Pap.szs,
        TireK_Zst.szs, ...) are consistent with the part it's filed under -
        including a pack that ships this part's file among others, or one
        that ships none of that kind at all. Otherwise {"expected": [...],
        "found": [...], "found_parts": [{name, section}, ...]}: found_parts
        names the parts whose files it DOES ship, so the UI can say which row
        it probably belongs under (and offer to move it there)."""
        section, item = self._vehicle_item(item_name)
        if item is None or not item.get("internal"):
            return None
        kind = {"vehicles": "Body", "wheels": "Tire", "gliders": "Wing"}[section]
        found = find_vehicle_part_ids(folder)
        actual = found[kind]
        expected_key = self._vehicle_expected_key(section, item)
        if expected_key in actual:
            return None
        if not actual:
            # Ships no file of this part's kind - fine (a texture pack, say) - unless it ships another kind of part's file:
            # a tire mod filed under a body, a glider under a wheel.
            actual = set().union(*found.values())
            if not actual:
                return None
        key_map = self._vehicle_key_map()
        parts = [{"name": key_map[k][1], "section": key_map[k][0]} for k in sorted(actual) if k in key_map]
        return {
            "expected": [expected_key],
            "found": sorted(actual),
            "found_parts": parts,
            "targets": [{"name": p["name"], "category": p["section"]} for p in parts],
            "unresolved": len(actual) - len(parts),
        }

    def get_vehicle_fit(self, part_name, unit_keys):
        """For the vehicle card's "Right part" step: of these downloaded mods (unit keys filed under `part_name`), the ones
        whose model files are for a different part - {unit key: {"expected": [...], "found": [...], "found_parts": [{name,
        section}], "mod_id", "record_type"}} (mod_id is None when the download isn't tracked, so it can't be moved). A mod
        that ships this part's file, or none of that kind at all, isn't listed."""
        if self.mod_root is None or self._vehicle_item(part_name)[1] is None:
            return {}
        tracked = self._load_gb_mods().get(part_name, [])
        out = {}
        for key in unit_keys or []:
            unit = self._unit_dir(key)
            if not unit.is_dir():
                continue
            mismatch = self._vehicle_slot_mismatch(part_name, unit)
            if not mismatch:
                continue
            mod = next((m for m in tracked for f in m.get("files", [])
                        if f.get("downloaded_to") and (Path(f["downloaded_to"]) == unit or Path(f["downloaded_to"]) in unit.parents)), None)
            out[key] = {**mismatch, "mod_id": mod["mod_id"] if mod else None,
                        "record_type": (mod or {}).get("record_type", "Mod")}
        return out

    def get_mod_ids(self, item_name, unit_keys):
        """For a "Move to..." on a mod: {unit key: {"mod_id", "record_type"}} of these downloaded mods (unit keys filed under
        `item_name`, whatever kind of thing it is) that are tracked from GameBanana - a mod added by hand has no id, so it
        can't be moved (it is left out)."""
        if self.mod_root is None or self._movable_item(item_name)[1] is None:
            return {}
        tracked = self._load_gb_mods().get(item_name, [])
        out = {}
        for key in unit_keys or []:
            unit = self._unit_dir(key)
            if not unit.is_dir():
                continue
            mod = next((m for m in tracked for f in m.get("files", [])
                        if f.get("downloaded_to") and (Path(f["downloaded_to"]) == unit or Path(f["downloaded_to"]) in unit.parents)), None)
            if mod:
                out[key] = {"mod_id": mod["mod_id"], "record_type": mod.get("record_type", "Mod")}
        return out

    def _rekey_unit_prefix(self, old_rel, new_rel):
        """Everything the app remembers about a mod is keyed by its path ("category/item/mod"): the ticks, the files left
        out, the clash priorities, the voice edits, the look reviews, the menu picture choices. After its folder moves, this
        rewrites each of those from `old_rel` to `new_rel` (the mod's folder and anything beneath it) so none is orphaned.
        The ticks are the caller's (they live in one file it already holds)."""
        def fix(text):
            return new_rel + text[len(old_rel):] if text == old_rel or text.startswith(old_rel + "/") else text

        def walk(v):
            if isinstance(v, dict):
                return {fix(k) if isinstance(k, str) else k: walk(x) for k, x in v.items()}
            if isinstance(v, list):
                return [walk(x) for x in v]
            return fix(v) if isinstance(v, str) else v

        stores = [self.excluded_files_path, self.conflict_resolutions_path, self.settings_path,
                  self.mod_root / VOICE_EDITS_FILENAME, self.mod_root / LOOK_REVIEWS_FILENAME,
                  self.mod_root / ui_setup.OVERRIDES_FILENAME]
        self._notes_rekey(old_rel, new_rel)     # (its keys only - a note's own text is never rewritten)
        for path in stores:
            if path is None or not path.is_file():
                continue
            data = self._load_json(path, None)
            if data is None:
                continue
            new = walk(data)
            if new != data:
                safe_io.write_json_atomic(path, new)
    def _movable_item(self, name):
        """(folder under mods/extracted/ it is filed in, roster entry) of anything a mod can be moved between - a vehicle
        part, an item (the "Other items" catch-all too), a character or a course - or (None, None). No two of these share a
        name."""
        section, part = self._vehicle_item(name)
        if part is not None:
            return section, part
        if name == ITEMS_OTHER or any(i["name"] == name for i in self._load_item_roster()):
            return ITEMS_CATEGORY, {"name": name}
        if name in self._load_roster():
            return "characters", {"name": name}
        if any(c["name"] == name for cup in self._load_course_roster() for c in cup["courses"]):
            return "courses", {"name": name}
        return None, None

    @staticmethod
    def _move_family(section):
        """What a mod can be moved between: parts to parts (across bodies, tires and gliders), items to items, and so on."""
        return "vehicle parts" if section in VEHICLE_SECTIONS else section

    @mutates_library
    def gb_move_mod(self, from_item, mod_id, to_item, record_type="Mod"):
        """Re-files a tracked mod under another character / course / vehicle part / item - what a download's files
        say it replaces (see _refile_mod), what "Move to..." on a mod asks for, and how a mod filed under "Other items" gets its
        item - without a remove-and-re-add: its tracking entry, extracted folders, archives, ticked state and everything else
        remembered about its path (see _rekey_unit_prefix) move together, and each moved file's slot check is re-run against its
        new home. Refuses if the mod is already tracked under the target (two entries for one mod would need merging) or the
        move would go between different kinds of thing (a character to a course...). Returns the moved folders' new
        paths as `moved_folders`, which is what an undo needs."""
        from_section, from_part = self._movable_item(from_item)
        to_section, to_part = self._movable_item(to_item)
        if from_part is None or to_part is None:
            return {"success": False, "error": "That isn't something a mod can be moved between."}
        if self._move_family(from_section) != self._move_family(to_section):
            return {"success": False, "error": f"A mod can only be moved to another one of the same kind - not from {self._move_family(from_section)} to {self._move_family(to_section)}."}
        if from_item == to_item:
            return {"success": False, "error": "That's already where it is."}
        gb_mods = self._load_gb_mods()
        source = gb_mods.get(from_item, [])
        mod = next(
            (x for x in source if x["mod_id"] == mod_id and x.get("record_type", "Mod") == record_type), None
        )
        if mod is None:
            return {"success": False, "error": f"That mod isn't tracked under {from_item}."}
        if any(x["mod_id"] == mod_id and x.get("record_type", "Mod") == record_type
               for x in gb_mods.get(to_item, [])):
            return {"success": False,
                    "error": f"This mod is already tracked under {to_item} - remove it there first."}

        extracted_root = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        downloads_root = self.mod_root / MODS_DIRNAME / DOWNLOADS_DIRNAME
        to_dir = sanitize_filename(to_item)
        done = []  # (new path, old path) of every completed move, for rollback
        moved_folders, renames = [], []
        try:
            for f in mod.get("files", []):
                old_folder = f.get("downloaded_to")
                if old_folder and Path(old_folder).is_dir():
                    old = Path(old_folder)
                    new_parent = extracted_root / to_section / to_dir
                    new_parent.mkdir(parents=True, exist_ok=True)
                    new = unique_dir_path(new_parent / old.name)
                    old_rel = old.relative_to(extracted_root).as_posix()
                    shutil.move(str(old), str(new))
                    done.append((new, old))
                    f["downloaded_to"] = str(new)
                    new_rel = new.relative_to(extracted_root).as_posix()
                    f["slot_mismatch"] = self._download_slot_mismatch(to_section, to_item, new)
                    moved_folders.append(new_rel)
                    renames.append((old_rel, new_rel))
                old_archive = f.get("archive_path")
                if old_archive and Path(old_archive).is_file():
                    archive_parent = downloads_root / to_section / to_dir
                    archive_parent.mkdir(parents=True, exist_ok=True)
                    new_archive = unique_path(archive_parent / Path(old_archive).name)
                    shutil.move(old_archive, str(new_archive))
                    done.append((new_archive, Path(old_archive)))
                    f["archive_path"] = str(new_archive)
        except (OSError, ValueError) as e:
            # Nothing has been persisted yet (the records are only written
            # below), so undoing the file moves leaves everything as it was.
            for new, old in reversed(done):
                try:
                    shutil.move(str(new), str(old))
                except OSError:
                    pass
            return {"success": False, "error": f"Couldn't move its files: {e}"}

        gb_mods[from_item] = [x for x in source if x is not mod]
        if not gb_mods[from_item]:
            del gb_mods[from_item]
        gb_mods.setdefault(to_item, []).append(mod)
        self._save_gb_mods(gb_mods)
        def rekey(state):   # (the ticks of the moved folders follow them - on the file as it is now, not as it was before the moves)
            for old_rel, new_rel in renames:
                for key in [k for k in state if k == old_rel or k.startswith(old_rel + "/")]:
                    state[new_rel + key[len(old_rel):]] = state.pop(key)
        self._update_state(rekey)
        for old_rel, new_rel in renames:
            self._rekey_unit_prefix(old_rel, new_rel)
        for _new, old in done:  # tidy now-empty item folders
            try:
                old.parent.rmdir()
            except OSError:
                pass
        return {"success": True, "from_item": from_item, "to_item": to_item, "to_section": to_section,
                "moved_folders": moved_folders}

    def get_vehicles_view(self):
        """Same idea as get_character_view(), for the three vehicle-part
        sections: every roster item always shows up (even with nothing
        downloaded yet), with its discovered mod units grouped by the item
        folder they were downloaded into."""
        categories = self._discover_mods()
        gb_attempted = self._gb_attempted_names()
        sections = []
        for key, items in self._load_vehicle_roster().items():
            norm_to_name = {normalize_char_name(sanitize_filename(i["name"])): i["name"] for i in items}
            grouped = {i["name"]: [] for i in items}
            for unit in categories.get(key, []):
                canonical = norm_to_name.get(normalize_char_name(unit.parts[0]))
                if canonical is not None:
                    grouped[canonical].append(f"{key}/{unit.as_posix()}")
            sections.append({
                "key": key,
                "label": VEHICLE_SECTIONS[key]["label"],
                "items": [
                    {
                        "name": i["name"],
                        "type": i.get("type"),
                        "internal": i.get("internal"),
                        "units": sorted(grouped[i["name"]]),
                        "gb_attempted": i["name"] in gb_attempted,
                    }
                    for i in items
                ],
            })
        return {"sections": sections, "checked": self._load_state()}

    def get_items_view(self):
        """Same idea as get_vehicles_view(), for the Items screen: every roster item always shows up (even with nothing
        downloaded yet) with its discovered mod units grouped by the item folder they were downloaded into, and a last
        catch-all ("Items": the folder everything filed before items had a roster is in) for what fits none of them."""
        categories = self._discover_mods()
        gb_attempted = self._gb_attempted_names()
        roster = self._load_item_roster()
        norm_to_name = {normalize_char_name(sanitize_filename(i["name"])): i["name"] for i in roster}
        grouped = {i["name"]: [] for i in roster}
        grouped[ITEMS_OTHER] = []
        for unit in categories.get(ITEMS_CATEGORY, []):
            canonical = norm_to_name.get(normalize_char_name(unit.parts[0]), ITEMS_OTHER)
            grouped[canonical].append(f"{ITEMS_CATEGORY}/{unit.as_posix()}")
        items = [{
            "name": i["name"],
            "internal": i.get("internal"),
            "units": sorted(grouped[i["name"]]),
            "gb_attempted": i["name"] in gb_attempted,
        } for i in roster]
        items.append({
            "name": ITEMS_OTHER, "label": ITEMS_OTHER_LABEL, "internal": None, "catch_all": True,
            "units": sorted(grouped[ITEMS_OTHER]), "gb_attempted": ITEMS_OTHER in gb_attempted,
        })
        return {"key": ITEMS_CATEGORY, "label": "Items", "items": items, "checked": self._load_state()}

    def _course_internal_names(self, course_name):
        """Looks up the known internal romfs Course/-slot id(s) for a course
        from roster.json's "internal" field (None if not yet known).
        Sourced from a community datamine, not derived from downloads, so
        this is ground truth rather than something a bad download could have
        contaminated. More than one entry means more than one is legitimately
        correct (only Animal Crossing's 4 seasonal variants, currently) -
        never leftover ambiguity from a multi-course bundle mod."""
        for cup in self._load_course_roster():
            for c in cup["courses"]:
                if c["name"] == course_name and c.get("internal"):
                    return set(c["internal"])
        return None

    def _course_music_slugs(self, course_name):
        """Same idea as _course_internal_names(), for roster.json's
        "music" field - the id embedded in that course's race BGM filenames
        (see find_course_music_slugs()). A Booster Course Pass course's music
        id is just its own Cnsw_NN internal id reused verbatim; everything
        else (all 48 base-game/Wii-U-DLC courses) has its own distinct,
        unrelated-looking id (e.g. Twisted Mansion's romfs id is
        Gu_HorrorHouse, but its music id is WU_HAUNTED) that only a
        datamine - not the internal id - could give us."""
        for cup in self._load_course_roster():
            for c in cup["courses"]:
                if c["name"] == course_name and c.get("music"):
                    # Uppercased to match find_course_music_slugs()'s own
                    # normalization - roster.json stores a BCP course's
                    # music id in whatever case its "internal" id already
                    # uses (e.g. "Cnsw_32"), not uppercase.
                    return {m.upper() for m in c["music"]}
        return None

    def _load_gb_mods(self):
        return self._load_json(self.gb_mods_path, {})

    def _save_gb_mods(self, data):
        safe_io.write_json_atomic(self.gb_mods_path, data)
    def _load_conflict_resolutions(self):
        """relpath -> priority-ordered list of unit-keys, most-preferred
        first (see resolve_conflict()). A stale entry - naming a mod that's
        since been unchecked or removed - is never actively cleaned up here;
        _compute_claims() just skips over it and tries the next one, so an
        outdated list is harmless rather than something that needs GC."""
        return self._load_json(self.conflict_resolutions_path, {})

    def _save_conflict_resolutions(self, data):
        safe_io.write_json_atomic(self.conflict_resolutions_path, data)
    def _load_known_shared_files(self):
        return self._load_json(self.known_shared_files_path, {})

    def get_known_shared_files(self):
        return self._load_known_shared_files()

    def resolve_conflict(self, path, preferred_key):
        """Records preferred_key as the top choice for `path` - moved to the
        front of its existing priority list (removing any earlier occurrence
        of it first) so a later fallback still works if this mod is ever
        removed or unchecked."""
        resolutions = self._load_conflict_resolutions()
        existing = [k for k in resolutions.get(path, []) if k != preferred_key]
        resolutions[path] = [preferred_key] + existing
        self._save_conflict_resolutions(resolutions)
        return resolutions[path]

    def clear_conflict_resolution(self, path):
        resolutions = self._load_conflict_resolutions()
        if path in resolutions:
            del resolutions[path]
            self._save_conflict_resolutions(resolutions)
        return True

    # --- files a mod leaves out (excluded-files.json) ------------------------
    # {mod key: {normalized romfs path: {"path", "reason", "kept_from", "added"}}}
    # "reason" is "conflict" (settled a clash - "kept_from" is the mod whose
    # copy was kept, or null for "use the game's own file") or "manual".
    # Superseded conflict-resolutions.json's "first listed mod wins": leaving a
    # file out of the losing mod says the same thing and is visible on that mod.

    @staticmethod
    def _norm_rel(path):
        return str(path).replace("\\", "/").strip("/").lower()

    def _load_excluded_files(self):
        data = self._load_json(self.excluded_files_path, {}) if self.excluded_files_path else {}
        return data if isinstance(data, dict) else {}

    def _save_excluded_files(self, data):
        data = {k: v for k, v in data.items() if v}
        safe_io.write_json_atomic(self.excluded_files_path, data)
    def _excluded_norms(self):
        return {mod: set(entries) for mod, entries in self._load_excluded_files().items()}

    def _unit_exists(self, key):
        return "/" in key and self._unit_dir(key).is_dir()

    def exclude_files(self, mod_key, paths, reason="manual", kept_from=None):
        """Leave `paths` (romfs-relative) out of `mod_key`'s contribution to
        the merge. Returns how many were newly left out."""
        if not self._unit_exists(mod_key):
            return {"success": False, "error": "That mod isn't downloaded any more."}
        data = self._load_excluded_files()
        entries = data.setdefault(mod_key, {})
        added = 0
        now = datetime.now().isoformat(timespec="seconds")
        for p in paths:
            p = str(p).replace("\\", "/").strip("/")
            if not p or p.lower().startswith("exefs/"):
                continue  # half a code patch can't be dropped
            norm = p.lower()
            if norm not in entries:
                added += 1
            entries[norm] = {"path": p, "reason": reason, "kept_from": kept_from, "added": now}
        self._save_excluded_files(data)
        return {"success": True, "added": added}

    def include_files(self, mod_key, paths=None):
        """Undo exclude_files(); paths=None includes everything again."""
        data = self._load_excluded_files()
        entries = data.get(mod_key, {})
        if paths is None:
            removed = len(entries)
            entries = {}
        else:
            drop = {self._norm_rel(p) for p in paths}
            removed = sum(1 for n in entries if n in drop)
            entries = {n: v for n, v in entries.items() if n not in drop}
        data[mod_key] = entries
        self._save_excluded_files(data)
        return {"success": True, "removed": removed}

    def get_excluded_files(self, mod_key=None):
        """{mod key: [{"path", "reason", "kept_from", "kept_label", "added",
        "in_mod"}]} for every mod with left-out files (or just `mod_key`).
        Entries of mods that are no longer downloaded are dropped."""
        data = self._load_excluded_files()
        pruned = {m: e for m, e in data.items() if e and self._unit_exists(m)}
        if pruned != data:
            self._save_excluded_files(pruned)
        out = {}
        for mod, entries in pruned.items():
            if mod_key is not None and mod != mod_key:
                continue
            romfs = self._unit_dir(mod) / "romfs"
            out[mod] = [
                {
                    "path": e["path"], "reason": e.get("reason", "manual"),
                    "kept_from": e.get("kept_from"),
                    "kept_label": mod_label(e["kept_from"]) if e.get("kept_from") else None,
                    "added": e.get("added"),
                    "in_mod": (romfs / e["path"]).is_file(),
                }
                for e in sorted(entries.values(), key=lambda e: e["path"].lower())
            ]
        return out

    def get_mod_files(self, mod_key, limit=4000):
        """Every romfs file a mod ships, with whether it's currently left out -
        the per-mod "Files" view."""
        if not self._unit_exists(mod_key):
            return {"files": [], "total": 0, "truncated": False}
        romfs = self._unit_dir(mod_key) / "romfs"
        excluded = self._excluded_norms().get(mod_key, set())
        files = []
        if romfs.is_dir():
            for f in sorted(romfs.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(romfs)
                files.append({
                    "path": rel.as_posix(),
                    "size": f.stat().st_size,
                    "left_out": rel.as_posix().lower() in excluded,
                    "kind": path_kind(rel.as_posix()),
                    "skipped_anyway": _is_packed_ui_archive(rel) or rel.as_posix().lower() in _MERGE_SKIP_RELPATHS,
                })
        return {"files": files[:limit], "total": len(files), "truncated": len(files) > limit}

    def resolve_conflict_group(self, mods, paths, keep):
        """Settles a group of conflicting files in one go. `keep` is the mod
        whose copy stays (every other mod in `mods` leaves those paths out,
        unless its copy is byte-identical anyway) or None for "use the game's
        own file" (every mod leaves them out)."""
        mods = list(mods)
        if keep is not None and keep not in mods:
            return {"success": False, "error": "That mod isn't part of this conflict."}
        excluded = 0
        for path in paths:
            if path.lower().startswith("exefs/"):
                continue
            keep_file = self._unit_dir(keep) / "romfs" / path if keep else None
            for mod in mods:
                if mod == keep:
                    continue
                mod_file = self._unit_dir(mod) / "romfs" / path
                if keep_file is not None and mod_file.is_file() and keep_file.is_file() \
                        and filecmp.cmp(mod_file, keep_file, shallow=False):
                    continue
                res = self.exclude_files(mod, [path], reason="conflict", kept_from=keep)
                excluded += res.get("added", 0) if res.get("success") else 0
            self.clear_conflict_resolution(path)  # an older saved preference must not linger
        return {"success": True, "excluded": excluded}

    def _load_settings(self):
        saved = self._load_json(self.settings_path, {})
        return {**DEFAULT_SETTINGS, **saved}

    def get_settings(self):
        return self._load_settings()

    def save_settings(self, settings):
        merged = {**self._load_settings(), **settings}
        safe_io.write_json_atomic(self.settings_path, merged)
        return merged

    def clear_all_mods(self, delete_files=True):
        """Forgets every tracked GameBanana mod (across all characters), and
        optionally deletes the files that were downloaded through this flow.
        Mods placed manually outside the app are never touched, since only
        paths this app itself recorded in gamebanana-mods.json are removed."""
        gb_mods = self._load_gb_mods()
        deleted = 0
        errors = []
        if delete_files:
            for char_mods in gb_mods.values():
                for mod in char_mods:
                    for file_entry in mod.get("files", []):
                        for key in ("downloaded_to", "archive_path"):
                            path_str = file_entry.get(key)
                            if not path_str:
                                continue
                            path = Path(path_str)
                            try:
                                if path.is_dir():
                                    shutil.rmtree(path)
                                    deleted += 1
                                elif path.is_file():
                                    path.unlink()
                                    deleted += 1
                            except OSError as e:
                                errors.append(f"{path}: {e}")
        self._save_gb_mods({})
        return {"success": True, "deleted": deleted, "errors": errors}

    def _extracted_token(self):
        """(see library_cache.tree_token) - changes when a mod folder is added or removed under mods/extracted/."""
        return library_cache.tree_token(self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME)

    def _discover_mods(self):
        """discover_mods() for this library, remembered until the library changes (see library_cache.py)."""
        return self._library.get("discover", None, lambda: discover_mods(self.mod_root), token=self._extracted_token,
                                 copy=lambda found: {category: list(units) for category, units in found.items()})

    def get_mods(self):
        self._library.bump()   # (this is what the Refresh button asks for: look at the folders again)
        self.sync_voice_edits()
        categories = self._discover_mods()
        saved = self._load_state()
        payload = {}
        for category, units in categories.items():
            payload[category] = [unit.as_posix() for unit in units]
        return {
            "categories": payload,
            "checked": saved,
            "epoch": self._root_epoch,   # (the page sends it back with every save - see save_checked)
            "notes": self._notes_payload(),          # {unit key: note text} - the user's own notes on mods (mod_notes.py)
            "ui_icons_text": ui_icons_status_text(self.mod_root),
        }

    def save_checked(self, changes, epoch=None):
        """Records ticks. `changes` is {unit key: on/off} for the units that CHANGED - never the page's whole picture: a key that
        isn't in it stays as it is, so a page can't lose ticks it doesn't know about (an empty or out-of-date page used to replace
        the whole file). `epoch` is what get_mods() handed the page: a page that loaded a different master folder (the folder was
        switched under it) or never finished loading is refused - False, and the page reloads its ticks. True when saved."""
        if epoch is not None and epoch != self._root_epoch:
            return False
        changes = {str(k): bool(v) for k, v in (changes or {}).items()}
        with self._state_lock:
            state = self._load_state()
            state.update(changes)
            self._write_state(state)
        try:
            self.sync_auto_names(state)      # ticking a character mod tries to give the character its name
        except Exception:
            pass                            # a naming hiccup must never lose the user's ticks
        self.sync_voice_edits()             # a Custom voice mod follows the mod it was made from (never raises)
        return True

    # --- naming a character after its mod ---------------------------------------
    # When a character mod is ticked the app tries to work out what the character should be
    # called in the menus: (1) the mod's own text (a message.sarc with a different name at the
    # character's entry - the UI step already applies that, so nothing more is stored),
    # else (2) the mod's name (GameBanana's, or its folder's), else (3) the folder inside it.
    # The guess is stored as a name flagged "auto" in ui-overrides.json, so it goes away again
    # when the mod is unticked, never overwrites a name the user typed, and stays gone once the
    # user cleared it ("Back to normal name").

    def _canon_char(self, folder_name):
        """The name the game/roster uses for a character folder ("Bowser Jr" -> "Bowser Jr.")."""
        if getattr(self, "_canon_table", None) is None:
            names = list((ui_setup.name_table().get("characters") or {}).keys())
            try:
                names += [r["name"] if isinstance(r, dict) else r for r in self._load_roster()]
            except (ValueError, KeyError, TypeError):
                pass
            self._canon_table = {}
            for n in names:
                self._canon_table.setdefault(_name_key(n), n)
        return self._canon_table.get(_name_key(folder_name), folder_name)

    # --- "checked": has the user confirmed how a character will look? ---------------
    # A character with ticked mods is "checked" once the user has pressed "Looks right" (or has set its
    # name or icon themselves, which is the same thing). What was checked is remembered as a signature of
    # the character's ticked mods, and every signature ever checked is kept - so ticking a mod off and on
    # again is still checked, while a different set of mods needs looking at again.

    def _ticked_by_char(self, state=None):
        state = state if state is not None else self._load_state()
        out = {}
        for k, v in state.items():
            if v and k.startswith("characters/") and k.count("/") >= 2:
                out.setdefault(self._canon_char(k.split("/")[1]), []).append(k)
        return {c: sorted(v) for c, v in out.items()}

    @staticmethod
    def _review_sig(keys):
        return hashlib.sha1("|".join(sorted(keys)).encode("utf-8")).hexdigest()[:12]

    def _review_data(self):
        """{"characters": {name: [signatures whose look was checked]}, "names": {name: [signatures whose
        guessed NAME was confirmed]}} - "Looks right" confirms both; the guessed-names review only confirms the name.
        "course_names" / "course_icons" are the same two records for courses (see get_course_look())."""
        data = self._load_json(self.mod_root / LOOK_REVIEWS_FILENAME, {})
        if not isinstance(data, dict):
            data = {}
        for bucket in ("characters", "names", "course_names", "course_icons", "part_names", "part_icons"):
            if not isinstance(data.get(bucket), dict):
                data[bucket] = {}
        return data

    def _review_state(self, canon, keys, name_changed, icons_changed):
        """Two independent review tasks for a character with ticked mods - Name (a ticked mod, or
        you, wants it called something other than the game's own name) and Icons (its menu pictures
        changed, or a model-swap mod needs a glance even though nothing in the menu icons themselves
        did). {"name_applicable", "name_done", "icons_applicable", "icons_done"} - confirming one
        never marks the other; a character with ticked mods but neither applicable has nothing to
        check at all. A UI combines them however it likes (reviewFinished() in ui/js/tiles-and-review.js)."""
        model = any(unit_has_driver_model(self._unit_dir(k)) and not self._slot_mismatch(k) for k in keys)
        data = self._review_data()
        sig = self._review_sig(keys)
        return {
            "name_applicable": bool(name_changed), "name_done": sig in data["names"].get(canon, []),
            "icons_applicable": bool(model or icons_changed), "icons_done": sig in data["characters"].get(canon, []),
        }

    def _mark_signature(self, bucket, item_name, undo=False):
        """Adds (or, `undo`, removes) the currently-ticked signature for `item_name` in one
        look-reviews.json bucket - "names" for the Name task, "characters" for the Icons one. Each
        is its own independent record; this never touches the other bucket."""
        canon = self._canon_char(item_name)
        return self._store_signature(bucket, canon, self._ticked_by_char().get(canon), undo)

    def _store_signature(self, bucket, canon, keys, undo=False):
        """The write behind _mark_signature() / _mark_course(): the signature of `keys` (the ticked mods)
        goes into, or (undo) comes out of, look-reviews.json's `bucket` for `canon`."""
        if not keys:
            return False
        data = self._review_data()
        sigs = data[bucket].setdefault(canon, [])
        sig = self._review_sig(keys)
        if sig in sigs:
            sigs.remove(sig)
        if not undo:
            sigs.append(sig)
        del sigs[:-30]
        safe_io.write_json_atomic((self.mod_root / LOOK_REVIEWS_FILENAME), data)
        return True

    # --- the same two review tasks for a course --------------------------------------------------
    # A course with ticked mods has a Name task (something wants it called other than the game's own
    # name - the mod's own text, a name you typed, or a guess from the mod's name that you haven't
    # confirmed yet) and an Icons task (the picture on the course-select screen: a mod that ships its
    # own needs no check; otherwise the game's own shows, or one made from a screenshot - either way
    # the user says so once). Like a character's, each is confirmed for the SET of ticked mods.

    def _ticked_by_course(self, state=None):
        state = state if state is not None else self._load_state()
        out = {}
        for k, v in state.items():
            if v and k.startswith("courses/") and k.count("/") >= 2:
                out.setdefault(k.split("/")[1], []).append(k)
        return {c: sorted(v) for c, v in out.items()}

    def _mark_course(self, bucket, course, undo=False):
        return self._store_signature(bucket, course, self._ticked_by_course().get(course), undo)

    def _course_picture(self, course, keys):
        """{"state": "mod" | "you" | "vanilla", "mod", "preview", "default"} - where the course-select picture comes from:
        a ticked mod's own CoursePict, else one made from a screenshot (course-icons/), else the game's own ("default" is
        the game's own picture, for showing what the course has without the mod)."""
        default = self.get_course_default_pictures([course]).get(course)
        bundled = next((k for k in keys if self._find_course_pict_file(k)), None)
        if bundled:
            return {"state": "mod", "mod": bundled.split("/")[2], "preview": self.get_course_icon_preview(bundled), "default": default}
        made = self._generated_course_pict_path(course)
        if made is not None and made.is_file():
            return {"state": "you", "mod": None, "preview": self.get_course_icon_preview(keys[0]), "default": default}
        return {"state": "vanilla", "mod": None, "preview": None, "default": default}

    def get_course_look(self, course, _ctx=None):
        """What a course card needs: {"course", "ticked": [unit keys], "name": {...get_menu_look()'s name..., "suggestion"},
        "picture": _course_picture(), "review": {"name_applicable", "name_done", "icons_applicable", "icons_done"}}
        - "review" is None when nothing is ticked for the course, and {"error"} comes back when the menu files can't be read."""
        keys = self._ticked_by_course().get(course, [])
        if not keys:
            return {"course": course, "ticked": [], "name": None, "picture": None, "review": None}
        base = self.get_menu_look(course, "courses", _ctx)
        if base.get("error"):
            return {"error": base["error"]}
        nm = dict(base.get("name") or {})
        suggestion = None
        if nm.get("state") == "vanilla":
            gb_names = self._gb_mod_names()
            for key in keys:
                parts = key.split("/")
                for text, source in ((gb_names.get("/".join(parts[:3]).lower()), "the mod's name"), (parts[2], "the mod's folder name")):
                    guess = suggest_name_from_mod(text, nm.get("vanilla") or course, max_len=32) if text else None
                    if guess:
                        suggestion = {"text": guess, "source": source, "mod": parts[2]}
                        break
                if suggestion:
                    break
        nm["suggestion"] = suggestion
        picture = self._course_picture(course, keys)
        data = self._review_data()
        sig = self._review_sig(keys)
        review = {
            "name_applicable": nm.get("state", "vanilla") != "vanilla" or suggestion is not None,
            "name_done": sig in data["course_names"].get(course, []),
            "icons_applicable": picture["state"] != "mod",
            "icons_done": sig in data["course_icons"].get(course, []),
        }
        return {"course": course, "ticked": keys, "name": nm, "picture": picture, "review": review}

    def get_course_tile_view(self, course_names):
        """{name: {"applicable", "finished"}} for the courses (of those asked about) that have ticked mods - what
        the tile's small "have you checked it?" marker needs. One menu-look context is shared by all of them."""
        ticked = self._ticked_by_course()
        wanted = [c for c in course_names if c in ticked]
        if not wanted:
            return {}
        ctx = self._menu_look_ctx()
        out = {}
        for c in wanted:
            look = self.get_course_look(c, ctx)
            r = look.get("review")
            if not r:
                continue
            applicable = r["name_applicable"] or r["icons_applicable"]
            nm = look.get("name") or {}
            out[c] = {"applicable": applicable,
                      "finished": (not r["name_applicable"] or r["name_done"]) and (not r["icons_applicable"] or r["icons_done"]),
                      "shown": nm.get("text") if nm.get("state") in ("mod", "you") else None}
        return out

    def confirm_course_name(self, course):
        """The course's Name task: the name as it is now (typed, the mod's, or the game's) is right."""
        return {"success": self._mark_course("course_names", course)}

    def mark_course_icon_reviewed(self, course):
        """The course's Icons task: the course-select picture is settled (the game's own, or the one made)."""
        return {"success": self._mark_course("course_icons", course)}

    def unmark_course_icon_reviewed(self, course):
        return {"success": self._mark_course("course_icons", course, undo=True)}

    # --- the same two review tasks for a vehicle part --------------------------------------------
    # A part with ticked mods has a Name task (the game's text can name it differently: the mod's own text, a name you
    # typed, or a guess from the mod's name) and an Icons task (its picture in the parts menu: a mod that ships its own
    # needs no check; otherwise the game's own shows, or one you chose - either way you say so once). Each is confirmed for
    # the SET of ticked mods, exactly like a course's. The picture is one texture in menu.sarc for most parts, or a set of
    # loose files for the sixteen that come in outfits (ui_setup.part_item(), vehicle_icons.py).

    def _part_folder_map(self):
        """{(section, normalized folder name): part name} - which part a mods/extracted/<section>/<folder> belongs to."""
        return {(section, normalize_char_name(sanitize_filename(i["name"]))): i["name"]
                for section, items in self._load_vehicle_roster().items() for i in items}

    def _ticked_by_part(self, state=None):
        state = state if state is not None else self._load_state()
        fmap = self._part_folder_map()
        out = {}
        for k, v in state.items():
            parts = k.split("/")
            if v and len(parts) >= 3 and parts[0] in ui_setup.PART_KINDS:
                name = fmap.get((parts[0], normalize_char_name(parts[1])))
                if name:
                    out.setdefault(name, []).append(k)
        return {n: sorted(v) for n, v in out.items()}

    def _mark_part(self, bucket, part, undo=False):
        return self._store_signature(bucket, part, self._ticked_by_part().get(part), undo)

    def _unit_loose_part_files(self, key):
        """The loose part-picture files (UI/cmn/menu/tc_KP_*.bntx) a mod unit ships in its romfs."""
        unit = self._unit_dir(key)
        menu = ui_setup._child(ui_setup._child(ui_setup._child(ui_setup._child(unit, "romfs"), "UI"), "cmn"), "menu")
        if menu is None or not menu.is_dir():
            return []
        return [f for f in sorted(menu.iterdir()) if f.is_file() and vehicle_icons.loose_family(f.name)]

    @staticmethod
    def _packed_winner(plan, choices, archive_id, iid):
        """(variant, change) when a ticked mod's own packed archive decides this texture, else None."""
        analysis = (plan or {}).get(archive_id)
        if not analysis:
            return None
        idx = ui_setup._winners(analysis, choices).get(iid)
        if idx is None:
            return None
        v = analysis["variants"][idx]
        if v.get("is_override"):
            return None
        return v, next(c for c in v["changes"] if ui_setup.item_id(c) == iid)

    def _part_picture(self, part, section, item, keys, ctx):
        """{"state": "you" | "mod" | "vanilla", "mod", "preview", "default", "editable"} - where the part's picture in the
        parts menu comes from: one the user chose (ui-overrides), a ticked mod's own (a texture in its menu.sarc, or its
        loose files), else the game's own ("default" is the game's own, to show what the part has without the mod)."""
        default = self.get_vehicle_icons().get(part)
        iid = ui_setup.part_item(section, item.get("internal"))
        base = {"state": "vanilla", "mod": None, "preview": None, "default": default, "editable": iid is not None}
        if iid is None:
            return base
        o = ctx["ov"]["textures"].get(iid)
        if o:
            left = 0
            if ui_setup.is_loose_item(iid):   # outfit pictures a ticked mod filed elsewhere supplies stay that mod's
                fam = iid.split("|", 1)[1]
                left = sum(1 for n in self._part_pictures_left_to_mods() if vehicle_icons.loose_family(n) == fam)
            return {**base, "state": "you", "preview": self._thumb_uri(self.mod_root / o["png"], 260), "left_to_mods": left}
        if ui_setup.is_loose_item(iid):
            fam = iid.split("|", 1)[1]
            for k in keys:
                mine = [f for f in self._unit_loose_part_files(k) if vehicle_icons.loose_family(f.name) == fam]
                if mine:
                    png = self._decoded_pict(f"part-mod:{mine[0]}", mine[0])
                    preview = image_cache.data_uri(png) if png else None
                    return {**base, "state": "mod", "mod": k.split("/")[2], "preview": preview}
        else:
            won = self._packed_winner(ctx["plan"], ctx["choices"], "menu", iid)
            if won:
                return {**base, "state": "mod", "mod": (won[0]["labels"] or ["a mod"])[0], "preview": won[1].get("preview")}
        return base

    def get_part_look(self, part, _ctx=None):
        """What a vehicle part's card needs - the same shape as get_course_look(): {"part", "ticked", "name", "picture",
        "review"}; "review" is None when nothing is ticked for the part, and {"error"} comes back when the menu files can't be read."""
        section, item = self._vehicle_item(part)
        if item is None:
            return {"error": f"{part} isn't a vehicle part."}
        self._top_up_pictures_once()
        keys = self._ticked_by_part().get(part, [])
        if not keys:
            return {"part": part, "ticked": [], "name": None, "picture": None, "review": None}
        ctx = _ctx or self._menu_look_ctx()
        base = self.get_menu_look(part, section, ctx)
        if base.get("error"):
            return {"error": base["error"]}
        nm = dict(base.get("name") or {})
        suggestion = None
        if nm.get("state") == "vanilla":
            gb_names = self._gb_mod_names()
            for key in keys:
                parts = key.split("/")
                for text, source in ((gb_names.get("/".join(parts[:3]).lower()), "the mod's name"), (parts[2], "the mod's folder name")):
                    guess = suggest_name_from_mod(text, nm.get("vanilla") or part, max_len=32) if text else None
                    if guess:
                        suggestion = {"text": guess, "source": source, "mod": parts[2]}
                        break
                if suggestion:
                    break
        nm["suggestion"] = suggestion
        picture = self._part_picture(part, section, item, keys, ctx)
        data = self._review_data()
        sig = self._review_sig(keys)
        review = {
            "name_applicable": nm.get("state", "vanilla") != "vanilla" or suggestion is not None,
            "name_done": sig in data["part_names"].get(part, []),
            "icons_applicable": picture["state"] != "mod" and picture["editable"],
            "icons_done": sig in data["part_icons"].get(part, []),
        }
        return {"part": part, "ticked": keys, "name": nm, "picture": picture, "review": review, "section": section}

    def get_part_tile_view(self, part_names):
        """{name: {"applicable", "finished", "shown", "icon"}} for the parts (of those asked about) that have ticked mods -
        the tile's "have you checked it?" marker, the name the menus will show, and the picture that will show when it is not
        the game's own. One menu-look context is shared by all of them."""
        ticked = self._ticked_by_part()
        wanted = [c for c in part_names if c in ticked]
        if not wanted:
            return {}
        ctx = self._menu_look_ctx()
        out = {}
        for c in wanted:
            look = self.get_part_look(c, ctx)
            r = look.get("review")
            if not r:
                continue
            nm = look.get("name") or {}
            pic = look.get("picture") or {}
            out[c] = {"applicable": r["name_applicable"] or r["icons_applicable"],
                      "finished": (not r["name_applicable"] or r["name_done"]) and (not r["icons_applicable"] or r["icons_done"]),
                      "shown": nm.get("text") if nm.get("state") in ("mod", "you") else None,
                      "icon": pic.get("preview") if pic.get("state") != "vanilla" else None}
        return out

    def confirm_part_name(self, part):
        """The part's Name task: the name as it is now (typed, the mod's, or the game's) is right."""
        return {"success": self._mark_part("part_names", part)}

    def mark_part_icon_reviewed(self, part):
        """The part's Icons task: its picture in the parts menu is settled (the game's own, or the one chosen)."""
        return {"success": self._mark_part("part_icons", part)}

    def unmark_part_icon_reviewed(self, part):
        return {"success": self._mark_part("part_icons", part, undo=True)}

    def _part_pictures_left_to_mods(self):
        """File names (lower-case) of loose part pictures a ticked mod supplies for a part it is NOT filed under - a character
        mod's per-outfit Standard Kart picture, say. A picture you chose for the part is not written over those: they stay
        the character mod's. (A mod filed under the part itself is what your choice replaces.)"""
        fmap = self._part_folder_map()
        names = vehicle_icons.key_names()
        left = set()
        for key, on in self._load_state().items():
            if not on or key.count("/") < 2:
                continue
            files = self._unit_loose_part_files(key)
            if not files:
                continue
            cat, folder = key.split("/")[:2]
            unit_part = fmap.get((cat, normalize_char_name(folder))) if cat in ui_setup.PART_KINDS else None
            for f in files:
                if unit_part is None or names.get(vehicle_icons.loose_family(f.name)) != unit_part:
                    left.add(f.name.lower())
        return left

    def sync_part_pictures(self):
        """Brings part-icons/ (always merged in) in line with the pictures the user chose for parts that are loose files: every
        variant file written, files no longer wanted removed. Cheap when there is nothing chosen. Returns build_part_pictures()'s
        report ({"written", "left_to_mods", "problems"})."""
        if self.mod_root is None:
            return {"written": [], "left_to_mods": [], "problems": []}
        out_dir = self.mod_root / PART_ICONS_DIRNAME / "romfs" / "UI" / "cmn" / "menu"
        ov = ui_setup.load_overrides(self.mod_root)
        if not any(ui_setup.is_loose_item(i) for i in ov["textures"]) and not out_dir.is_dir():
            return {"written": [], "left_to_mods": [], "problems": []}
        return ui_setup.build_part_pictures(self.mod_root, game_files.current_vehicle_picts(self.mod_root), out_dir,
                                            self._part_pictures_left_to_mods())

    def _set_part_icon(self, part, png_bytes):
        section, item = self._vehicle_item(part)
        iid = ui_setup.part_item(section, item.get("internal")) if item else None
        if iid is None:
            return {"success": False, "error": f"Don't know the game's picture for {part}."}
        try:
            rel = ui_setup.store_icon_picture(self.mod_root, png_bytes, square=False)
        except Exception as e:  # PIL raises a variety
            return {"success": False, "error": f"Couldn't use that picture: {e}"}
        ov = ui_setup.load_overrides(self.mod_root)
        ov["textures"][iid] = {"png": rel, "who": part}
        ui_setup.save_overrides(self.mod_root, ov)
        report = self.sync_part_pictures()
        if report["problems"]:
            return {"success": False, "error": "Couldn't write the picture into the game's files: " + "; ".join(report["problems"][:2])}
        return {"success": True, "left_to_mods": len(report["left_to_mods"])}

    def set_part_icon_from_url(self, part, image_url, crop_x, crop_y, crop_w, crop_h):
        """Uses (a crop of) an image from the web - one of a mod's own GameBanana screenshots - as a part's picture."""
        try:
            image_bytes = gamebanana_api.fetch_bytes(image_url)
            from PIL import Image
            src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            cropped = src.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Couldn't process that image: {e}"}
        return self._set_part_icon(part, buf.getvalue())

    def set_part_icon_from_data(self, part, data_url):
        """Same, for a picture the user chose from their own computer (already cropped in the page, sent as a data: URL)."""
        try:
            png = base64.b64decode(data_url.split(",", 1)[1])
        except (IndexError, ValueError):
            return {"success": False, "error": "That picture couldn't be read."}
        return self._set_part_icon(part, png)

    def clear_part_icon(self, part):
        """Back to the game's own picture (or the ticked mod's, if it brings one)."""
        section, item = self._vehicle_item(part)
        iid = ui_setup.part_item(section, item.get("internal")) if item else None
        ov = ui_setup.load_overrides(self.mod_root)
        if iid and ov["textures"].pop(iid, None) is not None:
            ui_setup.save_overrides(self.mod_root, ov)
        self.sync_part_pictures()
        self._mark_part("part_icons", part, undo=True)
        return {"success": True}

    def _guessed_names(self):
        """The names the app guessed (see sync_auto_names) that the user hasn't confirmed yet - the Commit
        page's "names were guessed" warning: [{"item", "name", "source", "mod", "vanilla"}]. A guess counts
        as confirmed once the Name task itself was confirmed for that set of ticked mods (confirming Icons
        doesn't settle it - the two are independent, see _review_state)."""
        ov = ui_setup.load_overrides(self.mod_root)
        ticked = self._ticked_by_char()
        data = self._review_data()
        out = []
        for nk, entry in sorted(ov["names"].items()):
            if not entry.get("auto"):
                continue
            kind, item = nk.split("|", 1)
            keys = ticked.get(item) if kind == "characters" else None
            if not keys:
                continue
            sig = self._review_sig(keys)
            if sig in data["names"].get(item, []):
                continue
            out.append({"item": item, "name": entry["text"], "source": entry.get("source") or "the mod",
                        "mod": (entry["from"].split("/") + ["", "", ""])[2] if entry.get("from") else "", "vanilla": item})
        return out

    def get_guessed_names(self):
        return self._guessed_names()

    def confirm_guessed_name(self, item_name):
        """The Name task: confirms the name as it currently is (typed, the mod's own, or the game's)
        for this set of ticked mods. Independent of the Icons task - see mark_icons_reviewed()."""
        return {"success": self._mark_signature("names", item_name)}

    def mark_icons_reviewed(self, item_name):
        """The Icons task: the user pressed "Looks right" on the character's menu pictures (and, for
        a model-swap mod with nothing else to preview, its in-game look in general). Independent of
        the Name task - see confirm_guessed_name()."""
        return {"success": self._mark_signature("characters", item_name)}

    def unmark_icons_reviewed(self, item_name):
        return {"success": self._mark_signature("characters", item_name, undo=True)}

    def _gb_mod_names(self):
        """{"<category>/<item>/<mod folder>" (lowercased): the mod's name on GameBanana} for every
        tracked download. Keyed by the part of the path below extracted/, so it doesn't matter
        where the data folder itself lives."""
        out = {}
        for mods in self._load_gb_mods().values():
            for mod in mods:
                for f in mod.get("files", []):
                    dl = f.get("downloaded_to")
                    if dl:
                        parts = Path(dl).parts
                        rel = parts[parts.index(EXTRACTED_DIRNAME) + 1:] if EXTRACTED_DIRNAME in parts else parts[-3:]
                        out["/".join(rel).lower()] = mod.get("name")
        return out

    def _guess_character_name(self, unit_key, canon, gb_names):
        """(name, where it came from) for one ticked character mod unit, or None."""
        parts = unit_key.split("/")
        gb = gb_names.get("/".join(parts[:3]).lower())
        for text, source in ((gb, "the mod's name"), (parts[2], "the mod's folder name"), (parts[-1] if len(parts) > 3 else None, "the folder inside the mod")):
            name = suggest_name_from_mod(text, canon) if text else None
            if name:
                return name, source
        return None

    def sync_auto_names(self, checked=None):
        """Brings the guessed character names in line with the ticked mods (see above). Returns
        what changed: [{"item", "name", "source"}] for new/changed guesses."""
        state = checked if checked is not None else self._load_state()
        ticked = sorted(k for k, v in state.items() if v and k.startswith("characters/") and k.count("/") >= 2)
        settings = self._load_settings()
        locale = settings.get("ui_setup_locale") or "USen"
        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        table = ui_setup.name_table().get("characters") or {}
        gb_names = self._gb_mod_names()
        wanted, ui_named = {}, set()
        for key in ticked:
            unit = self._unit_dir(key)
            if not unit.is_dir() or not unit_has_driver_model(unit) or self._slot_mismatch(key):
                continue   # a voice/kart/menu-only mod, or one for another character's slot, doesn't name this one
            canon = self._canon_char(key.split("/")[1])
            labels = table.get(canon) or []
            sources = ui_setup.collect_sources(extracted, [key])
            by_text = False
            for aid in (f"message:{locale}", "message:USen", "message:EUen"):
                for src in sources.get(aid, []):
                    text = ui_setup.message_name(src["path"], labels) if labels else None
                    if text and _name_key(text) != _name_key(canon):
                        by_text = True   # the mod's own text names it; the UI step applies that
                        break
                if by_text:
                    break
            if by_text:
                ui_named.add(canon)
            if canon in ui_named or canon in wanted:
                continue
            guess = self._guess_character_name(key, canon, gb_names)
            if guess:
                wanted[canon] = {"text": guess[0], "source": guess[1], "from": key}

        ov = ui_setup.load_overrides(self.mod_root)
        declined = set(ov["declined_names"])
        changes, dirty = [], False
        for nk in list(ov["names"]):
            entry = ov["names"][nk]
            if not entry.get("auto"):
                continue
            kind, nm = nk.split("|", 1)
            w = wanted.get(nm) if kind == "characters" else None
            if not w or nm in ui_named or w["text"] != entry.get("text") or nk in declined:
                del ov["names"][nk]      # unticked, now named by the mod's own text, or a better guess follows
                dirty = True
        legacy = {o.get("who") for o in ov["strings"].values() if o.get("kind") == "characters"}
        for canon, w in wanted.items():
            nk = f"characters|{canon}"
            if nk in ov["names"] or nk in declined or canon in legacy or canon in ui_named:
                continue                 # the user's own name (or an unchanged guess) stays
            ov["names"][nk] = {"text": w["text"], "auto": True, "source": w["source"], "from": w["from"]}
            changes.append({"item": canon, "name": w["text"], "source": w["source"]})
            dirty = True
        if dirty:
            ui_setup.save_overrides(self.mod_root, ov)
        return changes

    def _mod_folder(self, unit_key):
        # First 3 segments: category/item/mod - the atomic downloaded-mod
        # folder (a multi-variant pack's unit_key has more segments after
        # that for its own subfolder, e.g. "characters/Waluigi/Donald Trump/
        # Over Waluigi", but the whole pack is still removed/revealed/
        # icon-searched as one).
        parts = unit_key.split("/")
        return self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / Path(*parts[:3])

    def _find_icon_file(self, unit_key):
        mod_folder = self._mod_folder(unit_key)
        if not mod_folder.is_dir():
            return None
        return next(
            (p for p in sorted(mod_folder.rglob("*"))
             if p.is_file() and p.suffix.lower() in IMAGE_EXTS),
            None,
        )

    def has_mod_icon(self, unit_key):
        """Returns the found icon file's path as a string (for display/debugging),
        or None if this mod has no loose icon image files."""
        icon_path = self._find_icon_file(unit_key)
        return str(icon_path) if icon_path else None

    def reveal_icon(self, unit_key):
        """Opens the file manager with this mod's first icon file selected, so
        the user can look at it themselves - the app never displays it.
        (Under WSL this needs its Windows-interop feature to be working.)"""
        icon_path = self._find_icon_file(unit_key)
        if icon_path is None:
            return {"success": False, "error": "No icon file found for this mod."}
        try:
            show_in_file_manager(icon_path, select=True)
            return {"success": True}
        except (OSError, subprocess.SubprocessError) as e:
            return {"success": False, "error": f"Couldn't open the file manager. Details: {e}"}

    def _find_course_pict_file(self, unit_key):
        """Returns the Path to this course unit's own select-screen thumbnail
        (romfs/UI/cmn/menu/ym_CoursePict_<internal id>.bntx), or None if it
        doesn't bundle one - most course mods don't (see the "packed
        UI/*.sarc" section of docs/merge-rules.md for the character-icon equivalent of this).

        Resolves the exact checked unit's own romfs the same way
        _compute_claims() does (category/unit_rel/romfs) rather than via
        _mod_folder()'s first-3-segments shortcut - a multi-variant pack's
        checked unit lives one level deeper than its own download folder
        (e.g. "Sweet Sweet Canyon/Green Hill Zone (2)/GreenHillZone-v1.1.2"),
        and _mod_folder() would stop one level too early for those."""
        category, unit_rel = unit_key.split("/", 1)
        mod_romfs = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / category / unit_rel / "romfs"
        pict_dir = mod_romfs / "UI" / "cmn" / "menu"
        if not pict_dir.is_dir():
            return None
        return next(pict_dir.glob("ym_CoursePict_*.bntx"), None)

    def has_course_icon(self, unit_key):
        return self._find_course_pict_file(unit_key) is not None

    def _generated_course_pict_path(self, course_name):
        """Returns the Path an app-generated icon for `course_name` would be
        at under course-icons/ (see generate_course_icon()) - regardless of
        whether one has actually been generated yet."""
        internal_ids = self._course_internal_names(course_name)
        if not internal_ids:
            return None
        internal_id = sorted(internal_ids)[0]
        return (
            self.mod_root / COURSE_ICONS_DIRNAME / "romfs" / "UI" / "cmn" / "menu"
            / f"ym_CoursePict_{internal_id}_00^u.bntx"
        )

    def get_course_icon_preview(self, unit_key):
        """Decodes this course unit's icon to a PNG data URI for inline
        preview in the Course Select strip - the mod's own bundled
        CoursePict if it has one, otherwise an app-generated one from
        course-icons/ if generate_course_icon() has made one for this
        course. Returns None if neither exists, or if it's in a shape
        bntx_decode.py doesn't know how to handle (see that module's
        docstring)."""
        pict_path = self._find_course_pict_file(unit_key)
        if pict_path is None:
            category, unit_rel = unit_key.split("/", 1)
            course_name = unit_rel.split("/", 1)[0]
            generated = self._generated_course_pict_path(course_name)
            if generated is not None and generated.is_file():
                pict_path = generated
        if pict_path is None:
            return None
        png_bytes = self._decoded_pict(f"course-mod:{pict_path}", pict_path, _COURSE_PICT_CROP_BOX)
        return image_cache.data_uri(png_bytes) if png_bytes else None

    def _find_any_course_pict_template(self):
        """Returns the Path to any one real, mod-provided CoursePict.bntx
        among currently downloaded course mods, used as a structural
        template by generate_course_icon() - see bntx_encode.py's docstring
        for why building on a real, working file is safer than constructing
        a .bntx container from scratch for a format that can only really be
        validated by a real Switch console loading it."""
        extracted_root = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / "courses"
        if not extracted_root.is_dir():
            return None
        return next(extracted_root.rglob("ym_CoursePict_*.bntx"), None)

    def generate_course_icon(self, course_name, image_url, crop_x, crop_y, crop_w, crop_h):
        """Downloads `image_url` (one of a mod's own GameBanana screenshots),
        crops it to (crop_x, crop_y, crop_w, crop_h) in the source image's
        own pixel coordinates, and composites it into the fixed 304x256
        CoursePict canvas following MK8DX's own template convention (see
        _COURSE_PICT_CONTENT_* below), then writes a generated select-screen
        icon for `course_name` to course-icons/ - always merged in
        automatically, the same way ui-icons/ already is for character
        icons. For a course whose checked mod doesn't bundle its own icon
        (see bntx_encode.py for how the file itself is built)."""
        template_path = self._find_any_course_pict_template()
        if template_path is None:
            return {
                "success": False,
                "error": "No downloaded course mod has its own icon yet to use as a template - "
                         "can't generate one until at least one does.",
            }

        internal_ids = self._course_internal_names(course_name)
        if not internal_ids:
            return {"success": False, "error": f'No known internal id for "{course_name}".'}
        internal_id = sorted(internal_ids)[0]

        try:
            image_bytes = gamebanana_api.fetch_bytes(image_url)
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}

        try:
            from PIL import Image
            src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            cropped = src.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            resized = cropped.resize(
                (_COURSE_PICT_CONTENT_W, _COURSE_PICT_CONTENT_H), Image.LANCZOS
            )
            canvas = Image.new("RGBA", (304, 256), (0, 0, 0, 255))
            canvas.paste(resized, (_COURSE_PICT_CONTENT_LEFT, _COURSE_PICT_CONTENT_TOP))
            rgba_bytes = canvas.tobytes("raw", "RGBA")
        except Exception as e:
            return {"success": False, "error": f"Couldn't process that image: {e}"}

        try:
            new_bntx = bntx_encode.build_course_pict_bntx(
                template_path, internal_id, 304, 256, rgba_bytes, srgb=True
            )
        except bntx_encode.UnsupportedTemplateError as e:
            return {"success": False, "error": f"Couldn't use an existing icon as a template: {e}"}

        dest_path = self._generated_course_pict_path(course_name)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(new_bntx)

        return {"success": True}

    def clear_generated_course_icon(self, course_name):
        dest_path = self._generated_course_pict_path(course_name)
        if dest_path is not None and dest_path.is_file():
            dest_path.unlink()
        return {"success": True}

    def reveal_path(self, path_str):
        """Opens the file manager at an arbitrary already-known folder path
        (e.g. a GameBanana download that needs manual structure fixes) -
        unlike reveal_icon, this takes a full path directly rather than
        looking one up from a unit key."""
        path = Path(path_str)
        if not path.is_dir():
            return {"success": False, "error": "That folder no longer exists."}
        try:
            show_in_file_manager(path)
            return {"success": True}
        except (OSError, subprocess.SubprocessError) as e:
            return {"success": False, "error": f"Couldn't open the file manager. Details: {e}"}

    def reveal_mod_folder(self, unit_key):
        """Opens the file manager at a "Mods to merge" entry's actual mod
        folder - previously the only way to look at a downloaded mod's files
        from the app was the icon-reveal badge, which only appears when the
        mod happens to have a loose image file GameBanana's own file listing
        never guaranteed one."""
        mod_folder = self._mod_folder(unit_key)
        return self.reveal_path(str(mod_folder))

    @mutates_library
    def remove_mod_unit(self, unit_key):
        """Deletes a downloaded mod's folder from disk entirely, regardless
        of how it got there (manual download or GameBanana fetch). A
        multi-variant mod (e.g. several lighting/color choices sharing one
        download) is removed as a whole, since they share one folder."""
        mod_folder = self._mod_folder(unit_key)
        if not mod_folder.is_dir():
            return {"success": False, "error": "That mod folder no longer exists."}
        try:
            shutil.rmtree(mod_folder)
        except OSError as e:
            return {"success": False, "error": f"Couldn't delete it: {e}"}

        self._clear_state_prefix("/".join(unit_key.split("/")[:3]))
        self._notes_clear_prefix("/".join(unit_key.split("/")[:3]))   # (the user removed it on purpose; a re-download keeps its notes)
        self.sync_voice_edits()   # (removing a Custom voice mod gives back the files left out for it)

        # If this folder was tracked via the GameBanana flow, reset its
        # status rather than leaving a "Downloaded" badge pointing at a
        # folder that's now gone.
        gb_mods = self._load_gb_mods()
        gb_changed = False
        for char_mods in gb_mods.values():
            for mod in char_mods:
                for file_entry in mod.get("files", []):
                    if file_entry.get("downloaded_to") == str(mod_folder):
                        file_entry["download_status"] = "not_downloaded"
                        file_entry["downloaded_to"] = None
                        gb_changed = True
        if gb_changed:
            self._save_gb_mods(gb_mods)

        return {"success": True}

    def _gb_attempted_names(self):
        """Names with at least one tracked GameBanana file whose download was
        actually attempted (not just fetched-but-never-downloaded). Used to
        tell "never touched" apart from "downloaded, but needs manual fixing"
        on the character/course grid - both show 0 merge units otherwise,
        which made the latter easy to miss while scanning for what's left."""
        gb_mods = self._load_gb_mods()
        attempted = set()
        for name, mods in gb_mods.items():
            for mod in mods:
                for f in mod.get("files", []):
                    if f.get("download_status", "not_downloaded") != "not_downloaded":
                        attempted.add(name)
                        break
        return attempted

    def get_character_view(self):
        """Groups discovered 'characters' mod units by character (parsed from the
        '<Character> - <Mod Name>' folder naming convention), against the full
        roster so every character shows up even with nothing downloaded yet."""
        categories = self._discover_mods()
        char_units = categories.get("characters", [])
        roster = list(self._load_roster())
        roster_norm = {normalize_char_name(name): name for name in roster}
        gb_attempted = self._gb_attempted_names()

        grouped = {name: [] for name in roster}
        for unit in char_units:
            mod_folder = unit.parts[0]
            prefix = mod_folder.split(" - ", 1)[0].strip()
            canonical = roster_norm.get(normalize_char_name(prefix))
            if canonical is None:
                # Unrecognized character not in the roster - add it rather than
                # silently dropping its mods.
                canonical = prefix
                if canonical not in grouped:
                    grouped[canonical] = []
                    roster.append(canonical)
                    roster_norm[normalize_char_name(canonical)] = canonical
            grouped[canonical].append(f"characters/{unit.as_posix()}")

        roster_payload = [
            {
                "name": name,
                "units": sorted(grouped.get(name, [])),
                "gb_attempted": name in gb_attempted,
            }
            for name in roster
        ]

        return {
            "roster": roster_payload,
            "checked": self._load_state(),
            "ui_icons_text": ui_icons_status_text(self.mod_root),
        }

    def ui_icon_worklist(self):
        """Every tracked character mod GameBanana flagged "ui_assets" - a raw
        common.sarc/menu.sarc icon-texture dump, not a mergeable romfs mod -
        grouped by character with its actual on-disk folder path. This is the
        same download_status already shown per-file in each character's own
        GameBanana file list; this just collects every hit across the whole
        roster into one place, since hand-injecting these into the combined
        ui-icons/ set with an external tool (Switch Toolbox etc.) is much
        easier when every source folder is listed in one spot instead of
        found by opening each character one at a time."""
        gb_mods = self._load_gb_mods()
        roster = set(self._load_roster())
        # The "UI" simple category's downloads are keyed under its fixed
        # pseudo-item name (not a character), and are where most non-romfs UI
        # art (PNG icon sets, packed .sarc themes) ends up - so they're listed
        # too, under a "UI mods" heading. Other simple categories (a vehicle
        # download that's really just UI art, say) get their own label.
        simple_labels = {info["label"]: info["label"] for info in SIMPLE_MOD_CATEGORIES.values()}
        simple_labels["UI"] = "UI mods"
        simple_labels.update({i["name"]: i["name"] for i in self._load_item_roster()})
        simple_labels[ITEMS_OTHER] = ITEMS_OTHER_LABEL
        entries = []
        for item_name, mods in gb_mods.items():
            if item_name not in roster and item_name not in simple_labels:
                continue  # courses etc. never produce icon dumps
            group = item_name if item_name in roster else simple_labels[item_name]
            for mod in mods:
                for f in mod.get("files", []):
                    if f.get("download_status") == "ui_assets" and f.get("downloaded_to"):
                        entries.append({
                            "character": group,
                            "mod_name": mod["name"],
                            "file_name": f["name"],
                            "path": f["downloaded_to"],
                            "profile_url": mod.get("profile_url"),
                        })
        entries.sort(key=lambda e: (e["character"].lower(), e["mod_name"].lower()))
        return entries

    def get_course_view(self):
        """Same idea as get_character_view(), but for the 'courses' category,
        grouped by cup (Grand Prix) the way the game's map-select screen does -
        pick a cup first, then a course within it."""
        categories = self._discover_mods()
        course_units = categories.get("courses", [])
        cups = self._load_course_roster()
        all_course_names = [c["name"] for cup in cups for c in cup["courses"]]
        name_norm = {normalize_char_name(name): name for name in all_course_names}

        grouped = {name: [] for name in all_course_names}
        unrecognized = []
        for unit in course_units:
            mod_folder = unit.parts[0]
            prefix = mod_folder.split(" - ", 1)[0].strip()
            canonical = name_norm.get(normalize_char_name(prefix))
            if canonical is None:
                unrecognized.append(f"courses/{unit.as_posix()}")
                continue
            grouped[canonical].append(f"courses/{unit.as_posix()}")

        gb_attempted = self._gb_attempted_names()
        cup_payload = []
        for cup in cups:
            courses_payload = [
                {
                    "name": c["name"],
                    "units": sorted(grouped.get(c["name"], [])),
                    "gb_attempted": c["name"] in gb_attempted,
                }
                for c in cup["courses"]
            ]
            cup_payload.append({"cup": cup["cup"], "courses": courses_payload})

        return {
            "cups": cup_payload,
            "unrecognized": unrecognized,
            "checked": self._load_state(),
        }

    def get_simple_categories_view(self):
        """Same idea as get_character_view()/get_course_view(), but for the
        flat "simple" categories (see SIMPLE_MOD_CATEGORIES) - each one is a
        single fixed pseudo-item (its own label, e.g. "Mechanics") rather
        than a roster of many, since there's nothing further to group units
        by - every mod downloaded into one of these categories always nests
        under that same fixed item name (see gb_download_files() callers in
        ui/js/add-mod.js and gamebanana.js), so unlike get_character_view()'s folder-name parsing
        this can just take every discovered unit under the category as-is."""
        categories = self._discover_mods()
        gb_attempted = self._gb_attempted_names()
        payload = [
            {
                "key": key,
                "name": info["label"],
                "units": sorted(f"{key}/{unit.as_posix()}" for unit in categories.get(key, [])),
                "gb_attempted": info["label"] in gb_attempted,
            }
            for key, info in SIMPLE_MOD_CATEGORIES.items()
        ]
        return {"categories": payload, "checked": self._load_state()}

    def _dir_size(self, folder: Path) -> int:
        """Bytes in every file under `folder` - remembered for a minute unless a folder in it changes (library_cache.py)."""
        def compute():
            if not folder.is_dir():
                return 0
            total = 0
            for dirpath, _dirnames, filenames in os.walk(folder):
                for name in filenames:
                    try:
                        total += os.stat(os.path.join(dirpath, name)).st_size
                    except OSError:
                        pass
            return total
        return self._library.get(f"size:{folder}", None, compute, token=lambda: library_cache.tree_token(folder), max_age=60)

    def get_stats(self):
        """Footer summary: what fraction of the roster currently has at
        least one checked ("Mods to merge") unit - i.e. would actually show
        up in-game if you staged right now, not just "downloaded" - plus how
        much disk space the downloaded archives and their extracted mods
        take up."""
        checked = self._load_state()

        def modded_fraction(entries):
            total = len(entries)
            modded = sum(1 for e in entries if any(checked.get(u) for u in e["units"]))
            return {"modded": modded, "total": total, "pct": round(100 * modded / total) if total else 0}

        char_view = self.get_character_view()["roster"]
        course_view = self.get_course_view()["cups"]
        course_entries = [c for cup in course_view for c in cup["courses"]]
        packs = self.get_pack_links()["by_item"]   # (a pack counts on every card it is listed on)
        for entry in char_view + course_entries:
            entry["units"] = list(entry["units"]) + packs.get(entry["name"], [])

        return {
            "characters": modded_fraction(char_view),
            "courses": modded_fraction(course_entries),
            "compressed_bytes": self._dir_size(self.mod_root / MODS_DIRNAME / DOWNLOADS_DIRNAME),
            "extracted_bytes": self._dir_size(self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME),
        }

    def _gb_subcategory_id(self, character_name):
        """Resolves a roster character name to its GameBanana subcategory id,
        fetching+caching the full subcategory list on first use. Returns
        (id_or_None, error_or_None)."""
        cache = self._load_json(self.gb_categories_cache_path, {})
        subcats = cache.get("subcategories")
        if not subcats:
            try:
                subcats = gamebanana_api.fetch_subcategories(CHARACTERS_CATEGORY_ID)
            except gamebanana_api.GameBananaError as e:
                return None, str(e)
            self.gb_categories_cache_path.write_text(json.dumps(
                {"subcategories": subcats, "fetched_at": datetime.now(timezone.utc).isoformat()},
                indent=2,
            ))
        target = normalize_char_name(character_name)
        for entry in subcats:
            if normalize_char_name(entry["name"]) == target:
                return entry["id"], None
        return None, None

    def gb_browse(self, character_name, page=1, sort="most_liked"):
        """Lists mods from this character's GameBanana subcategory (paginated,
        sorted server-side by GameBanana), so the user can pick one without
        leaving the app."""
        sub_id, err = self._gb_subcategory_id(character_name)
        if err or sub_id is None:
            return {"error": err, "subcategory_id": None, "records": [], "total": 0, "is_complete": True, "page": page}
        try:
            result = gamebanana_api.browse_category(sub_id, page=page, sort=sort)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "subcategory_id": sub_id, "records": [], "total": 0, "is_complete": True, "page": page}
        if not self._load_settings().get("show_nsfw", False):
            result["records"] = [r for r in result["records"] if not r.get("has_content_ratings")]
        result["error"] = None
        result["subcategory_id"] = sub_id
        return result

    _GB_PREFETCH_DELAY = 1.0   # seconds a card has to stay open before anything is fetched for it (flicking through cards fetches nothing)

    def gb_prefetch(self, category, item_name):
        """Fetches the first page of the Browse GameBanana list for a card (a character, course, vehicle part or item) in the
        background, so the window opens with it already there: the page itself is kept (gamebanana_api's page cache) and so are the
        descriptions it needs (the description cache). Called when a card opens. Returns at once. It waits a moment first, only ever
        works on the newest card, and fetches a given list once (it is shared by every part of a kind) for a few minutes - flicking
        through cards doesn't pile up requests. Asks for what the window would: the saved sort, the same page, descriptions included."""
        with self._prefetch_lock:
            self._prefetch_pending = (category, item_name)
            if self._prefetch_busy:
                return {"started": False}   # (the running worker takes the newest request when it is done)
            self._prefetch_busy = True
        threading.Thread(target=self._prefetch_worker, daemon=True, name="gb-prefetch").start()
        return {"started": True}

    def _prefetch_worker(self):
        while True:
            time.sleep(self._GB_PREFETCH_DELAY)
            with self._prefetch_lock:
                request, self._prefetch_pending = self._prefetch_pending, None
                if request is None:
                    self._prefetch_busy = False
                    return
            try:
                self._prefetch_one(*request)
            except Exception:   # (an optimisation: whatever goes wrong here, the window just asks for itself)
                pass

    def _browse_sort(self, tagged):
        """The sort the Browse window starts on: the one the user picked last, else the kind's own default (see gb-browse.js)."""
        saved = self._load_settings().get("gb_browse_sort")
        return saved if saved in gamebanana_api.SORT_ALIASES else ("most_viewed" if tagged else "most_liked")

    def _prefetch_one(self, category, item_name):
        tagged = category in VEHICLE_SECTIONS or category == ITEMS_CATEGORY
        sort = self._browse_sort(tagged)
        if category == "characters":
            key = ("characters", item_name)
        elif category == "courses":
            key = ("courses", item_name)
        elif category == ITEMS_CATEGORY:
            key = ("items", sort)   # (one list for every item)
        elif category in VEHICLE_SECTIONS:
            section, item = self._vehicle_item(item_name)
            if item is None:
                return
            key = ("vehicles", self._vehicle_gb_category_id(section, item), sort)   # (one list per kind of part)
        else:
            return
        now = time.monotonic()
        with self._prefetch_lock:
            if now - self._prefetched.get(key, -1e9) < gamebanana_api.PAGE_CACHE_TTL:
                return
            self._prefetched[key] = now
        if category == "characters":
            self.gb_browse(item_name, 1, sort)
        elif category == "courses":
            self.gb_browse_course(item_name, 1)
        elif category == ITEMS_CATEGORY:
            self.gb_browse_item(item_name, 1, sort)
        else:
            self.gb_browse_vehicle(item_name, 1, sort)

    def gb_browse_course(self, course_name, page=1, quick=False):
        """Courses have no per-item GameBanana subcategory the way characters
        do, so this searches by the base course name instead (stripped of any
        platform prefix) and filters to the course-editing subcategories.
        Each call reads a few search pages at once (see search_course_mods) and
        gives the one to ask for next as `next_page`; every mod comes with a
        snippet of its description (around the course's name where it has it)
        and whether the course is named in its title or description. quick=True answers at once with only the descriptions
        already remembered (`pending` says more is to come); the same call without it fills in the rest."""
        query = strip_course_prefix(course_name)
        try:
            result = gamebanana_api.search_course_mods(query, first_page=page)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "records": [], "total": 0, "done": True, "page": page, "query": query}
        records = result["records"]
        if not self._load_settings().get("show_nsfw", False):
            records = [r for r in records if not r.get("has_content_ratings")]
        descriptions = self._descriptions(records, workers=4, wait=not quick)
        needle = query.lower()
        for rec in records:
            desc = descriptions[rec["mod_id"]]
            rec["described"] = desc is not None
            rec["description_snippet"] = gamebanana_api.snippet_around(desc or "", query)
            rec["mentions_course"] = bool(needle) and needle in f"{rec['name']} {desc or ''}".lower()
        result["records"] = records
        result["error"] = None
        result["query"] = query
        result["pending"] = self._still_pending(records, quick)
        return result

    def _search_kind(self, rec, characters):
        """What kind of mod a search result is, from the GameBanana category it is filed in: ("characters", the character's
        roster name), ("courses"|"vehicles"|"items"|<a simple category's key>, None), ("skin_packs"|"skin_misc", None) for
        Skins' Packs / Other/Misc, or ("other", None). Only the author's own filing - the files can still say otherwise, which the download checks (see _refile_mod)."""
        sub_id, root_id = rec.get("subcategory_id"), rec.get("root_category_id")
        if sub_id is not None and (sub_id in VEHICLE_BODY_CATEGORY_IDS.values() or sub_id == VEHICLES_CATEGORY_ID or any(
                info.get("gb_category_id") == sub_id for info in VEHICLE_SECTIONS.values())):
            return "vehicles", None
        if sub_id == ITEMS_GB_CATEGORY_ID:
            return "items", None
        if rec.get("subcategory") in gamebanana_api.COURSE_SEARCH_SUBCATEGORIES:
            return "courses", None
        for key, info in SIMPLE_MOD_CATEGORIES.items():
            if info["gb_category_id"] in (sub_id, root_id):
                return key, None
        if sub_id == SKINS_PACKS_CATEGORY_ID:
            return "skin_packs", None
        if sub_id == SKINS_MISC_CATEGORY_ID:
            return "skin_misc", None
        if rec.get("subcategory"):
            wanted = normalize_char_name(rec["subcategory"])
            match = next((name for name in characters if normalize_char_name(name) == wanted), None)
            if match:
                return "characters", match
        return "other", None

    def gb_search(self, category, query, page=1, quick=False):
        """Searches GameBanana (all of Mario Kart 8 Deluxe) for `query` from the Browse window of a card of `category`
        (characters / courses / a vehicle section / items / a simple category). Only the kind of mod that card is for is
        kept - a search for "odyssey" from a character's card lists character mods (of any character: the mod is moved
        to the right one when it is downloaded, see _refile_mod). Like gb_browse_course, one call reads a few search pages at once and gives the one to ask for next as
        `next_page`. Each mod comes with the kind it is filed as (`kind`, and `character` for a character), a snippet of its
        description around the query, and - for vehicle parts and items - the parts / items it looks like it replaces."""
        query = (query or "").strip()
        if not query:
            return {"error": None, "records": [], "total": 0, "done": True, "page": page, "query": query}
        wanted = "vehicles" if category in VEHICLE_SECTIONS else category
        # the kinds a card's search keeps: its own, plus Skins' packs and misc for the kinds those can be for
        accepted = {wanted} | ({"skin_packs", "skin_misc"} if wanted in ("characters", "vehicles", "items") else {"skin_packs"} if wanted == "modpacks" else set())
        characters = self._load_roster()
        kinds = {}

        def keep(rec):
            kinds[rec["mod_id"]] = self._search_kind(rec, characters)
            return kinds[rec["mod_id"]][0] in accepted

        try:
            result = gamebanana_api.search_filtered(query, keep, first_page=page)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "records": [], "total": 0, "done": True, "page": page, "query": query}
        records = result["records"]
        if not self._load_settings().get("show_nsfw", False):
            records = [r for r in records if not r.get("has_content_ratings")]
        for rec in records:
            rec["kind"], rec["character"] = kinds[rec["mod_id"]]
        # vehicle parts and items are tagged with what they look like they replace, by the roster of the mod's own kind
        # (a tire mod found from a kart's card is read against the tires)
        vehicles = self._load_vehicle_roster()
        groups = {}
        for rec in records:
            if rec["kind"] == "vehicles":
                sub_id = rec.get("subcategory_id")
                section = next((k for k, info in VEHICLE_SECTIONS.items() if sub_id and info.get("gb_category_id") == sub_id), "vehicles")
                groups.setdefault(section, (vehicles[section], []))[1].append(rec)
            elif rec["kind"] == "items":
                groups.setdefault(ITEMS_CATEGORY, (self._load_item_roster(), []))[1].append(rec)
        for section, (roster, recs) in groups.items():
            self._annotate_targets(section, roster, recs, wait=not quick)
        descriptions = self._descriptions(records, workers=4, wait=not quick)
        for rec in records:
            desc = descriptions[rec["mod_id"]]
            rec["described"] = desc is not None
            rec["description_snippet"] = gamebanana_api.snippet_around(desc or "", query)
        result["records"] = records
        result["error"] = None
        result["query"] = query
        result["pending"] = self._still_pending(records, quick)
        return result

    def gb_browse_simple(self, category_key, page=1, sort="most_liked"):
        """Browses a whole "simple" category (see SIMPLE_MOD_CATEGORIES)
        directly by its GameBanana category id - unlike characters, these
        have no per-item subcategory to resolve first, and unlike courses,
        Mod/Index's category filter already returns every mod filed under
        any subcategory beneath it (verified live), so this is a plain,
        one-call browse."""
        info = SIMPLE_MOD_CATEGORIES.get(category_key)
        if info is None:
            return {"error": f"Unknown category '{category_key}'.", "records": [], "total": 0, "is_complete": True, "page": page}
        try:
            result = gamebanana_api.browse_category(info["gb_category_id"], page=page, sort=sort)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "records": [], "total": 0, "is_complete": True, "page": page}
        if not self._load_settings().get("show_nsfw", False):
            result["records"] = [r for r in result["records"] if not r.get("has_content_ratings")]
        result["error"] = None
        return result

    def _guess_course_targets(self, mod_name, mod_description):
        """Best-effort guess at which course(s) a course-category mod is
        for, by matching roster.json course names (with any platform prefix
        stripped, same as gb_browse_course()) against the mod's own title
        first, falling back to its description. Returns up to 5 candidate
        course names, title matches and longer (more specific) names first -
        this is only ever a starting point for gb_identify_mod() to suggest,
        never applied without the user confirming it themselves."""
        name_text = mod_name or ""
        desc_text = mod_description or ""
        candidates = []
        for cup in self._load_course_roster():
            for course in cup["courses"]:
                base = strip_course_prefix(course["name"])
                pattern = re.compile(re.escape(base), re.IGNORECASE)
                if pattern.search(name_text):
                    candidates.append((0, len(base), course["name"]))
                elif pattern.search(desc_text):
                    candidates.append((1, len(base), course["name"]))
        candidates.sort(key=lambda c: (c[0], -c[1]))
        seen = set()
        result = []
        for _, _, name in candidates:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result[:5]

    def gb_identify_mod(self, mod_id_or_url):
        """Fetches a mod's metadata and makes a best-effort guess at what to
        track it as - the first step of the "Add a mod" flow (see
        #add-mod-modal in ui/html/add-mod-modal.html and ui/js/add-mod.js), reachable from the Full List tab for
        mods that don't obviously belong to a specific character/course grid
        tile. Unlike gb_fetch_mod(), this doesn't persist anything; it's a
        read-only lookup the frontend uses to propose a target before the
        user confirms (or overrides) it.

        Character mods classify with certainty - GameBanana puts every
        MK8DX character mod in a subcategory literally named after the
        character, one level under the "Characters" supercategory
        (id 10529, CHARACTERS_CATEGORY_ID), so category_id + roster
        membership together are conclusive, not a guess. Course mods have
        no such per-course category, so the target is only ever a guess
        from _guess_course_targets() - always surfaced as a suggestion to
        confirm, never auto-applied."""
        try:
            record_type, mod_id = gamebanana_api.parse_mod_ref(mod_id_or_url)
            detail = gamebanana_api.fetch_mod_detail(mod_id, record_type)
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}

        roster = self._load_roster()
        guess_category = None
        guess_target = None
        course_candidates = []

        cat_name = detail.get("category_name")
        cat_id = detail.get("category_id")
        super_cat_id = detail.get("super_category_id")
        simple_key = next(
            (key for key, info in SIMPLE_MOD_CATEGORIES.items()
             if info["gb_category_id"] in (cat_id, super_cat_id)),
            None,
        )
        is_item_mod = ITEMS_GB_CATEGORY_ID in (cat_id, super_cat_id)
        if super_cat_id == CHARACTERS_CATEGORY_ID and cat_name:
            match = next(
                (name for name in roster if normalize_char_name(name) == normalize_char_name(cat_name)),
                None,
            )
            if match:
                guess_category = "characters"
                guess_target = match
        elif cat_name in gamebanana_api.COURSE_SEARCH_SUBCATEGORIES:
            guess_category = "courses"
            course_candidates = self._guess_course_targets(detail["name"], detail["description"])
            guess_target = course_candidates[0] if course_candidates else None
        elif self._vehicle_section_for_category(cat_id) is not None or cat_id == VEHICLES_CATEGORY_ID:
            # A vehicle-part mod: the GameBanana category names the SECTION
            # (bodies / tires / gliders), but not which part - that has to be
            # read from the description (see match_vehicle_targets), so it's
            # only ever a suggestion. A mod filed directly in "Vehicles" with
            # no subcategory could be any section: try them all, best score wins.
            vehicle_roster = self._load_vehicle_roster()
            section = self._vehicle_section_for_category(cat_id)
            sections_to_try = [section] if section else list(VEHICLE_SECTIONS)
            best = None  # (score, section, item name)
            for sec in sections_to_try:
                for name, score in match_vehicle_targets(
                    sec, vehicle_roster[sec], detail["name"], detail["description"]
                ):
                    if best is None or score > best[0]:
                        best = (score, sec, name)
            # No match and no section either (filed directly in Vehicles):
            # still unmistakably a vehicle-part mod, just of an unknown part -
            # "vehicle_unsorted" tells the UI so, instead of it falling back to
            # its generic "couldn't tell what this is" message.
            guess_category = best[1] if best else (section or "vehicle_unsorted")
            guess_target = best[2] if best else None
        elif is_item_mod:
            # An item mod: the category is the one flat "Items" category, so which item is read from the text (a suggestion
            # only, like a vehicle part's); the catch-all when nothing names one - or several do (an item pack).
            matches = match_vehicle_targets("items", self._load_item_roster(), detail["name"], detail["description"])
            guess_category = ITEMS_CATEGORY
            guess_target = matches[0][0] if len(matches) == 1 else ITEMS_OTHER
        elif simple_key is not None:
            # Some of these (Mechanics, Items) file mods directly at the
            # category itself (category_id matches), others (UI) have real
            # subcategories underneath and file mods there instead
            # (super_category_id matches) - checked above, either way there's
            # exactly one fixed target, no further guessing needed.
            guess_category = simple_key
            guess_target = SIMPLE_MOD_CATEGORIES[simple_key]["label"]

        return {
            "success": True,
            "mod": detail,
            "guess_category": guess_category,
            "guess_target": guess_target,
            "course_candidates": course_candidates,
            "all_characters": roster,
            "all_courses": [c["name"] for cup in self._load_course_roster() for c in cup["courses"]],
            "all_items": [i["name"] for i in self._load_item_roster()] + [ITEMS_OTHER],
            "all_vehicle_parts": [
                {"section": key, "label": VEHICLE_SECTIONS[key]["label"], "items": [i["name"] for i in items]}
                for key, items in self._load_vehicle_roster().items()
            ],
            # Where each file of a vehicle mod probably belongs (see
            # suggest_file_targets) - lets the UI offer "file each to its own
            # part" for mods whose files target different parts.
            "file_suggestions": (
                suggest_file_targets(
                    detail["files"], detail["name"], detail["description"], self._load_vehicle_roster(),
                    self._vehicle_section_for_category(cat_id),
                )
                if guess_category in VEHICLE_SECTIONS or guess_category == "vehicle_unsorted"
                else []
            ),
        }

    @staticmethod
    def _vehicle_section_for_category(category_id):
        """Which vehicle-part section a GameBanana category id belongs to
        (None if it isn't one of the section categories)."""
        if category_id in VEHICLE_BODY_CATEGORY_IDS.values():
            return "vehicles"
        for key, info in VEHICLE_SECTIONS.items():
            if info.get("gb_category_id") == category_id:
                return key
        return None

    def _vehicle_gb_category_id(self, section, item):
        if section == "vehicles":
            return VEHICLE_BODY_CATEGORY_IDS.get(
                (item.get("type"), item.get("bike_class") if item.get("type") == "bike" else None)
            )
        return VEHICLE_SECTIONS[section]["gb_category_id"]

    def gb_browse_vehicle(self, item_name, page=1, sort="most_viewed", quick=False):
        """Browses the GameBanana category that holds this vehicle part's
        kind of mod (bodies by type: Kart / Bikes Outward|Inward / ATVs; tires;
        gliders) - there's no per-part subcategory, so every mod of that kind
        is listed, each annotated with the part(s) its description says it
        replaces (see match_vehicle_targets) so the caller can highlight or
        filter to likely matches. Descriptions cost one GameBanana request per
        mod, so only this page's uncached ones are fetched, a few at a time -
        GameBanana rate-limits bursts (HTTP 429), and any mod whose
        description can't be fetched just falls back to title-only matching."""
        section, item = self._vehicle_item(item_name)
        if item is None:
            return {"error": f"Unknown vehicle part '{item_name}'.", "records": [], "total": 0,
                    "is_complete": True, "page": page, "per_page": 15, "subcategory_id": None}
        cat_id = self._vehicle_gb_category_id(section, item)
        try:
            result = gamebanana_api.browse_category(cat_id, page=page, sort=sort)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "records": [], "total": 0, "is_complete": True, "page": page,
                    "per_page": 15, "subcategory_id": cat_id}
        seen = set()
        records = []
        for rec in result["records"]:  # GameBanana can repeat a mod within a listing
            if rec["mod_id"] not in seen:
                seen.add(rec["mod_id"])
                records.append(rec)
        if not self._load_settings().get("show_nsfw", False):
            records = [r for r in records if not r.get("has_content_ratings")]
        self._annotate_vehicle_targets(section, records, wait=not quick)
        result["records"] = records
        result["error"] = None
        result["subcategory_id"] = cat_id
        result["target_name"] = item_name
        result["pending"] = self._still_pending(records, quick)
        return result

    def gb_browse_item(self, item_name, page=1, sort="most_viewed", quick=False):
        """Browses GameBanana's one flat Items category for an item's card. Like a vehicle part's browse, every item mod is
        listed and each is annotated with the item(s) its text says it replaces (`targets`), so the card can mark the likely
        matches. The catch-all ("Other items") is any item mod at all."""
        try:
            result = gamebanana_api.browse_category(ITEMS_GB_CATEGORY_ID, page=page, sort=sort)
        except gamebanana_api.GameBananaError as e:
            return {"error": str(e), "records": [], "total": 0, "is_complete": True, "page": page,
                    "per_page": 15, "subcategory_id": ITEMS_GB_CATEGORY_ID}
        seen = set()
        records = []
        for rec in result["records"]:  # GameBanana can repeat a mod within a listing
            if rec["mod_id"] not in seen:
                seen.add(rec["mod_id"])
                records.append(rec)
        if not self._load_settings().get("show_nsfw", False):
            records = [r for r in records if not r.get("has_content_ratings")]
        self._annotate_targets("items", self._load_item_roster(), records, wait=not quick)
        result["records"] = records
        result["error"] = None
        result["subcategory_id"] = ITEMS_GB_CATEGORY_ID
        result["target_name"] = item_name
        result["pending"] = self._still_pending(records, quick)
        return result

    def _annotate_vehicle_targets(self, section, records, wait=True):
        self._annotate_targets(section, self._load_vehicle_roster()[section], records, wait=wait)

    @staticmethod
    def _still_pending(records, quick):
        """For a quick browse answer: whether some mod's description wasn't remembered, so a second call (quick=False) has
        something to add - matching, snippets and the "likely" filter all read the description."""
        return bool(quick) and any(not r.get("described") for r in records)

    def _descriptions(self, records, workers=3, wait=True):
        """{mod id: description text, or None if it couldn't be fetched} for a list of browse records. A browse list has no
        descriptions, so each costs one GameBanana request - only the ones not seen before are fetched, a few at a time
        (GameBanana rate-limits bursts with HTTP 429). With wait=False nothing is fetched: only what is already remembered
        comes back (the rest is None), so a list can be shown at once and finished by a second, waiting, call."""
        cache = self._gb_desc_cache
        store = self._gb_desc_store   # (the same descriptions kept on disk, so a restart doesn't fetch them all again)
        for r in records:
            if r["mod_id"] not in cache:
                saved = store.get(r["mod_id"])
                if saved is not None:
                    cache[r["mod_id"]] = saved
        todo = [r for r in records if r["mod_id"] not in cache] if wait else []

        def fetch(rec):
            try:
                return rec["mod_id"], gamebanana_api.fetch_mod_detail(rec["mod_id"])["description"]
            except gamebanana_api.GameBananaError:
                return rec["mod_id"], None

        if todo:
            fetched = {}
            with self._desc_fetch_lock, ThreadPoolExecutor(max_workers=workers) as pool:   # (one batch at a time: the rate limit)
                todo = [r for r in todo if r["mod_id"] not in cache]   # (another call may have fetched some while this one waited)
                for mod_id, desc in pool.map(fetch, todo):
                    if desc is not None:
                        cache[mod_id] = fetched[mod_id] = desc
            store.put_many(fetched)
        return {r["mod_id"]: cache.get(r["mod_id"]) for r in records}

    def _annotate_targets(self, section, items, records, wait=True):
        descriptions = self._descriptions(records, wait=wait)
        for rec in records:
            desc = descriptions[rec["mod_id"]]
            matches = match_vehicle_targets(section, items, rec["name"], desc or "")
            rec["targets"] = [name for name, _score in matches]
            rec["target_strength"] = matches[0][1] if matches else 0
            rec["described"] = desc is not None
            rec["description_snippet"] = gamebanana_api.snippet_around(desc or "", "")

    def gb_fetch_mod(self, character_name, mod_id_or_url):
        """Fetches (or re-fetches) a mod's metadata from GameBanana and stores
        it under this character, preserving any already-known download status
        for files that still exist on the mod."""
        try:
            record_type, mod_id = gamebanana_api.parse_mod_ref(mod_id_or_url)
            detail = gamebanana_api.fetch_mod_detail(mod_id, record_type)
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}

        # Character-roster cross-check only - course names don't collide the
        # same way, and applying character names as the candidate list to a
        # course would just produce nonsense hints.
        roster = self._load_roster()
        if character_name in roster:
            flag_cross_character_files(detail["files"], character_name, roster)

        gb_mods = self._load_gb_mods()
        char_mods = gb_mods.setdefault(character_name, [])
        # Mod and Sound ids are independent counters - matching on id alone
        # could collide with an unrelated record of the other type, so both
        # fields have to agree.
        existing = next(
            (m for m in char_mods if m["mod_id"] == mod_id and m.get("record_type", "Mod") == record_type),
            None,
        )
        prev_files = {f["file_id"]: f for f in existing["files"]} if existing else {}

        files_payload = []
        for f in detail["files"]:
            prev = prev_files.get(f["file_id"])
            files_payload.append({
                **f,
                "download_status": prev["download_status"] if prev else "not_downloaded",
                "downloaded_to": prev.get("downloaded_to") if prev else None,
                # Everything else recorded when this file was downloaded is
                # still true after a re-fetch of the mod's metadata - dropping
                # it silently lost the slot/music mismatch warnings and the
                # archive location (which moving a mod needs).
                **{k: prev[k] for k in ("archive_path", "slot_mismatch", "music_mismatch") if prev and k in prev},
            })

        record = {
            "mod_id": mod_id,
            "record_type": record_type,
            "name": detail["name"],
            "description": detail["description"],
            "description_runs": detail.get("description_runs", []),
            "profile_url": detail["profile_url"],
            "thumbnail_url": detail["thumbnail_url"],
            "thumbnail_url_large": detail.get("thumbnail_url_large"),
            "screenshots": detail.get("screenshots", []),
            "author": detail.get("author"),
            "version": detail.get("version"),
            "updated_at": detail.get("updated_at"),
            "download_count": detail.get("download_count", 0),
            "view_count": detail.get("view_count", 0),
            "like_count": detail.get("like_count", 0),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "game_id": detail.get("game_id"),
            "game_name": detail.get("game_name"),
            "files": files_payload,
        }

        if existing:
            char_mods[char_mods.index(existing)] = record
        else:
            char_mods.append(record)
        self._save_gb_mods(gb_mods)
        return {"success": True, "mod": record}

    def gb_preview_mod(self, mod_id):
        """Read-only mod detail fetch for the browse-grid preview modal -
        deliberately does NOT persist anything, so idly previewing mods while
        browsing doesn't clutter the tracked-mods list. Only gb_fetch_mod
        (triggered by "Use this mod") actually records a mod."""
        try:
            detail = gamebanana_api.fetch_mod_detail(mod_id)
            return {"success": True, "mod": detail}
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}

    def gb_get_saved_mods(self, character_name):
        return self._load_gb_mods().get(character_name, [])

    def gb_remove_mod(self, character_name, mod_id, record_type="Mod"):
        gb_mods = self._load_gb_mods()
        char_mods = gb_mods.get(character_name, [])
        gb_mods[character_name] = [
            m for m in char_mods
            if not (m["mod_id"] == mod_id and m.get("record_type", "Mod") == record_type)
        ]
        self._save_gb_mods(gb_mods)
        return True

    def gb_open_url(self, url):
        """Opens a GameBanana profile URL in the user's default browser, so
        clicking a mod name doesn't navigate this app's own window away."""
        if not re.match(r"^https?://(www\.)?gamebanana\.com/", url):
            return {"success": False, "error": "Refusing to open a non-GameBanana URL."}
        try:
            webbrowser.open(url)
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": f"Couldn't open a browser. Details: {e}"}

    def open_external_url(self, url):
        """Opens a link from a mod's description (a video, a Discord invite, the author's page...) in the user's default
        browser. Any http(s) address - the user clicked it, and it is shown to them (as the link's tooltip) first - but
        nothing else (no file:, no javascript:)."""
        if not isinstance(url, str) or len(url) > 2000 or not re.match(r"^https?://[^\s]+$", url, re.IGNORECASE):
            return {"success": False, "error": "Refusing to open that link."}
        try:
            webbrowser.open(url)
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": f"Couldn't open a browser. Details: {e}"}

    def open_help_link(self, url):
        """Opens one of the Help page's own curated reference links in the
        user's default browser - restricted to an allowlist of the specific
        documentation domains those links actually point at, same idea as
        gb_open_url(), not a general "open any URL" method."""
        if not re.match(r"^https://(www\.)?(gamebanana\.com|mkwiiki\.org|docs\.google\.com)/", url):
            return {"success": False, "error": "Refusing to open an untrusted URL."}
        try:
            webbrowser.open(url)
            return {"success": True}
        except OSError as e:
            return {"success": False, "error": f"Couldn't open a browser. Details: {e}"}

    @mutates_library
    def _download_and_extract_one(self, category, item_name, mod_name, file_entry):
        # Nested by item ("<category>/<item>/<mod>") rather than the old flat
        # "<item> - <mod>" naming - see "Folder naming" in docs/architecture.md.
        # item_name itself is sanitized here (unlike mod_name it was never
        # sanitized under the old flat scheme, since it was never the last -
        # and therefore never the trailing-dot/space-sensitive - path segment
        # until now; see sanitize_filename()'s own docstring for why that
        # matters, e.g. "Bowser Jr.").
        item_folder_name = sanitize_filename(item_name)
        mod_folder_name = sanitize_filename(mod_name)
        # Captured before anything is touched: if this exact tracked file was
        # already downloaded once (the author pushed an update, or this is
        # just a re-click), its previous extracted folder/archive is only
        # retired once the new download has fully succeeded below - so a
        # failed re-download (bad archive, network error, ...) never destroys
        # a previously-good copy.
        old_folder = file_entry.get("downloaded_to")
        old_archive = file_entry.get("archive_path")

        downloads_dir = self.mod_root / MODS_DIRNAME / DOWNLOADS_DIRNAME / category / item_folder_name
        downloads_dir.mkdir(parents=True, exist_ok=True)
        archive_path = unique_path(downloads_dir / file_entry["name"])

        gamebanana_api.download_file(
            file_entry["download_url"], archive_path,
            expected_size=file_entry["size"], expected_md5=file_entry.get("md5"),
        )

        item_dir = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / category / item_folder_name
        item_dir.mkdir(parents=True, exist_ok=True)
        preferred_dest = item_dir / mod_folder_name
        name_collided = preferred_dest.exists()
        dest_folder = unique_dir_path(preferred_dest)
        gamebanana_api.extract_archive(archive_path, dest_folder)

        # Collapse a pre-packaged "atmosphere/contents/<TITLE_ID>/" wrapper
        # (see fix_atmosphere_wrapper) before find_mod_units() ever runs, so
        # unit keys are never built from it in the first place.
        fix_atmosphere_wrapper(dest_folder)

        # Fold any stray Course/MapObj sitting next to an already-real romfs/
        # into that romfs/ before find_mod_units() ever runs - otherwise the
        # existing romfs/ (even a near-empty one) reads as "this download
        # succeeded" and the actual course content next to it never gets a
        # second look.
        fix_stray_course_content(dest_folder)

        # find_mod_units() already walks the whole tree looking for every
        # romfs-containing folder, however deep - a multi-variant pack (e.g.
        # separate "over Mario"/"over Metal Mario"/... slot options, a very
        # common GameBanana convention) is just as usable as a single
        # root-level romfs, and shows up fine as multiple selectable units in
        # "Mods to merge". The only real failure is finding no romfs at all
        # anywhere, which does need a human to go look at what the archive
        # actually contained.
        units = find_mod_units(dest_folder)
        # Missing-romfs-wrapper is mechanically fixable - once Driver/Kart/...
        # has been found, there's no ambiguity about where romfs/ belongs, so
        # just fix it rather than making the user do it by hand. (Skip if it
        # looks like a ui_assets dump instead - that content genuinely isn't
        # a mergeable mod, no wrapper would make it one.)
        if not units and not looks_like_ui_assets(dest_folder) and looks_like_missing_romfs_wrapper(dest_folder):
            fix_missing_romfs_wrapper(dest_folder)
            units = find_mod_units(dest_folder)

        # Course-mod-specific counterparts to the fix above - see their own
        # docstrings for why each is safe to apply unconditionally.
        if not units and not looks_like_ui_assets(dest_folder) and looks_like_bare_course_wrapper(dest_folder):
            fix_bare_course_wrapper(dest_folder)
            units = find_mod_units(dest_folder)

        # A course's files with no folder named for it at all ("Retextured" mods with just course_model.szs): the course
        # this was downloaded for says where they go - see fix_loose_course_files(). (Before the next fix, which would take
        # a wrapper folder's own name for the course id.)
        if not units and category == "courses" and not looks_like_ui_assets(dest_folder):
            slots = self._course_internal_names(item_name)
            if slots and len(slots) == 1 and fix_loose_course_files(dest_folder, next(iter(slots)), self._course_names_by_internal()):
                units = find_mod_units(dest_folder)

        if not units and not looks_like_ui_assets(dest_folder):
            if fix_bare_course_slot(dest_folder):
                units = find_mod_units(dest_folder)

        # ...and the item-mod counterpart: loose ItemXxx.bfres/.bars files
        # with no folders at all - see fix_loose_item_files().
        if not units and not looks_like_ui_assets(dest_folder):
            if fix_loose_item_files(dest_folder):
                units = find_mod_units(dest_folder)

        # ...and loose vehicle-part .szs files (BodyK_Cat.szs, Wing_Pap.szs, ...).
        if not units and not looks_like_ui_assets(dest_folder):
            if fix_loose_kart_parts(dest_folder):
                units = find_mod_units(dest_folder)

        # ...and a character's own loose files (<Slot>.szs, Driver_<Slot>.bars, MenuDriver_<Slot>.bars).
        if not units and not looks_like_ui_assets(dest_folder):
            if fix_loose_character_files(dest_folder):
                units = find_mod_units(dest_folder)

        # exefs code patches (.ips) are mergeable units too - see
        # find_exefs_units(). Deliberately checked only AFTER every romfs
        # fixer above has had its chance, and kept out of `units`: a mod
        # shipping both a patch and a mis-wrapped romfs must still get its
        # romfs fixed (those fixers only fire while `units` is empty).
        exefs_units = find_exefs_units(dest_folder)

        # A second download that landed on a "(2)"-suffixed name only because
        # something else under this item already owns the plain one, and turns
        # out to ship nothing mergeable but loose icon pictures for this
        # character, is almost always a "UI icons" companion pack rather than
        # just another copy of the same mod - see ui_setup.gather_auto_icons(),
        # which folds exactly this kind of download into the character's
        # auto-picked icon regardless of whether anything is ticked. Name it
        # for what it is instead of a bare "(2)", so its tile-icon tooltip and
        # Menu Look source label are self-explanatory rather than looking like
        # an accidental duplicate.
        if name_collided and category == "characters" and not units and not exefs_units:
            code = ui_setup.code_for_character(item_name)
            if code and ui_setup.find_loose_icon_sets(dest_folder, code):
                dest_folder = dest_folder.rename(unique_dir_path(item_dir / f"{mod_folder_name} (icon pictures)"))

        slot_mismatch = None
        music_mismatch = None
        if units or exefs_units:
            status = "downloaded"
            # Cross-check against roster.json's known internal slot
            # id(s) for this course, when we have one on file - this is what
            # would have caught "GCN Waluigi Stadium"'s mod actually writing
            # to DS Wario Stadium's slot (Course/Gds_WarioStadium/) at
            # download time instead of only via a conflict against another
            # mod later. A course with no known id yet, or a download with
            # no "Course/" folder at all (a MapObj-only skybox addon, say),
            # simply isn't checked - this only ever flags a definite,
            # verifiable disagreement, never a guess.
            if units and category == "courses":
                slot_mismatch = self._course_slot_mismatch(item_name, dest_folder)
                # Same idea, independently, for bundled race music - a mod
                # can get its Course/ folder right and still ship someone
                # else's BGM (or vice versa), so this isn't gated on
                # slot_mismatch being clear first. Most mods bundle no music
                # at all (find_course_music_slugs() returns empty then),
                # which is never treated as suspicious - only an actual,
                # confirmed *other* course's music id is.
                expected_music = self._course_music_slugs(item_name)
                if expected_music:
                    actual_music = find_course_music_slugs(dest_folder)
                    if actual_music and not (actual_music & expected_music):
                        music_mismatch = {"expected": sorted(expected_music), "found": sorted(actual_music)}
            elif units and category == "characters":
                # The driver model / voice files a character mod ships name the character
                # they replace; a download whose files are all for OTHER characters is
                # flagged (one that includes this character's own among others isn't).
                slot_mismatch = self._character_slot_mismatch(item_name, dest_folder)
            elif units and category == ITEMS_CATEGORY:
                slot_mismatch = self._item_slot_mismatch(item_name, dest_folder)
            elif units and category in VEHICLE_SECTIONS:
                # Same idea for vehicle parts: the model files a mod actually
                # ships (BodyK_Cat.szs, Wing_Pap.szs, TireK_Zst.szs) name the
                # exact part they replace, so a download whose files of this
                # part's kind don't include this item's own is flagged - it
                # probably belongs under a different row. A pack that ships
                # this item's file among others isn't flagged.
                slot_mismatch = self._vehicle_slot_mismatch(item_name, dest_folder)
        elif looks_like_missing_romfs_wrapper(dest_folder):
            # Checked before looks_like_ui_assets() - a Driver/Kart/Audio/...
            # folder is a specific, actionable diagnosis ("one folder-move
            # away from working"), and takes priority even when the tree
            # also happens to contain a nested common/menu folder somewhere
            # (a course mod that bundles a small UI update alongside real
            # track data, for instance - genuinely mergeable content, not a
            # UI-only dump). The auto-fix attempt above already declined to
            # touch this case (it also requires not-ui_assets), so this is
            # purely about giving the user the more accurate label to act on.
            status = "missing_romfs"
        elif looks_like_ui_assets(dest_folder) or (category == "ui" and looks_like_ui_art(dest_folder)):
            status = "ui_assets"
        else:
            status = "needs_manual_fix"

        # The new download succeeded - now safe to retire whatever this
        # exact tracked file previously pointed at, and reclaim ITS OWN old
        # slot for the new copy (not necessarily the plain un-suffixed name -
        # if this file was already living at a "(2)"-suffixed name because a
        # *different* file under the same mod, like a companion "ui-" icon
        # dump, owns the plain one, that's still its rightful slot, and
        # reusing it is what keeps a repeated re-download from creeping up
        # through "(3)", "(4)", ... every time instead of settling back to
        # the same folder). A first-ever download (old_folder is None) has no
        # old slot to reclaim, so it just keeps whatever unique_dir_path()
        # already gave it above.
        self._retire_previous_download(old_folder, old_archive)
        if old_folder:
            reclaim_folder = Path(old_folder)
            if dest_folder != reclaim_folder and not reclaim_folder.exists():
                dest_folder = dest_folder.rename(reclaim_folder)
        if old_archive:
            reclaim_archive = Path(old_archive)
            if archive_path != reclaim_archive and not reclaim_archive.exists():
                archive_path = archive_path.rename(reclaim_archive)

        return {
            "status": status,
            "downloaded_to": str(dest_folder),
            "archive_path": str(archive_path),
            "slot_mismatch": slot_mismatch,
            "music_mismatch": music_mismatch,
        }

    @mutates_library
    def _retire_previous_download(self, old_folder_str, old_archive_str):
        """Deletes a file's previous extracted folder/archive - called only
        after its replacement has already downloaded and extracted
        successfully (see _download_and_extract_one) - along with any
        mod-manager-state.json checked-unit keys that pointed into the old
        folder, so re-downloading a tracked file never leaves an orphaned
        duplicate next to the new copy, nor a stale checked reference to a
        folder that's now gone."""
        if old_folder_str:
            old_folder = Path(old_folder_str)
            if old_folder.is_dir():
                shutil.rmtree(old_folder, ignore_errors=True)
            extracted_root = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
            try:
                rel = old_folder.relative_to(extracted_root)
            except ValueError:
                pass
            else:
                self._clear_state_prefix(rel.as_posix())
        if old_archive_str:
            old_archive = Path(old_archive_str)
            if old_archive.is_file():
                try:
                    old_archive.unlink()
                except OSError:
                    pass

    def _clear_state_prefix(self, prefix):
        """Deletes every mod-manager-state.json checked-unit key at or under
        `prefix` (a "category/item/mod" string) - shared by remove_mod_unit()
        and _retire_previous_download() so removing a mod's files from disk
        never leaves a stale checked reference to a folder that's gone."""
        def clear(state):
            gone = [k for k in state if k == prefix or k.startswith(prefix + "/")]
            for k in gone:
                del state[k]
            return bool(gone)
        return self._update_state(clear)

    def gb_download_files(self, category, character_name, mod_id, file_ids, record_type="Mod"):
        gb_mods = self._load_gb_mods()
        char_mods = gb_mods.get(character_name, [])
        record = next(
            (m for m in char_mods if m["mod_id"] == mod_id and m.get("record_type", "Mod") == record_type),
            None,
        )
        if record is None:
            return {"success": False, "error": "This mod isn't tracked anymore - fetch its link again."}

        # Several files: fetch them at the same time first (GameBanana throttles each
        # connection), then the normal one-by-one download/extract below finds them ready.
        prefetch_dir = self.mod_root / MODS_DIRNAME / ".prefetch"
        jobs = [(f["download_url"], f["size"], f.get("md5")) for f in record["files"]
                if f["file_id"] in file_ids and f.get("download_url")]
        if len(jobs) > 1:
            try:
                gamebanana_api.prefetch_files(jobs, prefetch_dir)
            except Exception:
                pass  # the sequential path below still works
        results = []
        for file_id in file_ids:
            file_entry = next((f for f in record["files"] if f["file_id"] == file_id), None)
            if file_entry is None:
                results.append({"file_id": file_id, "status": "error", "error": "Unknown file id."})
                continue
            try:
                outcome = self._download_and_extract_one(category, character_name, record["name"], file_entry)
            except gamebanana_api.GameBananaError as e:
                file_entry["download_status"] = "error"
                results.append({"file_id": file_id, "status": "error", "error": str(e)})
                continue
            file_entry["download_status"] = outcome["status"]
            file_entry["downloaded_to"] = outcome["downloaded_to"]
            file_entry["archive_path"] = outcome["archive_path"]
            file_entry["slot_mismatch"] = outcome.get("slot_mismatch")
            file_entry["music_mismatch"] = outcome.get("music_mismatch")
            results.append({"file_id": file_id, **outcome})

        shutil.rmtree(prefetch_dir, ignore_errors=True)
        self._save_gb_mods(gb_mods)
        response = {"success": True, "results": results}
        if (category in VEHICLE_SECTIONS or category in ("characters", "courses", ITEMS_CATEGORY)) and not any(r.get("status") == "error" for r in results):
            response.update(self._refile_mod(character_name, record))
        return response

    def _refile_rank(self, name):
        """Where a name comes in the app's own order (characters, courses, vehicle parts, items) - which of a pack's things it
        is filed under."""
        order = (list(self._load_roster()) + [c["name"] for cup in self._load_course_roster() for c in cup["courses"]]
                 + [i["name"] for items in self._load_vehicle_roster().values() for i in items]
                 + [i["name"] for i in self._load_item_roster()])
        return order.index(name) if name in order else len(order)

    def _refile_target(self, item_name, record):
        """(the thing to file a tracked mod under, every thing it replaces) when its downloaded files say it isn't for `item_name`
        - else (None, []). Every file that has been downloaded must say something the app can place (nothing unrecognised in
        it) and none may fit `item_name`: moving a mod moves the whole record, so a file that fits, or says nothing, rules it out.
        One thing replaced -> that thing; several (a pack) -> the first of them in the app's order, which the pack is then filed
        under and listed on every card of the others (see get_pack_links)."""
        replaced = set()
        for f in record.get("files", []):
            if f.get("download_status") != "downloaded" or not f.get("downloaded_to"):
                continue   # (not downloaded: nothing to say about it)
            mismatch = f.get("slot_mismatch")
            targets = (mismatch or {}).get("targets") or []
            if not mismatch or not targets or mismatch.get("unresolved"):
                return None, []
            replaced |= {t["name"] for t in targets}
        if not replaced or item_name in replaced:
            return None, []
        names = sorted(replaced, key=self._refile_rank)
        return names[0], names

    def _refile_mod(self, item_name, record):
        """After a download: if the files are for something else than the card it came from, file the mod there now (see
        gb_move_mod) rather than leave it where it was found. {"moved": {...}} when it did (with what the UI needs to say
        so, open that card and undo it; `pack` names everything a pack replaces), {"move_error": text} when it should have but
        couldn't, {} otherwise."""
        target, replaced = self._refile_target(item_name, record)
        if target is None:
            return {}
        result = self.gb_move_mod(item_name, record["mod_id"], target, record.get("record_type", "Mod"))
        if not result.get("success"):
            return {"move_error": result["error"]}
        return {"moved": {"from_item": item_name, "to_item": target, "to_section": result["to_section"],
                          "mod_id": record["mod_id"], "record_type": record.get("record_type", "Mod"),
                          "mod_name": record["name"], "moved_folders": result["moved_folders"],
                          "pack": replaced if len(replaced) > 1 else []}}

    def _claims_for_status(self, checked_keys):
        """_compute_claims(..., include_ui_icons=False) for the read-only questions (the flow bar, the conflict cards, the live
        warnings), which the page asks over and over with the same ticks. Remembered while nothing it read has changed: the ticked
        mods' folders (down to every subfolder), the leave-out and settled-conflict files. Never used by the commit itself - that
        always reads the files afresh. The answer is shared, so callers must only read it."""
        keys = tuple(sorted(checked_keys))
        root = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME

        def file_sig(path):
            try:
                st = path.stat()
                return (st.st_mtime_ns, st.st_size)
            except OSError:
                return None

        def token():
            parts = [self._extracted_token()]
            for key in keys:
                category, unit_rel = key.split("/", 1)
                unit = root / category / unit_rel
                parts.append(library_cache.tree_token(unit, depth=0))   # (files beside romfs/)
                parts.append(library_cache.tree_token(unit / "romfs", depth=24))
            return hash(tuple(parts))

        key = (keys, file_sig(self.excluded_files_path), file_sig(self.conflict_resolutions_path))
        return self._library.get(f"claims:{hash(key)}", key, lambda: self._compute_claims(keys, include_ui_icons=False),
                                 token=token, max_age=15)

    def _compute_claims(self, checked_keys, include_ui_icons=True):
        """Walks every checked mod's romfs tree and figures out which mod claims
        each file path. Read-only - never touches the filesystem otherwise.
        Returns a namespace: claims, conflicts ((path, winner, loser) tuples),
        mods_processed, missing, ui_icons_files, bgm_bars_skipped, resolved,
        ui_archives_skipped, course_icons_files, plus what the conflict cards
        need - conflict_paths (path -> the distinct-content candidates, each
        with the mods that hold a byte-identical copy under "also"),
        claimants (normalized path -> every mod that has it), file_counts and
        excluded_counts (per mod). Files a mod has been told to leave out
        (excluded-files.json) are never claimed at all.

        A path with more than one DISTINCT-content claimant is first checked
        against conflict-resolutions.json's saved priority list for that path
        (see resolve_conflict()) before it's treated as a real conflict - the
        first listed mod that's actually among the current claimants silently
        wins, with nothing added to `conflicts`. `resolved` reports every path
        that took this path, as (path, winning mod key) pairs, so callers can
        surface "N conflicts auto-resolved" instead of it being invisible."""
        selected = sorted(checked_keys)
        # normalized relpath -> list of every DISTINCT-content claim on it
        # (byte-identical duplicates across mods are collapsed into whichever
        # one was seen first, same as before - see the dedup comment below).
        path_claims = {}
        mods_processed = []
        missing = []
        bgm_bars_skipped = 0
        ui_archives_skipped = []  # (unit key, romfs-relative path) per skipped .sarc
        excluded = self._excluded_norms()  # {mod key: {normalized path}} the user left out
        file_counts = {}       # mod key -> files it would contribute (before leave-outs)
        excluded_counts = {}   # mod key -> how many of those are left out
        claimants = {}         # normalized path -> every mod (any content) that has it

        for key in selected:
            category, unit_rel = key.split("/", 1)
            mod_romfs = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / category / unit_rel / "romfs"
            if not mod_romfs.is_dir():
                if not self._is_exefs_unit(key):  # code patches are handled by _compute_exefs()
                    missing.append(key)
                continue

            mods_processed.append(key)
            # packed menu files the mod put beside romfs/ (never staged anyway) still count as
            # "this mod changes menu pictures or names" - they take effect in the UI step
            for extra in ui_setup.unit_extra_archives(mod_romfs.parent).values():
                ui_archives_skipped.append((key, "(beside romfs/) " + extra.relative_to(mod_romfs.parent).as_posix()))
            for filepath in mod_romfs.rglob("*"):
                if filepath.is_file():
                    rel = filepath.relative_to(mod_romfs)
                    if _is_packed_ui_archive(rel):
                        # A packed .sarc under UI/ (common.sarc/menu.sarc for
                        # character-select icons, message.sarc for a locale's
                        # ENTIRE text table - course names included) bundles
                        # every character's/every string's entry in one file,
                        # never just this one mod's own change - merging a
                        # mod's own copy in directly would silently wipe out
                        # every other character's icon, or every other piece
                        # of text, not also present in that mod's rebuild.
                        # These need to be hand-injected with a tool like
                        # Switch Toolbox instead - see "UI Icon Worklist" in
                        # Settings and the Help page.
                        #
                        # A mod's own individually-named loose UI texture -
                        # e.g. a course's own UI/cmn/menu/ym_CoursePict_
                        # <internal id>.bntx select-screen thumbnail, or its
                        # UI/cmn/ending/ym_AwardBG_<internal id>.bntx results
                        # background - is a completely different, safe case:
                        # nothing else can plausibly claim that exact
                        # filename, so it's merged in normally below, same as
                        # any other romfs file.
                        ui_archives_skipped.append((key, rel.as_posix()))
                        continue
                    norm = rel.as_posix().lower()
                    if norm in _MERGE_SKIP_RELPATHS:
                        bgm_bars_skipped += 1
                        continue
                    file_counts[key] = file_counts.get(key, 0) + 1
                    if norm in excluded.get(key, ()):
                        excluded_counts[key] = excluded_counts.get(key, 0) + 1
                        continue
                    claimants.setdefault(norm, []).append(key)
                    candidates = path_claims.setdefault(norm, [])
                    # Two mods writing the same path only matters if they'd
                    # actually put different bytes there - a handful of
                    # course packs from the same author bundle an identical
                    # shared audio-bank fix with every download, and that
                    # coincidence shouldn't block staging the way a genuine
                    # competing edit should.
                    same = next((c for c in candidates if filecmp.cmp(c["src"], filepath, shallow=False)), None)
                    if same is not None:
                        same.setdefault("also", []).append(key)
                        continue
                    candidates.append({"mod": key, "src": filepath, "rel": rel})

        resolutions = self._load_conflict_resolutions()
        claims = {}
        conflicts = []
        resolved = []
        conflict_paths = {}  # path -> its distinct-content candidates, still unsettled
        for norm, candidates in path_claims.items():
            if len(candidates) == 1:
                claims[norm] = candidates[0]
                continue
            path = candidates[0]["rel"].as_posix()
            preferred = None
            for pref_key in resolutions.get(path, []):
                match = next((c for c in candidates if c["mod"] == pref_key), None)
                if match:
                    preferred = match
                    break
            if preferred:
                claims[norm] = preferred
                resolved.append((path, preferred["mod"]))
                continue
            # Still unresolved - report every subsequent distinct claim
            # against the first one, same pairwise shape as before (a 3+-way
            # collision produces one entry per extra claimant, all against
            # candidates[0], not every possible pair).
            claims[norm] = candidates[0]
            conflict_paths[path] = candidates
            for other in candidates[1:]:
                conflicts.append((path, candidates[0]["mod"], other["mod"]))

        ui_icons_files = 0
        if include_ui_icons:
            ui_icons_romfs = self.mod_root / "ui-icons" / "romfs"
            if ui_icons_romfs.is_dir():
                for filepath in ui_icons_romfs.rglob("*"):
                    if filepath.is_file():
                        rel = filepath.relative_to(ui_icons_romfs)
                        claims[rel.as_posix().lower()] = {
                            "mod": "ui-icons (combined UI)",
                            "src": filepath,
                            "rel": rel,
                        }
                        ui_icons_files += 1

        # Same "always merged in" idea as ui-icons/ above, for course-select
        # icons this app generated itself (see generate_course_icon()) -
        # kept in its own folder rather than ui-icons/ so app-generated
        # files never mix with the user's own hand-curated icon work.
        course_icons_files = 0
        if include_ui_icons:
            course_icons_romfs = self.mod_root / COURSE_ICONS_DIRNAME / "romfs"
            if course_icons_romfs.is_dir():
                for filepath in course_icons_romfs.rglob("*"):
                    if filepath.is_file():
                        rel = filepath.relative_to(course_icons_romfs)
                        claims[rel.as_posix().lower()] = {
                            "mod": "course-icons (generated)",
                            "src": filepath,
                            "rel": rel,
                        }
                        course_icons_files += 1

        # ...and for the user's own vehicle-part pictures that are loose files (see sync_part_pictures()).
        part_icons_files = 0
        if include_ui_icons:
            part_icons_romfs = self.mod_root / PART_ICONS_DIRNAME / "romfs"
            if part_icons_romfs.is_dir():
                for filepath in part_icons_romfs.rglob("*"):
                    if filepath.is_file():
                        rel = filepath.relative_to(part_icons_romfs)
                        claims[rel.as_posix().lower()] = {
                            "mod": "part-icons (your vehicle part pictures)",
                            "src": filepath,
                            "rel": rel,
                        }
                        part_icons_files += 1

        return types.SimpleNamespace(
            claims=claims, conflicts=conflicts, mods_processed=mods_processed, missing=missing,
            ui_icons_files=ui_icons_files, bgm_bars_skipped=bgm_bars_skipped, resolved=resolved,
            ui_archives_skipped=ui_archives_skipped, course_icons_files=course_icons_files, part_icons_files=part_icons_files,
            conflict_paths=conflict_paths, claimants=claimants, file_counts=file_counts,
            excluded_counts=excluded_counts,
        )

    # --- exefs code-patch units (see find_exefs_units) ---------------------

    def _unit_dir(self, key):
        return self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / Path(*key.split("/"))

    def _exefs_files(self, key):
        """{BUILD ID (upper-case hex): Path} for the patch files a patch unit
        directly holds, plus the names of any other exefs-looking files there
        (.ips32, .pchtxt, non-hex names) that Atmosphere would ignore."""
        patches, ignored = {}, []
        unit_dir = self._unit_dir(key)
        if not unit_dir.is_dir():
            return patches, ignored
        for f in sorted(unit_dir.iterdir()):
            if not f.is_file():
                continue
            if _EXEFS_PATCH_RE.match(f.name):
                patches[f.stem.upper()] = f
            elif f.suffix.lower() in (".ips", ".ips32", ".pchtxt"):
                ignored.append(f.name)
        return patches, ignored

    def _is_exefs_unit(self, key):
        """True for a checked-unit key that names a patch folder rather than
        a romfs-holding one."""
        unit_dir = self._unit_dir(key)
        if not unit_dir.is_dir() or (unit_dir / "romfs").is_dir():
            return False
        return any(_EXEFS_PATCH_RE.match(f.name) for f in unit_dir.iterdir() if f.is_file())

    @staticmethod
    def _build_id_label(build_id):
        version = KNOWN_BUILD_IDS.get(build_key(build_id))
        return f"{build_id[:8]}... (v{version})" if version else f"{build_id[:8]}..."

    def get_exefs_unit_info(self, unit_keys):
        """{unit key: {"ids": [{"id", "version"}], "inert": bool}} for just
        the keys that are code-patch units. `inert` is only ever true when the
        user has told the app their game's build id (Settings) and none of the
        unit's patches target it - a patch for another build silently does
        nothing, which is otherwise invisible."""
        settings = self._load_settings()
        mine = (settings.get("game_build_id") or "").strip().upper()
        info = {}
        for key in unit_keys:
            if not self._is_exefs_unit(key):
                continue
            patches, _ignored = self._exefs_files(key)
            fit = patch_fit(mine, settings.get("game_version"), patches)
            info[key] = {
                "ids": [{"id": bid, "version": KNOWN_BUILD_IDS.get(build_key(bid))} for bid in patches],
                "inert": fit == "wrong",
                "maybe": fit == "maybe",
            }
        return info

    def _compute_exefs(self, checked_keys):
        """Read-only. Returns (exefs_keys, conflicts, problems): the checked
        keys that are code-patch units, overlap conflicts between them in the
        same (path, winner, loser) shape _compute_claims() uses (path is a
        pseudo-path "exefs/<build id>@0x<offset>" - the first byte two
        patches for the same build disagree on), and (key, file, reason)
        tuples for patch files that couldn't be parsed. Patches from
        different mods only conflict if they're for the same build id AND
        write different bytes to an overlapping range."""
        exefs_keys = [k for k in sorted(checked_keys) if self._is_exefs_unit(k)]
        parsed = {}
        problems = []
        for key in exefs_keys:
            per_build = {}
            for build_id, path in self._exefs_files(key)[0].items():
                try:
                    per_build[build_id] = parse_ips(path.read_bytes())
                except (OSError, ValueError) as e:
                    problems.append((key, path.name, str(e)))
            parsed[key] = per_build
        conflicts = []
        for i, a in enumerate(exefs_keys):
            for b in exefs_keys[i + 1:]:
                for build_id in sorted(parsed[a].keys() & parsed[b].keys()):
                    clash = first_ips_clash(parsed[a][build_id], parsed[b][build_id])
                    if clash is not None:
                        conflicts.append((f"exefs/{build_id}@0x{clash:x}", a, b))
        return exefs_keys, conflicts, problems

    @staticmethod
    def _exefs_stage_name(key):
        """Patch-set folder name for a unit in the staging tree: the app's
        own prefix, the mod's folder name reduced to safe ASCII, and a short
        hash of the full key so two mods with the same name can't collide."""
        parts = key.split("/")
        mod_name = parts[2] if len(parts) > 2 else parts[-1]
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", mod_name).strip("-.") or "patch"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
        return f"{EXEFS_STAGING_PREFIX}{slug[:40]}_{digest}"

    def get_packed_only_units(self, unit_keys):
        """Which of these units would contribute NOTHING to a merge because
        every file in their romfs is one the merge deliberately skips (packed
        UI .sarc archives, the shared BGM.bars) - see _compute_claims(). Such a
        unit still downloads fine and can be checked, so without this the app
        gives no hint that ticking it does nothing (a whole-theme UI mod is
        typically exactly this). Read-only."""
        packed_only = []
        for key in unit_keys:
            category, unit_rel = key.split("/", 1)
            mod_romfs = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / category / unit_rel / "romfs"
            if not mod_romfs.is_dir():
                continue
            files = [p.relative_to(mod_romfs) for p in mod_romfs.rglob("*") if p.is_file()]
            if files and all(
                _is_packed_ui_archive(rel) or rel.as_posix().lower() in _MERGE_SKIP_RELPATHS
                for rel in files
            ):
                packed_only.append(key)
        return packed_only

    def check_conflicts(self, checked_keys):
        """Lightweight, read-only conflict check for a set of mods (e.g. just the
        ones checked for one character in the modal), used for live warnings
        before the user ever clicks Merge & Stage. Returns the flat pairwise
        list ("conflicts") and the same clashes grouped per set of mods
        ("groups", see _conflict_groups()) for the settle-it-here cards."""
        res = self._claims_for_status(checked_keys)
        exefs_conflicts = self._compute_exefs(checked_keys)[1]
        conflicts = res.conflicts + exefs_conflicts
        return {
            "conflicts": [
                {"path": path, "mods": [winner, loser]} for path, winner, loser in conflicts
            ],
            "groups": self._conflict_groups(res, exefs_conflicts),
        }

    def check_conflict_counts(self, key_sets):
        """[how many conflicting files there are among each set of mods] for many sets at once - what the tiles' "!" badges need,
        without the detail check_conflicts() adds. One call instead of one per tile."""
        counts = []
        for keys in key_sets:
            res = self._claims_for_status(keys)
            counts.append(len(res.conflicts) + len(self._compute_exefs(keys)[1]))
        return counts

    def _conflict_groups(self, res, exefs_conflicts):
        """One entry per SET of mods that clash, however many files they clash
        on: {"id", "mods", "labels", "paths", "summary", "kinds", "impact"
        ({mod: {"shared", "total"}}), "known" (curated notes), "can_exclude",
        "suggested" (mod to keep, or null)}. Asking once per pair instead of
        once per file is what makes a 40-file clash a single decision."""
        known_files = self._load_known_shared_files()
        raw = {}  # sorted tuple of mods -> {"paths": [...], "code": bool}
        for path, cands in res.conflict_paths.items():
            mods = sorted({m for c in cands for m in [c["mod"], *c.get("also", [])]})
            raw.setdefault(tuple(mods), {"paths": [], "code": False})["paths"].append(path)
        for path, a, b in exefs_conflicts:
            entry = raw.setdefault(tuple(sorted((a, b))), {"paths": [], "code": True})
            entry["code"] = True
            if path not in entry["paths"]:
                entry["paths"].append(path)
        groups = []
        for mods, entry in raw.items():
            paths = sorted(entry["paths"], key=str.lower)
            kinds = {}
            for p in paths:
                kinds[path_kind(p)] = kinds.get(path_kind(p), 0) + 1
            summary = " and ".join(
                f"{n} {kind}{'' if n == 1 else 's'}"
                for kind, n in sorted(kinds.items(), key=lambda kv: -kv[1])[:2]
            )
            impact = {
                m: {"shared": len(paths), "total": res.file_counts.get(m)} for m in mods
            }
            notes, seen = [], set()
            for p in paths:
                k = known_files.get(p)
                if k and k["label"] not in seen:
                    seen.add(k["label"])
                    notes.append(k)
            suggested = None
            if not entry["code"]:
                # Keep the mod that belongs in these files' slot first (one filed under
                # Funky Kong that really replaces Donkey Kong's model shouldn't beat the
                # actual Donkey Kong mod), then the one that relies on them most (they're
                # the biggest share of what it ships); ties go to the name that sorts
                # first so the suggestion is stable.
                def reliance(m):
                    total = impact[m]["total"] or 0
                    return (self._slot_mismatch(m), -(len(paths) / total) if total else 0, mod_label(m).lower())
                suggested = sorted(mods, key=reliance)[0]
            groups.append({
                "id": hashlib.sha1("|".join(mods).encode("utf-8")).hexdigest()[:10],
                "mods": list(mods),
                "labels": [mod_label(m) for m in mods],
                "full_labels": [mod_label(m, full=True) for m in mods],
                "paths": paths,
                "summary": summary,
                "kinds": kinds,
                "impact": impact,
                "known": notes[:3],
                "can_exclude": not entry["code"],
                "suggested": suggested,
            })
        groups.sort(key=lambda g: (-len(g["paths"]), g["id"]))
        return groups

    def get_all_conflicts(self):
        """Whole-roster conflict + resolution overview for Settings' Advanced-
        mode "Conflicts" panel - unlike check_conflicts() (scoped to whatever
        one character/course modal is open), this walks every mod checked
        anywhere in the app, so a conflict between two different courses'
        checked mods is never missed just because neither happens to be the
        currently-open modal."""
        checked_keys = [k for k, v in self._load_state().items() if v]
        if not checked_keys:
            return {"conflicts": [], "resolved": [], "groups": [], "settled": [], "left_out": self.get_excluded_files()}
        res = self._claims_for_status(checked_keys)
        resolved = res.resolved
        # Code-patch overlaps ("exefs/<build id>@0x..." pseudo-paths) have no
        # leave-out mechanism - half a patch can't be dropped - so they
        # always need one of the two mods unchecked.
        exefs_conflicts = self._compute_exefs(checked_keys)[1]
        conflicts = res.conflicts + exefs_conflicts
        known = self._load_known_shared_files()
        left_out = self.get_excluded_files()
        settled = {}
        for mod, entries in left_out.items():
            for e in entries:
                if e["reason"] != "conflict":
                    continue
                s = settled.setdefault((mod, e["kept_from"]), {
                    "mod": mod, "label": mod_label(mod), "kept_from": e["kept_from"],
                    "kept_label": e["kept_label"], "paths": [],
                })
                s["paths"].append(e["path"])

        conflict_payload = []
        seen_paths = set()
        for path, _winner, _loser in conflicts:
            if path in seen_paths:
                continue  # one row per path even if 3+ mods collide on it
            seen_paths.add(path)
            mods_for_path = sorted({m for p, a, b in conflicts if p == path for m in (a, b)})
            conflict_payload.append({"path": path, "mods": mods_for_path, "known": known.get(path)})

        resolved_payload = [
            {"path": path, "preferred": mod_key, "known": known.get(path)}
            for path, mod_key in resolved
        ]

        return {
            "conflicts": conflict_payload, "resolved": resolved_payload,
            "groups": self._conflict_groups(res, exefs_conflicts),
            "settled": sorted(settled.values(), key=lambda s: (s["label"].lower(), s["kept_label"] or "")),
            "left_out": left_out,
        }

    def _commit_signature(self, checked_keys):
        """What a commit is made from: the ticked mods plus every left-out file.
        Anything that changes either makes the last commit stale."""
        payload = [sorted(checked_keys), self._load_excluded_files()]
        voice = self._voice_signature()
        if voice:
            payload.append(voice)     # (only when there are voice edits, so a commit made before they existed isn't called stale)
        payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    def _ticked_signature(self, checked_keys):
        return hashlib.sha1("|".join(sorted(checked_keys)).encode("utf-8")).hexdigest()[:16]

    def _commit_summary(self, checked_keys, res, exefs_keys, exefs_conflicts, exefs_problems):
        """Counts and plain-language warning cards for the Commit page (and the
        same shape returned by merge()). Each warning: {"kind", "severity"
        ("info" | "todo" | "warn"), "title", "detail", "mods", "action"}."""
        warnings = []
        settings = self._load_settings()
        mine = (settings.get("game_build_id") or "").strip().upper()
        short = lambda keys: [k for k in keys]  # noqa: E731 - keys are already what the UI links on

        if res.missing:
            warnings.append({
                "kind": "missing", "severity": "warn",
                "title": f"{len(res.missing)} selected mod{'s' if len(res.missing) != 1 else ''} can't be found on disk",
                "detail": "Their files are gone (deleted or moved). Deselect them or download them again - they aren't part of this commit.",
                "mods": short(res.missing), "action": "open-mod",
            })
        if res.ui_archives_skipped:
            mods = sorted({k for k, _rel in res.ui_archives_skipped})
            warnings.append({
                "kind": "ui-archives", "severity": "info",
                "title": f"{len(mods)} mod{'s' if len(mods) != 1 else ''} change menu pictures or names",
                "detail": "Those changes can't be copied straight in (every mod ships its own copy of the same shared game "
                          "files) - they're combined into one set of files automatically when you commit. Settings has the "
                          "language it builds for and the built files themselves, if you want either.",
                "mods": mods, "action": "settings",
            })
            only = self.get_packed_only_units(res.mods_processed)
            if only:
                warnings.append({
                    "kind": "packed-only", "severity": "info",
                    "title": f"{len(only)} mod{'s' if len(only) != 1 else ''} only change menu pictures or names",
                    "detail": "Nothing from them is copied directly - they take effect automatically when you commit.",
                    "mods": only, "action": "open-mod",
                })
        if res.bgm_bars_skipped:
            warnings.append({
                "kind": "bgm-bars", "severity": "info",
                "title": f"{res.bgm_bars_skipped} course mod{'s' if res.bgm_bars_skipped != 1 else ''} bundle the shared music file",
                "detail": "That one file (Audio/Static/BGM.bars) is never copied - two mods rebuilding it is the most common source of clashes, for almost no gain.",
                "mods": [], "action": None,
            })
        left_out_total = sum(res.excluded_counts.values())
        if left_out_total:
            warnings.append({
                "kind": "left-out", "severity": "info",
                "title": f"{left_out_total} file{'s' if left_out_total != 1 else ''} left out on purpose",
                "detail": "From " + ", ".join(f"{mod_label(m)} ({n})" for m, n in sorted(res.excluded_counts.items()))
                          + ". You can include them again from each mod's Files button.",
                "mods": sorted(res.excluded_counts), "action": "open-mod",
            })
        if res.resolved:
            warnings.append({
                "kind": "saved-preferences", "severity": "info",
                "title": f"{len(res.resolved)} clash{'es' if len(res.resolved) != 1 else ''} settled by earlier choices",
                "detail": "Saved preferences from before are still applied; Settings shows them.",
                "mods": [], "action": None,
            })
        if exefs_keys:
            wrong, maybe = [], []
            for key in exefs_keys:
                fit = patch_fit(mine, settings.get("game_version"), list(self._exefs_files(key)[0]))
                if fit == "wrong":
                    wrong.append(key)
                elif fit == "maybe":
                    maybe.append(key)
            if wrong:
                warnings.append({
                    "kind": "exefs-version", "severity": "warn",
                    "title": f"{len(wrong)} code patch{'es are' if len(wrong) != 1 else ' is'} for a different game version",
                    "detail": f"They're built for another version than yours ({mine[:8]}...) and will do nothing on your game.",
                    "mods": wrong, "action": "open-mod",
                })
            if maybe:
                warnings.append({
                    "kind": "exefs-version-maybe", "severity": "todo",
                    "title": f"{len(maybe)} code patch{'es were' if len(maybe) != 1 else ' was'} made for an older game version",
                    "detail": "You said your game isn't one of the listed versions (probably newer), so these might not work on it. "
                              "A game update often leaves the executable alone, in which case they still do. "
                              "If one does nothing in the game, look for a newer version of the mod. "
                              "Entering your exact build ID in Settings lets the app check for sure.",
                    "mods": maybe, "action": "open-mod",
                })
            if not mine and settings.get("game_version") != NEWER_VERSION:
                warnings.append({
                    "kind": "exefs-version-unknown", "severity": "info",
                    "title": f"{len(exefs_keys)} code patch{'es' if len(exefs_keys) != 1 else ''} - game version not set",
                    "detail": "A code patch only works on the exact game version it was built for. Set your game version in Settings to be warned about mismatches.",
                    "mods": list(exefs_keys), "action": "settings",
                })
            for key, name, reason in exefs_problems:
                warnings.append({
                    "kind": "exefs-problem", "severity": "warn",
                    "title": f"A code patch file couldn't be read ({name})",
                    "detail": f"{mod_label(key)}: {reason}. It was skipped.", "mods": [key], "action": "open-mod",
                })
        _auto, needs = self._auto_icons()
        guessed = self._guessed_names()
        if guessed:
            warnings.append({
                "kind": "guessed-names", "severity": "todo",
                "title": f"{len(guessed)} name{'s were' if len(guessed) != 1 else ' was'} guessed for a mod that doesn't say",
                "detail": "A wrong guess would end up in the game's menus - check each one, or change it. It takes a few seconds.",
                "mods": [], "action": "guessed-names",
            })
        if needs:
            warnings.append({
                "kind": "icon-choice", "severity": "todo",
                "title": f"{len(needs)} character{'s have' if len(needs) != 1 else ' has'} icon pictures that need your pick",
                "detail": "A mod ships several versions of its icon pictures (for example one per costume), so the app can't tell which is which. "
                          "Open the character and choose in its Menu look card - until then the game's normal icons are used.",
                "mods": [], "items": [n["item"] for n in needs], "action": "open-items",
            })
        counts = {
            "mods": len(res.mods_processed), "files": len(res.claims), "left_out": left_out_total,
            "code_patches": len(exefs_keys), "ui_files": res.ui_icons_files, "course_icons": res.course_icons_files,
            "part_icons": res.part_icons_files,
        }
        return counts, warnings

    def preview_commit(self, checked_keys):
        """Dry run of merge(): what a commit would do, and anything that would
        stop it, without touching the staging folder. The Commit page shows
        this the moment it opens, so a conflict is settled BEFORE pressing
        Commit rather than discovered after."""
        if not checked_keys:
            return {"can_commit": False, "empty": True, "groups": [], "warnings": [], "counts": {}}
        res = self._compute_claims(checked_keys)
        exefs_keys, exefs_conflicts, exefs_problems = self._compute_exefs(checked_keys)
        groups = self._conflict_groups(res, exefs_conflicts) if (res.conflicts or exefs_conflicts) else []
        counts, warnings = self._commit_summary(checked_keys, res, exefs_keys, exefs_conflicts, exefs_problems)
        last = self._load_settings().get("last_commit")
        return {
            "can_commit": not groups, "empty": False, "groups": groups, "warnings": warnings, "counts": counts,
            "staging_path": str(self.mod_root.parent / "sd-card-staging"),
            "already": bool(last) and last.get("sig") == self._commit_signature(checked_keys),
        }

    def merge(self, checked_keys):
        self.sync_voice_edits()
        self.sync_part_pictures()   # (what a ticked mod supplies itself may have changed since the picture was set)
        lines = []
        staging_root = self.mod_root.parent / "sd-card-staging"
        out_romfs = staging_root / "atmosphere" / "contents" / TITLE_ID / "romfs"

        if not checked_keys:
            return {"lines": ["No mods checked - nothing to do."]}

        # Menu icons & text: built fresh here, before the copy pass below - so the ui-icons/romfs
        # files that pass already includes are always current for what's ticked right now. No
        # separate step, and no need to stage them afterward (build_ui_setup()'s own staging is
        # for when it's called on its own, from Settings).
        if self._ui_build_needed(checked_keys):
            settings = self._load_settings()
            locale = settings.get("ui_setup_locale") or "USen"
            build_locales = [locale]
            if settings.get("ui_setup_extra_english"):
                other = {"USen": "EUen", "EUen": "USen"}.get(locale)
                if other:
                    build_locales.append(other)
            ui_build = self._build_ui_archives(build_locales)
            if ui_build.get("success"):
                lines.append(f"Menu icons & text: built for {', '.join(build_locales)}.")
                for r in ui_build["results"]:
                    if r.get("error"):
                        lines.append(f"  WARNING - {r['archive']}: {r['error']}")
                    elif r.get("verify") and r["verify"]["total"] and r["verify"]["ok"] != r["verify"]["total"]:
                        lines.append(f"  WARNING - {r['archive']}: only {r['verify']['ok']} of {r['verify']['total']} changes are in it")
            else:
                lines.append(f"Menu icons & text: couldn't build - {ui_build.get('error')}")
            lines.append("")

        res = self._compute_claims(checked_keys)
        claims, conflicts, mods_processed, missing = res.claims, res.conflicts, res.mods_processed, res.missing
        ui_icons_files, bgm_bars_skipped, resolved = res.ui_icons_files, res.bgm_bars_skipped, res.resolved
        ui_archives_skipped, course_icons_files = res.ui_archives_skipped, res.course_icons_files
        lines.extend(f"SKIPPED (romfs not found): {key}" for key in missing)
        exefs_keys, exefs_conflicts, exefs_problems = self._compute_exefs(checked_keys)
        conflicts = conflicts + exefs_conflicts

        if conflicts:
            groups = self._conflict_groups(res, exefs_conflicts)
            lines.append("=== CONFLICTS DETECTED - staging NOT performed ===")
            lines.append(
                f"{len(conflicts)} file(s) are claimed by more than one checked mod "
                f"({len(groups)} conflicting set{'' if len(groups) == 1 else 's'} of mods):"
            )
            lines.append("")
            for g in groups:
                lines.append(f"  {' vs '.join(g['labels'])}: {g['summary']}")
                for path in g["paths"]:
                    lines.append(f"    {path}")
                lines.append("")
            lines.append(
                "Settle each one (keep one mod's version, or leave the files out of both) "
                "and commit again. The staging folder was left untouched."
            )
            return {"lines": lines, "conflict": True, "groups": groups}

        # Always exists after a successful merge (even one that staged no
        # files at all), so the "Open staging folder" button has a target.
        staging_root.mkdir(parents=True, exist_ok=True)
        if out_romfs.exists():
            shutil.rmtree(out_romfs)
        # (created lazily by the copies below - a merge of only code patches,
        # or of mods that are entirely packed archives, leaves no empty romfs/)

        for claim in claims.values():
            dest = out_romfs / claim["rel"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(claim["src"], dest)

        # exefs code patches -> atmosphere/exefs_patches/<prefix><slug>/<BUILD ID>.ips.
        # Only this app's own previous patch sets (EXEFS_STAGING_PREFIX) are
        # cleared first, so a re-merge never leaves stale patches behind but
        # also never touches sigpatches or anything else already there.
        patches_root = staging_root / "atmosphere" / EXEFS_PATCHES_DIRNAME
        if patches_root.is_dir():
            for old in patches_root.iterdir():
                if old.is_dir() and old.name.startswith(EXEFS_STAGING_PREFIX):
                    shutil.rmtree(old)
            if not any(patches_root.iterdir()):
                patches_root.rmdir()
        unparsable = {(key, name) for key, name, _reason in exefs_problems}
        staged_patches = []  # (unit key, [build ids actually staged])
        ignored_patch_files = []  # (unit key, filename) Atmosphere wouldn't load
        for key in exefs_keys:
            patch_files, ignored = self._exefs_files(key)
            ignored_patch_files.extend((key, name) for name in ignored)
            staged_ids = []
            for build_id, src in patch_files.items():
                if (key, src.name) in unparsable:
                    continue
                dest_dir = patches_root / self._exefs_stage_name(key)
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_dir / f"{build_id}.ips")
                staged_ids.append(build_id)
            staged_patches.append((key, staged_ids))

        lines.append("=== Commit complete ===")
        lines.append(f"Mods merged: {len(mods_processed)}")
        for m in mods_processed:
            lines.append(f"  - {m}")
        lines.append(f"Files copied: {len(claims)}")
        if ui_icons_files:
            lines.append(f"  (includes {ui_icons_files} file(s) from ui-icons/, always merged in)")
        else:
            lines.append("  (ui-icons/ is empty - no combined UI icons included)")
        if bgm_bars_skipped:
            lines.append(
                f"  ({bgm_bars_skipped} mod(s) bundled Audio/Static/BGM.bars - always skipped, "
                "see docs/merge-rules.md)"
            )
        if resolved:
            lines.append(
                f"  ({len(resolved)} conflict(s) auto-resolved using your saved preferences)"
            )
        left_out_total = sum(res.excluded_counts.values())
        if left_out_total:
            lines.append(
                f"  ({left_out_total} file(s) left out on purpose - "
                + ", ".join(f"{mod_label(m)}: {n}" for m, n in sorted(res.excluded_counts.items()))
                + ")"
            )
        if ui_archives_skipped and ui_icons_files:
            # Combined files exist (built automatically above, or by hand): the per-mod copies
            # are correctly left out - one line is enough.
            lines.append(
                f"  ({len(ui_archives_skipped)} packed UI archive(s) from individual mods weren't copied - "
                "their changes were combined automatically above instead, and the combined files "
                "from ui-icons/ are used.)"
            )
        elif ui_archives_skipped:
            lines.append(
                f"  ({len(ui_archives_skipped)} packed UI archive(s) (common.sarc/menu.sarc/message.sarc) "
                "skipped - a plain merge would wipe out other mods' icons/text, and they weren't combined "
                "automatically this time (see the warning above). Fix that and commit again):"
            )
            for key, rel in ui_archives_skipped:
                lines.append(f"      {key.split('/', 1)[1]}: {rel}")
        if ui_archives_skipped:
            for key in self.get_packed_only_units(mods_processed):
                lines.append(
                    f"  WARNING: {key.split('/', 1)[1]} contained ONLY packed archives - "
                    "nothing from it was merged."
                )
        if course_icons_files:
            lines.append(
                f"  (includes {course_icons_files} generated course-select icon(s) from course-icons/, "
                "always merged in)"
            )
        if res.part_icons_files:
            lines.append(
                f"  (includes {res.part_icons_files} vehicle part picture file(s) from part-icons/, "
                "always merged in)"
            )
        if staged_patches:
            settings = self._load_settings()
            mine = (settings.get("game_build_id") or "").strip().upper()
            lines.append(f"Code patches staged: {len(staged_patches)}")
            for key, ids in staged_patches:
                label = ", ".join(self._build_id_label(b) for b in ids) or "nothing usable"
                lines.append(f"  - {key.split('/', 1)[1]}: {label}")
                fit = patch_fit(mine, settings.get("game_version"), ids)
                if fit == "wrong":
                    lines.append(
                        f"    WARNING: built for a different game version than your build id "
                        f"({mine[:8]}...) - it will do nothing on your game."
                    )
                elif fit == "maybe":
                    lines.append(
                        "    NOTE: made for an older game version than yours (you chose \"not listed, probably newer\") "
                        "- it might not work on your game."
                    )
            if not mine and settings.get("game_version") != NEWER_VERSION:
                lines.append(
                    "  (A code patch only works on the exact game version it was built for - set "
                    "your game's build id in Settings to be warned about mismatches.)"
                )
            for key, name, reason in exefs_problems:
                lines.append(f"  SKIPPED patch file {name} in {key.split('/', 1)[1]}: {reason}")
            for key, name in ignored_patch_files:
                lines.append(
                    f"  (ignored {name} in {key.split('/', 1)[1]} - Atmosphere only loads "
                    "lowercase .ips files named after a build id)"
                )
        lines.append(f"Output: {out_romfs}")
        if staged_patches:
            lines.append(f"Code patches: {patches_root}")
        lines.append("")
        lines.append("Next step: copy the contents of:")
        lines.append(f"  {staging_root}")
        lines.append("onto your SD card root (merging into its existing atmosphere/ folder).")

        counts, warnings = self._commit_summary(checked_keys, res, exefs_keys, exefs_conflicts, exefs_problems)
        now = datetime.now().isoformat(timespec="seconds")
        self.save_settings({"last_commit": {
            "sig": self._commit_signature(checked_keys), "at": now,
            "mods": counts["mods"], "files": counts["files"], "left_out": counts["left_out"],
        }})
        return {
            "lines": lines, "conflict": False, "staged": True, "counts": counts, "warnings": warnings,
            "staging_path": str(staging_root), "at": now,
        }

    # --- guided flow: where the user is and what to do next ------------------

    def get_game_versions(self):
        """The game versions the app can recognise a code patch for (see
        KNOWN_BUILD_IDS), newest first, for the first-run setup and Settings."""
        return [
            {"version": v, "build_id": b}
            for b, v in sorted(KNOWN_BUILD_IDS.items(), key=lambda kv: [int(x) for x in kv[1].split(".")], reverse=True)
        ]

    def get_ui_locales(self):
        """The languages the game's text is stored in, for the setup wizard."""
        return [{"code": c, "label": l} for c, l in ui_setup.LOCALES.items()]

    def set_game_version(self, version):
        """Records the user's game version; a known one also sets the exact
        build id the code-patch checks use. "" = don't know (no checks);
        NEWER_VERSION = not a listed version (patches for a listed one are flagged "maybe")."""
        build = next((b for b, v in KNOWN_BUILD_IDS.items() if v == version), "")
        self.save_settings({"game_version": version or "", "game_build_id": build})
        return {"game_version": version or "", "game_build_id": build}

    def _ui_build_needed(self, checked):
        """Whether there's anything for the menu icons & text build to combine right now: a ticked
        mod's own common.sarc/menu.sarc/message.sarc for the current language, or the user's own
        icon/name overrides (or an automatic pick)."""
        sources = ui_setup.collect_sources(self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME, checked) if checked else {}
        locale = self._load_settings().get("ui_setup_locale") or "USen"
        needed = any(a in sources for a in ("common", "menu", f"message:{locale}"))
        if not needed:
            ov_now = ui_setup.load_overrides(self.mod_root)
            needed = bool(self._auto_icons()[0] or ov_now["textures"] or ov_now["strings"] or ov_now["names"])
        return needed

    def get_flow_status(self):
        """Where the user is in the setup > choose mods > commit > copy to Switch flow: which steps
        are done, which have gone stale (mods or menu-icon/text settings changed since), and the one
        thing to do next. Cheap enough (no UI-archive analysis) to call after every change."""
        if not self.mod_root:
            return {"setup": {"done": False}, "recommended": "setup"}
        settings = self._load_settings()
        checked = sorted(k for k, v in self._load_state().items() if v)
        base = game_files.status(self.mod_root)
        setup_done = bool(settings.get("setup_done")) and base["done"]

        res = self._claims_for_status(checked) if checked else None
        exefs_conflicts = self._compute_exefs(checked)[1] if checked else []
        conflicts = 0
        if res:
            conflicts = len(self._conflict_groups(res, exefs_conflicts)) if (res.conflicts or exefs_conflicts) else 0

        # Menu icons & text are built automatically as part of a commit (see merge()), so a commit
        # only counts as current when BOTH what was copied and what was built still match right now.
        ui_needed = self._ui_build_needed(checked)
        last_ui = settings.get("last_ui_build")
        ui_sig = self._ui_signature() if ui_needed else None
        ui_stale = ui_needed and (not last_ui or last_ui.get("sig") != ui_sig)

        last = settings.get("last_commit")
        commit_sig = self._commit_signature(checked)
        commit = {
            "done": bool(last), "at": last.get("at") if last else None,
            "stale": bool(last) and (last.get("sig") != commit_sig or ui_stale),
            "conflicts": conflicts,
            "summary": ({k: last.get(k) for k in ("mods", "files", "left_out")} if last else None),
        }

        ui_root = self.mod_root / "ui-icons" / "romfs"
        built = sum(1 for f in ui_root.rglob("*") if f.is_file()) if ui_root.is_dir() else 0
        ui = {
            "needed": ui_needed, "built": built, "at": last_ui.get("at") if last_ui else None,
            "choices": len(self._auto_icons()[1]), "guessed": len(self._guessed_names()),
        }

        done_marker = settings.get("switch_done")
        switch_sig = f"{commit_sig}:{last_ui.get('sig') if last_ui else ''}"
        switch = {
            "done": bool(done_marker) and done_marker.get("sig") == switch_sig,
            "stale": bool(done_marker) and done_marker.get("sig") != switch_sig,
            "staged": bool(last),
        }

        if not setup_done:
            recommended = "setup"
        elif not checked:
            recommended = "mods"
        elif not commit["done"] or commit["stale"] or conflicts:
            recommended = "commit"
        elif not switch["done"]:
            recommended = "switch"
        else:
            recommended = "done"
        return {
            "setup": {"done": setup_done, "base_files": base}, "mods": {"ticked": len(checked), "conflicts": conflicts},
            "commit": commit, "ui": ui, "switch": switch, "recommended": recommended,
            "game_version": settings.get("game_version") or "",
        }

    def mark_switch_done(self, done=True):
        """The user confirms the mods work on their Switch (step 5). Remembered
        against what was committed/built, so a later change makes it stale."""
        settings = self._load_settings()
        checked = sorted(k for k, v in self._load_state().items() if v)
        last_ui = settings.get("last_ui_build")
        sig = f"{self._commit_signature(checked)}:{last_ui.get('sig') if last_ui else ''}"
        self.save_settings({"switch_done": {"sig": sig, "at": datetime.now().isoformat(timespec="seconds")} if done else None})
        return True

    def complete_setup(self):
        self.save_settings({"setup_done": True})
        return True

    def open_staging_folder(self):
        """Opens the sd-card-staging folder Api.merge() writes into (next to
        the master directory) in the file manager, so the user never has to
        hunt for it."""
        return self.reveal_path(str(self.mod_root.parent / "sd-card-staging"))

    # --- Menu icons & text (see ui_setup.py) ---------------------------------
    # Mods that change a character's icon or a course's name each ship their own
    # copy of a shared archive (common.sarc / menu.sarc / message.sarc) that
    # Merge & Stage can't combine. These methods analyze every checked mod's
    # copy and build one combined file per archive into ui-icons/romfs/ (which
    # every merge already includes) - merge() calls the build automatically,
    # right before its own copy pass, so there's no separate step to run first.

    def _ui_setup_plan(self):
        """The cached analysis of every checked mod's packed UI archives -
        recomputed only when a source file changes or the set of checked mods
        does. One at a time: the background warm-up and a screen can ask together."""
        with self.__dict__.setdefault("_plan_lock", threading.RLock()):
            return self._ui_setup_plan_unlocked()

    def _ui_setup_plan_unlocked(self):
        checked = sorted(k for k, v in self._load_state().items() if v)
        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        game_files = self._game_files()
        sources = ui_setup.collect_sources(extracted, checked, game_files)
        signature = tuple(sorted(
            (str(s["path"]), s["path"].stat().st_mtime_ns, s["path"].stat().st_size)
            for group in sources.values() for s in group
        ))
        auto, needs = self._auto_icons()
        ov_sig = ui_setup.overrides_signature(self.mod_root) + "|" + ui_setup.auto_signature(auto, needs)
        cached = getattr(self, "_ui_plan_cache", None)
        if cached and cached[0] == signature:
            if cached[2] != ov_sig:  # only the user's own / automatic icons or names changed: re-apply, don't re-analyse
                ui_setup.apply_overrides(self.mod_root, cached[1], auto)
                self._ui_plan_cache = (signature, cached[1], ov_sig)
            return cached[1]
        cache_path = self.mod_root / "ui-setup-cache.json"
        plan = ui_setup.analyze_all(extracted, checked, cache_path, game_files)
        for archive_id in ui_setup.TEXTURE_ARCHIVES:
            if archive_id in plan:
                ui_setup.add_previews(plan[archive_id], cache_path)
        ui_setup.apply_overrides(self.mod_root, plan, auto)
        self._ui_plan_cache = (signature, plan, ov_sig)
        return plan

    def _ui_archive_view(self, archive_id, analysis, choices):
        variants = analysis["variants"]
        winners = ui_setup._winners(analysis, choices)
        chosen_by_item = {item: variants[idx]["id"] for item, idx in winners.items()}
        conflicts = []
        for item, idxs in analysis["conflicts"].items():
            change = next(c for i in idxs for c in variants[i]["changes"] if ui_setup.item_id(c) == item)
            conflicts.append({
                "item": item,
                "what": ui_setup._what(change),
                "options": [{"id": variants[i]["id"], "labels": variants[i]["labels"]} for i in idxs],
                "chosen": chosen_by_item.get(item),
            })
        return {
            "id": archive_id,
            "file": ui_setup.TEXTURE_ARCHIVES[archive_id]["file"] if archive_id in ui_setup.TEXTURE_ARCHIVES else "message.sarc",
            "locale": archive_id.split(":", 1)[1] if archive_id.startswith("message:") else None,
            "dest": str(ui_setup.archive_dest(self.mod_root, archive_id)),
            "confidence": analysis["confidence"],
            "base": {"labels": variants[analysis["base"]]["labels"], "entries": variants[analysis["base"]]["entries"],
                     "vanilla": bool(variants[analysis["base"]].get("vanilla"))},
            "nothing": not any(i != analysis["base"] for i in winners.values()),
            "versions": sorted({v["entries"] for v in variants}),
            "variants": [
                {
                    "id": v["id"], "labels": v["labels"], "filed_under": v["filed_under"],
                    "is_base": i == analysis["base"], "vanilla": bool(v.get("vanilla")), "entries": v["entries"], "path": v["path"],
                    "changes": v["changes"], "other": v.get("other", 0),
                }
                for i, v in enumerate(variants)
            ],
            "conflicts": conflicts,
            "verify": ui_setup.verify_archive(self.mod_root, archive_id, analysis, choices),
        }

    def get_ui_setup(self, locale=None):
        """For the Commit page's "Menu icons & text" card: for the icon archives and the chosen
        language's text archive, each checked mod's exact changes (with pictures), conflicts to
        pick between, what can't be merged automatically, and - for a finished file already in
        ui-icons/ - a check of it against the plan."""
        settings = self._load_settings()
        self._prune_stale_fills()
        try:
            plan = self._ui_setup_plan()
        except (OSError, ui_setup.ua.ArchiveError) as e:
            return {"error": f"Couldn't read your mods' UI files: {e}"}
        locale = locale or settings.get("ui_setup_locale") or "USen"
        choices = settings.get("ui_setup_choices") or {}
        locales = sorted(
            (
                {
                    "code": aid.split(":", 1)[1],
                    "label": ui_setup.LOCALES.get(aid.split(":", 1)[1], aid),
                    "mods": sum(len(v["keys"]) for v in a["variants"]),
                    "changes": sum(len(v["changes"]) for v in a["variants"]),
                }
                for aid, a in plan.items()
                if aid.startswith("message:") and any(v["changes"] for v in a["variants"])
            ),
            key=lambda x: x["label"],
        )
        wanted = [aid for aid in ("common", "menu", f"message:{locale}") if aid in plan]
        return {
            "locale": locale,
            "locale_label": ui_setup.LOCALES.get(locale, locale),
            "locales": locales,
            "all_locales": [{"code": c, "label": l} for c, l in ui_setup.LOCALES.items()],
            "archives": [self._ui_archive_view(aid, plan[aid], choices) for aid in wanted],
            "any_sources": any(v["changes"] for a in plan.values() for v in a["variants"] if not v.get("vanilla")),
            "game_files": self.get_base_files_status(),
            "icon_choices": self._auto_icons()[1],
            "ui_folder": str(self.mod_root / "ui-icons" / "romfs" / "UI"),
            "ui_icons_text": ui_icons_status_text(self.mod_root),
        }

    def _build_ui_archives(self, locales=None):
        """Builds the finished common.sarc, menu.sarc and message.sarc (for each language asked
        for, default the saved one) into ui-icons/romfs/, keeping a backup of any file it replaces,
        and checks each result. Doesn't stage the result anywhere - merge() calls this directly (its
        own copy pass right after already includes ui-icons/romfs); build_ui_setup() below is the
        version that also stages, for when this runs on its own from Settings."""
        settings = self._load_settings()
        self._prune_stale_fills()
        choices = settings.get("ui_setup_choices") or {}
        locales = locales or [settings.get("ui_setup_locale") or "USen"]
        try:
            plan = self._ui_setup_plan()
        except (OSError, ui_setup.ua.ArchiveError) as e:
            return {"success": False, "error": f"Couldn't read your mods' UI files: {e}"}
        ids = [aid for aid in ["common", "menu"] + [f"message:{l}" for l in locales] if aid in plan]
        results = []
        for archive_id in ids:
            analysis = plan[archive_id]
            if not any(i != analysis["base"] for i in ui_setup._winners(analysis, choices).values()):
                # nothing to change in this file: the game's own is used as it is
                dest = ui_setup.archive_dest(self.mod_root, archive_id)
                if dest.is_file():
                    ui_setup._backup(self.mod_root, dest)
                    dest.unlink()
                    staged = self._staging_romfs() / dest.relative_to(self.mod_root / "ui-icons" / "romfs")
                    if staged.is_file():
                        staged.unlink()
                results.append({"archive": archive_id, "nothing": True,
                                "report": {"archive": archive_id, "applied": [], "skipped": [], "backup": None, "written": None},
                                "verify": {"archive": archive_id, "exists": False, "items": [], "problems": [], "ok": 0, "total": 0}})
                continue
            try:
                report = ui_setup.build_archive(self.mod_root, archive_id, plan[archive_id], choices)
                verify = ui_setup.verify_archive(self.mod_root, archive_id, plan[archive_id], choices)
                results.append({"archive": archive_id, "report": report, "verify": verify})
            except (OSError, ui_setup.ua.ArchiveError) as e:
                results.append({"archive": archive_id, "error": str(e)})
        good = bool(results) and all(
            "error" not in r and r["verify"]["ok"] == r["verify"]["total"] for r in results)
        if good:
            self.save_settings({"last_ui_build": {
                "sig": self._ui_signature(), "at": datetime.now().isoformat(timespec="seconds")}})
        return {"success": True, "results": results}

    def build_ui_setup(self, locales=None):
        """_build_ui_archives(), plus staging the result right away - for Settings' manual
        "Rebuild now" (or "Check my work", which rebuilds nothing new but re-verifies), so looking
        at the result (Open the folder / a Switch already set up with an older commit) doesn't need
        a full commit first. A normal commit doesn't need this - merge() builds it directly."""
        result = self._build_ui_archives(locales)
        if not result.get("success"):
            return result
        staged = self.stage_ui_files()
        return {**result, "staged": staged}

    def _ui_signature(self):
        """What the built UI files were made from: every checked mod's packed UI
        archive (path + modification time), the language choice and the
        conflict picks. A change to any of them makes the built files stale."""
        checked = sorted(k for k, v in self._load_state().items() if v)
        sources = ui_setup.collect_sources(self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME, checked)
        parts = sorted(
            f"{s['key']}|{s['path'].stat().st_mtime_ns}|{s['path'].stat().st_size}"
            for group in sources.values() for s in group)
        settings = self._load_settings()
        parts.append(f"locale|{settings.get('ui_setup_locale') or 'USen'}|{bool(settings.get('ui_setup_extra_english'))}")
        parts.append(json.dumps(settings.get("ui_setup_choices") or {}, sort_keys=True))
        parts.append(ui_setup.overrides_signature(self.mod_root))
        parts.append(ui_setup.auto_signature(*self._auto_icons()))
        parts.extend(f"game|{aid}|{p.stat().st_mtime_ns}" for aid, p in sorted(self._game_files().items()))
        return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]

    def _staging_romfs(self):
        return self.mod_root.parent / "sd-card-staging" / "atmosphere" / "contents" / TITLE_ID / "romfs"

    def stage_ui_files(self):
        """Puts the built UI files into the staging folder right away, so
        finishing the UI step doesn't need a second commit. Only when a commit
        has already made a staging romfs - otherwise the next commit picks them
        up anyway. Returns how many files were staged."""
        out_romfs = self._staging_romfs()
        src_root = self.mod_root / "ui-icons" / "romfs"
        if not out_romfs.is_dir() or not src_root.is_dir():
            return 0
        n = 0
        for f in src_root.rglob("*"):
            if f.is_file():
                dest = out_romfs / f.relative_to(src_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                n += 1
        return n

    def reset_ui_setup(self, locales=None):
        """Undoes a build: moves the finished UI files out of ui-icons/ (into
        the backups folder) so the game falls back to its own."""
        settings = self._load_settings()
        locales = locales or [settings.get("ui_setup_locale") or "USen"]
        removed = []
        for archive_id in ["common", "menu"] + [f"message:{l}" for l in locales]:
            dest = ui_setup.archive_dest(self.mod_root, archive_id)
            if dest.is_file():
                ui_setup._backup(self.mod_root, dest)
                dest.unlink()
                removed.append(str(dest))
                # ...and out of the staging folder too, so undoing takes effect
                # on the next copy to the SD card without another commit.
                staged = self._staging_romfs() / dest.relative_to(self.mod_root / "ui-icons" / "romfs")
                if staged.is_file():
                    staged.unlink()
        self.save_settings({"last_ui_build": None})
        return {"success": True, "removed": removed}

    # --- "Menu look": what each menu screen shows for a character/course, and
    # letting the user supply an icon or name a mod doesn't ship (see
    # ui_setup's override section) -----------------------------------------------

    def _base_icon_preview(self, analysis, entry, texture_name):
        """A data-URL picture of a texture as it is in the plan's base file
        (used to show the game's own icon)."""
        base = analysis["variants"][analysis["base"]]
        path = Path(base["path"])
        stamp = image_cache.file_stamp(path)

        def build():
            memo = getattr(self, "_ui_base_tex", None)
            if memo is None:
                memo = self._ui_base_tex = {}
            key = (str(path), stamp, entry)
            if key not in memo:
                try:
                    memo[key] = ui_setup.ua.entry_texture_map(ui_setup.ua.parse_sarc(path.read_bytes())[entry])
                except (OSError, KeyError, ui_setup.ua.ArchiveError):
                    memo[key] = {}
            tex = memo[key].get(texture_name)
            return ui_setup.ua.texture_png(tex) if tex else None

        # (a picture already on disk doesn't even open the archive - the slow part)
        png = self._image_cache().picture(f"base-icon:{path}:{entry}:{texture_name}", stamp, build)
        return image_cache.data_uri(png) if png else None

    def _thumb_uri(self, path, size=96):
        """A small data-URL picture of an image file (None if unreadable)."""
        try:
            from PIL import Image
            with Image.open(path) as im:
                im = im.convert("RGBA")
                im.thumbnail((size, size))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

    def _menu_look_ctx(self):
        """Everything get_menu_look needs that doesn't depend on which item is asked about."""
        settings = self._load_settings()
        checked = sorted(k for k, v in self._load_state().items() if v)
        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        plan = {}
        if ui_setup.collect_sources(extracted, checked, self._game_files()):
            try:
                plan = self._ui_setup_plan()
            except (OSError, ui_setup.ua.ArchiveError) as e:
                return {"error": f"Couldn't read your mods' UI files: {e}"}
        auto, needs = self._auto_icons()
        return {"settings": settings, "checked": checked, "extracted": extracted, "plan": plan,
                "choices": settings.get("ui_setup_choices") or {}, "locale": settings.get("ui_setup_locale") or "USen",
                "ov": ui_setup.load_overrides(self.mod_root), "auto": auto, "needs": needs}

    @staticmethod
    def _tile_icon(slots):
        """The one icon a character tile draws: the first available of select-screen, results and
        map, preferring an actually-modded one at any of those kinds over a merely-vanilla one - a
        mod that only changes the map icon must still win the tile over the (always-available, once
        base files are set up) vanilla select-screen picture. Only when nothing is modded at all does
        the first vanilla picture show, so every tile still has something to draw. (kind, slot) or None."""
        order = ("Chara", "edChara", "MapChara")
        modded = next(((k, slots[k]) for k in order if k in slots and slots[k]["state"] != "vanilla" and slots[k].get("preview")), None)
        if modded:
            return modded
        return next(((k, slots[k]) for k in order if k in slots and slots[k].get("preview")), None)

    def get_character_tile_view(self, item_names, known_icons=None):
        """{"looks": get_character_looks(), "review": {name: _review_state()}} in one pass over
        the plan - what the character grid needs to draw its tiles. Every "looks" entry carries whatever
        picture will actually show - the game's own (once base files are set up) if nothing changes it,
        a mod's or the user's if something does ("icon_modded" says which) - so the grid can draw a
        picture on every tile, not only the modded ones. "voice": {name: {"race", "menu", "select", "from", "muted"}}
        for characters with a ticked mod that ships voice files for them (one whose voice files are for
        somebody else's slot doesn't count); "select": whether clicking the tile has a character-select
        sound to play." Every look with a picture also carries `icon_id` (a fingerprint of it); `known_icons` is {name: icon_id}
        of the pictures the page already holds - for those the picture itself is left out (`icon_known` true), since it is the
        biggest part of the answer and hardly ever changes."""
        ticked = self._ticked_by_char()
        voice = {}
        for name in item_names:
            found = {"race": False, "menu": False, "select": False, "from": []}
            for k in ticked.get(self._canon_char(name)) or []:
                unit = self._unit_dir(k)
                v = unit_voice(unit) if unit.is_dir() else None
                if v and any(v.values()) and not self._slot_mismatch(k):
                    found["race"] = found["race"] or v["race"]
                    found["menu"] = found["menu"] or v["menu"]
                    mod = k.split("/")[2] if k.count("/") >= 2 else k
                    if mod not in found["from"]:
                        found["from"].append(mod)
            if found["from"]:
                found["select"] = bool(found["menu"] and self._select_voice_source(name))
                found["muted"] = self._voice_all_muted(self._canon_char(name))   # (every sound silenced with the voice editor)
                voice[name] = found
        ctx = self._menu_look_ctx()
        if ctx.get("error"):
            return {"looks": {}, "review": {}, "voice": voice}
        looks, review = {}, {}
        for name in item_names:
            look = self.get_menu_look(name, "characters", ctx)
            if look.get("error"):
                continue
            slots = {s["kind"]: s for s in ((look.get("icons") or {}).get("slots") or [])}
            icon = self._tile_icon(slots)
            nm = look.get("name") or {}
            named = nm.get("state") in ("mod", "you")
            if icon or named:
                looks[name] = {
                    "icon": icon[1]["preview"] if icon else None, "icon_kind": icon[0] if icon else None,
                    "icon_from": icon[1]["who"] if icon else [],
                    "icon_modded": bool(icon and icon[1]["state"] != "vanilla"),
                    "name": nm.get("text") if named else None, "name_from": nm.get("who") if named else [],
                    "guessed": bool(named and nm.get("auto")),
                }
            keys = ticked.get(self._canon_char(name))
            if keys:
                icons_changed = any(s["state"] != "vanilla" for s in slots.values())
                name_changed = nm.get("state", "vanilla") != "vanilla"
                review[name] = self._review_state(self._canon_char(name), keys, name_changed, icons_changed)
        known = known_icons or {}
        for name, look in looks.items():
            if look["icon"]:
                look["icon_id"] = hashlib.sha1(look["icon"].encode("ascii", "ignore")).hexdigest()[:12]
                if known.get(name) == look["icon_id"]:
                    look["icon"], look["icon_known"] = None, True
        return {"looks": looks, "review": review, "voice": voice}

    def get_character_looks(self, item_names):
        """{name: {"icon", "icon_kind", "icon_from", "icon_modded", "name", "name_from", "guessed"}} for
        the characters with a picture or a name to show: the first icon available of the select-screen,
        results and map ones (the game's own, once base files are set up, or a mod's/the user's), and
        the modded name if there is one. A character with nothing at all - no base files yet and no
        mod that changes it - is left out. One pass over the plan for all of them (the character grid
        asks for every tile)."""
        ctx = self._menu_look_ctx()
        if ctx.get("error"):
            return {}
        out = {}
        for name in item_names:
            look = self.get_menu_look(name, "characters", ctx)
            if look.get("error"):
                continue
            slots = {s["kind"]: s for s in ((look.get("icons") or {}).get("slots") or [])}
            icon = self._tile_icon(slots)
            nm = look.get("name") or {}
            named = nm.get("state") in ("mod", "you")
            if not icon and not named:
                continue
            out[name] = {
                "icon": icon[1]["preview"] if icon else None, "icon_kind": icon[0] if icon else None,
                "icon_from": icon[1]["who"] if icon else [],
                "icon_modded": bool(icon and icon[1]["state"] != "vanilla"),
                "name": nm.get("text") if named else None, "name_from": nm.get("who") if named else [],
                "guessed": bool(named and nm.get("auto")),
            }
        return out

    @staticmethod
    def _icon_source_bytes(src):
        """The picture behind an icon slot's `src`: a data: URL (a mod's packed icon) or a file."""
        if src.startswith("data:"):
            return base64.b64decode(src.split(",", 1)[1])
        return Path(src).read_bytes()

    def get_menu_look(self, item_name, kind, _ctx=None, _sources=False):
        """What the menus will show for one character (`kind` "characters":
        three icons + name) or course ("courses": name), and where each comes
        from: the user ("you"), a mod's loose pictures the app picked on its own
        ("auto"), a mod's packed file ("mod"), or nothing ("vanilla").

        This only records and reads INTENT - it works with no game files at all.
        The analysis of packed mod files (slow the first time) is consulted only
        when some ticked mod actually ships them, to say what those change; the
        game's own files are needed later, when the UI step builds."""
        ctx = _ctx or self._menu_look_ctx()
        if ctx.get("error"):
            return {"error": ctx["error"]}
        settings, checked, extracted, plan = ctx["settings"], ctx["checked"], ctx["extracted"], ctx["plan"]
        choices, locale, ov, auto, needs = ctx["choices"], ctx["locale"], ctx["ov"], ctx["auto"], ctx["needs"]
        out = {"item": item_name, "kind": kind, "locale": locale, "icons": None, "name": None, "enriched": bool(plan)}

        def packed_winner(archive_id, iid):
            """(analysis, (variant, change)) for a change a mod's own packed file makes."""
            analysis = plan.get(archive_id)
            if not analysis:
                return None, None
            idx = ui_setup._winners(analysis, choices).get(iid)
            if idx is None:
                return analysis, None
            v = analysis["variants"][idx]
            if v.get("is_override"):
                return analysis, None
            return analysis, (v, next(c for c in v["changes"] if ui_setup.item_id(c) == iid))

        def blocked_reason(archive_id, iid):
            """(mods, reason) when a mod's icon for this texture exists but can't be swapped in."""
            for v in (plan.get(archive_id) or {}).get("variants", []):
                for c in v["changes"]:
                    if c.get("mergeable") is False and ui_setup.item_id(c) == iid:
                        return v["labels"], c.get("reason")
            return None

        if kind == "characters":
            code = ui_setup.code_for_character(item_name)
            if code:
                slots = []
                superseded = []
                order = ("you", "mod", "auto", "included")
                for k, archive_id, entry, label in ui_setup.CHARACTER_SLOTS:
                    per = []  # one entry per colour (one for most characters)
                    for stem, iid in zip(ui_setup.item_textures(code), ui_setup.slot_items(k, code)):
                        analysis, won = packed_winner(archive_id, iid)
                        v = {"state": "vanilla", "who": [], "preview": None, "blocked": None, "id": iid, "resized": False,
                             "filled": False, "fill_sig": None, "src": None}
                        blocked = blocked_reason(archive_id, iid)
                        o = ov["textures"].get(iid)
                        if o and o.get("fill") and (won or (iid in auto and not blocked)):
                            superseded.append(iid)   # a picture the mod really brings outranks one made from the Select screen
                            o = None
                        if o and not (blocked and blocked[0] == ["Your changes"]):
                            v.update(state="you", who=[o.get("from") or "Your picture"], preview=self._thumb_uri(self.mod_root / o["png"]),
                                     filled=bool(o.get("fill")), fill_sig=o.get("fill_sig"), src=str(self.mod_root / o["png"]))
                        elif won:
                            v.update(state="mod", who=won[0]["labels"], preview=won[1].get("preview"), resized=bool(won[1].get("rescale")),
                                     src=won[1].get("preview"))
                        elif iid in auto and not blocked:
                            v.update(state="auto", who=[auto[iid]["from"]], preview=self._thumb_uri(auto[iid]["png"]), src=str(auto[iid]["png"]))
                        else:
                            if blocked:
                                v["blocked"] = {"who": blocked[0], "reason": blocked[1]}
                            if analysis:
                                v["preview"] = self._base_icon_preview(analysis, entry, f"tc_{k}_{stem}^l")
                                b = analysis["variants"][analysis["base"]]
                                if (analysis["confidence"] == "single" and not b.get("vanilla")
                                        and item_name in b["filed_under"] and not blocked):
                                    # the only copy of these files there is, from a mod filed under this
                                    # character: with nothing to compare against the app can't say which of
                                    # its icons the mod changed - but they ARE in the file and will be used
                                    v.update(state="included", who=b["labels"], src=v["preview"])
                        per.append(v)
                    # what a mod really brings outranks a picture made from another one (see fill_missing_icons)
                    real = [p for p in per if p["state"] != "vanilla" and not p["filled"]]
                    pool = real or [p for p in per if p["state"] != "vanilla"]
                    state = next((st for st in order if any(p["state"] == st for p in pool)), "vanilla")
                    chosen = [p for p in pool if p["state"] == state]
                    blocked_all = [p["blocked"] for p in per if p["blocked"]]
                    slots.append({
                        "id": per[0]["id"], "kind": k, "label": label, "available": True, "state": state,
                        "who": sorted({w for p in chosen for w in p["who"]}),
                        "preview": next((p["preview"] for p in chosen if p["preview"]), per[0]["preview"]),
                        "variants": len(per), "changed": len(chosen) if state != "vanilla" else 0,
                        "resized": any(p["resized"] for p in chosen),
                        "blocked": ({"count": len(blocked_all), "reason": blocked_all[0]["reason"],
                                     "who": blocked_all[0]["who"]} if blocked_all else None),
                        "filled": state == "you" and all(p["filled"] for p in chosen),
                    })
                    if len(per) > 1 or _sources:
                        # one entry per colour, so the card can show each colour on its own
                        slots[-1]["per"] = [{"id": p["id"], "state": p["state"], "preview": p["preview"], "blocked": bool(p["blocked"]),
                                             "filled": p["filled"], "fill_sig": p["fill_sig"], "who": p["who"], **({"src": p["src"]} if _sources else {})}
                                            for p in per]
                # A picture made from the Select screen one (see fill_missing_icons) only stands while that Select
                # screen picture is what it was made from - change the mod, and it has to go, or it would outlive
                # its source (and keep an automatic pick from a new mod out of its slot).
                if not _sources:
                    stale = superseded + self._stale_fills(item_name, code, ov, ctx)
                    if stale:
                        for iid in stale:
                            ov["textures"].pop(iid, None)
                        ui_setup.save_overrides(self.mod_root, ov)
                        return self.get_menu_look(item_name, kind, _ctx=_ctx)
                out["icons"] = {"code": code, "slots": slots, "needs_choice": any(n["item"] == item_name for n in needs)}

        display = item_name
        if kind == "courses":
            for p in ui_setup._COURSE_PREFIXES:
                if display.startswith(p):
                    display = display[len(p):]
        name = {"available": True, "vanilla": display, "text": display, "state": "vanilla", "who": []}
        found = ui_setup.find_name_labels(plan, item_name, kind)  # the shipped table answers without any game file
        if found:
            name["vanilla"] = name["text"] = found["vanilla"]
        mine = ov["names"].get(f"{kind}|{item_name}")
        legacy = next((o for o in ov["strings"].values() if o.get("who") == item_name and o.get("kind") == kind), None)
        if mine or legacy:
            name.update(state="you", text=(mine or legacy)["text"])
            if mine and mine.get("auto"):
                name.update(auto=True, source=mine.get("source"))   # guessed from the mod, not typed by the user
        elif plan and found:
            an = plan.get(f"message:{locale}")
            label = f"Common.msbt|{found['labels'][0]}"
            _a, won = packed_winner(f"message:{locale}", label)
            if won:
                name.update(state="mod", who=won[0]["labels"], text=won[1]["new"])
            elif an and an["confidence"] == "single" and not an["variants"][an["base"]]["vanilla"] \
                    and locale in ("USen", "EUen") and item_name in an["variants"][an["base"]]["filed_under"]:
                # a single mod's own text file: what it says at this name's entry, if it isn't the game's name
                text = ui_setup.base_text(an, "Common.msbt", found["labels"][0])
                if text and text != found["vanilla"]:
                    name.update(state="mod", who=an["variants"][an["base"]]["labels"], text=text)
        out["name"] = name
        if kind == "characters":
            keys = self._ticked_by_char().get(self._canon_char(item_name))
            if keys:
                slots = (out.get("icons") or {}).get("slots") or []
                icons_changed = any(s["state"] != "vanilla" for s in slots)
                name_changed = name.get("state", "vanilla") != "vanilla"
                out["review"] = self._review_state(self._canon_char(item_name), keys, name_changed, icons_changed)
        return out

    def warm_ui_analysis(self):
        """Starts getting everything the screens will ask for ready in the background (right after the app starts) - the
        ticked mods' menu files, the game's pictures, the decompressed icon archives - so the first card, and the first
        time on each screen, open as fast as the later ones. Returns at once; see _warm_up()."""
        self._start_warmup()
        return True

    def _start_warmup(self):
        if self.mod_root is None:
            return
        self._warm_gen = getattr(self, "_warm_gen", 0) + 1
        threading.Thread(target=self._warm_up, args=(self._warm_gen,), daemon=True, name="warm-caches").start()

    def _warm_up(self, gen):
        """Runs what each screen would run the first time, one step after the other, and throws the answers away - the point
        is what it leaves behind: the disk caches (image-cache/) and this run's memory caches. Once everything is on disk a
        pass costs a fraction of a second. A step that fails is skipped (the screen will meet the same problem itself and
        say so); a new "Update from a new dump" (which bumps _warm_gen) ends a pass that is still running for the old one."""
        if self._game_files().get("menu") is None:
            return   # (no copy of the game's files yet: nothing to warm)
        try:
            names = [r["name"] if isinstance(r, dict) else r for r in self._load_roster()]
            course_names = [c["name"] for cup in self._load_course_roster() for c in cup["courses"]]
        except (OSError, ValueError, KeyError, TypeError):
            return
        steps = (
            self._ui_setup_plan,                                   # (the ticked mods' menu files)
            self.get_cup_icons,
            lambda: self.get_course_default_pictures(course_names),
            self.get_vehicle_icons,
            self.get_item_icons,
            lambda: self.get_character_tile_view(names),           # (the character icons, and the archives behind them)
            self.get_ui_setup,
        )
        for step in steps:
            if gen != getattr(self, "_warm_gen", gen):
                return
            try:
                step()
            except Exception:
                pass
            time.sleep(0.05)   # (leave the page's own requests a turn)

    # --- the user's own game files (the base the UI step builds on) -----------

    def _game_files(self):
        return game_files.find_current(self.mod_root)

    def _image_cache(self):
        """The disk cache of decoded pictures (see image_cache.py) - kept in the master folder, so it follows it."""
        return image_cache.ImageCache(None if self.mod_root is None else self.mod_root / image_cache.DIRNAME)

    def _decoded_pict(self, name, path, crop_box=None):
        """PNG bytes of a .bntx picture, decoded once and then read back from the disk cache; None when it can't be
        decoded (that is not remembered, so it is tried again next time)."""
        def build():
            try:
                return bntx_decode.decode_to_png(path, crop_box=crop_box)
            except (bntx_decode.UnsupportedBNTXError, OSError):
                return None
        return self._image_cache().picture(name, (image_cache.file_stamp(path), crop_box), build)

    def get_cup_icons(self):
        """{cup name: PNG data URI} - the game's own Grand Prix medallions for the Courses screen, decoded from the app's
        copy of menu.sarc (see cup_icons.py). {} when that copy isn't there (before Setup) or can't be read; the screen
        then keeps its plain tiles. Decoded once per copy: the answer is remembered until menu.sarc changes."""
        if self.mod_root is None:
            return {}
        menu = self._game_files().get("menu")
        if menu is None:
            return {}
        try:
            stamp = (str(menu), menu.stat().st_mtime_ns, menu.stat().st_size)
        except OSError:
            return {}
        cached = getattr(self, "_cup_icon_cache", None)
        if cached is None or cached[0] != stamp:
            icons = self._image_cache().group("cups", stamp, lambda: cup_icons.load(menu))
            self._cup_icon_cache = cached = (stamp, icons)
        return cached[1]

    # --- the game's own course-select pictures ---------------------------------------------------
    # The base game copy holds each course's own picture (UI/cmn/menu/ym_CoursePict_<id>_00^u.bntx - see game_files.py).
    # Base-game courses are named by their internal id (Gu_FirstCircuit; Animal Crossing's four seasons share Du_Animal);
    # the Booster Course Pass's 48 are DLC01..DLC48 in the pass's order (checked against the pictures), while their internal
    # ids are Cnsw_NN.

    def _course_pict_ids(self, course_name):
        """Candidate picture ids for a course, best first."""
        ids = []
        for i in sorted(self._course_internal_names(course_name) or []):
            ids.append(i)
            plain = re.sub(r"_(Spring|Summer|Autumn|Winter)$", "", i)
            if plain != i:
                ids.append(plain)
        n, started = 0, False
        for cup in self._load_course_roster():
            started = started or cup["cup"] == DLC_FIRST_CUP
            for c in cup["courses"]:
                if started:
                    n += 1
                    if c["name"] == course_name:
                        ids.append(f"DLC{n:02d}")
        return ids

    def _default_course_pict(self, course_name):
        """PNG data URI of the game's own picture for a course (cropped to its visible window, like a mod's), or None."""
        if self.mod_root is None:
            return None
        for pid in self._course_pict_ids(course_name):
            path = game_files.find_current_course_pict(self.mod_root, pid)
            if path is None:
                continue
            cache = self.__dict__.setdefault("_default_pict_cache", {})
            stamp = (str(path), path.stat().st_mtime_ns)
            if cache.get(pid, (None,))[0] != stamp:
                png = self._decoded_pict(f"course-default:{pid}", path, _COURSE_PICT_CROP_BOX)
                cache[pid] = (stamp, image_cache.data_uri(png) if png else None)
            if cache[pid][1]:
                return cache[pid][1]
        return None

    def get_course_default_pictures(self, course_names):
        """{course name: PNG data URI} - the game's own course-select picture for each course asked about that has one.
        A base-game copy made before pictures were part of it gets them added from the folder it was made from, if that is
        still there (once per run - see game_files.top_up_pictures())."""
        if self.mod_root is None:
            return {}
        self._top_up_pictures_once()
        return {n: uri for n in course_names for uri in [self._default_course_pict(n)] if uri}

    def _top_up_pictures_once(self):
        if self.__dict__.get("_picture_topup_done"):
            return
        self._picture_topup_done = True
        try:
            game_files.top_up_pictures(self.mod_root)
        except OSError:
            pass

    def get_vehicle_icons(self):
        """{part name: PNG data URI} - the game's own picture of every vehicle part (body, tire, glider) that has one, for
        the Vehicles screen (see vehicle_icons.py). {} before Setup or when the copy can't be read; the tiles then keep
        their plain names. Decoded once per copy: remembered until menu.sarc changes."""
        if self.mod_root is None:
            return {}
        menu = self._game_files().get("menu")
        if menu is None:
            return {}
        self._top_up_pictures_once()
        try:
            stamp = (str(menu), menu.stat().st_mtime_ns, menu.stat().st_size,
                     len([f for f in vehicle_icons.LOOSE_FILENAMES if game_files.find_current_vehicle_pict(self.mod_root, f)]))
        except OSError:
            return {}
        cached = getattr(self, "_vehicle_icon_cache", None)
        if cached is None or cached[0] != stamp:
            parts = [(section, item["name"], item.get("internal"))
                     for section, items in self._load_vehicle_roster().items() for item in items]
            loose = game_files.current_vehicle_picts(self.mod_root)
            disk_stamp = (stamp[:3], parts, sorted((n, image_cache.file_stamp(p)) for n, p in loose.items()))
            icons = self._image_cache().group("vehicles", disk_stamp, lambda: vehicle_icons.load(
                menu, parts, lambda f: game_files.find_current_vehicle_pict(self.mod_root, f)))
            self._vehicle_icon_cache = cached = (stamp, icons)
        return cached[1]

    def get_item_icons(self):
        """{item name: PNG data URI} - the game's own picture of every item that has one, for the Items screen (see
        item_icons.py). {} before Setup or when the copy can't be read; the tiles then keep their plain names. Decoded once per
        copy: remembered until menu.sarc changes."""
        if self.mod_root is None:
            return {}
        menu = self._game_files().get("menu")
        if menu is None:
            return {}
        try:
            stamp = (str(menu), menu.stat().st_mtime_ns, menu.stat().st_size)
        except OSError:
            return {}
        cached = getattr(self, "_item_icon_cache", None)
        if cached is None or cached[0] != stamp:
            roster = self._load_item_roster()
            icons = self._image_cache().group("items", (stamp[1:], [(i["name"], i.get("icon")) for i in roster]),
                                              lambda: item_icons.load(menu, roster))
            self._item_icon_cache = cached = (stamp, icons)
        return cached[1]

    def get_base_files_status(self):
        """{"done", "source" (shown for reference only - it doesn't need to still exist), "copied_at", "icons",
        "locales", "voice_found", "voice_total", "problems"} - the app's own local copy of the base game's files
        (see game_files.py), which both "UI icons & text" and default-voice muting are built on. Plus "copy_dir" (the
        folder holding the copy) and "source_exists" (whether the folder it was made from is still there), for the
        "you can delete your original dump" message."""
        st = game_files.status(self.mod_root)
        if self.mod_root is not None:
            st["copy_dir"] = str(self.mod_root / game_files.DIRNAME)
        st["source_exists"] = bool(st.get("source")) and Path(st["source"]).is_dir()
        return st

    def set_base_files_source(self, path):
        """Copies the base game files from `path` (both the pristine and working copies - see game_files.py),
        replacing whatever copy was there before ("Update from a new dump" in Settings). {"success", "status"} or
        {"success": False, "error": "plain words"}; nothing already copied is touched when this fails."""
        res = game_files.copy_both(path, self.mod_root)
        if not res["success"]:
            return res
        self._ui_plan_cache = None
        self._image_cache().clear()   # (a new dump can hold different pictures behind the same file sizes and dates)
        for attr in ("_cup_icon_cache", "_vehicle_icon_cache", "_item_icon_cache", "_default_pict_cache", "_ui_base_tex"):
            self.__dict__.pop(attr, None)
        ui_setup.ua.forget_decompressed()
        self._start_warmup()   # (bumps _warm_gen: a pass still running for the old dump stops)
        self.sync_voice_edits()
        return {"success": True, "status": game_files.status(self.mod_root)}

    def pick_base_files_source(self):
        """Native folder picker for the above."""
        chosen = self.pick_master_dir()
        if not chosen:
            return {"success": False, "cancelled": True}
        return self.set_base_files_source(chosen)

    def _select_sources(self, item_name, ctx=None):
        """The Select-screen picture behind each colour of a character: [{"state", "src"}] - or None."""
        look = self.get_menu_look(item_name, "characters", _ctx=ctx, _sources=True)
        icons = look.get("icons") if isinstance(look, dict) else None
        if not icons:
            return None, None
        slots = {s["kind"]: s for s in icons["slots"]}
        return slots, [{"state": p["state"], "src": p.get("src"), "id": p["id"]} for p in slots["Chara"]["per"]]

    def _stale_fills(self, item_name, code, ov, ctx=None):
        """Slot items whose "made from the Select screen" picture no longer matches that Select screen picture."""
        fills = {}
        for k in ("MapChara", "edChara"):
            for i, iid in enumerate(ui_setup.slot_items(k, code)):
                o = ov["textures"].get(iid)
                if o and o.get("fill"):
                    fills[iid] = (i, o)
        if not fills:
            return []
        slots, sel = self._select_sources(item_name, ctx)
        stale = []
        for iid, (i, o) in fills.items():
            cur = sel[i] if sel and i < len(sel) else None
            sig = None
            if cur and cur["state"] != "vanilla" and cur["src"]:
                try:
                    sig = hashlib.sha1(self._icon_source_bytes(cur["src"])).hexdigest()[:12]
                except (OSError, ValueError):
                    sig = None
            if sig is None or sig != o.get("fill_sig"):
                stale.append(iid)
        return stale

    def fill_missing_icons(self, item_name, colour=None, kinds=None):
        """For a character whose mod ships a Select-screen picture but not (all of) the Mini map / Results ones:
        makes the missing ones from the Select-screen picture (scaled down when the menus are built), so the
        game's own Mini map / Results picture doesn't show beside a modded Select screen. `colour` limits it to
        one colour of a colour-variant character (0-based), `kinds` to some of "MapChara" / "edChara"."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return {"success": False, "error": f"Don't know the game's internal id for {item_name}."}
        slots, sel = self._select_sources(item_name)
        if not sel:
            return {"success": False, "error": "Couldn't read what the menus show for this character."}
        want = [k for k in ("MapChara", "edChara") if not kinds or k in kinds]
        ov = ui_setup.load_overrides(self.mod_root)
        stored, filled = {}, 0
        for i, s in enumerate(sel):
            if (colour is not None and i != colour) or s["state"] == "vanilla" or not s["src"]:
                continue
            for k in want:
                tgt = slots[k]["per"][i]
                if tgt["state"] != "vanilla" or tgt["blocked"]:
                    continue
                try:
                    if s["src"] not in stored:
                        data = self._icon_source_bytes(s["src"])
                        stored[s["src"]] = (ui_setup.store_icon_picture(self.mod_root, data), hashlib.sha1(data).hexdigest()[:12])
                except Exception as e:
                    return {"success": False, "error": f"Couldn't use the Select screen picture: {e}"}
                rel, sig = stored[s["src"]]
                ov["textures"][tgt["id"]] = {"png": rel, "who": item_name, "from": "the Select screen picture", "fill": True, "fill_sig": sig}
                if tgt["id"] in ov["declined"]:
                    ov["declined"].remove(tgt["id"])
                filled += 1
        if not filled:
            return {"success": False, "error": "There's nothing missing to fill in."}
        ui_setup.save_overrides(self.mod_root, ov)   # (not "checked": the user looks at the result and confirms it)
        return {"success": True, "filled": filled}

    def unfill_icons(self, item_name, kinds=None, colour=None):
        """Takes back the pictures fill_missing_icons made (the game's own Mini map / Results show again);
        `colour` limits it to one colour of a colour-variant character (0-based)."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return {"success": True, "removed": 0}
        ov = ui_setup.load_overrides(self.mod_root)
        removed = 0
        for k in self._override_kinds(kinds):
            for i, iid in enumerate(ui_setup.slot_items(k, code)):
                if (colour is None or i == colour) and (ov["textures"].get(iid) or {}).get("fill"):
                    del ov["textures"][iid]
                    removed += 1
        if removed:
            ui_setup.save_overrides(self.mod_root, ov)
        return {"success": True, "removed": removed}

    def _prune_stale_fills(self):
        """Before anything is built: drop filled-in pictures whose Select screen picture changed."""
        ov = ui_setup.load_overrides(self.mod_root)
        items = {o.get("who") for o in ov["textures"].values() if o.get("fill")}
        for item in items:
            if item and ui_setup.code_for_character(item):
                self.get_menu_look(item, "characters")   # (drops stale ones itself)

    def _override_kinds(self, kinds):
        allowed = [k for k, _a, _e, _l in ui_setup.CHARACTER_SLOTS]
        return [k for k in (kinds or allowed) if k in allowed]

    def _loose_icon_sets(self, mod_folder, filed_under=None):
        """ui_setup.find_loose_icon_sets() for a mod folder; `filed_under` is the character folder it sits in."""
        return ui_setup.find_loose_icon_sets(mod_folder, ui_setup.code_for_character(filed_under) if filed_under else None)

    def _auto_icons(self):
        """(auto picks, characters needing a choice) for the ticked mods - see
        ui_setup.gather_auto_icons()."""
        checked = sorted(k for k, v in self._load_state().items() if v)
        return self._library.get(
            "auto_icons", (tuple(checked), ui_setup.overrides_signature(self.mod_root)),
            lambda: ui_setup.gather_auto_icons(
                self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME, checked, ui_setup.load_overrides(self.mod_root)),
            token=self._extracted_token, max_age=20, copy=copy.deepcopy)

    def get_icon_only_mods(self, item_name):
        """UI-icons-only downloads filed under this character - no mergeable
        romfs, so they never appear as a checkbox in "Mods to merge", but they
        do supply loose icon pictures ui_setup.gather_auto_icons() folds into
        this character's tile regardless of whether anything else is ticked
        (see _download_and_extract_one's "(icon pictures)" naming). Surfaced
        here so the mods list can show they exist instead of leaving them
        invisible. [{"mod", "kinds" (of this character's icon this download is
        currently supplying, if any - empty once every candidate kind has been
        turned down or a better source took over)}]."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return []
        item_dir = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / "characters" / sanitize_filename(item_name)
        if not item_dir.is_dir():
            return []
        auto, _needs = self._auto_icons()
        source_of = {iid: a["from"] for iid, a in auto.items()}
        out = []
        for mod in sorted(item_dir.iterdir()):
            if not mod.is_dir() or not ui_setup._ships_no_romfs(mod):
                continue
            if not ui_setup.find_loose_icon_sets(mod, code):
                continue
            kinds = [k for k in ("Chara", "edChara", "MapChara")
                     if any(source_of.get(iid) == mod.name for iid in ui_setup.slot_items(k, code))]
            out.append({"mod": mod.name, "kinds": kinds})
        return out

    def get_loose_icon_sets(self, item_name):
        """Icon pictures shipped as loose files by the mods that matter to this
        character: mods filed under it (ticked or not - a UI-only download can't
        be ticked) and mods filed elsewhere whose pictures are NAMED for this
        character. [{"mod", "label", "here" (filed under this character),
        "sets": [{"id", "label", "complete", "for" (the other character the
        pictures are named for, else None), "count", "kinds": {kind: {"preview",
        "size"}}}]}]."""
        from PIL import Image
        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        item_code = ui_setup.code_for_character(item_name)
        folders = {}
        chars = extracted / "characters"
        if chars.is_dir():
            for item_dir in chars.iterdir():
                if item_dir.is_dir():
                    for d in item_dir.iterdir():
                        if d.is_dir():
                            folders[f"characters/{item_dir.name}/{d.name}"] = item_dir.name
        out = []
        for mod, filed in sorted(folders.items(), key=lambda kv: (ui_setup.code_for_character(kv[1]) != item_code, kv[0])):
            here = ui_setup.code_for_character(filed) == item_code
            sets = []
            for n, st in enumerate(self._loose_icon_sets(extracted / Path(*mod.split("/")), filed)):
                _targets, other = ui_setup.resolve_pictures(st["pictures"], item_code) if item_code else ({}, None)
                named_for_me = item_code in ui_setup.picture_codes(st["pictures"])
                if not here and not named_for_me:
                    continue
                kinds = {}
                for kind, path in st["files"].items():
                    try:
                        with Image.open(path) as im:
                            size = im.size
                            thumb = im.convert("RGBA")
                            thumb.thumbnail((96, 96))
                            buf = io.BytesIO()
                            thumb.save(buf, format="PNG")
                    except Exception:
                        continue
                    kinds[kind] = {"preview": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
                                   "size": f"{size[0]}x{size[1]}"}
                if kinds:
                    sets.append({"id": st["suffix"], "label": f"Version {n + 1}", "kinds": kinds, "complete": len(kinds) == 3,
                                 "count": len(st["pictures"]), "colours": len({p["code"] for p in st["pictures"] if p.get("code")}),
                                 "for": ui_setup.CHARACTER_CODES.get(other) if other else None})
            if sets:
                out.append({"mod": mod, "label": mod.split("/")[2], "here": here, "filed": filed, "sets": sets})
        return out

    def get_mod_icon_pictures(self, item_name, colour=None):
        """The icon pictures the mods provide for this character, for the picture window ("Change picture") to
        offer first: [{"key", "kind" (Chara / MapChara / edChara), "colour" (0-based or None), "from" (mod name),
        "preview"}]. Two sources: what the ticked mods already bring into this character's menu icons (loose pictures
        or a packed menu file), and any other loose pictures in the mods filed under this character or named for it.
        For a character with colours, `colour` picks one (default: the first that has pictures)."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return []
        out, seen = [], set()

        def add(key, kind, col, who, data, preview, named_for=None):
            sig = hashlib.sha1(data).hexdigest()
            if sig in seen or len(out) >= 24 or (named_for and sum(1 for o in out if o["for"]) >= 6):
                return
            seen.add(sig)
            out.append({"key": key, "kind": kind, "colour": col, "from": who, "preview": preview, "for": named_for})

        look = self.get_menu_look(item_name, "characters", _sources=True)
        slots = {s["kind"]: s for s in ((look.get("icons") or {}).get("slots") or [])} if isinstance(look, dict) else {}
        n_col = len(slots["Chara"]["per"]) if "Chara" in slots else 1
        if n_col > 1 and colour is None:
            colour = next((i for i in range(n_col) if any(slots[k]["per"][i]["state"] in ("mod", "auto", "included")
                                                          for k in slots)), 0)
        for kind in ("Chara", "MapChara", "edChara"):
            s = slots.get(kind)
            for i, p in enumerate(s["per"] if s else []):
                if (colour is not None and i != colour) or p["state"] not in ("mod", "auto", "included") or not p.get("src"):
                    continue
                try:
                    data = self._icon_source_bytes(p["src"])
                except (OSError, ValueError):
                    continue
                add(f"slot:{kind}:{i}", kind, i if n_col > 1 else None, ", ".join(p["who"]) or "the mod", data, p["preview"])

        extracted = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME
        chars = extracted / "characters"
        if chars.is_dir():
            for item_dir in sorted(chars.iterdir()):
                if not item_dir.is_dir():
                    continue
                here = ui_setup.code_for_character(item_dir.name) == code
                for d in sorted(item_dir.iterdir()):
                    if not d.is_dir():
                        continue
                    for st in self._loose_icon_sets(d, item_dir.name):
                        for pic in st["pictures"]:
                            cls = ui_setup.classify_code(pic["code"]) if pic.get("code") else None
                            if cls and cls[0] != code:
                                # named for another character: offered last, and only from a mod filed under this one
                                if here:
                                    try:
                                        other_path = Path(pic["path"])
                                        prev = self._thumb_uri(other_path)
                                        if prev:
                                            add(f"file:characters/{item_dir.name}/{d.name}|{other_path.relative_to(d).as_posix()}", pic["kind"],
                                                None, d.name, other_path.read_bytes(), prev,
                                                ui_setup.CHARACTER_CODES.get(cls[0]) or cls[0])
                                    except OSError:
                                        pass
                                continue
                            if not here and not cls:
                                continue                       # a made-up name in a mod filed elsewhere isn't about this character
                            idx = int(cls[1]) if cls and cls[1] is not None else None
                            if colour is not None and idx is not None and idx != colour:
                                continue
                            path = Path(pic["path"])
                            try:
                                data = path.read_bytes()
                            except OSError:
                                continue
                            prev = self._thumb_uri(path)
                            if prev:
                                add(f"file:characters/{item_dir.name}/{d.name}|{path.relative_to(d).as_posix()}", pic["kind"],
                                    idx, d.name, data, prev)
        order = {"Chara": 0, "MapChara": 1, "edChara": 2}
        out.sort(key=lambda x: (bool(x["for"]), order.get(x["kind"], 9)))
        return out

    def use_mod_icon_picture(self, item_name, key, kinds=None, colour=None):
        """Uses one of get_mod_icon_pictures()'s pictures for the chosen icon(s) - no cropping, they are icons already."""
        try:
            if key.startswith("slot:"):
                _t, kind, idx = key.split(":")
                slots, _sel = self._select_sources(item_name)
                src = slots[kind]["per"][int(idx)].get("src") if slots else None
                if not src:
                    return {"success": False, "error": "That picture isn't there any more."}
                data = self._icon_source_bytes(src)
            elif key.startswith("file:"):
                mod, rel = key[5:].split("|", 1)
                base = (self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / Path(*mod.split("/"))).resolve()
                path = (base / rel).resolve()
                if base not in path.parents or not path.is_file():
                    return {"success": False, "error": "That picture isn't there any more."}
                data = path.read_bytes()
            else:
                return {"success": False, "error": "Unknown picture."}
        except (OSError, ValueError, KeyError, IndexError) as e:
            return {"success": False, "error": f"Couldn't read that picture: {e}"}
        return self._set_icons(item_name, data, kinds, colour)

    def use_loose_icon_set(self, item_name, mod, set_id):
        """Uses one version of a mod's loose icon pictures as this character's
        menu icons - all of them, in the right texture (a picture named for one
        colour goes to that colour; one named for the mod's own character goes to
        every colour). The user asking for it also overrides "these are named for
        another character"."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return {"success": False, "error": f"Don't know the game's internal id for {item_name}."}
        folder = self.mod_root / MODS_DIRNAME / EXTRACTED_DIRNAME / Path(*mod.split("/"))
        chosen = next((s for s in self._loose_icon_sets(folder, mod.split("/")[1]) if s["suffix"] == set_id), None)
        if chosen is None:
            return {"success": False, "error": "Those pictures are no longer in the mod's folder."}
        targets, _other = ui_setup.resolve_pictures(chosen["pictures"], code, explicit=True)
        ov = ui_setup.load_overrides(self.mod_root)
        stored = {}
        for item, path in targets.items():
            try:
                if path not in stored:
                    stored[path] = ui_setup.store_icon_picture(self.mod_root, path.read_bytes())
            except Exception as e:
                return {"success": False, "error": f"Couldn't use {path.name}: {e}"}
            ov["textures"][item] = {"png": stored[path], "who": item_name, "from": mod.split("/")[2]}
            if item in ov["declined"]:
                ov["declined"].remove(item)
        ui_setup.save_overrides(self.mod_root, ov)
        return {"success": True, "used": sorted(chosen["files"])}

    # (Picking, replacing or resetting icons never counts as "checking" the character: the card stays open so the
    # user sees the result and confirms it with "Looks right" - as with fill_missing_icons().)
    def _set_icons(self, item_name, png_bytes, kinds, colour=None):
        code = ui_setup.code_for_character(item_name)
        if not code:
            return {"success": False, "error": f"Don't know the game's internal id for {item_name}."}
        try:
            rel = ui_setup.store_icon_picture(self.mod_root, png_bytes)
        except Exception as e:  # PIL raises a variety
            return {"success": False, "error": f"Couldn't use that picture: {e}"}
        ov = ui_setup.load_overrides(self.mod_root)
        for k in self._override_kinds(kinds):
            for i, item in enumerate(ui_setup.slot_items(k, code)):  # every colour of a colour-variant character (or just `colour`)
                if colour is not None and i != colour:
                    continue
                ov["textures"][item] = {"png": rel, "who": item_name}
                if item in ov["declined"]:
                    ov["declined"].remove(item)
        ui_setup.save_overrides(self.mod_root, ov)
        return {"success": True}

    def set_character_icons_from_url(self, item_name, image_url, crop_x, crop_y, crop_w, crop_h, kinds=None, colour=None):
        """Uses (a crop of) an image from the web - one of a mod's own
        GameBanana screenshots - as a character's menu icons."""
        try:
            image_bytes = gamebanana_api.fetch_bytes(image_url)
            from PIL import Image
            src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            cropped = src.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
        except gamebanana_api.GameBananaError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Couldn't process that image: {e}"}
        return self._set_icons(item_name, buf.getvalue(), kinds, colour)

    def set_character_icons_from_data(self, item_name, data_url, kinds=None, colour=None):
        """Same, for a picture the user chose from their own computer (already
        cropped in the page, sent as a data: URL)."""
        try:
            png = base64.b64decode(data_url.split(",", 1)[1])
        except (IndexError, ValueError):
            return {"success": False, "error": "That picture couldn't be read."}
        return self._set_icons(item_name, png, kinds, colour)

    def clear_character_icons(self, item_name, kinds=None, colour=None):
        """Back to the game's normal icons. Icons the app picked on its own
        from a mod's loose pictures are turned down too (remembered, so they
        don't come back); "Use for..." picks them again."""
        code = ui_setup.code_for_character(item_name)
        if not code:
            return {"success": True}
        auto, _needs = self._auto_icons()
        ov = ui_setup.load_overrides(self.mod_root)
        for k in self._override_kinds(kinds):
            for i, item in enumerate(ui_setup.slot_items(k, code)):
                if colour is not None and i != colour:
                    continue
                ov["textures"].pop(item, None)
                if item in auto and item not in ov["declined"]:
                    ov["declined"].append(item)
        ui_setup.save_overrides(self.mod_root, ov)
        return {"success": True}

    def set_item_name(self, item_name, kind, text, mark_reviewed=True):
        """The name the menus should show for a character/course. Only the wish
        is stored (by name); the text entry it belongs to is found in the game's
        text file when it's built (automatically, on commit)."""
        text = (text or "").strip()
        if not text:
            return {"success": False, "error": "Type a name first."}
        if len(text) > 40:
            return {"success": False, "error": "That's too long for the menus - keep it under 40 characters."}
        ov = ui_setup.load_overrides(self.mod_root)
        ov["strings"] = {i: o for i, o in ov["strings"].items() if not (o.get("who") == item_name and o.get("kind") == kind)}
        ov["names"][f"{kind}|{item_name}"] = {"text": text}   # typed by the user: no "auto" flag, never touched by a guess
        ov["declined_names"] = [n for n in ov["declined_names"] if n != f"{kind}|{item_name}"]
        ui_setup.save_overrides(self.mod_root, ov)
        if kind == "characters" and mark_reviewed:
            self._mark_signature("names", item_name)   # typing a name confirms the Name task (not Icons)
        elif kind == "courses" and mark_reviewed:
            self._mark_course("course_names", item_name)
        elif kind in ui_setup.PART_KINDS and mark_reviewed:
            self._mark_part("part_names", item_name)
        return {"success": True}

    def clear_item_name(self, item_name, kind, mark_reviewed=True):
        ov = ui_setup.load_overrides(self.mod_root)
        gone = ov["names"].pop(f"{kind}|{item_name}", None)
        if gone and gone.get("auto") and f"{kind}|{item_name}" not in ov["declined_names"]:
            ov["declined_names"].append(f"{kind}|{item_name}")   # the user turned a guess down: don't guess it again
        ov["strings"] = {i: o for i, o in ov["strings"].items() if not (o.get("who") == item_name and o.get("kind") == kind)}
        ui_setup.save_overrides(self.mod_root, ov)
        if kind == "characters" and mark_reviewed:
            self._mark_signature("names", item_name)   # choosing "back to normal" confirms the Name task
        elif kind == "courses" and mark_reviewed:
            self._mark_course("course_names", item_name)
        elif kind in ui_setup.PART_KINDS and mark_reviewed:
            self._mark_part("part_names", item_name)
        return {"success": True}

    def open_ui_setup_folder(self):
        folder = self.mod_root / "ui-icons" / "romfs" / "UI"
        folder.mkdir(parents=True, exist_ok=True)
        return self.reveal_path(str(folder))


def default_window_size():
    """1280x720, but clamped down (with a little margin for taskbars/title
    bars) on screens too small to fit that - never below the window's own
    min_size (910x800) though, since requesting smaller than that would
    just conflict with it."""
    target_w, target_h = 1280, 720
    try:
        screen = webview.screens[0]
        target_w = min(target_w, screen.width - 40)
        target_h = min(target_h, screen.height - 80)
    except (IndexError, AttributeError):
        pass
    target_w = max(target_w, 910)
    target_h = max(target_h, 800)
    return target_w, target_h


def report_startup_failure(log_path):
    """Last resort for a packaged build: there is no console to show the traceback in, so say
    where it was written."""
    import traceback
    traceback.print_exc()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "The Mod Manager hit an error and has to close.\n\n"
            f"Details were saved to:\n{log_path}\n\n"
            "Attach that file when you report the problem.",
            "Mod Manager", 0x10)


def main():
    api = Api(load_master_dir_pointer() or default_master_dir())
    window_w, window_h = default_window_size()
    window = webview.create_window(
        "Mario Kart 8 Mod Manager",
        str(SCRIPT_DIR / "ui" / "index.html"),
        js_api=api,
        width=window_w,
        height=window_h,
        min_size=(910, 800),
    )
    api._window = window
    # debug=True enables WebView2's DevTools bridge, which has a known bug
    # where it recursively enumerates window.native's accessibility object
    # tree ("maximum recursion depth exceeded" spam in the console) badly
    # enough to hang the whole window. Not worth it just for Inspect Element,
    # so it stays off unless explicitly requested via MK8DX_DEBUG=1.
    webview.start(debug=os.environ.get("MK8DX_DEBUG") == "1")


if __name__ == "__main__":
    if LOG_PATH:
        print(f"Mod Manager {APP_VERSION}, Python {sys.version.split()[0]}")
    try:
        main()
    except Exception:
        if LOG_PATH is None:
            raise
        report_startup_failure(LOG_PATH)
        sys.exit(1)
