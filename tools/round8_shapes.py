# -*- coding: utf-8 -*-
"""Task 3: .256 table from offset 7; clut scan; entropy; 195-202 sizes."""

from __future__ import annotations

import io
import math
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from pid_level import load_maps  # noqa: E402
from shapes_pass1 import IDENT  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
OUT = ROOT / "reference/docs/round8_shapes.txt"
PALDIR = ROOT / "reference/palettes"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


def read_u32_table(data: bytes, start: int, n: int = 64) -> list[int]:
    vals = []
    pos = start
    for _ in range(n):
        if pos + 4 > len(data):
            break
        vals.append(struct.unpack_from(">I", data, pos)[0])
        pos += 4
    return vals


def ascending_in_range(vals: list[int], size: int, shift: int = 0) -> int:
    count = 0
    prev = -1
    for raw in vals:
        v = raw >> shift if shift else raw
        if v <= prev or v >= size:
            break
        count += 1
        prev = v
    return count


def shannon(block: bytes) -> float:
    if not block:
        return 0.0
    n = len(block)
    freq = Counter(block)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def try_clut_at(data: bytes, off: int) -> tuple[int, list[tuple[int, int, int, int]]] | None:
    """Return (count, entries) if a well-formed 256-entry clut starts here."""
    if off + 8 + 256 * 8 > len(data):
        return None
    seed, flags, size = struct.unpack_from(">IHH", data, off)
    # size field is n-1 for Mac clut
    if size != 255 and size != 256:
        # also allow raw 256 entries without header
        return None
    n = size + 1 if size == 255 else size
    if n != 256:
        return None
    pos = off + 8
    entries = []
    for i in range(256):
        if pos + 8 > len(data):
            return None
        idx, r, g, b = struct.unpack_from(">HHHH", data, pos)
        entries.append((idx, r, g, b))
        pos += 8
    idxs = [e[0] for e in entries]
    if idxs == list(range(256)):
        return 256, entries
    # allow index in high byte only / 0..255 any unique
    if sorted(idxs) == list(range(256)):
        return 256, entries
    return None


def try_raw_clut(data: bytes, off: int) -> list[tuple[int, int, int, int]] | None:
    if off + 256 * 8 > len(data):
        return None
    entries = []
    for i in range(256):
        idx, r, g, b = struct.unpack_from(">HHHH", data, off + i * 8)
        entries.append((idx, r, g, b))
    idxs = [e[0] for e in entries]
    if idxs == list(range(256)) or sorted(idxs) == list(range(256)):
        return entries
    # indices all 0 and RGB look like colors (high bytes used)
    if all(e[0] == 0 for e in entries):
        highs = [(e[1] >> 8, e[2] >> 8, e[3] >> 8) for e in entries]
        if len(set(highs)) > 32:
            return entries
    return None


