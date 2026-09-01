"""Mac Roman text helpers and published Resource Manager string formats.

STR#, STR , TEXT, MENU, and vers layouts are Inside Macintosh, not PID.
Harvest helpers scan unknown blobs; their hits are not a struct claim.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable

MAC_ROMAN = "mac_roman"


def decode_mac_roman(data: bytes) -> str:
    return data.decode(MAC_ROMAN, errors="replace")


def mac_roman_gutter(data: bytes) -> str:
    """One display column per byte, like hexdump ASCII but Mac Roman."""
    chars: list[str] = []
    for byte in data:
        if byte in (0x09, 0x0A, 0x0D):
            chars.append(".")
            continue
        glyph = bytes([byte]).decode(MAC_ROMAN, errors="replace")
        if glyph == "\ufffd" or not glyph.isprintable():
            chars.append(".")
        else:
            chars.append(glyph)
    return "".join(chars)


def hexdump_mac_roman(data: bytes, width: int = 16) -> str:
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"{offset:08x}  {hexpart:<{width * 3}} |{mac_roman_gutter(chunk)}|")
    return "\n".join(lines)


def parse_pstring_at(data: bytes, offset: int) -> tuple[str, int] | None:
    if offset >= len(data):
        return None
    length = data[offset]
    start = offset + 1
    end = start + length
    if end > len(data):
        return None
    return decode_mac_roman(data[start:end]), end


def parse_str(data: bytes) -> str | None:
    """'STR ' — Pascal string, optionally followed by unused bytes."""
    parsed = parse_pstring_at(data, 0)
    if parsed is None:
        return None
    return parsed[0]


def parse_str_list(data: bytes) -> list[str] | None:
    """'STR#' — big-endian count, then that many Pascal strings."""
    if len(data) < 2:
        return None
    count = struct.unpack(">H", data[:2])[0]
    if count > 2000:
        return None
    pos = 2
    out: list[str] = []
    for _ in range(count):
        parsed = parse_pstring_at(data, pos)
        if parsed is None:
            return None
        text, pos = parsed
        out.append(text)
    return out


def parse_vers(data: bytes) -> dict[str, object] | None:
    """'vers' — Inside Macintosh version record."""
    if len(data) < 8:
        return None
    short = parse_pstring_at(data, 6)
    if short is None:
        return None
    short_text, pos = short
    long = parse_pstring_at(data, pos)
    long_text = long[0] if long else ""
    return {
        "major": data[0],
        "minor": data[1],
        "dev_stage": data[2],
        "pre_release": data[3],
        "region": struct.unpack(">H", data[4:6])[0],
        "short": short_text,
        "long": long_text,
    }


def parse_menu(data: bytes) -> dict[str, object] | None:
    """'MENU' — id/title plus item Pascal strings until an empty name."""
    if len(data) < 15:
        return None
    menu_id = struct.unpack(">h", data[0:2])[0]
    title = parse_pstring_at(data, 14)
    if title is None:
        return None
    title_text, pos = title
    items: list[str] = []
    while pos < len(data):
        item = parse_pstring_at(data, pos)
        if item is None:
            break
        text, pos = item
        if text == "":
            break
        items.append(text)
        # icon, keyEquiv, marking, style
        pos += 4
        if pos > len(data):
            return None
    return {"id": menu_id, "title": title_text, "items": items}


def harvest_pascal_strings(data: bytes, min_len: int = 4) -> list[tuple[int, str]]:
    """Scan for Pascal strings whose payload is printable Mac Roman."""
    hits: list[tuple[int, str]] = []
    i = 0
    n = len(data)
    while i < n:
        length = data[i]
        if min_len <= length <= 255 and i + 1 + length <= n:
            payload = data[i + 1 : i + 1 + length]
            if _printable_mac_roman(payload):
                hits.append((i, decode_mac_roman(payload)))
                i += 1 + length
                continue
        i += 1
    return hits


def harvest_text_runs(data: bytes, min_len: int = 6) -> list[tuple[int, str]]:
    """Scan for runs of printable Mac Roman (not a format claim)."""
    hits: list[tuple[int, str]] = []
    start: int | None = None
    for i, byte in enumerate(data):
        ok = _printable_byte(byte)
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= min_len:
                hits.append((start, decode_mac_roman(data[start:i])))
            start = None
    if start is not None and len(data) - start >= min_len:
        hits.append((start, decode_mac_roman(data[start:])))
    return hits


def _printable_byte(byte: int) -> bool:
    if byte in (0x09, 0x0D, 0x0A, 0x20):
        return True
    if 0x20 <= byte <= 0x7E:
        return True
    # Mac Roman high bytes that are real letters/punctuation, not controls.
    return byte >= 0x80 and byte not in {0xCA}


def _printable_mac_roman(data: bytes) -> bool:
    if not data:
        return False
    letters = 0
    for byte in data:
        if byte == 0:
            return False
        if not _printable_byte(byte):
            return False
        glyph = bytes([byte]).decode(MAC_ROMAN, errors="replace")
        if glyph.isalpha():
            letters += 1
    return letters >= max(1, len(data) // 4)


def format_string_list(strings: Iterable[str]) -> str:
    lines = []
    for i, text in enumerate(strings):
        shown = text.replace("\r", "\\r").replace("\n", "\\n")
        lines.append(f"  [{i:03d}] {shown}")
    return "\n".join(lines)
