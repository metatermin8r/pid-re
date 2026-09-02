# -*- coding: utf-8 -*-
"""Round 16: solve player-island bit persistence from four named saves."""

from __future__ import annotations

import struct
import sys
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import SECTOR_TYPE_NAME, load_maps  # noqa: E402
from round10_256 import compact_gray, load_all_256  # noqa: E402

FOUR = ROOT / "reference/saves/Saved Games r16"
ONE = ROOT / "reference/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round16_bits.txt"
SHAPEDIR = ROOT / "reference/shapes"

SLOT = 2876
ISLAND0 = 1866
FLAG0, FLAG1 = 2080, 2220
INV0 = 2560
LEVEL_BASE = 39392
STRIDE = 9112

ALCOVE = {43, 44, 45, 53, 57}
CHEAT = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flashlight",
    0x06: "Canvas Sack",
    0x16: "Mein Kampf",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x33: "Walther P4 Ammo",
    0x39: "Colt .45 Ammo",
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


def runs_of(offs: list[int]) -> list[tuple[int, int]]:
    if not offs:
        return []
    out = []
    s = prev = offs[0]
    for o in offs[1:]:
        if o == prev + 1:
            prev = o
        else:
            out.append((s, prev))
            s = prev = o
    out.append((s, prev))
    return out


def classify(off: int) -> str:
    if 1866 <= off <= 1869:
        return "clock"
    if 1870 <= off <= 1875:
        return "u16_0750_0752"
    if 1876 <= off <= 1879:
        return "hp"
    if 2080 <= off < 2220:
        return "flag_region"
    if 2316 <= off <= 2335:
        return "pos_facing"
    if off >= 2560:
        return "inventory"
    return "other"


def new_bits(old: bytes, new: bytes, lo: int, hi: int) -> list[tuple[int, int, int]]:
    """(offset, bit_LSB, bit_MSB) newly set in new vs old."""
    out = []
    for i in range(lo, hi):
        gained = new[i] & ~old[i]
        if not gained:
            continue
        for b in range(8):
            if gained & (1 << b):
                out.append((i, b, 7 - b))
    return out


def cleared_bits(old: bytes, new: bytes, lo: int, hi: int) -> list[tuple[int, int, int]]:
    out = []
    for i in range(lo, hi):
        lost = old[i] & ~new[i]
        if not lost:
            continue
        for b in range(8):
            if lost & (1 << b):
                out.append((i, b, 7 - b))
    return out


def idx_from(off: int, bit_lsb: int, S: int, order: str) -> int:
    if order == "LSB":
        return (off - S) * 8 + bit_lsb
    return (off - S) * 8 + (7 - bit_lsb)


def live_packed(block: bytes, start: int = 256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs
        recs.append(rec)
        off += 8
    return recs


def flood_room(level, sx: int, sy: int) -> list[tuple[int, int]]:
    """Non-void flood. Blocked by void or a solid wall on the shared edge."""
    # wall slots 0..3 guessed as -Y, +X, +Y, -X (common) — also try if type!=0
    # Use: neighbor is reachable if dest is non-void. Then refine: if ANY
    # of the 6 wall types on src looking toward dest is a solid wall (32+),
    # still allow if dest is non-void? User said stop at walls.
    # Conservative: non-void 4-connected. Report size; if huge, apply walls.
    start = (sx, sy)
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy, wsrc, wdst in ((0, -1, 1, 3), (1, 0, 2, 0), (0, 1, 3, 1), (-1, 0, 0, 2)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < 32 and 0 <= ny < 32) or (nx, ny) in seen:
                continue
            dest = level.sector_at(nx, ny)
            if dest.type == 0:
                continue
            src = level.sector_at(x, y)
            # treat wall-type >= 32 on the facing slot as blocking (if 4 walls)
            # 6 walls: use first 4 as cardinal if they look like N/E/S/W
            if wsrc < len(src.walls) and src.walls[wsrc].type >= 32:
                continue
            if wdst < len(dest.walls) and dest.walls[wdst].type >= 32:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return sorted(seen)


def flood_novoid(level, sx: int, sy: int) -> list[tuple[int, int]]:
    seen = {(sx, sy)}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < 32 and 0 <= ny < 32) or (nx, ny) in seen:
                continue
            if level.sector_at(nx, ny).type == 0:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return sorted(seen)


