# -*- coding: utf-8 -*-
"""Find every player-stat block and byte-diff slot 1 vs slot 2."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from round11_saves import ITEM_NAMES  # noqa: E402

SAVE = ROOT / "data/saves/Saved Games"
OUT = ROOT / "reference/docs/round11_saves3.txt"


def u16(d: bytes, i: int) -> int:
    return struct.unpack_from(">H", d, i)[0]


def u32(d: bytes, i: int) -> int:
    return struct.unpack_from(">I", d, i)[0]


def main() -> None:
    d = SAVE.read_bytes()
    n = len(d)
    lines: list[str] = []

    hp_pat = bytes.fromhex("00 3c 00 3c")
    lines.append("== HP 60/60 pattern 00 3c 00 3c ==")
    pos = 0
    hps = []
    while True:
        i = d.find(hp_pat, pos)
        if i < 0:
            break
        hps.append(i)
        pos = i + 1
    lines.append(f"  count={len(hps)} offs={hps}")
    for i in hps:
        lines.append(f"  @{i} {d[i-12:i+20].hex(' ')}")

    xy_pat = bytes.fromhex("00 06 00 02 00 01 80 ff")
    lines.append("\n== XY (6,2) + facing 00 01 80 ff ==")
    pos = 0
    xys = []
    while True:
        i = d.find(xy_pat, pos)
        if i < 0:
            break
        xys.append(i)
        pos = i + 1
    lines.append(f"  count={len(xys)} offs={xys}")
    for i in xys:
        lines.append(f"  @{i} {d[i-16:i+24].hex(' ')}")

    time_pat = bytes.fromhex("00 00 14 54")
    lines.append("\n== time 5204 00 00 14 54 ==")
    pos = 0
    times = []
    while True:
        i = d.find(time_pat, pos)
        if i < 0:
            break
        times.append(i)
        pos = i + 1
    lines.append(f"  count={len(times)} offs={times}")

    # any other u32 that looks like a short tick count near a second HP
    lines.append("\n== u32 time-like (1..50000) at HP-12 and HP-90 ==")
    for i in hps:
        for delta in (-90, -88, -86, -12, -10, -8, 20, 24):
            off = i + delta
            if 0 <= off <= n - 4:
                v = u32(d, off)
                if 1 <= v <= 200000:
                    lines.append(f"  HP@{i} {delta:+d} -> @{off} u32={v} ({v/60:.2f}s)")

    # if 2+ HP blocks, treat as slots
    if len(hps) >= 2:
        s = hps[1] - hps[0]
        lines.append(f"\n== inferred slot stride from HP pair: {s} ==")
        lines.append(f"  file/s = {n/s:.4f}  n%s={n%s}")
        # how many slots fit from 0
        nslots = 0
        for k in range(16):
            base = k * s
            if base + 2560 + 8 > n:
                break
            # check HP at 1876+base
            hp_off = 1876 + base
            ok = hp_off + 4 <= n and d[hp_off : hp_off + 4] == hp_pat
            lines.append(f"  slot{k} base={base} HP@1876+base={ok} " f"name0={d[base] if base<n else '-'}")
            nslots += 1

        # COMPLETE diff slot0 vs slot1 for min(s, remaining)
        a0 = 0
        a1 = s
        length = min(s, n - a1)
        diffs = []
        for i in range(length):
            if d[a0 + i] != d[a1 + i]:
                diffs.append(i)
        lines.append(f"\n== T2 slot0 vs slot1 stride={s} len={length} ndiff={len(diffs)} ==")
        # cluster diffs
        if diffs:
            clusters = []
            start = prev = diffs[0]
            for x in diffs[1:]:
                if x <= prev + 8:
                    prev = x
                    continue
                clusters.append((start, prev, prev - start + 1))
                start = prev = x
            clusters.append((start, prev, prev - start + 1))
            lines.append(f"  clusters={len(clusters)}")
            for a, b, c in clusters[:40]:
                lines.append(f"    {a}..{b} span={c}")

        # print EVERY diff in the player-header region (0..4096) with context
        lines.append("\n== T2 EVERY diff in 0..4096 (slot-relative) ==")
        hdr_diffs = [i for i in diffs if i < 4096]
        lines.append(f"  count={len(hdr_diffs)}")
        for i in hdr_diffs:
            v1, v2 = d[a0 + i], d[a1 + i]
            ctx1 = d[max(0, a0 + i - 8) : a0 + i + 8]
            note = ""
            if i == 1786 or (1786 <= i <= 1789):
                note = " TIME"
            if 1876 <= i <= 1879:
                note = " HP"
            if 2328 <= i <= 2331:
                note = " XY"
            if v1 == 0x72 or v2 == 0x72 or i16_hit(d, a0, a1, i, 114):
                note += " **114**"
            if (v1 ^ v2) and bit114_flip(i, v1, v2):
                note += " **bit114-ish**"
            lines.append(
                f"  +{i:5d} {v1:02x}->{v2:02x}  s1={ctx1.hex(' ')}{note}"
            )

        # inventory both
        lines.append("\n== inventories at 2560+k*s ==")
        for k in range(min(4, nslots)):
            base = k * s + 2560
            lines.append(f"  -- slot{k} inv @{base} --")
            for j in range(20):
                rec = d[base + j * 8 : base + j * 8 + 8]
                if rec == b"\x00" * 8:
                    continue
                iid = u16(rec, 0) if len(rec) == 8 else 0
                if len(rec) < 8:
                    break
                a, b, c, e = struct.unpack(">4H", rec)
                if a == 0xFFFF and b > 256:
                    break
                lines.append(
                    f"    [{j}] {rec.hex(' ')} {ITEM_NAMES.get(a, '?')} st={b} q={c} cat={e}"
                )

        # 114 tests between the two slots
        lines.append("\n== T2(c) 114-specific ==")
        # i16 114 in each slot player region
        for k in range(2):
            hits = []
            base = k * s
            for i in range(length - 1):
                if d[base + i : base + i + 2] == b"\x00\x72":
                    hits.append(i)
            lines.append(f"  slot{k} i16be 114 at rel {hits[:40]} n={len(hits)}")
        # bytes that are 0 in slot0 and 114 in slot1 or vice versa
        appear = [i for i in diffs if d[a0 + i] != d[a1 + i] and 114 in (d[a0 + i], d[a1 + i])]
        lines.append(f"  diffs where a byte value is 114: {[(i, d[a0+i], d[a1+i]) for i in appear[:30]]}")
        # i16 that became 114
        i16_appear = []
        for i in range(0, length - 1):
            v0 = u16(d, a0 + i)
            v1 = u16(d, a1 + i)
            if v0 != v1 and 114 in (v0, v1):
                i16_appear.append((i, v0, v1))
        lines.append(f"  i16be diffs involving 114: {i16_appear[:40]}")

        # bit 114 of a bitmap: byte 14 of some region
        # check if any diff is at slot-rel offset 14 + 50*level or similar
        bit_offs = [14, 14 + 50, 14 + 128]
        for off in range(0, min(length, 8000)):
            if off % 50 == 14 or off % 128 == 14:
                if off in diffs:
                    lines.append(
                        f"  diff at bitmap-ish +{off} {d[a0+off]:02x}->{d[a1+off]:02x}"
                    )

    # all (6,2) u16 pairs
    lines.append("\n== all u16be 6,2 adjacent (aligned) ==")
    for i in range(0, n - 4, 2):
        if u16(d, i) == 6 and u16(d, i + 2) == 2:
            lines.append(f"  @{i} {d[i-8:i+16].hex(' ')}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest} lines={len(lines)}")


def i16_hit(d: bytes, a0: int, a1: int, i: int, val: int) -> bool:
    for off in (i - 1, i):
        if off < 0:
            continue
        if a0 + off + 2 <= len(d) and struct.unpack_from(">H", d, a0 + off)[0] == val:
            return True
        if a1 + off + 2 <= len(d) and struct.unpack_from(">H", d, a1 + off)[0] == val:
            return True
    return False


def bit114_flip(off: int, v1: int, v2: int) -> bool:
    """True if this byte is the 114th bit of some bitmap starting at 0 (byte 14)."""
    return off == 14 or (off % 50 == 14) or (off % 128 == 14)


if __name__ == "__main__":
    main()
