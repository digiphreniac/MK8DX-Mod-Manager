#!/usr/bin/env python3
"""Builds a working .bntx course-select icon file from a plain RGBA image,
for courses whose downloaded mod doesn't bundle its own (see the Help page
and bntx_decode.py's docstring for the read side of this).

Rather than constructing a brand-new .bntx container's string table/name-
lookup tree/relocation table from scratch, this loads a real, already-
working CoursePict.bntx (any of the user's own downloaded mods that has
one - see Api.generate_course_icon()) via the vendored _bntx_structs.py,
mutates only the handful of fields that actually need to change (the
texture's own pixel data/dimensions/format, and its name strings), and
re-saves it with that same vendored, community-proven save() logic. That
keeps every other structural detail (the name-lookup tree, relocation
table, block headers) exactly as a real, working file already has them,
rather than risking a subtly-wrong hand-built version of any of that - this
produces a file a real Switch console has to accept, which isn't something
that can be verified by testing here.

The generated texture uses a plain uncompressed RGBA8 format rather than
matching the source file's BC7 compression - deliberately: it avoids needing
a BC7 *encoder* (a much harder, lossy problem than the format's decoder,
which is genuinely one of the fiddlier block formats to get exactly right),
and RGBA8 is a standard, universally-supported baseline GPU texture format -
the only real cost is a larger file (roughly 300KB instead of 80KB for one
course icon), which is immaterial for a single UI image.
"""

import struct

import _bntx_structs as bs

_RGBA8_UNORM = 0x0b01
_RGBA8_SRGB = 0x0b06


class UnsupportedTemplateError(Exception):
    """Raised if the chosen template .bntx isn't the plain single-texture
    shape this module knows how to safely mutate."""


def _div_round_up(n, d):
    return (n + d - 1) // d


def _round_up(x, y):
    return ((x - 1) | (y - 1)) + 1


def _pow2_round_up(x):
    x -= 1
    x |= x >> 1
    x |= x >> 2
    x |= x >> 4
    x |= x >> 8
    x |= x >> 16
    return x + 1