def inv_recs(slot: bytes, n: int = 22) -> list[tuple[int, int, int, int]]:
    return [rec4(slot, INV0 + i * 8) for i in range(n)]


def inv_live(recs: list[tuple[int, int, int, int]]) -> list[tuple[int, tuple[int, int, int, int]]]:
    out = []
    for i, r in enumerate(recs):
        if r[0] == 0xFFFF or r[0] > 0x80:
            continue
        if r == (0, 0, 0, 0):
            continue
        out.append((i, r))
    return out


def main() -> None:
    data = FOUR.read_bytes()
    one = ONE.read_bytes()
    gf = load_maps(MAPS)[0]
    lines: list[str] = []

    # ---- T1 ----
    lines.append("========== TASK 1 four slots ==========")
    expect = 267452 + 3 * STRIDE
    lines.append(f"size={len(data)} expect={expect} match={len(data)==expect}")
    names = []
    for i in range(8):
        off = i * 128
        n = data[off]
        ok = 1 <= n <= 31 and all(32 <= b < 127 for b in data[off + 1 : off + 1 + n])
        nm = pascal(data, off) if ok else ""
        lines.append(f"  name[{i}] @{off} valid={ok} {nm!r}")
        if ok:
            names.append((i, off, nm))

    slots = []
    for i in range(4):
        base = i * SLOT
        sl = data[base : base + SLOT]
        clk = u32(sl, 1866)
        hp, hpm = u16(sl, 1876), u16(sl, 1878)
        lvl, x, y, fac = u16(sl, 2316), u16(sl, 2328), u16(sl, 2330), u16(sl, 2332)
        slots.append(
            {
                "i": i,
                "base": base,
                "sl": sl,
                "clk": clk,
                "hp": hp,
                "hpm": hpm,
                "lvl": lvl,
                "x": x,
                "y": y,
                "fac": fac,
            }
        )
        lines.append(
            f"  slot[{i}] @{base} clock={clk} ({clk/60:.2f}s) HP={hp}/{hpm} "
            f"u16@2316={lvl} pos=({x},{y}) facing={fac}"
        )
        pos16 = " ".join(f"{u16(sl, o):5d}" for o in range(2310, 2340, 2))
        lines.append(f"    u16[2310:2340]={pos16}")

    clocks = [s["clk"] for s in slots]
    lines.append(f"  clocks={clocks} increasing={clocks==sorted(clocks)}")
    if clocks != sorted(clocks):
        lines.append("  *** CLOCK ORDER MISMATCH vs name/slot order ***")
        lines.append("  Names A0..A3 sit in slots 0..3 (inventory confirms).")
        lines.append("  Clocks are A0=6780 < A3=6828 < A2=6910 < A1=7133.")
        lines.append("  NOT remapping — inventory, not clock, identifies the saves.")
        lines.append("  Likely explanation: A1/A2/A3 are branches from A0, or")
        lines.append("  the clock is not a monotonic play-through timer across slots.")

    labels = ["A0", "A1", "A2", "A3"]
    for lab, s in zip(labels, slots):
        s["lab"] = lab
    for a, b in zip(slots, slots[1:]):
        d = b["clk"] - a["clk"]
        lines.append(f"  delta {a['lab']}->{b['lab']}: {d} ticks = {d/60:.2f}s (clock, not play order)")

    # ---- T2 ----
    lines.append("\n========== TASK 2 three island diffs ==========")
    pairs = [("A0", "A1", slots[0], slots[1]), ("A1", "A2", slots[1], slots[2]), ("A2", "A3", slots[2], slots[3])]
    pair_bits = {}
    for a_lab, b_lab, a, b in pairs:
        sa, sb = a["sl"], b["sl"]
        diffs = [i for i in range(ISLAND0, SLOT) if sa[i] != sb[i]]
        lines.append(f"\n----- {a_lab}->{b_lab}: {len(diffs)} differing island bytes -----")
        by = {}
        for s, e in runs_of(diffs):
            cls = classify(s)
            by[cls] = by.get(cls, 0) + (e - s + 1)
            lines.append(
                f"  [{s}:{e}] ({e-s+1}B) {cls} "
                f"{a_lab}={sa[s:e+1].hex(' ')} {b_lab}={sb[s:e+1].hex(' ')}"
            )
        lines.append(f"  class totals: {by}")
        setb = new_bits(sa, sb, FLAG0, FLAG1)
        clrb = cleared_bits(sa, sb, FLAG0, FLAG1)
        pair_bits[(a_lab, b_lab)] = setb
        lines.append(f"  T2(c) newly SET bits (off, LSB, MSB): {setb}")
        lines.append(f"  newly CLEARED bits: {clrb}")
        lines.append(f"  flag hex {a_lab} 2080-2200:")
        lines.append(hexdump_mac_roman(sa[2080:2200]))
        lines.append(f"  flag hex {b_lab} 2080-2200:")
        lines.append(hexdump_mac_roman(sb[2080:2200]))

    b01 = pair_bits[("A0", "A1")]
    b12 = pair_bits[("A1", "A2")]
    b23 = pair_bits[("A2", "A3")]
    lines.append("\nT2(d) shape:")
    lines.append(f"  A0->A1 floor  n_set={len(b01)} bits={b01}")
    lines.append(f"  A1->A2 floor  n_set={len(b12)} bits={b12}")
    lines.append(f"  A2->A3 corpse n_set={len(b23)} bits={b23}")
    same_shape = len(b01) == len(b12) == len(b23)
    lines.append(f"  same bit-count shape: {same_shape}")

    # +36 pairing
    lines.append("\nT3(e) +36 pairing of new bits:")
    for lab, bits in (("A1", b01), ("A2", b12), ("A3", b23)):
        offs = [o for o, _, _ in bits]
        lines.append(f"  {lab} offs={offs}")
        for i, (o1, l1, m1) in enumerate(bits):
            for o2, l2, m2 in bits[i + 1 :]:
                lines.append(
                    f"    {o1} LSB{l1}/MSB{m1} vs {o2} LSB{l2}/MSB{m2} "
                    f"dOff={o2-o1} sameLSB={l1==l2} sameMSB={m1==m2}"
                )

    # ---- T3 solve A1+A3 only, blind-test A2 ----
    lines.append("\n========== TASK 3 bit encoding ==========")
    item_at = {}
    for y in range(32):
        for x in range(32):
            sec = gf.sector_at(x, y)
            if sec.item >= 0:
                item_at[sec.item] = (x, y, sec.type, sec.type_addl)

    recs0 = live_packed(data[LEVEL_BASE : LEVEL_BASE + STRIDE])
    lines.append(f"L0 packed recs={len(recs0)}")

    def models_for(bits: list[tuple[int, int, int]], targets: set[int], kind: str) -> list[tuple]:
        """kind: item | sector | rec."""
        hits = []
        for S in range(2080, 2162, 2):
            for order in ("LSB", "MSB"):
                idxs = [idx_from(o, lb, S, order) for o, lb, _ in bits]
                if any(i < 0 for i in idxs):
                    continue
                if targets & set(idxs):
                    hits.append((S, order, idxs))
        return hits

    # also include odd S for completeness but rank even first
    def all_S_hits(bits, targets):
        hits = []
        for S in range(2080, 2161):
            for order in ("LSB", "MSB"):
                idxs = [idx_from(o, lb, S, order) for o, lb, _ in bits]
                if any(i < 0 for i in idxs):
                    continue
                if targets & set(idxs):
                    hits.append((S, order, idxs, S % 2 == 0))
        return hits

    lines.append("\nT3(a) A1 bits vs alcove Items {43,44,45,53,57}:")
    a1_hits = all_S_hits(b01, ALCOVE)
    for S, order, idxs, even in a1_hits:
        alc = [i for i in idxs if i in ALCOVE]
        lines.append(f"  S={S} {'EVEN' if even else 'odd '} {order} idxs={idxs} alcove_hit={alc}")

    # A1+A3 unique: same (S,order) where A1 hits alcove AND A3 hits 114
    lines.append("\nT3(b) A1+A3 ONLY (A2 held out):")
    a3_item_hits = all_S_hits(b23, {114})
    a3_sec_hits = all_S_hits(b23, {206})
    lines.append(f"  A3 bits vs Item 114: {[(S,o,idx,e) for S,o,idx,e in a3_item_hits]}")
    lines.append(f"  A3 bits vs sector 206: {[(S,o,idx,e) for S,o,idx,e in a3_sec_hits]}")

    def intersect(h1, h3):
        k1 = {(S, order) for S, order, _, _ in h1}
        k3 = {(S, order) for S, order, _, _ in h3}
        return sorted(k1 & k3)

    item_sol = intersect(a1_hits, a3_item_hits)
    lines.append(f"  Item-model (S,order) in A1 AND A3: {item_sol}")

    # sector model: A1 alcove sectors 37,38,39,69,101 and A3=206
    ALC_SEC = {5 + 1 * 32, 6 + 1 * 32, 7 + 1 * 32, 5 + 2 * 32, 7 + 3 * 32}
    a1_sec = all_S_hits(b01, ALC_SEC)
    sec_sol = intersect(a1_sec, a3_sec_hits)
    lines.append(f"  Sector-model A1 alcove secs {ALC_SEC} ∩ A3 206: {sec_sol}")

    # record-index model: which L0 recs have f2 in alcove / 114
    rec_alcove = {i for i, r in enumerate(recs0) if r[2] in ALCOVE or r[0] in ALCOVE or r[1] in ALCOVE or r[3] in ALCOVE}
    rec_114 = {i for i, r in enumerate(recs0) if 114 in r}
    lines.append(f"  L0 recs touching alcove fields: {sorted(rec_alcove)}")
    lines.append(f"  L0 recs touching 114: {sorted(rec_114)}")
    a1_rec = all_S_hits(b01, rec_alcove) if rec_alcove else []
    a3_rec = all_S_hits(b23, rec_114) if rec_114 else []
    rec_sol = intersect(a1_rec, a3_rec) if rec_alcove and rec_114 else []
    lines.append(f"  Record-index model ∩: {rec_sol}")

    # pick unique even solutions first
    def decode_bits(bits, S, order):
        return [idx_from(o, lb, S, order) for o, lb, _ in bits]

    solutions = []
    for S, order in item_sol:
        solutions.append(("item", S, order, decode_bits(b01, S, order), decode_bits(b23, S, order)))
    for S, order in sec_sol:
        solutions.append(("sector", S, order, decode_bits(b01, S, order), decode_bits(b23, S, order)))
    for S, order in rec_sol:
        solutions.append(("record", S, order, decode_bits(b01, S, order), decode_bits(b23, S, order)))

    even_item = [(S, o) for S, o in item_sol if S % 2 == 0]
    lines.append(f"  even Item solutions: {even_item}")
    lines.append(f"  all solutions listed: {solutions}")

    # Blind-test A2
    lines.append("\n***** A2 BLIND TEST *****")
    unique_even_item = even_item
    if len(item_sol) == 1 or len(even_item) == 1:
        S, order = (even_item[0] if len(even_item) == 1 else item_sol[0])
        lines.append(f"  pinned Item solution: S={S} {order}")
        a1i = decode_bits(b01, S, order)
        a2i = decode_bits(b12, S, order)
        a3i = decode_bits(b23, S, order)
        lines.append(f"  A1 idxs={a1i}")
        lines.append(f"  A2 idxs={a2i}  (BLIND)")
        lines.append(f"  A3 idxs={a3i}")
        for idx in a2i:
            loc = item_at.get(idx)
            if loc:
                x, y, t, ta = loc
                tname = SECTOR_TYPE_NAME.get(t, str(t))
                dist = abs(x - 14) + abs(y - 6)
                ok = t == 1 and dist <= 8
                lines.append(
                    f"  A2 Item {idx} -> sector ({x},{y}) type={t} {tname} "
                    f"addl={ta} manhattan_to_14_6={dist} "
                    f"{'PASS' if ok else 'FAIL'}"
                )
            else:
                lines.append(f"  A2 index {idx} has NO Ground Floor Item — FAIL")
        # +36: if two bits, check they encode the SAME index under +36 shift
        if len(b01) >= 2:
            for lab, bits in (("A1", b01), ("A2", b12), ("A3", b23)):
                i0 = idx_from(bits[0][0], bits[0][1], S, order)
                # try other bits as same index in a map at S+36 or S-36
                for o, lb, _ in bits[1:]:
                    i_same = idx_from(o, lb, S, order)
                    i_p36 = idx_from(o, lb, S + 36, order)
                    i_m36 = idx_from(o, lb, S - 36, order)
                    lines.append(
                        f"  {lab} primary={i0} other_sameS={i_same} "
                        f"other_S+36={i_p36} other_S-36={i_m36} "
                        f"match_p36={i0==i_p36} match_m36={i0==i_m36}"
                    )
        # size of map
        lines.append(f"  50-byte Item map would be [{S}:{S+50}]")
        lines.append(f"  32-byte map [{S}:{S+32}]  36-byte [{S}:{S+36}]")
    elif len(item_sol) > 1:
        lines.append(f"  A1+A3 do NOT pin unique Item solution ({len(item_sol)} pairs)")
        lines.append("  even candidates:")
        for S, order in even_item or item_sol:
            lines.append(
                f"    S={S} {order} A1={decode_bits(b01,S,order)} "
                f"A3={decode_bits(b23,S,order)} A2={decode_bits(b12,S,order)}"
            )
        # fallback: room constraint
        room = flood_novoid(gf, 14, 6)
        room_w = flood_room(gf, 14, 6)
        lines.append(f"  nonvoid flood from (14,6): {len(room)} tiles")
        lines.append(f"  wall-aware flood: {len(room_w)} tiles {room_w[:40]}...")
        room_items = []
        for x, y in room_w if len(room_w) < len(room) else room:
            sec = gf.sector_at(x, y)
            if sec.item >= 0 and sec.type == 1:
                room_items.append((sec.item, x, y, sec.type))
        lines.append(f"  Type-1 Items in room: {room_items}")
        room_set = {it for it, *_ in room_items}
        for S, order in even_item or item_sol:
            a2i = decode_bits(b12, S, order)
            if room_set & set(a2i):
                lines.append(f"  FALLBACK HIT S={S} {order} A2={a2i}")
    else:
        lines.append("  NO Item-model (S,order) fits both A1 and A3")
        lines.append("  A1-only hits (incl odd):")
        for S, order, idxs, even in a1_hits:
            lines.append(
                f"    S={S} {'EVEN' if even else 'odd'} {order} A1={idxs} "
                f"A2={decode_bits(b12,S,order)} A3={decode_bits(b23,S,order)}"
            )
        # decode A3 extras under A1's S=2143 if present
        for S, order, idxs, even in a1_hits:
            lines.append(f"  decode ALL A3-vs-A0 bits under S={S} {order}:")
            a0a3 = new_bits(slots[0]["sl"], slots[3]["sl"], FLAG0, FLAG1)
            lines.append(f"    A0->A3 set {a0a3}")
            for o, lb, mb in a0a3:
                idx = idx_from(o, lb, S, order)
                loc = item_at.get(idx)
                lines.append(f"    @{o} LSB{lb} -> {idx} {loc}")

        room = flood_novoid(gf, 14, 6)
        room_w = flood_room(gf, 14, 6)
        lines.append(f"\n  FALLBACK room flood from (14,6): novoid={len(room)} wall-aware={len(room_w)}")
        lines.append("  wall-aware tiles:")
        for x, y in room_w:
            sec = gf.sector_at(x, y)
            mark = ""
            if (x, y) == (14, 6):
                mark = " JOHN_DOE"
            if sec.item in ALCOVE:
                mark += " ALCOVE"
            if sec.type == 1 and sec.item >= 0:
                mark += " CANDIDATE"
            lines.append(
                f"    ({x:2d},{y:2d}) Item={sec.item:4d} type={sec.type} "
                f"{SECTOR_TYPE_NAME.get(sec.type,'?')}{mark}"
            )
        lines.append("  A2 set no new flag bits vs A1 — cannot decode an Item.")
        lines.append("  A2 BLIND TEST: FAIL (no new bit to decode).")

    # always dump A0 vs A3 bits (full loot from baseline)
    a0a3_bits = new_bits(slots[0]["sl"], slots[3]["sl"], FLAG0, FLAG1)
    lines.append(f"\n  A0->A3 all newly set bits: {a0a3_bits}")
    lines.append("  A0->A1 bits should be a subset of A0->A3 if A3 continued from A1.")

    # If we have a solution, decode mid-game
    if len(even_item) == 1 or len(item_sol) == 1:
        S, order = (even_item[0] if len(even_item) == 1 else item_sol[0])
        one_slot = one[0:SLOT]
        a0 = slots[0]["sl"]
        mid_bits = []
        for i in range(S, min(S + 64, SLOT)):
            b = one_slot[i]
            if not b:
                continue
            for bit in range(8):
                if b & (1 << bit):
                    mid_bits.append((i, bit, idx_from(i, bit, S, order)))
        lines.append(f"\nT3(f) mid-game bits from S={S} {order} (64 bytes):")
        taken = []
        for off, bit, idx in mid_bits:
            loc = item_at.get(idx)
            taken.append(idx)
            lines.append(f"  @{off} LSB{bit} -> Item {idx} sector={loc}")
        lines.append(f"  implied taken Items: {taken}")
        lines.append("  mid-game inventory:")
        for i, r in inv_live(inv_recs(one_slot)):
            lines.append(f"    [{i:02d}] {r} {CHEAT.get(r[0], '')}")

        # also list A0 baseline bits in that map
        lines.append("  A0 bits in same map:")
        for i in range(S, min(S + 64, SLOT)):
            b = a0[i]
            for bit in range(8):
                if b & (1 << bit):
                    idx = idx_from(i, bit, S, order)
                    lines.append(f"    @{i} LSB{bit} -> {idx} {item_at.get(idx)}")

    # ---- T4 inventory ----
    lines.append("\n========== TASK 4 inventory ==========")
    recs4 = [inv_recs(s["sl"]) for s in slots]
    lines.append(f"{'slot':<4} " + "  ".join(f"{lab:28s}" for lab in labels))
    for i in range(20):
        row = [recs4[k][i] for k in range(4)]
        if all(r[0] == 0xFFFF and r[1] > 100 for r in row):
            break
        names_r = [CHEAT.get(r[0], "") if r[0] != 0xFFFF else "" for r in row]
        lines.append(f"[{i:02d}] " + "  ".join(f"{r} {n}"[:28].ljust(28) for r, n in zip(row, names_r)))

    for a, b, la, lb in (
        (recs4[0], recs4[1], "A0", "A1"),
        (recs4[1], recs4[2], "A1", "A2"),
        (recs4[2], recs4[3], "A2", "A3"),
    ):
        lines.append(f"\n  {la}->{lb} inventory changes:")
        for i, (ra, rb) in enumerate(zip(a, b)):
            if ra != rb:
                lines.append(f"    [{i:02d}] {ra} -> {rb} {CHEAT.get(rb[0], CHEAT.get(ra[0], ''))}")

    lines.append("\n  catalogs per live record:")
    for s, recs in zip(slots, recs4):
        cats = [(i, r[0], r[3], CHEAT.get(r[0], "")) for i, r in inv_live(recs)]
        lines.append(f"    {s['lab']}: {cats}")

    # ---- T5 0x0750/0752 ----
    lines.append("\n========== TASK 5 0x0750 / 0x0752 ==========")
    vals = []
    for s in slots:
        a = u16(s["sl"], 1872)
        b = u16(s["sl"], 1874)
        u = u32(s["sl"], 1872)
        vals.append((s["lab"], a, b, u, s["clk"]))
        lines.append(f"  {s['lab']} @0750={a} @0752={b} u32be={u} clock={s['clk']}")
        if a < SLOT:
            lines.append(f"    slot[{a}:] hex={s['sl'][a:a+16].hex(' ')}")
        if b < SLOT:
            lines.append(f"    slot[{b}:] hex={s['sl'][b:b+16].hex(' ')}")

    lines.append("\nT5(b) LCG reachability (~100000 iters):")
    # consecutive pairs of the u16s and the u32
    def mac_rand_16807(x: int) -> int:
        return (x * 16807) % 2147483647

    def lcg_ansi(x: int) -> int:
        return (x * 1103515245 + 12345) & 0x7FFFFFFF

    def lcg_16(x: int) -> int:
        return (x * 0x41A7 + 1) & 0xFFFF  # common 16-bit

    def lcg_mac16(x: int) -> int:
        # Toolbox Random uses long seed; 16-bit result is high bits
        return ((x * 16807) & 0xFFFFFFFF) >> 16

    def search(src: int, dst: int, step, mask: int, limit: int = 100000) -> int | None:
        x = src
        for i in range(1, limit + 1):
            x = step(x)
            if (x & mask) == (dst & mask):
                return i
        return None

    for i in range(3):
        la, a0, b0, u0, c0 = vals[i]
        lb, a1, b1, u1, c1 = vals[i + 1]
        lines.append(f"  {la}->{lb}:")
        for name, fn, mask, src, dst in (
            ("16807mod u32", mac_rand_16807, 0x7FFFFFFF, u0, u1),
            ("ansi u32", lcg_ansi, 0x7FFFFFFF, u0, u1),
            ("16807mod 0750", mac_rand_16807, 0xFFFF, a0, a1),
            ("ansi 0750", lcg_ansi, 0xFFFF, a0, a1),
            ("16bit 0750", lcg_16, 0xFFFF, a0, a1),
            ("16bit 0752", lcg_16, 0xFFFF, b0, b1),
            ("16807mod 0752", mac_rand_16807, 0xFFFF, b0, b1),
        ):
            n = search(src, dst, fn, mask)
            lines.append(f"    {name} {src}->{dst}: {n if n is not None else 'not in 1e5'}")

    lines.append("\nT5(d) A0->A1 is combat-free (Headless already dead).")
    lines.append(f"  0750 moved {vals[0][1]}->{vals[1][1]}  0752 {vals[0][2]}->{vals[1][2]}")
    lines.append("  fields move without combat => timer more likely than combat RNG.")

    # monster frequency from GF header
    lines.append(f"  GF monster list: {gf.monster_list}")

    # ---- T6 .256 ----
    lines.append("\n========== TASK 6 .256 widened literals ==========")
    do_256(lines)

    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    start = text.find("========== TASK 2")
    end = text.find("========== TASK 4")
    if start >= 0:
        print(text[start:end if end > start else None])
    print(f"\n... wrote {OUT} ({len(lines)} lines)")


