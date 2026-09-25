"""Readers for the packed UI archives MK8DX mods ship (romfs/UI/cmn/common.sarc,
menu.sarc and romfs/UI/<locale>/message.sarc), used by the guided UI setup
(ui_setup.py). Read-only: nothing here writes an archive.

The shape of these files, measured against real mod downloads:

  common.sarc / menu.sarc   plain little-endian SARC of ~50-110 named ".szs"
       entries (one per screen/widget: cm_L_CharaIcon_00.szs, mn_L_CharaIcon_00.szs,
       ...). Each entry is Yaz0-compressed and, once decompressed, is itself a
       SARC whose entries have NO names (only hashes). The icon entries hold
       one small layout blob plus a single BNTX texture package - and every
       character's icon lives in that ONE package (tc_MapChara_<code>^l,
       tc_edChara_<code>^l, tc_Chara_<code>^l, ...), so two mods that each
       changed one character's icon changed the same entry. Combining them means
       working on individual textures inside it, not on the entry.
  message.sarc              plain SARC of five MSBT text files (Common.msbt,
       DLC.msbt, Menu.msbt, Race.msbt, Region.msbt); course and character names
       are individual labelled strings inside them.
"""

import collections
import hashlib
import io
import os
import struct
import threading
from pathlib import Path

import bntx_decode

try:
    from PIL import Image
except ImportError:  # previews just become unavailable
    Image = None


class ArchiveError(Exception):
    """A file that isn't the shape this module understands."""


# --- Yaz0 ------------------------------------------------------------------

_BITS = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)


