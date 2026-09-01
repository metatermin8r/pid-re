# -*- coding: utf-8 -*-
"""Round 10: settle .256 encoding — discriminator, per-section, raw, headers."""

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
from round9_shapes import header, packbits, rle_highbit, rle_unsigned_literal, section_offs  # noqa: E402
from shapes_pass1 import IDENT  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/round10_256.txt"
SHAPEDIR = ROOT / "reference/shapes"
ALEPH = ROOT / "reference/aleph_shapes"

VALID195 = frozenset(range(3, 17))


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


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
            elif out:
                out.extend(bytes([out[-1]]) * (cnt - 1))
        else:
            out.append(b)
    return bytes(out)


def rle90_extra(src: bytes, marker: int = 0x90) -> bytes:
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


def packbits_until(src: bytes, target: int) -> tuple[bytes, int]:
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


def highbit_until(src: bytes, target: int) -> tuple[bytes, int]:
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < target:
        ctrl = src[i]
        i += 1
        if ctrl & 0x80:
            count = (ctrl & 0x7F) + 1
            if i >= n:
                break
            take = min(count, target - len(out))
            out.extend(bytes([src[i]]) * take)
            i += 1
        else:
            count = ctrl + 1
            take = min(count, target - len(out), n - i)
            out.extend(src[i : i + take])
            i += min(count, n - i)
    return bytes(out[:target]), i


def unsigned_until(src: bytes, target: int) -> tuple[bytes, int]:
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < target:
        c = src[i]
        i += 1
        count = c + 1
        take = min(count, target - len(out), n - i)
        out.extend(src[i : i + take])
        i += min(count, n - i)
    return bytes(out[:target]), i


def rle90_until(src: bytes, target: int) -> tuple[bytes, int]:
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < target:
        b = src[i]
        i += 1
        if b == 0x90:
            if i >= n:
                break
            cnt = src[i]
            i += 1
            if cnt == 0:
                out.append(0x90)
            elif out:
                take = min(cnt - 1, target - len(out))
                if take > 0:
                    out.extend(bytes([out[-1]]) * take)
        else:
            out.append(b)
    return bytes(out[:target]), i


UNTIL = {
    "packbits": packbits_until,
    "highbit_run": highbit_until,
    "rle90": rle90_until,
    "unsigned_literal": unsigned_until,
}


def compact_gray(data: bytes) -> list[tuple[int, int, int] | None]:
    pal: list[tuple[int, int, int] | None] = [None] * 256
    p = 29
    while p + 5 <= min(len(data), 200):
        idx = struct.unpack_from(">H", data, p)[0]
        kind = data[p + 2]
        val = data[p + 3]
        if idx > 40 or kind not in (3, 4):
            break
        pal[idx] = (val, val, val)
        p += 5
    return pal


def mac_clut_own(data: bytes) -> list[tuple[int, int, int] | None]:
    """Own 8-byte Mac clut runs (high==low per channel) plus compact gray."""
    pal = compact_gray(data)
    n = len(data)
    i = 23
    while i + 8 <= min(n, 800):
        idx, r, g, b = struct.unpack_from(">HHHH", data, i)
        if idx <= 255 and (r >> 8) == (r & 0xFF) and (g >> 8) == (g & 0xFF) and (b >> 8) == (b & 0xFF):
            # extend run
            pos = i
            prev = idx - 1
            while pos + 8 <= n:
                ix, rr, gg, bb = struct.unpack_from(">HHHH", data, pos)
                if ix > 255 or ix != prev + 1:
                    break
                if (rr >> 8) != (rr & 0xFF):
                    break
                pal[ix] = (rr >> 8, gg >> 8, bb >> 8)
                prev = ix
                pos += 8
            i = pos
        else:
            i += 1
    return pal


