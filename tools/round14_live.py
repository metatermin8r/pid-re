# -*- coding: utf-8 -*-
"""Round 14: live 9112-byte blocks for AAA (before) vs AAB (after)."""

from __future__ import annotations

import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402
from round10_256 import load_all_256  # noqa: E402
from round12_level_rle import decode_rle  # noqa: E402
from round9_shapes import header as shapes_header  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games r14"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round14_live.txt"
EXP_AAA = ROOT / "reference/saves/explored_AAA.png"
EXP_AAB = ROOT / "reference/saves/explored_AAB.png"

LEVEL_BASE = 39392
STRIDE = 9112
N_TEMPLATES = 25
INV_OFF = 0x0A00
TIME_FILE = 0x074A

ITEM_NAMES = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flash light",
    0x06: "Canvas sack",
    0x16: "Mein Kampf",
    0x23: "Silver Bowl?",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x33: "Walther P4 Ammo",
    0x3C: "40mm Projectile Cartridge",
}

# Descriptions Ni numbers (from reference/docs/...Descriptions)
NI = {
    0: 29,  # Ground Floor
    1: 40,
    2: 39,  # Lock&Load — user said 39i
    9: 22,  # We Can See In The Dark
}


def u16(d: bytes, o: int) -> int:
    return struct.unpack_from(">H", d, o)[0]


def u32(d: bytes, o: int) -> int:
    return struct.unpack_from(">I", d, o)[0]


