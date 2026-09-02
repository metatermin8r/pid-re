# -*- coding: utf-8 -*-
"""Round 14 follow-up: live blocks at 30280 and 267192."""

from __future__ import annotations

import struct
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games r14"
OLD1 = ROOT / "reference/saves/Saved Games"
OLD2 = ROOT / "reference/saves/Saved Games AAA-AAB"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round14_blocks.txt"
EXP_AAA = ROOT / "reference/saves/explored_AAA.png"
EXP_AAB = ROOT / "reference/saves/explored_AAB.png"

LEVEL_BASE = 39392
STRIDE = 9112
CANDIDATES = (30280, 267192, 276304)

ITEM_NAMES = {
    0x23: "Silver Bowl",
    0x2D: "Survival Knife",
    0x33: "Walther P4 Ammo",
    0x3C: "40mm Projectile Cartridge",
}


def u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def u32(d, o):
    return struct.unpack_from(">I", d, o)[0]


def rec4(d, o):
    return struct.unpack_from(">4H", d, o)


def match_pct(a, b):
    n = min(len(a), len(b))
    return 100.0 * sum(1 for i in range(n) if a[i] == b[i]) / n


def live_packed(block, start=256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs, off
        recs.append((off, rec))
        off += 8
    return recs, off


def bitmap_lsb(block, start=132, nbits=1024):
    bits = []
    for i in range(nbits):
        if start + i // 8 >= len(block):
            bits.append(0)
            continue
        byte = block[start + i // 8]
        bits.append((byte >> (i % 8)) & 1)
    return bits


def set_xy(bits):
    return [(i % 32, i // 32) for i, b in enumerate(bits) if b]


def render(bits, path, highlight=None):
    img = Image.new("RGB", (32, 32), (16, 16, 16))
    px = img.load()
    for i, b in enumerate(bits):
        x, y = i % 32, i // 32
        if highlight and (x, y) in highlight:
            px[x, y] = (255, 70, 70)
        elif b:
            px[x, y] = (230, 220, 70)
        else:
            px[x, y] = (20, 20, 20)
    img.resize((512, 512), Image.NEAREST).save(path)


def classify(off, recs_end):
    if 132 <= off < 260:
        return "explored_bitmap"
    if off < 256:
        return "header"
    if 256 <= off < recs_end + 16:
        return "packed_list"
    return "tail"


def decode_rec(label, rec, lines):
    alcove = {43, 44, 45, 53, 57}
    flags = []
    if rec[0] == 0x33:
        flags.append("f0==0x33 WaltherAmmo")
    if 0x33 in rec:
        flags.append("has 0x33")
    if 7 in rec:
        flags.append("has qty7")
    if 44 in rec:
        flags.append("HAS 44 — Sector.Item CONFIRMED")
    hit = [v for v in rec if v in alcove]
    if hit:
        flags.append(f"alcove {hit}")
    lines.append(f"    {label} {rec} {ITEM_NAMES.get(rec[0], '')} {flags}")


def main():
    data = SAVE.read_bytes()
    levels = load_maps(MAPS)
    lines = []
    templates = [data[LEVEL_BASE + n * STRIDE : LEVEL_BASE + (n + 1) * STRIDE] for n in range(25)]

    lines.append(f"size={len(data)}")
    for label, path in (("one-name", OLD1), ("old-AAAB", OLD2)):
        if path.exists():
            blob = path.read_bytes()
            lines.append(f"{label} size={len(blob)}")
            for off in CANDIDATES:
                if off + 16 <= len(blob):
                    chunk = blob[off : off + min(STRIDE, len(blob) - off)]
                    lines.append(
                        f"  {label} @{off} avail={len(chunk)} first8={chunk[:8].hex()} "
                        f"nonzero={sum(1 for b in chunk if b)}"
                    )

    blocks = {}
    for off in CANDIDATES:
        avail = min(STRIDE, len(data) - off)
        if avail <= 0:
            continue
        blk = data[off : off + avail]
        recs, term = live_packed(blk) if avail >= 264 else ([], None)
        ranks = [(n, match_pct(blk, templates[n][:avail]), levels[n].name) for n in range(25)]
        ranks.sort(key=lambda x: -x[1])
        bits = bitmap_lsb(blk)
        sxy = set_xy(bits)
        lines.append(f"\n======== block @{off} avail={avail} ========")
        lines.append(f"  first16={blk[:16].hex(' ')}")
        lines.append(f"  live_recs={len(recs)} term={term} explored_set={len(sxy)}")
        lines.append(f"  top5 templates: {[(n, f'{p:.2f}', name) for n, p, name in ranks[:5]]}")
        # header vs T0
        th = templates[0][: min(256, avail)]
        lh = blk[: min(256, avail)]
        hd = [(i, th[i], lh[i]) for i in range(len(th)) if th[i] != lh[i]]
        lines.append(f"  header diffs vs T0: {len(hd)}")
        if hd:
            # runs
            s = prev = hd[0][0]
            runs = []
            for i, _, _ in hd[1:]:
                if i == prev + 1:
                    prev = i
                else:
                    runs.append((s, prev))
                    s = prev = i
            runs.append((s, prev))
            for a, b in runs:
                lines.append(
                    f"    hdr[{a}:{b}] T={th[a:b+1].hex(' ')} L={lh[a:b+1].hex(' ')}"
                )
        # u16 zero in live, nz in template
        zcands = []
        for o in range(0, min(256, avail) - 1, 2):
            tv, lv = u16(th, o) if o + 2 <= len(th) else (0, 0), u16(lh, o) if o + 2 <= len(lh) else 0
            if isinstance(tv, tuple):
                tv = tv[0]
            if lv == 0 and tv != 0:
                zcands.append((o, tv))
        lines.append(f"  u16be zero-live nz-template: {zcands}")
        lines.append("  header dump:")
        lines.append(hexdump_mac_roman(lh[:256] if len(lh) >= 256 else lh))
        lines.append(f"  explored tiles: {sxy}")
        blocks[off] = (blk, recs, bits, sxy, ranks)

    # assign AAA/AAB by explored count (AAB walked more) AND by inventory/clock
    # player clocks
    t_a = u32(data, 0x074A)
    t_b = u32(data, 0x074A + 2876)
    lines.append(f"\nT1(d) player clocks 0x074A={t_a} ({t_a/60:.2f}s) +2876={t_b} ({t_b/60:.2f}s) delta={(t_b-t_a)/60:.2f}s")

    full = {off: v for off, v in blocks.items() if len(v[0]) >= 9000}
    lines.append(f"full 9112 blocks: {list(full)}")

    if len(full) >= 2:
        offs = sorted(full, key=lambda o: len(full[o][3]))  # fewer bits first
        aaa_off, aab_off = offs[0], offs[1]
        # if clocks in player region: earlier = AAA. We still need to bind
        # live block to name. Prefer: later clock's owner walked more.
        # Don't assume. Report both assignments if they disagree.
        lines.append(f"explored-order AAA? @{aaa_off} bits={len(full[aaa_off][3])} AAB? @{aab_off} bits={len(full[aab_off][3])}")
    elif len(full) == 1:
        only = next(iter(full))
        lines.append(f"only one full live block @{only}")
        aaa_off = aab_off = only
    else:
        lines.append("NO full live blocks")
        aaa_off = aab_off = None

    # If we have two full blocks, do THE DIFF
    if aaa_off != aab_off and aaa_off is not None:
        do_diff(aaa_off, aab_off, full, levels[0], lines)
        bits_aaa, bits_aab = full[aaa_off][2], full[aab_off][2]
        newly = set(full[aab_off][3]) - set(full[aaa_off][3])
        lost = set(full[aaa_off][3]) - set(full[aab_off][3])
    else:
        # compare 30280 vs 267192 even if one was not in `full` due to ranking
        if 30280 in blocks and 267192 in blocks and len(blocks[30280][0]) >= 9000:
            do_diff(30280, 267192, {30280: blocks[30280], 267192: blocks[267192]}, levels[0], lines)
            bits_aaa, bits_aab = blocks[30280][2], blocks[267192][2]
            newly = set(blocks[267192][3]) - set(blocks[30280][3])
            lost = set(blocks[30280][3]) - set(blocks[267192][3])
            aaa_off, aab_off = 30280, 267192
        else:
            bits_aaa = blocks.get(267192, (b"", [], [0] * 1024, [], []))[2]
            bits_aab = bits_aaa
            newly, lost = set(), set()

    # also compare 267192 bitmap vs 276304 bitmap (header-only second)
    if 267192 in blocks and 276304 in blocks:
        s1 = set(blocks[267192][3])
        s2 = set(blocks[276304][3])
        lines.append(f"\nbitmap 267192 vs 276304-header: only267={sorted(s1-s2)} only276={sorted(s2-s1)}")

    lines.append(f"\nT3 newly-set {sorted(newly)}")
    lines.append(f"T3 lost {sorted(lost)}")
    gf = levels[0]
    for x, y in sorted(newly):
        sec = gf.sector_at(x, y)
        lines.append(f"  ({x},{y}) type={sec.type} Item={sec.item} void={sec.type==0}")
    render(bits_aaa, EXP_AAA)
    render(bits_aab, EXP_AAB, newly)
    lines.append(f"wrote {EXP_AAA} {EXP_AAB}")

    # inventories reminder
    lines.append("\n== inventory AAA@2560 vs AAB@5436 ==")
    for i in range(16):
        a = rec4(data, 0x0A00 + i * 8)
        b = rec4(data, 0x0A00 + 2876 + i * 8)
        if a != b:
            lines.append(f"  rec[{i}] AAA={a} AAB={b}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def do_diff(a_off, b_off, blocks, gf, lines):
    a_blk, a_recs, _, _, _ = blocks[a_off]
    b_blk, b_recs, _, _, _ = blocks[b_off]
    n = min(len(a_blk), len(b_blk))
    diffs = [i for i in range(n) if a_blk[i] != b_blk[i]]
    lines.append(f"\n========== T2 DIFF @{a_off} vs @{b_off} ==========")
    lines.append(f"T2(c) counts A={len(a_recs)} B={len(b_recs)}")
    lines.append(f"T2(a) differing bytes={len(diffs)}")
    if not diffs:
        lines.append("  IDENTICAL")
        return
    runs = []
    s = prev = diffs[0]
    for o in diffs[1:]:
        if o == prev + 1:
            prev = o
        else:
            runs.append((s, prev))
            s = prev = o
    runs.append((s, prev))
    recs_end = max(
        a_recs[-1][0] + 8 if a_recs else 256,
        b_recs[-1][0] + 8 if b_recs else 256,
    )
    by = defaultdict(int)
    lines.append(f"  runs={len(runs)}")
    for a, b in runs:
        cls = classify(a, recs_end)
        by[cls] += b - a + 1
        lines.append(
            f"  [{a}:{b}] ({b-a+1}B) {cls} A={a_blk[a:b+1].hex(' ')} B={b_blk[a:b+1].hex(' ')}"
        )
        lines.append(f"    ctxA {a_blk[a:min(n,a+16)].hex(' ')}")
        lines.append(f"    ctxB {b_blk[a:min(n,a+16)].hex(' ')}")
    lines.append("T2(b) class bytes:")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {k}: {v}")

    if len(b_recs) == len(a_recs) - 1:
        di = next((i for i, ((_, ra), (_, rb)) in enumerate(zip(a_recs, b_recs)) if ra != rb), len(b_recs))
        lines.append(f"T2(d) first diverge rec[{di}]")
        a_from = a_blk[256 + (di + 1) * 8 : 256 + len(a_recs) * 8 + 8]
        b_from = b_blk[256 + di * 8 : 256 + len(b_recs) * 8 + 8]
        lines.append(f"  shift+8 match? {a_from == b_from}")
        removed = a_recs[di][1]
        lines.append(f"  removed {removed}")
        decode_rec("removed", removed, lines)
        lines.append(f"  T2(g) Sector.Item confirmed? {'YES' if 44 in removed else 'NO'}")
    elif len(a_recs) == len(b_recs):
        lines.append("T2(e) same count — in-place changes:")
        nchg = 0
        for i, ((oa, ra), (ob, rb)) in enumerate(zip(a_recs, b_recs)):
            if ra != rb:
                nchg += 1
                lines.append(f"  rec[{i}] +{oa} A={ra} B={rb}")
                for fi, name in enumerate(("f0", "f1", "f2", "f3")):
                    if ra[fi] != rb[fi]:
                        lines.append(f"    {name}: {ra[fi]} -> {rb[fi]}")
                decode_rec("A", ra, lines)
                decode_rec("B", rb, lines)
                lines.append(f"  T2(g) field 44? A={44 in ra} B={44 in rb}")
        if nchg == 0:
            lines.append("  packed lists IDENTICAL")
    else:
        lines.append(f"T2 counts {len(a_recs)} vs {len(b_recs)}")
        for i, ((_, ra), (_, rb)) in enumerate(zip(a_recs, b_recs)):
            if ra != rb:
                lines.append(f"  first diverge rec[{i}] A={ra} B={rb}")
                decode_rec("A", ra, lines)
                decode_rec("B", rb, lines)
                break


if __name__ == "__main__":
    main()
