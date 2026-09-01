# -*- coding: utf-8 -*-
"""Round 11: real Saved Games — slot stride, John Doe 114, documented fields."""

from __future__ import annotations

import hashlib
import struct
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

SAVE = ROOT / "data/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DPIN = ROOT / "reference/dpin_128.bin"
OUT = ROOT / "reference/docs/round11_saves.txt"

ITEM_NAMES: dict[int, str] = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flash light",
    0x03: "IR goggles",
    0x04: "Cuban gas mask",
    0x06: "Canvas sack",
    0x08: "Aromatic box",
    0x09: "Velvet red bag",
    0x0A: "Lead box",
    0x0C: "Empty elaborate vial",
    0x0E: "Red cloak",
    0x10: "Nuclear device",
    0x11: "Radio beacon",
    0x12: "Blue liquid vial",
    0x13: "Red liquid vial",
    0x14: "Brown liquid vial",
    0x15: "Violet liquid vial",
    0x16: "Mein Kampf",
    0x17: "Small pamphlet",
    0x18: "Bird's Egg",
    0x1C: "Bad Walther P4",
    0x2C: "Ceremonial Mask",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x30: "Schmeisser MP-41",
    0x31: "AK-47",
    0x32: "M-79 Grenade Launcher",
    0x33: "Walther P4 Ammo",
    0x40: "Yellow Crystal",
    0x41: "Blue Crystal",
    0x42: "Orange Crystal",
    0x44: "Mottled Crystal",
    0x45: "Green Crystal",
    0x46: "Black Crystal",
}


def rec8(block: bytes, i: int) -> tuple[int, int, int, int]:
    return struct.unpack_from(">4H", block, i * 8)


