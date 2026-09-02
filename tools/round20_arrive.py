# -*- coding: utf-8 -*-
"""Arrival coords come from other levels' LevelChangeList, not own Type 3."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, load_maps  # noqa: E402
from round18_walls import SOLID_A, TYPE_RGB, draw_walls, font, neighbors4, nonvoid_coords  # noqa: E402
from round19_doors import (  # noqa: E402
    blocked,
    find_doors_adj4,
    is_open_action,
    trigger_sectors,
)

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round20_arrive.txt"

CHANGE_NAME = {
    0: "Upward",
    1: "Downward",
    2: "SecretDownward",
    3: "SecretUpward",
    4: "Undocumented_4",
}

# Round 19 after adj4 + keys, old start set (own Type 3 + Type 9 + southmost).
PREV_R = [
    214, 478, 500, 451, 503, 563, 195, 283, 44, 13,
    5, 25, 89, 4, 249, 412, 472, 496, 521, 172,
    428, 529, 496, 519, 57,
]
PREV_NV = [
    214, 478, 500, 456, 504, 563, 195, 515, 459, 415,
    574, 537, 521, 525, 446, 505, 472, 496, 521, 172,
    437, 529, 496, 519, 181,
]


def change_name(typ: int) -> str:
    return CHANGE_NAME.get(typ, f"?{typ}")


def is_empty_slot(c) -> bool:
    return c.type == -1 and c.level == 0 and c.x == 0 and c.y == 0


def is_stale_minus1(c) -> bool:
    return c.type == -1 and not (c.level == 0 and c.x == 0 and c.y == 0)


def is_live_change(c) -> bool:
    return (
        c.type in (0, 1, 2, 3)
        and 0 <= c.level <= 24
        and 0 <= c.x < GRID
        and 0 <= c.y < GRID
    )


def type3_used_indices(level) -> set[int]:
    return {s.type_addl for s in level.sector_list if s.type == 3}


def type3_positions(level) -> list[tuple[int, int, int]]:
    out = []
    for i, s in enumerate(level.sector_list):
        if s.type == 3:
            out.append((i % GRID, i // GRID, s.type_addl))
    return out


def save_positions(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type == 9]


def flood_from(level, starts: list[tuple[int, int]], open_doors: set[tuple[int, int]]):
    seen: set[tuple[int, int]] = set()
    q: deque[tuple[int, int]] = deque()
    for p in starts:
        x, y = p
        if not (0 <= x < GRID and 0 <= y < GRID):
            continue
        if level.sector_at(x, y).type == 0:
            continue
        if p not in seen:
            seen.add(p)
            q.append(p)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (nx, ny) in seen:
                continue
            if blocked(level, x, y, nx, ny, SOLID_A, open_doors):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def old_starts(level) -> list[tuple[int, int]]:
    pts = [(x, y) for x, y, _ in type3_positions(level)]
    pts.extend(save_positions(level))
    best = None
    for i, s in enumerate(level.sector_list):
        if s.type == 0:
            continue
        x, y = i % GRID, i // GRID
        if best is None or y > best[1] or (y == best[1] and x < best[0]):
            best = (x, y)
    if best is not None and best not in pts:
        pts.append(best)
    return pts


def propagate_from(level, starts, use_keys: bool = True):
    open_doors: set[tuple[int, int]] = set()
    log = []
    for _ in range(64):
        reach = flood_from(level, starts, open_doors)
        added = []
        for x, y in trigger_sectors(level):
            if (x, y) not in reach:
                continue
            addl = level.sector_at(x, y).type_addl
            if not is_open_action(addl, use_keys, False):
                continue
            targets = [
                t for t in find_doors_adj4(level, x, y, addl) if t not in open_doors
            ]
            if targets:
                for t in targets:
                    open_doors.add(t)
                added.append(((x, y), addl, targets))
        if not added:
            return reach, open_doors, log
        log.extend(added)
    return flood_from(level, starts, open_doors), open_doors, log


def wall_component(level, seed: tuple[int, int], open_doors: set[tuple[int, int]]):
    return flood_from(level, [seed], open_doors)


def render_level(level, reach, arrivals, departures, cell: int = 18) -> Image.Image:
    legend_w = 180
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text(
        (4, 4),
        f"L{level.level_number:02d} {level.name}  arrivals+reach"[:78],
        fill=(230, 230, 220),
        font=fnt,
    )
    y0 = title_h
    reach_c = (70, 150, 90)
    sealed_c = (150, 40, 50)
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        if sec.type == 0:
            fill = (0, 0, 0)
        elif (x, y) in reach:
            fill = reach_c if sec.type == 1 else TYPE_RGB.get(sec.type, (80, 80, 80))
        else:
            fill = sealed_c if sec.type == 1 else tuple(
                max(0, c - 90) for c in TYPE_RGB.get(sec.type, (80, 80, 80))
            )
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=fill)
    draw_walls(draw, level, y0, cell)
    for x, y in departures:
        x0, top = x * cell, y0 + y * cell
        cx, cy = x0 + cell // 2, top + cell // 2
        draw.polygon(
            [(cx, top + 2), (x0 + cell - 3, top + cell - 3), (x0 + 2, top + cell - 3)],
            outline=(255, 220, 40),
            width=2,
        )
    for x, y in arrivals:
        x0, top = x * cell, y0 + y * cell
        cx, cy = x0 + cell // 2, top + cell // 2
        r = 5
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(40, 220, 255), width=2)
        draw.ellipse((cx - 1, cy - 1, cx + 1, cy + 1), fill=(40, 220, 255))
    for x, y in save_positions(level):
        x0, top = x * cell, y0 + y * cell
        draw.rectangle(
            (x0 + 3, top + 3, x0 + cell - 4, top + cell - 4),
            outline=(210, 40, 40),
            width=1,
        )
    lx = w + 8
    items = [
        (reach_c, "reachable"),
        (sealed_c, "sealed"),
        ((40, 220, 255), "ARRIVAL drop"),
        ((255, 220, 40), "DEPARTURE Type3"),
        ((210, 40, 40), "Save"),
    ]
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for i, (col, name) in enumerate(items):
        yy = y0 + 16 + i * 14
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=col)
        draw.text((lx + 16, yy), name, fill=(220, 220, 210), font=fnt)
    return img


def near_tiles(x: int, y: int) -> list[tuple[int, int]]:
    out = [(x, y)]
    out.extend(neighbors4(x, y))
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID and 0 <= ny < GRID:
            out.append((nx, ny))
    return out


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 20 — arrival coordinates from source LevelChangeList")
    lines.append("Live slot: Type in {0,1,2,3}, dest level 0-24, dest x,y on 0-31.")
    lines.append("Empty unused: Type=-1 Level=0 x=0 y=0 (368 slots).")
    lines.append("Stale leftover: Type=-1 but other fields nonzero (skipped).")
    lines.append("Type 4: undocumented; L22 Type 3s reference dest L0 (0,0).")
    lines.append("")

    # --- (a) full graph ---
    lines.append("========== (a) LevelChangeList graph ==========")
    live_edges = []  # (s, idx, typ, dest_lv, x, y, t3_ref)
    stale = []
    type4 = []
    empty_n = 0
    for lv in levels:
        used = type3_used_indices(lv)
        lines.append(f"\n--- L{lv.level_number:02d} {lv.name} ---")
        for i, c in enumerate(lv.level_change_list):
            if is_empty_slot(c):
                empty_n += 1
                continue
            if is_stale_minus1(c):
                stale.append((lv.level_number, i, c))
                lines.append(
                    f"  [{i:2d}] STALE type={c.type} L{c.level} ({c.x},{c.y}) "
                    f"(Type=-1 leftover; no Type 3 refs this index)"
                )
                continue
            if c.type == 4:
                type4.append((lv.level_number, i, c, i in used))
                lines.append(
                    f"  [{i:2d}] type=4 Undocumented_4 L{c.level} ({c.x},{c.y}) "
                    f"t3ref={i in used}"
                )
                continue
            if is_live_change(c):
                live_edges.append((lv.level_number, i, c.type, c.level, c.x, c.y, i in used))
                lines.append(
                    f"  [{i:2d}] {change_name(c.type):16s} -> L{c.level:02d} "
                    f"{levels[c.level].name} ({c.x},{c.y}) t3ref={i in used}"
                )
            else:
                lines.append(
                    f"  [{i:2d}] ODD type={c.type} L{c.level} ({c.x},{c.y}) t3ref={i in used}"
                )
    lines.append(f"\nempty unused slots: {empty_n}")
    lines.append(f"stale Type=-1 leftovers: {len(stale)}")
    lines.append(f"live transitions (type 0-3): {len(live_edges)}")
    lines.append(f"undocumented type 4: {len(type4)}")

    # arrivals per dest level
    arrivals: dict[int, list[tuple[int, int, int, int, int]]] = defaultdict(list)
    # dest_n -> list of (src, idx, typ, x, y)
    for s, idx, typ, d, x, y, _ref in live_edges:
        arrivals[d].append((s, idx, typ, x, y))

    # old reach for (b)
    old_reach = []
    for lv in levels:
        r, _, _ = propagate_from(lv, old_starts(lv), use_keys=True)
        old_reach.append(r)

    # --- (b) arrivals vs old reach ---
    lines.append("\n========== (b) arrivals per destination level ==========")
    new_starts: list[list[tuple[int, int]]] = [[] for _ in range(25)]
    for n, lv in enumerate(levels):
        seen_xy: dict[tuple[int, int], list] = defaultdict(list)
        for s, idx, typ, x, y in arrivals[n]:
            seen_xy[(x, y)].append((s, idx, typ))
        saves = save_positions(lv)
        starts = list(seen_xy.keys())
        for p in saves:
            if p not in starts:
                starts.append(p)
        new_starts[n] = starts
        lines.append(f"\n--- L{n:02d} {lv.name}  unique arrivals={len(seen_xy)} saves={len(saves)} ---")
        if not seen_xy:
            lines.append("  (no live arrival points at this level)")
        for (x, y), srcs in sorted(seen_xy.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if 0 <= x < GRID and 0 <= y < GRID:
                sec = lv.sector_at(x, y)
                in_old = (x, y) in old_reach[n]
                bucket = "OLD-REACH" if in_old else "OLD-SEAL"
                if sec.type == 0:
                    bucket = "VOID"
                src_s = ", ".join(
                    f"L{s}[{i}] {change_name(t)}" for s, i, t in srcs
                )
                lines.append(
                    f"  ({x:2d},{y:2d}) type={sec.type} {SECTOR_TYPE_NAME.get(sec.type, '?'):16s} "
                    f"Item={sec.item:4d} addl={sec.type_addl} {bucket}  from {src_s}"
                )
            else:
                lines.append(f"  ({x},{y}) OUT OF RANGE from {srcs}")
        extra_saves = [p for p in saves if p not in seen_xy]
        if extra_saves:
            lines.append(f"  extra Type 9 seeds (not also arrivals): {extra_saves}")

    # --- (c) corrected flood + doors ---
    lines.append("\n========== (c) reachability: arrivals + Type 9, then door fixed-point ==========")
    lines.append("prev = round 19 (own Type 3 + Type 9 + southmost, then doors).")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'prev_r':>6} {'prev_s':>6} "
        f"{'new_r':>5} {'new_s':>5} {'dR':>5}"
    )
    new_reach = []
    new_open = []
    for n, lv in enumerate(levels):
        nv = PREV_NV[n]
        reach, opened, _ = propagate_from(lv, new_starts[n], use_keys=True)
        new_reach.append(reach)
        new_open.append(opened)
        pr = PREV_R[n]
        lines.append(
            f"{n:3d} {lv.name:<36} {nv:4d} {pr:6d} {nv - pr:6d} "
            f"{len(reach):5d} {nv - len(reach):5d} {len(reach) - pr:5d}"
        )
    gf_ok = len(new_reach[0]) == 214
    lines.append(f"\nGround Floor sanity: {len(new_reach[0])}/214  {'PASS' if gf_ok else 'FAIL'}")

    # --- (d) Descriptions cross-check ---
    lines.append("\n========== (d) Descriptions cross-check ==========")
    expected = [
        ("L2 Lock&Load SW ladder to Ground Floor", 2, 0, None),
        ("L2 Lock&Load NE ladder to They May Be Slow", 2, 3, None),
        ("L3 West Teleporter to But They're Hungry", 3, 4, "secret"),
        ("L3 East Teleporter to Evil Undead Phantasms", 3, 5, "secret"),
        ("L13 NW to Happy Happy", 13, 14, None),
        ("L13 NE to Beware of Low-Flying Nightmares", 13, 12, None),
        ("L13 SW to Need a Light", 13, 15, None),
        ("L13 SE to Lasciate", 13, 16, None),
        ("L14 West Ladder to We Can See In The Dark", 14, 9, None),
        ("L14 East Ladder to Labyrinth", 14, 13, None),
        ("L14 Middle Teleporter to A Plague of Demons", 14, 11, "secret"),
        ("L14 North Teleporter to (trap)", 14, None, "trap"),
        ("L14 South Teleporter to (trap)", 14, None, "trap"),
    ]
    by_src: dict[int, list] = defaultdict(list)
    for s, idx, typ, d, x, y, ref in live_edges:
        by_src[s].append((idx, typ, d, x, y, ref))

    def has_edge(src, dest, secret=None) -> list:
        hits = []
        for idx, typ, d, x, y, ref in by_src[src]:
            if dest is not None and d != dest:
                continue
            if secret == "secret" and typ not in (2, 3):
                continue
            if secret == "trap" and typ not in (2, 3):
                continue
            hits.append((idx, typ, d, x, y))
        return hits

    for label, src, dest, kind in expected:
        hits = has_edge(src, dest, kind)
        if hits:
            bits = ", ".join(
                f"[{i}] {change_name(t)} -> L{d} ({x},{y})" for i, t, d, x, y in hits
            )
            lines.append(f"  AGREE  {label}: {bits}")
        else:
            lines.append(f"  MISS   {label}")
            lines.append(
                f"         live from L{src}: "
                + ", ".join(
                    f"[{i}] {change_name(t)}->L{d}({x},{y})"
                    for i, t, d, x, y, _ in by_src[src]
                )
            )

    # extra live edges on those levels not named
    lines.append("\n  other live edges on L2/L3/L13/L14:")
    for src in (2, 3, 13, 14):
        for idx, typ, d, x, y, ref in by_src[src]:
            lines.append(
                f"    L{src}[{idx}] {change_name(typ)} -> L{d} {levels[d].name} ({x},{y})"
            )

    # --- (e) traps ---
    lines.append("\n========== (e) Happy Happy North/South teleporter traps ==========")
    trap_entries = [
        (idx, typ, d, x, y)
        for idx, typ, d, x, y, _ in by_src[14]
        if typ == 2 and d == 20
    ]
    for idx, typ, d, x, y in trap_entries:
        lv = levels[d]
        sec = lv.sector_at(x, y)
        # component from the drop alone, no doors needed for a 3x3 void island
        comp = wall_component(lv, (x, y), set())
        t3_in = [(tx, ty) for tx, ty, _ in type3_positions(lv) if (tx, ty) in comp]
        saves_in = [p for p in save_positions(lv) if p in comp]
        # can this component reach the rest of the level? compare to flood from main arrivals
        main_starts = [p for p in new_starts[d] if p != (x, y)]
        # also exclude the other trap drop if same tile
        main_reach, _, _ = propagate_from(lv, main_starts, use_keys=True)
        isolated = (x, y) not in main_reach
        lines.append(
            f"  L14[{idx}] {change_name(typ)} -> L{d} {lv.name} ({x},{y}) "
            f"type={sec.type} {SECTOR_TYPE_NAME.get(sec.type, '?')} Item={sec.item}"
        )
        lines.append(
            f"    drop-component size={len(comp)} Type3_in={t3_in or 'none'} "
            f"Save_in={saves_in or 'none'} isolated_from_main={isolated}"
        )
        if isolated and not t3_in:
            lines.append(
                "    DESIGNED TRAP: drop is in a sealed room with no Type 3 exit."
            )

    # --- (f) bidirectionality ---
    lines.append("\n========== (f) one-way transitions ==========")
    lines.append("Two-way iff dest level has a Type 3 at/near the drop whose")
    lines.append("LevelChangeList entry points back to the source level.")
    oneway = []
    twoway = []
    for s, idx, typ, d, x, y, ref in live_edges:
        dest_lv = levels[d]
        back = []
        for px, py, addl in type3_positions(dest_lv):
            if (px, py) not in near_tiles(x, y):
                continue
            if addl >= 20:
                continue
            bc = dest_lv.level_change_list[addl]
            if is_live_change(bc) and bc.level == s:
                back.append((px, py, addl, bc.type, bc.x, bc.y))
        if back:
            twoway.append((s, idx, typ, d, x, y, back))
        else:
            oneway.append((s, idx, typ, d, x, y))
    lines.append(f"two-way: {len(twoway)}   one-way: {len(oneway)}")
    lines.append("one-way list:")
    for s, idx, typ, d, x, y in oneway:
        lines.append(
            f"  L{s:02d}[{idx}] {change_name(typ):16s} -> L{d:02d} {levels[d].name} ({x},{y})"
        )

    # --- (g) remains sealed ---
    lines.append("\n========== (g) still sealed after arrivals + doors ==========")
    for n, lv in enumerate(levels):
        nv = nonvoid_coords(lv)
        sealed = [(x, y) for x, y in nv if (x, y) not in new_reach[n]]
        if not sealed:
            continue
        hist = Counter(lv.sector_at(x, y).type for x, y in sealed)
        hist_s = ", ".join(
            f"{t}:{SECTOR_TYPE_NAME.get(t, '?')}={c}" for t, c in sorted(hist.items())
        )
        note = ""
        if n == 13:
            note = "  [Labyrinth regenerates]"
        if n == 24:
            note = "  [endgame / credit graphic; not a reachability failure]"
        lines.append(f"\nL{n:02d} {lv.name}: sealed={len(sealed)}/{len(nv)}  {hist_s}{note}")
        if n == 24:
            continue
        preview = 80 if n in (9, 10, 13) else 40
        for i, (x, y) in enumerate(sorted(sealed, key=lambda p: (p[1], p[0]))):
            if i >= preview:
                lines.append(f"  ... {len(sealed) - preview} more")
                break
            s = lv.sector_at(x, y)
            lines.append(
                f"  ({x:2d},{y:2d}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?'):16s} "
                f"Item={s.item:4d} addl={s.type_addl}"
            )

    # --- (h) L24 ---
    lines.append("\n========== (h) L24 Ok, Who Else Wants Some? ==========")
    lines.append(
        "Petrich sector_types_sqr cell is a 1993/snail credit graphic, not a floor plan."
    )
    lines.append("34 void-separated islands, empty DoorList, no Type 4. Special/non-standard.")
    lines.append("Arrivals pointing here:")
    for s, idx, typ, x, y in arrivals[24]:
        sec = levels[24].sector_at(x, y)
        lines.append(
            f"  from L{s}[{idx}] {change_name(typ)} -> ({x},{y}) "
            f"type={sec.type} {SECTOR_TYPE_NAME.get(sec.type, '?')} Item={sec.item} "
            f"{'in-reach' if (x, y) in new_reach[24] else 'sealed'}"
        )
    lines.append(f"  L24 own Type 3 departures:")
    for x, y, addl in type3_positions(levels[24]):
        c = levels[24].level_change_list[addl]
        lines.append(
            f"    ({x},{y}) addl={addl} {change_name(c.type)} -> L{c.level} ({c.x},{c.y})"
        )
    lines.append(f"  reachable after arrival seed: {len(new_reach[24])}/181")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    for n, lv in enumerate(levels):
        deps = [(x, y) for x, y, _ in type3_positions(lv)]
        arr = sorted({(x, y) for _s, _i, _t, x, y in arrivals[n]})
        img = render_level(lv, new_reach[n], arr, deps)
        img.save(OUT / f"L{n:02d}_arrive.png")

    print("\n".join(lines))
    print(f"\nwrote {REPORT}")
    print("wrote L00_arrive.png .. L24_arrive.png")


if __name__ == "__main__":
    main()
