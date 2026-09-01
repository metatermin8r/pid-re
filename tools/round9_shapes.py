# -*- coding: utf-8 -*-
"""Round 9: .256 partial palettes, 4-section directory, RLE decompress."""

from __future__ import annotations

import io
import struct
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from shapes_pass1 import IDENT  # noqa: E402

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/round9_shapes.txt"
PALDIR = ROOT / "reference/palettes"
SHAPEDIR = ROOT / "reference/shapes"

ROLES = {
    "items": [128],
    "monsters": list(range(129, 143)),
    "weapons": list(range(148, 153)),
    "props": list(range(153, 168)),
    "cutscene_ui": list(range(187, 192)),
    "walls": list(range(192, 195)),
    "floor_ceiling": list(range(195, 203)),
}


def role_of(rid: int) -> str:
    for name, ids in ROLES.items():
        if rid in ids:
            return name
    return "other"


def load_all_256() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b".256"][rid].data_raw for rid in rf[b".256"]}


def header(data: bytes) -> tuple[int, int, int]:
    u0 = struct.unpack_from(">I", data, 0)[0]
    u4 = struct.unpack_from(">H", data, 4)[0]
    return u0, u4, data[6]


def section_offs(data: bytes) -> list[int]:
    return [struct.unpack_from(">I", data, 7 + i * 4)[0] for i in range(4)]


def plausible_rgb(r: int, g: int, b: int) -> bool:
    """16-bit Mac RGB: channels often have matching high/low bytes (0xA5A5)."""
    # Accept any 16-bit triple; reject only all-zero with index later.
    # Tight filter: each channel's high and low bytes are equal, OR high byte
    # is the colour and low is 0 / high. Both appear in Mac cluts.
    return True


def scan_clut_run(data: bytes, start: int = 23) -> tuple[int, list[tuple[int, int, int, int]]]:
    """Longest ascending 8-byte clut run starting at or after `start`."""
    best_off = -1
    best: list[tuple[int, int, int, int]] = []
    n = len(data)
    for off in range(start, min(n - 8, start + 64)):
        if (n - off) < 8:
            break
        entries: list[tuple[int, int, int, int]] = []
        pos = off
        prev = -1
        while pos + 8 <= n:
            idx, r, g, b = struct.unpack_from(">HHHH", data, pos)
            if idx > 255:
                break
            if prev >= 0 and idx != prev + 1:
                break
            if prev < 0 and idx > 255:
                break
            entries.append((idx, r, g, b))
            prev = idx
            pos += 8
        if len(entries) > len(best):
            best = entries
            best_off = off
    return best_off, best


def packbits(src: bytes) -> bytes:
    """Apple PackBits. n in 0..127: copy n+1; n in 129..255: repeat 257-n; 128: no-op."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        ctrl = src[i]
        i += 1
        if ctrl <= 127:
            count = ctrl + 1
            if i + count > n:
                out.extend(src[i:])
                break
            out.extend(src[i : i + count])
            i += count
        elif ctrl == 128:
            continue
        else:
            count = 257 - ctrl
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
    return bytes(out)


def rle_unsigned_literal(src: bytes) -> bytes:
    """count C: copy C+1 literals. No repeat. Degenerate."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        i += 1
        count = c + 1
        if i + count > n:
            out.extend(src[i:])
            break
        out.extend(src[i : i + count])
        i += count
    return bytes(out)


def rle_count_then_byte(src: bytes) -> bytes:
    """pairs (count, byte): emit byte `count` times. count==0 skip."""
    out = bytearray()
    i = 0
    n = len(src)
    while i + 1 < n:
        count = src[i]
        val = src[i + 1]
        i += 2
        if count:
            out.extend(bytes([val]) * count)
    return bytes(out)


def rle_highbit(src: bytes) -> bytes:
    """high bit set: repeat next byte (ctrl&0x7F)+1 times; else copy ctrl+1 literals."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        ctrl = src[i]
        i += 1
        if ctrl & 0x80:
            count = (ctrl & 0x7F) + 1
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
        else:
            count = ctrl + 1
            if i + count > n:
                out.extend(src[i:])
                break
            out.extend(src[i : i + count])
            i += count
    return bytes(out)


def rle_highbit_inv(src: bytes) -> bytes:
    """high bit set: copy (ctrl&0x7F)+1 literals; else repeat next (ctrl+1) times."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        ctrl = src[i]
        i += 1
        if ctrl & 0x80:
            count = (ctrl & 0x7F) + 1
            if i + count > n:
                out.extend(src[i:])
                break
            out.extend(src[i : i + count])
            i += count
        else:
            count = ctrl + 1
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
    return bytes(out)


