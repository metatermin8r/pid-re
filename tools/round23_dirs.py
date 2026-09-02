# -*- coding: utf-8 -*-
"""Test which SIDE of a sector WallList[0]/[1] sit on, plus L9/L10 density."""

from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, load_maps  # noqa: E402
from round18_walls import SOLID_A  # noqa: E402
from round19_doors import find_doors_adj4, is_open_action, trigger_sectors  # noqa: E402
from round22_slots import (  # noqa: E402
    arrivals_to,
    gf_t_metrics,
    render_assigned,
    starts_for,
    type3_xy,
    type5_xy,
)

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round23_dirs.txt"

# Convention: slot_a faces dir_a on the storing sector; slot_b faces dir_b.
# dir is (dx, dy) of the face: N=(0,-1), S=(0,1), W=(-1,0), E=(1,0).
CONVENTIONS = {
    "N/W": ((0, -1), (-1, 0)),
    "S/E": ((0, 1), (1, 0)),
    "N/E": ((0, -1), (1, 0)),
    "S/W": ((0, 1), (-1, 0)),
}

SLOT_PAIRS = [
    (0, 1, "current"),
    (0, 2, "mixed-A"),
    (0, 3, "mixed-A"),
    (0, 4, "mixed-A"),
    (0, 5, "mixed-A"),
    (2, 1, "mixed-B"),
    (3, 1, "mixed-B"),
    (4, 1, "mixed-B"),
    (5, 1, "mixed-B"),
]


def edge_type(level, x, y, nx, ny, slot_a: int, slot_b: int, dir_a, dir_b) -> int:
    """Wall type on the shared edge, stored on the sector that owns that face."""
    step = (nx - x, ny - y)
    for slot, face in ((slot_a, dir_a), (slot_b, dir_b)):
        if step == face:
            return level.sector_at(x, y).walls[slot].type
        opposite = (-face[0], -face[1])
        if step == opposite:
            return level.sector_at(nx, ny).walls[slot].type
    return -1


def blocked(level, x, y, nx, ny, solid, open_doors, slot_a, slot_b, dir_a, dir_b) -> bool:
    if not (0 <= nx < GRID and 0 <= ny < GRID):
        return True
    if level.sector_at(nx, ny).type == 0:
        return True
    wt = edge_type(level, x, y, nx, ny, slot_a, slot_b, dir_a, dir_b)
    if wt not in solid:
        return False
    if (x, y) in open_doors or (nx, ny) in open_doors:
        return False
    return True


def flood(level, starts, solid, open_doors, slot_a, slot_b, dir_a, dir_b):
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
            if blocked(level, x, y, nx, ny, solid, open_doors, slot_a, slot_b, dir_a, dir_b):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def propagate(level, starts, slot_a, slot_b, dir_a, dir_b, use_keys: bool = True):
    open_doors: set[tuple[int, int]] = set()
    for _ in range(64):
        reach = flood(level, starts, SOLID_A, open_doors, slot_a, slot_b, dir_a, dir_b)
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
    return flood(level, starts, SOLID_A, open_doors, slot_a, slot_b, dir_a, dir_b)


