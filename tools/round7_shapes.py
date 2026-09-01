# -*- coding: utf-8 -*-
"""Task 3: .256 chunk directory. Task 4: clut palettes and texture slots."""

from __future__ import annotations

import io
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from pid_level import load_maps  # noqa: E402
from shapes_pass1 import IDENT, load_type, parse_clut  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
OUT = ROOT / "reference/docs/round7_shapes.txt"
PALDIR = ROOT / "reference/palettes"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


def chunk_offsets(data: bytes, start: int = 8, shift: int = 8) -> list[int]:
    """Read u32be words; stored value >> shift is the byte offset.

    Observed packing: 00 04 e8 00 == 1256 << 8.
    """
    offs = []
    pos = start
    prev = -1
    while pos + 4 <= len(data):
        raw = struct.unpack_from(">I", data, pos)[0]
        v = raw >> shift if shift else raw
        if v <= prev or v >= len(data) or v < start:
            break
        offs.append(v)
        prev = v
        pos += 4
    return offs


def main() -> None:
    shapes = load_all_256()
    levels = load_maps(MAPS)
    lines: list[str] = []

    # ----- Task 3 -----
    s128 = shapes[128]
    lines.append(f"== T3 .256 128 size={len(s128)} ==")
    lines.append(f"first16={s128[:16].hex(' ')}")
    lines.append(f"u32be[0]={struct.unpack_from('>I', s128, 0)[0]}")
    lines.append(f"u16be[0..6]={struct.unpack_from('>4H', s128, 0)}")
    raw8 = [struct.unpack_from(">I", s128, 8 + i * 4)[0] for i in range(6)]
    lines.append(f"u32be from 8 (raw)={ [hex(v) for v in raw8] }")
    lines.append(f"u32be from 8 >>8={ [v >> 8 for v in raw8] }")
    offs = chunk_offsets(s128)
    lines.append(f"ascending u32be from 8: count={len(offs)} first={offs[:8]} last={offs[-3:]}")
    # count in header?
    header_vals = {
        "u16@0": struct.unpack_from(">H", s128, 0)[0],
        "u16@2": struct.unpack_from(">H", s128, 2)[0],
        "u16@4": struct.unpack_from(">H", s128, 4)[0],
        "u16@6": struct.unpack_from(">H", s128, 6)[0],
        "u32@0": struct.unpack_from(">I", s128, 0)[0],
        "u32@4": struct.unpack_from(">I", s128, 4)[0],
    }
    lines.append(f"header fields vs chunk count {len(offs)}: {header_vals}")
    for k, v in header_vals.items():
        if v == len(offs):
            lines.append(f"  MATCH {k}=={v}")

    # maybe count is number of offsets including a terminator, or count-1
    for k, v in header_vals.items():
        if v in (len(offs) - 1, len(offs) + 1, len(offs) * 4, 8 + len(offs) * 4):
            lines.append(f"  near-match {k}={v}")

    lines.append("\n== T3 first 5 chunks of 128 ==")
    ends = offs[1:] + [len(s128)]
    for i, (a, b) in enumerate(zip(offs[:5], ends[:5])):
        chunk = s128[a:b]
        lines.append(
            f"  chunk{i} off={a} len={b-a} first32={chunk[:32].hex(' ')}"
        )
        # length vs image
        ln = b - a
        for bpp, name in ((8, "8bpp"), (4, "4bpp")):
            pixels = ln * (8 // bpp) if bpp else 0
            # try if first 4 bytes are w,h
        if len(chunk) >= 4:
            w1, h1 = struct.unpack_from(">HH", chunk, 0)
            w2, h2 = chunk[0], chunk[1]
            lines.append(
                f"       u16wh=({w1},{h1}) u8wh=({w2},{chunk[1]}) "
                f"8bpp={ln}px 4bpp={ln*2}px "
                f"u16wh*1={w1*h1 if w1*h1<10**7 else 'big'} "
                f"u16wh+hdr={w1*h1+4 if w1<4000 and h1<4000 else '-'}"
            )

    lines.append("\n== T3 chunk length histogram 128 ==")
    lens = [b - a for a, b in zip(offs, ends)] if offs else []
    if lens:
        lines.append(
            f"  n={len(lens)} min={min(lens)} max={max(lens)} "
            f"median={sorted(lens)[len(lens)//2]}"
        )
        lines.append(f"  most_common={Counter(lens).most_common(12)}")
    else:
        lines.append("  no chunks")

    focus = [129, 148, 192, 153]
    lines.append("\n== T3 same parse on 129/148/192/153 ==")
    for rid in focus:
        data = shapes[rid]
        o = chunk_offsets(data)
        e = o[1:] + [len(data)] if o else []
        clens = [b - a for a, b in zip(o, e)]
        hdr = data[:16].hex(" ")
        lines.append(
            f"  {rid} {IDENT.get(rid,'?'):40s} size={len(data):6d} chunks={len(o):4d} "
            f"len_min={min(clens) if clens else None} len_max={max(clens) if clens else None} "
            f"hdr={hdr}"
        )
        if o[:3]:
            lines.append(f"       first_offs={o[:5]} first_lens={clens[:5]}")
            lines.append(f"       chunk0_32={data[o[0]:o[0]+32].hex(' ')}")

    lines.append("\n== T3 all 50 .256 ==")
    for rid in sorted(shapes):
        data = shapes[rid]
        o = chunk_offsets(data)
        lines.append(
            f"  {rid:3d} size={len(data):6d} chunks={len(o):4d} "
            f"{IDENT.get(rid, '')}"
        )

    # 4bpp vs 8bpp: if common lengths match w*h or w*h/2 for typical sizes
    lines.append("\n== T3 bpp hint (common lengths vs w*h) ==")
    common_lens = Counter()
    for data in shapes.values():
        o = chunk_offsets(data)
        e = o[1:] + [len(data)]
        for a, b in zip(o, e):
            common_lens[b - a] += 1
    lines.append(f"  top lengths: {common_lens.most_common(20)}")
    typical_wh = [(16, 16), (32, 32), (64, 64), (128, 128), (8, 8), (24, 24), (48, 48), (20, 20)]
    for w, h in typical_wh:
        for bpp, extra in ((8, 0), (8, 4), (8, 8), (4, 0), (4, 4), (4, 8)):
            need = w * h * bpp // 8 + extra
            if common_lens[need]:
                lines.append(f"  {w}x{h} {bpp}bpp +{extra}hdr = {need} hits={common_lens[need]}")

    # ----- Task 4 -----
    PALDIR.mkdir(parents=True, exist_ok=True)
    lines.append("\n== T4 clut 128-135 ==")
    for rid in range(128, 136):
        blob = load_type(APP, b"clut", rid)
        seed, flags, size = struct.unpack(">IHH", blob[:8])
        entries = parse_clut(blob)
        lines.append(f"clut {rid}: bytes={len(blob)} seed={seed} flags={flags} size={size} n={len(entries)}")
        img = Image.new("RGB", (15, 1))
        pix = img.load()
        for i, (idx, r, g, b) in enumerate(entries):
            r8, g8, b8 = r >> 8, g >> 8, b >> 8
            lines.append(
                f"  [{i:2d}] idx={idx:2d} raw=({r:5d},{g:5d},{b:5d}) "
                f"hex16=({r:04x},{g:04x},{b:04x}) rgb8=({r8:3d},{g8:3d},{b8:3d})"
            )
            if i < 15:
                pix[i, 0] = (r8, g8, b8)
        scaled = img.resize((15 * 16, 16), Image.Resampling.NEAREST)
        path = PALDIR / f"clut_{rid}.png"
        scaled.save(path)
        lines.append(f"  wrote {path}")

    lines.append("\n== T4 texture_list variation/set ==")
    slot_vals: dict[int, Counter] = defaultdict(Counter)
    slot_vars: dict[int, Counter] = defaultdict(Counter)
    slot_sets: dict[int, Counter] = defaultdict(Counter)
    for li, lev in enumerate(levels):
        lines.append(f"L{li:02d} {lev.name}")
        for slot, val in enumerate(lev.texture_list):
            slot_vals[slot][val] += 1
            if val == -1:
                lines.append(f"  [{slot}] -1")
                continue
            var = (val >> 12) & 0xF
            texset = val & 0x0FFF
            resid = texset + 128
            slot_vars[slot][var] += 1
            slot_sets[slot][texset] += 1
            lines.append(
                f"  [{slot}] {val:6d} var={var} set={texset:3d} rsrc={resid} {IDENT.get(resid,'')}"
            )

    lines.append("\n== T4 variations per slot ==")
    for slot in range(8):
        lines.append(
            f"  slot {slot}: vars={dict(slot_vars[slot])} "
            f"sets={sorted(slot_sets[slot])} n_neg1={slot_vals[slot][-1]}"
        )

    lines.append("\n== T4 slot ranges / floor-ceiling 195-202 ==")
    for slot in range(8):
        nonempty = [v for v in slot_vals[slot] if v != -1]
        rsrcs = sorted({(v & 0x0FFF) + 128 for v in nonempty})
        fc = [r for r in rsrcs if 195 <= r <= 202]
        lines.append(
            f"  slot {slot}: used_on={25 - slot_vals[slot][-1]}/25 "
            f"raw_min={min(nonempty) if nonempty else None} raw_max={max(nonempty) if nonempty else None} "
            f"rsrc={rsrcs} floor_ceil={fc}"
        )

    # Does variation N == clut 128+N? variations observed
    all_vars = sorted({v for c in slot_vars.values() for v in c})
    lines.append(f"\nall variations seen: {all_vars}  clut ids 128-135 => N=0..7")
    lines.append("inferred: variation 0-3 documented; observed set listed above")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:120]))
    print(f"... wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
