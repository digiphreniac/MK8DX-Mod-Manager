"""Reading a character's voice files so they can be played in the app.

A character's voice lives in two Nintendo ".bars" archives (romfs/Audio/Driver/Driver_<name>.bars for the race,
romfs/Audio/DriverMenu/MenuDriver_<name>.bars for the menus). Each holds many small sounds ("BFWAV" files, one per
line - "pVO_CPC_OVTAK" is Cat Peach's overtake) next to a table of their names. This turns one of them into an
ordinary 16-bit .wav that a web page can play. Pure Python (no audio libraries): the clips are short.

Supported: BARS with BFWAV sounds, 8-bit / 16-bit PCM or DSP-ADPCM (which is what the game's voices use), any number
of channels, either byte order. Anything else raises VoiceError with a plain-words message.
"""
import io
import re
import struct
import sys
import wave
from array import array


class VoiceError(Exception):
    pass


MAX_SECONDS = 60          # nothing here is longer than ~7 s; a "voice" past a minute isn't one
_ENC_NAMES = {0: "8-bit PCM", 1: "16-bit PCM", 2: "DSP-ADPCM", 3: "IMA-ADPCM"}


def _u(fmt, data, off, e):
    try:
        return struct.unpack_from(e + fmt, data, off)
    except struct.error:
        raise VoiceError("the file is cut short")


def read_bars(data: bytes):
    """[{"name", "offset", "size"}] - the sounds in a .bars archive, in file order (names as the game spells them)."""
    if data[:4] != b"BARS":
        raise VoiceError("not a .bars sound archive")
    e = "<" if data[4 + 4:4 + 6] == b"\xff\xfe" else ">"
    (count,) = _u("I", data, 12, e)
    if count > 4096:
        raise VoiceError("the archive's table looks damaged")
    offs = _u(f"{2 * count}I", data, 16 + 4 * count, e) if count else ()
    entries = []
    for i in range(count):
        amta, asset = offs[2 * i], offs[2 * i + 1]
        if not (0 < amta < len(data) and 0 < asset < len(data)):
            raise VoiceError("the archive's table looks damaged")
        seg = data[amta:asset] if asset > amta else data[amta:amta + 0x400]
        name = None
        j = seg.find(b"STRG")
        if j >= 0 and j + 8 <= len(seg):
            (sz,) = _u("I", seg, j + 4, e)
            name = seg[j + 8:j + 8 + sz].split(b"\0")[0].decode("latin-1")
        entries.append({"name": name or f"sound {i + 1}", "offset": asset})
    # a sound runs to the start of the next one (or the end of the file)
    starts = sorted(x["offset"] for x in entries) + [len(data)]
    for x in entries:
        x["size"] = next(s for s in starts if s > x["offset"]) - x["offset"]
    return entries


def _bfwav_info(w: bytes):
    if w[:4] != b"FWAV":
        raise VoiceError("this sound isn't in the format the game's voices use")
    e = "<" if w[4:6] == b"\xff\xfe" else ">"
    (nblocks,) = _u("H", w, 0x10, e)
    info = data = None
    for i in range(min(nblocks, 8)):
        flag, _pad, off, _size = _u("HHII", w, 0x14 + 12 * i, e)
        if flag == 0x7000:
            info = off
        elif flag == 0x7001:
            data = off
    if info is None or data is None:
        raise VoiceError("the sound has no audio data")
    enc = w[info + 8] if info + 8 < len(w) else 255
    rate, _ls, nsamples = _u("III", w, info + 0x0C, e)
    (nchan,) = _u("I", w, info + 0x1C, e)
    return e, info, data, enc, rate, nsamples, nchan


def sound_length(w: bytes):
    """(seconds, channels) of one sound, from its header alone."""
    _e, _info, _data, _enc, rate, n, nchan = _bfwav_info(w)
    return (n / rate if rate else 0.0), nchan


