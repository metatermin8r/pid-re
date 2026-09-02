# -*- coding: utf-8 -*-
"""Corrected wall semantics: corners never block; two short-wall variants."""

from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, WALL_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round18_walls.txt"
SEALED = ROOT / "reference/docs/round18_sealed.txt"

# Round 17 union-flood (any non-zero type on edges 0/1 blocks).
PREV_RE = [
    214, 478, 500, 451, 503, 563, 195, 283, 44, 13,
    5, 10, 54, 4, 207, 412, 472, 496, 521, 172,
    428, 529, 496, 519, 57,
]
PREV_NV = [
    214, 478, 500, 456, 504, 563, 195, 515, 459, 415,
    574, 537, 521, 525, 446, 505, 472, 496, 521, 172,
    437, 529, 496, 519, 181,
]

SOLID_A = frozenset({32, 33})
SOLID_B = frozenset({32, 33, 64, 96, 128})

TYPE_RGB = {
    0: (0, 0, 0),
    1: (198, 186, 164),
    2: (55, 105, 220),
    3: (230, 200, 40),
    4: (45, 165, 75),
    5: (35, 55, 130),
    6: (235, 235, 235),
    7: (165, 55, 175),
    8: (220, 115, 35),
    9: (210, 40, 40),
}
TYPE_LABEL = [
    "Void",
    "Normal",
    "Door",
    "ChangeLevel",
    "DoorTrigger",
    "SecretDoor",
    "Corpse",
    "Pillar",
    "OtherTrigger",
    "Save",
]
WALL_FULL = (245, 240, 220)
WALL_SHORT = (190, 175, 130)
WALL_SWITCH = (70, 200, 220)
CORNER_MARK = (220, 200, 90)
LARGE_SEALED = 20


def font():
    try:
        return ImageFont.load_default()
    except OSError:
        return None


def blocked(level, x: int, y: int, nx: int, ny: int, solid: frozenset[int]) -> bool:
    """True if the step is illegal. Only WallList[0] / [1] can block."""
    if not (0 <= nx < GRID and 0 <= ny < GRID):
        return True
    dest = level.sector_at(nx, ny)
    if dest.type == 0:
        return True
    if nx == x and ny == y - 1:
        return level.sector_at(x, y).walls[0].type in solid
    if nx == x - 1 and ny == y:
        return level.sector_at(x, y).walls[1].type in solid
    if nx == x and ny == y + 1:
        return level.sector_at(x, y + 1).walls[0].type in solid
    if nx == x + 1 and ny == y:
        return level.sector_at(x + 1, y).walls[1].type in solid
    return True


def southmost_nonvoid(level) -> tuple[int, int] | None:
    best = None
    for i, sec in enumerate(level.sector_list):
        if sec.type == 0:
            continue
        x, y = i % GRID, i // GRID
        if best is None or y > best[1] or (y == best[1] and x < best[0]):
            best = (x, y)
    return best


