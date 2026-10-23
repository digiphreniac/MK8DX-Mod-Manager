#!/usr/bin/env python3
"""Decodes a small, specific subset of Nintendo Switch .bntx texture files -
just enough to preview MK8DX's course-select "CoursePict" thumbnails (and
any similarly-shaped single-mip, block-linear-tiled BC7 texture) as PNG. Not
a general BNTX library - every UI/cmn/menu/ym_CoursePict_*.bntx checked
against this app's real downloaded mods uses this exact shape (a single
BC7-compressed mip, GPU block-linear tiling, no mip chain), and that's all
this is built to handle.

Deswizzling (undoing the Tegra X1's GPU-friendly block-linear memory layout)
and BNTX's own header layout are both published, documented formats - see
https://github.com/aboood40091/BNTX-Editor for a fuller reference
implementation (GPL) covering many more formats/edge cases than this file
needs to. BC7 block *decompression* itself is delegated to Pillow's own DDS
reader (Pillow 9.2+) rather than reimplemented here - BC7 is one of the
fiddlier block formats to get exactly right by hand, and Pillow already
ships a tested decoder for it; this module's own job is just getting the
raw, correctly-ordered BC7 bytes into a shape Pillow recognizes.
"""

import functools
import io
import struct

import diag

try:
    from PIL import Image
except ImportError as _e:
    Image = None
    diag.log("error", f"Pillow couldn't be loaded ({_e}): pictures from the game's files can't be decoded, so they will be blank")


class UnsupportedBNTXError(Exception):
    """Raised for a .bntx this module doesn't know how to decode - a
    different pixel format, tiling mode, or multi-mip/array texture than
    the single-BC7-mip CoursePict shape this is built for. Callers should
    treat this as "no preview available", not a hard failure."""


def _div_round_up(n, d):
    return (n + d - 1) // d


def _round_up(x, y):
    return ((x - 1) | (y - 1)) + 1


