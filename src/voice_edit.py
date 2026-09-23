"""Changing a character's voice: muting lines, and (further down) putting in the user's own audio.

A character's voice lives in two Nintendo ".bars" archives - romfs/Audio/Driver/Driver_<slot>.bars (about 80 short sounds
used during a race) and romfs/Audio/DriverMenu/MenuDriver_<slot>.bars (the character-select sound). A voice mod replaces a
whole archive, so changing one line means writing out the whole archive again with that one sound swapped.

What is proven on a real Switch (see README, "Voice editing"): swapping chosen sounds for a tiny silent sound, and rewriting
the archive the way rebuild() does, works for both kinds of archive; other sounds are untouched and the metadata blocks
need no change. rebuild() keeps every byte of the archive as it was except the chosen sounds and the few numbers that
locate things (the offset table and the total size).

Pure Python, no dependencies (voice_audio.py reads the archives; this writes them).
"""
import base64
import re
import struct

import voice_audio as va


class VoiceEditError(Exception):
    """Something the user can be told in plain words."""


ALIGN = 0x40

# The silent sound: a copy, byte for byte, of the one "Roblox Chicken Nugget over Ludwig" (a mod confirmed working on a Switch)
# uses for dozens of muted lines - 246 samples of digital silence, 48 kHz, stereo. 592 bytes; padded to 640 in an archive.
SILENT_FWAV = base64.b64decode(
    "RldBVv/+QAAAAQEAUAIAAAIAAAAAcAAAQAAAAMAAAAABcAAAAAEAAFABAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAElORk/AAAAAAgAAAIC7AAAAAAAA9gAAAAAAAAACAAAAAHEAABQAAAAAcQAAKAAAAAAf"
    "AAAYAAAAAAMAACgAAAAAAAAAAB8AALgAAAAAAwAAQgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAERBVEFQAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)
SILENT_SECONDS = 0.05      # a sound shorter than this is silence as far as the app is concerned (muted, or a mod's own mute)


# ------------------------------------------------------------------------------------------------------- the archive
def parse(data: bytes) -> list:
    """[{"index", "name", "offset", "size"}] for a little-endian .bars archive (see voice_audio.read_bars)."""
    if data[:4] != b"BARS":
        raise VoiceEditError("That isn't a .bars sound archive.")
    if data[8:10] != b"\xff\xfe":
        raise VoiceEditError("That voice file uses a rarely used (big-endian) layout the app can't rewrite.")
    try:
        ents = va.read_bars(data)
    except va.VoiceError as e:
        raise VoiceEditError(f"Couldn't read the voice file: {e}.")
    _check_metadata_before_sounds(data, ents)
    return [dict(x, index=i) for i, x in enumerate(ents)]


def _check_metadata_before_sounds(data: bytes, ents: list):
    """rebuild() copies each kept sound's bytes verbatim from its offset to the next sound's, and treats everything before
    the first sound as one untouched "header" block (name table, offset table, every AMTA metadata block). That is true of
    every real archive seen (every AMTA block sits before the first sound's audio) - it is what makes rebuild's identity
    check pass on all of them. If some archive instead interleaves a metadata block among the sounds, copying a kept
    sound's byte range could silently carry another sound's metadata along with it (or drop it) instead of raising an
    error - so this is checked and refused up front rather than trusted."""
    count = len(ents)
    if not count:
        return
    amta_offsets = struct.unpack_from(f"<{2 * count}I", data, 16 + 4 * count)[0::2]
    if max(amta_offsets) >= min(x["offset"] for x in ents):
        raise VoiceEditError("This voice file's layout isn't one the app can safely rewrite (its metadata isn't grouped before its sounds).")


def rebuild(data: bytes, repl: dict) -> bytes:
    """`data` (a little-endian .bars) with the sounds at the given entry numbers replaced by the given FWAV sounds
    ({index: bytes}). Everything else - header, name table, every metadata block, every other sound - stays byte for byte;
    only the offset table and the total size are rewritten. Names that share one sound's data (START_GLIDE and
    START_GLIDE2 point at the same bytes) keep sharing it unless only some of them are replaced. With nothing to replace
    the result is identical to `data` (apart from a total-size number some mods leave stale)."""
    ents = parse(data)
    count = len(ents)
    pairs_at = 16 + 4 * count
    pairs = list(struct.unpack_from(f"<{2 * count}I", data, pairs_at))
    members = {}
    for x in ents:
        members.setdefault(x["offset"], []).append(x["index"])
    out = bytearray(data[:min(members)])            # header, name table, offset table, all metadata

    def put(blob):
        out.extend(b"\0" * (-len(out) % ALIGN))
        at = len(out)
        out.extend(blob)
        return at

    for off in sorted(members):
        names = members[off]
        keep = [i for i in names if i not in repl]
        if keep:                                   # the original bytes stay, for every name that keeps them
            at = put(data[off:off + ents[names[0]]["size"]])
            for i in keep:
                pairs[2 * i + 1] = at
        made = {}                                  # a replacement shared by several names is written once
        for i in names:
            if i in repl:
                blob = bytes(repl[i])
                blob += b"\0" * (-len(blob) % ALIGN)
                if blob not in made:
                    made[blob] = put(blob)
                pairs[2 * i + 1] = made[blob]
    struct.pack_into(f"<{2 * count}I", out, pairs_at, *pairs)
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)