def dump_195_table(blob: bytes, lines: list[str]) -> list[int]:
    """Dump every compact + Mac clut index 195 defines. Return defined indices."""
    defined = []
    lines.append("T6(a) resource 195 colour table (no idx>40 cutoff):")
    p = 29
    while p + 5 <= min(len(blob), 400):
        idx = struct.unpack_from(">H", blob, p)[0]
        kind = blob[p + 2]
        val = blob[p + 3]
        trail = blob[p + 4]
        if idx > 255 or kind not in (3, 4):
            lines.append(f"  stop compact @{p} idx={idx} kind={kind}")
            break
        defined.append(idx)
        lines.append(f"  compact @{p} idx={idx} kind={kind} gray=0x{val:02X} trail=0x{trail:02X}")
        p += 5
    # mac clut
    i = 23
    n = len(blob)
    while i + 8 <= min(n, 800):
        idx, r, g, b = struct.unpack_from(">HHHH", blob, i)
        if idx <= 255 and (r >> 8) == (r & 0xFF) and (g >> 8) == (g & 0xFF) and (b >> 8) == (b & 0xFF):
            pos = i
            prev = idx - 1
            while pos + 8 <= n:
                ix, rr, gg, bb = struct.unpack_from(">HHHH", blob, pos)
                if ix > 255 or ix != prev + 1:
                    break
                if (rr >> 8) != (rr & 0xFF):
                    break
                defined.append(ix)
                lines.append(f"  macclut @{pos} idx={ix} rgb=({rr>>8},{gg>>8},{bb>>8})")
                prev = ix
                pos += 8
            if pos == i:
                i += 1
            else:
                i = pos
        else:
            i += 1
    lines.append(f"  defined indices: {sorted(set(defined))}")
    return sorted(set(defined))


