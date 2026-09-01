"""Render a binary as a PNG: one pixel per byte, row width = --width.

Zeros are black. 0xFF is white. Other bytes are a gray/green mix so
nonzero structure reads against the empty field. This is a picture of
bytes, not a parsed layout.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def render(data: np.ndarray, width: int) -> Image.Image:
    rows = math.ceil(len(data) / width)
    padded = np.zeros(rows * width, dtype=np.uint8)
    padded[: len(data)] = data
    grid = padded.reshape(rows, width)

    rgb = np.zeros((rows, width, 3), dtype=np.uint8)
    nz = grid != 0
    ff = grid == 0xFF
    rgb[nz, 0] = grid[nz]
    rgb[nz, 1] = np.minimum(255, grid[nz].astype(np.uint16) + 40)
    rgb[nz, 2] = grid[nz] // 3
    rgb[ff] = (255, 255, 255)
    return Image.fromarray(rgb, "RGB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "reference" / "dpin_128.bin"),
    )
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    path = Path(args.path)
    data = np.fromfile(path, dtype=np.uint8)
    img = render(data, args.width)
    out = args.out
    if out is None:
        out = ROOT / "reference" / f"dpin_blockmap_w{args.width}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"{path} size={len(data)} width={args.width} -> {out} ({img.size[0]}x{img.size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
