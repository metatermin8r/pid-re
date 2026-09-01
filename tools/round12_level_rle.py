# -*- coding: utf-8 -*-
"""Round 12: per-level 9112-byte state array + revised .256 RLE."""

from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402
from round10_256 import load_all_256  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DPIN = ROOT / "reference/dpin_128.bin"
BOMB_NEW = ROOT / "reference/saves/BombCode.bin"
BOMB_OLD = ROOT / "reference/saves/BombCode_1995.bin"
OUT = ROOT / "reference/docs/round12_level_rle.txt"

LEVEL_BASE = 39392
LEVEL_STRIDE = 9112
N_LEVELS = 25
N_REC = 1139


def u16s(rec: bytes) -> tuple[int, int, int, int]:
    return struct.unpack(">4H", rec)


def field_stats(records: list[tuple[int, int, int, int]]) -> list[str]:
    lines = []
    for fi, name in enumerate(("f0", "f1", "f2", "f3")):
        vals = [r[fi] for r in records]
        z = sum(1 for v in vals if v == 0)
        ff = sum(1 for v in vals if v == 0xFFFF)
        nz = [v for v in vals if v not in (0, 0xFFFF)]
        lines.append(
            f"  {name}: zero={z} ffff={ff} other={len(nz)} "
            f"min={min(vals)} max={max(vals)} "
            f"nonzero_non_ffff min={min(nz) if nz else '-'} max={max(nz) if nz else '-'}"
        )
        c = Counter(vals)
        top = c.most_common(8)
        lines.append(f"    top={[(hex(v), n) for v, n in top]}")
    return lines


def nonempty_defs(rec: tuple[int, int, int, int]) -> dict[str, bool]:
    return {
        "not_zero": rec != (0, 0, 0, 0),
        "any_live": any(v not in (0, 0xFFFF) for v in rec),
        "f0_live": rec[0] not in (0, 0xFFFF),
        "not_empty_slot": rec not in ((0, 0, 0, 0), (0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)),
    }


def item_set(level) -> set[int]:
    return {sec.item for sec in level.sector_list if sec.item != -1}


def decode_rle(
    src: bytes,
    lit_mode: str,
    rep_mode: str,
    target: int | None = None,
) -> tuple[bytes, int]:
    """lit_mode: plus1 | times2 | times4 | times8
    rep_mode: c_minus_7f | highbit_plus1 | packbits | none
    If C>=0x80 use repeat; else literals.
    """
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        if target is not None and len(out) >= target:
            break
        c = src[i]
        i += 1
        if c >= 0x80 and rep_mode != "none":
            if i >= n:
                break
            val = src[i]
            i += 1
            if rep_mode == "c_minus_7f":
                count = c - 0x7F
            elif rep_mode == "highbit_plus1":
                count = (c & 0x7F) + 1
            elif rep_mode == "packbits":
                count = 257 - c
            else:
                count = 1
            take = count if target is None else min(count, target - len(out))
            out.extend(bytes([val]) * take)
        else:
            if lit_mode == "plus1":
                count = c + 1
            elif lit_mode == "times2":
                count = c * 2 if c else 2
            elif lit_mode == "times4":
                count = c * 4 if c else 4
            elif lit_mode == "times8":
                count = c * 8 if c else 8
            else:
                count = c + 1
            take = min(count, n - i)
            if target is not None:
                take = min(take, target - len(out))
            out.extend(src[i : i + take])
            i += min(count, n - i)
    return bytes(out), i


