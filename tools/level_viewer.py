# -*- coding: utf-8 -*-
"""Top-down render of a parsed Maps level: floors, walls, and specials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"

# Floor fill by sector type. Void is empty space.
FLOOR = {
    0: (12, 12, 12),
    1: (48, 44, 40),
    2: (40, 70, 170),
    3: (200, 170, 40),
    4: (40, 120, 50),
    5: (20, 40, 90),
    6: (90, 90, 90),
    7: (130, 40, 130),
    8: (180, 100, 30),
    9: (170, 30, 30),
}

WALL_RGB = (210, 200, 180)


def height_label(height10: int) -> str:
    if height10 == -32768:
        return "-3276.8m"
    return f"{height10 / 10:.1f}m"


def render_level(level, cell: int = 16) -> Image.Image:
    title_h = 28
    w = GRID * cell
    img = Image.new("RGB", (w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    title = f"{level.level_number:02d}  {level.name}   {height_label(level.height10)}"
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None
    draw.text((6, 6), title, fill=(230, 230, 220), font=font)

    y0 = title_h
    for i, sec in enumerate(level.sector_list):
        x, y = i % GRID, i // GRID
        x0, y1 = x * cell, y0 + y * cell
        x1, y2 = x0 + cell - 1, y1 + cell - 1
        draw.rectangle((x0, y1, x1, y2), fill=FLOOR.get(sec.type, (80, 80, 80)))

        # wall[0] = Y face (north), wall[1] = X face (west). Skip void leftovers.
        if sec.type != 0:
            if sec.walls[0].type != 0:
                draw.line((x0, y1, x1, y1), fill=WALL_RGB, width=2)
            if sec.walls[1].type != 0:
                draw.line((x0, y1, x0, y2), fill=WALL_RGB, width=2)

        cx, cy = x0 + cell // 2, y1 + cell // 2
        if sec.type == 6:
            r = max(2, cell // 4)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(220, 220, 220), width=1)
        elif sec.type == 9:
            draw.rectangle((cx - 3, cy - 3, cx + 3, cy + 3), outline=(255, 220, 80), width=1)
        elif sec.type == 3:
            draw.polygon(
                [(cx, y1 + 3), (x1 - 3, y2 - 3), (x0 + 3, y2 - 3)],
                outline=(255, 255, 180),
            )
        elif sec.type == 2:
            draw.line((x0 + 3, cy, x1 - 3, cy), fill=(180, 210, 255), width=2)

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Render PID levels top-down.")
    parser.add_argument("--maps", type=Path, default=MAPS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--level", type=int, default=None)
    parser.add_argument("--cell", type=int, default=16)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    levels = load_maps(args.maps)
    indices = [args.level] if args.level is not None else range(len(levels))
    for i in indices:
        img = render_level(levels[i], cell=args.cell)
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in levels[i].name)
        path = args.out / f"{i:02d}_{safe}.png"
        img.save(path)
        print(path)


if __name__ == "__main__":
    main()