def _block_linear_address(x, y, width_in_blocks, bytes_per_block, block_height):
    """Tegra X1 GPU block-linear texture addressing - the formula the
    console's own texture unit uses to find a given block in memory, given
    the texture's width (in blocks) and its "block height" (how many GOBs
    tall each cache-friendly tile is). Documented in the Tegra X1 TRM."""
    width_in_gobs = _div_round_up(width_in_blocks * bytes_per_block, 64)
    gob_address = (
        (y // (8 * block_height)) * 512 * block_height * width_in_gobs
        + (x * bytes_per_block // 64) * 512 * block_height
        + (y % (8 * block_height) // 8) * 512
    )
    x_bytes = x * bytes_per_block
    return (
        gob_address
        + ((x_bytes % 64) // 32) * 256
        + ((y % 8) // 2) * 64
        + ((x_bytes % 32) // 16) * 32
        + (y % 2) * 16
        + (x_bytes % 16)
    )


@functools.lru_cache(maxsize=32)
def _swizzle_table(width_px, height_px, block_px, bytes_per_block, block_height_log2):
    """(byte offset in the swizzled data of each block, in plain left-to-right, top-to-bottom order; the size of the
    swizzled surface). It depends only on the texture's shape, and every icon in an archive has the same one - so it is
    worked out once, not once per picture."""
    block_height = 1 << block_height_log2
    w = _div_round_up(width_px, block_px)
    h = _div_round_up(height_px, block_px)
    pitch = _round_up(w * bytes_per_block, 64)
    surf_size = pitch * _round_up(h, block_height * 8)
    offsets = tuple(_block_linear_address(x, y, w, bytes_per_block, block_height) for y in range(h) for x in range(w))
    return offsets, surf_size


def _deswizzle(width_px, height_px, block_px, bytes_per_block, block_height_log2, data):
    """Undoes block-linear tiling for a single-mip texture, returning its
    blocks in plain left-to-right, top-to-bottom order. A block that would
    be read from outside the data comes out as zeros."""
    offsets, surf_size = _swizzle_table(width_px, height_px, block_px, bytes_per_block, block_height_log2)
    limit = min(surf_size, len(data))
    view = memoryview(data)
    n = bytes_per_block
    zero = bytes(n)
    return b"".join([view[a:a + n] if a + n <= limit else zero for a in offsets])


def _read_int64(data, pos, endian):
    return struct.unpack(endian + "q", data[pos:pos + 8])[0]


def _parse_bntx(data):
    """Returns (format_, width, height, tile_mode, block_height_log2,
    tex_data) for the first texture in a .bntx file's bytes."""
    if data[:4] != b"BNTX":
        raise UnsupportedBNTXError("not a .bntx file")

    bom = data[12:14]
    if bom == b"\xff\xfe":
        endian = "<"
    elif bom == b"\xfe\xff":
        endian = ">"
    else:
        raise UnsupportedBNTXError("unrecognized byte-order mark")

    target, count, info_ptrs_addr, *_rest = struct.unpack_from(endian + "4sI5qI4x", data, 32)
    if target not in (b"NX  ", b"Gen "):
        raise UnsupportedBNTXError(f"unrecognized target {target!r}")
    if count < 1:
        raise UnsupportedBNTXError("no textures in file")

    tex_pos = _read_int64(data, info_ptrs_addr, endian)
    if data[tex_pos:tex_pos + 4] != b"BRTI":
        raise UnsupportedBNTXError("malformed texture info block")

    ti_pos = tex_pos + 16
    ti_fmt = endian + "2B4H2x2I3i3I20x3IB3x8q"
    (_flags, dim, tile_mode, _swizzle, _num_mips, _num_samples, format_, _access_flags,
     width, height, _depth, array_length, texture_layout, _texture_layout2, image_size,
     _alignment, _comp_sel, _img_dim, _name_addr, _parent_addr, ptrs_addr, *_rest2
     ) = struct.unpack_from(ti_fmt, data, ti_pos)

    if dim != 2 or array_length > 1:
        raise UnsupportedBNTXError("not a plain single 2D texture")

    block_height_log2 = texture_layout & 7
    first_mip_offset = _read_int64(data, ptrs_addr, endian)
    tex_data = data[first_mip_offset:first_mip_offset + image_size]

    return format_, width, height, tile_mode, block_height_log2, tex_data


# format_ >> 8 == 0x20 is BC7 in BNTX's format encoding - what every real
# mod-provided CoursePict checked against real downloads uses. 0x0b is
# RGBA8, used by icons this app generates itself (bntx_encode.py) rather
# than reimplementing a BC7 *encoder* - see that module's docstring. Both
# formats' low byte distinguishes UNORM (0x01) from the sRGB variant
# (0x06); BC7's maps to these DXGI format constants in the DDS container
# below, RGBA8 needs no such wrapping since it isn't block-compressed.
_BC7_UNORM = 98
_BC7_UNORM_SRGB = 99


def decode_to_png(path, crop_box=None):
    """Decodes a .bntx file's first texture to PNG bytes. Raises
    UnsupportedBNTXError for anything outside the single-mip BC7 or RGBA8
    2D texture shapes this is built for (see module docstring).

    `crop_box`, if given, is a (left, top, right, bottom) pixel box applied
    before encoding - used by callers that want just the visible-content
    window of a CoursePict rather than its full padded canvas (see
    mod_manager.py's _COURSE_PICT_CONTENT_* constants). Silently ignored if
    it doesn't fit the actual decoded image, since not every .bntx this
    gets pointed at is guaranteed to match the CoursePict convention it was
    measured from."""
    if Image is None:
        raise UnsupportedBNTXError("Pillow is not installed")

    data = path.read_bytes()
    format_, width, height, tile_mode, block_height_log2, tex_data = _parse_bntx(data)

    if tile_mode != 0:
        raise UnsupportedBNTXError(f"unsupported tile mode {tile_mode} (only block-linear is)")
    srgb = (format_ & 0xff) == 0x06

    if (format_ >> 8) == 0x20:
        bytes_per_block = 16  # BC7 is always 16 bytes per 4x4 block
        raw = _deswizzle(width, height, 4, bytes_per_block, block_height_log2, tex_data)
        dds_bytes = _wrap_bc7_dds(width, height, srgb, raw)
        img = Image.open(io.BytesIO(dds_bytes))
        img = img.convert("RGBA")
    elif (format_ >> 8) == 0x0b:
        raw = _deswizzle(width, height, 1, 4, block_height_log2, tex_data)
        img = Image.frombytes("RGBA", (width, height), raw)
    else:
        raise UnsupportedBNTXError(f"unsupported texture format 0x{format_:x} (only BC7/RGBA8 are)")

    if crop_box is not None:
        left, top, right, bottom = crop_box
        if 0 <= left < right <= img.width and 0 <= top < bottom <= img.height:
            img = img.crop(crop_box)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _wrap_bc7_dds(width, height, srgb, block_data):
    """Wraps already-deswizzled BC7 block data in a minimal DX10 DDS
    container, purely so Pillow's own (tested) DDS/BC7 reader can
    decompress it - see module docstring for why decompression itself
    isn't reimplemented here."""
    header = bytearray(124)
    struct.pack_into("<I", header, 0, 124)
    flags_ = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000  # CAPS | HEIGHT | WIDTH | PIXELFORMAT | LINEARSIZE
    struct.pack_into("<I", header, 4, flags_)
    struct.pack_into("<I", header, 8, height)
    struct.pack_into("<I", header, 12, width)
    linear_size = _div_round_up(width, 4) * _div_round_up(height, 4) * 16
    struct.pack_into("<I", header, 16, linear_size)
    struct.pack_into("<I", header, 24, 1)  # mipmap count

    pf_off = 72  # DDS_PIXELFORMAT sub-struct, 32 bytes
    struct.pack_into("<I", header, pf_off, 32)
    struct.pack_into("<I", header, pf_off + 4, 0x4)  # DDPF_FOURCC
    struct.pack_into("<4s", header, pf_off + 8, b"DX10")
    struct.pack_into("<I", header, 104, 0x1000)  # DDSCAPS_TEXTURE

    dxgi_format = _BC7_UNORM_SRGB if srgb else _BC7_UNORM
    dx10_header = struct.pack("<5I", dxgi_format, 3, 0, 1, 0)  # resourceDimension = TEXTURE2D

    return b"DDS " + bytes(header) + dx10_header + block_data