def render128(pixels: bytes, pal: list[tuple[int, int, int] | None], path: Path, pad: bytes | None = None) -> None:
    buf = pixels
    if pad is not None:
        buf = pixels + pad
    img = Image.new("RGB", (128, 128), (255, 0, 255))
    pix = img.load()
    for i, idx in enumerate(buf[:16384]):
        rgb = pal[idx] if idx < 256 else None
        pix[i % 128, i // 128] = rgb if rgb is not None else (idx, idx, idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def hist_block(data: bytes) -> tuple[list[int], int, int]:
    c = Counter(data)
    counts = [c.get(i, 0) for i in range(256)]
    in_n = sum(c.get(i, 0) for i in VALID195)
    return counts, in_n, len(data)


def oor_list(data: bytes, base: int, valid: frozenset[int], limit: int = 200) -> list[tuple[int, int, int]]:
    """(abs_offset, value, gap_since_prev_oor)."""
    out = []
    prev = base - 1
    for i, b in enumerate(data):
        if b not in valid:
            off = base + i
            gap = off - prev
            out.append((off, b, gap))
            prev = off
            if len(out) >= limit:
                break
    return out


def main() -> None:
    shapes = load_all_256()
    lines: list[str] = []
    d195 = shapes[195]
    d196 = shapes[196]
    d198 = shapes[198]

    # ------------------------------------------------------------------ T1
    pix195 = d195[258:]
    counts195, in195, n195 = hist_block(pix195)
    lines.append("== T1(a) rsrc 195 histogram offset 258..end ==")
    lines.append(f"  packed={len(d195)} slice={n195}")
    for i in range(256):
        if counts195[i]:
            mark = " IN" if i in VALID195 else " OOR"
            lines.append(f"  {i:3d} {i:02x} {counts195[i]:6d}{mark}")
    frac195 = in195 / n195 if n195 else 0
    lines.append(f"\n== T1(b) 195 in 3-16: {in195}/{n195} = {frac195:.4f} ({100*frac195:.2f}%) ==")
    lines.append(f"  OOR bytes: {n195 - in195}  per_KB={1000*(n195-in195)/n195:.2f}")

    oors195 = oor_list(pix195, 258, VALID195, 200)
    lines.append(f"\n== T1(c) first {len(oors195)} OOR bytes 195 ==")
    gaps = [g for _, _, g in oors195]
    for off, val, gap in oors195[:80]:
        lines.append(f"  off={off:5d} val={val:3d}/{val:02x} gap={gap}")
    if len(oors195) > 80:
        lines.append(f"  ... {len(oors195)-80} more")
    lines.append(f"\n== T1(d) gap stats 195 (first {len(gaps)} OOR) ==")
    if gaps:
        cg = Counter(gaps)
        lines.append(f"  min={min(gaps)} max={max(gaps)} median={sorted(gaps)[len(gaps)//2]}")
        lines.append(f"  mean={sum(gaps)/len(gaps):.2f}")
        lines.append(f"  most common gaps: {cg.most_common(15)}")
        small = sum(1 for g in gaps if g <= 8)
        lines.append(f"  gaps<=8: {small}/{len(gaps)} = {small/len(gaps):.3f}  (clustered=RLE-like)")
        # uniformity: many identical gaps?
        top1 = cg.most_common(1)[0]
        lines.append(f"  top gap {top1[0]} appears {top1[1]} times ({top1[1]/len(gaps):.3f})")

    pix198 = d198[258:]
    counts198, in198, n198 = hist_block(pix198)
    frac198 = in198 / n198 if n198 else 0
    oor195_perkb = 1000 * (n195 - in195) / n195
    oor198_perkb = 1000 * (n198 - in198) / n198
    lines.append(f"\n== T1(e) rsrc 198 histogram 258..end packed={len(d198)} slice={n198} ==")
    for i in range(256):
        if counts198[i]:
            mark = " IN" if i in VALID195 else " OOR"
            lines.append(f"  {i:3d} {i:02x} {counts198[i]:6d}{mark}")
    lines.append(f"  198 in 3-16: {in198}/{n198} = {frac198:.4f} ({100*frac198:.2f}%)")
    lines.append(f"  198 OOR={n198-in198} per_KB={oor198_perkb:.2f}")
    lines.append(f"  195 OOR per_KB={oor195_perkb:.2f}")
    lines.append(
        f"  198/195 OOR-density ratio={oor198_perkb/oor195_perkb:.3f}"
        if oor195_perkb
        else "  195 has zero OOR"
    )
    lines.append(
        "  MORE OOR/KB in 198 than 195? "
        f"{oor198_perkb > oor195_perkb}  "
        "(if yes: OOR bytes are compression controls)"
    )

    # also 196 for context
    pix196 = d196[258:]
    _, in196, n196 = hist_block(pix196)
    lines.append(
        f"  196 packed={len(d196)} in 3-16={in196}/{n196}={in196/n196:.4f} "
        f"OOR/KB={1000*(n196-in196)/n196:.2f}"
    )

    lines.append("\n== T1(f) rsrc 195 offsets 240-500 hex, OOR marked with * ==")
    chunk = d195[240:501]
    for off in range(240, 501, 16):
        sl = d195[off : min(off + 16, 501)]
        hexparts = []
        for b in sl:
            tag = f"{b:02x}"
            if off >= 258 and b not in VALID195:
                tag = f"{b:02x}*"
            hexparts.append(tag)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in sl)
        lines.append(f"  {off:04x}  {' '.join(hexparts):<64s} |{ascii_}|")

    # ------------------------------------------------------------------ T2
    u0, u4, b6 = header(d195)
    offs = section_offs(d195)
    # decompressed section starts: 0, 280, 344, 376, 32768, 33144
    dec_bounds = [0] + offs + [u0]
    sizes = [dec_bounds[i + 1] - dec_bounds[i] for i in range(len(dec_bounds) - 1)]
    lines.append(f"\n== T2(a) decompressed bounds {dec_bounds} sizes={sizes} ==")
    lines.append("  packed starts tried: 23 (after file header+table), 258 (pixel guess)")

    lines.append("\n== T2(b) per-section, restart decoder at each bound ==")
    for start_name, pstart in (("packed@23", 23), ("packed@258", 258)):
        for sname, fn in UNTIL.items():
            pos = pstart
            parts = []
            ok_all = True
            for si, exp in enumerate(sizes):
                if pos >= len(d195):
                    parts.append(f"s{si}:EOF")
                    ok_all = False
                    continue
                out, cons = fn(d195[pos:], exp)
                parts.append(f"s{si}:{len(out)}/{exp} cons={cons}{' EXACT' if len(out)==exp else ''}")
                if len(out) != exp:
                    ok_all = False
                pos += cons
            lines.append(
                f"  {sname:12s} {sname and ''}{sname} wait {sname} {fn.__name__ if False else sname:18s} "
                f"end_packed={pos} leftover={len(d195)-pos} all_exact={ok_all}"
            )
            # fix the messy line — rewrite cleanly
            lines[-1] = (
                f"  {start_name:12s} {sname:18s} end_pk={pos} left={len(d195)-pos} "
                f"all_exact={ok_all}"
            )
            lines.append("    " + " | ".join(parts))

    lines.append("\n== T2(c) final 32768 as two 16384 runs ==")
    for start_name, pstart in (("packed@23", 23), ("packed@258", 258)):
        # skip first 376 decompressed bytes first, then two 16384
        for sname, fn in UNTIL.items():
            pos = pstart
            # consume header 376
            h, c0 = fn(d195[pos:], 376)
            pos1 = pos + c0
            a, ca = fn(d195[pos1:], 16384)
            pos2 = pos1 + ca
            b, cb = fn(d195[pos2:], 16384)
            pos3 = pos2 + cb
            lines.append(
                f"  {start_name} {sname:18s} hdr={len(h)}/376 cons={c0} | "
                f"A={len(a)}/16384 cons={ca} | B={len(b)}/16384 cons={cb} | "
                f"end={pos3} left={len(d195)-pos3} "
                f"{'EXACT-BOTH' if len(a)==16384 and len(b)==16384 else ''}"
            )

    # also: no header skip, two 16384 from 258
    lines.append("  -- two 16384 directly from 258 (no 376 skip) --")
    for sname, fn in UNTIL.items():
        a, ca = fn(d195[258:], 16384)
        b, cb = fn(d195[258 + ca :], 16384)
        lines.append(
            f"  @258 {sname:18s} A={len(a)}/{16384} cons={ca} B={len(b)}/{16384} cons={cb} "
            f"end={258+ca+cb} left={len(d195)-258-ca-cb} "
            f"{'EXACT-BOTH' if len(a)==16384 and len(b)==16384 else ''}"
        )

    # ------------------------------------------------------------------ T3
    pal195 = mac_clut_own(d195)
    pal_gray = compact_gray(d195)
    # prefer own 8-byte if present else gray; user said own colour table 3-16
    # compact gray IS the own table for pixels (3-16). Use compact for render.
    used_pal = pal_gray
    filled = [i for i in range(256) if used_pal[i] is not None]
    lines.append(f"\n== T3 own palette 195 filled={filled} ==")

    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    a = d195[258 : 258 + 16384]
    render128(a, used_pal, SHAPEDIR / "195_raw_a.png")
    lines.append(f"  T3(a) wrote 195_raw_a.png bytes={len(a)}")

    avail_b = len(d195) - 16642
    lines.append(f"  T3(b) 31628-16642 = {avail_b} (expect 14986)")
    braw = d195[16642:]
    render128(braw, used_pal, SHAPEDIR / "195_raw_b.png", pad=b"\x00" * max(0, 16384 - len(braw)))
    lines.append(f"  wrote 195_raw_b.png available={len(braw)} padded={max(0,16384-len(braw))}")

    # cleanliness: fraction of A/B in 3-16
    in_a = sum(1 for x in a if x in VALID195)
    in_b = sum(1 for x in braw if x in VALID195)
    lines.append(f"  A in-palette {in_a}/{len(a)}={in_a/len(a):.4f}")
    lines.append(f"  B in-palette {in_b}/{len(braw)}={in_b/len(braw):.4f}")
    # sliding window of OOR density on B to see degradation
    win = 256
    dens = []
    for i in range(0, len(braw) - win + 1, win):
        sl = braw[i : i + win]
        oor = sum(1 for x in sl if x not in VALID195)
        dens.append((16642 + i, oor))
    lines.append(f"  B OOR-per-256 window: {dens[:20]} ... last={dens[-4:] if dens else None}")

    lines.append("\n== T3(d) 196 and 198 raw first/second 16384 from 258 ==")
    for rid, d in ((196, d196), (198, d198)):
        pal = compact_gray(d)
        # if compact empty, try mac clut
        if all(p is None for p in pal):
            pal = mac_clut_own(d)
        aa = d[258 : 258 + 16384]
        avail = max(0, len(d) - 16642)
        bb = d[16642:] if 16642 < len(d) else b""
        render128(aa, pal, SHAPEDIR / f"{rid}_raw_a.png")
        if bb:
            render128(bb, pal, SHAPEDIR / f"{rid}_raw_b.png", pad=b"\x00" * max(0, 16384 - len(bb)))
        ina = sum(1 for x in aa if 3 <= x <= 16) / len(aa) if aa else 0
        inb = sum(1 for x in bb if 3 <= x <= 16) / len(bb) if bb else 0
        lines.append(
            f"  {rid} packed={len(d)} A_len={len(aa)} A_in3-16={ina:.4f} "
            f"B_avail={avail} B_in3-16={inb:.4f}"
        )

    # ------------------------------------------------------------------ T4
    lines.append("\n== T4 188-byte header hunt ==")
    # dump packed 23, 211, and last 376
    for label, off in (("packed@23", 23), ("packed@211", 211), ("packed@end-376", len(d195) - 376), ("packed@end-188", len(d195) - 188)):
        if off < 0 or off + 16 > len(d195):
            continue
        sl = d195[off : off + 188]
        lines.append(f"\n--- 195 {label} off={off} len={len(sl)} ---")
        lines.append(hexdump_mac_roman(sl[:188] if len(sl) >= 188 else sl))
        u16s = [struct.unpack_from(">H", sl, i)[0] for i in range(0, min(len(sl) - 1, 188), 2)]
        hits = [(i * 2, v) for i, v in enumerate(u16s) if v in (128, 0x0080, 16384, 188, 33144, 2, 8, 256)]
        lines.append(f"  interesting u16be: {hits}")

    # compare 23..210 and 211..398 across 195-202
    lines.append("\n== T4(c) packed[23:211] (188 bytes) across 195-202 ==")
    blobs = {rid: shapes[rid][23:211] for rid in range(195, 203) if rid in shapes}
    ref = blobs[195]
    ident_bytes = [i for i in range(188) if all(blobs[r][i] == ref[i] for r in blobs)]
    vary_bytes = [i for i in range(188) if i not in ident_bytes]
    lines.append(f"  identical offsets ({len(ident_bytes)}): {ident_bytes[:40]}{'...' if len(ident_bytes)>40 else ''}")
    lines.append(f"  varying offsets ({len(vary_bytes)}): {vary_bytes[:60]}")
    # per-resource u16 table at 23
    lines.append("  first 24 u16be @23 per resource:")
    for rid in range(195, 203):
        d = shapes[rid]
        u16s = [struct.unpack_from(">H", d, 23 + i * 2)[0] for i in range(24)]
        lines.append(f"    {rid} {u16s}")

    lines.append("\n== T4(c) last 376 packed bytes across 195-202 ==")
    tails = {rid: shapes[rid][-376:] for rid in range(195, 203)}
    tref = tails[195]
    same = [i for i in range(376) if all(tails[r][i] == tref[i] for r in tails)]
    lines.append(f"  identical in last 376: {len(same)} bytes")
    lines.append(f"  195 last16={d195[-16:].hex(' ')}")
    lines.append(f"  198 last16={d198[-16:].hex(' ')}")
    lines.append(f"  196 last16={d196[-16:].hex(' ')}")

    # u16==128 etc in first 400 and last 400 of each
    lines.append("\n== T4(d) u16be in {128, 0x80, 16384, 188} in first 400 / last 400 ==")
    want = {128, 16384, 188}
    for rid in range(195, 203):
        d = shapes[rid]
        hits_f = []
        hits_t = []
        for i in range(0, min(400, len(d) - 1), 2):
            v = struct.unpack_from(">H", d, i)[0]
            if v in want:
                hits_f.append((i, v))
        for i in range(max(0, len(d) - 400), len(d) - 1, 2):
            v = struct.unpack_from(">H", d, i)[0]
            if v in want:
                hits_t.append((i, v))
        lines.append(f"  {rid} first400={hits_f} last400={hits_t[:12]}")

    # ------------------------------------------------------------------ T6 (before T5 so we know encoding)
    lines.append("\n== T6 failed section-table resources ==")
    for rid in (161, 162, 167, 189):
        d = shapes[rid]
        u0r, u4r, b6r = header(d)
        raw_offs = [struct.unpack_from(">I", d, 7 + i * 4)[0] for i in range(6)]
        lines.append(
            f"  {rid} packed={len(d)} u0={u0r} u4={u4r:#06x} b6={b6r} "
            f"ident={IDENT.get(rid,'?')}"
        )
        lines.append(f"    first64={d[:64].hex(' ')}")
        lines.append(f"    u32@7 first6={raw_offs}")
        # try 2 or 3 entry tables
        for nent in (2, 3, 4):
            oo = raw_offs[:nent]
            ok = all(oo[i] < oo[i + 1] for i in range(nent - 1)) and oo[-1] < u0r
            lines.append(f"    n={nent} offs={oo} ascending_lt_u0={ok}")

    # ------------------------------------------------------------------ T5 walls
    d192 = shapes[192]
    pal192 = mac_clut_own(d192)
    filled192 = [i for i in range(256) if pal192[i] is not None]
    u0_192, _, b6_192 = header(d192)
    o192 = section_offs(d192)
    lines.append(f"\n== T5 rsrc 192 packed={len(d192)} u0={u0_192} b6={b6_192} offs={o192} ==")
    lines.append(f"  own pal filled={filled192[:40]} n={len(filled192)}")

    # own valid set = filled indices
    valid192 = frozenset(filled192) if filled192 else frozenset(range(256))
    _, in192, n192s = hist_block(d192[258:])  # not using VALID195
    in_own = sum(1 for b in d192[23:] if b in valid192)
    lines.append(f"  bytes@23+ in own pal {in_own}/{len(d192)-23}={(in_own/(len(d192)-23)):.4f}")

    # try: raw 128x128 tiles from a guessed start
    # and packbits-until 16384 repeated b6 times
    WALLDIR = SHAPEDIR / "192"
    WALLDIR.mkdir(parents=True, exist_ok=True)
    # raw slices
    for i in range(min(6, b6_192)):
        st = 258 + i * 16384
        if st >= len(d192):
            break
        sl = d192[st : st + 16384]
        render128(sl, pal192, WALLDIR / f"raw_{i}.png", pad=b"\x00" * max(0, 16384 - len(sl)))
    lines.append("  wrote raw 128x128 guesses from 258")

    # packbits sequential 16384 from 23 and from after clut-ish
    pos = 23
    n_exact = 0
    for i in range(b6_192):
        out, cons = packbits_until(d192[pos:], 16384)
        if len(out) == 16384:
            n_exact += 1
            render128(out, pal192, WALLDIR / f"pb23_{i}.png")
        pos += cons
    lines.append(f"  packbits 16384-runs from 23: exact={n_exact}/{b6_192} end={pos} left={len(d192)-pos}")

    pos = 258
    n_exact = 0
    for i in range(b6_192):
        out, cons = packbits_until(d192[pos:], 16384)
        if len(out) == 16384:
            n_exact += 1
            render128(out, pal192, WALLDIR / f"pb258_{i}.png")
        pos += cons
    lines.append(f"  packbits 16384-runs from 258: exact={n_exact}/{b6_192} end={pos}")

    pos = 23
    n_exact = 0
    for i in range(b6_192):
        out, cons = highbit_until(d192[pos:], 16384)
        if len(out) == 16384:
            n_exact += 1
            render128(out, pal192, WALLDIR / f"hb23_{i}.png")
        pos += cons
    lines.append(f"  highbit 16384-runs from 23: exact={n_exact}/{b6_192} end={pos} left={len(d192)-pos}")

    # compare histograms vs AOPID c17-c21
    def img_hist(path: Path) -> Counter:
        im = Image.open(path).convert("L")
        return Counter(im.getdata())

    def hist_shape(c: Counter) -> list[int]:
        # 16-bin brightness histogram
        bins = [0] * 16
        for v, n in c.items():
            bins[min(15, v // 16)] += n
        s = sum(bins) or 1
        return [int(1000 * x / s) for x in bins]

    def l1(a: list[int], b: list[int]) -> int:
        return sum(abs(x - y) for x, y in zip(a, b))

    aleph_hists = []
    if ALEPH.exists():
        for p in sorted(ALEPH.glob("c1[7-9]/*.png")) + sorted(ALEPH.glob("c2[01]/*.png")):
            try:
                aleph_hists.append((str(p.relative_to(ROOT)), hist_shape(img_hist(p))))
            except OSError:
                continue
    lines.append(f"  AOPID wall pngs loaded={len(aleph_hists)}")
    our_pngs = list(WALLDIR.glob("*.png"))
    if aleph_hists and our_pngs:
        lines.append("  best L1 (16-bin luma) per our frame:")
        for op in sorted(our_pngs)[:18]:
            oh = hist_shape(img_hist(op))
            best = min(aleph_hists, key=lambda t: l1(oh, t[1]))
            score = l1(oh, best[1])
            lines.append(f"    {op.name} best={best[0]} L1={score} (0=identical bins)")

    dest = OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:120]))
    print(f"\n... wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
