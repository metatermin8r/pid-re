# -*- coding: utf-8 -*-
"""Decompress .256 from clut-run start via PackBits-until-u32@0; render 195."""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from round9_shapes import header, packbits, rgb8, section_offs  # noqa: E402
from shapes_pass1 import IDENT  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/round9_packbits115.txt"
PALDIR = ROOT / "reference/palettes"
SHAPEDIR = ROOT / "reference/shapes"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


def packbits_exact(src: bytes, target: int) -> tuple[bytes, int]:
    """PackBits until `target` output bytes. Truncate a final overshooting run."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < target:
        ctrl = src[i]
        i += 1
        if ctrl <= 127:
            count = ctrl + 1
            need = min(count, target - len(out), n - i)
            out.extend(src[i : i + need])
            i += min(count, n - i)
        elif ctrl == 128:
            continue
        else:
            count = 257 - ctrl
            if i >= n:
                break
            take = min(count, target - len(out))
            out.extend(bytes([src[i]]) * take)
            i += 1
    return bytes(out[:target]), i


def find_clut_runs(data: bytes, min_n: int = 8) -> list[tuple[int, int, int, int]]:
    runs = []
    n = len(data)
    i = 0
    while i + 8 <= n:
        idx0 = struct.unpack_from(">H", data, i)[0]
        if idx0 > 255:
            i += 1
            continue
        entries = 0
        pos = i
        prev = idx0 - 1
        while pos + 8 <= n:
            idx = struct.unpack_from(">H", data, pos)[0]
            if idx > 255 or idx != prev + 1:
                break
            entries += 1
            prev = idx
            pos += 8
        if entries >= min_n:
            runs.append((i, idx0, idx0 + entries - 1, entries))
            i = pos
        else:
            i += 1
    return runs


def parse_clut_from(data: bytes) -> list[tuple[int, int, int, int]]:
    runs = find_clut_runs(data, min_n=4)
    entries = []
    seen = set()
    for o, lo, hi, n in runs:
        for k in range(n):
            idx, r, g, b = struct.unpack_from(">HHHH", data, o + k * 8)
            if idx not in seen:
                entries.append((idx, r, g, b))
                seen.add(idx)
    return entries


def write_master(slots: list[tuple[int, int, int] | None]) -> None:
    PALDIR.mkdir(parents=True, exist_ok=True)
    cell = 28
    img = Image.new("RGB", (16 * cell, 16 * cell), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    act = bytearray(256 * 3)
    for i in range(256):
        x = (i % 16) * cell
        y = (i // 16) * cell
        rgb = slots[i]
        if rgb is None:
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(40, 40, 40), outline=(80, 80, 80))
            draw.text((x + 2, y + 2), f"{i:02X}?", fill=(180, 180, 180), font=font)
        else:
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=rgb, outline=(0, 0, 0))
            act[i * 3 : i * 3 + 3] = bytes(rgb)
            lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
            fill = (0, 0, 0) if lum > 128 else (255, 255, 255)
            draw.text((x + 2, y + 2), f"{i:02X}", fill=fill, font=font)
    img.save(PALDIR / "master_256.png")
    (PALDIR / "master_256.act").write_bytes(bytes(act))


def render_indexed(pixels: bytes, w: int, h: int, pal: list[tuple[int, int, int] | None], path: Path) -> None:
    img = Image.new("RGB", (w, h), (255, 0, 255))
    pix = img.load()
    for i, idx in enumerate(pixels[: w * h]):
        rgb = pal[idx] if idx < 256 else None
        pix[i % w, i // w] = rgb if rgb is not None else (idx, idx, idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def main() -> None:
    shapes = load_all_256()
    lines: list[str] = []

    # candidate starts per resource
    starts_try = {}
    for rid, d in shapes.items():
        runs = find_clut_runs(d, min_n=8) or find_clut_runs(d, min_n=4)
        first = runs[0][0] if runs else 23
        starts_try[rid] = [first, 23, 24, 115, 116]

    lines.append("== T3(e) packbits_exact from candidate starts ==")
    best_start: dict[int, int] = {}
    for rid in sorted(shapes):
        d = shapes[rid]
        u0, _, b6 = header(d)
        row = []
        for st in starts_try[rid]:
            if st >= len(d):
                continue
            out, cons = packbits_exact(d[st:], u0)
            mark = "EXACT" if len(out) == u0 else f"d={len(out)-u0:+d}"
            left = len(d) - st - cons
            row.append(f"@{st}:{len(out)}/{u0} {mark} cons={cons} left={left}")
            if len(out) == u0 and rid not in best_start:
                best_start[rid] = st
        lines.append(f"  {rid:3d} b6={b6:3d} {row}")

    n_exact = sum(1 for rid in shapes if rid in best_start)
    lines.append(f"  EXACT u32@0: {n_exact}/{len(shapes)}")
    missing = [rid for rid in sorted(shapes) if rid not in best_start]
    lines.append(f"  missing: {missing}")

    # force 195 from 115
    d195 = shapes[195]
    u0, u4, b6 = header(d195)
    out195, cons195 = packbits_exact(d195[115:], u0)
    lines.append(f"\n== 195 packbits @115 out={len(out195)} cons={cons195} left={len(d195)-115-cons195} ==")
    offs = section_offs(d195)
    lines.append(f"  header offs={offs} u0={u0}")
    lines.append("  decompressed first 128:")
    lines.append(hexdump_mac_roman(out195[:128]))
    lines.append("  at off0=280:")
    lines.append(hexdump_mac_roman(out195[280:360]))
    lines.append("  at off1=344:")
    lines.append(hexdump_mac_roman(out195[344:400]))
    lines.append("  at off2=376:")
    lines.append(hexdump_mac_roman(out195[376:440]))
    lines.append("  at off3=32768:")
    if len(out195) > 32768:
        lines.append(hexdump_mac_roman(out195[32768:32768 + 64]))

    # clut from decompressed section 0
    dec_clut = parse_clut_from(out195[: offs[0] + 8] if offs[0] < len(out195) else out195[:512])
    packed_clut = parse_clut_from(d195)
    lines.append(f"  clut in decomp[0:offs0]: n={len(dec_clut)} {[(e[0], rgb8(*e[1:])) for e in dec_clut[:8]]}")
    lines.append(f"  clut in packed file: n={len(packed_clut)}")

    # union palette: packed-file clut runs across all 50 (as Task 1 specified)
    slots: list[tuple[int, int, int] | None] = [None] * 256
    slot_src: list[int | None] = [None] * 256
    raw16: list[tuple[int, int, int] | None] = [None] * 256
    conflicts = 0
    contrib: dict[int, list[tuple[int, int]]] = {}
    for rid in sorted(shapes):
        runs = find_clut_runs(shapes[rid], min_n=4)
        ranges = []
        for o, lo, hi, n in runs:
            ranges.append((lo, hi))
            for k in range(n):
                idx, r, g, b = struct.unpack_from(">HHHH", shapes[rid], o + k * 8)
                rgb = rgb8(r, g, b)
                if raw16[idx] is None:
                    raw16[idx] = (r, g, b)
                    slots[idx] = rgb
                    slot_src[idx] = rid
                elif raw16[idx] != (r, g, b):
                    conflicts += 1
        contrib[rid] = ranges
    filled = [i for i in range(256) if slots[i] is not None]
    empty = [i for i in range(256) if slots[i] is None]
    lines.append(f"\n== T1(b) union from packed clut runs ==")
    lines.append(f"  filled={len(filled)} empty_n={len(empty)} empty={empty}")
    lines.append(f"  conflicts={conflicts}")
    lines.append("  contributor ranges:")
    for rid, ranges in contrib.items():
        if ranges:
            lines.append(f"    {rid:3d} {ranges} {IDENT.get(rid,'')}")
    r128 = contrib.get(128, [])
    lines.append(f"  rsrc128 ranges={r128} (Petrich base-range? first={r128[:1]})")
    write_master(slots)
    lines.append("  wrote master_256.png / .act")

    # also union from DECOMPRESSED section 0 if we have best_start
    slots2: list[tuple[int, int, int] | None] = [None] * 256
    for rid, st in best_start.items():
        d = shapes[rid]
        u0r, _, _ = header(d)
        out, _ = packbits_exact(d[st:], u0r)
        for idx, r, g, b in parse_clut_from(out[:2048]):
            if slots2[idx] is None:
                slots2[idx] = rgb8(r, g, b)
    filled2 = sum(1 for s in slots2 if s is not None)
    lines.append(f"  union from decompressed first 2k: filled={filled2}")

    # render 195 with several slicings
    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    pal = slots
    slices = {
        "plain": (out195[0:16384], out195[16384:32768]),
        "from376": (out195[376:376 + 16384], out195[376 + 16384:376 + 32768]),
        "hdr188": (out195[188:188 + 16384], out195[188 + 16572:188 + 16572 + 16384]),
        "tail32768": (
            out195[32768 - 16384:32768] if len(out195) >= 32768 else b"",
            out195[32768:32768 + 16384] if len(out195) >= 32768 + 376 else b"",
        ),
        "sec3_to_end": (out195[376:32768], b""),
    }
    for label, (a, b) in slices.items():
        if len(a) >= 16384:
            render_indexed(a[:16384], 128, 128, pal, SHAPEDIR / f"195_a_{label}.png")
        if len(b) >= 16384:
            render_indexed(b[:16384], 128, 128, pal, SHAPEDIR / f"195_b_{label}.png")
        lines.append(f"  slice {label}: a={len(a)} b={len(b)}")

    # histogram of putative pixels
    pix = out195[376:376 + 16384] if len(out195) >= 376 + 16384 else out195[:16384]
    from collections import Counter

    hist = Counter(pix)
    top = hist.most_common(12)
    lines.append(f"  pixel hist from376: {top}")
    lines.append(f"  unique indices={len(hist)} min={min(hist)} max={max(hist)}")

    # copy best-guess to canonical names
    if len(out195) >= 376 + 32768:
        render_indexed(out195[376:376 + 16384], 128, 128, pal, SHAPEDIR / "195_a.png")
        render_indexed(out195[376 + 16384:376 + 32768], 128, 128, pal, SHAPEDIR / "195_b.png")
    else:
        render_indexed(out195[:16384], 128, 128, pal, SHAPEDIR / "195_a.png")
        render_indexed(out195[16384:32768], 128, 128, pal, SHAPEDIR / "195_b.png")
    lines.append("  wrote 195_a.png 195_b.png")

    # 196-202
    lines.append("\n== 196-202 packbits @115 ==")
    for rid in range(196, 203):
        d = shapes[rid]
        u0r, _, _ = header(d)
        out, cons = packbits_exact(d[115:], u0r)
        mark = "EXACT" if len(out) == u0r else f"d={len(out)-u0r:+d}"
        lines.append(f"  {rid} out={len(out)} u0={u0r} {mark} cons={cons}")
        if len(out) >= 376 + 16384:
            render_indexed(out[376:376 + 16384], 128, 128, pal, SHAPEDIR / f"{rid}_a.png")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
