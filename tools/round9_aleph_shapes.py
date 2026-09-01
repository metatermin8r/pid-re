# -*- coding: utf-8 -*-
"""Dump Aleph One / Marathon 2 Shapes.shpA collection index and export bitmaps.

Marathon 2 layout (Hopper shapes2xml / Aleph One), used only to read the
AOPID conversion — not applied to PID .256 resources.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHAPES = ROOT / "data/aleph/AOPID_v1.4/AOPID_v1.4/Shapes.shpA"
OUTDIR = ROOT / "reference/aleph_shapes"
REPORT = ROOT / "reference/docs/round9_aleph.txt"


def read_collections(data: bytes) -> list[dict]:
    cols = []
    minoff = 32 * 256
    off = 0
    coll = 0
    while off + 32 <= minoff and off + 32 <= len(data):
        status, flags = struct.unpack_from(">hH", data, off)
        off8, len8, off16, len16 = struct.unpack_from(">iiii", data, off + 4)
        off += 32
        if off8 > 0:
            minoff = min(minoff, off8)
        if off16 > 0:
            minoff = min(minoff, off16)
        cols.append(
            {
                "index": coll,
                "status": status,
                "flags": flags,
                "off8": off8,
                "len8": len8,
                "off16": off16,
                "len16": len16,
            }
        )
        coll += 1
        if coll > 64:
            break
    return cols


def parse_collection(data: bytes, base: int, nbytes: int) -> dict | None:
    if base < 0 or base + 32 > len(data):
        return None
    version, ctype, cflags, color_count, cluts = struct.unpack_from(">hhHhh", data, base)
    coff = struct.unpack_from(">i", data, base + 10)[0]
    hcount = struct.unpack_from(">h", data, base + 14)[0]
    hoff = struct.unpack_from(">i", data, base + 16)[0]
    lcount = struct.unpack_from(">h", data, base + 20)[0]
    loff = struct.unpack_from(">i", data, base + 22)[0]
    bcount = struct.unpack_from(">h", data, base + 26)[0]
    boff = struct.unpack_from(">i", data, base + 28)[0]
    names = []
    if hoff > 0 and hcount > 0:
        table = base + hoff
        for i in range(hcount):
            if table + i * 4 + 4 > len(data):
                break
            ioff = struct.unpack_from(">i", data, table + i * 4)[0]
            if ioff <= 0:
                continue
            pos = base + ioff
            if pos + 40 > len(data):
                continue
            nlen = data[pos + 4]
            name = data[pos + 5 : pos + 5 + min(nlen, 33)].decode("mac_roman", errors="replace")
            names.append(name)
    return {
        "version": version,
        "type": ctype,
        "color_count": color_count,
        "cluts": cluts,
        "coff": coff,
        "hcount": hcount,
        "lcount": lcount,
        "bcount": bcount,
        "boff": boff,
        "names": names,
    }


def load_clut(data: bytes, base: int, coff: int, cluts: int, color_count: int) -> list[tuple[int, int, int]]:
    pal = [(0, 0, 0)] * 256
    if coff <= 0 or color_count <= 0:
        return pal
    pos = base + coff
    # first clut only
    for i in range(color_count):
        if pos + 8 > len(data):
            break
        flags, val, r, g, b = struct.unpack_from(">BBHHH", data, pos)
        pos += 8
        pal[val] = (r >> 8, g >> 8, b >> 8)
    return pal


def export_raw_bitmaps(data: bytes, base: int, info: dict, pal: list, dest: Path, limit: int = 8) -> int:
    """Export bitmaps whose bytes_per_row > -1 (uncompressed)."""
    boff = info["boff"]
    bcount = info["bcount"]
    if boff <= 0 or bcount <= 0:
        return 0
    table = base + boff
    n = 0
    dest.mkdir(parents=True, exist_ok=True)
    for i in range(bcount):
        if n >= limit:
            break
        if table + i * 4 + 4 > len(data):
            break
        ioff = struct.unpack_from(">i", data, table + i * 4)[0]
        if ioff <= 0:
            continue
        pos = base + ioff
        if pos + 26 > len(data):
            continue
        w, h, brow, flags, depth = struct.unpack_from(">hhhHh", data, pos)
        if w <= 0 or h <= 0 or w > 1024 or h > 1024:
            continue
        pix_off = pos + 26 + 4 * ((w + 1) if (flags & 0x8000) else (h + 1))
        if brow > -1:
            need = w * h
            if pix_off + need > len(data):
                continue
            raw = data[pix_off : pix_off + need]
            img = Image.new("RGB", (w, h))
            px = img.load()
            for p, idx in enumerate(raw):
                px[p % w, p // w] = pal[idx] if idx < 256 else (idx, idx, idx)
            img.save(dest / f"bmp_{i:03d}_{w}x{h}.png")
            n += 1
    return n


def main() -> None:
    data = SHAPES.read_bytes()
    lines = [f"Shapes.shpA size={len(data)}"]
    cols = read_collections(data)
    lines.append(f"index entries={len(cols)}")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for c in cols:
        if c["off8"] <= 0 or c["len8"] <= 0:
            continue
        info = parse_collection(data, c["off8"], c["len8"])
        if info is None:
            continue
        names = ", ".join(info["names"][:12])
        lines.append(
            f"  coll {c['index']:2d} off8={c['off8']:8d} len8={c['len8']:8d} "
            f"type={info['type']} colors={info['color_count']} cluts={info['cluts']} "
            f"hl={info['hcount']} ll={info['lcount']} bmp={info['bcount']} names=[{names}]"
        )
        pal = load_clut(data, c["off8"], info["coff"], info["cluts"], info["color_count"])
        n = export_raw_bitmaps(data, c["off8"], info, pal, OUTDIR / f"c{c['index']:02d}", limit=6)
        lines.append(f"       exported {n} uncompressed bitmaps")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
