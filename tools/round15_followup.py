# -*- coding: utf-8 -*-
"""Round 15 follow-up: L24 diffs, player-island, Cartesian floor RLE."""

from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from round10_256 import compact_gray, load_all_256  # noqa: E402

ONE = ROOT / "reference/saves/Saved Games"
TWO = ROOT / "reference/saves/Saved Games r14"
OLD = ROOT / "reference/saves/Saved Games AAA-AAB"
OUT = ROOT / "reference/docs/round15_followup.txt"
SHAPEDIR = ROOT / "reference/shapes"

LEVEL_BASE = 39392
STRIDE = 9112
SLOT = 2876

CHEAT = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flashlight",
    0x04: "?",
    0x06: "Canvas Sack",
    0x1C: "Bad Walther P4",
    0x23: "Silver Bowl",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x33: "Walther P4 Ammo (8 rounds)",
    0x3C: "40mm Projectile Cartridge",
}

ALCOVE = {43, 44, 45, 53, 57}


def u16(d: bytes, o: int) -> int:
    return struct.unpack_from(">H", d, o)[0]


def u32(d: bytes, o: int) -> int:
    return struct.unpack_from(">I", d, o)[0]


def rec4(d: bytes, o: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", d, o)


def runs_of(diffs: list[int]) -> list[tuple[int, int]]:
    if not diffs:
        return []
    out = []
    s = prev = diffs[0]
    for o in diffs[1:]:
        if o == prev + 1:
            prev = o
        else:
            out.append((s, prev))
            s = prev = o
    out.append((s, prev))
    return out


def popcount(b: bytes) -> int:
    return sum(bin(x).count("1") for x in b)


def main() -> None:
    one = ONE.read_bytes()
    two = TWO.read_bytes()
    old = OLD.read_bytes() if OLD.exists() else b""
    lines: list[str] = []

    # ---- L24 exact diffs ----
    lines.append("========== L24 CROSS-FILE (the only changing block) ==========")
    o24 = LEVEL_BASE + 24 * STRIDE
    a = one[o24 : o24 + STRIDE]
    b = two[o24 : o24 + STRIDE]
    diffs = [i for i in range(STRIDE) if a[i] != b[i]]
    lines.append(f"L24 @{o24} one-vs-r14: {len(diffs)} bytes")
    for s, e in runs_of(diffs):
        lines.append(
            f"  [{s}:{e}] ({e-s+1}B) one={a[s:e+1].hex(' ')} r14={b[s:e+1].hex(' ')}"
        )
        lines.append(f"    ctx1 {a[max(0,s-8):min(STRIDE,e+9)].hex(' ')}")
        lines.append(f"    ctx2 {b[max(0,s-8):min(STRIDE,e+9)].hex(' ')}")

    if old:
        c = old[o24 : o24 + STRIDE]
        d2 = [i for i in range(STRIDE) if b[i] != c[i]]
        lines.append(f"\nL24 r14-vs-old-AAA-AAB: {len(d2)} bytes")
        for s, e in runs_of(d2):
            lines.append(
                f"  [{s}:{e}] ({e-s+1}B) r14={b[s:e+1].hex(' ')} old={c[s:e+1].hex(' ')}"
            )

    # classify L24 diffs: header vs packed vs tail
    hdr = [i for i in diffs if i < 256]
    packed = [i for i in diffs if 256 <= i < 256 + 85 * 8]
    rest = [i for i in diffs if i >= 256 + 85 * 8]
    lines.append(f"\nL24 diff regions: header0-255={len(hdr)} packed256-936={len(packed)} rest={len(rest)}")
    lines.append("  => L24 is a scratch/live hybrid, NOT Ground Floor live state.")

    # ---- player island 1866+ ----
    lines.append("\n========== PLAYER ISLAND (rel 1866..2875) ==========")
    lines.append("Prefix 0..1865 of each 2876 slot is leftover 68k / name overlay,")
    lines.append("not duplicated player state. Real island starts at clock 0x074A.")
    sa = two[0:SLOT]
    sb = two[SLOT : 2 * SLOT]
    s1 = one[0:SLOT]
    island_diffs = [i for i in range(1866, SLOT) if sa[i] != sb[i]]
    lines.append(f"AAA vs AAB island diffs: {len(island_diffs)} bytes at {island_diffs}")
    for s, e in runs_of(island_diffs):
        lines.append(f"  [{s}:{e}] ({e-s+1}B) AAA={sa[s:e+1].hex(' ')} AAB={sb[s:e+1].hex(' ')}")
        lines.append(f"    ctxA {sa[max(1866,s-8):min(SLOT,e+9)].hex(' ')}")
        lines.append(f"    ctxB {sb[max(1866,s-8):min(SLOT,e+9)].hex(' ')}")

    # decode known + mystery
    lines.append("\nDecoded island fields (AAA / AAB / one-name):")
    fields = [
        (1866, 4, "clock u32"),
        (1872, 2, "u16 @0x0750 mystery"),
        (1874, 2, "u16 @0x0752 mystery"),
        (1876, 2, "HP"),
        (1878, 2, "HPmax"),
        (1880, 2, "u16 @0x0758"),
        (1882, 2, "u16 @0x075A"),
        (1884, 2, "u16 @0x075C"),
        (1886, 2, "u16 @0x075E"),
        (1888, 2, "u16 @0x0760"),
        (2112, 1, "BYTE @2112 flag/count"),
        (2148, 1, "BYTE @2148 flag/bits"),
        (2316, 2, "level"),
        (2328, 2, "X"),
        (2330, 2, "Y"),
        (2332, 2, "facing"),
        (2560, 8, "inv[0]"),
    ]
    for off, n, name in fields:
        lines.append(
            f"  {name} @{off}: AAA={sa[off:off+n].hex(' ')} "
            f"AAB={sb[off:off+n].hex(' ')} one={s1[off:off+n].hex(' ')}"
        )

    lines.append(
        f"\n  @0x0750 u16 AAA={u16(sa,1872)} AAB={u16(sb,1872)} one={u16(s1,1872)} "
        f"delta={u16(sb,1872)-u16(sa,1872)}"
    )
    lines.append(
        f"  @0x0752 u16 AAA={u16(sa,1874)} AAB={u16(sb,1874)} one={u16(s1,1874)} "
        f"delta={u16(sb,1874)-u16(sa,1874)}"
    )
    lines.append(f"  clock ticks AAA={u32(sa,1866)} AAB={u32(sb,1866)} one={u32(s1,1866)}")
    lines.append(f"  2112: AAA={sa[2112]} AAB={sb[2112]} one={s1[2112]}")
    lines.append(f"  2148: AAA={sa[2148]} AAB={sb[2148]} one={s1[2148]} bits AAB={bin(sb[2148])}")

    # interpret 2148 as bitmap start candidates
    lines.append("\n2148=0x08 interpretations:")
    lines.append("  if this BYTE is a counter: 8 (unrelated to Item 44)")
    lines.append("  if bitmap starts at 2143 (byte 5 = items 40-47), LSB bit3 = Item 43 (Red alcove, NOT pink 44)")
    lines.append("  if bitmap starts at 2143, LSB bit4 would be Item 44 — observed bit is 3, not 4")
    lines.append("  if bitmap starts at 2148 as byte 0: LSB bit3 = Item 3; MSB bit3 = Item 4")
    # search which start would make bit 44 flip
    # we know only byte 2148 changed from 0 to 8 in a large zero region
    # so the flipped bit is file-relative bit...
    lines.append("  ONLY byte 2148 in that zero run flipped, value 0x08 = LSB bit 3")
    for start in range(2090, 2150):
        # item 44 at start: byte = start + 44//8, bit = 44%8
        boff = start + 44 // 8
        bit = 44 % 8
        if boff == 2148 and (1 << bit) == 0x08:
            lines.append(f"  LSB Item44 maps to 2148 bit3 if bitmap starts at {start}")
        bit_msb = 7 - (44 % 8)
        if boff == 2148 and (1 << bit_msb) == 0x08:
            lines.append(f"  MSB Item44 maps to 2148 bit3 if bitmap starts at {start}")
    for start in range(2090, 2150):
        boff = start + 43 // 8
        bit = 43 % 8
        if boff == 2148 and (1 << bit) == 0x08:
            lines.append(f"  LSB Item43 maps to 2148 bit3 if bitmap starts at {start}")

    # 2112 = 0->1: taken-count?
    lines.append("\n2112 0->1: consistent with a taken-item COUNTER (one pickup).")
    lines.append(f"  one-name @2112={s1[2112]} (mid-game, many pickups — if this were a")
    lines.append("  global taken count it would be >>1; so either per-session, per-level,")
    lines.append("  or not a count).")

    # dump every nonzero u16 in island for AAA/AAB/one
    lines.append("\nAll nonzero u16be in island 1866-2558 (before inventory):")
    for off in range(1866, 2560, 2):
        va, vb, v1 = u16(sa, off), u16(sb, off), u16(s1, off)
        if va or vb or v1:
            mark = " DIFF" if va != vb else ""
            lines.append(f"  @{off} (0x{off:04X}) AAA={va:5d} AAB={vb:5d} one={v1:5d}{mark}")

    # 32x32 automap hunt in island
    lines.append("\nT3(d) 128-byte automap in player island:")
    live_auto = two[267192 + 132 : 267192 + 260]
    lines.append(f"  live header automap pop={popcount(live_auto)} hex={live_auto[:32].hex(' ')}...")
    for label, slot in (("AAA", sa), ("AAB", sb), ("one", s1)):
        found = []
        for off in range(1866, SLOT - 128 + 1):
            if slot[off : off + 128] == live_auto:
                found.append(off)
        near = [
            (off, popcount(slot[off : off + 128]))
            for off in range(1866, SLOT - 128 + 1, 2)
            if 80 <= popcount(slot[off : off + 128]) <= 200
        ]
        lines.append(f"  {label} exact copies={found} near-pop windows={near[:8]}")

    # inventory full
    lines.append("\nInventory AAA vs AAB (from 2560, 8-byte recs until garbage):")
    for i in range(20):
        ra, rb = rec4(sa, 2560 + i * 8), rec4(sb, 2560 + i * 8)
        name = CHEAT.get(ra[0], CHEAT.get(rb[0], ""))
        mark = " DIFF" if ra != rb else ""
        lines.append(f"  [{i:02d}] AAA={ra} AAB={rb} {name}{mark}")

    lines.append("\nKnife catalog 0003 as table index:")
    lines.append(f"  inv slot[3] AAA={rec4(sa,2560+24)} AAB={rec4(sb,2560+24)} (empty)")
    lines.append(f"  L0 packed rec[3]={rec4(two, LEVEL_BASE+256+24)}")
    lines.append(f"  L24 packed rec[3]={rec4(two, o24+256+24)}")
    live = two[267192 : 267192 + STRIDE]
    lines.append(f"  extra9112 rec[3]={rec4(live, 256+24)}")
    # dpin-like: maybe catalog 3 is the 4th world-instance assigned
    cats_aaa = [rec4(sa, 2560 + i * 8)[3] for i in range(16)]
    cats_aab = [rec4(sb, 2560 + i * 8)[3] for i in range(16)]
    lines.append(f"  AAA catalogs={cats_aaa}")
    lines.append(f"  AAB catalogs={cats_aab}")
    lines.append("  Catalog looks like an instance-id free-list (1,2,5,8,...).")
    lines.append("  Knife FFFF->0003 = assigned instance id 3. Slot 3 empty, so not an inv index.")

    # one-name inventory for comparison
    lines.append("\nOne-name inventory (mid-game):")
    for i in range(20):
        r = rec4(s1, 2560 + i * 8)
        if r[0] in (0xFFFF, 0) and r[1] > 100:
            lines.append(f"  [{i:02d}] {r} (garbage/end)")
            break
        lines.append(f"  [{i:02d}] {r} {CHEAT.get(r[0], '')}")

    # ---- T4 extra notes ----
    lines.append("\n========== T4 extra ==========")
    lines.append("One-name file ENDS at 267452 = 267192+260. It has the 260-byte")
    lines.append("header/tail but NOT the extra 9112 body. Two-name inserts 9112")
    lines.append("at 267192 and keeps a 260-byte header clone at EOF.")
    t24 = two[o24 : o24 + STRIDE]
    d24 = [i for i in range(STRIDE) if live[i] != t24[i]]
    auto_d = [i for i in d24 if 132 <= i < 260]
    other_d = [i for i in d24 if not (132 <= i < 260)]
    lines.append(f"extra9112 vs T24: {len(d24)} total, automap[132:260]={len(auto_d)}, other={len(other_d)}")
    lines.append("Other-than-automap diffs (so it is NOT only a buffer artifact):")
    for s, e in runs_of(other_d):
        lines.append(f"  [{s}:{e}] T24={t24[s:e+1].hex(' ')} live={live[s:e+1].hex(' ')}")

    # ---- T5 cartesian ----
    lines.append("\n========== T5 cartesian RLE ==========")
    do_256(lines)

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print(f"\n... wrote {OUT} ({len(lines)} lines)")


def decode_combo(
    src: bytes,
    rep: str,
    low: str,
    hi: str,
) -> bytes:
    """rep: prev7f/prev80/next7f/next80
    low: emit_plus (00=2,01=3,02=4) | u16count
    hi: skip | lit | plus1  for 0x11-0x7F (or just 0x11/0x12)
    """
    out = bytearray()
    i = 0
    n = len(src)
    prev = 0
    while i < n:
        b = src[i]
        i += 1
        if 0x03 <= b <= 0x10:
            out.append(b)
            prev = b
            continue
        if b >= 0x80:
            if rep.startswith("prev"):
                nrep = (b - 0x7F) if rep == "prev7f" else (b - 0x80)
                if nrep < 1:
                    nrep = 1
                out.extend(bytes([prev]) * nrep)
            else:
                if i >= n:
                    break
                val = src[i]
                i += 1
                nrep = (b - 0x7F) if rep == "next7f" else (b - 0x80)
                if nrep < 1:
                    nrep = 1
                out.extend(bytes([val]) * nrep)
                prev = val
            continue
        if b <= 2:
            if low == "emit_plus":
                if i >= n:
                    break
                val = src[i]
                i += 1
                out.extend(bytes([val]) * (b + 2))
                prev = val
            else:
                if i + 1 >= n:
                    break
                lo = src[i]
                i += 1
                val = src[i]
                i += 1
                cnt = (b << 8) | lo
                if cnt > 8192:
                    cnt = 8192
                out.extend(bytes([val]) * max(cnt, 1))
                prev = val
            continue
        # 0x11..0x7F
        if hi == "skip":
            continue
        if hi == "lit11" and b in (0x11, 0x12):
            out.append(b)
            prev = b
            continue
        if hi == "lit11" and b > 0x12:
            # leftover: plus1
            cnt = b + 1
            take = min(cnt, n - i)
            out.extend(src[i : i + take])
            if take:
                prev = src[i + take - 1]
            i += take
            continue
        if hi == "lit_all":
            out.append(b)
            prev = b
            continue
        if hi == "plus1":
            cnt = b + 1
            take = min(cnt, n - i)
            out.extend(src[i : i + take])
            if take:
                prev = src[i + take - 1]
            i += take
            continue
        if hi == "op_next":
            # 0x11/0x12 as opcode + pixel
            if i >= n:
                break
            val = src[i]
            i += 1
            out.extend(bytes([val]) * (b - 0x10 + 1))  # 11=2, 12=3?
            prev = val
            continue
    return bytes(out)


def do_256(lines: list[str]) -> None:
    shapes = load_all_256()
    srcs = {rid: shapes[rid][257:] for rid in range(195, 203) if rid in shapes}
    reps = ("prev7f", "prev80", "next7f", "next80")
    lows = ("emit_plus", "u16count")
    his = ("plus1", "skip", "lit11", "lit_all", "op_next")
    lines.append("T5(a) Cartesian (195/196/198 vs 33144):")
    hits = []
    closest = []
    for rep in reps:
        for low in lows:
            for hi in his:
                mode = f"{rep}+{low}+{hi}"
                for rid in (195, 196, 198):
                    out = decode_combo(srcs[rid], rep, low, hi)
                    err = abs(len(out) - 33144)
                    closest.append((err, rid, mode, len(out)))
                    mark = " HIT" if len(out) == 33144 else ""
                    if rid == 195 or mark:
                        lines.append(f"  {rid} {mode}: {len(out)}{mark}")
                    if len(out) == 33144:
                        hits.append((rid, mode))
    closest.sort()
    lines.append("closest 12:")
    for err, rid, mode, ln in closest[:12]:
        lines.append(f"  {rid} {mode}: {ln} err={err}")
    if hits:
        lines.append(f"EXACT HITS: {hits}")
        mode = hits[0][1]
        rep, low, hi = mode.split("+")
        for rid in range(195, 203):
            out = decode_combo(srcs[rid], rep, low, hi)
            lines.append(f"  all {rid}: {len(out)}")
        blob = shapes[195]
        pal = compact_gray(blob)
        out = decode_combo(srcs[195], rep, low, hi)
        render_pair(out, pal, SHAPEDIR / "195_a.png", SHAPEDIR / "195_b.png")
        lines.append("wrote 195_a.png 195_b.png")
    else:
        lines.append("NO exact 33144 hit. Not rendering.")

    # 0x11/0x12 more detail
    src = srcs[195]
    lines.append("\nT5(b) 0x11/0x12 neighbors as (prev, next) pairs:")
    for val in (0x11, 0x12):
        pairs = Counter()
        pos = []
        for i, b in enumerate(src):
            if b != val:
                continue
            prev = src[i - 1] if i else -1
            nxt = src[i + 1] if i + 1 < len(src) else -1
            pairs[(prev, nxt)] += 1
            pos.append(i)
        lines.append(f"  0x{val:02X} n={len(pos)} unique_pairs={len(pairs)} top={pairs.most_common(10)}")
        # runs of 11/12
        run_lens = []
        i = 0
        while i < len(src):
            if src[i] == val:
                j = i
                while j < len(src) and src[j] == val:
                    j += 1
                run_lens.append(j - i)
                i = j
            else:
                i += 1
        lines.append(f"    run_len hist={Counter(run_lens).most_common(8)}")


def render_pair(out: bytes, pal, path_a: Path, path_b: Path) -> None:
    def pix(i: int) -> tuple[int, int, int]:
        v = out[i] if i < len(out) else 0
        if v < 256 and pal[v]:
            return pal[v]
        return (v & 0xFF, v & 0xFF, v & 0xFF)

    SHAPEDIR.mkdir(parents=True, exist_ok=True)
    for path, start in ((path_a, 0), (path_b, 16384)):
        img = Image.new("RGB", (128, 128))
        px = img.load()
        for y in range(128):
            for x in range(128):
                px[x, y] = pix(start + y * 128 + x)
        img.save(path)


if __name__ == "__main__":
    main()
