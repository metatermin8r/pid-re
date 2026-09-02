# -*- coding: utf-8 -*-
"""Round 15: locate per-level persistence — cross-file block 0 first."""

from __future__ import annotations

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402
from round10_256 import compact_gray, load_all_256  # noqa: E402

ONE = ROOT / "reference/saves/Saved Games"
TWO = ROOT / "reference/saves/Saved Games r14"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round15_persist.txt"
SHAPEDIR = ROOT / "reference/shapes"

LEVEL_BASE = 39392
STRIDE = 9112
SLOT = 2876
TIME_OFF = 0x074A
HP_OFF = 0x0754
LEVEL_OFF = 0x090C
X_OFF = 0x0918
Y_OFF = 0x091A
FACING_OFF = 0x091C
INV_OFF = 0x0A00

ITEM_NAMES = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flash light",
    0x06: "Canvas sack",
    0x16: "Mein Kampf",
    0x23: "Silver Bowl / type-35",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x33: "Walther P4 Ammo",
    0x3C: "40mm Projectile Cartridge",
}

ALCOVE_ITEMS = {43, 44, 45, 53, 57}
ALCOVE_SECTORS = {
    (5, 1): 53,
    (6, 1): 43,
    (7, 1): 57,
    (5, 2): 44,
    (7, 3): 45,
}


def u16(d: bytes, o: int) -> int:
    return struct.unpack_from(">H", d, o)[0]


def u32(d: bytes, o: int) -> int:
    return struct.unpack_from(">I", d, o)[0]