def decode_wide(src: bytes, lit_hi: int, rep: str, low: str) -> bytes:
    out = bytearray()
    i = 0
    n = len(src)
    prev = 0
    while i < n:
        b = src[i]
        i += 1
        if 0x03 <= b <= lit_hi:
            out.append(b)
            prev = b
            continue
        if b >= 0x80:
            if rep.startswith("prev"):
                nrep = (b - 0x7F) if rep == "prev7f" else (b - 0x80)
                if nrep < 1:
                    nrep = 1
                out.extend(bytes([prev]) * nrep)
            else:
                if i >= n:
                    break
                val = src[i]
                i += 1
                nrep = (b - 0x7F) if rep == "next7f" else (b - 0x80)
                if nrep < 1:
                    nrep = 1
                out.extend(bytes([val]) * nrep)
                prev = val
            continue
        if b <= 2:
            if low == "emit_plus":
                if i >= n:
                    break
                val = src[i]
                i += 1
                out.extend(bytes([val]) * (b + 2))
                prev = val
            elif low == "op_next":
                # leftover from best-so-far: 00/01/02 + pixel, count = b+2
                if i >= n:
                    break
                val = src[i]
                i += 1
                out.extend(bytes([val]) * (b + 2))
                prev = val
            else:
                if i + 1 >= n:
                    break
                lo = src[i]
                i += 1
                val = src[i]
                i += 1
                cnt = min((b << 8) | lo, 8192)
                out.extend(bytes([val]) * max(cnt, 1))
                prev = val
            continue
        # above lit_hi and < 0x80: treat as plus1 leftover
        cnt = b + 1
        take = min(cnt, n - i)
        out.extend(src[i : i + take])
        if take:
            prev = src[i + take - 1]
        i += take
    return bytes(out)