def rle_tiff_packbits_alt(src: bytes) -> bytes:
    """PackBits but 0x80 means repeat 128 (some TIFF variants)."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        ctrl = src[i]
        i += 1
        if ctrl < 128:
            count = ctrl + 1
            if i + count > n:
                out.extend(src[i:])
                break
            out.extend(src[i : i + count])
            i += count
        else:
            count = 257 - ctrl if ctrl > 128 else 128
            if i >= n:
                break
            out.extend(bytes([src[i]]) * count)
            i += 1
    return bytes(out)


SCHEMES = [
    ("packbits", packbits),
    ("packbits_80rep", rle_tiff_packbits_alt),
    ("unsigned_literal", rle_unsigned_literal),
    ("count_then_byte", rle_count_then_byte),
    ("highbit_run", rle_highbit),
    ("highbit_lit", rle_highbit_inv),
]


def try_scheme(fn, src: bytes, target: int) -> tuple[int, int]:
    """Return (output_len, leftover_input). Stop early if output far exceeds target."""
    # Run fully; these files are small.
    out = fn(src)
    return len(out), 0


def rgb8(r: int, g: int, b: int) -> tuple[int, int, int]:
    return (r >> 8, g >> 8, b >> 8)


def write_master_palette(
    slots: list[tuple[int, int, int] | None],
    contrib: dict[int, list[int]],
) -> None:
    PALDIR.mkdir(parents=True, exist_ok=True)
    cell = 28
    img = Image.new("RGB", (16 * cell, 16 * cell), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None
    act = bytearray(256 * 3)
    for i in range(256):
        x = (i % 16) * cell
        y = (i // 16) * cell
        rgb = slots[i]
        if rgb is None:
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(40, 40, 40), outline=(80, 80, 80))
            label = f"{i:02X}?"
            fill = (180, 180, 180)
        else:
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=rgb, outline=(0, 0, 0))
            act[i * 3 : i * 3 + 3] = bytes(rgb)
            label = f"{i:02X}"
            lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
            fill = (0, 0, 0) if lum > 128 else (255, 255, 255)
        if font:
            draw.text((x + 2, y + 2), label, fill=fill, font=font)
    img.save(PALDIR / "master_256.png")
    (PALDIR / "master_256.act").write_bytes(bytes(act))


def render_floor(pixels: bytes, palette: list[tuple[int, int, int] | None], path: Path) -> None:
    img = Image.new("RGB", (128, 128), (255, 0, 255))
    pix = img.load()
    for i, idx in enumerate(pixels[: 128 * 128]):
        rgb = palette[idx]
        pix[i % 128, i // 128] = rgb if rgb is not None else (idx, idx, idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def hex_block(data: bytes, n: int = 256) -> str:
    return hexdump_mac_roman(data[:n])


def main() -> None:
    shapes = load_all_256()
    ids = sorted(shapes)
    lines: list[str] = []

    lines.append(f"== loaded {len(ids)} .256 resources: {ids} ==")

    # ------------------------------------------------------------------ Task 1
    lines.append("\n== T1(a) clut runs from offset 23 ==")
    clut_by_rsrc: dict[int, tuple[int, list[tuple[int, int, int, int]]]] = {}
    for rid in ids:
        off, entries = scan_clut_run(shapes[rid], 23)
        clut_by_rsrc[rid] = (off, entries)
        if not entries:
            lines.append(f"  {rid:3d} NO RUN")
            continue
        lo = entries[0][0]
        hi = entries[-1][0]
        lines.append(
            f"  {rid:3d} off={off:4d} idx={lo:3d}..{hi:3d} n={len(entries):3d} "
            f"b6={shapes[rid][6]:3d} {IDENT.get(rid, '')}"
        )

    slots: list[tuple[int, int, int] | None] = [None] * 256
    slot_src: list[list[int]] = [[] for _ in range(256)]
    conflicts: list[str] = []
    raw16: list[tuple[int, int, int] | None] = [None] * 256
    for rid in ids:
        off, entries = clut_by_rsrc[rid]
        for idx, r, g, b in entries:
            rgb = rgb8(r, g, b)
            raw = (r, g, b)
            if raw16[idx] is None:
                raw16[idx] = raw
                slots[idx] = rgb
                slot_src[idx].append(rid)
            else:
                if raw16[idx] != raw:
                    conflicts.append(
                        f"  CONFLICT idx={idx} rsrc {slot_src[idx][0]} {raw16[idx]} "
                        f"vs rsrc {rid} {raw}"
                    )
                if rid not in slot_src[idx]:
                    slot_src[idx].append(rid)

    filled = [i for i in range(256) if slots[i] is not None]
    empty = [i for i in range(256) if slots[i] is None]
    lines.append("\n== T1(b) union 256 ==")
    lines.append(f"  filled={len(filled)} empty={len(empty)} empty_slots={empty}")
    lines.append(f"  conflicts={len(conflicts)}")
    lines.extend(conflicts[:40])
    if len(conflicts) > 40:
        lines.append(f"  ... {len(conflicts) - 40} more conflicts")

    # contributor ranges
    lines.append("\n== T1(c) contributor ranges ==")
    for rid in ids:
        _, entries = clut_by_rsrc[rid]
        if not entries:
            continue
        lo, hi = entries[0][0], entries[-1][0]
        lines.append(f"  {rid:3d} {lo:3d}..{hi:3d} ({len(entries)}) first_src_only="
                     f"{sum(1 for i in range(lo, hi + 1) if slot_src[i][:1] == [rid])}")
    r128 = clut_by_rsrc.get(128, (-1, []))[1]
    if r128:
        lines.append(
            f"  rsrc 128 covers {r128[0][0]}..{r128[-1][0]} n={len(r128)} "
            f"(Petrich 'overall color table': {'YES base-ish' if r128[0][0] <= 1 else 'NOT from 0'})"
        )

    PALDIR.mkdir(parents=True, exist_ok=True)
    write_master_palette(slots, {i: slot_src[i] for i in range(256)})
    lines.append(f"  wrote {PALDIR / 'master_256.png'} and master_256.act")

    lines.append("\n== T1(d) index count vs byte 6 ==")
    for rid in (128, 148, 153, 192, 195, 196, 197, 198):
        n = len(clut_by_rsrc[rid][1])
        b6 = shapes[rid][6]
        lines.append(f"  {rid} clut_n={n} b6={b6} equal={n == b6}")
    all_eq = all(len(clut_by_rsrc[rid][1]) == shapes[rid][6] for rid in ids)
    lines.append(f"  ALL clut_n == b6? {all_eq}  -> byte6 is {'colour count' if all_eq else 'NOT colour count (frame count inferred)'}")

    # ------------------------------------------------------------------ Task 2
    lines.append("\n== T2(a) four u32be @7 vs decompressed size ==")
    fails = []
    section_rows: list[tuple[int, int, list[int], list[int]]] = []
    for rid in ids:
        d = shapes[rid]
        u0, u4, b6 = header(d)
        offs = section_offs(d)
        shifted = [v >> 8 for v in offs]
        # report BOTH raw and >>8; user says values ARE 1256,... which is raw@7
        ok = all(offs[i] < offs[i + 1] for i in range(3)) and offs[3] < u0
        ok_sh = all(shifted[i] < shifted[i + 1] for i in range(3)) and shifted[3] < u0
        if not ok:
            fails.append((rid, offs, u0, ok, ok_sh, shifted))
        sizes = [offs[0] - 0, offs[1] - offs[0], offs[2] - offs[1], offs[3] - offs[2], u0 - offs[3]]
        section_rows.append((rid, u0, offs, sizes))
        mark = "OK" if ok else "FAIL"
        lines.append(
            f"  {rid:3d} {mark} u0={u0:7d} offs={offs} sizes={sizes} "
            f"b6={b6} packed={len(d)}"
        )
    lines.append(f"  FAIL count={len(fails)}")
    for row in fails:
        lines.append(f"  FAIL {row}")

    lines.append("\n== T2(b) section sizes by role ==")
    by_role: dict[str, list[tuple[int, list[int]]]] = defaultdict(list)
    for rid, u0, offs, sizes in section_rows:
        by_role[role_of(rid)].append((rid, sizes))
    for role, rows in by_role.items():
        lines.append(f"  -- {role} --")
        for rid, sizes in rows:
            lines.append(f"     {rid:3d} {sizes}")
        # unique size tuples
        uniq = sorted({tuple(s) for _, s in rows})
        lines.append(f"     unique patterns ({len(uniq)}): {uniq[:8]}")

    lines.append("\n== T2(c) 195-202 vs 2*(16384+188)=33144 ==")
    model_points = [0, 188, 16384, 16572, 16760, 32768, 32956, 33144]
    for rid in range(195, 203):
        if rid not in shapes:
            continue
        d = shapes[rid]
        u0, _, b6 = header(d)
        offs = section_offs(d)
        hits = []
        for o in offs:
            hits.append((o, o in model_points))
        lines.append(
            f"  {rid} u0={u0} b6={b6} offs={offs} on_model={hits} "
            f"u0-offs3={u0 - offs[3]} 16572-offs? {[16572 - o for o in offs]}"
        )

    # ------------------------------------------------------------------ Task 3
    d195 = shapes[195]
    u0_195, u4_195, b6_195 = header(d195)
    clut_off_195, clut_195 = clut_by_rsrc[195]
    pixel_off = clut_off_195 + 8 * len(clut_195) if clut_195 else 23
    lines.append("\n== T3(a) rsrc 195 pixel start ==")
    lines.append(
        f"  packed={len(d195)} u0={u0_195} u4={u4_195:#06x} b6={b6_195} "
        f"clut_off={clut_off_195} clut_n={len(clut_195)} pixel_off={pixel_off}"
    )
    lines.append(f"  first16={d195[:16].hex(' ')}")
    lines.append(f"  offs={section_offs(d195)}")
    lines.append("\n== T3(b) 256 bytes from pixel_off ==")
    lines.append(hex_block(d195[pixel_off:], 256))

    # also dump a few bytes before in case clut scan ate pixels
    lines.append("\n== T3(b) also from offset 23 (in case clut is empty/short) ==")
    lines.append(hex_block(d195[23:], 128))

    targets = [u0_195, 16572, 16384, 33144, 2 * 16384]
    lines.append("\n== T3(c/d) decompress trials from pixel_off ==")
    results: dict[str, dict[int, int]] = {}
    for name, fn in SCHEMES:
        out = fn(d195[pixel_off:])
        results[name] = {195: len(out)}
        flags = []
        for t in targets:
            if len(out) == t:
                flags.append(f"EXACT {t}")
        near = min(targets, key=lambda t: abs(len(out) - t))
        lines.append(
            f"  {name:18s} out={len(out):7d} vs 33144 d={len(out)-33144:+d} "
            f"nearest={near} d={len(out)-near:+d} {' '.join(flags)}"
        )

    # try a few extra start offsets around the clut end, in case we missed a
    # small header after the clut
    lines.append("\n== T3 extra: packbits from nearby starts ==")
    for start in sorted(set([pixel_off, pixel_off - 8, pixel_off + 8, 23, 7, 0,
                             clut_off_195, clut_off_195 + 8,
                             pixel_off + 2, pixel_off + 4, pixel_off + 16])):
        if start < 0 or start >= len(d195):
            continue
        out = packbits(d195[start:])
        mark = ""
        if len(out) == 33144:
            mark = " *** EXACT 33144"
        elif len(out) == 16572:
            mark = " *** EXACT 16572"
        elif abs(len(out) - 33144) < 64:
            mark = " ~near 33144"
        lines.append(f"  packbits @{start:5d} out={len(out):7d}{mark}")

    # If nothing hit, try treating the WHOLE resource after header as packed,
    # and also try decompressing only a tail sized so that literal-mostly data
    # would expand to 33144.
    lines.append("\n== T3 extra: packbits whole-after-header (off 23) leftover check ==")
    # Walk packbits and report when output crosses interesting sizes
    src = d195[pixel_off:]
    out = bytearray()
    i = 0
    crossings = []
    interesting = {16384, 16572, 16760, 32768, 32956, 33144, 33145, 33143}
    while i < len(src):
        ctrl = src[i]
        i += 1
        before = len(out)
        if ctrl <= 127:
            count = ctrl + 1
            chunk = src[i : i + count]
            out.extend(chunk)
            i += len(chunk)
        elif ctrl == 128:
            pass
        else:
            count = 257 - ctrl
            if i < len(src):
                out.extend(bytes([src[i]]) * count)
                i += 1
        after = len(out)
        for t in interesting:
            if before < t <= after:
                crossings.append((t, i, after, len(src) - i))
    lines.append(f"  packbits consumed={i}/{len(src)} out={len(out)} crossings={crossings}")

    # Try: maybe the four sections are independently compressed, and the
    # packed stream is the whole resource after offset 23 (or after clut).
    # Or maybe compression covers ONLY the last section (pixel data) and
    # the first three sections are stored uncompressed in the resource.
    lines.append("\n== T3 extra: first-three-sections-as-raw in packed file? ==")
    offs = section_offs(d195)
    # If first section starts at 0 in decompressed, and is `offs[0]` bytes,
    # is that present raw at some packed offset?
    for raw_start in (0, 7, 23, clut_off_195, pixel_off):
        lines.append(f"  packed[{raw_start}:] first 16 = {d195[raw_start:raw_start+16].hex(' ')}")

    # ------------------------------------------------------------------ render if we have a winner
    winner_fn = None
    winner_name = None
    winner_start = pixel_off
    # re-scan for exact
    for start in range(0, min(80, len(d195))):
        out = packbits(d195[start:])
        if len(out) == 33144:
            winner_fn = packbits
            winner_name = f"packbits@{start}"
            winner_start = start
            break
    if winner_fn is None:
        for name, fn in SCHEMES:
            out = fn(d195[pixel_off:])
            if len(out) == 33144:
                winner_fn = fn
                winner_name = name
                winner_start = pixel_off
                break

    lines.append(f"\n== T3 winner so far: {winner_name} start={winner_start} ==")

    if winner_fn is not None:
        lines.append("\n== T3(e) apply winner to 196-202, 153, 148, 192, 128, all 50 ==")
        for rid in list(range(196, 203)) + [153, 148, 192, 128]:
            if rid not in shapes:
                continue
            d = shapes[rid]
            u0, _, _ = header(d)
            coff, cent = clut_by_rsrc[rid]
            poff = coff + 8 * len(cent) if cent else 23
            # use same start-relative rule: if winner was packbits@N with N
            # matching pixel_off style, use each resource's pixel_off
            start = poff if winner_start == pixel_off else winner_start
            out = winner_fn(d[start:])
            mark = "EXACT" if len(out) == u0 else f"d={len(out)-u0:+d}"
            lines.append(f"  {rid:3d} start={start} out={len(out):7d} u0={u0:7d} {mark}")

        n_exact = 0
        for rid in ids:
            d = shapes[rid]
            u0, _, _ = header(d)
            coff, cent = clut_by_rsrc[rid]
            poff = coff + 8 * len(cent) if cent else 23
            start = poff if winner_start == pixel_off else winner_start
            if start >= len(d):
                continue
            out = winner_fn(d[start:])
            if len(out) == u0:
                n_exact += 1
        lines.append(f"  EXACT u32@0 on {n_exact}/{len(ids)}")

        # render 195
        out195 = winner_fn(d195[winner_start:])
        SHAPEDIR.mkdir(parents=True, exist_ok=True)
        # try two 128x128 after optional 188-byte headers
        candidates = [
            ("plain", out195[0:16384], out195[16384:32768]),
            ("hdr188", out195[188:188 + 16384], out195[188 + 16384 + 188 : 188 + 16384 + 188 + 16384]),
            ("tail", out195[-32768:-16384], out195[-16384:]),
            ("sec3", None, None),
        ]
        # last-section based
        o = section_offs(d195)
        if o[3] + 16384 <= len(out195):
            a = out195[o[3] : o[3] + 16384]
            bstart = o[3] + 16384
            if bstart + 188 < len(out195) and len(out195) - bstart >= 16384 + 188:
                candidates.append(("from_off3_hdr", a, out195[bstart + 188 : bstart + 188 + 16384]))
            if bstart + 16384 <= len(out195):
                candidates.append(("from_off3", a, out195[bstart : bstart + 16384]))

        for label, a, b in candidates:
            if a is None or b is None or len(a) < 16384 or len(b) < 16384:
                continue
            render_floor(a[:16384], slots, SHAPEDIR / f"195_a_{label}.png")
            render_floor(b[:16384], slots, SHAPEDIR / f"195_b_{label}.png")
            lines.append(f"  wrote 195_*_{label}.png")
        # canonical names: prefer hdr188 if present
        if len(out195) >= 33144:
            a = out195[188:188 + 16384]
            b = out195[188 + 16384 + 188 : 188 + 16384 + 188 + 16384]
            if len(a) == 16384 and len(b) == 16384:
                render_floor(a, slots, SHAPEDIR / "195_a.png")
                render_floor(b, slots, SHAPEDIR / "195_b.png")
            else:
                render_floor(out195[:16384], slots, SHAPEDIR / "195_a.png")
                render_floor(out195[16384:32768], slots, SHAPEDIR / "195_b.png")
            lines.append("  wrote reference/shapes/195_a.png 195_b.png")

    dest = OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n... wrote {dest} lines={len(lines)}")


if __name__ == "__main__":
    main()