def _decode_dsp(data, start, nsamples, coefs, h1, h2):
    out = array("h")
    append = out.append
    pos = start
    remaining = nsamples
    end = len(data)
    while remaining > 0:
        if pos >= end:
            raise VoiceError("the sound's audio is cut short")
        head = data[pos]
        scale = 1 << (head & 0xF)
        idx = (head >> 4) & 7
        c1, c2 = coefs[2 * idx], coefs[2 * idx + 1]
        n = 14 if remaining > 14 else remaining
        for i in range(n):
            b = data[pos + 1 + (i >> 1)] if pos + 1 + (i >> 1) < end else 0
            nib = (b >> 4) if not (i & 1) else (b & 15)
            if nib > 7:
                nib -= 16
            s = (((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2) >> 11
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            append(s)
            h2 = h1
            h1 = s
        pos += 8
        remaining -= n
    return out


def decode_bfwav(w: bytes):
    """(sample rate, channels, [array of 16-bit samples per channel]) for one BFWAV sound."""
    e, info, data, enc, rate, n, nchan = _bfwav_info(w)
    if enc not in (0, 1, 2):
        raise VoiceError(f"this sound is {_ENC_NAMES.get(enc, 'in an unknown encoding')}, which can't be played here")
    if not (1 <= nchan <= 8) or not (0 < rate <= 192000) or n <= 0:
        raise VoiceError("the sound's header looks damaged")
    if n / rate > MAX_SECONDS:
        raise VoiceError("this sound is too long to preview")
    table = info + 0x1C          # channel offsets count from the start of the channel table
    body = data + 8              # ... and sample offsets from the start of the audio block's body
    channels = []
    for c in range(nchan):
        _flag, _pad, coff = _u("HHI", w, table + 4 + 8 * c, e)
        chan = table + coff
        _f1, _p1, soff = _u("HHI", w, chan, e)
        start = body + soff
        if enc == 2:
            _f2, _p2, aoff = _u("HHI", w, chan + 8, e)
            adpcm = chan + aoff
            coefs = _u("16h", w, adpcm, e)
            _ps, h1, h2 = _u("Hhh", w, adpcm + 0x20, e)
            channels.append(_decode_dsp(w, start, n, coefs, h1, h2))
        elif enc == 1:
            if start + 2 * n > len(w):
                raise VoiceError("the sound's audio is cut short")
            channels.append(array("h", _u(f"{n}h", w, start, e)))
        else:
            if start + n > len(w):
                raise VoiceError("the sound's audio is cut short")
            channels.append(array("h", [(b - 256 if b > 127 else b) * 256 for b in w[start:start + n]]))
    return rate, nchan, channels


def to_wav(rate, channels):
    """A .wav file (bytes) from per-channel 16-bit sample arrays."""
    n = len(channels[0])
    if len(channels) == 1:
        frames = channels[0]
    else:
        frames = array("h", bytes(2 * n * len(channels)))
        for c, ch in enumerate(channels):
            frames[c::len(channels)] = ch[:n]
    if sys.byteorder == "big":
        frames = array("h", frames)
        frames.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(len(channels))
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(frames.tobytes())
    return buf.getvalue()


# ---- plain-words names for the sounds ----------------------------------------------------------------------------
# The game names them like "pVO_CPC_OVTAK2" (voice, character code, what happens, take 2). The words below are
# the ones that are clear; the rest are shown as the game spells them, and the exact name is always in the tooltip.
_WORDS = {
    "START": "Start", "OVTAK": "Overtake", "DMG": "Hit", "GOL": "Goal", "TOP": "top", "GOD": "good", "BAD": "bad",
    "FALL": "Fall", "WATER": "into water", "LAVA": "into lava", "ITM": "Item", "TRW": "throw", "STAR": "star",
    "GESSO": "Blooper", "JP": "Jump", "ACT": "trick", "HOVER": "Anti-gravity", "GLIDE": "Glide", "DSH": "Dash",
    "DASH": "Dash", "CHARGE": "charge", "CRSH": "Crash", "BOUND": "Bounce", "HORN": "Horn", "ON": "on", "OFF": "off",
    "END": "end", "SHORT": "short", "FAIL": "fail", "STR": "Start boost",
}


def clip_label(raw: str):
    """(label, group) for a sound name: group is "select" (the character-select voice), "race" or "horn"."""
    name = re.sub(r"^p?(VO|SE)_", "", raw)
    if re.match(r"^p?VO_M_", raw):
        rest = name.split("_")[2:]       # M, <character>, ...
        if any(t.startswith("SELECT") for t in rest):
            return "Character select", "select"
        return " ".join(_word(t) for t in rest).strip().capitalize() or raw, "select"
    parts = name.split("_")
    if raw.startswith(("pSE_HORN", "SE_HORN")):
        rest = [parts[0]] + parts[2:]    # HORN, <character>, ON/OFF ...
        return _join(rest), "horn"
    return _join(parts[1:] if len(parts) > 1 else parts), "race"


def _word(tok):
    m = re.match(r"^([A-Za-z]+?)(\d+)$", tok)
    base, num = (m.group(1), m.group(2)) if m else (tok, "")
    word = _WORDS.get(base.upper()) or (base.upper() if len(base) <= 2 else base.capitalize())   # (short codes like "SB" stay as they are)
    return word + (f" {num}" if num else "")


def _join(tokens):
    words = [_word(t) for t in tokens if t]
    if not words:
        return "Sound"
    return (words[0][0].upper() + words[0][1:] + (" " + " ".join(words[1:]) if len(words) > 1 else "")).strip()