def sound_bytes(data: bytes, entry: dict) -> bytes:
    return data[entry["offset"]:entry["offset"] + entry["size"]]


def is_silent(fwav: bytes) -> bool:
    """True for a sound too short to be heard (what a muted line is)."""
    try:
        seconds, _ch = va.sound_length(fwav)
    except va.VoiceError:
        return False
    return seconds < SILENT_SECONDS


def sound_format(fwav: bytes) -> tuple:
    """(sample rate, channels, seconds) of one sound, from its header."""
    _e, _info, _data, _enc, rate, n, nchan = va._bfwav_info(fwav)
    return rate, nchan, (n / rate if rate else 0.0)


# ------------------------------------------------------------------------------------------------------- the lines
# A "line" is what a player thinks of as one thing the character says ("Finish first"). In the archive it is often
# several sounds - a base one, numbered alternatives (GOL_TOP2) and a tail (GOL_TOP_END) - and which of them the game plays,
# and when, isn't known, so a line is always changed as a whole. The line key is the sound's name without the character's
# code and without the number / _END: "pVO_BMR_GOL_TOP_END" -> "GOL_TOP".
_MENU_RE = re.compile(r"^pVO_M_[A-Za-z0-9]+_(.+)$")
_VO_RE = re.compile(r"^pVO_[A-Za-z0-9]+_(.+)$")
_HORN_RE = re.compile(r"^pSE_HORN_.+?_(ON_SP|ON|OFF)$", re.IGNORECASE)
_SE_RE = re.compile(r"^p?SE_[A-Za-z0-9]+_(.+)$")


def line_key(name: str) -> str:
    """The line a sound belongs to (see above). Menu sounds start with "M_" ("M_SELECT_CHAR"), horns are "HORN_ON" / "HORN_OFF" /
    "HORN_ON_SP"; a name the rules don't recognise is its own line."""
    m = _HORN_RE.match(name)
    if m:
        return "HORN_" + m.group(1).upper()
    m = _MENU_RE.match(name)
    if m:
        return "M_" + m.group(1)
    m = _VO_RE.match(name)
    if m:
        rest = m.group(1)
        key = re.sub(r"\d+$", "", re.sub(r"_END$", "", rest))
        return key or rest
    m = _SE_RE.match(name)
    if m:
        return m.group(1)                           # SE_CHR01_NEW_01 -> NEW_01
    return name


