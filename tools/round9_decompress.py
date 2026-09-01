# -*- coding: utf-8 -*-
"""Round 9 follow-up: find real clut runs; brute-force RLE start offsets."""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from round9_shapes import (  # noqa: E402
    SCHEMES,
    header,
    packbits,
    rle_highbit,
    rle_highbit_inv,
    section_offs,
)

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/round9_decompress.txt"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    out = {}
    for rid in rf[b".256"]:
        res = rf[b".256"][rid]
        raw = res.data_raw
        try:
            dec = res.data
        except Exception:
            dec = None
        out[rid] = (raw, dec)
    return out


def find_clut_runs(data: bytes, min_n: int = 4) -> list[tuple[int, int, int, int]]:
    """All runs of 8-byte (index,R,G,B) with index ascending by 1. Returns (off, lo, hi, n)."""
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
            idx, r, g, b = struct.unpack_from(">HHHH", data, pos)
            if idx > 255 or idx != prev + 1:
                break
            # reject obviously non-colour if all three channels identical to index
            entries += 1
            prev = idx
            pos += 8
        if entries >= min_n:
            lo = struct.unpack_from(">H", data, i)[0]
            hi = lo + entries - 1
            runs.append((i, lo, hi, entries))
            i = pos
        else:
            i += 1
    return runs


def packbits_until(src: bytes, target: int) -> tuple[int, int, int]:
    """Run PackBits until output >= target. Return (out_len, consumed, leftover)."""
    out_n = 0
    i = 0
    n = len(src)
    while i < n and out_n < target:
        ctrl = src[i]
        i += 1
        if ctrl <= 127:
            count = ctrl + 1
            take = min(count, n - i)
            out_n += take
            i += take
            if take < count:
                break
        elif ctrl == 128:
            continue
        else:
            count = 257 - ctrl
            if i >= n:
                break
            out_n += count
            i += 1
    return out_n, i, n - i


def packbits_rows(src: bytes, width: int, n_rows: int) -> tuple[int, int]:
    """Decode n_rows of PackBits, each expanding to exactly `width` bytes.
    Returns (rows_ok, consumed) or (rows_decoded, consumed) on shortfall."""
    i = 0
    n = len(src)
    rows = 0
    for _ in range(n_rows):
        got = 0
        start_i = i
        while got < width:
            if i >= n:
                return rows, i
            ctrl = src[i]
            i += 1
            if ctrl <= 127:
                count = ctrl + 1
                take = min(count, n - i, width - got)
                got += take
                i += min(count, n - (i - 1) - 1) if False else min(count, n - i + 0)
                # consumed `count` input bytes after ctrl, even if we only needed some
                # redo properly:
                return _packbits_rows_impl(src, width, n_rows)
            elif ctrl == 128:
                continue
            else:
                count = min(257 - ctrl, width - got)
                if i >= n:
                    return rows, i
                got += 257 - ctrl
                i += 1
                if got > width:
                    return rows, i
        rows += 1
        if i == start_i:
            break
    return rows, i


def _packbits_rows_impl(src: bytes, width: int, n_rows: int) -> tuple[int, int]:
    i = 0
    n = len(src)
    rows = 0
    for _ in range(n_rows):
        row = bytearray()
        guard = 0
        while len(row) < width:
            if i >= n:
                return rows, i
            ctrl = src[i]
            i += 1
            if ctrl <= 127:
                count = ctrl + 1
                chunk = src[i : i + count]
                i += len(chunk)
                row.extend(chunk)
            elif ctrl == 128:
                continue
            else:
                count = 257 - ctrl
                if i >= n:
                    return rows, i
                row.extend(bytes([src[i]]) * count)
                i += 1
            guard += 1
            if guard > width + 8:
                return rows, i
        if len(row) != width:
            return rows, i
        rows += 1
    return rows, i


def highbit_until(src: bytes, target: int, plus1: bool = True) -> tuple[int, int]:
    out_n = 0
    i = 0
    n = len(src)
    while i < n and out_n < target:
        ctrl = src[i]
        i += 1
        if ctrl & 0x80:
            count = (ctrl & 0x7F) + (1 if plus1 else 0)
            if count <= 0:
                continue
            if i >= n:
                break
            out_n += count
            i += 1
        else:
            count = ctrl + (1 if plus1 else 0)
            if count <= 0:
                continue
            take = min(count, n - i)
            out_n += take
            i += take
    return out_n, i