def main() -> None:
    shapes = load_all_256()
    s128 = shapes[128]
    lines: list[str] = []

    lines.append(f"== T3 header 128 size={len(s128)} ==")
    lines.append(f"first16={s128[:16].hex(' ')}")
    lines.append(f"u32@0={struct.unpack_from('>I', s128, 0)[0]}")
    lines.append(f"u16@4={struct.unpack_from('>H', s128, 4)[0]} hex={s128[4:6].hex()}")
    lines.append(f"u8@6={s128[6]}")

    raw64 = read_u32_table(s128, 7, 64)
    lines.append("\n== T3(a) first 64 u32be from offset 7 ==")
    for i, v in enumerate(raw64):
        shifted = v >> 8
        flag = ""
        if i > 0:
            prev = raw64[i - 1] >> 8
            if shifted <= prev or shifted >= len(s128):
                flag = " BREAK" if shifted <= prev or shifted >= len(s128) else ""
        lines.append(
            f"  [{i:02d}] raw={v:#010x} ({v:10d}) >>8={shifted:8d}{flag}"
        )

    # find first break on >>8
    n_asc = ascending_in_range(raw64, len(s128), shift=8)
    lines.append(f"ascending >>8 count from off7={n_asc}")
    n_raw = ascending_in_range(raw64, len(s128), shift=0)
    lines.append(f"ascending raw count from off7={n_raw}")

    lines.append("\n== T3(b) table-read comparison ==")

    def read_u16(data, start, n=80):
        out = []
        pos = start
        for _ in range(n):
            if pos + 2 > len(data):
                break
            out.append(struct.unpack_from(">H", data, pos)[0])
            pos += 2
        return out

    def read_u24(data, start, n=80):
        out = []
        pos = start
        for _ in range(n):
            if pos + 3 > len(data):
                break
            out.append(int.from_bytes(data[pos : pos + 3], "big"))
            pos += 3
        return out

    count_b6 = s128[6]
    candidates = []
    for start, label, reader, shift in (
        (7, "u32@7", lambda d, s: read_u32_table(d, s, 80), 0),
        (7, "u32@7>>8", lambda d, s: read_u32_table(d, s, 80), 8),
        (6, "u32@6", lambda d, s: read_u32_table(d, s, 80), 0),
        (6, "u32@6>>8", lambda d, s: read_u32_table(d, s, 80), 8),
        (8, "u32@8", lambda d, s: read_u32_table(d, s, 80), 0),
        (8, "u32@8>>8", lambda d, s: read_u32_table(d, s, 80), 8),
        (7, "u16@7", read_u16, 0),
        (7, "u24@7", read_u24, 0),
        (7, "u24@7>>8", read_u24, 8),
    ):
        vals = reader(s128, start)
        n = ascending_in_range(vals, len(s128), shift=shift)
        near = abs(n - count_b6)
        candidates.append((n, near, label, vals[:8]))
        lines.append(f"  {label:12s} ascending={n:3d} |n-count59|={near} first={vals[:6]}")

    best = max(candidates, key=lambda t: t[0])
    lines.append(f"BEST ascending={best[0]} via {best[2]}")

    # apply best-ish to other resources
    lines.append("\n== T3(b) u32@7>>8 ascending vs byte6 for focus rsrcs ==")
    for rid in (128, 129, 148, 153, 192, 195):
        d = shapes[rid]
        vals = read_u32_table(d, 7, 80)
        n = ascending_in_range(vals, len(d), shift=8)
        lines.append(f"  {rid} size={len(d)} b6={d[6]} asc>>8={n}")

    lines.append("\n== T3(c) clut scan rsrc 128 offsets 0..0x200 ==")
    found = []
    for off in range(0, 0x201):
        hit = try_clut_at(s128, off)
        if hit:
            found.append((off, "headered", hit[1]))
            lines.append(f"  HEADERED 256 clut at {off:#x}")
        raw = try_raw_clut(s128, off)
        if raw:
            found.append((off, "raw", raw))
            lines.append(f"  RAW 256 entries at {off:#x} idx0={raw[0]} idx1={raw[1]}")
    if not found:
        lines.append("  NO 256-entry clut (indices 0..255) in 0..0x200")
        # also scan whole file every 2 bytes for headered
        whole = []
        for off in range(0, min(len(s128) - 8 - 256 * 8, 8000), 2):
            hit = try_clut_at(s128, off)
            if hit:
                whole.append(off)
        lines.append(f"  whole-file headered clut offs (first 8k, step 2): {whole[:10]}")

    if found:
        entries = found[0][2]
        PALDIR.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (16, 16))
        pix = img.load()
        act = bytearray()
        for i, (idx, r, g, b) in enumerate(entries):
            rgb = (r >> 8, g >> 8, b >> 8)
            pix[i % 16, i // 16] = rgb
            act.extend(rgb)
        img.resize((256, 256), Image.Resampling.NEAREST).save(PALDIR / "master_256.png")
        (PALDIR / "master_256.act").write_bytes(bytes(act))
        lines.append(f"  wrote {PALDIR / 'master_256.png'} and .act")

    lines.append("\n== T3(d) entropy 1KB blocks ==")
    for rid in (128, 148, 192, 195):
        d = shapes[rid]
        ents = [shannon(d[i : i + 1024]) for i in range(0, len(d), 1024)]
        mean = sum(ents) / len(ents)
        lines.append(
            f"  {rid} blocks={len(ents)} mean={mean:.3f} min={min(ents):.3f} "
            f"max={max(ents):.3f} n>7.5={sum(1 for e in ents if e > 7.5)}"
        )
        jumps = []
        for i in range(1, len(ents)):
            if abs(ents[i] - ents[i - 1]) >= 1.5:
                jumps.append((i * 1024, ents[i - 1], ents[i]))
        lines.append(f"       jumps(|d|>=1.5): {jumps[:12]}")
        lines.append("       per-block: " + " ".join(f"{e:.2f}" for e in ents))

    lines.append("\n== T3(e) resources 195-202 ==")
    for rid in range(195, 203):
        d = shapes[rid]
        u0 = struct.unpack_from(">I", d, 0)[0]
        lines.append(
            f"  {rid} size={len(d)} u32@0={u0} b6={d[6]} "
            f"size-vs-33144={len(d)-33144} 16384+188={16384+188} "
            f"33144-size={33144-len(d)}"
        )
    lines.append("  33144/2=16572  128*128=16384  128*128/2=8192  256*128=32768")
    lines.append("  33144-16384=16760  33144-8192=24952  33144-32768=376")

    lines.append("\n== T3(f) rsrc 192 / 153 first 64 and table @7 ==")
    for rid in (192, 153):
        d = shapes[rid]
        lines.append(f"\n--- {rid} {IDENT.get(rid)} size={len(d)} b6={d[6]} ---")
        lines.append(f"first64={d[:64].hex(' ')}")
        vals = read_u32_table(d, 7, max(d[6] + 8, 32))
        lines.append("u32@7:")
        for i, v in enumerate(vals):
            lines.append(f"  [{i:02d}] {v:#010x} >>8={v>>8}")

    # T5 texture table while we're here
    levels = load_maps(MAPS)
    lines.append("\n== T5(a) texture_list all 25 ==")
    for li, lev in enumerate(levels):
        parts = []
        for val in lev.texture_list:
            if val == -1:
                parts.append("-1")
            else:
                parts.append(f"v{(val>>12)&0xF}/s{val&0xFFF}->{128+(val&0xFFF)}")
        walls = lev.texture_list[0]
        theme = "?"
        if walls != -1:
            s = walls & 0xFFF
            theme = {64: "plain", 65: "vine", 66: "crystal"}.get(s, str(s))
        lines.append(f"L{li:02d} {theme:7s} {lev.name:42s} {parts}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print(f"... wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
