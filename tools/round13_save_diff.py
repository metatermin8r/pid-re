# -*- coding: utf-8 -*-
"""Round 13 save: extract AAA/AAB from the two-name Saved Games file."""

from __future__ import annotations

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import SECTOR_TYPE_NAME, load_maps  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games AAA-AAB"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round13_save_diff.txt"
AAA_OUT = ROOT / "reference/saves/save_AAA"
AAB_OUT = ROOT / "reference/saves/save_AAB"

LEVEL_BASE = 39392
LEVEL_STRIDE = 9112
SLOT = 2876
INV_OFF = 0x0A00
TIME_OFF = 0x074A
HP_OFF = 0x0754
LEVEL_OFF = 0x090C
X_OFF = 0x0918
Y_OFF = 0x091A
FACING_OFF = 0x091C

ITEM_NAMES = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flash light",
    0x06: "Canvas sack",
    0x16: "Mein Kampf",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x33: "Walther P4 Ammo",
}


def u16(d: bytes, o: int) -> int:
    return struct.unpack_from(">H", d, o)[0]


def u32(d: bytes, o: int) -> int:
    return struct.unpack_from(">I", d, o)[0]


def rec4(d: bytes, o: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", d, o)


def live_packed(block: bytes, start: int = 256) -> tuple[int, int, list[tuple[int, tuple[int, int, int, int]]]]:
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return len(recs), off, recs
        recs.append((off, rec))
        off += 8
    return len(recs), off, recs


def dump_inv(data: bytes, start: int, n: int, lines: list[str], label: str) -> None:
    lines.append(f"  {label} inventory window @{start} ({n} records):")
    for i in range(n):
        off = start + i * 8
        if off + 8 > len(data):
            break
        rec = rec4(data, off)
        name = ITEM_NAMES.get(rec[0], "")
        lines.append(f"    [{i:02d}] @{off} ({rec[0]:5d},{rec[1]:5d},{rec[2]:5d},{rec[3]:5d}) {name}")


def classify(off: int) -> str:
    if TIME_OFF <= off <= TIME_OFF + 3:
        return "clock"
    if X_OFF <= off <= X_OFF + 1:
        return "position_x"
    if Y_OFF <= off <= Y_OFF + 1:
        return "position_y"
    if FACING_OFF <= off <= FACING_OFF + 3:
        return "facing"
    if LEVEL_OFF <= off <= LEVEL_OFF + 1:
        return "level"
    if HP_OFF <= off <= HP_OFF + 3:
        return "hp"
    if INV_OFF <= off < LEVEL_BASE:
        return "inventory_region"
    if LEVEL_BASE <= off < LEVEL_BASE + 26 * LEVEL_STRIDE:
        n = (off - LEVEL_BASE) // LEVEL_STRIDE
        return f"level{n}_block"
    return "other"


def main() -> None:
    data = SAVE.read_bytes()
    lines: list[str] = []
    lines.append(f"size={len(data)} extra_vs_267452={len(data) - 267452}")
    nblocks = (len(data) - LEVEL_BASE) // LEVEL_STRIDE
    tail = (len(data) - LEVEL_BASE) % LEVEL_STRIDE
    lines.append(f"level_blocks_from_{LEVEL_BASE}={nblocks} tail={tail}")

    # --- two player slots at stride 2876 ---
    lines.append("\n========== PLAYER SLOTS (stride 2876) ==========")
    for name, base in (("AAA", 0), ("AAB", SLOT)):
        t = u32(data, TIME_OFF + base)
        hp = u16(data, HP_OFF + base)
        hpm = u16(data, HP_OFF + 2 + base)
        lev = u16(data, LEVEL_OFF + base)
        x = u16(data, X_OFF + base)
        y = u16(data, Y_OFF + base)
        fac = data[FACING_OFF + base : FACING_OFF + 4 + base]
        lines.append(
            f"  {name} base={base} time={t} ({t/60:.2f}s) hp={hp}/{hpm} "
            f"level={lev} xy=({x},{y}) facing={fac.hex()}"
        )

    # byte-diff the two 2876-byte windows that contain player fields
    # Use windows aligned to the known field region: compare [0:2876] vs [2876:5752]
    # AND compare [1780:2876] vs [1780+2876:2876+2876]
    w0 = data[0:SLOT]
    w1 = data[SLOT : 2 * SLOT]
    diffs = [i for i in range(SLOT) if w0[i] != w1[i]]
    lines.append(f"\n== slot-window [0:2876] vs [2876:5752]: {len(diffs)} differing bytes ==")
    # group runs
    runs = []
    if diffs:
        s = prev = diffs[0]
        for o in diffs[1:]:
            if o == prev + 1:
                prev = o
            else:
                runs.append((s, prev))
                s = prev = o
        runs.append((s, prev))
    lines.append(f"  runs={len(runs)}")
    for a, b in runs:
        ctx0 = data[max(0, a - 4) : min(SLOT, b + 5)].hex(" ")
        ctx1 = data[SLOT + max(0, a - 4) : SLOT + min(SLOT, b + 5)].hex(" ")
        lines.append(f"  [{a}:{b}] ({b-a+1}B) AAA={data[a:b+1].hex(' ')} AAB={data[SLOT+a:SLOT+b+1].hex(' ')}")
        lines.append(f"    ctxAAA {ctx0}")
        lines.append(f"    ctxAAB {ctx1}")

    # inventories
    lines.append("\n========== TASK 4 inventory ==========")
    dump_inv(data, INV_OFF, 24, lines, "AAA@0x0A00")
    dump_inv(data, INV_OFF + SLOT, 24, lines, "AAB@0x0A00+2876")

    # also dump raw hex of both inv regions
    lines.append("\nAAA inv hex 2560..2760:")
    lines.append(hexdump_mac_roman(data[2560:2760]))
    lines.append("AAB inv hex 5436..5636:")
    lines.append(hexdump_mac_roman(data[5436:5636]))

    # --- full file diff is meaningless (two slots in one file). ---
    # Diff the two slot windows is the real AAA vs AAB player delta.
    # Also diff if we construct two virtual files by swapping slots.

    # --- level blocks ---
    lines.append("\n========== TASK 2 live packed lists ==========")
    counts = []
    for n in range(nblocks):
        block = data[LEVEL_BASE + n * LEVEL_STRIDE : LEVEL_BASE + (n + 1) * LEVEL_STRIDE]
        cnt, term, recs = live_packed(block)
        counts.append(cnt)
        extra = ""
        if n in (0, nblocks - 1) or (nblocks > 25 and n == 25):
            extra = f" first={[r[1] for r in recs[:3]]} last={[r[1] for r in recs[-3:]]}"
        lines.append(f"  L{n} live={cnt} term={term}{extra}")
    lines.append(f"  count_histogram={Counter(counts)}")

    # compare L0 vs L25 if 26 blocks
    if nblocks >= 26:
        b0 = data[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
        b25 = data[LEVEL_BASE + 25 * LEVEL_STRIDE : LEVEL_BASE + 26 * LEVEL_STRIDE]
        nd = sum(1 for i in range(LEVEL_STRIDE) if b0[i] != b25[i])
        lines.append(f"\n  L0 vs L25 differing bytes: {nd}/{LEVEL_STRIDE}")
        dpos = [i for i in range(LEVEL_STRIDE) if b0[i] != b25[i]]
        if dpos:
            s = prev = dpos[0]
            rlist = []
            for o in dpos[1:]:
                if o == prev + 1:
                    prev = o
                else:
                    rlist.append((s, prev))
                    s = prev = o
            rlist.append((s, prev))
            for a, b in rlist[:40]:
                lines.append(
                    f"    L0/L25 [{a}:{b}] L0={b0[a:b+1].hex(' ')} L25={b25[a:b+1].hex(' ')}"
                )

    # L0 packed list details
    b0 = data[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
    n0, term0, recs0 = live_packed(b0)
    lines.append(f"\n== T2(a) L0 live={n0} (expected AAA 85) ==")
    lines.append("  all L0 records:")
    for i, (off, rec) in enumerate(recs0):
        mark = ""
        if 0x33 in rec:
            mark += " WAMMO"
        if 8 in rec:
            mark += " qty8"
        lines.append(f"    [{i:03d}] +{off} {rec}{mark}")

    # If only one L0, world is last-write (AAB). Search for a second 85-record list.
    lines.append("\n== search other packed lists with live 80-90 ==")
    for off in range(0, len(data) - 256, 8):
        if off == LEVEL_BASE + 256:
            continue
        # cheap: first rec f0 small, scan
        if off + 8 > len(data):
            break
        r0 = rec4(data, off)
        if r0 != recs0[0][1]:
            continue
        blk = data[off - 256 : off - 256 + LEVEL_STRIDE] if off >= 256 else None
        if blk is None or len(blk) < 300:
            continue
        cnt, term, recs = live_packed(blk)
        if 70 <= cnt <= 90:
            lines.append(f"  clone of first-rec at list@{off} live={cnt} block_start={off-256}")

    # in-place field changes: compare L0 records against a second copy if any
    # also: any record containing 0x33 / 8 / candidate Item ids
    lines.append("\n== L0 records containing 0x33 or qty-like 8 ==")
    for i, (off, rec) in enumerate(recs0):
        if 0x33 in rec or rec[2] == 8 or rec[0] == 51:
            lines.append(f"  [{i}] +{off} {rec}")

    # --- Task 3: save-room sectors ---
    levels = load_maps(MAPS)
    gf = next(lv for lv in levels if lv.level_number == 0)
    lines.append(f"\n========== TASK 3 Ground Floor save room ==========")
    lines.append(f"  level {gf.name!r} n={gf.level_number}")

    # flood-fill walkable (type 1 or 9) from (6,2)
    start = (6, 2)
    walkable = {1, 6, 9}  # normal, corpse, save
    seen = set()
    stack = [start]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen:
            continue
        if not (0 <= x < 32 and 0 <= y < 32):
            continue
        sec = gf.sector_at(x, y)
        if sec.type not in walkable:
            continue
        seen.add((x, y))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            stack.append((x + dx, y + dy))

    xs = [p[0] for p in seen]
    ys = [p[1] for p in seen]
    lines.append(f"  flood from (6,2): {len(seen)} sectors bbox x={min(xs)}..{max(xs)} y={min(ys)}..{max(ys)}")

    # all type==1 in that flood, plus a tight corner around (6,2)
    lines.append("  Type==1 in flood-fill room:")
    for y in range(min(ys), max(ys) + 1):
        for x in range(min(xs), max(xs) + 1):
            if (x, y) not in seen:
                continue
            sec = gf.sector_at(x, y)
            if sec.type == 1:
                lines.append(
                    f"    ({x:2d},{y:2d}) Item={sec.item:4d} TypeAddl={sec.type_addl} "
                    f"walls={[ (w.type, w.texture) for w in sec.walls ]}"
                )

    lines.append("  Type==9 (save) in flood:")
    for x, y in sorted(seen):
        sec = gf.sector_at(x, y)
        if sec.type == 9:
            lines.append(f"    ({x},{y}) Item={sec.item}")

    # corners of bbox
    lines.append("  bbox corners (even if not type 1):")
    for x, y in (
        (min(xs), min(ys)),
        (max(xs), min(ys)),
        (min(xs), max(ys)),
        (max(xs), max(ys)),
    ):
        sec = gf.sector_at(x, y)
        lines.append(
            f"    ({x},{y}) type={sec.type}/{SECTOR_TYPE_NAME.get(sec.type, '?')} Item={sec.item}"
        )

    # all Item-bearing type 1 near (6,2) within chebyshev 6
    lines.append("  Type==1 Item!=-1 within chebyshev 6 of (6,2):")
    for y in range(32):
        for x in range(32):
            if max(abs(x - 6), abs(y - 2)) > 6:
                continue
            sec = gf.sector_at(x, y)
            if sec.type == 1 and sec.item != -1:
                lines.append(f"    ({x:2d},{y:2d}) Item={sec.item}")

    # cross-ref L0 records vs those Item values
    near_items = []
    for y in range(32):
        for x in range(32):
            if max(abs(x - 6), abs(y - 2)) > 6:
                continue
            sec = gf.sector_at(x, y)
            if sec.type == 1 and sec.item != -1:
                near_items.append(sec.item)
    lines.append("\n  L0 records whose any field matches a nearby Type-1 Item:")
    near_set = set(near_items)
    for i, (off, rec) in enumerate(recs0):
        hits = [v for v in rec if v in near_set]
        if hits:
            lines.append(f"    [{i}] {rec} matched Item={hits}")

    # ascii map of flood
    lines.append("\n  room ascii (1=normal Item, 9=save, .=other walkable, space=out):")
    for y in range(min(ys), max(ys) + 1):
        row = []
        for x in range(min(xs), max(xs) + 1):
            if (x, y) not in seen:
                row.append(" ")
                continue
            sec = gf.sector_at(x, y)
            if sec.type == 9:
                row.append("S")
            elif sec.type == 1 and sec.item != -1:
                row.append("I")
            elif sec.type == 1:
                row.append(".")
            else:
                row.append(str(sec.type))
        lines.append("    " + "".join(row) + f"  y={y}")

    # write extracted slot slices for later
    AAA_OUT.write_bytes(data[0:SLOT])
    AAB_OUT.write_bytes(data[SLOT : 2 * SLOT])
    lines.append(f"\nwrote {AAA_OUT.name} and {AAB_OUT.name} ({SLOT} bytes each) — player-slot slices, not full saves")

    # region classification of slot diffs (file offsets)
    lines.append("\n========== TASK 1 slot-diff classification ==========")
    by = defaultdict(int)
    for o in diffs:
        by[classify(o)] += 1
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {k}: {v}")
    lines.append(f"  TOTAL slot-window diffs: {len(diffs)}")

    # also: how much of the REST of the file (beyond 2*SLOT) is unique vs old?
    # dump bytes around L0 packed list start
    lines.append("\nL0 header + first 64 of packed list:")
    lines.append(hexdump_mac_roman(b0[:320]))

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:120]))
    print(f"\n... wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
