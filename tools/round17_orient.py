# -*- coding: utf-8 -*-
"""Render Ground Floor in both index orientations and dump specials."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/levels"
REPORT = ROOT / "reference/docs/round17_orient.txt"

# Distinct colours per sector type (user names).
TYPE_RGB = {
    0: (18, 18, 18),  # Void
    1: (70, 68, 62),  # Normal
    2: (50, 90, 200),  # Door
    3: (220, 190, 40),  # ChangeLevel
    4: (40, 150, 70),  # DoorTrigger
    5: (30, 50, 120),  # SecretDoor
    6: (200, 200, 200),  # Corpse
    7: (160, 50, 170),  # Pillar
    8: (210, 110, 30),  # OtherTrigger
    9: (200, 35, 35),  # Save
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


def font():
    try:
        return ImageFont.load_default()
    except OSError:
        return None


def render(level, transposed: bool, cell: int = 18) -> Image.Image:
    """transposed=False: display (x,y) = (i%32, i//32)  index=y*32+x
    transposed=True:  display (x,y) = (i//32, i%32)  index=x*32+y
    y increases downward in both.
    """
    legend_w = 150
    title_h = 22
    w = GRID * cell
    img = Image.new("RGB", (w + legend_w, w + title_h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font()
    title = "L00 Ground Floor  " + ("TRANSPOSE index=x*32+y" if transposed else "ROW-MAJOR index=y*32+x")
    draw.text((4, 4), title, fill=(230, 230, 220), font=fnt)
    y0 = title_h
    for i, sec in enumerate(level.sector_list):
        if transposed:
            x, y = i // GRID, i % GRID
        else:
            x, y = i % GRID, i // GRID
        x0, y1 = x * cell, y0 + y * cell
        x1, y2 = x0 + cell - 1, y1 + cell - 1
        draw.rectangle((x0, y1, x1, y2), fill=TYPE_RGB.get(sec.type, (80, 80, 80)))
        if sec.type != 0:
            draw.rectangle((x0, y1, x1, y2), outline=(28, 28, 28))

    # legend
    lx = w + 8
    draw.text((lx, y0), "legend", fill=(200, 200, 190), font=fnt)
    for t, name in enumerate(TYPE_LABEL):
        yy = y0 + 16 + t * 16
        draw.rectangle((lx, yy, lx + 12, yy + 12), fill=TYPE_RGB[t])
        draw.text((lx + 16, yy), f"{t} {name}", fill=(220, 220, 210), font=fnt)
    return img


def xy_of(i: int, transposed: bool) -> tuple[int, int]:
    if transposed:
        return i // GRID, i % GRID
    return i % GRID, i // GRID


def main() -> None:
    gf = load_maps(MAPS)[0]
    OUT.mkdir(parents=True, exist_ok=True)
    row = render(gf, transposed=False)
    trn = render(gf, transposed=True)
    p_row = OUT / "L00_rowmajor.png"
    p_tr = OUT / "L00_transposed.png"
    row.save(p_row)
    trn.save(p_tr)

    lines: list[str] = []
    lines.append(f"wrote {p_row} {p_tr}")
    lines.append(f"level {gf.level_number} {gf.name!r} n_sectors={len(gf.sector_list)}")

    for label, transposed in (("ROW-MAJOR index=y*32+x", False), ("TRANSPOSE index=x*32+y", True)):
        lines.append(f"\n========== {label} ==========")
        specials: dict[int, list[tuple[int, int, int]]] = {t: [] for t in range(10)}
        xs, ys = [], []
        for i, sec in enumerate(gf.sector_list):
            x, y = xy_of(i, transposed)
            specials[sec.type].append((x, y, sec.item))
            if sec.type != 0:
                xs.append(x)
                ys.append(y)
        nvoid = 1024 - len(xs)
        lines.append(f"  non-void={len(xs)} void={nvoid}")
        lines.append(f"  bbox x={min(xs)}..{max(xs)}  y={min(ys)}..{max(ys)}")
        lines.append(f"  bbox size {max(xs)-min(xs)+1} x {max(ys)-min(ys)+1}")
        for t in range(1, 10):
            recs = specials[t]
            lines.append(f"  type {t} {TYPE_LABEL[t]} n={len(recs)}")
            if t in (3, 6, 9) or (t == 7 and len(recs) <= 80):
                for x, y, item in recs:
                    lines.append(f"    ({x:2d},{y:2d}) Item={item}")

        # stem direction: longest axis of non-void vs whether a southward protrusion exists
        # report y extent of the middle x column vs x extent of the top rows
        mid_x = (min(xs) + max(xs)) // 2
        col = [y for x, y, _ in ((xy_of(i, transposed)[0], xy_of(i, transposed)[1], s) for i, s in enumerate(gf.sector_list) if s.type != 0) if x == mid_x]
        # simpler: count non-void per row and per col
        rows = [0] * 32
        cols = [0] * 32
        for i, sec in enumerate(gf.sector_list):
            if sec.type == 0:
                continue
            x, y = xy_of(i, transposed)
            rows[y] += 1
            cols[x] += 1
        lines.append(f"  nonvoid per row y0..31: {rows}")
        lines.append(f"  nonvoid per col x0..31: {cols}")
        wide_rows = [y for y, n in enumerate(rows) if n >= 12]
        tall_cols = [x for x, n in enumerate(cols) if n >= 12]
        lines.append(f"  wide rows (>=12 nv): {wide_rows}")
        lines.append(f"  tall cols (>=12 nv): {tall_cols}")

    # detailed report under BOTH, then we state which is T
    lines.append("\n========== CORRECT-ORIENTATION DETAILS (computed for both) ==========")
    for label, transposed in (("row-major", False), ("transpose", True)):
        lines.append(f"\n--- {label} ---")
        saves, corpses, changes, pillars = [], [], [], []
        items_of = {}
        for i, sec in enumerate(gf.sector_list):
            x, y = xy_of(i, transposed)
            if sec.type == 9:
                saves.append((x, y, sec.item, sec.type_addl))
            elif sec.type == 6:
                corpses.append((x, y, sec.item, sec.type_addl))
            elif sec.type == 3:
                changes.append((x, y, sec.item, sec.type_addl))
            elif sec.type == 7:
                pillars.append((x, y, sec.item))
            if sec.item >= 0:
                items_of[sec.item] = (x, y, sec.type)
        lines.append(f"  Type9 Save: {saves}")
        lines.append(f"  Type6 Corpse: {corpses}")
        lines.append(f"  Type3 ChangeLevel: {changes}")
        lines.append(f"  Type7 Pillar n={len(pillars)}")
        # group pillars by row and col
        by_y: dict[int, list[int]] = {}
        by_x: dict[int, list[int]] = {}
        for x, y, _ in pillars:
            by_y.setdefault(y, []).append(x)
            by_x.setdefault(x, []).append(y)
        lines.append("  pillars by row (y -> xs):")
        for y in sorted(by_y):
            xs = sorted(by_y[y])
            lines.append(f"    y={y:2d} xs={xs}")
        lines.append("  pillars by col (x -> ys):")
        for x in sorted(by_x):
            ys = sorted(by_x[x])
            lines.append(f"    x={x:2d} ys={ys}")

        for cx, cy, citem, cadd in corpses:
            lines.append(f"  corpse at ({cx},{cy}) Item={citem} addl={cadd}")
            lines.append("  adjacent (4-neigh + diagonals):")
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if not (0 <= nx < 32 and 0 <= ny < 32):
                        continue
                    if transposed:
                        sec = gf.sector_list[nx * GRID + ny]
                    else:
                        sec = gf.sector_at(nx, ny)
                    lines.append(
                        f"    ({nx:2d},{ny:2d}) type={sec.type} {TYPE_LABEL[sec.type]:14s} "
                        f"Item={sec.item:4d}"
                    )

        lines.append("  requested Items:")
        for it in (43, 44, 45, 53, 57, 114):
            loc = items_of.get(it)
            lines.append(f"    Item {it} -> {loc}")

        # southmost non-void (player start candidate)
        nv = []
        for i, sec in enumerate(gf.sector_list):
            if sec.type != 0:
                nv.append((*xy_of(i, transposed), sec.type, sec.item))
        south = max(nv, key=lambda t: t[1])
        north = min(nv, key=lambda t: t[1])
        lines.append(f"  northernmost nv {north}  southernmost nv {south}")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