def decode_nibble(src: bytes, target: int | None = None) -> tuple[bytes, int]:
    """High nibble = literal count, low nibble = run count of next byte after lits."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        if target is not None and len(out) >= target:
            break
        c = src[i]
        i += 1
        nlit = (c >> 4) & 0xF
        nrun = c & 0xF
        take = min(nlit, n - i)
        if target is not None:
            take = min(take, target - len(out))
        out.extend(src[i : i + take])
        i += min(nlit, n - i)
        if nrun and i < n and (target is None or len(out) < target):
            val = src[i]
            i += 1
            take = nrun if target is None else min(nrun, target - len(out))
            out.extend(bytes([val]) * take)
    return bytes(out), i


def decode_opcodes(src: bytes, target: int | None = None) -> tuple[bytes, int]:
    """00 = copy 8 lits; 01 = repeat next count? or repeat next byte; 02 = skip/eor.
    Try: 00 + 8 literals; 01 + value (repeat using following as count?);
    Conservative: 01 = repeat next byte 2 times; 02 = skip 1 / end row no-op.
    Better measured from follow-bytes — implemented as:
      00: copy 8
      01: copy 1 then? wait — 01 + byte = repeat that byte (count from 01+1=2)
      02: no-op / consume 0
    Actually user asked to REPORT follow-bytes first; this decoder is one candidate:
      00 -> copy 8 literals
      01 -> next byte is a value, emit it twice (or next is count)
      02 -> skip (consume no extra) OR copy 0
    """
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        if target is not None and len(out) >= target:
            break
        c = src[i]
        i += 1
        if c == 0x00:
            take = min(8, n - i)
            if target is not None:
                take = min(take, target - len(out))
            out.extend(src[i : i + take])
            i += min(8, n - i)
        elif c == 0x01:
            if i >= n:
                break
            val = src[i]
            i += 1
            take = 2 if target is None else min(2, target - len(out))
            out.extend(bytes([val]) * take)
        elif c == 0x02:
            continue
        elif c >= 0x80:
            if i >= n:
                break
            val = src[i]
            i += 1
            count = (c & 0x7F) + 1
            take = count if target is None else min(count, target - len(out))
            out.extend(bytes([val]) * take)
        else:
            # 03-7F: treat as literal pixel (discriminator) or copy c+1
            take = min(c + 1, n - i)
            if target is not None:
                take = min(take, target - len(out))
            out.extend(src[i : i + take])
            i += min(c + 1, n - i)
    return bytes(out), i


def main() -> None:
    data = SAVE.read_bytes()
    levels = load_maps(MAPS)
    dpin = DPIN.read_bytes()
    lines: list[str] = []

    # map item sets
    lines.append("== map Item sets (from Maps file) ==")
    want = {0: "Ground Floor", 6: "Ascension", 13: "The Labyrinth"}
    item_sets: dict[int, set[int]] = {}
    for lev in levels:
        s = item_set(lev)
        item_sets[lev.level_number] = s
        if lev.level_number in want:
            holes = [i for i in range(min(s), max(s) + 1) if i not in s] if s else []
            lines.append(
                f"  L{lev.level_number} {lev.name!r} n_distinct={len(s)} "
                f"min={min(s)} max={max(s)} holes={len(holes)} "
                f"has_114={114 in s}"
            )
            if lev.level_number == 0:
                lines.append(f"    items={sorted(s)}")
            if lev.level_number == 13:
                lines.append(f"    holes={holes[:40]}")

    # ---- T1 ----
    b0 = data[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
    lines.append(f"\n== T1(a) L0 first 512 @{LEVEL_BASE} ==")
    lines.append(hexdump_mac_roman(b0[:512]))
    lines.append("\n== T1(a) L0 last 256 ==")
    lines.append(hexdump_mac_roman(b0[-256:]))

    recs0 = [u16s(b0[i * 8 : (i + 1) * 8]) for i in range(N_REC)]
    lines.append("\n== T1(b) 1139 x 8-byte as 4 u16be ==")
    lines.extend(field_stats(recs0))

    # dpin 8-byte profile (from 596)
    dpin_body = dpin[596:]
    n_dpin = len(dpin_body) // 8
    recs_d = [u16s(dpin_body[i * 8 : (i + 1) * 8]) for i in range(n_dpin)]
    lines.append(f"\n== dpin 8-byte profile n={n_dpin} @596 ==")
    lines.extend(field_stats(recs_d))

    # T1(c) f0 == 114
    hits114 = [(i, recs0[i]) for i in range(N_REC) if recs0[i][0] == 114]
    any114 = [(i, recs0[i]) for i in range(N_REC) if 114 in recs0[i]]
    lines.append(f"\n== T1(c) f0==114 count={len(hits114)} {hits114[:10]} ==")
    lines.append(f"  any field==114 count={len(any114)} {any114[:15]}")

    # T1(d) record 114
    r114 = recs0[114]
    off114 = LEVEL_BASE + 114 * 8
    lines.append(f"\n== T1(d) record 114 @{off114} {b0[114*8:114*8+8].hex(' ')} u16={r114} ==")
    # neighbors
    for i in range(110, 119):
        lines.append(f"  rec[{i}] @{LEVEL_BASE+i*8} {b0[i*8:i*8+8].hex(' ')} {recs0[i]}")

    # T1(e) live counts + item index correspondence
    lines.append("\n== T1(e)(f) live-record counts vs map Item sets ==")
    for ln, name in ((0, "Ground Floor"), (6, "Ascension"), (13, "The Labyrinth")):
        blk = data[LEVEL_BASE + ln * LEVEL_STRIDE : LEVEL_BASE + (ln + 1) * LEVEL_STRIDE]
        recs = [u16s(blk[i * 8 : (i + 1) * 8]) for i in range(N_REC)]
        items = item_sets[ln]
        counts = {k: 0 for k in ("not_zero", "any_live", "f0_live", "not_empty_slot")}
        live_idx = {k: [] for k in counts}
        for i, r in enumerate(recs):
            dfn = nonempty_defs(r)
            for k, v in dfn.items():
                if v:
                    counts[k] += 1
                    live_idx[k].append(i)
        lines.append(f"\n  -- L{ln} {name} map_items={len(items)} --")
        for k in counts:
            idx = live_idx[k]
            first400 = sum(1 for i in idx if i < 400)
            in_items = sum(1 for i in idx if i in items)
            items_that_are_live = sum(1 for it in items if it < N_REC and nonempty_defs(recs[it])[k])
            lines.append(
                f"    {k}: live={counts[k]} in_0..399={first400} "
                f"live_idx_in_itemset={in_items}/{counts[k]} "
                f"itemset_that_are_live={items_that_are_live}/{len(items)}"
            )
        # first 20 live any_live indices
        lines.append(f"    any_live idx[:30]={live_idx['any_live'][:30]}")
        lines.append(f"    f0_live idx[:30]={live_idx['f0_live'][:30]}")
        # specifically: records at exact item indices
        empty_at_items = [it for it in sorted(items) if it < N_REC and recs[it] == (0, 0, 0, 0)]
        live_at_items = [it for it in sorted(items) if it < N_REC and recs[it] != (0, 0, 0, 0)]
        lines.append(f"    rec[item]!=0: {len(live_at_items)}  rec[item]==0: {len(empty_at_items)}")
        if ln == 0:
            lines.append(f"    rec[114]={recs[114]} rec[0]={recs[0]} rec[52]={recs[52]}")
            # dump all records whose index is a GF item
            lines.append("    records at GF Item indices:")
            for it in sorted(items):
                if it < N_REC:
                    lines.append(f"      [{it:4d}] {blk[it*8:it*8+8].hex(' ')} {recs[it]}")

    # T1(g) alternative layouts
    lines.append("\n== T1(g) 9112 minus header vs 4/6/8/12/16 ==")
    for hdr in (0, 4, 8, 12, 16, 20, 24, 32, 48, 64, 128, 256, 260, 512):
        rem = LEVEL_STRIDE - hdr
        parts = []
        for rs in (4, 6, 8, 12, 16):
            parts.append(f"{rs}:{'Y'+str(rem//rs) if rem%rs==0 else 'n'}")
        lines.append(f"  hdr={hdr} rem={rem} {' '.join(parts)}")

    # try 16-byte records (the ff fe pattern)
    recs16 = [struct.unpack_from(">8H", b0, i * 16) for i in range(LEVEL_STRIDE // 16)]
    lines.append(f"\n  16-byte records n={len(recs16)} first5={recs16[:5]}")
    z16 = sum(1 for r in recs16 if any(x not in (0, 0xFFFF, 0xFFFE) for x in r))
    lines.append(f"  16-byte 'any live'={z16}")

    # 12-byte from 0
    if LEVEL_STRIDE % 12 == 0:
        n12 = LEVEL_STRIDE // 12
        recs12 = [struct.unpack_from(">6H", b0, i * 12) for i in range(n12)]
        live12 = sum(1 for r in recs12 if any(x not in (0, 0xFFFF) for x in r))
        lines.append(f"  12-byte n={n12} any_live={live12}")

    # ---- T2 ----
    lines.append("\n== T2(a) bytes zero across all 25 levels ==")
    blocks = [
        data[LEVEL_BASE + i * LEVEL_STRIDE : LEVEL_BASE + (i + 1) * LEVEL_STRIDE]
        for i in range(N_LEVELS)
    ]
    all_zero = []
    all_same = []
    vary = []
    for i in range(LEVEL_STRIDE):
        col = [b[i] for b in blocks]
        if all(v == 0 for v in col):
            all_zero.append(i)
        elif len(set(col)) == 1:
            all_same.append((i, col[0]))
        else:
            vary.append(i)
    lines.append(f"  all-zero bytes: {len(all_zero)}")
    # cluster zero ranges
    ranges = []
    if all_zero:
        s = p = all_zero[0]
        for x in all_zero[1:]:
            if x == p + 1:
                p = x
            else:
                ranges.append((s, p, p - s + 1))
                s = p = x
        ranges.append((s, p, p - s + 1))
    lines.append(f"  all-zero ranges (start,end,len) count={len(ranges)}")
    for r in ranges:
        if r[2] >= 8:
            lines.append(f"    {r}")
    lines.append(f"  identical-nonzero bytes: {len(all_same)} first20={all_same[:20]}")
    lines.append(f"  varying bytes: {len(vary)}")

    # T2(b) u16 pairs in 0-31
    lines.append("\n== T2(b) adjacent u16be pairs both in 0..31 (L0) ==")
    coord_hits = []
    for i in range(0, LEVEL_STRIDE - 4, 2):
        x, y = struct.unpack_from(">2H", b0, i)
        if x <= 31 and y <= 31 and not (x == 0 and y == 0):
            coord_hits.append((i, x, y))
    lines.append(f"  count={len(coord_hits)} first40={coord_hits[:40]}")
    # also i16
    # door list from map GF
    gf = levels[0]
    doors = [(d.x, d.y) for d in gf.door_list if d.x != -1]
    lines.append(f"  GF doors={doors}")
    saves = [(i % 32, i // 32, gf.sector_list[i].item) for i in range(1024) if gf.sector_list[i].type == 9]
    lines.append(f"  GF saves={saves}")
    corpses = [(i % 32, i // 32, gf.sector_list[i].item) for i in range(1024) if gf.sector_list[i].type == 6]
    lines.append(f"  GF corpses={corpses}")

    # T2(c) bit density
    lines.append("\n== T2(c) bit-density per 32-byte window L0 ==")
    dense = []
    for i in range(0, LEVEL_STRIDE, 32):
        w = b0[i : i + 32]
        bits = sum(bin(b).count("1") for b in w)
        nz = sum(1 for b in w if b)
        dense.append((i, bits, nz, bits / (32 * 8)))
    dense_sorted = sorted(dense, key=lambda t: -t[3])
    lines.append("  top density windows:")
    for t in dense_sorted[:12]:
        lines.append(f"    @{t[0]} bits={t[1]} nz_bytes={t[2]} dens={t[3]:.3f} {b0[t[0]:t[0]+32].hex(' ')}")
    # look for windows that are not 8-byte-looking (few 00 00 prefixes)
    lines.append("  low-structure high-density (few 00 pairs):")
    for i, bits, nz, dens in dense:
        if dens > 0.35:
            pairs = sum(1 for j in range(0, 32, 2) if b0[i + j] == 0)
            if pairs <= 4:
                lines.append(f"    @{i} dens={dens:.3f} z_hi_bytes={pairs} {b0[i:i+32].hex(' ')}")

    # ---- T3 Bomb Code ----
    bn = BOMB_NEW.read_bytes()
    bo = BOMB_OLD.read_bytes()
    lines.append(f"\n== T3 Bomb Code new={len(bn)} old={len(bo)} ==")
    lines.append("-- exported --")
    lines.append(hexdump_mac_roman(bn))
    lines.append("-- 1995 tree --")
    lines.append(hexdump_mac_roman(bo))
    diffs = [(i, bo[i], bn[i]) for i in range(min(len(bo), len(bn))) if bo[i] != bn[i]]
    if len(bo) != len(bn):
        lines.append(f"  length differ {len(bo)} vs {len(bn)}")
    lines.append(f"  byte diffs={len(diffs)}")
    for i, a, b in diffs[:40]:
        lines.append(f"    @{i} {a:02x}->{b:02x}")
    # ascii / pascal
    ascii_runs = []
    i = 0
    while i < len(bn):
        if 32 <= bn[i] < 127:
            j = i
            while j < len(bn) and 32 <= bn[j] < 127:
                j += 1
            if j - i >= 4:
                ascii_runs.append((i, bn[i:j].decode("ascii")))
            i = j
        else:
            i += 1
    lines.append(f"  ascii>=4: {ascii_runs}")
    if bn and 1 <= bn[0] <= 40:
        lines.append(f"  pascal@0? {bn[1:1+bn[0]]!r}")
    u16_small = [(i, struct.unpack_from(">H", bn, i)[0]) for i in range(0, len(bn) - 1, 2)]
    lines.append(f"  u16be: {u16_small}")

    # ---- T4 RLE ----
    shapes = load_all_256()
    d195 = shapes[195]
    lines.append(f"\n== T4 rsrc 195 packed={len(d195)} u0=33144 ==")
    # follow-bytes after 00/01/02 from 257
    sl = d195[257:]
    lines.append("\n== T4(d) byte following 00/01/02 from @257 ==")
    for code in (0x00, 0x01, 0x02):
        follows: list[int] = []
        i = 0
        while i < len(sl) - 1:
            if sl[i] == code:
                follows.append(sl[i + 1])
                i += 2
            else:
                i += 1
        c = Counter(follows)
        in_pal = sum(1 for v in follows if 3 <= v <= 16)
        hi = sum(1 for v in follows if v >= 0x80)
        lines.append(
            f"  after {code:02x}: n={len(follows)} in3-16={in_pal} "
            f"ge80={hi} le2={sum(1 for v in follows if v<=2)} "
            f"top={c.most_common(12)}"
        )

    schemes = []
    for start in (257, 258, 23):
        src = d195[start:]
        for lit in ("plus1", "times2", "times4", "times8"):
            for rep in ("c_minus_7f", "highbit_plus1", "packbits", "none"):
                # swapped order: if we treat high as lit and low as rep — skip, that's different
                out, cons = decode_rle(src, lit, rep, target=33144)
                schemes.append((f"@{start} lit={lit} rep={rep}", len(out), cons, start + cons, len(src) - cons))
            out, cons = decode_rle(src, lit, "highbit_plus1")  # full, no target
            # also full length
        outn, consn = decode_nibble(src, target=33144)
        schemes.append((f"@{start} nibble", len(outn), consn, start + consn, len(src) - consn))
        outo, conso = decode_opcodes(src, target=33144)
        schemes.append((f"@{start} opcodes(00=copy8,01=rep2,02=nop,80+=hb)", len(outo), conso, start + conso, len(src) - conso))

    # also invert: C>=80 copy lits, else repeat
    def decode_swapped(src: bytes, lit_mode: str, target: int | None) -> tuple[bytes, int]:
        out = bytearray()
        i = 0
        n = len(src)
        while i < n:
            if target is not None and len(out) >= target:
                break
            c = src[i]
            i += 1
            if c < 0x80:
                if i >= n:
                    break
                val = src[i]
                i += 1
                count = c + 1
                take = count if target is None else min(count, target - len(out))
                out.extend(bytes([val]) * take)
            else:
                if lit_mode == "plus1":
                    count = (c & 0x7F) + 1
                elif lit_mode == "times8":
                    count = (c & 0x7F) * 8 or 8
                else:
                    count = (c & 0x7F) + 1
                take = min(count, n - i)
                if target is not None:
                    take = min(take, target - len(out))
                out.extend(src[i : i + take])
                i += min(count, n - i)
        return bytes(out), i

    for start in (257, 258):
        for lit in ("plus1", "times8"):
            out, cons = decode_swapped(d195[start:], lit, 33144)
            schemes.append((f"@{start} SWAP lit={lit} (low=rep,high=copy)", len(out), cons, start + cons, len(d195) - start - cons))

    lines.append("\n== T4(e) consume-until-33144 ==")
    lines.append(f"  packed_len={len(d195)}")
    exact = []
    for name, outn, cons, end, left in schemes:
        mark = ""
        if outn == 33144 and end == len(d195):
            mark = "  *** WIN consume-to-EOF ***"
            exact.append(name)
        elif outn == 33144:
            mark = "  HIT 33144"
        lines.append(f"  {name}: out={outn} cons={cons} end={end} left={left}{mark}")
    lines.append(f"  winners={exact}")

    # full (no target) lengths for best-looking
    lines.append("\n== T4 full-stream out vs 33144 (no target) @257/@258 ==")
    for start in (257, 258):
        src = d195[start:]
        for lit in ("plus1", "times8"):
            for rep in ("highbit_plus1", "c_minus_7f"):
                out, cons = decode_rle(src, lit, rep, target=None)
                lines.append(f"  @{start} {lit}/{rep} out={len(out)} d={len(out)-33144:+d} cons={cons} left={len(src)-cons}")
        out, cons = decode_nibble(src)
        lines.append(f"  @{start} nibble out={len(out)} d={len(out)-33144:+d} cons={cons}")
        out, cons = decode_opcodes(src)
        lines.append(f"  @{start} opcodes out={len(out)} d={len(out)-33144:+d} cons={cons}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
