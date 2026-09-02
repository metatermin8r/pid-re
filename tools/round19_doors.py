# -*- coding: utf-8 -*-
"""DoorTrigger propagation: closed arrival doors on levels 7-15."""

from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, WALL_TYPE_NAME, load_maps  # noqa: E402
from round18_walls import (  # noqa: E402
    SOLID_A,
    TYPE_RGB,
    draw_walls,
    entry_points,
    font,
    neighbors4,
    nonvoid_coords,
)

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round19_doors.txt"

ACTION = {
    6: "Chain1",
    7: "Chain2",
    8: "Unknown_8",
    12: "Unknown_HHCC_1",
    13: "Unknown_HHCC_2",
    14: "CloseNgbrDoor_Flag",
    17: "Unknown_HHCC_3",
    18: "Unknown_18",
    19: "Unknown_19",
    20: "Unknown_20",
    21: "Unknown_21",
    22: "Unknown_22",
    23: "Unknown_23",
    24: "EndGame",
    128: "CloseNgbrDoor",
    129: "OpenNgbrDoor",
    130: "AlienPipes",
    131: "OpenNgbrDoor_Silver",
    132: "OpenNgbrDoor_Gold",
    134: "Unknown_NAL_1",
    135: "Unknown_NAL_2",
    137: "Unknown_LOS_1",
    138: "Unknown_LOS_2",
    139: "Unknown_LOS_3",
    140: "Unknown_140",
    141: "OpenNgbrDoor_Flag",
}
ACTION_SHORT = {
    6: "C1",
    7: "C2",
    128: "Cl",
    129: "Op",
    130: "Pi",
    131: "Ag",
    132: "Au",
    141: "Fl",
    12: "U12",
    13: "U13",
    17: "U17",
    134: "U4",
    135: "U5",
}
OPEN_FREE = frozenset({129, 130, 6, 7})
OPEN_KEY = frozenset({131, 132, 141})
OPEN_UNKNOWN = frozenset({12, 13, 17, 134, 135})

PREV = {
    0: (214, 0),
    1: (478, 0),
    2: (500, 0),
    3: (451, 5),
    4: (503, 1),
    5: (563, 0),
    6: (195, 0),
    7: (283, 232),
    8: (44, 415),
    9: (13, 402),
    10: (5, 569),
    11: (10, 527),
    12: (54, 467),
    13: (4, 521),
    14: (207, 239),
    15: (412, 93),
    16: (472, 0),
    17: (496, 0),
    18: (521, 0),
    19: (172, 0),
    20: (428, 9),
    21: (529, 0),
    22: (496, 0),
    23: (519, 0),
    24: (57, 124),
}


def action_name(addl: int) -> str:
    return ACTION.get(addl, f"?{addl}")


def door_sectors(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type == 2]


def trigger_sectors(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type == 4]


def door_by_index(level) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    for x, y in door_sectors(level):
        out[level.sector_at(x, y).type_addl] = (x, y)
    return out


def neighbors8(x: int, y: int) -> list[tuple[int, int]]:
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < GRID and 0 <= ny < GRID:
                out.append((nx, ny))
    return out


