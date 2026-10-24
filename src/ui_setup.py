"""Engine for menu icons & text - built automatically as part of a commit (see mod_manager.Api.merge()),
with the review/language-pick UI on the Commit page (src/ui/js/flow.js).

Mods that change a character's select-screen icon or a course's name ship their
own complete copy of a shared archive (common.sarc / menu.sarc / message.sarc);
Merge & Stage can't safely merge those, because copying one mod's file over
another's would wipe out the other's change. What CAN be done is to work out,
exactly, what each mod's copy changes - and this module does that, then builds
the combined file and checks it:

* Every mod's copy is "the game's file, plus that mod's changes" (verified
  against real downloads), so with several copies to compare the game's own
  value is simply the one most of them agree on, and a mod's deliberate change
  is whatever ONLY that mod has. (Copies built on a different game version or
  region share a handful of non-vanilla values between themselves - those are
  never unique to one mod, so they're correctly ignored as noise.)
* The comparison happens at the smallest useful unit: an individual TEXTURE
  inside the shared character-icon package (an archive entry like
  cm_L_CharaIcon_00.szs holds EVERY character's icon), or an individual
  labelled STRING inside a message.sarc's MSBT files.
* Building starts from the copy that looks newest and swaps in the other mods'
  textures/strings - a same-length byte copy for textures, a rebuilt text table
  for strings - leaving every other byte of the file alone. See ui_archives.py
  for how each piece is written and tested.
"""

import base64
import collections
import datetime
import json
import safe_io
import os
import re
import shutil
from pathlib import Path

import app_paths
import diag
import bntx_decode
import bntx_encode
import ui_archives as ua
import vehicle_icons

# Texture name -> friendly name, e.g. tc_MapChara_Kinopico^l -> "Toadette".
# Codes are the game's internal character ids; anything not listed is shown
# by its raw code rather than guessed at.
CHARACTER_CODES = {
    "Mario": "Mario", "Luigi": "Luigi", "Peach": "Peach", "Daisy": "Daisy", "Rosetta": "Rosalina",
    "TanukiMario": "Tanooki Mario", "CatPeach": "Cat Peach", "Yoshi": "Yoshi", "Kinopio": "Toad",
    "Nokonoko": "Koopa Troopa", "Heyho": "Shy Guy", "Jugemu": "Lakitu", "Kinopico": "Toadette",
    "BbMario": "Baby Mario", "BbLuigi": "Baby Luigi", "BbPeach": "Baby Peach", "BbDaisy": "Baby Daisy",
    "BbRosetta": "Baby Rosalina", "MetalMario": "Metal Mario", "PGoldPeach": "Pink Gold Peach",
    "GoldMario": "Gold Mario", "Wario": "Wario", "Waluigi": "Waluigi", "DK": "Donkey Kong",
    "Koopa": "Bowser", "HoneKoopa": "Dry Bowser", "KoopaJr": "Bowser Jr.", "Karon": "Dry Bones",
    "KingTeresa": "King Boo", "Larry": "Larry", "Lemmy": "Lemmy", "Wendy": "Wendy", "Ludwig": "Ludwig",
    "Iggy": "Iggy", "Roy": "Roy", "Morton": "Morton", "SplatoonGirl": "Inkling Girl",
    "SplatoonBoy": "Inkling Boy", "Link": "Link", "LinkBotw": "Link (Breath of the Wild)",
    "AnimalBoyA": "Villager (Boy)", "AnimalGirlA": "Villager (Girl)", "Shizue": "Isabelle",
    "Mii": "Mii", "MiiAmiibo": "Mii (amiibo)", "Catherine": "Birdo", "BossPakkun": "Petey Piranha",
    "Hanachan": "Wiggler", "Kameck": "Kamek", "DiddyKong": "Diddy Kong", "FK": "Funky Kong",
    "Pauline": "Pauline", "Kinopeach": "Peachette",
}
_TEXTURE_NAME_RE = re.compile(r"^tc_(MapChara|edChara|Chara)_([A-Za-z]+?)(\d\d)?\^l$")

# The archives the guide handles, and where the finished file goes under the
# app's always-merged ui-icons/romfs/ folder.
TEXTURE_ARCHIVES = {
    "common": {"file": "common.sarc", "dest_dir": "UI/cmn", "label": "common.sarc"},
    "menu": {"file": "menu.sarc", "dest_dir": "UI/cmn", "label": "menu.sarc"},
}
# A message.sarc is one per language; the game loads the one matching the
# console's language.
LOCALES = {
    "USen": "English (United States)", "EUen": "English (Europe / UK)", "USes": "Spanish (Latin America)",
    "EUes": "Spanish (Europe)", "USfr": "French (Canada)", "EUfr": "French (Europe)",
    "EUde": "German", "EUit": "Italian", "EUnl": "Dutch", "EUpt": "Portuguese", "EUru": "Russian",
    "JPja": "Japanese", "KRko": "Korean", "CNzh": "Chinese (Simplified)", "TWzh": "Chinese (Traditional)",
}
BACKUPS_DIRNAME = "ui-icons-backups"


def describe_texture(name: str) -> dict:
    """{name, character, kind} for a character-icon texture name (character is
    None for anything that isn't one)."""
    m = _TEXTURE_NAME_RE.match(name)
    if not m:
        key = name[len(vehicle_icons.PREFIX):-len(vehicle_icons.SUFFIX)] if (
            name.startswith(vehicle_icons.PREFIX) and name.endswith(vehicle_icons.SUFFIX)) else None
        part = vehicle_icons.key_names().get(key) if key else None
        if part:   # a vehicle part's picture in the parts menu
            return {"name": name, "character": part, "kind": "Part"}
        return {"name": name, "character": None, "kind": None}
    kind, code, variant = m.groups()
    character = CHARACTER_CODES.get(code)
    if character and variant is not None:
        character = f"{character} (color {int(variant) + 1})"
    return {"name": name, "character": character or code, "kind": kind}


def archive_dest(master_root: Path, archive_id: str) -> Path:
    """Where the finished file for an archive id lives."""
    base = master_root / "ui-icons" / "romfs"
    if archive_id in TEXTURE_ARCHIVES:
        spec = TEXTURE_ARCHIVES[archive_id]
        return base / spec["dest_dir"] / spec["file"]
    locale = archive_id.split(":", 1)[1]
    return base / "UI" / locale / "message.sarc"


# --- source discovery ------------------------------------------------------

def _child(parent, name: str):
    """Case-insensitive lookup of one child of `parent` (Windows mods ship
    'UI', 'Ui', 'ui' interchangeably)."""
    if parent is None or not parent.is_dir():
        return None
    return next((c for c in parent.iterdir() if c.name.lower() == name.lower()), None)


def find_game_files(folder) -> dict:
    """{archive id: Path} for the game's own menu files inside a folder the user
    extracted from their game (the romfs itself, or a folder holding it):
    UI/cmn/common.sarc, UI/cmn/menu.sarc and UI/<language>/message.sarc."""
    found = {}
    if not folder:
        return found
    folder = Path(folder)
    for root in (folder, _child(folder, "romfs")):
        ui = _child(root, "UI")
        if ui is None:
            continue
        cmn = _child(ui, "cmn")
        for archive_id, spec in TEXTURE_ARCHIVES.items():
            f = _child(cmn, spec["file"])
            if f is not None and f.is_file():
                found.setdefault(archive_id, f)
        for loc_dir in ui.iterdir():
            if loc_dir.is_dir() and loc_dir.name in LOCALES:
                f = _child(loc_dir, "message.sarc")
                if f is not None and f.is_file():
                    found.setdefault(f"message:{loc_dir.name}", f)
    return found


# Some mods put their packed menu files NEXT TO romfs/ instead of inside it, under whatever
# folder name the author liked: "UI/cmn/common.sarc" (a UI folder beside romfs), "icons/common.sarc",
# "Character name change files/message.sarc". They are found by what they ARE, not by folder
# name: a file called common.sarc/menu.sarc that really holds the character-icon entry, and a
# message.sarc under a language folder (USen, ...) - or, with no language folder, one whose
# text is English (checked against the shipped name table), which counts for both English ones.
_EXTRA_CACHE = {}


def _archive_kind(path: Path, want: str):
    """Cached check of a candidate file: for "common"/"menu" whether it really holds that
    archive's character-icon entry; for "message" the language guessed from its text
    (["USen", "EUen"] for English, [] if unknown)."""
    try:
        st = path.stat()
    except OSError:
        return None if want != "message" else []
    key = (str(path), st.st_mtime_ns, st.st_size, want)
    if key in _EXTRA_CACHE:
        return _EXTRA_CACHE[key]
    result = None if want != "message" else []
    try:
        entries = ua.parse_sarc(path.read_bytes())
        if want != "message":
            result = any(ENTRY_ARCHIVE.get(n) == want for n in entries) or None
        elif "Common.msbt" in entries:
            texts = ua.parse_msbt(entries["Common.msbt"])
            table = (name_table().get("courses") or {})
            hits = total = 0
            for name, labels in table.items():
                total += 1
                target = re.sub(r"[^a-z0-9]+", " ", _strip_course_prefix(name).lower()).strip()
                if any(lb in texts and re.sub(r"[^a-z0-9]+", " ", ua.msbt_text(texts[lb]).lower()).strip() == target
                       for lb in labels):
                    hits += 1
            if total and hits / total >= 0.5:
                result = ["USen", "EUen"]
    except (OSError, ua.ArchiveError, KeyError, ValueError):
        pass
    _EXTRA_CACHE[key] = result
    return result


def unit_extra_archives(unit_dir: Path) -> dict:
    """{archive id: Path} for the packed menu files a mod unit ships outside its romfs/
    (see above). Never looks inside a romfs/ (the normal place, handled by
    collect_sources) or into another unit's folder."""
    found = {}
    if not unit_dir.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(unit_dir):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d.lower() != "romfs" and _child(here / d, "romfs") is None)
        for fn in sorted(filenames):
            low, path = fn.lower(), here / fn
            if low in ("common.sarc", "menu.sarc"):
                aid = low[:-5]
                if aid not in found and _archive_kind(path, aid):
                    found[aid] = path
            elif low == "message.sarc":
                locales = [here.name] if here.name in LOCALES else _archive_kind(path, "message")
                for loc in locales:
                    found.setdefault(f"message:{loc}", path)
    return found