def entry_points(level) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    for i, s in enumerate(level.sector_list):
        if s.type in (3, 9):
            pts.append((i % GRID, i // GRID))
    sm = southmost_nonvoid(level)
    if sm is not None and sm not in pts:
        pts.append(sm)
    return pts


def reachable_from(level, start: tuple[int, int], solid: frozenset[int]) -> set[tuple[int, int]]:
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (nx, ny) in seen:
                continue
            if blocked(level, x, y, nx, ny, solid):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def union_flood(level, solid: frozenset[int]) -> set[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    for p in entry_points(level):
        seen |= reachable_from(level, p, solid)
    return seen


def nonvoid_coords(level) -> list[tuple[int, int]]:
    return [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type != 0]


def has_switchable_corner(sec) -> bool:
    return any(w.type == 1 for w in sec.walls)


def neighbors4(x: int, y: int) -> list[tuple[int, int]]:
    out = []
    for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
        if 0 <= nx < GRID and 0 <= ny < GRID:
            out.append((nx, ny))
    return out


def edge_style(wtype: int) -> tuple[tuple[int, int, int], int] | None:
    """Draw style for WallList[0]/[1]. Corners on these slots get a tick, not a bar."""
    if wtype in (32, 33):
        return WALL_FULL, 3
    if wtype in (64, 96, 128):
        return WALL_SHORT, 2
    if wtype == 1:
        return WALL_SWITCH, 2
    if wtype == 160:
        return CORNER_MARK, 1
    if wtype != 0:
        return (180, 80, 80), 2
    return None


def draw_corner_mark(draw: ImageDraw.ImageDraw, x0: int, top: int, x1: int, bot: int, idx: int) -> None:
    r = 2
    if idx == 2:  # HighX LowY = NE / top-right
        cx, cy = x1 - 1, top
    elif idx == 3:  # LowX LowY = NW / top-left
        cx, cy = x0, top
    elif idx == 4:  # HighX HighY = SE / bottom-right
        cx, cy = x1 - 1, bot - 1
    elif idx == 5:  # LowX HighY = SW / bottom-left
        cx, cy = x0, bot - 1
    else:
        return
    draw.rectangle((cx - r, cy - r, cx + r, cy + r), fill=CORNER_MARK)


def draw_walls(draw: ImageDraw.ImageDraw, level, y0: int, cell: int) -> None:
    for i, sec in enumerate(level.sector_list):
        if sec.type == 0:
            continue
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        x1, bot = x0 + cell, top + cell
        n_style = edge_style(sec.walls[0].type)
        if n_style:
            col, width = n_style
            if sec.walls[0].type == 160:
                mid = (x0 + x1) // 2
                draw.line((mid - 3, top, mid + 3, top), fill=col, width=2)
            else:
                draw.line((x0, top, x1, top), fill=col, width=width)
        w_style = edge_style(sec.walls[1].type)
        if w_style:
            col, width = w_style
            if sec.walls[1].type == 160:
                mid = (top + bot) // 2
                draw.line((x0, mid - 3, x0, mid + 3), fill=col, width=2)
            else:
                draw.line((x0, top, x0, bot), fill=col, width=width)
        for idx in (2, 3, 4, 5):
            if sec.walls[idx].type != 0:
                draw_corner_mark(draw, x0, top, x1, bot, idx)


def render_typed(level, cell: int = 18) -> Image.Image:
    legend_w = 168
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    title = f"L{level.level_number:02d} {level.name}  walls  Void=black  Normal=tan"
    draw.text((4, 4), title[:78], fill=(230, 230, 220), font=fnt)
    y0 = title_h
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=TYPE_RGB.get(sec.type, (80, 80, 80)))
    draw_walls(draw, level, y0, cell)
    lx = w + 8
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for t, name in enumerate(TYPE_LABEL):
        yy = y0 + 16 + t * 14
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=TYPE_RGB[t])
        draw.text((lx + 16, yy), f"{t} {name}", fill=(220, 220, 210), font=fnt)
    extras = [
        (WALL_FULL, "32/33 edge"),
        (WALL_SHORT, "64/96/128 short"),
        (WALL_SWITCH, "1 switchable"),
        (CORNER_MARK, "corner mark"),
    ]
    base = y0 + 16 + 10 * 14 + 8
    for i, (col, name) in enumerate(extras):
        yy = base + i * 14
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=col)
        draw.text((lx + 16, yy), name, fill=(220, 220, 210), font=fnt)
    return img


def render_reach(level, reach: set[tuple[int, int]], label: str, cell: int = 18) -> Image.Image:
    legend_w = 168
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text((4, 4), f"L{level.level_number:02d} {level.name}  {label}"[:78], fill=(230, 230, 220), font=fnt)
    y0 = title_h
    reach_c = (70, 150, 90)
    sealed_c = (190, 40, 50)
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        if sec.type == 0:
            fill = (0, 0, 0)
        elif (x, y) in reach:
            fill = reach_c
        else:
            fill = sealed_c
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=fill)
        if sec.type in (2, 3, 4, 5, 6, 9):
            inset = 4
            draw.rectangle(
                (x0 + inset, top + inset, x0 + cell - 1 - inset, top + cell - 1 - inset),
                outline=TYPE_RGB[sec.type],
                width=2,
            )
    draw_walls(draw, level, y0, cell)
    lx = w + 8
    items = [
        ((0, 0, 0), "Void"),
        (reach_c, "reachable"),
        (sealed_c, "sealed"),
        (TYPE_RGB[5], "SecretDoor"),
        (TYPE_RGB[9], "Save"),
        (TYPE_RGB[3], "Ladder"),
        (WALL_FULL, "edge wall"),
        (CORNER_MARK, "corner"),
    ]
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for i, (col, name) in enumerate(items):
        yy = y0 + 16 + i * 14
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=col)
        draw.text((lx + 16, yy), name, fill=(220, 220, 210), font=fnt)
    return img


