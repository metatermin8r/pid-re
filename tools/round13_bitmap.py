# -*- coding: utf-8 -*-
"""Round 13: 1024-bit sector map in the 256-byte level-block header?"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games AAA-AAB"
OLD = ROOT / "reference/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round13_bitmap.txt"

LEVEL_BASE = 39392
LEVEL_STRIDE = 9112


def bits_from(block: bytes, start: int, nbits: int) -> list[int]:
    out = []
    for i in range(nbits):
        byte = block[start + i // 8]
        bit = (byte >> (7 - (i % 8))) & 1  # msb first
        out.append(bit)
    return out


def bits_lsb(block: bytes, start: int, nbits: int) -> list[int]:
    out = []
    for i in range(nbits):
        byte = block[start + i // 8]
        bit = (byte >> (i % 8)) & 1
        out.append(bit)
    return out


def main() -> None:
    data = SAVE.read_bytes()
    old = OLD.read_bytes()
    gf = next(lv for lv in load_maps(MAPS) if lv.level_number == 0)
    lines: list[str] = []

    nblocks = (len(data) - LEVEL_BASE) // LEVEL_STRIDE
    lines.append(f"nblocks={nblocks}")

    # header identity
    headers = [data[LEVEL_BASE + n * LEVEL_STRIDE : LEVEL_BASE + n * LEVEL_STRIDE + 256] for n in range(nblocks)]
    lines.append("\n== header[0:256] unique? ==")
    for n, h in enumerate(headers):
        same_as_0 = h == headers[0]
        nz = sum(1 for b in h if b)
        lines.append(f"  L{n} ==L0={same_as_0} nonzero={nz}")

    lines.append("\nL0 header:")
    lines.append(hexdump_mac_roman(headers[0]))
    lines.append("\nL25 header:")
    lines.append(hexdump_mac_roman(headers[25]))

    # old vs new L0 header
    old_h = old[LEVEL_BASE : LEVEL_BASE + 256]
    lines.append(f"\nold L0 header == new L0 header? {old_h == headers[0]}")
    if old_h != headers[0]:
        diffs = [i for i in range(256) if old_h[i] != headers[0][i]]
        lines.append(f"  diffs at {diffs}")

    # try bytes 128-255 as 1024-bit map
    for n in (0, 25):
        h = headers[n]
        for order, fn in (("msb", bits_from), ("lsb", bits_lsb)):
            bits = fn(h, 128, 1024)
            nset = sum(bits)
            lines.append(f"\n== L{n} header[128:256] {order} set={nset}/1024 ==")
            # print 32x32
            grid = []
            for y in range(32):
                row = "".join("1" if bits[y * 32 + x] else "." for x in range(32))
                grid.append(row)
            for y, row in enumerate(grid):
                lines.append(f"  {y:02d} {row}")
            # bits at save alcove
            for x, y in ((5, 1), (6, 1), (7, 1), (5, 2), (6, 2), (7, 2), (5, 3), (6, 3), (7, 3), (14, 6)):
                idx = y * 32 + x
                lines.append(f"    ({x},{y}) bit={bits[idx]} Item={gf.sector_at(x,y).item} type={gf.sector_at(x,y).type}")

    # also try header[0:128] as bitmap
    for n in (0, 25):
        bits = bits_lsb(headers[n], 0, 1024)
        # only 256 bytes header = 2048 bits max; 0:128 = 1024 bits
        nset = sum(bits)
        lines.append(f"\nL{n} header[0:128] lsb set={nset}")

    # L0 vs L25 full header hex of 128-256
    lines.append("\nL0[128:256] hex:")
    lines.append(headers[0][128:].hex(" "))
    lines.append("L25[128:256] hex:")
    lines.append(headers[25][128:].hex(" "))

    # search whole file for a 128-byte region that has bit 44 or sector (5,2)=5+2*32=69 set
    # and differs in a pickup-like way — skip, too vague

    # extra 9112 block: is it a 26th level or a taken-table?
    b25 = data[LEVEL_BASE + 25 * LEVEL_STRIDE : LEVEL_BASE + 26 * LEVEL_STRIDE]
    lines.append(f"\nL25 nonzero={sum(1 for b in b25 if b)} first32={b25[:32].hex(' ')}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
