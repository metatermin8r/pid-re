# -*- coding: utf-8 -*-
"""Own-palette render of 195; tighten clut filter; try pixel-start variants."""

from __future__ import annotations

import io
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from round9_packbits115 import packbits_exact  # noqa: E402
from round9_shapes import header, packbits, rgb8, section_offs  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/round9_pixels.txt"
SHAPEDIR = ROOT / "reference/shapes"
PALDIR = ROOT / "reference/palettes"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


def mac_rgb(r: int, g: int, b: int) -> bool:
    """True if each 16-bit channel has matching high/low bytes (0xA5A5)."""
    return (r >> 8) == (r & 0xFF) and (g >> 8) == (g & 0xFF) and (b >> 8) == (b & 0xFF)


def find_clut_runs(data: bytes, min_n: int = 4, require_mac: bool = True) -> list[tuple[int, int, int, int]]:
    runs = []
    n = len(data)
    i = 0
    while i + 8 <= n:
        idx0, r, g, b = struct.unpack_from(">HHHH", data, i)
        if idx0 > 255 or (require_mac and not mac_rgb(r, g, b)):
            i += 1
            continue
        entries = 0
        pos = i
        prev = idx0 - 1
        while pos + 8 <= n:
            idx, r, g, b = struct.unpack_from(">HHHH", data, pos)
            if idx > 255 or idx != prev + 1:
                break
            if require_mac and not mac_rgb(r, g, b):
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