def wall_slot_census(levels) -> list[str]:
    lines = ["Wall type by slot (non-Void sectors, all 25 levels):"]
    counts = [[Counter() for _ in range(6)] for _ in range(25)]
    global_slot = [Counter() for _ in range(6)]
    for lv in levels:
        for sec in lv.sector_list:
            if sec.type == 0:
                continue
            for k, w in enumerate(sec.walls):
                if w.type != 0:
                    counts[lv.level_number][k][w.type] += 1
                    global_slot[k][w.type] += 1
    for k in range(6):
        slot = "Wall_Y" if k == 0 else "Wall_X" if k == 1 else f"corner[{k}]"
        parts = [f"{WALL_TYPE_NAME.get(t, t)}={n}" for t, n in sorted(global_slot[k].items())]
        lines.append(f"  {slot}: {', '.join(parts) if parts else '(none)'}")
    return lines


def shared_edge_type(level, x: int, y: int, nx: int, ny: int) -> int:
    """Wall type on the shared edge between (x,y) and (nx,ny)."""
    if nx == x and ny == y - 1:
        return level.sector_at(x, y).walls[0].type
    if nx == x - 1 and ny == y:
        return level.sector_at(x, y).walls[1].type
    if nx == x and ny == y + 1:
        return level.sector_at(x, y + 1).walls[0].type
    if nx == x + 1 and ny == y:
        return level.sector_at(x + 1, y).walls[1].type
    return -1


