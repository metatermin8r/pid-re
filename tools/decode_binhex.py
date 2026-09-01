# -*- coding: utf-8 -*-
"""Decode a BinHex 4.0 payload from SuperdudeSavedGame.txt."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

# BinHex 4.0 6-bit alphabet (RFC 1741). 64 glyphs, no 7/O/W.
HQX_ALPHABET = b'!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr'
HQX_MAP = {ch: i for i, ch in enumerate(HQX_ALPHABET)}


def a2b_hqx(body: str) -> bytes:
    bits = 0
    nbits = 0
    out = bytearray()
    skipped = 0
    for ch in body.encode("latin-1", errors="replace"):
        if ch in b" \t\r\n":
            continue
        if ch not in HQX_MAP:
            skipped += 1
            continue
        bits = (bits << 6) | HQX_MAP[ch]
        nbits += 6
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
    if skipped:
        print(f"a2b_hqx skipped {skipped} non-alphabet bytes")
    return bytes(out)


def rledecode_hqx(data: bytes) -> bytes:
    """BinHex RLE: 0x90 N repeats the previous byte N times total (N==0 => literal 0x90)."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        i += 1
        if c != 0x90:
            out.append(c)
            continue
        if i >= n:
            raise ValueError("truncated RLE marker")
        count = data[i]
        i += 1
        if count == 0:
            out.append(0x90)
        else:
            if not out:
                raise ValueError("RLE with no previous byte")
            # Classic: previous already emitted once; emit count-1 more so total=count.
            out.extend([out[-1]] * (count - 1))
    return bytes(out)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/cd/pathwaysintodarkness/docs_web/SuperdudeSavedGame.txt"
OUT_DIR = ROOT / "reference/saves"
REPORT = ROOT / "reference/docs/round8_save.txt"


def extract_hqx_body(text: str) -> str:
    marker = "(This file must be converted with BinHex 4.0)"
    idx = text.find(marker)
    region = text[idx + len(marker) :] if idx >= 0 else text
    start = region.find(":")
    if start < 0:
        raise ValueError("no BinHex start colon")
    end = region.rfind(":")
    if end <= start:
        raise ValueError("no BinHex end colon")
    body = region[start + 1 : end]
    return "".join(ch for ch in body if not ch.isspace())


def decode_hqx(body: str) -> bytes:
    raw = a2b_hqx(body)
    cand_a = rledecode_hqx(raw)
    try:
        cand_b = rledecode_hqx_extra(raw)
    except ValueError:
        cand_b = b""
    def score(blob: bytes) -> int:
        if len(blob) < 22:
            return -1
        nlen = blob[0]
        if nlen > 63 or 1 + nlen + 21 > len(blob):
            return -1
        pos = 1 + nlen + 1 + 4 + 4 + 2
        dlen = struct.unpack_from(">I", blob, pos)[0]
        rlen = struct.unpack_from(">I", blob, pos + 4)[0]
        need = 1 + nlen + 21 + dlen + 2 + rlen + 2
        return 1000 - abs(len(blob) - need) if dlen < 2_000_000 and rlen < 2_000_000 else -1

    sa, sb = score(cand_a), score(cand_b)
    return cand_a if sa >= sb else cand_b


def rledecode_hqx_extra(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        i += 1
        if c != 0x90:
            out.append(c)
            continue
        if i >= n:
            raise ValueError("truncated RLE marker")
        count = data[i]
        i += 1
        if count == 0:
            out.append(0x90)
        else:
            if not out:
                raise ValueError("RLE with no previous byte")
            out.extend([out[-1]] * count)
    return bytes(out)


def parse_binhex_file(decoded: bytes) -> dict:
    if not decoded:
        raise ValueError("empty decode")
    nlen = decoded[0]
    pos = 1
    name = decoded[pos : pos + nlen]
    pos += nlen
    version = decoded[pos]
    pos += 1
    ftype = decoded[pos : pos + 4]
    pos += 4
    creator = decoded[pos : pos + 4]
    pos += 4
    flags = struct.unpack_from(">H", decoded, pos)[0]
    pos += 2
    dlen = struct.unpack_from(">I", decoded, pos)[0]
    pos += 4
    rlen = struct.unpack_from(">I", decoded, pos)[0]
    pos += 4
    hcrc = struct.unpack_from(">H", decoded, pos)[0]
    pos += 2
    data = decoded[pos : pos + dlen]
    pos += dlen
    dcrc = struct.unpack_from(">H", decoded, pos)[0] if pos + 2 <= len(decoded) else None
    pos += 2
    rsrc = decoded[pos : pos + rlen]
    pos += rlen
    rcrc = struct.unpack_from(">H", decoded, pos)[0] if pos + 2 <= len(decoded) else None
    return {
        "name": name,
        "name_mac": name.decode("mac_roman", errors="replace"),
        "version": version,
        "type": ftype,
        "creator": creator,
        "flags": flags,
        "data_len_hdr": dlen,
        "rsrc_len_hdr": rlen,
        "header_crc": hcrc,
        "data": data,
        "data_crc": dcrc,
        "rsrc": rsrc,
        "rsrc_crc": rcrc,
        "decoded_total": len(decoded),
        "consumed": pos,
    }


def hexdump(data: bytes, n: int = 512) -> str:
    lines = []
    chunk = data[:n]
    for i in range(0, len(chunk), 16):
        row = chunk[i : i + 16]
        hx = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{i:08x}  {hx:<47s}  {asc}")
    return "\n".join(lines)


def main() -> None:
    raw_text = SRC.read_bytes().decode("mac_roman", errors="replace")
    body = extract_hqx_body(raw_text)
    decoded = decode_hqx(body)
    info = parse_binhex_file(decoded)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data_path = OUT_DIR / "superdude.bin"
    data_path.write_bytes(info["data"])
    rsrc_path = None
    if info["rsrc"]:
        rsrc_path = OUT_DIR / "superdude.bin.rsrc"
        rsrc_path.write_bytes(info["rsrc"])

    lines = [
        f"hqx_body_chars={len(body)}",
        f"decoded_bytes={info['decoded_total']}",
        f"filename={info['name_mac']!r} raw={info['name'].hex()}",
        f"version={info['version']}",
        f"type={info['type']!r} {info['type'].decode('ascii', errors='replace')}",
        f"creator={info['creator']!r} {info['creator'].decode('ascii', errors='replace')}",
        f"flags={info['flags']:#06x}",
        f"data_fork_hdr={info['data_len_hdr']} actual={len(info['data'])}",
        f"rsrc_fork_hdr={info['rsrc_len_hdr']} actual={len(info['rsrc'])}",
        f"header_crc={info['header_crc']:#06x} data_crc={info['data_crc']} rsrc_crc={info['rsrc_crc']}",
        f"wrote {data_path} {data_path.stat().st_size}",
        f"rsrc {rsrc_path}",
        "",
        "== data fork first 512 ==",
        hexdump(info["data"], 512),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
