# -*- coding: utf-8 -*-
"""Task 1: per-level Item uniqueness. Task 2: unknown1 checksum hunt."""

from __future__ import annotations

import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import RECORD_SIZE, SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DESC = ROOT / "reference/docs/hfs_Pathways_Extras_PIDMaps_Folder_Descriptions.txt"
OUT = ROOT / "reference/docs/round7_item_checksum.txt"

UNKNOWN_OFF = 0x86
UNKNOWN_LEN = 8
SECTOR_OFF = 0x1C2
HEADER_SIZE = 450


def crc16(data: bytes, poly: int, init: int, xorout: int = 0, refin: bool = False, refout: bool = False) -> int:
    crc = init
    for byte in data:
        if refin:
            byte = int(f"{byte:08b}"[::-1], 2)
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    if refout:
        crc = int(f"{crc:016b}"[::-1], 2)
    return crc ^ xorout


def sum_u16be(data: bytes) -> int:
    n = len(data) // 2
    if n:
        total = sum(struct.unpack(f">{n}H", data[: n * 2]))
    else:
        total = 0
    if len(data) % 2:
        total += data[-1] << 8
    return total & 0xFFFF


def xor_u16be(data: bytes) -> int:
    n = len(data) // 2
    acc = 0
    if n:
        for v in struct.unpack(f">{n}H", data[: n * 2]):
            acc ^= v
    if len(data) % 2:
        acc ^= data[-1] << 8
    return acc & 0xFFFF


def sum_bytes(data: bytes) -> int:
    return sum(data) & 0xFFFF