def yaz0_decompress(data: bytes, limit: int = None) -> bytes:
    """Decompresses a Yaz0 stream. `limit` stops as soon as that many output
    bytes exist (enough to read an archive's header without paying for the
    whole thing)."""
    if data[:4] != b"Yaz0":
        raise ArchiveError("not a Yaz0 stream")
    size = struct.unpack_from(">I", data, 4)[0]
    if limit is not None:
        size = min(size, limit)
    out = bytearray(size)
    src, dst, n = 16, 0, len(data)
    # (bulk of the stream: far enough from both ends that no group can run past them, so nothing needs checking per byte)
    safe_dst = size - 8 * 273
    safe_src = n - 8 * 3 - 1
    while dst < safe_dst and src < safe_src:
        code = data[src]
        src += 1
        if code == 0xFF:
            out[dst:dst + 8] = data[src:src + 8]
            dst += 8
            src += 8
            continue
        for bit in _BITS:
            if code & bit:
                out[dst] = data[src]
                dst += 1
                src += 1
            else:
                b1 = data[src]
                dist = (((b1 & 0x0F) << 8) | data[src + 1]) + 1
                length = b1 >> 4
                if length == 0:
                    length = data[src + 2] + 0x12
                    src += 3
                else:
                    length += 2
                    src += 2
                start = dst - dist
                if start < 0:
                    raise ArchiveError("corrupt Yaz0 stream")
                if dist >= length:
                    out[dst:dst + length] = out[start:start + length]
                elif dist == 1:
                    out[dst:dst + length] = bytes((out[start],)) * length
                else:
                    chunk = bytes(out[start:dst])
                    out[dst:dst + length] = (chunk * (length // dist + 1))[:length]
                dst += length
    while dst < size and src < n:
        code = data[src]
        src += 1
        if code == 0xFF and dst + 8 <= size and src + 8 <= n:   # eight literals in a row: one copy
            out[dst:dst + 8] = data[src:src + 8]
            dst += 8
            src += 8
            continue
        for _ in range(8):
            if dst >= size:
                break
            if code & 0x80:
                out[dst] = data[src]
                dst += 1
                src += 1
            else:
                b1 = data[src]
                dist = (((b1 & 0x0F) << 8) | data[src + 1]) + 1
                length = b1 >> 4
                if length == 0:
                    length = data[src + 2] + 0x12
                    src += 3
                else:
                    length += 2
                    src += 2
                if length > size - dst:
                    length = size - dst
                start = dst - dist
                if start < 0:
                    raise ArchiveError("corrupt Yaz0 stream")
                if dist >= length:
                    out[dst:dst + length] = out[start:start + length]
                elif dist == 1:
                    out[dst:dst + length] = bytes((out[start],)) * length
                else:  # overlapping copy repeats the last `dist` bytes
                    chunk = bytes(out[start:dst])
                    out[dst:dst + length] = (chunk * (length // dist + 1))[:length]
                dst += length
            code = (code << 1) & 0xFF
    return bytes(out[:dst])


# Decompressing a big icon archive takes a third of a second or more (it is a plain Python loop), and the same few
# archives are opened again and again - by every menu-look card, by the UI step's checks, on every launch. So a
# decompressed archive is remembered: in memory for this run, and (once set_cache_dir() has been told where) on disk for the
# next ones. It is found by a fingerprint of the compressed bytes, so a changed archive can never be mistaken for the old one.
_CACHE_MIN_SIZE = 256 * 1024        # smaller ones aren't worth remembering
_MEM_LIMIT = 96 * 1024 * 1024       # bytes of decompressed archives kept in memory
_DISK_FILES = 24                    # decompressed archives kept on disk (least recently used are dropped)
_DISK_BYTES = 400 * 1024 * 1024
_mem = collections.OrderedDict()    # fingerprint -> decompressed bytes
_mem_lock = threading.Lock()
_cache_dir = None


def set_cache_dir(path) -> None:
    """Where decompressed archives are kept between runs (None = memory only)."""
    global _cache_dir
    _cache_dir = Path(path) if path is not None else None


def forget_decompressed() -> None:
    """Drops every remembered decompressed archive, in memory and on disk (the game's files were replaced)."""
    with _mem_lock:
        _mem.clear()
    if _cache_dir is not None:
        for f in _cache_dir.glob("*.bin"):
            f.unlink(missing_ok=True)


def _disk_get(key: str, size: int):
    if _cache_dir is None:
        return None
    path = _cache_dir / f"{key}.bin"
    try:
        out = path.read_bytes()
        if len(out) != size:
            return None
        os.utime(path)   # (used just now: it is the last to be dropped)
        return out
    except OSError:
        return None


def _disk_put(key: str, out: bytes) -> None:
    if _cache_dir is None:
        return
    try:
        _cache_dir.mkdir(parents=True, exist_ok=True)
        path = _cache_dir / f"{key}.bin"
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_bytes(out)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        files = sorted(((f.stat().st_mtime, f.stat().st_size, f) for f in _cache_dir.glob("*.bin")), key=lambda t: t[0])
        total = sum(t[1] for t in files)
        while files and (len(files) > _DISK_FILES or total > _DISK_BYTES) and files[0][2] != path:
            _mtime, size, old = files.pop(0)
            total -= size
            old.unlink(missing_ok=True)
    except OSError:
        pass


def _yaz0_remembered(blob: bytes) -> bytes:
    """The whole decompressed archive, worked out once per distinct archive."""
    size = struct.unpack_from(">I", blob, 4)[0]
    if size < _CACHE_MIN_SIZE:
        return yaz0_decompress(blob)
    key = hashlib.sha1(blob).hexdigest()
    with _mem_lock:
        hit = _mem.get(key)
        if hit is not None:
            _mem.move_to_end(key)
            return hit
    out = _disk_get(key, size)
    if out is None:
        out = yaz0_decompress(blob)
        _disk_put(key, out)
    with _mem_lock:
        _mem[key] = out
        while len(_mem) > 1 and sum(len(v) for v in _mem.values()) > _MEM_LIMIT:
            _mem.popitem(last=False)
    return out


def unwrap(blob: bytes, limit: int = None) -> bytes:
    """Yaz0-decompresses a blob if it is one, else returns it as is."""
    if blob[:4] != b"Yaz0":
        return blob
    if limit is not None:   # (just the start of it: cheap, and not worth remembering)
        return yaz0_decompress(blob, limit)
    return _yaz0_remembered(blob)


# --- SARC ------------------------------------------------------------------

def parse_sarc(data: bytes) -> dict:
    """{name: bytes} for a SARC. An entry with no stored name (the icon
    archives' inner SARCs) is keyed by its hash, "#xxxxxxxx"."""
    if data[:4] != b"SARC":
        raise ArchiveError("not a SARC archive")
    _hdr, bom = struct.unpack_from("<HH", data, 4)
    endian = "<" if bom == 0xFEFF else ">"
    _size, data_off = struct.unpack_from(endian + "II", data, 8)
    if data[0x14:0x18] != b"SFAT":
        raise ArchiveError("SARC has no SFAT table")
    _sfat_hdr, count = struct.unpack_from(endian + "HH", data, 0x18)
    pos = 0x20
    nodes = []
    for _ in range(count):
        nodes.append(struct.unpack_from(endian + "IIII", data, pos))
        pos += 16
    if data[pos:pos + 4] != b"SFNT":
        raise ArchiveError("SARC has no SFNT table")
    names_base = pos + 8
    out = {}
    for name_hash, attr, start, end in nodes:
        if attr >> 24:
            at = names_base + (attr & 0xFFFFFF) * 4
            name = data[at:data.index(b"\0", at)].decode("utf-8", "replace")
        else:
            name = f"#{name_hash:08x}"
        out[name] = data[data_off + start:data_off + end]
    return out


def _pow2_alignment(offset: int, cap: int = 0x1000) -> int:
    """The largest power of two (up to `cap`) that divides `offset` - the
    alignment an entry was written with, recovered from where it sits."""
    if offset == 0:
        return cap
    return min(offset & -offset, cap)


def rebuild_sarc(original: bytes, replacements: dict) -> bytes:
    """A copy of the SARC `original` with some named entries' data replaced.

    Nothing about the archive's structure changes - same entries, names,
    order and header tables - so those bytes are reused verbatim and only the
    entry offsets/sizes and the total size are recomputed. Each entry keeps
    the alignment it was originally written with (recovered from its original
    offset), so a rebuild with NO replacements reproduces the original file
    byte for byte (which is how this is tested)."""
    if original[:4] != b"SARC":
        raise ArchiveError("not a SARC archive")
    _hdr, bom = struct.unpack_from("<HH", original, 4)
    if bom != 0xFEFF:
        raise ArchiveError("only little-endian (Switch) SARCs are supported")
    data_off = struct.unpack_from("<I", original, 0x0C)[0]
    count = struct.unpack_from("<H", original, 0x1A)[0]
    nodes = [list(struct.unpack_from("<IIII", original, 0x20 + 16 * i)) for i in range(count)]
    names = parse_sarc(original)  # name -> original bytes (also validates the tables)
    by_index = []
    sfnt = 0x20 + 16 * count + 8
    for hash_, attr, _s, _e in nodes:
        at = sfnt + (attr & 0xFFFFFF) * 4
        by_index.append(original[at:original.index(b"\0", at)].decode("utf-8", "replace"))
    unknown = set(replacements) - set(by_index)
    if unknown:
        raise ArchiveError(f"no such entry in the archive: {sorted(unknown)[0]}")

    head = bytearray(original[:data_off])
    data = bytearray()
    for i, (hash_, attr, start, end) in enumerate(nodes):
        name = by_index[i]
        blob = replacements.get(name, original[data_off + start:data_off + end])
        align = _pow2_alignment(data_off + start)
        pad = (-(data_off + len(data))) % align
        data += b"\0" * pad
        new_start = len(data)
        data += blob
        struct.pack_into("<II", head, 0x20 + 16 * i + 8, new_start, new_start + len(blob))
    struct.pack_into("<I", head, 0x08, data_off + len(data))
    return bytes(head) + bytes(data)


def yaz0_store(data: bytes) -> bytes:
    """A valid Yaz0 stream holding `data` uncompressed (every group is eight
    literals). Larger than a real compression (~12%), but every Yaz0 decoder
    reads it, and it needs no compressor - fine for an icon archive."""
    full, rest = divmod(len(data), 8)
    body = bytearray(9 * full)
    body[0::9] = b"\xff" * full          # (the group's flag byte, then its eight literals - filled a column at a time)
    for j in range(8):
        body[1 + j::9] = data[j:full * 8:8]
    if rest:
        body.append((0xFF << (8 - rest)) & 0xFF)
        body += data[full * 8:]
    return b"Yaz0" + struct.pack(">I", len(data)) + b"\0" * 8 + bytes(body)


# --- BNTX ------------------------------------------------------------------

def parse_bntx_textures(data: bytes) -> list:
    """Every texture in a .bntx: [{name, format, width, height, layout, data}].
    `data` is the first mip's raw (still block-linear swizzled) bytes."""
    if data[:4] != b"BNTX":
        raise ArchiveError("not a BNTX")
    endian = "<" if data[12:14] == b"\xff\xfe" else ">"
    _target, count, info_ptrs_addr, *_rest = struct.unpack_from(endian + "4sI5qI4x", data, 32)
    textures = []
    for i in range(count):
        tex_pos = struct.unpack_from(endian + "q", data, info_ptrs_addr + 8 * i)[0]
        if data[tex_pos:tex_pos + 4] != b"BRTI":
            raise ArchiveError("malformed texture block")
        v = struct.unpack_from(endian + "2B4H2x2I3i3I20x3IB3x8q", data, tex_pos + 16)
        fmt, width, height, layout, image_size, name_addr, ptrs_addr = v[6], v[8], v[9], v[12], v[14], v[18], v[20]
        name_len = struct.unpack_from(endian + "H", data, name_addr)[0]
        name = data[name_addr + 2:name_addr + 2 + name_len].decode("utf-8", "replace")
        first = struct.unpack_from(endian + "q", data, ptrs_addr)[0]
        textures.append({
            "name": name, "format": fmt, "width": width, "height": height,
            "layout": layout, "data": data[first:first + image_size], "offset": first,
        })
    return textures


def texture_png(tex: dict):
    """PNG bytes for an uncompressed RGBA8 texture (every character icon is),
    or None for any other format / without Pillow."""
    if Image is None or (tex["format"] >> 8) != 0x0B:
        return None
    try:
        raw = bntx_decode._deswizzle(tex["width"], tex["height"], 1, 4, tex["layout"] & 7, tex["data"])
        img = Image.frombytes("RGBA", (tex["width"], tex["height"]), raw)
    except Exception:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def entry_textures(entry_blob: bytes) -> list:
    """The textures inside one ".szs" entry of common/menu.sarc, or [] if that
    entry is layout-only (no BNTX inside)."""
    inner = parse_sarc(unwrap(entry_blob))
    for blob in inner.values():
        if blob[:4] == b"BNTX":
            return parse_bntx_textures(blob)
    return []


class PatchError(ArchiveError):
    """A change that can't be applied without restructuring the archive
    (the texture isn't in the base, or is a different size/format)."""


def sarc_entry_spans(data: bytes) -> dict:
    """{name: (start, end)} absolute byte spans of a SARC's entries."""
    parse_sarc(data)  # validates
    data_off = struct.unpack_from("<I", data, 0x0C)[0]
    count = struct.unpack_from("<H", data, 0x1A)[0]
    sfnt = 0x20 + 16 * count + 8
    spans = {}
    for i in range(count):
        hash_, attr, start, end = struct.unpack_from("<IIII", data, 0x20 + 16 * i)
        if attr >> 24:
            at = sfnt + (attr & 0xFFFFFF) * 4
            name = data[at:data.index(b"\0", at)].decode("utf-8", "replace")
        else:
            name = f"#{hash_:08x}"
        spans[name] = (data_off + start, data_off + end)
    return spans


def patch_icon_entry(entry_blob: bytes, new_pixels: dict, want: dict) -> bytes:
    """A ".szs" icon entry (Yaz0 -> nameless SARC -> BNTX package) with some
    textures' pixel data swapped, as a new Yaz0 blob.

    `new_pixels` is {texture name: raw bytes}; `want` is {texture name:
    (format, width, height)} the incoming pixels were made for. Every texture
    must already exist in this package with the SAME format and size - then the
    swap is a same-length byte copy, so nothing else in the package moves. A
    texture that doesn't fit raises PatchError instead of being forced in."""
    inner = bytearray(unwrap(entry_blob))
    spans = sarc_entry_spans(bytes(inner))
    bntx_span = next(((a, b) for a, b in spans.values() if inner[a:a + 4] == b"BNTX"), None)
    if bntx_span is None:
        raise PatchError("this entry has no texture package")
    a, b = bntx_span
    package = bytes(inner[a:b])
    have = {t["name"]: t for t in parse_bntx_textures(package)}
    for name, pixels in new_pixels.items():
        t = have.get(name)
        if t is None:
            raise PatchError(f"{name} isn't in your base file (it was built for an older game version)")
        if (t["format"], t["width"], t["height"]) != tuple(want[name]) or len(t["data"]) != len(pixels):
            raise PatchError(f"{name} is a different size/format than the one in your base file")
        inner[a + t["offset"]:a + t["offset"] + len(pixels)] = pixels
    return yaz0_store(bytes(inner))


def entry_texture_map(entry_blob: bytes) -> dict:
    """{texture name: texture dict} for an icon entry ({} if none)."""
    return {t["name"]: t for t in entry_textures(entry_blob)}


# --- MSBT ------------------------------------------------------------------

def parse_msbt(data: bytes) -> dict:
    """{label: raw UTF-16 string bytes} for an MSBT (labels from LBL1, strings
    from TXT2). Strings with no label are keyed "#<index>"."""
    if data[:8] != b"MsgStdBn":
        raise ArchiveError("not an MSBT")
    endian = "<" if data[8:10] == b"\xff\xfe" else ">"
    sections = struct.unpack_from(endian + "H", data, 0x0E)[0]
    pos = 0x20
    labels, strings = {}, []
    for _ in range(sections):
        magic = data[pos:pos + 4]
        size = struct.unpack_from(endian + "I", data, pos + 4)[0]
        body = pos + 0x10
        if magic == b"LBL1":
            groups = struct.unpack_from(endian + "I", data, body)[0]
            for g in range(groups):
                count, off = struct.unpack_from(endian + "II", data, body + 4 + g * 8)
                p = body + off
                for _l in range(count):
                    name_len = data[p]
                    name = data[p + 1:p + 1 + name_len].decode("utf-8", "replace")
                    labels[struct.unpack_from(endian + "I", data, p + 1 + name_len)[0]] = name
                    p += 1 + name_len + 4
        elif magic == b"TXT2":
            n = struct.unpack_from(endian + "I", data, body)[0]
            offs = [struct.unpack_from(endian + "I", data, body + 4 + i * 4)[0] for i in range(n)] + [size]
            strings = [data[body + offs[i]:body + offs[i + 1]] for i in range(n)]
        pos = (body + size + 15) & ~15
    return {labels.get(i, f"#{i}"): s for i, s in enumerate(strings)}


def msbt_text(raw: bytes, endian: str = "<") -> str:
    """A string's readable text: UTF-16 with the terminator and the game's
    inline control codes (which start with 0x000E) dropped."""
    text = raw.decode("utf-16-le" if endian == "<" else "utf-16-be", "replace")
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\x0e" and i + 3 < len(text):
            # control code: 0x0E, group, type, then a byte-count payload
            payload = ord(text[i + 3]) if i + 3 < len(text) else 0
            i += 4 + payload // 2
            continue
        if ch != "\x00":
            out.append(ch)
        i += 1
    return "".join(out).strip()


def md5(blob: bytes) -> str:
    return hashlib.md5(blob).hexdigest()


def patch_msbt(data: bytes, new_strings: dict) -> bytes:
    """An MSBT with some labelled strings replaced by `new_strings` ({label:
    raw UTF-16 bytes, terminator and control codes included, exactly as another
    copy of the file stores them}). Only the TXT2 section is rebuilt (its
    offsets and size); every other section is copied untouched, and the
    section padding and total size are recomputed. A label that isn't in this
    file raises PatchError."""
    if data[:8] != b"MsgStdBn":
        raise ArchiveError("not an MSBT")
    endian = "<" if data[8:10] == b"\xff\xfe" else ">"
    if endian != "<":
        raise ArchiveError("only little-endian MSBTs are supported")
    sections = struct.unpack_from("<H", data, 0x0E)[0]
    labels = parse_msbt(data)
    missing = set(new_strings) - set(labels)
    if missing:
        raise PatchError(f"text entry {sorted(missing)[0]} isn't in your base file (built for an older game version)")

    out = bytearray(data[:0x20])
    pos = 0x20
    for _ in range(sections):
        magic = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 0x10
        payload = data[body:body + size]
        if magic == b"TXT2":
            n = struct.unpack_from("<I", payload, 0)[0]
            offs = [struct.unpack_from("<I", payload, 4 + 4 * i)[0] for i in range(n)] + [size]
            index_label = {}  # string index -> label, via parse order
            ordered = list(labels)
            strings = []
            for i in range(n):
                label = ordered[i]
                strings.append(new_strings.get(label, payload[offs[i]:offs[i + 1]]))
            table = 4 + 4 * n
            new_offs, cursor = [], table
            for st in strings:
                new_offs.append(cursor)
                cursor += len(st)
            payload = struct.pack("<I", n) + b"".join(struct.pack("<I", o) for o in new_offs) + b"".join(strings)
            size = len(payload)
        out += magic + struct.pack("<I", size) + data[pos + 8:pos + 0x10] + payload
        out += b"\xab" * ((-len(out)) % 16)
        pos = (body + struct.unpack_from("<I", data, pos + 4)[0] + 15) & ~15
    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)
