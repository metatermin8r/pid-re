"""Published Mac container formats, not PID structures.

AppleDouble (RFC 1740) and MacBinary are how resource forks survive on
Windows after `unar`. This module peels those wrappers so `rsrcfork` sees
a raw Resource Manager map.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

APPLEDOUBLE_MAGIC = 0x00051607
APPLEDOUBLE_VERSION_2 = 0x00020000
APPLEDOUBLE_ENTRY_RESOURCE_FORK = 2

# Classic Resource Manager header is 16 bytes of big-endian offsets/lengths.
RESOURCE_HEADER_SIZE = 16


@dataclass(frozen=True)
class ResourcePayload:
    """Raw Resource Manager bytes plus how they were found."""

    data: bytes
    source: str  # appledouble | macbinary | raw-rsrc | data-fork


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack(">H", data[offset : offset + 2])[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset : offset + 4])[0]


def looks_like_resource_map(data: bytes) -> bool:
    """Sanity-check a Resource Manager header. No PID-specific fields."""
    if len(data) < RESOURCE_HEADER_SIZE:
        return False
    data_off = _u32(data, 0)
    map_off = _u32(data, 4)
    data_len = _u32(data, 8)
    map_len = _u32(data, 12)
    if data_off == 0 and map_off == 0 and data_len == 0 and map_len == 0:
        return False
    if map_off + map_len > len(data):
        return False
    if data_off + data_len > len(data):
        return False
    if map_len < 30:
        return False
    return True


def extract_appledouble_resource_fork(data: bytes) -> bytes | None:
    if len(data) < 26 or _u32(data, 0) != APPLEDOUBLE_MAGIC:
        return None
    # Version is usually 0x00020000; still walk entries if the magic matches.
    nentries = _u16(data, 24)
    table = 26
    needed = table + nentries * 12
    if len(data) < needed:
        return None
    for i in range(nentries):
        base = table + i * 12
        entry_id = _u32(data, base)
        offset = _u32(data, base + 4)
        length = _u32(data, base + 8)
        if entry_id != APPLEDOUBLE_ENTRY_RESOURCE_FORK:
            continue
        if offset + length > len(data):
            return None
        return data[offset : offset + length]
    return None


def extract_macbinary_resource_fork(data: bytes) -> bytes | None:
    """MacBinary I/II/III. Returns None if the header does not check out."""
    if len(data) < 128:
        return None
    if data[0] != 0:
        return None
    name_len = data[1]
    if name_len == 0 or name_len > 63:
        return None
    data_len = _u32(data, 83)
    rsrc_len = _u32(data, 87)
    if rsrc_len == 0:
        return None
    # Data fork is padded to a 128-byte multiple after the 128-byte header.
    data_padded = (data_len + 127) & ~127
    start = 128 + data_padded
    end = start + rsrc_len
    if end > len(data):
        return None
    payload = data[start:end]
    if not looks_like_resource_map(payload):
        return None
    return payload


def load_resource_payload(path: Path) -> ResourcePayload | None:
    """Return Resource Manager bytes if this file contains them."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return None

    apple = extract_appledouble_resource_fork(raw)
    if apple is not None:
        return ResourcePayload(apple, "appledouble")

    macbin = extract_macbinary_resource_fork(raw)
    if macbin is not None:
        return ResourcePayload(macbin, "macbinary")

    if path.name.startswith("._") or path.suffix.lower() in {".rsrc", ".dfont"}:
        if looks_like_resource_map(raw):
            return ResourcePayload(raw, "raw-rsrc")

    if looks_like_resource_map(raw):
        return ResourcePayload(raw, "data-fork")

    return None
