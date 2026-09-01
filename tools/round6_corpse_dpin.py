# -*- coding: utf-8 -*-
"""Corpse TypeAddl scope + dpin-as-item-groups tests."""

from __future__ import annotations

import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import decode_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DPIN = ROOT / "reference/dpin_128.bin"
DESC = ROOT / "reference/docs/hfs_Pathways_Extras_PIDMaps_Folder_Descriptions.txt"
PART1 = ROOT / "data/cd/pathwaysintodarkness/docs_web/DeadScriptsPart1.txt"
PART2 = ROOT / "data/cd/pathwaysintodarkness/docs_web/DeadScriptsPart2.txt"
CHEAT = ROOT / "data/cd/pathwaysintodarkness/docs_web/ItemCheatFile_3_10.txt"
OUT = ROOT / "reference/docs"
PREFIX = 596
GROUP = 80
N_GROUPS = 2876


def parse_descriptions(text: str) -> dict[str, dict]:
    """level_key -> {title, corpses: [(raw, names)], items: [line]}."""
    levels: dict[str, dict] = {}
    current = None
    header_re = re.compile(
        r"^(\S.*?)(?:\s+-?\d+\.?\d*m?\s+[0-9A-Fa-f]{2}\s+\d+i)?\s*$"
    )
    known_starts = [
        "Ground Floor",
        "Never Stop Firing",
        "Lock&Load",
        "They May Be Slow",
        "But They're Hungry",
        "Evil Undead",
        "Ascension",
        "Wrong Way",
        "Welcome, Tasty",
        "We Can See",
        "Happy Happy",
        "Feel The Power",
        "A Plague",
        "Beware of",
        "The Labyrinth",
        "Need A Light",
        "Lasciate",
        "Watch Yor",
        "Watch Your",
        "I'd Rather",
        "Warning",
        "Don't Get",
        "Please Excuse",
        "But Wait",
        "Where Only",
        "Ok, Who Else",
    ]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_header = (not line.startswith("\t")) and any(
            stripped.startswith(s) or stripped.lstrip("\u2026.").startswith(s)
            for s in known_starts
        )
        # ellipsis-prefixed Hungry
        if stripped.startswith("\u2026") or stripped.startswith("..."):
            is_header = True
        if is_header and not stripped.startswith("Dead ") and "\t" not in line[:1]:
            # skip the silver-key prose line
            if stripped.startswith("All doors on previous"):
                continue
            current = stripped
            levels[current] = {"corpses": [], "items": []}
            continue
        if current is None:
            continue
        if stripped.startswith("Dead "):
            names = re.findall(r"\(([^)]*)\)", stripped)
            levels[current]["corpses"].append((stripped, names))
        elif line.startswith("\t") and not stripped.startswith("Dead "):
            levels[current]["items"].append(stripped)
    return levels


