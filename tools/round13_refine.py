# -*- coding: utf-8 -*-
"""Round 13 refine: two inventories, Item vs type-35, L0 vs L25, row-skip RLE."""

from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402
from round10_256 import load_all_256  # noqa: E402
from round12_level_rle import decode_rle  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games AAA-AAB"
OLD = ROOT / "reference/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round13_refine.txt"

LEVEL_BASE = 39392
LEVEL_STRIDE = 9112
SLOT = 2876
INV = 0x0A00


def rec4(d: bytes, o: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", d, o)


def live_packed(block: bytes, start: int = 256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs, off
        recs.append(rec)
        off += 8
    return recs, off


def main() -> None:
    data = SAVE.read_bytes()
    old = OLD.read_bytes() if OLD.exists() else b""
    levels = load_maps(MAPS)
    gf = next(lv for lv in levels if lv.level_number == 0)
    lines: list[str] = []

    # ---- inventories at 2560 + k*2876 ----
    lines.append("========== inventory copies at 2560+k*2876 ==========")
    for k in range(6):
        off = INV + k * SLOT
        if off + 160 > len(data):
            break
        recs = [rec4(data, off + i * 8) for i in range(16)]
        live = [(i, r) for i, r in enumerate(recs) if r[0] not in (0, 0xFFFF) or r[2] not in (0, 0xFFFF)]
        lines.append(f"  k={k} @{off}")
        for i, r in enumerate(recs):
            lines.append(f"    [{i:02d}] {r}")

    # exact 8-byte diffs between k=0 and k=1
    lines.append("\n== AAA@2560 vs AAB@5436 record diffs ==")
    for i in range(20):
        a = rec4(data, INV + i * 8)
        b = rec4(data, INV + SLOT + i * 8)
        if a != b:
            lines.append(f"  rec[{i}] AAA={a} AAB={b} bytesAAA={data[INV+i*8:INV+i*8+8].hex(' ')} bytesAAB={data[INV+SLOT+i*8:INV+SLOT+i*8+8].hex(' ')}")

    # player fields at +0 and +2876
    lines.append("\n== player fields base vs +2876 ==")
    for label, off in (
        ("time", 0x074A),
        ("hp", 0x0754),
        ("level", 0x090C),
        ("x", 0x0918),
        ("y", 0x091A),
        ("facing", 0x091C),
    ):
        a = data[off : off + 4]
        b = data[off + SLOT : off + SLOT + 4]
        lines.append(f"  {label} @{off} AAA={a.hex()} AAB={b.hex()}")

    # ---- GF items vs L0 type-35 f2 ----
    b0 = data[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
    recs0, term0 = live_packed(b0)
    type35 = [r for r in recs0 if r[0] == 35]
    f2s = {r[2] for r in type35}
    items = {sec.item for sec in gf.sector_list if sec.item != -1}
    lines.append(f"\n========== Sector.Item vs L0 type-35 f2 ==========")
    lines.append(f"  type35_count={len(type35)} f2_set={sorted(f2s)}")
    lines.append(f"  map_items={len(items)} missing_from_type35={sorted(items - f2s)}")
    lines.append(f"  type35_f2_not_on_map={sorted(f2s - items)}")

    # west alcove x=5..7 y=1..3
    lines.append("\n== west save alcove (5..7, 1..3) ==")
    for y in range(1, 4):
        for x in range(5, 8):
            sec = gf.sector_at(x, y)
            in35 = sec.item in f2s
            lines.append(
                f"  ({x},{y}) type={sec.type} Item={sec.item} in_type35={in35}"
            )

    # all type-1 Item in alcove-ish x=5..8 y=1..4
    lines.append("\n== Type==1 Item-bearing x=4..8 y=1..4 ==")
    for y in range(1, 5):
        for x in range(4, 9):
            sec = gf.sector_at(x, y)
            if sec.type == 1:
                lines.append(f"  ({x},{y}) Item={sec.item} in35={sec.item in f2s}")

    # L25 packed
    b25 = data[LEVEL_BASE + 25 * LEVEL_STRIDE : LEVEL_BASE + 26 * LEVEL_STRIDE]
    recs25, _ = live_packed(b25)
    lines.append(f"\n========== L25 packed ({len(recs25)}) vs L0 ({len(recs0)}) ==========")
    # which level's items match L25 f2?
    f2_25 = {r[2] for r in recs25 if r[0] in (35, 60, 0)}
    for lv in levels:
        its = {sec.item for sec in lv.sector_list if sec.item != -1}
        t35 = {r[2] for r in recs25 if r[0] == 35}
        inter = t35 & its
        lines.append(
            f"  L{lv.level_number:02d} {lv.name!r} item_n={len(its)} "
            f"t35_inter={len(inter)} t35_only={len(t35-its)}"
        )

    # record-by-record L0 vs L25
    same = sum(1 for a, b in zip(recs0, recs25) if a == b)
    lines.append(f"  pairwise equal={same}/{min(len(recs0), len(recs25))}")

    # shift test: is L25 L0 with one record removed?
    lines.append("\n== shift-by-8 test L0 vs L25 (not expected to match) ==")
    # find first diverge in L0 vs a second L0 copy — we don't have AAA L0.
    # Instead: is 44 present as any field in L0 / L25?
    for label, recs in (("L0", recs0), ("L25", recs25)):
        hits = [(i, r) for i, r in enumerate(recs) if 44 in r]
        lines.append(f"  {label} records containing 44: {hits}")

    # old save L0
    if old and len(old) > LEVEL_BASE + LEVEL_STRIDE:
        old0 = old[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
        recs_old, _ = live_packed(old0)
        t35_old = [r for r in recs_old if r[0] == 35]
        f2_old = {r[2] for r in t35_old}
        lines.append(f"\n== old Saved Games L0 live={len(recs_old)} type35={len(t35_old)} ==")
        lines.append(f"  f2_old missing 44? {44 not in f2_old}")
        lines.append(f"  new-old type35 f2 added={sorted(f2s - f2_old)}")
        lines.append(f"  new-old type35 f2 removed={sorted(f2_old - f2s)}")
        # first diverge
        for i, (a, b) in enumerate(zip(recs_old, recs0)):
            if a != b:
                lines.append(f"  first rec differ [{i}] old={a} new={b}")
                break
        else:
            lines.append("  prefix equal")

    # ---- RLE skip-at-row ----
    lines.append("\n========== T5 extra: skip N bytes at each row boundary ==========")
    shapes = load_all_256()

    def plus1(src, target=None):
        return decode_rle(src, "plus1", "highbit_plus1", target)

    for rid in (195, 198):
        src = shapes[rid][257:]
        for skip in (0, 1, 2, 8, 15, 16):
            for nrows in (128, 256):
                out = bytearray()
                i = 0
                ok = True
                for r in range(nrows):
                    chunk, used = plus1(src[i:], 128)
                    if len(chunk) < 128:
                        ok = False
                        break
                    out.extend(chunk)
                    i += used + skip
                    if i > len(src):
                        ok = False
                        break
                lines.append(
                    f"  {rid} skip={skip} rows={nrows}: ok={ok} out={len(out)} "
                    f"used={i}/{len(src)} leftover={len(src)-i}"
                )

    # leftover dump for 198 plus1 per-row (85 bytes)
    src198 = shapes[198][257:]
    out, used, _ = None, None, None
    i = 0
    for r in range(128):
        chunk, used = plus1(src198[i:], 128)
        i += used
    left = src198[i:]
    lines.append(f"\n198 leftover after 128-row plus1: {len(left)} bytes")
    lines.append(left.hex(" "))
    lines.append(hexdump_mac_roman(left))

    # 256 rows no skip
    i = 0
    nout = 0
    rows_done = 0
    for r in range(256):
        chunk, used = plus1(src198[i:], 128)
        if len(chunk) < 128:
            break
        nout += len(chunk)
        i += used
        rows_done += 1
    lines.append(f"198 256-row attempt: rows={rows_done} out={nout} used={i} leftover={len(src198)-i}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
