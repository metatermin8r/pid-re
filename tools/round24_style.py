# -*- coding: utf-8 -*-
"""Wall blocking may differ by construction style (short-wall vs 32/33-only)."""

from __future__ import annotations

import itertools
import sys
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPES, WALL_TYPES, load_maps  # noqa: E402
from round18_walls import TYPE_RGB, draw_walls, font  # noqa: E402
from round19_doors import find_doors_adj4, is_open_action, trigger_sectors  # noqa: E402
from round22_slots import gf_t_metrics, starts_for, type3_xy, type5_xy  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round24_style.txt"


def edge_wt(level, x, y, nx, ny) -> tuple[int, int]:
    """(type, texture) on the N/W stored edge between (x,y) and (nx,ny)."""
    if nx == x and ny == y - 1:
        w = level.sector_at(x, y).walls[0]
    elif nx == x - 1 and ny == y:
        w = level.sector_at(x, y).walls[1]
    elif nx == x and ny == y + 1:
        w = level.sector_at(x, y + 1).walls[0]
    elif nx == x + 1 and ny == y:
        w = level.sector_at(x + 1, y).walls[1]
    else:
        return -1, 0
    return w.type, w.texture


def flood(level, starts, blocks, open_doors=None):
    open_doors = open_doors or set()
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
            if not (0 <= nx < GRID and 0 <= ny < GRID):
                continue
            if level.sector_at(nx, ny).type == 0:
                continue
            wt, tex = edge_wt(level, x, y, nx, ny)
            if blocks(wt, tex) and (x, y) not in open_doors and (nx, ny) not in open_doors:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def propagate(level, starts, blocks, use_keys: bool = True):
    open_doors: set[tuple[int, int]] = set()
    for _ in range(64):
        reach = flood(level, starts, blocks, open_doors)
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
    return flood(level, starts, blocks, open_doors)


