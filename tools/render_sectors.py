# -*- coding: utf-8 -*-
"""Render 32x32 sector-type grids and score them against sector_types_sqr.png."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
SHEET = ROOT / "reference/docs/sector_types_sqr.png"
OUT = ROOT / "reference/docs/sectors"

# Torch-ish defaults, distinct so a human can read our PNGs.
TYPE_RGB = {
    0: (255, 255, 255),
    1: (20, 20, 20),
    2: (40, 80, 220),
    3: (240, 220, 40),
    4: (40, 180, 60),
    5: (20, 40, 140),
    6: (140, 140, 140),
    7: (200, 40, 200),
    8: (230, 140, 30),
    9: (220, 30, 30),
}

# GIF sheet order (row-major). Last cell is a credit, not a plan.
SHEET_ORDER = [
    (0, "Ground Floor"),
    (5, "Evil Undead"),
    (10, "Feel the Power"),
    (15, "Need a Light"),
    (20, "Don't Get Poisoned"),
    (1, "Never Stop Firing"),
    (6, "Ascension"),
    (11, "A Plague of Demons"),
    (16, "Lasciate"),
    (21, "Please Excuse Our Dust"),
    (2, "Lock&Load"),
    (7, "Wrong Way"),
    (12, "Beware of Low-Flying"),
    (17, "Watch Your Step"),
    (22, "But Wait"),
    (3, "They May Be Slow"),
    (8, "Welcome"),
    (13, "The Labyrinth"),
    (18, "I'd Rather Be Surfing"),
    (23, "Where Only Fools"),
    (4, "But They're Hungry"),
    (9, "We Can See In The Dark"),
    (14, "Happy Happy"),
    (19, "Warning: Earthquake"),
    None,
]


def type_grid(level) -> np.ndarray:
    g = np.zeros((GRID, GRID), dtype=np.uint8)
    for i, sec in enumerate(level.sector_list):
        g[i // GRID, i % GRID] = sec.type
    return g


def render_level(grid: np.ndarray, scale: int = 8) -> Image.Image:
    h, w = grid.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for t, color in TYPE_RGB.items():
        rgb[grid == t] = color
    img = Image.fromarray(rgb, "RGB")
    if scale != 1:
        img = img.resize((w * scale, h * scale), Image.Resampling.NEAREST)
    return img


def _nonblack_mask(arr: np.ndarray) -> np.ndarray:
    return arr.max(axis=2) > 8


def find_cells(sheet: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Fixed 5x5: 128x128 maps (4 px/sector) on a 144-pixel pitch.

    Non-black bbox detection shrinks around void-as-black levels
    (Ground Floor). Pitch is observed: cells at 20 + 144*n.
    """
    origin = 16
    pitch = 144
    size = 128
    cells: list[tuple[int, int, int, int]] = []
    for row in range(5):
        for col in range(5):
            x0 = origin + col * pitch
            y0 = origin + row * pitch
            cells.append((x0, y0, x0 + size, y0 + size))
    return cells


def _runs(hits: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for i, flag in enumerate(hits):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(hits)))
    return runs


