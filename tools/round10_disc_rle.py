# -*- coding: utf-8 -*-
"""Discriminator-aware RLE and per-scanline restarts — the 1170-byte gap."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from round10_256 import compact_gray, highbit_until, load_all_256, packbits_until, render128
from round9_shapes import packbits, rle_highbit, header, scan_clut_run

SHAPEDIR = ROOT / "reference/shapes"
OUT = ROOT / "reference/docs/round10_disc_rle.txt"
VALID = frozenset(range(3, 17))


def disc_rle(src: bytes, pal: set[int], mid: str) -> bytes:
    """In-palette bytes are literals. 0x00-0x02 and 0x80+ are controls.

    mid: how to treat 17..127
      'pixel' — emit as pixel
      'copy'  — copy (b+1) literals (standard highbit low half)
      'skip'  — skip the byte
    """
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        b = src[i]
        i += 1
        if b in pal:
            out.append(b)
        elif b <= 2:
            count = b + 1
            take = min(count, n - i)
            out.extend(src[i : i + take])
            i += take
        elif b >= 0x80:
            count = (b & 0x7F) + 1
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
        else:
            if mid == "pixel":
                out.append(b)
            elif mid == "copy":
                count = b + 1
                take = min(count, n - i)
                out.extend(src[i : i + take])
                i += take
            elif mid == "skip":
                continue
    return bytes(out)


def disc_rle_packbits_repeat(src: bytes, pal: set[int]) -> bytes:
    """In-palette = literal; 00-02 = copy n+1; 80+ = PackBits repeat (257-n)."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        b = src[i]
        i += 1
        if b in pal:
            out.append(b)
        elif b <= 2:
            count = b + 1
            take = min(count, n - i)
            out.extend(src[i : i + take])
            i += take
        elif b == 0x80:
            continue
        elif b >= 0x81:
            count = 257 - b
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
        else:
            out.append(b)
    return bytes(out)


def decode_rows(src: bytes, decode_until, row_w: int, n_rows: int) -> tuple[bytes, int, list[int]]:
    """Restart decoder every row_w output pixels. Returns (pixels, consumed, per-row consumed)."""
    out = bytearray()
    pos = 0
    row_cons: list[int] = []
    for _ in range(n_rows):
        if pos >= len(src):
            break
        row, cons = decode_until(src[pos:], row_w)
        out.extend(row)
        row_cons.append(cons)
        pos += cons
    return bytes(out), pos, row_cons


def natural_end(src: bytes, decode_fn, target: int) -> tuple[int, int]:
    """Run decode_fn on whole src; report (out_len, consumed_if_stop_at_target)."""
    full = decode_fn(src)
    return len(full), -1


