# -*- coding: utf-8 -*-
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pid_level import load_maps  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
data = (ROOT / "reference/saves/Saved Games r16").read_bytes()
one = (ROOT / "reference/saves/Saved Games").read_bytes()
gf = load_maps(ROOT / "data/hfs/Pathways_1995/Maps")[0]
item_at = {}
for y in range(32):
    for x in range(32):
        s = gf.sector_at(x, y)
        if s.item >= 0:
            item_at[s.item] = (x, y, s.type)

ALCOVE = {43, 44, 45, 53, 57}
A1 = [(2112, 0), (2148, 3)]
A3 = [(2111, 7), (2144, 6), (2147, 6)]


def idx(off, bit, S, order):
    return (off - S) * 8 + (bit if order == "LSB" else 7 - bit)


print("=== T3(a) each A1 bit independently vs alcove ===")
for S in range(2080, 2161):
    for order in ("LSB", "MSB"):
        hits = []
        for o, b in A1:
            i = idx(o, b, S, order)
            if i in ALCOVE:
                hits.append((o, b, i))
        if hits:
            ev = "EVEN" if S % 2 == 0 else "odd"
            print(f"  S={S} {ev} {order} {hits}")

print("=== T3 A3 bits independently vs 114 or 206 ===")
for S in range(2048, 2181):
    for order in ("LSB", "MSB"):
        hits = []
        for o, b in A3:
            i = idx(o, b, S, order)
            if i in (114, 206):
                hits.append((o, b, i))
        if hits:
            ev = "EVEN" if S % 2 == 0 else "odd"
            print(f"  S={S} {ev} {order} {hits}")

print("=== A3 bits as GF Items (even S) ===")
for S in range(2080, 2161, 2):
    for order in ("LSB", "MSB"):
        decoded = []
        for o, b in A3:
            i = idx(o, b, S, order)
            if 0 <= i <= 400 and i in item_at:
                decoded.append((o, i, item_at[i]))
        if decoded:
            print(f"  S={S} {order} {decoded}")

print("=== S=2143 ===")
for order in ("LSB", "MSB"):
    print(order)
    for lab, bits in (("A1", A1), ("A3", A3)):
        for o, b in bits:
            i = idx(o, b, 2143, order)
            print(f"  {lab} @{o} bit{b} -> {i} {item_at.get(i)}")

print("=== mid-game under S=2143 ===")
slot = one[:2876]
for order in ("MSB", "LSB"):
    print(f"-- 2143 {order} --")
    for off in range(2080, 2200):
        bv = slot[off]
        if not bv or bv == 0xFF:
            continue
        for bit in range(8):
            if bv & (1 << bit):
                i = idx(off, bit, 2143, order)
                print(f"  @{off} b{bit} -> {i} {item_at.get(i)}")