# key -> (label, description, confidence, category)
#   confidence: "sure" (heard on a Switch, or the name says it outright), "likely" (the name and the game make it clear
#   enough, or an outside source backs it up - stated as fact, not hedged), "unknown" (no reading anyone could point to
#   a source for - rather than dress up a guess as a fact, the description just says "Unknown").
CATEGORIES = ["Character select", "Finish", "Race start", "Overtaking", "Getting hit", "Falling", "Items", "Boosts", "Jumps & tricks", "Horn", "Other"]
# Checked against two modder references, not just the name alone: a GameBanana file-name key
# ("Audio Modding References, Meanings & Key File Name Tutorial", gamebanana.com/tuts/15275) that
# groups every line by what it's for, and a Super Mario Boards thread (marioboards.com/threads/42300)
# working out the older Wii U-era abbreviations these names were carried over from (GV -> GOL_GOD,
# CHOV -> HOVER_CHARGE, DHOV -> HOVER_DASH, SHOV -> START_HOVER, CMBL/W -> CMB_LAVA/CMB_WATER,
# STAF -> STR_FAIL), plus the game's own Super Horn item (HORN_ON_SP). A line neither source (nor the
# name itself) pins down is marked "unknown" rather than given a description dressed up to sound
# more certain than it is.
LINES = {
    "M_SELECT_CHAR": ("Character select", "Plays on the character-select screen when you pick this character.", "sure", "Character select"),
    "GOL_TOP": ("Finish first", "Plays when you finish the race in first place.", "sure", "Finish"),
    "GOL_GOD": ("Finish mid-pack", "Plays when you finish with a good result - a middle place (heard at 4th) - short of first.", "sure", "Finish"),
    "GOL_BAD": ("Finish last", "Plays when you finish with a bad result (heard at last place).", "sure", "Finish"),
    "START": ("Race start", "Said at the start of the race.", "likely", "Race start"),
    "STRM": ("STRM", "Unknown.", "unknown", "Race start"),
    "STR_FAIL": ("Mistimed start", "Plays for a bad start - pressing accelerate too early and stalling instead of boosting (\"Start Fail\" in modder shorthand).", "likely", "Race start"),
    "START_GLIDE": ("Taking flight (glider)", "Plays when your glider deploys and you launch into the air, not tied to the race start despite the name.", "likely", "Boosts"),
    "START_HOVER": ("Entering anti-gravity", "Plays when the track tilts you into an anti-gravity section and your kart starts to hover.", "likely", "Boosts"),
    "OVTAK": ("Overtaking", "Plays when you pass another racer.", "likely", "Overtaking"),
    "DMG_S": ("Hit (light)", "Plays when you are hit lightly, for example by a thrown item.", "likely", "Getting hit"),
    "DMG_CRSH": ("Hit (hard)", "Plays when you are hit hard, for example by an explosion.", "likely", "Getting hit"),
    "DMG_SPN": ("Spinning out", "Plays when you spin out.", "likely", "Getting hit"),
    "DMG_BOUND": ("Bump", "Unknown.", "unknown", "Getting hit"),
    "FALL_WATER": ("Falling into water", "Plays when you fall into water.", "likely", "Falling"),
    "FALL_LAVA": ("Falling into lava", "Plays when you fall into lava or a similar hazard.", "likely", "Falling"),
    "FALL_SHORT": ("Short fall", "Plays after a short fall off the course.", "likely", "Falling"),
    "CMB_WATER": ("Back from the water", "A \"comeback\" line: plays as you're put back on the track after falling into water.", "likely", "Falling"),
    "CMB_LAVA": ("Back from the lava", "A \"comeback\" line: plays as you're put back on the track after falling into lava.", "likely", "Falling"),
    "ITM_STAR": ("Super Star", "Plays when you use a Super Star.", "likely", "Items"),
    "ITM_TRW": ("Throwing an item", "Plays when you throw an item.", "likely", "Items"),
    "ITM_PUT": ("Dropping an item", "Plays when you drop an item behind you.", "likely", "Items"),
    "ITM_SCES": ("Item hits someone", "Plays when an item you threw or dropped lands a hit on another racer.", "likely", "Items"),
    "ITM_GESSO": ("Blooper ink", "Plays when you are hit by a Blooper's ink.", "likely", "Items"),
    "DSH": ("Boost", "Plays when you get a boost (mushroom, boost pad).", "likely", "Boosts"),
    "DSH_S": ("Small boost", "Plays for a smaller drift boost (a blue mini-turbo) rather than the bigger DSH boost.", "likely", "Boosts"),
    "HOVER_DASH": ("Boost (anti-gravity)", "Plays for the boost you get after charging up while hovering in anti-gravity.", "likely", "Boosts"),
    "HOVER_CHARGE": ("Charging (anti-gravity)", "Plays for the boost from bumping into another racer while hovering in anti-gravity.", "likely", "Boosts"),
    "JP_ACT": ("Jump", "Plays when you jump off a ramp and do a trick.", "likely", "Jumps & tricks"),
    "JP_ACT_SA": ("Trick A", "Unknown.", "unknown", "Jumps & tricks"),
    "JP_ACT_SB": ("Trick B", "Unknown.", "unknown", "Jumps & tricks"),
    "KT_JPACT": ("Kart jump effect", "A body-specific jump trick sound some characters (Inkling, Tanooki Mario, Peachette) have only in a kart body, on top of the regular JP_ACT.", "likely", "Jumps & tricks"),
    "KT_JPACT_SA": ("Kart jump effect A", "Unknown.", "unknown", "Jumps & tricks"),
    "KT_JPACT_SB": ("Kart jump effect B", "Unknown.", "unknown", "Jumps & tricks"),
    "BK_JPACT": ("Bike jump effect", "The bike-body counterpart to KT_JPACT: a jump trick sound only used on a bike, on top of the regular JP_ACT.", "likely", "Jumps & tricks"),
    "BK_JPACT_SA": ("Bike jump effect A", "Unknown.", "unknown", "Jumps & tricks"),
    "BK_JPACT_SB": ("Bike jump effect B", "Unknown.", "unknown", "Jumps & tricks"),
    "HORN_ON": ("Horn (press)", "The character's horn sound while you hold the horn.", "likely", "Horn"),
    "HORN_OFF": ("Horn (release)", "The short sound when you let go of the horn.", "likely", "Horn"),
    "HORN_ON_SP": ("Super Horn", "Plays when you use the Super Horn item - a louder, distorted version of the character's own horn that can flip nearby racers and pop shells.", "likely", "Horn"),
    "NEW_01": ("Extra menu sound", "Unknown.", "unknown", "Other"),
}
# what the four "important moments" at the top of the editor are
MOMENTS = ["M_SELECT_CHAR", "GOL_TOP", "GOL_GOD", "GOL_BAD"]
CONFIDENCE_NOTE = {"sure": "", "likely": "", "unknown": ""}


def describe(key: str) -> dict:
    """{"key", "label", "description", "confidence", "category", "moment"} for a line key (a plain fallback for one that
    isn't in the list)."""
    if key in LINES:
        label, desc, conf, cat = LINES[key]
    else:
        label = key.replace("_", " ").strip().capitalize() or "Sound"
        desc, conf, cat = "Not identified yet - play it to hear what it is.", "unknown", "Other"
    return {"key": key, "label": label, "description": desc, "confidence": conf, "category": cat, "moment": key in MOMENTS}


def line_kind(key: str) -> str:
    """"menu" for a line in a MenuDriver archive, else "race"."""
    return "menu" if key.startswith("M_") or key == "NEW_01" else "race"


def group_lines(entries: list) -> dict:
    """{line key: [entry index...]} for the sounds of an archive (parse())."""
    out = {}
    for x in entries:
        out.setdefault(line_key(x["name"]), []).append(x["index"])
    return out


# ------------------------------------------------------------------------------------------------------- new sounds
# Audio the user chose is turned into a sound the game plays by voice_dsp.py (DSP-ADPCM, the format of every voice in the game).
from voice_dsp import EncodeError, encode_sound, make_fwav  # noqa: E402,F401