def main() -> None:
    shapes = load_all_256()
    lines: list[str] = []

    for rid in (195, 196, 198):
        d = shapes[rid]
        pal_map = compact_gray(d)
        pal = {i for i in range(256) if pal_map[i] is not None}
        u0, u4, b6 = header(d)
        clut_off, clut = scan_clut_run(d, 23)
        clut_idx = [e[0] for e in clut]
        lines.append(f"\n==== rsrc {rid} packed={len(d)} u0={u0} b6={b6} ====")
        lines.append(f"  compact={sorted(pal)}")
        lines.append(f"  8-byte clut @ {clut_off} n={len(clut)} idx={clut_idx[:20]}{'...' if len(clut)>20 else ''}")

        for start in (23, 211, 249, 256, 258, 264):
            if start >= len(d):
                continue
            sl = d[start:]
            lines.append(f"  -- start @{start} sl={len(sl)} --")
            for mid in ("pixel", "copy", "skip"):
                out = disc_rle(sl, pal, mid)
                out3 = disc_rle(sl, VALID, mid)
                lines.append(
                    f"    disc pal/{mid}: out={len(out)} d_u0={len(out)-u0:+d} "
                    f"d_32768={len(out)-32768:+d} d_2x16384={len(out)-32768:+d}"
                )
                if pal != VALID:
                    lines.append(f"    disc 3-16/{mid}: out={len(out3)} d_u0={len(out3)-u0:+d}")
            pb = disc_rle_packbits_repeat(sl, pal)
            lines.append(f"    disc+packbits-repeat: out={len(pb)} d_u0={len(pb)-u0:+d} d_32768={len(pb)-32768:+d}")

            hb = rle_highbit(sl)
            pbf = packbits(sl)
            lines.append(f"    highbit full: out={len(hb)} d_u0={len(hb)-u0:+d}")
            lines.append(f"    packbits full: out={len(pbf)} d_u0={len(pbf)-u0:+d}")

            # per-scanline
            for name, fn in (("packbits", packbits_until), ("highbit", highbit_until)):
                pix, cons, rows = decode_rows(sl, fn, 128, 128)
                exact_rows = sum(1 for r in rows if r > 0)
                lines.append(
                    f"    row128 {name}: out={len(pix)} cons={cons} rows={exact_rows} "
                    f"left={len(sl)-cons} row_cons_minmax=({min(rows) if rows else 0},{max(rows) if rows else 0})"
                )
                # second image
                pix2, cons2, rows2 = decode_rows(sl[cons:], fn, 128, 128)
                lines.append(
                    f"      +imgB {name}: out={len(pix2)} cons={cons2} rows={len(rows2)} "
                    f"end={start+cons+cons2} left={len(d)-(start+cons+cons2)}"
                )
            # per-column
            for name, fn in (("packbits", packbits_until), ("highbit", highbit_until)):
                pix, cons, cols = decode_rows(sl, fn, 128, 128)
                # same as rows for 128x128; also try 64-tall columns? skip
                pass

        # render best disc variants from 258
        pal_rgb = pal_map
        for mid in ("pixel", "copy"):
            out = disc_rle(d[258:], pal, mid)
            if len(out) >= 16384:
                render128(out[:16384], pal_rgb, SHAPEDIR / f"{rid}_disc_{mid}_a.png")
            if len(out) >= 32768:
                render128(out[16384:32768], pal_rgb, SHAPEDIR / f"{rid}_disc_{mid}_b.png")
            elif len(out) > 16384:
                tail = out[16384:]
                render128(tail, pal_rgb, SHAPEDIR / f"{rid}_disc_{mid}_b.png")

        # per-row packbits render
        pix, cons, _ = decode_rows(d[258:], packbits_until, 128, 128)
        render128(pix, pal_rgb, SHAPEDIR / f"{rid}_rowpb_a.png")
        pix2, cons2, _ = decode_rows(d[258 + cons :], packbits_until, 128, 128)
        if pix2:
            render128(pix2, pal_rgb, SHAPEDIR / f"{rid}_rowpb_b.png")
        pixh, consh, _ = decode_rows(d[258:], highbit_until, 128, 128)
        render128(pixh, pal_rgb, SHAPEDIR / f"{rid}_rowhb_a.png")
        pixh2, _, _ = decode_rows(d[258 + consh :], highbit_until, 128, 128)
        if pixh2:
            render128(pixh2, pal_rgb, SHAPEDIR / f"{rid}_rowhb_b.png")

    # header fields 200-270 on 195-202
    lines.append("\n==== packed u16/u32 200-270 across 195-202 ====")
    d195 = shapes[195]
    for off in range(200, 271):
        if off + 2 > len(d195):
            break
        vals = []
        ident = True
        v0 = d195[off]
        for rid in range(195, 203):
            vals.append(shapes[rid][off] if off < len(shapes[rid]) else None)
            if off < len(shapes[rid]) and shapes[rid][off] != v0:
                ident = False
        mark = "CONST" if ident else "vary"
        u16 = struct.unpack_from(">H", d195, off)[0] if off + 2 <= len(d195) else 0
        flag = ""
        if u16 in (128, 188, 256, 376, 16384, 2, 8, 16, 32, 64, 280, 344):
            flag = f"  **u16={u16}"
        lines.append(f"  @{off:4d} {mark} b195={d195[off]:02x} u16={u16:5d}{flag}")

    # 198 extra indices: are 0x11/0x12 in the 8-byte clut?
    lines.append("\n==== 198 clut vs 0x11/0x12 ====")
    d198 = shapes[198]
    _, clut198 = scan_clut_run(d198, 23)
    lines.append(f"  clut idx={ [e[0] for e in clut198] }")
    # scan all compact-like 5-byte and any index mentions
    idx_hits = []
    pos = 23
    while pos + 5 <= 280:
        idx = struct.unpack_from(">H", d198, pos)[0]
        if idx <= 255 and d198[pos + 2] in (3, 4):
            idx_hits.append((pos, idx, d198[pos + 2], d198[pos + 3], d198[pos + 4]))
            pos += 5
        else:
            pos += 1
    lines.append(f"  compact-like records: {idx_hits[:20]} n={len(idx_hits)}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
