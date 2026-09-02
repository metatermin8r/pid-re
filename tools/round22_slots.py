# -*- coding: utf-8 -*-
"""Brute-force which WallList slots are the two edges."""

from __future__ import annotations

import itertools
import sys
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, WALL_TYPE_NAME, load_maps  # noqa: E402
from round18_walls import SOLID_A, SOLID_B, TYPE_RGB, edge_style, font  # noqa: E402
from round19_doors import find_doors_adj4, is_open_action, trigger_sectors  # noqa: E402
from round20_arrive import is_live_change, save_positions  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round22_slots.txt"

# Round 20 (0,1) sealed per level after arrivals + doors.
PREV_SEALED = [
    0, 0, 0, 7, 1, 0, 0, 233, 416, 403,
    570, 512, 433, 323, 201, 94, 0, 0, 0, 0,
    0, 0, 0, 0, 148,
]


def arrivals_to(levels, dest: int) -> list[tuple[int, int]]:
    seen: list[tuple[int, int]] = []
    for lv in levels:
        for c in lv.level_change_list:
            if is_live_change(c) and c.level == dest:
                p = (c.x, c.y)
                if p not in seen:
                    seen.append(p)
    return seen


def starts_for(levels, n: int) -> list[tuple[int, int]]:
    pts = arrivals_to(levels, n)
    for p in save_positions(levels[n]):
        if p not in pts:
            pts.append(p)
    return pts


def edge_type(level, x, y, nx, ny, north: int, west: int) -> int:
    if nx == x and ny == y - 1:
        return level.sector_at(x, y).walls[north].type
    if nx == x - 1 and ny == y:
        return level.sector_at(x, y).walls[west].type
    if nx == x and ny == y + 1:
        return level.sector_at(x, y + 1).walls[north].type
    if nx == x + 1 and ny == y:
        return level.sector_at(x + 1, y).walls[west].type
    return -1


def blocked(level, x, y, nx, ny, solid, open_doors, north: int, west: int) -> bool:
    if not (0 <= nx < GRID and 0 <= ny < GRID):
        return True
    if level.sector_at(nx, ny).type == 0:
        return True
    wt = edge_type(level, x, y, nx, ny, north, west)
    if wt not in solid:
        return False
    if (x, y) in open_doors or (nx, ny) in open_doors:
        return False
    return True


def flood(level, starts, solid, open_doors, north: int, west: int):
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
            if blocked(level, x, y, nx, ny, solid, open_doors, north, west):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def propagate(level, starts, solid, north: int, west: int, use_keys: bool = True):
    open_doors: set[tuple[int, int]] = set()
    for _ in range(64):
        reach = flood(level, starts, solid, open_doors, north, west)
        added = False
        for x, y in trigger_sectors(level):
            if (x, y) not in reach:
                continue
            addl = level.sector_at(x, y).type_addl
            if not is_open_action(addl, use_keys, False):
                continue
            for t in find_doors_adj4(level, x, y, addl):
                if t not in open_doors:
                    open_doors.add(t)
                    added = True
        if not added:
            return reach
    return flood(level, starts, solid, open_doors, north, west)


def type3_xy(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type == 3]


def type5_xy(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type == 5]


def gf_t_metrics(level, reach: set[tuple[int, int]]) -> dict:
    """Geometric checks that GF is the published T (stem south, bar north)."""
    nv = [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type != 0]
    xs = [x for x, _ in nv]
    ys = [y for _, y in nv]
    # stem: southern cells clustered around x~16; bar: northern band spanning x
    south = [(x, y) for x, y in nv if y >= 16]
    north = [(x, y) for x, y in nv if y <= 11]
    south_xs = [x for x, _ in south]
    north_xs = [x for x, _ in north]
    stem_narrow = (max(south_xs) - min(south_xs) <= 8) if south_xs else False
    bar_wide = (max(north_xs) - min(north_xs) >= 20) if north_xs else False
    # known landmarks from prior work / fan map
    landmarks = {
        "stem_save": (6, 2) in reach or (16, 30) in nv,  # (6,2) is save rune; stem foot
        "nw_ladder": (4, 1) in nv,
        "ne_ladder": (28, 3) in nv or (28, 1) in nv,
        "sw_down": (4, 11) in nv,
        "se_feel": (28, 11) in nv,
    }
    return {
        "nv": len(nv),
        "reach": len(reach),
        "bbox": (min(xs), min(ys), max(xs), max(ys)),
        "stem_narrow": stem_narrow,
        "bar_wide": bar_wide,
        "stem_span_x": (min(south_xs), max(south_xs)) if south_xs else None,
        "bar_span_x": (min(north_xs), max(north_xs)) if north_xs else None,
        "landmarks": landmarks,
    }


