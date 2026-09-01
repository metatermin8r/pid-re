# -*- coding: utf-8 -*-
"""D1 refinement: field layout, search for known item IDs, per-type Item stats."""

from __future__ import annotations

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DPIN = ROOT / "reference/dpin_128.bin"
OUT = ROOT / "reference/docs/round6_d1_refine.txt"
PREFIX = 596
GROUP = 80
N_GROUPS = 2876

# ItemCheatFile IDs of interest
WANTED = {
    0x16: "Mein Kampf",
    0x2E: "Walther P4",
    0x33: "Walther P4 Ammo",
    0x41: "Blue Crystal",
    0x28: "Emerald",
    0x23: "Silver Bowl",
    0x40: "Yellow Crystal",
}


def slots_u16(chunk: bytes) -> list[tuple[int, int, int, int]]:
    return [struct.unpack_from(">4H", chunk, i * 8) for i in range(10)]


def slots_bytes(chunk: bytes) -> list[bytes]:
    return [chunk[i * 8 : (i + 1) * 8] for i in range(10)]


def main() -> None:
    dpin = DPIN.read_bytes()
    levels = load_maps(MAPS)
    lines: list[str] = []

    # --- Item by sector type ---
    by_type: dict[int, list[int]] = defaultdict(list)
    all_items: list[int] = []
    for lev in levels:
        for sec in lev.sector_list:
            if sec.item != -1:
                by_type[sec.type].append(sec.item)
                all_items.append(sec.item)
    lines.append("== Item by sector type ==")
    for t in sorted(by_type):
        vals = by_type[t]
        lines.append(
            f"  type={t} {SECTOR_TYPE_NAME.get(t)} n={len(vals)} "
            f"unique={len(set(vals))} min={min(vals)} max={max(vals)}"
        )
    none_count = sum(
        1 for lev in levels for sec in lev.sector_list if sec.item == -1
    )
    lines.append(f"item==-1 count={none_count} item!=-1={len(all_items)}")

    # unique Item values that appear on Type==1 only
    t1 = set(by_type[1])
    others = set()
    for t, vals in by_type.items():
        if t != 1:
            others.update(vals)
    lines.append(f"type1_only_item_ids={sorted(t1 - others)[:80]} count={len(t1-others)}")
    lines.append(f"shared_with_other_types={len(t1 & others)}")

    # Ground Floor: type==1 items that are unique on that level (candidate pickups)
    gf = levels[0]
    gf_items = [
        (i, i % 32, i // 32, sec.type, sec.item)
        for i, sec in enumerate(gf.sector_list)
        if sec.item != -1
    ]
    freq = Counter(x[4] for x in gf_items)
    lines.append("\n== Ground Floor Item frequencies ==")
    for val, n in freq.most_common():
        locs = [(x, y, t) for _, x, y, t, it in gf_items if it == val]
        lines.append(f"  item={val:4d} n={n:3d} locs={locs[:8]}{'...' if n>8 else ''}")

    # --- dump group 42 raw ---
    off42 = PREFIX + 42 * GROUP
    chunk42 = dpin[off42 : off42 + GROUP]
    lines.append(f"\n== group 42 raw @ {off42} ==")
    lines.append(chunk42.hex(" "))
    lines.append("as 10 x 8 bytes (id@1 state@3 qty@5 cat@7 per ItemCheatFile):")
    for i, sl in enumerate(slots_bytes(chunk42)):
        lines.append(
            f"  [{i}] {sl.hex(' ')}  b1={sl[1]:02x} b3={sl[3]:02x} "
            f"b5={sl[5]:02x} b7={sl[7]:02x}  "
            f"hi={sl[0]:02x}/{sl[2]:02x}/{sl[4]:02x}/{sl[6]:02x}"
        )

    # --- search all groups for wanted item IDs at byte1 and byte0 ---
    hits_b1: dict[int, list[int]] = defaultdict(list)
    hits_b0: dict[int, list[int]] = defaultdict(list)
    hits_u16_low: dict[int, list[int]] = defaultdict(list)
    hits_u16_hi: dict[int, list[int]] = defaultdict(list)
    qty_hits: list[tuple[int, int, int, int, int]] = []  # gid, slot, idpos, id, qty

    for g in range(N_GROUPS):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        for s, sl in enumerate(slots_bytes(chunk)):
            if sl[1] in WANTED:
                hits_b1[sl[1]].append(g)
            if sl[0] in WANTED:
                hits_b0[sl[0]].append(g)
            a, b, c, d = struct.unpack(">4H", sl)
            if (a & 0xFF) in WANTED:
                hits_u16_low[a & 0xFF].append(g)
            if (a >> 8) in WANTED:
                hits_u16_hi[a >> 8].append(g)
            # qty candidates: if id at byte1 and qty at byte5
            if sl[1] in WANTED and sl[5] in (3, 4, 5, 6, 7, 8):
                qty_hits.append((g, s, 1, sl[1], sl[5]))
            if sl[0] in WANTED and sl[4] in (3, 4, 5, 6, 7, 8):
                qty_hits.append((g, s, 0, sl[0], sl[4]))
            if sl[0] in WANTED and sl[5] in (3, 4, 5, 6, 7, 8):
                qty_hits.append((g, s, 1, sl[0], sl[5]))

    lines.append("\n== dpin search wanted IDs (unique groups) ==")
    for k, name in WANTED.items():
        lines.append(
            f"  {k:02X} {name}: byte1={len(set(hits_b1[k]))} "
            f"byte0={len(set(hits_b0[k]))} "
            f"u16low0={len(set(hits_u16_low[k]))} "
            f"u16hi0={len(set(hits_u16_hi[k]))}"
        )
        b1g = sorted(set(hits_b1[k]))
        b0g = sorted(set(hits_b0[k]))
        if b1g[:15]:
            lines.append(f"    byte1 groups[:15]={b1g[:15]}")
        if b0g[:15]:
            lines.append(f"    byte0 groups[:15]={b0g[:15]}")

    lines.append(f"\n== slots with wanted id AND qty in {{3..8}} count={len(qty_hits)} ==")
    for row in qty_hits[:80]:
        lines.append(f"  group={row[0]} slot={row[1]} id_at_byte{row[2]} id={row[3]:02X} qty={row[4]}")

    # Do any of those groups appear as Ground Floor Sector.Item?
    gf_item_set = {it for *_, it in gf_items}
    qg = {g for g, *_ in qty_hits}
    lines.append(f"\nqty-hit groups ? Ground Floor Item: {sorted(qg & gf_item_set)}")

    # Decode those intersecting groups + a few corpse groups
    decode_ids = sorted(qg & gf_item_set)
    # also first 5 groups that contain 0x33 at byte1
    ammo_g = sorted(set(hits_b1[0x33]))[:8]
    walth_g = sorted(set(hits_b1[0x2E]))[:8]
    decode_ids = sorted(set(decode_ids) | set(ammo_g) | set(walth_g) | {42, 114, 0, 1})

    lines.append("\n== decode selected groups (byte1=id byte3=st byte5=qty byte7=cat) ==")
    used_on = defaultdict(list)
    for li, lev in enumerate(levels):
        for si, sec in enumerate(lev.sector_list):
            if sec.item in decode_ids:
                used_on[sec.item].append(
                    (li, lev.name, si % 32, si // 32, sec.type)
                )

    for g in decode_ids:
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        lines.append(f"\ngroup {g} used_on={used_on.get(g, [])[:6]}")
        for i, sl in enumerate(slots_bytes(chunk)):
            if sl == b"\x00" * 8 or sl == b"\xff" * 8:
                continue
            emptyish = sl[1] == 0 and sl[5] == 0 and sl[3] == 0
            name = WANTED.get(sl[1], "")
            lines.append(
                f"  [{i}] {sl.hex(' ')} id={sl[1]:02x} st={sl[3]:02x} "
                f"qty={sl[5]} cat={sl[7]:02x} {name}"
            )
            if emptyish and sl != b"\x00" * 8:
                a, b, c, d = struct.unpack(">4H", sl)
                lines.append(f"       u16be=({a},{b},{c},{d})")

    # How many of 2876 groups have any byte1 in 0x00-0x46 (plausible item id)
    # excluding empty 00/00/00/00 and ff
    plausible = 0
    empty = 0
    for g in range(N_GROUPS):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        ids = [chunk[i * 8 + 1] for i in range(10)]
        if all(chunk[i * 8 : i * 8 + 8] in (b"\x00" * 8, b"\xff" * 8) for i in range(10)):
            empty += 1
            continue
        if any(0x00 <= b <= 0x46 for b in ids if b):
            plausible += 1
    lines.append(f"\nempty_or_ff_groups={empty} plausible_itemid_byte1={plausible}")

    # 4th u16 == ffff rate (previous measurement)
    ffff4 = 0
    total_slots = 0
    for g in range(N_GROUPS):
        chunk = dpin[PREFIX + g * GROUP : PREFIX + (g + 1) * GROUP]
        for i in range(10):
            total_slots += 1
            if chunk[i * 8 + 6 : i * 8 + 8] == b"\xff\xff":
                ffff4 += 1
    lines.append(f"slot4_ffff={ffff4}/{total_slots} = {ffff4/total_slots:.3f}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