def parse_desc_i(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        m = re.search(r"(\d+)i\s*$", line.strip())
        if m and not line.startswith("\t"):
            out[line.strip()] = int(m.group(1))
    return out


def match_desc(name: str, desc_i: dict[str, int]) -> tuple[str | None, int | None]:
    key = re.sub(r"[^a-z0-9]+", "", name.lower())[:14]
    for title, n in desc_i.items():
        tk = re.sub(r"[^a-z0-9]+", "", title.lower())
        if key and key in tk:
            return title, n
        if tk[:10] and tk[:10] in key:
            return title, n
    return None, None


def main() -> None:
    raw = MAPS.read_bytes()
    levels = load_maps(MAPS)
    desc_i = parse_desc_i(DESC.read_text(encoding="utf-8"))
    lines: list[str] = []

    # ----- Task 1 -----
    lines.append("== T1(a) per-level Item uniqueness ==")
    all_used: set[int] = set()
    type_by_item: dict[int, set[int]] = defaultdict(set)
    global_item_types: dict[int, Counter] = defaultdict(Counter)
    any_dups = False
    for li, lev in enumerate(levels):
        vals = []
        locs = defaultdict(list)
        for si, sec in enumerate(lev.sector_list):
            if sec.item != -1:
                vals.append(sec.item)
                locs[sec.item].append((si % 32, si // 32, sec.type, SECTOR_TYPE_NAME[sec.type]))
                all_used.add(sec.item)
                type_by_item[sec.item].add(sec.type)
                global_item_types[sec.type][sec.item] += 1
        distinct = set(vals)
        dups = {k: v for k, v in locs.items() if len(v) > 1}
        if dups:
            any_dups = True
        lines.append(
            f"L{li:02d} {lev.name!r:42s} n={len(vals):4d} distinct={len(distinct):4d} "
            f"unique={len(vals)==len(distinct)}"
        )
        for val, spots in sorted(dups.items()):
            lines.append(f"    DUP item={val} {spots}")
    lines.append(f"ANY_LEVEL_HAS_DUPLICATES={any_dups}")

    lines.append("\n== T1(b) min/max / 0..399 coverage ==")
    for li, lev in enumerate(levels):
        vals = [s.item for s in lev.sector_list if s.item != -1]
        if not vals:
            lines.append(f"L{li:02d} empty")
            continue
        used = set(vals)
        span = max(vals) - min(vals) + 1
        holes = [i for i in range(min(vals), max(vals) + 1) if i not in used]
        lines.append(
            f"L{li:02d} min={min(vals):3d} max={max(vals):3d} n={len(vals):3d} "
            f"distinct={len(used):3d} span={span:3d} holes_in_span={len(holes)} "
            f"used_of_0_399={len(used & set(range(400)))} "
            f"contiguous_0_N={min(vals)==0 and not holes}"
        )

    lines.append("\n== T1(c) vs Descriptions Ni ==")
    lines.append(f"desc headers parsed: {len(desc_i)}")
    for li, lev in enumerate(levels):
        all_n = sum(1 for s in lev.sector_list if s.item != -1)
        t1 = sum(1 for s in lev.sector_list if s.item != -1 and s.type == 1)
        title, ni = match_desc(lev.name, desc_i)
        flag = ""
        if ni is not None:
            if all_n == ni:
                flag = " MATCH_ALL"
            elif t1 == ni:
                flag = " MATCH_TYPE1"
            else:
                flag = f" no_match all-Ni={all_n-ni} t1-Ni={t1-ni}"
        lines.append(
            f"L{li:02d} {lev.name!r:42s} Item!=-1={all_n:3d} Type1+Item={t1:3d} "
            f"desc={ni} {title!r}{flag}"
        )

    lines.append("\n== T1(d) Item value vs sector Type (global) ==")
    for t in range(10):
        items = sorted(global_item_types[t])
        if not items:
            lines.append(f"  type={t} {SECTOR_TYPE_NAME[t]} none")
            continue
        lines.append(
            f"  type={t} {SECTOR_TYPE_NAME[t]:16s} n={sum(global_item_types[t].values()):4d} "
            f"unique={len(items):3d} min={items[0]} max={items[-1]}"
        )
    mixed = {v: ts for v, ts in type_by_item.items() if len(ts) > 1}
    lines.append(f"Item values used with >1 sector type: {len(mixed)}")
    # sample
    for v, ts in list(sorted(mixed.items()))[:15]:
        lines.append(f"  item={v} types={sorted(ts)}")

    lines.append("\n== T1(e) unused 376,377,378,383,393 ==")
    unused_reported = {376, 377, 378, 383, 393}
    for v in sorted(unused_reported):
        users = []
        for li, lev in enumerate(levels):
            for si, sec in enumerate(lev.sector_list):
                if sec.item == v:
                    users.append((li, lev.name, si % 32, si // 32, sec.type))
        lines.append(f"  {v}: used={bool(users)} {users}")
    unused_global = sorted(set(range(400)) - all_used)
    lines.append(f"globally unused in 0..399: {unused_global}")

    # ----- Task 2 -----
    lines.append("\n== T2 stored unknown1 ==")
    stored = []
    for i in range(25):
        rec = raw[i * RECORD_SIZE : (i + 1) * RECORD_SIZE]
        a, b = struct.unpack_from(">2i", rec, UNKNOWN_OFF)
        a16 = a & 0xFFFF
        b16 = b & 0xFFFF
        stored.append((a, b, a16, b16))
        hi0 = (a >> 16) == 0 and (b >> 16) == 0
        lines.append(
            f"L{i:02d} i32=({a},{b}) u16=({a16},{b16}) hex=({a16:#06x},{b16:#06x}) "
            f"high_words_zero={hi0} bytes={rec[UNKNOWN_OFF:UNKNOWN_OFF+8].hex(' ')}"
        )

    expected = {
        0: (16857, 11485),
        1: (14745, 24384),
        2: (28551, 2560),
        24: (13354, 17840),
    }
    lines.append("\n== T2 expected-spot check ==")
    for i, (ea, eb) in expected.items():
        a, b, a16, b16 = stored[i]
        lines.append(
            f"  rec{i} stored_u16=({a16},{b16}) expected=({ea},{eb}) "
            f"match=({a16==ea},{b16==eb})"
        )

    def ranges(rec: bytes) -> dict[str, bytes]:
        return {
            "sectors": rec[SECTOR_OFF:],
            "whole_ex_unk": rec[:UNKNOWN_OFF] + rec[UNKNOWN_OFF + UNKNOWN_LEN :],
            "name": rec[:128],
            "header": rec[:HEADER_SIZE],
            "header_ex_unk": rec[:UNKNOWN_OFF] + rec[UNKNOWN_OFF + UNKNOWN_LEN : HEADER_SIZE],
        }

    funcs = {
        "sum_u16": sum_u16be,
        "xor_u16": xor_u16be,
        "sum_bytes": sum_bytes,
        "crc16_ccitt_ffff": lambda d: crc16(d, 0x1021, 0xFFFF),
        "crc16_ccitt_0000": lambda d: crc16(d, 0x1021, 0x0000),
        "crc16_ccitt_1d0f": lambda d: crc16(d, 0x1021, 0x1D0F),
        "crc16_ibm_0000": lambda d: crc16(d, 0x8005, 0x0000),
        "crc16_ibm_ffff": lambda d: crc16(d, 0x8005, 0xFFFF),
        "crc16_ibm_reflected": lambda d: crc16(d, 0x8005, 0x0000, refin=True, refout=True),
    }

    lines.append("\n== T2 checksum hunt (match all 25 against either stored u16) ==")
    hits = []
    for rname in ("sectors", "whole_ex_unk", "name", "header", "header_ex_unk"):
        for fname, fn in funcs.items():
            match_a = 0
            match_b = 0
            vals = []
            for i in range(25):
                rec = raw[i * RECORD_SIZE : (i + 1) * RECORD_SIZE]
                v = fn(ranges(rec)[rname])
                vals.append(v)
                if v == stored[i][2]:
                    match_a += 1
                if v == stored[i][3]:
                    match_b += 1
            lines.append(
                f"  {fname:22s} {rname:14s} match_a={match_a:2d} match_b={match_b:2d} "
                f"e.g. rec0={vals[0]}"
            )
            if match_a == 25 or match_b == 25:
                hits.append((fname, rname, match_a, match_b))

    lines.append(f"\nFULL_MATCHES={hits if hits else 'NONE'}")

    # extra: maybe they are i16 stored in the LOW word of i32 with swapped order,
    # or sum of i16 signed then abs, or two complementary sums
    lines.append("\n== T2 extra: rec0 computed dump ==")
    rec0 = raw[:RECORD_SIZE]
    for rname, blob in ranges(rec0).items():
        lines.append(
            f"  {rname} len={len(blob)} sum_u16={sum_u16be(blob)} xor={xor_u16be(blob)} "
            f"sumb={sum_bytes(blob)} ccitt={crc16(blob,0x1021,0xFFFF)}"
        )

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