def do_256(lines: list[str]) -> None:
    shapes = load_all_256()
    blob = shapes[195]
    defined = dump_195_table(blob, lines)
    lit_hi = max((i for i in defined if i <= 0x20), default=0x10)
    lines.append(f"  widened literal high = 0x{lit_hi:02X}")

    srcs = {rid: shapes[rid][257:] for rid in range(195, 203) if rid in shapes}
    schemes = [
        ("next80", "emit_plus"),
        ("next80", "op_next"),
        ("next7f", "emit_plus"),
        ("prev80", "emit_plus"),
        ("prev7f", "emit_plus"),
        ("next80", "u16count"),
    ]
    lines.append("\nT6(b) 195 widened:")
    hits = []
    for rep, low in schemes:
        for hi in (0x12, lit_hi if lit_hi != 0x12 else 0x12):
            out = decode_wide(srcs[195], hi, rep, low)
            mark = " HIT" if len(out) == 33144 else ""
            lines.append(f"  195 lit..{hi:02X} {rep}+{low}: {len(out)}{mark}")
            if len(out) == 33144:
                hits.append((hi, rep, low))

    lines.append("\nT6(c) top schemes on 195-202:")
    top = [("next80", "emit_plus"), ("next80", "op_next"), ("next7f", "emit_plus")]
    for rid in range(195, 203):
        for rep, low in top:
            out = decode_wide(srcs[rid], 0x12, rep, low)
            mark = " HIT" if len(out) == 33144 else ""
            lines.append(f"  {rid} {rep}+{low} lit..12: {len(out)}{mark}")
            if len(out) == 33144:
                hits.append((0x12, rep, low, rid))

    if hits:
        lines.append(f"  HITS={hits}")
        # render 195 if it hit
        hit195 = [h for h in hits if (len(h) == 3) or (len(h) == 4 and h[3] == 195)]
        if hit195:
            h = hit195[0]
            hi, rep, low = h[0], h[1], h[2]
            pal = compact_gray(blob)
            # also paint 0x11/0x12 if defined
            out = decode_wide(srcs[195], hi, rep, low)
            render_pair(out, pal, SHAPEDIR / "195_a.png", SHAPEDIR / "195_b.png")
            lines.append("  wrote 195_a.png 195_b.png")
    else:
        lines.append("  no 33144 hit")


def render_pair(out: bytes, pal, path_a: Path, path_b: Path) -> None:
    def pix(i: int) -> tuple[int, int, int]:
        v = out[i] if i < len(out) else 0
        if v < 256 and pal[v]:
            return pal[v]
        return (v & 0xFF, v & 0xFF, v & 0xFF)

    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    for path, start in ((path_a, 0), (path_b, 16384)):
        img = Image.new("RGB", (128, 128))
        px = img.load()
        for y in range(128):
            for x in range(128):
                px[x, y] = pix(start + y * 128 + x)
        img.save(path)


if __name__ == "__main__":
    main()