def collect_sources(extracted_root: Path, checked_keys, game_files: dict = None) -> dict:
    """{archive id: [ {key, path} ]} - every packed UI archive shipped by a
    checked mod. Archive ids: "common", "menu", "message:<locale>". The user's
    own game files (`game_files`, see find_game_files) join each list as a
    source flagged `vanilla`: they ARE the game's own values, so they replace
    the guess "whatever most mods agree on"."""
    found = collections.defaultdict(list)
    for archive_id, path in (game_files or {}).items():
        found[archive_id].append({"key": "game", "path": path, "vanilla": True})
    for key in sorted(checked_keys):
        category, unit_rel = key.split("/", 1)
        unit_dir = extracted_root / category / Path(*unit_rel.split("/"))
        mine = {}  # archive id -> file, for this one mod (its own romfs/UI first)
        ui = _child(unit_dir / "romfs", "UI")
        if ui is not None:
            cmn = _child(ui, "cmn")
            for archive_id, spec in TEXTURE_ARCHIVES.items():
                f = _child(cmn, spec["file"])
                if f is not None and f.is_file():
                    mine[archive_id] = f
            for loc_dir in ui.iterdir():
                if loc_dir.is_dir() and loc_dir.name in LOCALES:
                    f = _child(loc_dir, "message.sarc")
                    if f is not None and f.is_file():
                        mine[f"message:{loc_dir.name}"] = f
        for archive_id, f in unit_extra_archives(unit_dir).items():
            mine.setdefault(archive_id, f)   # the ones beside romfs/ only fill what romfs/UI lacks
        for archive_id, f in mine.items():
            found[archive_id].append({"key": key, "path": f})
    return dict(found)


def mod_label(key: str) -> str:
    """'characters/Toadette/Pomni from TADC/Pomni - final' -> 'Pomni from TADC'
    (the mod's own folder, which is what the user recognizes)."""
    parts = key.split("/")
    return parts[2] if len(parts) > 2 else parts[-1]


def filed_under(key: str) -> str:
    parts = key.split("/")
    return parts[1] if len(parts) > 1 else ""


# --- analysis --------------------------------------------------------------

class Cache:
    """Persistent caches so the (pure-Python, therefore slow) Yaz0
    decompression of an archive entry is only ever paid once, however many mods
    ship an identical copy of it or how often the guide is reopened:
    {entry md5 -> texture summaries} and {pixel md5 -> preview PNG (base64)}."""

    VERSION = 2   # raise it when how an entry is read or turned into a picture changes: the file then drops what it can't vouch for

    def __init__(self, path: Path):
        self.path = path
        self.summaries, self.previews = {}, {}
        self.failed = set()   # (entries that couldn't be read or drawn this run: tried once, never saved - see textures/preview)
        self.dirty = False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.summaries, self.previews = data.get("summaries", {}), data.get("previews", {})
            if data.get("version") != self.VERSION:
                # An older file may hold a failure that was caused by the day (a broken library, an older bug) as if it were an
                # answer: an entry with no textures, a picture that is "". Those are looked at again; the rest is kept.
                self.summaries = {k: v for k, v in self.summaries.items() if v}
                self.previews = {k: v for k, v in self.previews.items() if v}
                self.dirty = True
        except (OSError, ValueError):
            pass

    def textures(self, entry_blob: bytes) -> list:
        key = ua.md5(entry_blob)
        if key in self.failed:
            return []
        if key not in self.summaries:
            try:
                tex = ua.entry_textures(entry_blob)
            except ua.ArchiveError as e:
                # Not saved: a fix to the app (or to the file) must get another go at it.
                self.failed.add(key)
                diag.log_once(("cache-entry", key), "warn", f"an archive entry ({key}) couldn't be read: {type(e).__name__}: {e}")
                return []
            self.summaries[key] = [
                {"name": t["name"], "md5": ua.md5(t["data"]), "w": t["width"], "h": t["height"], "fmt": t["format"]}
                for t in tex
            ]
            self.dirty = True
        return self.summaries[key]

    def preview(self, pixel_md5: str, make):
        """A data-URL PNG for a texture, generated by make() on first use."""
        if pixel_md5 in self.failed:
            return None
        if pixel_md5 not in self.previews:
            png = make()
            if not png:   # (a picture that couldn't be made is tried once per run, not remembered: the reason may be gone next time)
                self.failed.add(pixel_md5)
                return None
            self.previews[pixel_md5] = base64.b64encode(png).decode("ascii")
            self.dirty = True
        b64 = self.previews[pixel_md5]
        return f"data:image/png;base64,{b64}" if b64 else None

    def save(self):
        if self.dirty:
            try:   # (in one step: two caches saving at once, or a crash, must not leave half a file that reads as empty)
                safe_io.write_text_atomic(self.path, json.dumps({"version": self.VERSION, "summaries": self.summaries, "previews": self.previews}))
                self.dirty = False
            except OSError:
                pass


def _group_variants(sources) -> list:
    """Groups byte-identical files (two downloads of the same mod, or a mod
    re-uploaded) into one variant, so a change shared by them isn't mistaken
    for shared 'base' noise. [{md5, path, keys, blob}]"""
    variants = {}
    for s in sources:
        blob = s["path"].read_bytes()
        digest = ua.md5(blob)
        v = variants.setdefault(digest, {"md5": digest, "path": s["path"], "keys": [], "blob": blob, "vanilla": False})
        v["keys"].append(s["key"])
        if s.get("vanilla"):
            v["vanilla"] = True
            v["path"] = s["path"]  # show/build from the user's own file, not a mod's identical copy
    return list(variants.values())


def _mode(counter: collections.Counter):
    return counter.most_common(1)[0][0]


def _variant_summary(v, entries, changes, **extra):
    mods = [k for k in v["keys"] if k != "game"]
    return {
        "id": v["md5"],  # stable across re-analysis, unlike the variant's position
        "keys": mods,
        "vanilla": bool(v.get("vanilla")),
        "labels": sorted({mod_label(k) for k in mods}) or ["Your game's own files"],
        "filed_under": sorted({filed_under(k) for k in mods}),
        "path": str(v["path"]),
        "entries": entries,
        "changes": changes,
        **extra,
    }


def analyze_textures(sources, cache: Cache) -> dict:
    """Per-variant deliberate texture changes for common/menu.sarc.

    {variants: [...], base: index, confidence: "ok"|"few"|"single"}. Each
    variant lists its `changes`: [{entry, name, md5, width, height, format,
    character, kind}] - only what is unique to that variant."""
    variants = _group_variants(sources)
    van = next((i for i, v in enumerate(variants) if v["vanilla"]), None)  # the user's own game file, if given
    entry_maps = []
    for v in variants:
        entry_maps.append(ua.parse_sarc(v["blob"]))
    if len(variants) == 1:
        return {"variants": [_variant_summary(variants[0], len(entry_maps[0]), [], layout_diffs=0)],
                "base": 0, "confidence": "single"}

    names = set().union(*(m.keys() for m in entry_maps))
    entry_hash = {n: {i: ua.md5(m[n]) for i, m in enumerate(entry_maps) if n in m} for n in names}
    found = [{} for _ in variants]  # variant index -> {(entry, texture): summary}
    layout_diffs = [0] * len(variants)

    for entry, hashes in entry_hash.items():
        if len(set(hashes.values())) == 1:
            continue  # every copy agrees - the game's own value, nothing to look at
        tex_by_variant = {i: cache.textures(entry_maps[i][entry]) for i in hashes}
        if not any(tex_by_variant.values()):
            # A layout-only entry (no icons inside) that differs is a game
            # version / base difference, not something a user merges by hand.
            mode_hash = hashes[van] if van in hashes else _mode(collections.Counter(hashes.values()))
            for i, h in hashes.items():
                if h != mode_hash:
                    layout_diffs[i] += 1
            continue
        tex_names = set().union(*(set(t["name"] for t in ts) for ts in tex_by_variant.values()))
        for tn in tex_names:
            per = {}
            for i, ts in tex_by_variant.items():
                t = next((t for t in ts if t["name"] == tn), None)
                if t is not None:
                    per[i] = t
            counts = collections.Counter(t["md5"] for t in per.values())
            if len(counts) == 1:
                continue
            mode_md5 = per[van]["md5"] if van in per else _mode(counts)
            character = describe_texture(tn)["character"] or ""
            for i, t in per.items():
                # Unique to this copy = its own change. A value SHARED with other
                # copies is only a change too when it's about what this mod is for
                # (two uploads/versions of the same mod share their icon); shared
                # anything else is a different base version's artwork.
                deliberate = counts[t["md5"]] == 1 or _related(character, variants[i]["keys"])
                if t["md5"] != mode_md5 and (deliberate or len(variants) == 2):
                    found[i][(entry, tn)] = t

    result = {"variants": [], "confidence": "ok" if van is not None else ("few" if len(variants) == 2 else "ok")}
    for i, v in enumerate(variants):
        changes = []
        for (entry, tn), t in sorted(found[i].items()):
            d = describe_texture(tn)
            changes.append({"entry": entry, "name": tn, "md5": t["md5"], "width": t["w"], "height": t["h"],
                            "format": t["fmt"], "character": d["character"], "kind": d["kind"]})
        changes, other = _split_changes(changes, v["keys"], lambda c: c["character"] or "")
        result["variants"].append(_variant_summary(v, len(entry_maps[i]), changes,
                                                   layout_diffs=layout_diffs[i], other=len(other)))
    result["base"] = van if van is not None else choose_base(result["variants"])

    # Which changes can actually be swapped into the chosen base? A texture has
    # to exist there with the same format and size (then it's a same-length
    # byte copy); a mod built for another game version, or one that used a
    # different-sized picture, can't be merged automatically.
    base_entries = entry_maps[result["base"]]
    base_tex = {}
    for i, v in enumerate(result["variants"]):
        for c in v["changes"]:
            c["mergeable"], c["reason"] = True, None
            if i == result["base"]:
                continue
            if c["entry"] not in base_entries:
                c["mergeable"], c["reason"] = False, "this screen isn't in your base file (it was built for a different game version)"
                continue
            if c["entry"] not in base_tex:
                base_tex[c["entry"]] = {t["name"]: t for t in cache.textures(base_entries[c["entry"]])}
            bt = base_tex[c["entry"]].get(c["name"])
            if bt is None:
                c["mergeable"], c["reason"] = False, "this picture isn't in your base file (it was built for a different game version)"
            elif (bt["fmt"], bt["w"], bt["h"]) != (c["format"], c["width"], c["height"]):
                if can_rescale(c["format"], c["width"], c["height"], bt["fmt"], bt["w"], bt["h"]):
                    # a plain picture of the same shape, just another size: it is resized to the game's
                    c["rescale"] = {"from": [c["width"], c["height"]], "to": [bt["w"], bt["h"]]}
                else:
                    c["mergeable"], c["reason"] = False, "its picture is a different shape or format than the game's own, so it can't be swapped in automatically"
    return result


