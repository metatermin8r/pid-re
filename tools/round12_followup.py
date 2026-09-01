# -*- coding: utf-8 -*-
"""Round 12 follow-up: +256 object list, 16-byte middle, pair-RLE."""

from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import load_maps  # noqa: E402
from round10_256 import load_all_256  # noqa: E402
from round9_shapes import rle_count_then_byte, rle_highbit_inv  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round12_followup.txt"
LEVEL_BASE = 39392
LEVEL_STRIDE = 9112


def rec8(block: bytes, i: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", block, i * 8)


def item_set(level) -> set[int]:
    return {s.item for s in level.sector_list if s.item != -1}


def pair_repeat(src: bytes, low_is_count_plus1: bool = True) -> bytes:
    """Always (ctrl, pixel) pairs. C<80: count=C+1; C>=80: (C&7F)+1."""
    out = bytearray()
    i = 0
    n = len(src)
    while i + 1 < n:
        c = src[i]
        v = src[i + 1]
        i += 2
        if c & 0x80:
            count = (c & 0x7F) + 1
        else:
            count = c + 1 if low_is_count_plus1 else (c if c else 1)
        out.extend(bytes([v]) * count)
    return bytes(out)


def disc_repeat_only(src: bytes) -> bytes:
    """3-16 = literal pixel; 00/01/02 = repeat (C+1) of next; 80+ = highbit repeat."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        b = src[i]
        i += 1
        if 3 <= b <= 16:
            out.append(b)
        elif b <= 2:
            if i >= n:
                break
            out.extend(bytes([src[i]]) * (b + 1))
            i += 1
        elif b >= 0x80:
            if i >= n:
                break
            out.extend(bytes([src[i]]) * ((b & 0x7F) + 1))
            i += 1
        else:
            out.append(b)
    return bytes(out)


def consume_until(decode_fn, src: bytes, target: int) -> tuple[int, int]:
    """Walk with a streaming decoder is hard; decode full then see.
    For pair/count schemes we can stream."""
    out = decode_fn(src)
    return len(out), len(src)


def main() -> None:
    data = SAVE.read_bytes()
    levels = load_maps(MAPS)
    lines: list[str] = []

    lines.append("== object list from block+256 (8-byte until 8x FFFF-run) ==")
    for ln, expect in ((0, 116), (6, 109), (13, 294)):
        blk = data[LEVEL_BASE + ln * LEVEL_STRIDE : LEVEL_BASE + (ln + 1) * LEVEL_STRIDE]
        items = item_set(levels[ln])
        recs = []
        for i in range(32, 1139):  # 32*8=256
            r = rec8(blk, i)
            recs.append((i, r))
        # terminate at 4 consecutive FFFF-leading empties
        live = []
        for i, r in recs:
            if r[0] == 0xFFFF and r[1] == 0:
                break
            live.append((i, r))
        by_f0 = Counter(r[0] for _, r in live)
        f2s = [r[2] for _, r in live]
        f2_in_items = sum(1 for v in f2s if v in items)
        f0_23 = [(i, r) for i, r in live if r[0] == 0x23]
        f2_of_23 = [r[2] for _, r in f0_23]
        match_23 = sum(1 for v in f2_of_23 if v in items)
        lines.append(
            f"  L{ln} {levels[ln].name!r} expect={expect} map_items={len(items)}"
        )
        lines.append(f"    packed-live until FFFF: {len(live)}  f0_top={by_f0.most_common(6)}")
        lines.append(f"    f2_in_itemset={f2_in_items}/{len(live)}  f0==0x23 n={len(f0_23)} f2_of_23_in_items={match_23}")
        lines.append(f"    first8={live[:8]}")
        lines.append(f"    last4={live[-4:]}")
        if ln == 0:
            # is f2 sequence of 0x23 recs == GF items minus some?
            lines.append(f"    f2 of 0x23: {f2_of_23[:40]} ... n={len(f2_of_23)}")
            lines.append(f"    GF items not in f2_of_23: {sorted(items - set(f2_of_23))[:40]}")
            lines.append(f"    f2_of_23 not in GF items: {sorted(set(f2_of_23) - items)[:40]}")
            # any rec with 114 in any field after +256
            hit = [(i, r) for i, r in live if 114 in r]
            lines.append(f"    114 in packed-live: {hit}")
            # record index from 256: rec0 at 256, rec114 at 256+114*8
            r114 = rec8(blk, 32 + 114)
            lines.append(f"    rec[32+114=146] {r114}")
            # Item-indexed from +256: index 114
            # that's rec8 index 32+114 = 146, same

        # 16-byte objects in the middle (look for 0x2007 / ffff cadence)
        pat = 0
        for off in range(256, 7000, 16):
            a = struct.unpack_from(">8H", blk, off)
            if a[5] == 0xFFFF or a[3] in (0x2007, 0x0007, 0xE007):
                pat += 1
        lines.append(f"    16-byte-ish (ffff or *007 at field) count={pat}")

    # header 256 shared structure
    lines.append("\n== L0 vs L13 bytes 0-256 ==")
    b0 = data[LEVEL_BASE : LEVEL_BASE + 256]
    b13 = data[LEVEL_BASE + 13 * LEVEL_STRIDE : LEVEL_BASE + 13 * LEVEL_STRIDE + 256]
    same = sum(1 for a, b in zip(b0, b13, strict=True) if a == b)
    lines.append(f"  identical 0-256 L0/L13: {same}/256")
    lines.append(f"  L0[0:32]={b0[:32].hex(' ')}")
    lines.append(f"  L13[0:32]={b13[:32].hex(' ')}")

    # count-then-byte and pair RLE
    shapes = load_all_256()
    d195 = shapes[195]
    lines.append(f"\n== T4 extra RLE packed={len(d195)} ==")
    for start in (257, 258, 23):
        src = d195[start:]
        ctb = rle_count_then_byte(src)
        pr = pair_repeat(src)
        pr0 = pair_repeat(src, low_is_count_plus1=False)
        disc = disc_repeat_only(src)
        inv = rle_highbit_inv(src)
        for name, out in (
            ("count_then_byte", ctb),
            ("pair C+1 / hb", pr),
            ("pair C / hb (C=0 skip)", pr0),
            ("disc 3-16 lit, 00-02/80+ rep", disc),
            ("highbit_inv", inv),
        ):
            lines.append(
                f"  @{start} {name}: out={len(out)} d={len(out)-33144:+d} "
                f"{'HIT' if len(out)==33144 else ''}"
            )

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