def nonvoid(level) -> set[tuple[int, int]]:
    return {
        (i % GRID, i // GRID)
        for i, s in enumerate(level.sector_list)
        if s.type != 0
    }


def components(level, tiles, blocks) -> list[int]:
    left = set(tiles)
    sizes = []
    while left:
        seed = next(iter(left))
        comp = flood(level, [seed], blocks)
        comp &= left
        if not comp:
            comp = {seed}
        sizes.append(len(comp))
        left -= comp
    sizes.sort(reverse=True)
    return sizes


def geom_components(tiles: set[tuple[int, int]]) -> list[int]:
    left = set(tiles)
    sizes = []
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
        sizes.append(len(seen))
    sizes.sort(reverse=True)
    return sizes


def enum_blocks(solid: frozenset[int]):
    def fn(wt, tex):
        return wt in solid

    return fn


def tex127_drawonly(wt, tex):
    if wt == 33 and tex == 127:
        return False
    return wt in (32, 33)


def tex127_only_passable(wt, tex):
    """(33,127) passable; any other non-zero type blocks."""
    if wt == 33 and tex == 127:
        return False
    return wt != 0


def bit_blocks(bit: int):
    def fn(wt, tex):
        return (wt & bit) != 0

    return fn


def density(level) -> dict:
    n32 = n33 = n_short = n0 = n_slots = 0
    tex_by_type: dict[int, Counter] = {}
    for sec in level.sector_list:
        if sec.type == 0:
            continue
        for wi in (0, 1):
            w = sec.walls[wi]
            n_slots += 1
            tex_by_type.setdefault(w.type, Counter())[w.texture] += 1
            if w.type == 32:
                n32 += 1
            elif w.type == 33:
                n33 += 1
            elif w.type in (64, 96, 128):
                n_short += 1
            elif w.type == 0:
                n0 += 1
    return {
        "slots": n_slots,
        "n32": n32,
        "n33": n33,
        "solid": n32 + n33,
        "short": n_short,
        "none": n0,
        "solid_frac": (n32 + n33) / n_slots if n_slots else 0.0,
        "tex": tex_by_type,
    }


def gates(levels, reach_lv, nv, comps_lv, geom_lv):
    gf_ok = len(reach_lv[0]) == 214
    gf_m = gf_t_metrics(levels[0], reach_lv[0])
    shape_ok = gf_ok and gf_m["stem_narrow"] and gf_m["bar_wide"]
    l13 = reach_lv[13]
    maze = len(l13)
    centre_ok = (16, 18) in l13
    maze_ok = centre_ok and 180 <= maze <= 230
    corners = [
        p
        for p in type3_xy(levels[13])
        if (p[0] <= 2 or p[0] >= 29) and (p[1] <= 2 or p[1] >= 29)
    ]
    corners_ok = all(p not in l13 for p in corners)
    secrets_open = []
    for ln in (3, 4):
        for p in type5_xy(levels[ln]):
            if p in reach_lv[ln]:
                secrets_open.append((ln, p))
    secret_ok = not secrets_open
    extra = [len(comps_lv[n]) - len(geom_lv[n]) for n in range(25)]
    shatter = [n for n in range(25) if extra[n] > 5]
    # raw wall-aware > 5 on levels that are one geometric blob
    raw_bad = [
        n
        for n in range(25)
        if len(geom_lv[n]) <= 2 and len(comps_lv[n]) > 5
    ]
    return {
        "gf_214": gf_ok,
        "gf_T": shape_ok,
        "l13_maze": maze,
        "l13_ok": maze_ok and corners_ok,
        "secret_ok": secret_ok,
        "secrets_open": secrets_open,
        "shatter": shatter,
        "raw_bad": raw_bad,
        "max_extra": max(extra) if extra else 0,
        "max_comps": max(len(c) for c in comps_lv),
        "all_pass": gf_ok
        and shape_ok
        and maze_ok
        and corners_ok
        and secret_ok
        and not shatter,
    }


def render_level(level, reach, tag: str, cell: int = 16) -> Image.Image:
    legend_w = 8
    title_h = 20
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text(
        (4, 2),
        f"L{level.level_number:02d} {level.name}  {tag}"[:76],
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
    return img


def main() -> None:
    levels = load_maps(MAPS)
    lines: list[str] = []
    lines.append("Round 24 — wall semantics by construction style")
    lines.append("Direction N/W, slots (0,1). Arrival seeds + Type 9 + door fixed-point.")
    lines.append("")

    # (i) type parsing unchanged
    bad_types = 0
    bad_walls = 0
    for lv in levels:
        for s in lv.sector_list:
            if s.type not in SECTOR_TYPES:
                bad_types += 1
            for w in s.walls:
                if w.type not in WALL_TYPES:
                    bad_walls += 1
    lines.append(
        f"(i) sector type parsing unchanged: violations={bad_types}  "
        f"wall-type violations={bad_walls}  (both must be 0)"
    )

    starts = [starts_for(levels, n) for n in range(25)]
    nv = [sum(1 for s in lv.sector_list if s.type != 0) for lv in levels]
    names = [lv.name for lv in levels]
    tiles = [nonvoid(lv) for lv in levels]
    geom = [geom_components(t) for t in tiles]
    dens = [density(lv) for lv in levels]
    total_nv = sum(nv)

    base_fn = enum_blocks(frozenset({32, 33}))

    # --- (a) component census under 32/33 ---
    lines.append("\n========== (a) per-level style + 32/33 component shatter ==========")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'32/33':>5} {'frac':>5} {'short':>5} "
        f"{'geom':>4} {'wallC':>5} {'maxW':>5}"
    )
    band = []
    for n, lv in enumerate(levels):
        comps = components(lv, tiles[n], base_fn)
        d = dens[n]
        band.append(d["short"] == 0)
        lines.append(
            f"{n:3d} {names[n]:<36} {nv[n]:4d} {d['solid']:5d} {d['solid_frac']:5.3f} "
            f"{d['short']:5d} {len(geom[n]):4d} {len(comps):5d} {comps[0] if comps else 0:5d}"
        )
    no_short = [n for n in range(25) if dens[n]["short"] == 0]
    has_short = [n for n in range(25) if dens[n]["short"] > 0]
    lines.append(f"\n  zero short walls: {no_short}")
    lines.append(f"  has short walls:  {has_short}")
    lines.append("  split is 7-15 (plus L24 has shorts; L13 has zero shorts).")

    # --- (b) 32 vs 33 ---
    lines.append("\n========== (b) type 32 vs 33 on edges 0/1 (non-Void) ==========")
    lines.append(f"{'Lv':>3} {'name':<36} {'32':>6} {'33':>6} {'33frac':>7}")
    for n in range(25):
        d = dens[n]
        tot = d["n32"] + d["n33"]
        frac = d["n33"] / tot if tot else 0.0
        lines.append(
            f"{n:3d} {names[n]:<36} {d['n32']:6d} {d['n33']:6d} {frac:7.3f}"
        )

    # --- (e) texture distribution (summary: top values per type) ---
    lines.append("\n========== (e) texture distribution (edges 0/1, top values) ==========")
    for n in range(25):
        d = dens[n]
        parts = []
        for wt in sorted(d["tex"]):
            top = d["tex"][wt].most_common(4)
            parts.append(
                f"{wt}:[" + ",".join(f"{tex}×{c}" for tex, c in top) + "]"
            )
        lines.append(f"  L{n:02d} " + "  ".join(parts))

    # --- candidates ---
    candidates: list[tuple[str, object]] = []
    # (c)(d) enum combinations
    kinds = (32, 33, 64, 96, 128)
    for bits in itertools.product((False, True), repeat=5):
        solid = frozenset(k for k, on in zip(kinds, bits) if on)
        name = "enum{" + ",".join(str(k) for k in sorted(solid)) + "}"
        candidates.append((name, enum_blocks(solid)))
    candidates.append(("33+tex127 passable; 32/33 else block", tex127_drawonly))
    candidates.append(("33+tex127 passable; any nonzero blocks", tex127_only_passable))
    for bit in (1, 32, 64, 128):
        candidates.append((f"bit{bit} (0x{bit:02x})", bit_blocks(bit)))

    lines.append("\n========== (c/d/e/f) blocking-rule scan ==========")
    lines.append(
        f"{'rule':<42} {'reach':>6} {'sealed':>7} {'maxC':>5} {'maxX':>5}  gates"
    )

    scored = []
    geom_all = geom
    for name, fn in candidates:
        reach_lv = [propagate(lv, starts[n], fn) for n, lv in enumerate(levels)]
        comps_lv = [components(lv, tiles[n], fn) for n, lv in enumerate(levels)]
        sealed = [nv[n] - len(reach_lv[n]) for n in range(25)]
        tot_s = sum(sealed)
        g = gates(levels, reach_lv, nv, comps_lv, geom_all)
        flag = []
        if g["all_pass"]:
            flag.append("ALL_GATES")
        else:
            if not g["gf_214"]:
                flag.append("GF")
            if not g["l13_ok"]:
                flag.append(f"L13={g['l13_maze']}")
            if not g["secret_ok"]:
                flag.append("T5")
            if g["shatter"]:
                flag.append(f"shatter{g['shatter']}")
        scored.append((name, fn, reach_lv, comps_lv, sealed, tot_s, g))
        lines.append(
            f"  {name:<40} {total_nv - tot_s:6d} {tot_s:7d} {g['max_comps']:5d} "
            f"{g['max_extra']:5d}  {' '.join(flag) if flag else '-'}"
        )

    # rank by sealed among gate-passers, else among all
    passers = [s for s in scored if s[6]["all_pass"]]
    lines.append(f"\n  gate-passers: {len(passers)}")
    if passers:
        passers.sort(key=lambda t: (t[5], t[6]["max_extra"], t[6]["max_comps"]))
        win = passers[0]
    else:
        scored.sort(key=lambda t: (t[5], t[6]["max_extra"]))
        win = scored[0]
        lines.append("  NO rule passed every gate. Reporting fewest-sealed anyway.")

    lines.append("\n========== (h) winner ==========")
    wname, wfn, wreach, wcomps, wsealed, wtot, wg = win
    lines.append(f"  {wname}  sealed={wtot}  max_comps={wg['max_comps']}  max_extra={wg['max_extra']}")
    lines.append(f"  gates: GF={wg['gf_214']} T={wg['gf_T']} L13={wg['l13_ok']} ({wg['l13_maze']}) T5={wg['secret_ok']}")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'reach':>5} {'sealed':>6} "
        f"{'geomC':>5} {'wallC':>5} {'maxW':>5} {'extra':>5}"
    )
    for n in range(25):
        extra = len(wcomps[n]) - len(geom[n])
        lines.append(
            f"{n:3d} {names[n]:<36} {nv[n]:4d} {len(wreach[n]):5d} {wsealed[n]:6d} "
            f"{len(geom[n]):5d} {len(wcomps[n]):5d} {wcomps[n][0] if wcomps[n] else 0:5d} "
            f"{extra:5d}"
        )

    # headline component table vs baseline 32/33
    lines.append("\n========== headline: wall-aware component counts ==========")
    lines.append(f"{'Lv':>3} {'name':<36} {'32/33 C':>8} {'winner C':>8} {'geom C':>7}")
    base_comps = [components(lv, tiles[n], base_fn) for n, lv in enumerate(levels)]
    for n in range(25):
        lines.append(
            f"{n:3d} {names[n]:<36} {len(base_comps[n]):8d} {len(wcomps[n]):8d} {len(geom[n]):7d}"
        )

    # named tests in detail
    lines.append("\n========== named tests (c, inverse, tex127) per-level sealed ==========")
    want = (
        "enum{32}",
        "enum{33}",
        "enum{32,33}",
        "33+tex127 passable; 32/33 else block",
    )
    for name, fn, reach_lv, comps_lv, sealed, tot_s, g in scored:
        if name not in want:
            continue
        lines.append(f"\n--- {name} sealed={tot_s} L9c={len(comps_lv[9])} L10c={len(comps_lv[10])} ---")
        lines.append(
            f"  L9 {len(reach_lv[9])}/{nv[9]}  L10 {len(reach_lv[10])}/{nv[10]}  "
            f"GF {len(reach_lv[0])}/214  L13 {len(reach_lv[13])}"
        )

    # renders
    tag = wname[:28]
    for n, lv in enumerate(levels):
        img = render_level(lv, wreach[n], tag)
        img.save(OUT / f"L{n:02d}_style.png")
    lines.append(f"\n  wrote L00_style.png … L24_style.png under '{wname}'")

    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