def can_rescale(fmt, w, h, base_fmt, base_w, base_h) -> bool:
    """Only plain RGBA pictures whose proportions match (within 5%) are resized -
    squashing a wide picture into a square one would ruin it."""
    return (fmt == base_fmt and (fmt >> 8) == 0x0B and min(w, h, base_w, base_h) > 0
            and abs((w / h) / (base_w / base_h) - 1) <= 0.05)


def rescale_texture(src: dict, base: dict) -> bytes:
    """The mod's picture (`src`, a parsed texture) as the exact bytes of the
    game's texture `base`: decoded, resized to the game's size with the
    same alpha-safe filter the user's own pictures get, and laid out for the
    Switch's GPU the way `base` is."""
    from PIL import Image
    raw = bntx_decode._deswizzle(src["width"], src["height"], 1, 4, src["layout"] & 7, src["data"])
    img = Image.frombytes("RGBA", (src["width"], src["height"]), raw)
    w, h = base["width"], base["height"]
    img = img.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    data = bntx_encode._swizzle(w, h, 1, 4, base["layout"] & 7, img.tobytes("raw", "RGBA"))
    if len(data) != len(base["data"]):
        raise ua.PatchError("the resized picture doesn't fit the game's icon")
    return data


def analyze_strings(sources) -> dict:
    """Per-variant deliberate text changes for a message.sarc.

    Each variant's `changes`: [{file, label, old, new}]; `ignored` counts
    differences shared by several mods (a different regional/version base),
    which are not deliberate edits."""
    variants = _group_variants(sources)
    van = next((i for i, v in enumerate(variants) if v["vanilla"]), None)  # the user's own game file, if given
    parsed = []
    for v in variants:
        strings = {}
        for fname, blob in ua.parse_sarc(v["blob"]).items():
            if blob[:8] == b"MsgStdBn":
                for label, raw in ua.parse_msbt(blob).items():
                    strings[(fname, label)] = raw
        parsed.append(strings)
    if len(variants) == 1:
        return {"variants": [_variant_summary(variants[0], len(parsed[0]), [], ignored=0)],
                "base": 0, "confidence": "single"}
    keys = set().union(*(s.keys() for s in parsed))
    counts, mode = {}, {}
    for k in keys:
        c = collections.Counter(s[k] for s in parsed if k in s)
        counts[k], mode[k] = c, (parsed[van][k] if van is not None and k in parsed[van] else _mode(c))
    result = {"variants": [], "confidence": "ok" if van is not None else ("few" if len(variants) == 2 else "ok")}
    for i, v in enumerate(variants):
        changes, ignored = [], 0
        unique_common = 0  # differences unique to this mod in Common.msbt, BEFORE dropping look-alikes
        for k, raw in sorted(parsed[i].items()):
            if raw == mode[k]:
                continue
            old_text, new_text = ua.msbt_text(mode[k]), ua.msbt_text(raw)
            # unique to this copy, or shared but about what this mod is for (see
            # analyze_textures): two versions of one mod share their renames
            is_unique = counts[k][raw] == 1 or len(variants) == 2 or _related(old_text, v["keys"])
            if is_unique and k[0] == "Common.msbt":
                unique_common += 1
            if new_text == old_text:
                ignored += 1  # same words, different hidden formatting - not an edit
            elif is_unique:
                changes.append({"file": k[0], "label": k[1], "old": old_text, "new": new_text})
            else:
                ignored += 1
        # Names (characters, courses, karts) live in Common.msbt, so that is
        # where a mod's renames are - trusted while the mod changes a modest
        # number of them. A change in any other file (menu sentences, promo
        # text) is usually just an older/newer wording from the mod's base
        # game version, so it's only kept when it's about what the mod is for.
        trust_common = unique_common <= SMALL_DIFF_LIMIT
        kept = [c for c in changes if _related(c["old"], v["keys"]) or (c["file"] == "Common.msbt" and trust_common)]
        other = [c for c in changes if c not in kept]
        result["variants"].append(_variant_summary(v, len(parsed[i]), kept, ignored=ignored + len(other), other=len(other)))
    result["base"] = van if van is not None else choose_base(result["variants"])
    # A text entry can only be merged if the base file has that entry too.
    base_strings = parsed[result["base"]]
    for i, v in enumerate(result["variants"]):
        for c in v["changes"]:
            c["mergeable"], c["reason"] = True, None
            if i != result["base"] and (c["file"], c["label"]) not in base_strings:
                c["mergeable"], c["reason"] = False, "this text isn't in your base file (it was built for a different game version)"
    return result


# A mod that changes more than this many things in one archive is almost
# certainly built on a different regional/version base as well (real example:
# a mod whose file carries ~110 European-English course names next to its one
# real edit), so only the changes that are about what the mod IS are trusted.
SMALL_DIFF_LIMIT = 12
_PLATFORM_PREFIXES = ("wii ", "gba ", "ds ", "n64 ", "gcn ", "snes ", "3ds ", "tour ")


def _norm(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    for p in _PLATFORM_PREFIXES:
        if t.startswith(p):
            t = t[len(p):]
    return t


def _related(text: str, keys) -> bool:
    """Whether `text` (a character or course name) is about the item(s) this
    mod is filed under - the app's own knowledge of what the mod is for."""
    t = _norm(text or "")
    if not t:
        return False
    for k in keys:
        f = _norm(filed_under(k))
        if f and (t in f or f in t):
            return True
    return False


def _split_changes(changes, keys, subject_of):
    """(kept, other): for a mod with a small number of changes everything is
    kept; for one with many, only the changes whose subject (`subject_of`,
    e.g. the character a texture is for, or the text being replaced) is what
    the mod is filed under."""
    if len(changes) <= SMALL_DIFF_LIMIT:
        return changes, []
    kept = [c for c in changes if _related(subject_of(c), keys)]
    return kept, [c for c in changes if c not in kept]


def choose_base(variants) -> int:
    """The copy to start the finished file from: the one that looks like it was
    built on the newest game version (most entries - later versions only ever
    add), and among those the one with the fewest changes of its own, so the
    least gets inherited that the user didn't ask for."""
    best, best_score = 0, None
    for i, v in enumerate(variants):
        score = (v["entries"], -len(v["changes"]))
        if best_score is None or score > best_score:
            best, best_score = i, score
    return best


def _conflicts(analysis: dict) -> dict:
    """{item id: [variant indexes]} for items more than one (non-base) mod
    changes - the user has to pick which mod's version wins."""
    owners = collections.defaultdict(list)
    values = collections.defaultdict(set)
    for i, v in enumerate(analysis["variants"]):
        for c in v["changes"]:
            if c.get("mergeable", True):
                owners[item_id(c)].append(i)
                values[item_id(c)].add(c["md5"] if "md5" in c else c["new"])
    # two mods that make the IDENTICAL change (two versions of one mod) don't
    # conflict - there's nothing to choose between
    return {k: idx for k, idx in owners.items() if len(idx) > 1 and len(values[k]) > 1}


def item_id(change: dict) -> str:
    """A stable id for one change: 'entry|texture' or 'file|label'."""
    if "entry" in change:
        return f"{change['entry']}|{change['name']}"
    return f"{change['file']}|{change['label']}"


def analyze_all(extracted_root: Path, checked_keys, cache_path: Path, game_files: dict = None) -> dict:
    """The whole plan: {archive id: analysis}, each with a `conflicts` map."""
    cache = Cache(cache_path)
    sources = collect_sources(extracted_root, checked_keys, game_files)
    plan = {}
    for archive_id, srcs in sources.items():
        analysis = analyze_textures(srcs, cache) if archive_id in TEXTURE_ARCHIVES else analyze_strings(srcs)
        analysis["conflicts"] = _conflicts(analysis)
        plan[archive_id] = analysis
    cache.save()
    return plan


def add_previews(analysis: dict, cache_path: Path):
    """Attaches a preview picture to every icon change (a small PNG of the
    exact icon, so the user can see what each mod is bringing)."""
    cache = Cache(cache_path)
    for v in analysis["variants"]:
        entries_cache = {}
        if v.get("is_override"):
            continue
        for c in v["changes"]:
            if "entry" not in c:
                continue

            def make(c=c, v=v):
                if c["entry"] not in entries_cache:
                    entries_cache[c["entry"]] = ua.entry_texture_map(ua.parse_sarc(Path(v["path"]).read_bytes())[c["entry"]])
                t = entries_cache[c["entry"]].get(c["name"])
                return ua.texture_png(t) if t else None

            c["preview"] = cache.preview(c["md5"], make)
    cache.save()


# --- building --------------------------------------------------------------

def _backup(master_root: Path, path: Path):
    """Keeps whatever is at `path` (a file the user made by hand, or an older
    build) before it's replaced."""
    if not path.is_file():
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = master_root / BACKUPS_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stamp}-{path.parent.name}-{path.name}"
    shutil.copy2(path, dest)
    return dest