def _get_block_height(height_in_blocks):
    block_height = _pow2_round_up(max(1, height_in_blocks) // 8)
    return min(block_height, 16)


def _block_linear_address(x, y, width_in_blocks, bytes_per_block, block_height):
    """Same Tegra X1 block-linear addressing as bntx_decode.py's own copy -
    duplicated rather than imported so each module stays independently
    readable; this is the write-direction (swizzle) use of the identical
    formula deswizzle() uses in reverse."""
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


def _swizzle(width_px, height_px, block_px, bytes_per_block, block_height_log2, linear_data):
    """Inverse of bntx_decode._deswizzle(): takes plain top-to-bottom,
    left-to-right block data and lays it out in the block-linear order the
    Switch GPU expects."""
    block_height = 1 << block_height_log2
    w = _div_round_up(width_px, block_px)
    h = _div_round_up(height_px, block_px)
    pitch = _round_up(w * bytes_per_block, 64)
    surf_size = pitch * _round_up(h, block_height * 8)
    out = bytearray(surf_size)
    for y in range(h):
        for x in range(w):
            dst = _block_linear_address(x, y, w, bytes_per_block, block_height)
            src = (y * w + x) * bytes_per_block
            if dst + bytes_per_block <= surf_size and src + bytes_per_block <= len(linear_data):
                out[dst:dst + bytes_per_block] = linear_data[src:src + bytes_per_block]
    return bytes(out)


class _File:
    """Trimmed port of BNTX-Editor's File class (load/save only - no GUI,
    no multi-format extract/replace) - see _bntx_structs.py's module
    docstring for attribution."""

    def load(self, data, pos=0):
        self.header = bs.BNTXHeader()
        rc = self.header.load(data, pos)
        if rc:
            raise UnsupportedTemplateError(f"bad header (code {rc})")
        pos += 32

        self.texContainer = bs.TexContainer(self.header.endianness)
        rc = self.texContainer.load(data, pos)
        if rc:
            raise UnsupportedTemplateError(f"bad texture container (code {rc})")
        self.target = self.texContainer.target.decode("utf-8")

        self.strTblHeader = bs.BlockHeader(self.header.endianness)
        self.strTblHeader.load(data, self.header.firstBlkAddr)
        if self.strTblHeader.isValid(b'_STR'):
            raise UnsupportedTemplateError("bad string table header")

        self.strTbl = bs.StringTable(self.header.endianness)
        self.strTbl.load(data, self.header.firstBlkAddr + 16)
        self.header.setNameIndex(self.strTbl)
        self.name = self.strTbl[self.header.nameIdx]

        pos = self.texContainer.dictAddr
        self.texNameDict = self.strTbl.TexNameDict(self.header.endianness, self.strTbl)
        self.texNameDict.load(data, pos)

        infoPtrsAddr = self.texContainer.infoPtrsAddr
        self.textures = []
        for i in range(self.texContainer.count):
            pos = bs.readInt64(data, infoPtrsAddr + 8 * i, self.header.endianness)
            if data[pos:pos + 4] != b'BRTI':
                raise UnsupportedTemplateError("malformed texture info block")
            texture = bs.TextureInfo(self.header.endianness)
            texture.load(data, pos + 16)
            texture.setNameIndex(self.strTbl)
            texture.name = self.strTbl[texture.nameIdx]
            self.textures.append(texture)

        pos = self.header.relocAddr
        self.relocTblHeader = bs.BlockHeader(self.header.endianness)
        self.relocTblHeader.load(data, pos)
        if self.relocTblHeader.isValid(b'_RLT'):
            raise UnsupportedTemplateError("bad relocation table header")

        self.relocTbl = bs.RelocTBL(self.header.endianness)
        self.relocTbl.load(data, pos + 16, self.relocTblHeader.blockSize)

    def save(self):
        self.relocTblHeader.blockSize = 2
        self.relocTbl.blocks = [self.relocTbl.Block(self.header.endianness), self.relocTbl.Block(self.header.endianness)]
        self.relocTbl.entries = []
        self.relocTbl.blocks[0].pos = 0
        self.relocTbl.blocks[0].relocEntryIdx = 0

        self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
        self.relocTbl.entries[0].pos = 0x28
        self.relocTbl.entries[0].structs = [[0x28], [0x38]]
        self.relocTbl.entries[0].paddingCount = 1

        self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
        self.relocTbl.entries[1].pos = 0x40
        self.relocTbl.entries[1].structs = [[0x40]]
        self.relocTbl.entries[1].paddingCount = 0

        pos = 0x198
        count = self.texContainer.count
        while count > 0:
            self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
            self.relocTbl.entries[-1].pos = pos
            self.relocTbl.entries[-1].structs = [[pos + i * 8 for i in range(min(count, 0xFF))]]
            self.relocTbl.entries[-1].paddingCount = 0
            pos += min(count, 0xFF) * 8
            count -= 0xFF

        self.header.version = 0x40000
        self.header.alignmentShift = 0xC if self.texContainer.target == b'NX  ' else 3
        self.header.targetAddrSize = 0x40
        self.header.flag = 0

        self.strTbl.pos = 0x198 + 8 * self.texContainer.count + 16
        strTbl = self.strTbl.save()

        self.header.fileNameAddr = self.strTbl.getPosFromIndex(self.header.nameIdx) + 2
        self.header.firstBlkAddr = self.strTbl.pos - 16

        self.texNameDict.pos = self.strTbl.pos + len(strTbl)
        texNameDictAlignBytes = b'\0' * (_round_up(self.texNameDict.pos, 8) - self.texNameDict.pos)
        self.texNameDict.pos += len(texNameDictAlignBytes)
        texNameDict = b''.join([texNameDictAlignBytes, self.texNameDict.save()])

        pos = self.texNameDict.pos + 16
        count = self.texNameDict.count + 1
        while count > 0:
            self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
            self.relocTbl.entries[-1].pos = pos
            self.relocTbl.entries[-1].structs = [[pos + i * 8 for i in range(min(count, 0xFF))]]
            self.relocTbl.entries[-1].paddingCount = 0
            pos += min(count, 0xFF) * 8
            count -= 0xFF

        self.texContainer.dictAddr = self.texNameDict.pos
        self.texContainer.infoPtrsAddr = 0x198
        self.texContainer.memPoolAddr = 0x58
        self.texContainer.currMemPoolAddr = 0
        self.texContainer.baseMemPoolAddr = 0

        self.strTblHeader.blockSize = len(strTbl) + len(texNameDict) + 16
        self.strTblHeader.nextBlkAddr = self.strTblHeader.blockSize
        strTblHeader = self.strTblHeader.save()

        infoBlksPos = self.strTbl.pos - 16 + self.strTblHeader.nextBlkAddr
        infoBlks = bytearray()

        dataBlkHeader = bs.BlockHeader(self.header.endianness)
        dataBlkHeader.magic = b'BRTD'
        dataBlkHeader.nextBlkAddr = 0

        dataBlkPos = infoBlksPos + 16
        for i in range(self.texContainer.count):
            dataBlkPos += 0x2A0 + 8 * self.textures[i].numMips

        self.relocTbl.blocks[0].size_ = dataBlkPos - 16

        dataAlignment = 1 << self.header.alignmentShift

        dataBlkAlignBytes = b'\0' * (_round_up(dataBlkPos, dataAlignment) - dataBlkPos)
        dataBlkPos += len(dataBlkAlignBytes)
        self.texContainer.dataBlkAddr = dataBlkPos - 16
        dataBlk_ = bytearray()

        for i in range(self.texContainer.count):
            texture = self.textures[i]
            texture.pos = infoBlksPos + len(infoBlks) + 16
            texture.nameAddr = self.strTbl.getPosFromIndex(texture.nameIdx)
            texture.parentAddr = 0x20
            texture.ptrsAddr = texture.pos + 0x290
            texture.userDataAddr = 0
            texture.texPtr = texture.pos + 0x90
            texture.texViewPtr = texture.pos + 0x190
            texture.descSlotDataAddr = 0
            texture.userDictAddr = 0

            self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
            self.relocTbl.entries[-1].pos = texture.pos + 0x50
            self.relocTbl.entries[-1].structs = [[texture.pos + 0x50, texture.pos + 0x58, texture.pos + 0x60]]
            self.relocTbl.entries[-1].paddingCount = 0

            self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
            self.relocTbl.entries[-1].pos = texture.pos + 0x70
            self.relocTbl.entries[-1].structs = [[texture.pos + 0x70, texture.pos + 0x78]]
            self.relocTbl.entries[-1].paddingCount = 0

            infoBlkHeader = bs.BlockHeader(self.header.endianness)
            infoBlkHeader.magic = b'BRTI'
            infoBlkHeader.blockSize = 0x2A0 + 8 * texture.numMips

            if i == self.texContainer.count - 1:
                infoBlkHeader.blockSize += len(dataBlkAlignBytes)

            infoBlkHeader.nextBlkAddr = infoBlkHeader.blockSize

            infoBlks += infoBlkHeader.save()
            infoBlks += texture.save()
            infoBlks += b'\0\0' * 0x100

            dataPos = dataBlkPos + len(dataBlk_)
            dataAlignBytes = b'\0' * (_round_up(dataPos, texture.alignment) - dataPos)
            dataPos += len(dataAlignBytes)
            dataBlk_ += dataAlignBytes

            for offset in texture.mipOffsets:
                infoBlks += bs.packInt64(dataPos + offset, self.header.endianness)

            dataBlk_ += texture.data

        self.header.relocAddr = dataBlkPos + len(dataBlk_)
        relocTblAlignBytes = b'\0' * (_round_up(self.header.relocAddr, dataAlignment) - self.header.relocAddr)
        self.header.relocAddr += len(relocTblAlignBytes)
        dataBlk_ += relocTblAlignBytes

        dataBlkHeader.blockSize = len(dataBlk_) + 16
        dataBlk = b''.join([dataBlkAlignBytes, dataBlkHeader.save(), dataBlk_])

        self.relocTblHeader.magic = b'_RLT'
        self.relocTblHeader.nextBlkAddr = self.header.relocAddr
        self.relocTbl.blocks[0].relocEntryCount = len(self.relocTbl.entries)

        self.relocTbl.blocks[1].pos = self.texContainer.dataBlkAddr
        self.relocTbl.blocks[1].size_ = dataBlkHeader.blockSize
        self.relocTbl.blocks[1].relocEntryIdx = self.relocTbl.blocks[0].relocEntryCount

        self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
        self.relocTbl.entries[-1].pos = 0x30
        self.relocTbl.entries[-1].structs = [[0x30]]
        self.relocTbl.entries[-1].paddingCount = 0

        for texture in self.textures:
            pos = texture.pos + 0x290
            count = texture.numMips
            while count > 0:
                self.relocTbl.entries.append(self.relocTbl.Entry(self.header.endianness))
                self.relocTbl.entries[-1].pos = pos
                self.relocTbl.entries[-1].structs = [[pos + i * 8 for i in range(min(count, 0xFF))]]
                self.relocTbl.entries[-1].paddingCount = 0
                pos += min(count, 0xFF) * 8
                count -= 0xFF

        self.relocTbl.blocks[1].relocEntryCount = len(self.relocTbl.entries) - self.relocTbl.blocks[1].relocEntryIdx

        relocTbl = b''.join([self.relocTblHeader.save(), self.relocTbl.save()])

        fileData = bytearray(self.texContainer.save())
        fileData += b'\0' * 0x140

        for i in range(self.texContainer.count):
            fileData += bs.packInt64(self.textures[i].pos - 16, self.header.endianness)

        fileData += strTblHeader
        fileData += strTbl
        fileData += texNameDict
        fileData += infoBlks
        fileData += dataBlk
        fileData += relocTbl

        self.header.fileSize = len(fileData) + 32

        return b''.join([self.header.save(), fileData])


def build_course_pict_bntx(template_path, internal_id, width, height, rgba_pixels, srgb=True):
    """Loads a real, working CoursePict.bntx (`template_path` - any of the
    user's own already-decoded-successfully course icons) and returns new
    file bytes for a texture named f"ym_CoursePict_{internal_id}_00"
    containing `rgba_pixels` (raw, top-to-bottom left-to-right RGBA8 bytes,
    len == width*height*4) at `width`x`height`. Only the texture's own data/
    dimensions/format and its name strings are changed - everything else
    (the name-lookup tree, relocation table, block structure) is kept as
    the template already has it. Raises UnsupportedTemplateError if the
    template isn't a plain single-texture .bntx."""
    f = _File()
    f.load(template_path.read_bytes())

    if f.texContainer.count != 1 or len(f.textures) != 1:
        raise UnsupportedTemplateError("template must contain exactly one texture")

    texture = f.textures[0]
    if texture.dim != 2 or texture.arrayLength != 1:
        raise UnsupportedTemplateError("template texture must be a plain single 2D image")

    bytes_per_pixel = 4  # RGBA8
    block_height = _get_block_height(height)
    block_height_log2 = len(bin(block_height)[2:]) - 1

    swizzled = _swizzle(width, height, 1, bytes_per_pixel, block_height_log2, rgba_pixels)

    # Every real CoursePict checked uses this exact naming convention for
    # both its on-disk filename and its internal texture name (identical,
    # including the trailing "^u" marker) - matched here so a generated
    # icon is indistinguishable in shape from a mod-provided one.
    texture_name = f"ym_CoursePict_{internal_id}_00^u"

    # Rename both the file's own top-level name and this texture's own name
    # to match - real CoursePict files use the same convention for both.
    file_name_entry = f.strTbl.entries[f.header.nameIdx]
    file_name_entry.string = texture_name
    file_name_entry.size_ = len(texture_name.encode("utf-8"))

    if texture.nameIdx != f.header.nameIdx:
        tex_name_entry = f.strTbl.entries[texture.nameIdx]
        tex_name_entry.string = texture_name
        tex_name_entry.size_ = len(texture_name.encode("utf-8"))

    texture.name = texture_name
    texture.dim = 2
    texture.tileMode = 0  # block-linear, same as every real CoursePict checked
    texture.numMips = 1
    texture.mipOffsets = [0]
    texture.width = width
    texture.height = height
    texture.depth = 1
    texture.arrayLength = 1
    texture.format_ = _RGBA8_SRGB if srgb else _RGBA8_UNORM
    texture.readTexLayout = 1
    texture.sparseBinding = 0
    texture.sparseResidency = 0
    texture.blockHeightLog2 = block_height_log2
    texture.imageSize = len(swizzled)
    texture.alignment = 512
    texture.imgDim = 1
    texture.data = swizzled
    # compSel (component/channel order) is format-independent - the
    # template's existing identity R/G/B/A mapping is exactly what a plain
    # RGBA8 image needs too, so it's left untouched.

    return f.save()