def main() -> None:
    blobs = load_all_256()
    lines: list[str] = []

    raw195, dec195 = blobs[195]
    lines.append("== data vs data_raw 195 ==")
    lines.append(f"  data_raw={len(raw195)} data={None if dec195 is None else len(dec195)} same={dec195 == raw195}")
    if dec195 is not None and dec195 != raw195:
        lines.append(f"  DATA is different! first16={dec195[:16].hex(' ')} len={len(dec195)}")

    lines.append("\n== header byte4/5 all 50 ==")
    for rid in sorted(blobs):
        d = blobs[rid][0]
        u0, u4, b6 = header(d)
        lines.append(f"  {rid:3d} u4={u4:#06x} b4={d[4]:02x} b5={d[5]:02x} b6={b6:3d} u0={u0}")

    lines.append("\n== T1 clut runs (min 8 entries) whole packed file ==")
    all_slots: dict[int, tuple[int, int, int, int]] = {}
    conflicts = []
    for rid in sorted(blobs):
        d = blobs[rid][0]
        runs = find_clut_runs(d, min_n=8)
        if not runs:
            runs4 = find_clut_runs(d, min_n=4)
            lines.append(f"  {rid:3d} no n>=8; n>=4: {runs4[:4]}")
            continue
        parts = [f"off={o} idx={lo}..{hi} n={n}" for o, lo, hi, n in runs]
        lines.append(f"  {rid:3d} {parts}")
        for o, lo, hi, n in runs:
            for i in range(n):
                idx, r, g, b = struct.unpack_from(">HHHH", d, o + i * 8)
                rgb = (r, g, b)
                if idx in all_slots and all_slots[idx][1:] != rgb:
                    conflicts.append((idx, all_slots[idx][0], all_slots[idx][1:], rid, rgb))
                elif idx not in all_slots:
                    all_slots[idx] = (rid, r, g, b)

    lines.append(f"\n  union filled={len(all_slots)} empty={[i for i in range(256) if i not in all_slots]}")
    lines.append(f"  conflicts={len(conflicts)}")
    for c in conflicts[:20]:
        lines.append(f"    idx={c[0]} rsrc{c[1]} {c[2]} vs rsrc{c[3]} {c[4]}")

    # rsrc 128 dump around 0x17..0x80
    d128 = blobs[128][0]
    lines.append("\n== rsrc 128 bytes 23..200 ==")
    lines.append(hexdump_mac_roman(d128[23:200]))

    lines.append("\n== rsrc 195 bytes 23..200 ==")
    lines.append(hexdump_mac_roman(raw195[23:200]))

    # brute packbits start for exact 33144
    lines.append("\n== brute packbits start 0..500 for exact/near 33144 or 16572 ==")
    hits = []
    for start in range(0, 501):
        out = packbits(raw195[start:])
        if len(out) in (33144, 16572, 16384, 32768):
            hits.append((start, len(out), "EXACT"))
        elif abs(len(out) - 33144) <= 16:
            hits.append((start, len(out), "near33144"))
        elif abs(len(out) - 16572) <= 16:
            hits.append((start, len(out), "near16572"))
    lines.append(f"  hits={hits[:40]} count={len(hits)}")

    # packbits_until 33144 from various starts
    lines.append("\n== packbits_until 33144 ==")
    for start in (0, 7, 23, 24, 32, 115, 200, 256, 376):
        out_n, cons, left = packbits_until(raw195[start:], 33144)
        lines.append(f"  @{start:4d} out={out_n} consumed={cons} leftover={left} packed_tail={len(raw195)-start}")

    lines.append("\n== highbit_until 33144 ==")
    for start in (0, 7, 23, 24, 32, 115, 200):
        for plus1 in (True, False):
            out_n, cons = highbit_until(raw195[start:], 33144, plus1=plus1)
            left = len(raw195) - start - cons
            mark = "EXACT" if out_n == 33144 else ""
            lines.append(f"  @{start:4d} plus1={plus1} out={out_n} cons={cons} left={left} {mark}")

    # per-row packbits
    lines.append("\n== per-row packbits ==")
    for start in (23, 32, 115, 200, 256):
        for width, rows in ((128, 128), (128, 256), (64, 128), (256, 128), (160, 128)):
            ok, cons = _packbits_rows_impl(raw195[start:], width, rows)
            lines.append(
                f"  @{start} {width}x{rows} rows_ok={ok} cons={cons} "
                f"expect_out={width*rows} leftover={len(raw195)-start-cons}"
            )

    # uncompressed prefix + packbits
    lines.append("\n== prefix uncompressed + packbits rest, target 33144 ==")
    prefix_hits = []
    for pref in range(0, 400, 2):
        rest = raw195[pref:]
        dec = raw195[:pref] + packbits(rest) if pref else packbits(rest)
        # also: only the tail is packed, prefix is already in output as-is
        # output = prefix + packbits(file[prefix:])
        if len(dec) == 33144:
            prefix_hits.append(pref)
    lines.append(f"  exact prefix starts (step 2, 0..398): {prefix_hits}")

    # maybe pixels only: prefix stays, packbits of rest should equal 33144-prefix
    pix_hits = []
    for pref in (23, 24, 32, 115, 200, 280, 344, 376):
        if pref >= len(raw195):
            continue
        out = packbits(raw195[pref:])
        lines.append(f"  packbits after pref {pref}: out={len(out)} pref+out={pref+len(out)} vs 33144 d={pref+len(out)-33144:+d}")

    # try: file after 23 is [uncompressed clut of N bytes][packbits pixels]
    # clut run end
    runs195 = find_clut_runs(raw195, min_n=4)
    lines.append(f"\n  rsrc195 clut runs n>=4: {runs195}")
    for o, lo, hi, n in runs195:
        end = o + n * 8
        out = packbits(raw195[end:])
        lines.append(f"  packbits after clut {o}+{n}*8={end}: out={len(out)} vs {33144} d={len(out)-33144:+d}")

    # 0x90-style RLE (BinHex / MacPaint old)
    def rle90(src: bytes, marker: int = 0x90) -> bytes:
        out = bytearray()
        i = 0
        n = len(src)
        while i < n:
            b = src[i]
            i += 1
            if b == marker:
                if i >= n:
                    break
                cnt = src[i]
                i += 1
                if cnt == 0:
                    out.append(marker)
                else:
                    if not out:
                        continue
                    out.extend(bytes([out[-1]]) * (cnt - 1) if cnt else b"")
                    # classic: count is total repeats of previous
                    # already appended previous; add count-1 more. If we used cnt as extra:
            else:
                out.append(b)
        return bytes(out)

    def rle90_extra(src: bytes, marker: int = 0x90) -> bytes:
        """0x90 N means emit previous byte N extra times. 0x90 0x00 emits 0x90."""
        out = bytearray()
        i = 0
        n = len(src)
        while i < n:
            b = src[i]
            i += 1
            if b == marker:
                if i >= n:
                    break
                cnt = src[i]
                i += 1
                if cnt == 0:
                    out.append(marker)
                elif out:
                    out.extend(bytes([out[-1]]) * cnt)
            else:
                out.append(b)
        return bytes(out)

    lines.append("\n== 0x90 RLE ==")
    for start in (0, 23, 32):
        for fn, name in ((rle90, "rle90"), (rle90_extra, "rle90_extra")):
            out = fn(raw195[start:])
            lines.append(f"  {name} @{start} out={len(out)} d33144={len(out)-33144:+d}")

    # control-nibble: high nibble = type, low = count
    def rle_nibble(src: bytes) -> bytes:
        out = bytearray()
        i = 0
        n = len(src)
        while i < n:
            c = src[i]
            i += 1
            kind, cnt = c >> 4, (c & 0x0F) + 1
            if kind == 0:
                chunk = src[i : i + cnt]
                out.extend(chunk)
                i += len(chunk)
            elif kind == 0x8 or kind == 0xF:
                if i >= n:
                    break
                out.extend(bytes([src[i]]) * cnt)
                i += 1
            else:
                # treat as literal byte
                out.append(c)
        return bytes(out)

    lines.append("\n== nibble RLE @23 ==")
    out = rle_nibble(raw195[23:])
    lines.append(f"  out={len(out)} d={len(out)-33144:+d}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