def render_indexed(pixels: bytes, w: int, h: int, pal: list[tuple[int, int, int] | None], path: Path) -> None:
    img = Image.new("RGB", (w, h), (255, 0, 255))
    pix = img.load()
    for i, idx in enumerate(pixels[: w * h]):
        rgb = pal[idx] if idx < 256 else None
        pix[i % w, i // w] = rgb if rgb is not None else (idx, idx, idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def m1_line(src: bytes, start: int, row_len: int) -> tuple[bytes, int] | None:
    """Marathon 1 packed line: i16be opcode >0 copy, <0 zeros, 0 end."""
    i = start
    n = len(src)
    out = bytearray()
    while i + 2 <= n:
        op = struct.unpack_from(">h", src, i)[0]
        i += 2
        if op == 0:
            return bytes(out), i
        if op > 0:
            if i + op > n:
                return None
            out.extend(src[i : i + op])
            i += op
        else:
            out.extend(b"\x00" * (-op))
        if len(out) > row_len + 8:
            return None
    return None


def m1_image(src: bytes, start: int, rows: int, row_len: int) -> tuple[bytes, int] | None:
    i = start
    buf = bytearray()
    for _ in range(rows):
        line = m1_line(src, i, row_len)
        if line is None:
            return None
        data, i = line
        if len(data) != row_len:
            # allow shorter (transparent tail)
            if len(data) > row_len:
                return None
            data = data + b"\x00" * (row_len - len(data))
        buf.extend(data)
    return bytes(buf), i


def main() -> None:
    shapes = load_all_256()
    lines: list[str] = []
    d195 = shapes[195]

    lines.append("== rsrc 195 bytes 23..230 ==")
    lines.append(hexdump_mac_roman(d195[23:230]))

    runs = find_clut_runs(d195, min_n=4, require_mac=True)
    lines.append(f"\nmac-filtered clut runs: {runs}")

    pal195: list[tuple[int, int, int] | None] = [None] * 256
    for o, lo, hi, n in runs:
        for k in range(n):
            idx, r, g, b = struct.unpack_from(">HHHH", d195, o + k * 8)
            pal195[idx] = rgb8(r, g, b)
            lines.append(f"  idx {idx:3d} raw=({r:#06x},{g:#06x},{b:#06x}) rgb={rgb8(r,g,b)}")

    # compact 5-byte records before clut
    lines.append("\n== compact records from 23 ==")
    pos = 23
    lines.append(f"  prefix {d195[23:32].hex(' ')}")
    pos = 29  # after 02 00 00 02 00 10 ?
    # try from various
    for start in (23, 25, 27, 29):
        recs = []
        p = start
        while p + 5 <= 130:
            idx = struct.unpack_from(">H", d195, p)[0]
            kind = d195[p + 2]
            if idx > 40 or kind not in (3, 4):
                break
            recs.append((p, idx, kind, d195[p : p + 5].hex(" ")))
            p += 5
        lines.append(f"  start {start}: n={len(recs)} last={recs[-3:] if recs else None} nextp={p}")

    clut_end = runs[0][0] + runs[0][3] * 8 if runs else 227
    lines.append(f"\nclut_end={clut_end}")

    # raw pixels after clut
    raw = d195[clut_end:]
    lines.append(f"raw after clut: {len(raw)} bytes")
    lines.append(hexdump_mac_roman(raw[:64]))

    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    if len(raw) >= 16384:
        render_indexed(raw[:16384], 128, 128, pal195, SHAPEDIR / "195_raw_a.png")
        render_indexed(raw[16384:32768] if len(raw) >= 32768 else raw[len(raw)//2:], 128, 128, pal195, SHAPEDIR / "195_raw_b.png")
        hist = Counter(raw[:16384])
        lines.append(f"  raw hist: {hist.most_common(10)}")

    # packbits after clut, own palette
    out, cons = packbits_exact(d195[clut_end:], 32768)
    lines.append(f"packbits after clut: out={len(out)} cons={cons} left={len(d195)-clut_end-cons}")
    render_indexed(out[:16384], 128, 128, pal195, SHAPEDIR / "195_pb_own_a.png")
    render_indexed(out[16384:32768], 128, 128, pal195, SHAPEDIR / "195_pb_own_b.png")
    hist = Counter(out[:16384])
    lines.append(f"  pb hist: {hist.most_common(10)}")

    # packbits from 23 until 33144, own palette, slice 376
    out23, cons23 = packbits_exact(d195[23:], 33144)
    lines.append(f"packbits @23: out={len(out23)} cons={cons23}")
    render_indexed(out23[376:376+16384], 128, 128, pal195, SHAPEDIR / "195_pb23_own.png")
    hist = Counter(out23[376:376+16384])
    lines.append(f"  pb23 from376 hist: {hist.most_common(10)}")

    # two-stream 16572
    a, ca = packbits_exact(d195[23:], 16572)
    b, cb = packbits_exact(d195[23+ca:], 16572)
    lines.append(f"two-stream @23: a={len(a)} consA={ca} b={len(b)} consB={cb} total_cons={ca+cb} packed_payload={len(d195)-23}")
    render_indexed(a[188:188+16384] if len(a) >= 188+16384 else a[:16384], 128, 128, pal195, SHAPEDIR / "195_twostream_a.png")
    if len(b) >= 16384:
        render_indexed(b[188:188+16384] if len(b) >= 188+16384 else b[:16384], 128, 128, pal195, SHAPEDIR / "195_twostream_b.png")

    # M1 lines
    lines.append("\n== M1 line codec ==")
    for start in (23, 29, 115, clut_end, clut_end + 2):
        img = m1_image(d195, start, 128, 128)
        if img is None:
            # try a few lines
            ok = 0
            i = start
            for _ in range(8):
                ln = m1_line(d195, i, 128)
                if ln is None:
                    break
                data, i = ln
                ok += 1
            lines.append(f"  @{start} first-lines={ok}")
        else:
            data, consumed = img
            lines.append(f"  @{start} 128x128 OK cons={consumed} leftover={len(d195)-consumed}")
            render_indexed(data, 128, 128, pal195, SHAPEDIR / f"195_m1_{start}.png")

    # union with mac filter
    slots: list[tuple[int, int, int] | None] = [None] * 256
    raw16: list[tuple[int, int, int] | None] = [None] * 256
    conflicts = []
    contrib = {}
    for rid in sorted(shapes):
        rs = find_clut_runs(shapes[rid], min_n=4, require_mac=True)
        ranges = []
        for o, lo, hi, n in rs:
            ranges.append((lo, hi, n, o))
            for k in range(n):
                idx, r, g, b = struct.unpack_from(">HHHH", shapes[rid], o + k * 8)
                if raw16[idx] is None:
                    raw16[idx] = (r, g, b)
                    slots[idx] = rgb8(r, g, b)
                elif raw16[idx] != (r, g, b):
                    conflicts.append((idx, rid, raw16[idx], (r, g, b)))
        contrib[rid] = ranges
    filled = [i for i in range(256) if slots[i] is not None]
    empty = [i for i in range(256) if slots[i] is None]
    lines.append("\n== T1(b) mac-filtered union ==")
    lines.append(f"  filled={len(filled)} empty_n={len(empty)} empty={empty}")
    lines.append(f"  conflicts={len(conflicts)}")
    for c in conflicts[:15]:
        lines.append(f"    idx={c[0]} vs rsrc {c[1]} {c[2]} {c[3]}")
    lines.append("  ranges:")
    for rid, ranges in contrib.items():
        if ranges:
            lines.append(f"    {rid:3d} {[(a,b,n) for a,b,n,_ in ranges]}")

    # rewrite master with filtered palette
    PALDIR.mkdir(parents=True, exist_ok=True)
    cell = 28
    from PIL import ImageDraw, ImageFont

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
    lines.append("  rewrote master_256.png with mac-filtered union")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