def main() -> None:
    data = SAVE.read_bytes()
    n = len(data)
    lines: list[str] = []

    lines.append(f"== T1(a) size={n} (0x{n:X}) ==")
    lines.append(hexdump_mac_roman(data[:512]))

    lines.append("\n== zip listing ==")
    zpath = ROOT / "data/saves/Saved Games.zip"
    if zpath.exists():
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                lines.append(f"  {info.filename!r} size={info.file_size}")

    # --- T1 slot hunt ---
    lines.append("\n== T1 name / score-string hits ==")
    for needle in (b"Pathways", b"You have scored", b"Ground Floor", b"uncompress_world"):
        pos = 0
        hits = []
        while True:
            i = data.find(needle, pos)
            if i < 0:
                break
            hits.append(i)
            pos = i + 1
        lines.append(f"  {needle!r} count={len(hits)} offs={hits[:12]}")

    lines.append("\n== T1(c) 256-byte window duplicates step=8 ==")
    seen: dict[bytes, list[int]] = defaultdict(list)
    for i in range(0, n - 256, 8):
        seen[hashlib.md5(data[i : i + 256]).digest()].append(i)
    pair_gaps: list[int] = []
    for offs in seen.values():
        if len(offs) == 2:
            pair_gaps.append(offs[1] - offs[0])
    gap_c = Counter(pair_gaps)
    lines.append(f"  2-copy windows={len(pair_gaps)} most_common_gaps={gap_c.most_common(15)}")
    multi = [(len(v), v[1] - v[0] if len(v) > 1 else 0, v[:6]) for v in seen.values() if len(v) >= 3]
    multi.sort(reverse=True)
    lines.append(f"  3+ copy window kinds={len(multi)} top={multi[:8]}")

    # adjacent-pair rates at 512-aligned and cheat-related sizes
    lines.append("\n== T1 adjacent pair data[0:s]==data[s:2s] ==")
    trial = list(range(512, 70000, 512))
    trial += [25600, 26624, 26745, 27136, 28672, 30720, 32768, 33431, 38400, 40960, 44575, 49152, 53490, 65536]
    trial += [h for h in range(25000, 36000, 64)]
    best: list[tuple[float, int, int]] = []
    for s in sorted(set(trial)):
        if 2 * s > n:
            continue
        eq = sum(1 for a, b in zip(data[:s], data[s : 2 * s], strict=True) if a == b)
        best.append((eq / s, eq, s))
    best.sort(reverse=True)
    for rate, eq, s in best[:20]:
        lines.append(f"  s={s:6d} rate={rate:.6f} {eq}/{s}")

    # header + k slots exact divide, rate slot0 vs slot1
    lines.append("\n== T1 header+k exact divide, slot0 vs slot1 rate>=0.5 ==")
    arr = np.frombuffer(data, dtype=np.uint8)
    for h in (0, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1280, 2048):
        for k in range(2, 17):
            if (n - h) % k:
                continue
            s = (n - h) // k
            if not (4000 <= s <= 80000) or h + 2 * s > n:
                continue
            rate = float(np.mean(arr[h : h + s] == arr[h + s : h + 2 * s]))
            if rate >= 0.50:
                # unused slot3 vs slot0
                r03 = float(np.mean(arr[h : h + s] == arr[h + 2 * s : h + 3 * s])) if h + 3 * s <= n else -1
                lines.append(f"  H={h} k={k} S={s} r01={rate:.4f} r02={r03:.4f}")

    # stride_finder-style on a reduced set (every 64 from 4k-70k) of WHOLE file
    lines.append("\n== T1(b) reduced autocorrelation (step 64, 4096..70000) ==")
    ac: list[tuple[float, int, int, int]] = []
    for s in range(4096, min(70000, n // 2) + 1, 64):
        a = arr[:-s]
        b = arr[s:]
        live = (a != 0) | (b != 0)
        count = int(live.sum())
        if count == 0:
            continue
        hits = int(((a == b) & live).sum())
        ac.append((hits / count, hits, count, s))
    ac.sort(reverse=True)
    for i, (sc, hits, live, s) in enumerate(ac[:20], 1):
        lines.append(
            f"  {i:2d} stride={s:6d} score={sc:.6f} matched={hits} live={live} divides={n % s == 0}"
        )
    # refine ±64 around top 5
    lines.append("  refine ±32 around top 5:")
    refined: list[tuple[float, int, int]] = []
    for _, _, _, center in ac[:5]:
        for s in range(max(256, center - 32), min(n // 2, center + 33)):
            a = arr[:-s]
            b = arr[s:]
            live = (a != 0) | (b != 0)
            count = int(live.sum())
            if not count:
                continue
            hits = int(((a == b) & live).sum())
            refined.append((hits / count, hits, s))
    refined.sort(reverse=True)
    seen_s = set()
    shown = 0
    for sc, hits, s in refined:
        if s in seen_s:
            continue
        seen_s.add(s)
        lines.append(f"    stride={s} score={sc:.6f} matched={hits}")
        shown += 1
        if shown >= 15:
            break

    # zero / unused
    lines.append("\n== T1(d) zero fill ==")
    lines.append(f"  zeros={data.count(0)}/{n} = {data.count(0)/n:.4f}")
    runs = []
    i = 0
    while i < n:
        if data[i] == 0:
            j = i
            while j < n and data[j] == 0:
                j += 1
            if j - i >= 256:
                runs.append((i, j - i))
            i = j
        else:
            i += 1
    lines.append(f"  zero-runs>=256: {len(runs)} longest={max((r[1] for r in runs), default=0)}")
    lines.append(f"  first10={runs[:10]}")

    # --- documented offsets ---
    lines.append("\n== T3 documented absolute offsets (ItemCheat) ==")
    cheat_offs = {
        "time_1786": 1786,
        "X_1868": 1868,
        "Y_1872": 1872,
        "level_1875": 1875,
        "hp_1877": 1877,
        "hpmax_1879": 1879,
        "inv_2560": 2560,
    }
    hex_offs = {"hex_level_line1856": 1856, "hex_vert_1872": 1872}
    for name, off in {**cheat_offs, **hex_offs}.items():
        chunk = data[off : off + 16]
        u16 = struct.unpack_from(">H", data, off)[0] if off + 2 <= n else 0
        u32 = struct.unpack_from(">I", data, off)[0] if off + 4 <= n else 0
        lines.append(f"  {name}@{off}: u8={data[off]:02x} u16be={u16} u32be={u32}  {chunk.hex(' ')}")

    # inventory dump at 2560
    lines.append("\n== T4 candidate inventory @2560 (32 x 8) ==")
    for i in range(32):
        off = 2560 + i * 8
        a, b, c, e = rec8(data, (off) // 8) if off % 8 == 0 else struct.unpack_from(">4H", data, off)
        a, b, c, e = struct.unpack_from(">4H", data, off)
        name = ITEM_NAMES.get(a, ITEM_NAMES.get(data[off + 1], "?"))
        lines.append(
            f"  [{i:2d}] @{off} {data[off:off+8].hex(' ')}  u16=({a},{b},{c},{e}) "
            f"b1={data[off+1]:02x}({ITEM_NAMES.get(data[off+1], '?')})"
        )

    # search starting loadout cluster
    lines.append("\n== T4 search for knife 0x2D / flashlight 0x02 / watch 0x01 / map 0x00 cluster ==")
    # look for 8-byte aligned 00 2D
    knife_hits = []
    for off in range(0, n - 8, 2):
        if data[off : off + 2] == b"\x00\x2d":
            knife_hits.append(off)
    lines.append(f"  u16be 0x002D count={len(knife_hits)} offs={knife_hits[:40]}")
    for off in knife_hits[:20]:
        lines.append(f"    @{off} ctx={data[max(0,off-16):off+24].hex(' ')}")

    # search 6,2 and 24,8 encodings
    lines.append("\n== T3(c) encodings of (6,2) and (24,8) with nearby 0 ==")
    hits62 = []
    for i in range(0, n - 8):
        if data[i : i + 2] == b"\x00\x06" and data[i + 4 : i + 6] == b"\x00\x02":
            hits62.append(("u16be 6 .. 2", i))
        if data[i : i + 2] == b"\x00\x06" and data[i + 2 : i + 4] == b"\x00\x02":
            hits62.append(("u16be 6,2 adj", i))
        if data[i : i + 2] == b"\x00\x18" and data[i + 4 : i + 6] == b"\x00\x08":
            hits62.append(("u16be 24 .. 8", i))
        if data[i] == 6 and data[i + 1] == 2:
            hits62.append(("bytes 6,2", i))
        if data[i] == 0x18 and data[i + 1] == 0x08:
            hits62.append(("bytes 24,8", i))
    # keep those with a 0 within ±8 bytes
    shown = 0
    for kind, i in hits62:
        window = data[max(0, i - 8) : i + 16]
        if 0 in window or True:
            if shown < 60:
                lines.append(f"  {kind} @{i} {window.hex(' ')}")
                shown += 1
    lines.append(f"  total encoding hits={len(hits62)} shown={shown}")

    # i16 114
    lines.append("\n== T2(c) file-wide i16be==114 (0x0072) ==")
    hits114 = [i for i in range(0, n - 1, 1) if data[i : i + 2] == b"\x00\x72"]
    lines.append(f"  count={len(hits114)} offs={hits114[:80]}")

    # Ground Floor map check
    levels = load_maps(MAPS)
    gf = levels[0]
    lines.append(f"\n== T5 map Ground Floor name={gf.name!r} level_number={gf.level_number} ==")
    for x, y in ((6, 2), (26, 2), (5, 10), (27, 10), (14, 6)):
        sec = gf.sector_at(x, y)
        lines.append(
            f"  ({x},{y}) type={sec.type} item={sec.item} addl={sec.type_addl}"
        )

    # dpin 8-byte compare later once inventory found
    if DPIN.exists():
        dpin = DPIN.read_bytes()
        lines.append(f"\n== dpin size={len(dpin)} prefix=596 ==")
        # show a couple template rows matching knife
        for g in range(20):
            chunk = dpin[596 + g * 80 : 596 + (g + 1) * 80]
            ids = [chunk[i * 8 + 1] for i in range(10)]
            if 0x2D in ids or 0x02 in ids:
                lines.append(f"  dpin g={g} ids={[hex(x) for x in ids]}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
