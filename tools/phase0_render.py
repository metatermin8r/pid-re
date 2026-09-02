# -*- coding: utf-8 -*-
"""Phase 0 final validation renders under the {32} movement rule."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, load_maps  # noqa: E402
from round18_walls import TYPE_RGB, font  # noqa: E402
from round22_slots import gf_t_metrics, starts_for  # noqa: E402
from round24_style import components, enum_blocks, nonvoid, propagate  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/phase0_table.txt"

TAN = (196, 168, 122)
VOID = (0, 0, 0)
WALL32 = (240, 236, 220)
WALL33 = (150, 165, 185)
SHORT = (170, 145, 95)
ARRIVE = (60, 230, 255)
DEPART = (255, 220, 40)

MARK = {
    2: (55, 105, 220),
    3: (230, 200, 40),
    4: (45, 165, 75),
    5: (70, 90, 180),
    6: (245, 245, 245),
    7: (165, 55, 175),
    8: (220, 115, 35),
    9: (210, 40, 40),
}

BLOCKS = enum_blocks(frozenset({32}))


def _edge(draw, x0, y0, x1, y1, color, width):
    draw.line((x0, y0, x1, y1), fill=color, width=width)


def draw_edges(draw, level, y0: int, cell: int) -> None:
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        left, top = x * cell, y0 + y * cell
        right, bot = left + cell - 1, top + cell - 1
        n, w = sec.walls[0], sec.walls[1]
        if n.type == 32:
            _edge(draw, left, top, right, top, WALL32, 3)
        elif n.type == 33:
            _edge(draw, left, top, right, top, WALL33, 1)
        elif n.type in (64, 96, 128):
            _edge(draw, left + 2, top, right - 2, top, SHORT, 1)
        if w.type == 32:
            _edge(draw, left, top, left, bot, WALL32, 3)
        elif w.type == 33:
            _edge(draw, left, top, left, bot, WALL33, 1)
        elif w.type in (64, 96, 128):
            _edge(draw, left, top + 2, left, bot - 2, SHORT, 1)


def _diamond(draw, cx, cy, r, fill, outline):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    draw.polygon(pts, fill=fill, outline=outline)


def render_level(level, arrivals, cell: int = 18) -> Image.Image:
    legend_w = 132
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (12, 12, 14))
    draw = ImageDraw.Draw(img)
    fnt = font()
    draw.text(
        (4, 3),
        f"L{level.level_number:02d}  {level.name}   {{32}} movement"[:78],
        fill=(230, 226, 210),
        font=fnt,
    )
    y0 = title_h
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, top = x * cell, y0 + y * cell
        if sec.type == 0:
            fill = VOID
        elif sec.type == 1:
            fill = TAN
        else:
            fill = MARK.get(sec.type, TAN)
        draw.rectangle((x0, top, x0 + cell - 1, top + cell - 1), fill=fill)
    draw_edges(draw, level, y0, cell)

    seen_arr = set()
    for a in arrivals:
        p = (a[0], a[1])
        if p in seen_arr:
            continue
        seen_arr.add(p)
        ax, ay = p
        cx = ax * cell + cell // 2
        cy = y0 + ay * cell + cell // 2
        _diamond(draw, cx, cy, max(3, cell // 4), ARRIVE, (20, 40, 60))

    for i, sec in enumerate(level.sector_list):
        if sec.type != 3:
            continue
        x, y = i % GRID, i // GRID
        cx = x * cell + cell // 2
        cy = y0 + y * cell + cell // 2
        r = max(2, cell // 5)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=DEPART, width=2)

    lx = w + 6
    legend = [
        ("Void", VOID),
        ("Normal", TAN),
        ("Door", MARK[2]),
        ("Departure / Type 3", MARK[3]),
        ("Door trigger", MARK[4]),
        ("Secret door", MARK[5]),
        ("Corpse", MARK[6]),
        ("Pillar", MARK[7]),
        ("Other trigger", MARK[8]),
        ("Save", MARK[9]),
        ("Type 32 wall (thick)", WALL32),
        ("Type 33 face (thin)", WALL33),
        ("Arrival diamond", ARRIVE),
        ("Departure ring", DEPART),
    ]
    ty = title_h + 4
    for label, color in legend:
        draw.rectangle((lx, ty, lx + 10, ty + 10), fill=color, outline=(80, 80, 80))
        draw.text((lx + 14, ty), label, fill=(210, 210, 200), font=fnt)
        ty += 14
    return img


def counts(level):
    items = corpses = triggers = 0
    for s in level.sector_list:
        if s.item != -1:
            items += 1
        if s.type == 6:
            corpses += 1
        if s.type in (4, 8):
            triggers += 1
    return items, corpses, triggers


def main() -> None:
    levels = load_maps(MAPS)
    OUT.mkdir(parents=True, exist_ok=True)
    starts = [starts_for(levels, n) for n in range(len(levels))]
    lines = [
        "Phase 0 result table  —  movement rule {32}",
        "reachable = arrival + Type 9 + door fixed-point; components on non-Void",
        "",
        f"{'Lv':>3} {'name':<36} {'nv':>4} {'reach':>5} {'comp':>4} "
        f"{'item':>5} {'corp':>4} {'trig':>4}",
    ]
    rows = []
    for n, lv in enumerate(levels):
        nv = nonvoid(lv)
        reach = propagate(lv, starts[n], BLOCKS)
        comps = components(lv, nv, BLOCKS)
        items, corpses, trigs = counts(lv)
        rows.append((n, lv.name, len(nv), len(reach), len(comps), items, corpses, trigs))
        lines.append(
            f"{n:3d} {lv.name:<36} {len(nv):4d} {len(reach):5d} {len(comps):4d} "
            f"{items:5d} {corpses:4d} {trigs:4d}"
        )
        arrivals = [(c.x, c.y) for src in levels for c in src.level_change_list
                    if c.type in (0, 1, 2, 3) and 0 <= c.level <= 24
                    and 0 <= c.x < GRID and 0 <= c.y < GRID and c.level == n]
        img = render_level(lv, arrivals)
        dest = OUT / f"L{n:02d}.png"
        img.save(dest)
        print(f"wrote {dest.name}")

    gf = gf_t_metrics(levels[0], propagate(levels[0], starts[0], BLOCKS))
    lines.append("")
    lines.append("Ground Floor vs Earhart T:")
    lines.append(
        f"  nv={gf['nv']} reach={gf['reach']} bbox={gf['bbox']} "
        f"stem_narrow={gf['stem_narrow']} bar_wide={gf['bar_wide']}"
    )
    lines.append(f"  landmarks={gf.get('landmarks', {})}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
