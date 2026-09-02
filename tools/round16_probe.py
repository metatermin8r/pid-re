# -*- coding: utf-8 -*-
"""Probe four-name save: find clocks, inventories, level/pos for each slot."""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = (ROOT / "reference/saves/Saved Games r16").read_bytes()
ONE = (ROOT / "reference/saves/Saved Games").read_bytes()
R14 = (ROOT / "reference/saves/Saved Games r14").read_bytes()

CHEAT = {
    0x00: "Map",
    0x01: "Watch",
    0x02: "Flash",
    0x06: "Sack",
    0x16: "MeinKampf",
    0x2D: "Knife",
    0x2E: "Walther",
    0x2F: "Colt",
    0x33: "Wammo",
    0x39: "Cammo",
}


def u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def u32(d, o):
    return struct.unpack_from(">I", d, o)[0]


def rec4(d, o):
    return struct.unpack_from(">4H", d, o)


def dump_inv(d, base, label):
    print(f"\n== {label} inv @{base+2560} ==")
    for i in range(20):
        r = rec4(d, base + 2560 + i * 8)
        if r[0] == 0xFFFF and r[1] > 200:
            print(f"  [{i:02d}] END {r}")
            break
        print(f"  [{i:02d}] {r} {CHEAT.get(r[0], '')}")


def dump_slot(d, base, label):
    clk = u32(d, base + 1866)
    hp, hpm = u16(d, base + 1876), u16(d, base + 1878)
    v750, v752 = u16(d, base + 1872), u16(d, base + 1874)
    lvl, x, y = u16(d, base + 2316), u16(d, base + 2328), u16(d, base + 2330)
    print(
        f"{label} @{base} clk={clk} ({clk/60:.2f}s) 0750={v750} 0752={v752} "
        f"HP={hp}/{hpm} lvl={lvl} xy=({x},{y})"
    )
    # flags
    flags = []
    for off in range(2080, 2200):
        b = d[base + off]
        if b and b != 0xFF:
            flags.append(f"{off}=0x{b:02X}")
    print(f"  flags: {flags}")
    dump_inv(d, base, label)


print(f"file {len(DATA)}")
print("\n======= stride 2876 from 0 =======")
for i in range(4):
    dump_slot(DATA, i * 2876, f"slot{i}")

print("\n======= stride 2876 from 512 (after 4 names) =======")
for i in range(4):
    dump_slot(DATA, 512 + i * 2876, f"n512[{i}]")

print("\n======= search for inventory-shaped 0033 0000 0007/0008 =======")
pat = bytes.fromhex("00330000")
pos = 0
while True:
    j = DATA.find(pat, pos)
    if j < 0:
        break
    rec = rec4(DATA, j)
    print(f"  ammo-like @{j} {rec} {CHEAT.get(rec[0], '')}")
    pos = j + 1

print("\n======= search Walther 002e =======")
pos = 0
while True:
    j = DATA.find(bytes.fromhex("002e0001"), pos)
    if j < 0:
        break
    print(f"  walther @{j} {rec4(DATA, j)}")
    pos = j + 1

print("\n======= clocks as u32be in 0..20000 matching 1000-20000 =======")
for off in range(0, 20000, 2):
    v = u32(DATA, off)
    if 4000 <= v <= 20000:
        # likely clock-ish
        if off % 2876 in (1864, 1866, 1868, 1870) or True:
            pass
# print unique plausible clock sites near 1866 mod 2876
print("offsets where u32 in 5000-15000 and (off%2876) in 1860-1880:")
for off in range(0, min(len(DATA), 40000)):
    if 1860 <= (off % 2876) <= 1880:
        v = u32(DATA, off) if off + 4 <= len(DATA) else 0
        if 1000 <= v <= 30000:
            print(f"  @{off} (slot-ish {off//2876} rem {off%2876}) {v}")
