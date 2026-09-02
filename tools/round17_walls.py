# -*- coding: utf-8 -*-
"""Ground Floor walls + reachability; all-25 unreachable census."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round17_walls.txt"

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
WALL_RGB = (245, 240, 220)
WALL_NONE = 0


def font():
    try:
        return ImageFont.load_default()
    except OSError:
        return None


def is_wall(wtype: int) -> bool:
    return wtype != WALL_NONE


def blocked(level, x: int, y: int, nx: int, ny: int) -> bool:
    """True if the step (x,y) -> (nx,ny) is illegal."""
    if not (0 <= nx < GRID and 0 <= ny < GRID):
        return True
    dest = level.sector_at(nx, ny)
    if dest.type == 0:
        return True
    if nx == x and ny == y - 1:
        return is_wall(level.sector_at(x, y).walls[0].type)
    if nx == x - 1 and ny == y:
        return is_wall(level.sector_at(x, y).walls[1].type)
    if nx == x and ny == y + 1:
        return is_wall(level.sector_at(x, y + 1).walls[0].type)
    if nx == x + 1 and ny == y:
        return is_wall(level.sector_at(x + 1, y).walls[1].type)
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


def reachable_from(level, start: tuple[int, int]) -> set[tuple[int, int]]:
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (nx, ny) in seen:
                continue
            if blocked(level, x, y, nx, ny):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def draw_walls(draw: ImageDraw.ImageDraw, level, y0: int, cell: int, only_nonvoid: bool = True) -> None:
    for i, sec in enumerate(level.sector_list):
        if only_nonvoid and sec.type == 0:
            continue
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        x1, bot = x0 + cell, top + cell
        if is_wall(sec.walls[0].type):
            draw.line((x0, top, x1, top), fill=WALL_RGB, width=3)
        if is_wall(sec.walls[1].type):
            draw.line((x0, top, x0, bot), fill=WALL_RGB, width=3)


def render_typed(level, cell: int = 18) -> Image.Image:
    legend_w = 150
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text((4, 4), "L00 Ground Floor  WALLS  Void=black  Normal=tan", fill=(230, 230, 220), font=fnt)
    y0 = title_h
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=TYPE_RGB.get(sec.type, (80, 80, 80)))
    draw_walls(draw, level, y0, cell)
    lx = w + 8
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for t, name in enumerate(TYPE_LABEL):
        yy = y0 + 16 + t * 16
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=TYPE_RGB[t])
        draw.text((lx + 16, yy), f"{t} {name}", fill=(220, 220, 210), font=fnt)
    return img


def render_reach(level, reach: set[tuple[int, int]], cell: int = 18) -> Image.Image:
    legend_w = 180
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text((4, 4), "L00 Ground Floor  REACHABLE vs sealed", fill=(230, 230, 220), font=fnt)
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
        # overlay specials as a small inset
        if sec.type in (2, 3, 4, 6, 9) and sec.type != 0:
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
        (sealed_c, "non-Void sealed"),
        (TYPE_RGB[9], "Save inset"),
        (TYPE_RGB[3], "Ladder inset"),
        (TYPE_RGB[6], "Corpse inset"),
        (TYPE_RGB[2], "Door inset"),
        (WALL_RGB, "wall"),
    ]
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for i, (col, name) in enumerate(items):
        yy = y0 + 16 + i * 16
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=col)
        draw.text((lx + 16, yy), name, fill=(220, 220, 210), font=fnt)
    return img


def entry_points(level) -> list[tuple[int, int]]:
    pts = []
    for i, s in enumerate(level.sector_list):
        if s.type in (3, 9):
            pts.append((i % GRID, i // GRID))
    sm = southmost_nonvoid(level)
    if sm is not None and sm not in pts:
        pts.append(sm)
    return pts


def census(level) -> tuple[int, int, int, tuple[int, int] | None, set[tuple[int, int]]]:
    nv = [(i % GRID, i // GRID) for i, s in enumerate(level.sector_list) if s.type != 0]
    start = southmost_nonvoid(level)
    if start is None:
        return 0, 0, 0, None, set()
    reach = reachable_from(level, start)
    return len(nv), len(reach), len(nv) - len(reach), start, reach


def census_entries(level) -> tuple[int, int, int, int]:
    """Union flood from every Type 3 / Type 9 (plus southmost)."""
    nv = sum(1 for s in level.sector_list if s.type != 0)
    seen: set[tuple[int, int]] = set()
    for p in entry_points(level):
        seen |= reachable_from(level, p)
    return nv, len(seen), nv - len(seen), len(entry_points(level))


def main() -> None:
    levels = load_maps(MAPS)
    gf = levels[0]
    start = southmost_nonvoid(gf)
    assert start is not None
    reach = reachable_from(gf, start)
    nv = [(i % GRID, i // GRID, s) for i, s in enumerate(gf.sector_list) if s.type != 0]
    sealed = [(x, y, s) for x, y, s in nv if (x, y) not in reach]

    OUT.mkdir(parents=True, exist_ok=True)
    p_walls = OUT / "L00_walls.png"
    p_reach = OUT / "L00_reachable.png"
    render_typed(gf).save(p_walls)
    render_reach(gf, reach).save(p_reach)

    lines: list[str] = []
    lines.append(f"wrote {p_walls}")
    lines.append(f"wrote {p_reach}")
    lines.append(f"start (southmost non-Void) = {start} type={gf.sector_at(*start).type}")
    lines.append(f"non-Void={len(nv)} reachable={len(reach)} sealed={len(sealed)}")

    # wall leftover on void
    void_w = 0
    for s in gf.sector_list:
        if s.type == 0 and (is_wall(s.walls[0].type) or is_wall(s.walls[1].type)):
            void_w += 1
    lines.append(f"Void sectors with leftover Wall_X/Y: {void_w}")

    saves = [(6, 2), (26, 2), (5, 10), (27, 10)]
    ladders = [(4, 1), (28, 3), (4, 11), (28, 11)]
    lines.append("\nType 9 Save reachability:")
    for x, y in saves:
        s = gf.sector_at(x, y)
        lines.append(f"  ({x},{y}) type={s.type} Item={s.item} reachable={(x,y) in reach}")
    lines.append("Type 3 ChangeLevel reachability:")
    for x, y in ladders:
        s = gf.sector_at(x, y)
        lines.append(f"  ({x},{y}) type={s.type} Item={s.item} reachable={(x,y) in reach}")

    # reachable bbox / shape
    if reach:
        xs = [x for x, y in reach]
        ys = [y for x, y in reach]
        rows = [0] * 32
        cols = [0] * 32
        for x, y in reach:
            rows[y] += 1
            cols[x] += 1
        lines.append(f"\nreachable bbox x={min(xs)}..{max(xs)} y={min(ys)}..{max(ys)}")
        lines.append(f"reachable per row: {rows}")
        lines.append(f"reachable per col: {cols}")
        lines.append(f"wide reachable rows (>=8): {[y for y,n in enumerate(rows) if n>=8]}")
        lines.append(f"tall reachable cols (>=8): {[x for x,n in enumerate(cols) if n>=8]}")

    lines.append("\nGround Floor unreachable non-Void:")
    if not sealed:
        lines.append("  (none)")
    for x, y, s in sealed:
        lines.append(
            f"  ({x:2d},{y:2d}) type={s.type} {SECTOR_TYPE_NAME.get(s.type,'?'):16s} "
            f"Item={s.item:4d} addl={s.type_addl}"
        )

    lines.append("\n========== ALL 25 LEVELS ==========")
    lines.append("reach_S = flood from southmost non-Void only (GF player-start rule).")
    lines.append("reach_E = union flood from every Type 3 + Type 9 (+ southmost).")
    lines.append(
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'rS':>4} {'sS':>4} {'rE':>4} {'sE':>4} starts"
    )
    for lv in levels:
        n_nv, n_r, n_s, st, _ = census(lv)
        _, n_re, n_se, n_ent = census_entries(lv)
        lines.append(
            f"{lv.level_number:3d} {lv.name:<36} {n_nv:4d} {n_r:4d} {n_s:4d} "
            f"{n_re:4d} {n_se:4d} {n_ent} {st}"
        )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