def sealed_components(sealed: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    left = set(sealed)
    comps: list[list[tuple[int, int]]] = []
    while left:
        start = next(iter(left))
        q = deque([start])
        left.remove(start)
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


def frontier_stats(level, reach: set[tuple[int, int]], sealed: list[tuple[int, int]]) -> list[str]:
    sealed_set = set(sealed)
    wall_hist: Counter[int] = Counter()
    reach_type: Counter[int] = Counter()
    sealed_type: Counter[int] = Counter()
    n_edges = 0
    for x, y in sealed:
        for nx, ny in neighbors4(x, y):
            if (nx, ny) not in reach:
                continue
            n_edges += 1
            wt = shared_edge_type(level, x, y, nx, ny)
            wall_hist[wt] += 1
            reach_type[level.sector_at(nx, ny).type] += 1
            sealed_type[level.sector_at(x, y).type] += 1
    comps = sealed_components(sealed)
    lines = [f"  sealed 4-components: {len(comps)} sizes={[len(c) for c in comps[:12]]}"]
    lines.append(f"  reach/sealed frontier edges: {n_edges}")
    if wall_hist:
        lines.append(
            "  frontier wall types: "
            + ", ".join(f"{t}:{WALL_TYPE_NAME.get(t, t)}={n}" for t, n in sorted(wall_hist.items()))
        )
        lines.append(
            "  frontier reach-side sector: "
            + ", ".join(f"{t}:{SECTOR_TYPE_NAME.get(t, '?')}={n}" for t, n in sorted(reach_type.items()))
        )
        lines.append(
            "  frontier sealed-side sector: "
            + ", ".join(f"{t}:{SECTOR_TYPE_NAME.get(t, '?')}={n}" for t, n in sorted(sealed_type.items()))
        )
    type5 = [
        (i % GRID, i // GRID, s)
        for i, s in enumerate(level.sector_list)
        if s.type == 5
    ]
    if type5:
        bits = []
        for x, y, s in type5:
            tag = "reach" if (x, y) in reach else "sealed"
            bits.append(f"({x},{y}) Item={s.item} {tag}")
        lines.append(f"  Type 5 SecretDoor ({len(type5)}): {', '.join(bits)}")
    else:
        lines.append("  Type 5 SecretDoor: (none on this level)")
    return lines


def describe_sealed(
    level,
    sealed: list[tuple[int, int]],
    reach: set[tuple[int, int]],
    lines: list[str],
    dump: list[str],
) -> None:
    lines.append(f"\n--- L{level.level_number:02d} {level.name}  sealed={len(sealed)} ---")
    type_hist = Counter()
    border_secret = 0
    border_switch = 0
    for x, y in sealed:
        sec = level.sector_at(x, y)
        type_hist[sec.type] += 1
        touches_secret = False
        touches_switch = False
        if has_switchable_corner(sec):
            touches_switch = True
        for nx, ny in neighbors4(x, y):
            nsec = level.sector_at(nx, ny)
            if nsec.type == 5:
                touches_secret = True
            if has_switchable_corner(nsec):
                touches_switch = True
        if touches_secret:
            border_secret += 1
        if touches_switch:
            border_switch += 1
    lines.append(
        "  type hist: "
        + ", ".join(f"{t}:{SECTOR_TYPE_NAME.get(t, '?')}={n}" for t, n in sorted(type_hist.items()))
    )
    lines.append(
        f"  sealed bordering Type 5 SecretDoor: {border_secret}/{len(sealed)}"
    )
    lines.append(
        f"  sealed bordering / containing wall-type 1 SwitchableWallCorner: {border_switch}/{len(sealed)}"
    )
    lines.extend(frontier_stats(level, reach, sealed))
    if level.level_number == 13:
        lines.append(
            "  NOTE: Labyrinth layout regenerates on every visit; stored geometry may not be walkable."
        )
    dump.append(f"\n=== L{level.level_number:02d} {level.name}  sealed={len(sealed)} ===")
    for x, y in sorted(sealed, key=lambda p: (p[1], p[0])):
        s = level.sector_at(x, y)
        flags = []
        if any(level.sector_at(nx, ny).type == 5 for nx, ny in neighbors4(x, y)):
            flags.append("adjSecretDoor")
        if has_switchable_corner(s) or any(
            has_switchable_corner(level.sector_at(nx, ny)) for nx, ny in neighbors4(x, y)
        ):
            flags.append("adjSwitchable")
        extra = (" " + " ".join(flags)) if flags else ""
        row = (
            f"  ({x:2d},{y:2d}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?'):16s} "
            f"Item={s.item:4d} addl={s.type_addl}{extra}"
        )
        dump.append(row)
    preview = 24
    lines.append(f"  full list in round18_sealed.txt ({len(sealed)} rows); preview:")
    for row in dump[-(len(sealed)) :][:preview]:
        lines.append(row)
    if len(sealed) > preview:
        lines.append(f"  ... {len(sealed) - preview} more")


def main() -> None:
    levels = load_maps(MAPS)
    gf = levels[0]
    nv0 = nonvoid_coords(gf)
    reach_a0 = union_flood(gf, SOLID_A)
    reach_b0 = union_flood(gf, SOLID_B)
    if len(nv0) != 214 or len(reach_a0) != 214 or len(reach_b0) != 214:
        raise SystemExit(
            f"SANITY FAIL Ground Floor: nv={len(nv0)} a={len(reach_a0)} b={len(reach_b0)} "
            f"(expected 214/214 both variants)"
        )

    rows = []
    reach_a = []
    reach_b = []
    for lv in levels:
        nv = nonvoid_coords(lv)
        ra = union_flood(lv, SOLID_A)
        rb = union_flood(lv, SOLID_B)
        reach_a.append(ra)
        reach_b.append(rb)
        rows.append((lv, len(nv), len(ra), len(nv) - len(ra), len(rb), len(nv) - len(rb)))

    sealed_a_total = sum(r[3] for r in rows)
    sealed_b_total = sum(r[5] for r in rows)
    best_name = "A (32/33 only)" if sealed_a_total <= sealed_b_total else "B (32/33 + short 64/96/128)"
    best_reach = reach_a if sealed_a_total <= sealed_b_total else reach_b
    best_sealed_n = [r[3] if sealed_a_total <= sealed_b_total else r[5] for r in rows]

    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("Round 18 — corrected wall semantics")
    lines.append("Corners (WallList 2-5) never block. Only edges 0 (Wall_Y / north) and")
    lines.append("1 (Wall_X / west) can block. Union flood from Type 3 + Type 9 + southmost.")
    lines.append("A: only 32 Wall and 33 Wall_FancyCorners block.")
    lines.append("B: 32, 33, 64 Wall_ShortLow, 96 Wall_ShortHigh, 128 Wall_ShortBoth block.")
    lines.append("prev: round 17, any non-zero type on edges 0/1 blocked (includes 1 and 160).")
    lines.append("")
    lines.append(f"Ground Floor sanity: nv=214  A={len(reach_a0)}  B={len(reach_b0)}  PASS")
    lines.append("")
    lines.extend(wall_slot_census(levels))
    lines.append("")
    hdr = (
        f"{'Lv':>3} {'name':<36} {'nv':>4} "
        f"{'prev_r':>6} {'prev_s':>6} "
        f"{'A_r':>5} {'A_s':>5} "
        f"{'B_r':>5} {'B_s':>5} "
        f"{'A-B':>5}"
    )
    lines.append(hdr)
    for lv, nv, ar, as_, br, bs in rows:
        prev_r = PREV_RE[lv.level_number]
        prev_s = PREV_NV[lv.level_number] - prev_r
        if nv != PREV_NV[lv.level_number]:
            lines.append(f"WARNING nv changed L{lv.level_number}: {nv} vs {PREV_NV[lv.level_number]}")
        lines.append(
            f"{lv.level_number:3d} {lv.name:<36} {nv:4d} "
            f"{prev_r:6d} {prev_s:6d} "
            f"{ar:5d} {as_:5d} "
            f"{br:5d} {bs:5d} "
            f"{as_ - bs:5d}"
        )
    lines.append("")
    lines.append(f"sealed totals: prev={sum(PREV_NV[i]-PREV_RE[i] for i in range(25))}  A={sealed_a_total}  B={sealed_b_total}")
    if sealed_a_total == sealed_b_total:
        best_name = "A and B tie (32/33 vs 32/33+short)"
    lines.append(f"fewest sealed: {best_name}")
    if sealed_a_total < sealed_b_total:
        lines.append(
            "Data support: short walls (64/96/128) are NOT solid barriers. Treating them as "
            "solid seals extra sectors that union-flood from ladders/saves can otherwise reach."
        )
    elif sealed_b_total < sealed_a_total:
        lines.append(
            "Data support: short walls behave as solid on the stored edges — opening them "
            "would connect regions the geometry keeps apart. Unlikely given the docs; check counts."
        )
    else:
        lines.append(
            "A and B seal the same number of sectors globally. Short walls do not isolate "
            "any extra region under the union-flood start set (they may still exist as geometry)."
        )
    lines.append(
        f"A vs B delta (sectors A opens that B seals): {sealed_b_total - sealed_a_total}"
    )

    large = [lv.level_number for lv, n in zip(levels, best_sealed_n) if n >= LARGE_SEALED]
    lines.append("")
    lines.append(
        f"Levels with sealed >= {LARGE_SEALED} under {best_name}: "
        + (", ".join(str(n) for n in large) if large else "(none)")
    )
    dump: list[str] = [
        "Full sealed-sector lists (best variant = A and B, identical).",
        "adjSecretDoor = 4-adjacent to a Type 5 sector.",
        "adjSwitchable = this sector or a 4-neighbor has wall type 1 on any slot.",
    ]
    for n in large:
        nv = nonvoid_coords(levels[n])
        sealed = [(x, y) for x, y in nv if (x, y) not in best_reach[n]]
        describe_sealed(levels[n], sealed, best_reach[n], lines, dump)

    # smaller leftovers still worth a one-liner
    leftover = [
        (lv.level_number, lv.name, n)
        for lv, n in zip(levels, best_sealed_n)
        if 0 < n < LARGE_SEALED
    ]
    if leftover:
        lines.append("\nSmall sealed leftovers (best variant):")
        for n, name, count in leftover:
            nv = nonvoid_coords(levels[n])
            sealed = [(x, y) for x, y in nv if (x, y) not in best_reach[n]]
            bits = []
            for x, y in sealed:
                s = levels[n].sector_at(x, y)
                bits.append(f"({x},{y}) t={s.type} Item={s.item}")
            lines.append(f"  L{n:02d} {name}: {count}  {', '.join(bits)}")
            dump.append(f"\n=== L{n:02d} {name}  sealed={count} (small leftover) ===")
            for x, y in sealed:
                s = levels[n].sector_at(x, y)
                dump.append(
                    f"  ({x:2d},{y:2d}) type={s.type} {SECTOR_TYPE_NAME.get(s.type, '?'):16s} "
                    f"Item={s.item:4d} addl={s.type_addl}"
                )
            lines.extend(frontier_stats(levels[n], best_reach[n], sealed))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    SEALED.write_text("\n".join(dump) + "\n", encoding="utf-8")

    for lv in levels:
        p = OUT / f"L{lv.level_number:02d}_walls.png"
        render_typed(lv).save(p)
    render_reach(gf, reach_a0, "REACH A=B 214/214").save(OUT / "L00_reachable.png")
    for n in list(large) + [n for n, _, _ in leftover]:
        render_reach(levels[n], best_reach[n], f"REACH sealed={best_sealed_n[n]}").save(
            OUT / f"L{n:02d}_reachable.png"
        )

    print("\n".join(lines))
    print(f"\nwrote {REPORT}")
    print(f"wrote {SEALED}")
    print(f"wrote {OUT / 'L00_walls.png'} .. {OUT / 'L24_walls.png'}")


if __name__ == "__main__":
    main()