def _winners(analysis: dict, choices: dict) -> dict:
    """{item id: variant index} for every change that should be in the result:
    the base's own are already there; for a conflict the user's pick wins
    (default: the first mod, alphabetically by folder)."""
    base = analysis["base"]
    win = {}
    for i, v in enumerate(analysis["variants"]):
        for c in v["changes"]:
            if c.get("mergeable", True):
                win.setdefault(item_id(c), []).append(i)
    out = {}
    for item, idxs in win.items():
        # `choices` maps an item to the chosen variant's id (see _variant_summary)
        pick = next((i for i in idxs if analysis["variants"][i]["id"] == choices.get(item)), None)
        mine = next((i for i in idxs if analysis["variants"][i].get("is_override")), None)
        out[item] = mine if mine is not None else (pick if pick is not None else (base if base in idxs else idxs[0]))
    return out


def build_archive(master_root: Path, archive_id: str, analysis: dict, choices: dict = None) -> dict:
    """Builds the finished file for one archive and writes it under
    ui-icons/romfs/ (keeping a backup of anything it replaces). Returns a
    report: {written, applied: [...], skipped: [{..., reason}], backup}."""
    choices = choices or {}
    variants = analysis["variants"]
    base = variants[analysis["base"]]
    base_bytes = Path(base["path"]).read_bytes()
    winners = _winners(analysis, choices)
    report = {"archive": archive_id, "applied": [], "skipped": [], "base": base["labels"]}
    replacements = {}

    if archive_id in TEXTURE_ARCHIVES:
        base_entries = ua.parse_sarc(base_bytes)
        wanted = collections.defaultdict(dict)  # entry -> {texture: (variant idx, change)}
        for item, idx in winners.items():
            if idx == analysis["base"]:
                continue
            change = next(c for c in variants[idx]["changes"] if item_id(c) == item)
            wanted[change["entry"]][change["name"]] = (idx, change)
        source_cache = {}
        for entry, textures in wanted.items():
            if entry not in base_entries:
                for name, (idx, c) in textures.items():
                    report["skipped"].append(_skip(variants[idx], c, "this screen doesn't exist in your base file (older game version)"))
                continue
            base_tex = ua.entry_texture_map(base_entries[entry])
            pixels, want, ok = {}, {}, {}
            for name, (idx, c) in textures.items():
                if variants[idx].get("is_override"):
                    src_tex = variants[idx]["inline"].get(item_id(c))
                else:
                    if idx not in source_cache:
                        source_cache[idx] = ua.parse_sarc(Path(variants[idx]["path"]).read_bytes())
                    src_tex = ua.entry_texture_map(source_cache[idx][entry]).get(name)
                bt = base_tex.get(name)
                if src_tex is None:
                    report["skipped"].append(_skip(variants[idx], c, "texture not found in the mod's file"))
                elif bt is None:
                    report["skipped"].append(_skip(variants[idx], c, "not in your base file (it was built for an older game version)"))
                elif (bt["format"], bt["width"], bt["height"]) != (src_tex["format"], src_tex["width"], src_tex["height"]):
                    if not can_rescale(src_tex["format"], src_tex["width"], src_tex["height"], bt["format"], bt["width"], bt["height"]):
                        report["skipped"].append(_skip(variants[idx], c, "different shape/format than the game's own icon"))
                        continue
                    try:
                        data = rescale_texture(src_tex, bt)
                    except (ua.ArchiveError, ValueError) as e:
                        report["skipped"].append(_skip(variants[idx], c, f"couldn't be resized to the game's icon size: {e}"))
                        continue
                    if bt["data"] == data:
                        report["applied"].append(_done(variants[idx], c, already=True))
                    else:
                        pixels[name] = data
                        want[name] = (bt["format"], bt["width"], bt["height"])
                        ok[name] = (idx, c)
                elif bt["data"] == src_tex["data"]:
                    report["applied"].append(_done(variants[idx], c, already=True))
                else:
                    pixels[name] = src_tex["data"]
                    want[name] = (src_tex["format"], src_tex["width"], src_tex["height"])
                    ok[name] = (idx, c)
            if pixels:
                replacements[entry] = ua.patch_icon_entry(base_entries[entry], pixels, want)
                report["applied"].extend(_done(variants[idx], c) for idx, c in ok.values())
        out_bytes = ua.rebuild_sarc(base_bytes, replacements) if replacements else base_bytes
    else:
        base_files = ua.parse_sarc(base_bytes)
        wanted = collections.defaultdict(dict)  # msbt file -> {label: (idx, change, raw)}
        source_cache = {}
        for item, idx in winners.items():
            if idx == analysis["base"]:
                continue
            change = next(c for c in variants[idx]["changes"] if item_id(c) == item)
            if variants[idx].get("is_override"):
                raw = variants[idx]["inline"].get(item)
            else:
                if idx not in source_cache:
                    source_cache[idx] = {}
                    for fname, blob in ua.parse_sarc(Path(variants[idx]["path"]).read_bytes()).items():
                        if blob[:8] == b"MsgStdBn":
                            source_cache[idx][fname] = ua.parse_msbt(blob)
                raw = source_cache[idx].get(change["file"], {}).get(change["label"])
            if raw is None:
                report["skipped"].append(_skip(variants[idx], change, "text not found in the mod's file"))
                continue
            wanted[change["file"]][change["label"]] = (idx, change, raw)
        for fname, labels in wanted.items():
            if fname not in base_files:
                for label, (idx, c, raw) in labels.items():
                    report["skipped"].append(_skip(variants[idx], c, f"{fname} isn't in your base file"))
                continue
            have = ua.parse_msbt(base_files[fname])
            good = {}
            for label, (idx, c, raw) in labels.items():
                if label not in have:
                    report["skipped"].append(_skip(variants[idx], c, "not in your base file (it was built for an older game version)"))
                elif have[label] == raw:
                    report["applied"].append(_done(variants[idx], c, already=True))
                else:
                    good[label] = raw
                    report["applied"].append(_done(variants[idx], c))
            if good:
                replacements[fname] = ua.patch_msbt(base_files[fname], good)
        out_bytes = ua.rebuild_sarc(base_bytes, replacements) if replacements else base_bytes

    dest = archive_dest(master_root, archive_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.read_bytes() == out_bytes:
        report["backup"] = None
    else:
        report["backup"] = str(_backup(master_root, dest)) if dest.is_file() else None
        dest.write_bytes(out_bytes)
    report["written"] = str(dest)
    report["size"] = len(out_bytes)
    return report


def dropped_changes(analysis: dict) -> list:
    """What the selected mods change in this archive that the build can't use, as [{"mods", "what", "reason"}] - so "no icons were built"
    can say why: a picture built for another game version or of another shape, a screen the user's own game file doesn't have, and the
    changes of a mod with many (set aside as unrelated to what the mod is filed under, see _split_changes)."""
    out = []
    for i, v in enumerate(analysis["variants"]):
        if i == analysis["base"]:
            continue
        for c in v["changes"]:
            if not c.get("mergeable", True):
                out.append({"mods": v["labels"], "what": _what(c), "reason": c.get("reason") or "can't be swapped in automatically"})
        if v.get("other"):
            out.append({"mods": v["labels"], "what": f"{v['other']} other entr{'y' if v['other'] == 1 else 'ies'}",
                        "reason": "set aside as unrelated to what the mod is filed under"})
    return out


def _skip(variant, change, reason):
    return {"mods": variant["labels"], "item": item_id(change), "what": _what(change), "reason": reason}


def _done(variant, change, already=False):
    return {"mods": variant["labels"], "item": item_id(change), "what": _what(change), "already": already}


def _what(change) -> str:
    if "entry" in change:
        return change.get("character") or change["name"]
    return change["new"] or change["label"]


# --- verification ------------------------------------------------------------

def verify_archive(master_root: Path, archive_id: str, analysis: dict, choices: dict = None) -> dict:
    """Checks the file at the archive's destination against the plan and
    reports each expected change: "ok" (the file has exactly the mod's version),
    "missing" (still the game's own value) or "other" (something else there).
    Also checks the file is structurally sound. Works on a file the app built
    or one made by hand."""
    dest = archive_dest(master_root, archive_id)
    res = {"archive": archive_id, "path": str(dest), "exists": dest.is_file(), "items": [], "problems": []}
    if not res["exists"]:
        return res
    data = dest.read_bytes()
    try:
        outer = ua.parse_sarc(data)
    except ua.ArchiveError as e:
        res["problems"].append(f"Couldn't read this file as an archive: {e}")
        return res
    res["size"] = len(data)
    winners = _winners(analysis, choices or {})
    variants = analysis["variants"]
    if archive_id in TEXTURE_ARCHIVES:
        cache, source_cache = {}, {}
        for item, idx in sorted(winners.items()):
            c = next(c for c in variants[idx]["changes"] if item_id(c) == item)
            if c["entry"] not in cache:
                try:
                    cache[c["entry"]] = {t["name"]: t for t in ua.entry_textures(outer[c["entry"]])} if c["entry"] in outer else None
                except ua.ArchiveError as e:
                    cache[c["entry"]] = None
                    res["problems"].append(f"{c['entry']} inside your file couldn't be read: {e}")
            have_tex = (cache[c["entry"]] or {}).get(c["name"])
            have = ua.md5(have_tex["data"]) if have_tex else None
            want_md5 = c["md5"]
            if c.get("rescale") and have_tex is not None:
                # a resized icon: what should be there is the mod's picture resized to the game's size
                try:
                    if idx not in source_cache:
                        source_cache[idx] = ua.parse_sarc(Path(variants[idx]["path"]).read_bytes())
                    src_tex = ua.entry_texture_map(source_cache[idx][c["entry"]])[c["name"]]
                    want_md5 = ua.md5(rescale_texture(src_tex, have_tex))
                except (KeyError, OSError, ua.ArchiveError, ValueError):
                    pass
            state = "ok" if have == want_md5 else ("missing" if have is None else "other")
            res["items"].append({"item": item, "mods": variants[idx]["labels"], "what": _what(c), "state": state})
    else:
        texts = {}
        for fname, blob in outer.items():
            if blob[:8] == b"MsgStdBn":
                try:
                    texts[fname] = ua.parse_msbt(blob)
                except ua.ArchiveError as e:
                    res["problems"].append(f"{fname} inside your file couldn't be read: {e}")
        for item, idx in sorted(winners.items()):
            c = next(c for c in variants[idx]["changes"] if item_id(c) == item)
            have = texts.get(c["file"], {}).get(c["label"])
            want_text = c["new"]
            state = "ok" if have is not None and ua.msbt_text(have) == want_text else (
                "missing" if have is None or ua.msbt_text(have) == c["old"] else "other")
            res["items"].append({"item": item, "mods": variants[idx]["labels"], "what": _what(c), "state": state})
    res["ok"] = sum(1 for i in res["items"] if i["state"] == "ok")
    res["total"] = len(res["items"])
    return res


# --- the user's own icons and names --------------------------------------------
# A mod that changes nothing in the menus (most of them) leaves a character with
# the game's own icon and name. These overrides let the user supply their own:
# one picture used for the select / map / results icons, and a name. They are
# stored next to the other user data (ui-overrides.json + ui-overrides/*.png) and
# enter the plan as one more "mod" called "Your changes" whose picks always win,
# so building, checking and the review screen treat them like any other change.

OVERRIDES_FILENAME = "ui-overrides.json"
OVERRIDES_DIRNAME = "ui-overrides"

# A character's icons: (texture kind, archive id, archive entry, what it's called).
CHARACTER_SLOTS = [
    ("Chara", "menu", "mn_L_CharaIcon_00.szs", "Character-select icon"),
    ("MapChara", "common", "cm_L_CharaIcon_00.szs", "Map icon"),
    ("edChara", "common", "cm_L_CharaIcon_00.szs", "Results-screen icon"),
]
ENTRY_ARCHIVE = {"cm_L_CharaIcon_00.szs": "common", "mn_L_CharaIcon_00.szs": "menu", vehicle_icons.SARC_ENTRY: "menu"}
LOOSE_ENTRY = "loose"   # the "entry" of a part picture that is a loose file rather than a texture in an archive: "loose|K_Std"
# Numeric MSBT labels in Common.msbt: characters' names sit in 1000-1099, each
# course's name twice - short and with the cup line: 1400-1499 / 1500-1599 for the
# original courses, 11700-11799 / 11800-11899 for the retro and Booster Course Pass ones.
NAME_LABEL_RANGES = {"characters": [(1000, 1100)], "courses": [(1400, 1600), (11700, 11900)],
                     "vehicles": [(1100, 1300)], "wheels": [(1100, 1300)], "gliders": [(1100, 1300)]}   # (the parts: bodies 1101-1186, tires 1201-1222, gliders 1251-1265)
PART_KINDS = ("vehicles", "wheels", "gliders")   # the name kinds (and categories) of vehicle parts
_COURSE_PREFIXES = ("Wii ", "GBA ", "DS ", "N64 ", "GCN ", "SNES ", "3DS ", "Tour ")
_ICON_SOURCE_SIZE = 256


def code_for_character(name: str):
    """The game's internal code for a character's display name, or None.
    (A folder name loses the dot of "Bowser Jr." - trailing dots don't matter.)"""
    low = (name or "").strip().lower().rstrip(".")
    for code, nm in CHARACTER_CODES.items():
        if nm.lower().rstrip(".") == low:
            return code
    return None


# Characters whose icons come in several colours: the game keeps one texture PER
# COLOUR (tc_Chara_Yoshi00^l ... Yoshi08^l) and has no plain "Yoshi" texture at all.
# (Counted from the game's own icon files; every other character has exactly one.)
COLOR_VARIANTS = {"Yoshi": 9, "Heyho": 9, "Catherine": 9, "SplatoonBoy": 3, "SplatoonGirl": 3}
_KIND_ENTRY = {k: e for k, _a, e, _l in CHARACTER_SLOTS}


def item_textures(code: str) -> list:
    """The texture-name stems a character's icons use: ["Mario"], or nine for Yoshi."""
    n = COLOR_VARIANTS.get(code)
    return [f"{code}{i:02d}" for i in range(n)] if n else [code]


def slot_items(kind: str, code: str) -> list:
    """Every plan item (archive entry|texture) that is this character's icon of
    this kind - one per colour for a colour-variant character."""
    return [f"{_KIND_ENTRY[kind]}|tc_{kind}_{stem}^l" for stem in item_textures(code)]


def slot_item(kind: str, code: str) -> str:
    return slot_items(kind, code)[0]


def part_item(section: str, internal: str):
    """The picture item of a vehicle part: "mn_L_KartParts_00.szs|tc_KP_K_Ufo^l" for a part whose picture is a texture in
    menu.sarc, "loose|K_Std" for one that is a set of loose files (see vehicle_icons.py); None when the id isn't known."""
    key = vehicle_icons.texture_key(section, internal)
    if key is None:
        return None
    if key in vehicle_icons.LOOSE_DEFAULTS:
        return f"{LOOSE_ENTRY}|{key}"
    return f"{vehicle_icons.SARC_ENTRY}|{vehicle_icons.PREFIX}{key}{vehicle_icons.SUFFIX}"


def is_loose_item(item: str) -> bool:
    return item.startswith(LOOSE_ENTRY + "|")


def classify_code(code: str):
    """(game character code, colour index or None) for a texture-name stem the
    game really has ("SplatoonGirl02" -> ("SplatoonGirl", "02")), or None for a
    name a mod made up ("MarioSunshine")."""
    if code in CHARACTER_CODES:
        return code, None
    m = re.match(r"^(.+?)(\d\d)$", code)
    if m and m.group(1) in COLOR_VARIANTS and int(m.group(2)) < COLOR_VARIANTS[m.group(1)]:
        return m.group(1), m.group(2)
    return None


def load_overrides(master_root: Path) -> dict:
    try:
        data = json.loads((master_root / OVERRIDES_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("textures", {})
    data.setdefault("strings", {})  # label-keyed names from older versions: "Common.msbt|<label>"
    data.setdefault("names", {})    # what the user asked for, by name: "<kind>|<item>" -> {"text"}; resolved to labels at build time
    data.setdefault("declined", [])  # icon slots the user turned automatic pictures down for
    data.setdefault("declined_names", [])  # "<kind>|<item>" the user cleared a guessed name of - never guessed again
    return data


def save_overrides(master_root: Path, data: dict):
    safe_io.write_json_atomic((master_root / OVERRIDES_FILENAME), data)
def overrides_signature(master_root: Path) -> str:
    """Changes whenever the overrides (or a picture they use) change."""
    ov = load_overrides(master_root)
    parts = [json.dumps(ov, sort_keys=True)]
    for o in ov["textures"].values():
        try:
            parts.append(str((master_root / o["png"]).stat().st_mtime_ns))
        except OSError:
            parts.append("missing")
    return "|".join(parts)


_PART_PICTURE_SIDE = 400   # a part picture is 200x128 in the game; kept at twice that, in its own shape


def store_icon_picture(master_root: Path, png_bytes: bytes, square: bool = True) -> str:
    """Saves a picture under ui-overrides/ and returns its path relative to
    the master folder. Anything larger than 256 px is scaled down to a 256x256
    square (a crop from a screenshot); a small picture - a mod's own 64x64 map
    icon - is kept exactly as it is, since blowing it up and shrinking it back
    would only blur it."""
    from PIL import Image
    import hashlib
    import io
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if not square:   # a part picture keeps its own shape, only shrunk if it is large
        if max(img.size) > _PART_PICTURE_SIDE:
            k = _PART_PICTURE_SIDE / max(img.size)
            img = img.convert("RGBa").resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS).convert("RGBA")
    elif max(img.size) > _ICON_SOURCE_SIZE:
        img = img.convert("RGBa").resize((_ICON_SOURCE_SIZE, _ICON_SOURCE_SIZE), Image.LANCZOS).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    rel = f"{OVERRIDES_DIRNAME}/{hashlib.sha1(data).hexdigest()[:12]}.png"
    (master_root / OVERRIDES_DIRNAME).mkdir(parents=True, exist_ok=True)
    (master_root / rel).write_bytes(data)
    return rel


def _fit_picture(img, w: int, h: int):
    """`img` as a w x h picture: resized to fill it when it is (nearly) the right shape, else shrunk to fit inside it and
    centred on a transparent background - a part's picture keeps its proportions rather than being squashed."""
    from PIL import Image
    if abs(img.width / img.height - w / h) <= 0.03 * (w / h):
        return img.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    k = min(w / img.width, h / img.height)
    inner = img.convert("RGBa").resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS).convert("RGBA")
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(inner, ((w - inner.width) // 2, (h - inner.height) // 2))
    return out


def _render_icon(png_path: Path, tex: dict, contain: bool = False) -> bytes:
    """The picture as the exact bytes of this texture: resized to its size,
    RGBA8, laid out the way the Switch's GPU reads it (verified to be the exact
    inverse of what the previews decode)."""
    from PIL import Image
    if (tex["format"] >> 8) != 0x0B:
        raise ua.PatchError("that icon isn't a plain RGBA picture")
    w, h = tex["width"], tex["height"]
    img = Image.open(png_path).convert("RGBA")
    if img.size != (w, h):
        img = _fit_picture(img, w, h) if contain else img.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    data = bntx_encode._swizzle(w, h, 1, 4, tex["layout"] & 7, img.tobytes("raw", "RGBA"))
    if len(data) != len(tex["data"]):
        raise ua.PatchError("picture doesn't fit the game's icon size")
    return data


def build_part_pictures(master_root: Path, originals: dict, out_dir: Path, skip=frozenset()) -> dict:
    """Writes the user's own pictures for the vehicle parts whose pictures are loose files (see vehicle_icons.py): for each
    such part, a copy of EVERY variant file the game has (the Standard Kart has one per character outfit), each the game's own
    file with its picture swapped in place - the file keeps its name, size and layout, only the pixels change (verified:
    re-encoding the game's own picture reproduces the file exactly). `originals` is {file name: Path} of the game's files
    (game_files.current_vehicle_picts()); `skip` is file names (lower-case) a ticked mod supplies itself - those are left to
    that mod. `out_dir` is only ever written by this: files in it that are no longer wanted are deleted.
    {"written": [...], "left_to_mods": [...], "problems": [...]}"""
    ov = load_overrides(master_root)
    wanted = {i: o for i, o in ov["textures"].items() if is_loose_item(i)}
    written, left, problems = set(), [], []
    if wanted and not originals:
        problems.append("the game's own picture files aren't in your base copy yet - open Settings > Base game files")
    for item, o in sorted(wanted.items()):
        key = item.split("|", 1)[1]
        for fname, src in sorted(originals.items()):
            if vehicle_icons.loose_family(fname) != key:
                continue
            if fname.lower() in skip:
                left.append(fname)
                continue
            try:
                blob = src.read_bytes()
                tex = ua.parse_bntx_textures(blob)[0]
                data = _render_icon(master_root / o["png"], tex, contain=True)
                out = bytearray(blob)
                out[tex["offset"]:tex["offset"] + len(data)] = data
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / fname).write_bytes(bytes(out))
                written.add(fname)
            except (OSError, ua.ArchiveError, ua.PatchError, ValueError, IndexError) as e:
                problems.append(f"{fname}: {e}")
    if out_dir.is_dir():
        for f in out_dir.iterdir():
            if f.is_file() and f.name not in written:
                try:
                    f.unlink()
                except OSError:
                    pass
    return {"written": sorted(written), "left_to_mods": left, "problems": problems}


def _msbt_names(plan: dict, prefer=("USen", "EUen")):
    """(labels -> raw string, source id) of Common.msbt from an English
    message archive in the plan - the one place the numeric name labels can be
    matched to names people know."""
    order = [f"message:{l}" for l in prefer] + [k for k in plan if k.startswith("message:")]
    for aid in order:
        analysis = plan.get(aid)
        if not analysis:
            continue
        base = analysis["variants"][analysis["base"]]
        try:
            files = ua.parse_sarc(Path(base["path"]).read_bytes())
            if "Common.msbt" in files:
                return ua.parse_msbt(files["Common.msbt"]), aid
        except (OSError, ua.ArchiveError):
            continue
    return None, None


_NAME_TABLE = None


# Characters that are a second version of another one and share its name text (the game has one "Link" entry for both Link
# and Link (Breath of the Wild)): {name: the character whose name entry it shares}. Naming either one changes both in-game.
NAME_ALIASES = {"Link (Breath of the Wild)": "Link"}


def name_table() -> dict:
    """name-labels.json (shipped with the app): {"characters": {name: [labels]},
    "courses": {name: [labels]}} - which text entry holds each name. The numbers
    are game facts that never change between mods, so knowing them means a name
    can be handled without opening any of the game's files."""
    global _NAME_TABLE
    if _NAME_TABLE is None:
        try:
            _NAME_TABLE = json.loads((app_paths.RESOURCE_DIR / "name-labels.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _NAME_TABLE = {}
        chars = _NAME_TABLE.get("characters")
        if isinstance(chars, dict):
            for alias, target in NAME_ALIASES.items():
                if target in chars:
                    chars.setdefault(alias, chars[target])
    return _NAME_TABLE


def _strip_course_prefix(name: str) -> str:
    for p in _COURSE_PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def find_name_labels(plan: dict, name: str, kind: str):
    """{"labels": [...], "vanilla": the game's English name} for a character's or
    course's name entry in Common.msbt, or None when it can't be worked out.
    The shipped table answers without any game file; only an item the table
    doesn't know falls back to searching an English message file in the plan
    for the name's text."""
    if kind not in NAME_LABEL_RANGES:
        return None
    labels = (name_table().get(kind) or {}).get(name)
    if labels:
        return {"labels": list(labels), "vanilla": _strip_course_prefix(name) if kind == "courses" else NAME_ALIASES.get(name, name)}
    msbt, _aid = _msbt_names(plan or {})
    if not msbt:
        return None
    target = _strip_course_prefix(name) if kind == "courses" else name
    want = re.sub(r"[^a-z0-9]+", " ", target.lower()).strip()
    found, vanilla = [], None
    for label, raw in msbt.items():
        if not label.isdigit() or not any(lo <= int(label) < hi for lo, hi in NAME_LABEL_RANGES[kind]):
            continue
        text = ua.msbt_text(raw)
        if re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() == want:
            found.append(label)
            vanilla = vanilla or text
    return {"labels": sorted(found, key=int), "vanilla": vanilla} if found else None


_MSG_NAME_CACHE = {}


def message_name(path: Path, labels) -> str:
    """The text a mod's own message.sarc has at a character's name entry (`labels`, see
    name_table) - None when it's missing. Cached by file, so asking on every tick is cheap."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size, tuple(labels))
    if key not in _MSG_NAME_CACHE:
        text = None
        try:
            texts = ua.parse_msbt(ua.parse_sarc(Path(path).read_bytes())["Common.msbt"])
            for label in labels:
                if label in texts:
                    text = ua.msbt_text(texts[label]).strip()
                    break
        except (OSError, KeyError, ua.ArchiveError, ValueError):
            pass
        _MSG_NAME_CACHE[key] = text
    return _MSG_NAME_CACHE[key]


def base_text(analysis: dict, fname: str, label: str):
    """The text at `label` in an archive's chosen base file (None if absent)."""
    base = analysis["variants"][analysis["base"]]
    try:
        files = ua.parse_sarc(Path(base["path"]).read_bytes())
        raw = ua.parse_msbt(files[fname]).get(label) if fname in files else None
    except (OSError, ua.ArchiveError):
        return None
    return ua.msbt_text(raw) if raw is not None else None


def apply_overrides(master_root: Path, plan: dict, auto: dict = None):
    """Adds the user's icons/names to every archive in the plan as extra
    variants holding their own bytes in `inline`: "Your changes" (`is_override`)
    and, for icon pictures a mod ships loose that the app picked on its own
    (`auto`, see gather_auto_icons), "<mod> (icon pictures)" (`is_override` +
    `is_auto`). An override that can't be applied (the icon isn't in the base
    file, wrong size) is kept as an unmergeable change with the reason, like any
    other."""
    ov = load_overrides(master_root)
    auto = auto or {}
    for archive_id, analysis in plan.items():
        # re-applying (the overrides changed) replaces the previous extra variants
        analysis["variants"] = [v for v in analysis["variants"] if not v.get("is_override")]
        base = analysis["variants"][analysis["base"]]
        try:
            base_files = ua.parse_sarc(Path(base["path"]).read_bytes())
        except (OSError, ua.ArchiveError):
            continue
        new_variants = []
        if archive_id in TEXTURE_ARCHIVES:
            maps = {}
            taken = {item_id(c) for v in analysis["variants"] for c in v["changes"]}

            def render(slots):
                changes, inline = [], {}
                for item, o in sorted(slots.items()):
                    entry, name = item.split("|", 1)
                    d = describe_texture(name)
                    change = {"entry": entry, "name": name, "character": d["character"], "kind": d["kind"],
                              "override": True, "md5": "", "width": 0, "height": 0, "format": 0}
                    try:
                        if entry not in base_files:
                            raise ua.PatchError("this screen isn't in your base file")
                        if entry not in maps:
                            maps[entry] = ua.entry_texture_map(base_files[entry])
                        tex = maps[entry].get(name)
                        if tex is None:
                            raise ua.PatchError("this icon isn't in your base file (it was built for an older game version)")
                        data = _render_icon(master_root / o["png"], tex, contain=d["kind"] == "Part")  # an absolute path stays absolute
                        change.update(md5=ua.md5(data), width=tex["width"], height=tex["height"], format=tex["format"], mergeable=True)
                        inline[item] = {"format": tex["format"], "width": tex["width"], "height": tex["height"], "data": data}
                        png = ua.texture_png({**tex, "data": data})
                        change["preview"] = ("data:image/png;base64," + base64.b64encode(png).decode("ascii")) if png else None
                    except (OSError, ua.PatchError, ua.ArchiveError, ValueError) as e:
                        change.update(mergeable=False, reason=str(e))
                    changes.append(change)
                return changes, inline

            mine = {i: o for i, o in ov["textures"].items() if ENTRY_ARCHIVE.get(i.split("|", 1)[0]) == archive_id}
            if mine:
                changes, inline = render(mine)
                new_variants.append(("Your changes", False, changes, inline))
            # pictures a mod ships loose: only where nothing else already decides the icon
            picked = {i: o for i, o in auto.items()
                      if ENTRY_ARCHIVE.get(i.split("|", 1)[0]) == archive_id and i not in mine and i not in taken}
            for mod_name in sorted({o["from"] for o in picked.values()}):
                changes, inline = render({i: o for i, o in picked.items() if o["from"] == mod_name})
                new_variants.append((f"{mod_name} (icon pictures)", True, changes, inline))
        else:
            changes, inline = [], {}
            files = {}
            wanted = dict(ov["strings"])
            resolved = {}
            for key, o in sorted(ov["names"].items()):
                kind, nm = key.split("|", 1)
                if (kind, nm) not in resolved:
                    resolved[(kind, nm)] = find_name_labels(plan, nm, kind)
                found = resolved[(kind, nm)]
                if found:
                    for label in found["labels"]:
                        wanted[f"Common.msbt|{label}"] = {"text": o["text"]}
                else:
                    # kept, so the review can say so instead of silently dropping it
                    changes.append({"file": "Common.msbt", "label": f"?{key}", "old": nm, "new": o["text"], "override": True,
                                    "mergeable": False,
                                    "reason": f"couldn't find \"{nm}\" in the game's text (or the game's text file isn't available)"})
            for item, o in sorted(wanted.items()):
                fname, label = item.split("|", 1)
                change = {"file": fname, "label": label, "old": "", "new": o["text"], "override": True}
                if fname not in files:
                    files[fname] = ua.parse_msbt(base_files[fname]) if fname in base_files and base_files[fname][:8] == b"MsgStdBn" else {}
                have = files[fname].get(label)
                if have is None:
                    change.update(mergeable=False, reason="this text isn't in your base file")
                else:
                    change.update(old=ua.msbt_text(have), mergeable=True)
                    inline[item] = o["text"].encode("utf-16-le") + b"\x00\x00"
                changes.append(change)
            if changes:
                new_variants.append(("Your changes", False, changes, inline))
        for label, is_auto, changes, inline in new_variants:
            analysis["variants"].append({
                "id": f"overrides-auto:{label}" if is_auto else "overrides", "keys": [], "labels": [label], "filed_under": [],
                "path": None, "entries": base["entries"], "changes": changes, "other": 0,
                "is_override": True, "is_auto": is_auto, "inline": inline,
            })


# --- loose icon pictures a mod ships (meant for hand-injection) ------------------
# Many mods ship no packed common.sarc / menu.sarc at all, just PNGs named
# tc_<Chara|MapChara|edChara>_<name>^l<suffix>.png. The suffix separates versions
# that Windows numbered when the same name was saved more than once (^l, ^l1 ...).

LOOSE_ICON_RE = re.compile(r"^tc_(Chara|MapChara|edChara)_(.+?)(?:\^l(.*))?\.png$", re.IGNORECASE)   # "^l" is optional
_SUPERSCRIPT_DIGITS = str.maketrans("¹²³", "123")
# Pictures named for what they are ("King Dedede Map.png", "... Menu.png", "... Common.png").
_PURPOSE_RE = re.compile(r"^(?P<prefix>.*?)[\s_\-]*(?P<what>map|menu|select|common|results?)\.png$", re.IGNORECASE)
_PURPOSE_KIND = {"map": "MapChara", "menu": "Chara", "select": "Chara", "common": "edChara", "result": "edChara", "results": "edChara"}


def _icon_walk(mod_folder: Path):
    """os.walk over a mod folder for loose pictures. Inside a romfs/ only its UI folder is looked at: some authors leave
    the pictures they made there (romfs/UI/Common/tc_MapChara_Iggy^l.png, romfs/UI/Menu.PNG) - the game ignores them, but
    they are the mod's icons all the same. Nothing else in a romfs/ is (its models and textures aren't pictures)."""
    for dirpath, dirnames, filenames in os.walk(mod_folder):
        rel = Path(dirpath).relative_to(mod_folder).parts
        if rel and rel[-1].lower() == "romfs":
            dirnames[:] = [d for d in dirnames if d.lower() == "ui"]
            filenames = []
        yield dirpath, dirnames, filenames


# Colour packs: pictures named by COLOUR for a character whose icons come in colours ("Map Light Blue.png",
# "Menu Black.png", "Ed Menu Pink.png"). Which of the game's colour slots each colour is comes from the game's own order,
# read off the game's icon textures (see the table below) - it differs from character to character (Yoshi's slot 00 is green,
# Shy Guy's is red). A colour the game has no slot for ("Purple" for Yoshi) takes the one slot left over, when exactly one
# is - and is left out when that isn't clear. Only words that mean one slot are listed; a name that could be two is left out.
_BLUES = {"blue": 2, "dark blue": 2, "navy": 2}
_LIGHT_BLUES = {"light blue": 3, "cyan": 3, "sky blue": 3, "aqua": 3, "turquoise": 3}
COLOUR_SLOT_NAMES = {   # slot -> what the game's icon looks like (for reading the tables below; not used by the app)
    "Yoshi":        "green, red, dark blue, light blue, yellow, pink, black, white, orange",
    "Heyho":        "red, green, blue, light blue, yellow, pink, black, white, orange   (Shy Guy: the coloured part is his hood and body)",
    "Catherine":    "pink, red, blue, light blue, yellow, green, black, white, orange   (Birdo: named by her body; the bow is another colour)",
    "SplatoonBoy":  "blue, purple, teal",
    "SplatoonGirl": "orange, lime, pink",
}
COLOUR_WORDS = {
    "Yoshi": {"green": 0, "red": 1, **_BLUES, **_LIGHT_BLUES, "yellow": 4, "pink": 5, "black": 6, "white": 7, "orange": 8},
    "Heyho": {"red": 0, "green": 1, **_BLUES, **_LIGHT_BLUES, "yellow": 4, "gold": 4, "pink": 5, "black": 6, "white": 7,
              "grey": 7, "gray": 7, "silver": 7, "orange": 8},
    "Catherine": {"pink": 0, "red": 1, **_BLUES, **_LIGHT_BLUES, "yellow": 4, "green": 5, "light green": 5, "lime": 5,
                  "black": 6, "white": 7, "orange": 8},
    "SplatoonBoy": {"blue": 0, "dark blue": 0, "purple": 1, "violet": 1, "teal": 2, "turquoise": 2, "cyan": 2, "aqua": 2},
    "SplatoonGirl": {"orange": 0, "lime": 1, "yellow green": 1, "green": 1, "pink": 2, "magenta": 2},
}
_PURPOSE_WORDS = {"map": "MapChara", "minimap": "MapChara", "menu": "Chara", "select": "Chara", "chara": "Chara",
                  "ed": "edChara", "edmenu": "edChara", "result": "edChara", "results": "edChara", "end": "edChara"}
_FILLER_WORDS = {"icon", "icons", "mini", "race", "screen", "picture", "pic", "the"}


def _colour_pack(mod_folder: Path, code: str):
    """(set or None, the picture paths it uses) for a colour pack of character `code` in a mod folder."""
    words = COLOUR_WORDS.get(code)
    if not words or code not in COLOR_VARIANTS:
        return None, set()
    found = collections.defaultdict(dict)      # colour name -> {kind: path}
    for dirpath, dirnames, filenames in _icon_walk(mod_folder):
        for f in sorted(filenames):
            if not f.lower().endswith(".png") or LOOSE_ICON_RE.match(f):
                continue
            tokens = [t for t in re.split(r"[\s_\-]+", f[:-4].lower()) if t]
            purpose = [_PURPOSE_WORDS[t] for t in tokens if t in _PURPOSE_WORDS]
            colour = " ".join(t for t in tokens if t not in _PURPOSE_WORDS and t not in _FILLER_WORDS)
            if not colour:
                continue
            path = Path(dirpath) / f
            kind = ("edChara" if "edChara" in purpose else "MapChara" if "MapChara" in purpose else "Chara" if "Chara" in purpose
                    else _icon_kind_by_size(path))
            if kind:
                found[colour].setdefault(kind, path)
    slots = {}                                  # slot -> colour name
    for colour in sorted(found):
        if colour in words and words[colour] not in slots:
            slots[words[colour]] = colour
    unknown = [c for c in sorted(found) if c not in words]
    free = [i for i in range(COLOR_VARIANTS[code]) if i not in slots]
    if len(unknown) == 1 and len(free) == 1:
        slots[free[0]] = unknown[0]
    if len(slots) < 2:
        return None, set()
    pics = [{"kind": kind, "code": f"{code}{slot:02d}", "path": path}
            for slot, colour in sorted(slots.items()) for kind, path in sorted(found[colour].items())]
    return _picture_set("~colours", pics), {p["path"] for p in pics}


# Numbered colours: a mod names its pictures with a number of its own ("tc_Chara_shy0.png" .. "shy8.png", the results icons
# "shy0k.png" .., the map icons "shy0kk.png" ..) - not a name the game has, so they would all go to every colour and the last
# one would win. When the numbers of a kind are exactly the character's colours - 0..n-1 (the game's slot numbers) or 1..n - each
# picture is that colour's. Anything less complete is left alone: partial numbering isn't something to guess at.
_NUMBERED_RE = re.compile(r"^[A-Za-z_ ]*?(?P<num>\d{1,2})[A-Za-z]{0,3}$")


def _numbered_colours(pics: list, code: str) -> list:
    n = COLOR_VARIANTS.get(code)
    if not n:
        return pics
    by_kind = collections.defaultdict(dict)        # kind -> {number: picture}
    for p in pics:
        m = _NUMBERED_RE.match(p["code"] or "")
        if m and not classify_code(p["code"]):
            by_kind[p["kind"]].setdefault(int(m.group("num")), p)
    renamed = {}
    for kind, numbered in by_kind.items():
        nums = set(numbered)
        shift = 0 if nums == set(range(n)) else 1 if nums == set(range(1, n + 1)) else None
        if shift is not None:
            renamed.update({id(p): f"{code}{num - shift:02d}" for num, p in numbered.items()})
    return [dict(p, code=renamed[id(p)]) if id(p) in renamed else p for p in pics]


def _small_picture(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return max(im.size) <= 600
    except Exception:
        return False


# Pictures with no telling name ("kirby.png", "kirbyk.png") but exactly the game's icon sizes: the
# three icons of a character are all different sizes, so size says which is which.
_ICON_SIZE_KIND = {(128, 128): "Chara", (64, 64): "MapChara", (52, 52): "edChara"}
_ICONISH_DIR_RE = re.compile(r"(^|[^a-z])(ui|icons?)([^a-z]|$)", re.IGNORECASE)


def _icon_kind_by_size(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return _ICON_SIZE_KIND.get(im.size)
    except Exception:
        return None


def _picture_set(suffix: str, pictures: list) -> dict:
    files = {}
    for p in pictures:
        files.setdefault(p["kind"], p["path"])
    return {"suffix": suffix, "files": files, "pictures": pictures}


def find_loose_icon_sets(mod_folder: Path, code: str = None) -> list:
    """The loose icon pictures in a mod folder (not looking inside romfs/),
    grouped into versions: [{"suffix", "files": {kind: first Path}, "pictures":
    [{"kind", "code", "path"}]}]. `code` is the texture-name stem of a tc_...^l
    picture, None for one named by purpose ("... Map.png") or told apart by its
    exact size. The un-suffixed version comes first, then numbered ones, then
    the other sets (purpose-named, exact-size, and - only when there is nothing
    else in the mod - a folder holding all three icon sizes). `code` is the game
    character the mod is filed under: with it, a pack named by colour (see
    COLOUR_WORDS) is one more set, its pictures carrying the right colour's name.
    Looks inside a romfs/ only at its UI folder (see _icon_walk)."""
    colour_set, colour_paths = _colour_pack(mod_folder, code) if code else (None, set())
    sets, purposeful = {}, {}
    named_in = collections.defaultdict(set)   # folder -> the tc_... set suffixes found in it
    sized = collections.defaultdict(list)     # folder -> unnamed pictures of exact icon sizes
    exact = collections.defaultdict(list)     # folder (not icon-looking) -> pictures of exact icon sizes, for the last resort below
    if not mod_folder.is_dir():
        return []
    for dirpath, dirnames, filenames in _icon_walk(mod_folder):
        iconish = any(_ICONISH_DIR_RE.search(part) for part in Path(dirpath).relative_to(mod_folder).parts)
        for f in filenames:
            path = Path(dirpath) / f
            if path in colour_paths:
                continue                                    # already in the colour pack
            m = LOOSE_ICON_RE.match(f)
            if m:
                kind = {"chara": "Chara", "mapchara": "MapChara", "edchara": "edChara"}[m.group(1).lower()]
                sfx = m.group(3) or ""
                sets.setdefault(sfx, []).append({"kind": kind, "code": m.group(2), "path": path})
                named_in[Path(dirpath)].add(sfx)
                continue
            pm = _PURPOSE_RE.match(f)
            if pm:
                kind, prefix = _PURPOSE_KIND[pm.group("what").lower()], pm.group("prefix").strip()
                if kind == "Chara" and pm.group("what").lower() == "menu" and re.search(r"(^|[\s_\-])ed$", prefix, re.IGNORECASE):
                    kind, prefix = "edChara", re.sub(r"[\s_\-]*ed$", "", prefix, flags=re.IGNORECASE).strip()   # "EdMenu" = results
                purposeful.setdefault(prefix, []).append({"kind": kind, "code": None, "path": path})
            elif iconish and f.lower().endswith(".png"):
                kind = _icon_kind_by_size(path)
                if kind:
                    sized[Path(dirpath)].append({"kind": kind, "code": None, "path": path})
            if not iconish and f.lower().endswith(".png"):
                kind = _icon_kind_by_size(path)
                if kind:
                    exact[Path(dirpath)].append({"kind": kind, "code": None, "path": path})
    leftovers = []   # pictures that aren't a set by themselves
    out_purpose = []
    for prefix, pics in sorted(purposeful.items()):
        # a lone "Map.png" could be anything; two or more differently-purposed, small pictures are icons
        if len({p["kind"] for p in pics}) >= 2 and all(_small_picture(p["path"]) for p in pics):
            out_purpose.append(_picture_set("~" + prefix, pics))
        else:
            leftovers.extend(pics)
    for folder, pics in sorted(sized.items()):
        if len({p["kind"] for p in pics}) >= 2:
            out_purpose.append(_picture_set("~" + folder.name, pics))
        else:
            leftovers.extend(pics)
    # A single picture beside a set of tc_... pictures in the same folder ("UI_menu.png" next to
    # "tc_MapChara_Pizza.png") fills the kind that set lacks.
    alone = collections.defaultdict(list)     # folder -> leftovers with no tc_... set there to join
    for p in leftovers:
        folder = Path(p["path"]).parent
        if named_in.get(folder):
            if len(named_in[folder]) == 1 and (p["kind"] in _ICON_SIZE_KIND.values()):
                sfx = next(iter(named_in[folder]))
                if p["kind"] not in {q["kind"] for q in sets[sfx]} and _icon_kind_by_size(p["path"]) == p["kind"]:
                    sets[sfx].append(p)
        else:
            alone[folder].append(p)
    # Pictures that were each on their own above because they were told apart in different ways - "Menu.png" (by its
    # name), "Race Mini Map.png" (by its name), "Race end.png" (only by its exact size) - are one set when they sit in
    # the same folder: two or more different icons there, in a folder that looks like one for icons ("UI images",
    # "Icons") or every one of them exactly the game's icon size for what it is. One picture per icon (the first by name).
    for folder, pics in sorted(alone.items()):
        one = {}
        for p in sorted(pics, key=lambda q: Path(q["path"]).name.lower()):
            one.setdefault(p["kind"], p)
        looks_like_icons = any(_ICONISH_DIR_RE.search(part) for part in folder.relative_to(mod_folder).parts)
        if len(one) >= 2 and (looks_like_icons or all(_icon_kind_by_size(p["path"]) == p["kind"] for p in one.values())):
            out_purpose.append(_picture_set("~" + folder.name, list(one.values())))
    out = [_picture_set(sfx, _numbered_colours(pics, code) if code else pics)
           for sfx, pics in sorted(sets.items(), key=lambda kv: (kv[0] != "", kv[0].translate(_SUPERSCRIPT_DIGITS)))]
    # Last resort, only when nothing above was found in the whole mod: a folder holding all three of the game's icon
    # sizes (128, 64 and 52 pixels) is icons, whatever it and its files are called ("Image Files Used" / 128.png,
    # Race.png, 52.png). When the mod has a set already, these are copies of it and are left alone.
    if not out and not out_purpose:
        for folder, pics in sorted(exact.items()):
            one = {}
            for p in sorted(pics, key=lambda q: Path(q["path"]).name.lower()):
                one.setdefault(p["kind"], p)
            if len(one) == 3:
                out_purpose.append(_picture_set("~" + folder.name, list(one.values())))
    return out + out_purpose + ([colour_set] if colour_set else [])


def picture_codes(pictures: list) -> set:
    """The game characters (base codes) a set's pictures are named for."""
    found = set()
    for p in pictures:
        cls = classify_code(p["code"]) if p["code"] else None
        if cls:
            found.add(cls[0])
    return found


def resolve_pictures(pictures: list, item_code: str, explicit: bool = False):
    """Which texture each picture goes to for character `item_code`:
    ({slot item: Path}, other) where `other` is the game character (code) the set
    is really named for when that isn't this one.

    A picture named for a real game texture ("SplatoonGirl02") goes exactly there;
    one named for something the mod made up ("MarioSunshine") or by purpose goes
    to all of this character's textures. A picture named for a DIFFERENT game
    character is skipped (`explicit` False - the automatic pick must not put Baby
    Rosalina's icons on Wendy) or, when the user says so (`explicit` True), moved
    to this character (keeping its colour number when this character has that colour)."""
    targets, other = {}, None
    for p in pictures:
        cls = classify_code(p["code"]) if p["code"] else None
        if cls and cls[0] != item_code and not explicit:
            other = other or cls[0]
            continue
        idx = cls[1] if cls else None
        if idx is not None and item_code in COLOR_VARIANTS and int(idx) < COLOR_VARIANTS[item_code]:
            stems = [f"{item_code}{idx}"]
        elif idx is not None and cls[0] == item_code:
            stems = [f"{item_code}{idx}"]
        else:
            stems = item_textures(item_code)
        for stem in stems:
            targets[f"{_KIND_ENTRY[p['kind']]}|tc_{p['kind']}_{stem}^l"] = p["path"]
    return targets, other


def _ships_no_romfs(mod_folder: Path) -> bool:
    import os
    for _d, dirs, _f in os.walk(mod_folder):
        if any(d.lower() == "romfs" for d in dirs):
            return False
    return True


def gather_auto_icons(extracted_root: Path, checked_keys, overrides: dict):
    """Decides which loose icon pictures to use without asking.

    For each character with exactly ONE mod that ships pictures for it, and
    exactly ONE version of them, the pictures are used for that character -
    unless the user already chose icons there or turned them down. When a mod
    ships several versions (or several mods do) the app can't know which is
    meant, so that character is returned in `needs_choice` for the user to pick.

    The mods considered are the ticked ones, plus downloads that are ONLY
    pictures (no romfs - a "UI icons" companion): they can't be ticked, and were
    downloaded under that character on purpose. Pictures named for a different
    game character than the one they're filed under are left alone.
    Returns ({slot item: {"png", "from", "who"}}, [{"item", "mods", "versions"}])."""
    import os
    by_item = collections.defaultdict(dict)  # item -> {mod folder key: sets}

    def add(folder_key):
        parts = folder_key.split("/")
        if folder_key in by_item.get(parts[1], {}):
            return
        sets = find_loose_icon_sets(extracted_root / Path(*parts), code_for_character(parts[1]))
        if sets:
            by_item[parts[1]][folder_key] = sets

    for key in sorted(checked_keys):
        parts = key.split("/")
        if len(parts) >= 3 and parts[0] == "characters":
            add("/".join(parts[:3]))
    chars = extracted_root / "characters"
    if chars.is_dir():
        for item_dir in sorted(chars.iterdir()):
            if item_dir.is_dir():
                for mod in sorted(item_dir.iterdir()):
                    if mod.is_dir() and _ships_no_romfs(mod):
                        add(f"characters/{item_dir.name}/{mod.name}")
    auto, needs = {}, []
    declined = set(overrides.get("declined", []))
    mine = {i for i, o in overrides.get("textures", {}).items() if not o.get("fill")}   # (a picture made from the Select screen gives way to a real one)
    for item, mods in sorted(by_item.items()):
        code = code_for_character(item)
        if not code:
            continue
        cands = []  # (mod folder key, set, {slot item: Path})
        for folder_key, sets in mods.items():
            for st in sets:
                targets, _other = resolve_pictures(st["pictures"], code)
                targets = {i: p for i, p in targets.items() if i not in mine and i not in declined}
                if targets:
                    cands.append((folder_key, st, targets))
        if not cands:
            continue  # the user decided every icon of this character, or nothing here is for it
        if len(cands) == 1:
            folder_key, _st, targets = cands[0]
            for iid, path in targets.items():
                auto[iid] = {"png": str(Path(path).resolve()), "from": folder_key.split("/")[2], "who": item}
        else:
            needs.append({"item": item, "mods": sorted({c[0].split("/")[2] for c in cands}), "versions": len(cands)})
    return auto, needs


def auto_signature(auto: dict, needs: list) -> str:
    """Changes when the automatic picks (or a picture behind one) change."""
    parts = [json.dumps([auto, needs], sort_keys=True)]
    for o in auto.values():
        try:
            parts.append(str(Path(o["png"]).stat().st_mtime_ns))
        except OSError:
            parts.append("missing")
    return "|".join(parts)
