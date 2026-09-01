# -*- coding: utf-8 -*-
"""Round 13: AAA vs AAB pickup diff + .256 per-row / column RLE."""

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
from round12_level_rle import decode_opcodes, decode_rle  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games AAA-AAB"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round13_pickup_rle.txt"
AAA_OUT = ROOT / "reference/saves/save_AAA"
AAB_OUT = ROOT / "reference/saves/save_AAB"

LEVEL_BASE = 39392
LEVEL_STRIDE = 9112
N_LEVELS = 25
INV_OFF = 0x0A00
TIME_OFF = 0x074A
HP_OFF = 0x0754
LEVEL_OFF = 0x090C
X_OFF = 0x0918
Y_OFF = 0x091A
FACING_OFF = 0x091C

ITEM_NAMES: dict[int, str] = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flash light",
    0x06: "Canvas sack",
    0x16: "Mein Kampf",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x33: "Walther P4 Ammo",
}


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def rec4(data: bytes, off: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", data, off)


def pascal_at(data: bytes, off: int) -> str:
    n = data[off]
    if n > 127:
        return f"<len {n}>"
    return data[off + 1 : off + 1 + n].decode("mac_roman", errors="replace")


def inventory_records(data: bytes, start: int = INV_OFF, limit: int = 80) -> list[tuple[int, tuple[int, int, int, int]]]:
    out = []
    for i in range(limit):
        off = start + i * 8
        if off + 8 > len(data):
            break
        rec = rec4(data, off)
        out.append((off, rec))
        if rec[0] == 0xFFFF:
            break
    return out


def live_packed(block: bytes, start: int = 256) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Return (count, term_offset_in_block, records) for FFFF-terminated list from +256."""
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return len(recs), off, recs
        recs.append(rec)
        off += 8
    return len(recs), off, recs


def find_runs(diffs: list[int]) -> list[tuple[int, int]]:
    if not diffs:
        return []
    runs = []
    s = prev = diffs[0]
    for o in diffs[1:]:
        if o == prev + 1:
            prev = o
            continue
        runs.append((s, prev))
        s = prev = o
    runs.append((s, prev))
    return runs


def classify_offset(off: int) -> str:
    if TIME_OFF <= off <= TIME_OFF + 3:
        return "clock"
    if X_OFF <= off <= X_OFF + 1:
        return "position_x"
    if Y_OFF <= off <= Y_OFF + 1:
        return "position_y"
    if FACING_OFF <= off <= FACING_OFF + 3:
        return "facing"
    if LEVEL_OFF <= off <= LEVEL_OFF + 1:
        return "level"
    if HP_OFF <= off <= HP_OFF + 3:
        return "hp"
    if INV_OFF <= off < LEVEL_BASE:
        return "inventory_region"
    l0 = LEVEL_BASE
    l0_end = LEVEL_BASE + LEVEL_STRIDE - 1
    if l0 <= off <= l0_end:
        return "level0_block"
    if LEVEL_BASE <= off < LEVEL_BASE + N_LEVELS * LEVEL_STRIDE:
        n = (off - LEVEL_BASE) // LEVEL_STRIDE
        return f"level{n}_block"
    return "other"


def hex16(data: bytes, off: int) -> str:
    lo = max(0, off)
    chunk = data[lo : lo + 16]
    return chunk.hex(" ")


# ---------------------------------------------------------------------------
# Save-file structure: locate two game bodies
# ---------------------------------------------------------------------------


def probe_structure(data: bytes, lines: list[str]) -> tuple[bytes, bytes]:
    lines.append(f"== file size {len(data)} (0x{len(data):X}) ==")
    lines.append(f"name@0={pascal_at(data, 0)!r}  name@128={pascal_at(data, 128)!r}")
    lines.append("name slot 0:")
    lines.append(hexdump_mac_roman(data[0:128]))
    lines.append("name slot 1:")
    lines.append(hexdump_mac_roman(data[128:256]))

    # how many 128-byte name slots?
    nslots = 0
    for i in range(16):
        off = i * 128
        n = data[off]
        if 1 <= n <= 31 and all(32 <= b < 127 for b in data[off + 1 : off + 1 + n]):
            nslots += 1
            lines.append(f"  name_slot[{i}] @{off} {pascal_at(data, off)!r}")
        else:
            break
    lines.append(f"leading name slots: {nslots}")

    # known fields as if single-body (AAA at 0, body shared)
    lines.append("\n== single-body view (offsets from file start) ==")
    if len(data) > FACING_OFF + 4:
        lines.append(
            f"  time@{TIME_OFF}={u32(data, TIME_OFF)} "
            f"hp={u16(data, HP_OFF)}/{u16(data, HP_OFF + 2)} "
            f"level={u16(data, LEVEL_OFF)} "
            f"xy=({u16(data, X_OFF)},{u16(data, Y_OFF)}) "
            f"facing={data[FACING_OFF:FACING_OFF+4].hex()}"
        )
        inv = inventory_records(data)
        lines.append(f"  inventory n={len(inv)}")
        for off, rec in inv:
            name = ITEM_NAMES.get(rec[0], "?")
            lines.append(f"    @{off} {rec} {name}")

    # search for second inventory-like knife / walther ammo
    knife = struct.pack(">4H", 0x2D, 0, 0, 0)  # may not match exactly
    lines.append("\n== search inventory-shaped records ==")
    for iid, label in [(0x2D, "knife"), (0x33, "wammo"), (0x2E, "walther"), (0x01, "watch")]:
        hits = []
        i = 0
        pat = struct.pack(">H", iid)
        while True:
            j = data.find(pat, i)
            if j < 0:
                break
            if j % 2 == 0 and j + 8 <= len(data):
                rec = rec4(data, j)
                if rec[0] == iid and rec[3] in (0, 1, 0xFFFF) or (rec[0] == iid and rec[2] < 10000):
                    hits.append((j, rec))
            i = j + 1
        lines.append(f"  {label} id=0x{iid:02X} aligned-ish hits={len(hits)}")
        for j, rec in hits[:12]:
            lines.append(f"    @{j} {rec}")

    # autocorrelation-ish: find another copy of bytes around X/Y
    xy = data[X_OFF : X_OFF + 4]
    lines.append(f"\n== repeats of xy bytes {xy.hex()} ==")
    i = 0
    hits = []
    while True:
        j = data.find(xy, i)
        if j < 0:
            break
        hits.append(j)
        i = j + 1
    lines.append(f"  n={len(hits)} first={hits[:20]}")

    # try equal split after 256-byte name table
    body_len = (len(data) - 256) // 2
    lines.append(f"\n== equal-split after 256-byte names: body_len={body_len} ==")
    a = data[256 : 256 + body_len]
    b = data[256 + body_len : 256 + 2 * body_len]
    same = sum(1 for i in range(min(len(a), len(b))) if a[i] == b[i])
    lines.append(f"  a==b bytes {same}/{len(a)} frac={same / len(a):.4f}")

    # try: two full copies starting at 0 and some stride
    # scan strides where data[s:s+16]==data[0:16] (AAA name) — none expected
    # scan for second time/level/xy cluster
    lines.append("\n== scan for second player-state cluster (level=0, x<32, y<32) ==")
    clusters = []
    for off in range(0, len(data) - 20, 2):
        lev = u16(data, off)
        if lev != 0:
            continue
        # level at 0x090C, x at +0x0C
        if off + 0x10 >= len(data):
            continue
        x = u16(data, off + 0x0C)
        y = u16(data, off + 0x0E)
        if x < 32 and y < 32:
            clusters.append((off, x, y, data[off + 0x10 : off + 0x14].hex()))
    # filter to those where off looks like LEVEL_OFF + k*stride
    lines.append(f"  raw level0+xy32 clusters={len(clusters)}")
    for c in clusters[:30]:
        lines.append(f"    level@{c[0]} xy=({c[1]},{c[2]}) facing={c[3]}")

    # XOR / byte-diff of two halves of the file
    half = len(data) // 2
    nd = sum(1 for i in range(half) if data[i] != data[i + half])
    lines.append(f"\n== half-file diffs: {nd}/{half}")

    # If names are a directory and bodies are sequential after a fixed
    # name table of N reserved slots (try 8, 10, 16).
    for nres in (2, 4, 8, 10, 16):
        hdr = nres * 128
        rest = len(data) - hdr
        if rest % 2:
            continue
        bl = rest // 2
        aa = data[hdr : hdr + bl]
        bb = data[hdr + bl : hdr + 2 * bl]
        same = sum(1 for i in range(bl) if aa[i] == bb[i])
        lines.append(f"  reserved_names={nres} hdr={hdr} body={bl} identical={same}/{bl} ({same / bl:.4f})")

    # Default: treat as ONE body (AAB last-write) unless we find two.
    # Also try: AAA body is the whole file; AAB is a delta stored at the end.
    extra = len(data) - 267452
    lines.append(f"\n== vs previous single-save size 267452: extra={extra} ==")
    if extra > 0:
        lines.append("tail extra:")
        lines.append(hexdump_mac_roman(data[-min(extra + 32, 256) :]))

    # Compare first 267452 of new vs old if old exists
    oldp = ROOT / "reference/saves/Saved Games"
    if oldp.exists():
        old = oldp.read_bytes()
        m = min(len(old), len(data))
        nd = sum(1 for i in range(m) if old[i] != data[i])
        lines.append(f"  vs old Saved Games: {nd} diffs in first {m}")

    return data, data  # placeholder; refined after probe prints


def extract_two_games(data: bytes, lines: list[str]) -> tuple[bytes, bytes] | None:
    """If two near-identical bodies exist, return (aaa, aab)."""
    # Hypothesis: after 2×128 names, two equal bodies.
    hdr = 256
    rest = len(data) - hdr
    if rest % 2 == 0:
        bl = rest // 2
        aa, bb = data[hdr : hdr + bl], data[hdr + bl :]
        # check player fields at relative 0x090C-256? or absolute within body
        # Body may start at file offset 0 with names included — try stride
        pass

    # Hypothesis: two full file-sized records concatenated after shared prefix.
    # Search for a second occurrence of the 256-byte level-block header pattern.
    hdr_pat = data[LEVEL_BASE : LEVEL_BASE + 16]
    lines.append(f"\n== L0 header pattern {hdr_pat.hex()} repeats ==")
    i = 0
    hits = []
    while True:
        j = data.find(hdr_pat, i)
        if j < 0:
            break
        hits.append(j)
        i = j + 1
    lines.append(f"  hits={hits}")

    # Hypothesis: slot stride S where inventory at 0x0A00 and 0x0A00+S both look valid
    lines.append("\n== stride hunt (inventory at 0x0A00 and 0x0A00+S both FFFF-terminated) ==")
    inv0 = inventory_records(data, INV_OFF)
    lines.append(f"  inv@0x0A00 n={len(inv0)} last={inv0[-1] if inv0 else None}")
    candidates = []
    for s in range(128, len(data) - INV_OFF - 64, 8):
        if INV_OFF + s + 16 >= len(data):
            break
        rec0 = rec4(data, INV_OFF + s)
        if rec0[0] > 0x80 and rec0[0] != 0xFFFF:
            continue
        invs = inventory_records(data, INV_OFF + s, limit=40)
        if not invs:
            continue
        ids = [r[0] for _, r in invs]
        if 0x2D in ids or 0x33 in ids or 0x01 in ids:
            if invs[-1][1][0] == 0xFFFF and 2 <= len(invs) <= 30:
                candidates.append((s, len(invs), invs[:6]))
    lines.append(f"  candidate strides={len(candidates)}")
    for s, n, sample in candidates[:15]:
        lines.append(f"    S={s} n={n} sample={sample}")

    return None


def decode_plus1_highbit(src: bytes, target: int | None = None) -> tuple[bytes, int]:
    return decode_rle(src, "plus1", "highbit_plus1", target)


def decode_times8_highbit(src: bytes, target: int | None = None) -> tuple[bytes, int]:
    return decode_rle(src, "times8", "highbit_plus1", target)


def per_row_decode(src: bytes, row: int, cols: int, decoder) -> tuple[bytes, int, list[int]]:
    """Decode resetting at each row boundary. decoder(src)->(out, consumed)."""
    out = bytearray()
    i = 0
    n = len(src)
    consumed_at_row = []
    for r in range(row):
        chunk, used = decoder(src[i:], target=cols)
        out.extend(chunk[:cols])
        if len(chunk) < cols:
            consumed_at_row.append(i + used)
            return bytes(out), i + used, consumed_at_row
        i += used
        consumed_at_row.append(i)
        if i >= n:
            break
    return bytes(out), i, consumed_at_row


def main() -> None:
    data = SAVE.read_bytes()
    lines: list[str] = []

    probe_structure(data, lines)
    extract_two_games(data, lines)

    # Also dump known offsets + L0 live count immediately (single-body)
    lines.append("\n========== TASK 2(a) single-body L0 live counts ==========")
    for label, blob in [("FILE", data)]:
        if LEVEL_BASE + LEVEL_STRIDE <= len(blob):
            block = blob[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
            n, term, recs = live_packed(block)
            lines.append(f"  {label} L0 live={n} term_off={term} first3={recs[:3]} last3={recs[-3:]}")

    # .256 Task 5 — can run regardless of save split
    lines.append("\n========== TASK 5 .256 RLE ==========")
    shapes = load_all_256()
    fc = [195, 196, 197, 198, 199, 200, 201, 202]
    for rid in fc:
        blob = shapes[rid]
        lines.append(f"\n-- rsrc {rid} size={len(blob)} --")
        lines.append(f"  bytes[240:280]={blob[240:280].hex(' ')}")
        u16s = [u16(blob, o) for o in range(240, 280, 2)]
        u32s = [u32(blob, o) for o in range(240, 280, 4)]
        lines.append(f"  u16be[240:280]={u16s}")
        lines.append(f"  u32be[240:280]={u32s}")
        # known 128 at 20 and 244, 16384 at 249
        lines.append(f"  u16@20={u16(blob, 20)} u16@244={u16(blob, 244)} u32@249={u32(blob, 249)}")

    # 5a per-row reset
    lines.append("\n== T5(a) per-row reset (128 rows x 128) ==")
    schemes = {
        "plus1+highbit": lambda s, target=None: decode_rle(s, "plus1", "highbit_plus1", target),
        "times8+highbit": lambda s, target=None: decode_rle(s, "times8", "highbit_plus1", target),
        "opcodes00=copy8": decode_opcodes,
    }
    for rid in (195, 196, 198):
        packed = shapes[rid][257:]
        packed258 = shapes[rid][258:]
        for start_name, src in (("257", packed), ("258", packed258)):
            for sname, dec in schemes.items():
                out, used, rows = per_row_decode(src, 128, 128, dec)
                lines.append(
                    f"  {rid} @{start_name} {sname}: out={len(out)} used={used}/{len(src)} "
                    f"rows_done={len(rows)} leftover={len(src) - used}"
                )

    # 5b row-length prefixes
    lines.append("\n== T5(b) u16be row-length prefixes ==")
    for rid in fc:
        for start in (257, 258, 280):
            src = shapes[rid][start:]
            ok = True
            total = 0
            lens = []
            p = 0
            for r in range(128):
                if p + 2 > len(src):
                    ok = False
                    break
                ln = u16(src, p)
                lens.append(ln)
                p += 2
                if ln > 400 or p + ln > len(src):
                    ok = False
                    break
                p += ln
                total += ln
            lines.append(
                f"  {rid} @{start}: ok={ok} consumed={p}/{len(src)} "
                f"sum_lens={total} leftover={len(src) - p if ok else 'n/a'} "
                f"lens_minmax=({min(lens) if lens else '-'},{max(lens) if lens else '-'}) "
                f"first8={lens[:8]}"
            )

    # 5c row offset table in first 512
    lines.append("\n== T5(c) row offset table in first 512 ==")
    for rid in (195, 198):
        blob = shapes[rid]
        for off, width, count in (
            (0, 2, 128),
            (7, 2, 128),
            (20, 2, 128),
            (240, 2, 128),
            (244, 2, 128),
            (249, 2, 128),
            (256, 2, 128),
            (0, 4, 128),
            (7, 4, 128),
            (240, 4, 128),
            (249, 4, 128),
        ):
            if off + width * count > len(blob):
                continue
            if width == 2:
                vals = [u16(blob, off + i * 2) for i in range(count)]
            else:
                vals = [u32(blob, off + i * 4) for i in range(count)]
            # a row table should be increasing and land inside the file
            inc = sum(1 for i in range(1, count) if vals[i] > vals[i - 1])
            inrange = sum(1 for v in vals if 0 <= v <= len(blob))
            lines.append(
                f"  {rid} table@{off} u{width*8} n={count}: "
                f"inc={inc} inrange={inrange} first8={vals[:8]} last4={vals[-4:]}"
            )

    # 5d leftover after max output
    lines.append("\n== T5(d) leftover after max output (target 33144) ==")
    for rid in fc:
        for start in (257, 258):
            src = shapes[rid][start:]
            for sname, dec in (
                ("plus1+highbit", lambda s, t=None: decode_rle(s, "plus1", "highbit_plus1", t)),
                ("times8+highbit", lambda s, t=None: decode_rle(s, "times8", "highbit_plus1", t)),
                ("opcodes", decode_opcodes),
            ):
                out, used = dec(src, 33144)
                leftover = src[used:]
                lines.append(
                    f"  {rid} @{start} {sname}: out={len(out)} used={used} "
                    f"remain={len(leftover)} remain_hex={leftover[:32].hex(' ') if leftover else ''}"
                )

    # 5e column-major: 128 columns of 128
    lines.append("\n== T5(e) COLUMN-major 128 columns x 128 ==")
    for rid in (195, 196, 198):
        for start in (257, 258):
            src = shapes[rid][start:]
            for sname, dec in schemes.items():
                # decode as if 128 columns, reset each column (same as per-row!)
                out, used, cols = per_row_decode(src, 128, 128, dec)
                lines.append(
                    f"  {rid} @{start} {sname} col-reset: out={len(out)} used={used}/{len(src)} "
                    f"cols_done={len(cols)} leftover={len(src) - used}"
                )
                # also: decode whole stream then reshape column-major (no reset)
                out2, used2 = dec(src, 16384)
                lines.append(
                    f"    stream-to-16384: out={len(out2)} used={used2} leftover={len(src) - used2}"
                )
            # raw 16384 from start as columns
            raw = src[:16384]
            lines.append(f"  {rid} @{start} raw[:16384] avail={min(16384, len(src))}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines)")
    # also print the head so the chat can start Task 2 immediately
    print("\n".join(lines[:80]))


if __name__ == "__main__":
    main()