def draw_walls_assigned(draw, level, y0, cell, north: int, west: int) -> None:
    for i, sec in enumerate(level.sector_list):
        if sec.type == 0:
            continue
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        x1, bot = x0 + cell, top + cell
        n_style = edge_style(sec.walls[north].type)
        if n_style:
            col, width = n_style
            draw.line((x0, top, x1, top), fill=col, width=width)
        w_style = edge_style(sec.walls[west].type)
        if w_style:
            col, width = w_style
            draw.line((x0, top, x0, bot), fill=col, width=width)
        corners = [k for k in range(6) if k not in (north, west)]
        marks = {
            0: ((x0 + x1) // 2, top),
            1: (x0, (top + bot) // 2),
            2: (x1 - 1, top),
            3: (x0, top),
            4: (x1 - 1, bot - 1),
            5: (x0, bot - 1),
        }
        for idx in corners:
            if sec.walls[idx].type == 0:
                continue
            cx, cy = marks.get(idx, ((x0 + x1) // 2, (top + bot) // 2))
            draw.rectangle((cx - 2, cy - 2, cx + 2, cy + 2), fill=(220, 200, 90))


def render_assigned(level, reach, north: int, west: int, tag: str, cell: int = 18) -> Image.Image:
    legend_w = 180
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text(
        (4, 4),
        f"L{level.level_number:02d} {level.name}  slots N={north} W={west}  {tag}"[:78],
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
    draw_walls_assigned(draw, level, y0, cell, north, west)
    return img


def slot_census(levels) -> list[Counter]:
    counts = [Counter() for _ in range(6)]
    for lv in levels:
        for sec in lv.sector_list:
            for i, w in enumerate(sec.walls):
                counts[i][w.type] += 1
    return counts


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 22 — brute-force WallList slot assignment")
    lines.append("slot i = NORTH (-Y) edge; slot j = WEST (-X) edge; other four = corners.")
    lines.append("Flood: arrivals from source LevelChangeList + Type 9, then door adj4 fixed-point.")
    lines.append("Solid A = {32,33}; Solid B = {32,33,64,96,128}.")
    lines.append("")

    starts = [starts_for(levels, n) for n in range(25)]
    nv = [sum(1 for s in lv.sector_list if s.type != 0) for lv in levels]
    total_nv = sum(nv)

    # --- type-per-slot census (independent of flood) ---
    lines.append("========== wall-type census by slot (all 25 x 1024) ==========")
    census = slot_census(levels)
    for i, c in enumerate(census):
        bits = "  ".join(
            f"{WALL_TYPE_NAME.get(t, t)}={c[t]}" for t in sorted(c) if t != 0 or True
        )
        has160 = c.get(160, 0)
        has32 = c.get(32, 0) + c.get(33, 0)
        lines.append(f"  slot {i}: n160={has160:5d}  n32+33={has32:5d}  {dict(sorted(c.items()))}")
    lines.append(
        "  If CutoffCorner(160) is corner-only, slots with n160==0 are the only "
        "plausible edges."
    )

    pairs = list(itertools.permutations(range(6), 2))
    results_a = []
    results_b = []

    def run_all(solid):
        out = []
        for north, west in pairs:
            sealed_lv = []
            reach_lv = []
            for n, lv in enumerate(levels):
                r = propagate(lv, starts[n], solid, north, west)
                reach_lv.append(r)
                sealed_lv.append(nv[n] - len(r))
            out.append((north, west, reach_lv, sealed_lv, sum(sealed_lv)))
        out.sort(key=lambda t: (t[4], t[0], t[1]))
        return out

    lines.append("\n========== (b) 30 ordered pairs, solid A {32,33} ==========")
    results_a = run_all(SOLID_A)
    lines.append(f"{'N,W':>6} {'nv':>6} {'reach':>6} {'sealed':>7}  vs(0,1)")
    sealed_01 = next(t[4] for t in results_a if t[0] == 0 and t[1] == 1)
    for north, west, reach_lv, sealed_lv, tot in results_a:
        reach_n = total_nv - tot
        delta = tot - sealed_01
        mark = "  <-- current" if (north, west) == (0, 1) else ""
        lines.append(
            f"  ({north},{west}) {total_nv:6d} {reach_n:6d} {tot:7d}  {delta:+6d}{mark}"
        )

    lines.append("\n========== (b2) same 30 pairs, solid B {32,33,64,96,128} ==========")
    results_b = run_all(SOLID_B)
    sealed_01b = next(t[4] for t in results_b if t[0] == 0 and t[1] == 1)
    lines.append(f"{'N,W':>6} {'nv':>6} {'reach':>6} {'sealed':>7}  vs A-same  vs B(0,1)")
    a_by = {(t[0], t[1]): t[4] for t in results_a}
    for north, west, reach_lv, sealed_lv, tot in results_b:
        reach_n = total_nv - tot
        lines.append(
            f"  ({north},{west}) {total_nv:6d} {reach_n:6d} {tot:7d}  "
            f"A={a_by[(north, west)]:5d} dA={tot - a_by[(north, west)]:+d}  "
            f"dB01={tot - sealed_01b:+d}"
        )

    # --- (c) top 5 ---
    lines.append("\n========== (c) top 5 assignments by sealed (solid A) ==========")
    top5 = results_a[:5]
    names = [lv.name for lv in levels]
    for rank, (north, west, reach_lv, sealed_lv, tot) in enumerate(top5, 1):
        lines.append(
            f"\n--- #{rank}  (N={north}, W={west})  sealed={tot}  "
            f"reach={total_nv - tot}/{total_nv} ---"
        )
        lines.append(f"{'Lv':>3} {'name':<36} {'nv':>4} {'reach':>5} {'sealed':>6} {'prev':>5}")
        for n in range(25):
            lines.append(
                f"{n:3d} {names[n]:<36} {nv[n]:4d} {len(reach_lv[n]):5d} "
                f"{sealed_lv[n]:6d} {PREV_SEALED[n]:5d}"
            )

    # --- (f) (0,1) vs (1,0) ---
    lines.append("\n========== (f) (0,1) vs (1,0) — Petrich/Semmler name swap ==========")
    t01 = next(t for t in results_a if t[0] == 0 and t[1] == 1)
    t10 = next(t for t in results_a if t[0] == 1 and t[1] == 0)
    lines.append(f"  (0,1) Petrich current: sealed={t01[4]}")
    lines.append(f"  (1,0) swapped N/W:     sealed={t10[4]}")
    lines.append(
        f"  differ: {t01[4] != t10[4]}  delta={(t10[4] - t01[4]):+d}"
    )
    if t01[4] != t10[4]:
        lines.append("  North/west assignment MATTERS. Naming conflict is material.")
        lines.append("  per-level sealed (0,1) vs (1,0):")
        for n in range(25):
            if t01[3][n] != t10[3][n]:
                lines.append(
                    f"    L{n:02d} {names[n]}: (0,1)={t01[3][n]}  (1,0)={t10[3][n]}"
                )
    else:
        lines.append("  North/west assignment does not change total sealed.")

    # --- (e) validation gates on top candidates + (0,1) + (1,0) ---
    lines.append("\n========== (e) validation gates ==========")
    # L13 landmarks
    l13 = levels[13]
    l13_t3 = type3_xy(l13)
    l13_corners = []
    for x, y in l13_t3:
        if (x <= 2 or x >= 29) and (y <= 2 or y >= 29):
            l13_corners.append((x, y))
    centre_drops = [(16, 18), (16, 17)]

    # L3/L4 type 5 — secret closets must stay sealed
    secret_tiles = {
        3: type5_xy(levels[3]),
        4: type5_xy(levels[4]),
    }

    def gates(north, west, reach_lv):
        gf_r = reach_lv[0]
        gf_ok = len(gf_r) == 214
        gf_m = gf_t_metrics(levels[0], gf_r)
        shape_ok = gf_ok and gf_m["stem_narrow"] and gf_m["bar_wide"]
        l13_r = reach_lv[13]
        centre_ok = (16, 18) in l13_r
        # (16,17) is void in the template — must not be reachable
        void_drop = levels[13].sector_at(16, 17).type == 0
        corners_reach = [(p, p in l13_r) for p in l13_corners]
        maze = len(l13_r)
        # secret closets: Type 5 tiles themselves should stay sealed
        secrets_open = []
        for ln, tiles in secret_tiles.items():
            for p in tiles:
                if p in reach_lv[ln]:
                    secrets_open.append((ln, p))
        secret_ok = len(secrets_open) == 0
        l9_open = nv[9] - len(reach_lv[9]) == 0
        l10_open = nv[10] - len(reach_lv[10]) == 0
        return {
            "gf_214": gf_ok,
            "gf_T_shape": shape_ok,
            "gf_metrics": gf_m,
            "l13_centre": centre_ok,
            "l13_void17": void_drop,
            "l13_maze": maze,
            "l13_corners": corners_reach,
            "secret_closets_sealed": secret_ok,
            "secrets_open": secrets_open,
            "l9_fully_open": l9_open,
            "l10_fully_open": l10_open,
            "l9_sealed": nv[9] - len(reach_lv[9]),
            "l10_sealed": nv[10] - len(reach_lv[10]),
        }

    reviewed = []
    seen_pairs = set()
    for item in top5 + [t01, t10]:
        key = (item[0], item[1])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        reviewed.append(item)

    any_opens_l9l10_and_gf = False
    for north, west, reach_lv, sealed_lv, tot in reviewed:
        g = gates(north, west, reach_lv)
        lines.append(f"\n--- assignment (N={north}, W={west}) sealed={tot} ---")
        lines.append(f"  GF 214/214:              {'PASS' if g['gf_214'] else 'FAIL'}  ({g['gf_metrics']['reach']}/214)")
        lines.append(
            f"  GF T (bar north, stem S): {'PASS' if g['gf_T_shape'] else 'FAIL'}  "
            f"stem_x={g['gf_metrics']['stem_span_x']} bar_x={g['gf_metrics']['bar_span_x']} "
            f"narrow={g['gf_metrics']['stem_narrow']} wide={g['gf_metrics']['bar_wide']}"
        )
        lines.append(
            f"  L13 centre (16,18) reach: {'PASS' if g['l13_centre'] else 'FAIL'}  "
            f"maze={g['l13_maze']}  (16,17) void={g['l13_void17']}"
        )
        cstat = ", ".join(
            f"{p}={'R' if ok else 'sealed'}" for p, ok in g["l13_corners"]
        )
        lines.append(f"  L13 corner ladders:      {cstat or '(none tagged as corners)'}")
        lines.append(
            f"  L3/L4 Type5 stay sealed: {'PASS' if g['secret_closets_sealed'] else 'FAIL'}  "
            f"opened={g['secrets_open']}"
        )
        lines.append(
            f"  L9 sealed={g['l9_sealed']}/415  L10 sealed={g['l10_sealed']}/574  "
            f"opened={g['l9_fully_open'] and g['l10_fully_open']}"
        )
        if g["gf_214"] and g["gf_T_shape"] and (g["l9_fully_open"] or g["l10_fully_open"]):
            any_opens_l9l10_and_gf = True

    # Did ANY of the 30 open L9/L10 while keeping GF 214?
    lines.append("\n========== any assignment opens L9/L10 with GF intact? ==========")
    winners_l9 = []
    for north, west, reach_lv, sealed_lv, tot in results_a:
        g = gates(north, west, reach_lv)
        if (g["l9_fully_open"] or g["l10_fully_open"]) and g["gf_214"]:
            winners_l9.append((north, west, tot, g))
            lines.append(
                f"  (N={north},W={west}) sealed={tot} GF={g['gf_metrics']['reach']} "
                f"T={g['gf_T_shape']} L9s={g['l9_sealed']} L10s={g['l10_sealed']} "
                f"L13c={g['l13_centre']} secrets={g['secret_closets_sealed']}"
            )
    if not winners_l9:
        lines.append("  NONE. No (i,j) opens L9 or L10 while keeping Ground Floor 214/214.")
        lines.append("  Slot order (0,1) is consistent with the gates; the L9/L10 mechanic is elsewhere.")

    # pick winning assignment: fewest sealed among those passing GF 214 + T + secrets + L13 centre
    lines.append("\n========== winning assignment ==========")
    passing = []
    for north, west, reach_lv, sealed_lv, tot in results_a:
        g = gates(north, west, reach_lv)
        if g["gf_214"] and g["gf_T_shape"] and g["secret_closets_sealed"] and g["l13_centre"]:
            passing.append((north, west, reach_lv, sealed_lv, tot, g))
    if passing:
        win = min(passing, key=lambda t: (t[4], t[0], t[1]))
        lines.append(
            f"  Fewest sealed among gate-passers: (N={win[0]}, W={win[1]}) sealed={win[4]}"
        )
        lines.append(f"  Current assumption (0,1) is {'the winner' if win[0]==0 and win[1]==1 else 'NOT the winner'}.")
    else:
        win = t01
        lines.append("  No assignment passed every gate. Falling back to (0,1) for renders.")
        win = (0, 1, t01[2], t01[3], t01[4], gates(0, 1, t01[2]))

    wn, ww, wreach = win[0], win[1], win[2]
    for n in (0, 9, 10):
        tag = "win"
        img = render_assigned(levels[n], wreach[n], wn, ww, tag)
        path = OUT / f"L{n:02d}_slots.png"
        img.save(path)
        lines.append(f"  wrote {path.name}")

    # also render (1,0) GF if it differs, for the naming conflict
    if t10[4] != t01[4] or True:
        img = render_assigned(levels[0], t10[2][0], 1, 0, "swap10")
        img.save(OUT / "L00_slots_10.png")
        lines.append("  wrote L00_slots_10.png  (N=1,W=0 swap)")

    lines.append(f"\nGround Floor under winner: {len(wreach[0])}/214")
    lines.append(f"L9 under winner: {len(wreach[9])}/{nv[9]} sealed={nv[9]-len(wreach[9])}")
    lines.append(f"L10 under winner: {len(wreach[10])}/{nv[10]} sealed={nv[10]-len(wreach[10])}")

    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