def crop_map_pixels(sheet: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    return sheet[y0:y1, x0:x1]


def downsample_to_32(tile: np.ndarray) -> np.ndarray:
    """4x4 blocks -> one sector. Mode of each block, not nearest-of-corner."""
    h, w = tile.shape[:2]
    if h != 128 or w != 128:
        tile = np.array(Image.fromarray(tile).resize((128, 128), Image.Resampling.NEAREST))
    out = np.zeros((GRID, GRID, 3), dtype=np.uint8)
    for y in range(GRID):
        for x in range(GRID):
            block = tile[y * 4 : (y + 1) * 4, x * 4 : (x + 1) * 4].reshape(-1, 3)
            keys, counts = np.unique(block, axis=0, return_counts=True)
            out[y, x] = keys[int(np.argmax(counts))]
    return out


def color_key(rgb: np.ndarray) -> tuple[int, int, int]:
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def build_color_map(
    gif_grid: np.ndarray, type_grid_arr: np.ndarray
) -> dict[tuple[int, int, int], int]:
    votes: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    for y in range(GRID):
        for x in range(GRID):
            votes[color_key(gif_grid[y, x])][int(type_grid_arr[y, x])] += 1
    mapping = {color: counts.most_common(1)[0][0] for color, counts in votes.items()}
    return mapping


def score(gif_grid: np.ndarray, type_grid_arr: np.ndarray, mapping) -> float:
    agree = 0
    total = GRID * GRID
    for y in range(GRID):
        for x in range(GRID):
            pred = mapping.get(color_key(gif_grid[y, x]))
            if pred == int(type_grid_arr[y, x]):
                agree += 1
    return 100.0 * agree / total


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    levels = load_maps(MAPS)
    for i, level in enumerate(levels):
        grid = type_grid(level)
        png = render_level(grid)
        dest = OUT / f"{i:02d}_{_slug(level.name)}.png"
        png.save(dest)
        print(f"wrote {dest}")

    sheet_img = Image.open(SHEET).convert("RGB")
    sheet = np.array(sheet_img)
    cells = find_cells(sheet)
    print(f"sheet {sheet.shape[1]}x{sheet.shape[0]} cells={len(cells)}")
    for i, box in enumerate(cells):
        print(f"  cell {i:02d} box={box} w={box[2]-box[0]} h={box[3]-box[1]}")

    # Build color->type map from every aligned non-labyrinth, non-credit cell.
    mappings: list[dict] = []
    samples: list[tuple[int, np.ndarray, np.ndarray]] = []
    for idx, spec in enumerate(SHEET_ORDER):
        if spec is None:
            continue
        if idx >= len(cells):
            print(f"MISSING cell for sheet slot {idx}")
            continue
        li, label = spec
        tile = downsample_to_32(crop_map_pixels(sheet, cells[idx]))
        grid = type_grid(levels[li])
        samples.append((li, tile, grid))
        Image.fromarray(tile).resize((256, 256), Image.Resampling.NEAREST).save(
            OUT / f"sheet_{idx:02d}_{_slug(levels[li].name)}.png"
        )
        if "Labyrinth" not in levels[li].name:
            mappings.append(build_color_map(tile, grid))

    # Merge votes: last mapping wins per color is weak; union by majority.
    merged_votes: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    for mapping, (li, tile, grid) in zip(
        [build_color_map(t, g) for li, t, g in samples if "Labyrinth" not in levels[li].name],
        [(li, t, g) for li, t, g in samples if "Labyrinth" not in levels[li].name],
    ):
        for y in range(GRID):
            for x in range(GRID):
                merged_votes[color_key(tile[y, x])][int(grid[y, x])] += 1
    merged = {c: v.most_common(1)[0][0] for c, v in merged_votes.items()}
    print("gif_color_to_type:")
    for color, typ in sorted(merged.items(), key=lambda kv: kv[1]):
        print(f"  {color} -> {typ} {SECTOR_TYPE_NAME[typ]}")

    def occ_score(tile, grid, flip_y: bool) -> float:
        g = np.flipud(grid) if flip_y else grid
        agree = 0
        for y in range(GRID):
            for x in range(GRID):
                gif_void = color_key(tile[y, x]) == (0, 0, 0)
                our_void = int(g[y, x]) == 0
                if gif_void == our_void:
                    agree += 1
        return 100.0 * agree / (GRID * GRID)

    print("occupancy void-vs-not (no flip / flip_y)")
    for li, tile, grid in samples:
        a = occ_score(tile, grid, False)
        b = occ_score(tile, grid, True)
        print(f"  {li:2d} {levels[li].name!r:42s} {a:6.2f}%  flip={b:6.2f}%")

    print("agreement")
    lines = ["level_index\tname\tscore\tnote"]
    for li, tile, grid in samples:
        pct = score(tile, grid, merged)
        note = ""
        if "Labyrinth" in levels[li].name:
            note = "labyrinth_reforms"
        if pct < 95 and not note:
            note = "LOW"
        print(f"  {li:2d} {levels[li].name!r:42s} {pct:6.2f}% {note}")
        lines.append(f"{li}\t{levels[li].name}\t{pct:.2f}\t{note}")

    (OUT / "agreement.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _slug(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("_")
    return "".join(out).strip("_")[:48]


if __name__ == "__main__":
    main()