def flood_among(level, seeds, allowed, slot_a, slot_b, dir_a, dir_b):
    """Wall-aware flood that may only step onto `allowed` tiles."""
    seen: set[tuple[int, int]] = set()
    q: deque[tuple[int, int]] = deque()
    for p in seeds:
        if p not in allowed:
            continue
        if p not in seen:
            seen.add(p)
            q.append(p)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (nx, ny) in seen or (nx, ny) not in allowed:
                continue
            if blocked(level, x, y, nx, ny, SOLID_A, set(), slot_a, slot_b, dir_a, dir_b):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def adj_components(tiles: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    left = set(tiles)
    comps = []
    while left:
        seed = next(iter(left))
        seen = {seed}
        q = deque([seed])
        left.remove(seed)
        while q:
            x, y = q.popleft()
            for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
                if (nx, ny) in left:
                    left.remove((nx, ny))
                    seen.add((nx, ny))
                    q.append((nx, ny))
        comps.append(seen)
    return comps


def edge_density(level, tiles: set[tuple[int, int]] | None = None) -> dict:
    n32 = n_short = n0 = n_other = 0
    n_slots = 0
    for i, sec in enumerate(level.sector_list):
        if sec.type == 0:
            continue
        x, y = i % GRID, i // GRID
        if tiles is not None and (x, y) not in tiles:
            continue
        for wi in (0, 1):
            n_slots += 1
            t = sec.walls[wi].type
            if t in (32, 33):
                n32 += 1
            elif t in (64, 96, 128):
                n_short += 1
            elif t == 0:
                n0 += 1
            else:
                n_other += 1
    return {
        "slots": n_slots,
        "solid": n32,
        "short": n_short,
        "none": n0,
        "other": n_other,
        "solid_frac": (n32 / n_slots) if n_slots else 0.0,
        "short_frac": (n_short / n_slots) if n_slots else 0.0,
        "none_frac": (n0 / n_slots) if n_slots else 0.0,
    }


def item_ids(level) -> list[int]:
    return sorted({s.item for s in level.sector_list if s.item != -1})


def contig_report(ids: list[int]) -> str:
    if not ids:
        return "empty"
    lo, hi = ids[0], ids[-1]
    holes = [n for n in range(lo, hi + 1) if n not in set(ids)]
    from_zero = lo == 0 and not holes
    return (
        f"n={len(ids)} min={lo} max={hi} holes={len(holes)} "
        f"contiguous_0_N={from_zero} "
        f"hole_list={holes[:20]}{'…' if len(holes) > 20 else ''}"
    )


def gates(levels, reach_lv, nv):
    gf_r = reach_lv[0]
    gf_ok = len(gf_r) == 214
    gf_m = gf_t_metrics(levels[0], gf_r)
    shape_ok = gf_ok and gf_m["stem_narrow"] and gf_m["bar_wide"]
    l13_r = reach_lv[13]
    centre_ok = (16, 18) in l13_r
    maze = len(l13_r)
    maze_ok = centre_ok and 180 <= maze <= 230
    l13_t3 = type3_xy(levels[13])
    corners = [
        p for p in l13_t3 if (p[0] <= 2 or p[0] >= 29) and (p[1] <= 2 or p[1] >= 29)
    ]
    corners_sealed = all(p not in l13_r for p in corners)
    secrets_open = []
    for ln in (3, 4):
        for p in type5_xy(levels[ln]):
            if p in reach_lv[ln]:
                secrets_open.append((ln, p))
    secret_ok = not secrets_open
    return {
        "gf_214": gf_ok,
        "gf_T": shape_ok,
        "gf_reach": len(gf_r),
        "l13_centre": centre_ok,
        "l13_maze": maze,
        "l13_maze_ok": maze_ok,
        "l13_corners_sealed": corners_sealed,
        "l13_corners": [(p, p in l13_r) for p in corners],
        "secret_ok": secret_ok,
        "secrets_open": secrets_open,
        "l9_sealed": nv[9] - len(reach_lv[9]),
        "l10_sealed": nv[10] - len(reach_lv[10]),
        "all_pass": gf_ok and shape_ok and maze_ok and corners_sealed and secret_ok,
    }


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 23 — wall direction conventions + L9/L10 density")
    lines.append("Flood: arrivals + Type 9, then door adj4 fixed-point. Solid={32,33}.")
    lines.append("")

    starts = [starts_for(levels, n) for n in range(25)]
    nv = [sum(1 for s in lv.sector_list if s.type != 0) for lv in levels]
    total_nv = sum(nv)
    names = [lv.name for lv in levels]

    # baseline N/W (0,1)
    base_reach = [
        propagate(lv, starts[n], 0, 1, *CONVENTIONS["N/W"])
        for n, lv in enumerate(levels)
    ]
    base_sealed = [nv[n] - len(base_reach[n]) for n in range(25)]
    base_tot = sum(base_sealed)
    lines.append(f"Baseline N/W (0,1) sealed={base_tot} reach={total_nv - base_tot}/{total_nv}")

    # --- (a)+(b) all conventions × slot pairs ---
    lines.append("\n========== (a/b) convention × slot pair ==========")
    lines.append(
        f"{'slots':<8} {'conv':<5} {'kind':<8} {'reach':>6} {'sealed':>7} {'d01':>6}  gates"
    )
    results = []
    for slot_a, slot_b, kind in SLOT_PAIRS:
        for cname, (dir_a, dir_b) in CONVENTIONS.items():
            reach_lv = [
                propagate(lv, starts[n], slot_a, slot_b, dir_a, dir_b)
                for n, lv in enumerate(levels)
            ]
            sealed_lv = [nv[n] - len(r) for n, r in enumerate(reach_lv)]
            tot = sum(sealed_lv)
            g = gates(levels, reach_lv, nv)
            flag = []
            if g["all_pass"]:
                flag.append("ALL_GATES")
            else:
                if not g["gf_214"]:
                    flag.append(f"GF={g['gf_reach']}")
                if not g["gf_T"]:
                    flag.append("noT")
                if not g["l13_maze_ok"]:
                    flag.append(f"L13={g['l13_maze']}")
                if not g["l13_corners_sealed"]:
                    flag.append("L13corners")
                if not g["secret_ok"]:
                    flag.append(f"secrets{g['secrets_open']}")
            if g["l9_sealed"] == 0:
                flag.append("L9OPEN")
            if g["l10_sealed"] == 0:
                flag.append("L10OPEN")
            results.append((slot_a, slot_b, cname, kind, reach_lv, sealed_lv, tot, g))
            lines.append(
                f"  ({slot_a},{slot_b}) {cname:<5} {kind:<8} {total_nv - tot:6d} {tot:7d} "
                f"{tot - base_tot:+6d}  {' '.join(flag) if flag else 'ok-ish'}"
            )

    # per-level for anything that beats 3341
    lines.append("\n========== per-level for conventions that beat 3341 ==========")
    beat = [r for r in results if r[6] < base_tot]
    if not beat:
        lines.append("  none")
    for slot_a, slot_b, cname, kind, reach_lv, sealed_lv, tot, g in beat:
        lines.append(
            f"\n--- ({slot_a},{slot_b}) {cname} {kind} sealed={tot} "
            f"L9s={g['l9_sealed']} L10s={g['l10_sealed']} ---"
        )
        lines.append(f"{'Lv':>3} {'name':<36} {'nv':>4} {'reach':>5} {'sealed':>6} {'base':>5}")
        for n in range(25):
            if sealed_lv[n] != base_sealed[n]:
                lines.append(
                    f"{n:3d} {names[n]:<36} {nv[n]:4d} {len(reach_lv[n]):5d} "
                    f"{sealed_lv[n]:6d} {base_sealed[n]:5d}"
                )

    # --- (c) gates in full for (0,1) × 4 and best mixed ---
    lines.append("\n========== (c) validation gates ==========")
    review = [r for r in results if r[0] == 0 and r[1] == 1]
    # plus the best mixed per convention if different
    seen = {(0, 1, c) for c in CONVENTIONS}
    for r in sorted(results, key=lambda t: t[6]):
        key = (r[0], r[1], r[2])
        if key in seen:
            continue
        if r[3] != "current" and (r[6] < base_tot or r[7]["all_pass"]):
            review.append(r)
            seen.add(key)
    # always include one mixed-A and mixed-B under N/W for contrast
    for want in ((0, 2, "N/W"), (2, 1, "N/W")):
        extra = next(r for r in results if (r[0], r[1], r[2]) == want)
        if (extra[0], extra[1], extra[2]) not in seen:
            review.append(extra)

    for slot_a, slot_b, cname, kind, reach_lv, sealed_lv, tot, g in review:
        lines.append(f"\n--- ({slot_a},{slot_b}) {cname} sealed={tot} ---")
        lines.append(f"  GF 214/214:              {'PASS' if g['gf_214'] else 'FAIL'} ({g['gf_reach']}/214)")
        lines.append(f"  GF T bar-N stem-S:       {'PASS' if g['gf_T'] else 'FAIL'}")
        lines.append(
            f"  L13 centre~200 corners:  "
            f"{'PASS' if g['l13_maze_ok'] and g['l13_corners_sealed'] else 'FAIL'}  "
            f"maze={g['l13_maze']} centre={g['l13_centre']} "
            f"corners={[p for p, ok in g['l13_corners'] if ok] or 'all sealed'}"
        )
        lines.append(
            f"  L3/L4 Type5 sealed:      {'PASS' if g['secret_ok'] else 'FAIL'} "
            f"{g['secrets_open']}"
        )
        lines.append(f"  L9 sealed={g['l9_sealed']}/415  L10 sealed={g['l10_sealed']}/574")

    winners = [r for r in results if r[7]["all_pass"] and r[7]["l9_sealed"] == 0 and r[7]["l10_sealed"] == 0]
    lines.append("\n========== (h) combination that opens L9/L10 and passes every gate ==========")
    if winners:
        for r in winners:
            lines.append(f"  WIN ({r[0]},{r[1]}) {r[2]} sealed={r[6]}")
    else:
        lines.append("  NONE. No slot/direction combination opens L9 and L10 while passing every gate.")

    # --- (d) wall density per level ---
    lines.append("\n========== (d) wall density per level (slots 0+1, non-Void) ==========")
    dens = []
    for n, lv in enumerate(levels):
        tiles = {
            (i % GRID, i // GRID)
            for i, s in enumerate(lv.sector_list)
            if s.type != 0
        }
        d = edge_density(lv, tiles)
        dens.append((n, d))
    dens_sorted = sorted(dens, key=lambda t: t[1]["solid_frac"], reverse=True)
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'slots':>5} {'32/33':>6} {'frac':>6} "
        f"{'short':>5} {'sfrac':>6} {'none':>5} {'nfrac':>6} {'oth':>4}"
    )
    rank_of = {}
    for rank, (n, d) in enumerate(dens_sorted, 1):
        rank_of[n] = rank
        lines.append(
            f"{n:3d} {names[n]:<36} {nv[n]:4d} {d['slots']:5d} {d['solid']:6d} "
            f"{d['solid_frac']:6.3f} {d['short']:5d} {d['short_frac']:6.3f} "
            f"{d['none']:5d} {d['none_frac']:6.3f} {d['other']:4d}"
        )
    lines.append(
        f"\n  L9 density rank={rank_of[9]}/25  L10 rank={rank_of[10]}/25  "
        f"(1 = densest 32/33)"
    )

    # --- (e) sealed vs reachable density on L9/L10 ---
    lines.append("\n========== (e) L9/L10 sealed vs reachable edge density ==========")
    dir_a, dir_b = CONVENTIONS["N/W"]
    for n in (9, 10):
        reach = base_reach[n]
        sealed = {
            (i % GRID, i // GRID)
            for i, s in enumerate(levels[n].sector_list)
            if s.type != 0 and (i % GRID, i // GRID) not in reach
        }
        dr = edge_density(levels[n], reach)
        ds = edge_density(levels[n], sealed)
        lines.append(f"\n--- L{n:02d} {names[n]}  reach={len(reach)} sealed={len(sealed)} ---")
        for label, d in (("REACH", dr), ("SEAL ", ds)):
            lines.append(
                f"  {label} slots={d['slots']}  32/33={d['solid']} ({d['solid_frac']:.3f})  "
                f"short={d['short']} ({d['short_frac']:.3f})  "
                f"none={d['none']} ({d['none_frac']:.3f})"
            )

        # frontier: sealed tile 4-adj to a reachable tile
        front_sealed = set()
        front_reach = set()
        for x, y in sealed:
            for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
                if (nx, ny) in reach:
                    front_sealed.add((x, y))
                    front_reach.add((nx, ny))
        df = edge_density(levels[n], front_sealed)
        lines.append(
            f"  FRONTIER sealed tiles={len(front_sealed)}  "
            f"32/33={df['solid']}/{df['slots']} ({df['solid_frac']:.3f})"
        )

    # --- (f) sealed-mass connectivity + corpses/loot ---
    lines.append("\n========== (f) sealed-mass connectivity + contents ==========")
    for n in (9, 10):
        lv = levels[n]
        reach = base_reach[n]
        sealed = {
            (i % GRID, i // GRID)
            for i, s in enumerate(lv.sector_list)
            if s.type != 0 and (i % GRID, i // GRID) not in reach
        }
        geom = adj_components(sealed)
        lines.append(f"\n--- L{n:02d} {lv.name} ---")
        lines.append(
            f"  4-adj components (ignore walls): {len(geom)}  "
            f"sizes={sorted((len(c) for c in geom), reverse=True)}"
        )
        # wall-aware components
        left = set(sealed)
        wcomps = []
        while left:
            seed = next(iter(left))
            comp = flood_among(lv, [seed], sealed, 0, 1, *CONVENTIONS["N/W"])
            wcomps.append(comp)
            left -= comp
        lines.append(
            f"  wall-aware components (N/W 0,1): {len(wcomps)}  "
            f"sizes={sorted((len(c) for c in wcomps), reverse=True)}"
        )

        corpses = [
            (i % GRID, i // GRID, s.item, s.type_addl)
            for i, s in enumerate(lv.sector_list)
            if s.type == 6
        ]
        for x, y, item, addl in corpses:
            bucket = "SEALED" if (x, y) in sealed else ("REACH" if (x, y) in reach else "?")
            lines.append(
                f"  corpse ({x},{y}) Item={item} addl={addl} scri={128 + addl} {bucket}"
            )

        by_type = Counter()
        items_seal = 0
        items_reach = 0
        for i, s in enumerate(lv.sector_list):
            p = (i % GRID, i // GRID)
            if s.type == 0:
                continue
            key = "SEAL" if p in sealed else "REACH"
            by_type[(key, s.type)] += 1
            if s.item != -1:
                if p in sealed:
                    items_seal += 1
                else:
                    items_reach += 1
        lines.append(f"  Item!=-1 in sealed={items_seal}  in reachable={items_reach}")
        for key in ("SEAL", "REACH"):
            parts = [
                f"{SECTOR_TYPE_NAME.get(t, t)}={by_type[(key, t)]}"
                for t in range(10)
                if by_type[(key, t)]
            ]
            lines.append(f"  {key} types: {', '.join(parts)}")

        # saves
        for i, s in enumerate(lv.sector_list):
            if s.type == 9:
                p = (i % GRID, i // GRID)
                bucket = "SEALED" if p in sealed else "REACH"
                lines.append(f"  save {p} Item={s.item} {bucket}")

    # --- (g) Item contiguity ---
    lines.append("\n========== (g) Item value contiguity (Item != -1) ==========")
    lines.append(f"{'Lv':>3} {'name':<36} {'report'}")
    for n, lv in enumerate(levels):
        ids = item_ids(lv)
        mark = ""
        if n in (9, 10, 13):
            mark = "  <--"
        lines.append(f"{n:3d} {lv.name:<36} {contig_report(ids)}{mark}")

    # --- (h) render? ---
    lines.append("\n========== (h) renders ==========")
    if winners:
        w = winners[0]
        lines.append(f"  Re-rendering all 25 under ({w[0]},{w[1]}) {w[2]}")
        # direction-aware render: reuse slot draw for (0,1) N/W only if that's the winner
        for n, lv in enumerate(levels):
            img = render_assigned(lv, w[4][n], w[0], w[1], f"{w[2]}-win")
            img.save(OUT / f"L{n:02d}_dirs.png")
        lines.append("  wrote L00_dirs.png … L24_dirs.png")
    else:
        lines.append("  No winning combination. Not re-rendering all 25.")
        lines.append("  L9/L10 connectivity is unexplained under every tested wall interpretation.")

    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