def rec4(d: bytes, o: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", d, o)


def pascal(d: bytes, o: int) -> str:
    n = d[o]
    return d[o + 1 : o + 1 + n].decode("mac_roman", errors="replace")


def live_packed(block: bytes, start: int = 256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs, off
        recs.append((off, rec))
        off += 8
    return recs, off


def runs_of(diffs: list[int]) -> list[tuple[int, int]]:
    if not diffs:
        return []
    out = []
    s = prev = diffs[0]
    for o in diffs[1:]:
        if o == prev + 1:
            prev = o
        else:
            out.append((s, prev))
            s = prev = o
    out.append((s, prev))
    return out


def classify_player(off: int) -> str:
    if TIME_OFF <= off <= TIME_OFF + 3:
        return "clock"
    if HP_OFF <= off <= HP_OFF + 3:
        return "hp"
    if LEVEL_OFF <= off <= LEVEL_OFF + 1:
        return "level"
    if X_OFF <= off <= X_OFF + 1:
        return "position_x"
    if Y_OFF <= off <= Y_OFF + 1:
        return "position_y"
    if FACING_OFF <= off <= FACING_OFF + 3:
        return "facing"
    if INV_OFF <= off < SLOT:
        return "inventory_region"
    return "other"


def popcount_bytes(b: bytes) -> int:
    return sum(bin(x).count("1") for x in b)


def bitmap_candidates(slot: bytes, min_len: int = 32, max_len: int = 128) -> list[tuple[int, int, int, float]]:
    """Return (offset, length, popcount, density) for irregular bit-dense windows."""
    cands = []
    for length in (50, 52, 64, 100, 128):
        if length > len(slot):
            continue
        for off in range(0, len(slot) - length + 1, 2):
            win = slot[off : off + length]
            pc = popcount_bytes(win)
            dens = pc / (length * 8)
            # irregular: not all-zero, not all-ones, density 0.05-0.6
            if 0.05 <= dens <= 0.60 and pc >= 8:
                # skip obvious ASCII / 68k code (too many printable)
                printable = sum(1 for x in win if 32 <= x < 127)
                if printable / length > 0.5:
                    continue
                cands.append((off, length, pc, dens))
    # collapse nearby of same length, keep highest density
    kept = []
    for c in sorted(cands, key=lambda x: (x[1], x[0])):
        if kept and kept[-1][1] == c[1] and c[0] - kept[-1][0] < c[1] // 2:
            if c[3] > kept[-1][3]:
                kept[-1] = c
            continue
        kept.append(c)
    return kept


def main() -> None:
    one = ONE.read_bytes()
    two = TWO.read_bytes()
    levels = load_maps(MAPS)
    lines: list[str] = []

    lines.append("========== TASK 1 cross-file / layout ==========")
    lines.append(f"one={len(one)} two={len(two)} delta={len(two)-len(one)} (=9112? {len(two)-len(one)==STRIDE})")
    lines.append(f"T1(a) names: @{0} {pascal(two, 0)!r}  @{128} {pascal(two, 128)!r}")
    lines.append("name slot 0:")
    lines.append(hexdump_mac_roman(two[0:128]))
    lines.append("name slot 1:")
    lines.append(hexdump_mac_roman(two[128:256]))
    # how many 128-byte name slots?
    for i in range(8):
        off = i * 128
        n = two[off]
        ok = 1 <= n <= 31 and all(32 <= b < 127 for b in two[off + 1 : off + 1 + n])
        shown = repr(pascal(two, off)) if ok else ""
        lines.append(f"  slot[{i}] @{off} valid_name={ok} {shown}")

    # T1(b) player slot full diff
    a = two[0:SLOT]
    b = two[SLOT : 2 * SLOT]
    diffs = [i for i in range(SLOT) if a[i] != b[i]]
    lines.append(f"\nT1(b) player AAA[0:2876] vs AAB[2876:5752]: {len(diffs)} differing bytes")
    by = defaultdict(int)
    for s, e in runs_of(diffs):
        cls = classify_player(s)
        by[cls] += e - s + 1
        lines.append(
            f"  [{s}:{e}] ({e-s+1}B) {cls} A={a[s:e+1].hex(' ')} B={b[s:e+1].hex(' ')}"
        )
        lines.append(f"    ctxA {a[s:min(SLOT,s+16)].hex(' ')}")
        lines.append(f"    ctxB {b[s:min(SLOT,s+16)].hex(' ')}")
    lines.append("  class totals:")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {k}: {v}")

    # T1(c) arithmetic
    lines.append("\nT1(c) arithmetic:")
    lines.append(f"  25*9112={25*STRIDE}")
    lines.append(f"  one-name: 39392+25*9112={LEVEL_BASE+25*STRIDE}, tail={len(one)-(LEVEL_BASE+25*STRIDE)}")
    lines.append(f"  two-name: 39392+25*9112={LEVEL_BASE+25*STRIDE}, extra={len(two)-(LEVEL_BASE+25*STRIDE)}")
    lines.append("  duplicating 25 blocks per save would need +227800; file grew +9112.")
    lines.append("  => the 25 blocks are SHARED, not per-save.")

    # T1(d)(e) CROSS-FILE block diffs — THE DECISIVE TEST
    lines.append("\n********** T1(d)/(e) CROSS-FILE BLOCK DIFFS **********")
    n0_one = min(STRIDE, len(one) - LEVEL_BASE)
    n0_two = min(STRIDE, len(two) - LEVEL_BASE)
    b0_one = one[LEVEL_BASE : LEVEL_BASE + n0_one]
    b0_two = two[LEVEL_BASE : LEVEL_BASE + n0_two]
    n = min(len(b0_one), len(b0_two))
    d0 = [i for i in range(n) if b0_one[i] != b0_two[i]]
    lines.append(f"T1(d) block 0 (39392..{39392+n-1}): {len(d0)} differing bytes / {n}")
    if not d0:
        lines.append("  BLOCK 0 IS IDENTICAL across files. Not live pickup state.")
    else:
        for s, e in runs_of(d0):
            lines.append(
                f"  [{s}:{e}] ({e-s+1}B) one={b0_one[s:e+1].hex(' ')} two={b0_two[s:e+1].hex(' ')}"
            )
            lines.append(f"    ctx1 {b0_one[s:min(n,s+16)].hex(' ')}")
            lines.append(f"    ctx2 {b0_two[s:min(n,s+16)].hex(' ')}")

    lines.append("\nT1(e) all 25 blocks one-name vs r14:")
    total_diff_blocks = 0
    for i in range(25):
        off = LEVEL_BASE + i * STRIDE
        if off + STRIDE > len(one) or off + STRIDE > len(two):
            lines.append(f"  L{i} TRUNCATED")
            continue
        aa = one[off : off + STRIDE]
        bb = two[off : off + STRIDE]
        nd = sum(1 for j in range(STRIDE) if aa[j] != bb[j])
        if nd:
            total_diff_blocks += 1
        lines.append(f"  L{i:02d} @{off} diffs={nd}")
    lines.append(f"  blocks that differ: {total_diff_blocks}/25")
    if total_diff_blocks == 0:
        lines.append("  ALL 25 BLOCKS IDENTICAL. They are static templates (or identical live leftovers).")
    elif total_diff_blocks == 1:
        lines.append("  ONLY ONE BLOCK DIFFERS — that block is live.")

    # also r14 vs old AAA-AAB (both two-name, same session family?)
    old2p = ROOT / "reference/saves/Saved Games AAA-AAB"
    if old2p.exists():
        old2 = old2p.read_bytes()
        lines.append("\n  r14 vs prior two-name AAA-AAB (both 276564):")
        nd_all = sum(1 for i in range(min(len(two), len(old2))) if two[i] != old2[i])
        lines.append(f"    whole-file diffs={nd_all}")
        for i in range(25):
            off = LEVEL_BASE + i * STRIDE
            aa = old2[off : off + STRIDE]
            bb = two[off : off + STRIDE]
            nd = sum(1 for j in range(STRIDE) if aa[j] != bb[j])
            if nd:
                lines.append(f"    L{i} diffs={nd}")

    # ---- T2 side-by-side records (will be identical if T1d is 0) ----
    lines.append("\n========== TASK 2 in-place flags ==========")
    recs1, _ = live_packed(b0_one)
    recs2, _ = live_packed(b0_two)
    lines.append(f"T2(a) n one={len(recs1)} two={len(recs2)}")
    nchg = 0
    for i, ((o1, r1), (o2, r2)) in enumerate(zip(recs1, recs2)):
        mark = " DIFF" if r1 != r2 else ""
        if r1 != r2:
            nchg += 1
        lines.append(f"  [{i:03d}] +{o1} one={r1} two={r2}{mark}")
    lines.append(f"T2(b) records with any field change: {nchg}")

    lines.append("\nT2(c) alcove f2 matches:")
    for i, ((_, r1), (_, r2)) in enumerate(zip(recs1, recs2)):
        if r1[0] == 0x23 and r1[2] in ALCOVE_ITEMS:
            lines.append(
                f"  rec[{i}] f2={r1[2]} one={r1} two={r2} "
                f"f1_name={ITEM_NAMES.get(r1[1], '?')} f3_name={ITEM_NAMES.get(r1[3], '?')}"
            )
            # also decode f1/f3 as raw
            lines.append(f"    f1={r1[1]} (0x{r1[1]:04X}) f3={r1[3]} (0x{r1[3]:04X})")

    # ---- T3 player record map ----
    lines.append("\n========== TASK 3 player-record map ==========")
    map_player(two, 0, "AAA", lines)
    map_player(two, SLOT, "AAB", lines)

    # bitmaps
    lines.append("\nT3(b) bitmap-like candidates:")
    for base, label in ((0, "AAA"), (SLOT, "AAB")):
        slot = two[base : base + SLOT]
        cands = bitmap_candidates(slot)
        lines.append(f"  {label} n_cand={len(cands)} (showing top 20 by |dens-0.25|):")
        cands.sort(key=lambda c: abs(c[3] - 0.25))
        for off, ln, pc, dens in cands[:20]:
            lines.append(f"    @{off}+{base} len={ln} pop={pc} dens={dens:.3f}")

    # T3(c) diff bitmaps at same relative offsets
    lines.append("\nT3(c) bit-diff of 50-byte and 128-byte windows that change:")
    sa = two[0:SLOT]
    sb = two[SLOT : 2 * SLOT]
    for length in (50, 128):
        flipped = []
        for off in range(0, SLOT - length + 1, 2):
            if sa[off : off + length] == sb[off : off + length]:
                continue
            # count flipped bits
            nbit = 0
            idxs = []
            for i, (x, y) in enumerate(zip(sa[off : off + length], sb[off : off + length])):
                xor = x ^ y
                if xor:
                    for bit in range(8):
                        if xor & (1 << bit):
                            nbit += 1
                            idxs.append(i * 8 + bit)
            if 1 <= nbit <= 8:
                flipped.append((off, length, nbit, idxs))
        lines.append(f"  len={length} windows with 1-8 flipped bits: {len(flipped)}")
        for off, ln, nbit, idxs in flipped[:30]:
            lines.append(f"    @{off} flips={nbit} bit_indices={idxs}")
            for bi in idxs:
                lines.append(
                    f"      bit {bi} vs Items {bi in ALCOVE_ITEMS} "
                    f"vs sectors 69/37/5+1*32={(bi in (69, 37, 5 + 1 * 32, 7 + 1 * 32, 7 + 3 * 32))}"
                )

    # T3(d) second 32x32 automap in player record?
    lines.append("\nT3(d) 128-byte windows matching live automap or similar popcount:")
    live_hdr = two[LEVEL_BASE + 25 * STRIDE : LEVEL_BASE + 25 * STRIDE + 256] if LEVEL_BASE + 25 * STRIDE + 256 <= len(two) else b""
    auto = live_hdr[132:260] if len(live_hdr) >= 260 else b""
    auto_pc = popcount_bytes(auto) if auto else 0
    lines.append(f"  live automap[132:260] pop={auto_pc}")
    for base, label in ((0, "AAA"), (SLOT, "AAB")):
        slot = two[base : base + SLOT]
        for off in range(0, SLOT - 128 + 1):
            if auto and slot[off : off + 128] == auto:
                lines.append(f"  {label} EXACT automap copy @{off}")
        # any 128-byte with popcount near 156
        near = []
        for off in range(0, SLOT - 128 + 1, 2):
            pc = popcount_bytes(slot[off : off + 128])
            if 100 <= pc <= 220:
                near.append((off, pc))
        lines.append(f"  {label} 128B windows pop 100-220: {len(near)} first10={near[:10]}")

    # T3(e) knife catalog
    lines.append("\nT3(e) knife catalog FFFF->0003:")
    for base, label in ((0, "AAA"), (SLOT, "AAB")):
        for i in range(20):
            r = rec4(two, INV_OFF + base + i * 8)
            if r[0] == 0x2D:
                lines.append(f"  {label} knife @{INV_OFF+base+i*8} {r}")
    # what is "index 3" — inventory rec 3? dpin? 
    lines.append("  inventory rec[3] AAA/AAB:")
    lines.append(f"    AAA {rec4(two, INV_OFF+3*8)}")
    lines.append(f"    AAB {rec4(two, INV_OFF+SLOT+3*8)}")
    # dump bytes around catalog-as-pointer: if 3 is a table index into player record
    lines.append("  first 16 inv records AAB (catalog as next/link?):")
    for i in range(16):
        r = rec4(two, INV_OFF + SLOT + i * 8)
        lines.append(f"    [{i:02d}] {r} {ITEM_NAMES.get(r[0], '')}")

    # ---- T4 tail and 9112 ----
    lines.append("\n========== TASK 4 tail + 9112 region ==========")
    tail2 = two[276304:]
    tail1_start = LEVEL_BASE + 25 * STRIDE  # 267192
    tail1 = one[tail1_start:] if tail1_start < len(one) else b""
    lines.append(f"T4(a) two-name tail @{276304} len={len(tail2)}")
    lines.append(hexdump_mac_roman(tail2))
    lines.append(f"  one-name tail @{tail1_start} len={len(tail1)}")
    lines.append(hexdump_mac_roman(tail1[:260] if len(tail1) >= 260 else tail1))
    lines.append(f"  tails equal? {tail1[:260]==tail2 if len(tail1)>=260 else 'one shorter'}")
    if len(tail1) >= 260:
        nd = sum(1 for i in range(260) if tail1[i] != tail2[i])
        lines.append(f"  tail diffs={nd}")

    live = two[267192 : 267192 + STRIDE]
    t24 = two[LEVEL_BASE + 24 * STRIDE : LEVEL_BASE + 25 * STRIDE]
    d24 = [i for i in range(STRIDE) if live[i] != t24[i]]
    lines.append(f"\nT4(b) 267192 vs template 24: {len(d24)} differing bytes")
    for s, e in runs_of(d24):
        lines.append(
            f"  [{s}:{e}] ({e-s+1}B) T24={t24[s:e+1].hex(' ')} live={live[s:e+1].hex(' ')}"
        )
    recs_l, _ = live_packed(live)
    recs_t, _ = live_packed(t24)
    lines.append(f"  live recs={len(recs_l)} T24 recs={len(recs_t)}")
    rec_diffs = [(i, ra, rb) for i, ((_, ra), (_, rb)) in enumerate(zip(recs_l, recs_t)) if ra != rb]
    lines.append(f"  packed-list record diffs={len(rec_diffs)}")
    for i, ra, rb in rec_diffs[:20]:
        lines.append(f"    rec[{i}] T24={ra} live={rb}")

    lines.append("\nT4(c) one-name @267192:")
    if tail1_start + 16 <= len(one):
        chunk = one[tail1_start:]
        lines.append(f"  avail={len(chunk)} first16={chunk[:16].hex(' ')}")
        if len(chunk) >= STRIDE:
            t24_1 = one[LEVEL_BASE + 24 * STRIDE : LEVEL_BASE + 25 * STRIDE]
            nd = sum(1 for i in range(STRIDE) if chunk[i] != t24_1[i])
            lines.append(f"  body vs its T24 diffs={nd}")
        else:
            # compare available prefix to T24 header
            t24_1 = one[LEVEL_BASE + 24 * STRIDE : LEVEL_BASE + 24 * STRIDE + len(chunk)]
            nd = sum(1 for i in range(len(chunk)) if chunk[i] != t24_1[i])
            lines.append(f"  {len(chunk)}B vs T24 prefix diffs={nd}")
            # vs r14 live header
            ndh = sum(1 for i in range(min(len(chunk), 256)) if chunk[i] != live[i])
            lines.append(f"  vs r14 live header diffs={ndh}")

    # ---- T5 floors ----
    lines.append("\n========== TASK 5 .256 self-describing literals ==========")
    do_256(lines)

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # print the decisive part first
    start = next(i for i, l in enumerate(lines) if "T1(d)" in l)
    print("\n".join(lines[start : start + 40]))
    print(f"\n... wrote {OUT} ({len(lines)} lines)")


def map_player(data: bytes, base: int, label: str, lines: list[str]) -> None:
    slot = data[base : base + SLOT]
    lines.append(f"\nT3(a) {label} slot @{base} nonzero={sum(1 for b in slot if b)}/{SLOT}")
    known = [
        (0, 128, "name_slot0_or_overlap"),
        (128, 256, "name_slot1_or_overlap"),
        (TIME_OFF, TIME_OFF + 4, "clock"),
        (HP_OFF, HP_OFF + 4, "hp/max"),
        (LEVEL_OFF, LEVEL_OFF + 2, "level"),
        (X_OFF, X_OFF + 2, "X"),
        (Y_OFF, Y_OFF + 2, "Y"),
        (FACING_OFF, FACING_OFF + 4, "facing"),
        (INV_OFF, INV_OFF + 160, "inventory_window"),
    ]
    # walk 16-byte rows, mark known
    i = 0
    while i < SLOT:
        # skip to next nonzero run
        if slot[i] == 0:
            z = i
            while i < SLOT and slot[i] == 0:
                i += 1
            if i - z >= 8:
                lines.append(f"  [{z}:{i}] zeros {i-z}B")
                continue
        j = i
        while j < SLOT and not (slot[j] == 0 and j + 8 <= SLOT and slot[j : j + 8] == b"\x00" * 8):
            j += 1
        if j == i:
            i += 1
            continue
        chunk = slot[i:j]
        tag = ""
        for a, b, name in known:
            if a < j and b > i:
                tag += f" {name}"
        lines.append(f"  [{i}:{j}] {j-i}B nz={sum(1 for x in chunk if x)}{tag}")
        if j - i <= 64:
            lines.append(f"    {chunk.hex(' ')}")
        i = j


def do_256(lines: list[str]) -> None:
    shapes = load_all_256()
    srcs = {rid: shapes[rid][257:] for rid in range(195, 203) if rid in shapes}

    def decode(src: bytes, mode: str) -> bytes:
        """Self-describing literals 0x03-0x10. mode keys listed below."""
        out = bytearray()
        i = 0
        n = len(src)
        prev = 0
        while i < n:
            b = src[i]
            i += 1
            if 0x03 <= b <= 0x10:
                out.append(b)
                prev = b
                continue
            if b >= 0x80:
                if mode in ("rep_prev_7f", "rep_prev_80"):
                    nrep = (b - 0x7F) if mode == "rep_prev_7f" else (b - 0x80)
                    if nrep < 1:
                        nrep = 1
                    out.extend(bytes([prev]) * nrep)
                elif mode in ("rep_next_7f", "rep_next_80"):
                    if i >= n:
                        break
                    val = src[i]
                    i += 1
                    nrep = (b - 0x7F) if mode == "rep_next_7f" else (b - 0x80)
                    if nrep < 1:
                        nrep = 1
                    out.extend(bytes([val]) * nrep)
                    prev = val
                else:
                    # unused
                    if i >= n:
                        break
                    val = src[i]
                    i += 1
                    out.extend(bytes([val]) * ((b & 0x7F) + 1))
                    prev = val
                continue
            if b <= 2:
                if mode.startswith("emit_plus"):
                    # 00 X = twice, 01 = three, 02 = four
                    if i >= n:
                        break
                    val = src[i]
                    i += 1
                    out.extend(bytes([val]) * (b + 2))
                    prev = val
                elif mode.startswith("u16count"):
                    if i + 1 >= n:
                        break
                    # 00/01/02 as high byte of 16-bit count + pixel
                    lo = src[i]
                    i += 1
                    if i >= n:
                        break
                    val = src[i]
                    i += 1
                    cnt = (b << 8) | lo
                    if cnt > 4096:
                        cnt = 4096
                    out.extend(bytes([val]) * max(cnt, 1))
                    prev = val
                else:
                    # treat 00-02 as leftover plus1 literal count for completeness
                    cnt = b + 1
                    take = min(cnt, n - i)
                    out.extend(src[i : i + take])
                    if take:
                        prev = src[i + take - 1]
                    i += take
                continue
            # 0x11, 0x12, 0x13-0x7F: emit as pixel (variant) or skip
            if mode.endswith("_hi_lit") and b in (0x11, 0x12):
                out.append(b)
                prev = b
                continue
            # default: plus1 literals
            cnt = b + 1
            take = min(cnt, n - i)
            out.extend(src[i : i + take])
            if take:
                prev = src[i + take - 1]
            i += take
        return bytes(out)

    modes = [
        "rep_prev_7f",
        "rep_prev_80",
        "rep_next_7f",
        "rep_next_80",
        "emit_plus",
        "u16count",
        "rep_next_7f_hi_lit",
        "rep_next_80_hi_lit",
        "rep_prev_7f_hi_lit",
        "emit_plus_hi_lit",
    ]
    lines.append("T5(a) output lengths (target 33144):")
    hits = []
    for mode in modes:
        for rid in (195, 196, 198):
            out = decode(srcs[rid], mode)
            mark = " HIT" if len(out) == 33144 else ""
            lines.append(f"  {rid} {mode}: {len(out)}{mark}")
            if len(out) == 33144:
                hits.append((rid, mode))

    # also run every mode on 195 only first for speed — already did 195/196/198
    if hits:
        lines.append(f"  EXACT HITS: {hits}")
        mode = hits[0][1]
        for rid in range(195, 203):
            out = decode(srcs[rid], mode)
            lines.append(f"  all {rid} {mode}: {len(out)}")
        # render 195
        blob = load_all_256()[195]
        pal = compact_gray(blob)
        out = decode(srcs[195], mode)
        render_pair(out, pal, SHAPEDIR / "195_a.png", SHAPEDIR / "195_b.png")
        lines.append("  wrote 195_a.png 195_b.png")

    # T5(b) 0x11 / 0x12 in 195
    src = srcs[195]
    lines.append("\nT5(b) 0x11 / 0x12 in 195 packed@257:")
    for val, name in ((0x11, "0x11"), (0x12, "0x12")):
        pos = [i for i, b in enumerate(src) if b == val]
        lines.append(f"  {name} count={len(pos)}")
        before = Counter(src[i - 1] if i else None for i in pos)
        after = Counter(src[i + 1] if i + 1 < len(src) else None for i in pos)
        lines.append(f"    before top={before.most_common(8)}")
        lines.append(f"    after top={after.most_common(8)}")
        # positional: which third of the stream
        n = len(src)
        buckets = [0, 0, 0]
        for i in pos:
            buckets[min(2, i * 3 // n)] += 1
        lines.append(f"    thirds={buckets}")
        # row-ish: if we assume ~128-wide, offset mod 128
        mod = Counter(i % 128 for i in pos)
        lines.append(f"    mod128 top={mod.most_common(6)}")


def render_pair(out: bytes, pal, path_a: Path, path_b: Path) -> None:
    def pix(i: int) -> tuple[int, int, int]:
        v = out[i] if i < len(out) else 0
        if pal[v]:
            return pal[v]
        return (v, v, v)

    for path, start in ((path_a, 0), (path_b, 16384)):
        img = Image.new("RGB", (128, 128))
        px = img.load()
        for y in range(128):
            for x in range(128):
                px[x, y] = pix(start + y * 128 + x)
        img.save(path)


if __name__ == "__main__":
    main()
