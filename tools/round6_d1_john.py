# -*- coding: utf-8 -*-
"""Find dpin groups matching John Doe / Ground Floor loot; try alt indexes."""

from __future__ import annotations

import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pid_level import load_maps  # noqa: E402

DPIN = ROOT / "reference/dpin_128.bin"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
PREFIX = 596
GROUP = 80
N = 2876
OUT = ROOT / "reference/docs/round6_d1_john.txt"

ITEM = {
    0x16: "MeinKampf",
    0x2E: "WaltherP4",
    0x33: "WaltherAmmo",
    0x41: "BlueCrystal",
    0x40: "YellowCrystal",
    0x28: "Emerald",
}


def group_ids(chunk: bytes) -> list[int]:
    return [chunk[i * 8 + 1] for i in range(10)]


def group_qtys(chunk: bytes) -> list[int]:
    return [chunk[i * 8 + 5] for i in range(10)]


def main() -> None:
    dpin = DPIN.read_bytes()
    levels = load_maps(MAPS)
    lines = []

    # groups containing multiple of {0x16, 0x2E, 0x33}
    lines.append("== groups with 2+ of {MeinKampf, Walther, Ammo} at byte1 ==")
    for g in range(N):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        ids = group_ids(chunk)
        have = {i for i in (0x16, 0x2E, 0x33) if i in ids}
        if len(have) >= 2:
            qtys = group_qtys(chunk)
            named = [f"{ITEM.get(i, f'{i:02x}')}@{s}q={qtys[s]}" for s, i in enumerate(ids) if i in ITEM]
            lines.append(f"  g={g} have={sorted(have)} {named} ids={[f'{i:02x}' for i in ids]}")

    # ammo qty==8 (0x08) anywhere as byte5 with id 0x33 at byte1
    lines.append("\n== Walther ammo slots with qty byte5 in {4,5,6,7,8} ==")
    for g in range(N):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        for s in range(10):
            sl = chunk[s * 8 : (s + 1) * 8]
            if sl[1] == 0x33 and sl[5] in (4, 5, 6, 7, 8):
                lines.append(f"  g={g} s={s} {sl.hex(' ')}")

    # qty as u16be field 2 (bytes 4-5) == 8 with id u16be field 0 == 0x33
    lines.append("\n== u16be (id,state,qty,cat) with id==0x33 and qty in {3,4,5,6,7,8} ==")
    n = 0
    for g in range(N):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        for s in range(10):
            a, b, c, d = struct.unpack_from(">4H", chunk, s * 8)
            if a == 0x33 and c in (3, 4, 5, 6, 7, 8):
                lines.append(f"  g={g} s={s} ({a},{b},{c},{d})")
                n += 1
    lines.append(f"count={n}")

    # alt index: 8-byte slot at 596+item*8
    lines.append("\n== alt: 8-byte slot at PREFIX+Item*8 for GF unique items 42,53 and corpse 114 ==")
    for it in (42, 53, 114, 0, 1):
        off = PREFIX + it * 8
        sl = dpin[off : off + 8]
        a, b, c, d = struct.unpack(">4H", sl)
        lines.append(f"  item={it} off={off} {sl.hex(' ')} u16=({a},{b},{c},{d}) id_b1={sl[1]:02x} qty_b5={sl[5]}")

    # alt: 16-byte at PREFIX+Item*16
    lines.append("\n== alt: 16-byte at PREFIX+Item*16 ==")
    for it in (42, 53, 114):
        off = PREFIX + it * 16
        sl = dpin[off : off + 16]
        lines.append(f"  item={it} off={off} {sl.hex(' ')}")

    # which Sector.Item values on Type==1 Ground Floor decode as inventory-shaped
    # (first u16 <= 0x46 and third u16 in 1..255)
    gf = levels[0]
    lines.append("\n== GF Type==1 Item groups that look like inventory (u16 id<=0x46, qty 1..255) ==")
    hits = 0
    for si, sec in enumerate(gf.sector_list):
        if sec.type != 1 or sec.item < 0:
            continue
        chunk = dpin[PREFIX + sec.item * GROUP : PREFIX + (sec.item + 1) * GROUP]
        inv = []
        for s in range(10):
            a, b, c, d = struct.unpack_from(">4H", chunk, s * 8)
            if a <= 0x46 and 1 <= c <= 255:
                inv.append((a, b, c, d))
        if inv:
            hits += 1
            lines.append(f"  ({si%32},{si//32}) item={sec.item} {inv}")
    lines.append(f"such_sectors={hits}")

    # How many groups 0-399 look inventory-shaped vs coordinate-shaped vs empty
    lines.append("\n== classify groups 0-399 ==")
    cls = defaultdict(int)
    for g in range(400):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        inv_slots = 0
        coordish = 0
        empty = 0
        for s in range(10):
            a, b, c, d = struct.unpack_from(">4H", chunk, s * 8)
            sl = chunk[s * 8 : s * 8 + 8]
            if sl == b"\x00" * 8 or (a, b, c) == (0, 0, 0) and d in (0, 0xFFFE, 0xFFFF):
                empty += 1
            elif a <= 0x46 and c <= 255:
                inv_slots += 1
            else:
                coordish += 1
        if inv_slots >= 3:
            cls["inventory"] += 1
        elif empty >= 8:
            cls["empty"] += 1
        else:
            cls["other"] += 1
    lines.append(dict(cls).__repr__())

    # corpse Item values
    lines.append("\n== corpse Sector.Item ==")
    for li, lev in enumerate(levels):
        for si, sec in enumerate(lev.sector_list):
            if sec.type == 6:
                chunk = dpin[PREFIX + sec.item * GROUP : PREFIX + (sec.item + 1) * GROUP]
                ids = group_ids(chunk)
                qtys = group_qtys(chunk)
                lines.append(
                    f"  L{li:02d} {lev.name!r} addl={sec.type_addl} item={sec.item} "
                    f"ids={[f'{i:02x}' for i in ids]} qtys={qtys}"
                )

    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