def parse_deadscripts() -> dict[int, str | None]:
    text = ""
    for path in (PART1, PART2):
        text += decode_mac_roman(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
    out: dict[int, str | None] = {}
    for m in re.finditer(
        r'^-----scri (\d+)(?:\s+"([^"]*)")?-----', text, flags=re.M
    ):
        out[int(m.group(1))] = m.group(2)
    return out


def parse_item_table(text: str) -> dict[int, str]:
    table: dict[int, str] = {}
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("code#"):
            in_table = True
            continue
        if in_table:
            if re.match(r"^[0-9A-Fa-f]{2}\s", line.strip()) or re.match(
                r"^[0-9A-Fa-f]{2}\s*$", line.strip()
            ):
                parts = line.strip().split(None, 1)
                code = int(parts[0], 16)
                name = parts[1] if len(parts) > 1 else ""
                table[code] = name
            elif line.strip() == "" or line.startswith("This file"):
                if table and (line.startswith("This file") or len(table) >= 0x40):
                    if line.startswith("This file"):
                        break
            elif not re.match(r"^[0-9A-Fa-f]{2}", line.strip()):
                if table and max(table) >= 0x40:
                    break
    return table


def level_key(name: str) -> str:
    n = name.lower().replace("\u2019", "'").replace("\u2014", "-")
    return n


def match_desc_level(maps_name: str, desc_levels: dict[str, dict]) -> str | None:
    mn = level_key(maps_name)
    for title in desc_levels:
        tn = level_key(title)
        # first few significant words
        if mn[:12] in tn or tn[:12] in mn:
            return title
        core = re.sub(r"[^a-z0-9]+", "", mn)[:16]
        if core and core in re.sub(r"[^a-z0-9]+", "", tn):
            return title
    return None


def decode_group(blob: bytes, index: int) -> list[tuple[int, int, int, int]]:
    off = PREFIX + index * GROUP
    chunk = blob[off : off + GROUP]
    rows = []
    for i in range(10):
        a, b, c, d = struct.unpack_from(">4H", chunk, i * 8)
        rows.append((a, b, c, d))
    return rows


def main() -> None:
    levels = load_maps(MAPS)
    dpin = DPIN.read_bytes()
    desc_text = DESC.read_text(encoding="utf-8")
    desc = parse_descriptions(desc_text)
    scripts = parse_deadscripts()
    cheat_text = decode_mac_roman(CHEAT.read_bytes()).replace("\r\n", "\n")
    items = parse_item_table(cheat_text)

    lines: list[str] = []

    # --- C1 ---
    corpses: list[tuple[int, str, int, int, int, int]] = []
    for li, lev in enumerate(levels):
        for si, sec in enumerate(lev.sector_list):
            if sec.type == 6:
                x, y = si % 32, si // 32
                corpses.append((li, lev.name, si, x, y, sec.type_addl))

    addls = [c[5] for c in corpses]
    cnt = Counter(addls)
    unique = set(addls)
    repeats = {k: v for k, v in cnt.items() if v > 1}
    lines.append("== C1 corpses ==")
    lines.append(f"total={len(corpses)}")
    lines.append(f"unique_type_addl={sorted(unique)}")
    lines.append(f"repeats={repeats}")
    lines.append(f"min={min(addls) if addls else None} max={max(addls) if addls else None}")
    expected = set(range(28))
    unused = sorted(expected - unique)
    extra = sorted(unique - expected)
    lines.append(f"unused_in_0_27={unused}")
    lines.append(f"outside_0_27={extra}")
    global_unique = len(unique) == len(addls)
    # restart near 0 each level?
    per_level = defaultdict(list)
    for li, name, si, x, y, addl in corpses:
        per_level[li].append(addl)
    restarts = all(min(v) <= 2 for v in per_level.values() if v)
    lines.append(f"globally_unique={global_unique}")
    lines.append(f"each_level_restarts_near_0={restarts}")
    lines.append("list:")
    for row in corpses:
        lines.append(
            f"  L{row[0]:02d} {row[1]!r:42s} sec={row[2]:4d} ({row[3]:2d},{row[4]:2d}) addl={row[5]}"
        )

    # --- C2 ---
    lines.append("\n== C2 Descriptions corpses ==")
    for title, data in desc.items():
        names = [c[1] for c in data["corpses"]]
        lines.append(f"  {title!r} n={len(data['corpses'])} {names}")

    lines.append("\n== C2 DeadScripts headings ==")
    lines.append(f"headed_ids={sorted(scripts)}")
    missing_heads = [i for i in range(128, 157) if i not in scripts]
    lines.append(f"missing_headings_128_156={missing_heads}")
    for n, name in sorted(scripts.items()):
        lines.append(f"  scri {n} name={name!r}")

    lines.append("\n== C2 join ==")
    # name from DeadScripts vs Descriptions
    # also 128+addl
    for li, lev in enumerate(levels):
        title = match_desc_level(lev.name, desc)
        desc_corpses = desc[title]["corpses"] if title else []
        map_corpses = [c for c in corpses if c[0] == li]
        lines.append(
            f"L{li:02d} maps={lev.name!r} desc={title!r} "
            f"map_count={len(map_corpses)} desc_count={len(desc_corpses)}"
        )
        for c in map_corpses:
            addl = c[5]
            scri = 128 + addl if addl <= 27 else None
            scri_name = scripts.get(scri) if scri else None
            lines.append(
                f"  map ({c[3]},{c[4]}) addl={addl} scri={scri} "
                f"heading_name={scri_name!r} eq={scri in scripts if scri else False}"
            )
        for raw, names in desc_corpses:
            lines.append(f"  desc {raw!r} names={names}")

    expected_counts = {
        "ground floor": 1,
        "lock&load": 2,
        "need a light": 5,
        "happy happy": 5,
        "fools": 2,
        "labyrinth": 0,
        "lasciate": 0,
    }
    lines.append("\n== C2 count check ==")
    for li, lev in enumerate(levels):
        n = sum(1 for c in corpses if c[0] == li)
        key = None
        for k in expected_counts:
            if k in lev.name.lower():
                key = k
                break
        exp = expected_counts.get(key) if key else None
        flag = ""
        if exp is not None and n != exp:
            flag = " MISMATCH"
        lines.append(f"  L{li:02d} {lev.name!r} map={n} expected={exp}{flag}")

    # --- D1 ---
    item_vals = []
    item_locs = []
    for li, lev in enumerate(levels):
        for si, sec in enumerate(lev.sector_list):
            if sec.item != -1:
                item_vals.append(sec.item)
                item_locs.append((li, lev.name, si, si % 32, si // 32, sec.item, sec.type))
    lines.append("\n== D1 Sector.Item ==")
    lines.append(f"nonzero_count={len(item_vals)}")
    lines.append(f"unique={len(set(item_vals))}")
    lines.append(f"min={min(item_vals) if item_vals else None} max={max(item_vals) if item_vals else None}")
    over = [v for v in item_vals if v >= N_GROUPS]
    lines.append(f"exceed_2875={len(over)} values={sorted(set(over))}")
    lines.append(f"negative_other={sorted({v for v in item_vals if v < 0})}")
    hist = Counter(item_vals)
    lines.append(f"most_common={hist.most_common(20)}")
    lines.append("all unique values: " + ",".join(str(v) for v in sorted(set(item_vals))))

    lines.append("\n== D1 group 42 ==")
    g42 = decode_group(dpin, 42)
    lines.append(f"offset={PREFIX + 42 * GROUP}")
    for i, (a, b, c, d) in enumerate(g42):
        lines.append(
            f"  [{i}] u16=({a},{b},{c},{d}) "
            f"low=({a & 0xFF:02x},{b & 0xFF:02x},{c & 0xFF:02x},{d & 0xFF:02x}) "
            f"id?={items.get(a & 0xFF, '?')!r}/{items.get(b & 0xFF, '?')!r} "
            f"qty_c={c} qty_d={d}"
        )
        qty_hits = [n for n in (a, b, c, d, a & 0xFF, b & 0xFF, c & 0xFF, d & 0xFF) if n in (8, 7, 3, 4)]
        if qty_hits:
            lines.append(f"       qty_hits={qty_hits}")

    # also dump groups for every Ground Floor item sector
    lines.append("\n== D1 Ground Floor item sectors ==")
    for loc in item_locs:
        if loc[0] != 0:
            continue
        gi = loc[5]
        rows = decode_group(dpin, gi) if 0 <= gi < N_GROUPS else []
        names = []
        for a, b, c, d in rows:
            if a != 0xFFFF and b != 0xFFFF:
                names.append(
                    f"{items.get(a & 0xFF, hex(a))}|st={b}|q={c}|cat={d}"
                )
        lines.append(
            f"  sec={loc[2]} ({loc[3]},{loc[4]}) type={loc[6]} item={gi} -> {names}"
        )

    lines.append("\n== D1 item id table ==")
    for code in range(0x47):
        lines.append(f"  {code:02X} {items.get(code, '')}")

    # per-level decode vs descriptions
    lines.append("\n== D1 per-level vs Descriptions ==")
    # field guess: try each of 4 u16 as item id
    for li, lev in enumerate(levels):
        title = match_desc_level(lev.name, desc)
        desc_items = desc[title]["items"] if title else []
        groups = []
        for loc in item_locs:
            if loc[0] != li:
                continue
            gi = loc[5]
            if not (0 <= gi < N_GROUPS):
                continue
            rows = decode_group(dpin, gi)
            decoded = []
            for a, b, c, d in rows:
                # skip empty ffff
                if a == 0xFFFF and b == 0xFFFF and c == 0xFFFF and d == 0xFFFF:
                    continue
                decoded.append((a, b, c, d, items.get(a & 0xFF, "?"), items.get(b & 0xFF, "?")))
            groups.append((loc[3], loc[4], gi, loc[6], decoded))
        lines.append(f"\nL{li:02d} {lev.name!r} desc={title!r}")
        lines.append(f"  desc_items={desc_items}")
        for x, y, gi, st, decoded in groups:
            pretty = [
                f"{t[4]!r}/alt={t[5]!r} u16=({t[0]},{t[1]},{t[2]},{t[3]})"
                for t in decoded
            ]
            lines.append(f"  ({x},{y}) type={st} item={gi} {pretty}")

    # prefix
    lines.append("\n== D1 prefix 596 ==")
    u16s = struct.unpack(f">{PREFIX // 2}H", dpin[:PREFIX])
    lines.append(f"u16be[0]={u16s[0]} u16be[1]={u16s[1]}")
    nonzero = [(i * 2, u16s[i]) for i in range(len(u16s)) if u16s[i]]
    lines.append(f"nonzero_u16_count={len(nonzero)}")
    lines.append("nonzero: " + " ".join(f"{off:#05x}={val}" for off, val in nonzero))

    dest = OUT / "round6_corpse_dpin.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print("...")
    print(f"wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
