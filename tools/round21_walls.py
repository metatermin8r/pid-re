# -*- coding: utf-8 -*-
"""Round 21 — L9/L10 SwitchableWallCorner, frontier, type-1 census."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import (  # noqa: E402
    GRID,
    SECTOR_TYPE_NAME,
    WALL_TYPE_NAME,
    load_maps,
)
from round18_walls import SOLID_A, neighbors4  # noqa: E402
from round20_arrive import (  # noqa: E402
    CHANGE_NAME,
    change_name,
    is_live_change,
    propagate_from,
    save_positions,
)

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
REPORT = ROOT / "reference/docs/round21_walls.txt"

WALL_INDEX_NAME = {
    0: "Wall_Y / north",
    1: "Wall_X / west",
    2: "Corner_HighX_LowY",
    3: "Corner_LowX_LowY",
    4: "Corner_HighX_HighY",
    5: "Corner_LowX_HighY",
}


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


def edge_owner(x: int, y: int, nx: int, ny: int) -> tuple[int, int, int] | None:
    """Return (wx, wy, wall_index) for the edge between (x,y) and (nx,ny)."""
    if nx == x and ny == y - 1:
        return x, y, 0
    if nx == x - 1 and ny == y:
        return x, y, 1
    if nx == x and ny == y + 1:
        return x, y + 1, 0
    if nx == x + 1 and ny == y:
        return x + 1, y, 1
    return None


def frontier_edges(level, reach: set[tuple[int, int]]):
    """4-adjacent (reachable, sealed-nonvoid) pairs plus owning wall."""
    out = []
    seen = set()
    for x, y in sorted(reach):
        for nx, ny in neighbors4(x, y):
            if not (0 <= nx < GRID and 0 <= ny < GRID):
                continue
            dest = level.sector_at(nx, ny)
            if dest.type == 0:
                continue
            if (nx, ny) in reach:
                continue
            key = tuple(sorted(((x, y), (nx, ny))))
            if key in seen:
                continue
            seen.add(key)
            owner = edge_owner(x, y, nx, ny)
            if owner is None:
                continue
            wx, wy, wi = owner
            wall = level.sector_at(wx, wy).walls[wi]
            out.append(((x, y), (nx, ny), wi, wall.type, wall.texture, wx, wy))
    return out


def type1_hits(level):
    hits = []
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        for wi, w in enumerate(sec.walls):
            if w.type == 1:
                hits.append((x, y, wi, w.texture, sec.type, sec.item))
    return hits


def census_type1(level) -> tuple[int, ...]:
    counts = [0] * 6
    for sec in level.sector_list:
        for wi, w in enumerate(sec.walls):
            if w.type == 1:
                counts[wi] += 1
    return tuple(counts)


def texture_hist(level, wall_types: frozenset[int] | None = None, edges_only: bool = True):
    c = Counter()
    for sec in level.sector_list:
        rng = (0, 1) if edges_only else range(6)
        for wi in rng:
            w = sec.walls[wi]
            if wall_types is None or w.type in wall_types:
                if w.type != 0:
                    c[(w.type, w.texture)] += 1
    return c


def flood_passable_types(level, starts, extra_passable: frozenset[int]):
    """Reachability treating extra wall types as passable (still void-blocked)."""
    from collections import deque

    seen: set[tuple[int, int]] = set()
    q = deque()
    for p in starts:
        x, y = p
        if not (0 <= x < GRID and 0 <= y < GRID):
            continue
        if level.sector_at(x, y).type == 0:
            continue
        if p not in seen:
            seen.add(p)
            q.append(p)
    solid = SOLID_A - extra_passable
    while q:
        x, y = q.popleft()
        for nx, ny in neighbors4(x, y):
            if (nx, ny) in seen:
                continue
            if not (0 <= nx < GRID and 0 <= ny < GRID):
                continue
            if level.sector_at(nx, ny).type == 0:
                continue
            owner = edge_owner(x, y, nx, ny)
            if owner is None:
                continue
            wx, wy, wi = owner
            wt = level.sector_at(wx, wy).walls[wi].type
            if wt in solid:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def describe_sector(level, x: int, y: int, reach) -> str:
    if not (0 <= x < GRID and 0 <= y < GRID):
        return f"  ({x},{y}) OOB"
    sec = level.sector_at(x, y)
    bucket = "REACH" if (x, y) in reach else "SEAL"
    if sec.type == 0:
        bucket = "VOID"
    walls = ", ".join(
        f"{wi}:{WALL_TYPE_NAME.get(w.type, w.type)}/tex{w.texture}"
        for wi, w in enumerate(sec.walls)
        if w.type != 0
    )
    return (
        f"  ({x:2d},{y:2d}) type={sec.type} {SECTOR_TYPE_NAME.get(sec.type, '?'):16s} "
        f"Item={sec.item:4d} addl={sec.type_addl:3d} {bucket}  walls=[{walls}]"
    )


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 21 — SwitchableWallCorner + L9/L10 frontier")
    lines.append("Start set: arrivals from other levels' LevelChangeList + Type 9.")
    lines.append("Doors: round-19 adj4 fixed-point with keys.")
    lines.append("")

    starts = [starts_for(levels, n) for n in range(25)]
    reach = []
    for n, lv in enumerate(levels):
        r, _, _ = propagate_from(lv, starts[n], use_keys=True)
        reach.append(r)

    # --- Task 1a: every type-1 wall on L9 / L10 ---
    lines.append("========== TASK 1a  type-1 walls on L9 / L10 ==========")
    for n in (9, 10):
        lv = levels[n]
        hits = type1_hits(lv)
        lines.append(f"\n--- L{n:02d} {lv.name}  type-1 count={len(hits)} ---")
        if not hits:
            lines.append("  NONE")
            continue
        by_idx = Counter(h[2] for h in hits)
        by_reach = Counter(
            "REACH" if (h[0], h[1]) in reach[n] else "SEAL" for h in hits
        )
        lines.append(f"  by WallList index: {dict(sorted(by_idx.items()))}")
        lines.append(f"  by reach: {dict(by_reach)}")
        for x, y, wi, tex, st, item in hits:
            bucket = "REACH" if (x, y) in reach[n] else "SEAL"
            lines.append(
                f"  ({x:2d},{y:2d}) idx={wi} {WALL_INDEX_NAME[wi]:20s} "
                f"tex={tex:3d} sector={SECTOR_TYPE_NAME.get(st, st)} "
                f"Item={item:4d} {bucket}"
            )

    # --- Task 1b: type-1 on frontier? ---
    lines.append("\n========== TASK 1b  type-1 on the arrival/sealed frontier ==========")
    for n in (9, 10):
        lv = levels[n]
        front = frontier_edges(lv, reach[n])
        t1_front = [e for e in front if e[3] == 1]
        lines.append(
            f"\nL{n:02d}: frontier edges={len(front)}  type-1 on frontier={len(t1_front)}"
        )
        for e in t1_front:
            (ax, ay), (bx, by), wi, wt, tex, wx, wy = e
            lines.append(
                f"  ({ax},{ay})-({bx},{by}) owner=({wx},{wy})[{wi}] "
                f"type={wt} tex={tex}"
            )
        extra = flood_passable_types(lv, starts[n], frozenset({1}))
        lines.append(
            f"  treating type-1 as passable: reach {len(reach[n])} -> {len(extra)} "
            f"(gain {len(extra) - len(reach[n])})"
        )

    # --- Task 1c: per-level census ---
    lines.append("\n========== TASK 1c  type-1 census all 25 levels ==========")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'e0':>5} {'e1':>5} {'c2':>5} {'c3':>5} "
        f"{'c4':>5} {'c5':>5} {'tot':>6}"
    )
    totals = [0] * 6
    for n, lv in enumerate(levels):
        c = census_type1(lv)
        for i, v in enumerate(c):
            totals[i] += v
        lines.append(
            f"{n:3d} {lv.name:<36} {c[0]:5d} {c[1]:5d} {c[2]:5d} {c[3]:5d} "
            f"{c[4]:5d} {c[5]:5d} {sum(c):6d}"
        )
    lines.append(
        f"{'':3} {'TOTAL':<36} {totals[0]:5d} {totals[1]:5d} {totals[2]:5d} "
        f"{totals[3]:5d} {totals[4]:5d} {totals[5]:5d} {sum(totals):6d}"
    )
    cluster = {n: sum(census_type1(levels[n])) for n in (9, 10, 13)}
    others = sum(sum(census_type1(levels[n])) for n in range(25) if n not in (9, 10, 13))
    lines.append(
        f"\nL9+L10+L13 type-1 total={sum(cluster.values())}  "
        f"(L9={cluster[9]} L10={cluster[10]} L13={cluster[13]})  "
        f"other 22 levels={others}"
    )

    # --- Task 2a: every frontier edge ---
    lines.append("\n========== TASK 2a  frontier edges L9 / L10 ==========")
    for n in (9, 10):
        lv = levels[n]
        front = frontier_edges(lv, reach[n])
        lines.append(
            f"\n--- L{n:02d} {lv.name}  reachable={len(reach[n])} "
            f"frontier={len(front)} ---"
        )
        for (ax, ay), (bx, by), wi, wt, tex, wx, wy in front:
            a = lv.sector_at(ax, ay)
            b = lv.sector_at(bx, by)
            lines.append(
                f"  REACH({ax:2d},{ay:2d}) t={a.type}/{SECTOR_TYPE_NAME.get(a.type,'?')} "
                f"Item={a.item:4d}  |  SEAL({bx:2d},{by:2d}) "
                f"t={b.type}/{SECTOR_TYPE_NAME.get(b.type,'?')} Item={b.item:4d}  "
                f"wall[{wi}]@{wx},{wy} type={wt} {WALL_TYPE_NAME.get(wt, wt)} tex={tex}"
            )

    # --- Task 2b: frontier texture vs ordinary ---
    lines.append("\n========== TASK 2b  frontier texture vs ordinary walls ==========")
    for n in (9, 10):
        lv = levels[n]
        front = frontier_edges(lv, reach[n])
        front_tex = Counter((e[3], e[4]) for e in front)
        all_tex = texture_hist(lv, wall_types=frozenset({32, 33}), edges_only=True)
        lines.append(f"\n--- L{n:02d} {lv.name} ---")
        lines.append("  frontier (type, tex) counts:")
        for k, v in sorted(front_tex.items()):
            lines.append(f"    type={k[0]} tex={k[1]:3d}  n={v}")
        lines.append("  all edge 32/33 (type, tex) counts:")
        for k, v in sorted(all_tex.items()):
            mark = "  <-- used on frontier" if k in front_tex else ""
            lines.append(f"    type={k[0]} tex={k[1]:3d}  n={v}{mark}")
        only_front = set(front_tex) - set(all_tex)
        # all_tex includes frontier; compare uniqueness another way
        front_only_tex = set()
        for typ, tex in front_tex:
            ordinary = all_tex[(typ, tex)] - front_tex[(typ, tex)]
            if ordinary == 0:
                front_only_tex.add((typ, tex))
        if front_only_tex:
            lines.append(f"  DISTINCT (never used off-frontier): {sorted(front_only_tex)}")
        else:
            lines.append("  No frontier (type,tex) pair is unique to the frontier.")

    # --- Task 2c: arrival items + neighbours ---
    lines.append("\n========== TASK 2c  boxed arrival Items + neighbours ==========")
    for n in (9, 10):
        lv = levels[n]
        arr = arrivals_to(levels, n)
        lines.append(f"\n--- L{n:02d} {lv.name}  arrivals={arr} ---")
        for x, y in arr:
            lines.append(f" arrival {describe_sector(lv, x, y, reach[n])}")
            for nx, ny in neighbors4(x, y):
                lines.append(f"  n4 {describe_sector(lv, nx, ny, reach[n])}")
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                lines.append(f"  n8 {describe_sector(lv, x + dx, y + dy, reach[n])}")

    # extra: Type 5 / Type 8 / Type 2/4 on these levels
    lines.append("\n========== extra  Type 5 SecretDoor / Type 8 OtherTrigger ==========")
    for n in range(25):
        lv = levels[n]
        t5 = [
            (i % GRID, i // GRID, s.item, s.type_addl)
            for i, s in enumerate(lv.sector_list)
            if s.type == 5
        ]
        t8 = [
            (i % GRID, i // GRID, s.item, s.type_addl)
            for i, s in enumerate(lv.sector_list)
            if s.type == 8
        ]
        if n in (3, 4, 5, 9, 10, 14) or t5 or (n in (9, 10) and t8):
            lines.append(f"\nL{n:02d} {lv.name}  Type5={len(t5)} Type8={len(t8)}")
            for x, y, item, addl in t5:
                bucket = "REACH" if (x, y) in reach[n] else "SEAL"
                lines.append(
                    f"  Type5 ({x:2d},{y:2d}) Item={item:4d} addl={addl} {bucket}"
                )
            if n in (9, 10):
                for x, y, item, addl in t8:
                    bucket = "REACH" if (x, y) in reach[n] else "SEAL"
                    lines.append(
                        f"  Type8 ({x:2d},{y:2d}) Item={item:4d} addl={addl} {bucket}"
                    )

    # known walk-through: L3 Blue Crystal secret wall
    lines.append("\n========== L3 walk-through comparison (Blue Crystal room) ==========")
    lv3 = levels[3]
    t5_3 = [
        (i % GRID, i // GRID, s)
        for i, s in enumerate(lv3.sector_list)
        if s.type == 5
    ]
    lines.append(f"L03 Type 5 count={len(t5_3)}")
    for x, y, s in t5_3:
        lines.append(describe_sector(lv3, x, y, reach[3]))
        for nx, ny in neighbors4(x, y):
            lines.append("   " + describe_sector(lv3, nx, ny, reach[3]))

    # also try treating Type 5 walls / all 33 as passable? Type 5 is a sector type
    # Treat Type 5 sectors as walk-through (ignore their 32/33) — for comparison
    lines.append("\n========== treating Type 5 sectors as walk-through ==========")
    for n in (3, 9, 10):
        lv = levels[n]
        secret = {
            (i % GRID, i // GRID)
            for i, s in enumerate(lv.sector_list)
            if s.type == 5
        }
        from collections import deque

        seen: set[tuple[int, int]] = set()
        q = deque()
        for p in starts[n]:
            x, y = p
            if not (0 <= x < GRID and 0 <= y < GRID):
                continue
            if lv.sector_at(x, y).type == 0:
                continue
            if p not in seen:
                seen.add(p)
                q.append(p)
        while q:
            x, y = q.popleft()
            for nx, ny in neighbors4(x, y):
                if (nx, ny) in seen:
                    continue
                if not (0 <= nx < GRID and 0 <= ny < GRID):
                    continue
                if lv.sector_at(nx, ny).type == 0:
                    continue
                owner = edge_owner(x, y, nx, ny)
                if owner is None:
                    continue
                wx, wy, wi = owner
                wt = lv.sector_at(wx, wy).walls[wi].type
                walk_secret = (x, y) in secret or (nx, ny) in secret
                if wt in SOLID_A and not walk_secret:
                    continue
                seen.add((nx, ny))
                q.append((nx, ny))
        lines.append(
            f"  L{n:02d}: Type5 walk-through reach {len(reach[n])} -> {len(seen)} "
            f"(gain {len(seen) - len(reach[n])})  Type5={len(secret)}"
        )

    # extra: tex=127 as holographic; Type 3/9 walk-out
    lines.append("\n========== extra  tex=127 passable / Type3+9 walk-out ==========")

    def flood_custom(level, start_pts, tex_passable=None, walk_types=None):
        from collections import deque

        seen: set[tuple[int, int]] = set()
        q = deque()
        for p in start_pts:
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
            for nx, ny in neighbors4(x, y):
                if (nx, ny) in seen:
                    continue
                if not (0 <= nx < GRID and 0 <= ny < GRID):
                    continue
                if level.sector_at(nx, ny).type == 0:
                    continue
                owner = edge_owner(x, y, nx, ny)
                if owner is None:
                    continue
                wx, wy, wi = owner
                w = level.sector_at(wx, wy).walls[wi]
                skip = False
                if tex_passable is not None and w.texture == tex_passable:
                    skip = True
                if walk_types is not None:
                    if level.sector_at(x, y).type in walk_types:
                        skip = True
                    if level.sector_at(nx, ny).type in walk_types:
                        skip = True
                if w.type in SOLID_A and not skip:
                    continue
                seen.add((nx, ny))
                q.append((nx, ny))
        return seen

    for n in (0, 3, 7, 9, 10, 13):
        lv = levels[n]
        nv = sum(1 for s in lv.sector_list if s.type != 0)
        r127 = flood_custom(lv, starts[n], tex_passable=127)
        r39 = flood_custom(lv, starts[n], walk_types={3, 9})
        rboth = flood_custom(lv, starts[n], tex_passable=127, walk_types={3, 9})
        lines.append(
            f"  L{n:02d} nv={nv} base={len(reach[n])}  "
            f"tex127={len(r127)} (d{len(r127)-len(reach[n]):+d})  "
            f"T3+9walk={len(r39)} (d{len(r39)-len(reach[n]):+d})  "
            f"both={len(rboth)}"
        )

    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