def rec4(d: bytes, o: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", d, o)


def pascal(d: bytes, o: int) -> str:
    n = d[o]
    if n > 127:
        return f"<len {n}>"
    return d[o + 1 : o + 1 + n].decode("mac_roman", errors="replace")


def live_packed(block: bytes, start: int = 256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs, off
        recs.append((off, rec))
        off += 8
    return recs, off


def match_pct(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return 100.0 * sum(1 for i in range(n) if a[i] == b[i]) / n


def bitmap_lsb(block: bytes, start: int = 132, nbits: int = 1024) -> list[int]:
    bits = []
    for i in range(nbits):
        byte = block[start + i // 8]
        bits.append((byte >> (i % 8)) & 1)
    return bits


def set_xy(bits: list[int]) -> list[tuple[int, int]]:
    out = []
    for i, b in enumerate(bits):
        if b:
            out.append((i % 32, i // 32))
    return out


def render_explored(bits: list[int], path: Path, highlight: set[tuple[int, int]] | None = None) -> None:
    img = Image.new("RGB", (32, 32), (16, 16, 16))
    px = img.load()
    for i, b in enumerate(bits):
        x, y = i % 32, i // 32
        if highlight and (x, y) in highlight:
            px[x, y] = (255, 80, 80)
        elif b:
            px[x, y] = (220, 220, 80)
        else:
            px[x, y] = (24, 24, 24)
    img.resize((512, 512), Image.NEAREST).save(path)


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def find_names(data: bytes) -> list[tuple[int, str]]:
    found = []
    for off in range(0, min(len(data), 4096), 128):
        n = data[off]
        if 1 <= n <= 31 and all(32 <= b < 127 for b in data[off + 1 : off + 1 + n]):
            s = pascal(data, off)
            if s in ("AAA", "AAB") or (s.isprintable() and 1 <= len(s) <= 31):
                found.append((off, s))
        else:
            if off > 0 and found:
                break
    return found


def locate_live_blocks(data: bytes, templates: list[bytes], lines: list[str]) -> list[int]:
    """Return offsets of 9112-byte windows that look like live GF copies."""
    t0 = templates[0]
    candidates = []
    # scan every 8 bytes in the file (and also the expected slots)
    expected = [LEVEL_BASE + 25 * STRIDE]
    for off in range(0, len(data) - STRIDE + 1, 8):
        win = data[off : off + STRIDE]
        # cheap reject: live/template headers start 00 00 ff fe
        if win[0:4] != b"\x00\x00\xff\xfe":
            continue
        pct = match_pct(win, t0)
        if pct >= 70:
            candidates.append((off, pct, sum(1 for b in win if b)))
    lines.append("== 9112-windows matching L0 template >=70% (header 0000fffe) ==")
    # collapse nearby
    kept = []
    for off, pct, nz in candidates:
        if kept and off - kept[-1][0] < STRIDE:
            if pct > kept[-1][1]:
                kept[-1] = (off, pct, nz)
            continue
        kept.append((off, pct, nz))
    for off, pct, nz in kept:
        mark = " EXPECTED" if off in expected or off == LEVEL_BASE else ""
        is_tmpl = any(off == LEVEL_BASE + n * STRIDE for n in range(N_TEMPLATES))
        lines.append(f"  @{off} pctL0={pct:.2f} nonzero={nz} template={is_tmpl}{mark}")
    return [off for off, pct, nz in kept if not any(off == LEVEL_BASE + n * STRIDE for n in range(N_TEMPLATES))]


def main() -> None:
    data = SAVE.read_bytes()
    levels = load_maps(MAPS)
    lines: list[str] = []

    # ---- T1 a/b ----
    extra = len(data) - 267452
    k = extra / STRIDE
    lines.append("========== TASK 1 locate live blocks ==========")
    lines.append(f"T1(a) size={len(data)} (0x{len(data):X}) 267452+k*9112 => k={k}")
    names = find_names(data)
    lines.append("T1(b) Pascal names:")
    for off, s in names:
        lines.append(f"  @{off} {s!r}")
        lines.append(hexdump_mac_roman(data[off : off + 128]))

    templates = [
        data[LEVEL_BASE + n * STRIDE : LEVEL_BASE + (n + 1) * STRIDE]
        for n in range(N_TEMPLATES)
    ]
    nblocks = (len(data) - LEVEL_BASE) // STRIDE
    tail = (len(data) - LEVEL_BASE) % STRIDE
    lines.append(f"templates@39392 n={N_TEMPLATES} extra_blocks={nblocks - N_TEMPLATES} tail={tail}")

    live_offs = locate_live_blocks(data, templates, lines)

    # also always include expected
    exp_live = LEVEL_BASE + N_TEMPLATES * STRIDE
    if exp_live + STRIDE <= len(data) and exp_live not in live_offs:
        live_offs.append(exp_live)
    # scan first 39392 for a 9112 window best-matching L0
    best_prefix = (0, 0.0)
    for off in range(0, LEVEL_BASE - STRIDE + 1, 8):
        pct = match_pct(data[off : off + STRIDE], templates[0])
        if pct > best_prefix[1]:
            best_prefix = (off, pct)
    lines.append(f"best L0-match in prefix[0:39392]: @{best_prefix[0]} pct={best_prefix[1]:.2f}")

    # explored-bitmap signature f8 ff 1f in headers
    lines.append("== f8ff1f / explored-like hits ==")
    i = 0
    while True:
        j = data.find(b"\xf8\xff\x1f", i)
        if j < 0:
            break
        lines.append(f"  f8ff1f @{j} (block-rel {j - LEVEL_BASE if j >= LEVEL_BASE else 'pre'})")
        i = j + 1

    # player-region clocks (known offsets)
    lines.append("\n== player-region clocks (file offsets, not in 9112 block) ==")
    for off in (TIME_FILE, TIME_FILE + 2876, 1786, 1786 + 2876):
        t = u32(data, off)
        lines.append(f"  @{off} ({off:#x}) = {t} ({t/60:.2f}s)")
    t0 = u32(data, TIME_FILE)
    t1 = u32(data, TIME_FILE + 2876)
    lines.append(f"  0x074A vs +2876 delta = {t1 - t0} ticks = {(t1 - t0)/60:.2f}s")

    # clocks / player fields inside each candidate live block
    lines.append("\n== T1(c)(d)(e) candidate live blocks ==")
    ranked_blocks = []
    for off in sorted(set(live_offs + [exp_live])):
        if off + STRIDE > len(data):
            lines.append(f"  @{off} TRUNCATED (need {off+STRIDE}, file {len(data)})")
            continue
        blk = data[off : off + STRIDE]
        ranks = [(n, match_pct(blk, templates[n]), levels[n].name) for n in range(N_TEMPLATES)]
        ranks.sort(key=lambda x: -x[1])
        recs, term = live_packed(blk)
        lines.append(f"\n  block @{off} size={STRIDE} live_recs={len(recs)} term={term}")
        lines.append(f"    top template matches: {ranks[:5]}")
        # time-like at start of header (skip fffe)
        # dump header bytes that differ from template 0
        th = templates[0][:256]
        dh = [(i, th[i], blk[i]) for i in range(256) if th[i] != blk[i]]
        lines.append(f"    header diffs vs T0: {len(dh)}")
        ranked_blocks.append((off, blk, ranks, recs, dh))

    # If only one post-template block, the other live copy may be
    # the player-state region. Compare inventories at 2560 / 5436.
    lines.append("\n== inventories @0x0A00 and +2876 (player copies) ==")
    for base, label in ((0, "slot0"), (2876, "slot1")):
        lines.append(f"  {label}:")
        for i in range(16):
            off = INV_OFF + base + i * 8
            r = rec4(data, off)
            name = ITEM_NAMES.get(r[0], "")
            lines.append(f"    [{i:02d}] @{off} {r} {name}")

    # Decide AAA vs AAB by clock in player region first (T1d gate)
    clock_delta_s = (t1 - t0) / 60.0
    lines.append(f"\n********** T1(d) CLOCK GATE **********")
    lines.append(f"player 0x074A={t0} ({t0/60:.2f}s)  +2876={t1} ({t1/60:.2f}s)  delta={clock_delta_s:.2f}s")
    if clock_delta_s < 1.0:
        lines.append("CAPTURE BAD: clock delta under 1 second. STOP.")
    else:
        lines.append("Clock delta >= 1s — proceed. (2–3s is a one-tile alcove trip.)")

    # ---- T2: if we have 2 live blocks, diff them; else diff live vs template
    # and also search for a second packed list that diverges.
    live_full = [(off, blk, recs) for off, blk, ranks, recs, dh in ranked_blocks if off >= exp_live - 8]
    # add any high-match non-template from locate
    for off in live_offs:
        if off + STRIDE <= len(data) and all(o != off for o, _, _ in live_full):
            blk = data[off : off + STRIDE]
            recs, _ = live_packed(blk)
            live_full.append((off, blk, recs))

    lines.append(f"\n========== TASK 2 live-block diff (n={len(live_full)}) ==========")
    if len(live_full) >= 2:
        # assign by clock if we can find a clock in-block; else by explored
        # bit count / inventory later. For now pair first two post-template.
        a_off, a_blk, a_recs = live_full[0]
        b_off, b_blk, b_recs = live_full[1]
        # if clocks exist in player region, map later clock to AAB
        # We don't yet know which live block is which — use explored bit count
        # (AAB walked more) as a hint, and also packed-list shrink.
        sa = sum(bitmap_lsb(a_blk))
        sb = sum(bitmap_lsb(b_blk))
        lines.append(f"  blockA @{a_off} bits={sa} recs={len(a_recs)}")
        lines.append(f"  blockB @{b_off} bits={sb} recs={len(b_recs)}")
        aaa_blk, aab_blk = (a_blk, b_blk) if sa <= sb else (b_blk, a_blk)
        aaa_off = a_off if sa <= sb else b_off
        aab_off = b_off if sa <= sb else a_off
        aaa_recs = a_recs if sa <= sb else b_recs
        aab_recs = b_recs if sa <= sb else a_recs
        lines.append(f"  assigned AAA=@{aaa_off} (fewer/equal explored) AAB=@{aab_off}")
        do_block_diff(aaa_off, aaa_blk, aaa_recs, aab_off, aab_blk, aab_recs, templates[0], levels[0], lines)
    elif len(live_full) == 1:
        off, blk, recs = live_full[0]
        lines.append(f"  ONLY ONE post-template live block @{off} recs={len(recs)}")
        lines.append("  Diffing it against Ground Floor TEMPLATE (not AAA vs AAB).")
        t_recs, _ = live_packed(templates[0])
        do_block_diff(LEVEL_BASE, templates[0], t_recs, off, blk, recs, templates[0], levels[0], lines)
        # also: is there a second packed list elsewhere that diverges from template?
        lines.append("\n== search for a second packed list that is NOT the template ==")
        tlist = [r for _, r in t_recs]
        found_alt = []
        for off2 in range(0, len(data) - 8 * 86, 8):
            if LEVEL_BASE <= off2 < LEVEL_BASE + N_TEMPLATES * STRIDE:
                continue
            rec0 = rec4(data, off2)
            if rec0 != tlist[0]:
                continue
            # read 85
            recs2 = []
            p = off2
            ok = True
            for _ in range(86):
                if p + 8 > len(data):
                    ok = False
                    break
                r = rec4(data, p)
                if r[0] == 0xFFFF:
                    break
                recs2.append(r)
                p += 8
            if ok and 70 <= len(recs2) <= 90 and recs2 != tlist:
                found_alt.append((off2, len(recs2)))
        lines.append(f"  diverging 70-90 lists starting with T0 rec0: {found_alt[:20]}")

    # ---- T3 explored (for every live-like block + template) ----
    lines.append("\n========== TASK 3 explored bitmap ==========")
    bitmaps = []
    for label, off, blk in [("T0", LEVEL_BASE, templates[0])] + [
        (f"@{o}", o, data[o : o + STRIDE]) for o in sorted(set(live_offs + [exp_live])) if o + STRIDE <= len(data)
    ]:
        bits = bitmap_lsb(blk)
        sxy = set_xy(bits)
        lines.append(f"  {label} set={len(sxy)} {sxy}")
        bitmaps.append((label, off, bits, sxy))

    # render AAA/AAB: use the one live block vs template if only one live
    live_bitmaps = [(lab, off, bits, sxy) for lab, off, bits, sxy in bitmaps if lab != "T0"]
    if len(live_bitmaps) >= 2:
        # fewer bits = AAA
        live_bitmaps.sort(key=lambda x: len(x[3]))
        (_, _, bits_aaa, s_aaa) = live_bitmaps[0]
        (_, _, bits_aab, s_aab) = live_bitmaps[1]
    elif len(live_bitmaps) == 1:
        bits_aaa = bitmaps[0][2]  # template
        s_aaa = bitmaps[0][3]
        bits_aab = live_bitmaps[0][2]
        s_aab = live_bitmaps[0][3]
        lines.append("  NOTE: rendering template as explored_AAA stand-in; only one live bitmap")
    else:
        bits_aaa = bits_aab = [0] * 1024
        s_aaa = s_aab = set()
    newly = set(s_aab) - set(s_aaa)
    lines.append(f"  newly set {sorted(newly)}")
    gf = levels[0]
    for x, y in sorted(newly):
        sec = gf.sector_at(x, y)
        lines.append(f"    ({x},{y}) type={sec.type} Item={sec.item} walkable={sec.type != 0}")
    render_explored(bits_aaa, EXP_AAA, newly if False else None)
    render_explored(bits_aab, EXP_AAB, newly)
    lines.append(f"  wrote {EXP_AAA.name} {EXP_AAB.name}")

    # ---- T4 header ----
    lines.append("\n========== TASK 4 live header vs template ==========")
    th = templates[0][:256]
    for off in sorted(set(live_offs + [exp_live])):
        if off + 256 > len(data):
            continue
        lh = data[off : off + 256]
        diffs = [(i, th[i], lh[i]) for i in range(256) if th[i] != lh[i]]
        lines.append(f"  live @{off} header diffs={len(diffs)}")
        # group runs
        if diffs:
            s = prev = diffs[0][0]
            run = [diffs[0]]
            runs = []
            for i, a, b in diffs[1:]:
                if i == prev + 1:
                    prev = i
                    run.append((i, a, b))
                else:
                    runs.append(run)
                    s = prev = i
                    run = [(i, a, b)]
            runs.append(run)
            for run in runs:
                a0, a1 = run[0][0], run[-1][0]
                tv = bytes(th[a0 : a1 + 1]).hex(" ")
                lv = bytes(lh[a0 : a1 + 1]).hex(" ")
                lines.append(f"    [{a0}:{a1}] T={tv} L={lv}")
        # u16be == 0 in live, nonzero in template
        lines.append("  u16be zero-in-live nonzero-in-template:")
        for o in range(0, 256, 2):
            tv = u16(th, o)
            lv = u16(lh, o)
            if lv == 0 and tv != 0:
                lines.append(f"    +{o} T={tv} L=0")
        lines.append("  live header hex:")
        lines.append(hexdump_mac_roman(lh))

    # ---- T5 templates ----
    lines.append("\n========== TASK 5 template list semantics ==========")
    # L13
    b13 = templates[13]
    recs13, term13 = live_packed(b13)
    lines.append(f"T5(a) L13 live={len(recs13)} term={term13} (9112 means no FFFF)")
    lines.append(f"  L13 nonzero={sum(1 for b in b13 if b)} header={b13[:32].hex(' ')}")
    lines.append(f"  L13 first8 recs={[r for _, r in recs13[:8]]}")
    lines.append(f"  L13 bytes 256:320 {b13[256:320].hex(' ')}")
    # entropy-ish
    c = Counter(b13)
    lines.append(f"  L13 unique_bytes={len(c)} top={c.most_common(6)}")

    counts = []
    item_n = []
    type1_n = []
    corpse_n = []
    ni_x = []
    ni_y = []
    lines.append("T5(b) counts vs map:")
    for n, lv in enumerate(levels):
        recs, term = live_packed(templates[n])
        counts.append(len(recs))
        items = sum(1 for s in lv.sector_list if s.item != -1)
        t1 = sum(1 for s in lv.sector_list if s.type == 1)
        corpses = sum(1 for s in lv.sector_list if s.type == 6)
        item_n.append(items)
        type1_n.append(t1)
        corpse_n.append(corpses)
        ni = NI.get(n)
        extra = f" Ni={ni}" if ni is not None else ""
        lines.append(
            f"  L{n:02d} {lv.name!r:40s} live={len(recs):4d} items={items:3d} "
            f"type1={t1:3d} corpses={corpses:2d}{extra}"
        )
        if ni is not None:
            ni_x.append(float(len(recs)))
            ni_y.append(float(ni))
    # Pearson excluding L13 (1107)
    use = [i for i in range(25) if i != 13]
    lines.append(
        f"  Pearson r live~items (ex L13)={pearson([counts[i] for i in use], [item_n[i] for i in use]):.4f}"
    )
    lines.append(
        f"  Pearson r live~type1 (ex L13)={pearson([counts[i] for i in use], [type1_n[i] for i in use]):.4f}"
    )
    lines.append(
        f"  Pearson r live~corpses (ex L13)={pearson([counts[i] for i in use], [corpse_n[i] for i in use]):.4f}"
    )
    # Ni: we only have a few; also try reading Descriptions for all
    desc = ROOT / "reference/docs/hfs_Pathways_Extras_PIDMaps_Folder_Descriptions.txt"
    ni_all = parse_ni(desc)
    lines.append(f"  Descriptions Ni parsed: {ni_all}")
    if ni_all:
        xs, ys = [], []
        for n, ni in ni_all.items():
            if n == 13:
                continue
            if n < 25:
                xs.append(float(counts[n]))
                ys.append(float(ni))
        lines.append(f"  Pearson r live~Ni (ex L13)={pearson(xs, ys):.4f} n={len(xs)}")

    # T5(c) f0 vs item ids / Descriptions
    lines.append("\nT5(c) f0 histograms + ammo/bowl/40mm:")
    for n in (0, 1, 2, 6, 13):
        recs, _ = live_packed(templates[n])
        f0 = Counter(r[0] for _, r in recs)
        ammo = [r for _, r in recs if 0x33 in r or r[0] == 0x33]
        bowl = [r for _, r in recs if r[0] == 0x23]
        cart = [r for _, r in recs if r[0] == 0x3C]
        lines.append(
            f"  L{n} n={len(recs)} f0_top={[(hex(k), c) for k, c in f0.most_common(8)]} "
            f"ammo={len(ammo)} bowl={len(bowl)} cart={len(cart)}"
        )
        if n == 0:
            for i, (_, r) in enumerate(recs):
                if r[0] in (0x33, 0x23, 0x3C, 51, 35) or 44 in r or 7 in r:
                    lines.append(f"    [{i}] {r} {ITEM_NAMES.get(r[0], '')}")

    # type-35 f2 vs Items on GF
    recs0, _ = live_packed(templates[0])
    f2_35 = {r[2] for _, r in recs0 if r[0] == 35}
    items0 = {s.item for s in levels[0].sector_list if s.item != -1}
    lines.append(f"  GF type35 f2 n={len(f2_35)} items n={len(items0)} inter={len(f2_35 & items0)}")
    lines.append(f"  items missing from type35={sorted(items0 - f2_35)[:40]}...")

    # ---- T6 .256 ----
    lines.append("\n========== TASK 6 .256 uncapped ==========")
    do_256(lines)

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:100]))
    print(f"\n... wrote {OUT} ({len(lines)} lines)")


def do_block_diff(a_off, a_blk, a_recs, b_off, b_blk, b_recs, template, gf, lines):
    lines.append(f"T2(c) live counts: A@{a_off}={len(a_recs)}  B@{b_off}={len(b_recs)}  template={85}")
    diffs = [i for i in range(STRIDE) if a_blk[i] != b_blk[i]]
    lines.append(f"T2(a) differing bytes={len(diffs)}")
    runs = []
    if diffs:
        s = prev = diffs[0]
        for o in diffs[1:]:
            if o == prev + 1:
                prev = o
            else:
                runs.append((s, prev))
                s = prev = o
        runs.append((s, prev))
    lines.append(f"  runs={len(runs)}")

    def classify(off: int) -> str:
        if 132 <= off < 260:
            return "explored_bitmap"
        if off < 256:
            return "header"
        recs_end = max(
            (a_recs[-1][0] + 8 if a_recs else 256),
            (b_recs[-1][0] + 8 if b_recs else 256),
        )
        if 256 <= off < recs_end + 8:
            return "packed_list"
        return "tail"

    by = defaultdict(int)
    for a, b in runs:
        cls = classify(a)
        by[cls] += b - a + 1
        ctx_a = a_blk[a : min(STRIDE, a + 16)].hex(" ")
        ctx_b = b_blk[a : min(STRIDE, a + 16)].hex(" ")
        lines.append(
            f"  [{a}:{b}] ({b-a+1}B) {cls} A={a_blk[a:b+1].hex(' ')} B={b_blk[a:b+1].hex(' ')}"
        )
        lines.append(f"    ctxA {ctx_a}")
        lines.append(f"    ctxB {ctx_b}")
    lines.append("T2(b) bytes per class:")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {k}: {v}")

    # T2 d/e
    if len(b_recs) == len(a_recs) - 1:
        # find first diverge
        di = 0
        for i, ((oa, ra), (ob, rb)) in enumerate(zip(a_recs, b_recs)):
            if ra != rb:
                di = i
                break
        else:
            di = len(b_recs)
        lines.append(f"T2(d) first list diverge at record {di}")
        # shift test
        a_from = a_blk[256 + (di + 1) * 8 : 256 + len(a_recs) * 8 + 8]
        b_from = b_blk[256 + di * 8 : 256 + len(b_recs) * 8 + 8]
        lines.append(f"  AAB[di:] == AAA[di+1:] ? {a_from == b_from} lens {len(a_from)} {len(b_from)}")
        removed = a_recs[di][1]
        lines.append(f"  removed record {removed}")
        decode_record("removed", removed, lines)
    elif len(a_recs) == len(b_recs):
        lines.append("T2(e) counts match — in-place field changes:")
        for i, ((oa, ra), (ob, rb)) in enumerate(zip(a_recs, b_recs)):
            if ra != rb:
                lines.append(f"  rec[{i}] +{oa} A={ra} B={rb}")
                for fi, name in enumerate(("f0", "f1", "f2", "f3")):
                    if ra[fi] != rb[fi]:
                        lines.append(f"    {name}: {ra[fi]} -> {rb[fi]}")
                decode_record("A", ra, lines)
                decode_record("B", rb, lines)
        if all(ra == rb for (_, ra), (_, rb) in zip(a_recs, b_recs)):
            lines.append("  packed lists IDENTICAL")
    else:
        lines.append(f"T2(d/e) count delta {len(a_recs)} -> {len(b_recs)} (not -1)")
        # still show first diverge
        for i, ((oa, ra), (ob, rb)) in enumerate(zip(a_recs, b_recs)):
            if ra != rb:
                lines.append(f"  first diverge rec[{i}] A={ra} B={rb}")
                decode_record("A", ra, lines)
                decode_record("B", rb, lines)
                break


def decode_record(label: str, rec: tuple[int, int, int, int], lines: list[str]) -> None:
    alcove = {43, 44, 45, 53, 57}
    flags = []
    if rec[0] == 0x33:
        flags.append("f0==0x33 WaltherAmmo")
    if 0x33 in rec:
        flags.append("field==0x33")
    if 7 in rec:
        flags.append("field==7 qty")
    if 44 in rec:
        flags.append("field==44 Item(5,2) CONFIRMS Sector.Item")
    hits = [v for v in rec if v in alcove]
    if hits:
        flags.append(f"alcove Items {hits}")
    name = ITEM_NAMES.get(rec[0], "")
    lines.append(f"  T2(f) {label} {rec} {name} {flags}")
    lines.append(f"  T2(g) Sector.Item confirmed? {'YES' if 44 in rec else 'no field==44'}")


def parse_ni(path: Path) -> dict[int, int]:
    if not path.exists():
        return {}
    # lines like "Ground Floor 0.0m 00 29i"
    import re

    out = {}
    # map name prefixes to level numbers via later load — parse "NN i" after level header
    # We'll fill from known file: first token line without leading tab, trailing Ni
    n = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"\b(\d+)i\b", line)
        if m and not line.startswith("\t") and not line.startswith(" "):
            # crude: sequential level headers
            out[n] = int(m.group(1))
            n += 1
    return out


def do_256(lines: list[str]) -> None:
    shapes = load_all_256()

    def plus1(src, target=None):
        return decode_rle(src, "plus1", "highbit_plus1", target)

    def plus1_zero00(src, target=None):
        """0x00 = emit (next? or fixed) zeros; otherwise plus1+highbit.
        Try: 00 => emit N zeros where N is a parameter — test several.
        Simpler: 00 with no operand emits 1 zero; or 00 + count.
        User: opcode 0x00 as emit N transparent/zero pixels rather than copy literal.
        We'll treat 00 as 'emit next-byte zeros' AND as 'emit 8 zeros' AND as 'emit 1 zero'.
        This function: 00 + n => n zeros (n=following byte). If following is a pixel 3-16
        that would be wrong... user said 00's operand is a pixel. Alternative: 00 means
        emit a run of zeros whose length comes from a default.
        Implement: C==0 => emit `zcount` zeros, consume 1 byte (the opcode only).
        """
        return None  # handled below

    # 6a 198 uncapped
    src198 = shapes[198][257:]
    out, used = plus1(src198, None)
    lines.append(f"T6(a) 198 @257 plus1+highbit NO CAP: out={len(out)} used={used}/{len(src198)} leftover={len(src198)-used}")
    outc, usedc = plus1(src198, 16384)
    lines.append(f"       capped 16384: out={len(outc)} used={usedc} leftover={len(src198)-usedc}")

    # 6b 195 uncapped
    src195 = shapes[195][257:]
    out, used = plus1(src195, None)
    lines.append(f"T6(b) 195 @257 plus1+highbit NO CAP: out={len(out)} used={used}/{len(src195)} leftover={len(src195)-used}")
    outc, usedc = plus1(src195, 33144)
    lines.append(f"       capped 33144: out={len(outc)} used={usedc} leftover={len(src195)-usedc}")

    # 6c 00 = emit zeros
    for zmode, zparam in (
        ("emit1", 1),
        ("emit8", 8),
        ("emit_follow_as_count", None),
    ):
        for rid, src in ((195, src195), (198, src198)):
            out = bytearray()
            i = 0
            n = len(src)
            while i < n:
                c = src[i]
                i += 1
                if c == 0x00:
                    if zmode == "emit_follow_as_count":
                        if i >= n:
                            break
                        cnt = src[i]
                        i += 1
                        out.extend(b"\x00" * cnt)
                    else:
                        out.extend(b"\x00" * zparam)
                elif c >= 0x80:
                    if i >= n:
                        break
                    val = src[i]
                    i += 1
                    out.extend(bytes([val]) * ((c & 0x7F) + 1))
                else:
                    cnt = c + 1
                    take = min(cnt, n - i)
                    out.extend(src[i : i + take])
                    i += min(cnt, n - i)
            lines.append(f"T6(c) {rid} 00={zmode}: out={len(out)} used={i}/{n} leftover={n-i}")

    # 6d ratio out / u32@0 for all 50
    lines.append("\nT6(d) plus1+highbit @257 uncapped vs u32@0:")
    ratios = []
    for rid in sorted(shapes):
        blob = shapes[rid]
        u0 = u32(blob, 0) if len(blob) >= 4 else 0
        # header() from round9 uses offset 7 table; u32@0 is first word of resource
        src = blob[257:] if len(blob) > 257 else blob
        out, used = plus1(src, None)
        ratio = (len(out) / u0) if u0 else float("nan")
        ratios.append(ratio)
        lines.append(
            f"  {rid:3d} size={len(blob):6d} u32@0={u0:7d} out={len(out):7d} "
            f"ratio={ratio:.4f} used={used}/{len(src)}"
        )
    valid = [r for r in ratios if r == r]
    if valid:
        lines.append(
            f"  ratio min={min(valid):.4f} max={max(valid):.4f} "
            f"median={sorted(valid)[len(valid)//2]:.4f}"
        )

    # 6e last 128 packed
    for rid in (195, 198):
        src = shapes[rid][257:]
        tail = src[-128:]
        lines.append(f"\nT6(e) {rid} last 128 packed:")
        lines.append(tail.hex(" "))
        lines.append(hexdump_mac_roman(tail))


if __name__ == "__main__":
    main()
