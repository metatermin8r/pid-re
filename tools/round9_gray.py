# -*- coding: utf-8 -*-
"""Render 195 with compact gray ramp; find pixel start by visual structure."""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from round9_shapes import header  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
SHAPEDIR = ROOT / "reference/shapes"
OUT = ROOT / "reference/docs/round9_gray.txt"


def load_195() -> bytes:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return rf[b".256"][195].data_raw


def render(pixels: bytes, pal: list[tuple[int, int, int] | None], path: Path) -> None:
    img = Image.new("RGB", (128, 128), (255, 0, 255))
    pix = img.load()
    for i, idx in enumerate(pixels[: 16384]):
        rgb = pal[idx] if idx < 256 else None
        pix[i % 128, i // 128] = rgb if rgb is not None else (idx, idx, idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def main() -> None:
    d = load_195()
    lines = []
    # compact gray: from offset 29, 5-byte records
    pal_gray: list[tuple[int, int, int] | None] = [None] * 256
    pal_blue: list[tuple[int, int, int] | None] = [None] * 256
    p = 29
    compact = []
    while p + 5 <= 120:
        idx = struct.unpack_from(">H", d, p)[0]
        kind = d[p + 2]
        val = d[p + 3]
        term = d[p + 4]
        if idx > 40:
            break
        compact.append((p, idx, kind, val, term))
        pal_gray[idx] = (val, val, val)
        p += 5
    lines.append(f"compact n={len(compact)} {compact}")

    # 8-byte blue ramp at 115
    pos = 115
    while pos + 8 <= 230:
        idx, r, g, b = struct.unpack_from(">HHHH", d, pos)
        if idx > 255:
            break
        pal_blue[idx] = (r >> 8, g >> 8, b >> 8)
        pos += 8
        if idx >= 16:
            break
    lines.append(f"blue ramp {[(i, pal_blue[i]) for i in range(256) if pal_blue[i]]}")

    # candidate pixel starts
    starts = [219, 227, 235, 243, 251, 259, 267, 275, 280, 288]
    # also search for the 0b 0d 0c run
    needle = bytes([0x0B, 0x0D, 0x0C, 0x0C, 0x0B, 0x09])
    hit = d.find(needle)
    lines.append(f"needle 0b0d0c.. at {hit}")
    if hit >= 0:
        starts.append(hit)
        starts.append(hit - 2)
        starts.append(hit + 6)

    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    for st in sorted(set(starts)):
        if st < 0 or st + 16384 > len(d):
            continue
        render(d[st:], pal_gray, SHAPEDIR / f"195_gray_{st}.png")
        render(d[st:], pal_blue, SHAPEDIR / f"195_blue_{st}.png")
        if st + 32768 <= len(d):
            render(d[st + 16384 :], pal_gray, SHAPEDIR / f"195_gray_{st}_b.png")
        lines.append(f"  wrote starts {st}")

    # canonical: gray from needle, two 128x128
    if hit >= 0 and hit + 32768 <= len(d):
        render(d[hit:], pal_gray, SHAPEDIR / "195_a.png")
        render(d[hit + 16384 :], pal_gray, SHAPEDIR / "195_b.png")
        lines.append(f"canonical 195_a/b from raw@{hit} gray palette")
    else:
        render(d[219:], pal_gray, SHAPEDIR / "195_a.png")
        render(d[219 + 16384 :], pal_gray, SHAPEDIR / "195_b.png")
        lines.append("canonical 195_a/b from raw@219 gray palette")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