def find_doors_adj4(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
    return [(nx, ny) for nx, ny in neighbors4(x, y) if level.sector_at(nx, ny).type == 2]


def find_doors_adj8(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
    return [(nx, ny) for nx, ny in neighbors8(x, y) if level.sector_at(nx, ny).type == 2]


def find_doors_radius(radius: int):
    def fn(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
        hits = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < GRID and 0 <= ny < GRID and level.sector_at(nx, ny).type == 2:
                    hits.append((nx, ny))
        return hits

    return fn


def find_doors_nearest(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
    doors = door_sectors(level)
    if not doors:
        return []
    best = min(doors, key=lambda p: (abs(p[0] - x) + abs(p[1] - y), abs(p[0] - x), abs(p[1] - y)))
    return [best]


def find_doors_index0(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
    idx = door_by_index(level)
    return [idx[0]] if 0 in idx else []


def find_doors_hybrid(level, x: int, y: int, addl: int) -> list[tuple[int, int]]:
    """Documented model: Chain -> DoorList[0]; OpenNgbr* -> 4-adj; AlienPipes -> r=5."""
    if addl in (6, 7):
        return find_doors_index0(level, x, y, addl)
    if addl == 130:
        return find_doors_radius(5)(level, x, y, addl)
    return find_doors_adj4(level, x, y, addl)


NEIGHBOR_FNS = {
    "adj4": find_doors_adj4,
    "adj8": find_doors_adj8,
    "radius2": find_doors_radius(2),
    "radius3": find_doors_radius(3),
    "nearest": find_doors_nearest,
    "index0": find_doors_index0,
    "hybrid": find_doors_hybrid,
}


def edge_wall(level, x: int, y: int, nx: int, ny: int) -> int:
    if nx == x and ny == y - 1:
        return level.sector_at(x, y).walls[0].type
    if nx == x - 1 and ny == y:
        return level.sector_at(x, y).walls[1].type
    if nx == x and ny == y + 1:
        return level.sector_at(x, y + 1).walls[0].type
    if nx == x + 1 and ny == y:
        return level.sector_at(x + 1, y).walls[1].type
    return -1


def blocked(level, x, y, nx, ny, solid, open_doors: set[tuple[int, int]]) -> bool:
    if not (0 <= nx < GRID and 0 <= ny < GRID):
        return True
    if level.sector_at(nx, ny).type == 0:
        return True
    wt = edge_wall(level, x, y, nx, ny)
    if wt not in solid:
        return False
    if (x, y) in open_doors or (nx, ny) in open_doors:
        return False
    return True


def flood(level, solid, open_doors: set[tuple[int, int]]) -> set[tuple[int, int]]:
    starts = entry_points(level)
    seen: set[tuple[int, int]] = set()
    q: deque[tuple[int, int]] = deque()
    for p in starts:
        if p not in seen:
            seen.add(p)
            q.append(p)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (nx, ny) in seen:
                continue
            if blocked(level, x, y, nx, ny, solid, open_doors):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def is_open_action(addl: int, use_keys: bool, use_unknown: bool) -> bool:
    if addl in OPEN_FREE:
        return True
    if use_keys and addl in OPEN_KEY:
        return True
    if use_unknown and addl in OPEN_UNKNOWN:
        return True
    return False


def propagate(level, neighbor_fn, use_keys: bool, use_unknown: bool = False):
    open_doors: set[tuple[int, int]] = set()
    log: list[tuple[tuple[int, int], int, list[tuple[int, int]]]] = []
    for _ in range(64):
        reach = flood(level, SOLID_A, open_doors)
        added: list[tuple[tuple[int, int], int, list[tuple[int, int]]]] = []
        for x, y in trigger_sectors(level):
            if (x, y) not in reach:
                continue
            addl = level.sector_at(x, y).type_addl
            if not is_open_action(addl, use_keys, use_unknown):
                continue
            targets = [(tx, ty) for tx, ty in neighbor_fn(level, x, y, addl) if (tx, ty) not in open_doors]
            if targets:
                for t in targets:
                    open_doors.add(t)
                added.append(((x, y), addl, targets))
        if not added:
            return reach, open_doors, log
        log.extend(added)
    return flood(level, SOLID_A, open_doors), open_doors, log


def components_voidsep(level) -> list[list[tuple[int, int]]]:
    left = set(nonvoid_coords(level))
    comps = []
    while left:
        start = next(iter(left))
        left.remove(start)
        q = deque([start])
        comp = [start]
        while q:
            x, y = q.popleft()
            for nx, ny in neighbors4(x, y):
                if (nx, ny) in left:
                    left.remove((nx, ny))
                    q.append((nx, ny))
                    comp.append((nx, ny))
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def render_doors(level, reach, open_doors, use_keys: bool, cell: int = 18) -> Image.Image:
    legend_w = 176
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    title = f"L{level.level_number:02d} {level.name}  doors+triggers"
    draw.text((4, 4), title[:78], fill=(230, 230, 220), font=fnt)
    y0 = title_h
    reach_c = (70, 150, 90)
    sealed_c = (150, 40, 50)
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        if sec.type == 0:
            fill = (0, 0, 0)
        elif (x, y) in reach:
            fill = TYPE_RGB.get(sec.type, (80, 80, 80)) if sec.type != 1 else (198, 186, 164)
            if sec.type == 1 and (x, y) not in reach:
                fill = sealed_c
        else:
            fill = (90, 28, 32) if sec.type == 1 else TYPE_RGB.get(sec.type, (80, 80, 80))
            if sec.type == 1:
                fill = sealed_c
            else:
                fill = tuple(max(0, c - 80) for c in TYPE_RGB.get(sec.type, (80, 80, 80)))
        if (x, y) in reach and sec.type == 1:
            fill = reach_c
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=fill)
    draw_walls(draw, level, y0, cell)
    for x, y in door_sectors(level):
        x0, top = x * cell, y0 + y * cell
        if (x, y) in open_doors:
            col = (80, 220, 90)
        else:
            col = (220, 50, 50)
        draw.rectangle((x0 + 2, top + 2, x0 + cell - 3, top + cell - 3), outline=col, width=2)
        if (x, y) in open_doors:
            draw.line((x0 + 4, top + 4, x0 + cell - 5, top + cell - 5), fill=col, width=2)
    for x, y in trigger_sectors(level):
        sec = level.sector_at(x, y)
        x0, top = x * cell, y0 + y * cell
        short = ACTION_SHORT.get(sec.type_addl, f"{sec.type_addl}")
        col = (255, 240, 80)
        if sec.type_addl in OPEN_KEY:
            col = (255, 200, 60)
        if sec.type_addl in (128, 14):
            col = (180, 180, 180)
        draw.text((x0 + 2, top + 3), short, fill=col, font=fnt)
        if (x, y) in reach:
            draw.rectangle((x0 + 1, top + 1, x0 + cell - 2, top + cell - 2), outline=(255, 240, 80), width=1)
    lx = w + 8
    items = [
        (reach_c, "reachable"),
        (sealed_c, "sealed"),
        ((80, 220, 90), "door OPEN"),
        ((220, 50, 50), "door CLOSED"),
        ((255, 240, 80), "trigger (reach)"),
        ((255, 200, 60), "key-gated trig"),
    ]
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for i, (col, name) in enumerate(items):
        yy = y0 + 16 + i * 14
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=col)
        draw.text((lx + 16, yy), name, fill=(220, 220, 210), font=fnt)
    return img


def dump_sector(level, x: int, y: int) -> str:
    s = level.sector_at(x, y)
    walls = " ".join(f"{k}:{w.type}/{w.texture}" for k, w in enumerate(s.walls))
    return (
        f"({x},{y}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?')} "
        f"Item={s.item} addl={s.type_addl} walls=[{walls}]"
    )


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 19 — DoorTrigger propagation")
    lines.append("Solid walls: 32/33 on edges 0/1. Open door = ignore 32/33 when")
    lines.append("stepping onto or off a Type 2 sector marked open.")
    lines.append("Start set: every Type 3 + Type 9 + southmost non-Void.")
    lines.append("Open actions: 129 OpenNgbrDoor, 130 AlienPipes, 131 Silver, 132 Gold,")
    lines.append("141 Flag, 6 Chain1, 7 Chain2. Close actions never open.")
    lines.append("")

    # --- (a) Type 4 census on 7-15 ---
    lines.append("========== (a) Type 4 DoorTrigger on levels 7-15 ==========")
    before_reach = []
    for n in range(25):
        before_reach.append(flood(levels[n], SOLID_A, set()))
    for n in range(7, 16):
        lv = levels[n]
        reach = before_reach[n]
        trigs = trigger_sectors(lv)
        lines.append(f"\n--- L{n:02d} {lv.name}  triggers={len(trigs)} doors={len(door_sectors(lv))} ---")
        if not trigs:
            lines.append("  (no Type 4 on this level)")
            continue
        for x, y in sorted(trigs, key=lambda p: (p[1], p[0])):
            s = lv.sector_at(x, y)
            tag = "REACH" if (x, y) in reach else "SEAL"
            adj = find_doors_adj4(lv, x, y, s.type_addl)
            adj_s = ",".join(f"({tx},{ty})# {lv.sector_at(tx, ty).type_addl}" for tx, ty in adj) or "-"
            lines.append(
                f"  ({x:2d},{y:2d}) {tag} Item={s.item:4d} addl={s.type_addl:3d} "
                f"{action_name(s.type_addl):22s} adj4={adj_s}"
            )

    # --- (c) neighbor-definition bake-off, keys ON ---
    lines.append("\n========== (c) neighbor definition bake-off (keys ON) ==========")
    lines.append("Score = sum reachable on L7-L15 except L13. Orphans = reachable open")
    lines.append("triggers that matched zero Type 2 doors.")
    hdr = f"{'def':<10} " + " ".join(f"L{n:02d}" for n in range(7, 16)) + "  sum*-13  orphans"
    lines.append(hdr)
    scores = {}
    for name, fn in NEIGHBOR_FNS.items():
        cells = []
        total = 0
        orphans = 0
        for n in range(7, 16):
            reach, opened, log = propagate(levels[n], fn, use_keys=True)
            cells.append(f"{len(reach):4d}")
            if n != 13:
                total += len(reach)
            for x, y in trigger_sectors(levels[n]):
                if (x, y) not in reach:
                    continue
                addl = levels[n].sector_at(x, y).type_addl
                if is_open_action(addl, True, False) and not fn(levels[n], x, y, addl):
                    orphans += 1
        scores[name] = (total, -orphans, name)
        lines.append(f"{name:<10} {' '.join(cells)}  {total:7d}  {orphans:7d}")
    best_total = max(v[0] for v in scores.values())
    # Geometric defs all tie on reachability. Prefer documented 4-adjacency
    # (OpenNgbrDoor) over wider radii that mark extra doors open without
    # connecting any new tiles.
    tied = [name for name, (tot, _, _) in scores.items() if tot == best_total]
    winner = "adj4" if "adj4" in tied else max(scores.values())[2]
    lines.append(
        f"reach-max defs: {', '.join(tied)} (all {best_total}). "
        f"Using {winner}: OpenNgbr* is 4-adjacent in every observed case; "
        f"wider radii open extra doors that do not change connectivity."
    )
    win_fn = NEIGHBOR_FNS[winner]

    # --- (b) before/after with winner, keys ON ---
    lines.append(f"\n========== (b) reachability before vs after ({winner}, keys ON) ==========")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'before_r':>8} {'before_s':>8} "
        f"{'after_r':>7} {'after_s':>7} {'opened':>6}"
    )
    after_key = []
    opened_key = []
    logs_key = []
    for n in range(25):
        lv = levels[n]
        nv = len(nonvoid_coords(lv))
        br = len(before_reach[n])
        reach, opened, log = propagate(lv, win_fn, use_keys=True)
        after_key.append(reach)
        opened_key.append(opened)
        logs_key.append(log)
        lines.append(
            f"{n:3d} {lv.name:<36} {nv:4d} {br:8d} {nv - br:8d} "
            f"{len(reach):7d} {nv - len(reach):7d} {len(opened):6d}"
        )

    lines.append(f"\n--- doors each reachable trigger opens ({winner}, keys ON), L7-15 ---")
    for n in range(7, 16):
        lv = levels[n]
        if not logs_key[n] and not trigger_sectors(lv):
            continue
        lines.append(f"L{n:02d} {lv.name}:")
        if not logs_key[n]:
            lines.append("  (no door opened)")
            continue
        for (x, y), addl, targets in logs_key[n]:
            bits = []
            for tx, ty in targets:
                d = lv.sector_at(tx, ty)
                bits.append(f"door({tx},{ty})# {d.type_addl}")
            lines.append(
                f"  trigger ({x},{y}) {action_name(addl)} -> {', '.join(bits)}"
            )
        lines.append("  Type 2 far-side (4-neighbors after propagation):")
        for x, y in door_sectors(lv):
            s = lv.sector_at(x, y)
            tag = "OPEN" if (x, y) in opened_key[n] else (
                "R" if (x, y) in after_key[n] else "S"
            )
            nbrs = []
            for nx, ny in neighbors4(x, y):
                ns = lv.sector_at(nx, ny)
                st = "void" if ns.type == 0 else (
                    "R" if (nx, ny) in after_key[n] else "S"
                )
                nbrs.append(f"({nx},{ny})t={ns.type}{st}")
            lines.append(
                f"    ({x},{y})#{s.type_addl} {tag} WY={s.walls[0].type} "
                f"WX={s.walls[1].type} nbrs={nbrs}"
            )

    # --- (d) key-gated delta ---
    lines.append(f"\n========== (d) key-gated content ({winner}) ==========")
    lines.append("WITHOUT = only 129/130/6/7. WITH = also 131 silver, 132 gold, 141 flag.")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'no_key':>6} {'with_key':>8} {'gated':>6}"
    )
    after_nokey = []
    opened_nokey = []
    for n in range(25):
        lv = levels[n]
        reach, opened, _ = propagate(lv, win_fn, use_keys=False)
        after_nokey.append(reach)
        opened_nokey.append(opened)
        gated = len(after_key[n]) - len(reach)
        lines.append(
            f"{n:3d} {lv.name:<36} {len(reach):6d} {len(after_key[n]):8d} {gated:6d}"
        )
        if gated and n in range(7, 16):
            extra = sorted(after_key[n] - reach)
            lines.append(f"    gated tiles ({len(extra)}): first 40 shown")
            for x, y in extra[:40]:
                s = lv.sector_at(x, y)
                lines.append(
                    f"      ({x:2d},{y:2d}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?'):16s} Item={s.item:4d}"
                )
            if len(extra) > 40:
                lines.append(f"      ... {len(extra) - 40} more")

    # unknowns-as-open footnote on leftover door levels
    lines.append(f"\n--- footnote: treat HHCC/NAL unknowns as open ({winner}, keys ON) ---")
    for n in (14, 15):
        lv = levels[n]
        nv = len(nonvoid_coords(lv))
        reach_u, opened_u, log_u = propagate(lv, win_fn, use_keys=True, use_unknown=True)
        lines.append(
            f"  L{n:02d} after+unknown r={len(reach_u)} sealed={nv - len(reach_u)} "
            f"(keys-only sealed={nv - len(after_key[n])}) extra_open={len(opened_u - opened_key[n])}"
        )
        for (x, y), addl, targets in log_u:
            if addl in OPEN_UNKNOWN:
                bits = ",".join(f"({tx},{ty})" for tx, ty in targets)
                lines.append(f"    {action_name(addl)} ({x},{y}) -> {bits}")

    # --- (e) remains sealed ---
    lines.append(f"\n========== (e) remains sealed after {winner} + keys ==========")
    for n in range(25):
        lv = levels[n]
        nv = nonvoid_coords(lv)
        sealed = [(x, y) for x, y in nv if (x, y) not in after_key[n]]
        if not sealed:
            continue
        hist = Counter(lv.sector_at(x, y).type for x, y in sealed)
        hist_s = ", ".join(f"{t}:{SECTOR_TYPE_NAME.get(t, '?')}={c}" for t, c in sorted(hist.items()))
        note = ""
        if n == 13:
            note = "  [Labyrinth: stored geometry regenerates; ignore]"
        if n == 24:
            note = "  [endgame; see structure below]"
        if n == 20:
            note = "  [3x3 island; see (f)]"
        lines.append(f"  L{n:02d} {lv.name}: sealed={len(sealed)}/{len(nv)}  {hist_s}{note}")
        if n in range(7, 16) and n != 13 and sealed:
            # remaining Type 4 / Type 2 still sealed
            still_t4 = [(x, y) for x, y in trigger_sectors(lv) if (x, y) in sealed]
            still_t2 = [(x, y) for x, y in door_sectors(lv) if (x, y) in sealed]
            lines.append(f"    sealed triggers: {still_t4 or '(none)'}")
            lines.append(f"    sealed doors: {still_t2 or '(none)'}")

    # L24 structure
    lines.append("\n========== (e2) L24 Ok, Who Else Wants Some? structure ==========")
    lv24 = levels[24]
    comps = components_voidsep(lv24)
    lines.append(f"void-separated 4-islands: {len(comps)}  sizes={[len(c) for c in comps]}")
    lines.append(f"Type 2={len(door_sectors(lv24))} Type 4={len(trigger_sectors(lv24))} DoorList used="
                 f"{sum(1 for d in lv24.door_list if d.direction != -1)}")
    reach24 = after_key[24]
    for i, comp in enumerate(comps):
        xs = [p[0] for p in comp]
        ys = [p[1] for p in comp]
        types = Counter(lv24.sector_at(x, y).type for x, y in comp)
        items = [lv24.sector_at(x, y).item for x, y in comp if lv24.sector_at(x, y).item != -1]
        n_reach = sum(1 for p in comp if p in reach24)
        tstr = ",".join(f"{t}:{c}" for t, c in sorted(types.items()))
        lines.append(
            f"  island {i:02d} n={len(comp):3d} reach={n_reach:3d} "
            f"bbox=({min(xs)}..{max(xs)},{min(ys)}..{max(ys)}) types={tstr} "
            f"items={items[:12]}{'...' if len(items) > 12 else ''}"
        )

    # --- (f) L20 3x3 ---
    lines.append("\n========== (f) L20 3x3 block (1-3,1-3) ==========")
    lv20 = levels[20]
    for y in range(1, 4):
        for x in range(1, 4):
            lines.append("  " + dump_sector(lv20, x, y))
    # neighbors of the block
    lines.append("  4-neighbors of the 3x3 (outside the block):")
    block = {(x, y) for x in range(1, 4) for y in range(1, 4)}
    seen_n = set()
    for x, y in block:
        for nx, ny in neighbors4(x, y):
            if (nx, ny) not in block and (nx, ny) not in seen_n:
                seen_n.add((nx, ny))
                s = lv20.sector_at(nx, ny)
                lines.append(
                    f"    ({nx},{ny}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?')} "
                    f"Item={s.item} addl={s.type_addl} "
                    f"WY={s.walls[0].type} WX={s.walls[1].type}"
                )

    # GF sanity
    gf_before = len(before_reach[0])
    gf_after = len(after_key[0])
    lines.append(f"\nGround Floor sanity: before={gf_before} after={gf_after} (expect 214/214)")
    if gf_before != 214 or gf_after != 214:
        lines.append("  SANITY FAIL")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    for n in range(7, 16):
        img = render_doors(levels[n], after_key[n], opened_key[n], use_keys=True)
        img.save(OUT / f"L{n:02d}_doors.png")

    print("\n".join(lines))
    print(f"\nwrote {REPORT}")
    print("wrote L07_doors.png .. L15_doors.png")


if __name__ == "__main__":
    main()
