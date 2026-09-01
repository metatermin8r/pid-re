# -*- coding: utf-8 -*-
"""Round 11 part 2: slot diffs, 9112-byte level table, bit 114, fields."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402
from round11_saves import ITEM_NAMES  # noqa: E402

SAVE = ROOT / "data/saves/Saved Games"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
DPIN = ROOT / "reference/dpin_128.bin"
OUT = ROOT / "reference/docs/round11_saves2.txt"

LEVEL_STRIDE = 9112
LEVEL_BASE = 39392
N_LEVELS = 25


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def i16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def dump_inv(data: bytes, start: int, count: int, lines: list[str], label: str) -> None:
    lines.append(f"\n== inventory {label} @{start} ==")
    for i in range(count):
        off = start + i * 8
        rec = data[off : off + 8]
        a, b, c, d = struct.unpack(">4H", rec)
        iid = a
        name = ITEM_NAMES.get(iid, "?")
        lines.append(
            f"  [{i:2d}] @{off} {rec.hex(' ')}  id={iid}({name}) state={b} qty={c} cat={d}"
        )


def bit_test(blob: bytes, bit_index: int) -> list[str]:
    """Test bit 114 in both bit orders, byte 14 bit 2."""
    out = []
    if bit_index // 8 >= len(blob):
        return [f"  bit {bit_index} out of range for {len(blob)} bytes"]
    byte_i = bit_index // 8
    bit_le = bit_index % 8  # LSB = bit 0
    bit_be = 7 - bit_le  # MSB = bit 0
    b = blob[byte_i]
    out.append(
        f"  bit{bit_index} byte_off={byte_i} value=0x{b:02x} "
        f"LSB0={bool(b >> bit_le & 1)} MSB0={bool(b >> bit_be & 1)}"
    )
    return out


def main() -> None:
    data = SAVE.read_bytes()
    n = len(data)
    lines: list[str] = []

    # confirm 25 x 9112
    lines.append(f"== 25 x {LEVEL_STRIDE} from {LEVEL_BASE} ==")
    lines.append(f"  end={LEVEL_BASE + N_LEVELS * LEVEL_STRIDE} file={n} tail={n - (LEVEL_BASE + N_LEVELS * LEVEL_STRIDE)}")
    nz = []
    for i in range(N_LEVELS):
        block = data[LEVEL_BASE + i * LEVEL_STRIDE : LEVEL_BASE + (i + 1) * LEVEL_STRIDE]
        c = sum(1 for b in block if b)
        nz.append(c)
        lines.append(f"  L{i:02d} @{LEVEL_BASE + i * LEVEL_STRIDE} nonzero={c} head={block[:32].hex(' ')}")
    lines.append(f"  identical-to-L0: {[i for i in range(1, 25) if data[LEVEL_BASE+i*LEVEL_STRIDE:LEVEL_BASE+(i+1)*LEVEL_STRIDE] == data[LEVEL_BASE:LEVEL_BASE+LEVEL_STRIDE]]}")
    # pairwise unique
    uniq = {}
    for i in range(25):
        block = data[LEVEL_BASE + i * LEVEL_STRIDE : LEVEL_BASE + (i + 1) * LEVEL_STRIDE]
        uniq.setdefault(block, []).append(i)
    lines.append(f"  unique-block groups: {[(len(v), v[:8]) for v in uniq.values()]}")

    # L0 vs L1 first diffs
    b0 = data[LEVEL_BASE : LEVEL_BASE + LEVEL_STRIDE]
    b1 = data[LEVEL_BASE + LEVEL_STRIDE : LEVEL_BASE + 2 * LEVEL_STRIDE]
    diffs01 = [i for i in range(LEVEL_STRIDE) if b0[i] != b1[i]]
    lines.append(f"  L0 vs L1 diffs={len(diffs01)} first20={diffs01[:20]}")

    # try other bases that also have 9112 * 25 copies
    for base in (39384, 39376, 33944, 25680, 0, 128, 256, 512, 2048, 2560):
        if base + 25 * LEVEL_STRIDE > n:
            continue
        groups = {}
        for i in range(25):
            block = data[base + i * LEVEL_STRIDE : base + (i + 1) * LEVEL_STRIDE]
            groups.setdefault(hash(block), []).append(i)
        lines.append(f"  alt base={base} unique={len(groups)} group_sizes={sorted((len(v), v[0]) for v in groups.values())[:8]}")

    # player/header region 0..39392
    lines.append("\n== header 0..39392 hex slices ==")
    for off in (2048, 2200, 2300, 2320, 2400, 2480, 2544, 25680, 25680 - 232, 1780, 1840, 1860):
        if 0 <= off < n:
            lines.append(f"\n-- @{off} --")
            lines.append(hexdump_mac_roman(data[off : off + 64]))

    dump_inv(data, 2560, 22, lines, "abs2560")
    dump_inv(data, 25680, 16, lines, "abs25680")

    # is 25680-2560 a slot stride? diff those two 23000-byte windows
    stride_inv = 25680 - 2560
    lines.append(f"\n== region {2560} vs {25680} stride={stride_inv} ==")
    a = data[2560 : 2560 + 400]
    b = data[25680 : 25680 + 400]
    dd = [(i, a[i], b[i]) for i in range(min(len(a), len(b))) if a[i] != b[i]]
    lines.append(f"  first400 diffs={len(dd)}")
    for i, va, vb in dd[:40]:
        lines.append(f"    +{i} {va:02x}->{vb:02x}")

    # full slot candidates: compare data[0:S] vs data[S:2S] with S around 18224, 23008, 9112, 39652
    lines.append("\n== full-window diffs for candidate slot sizes ==")
    for s in (9112, 18224, 18304, 23008, 23020, 23120, 25600, 26624, 32768, 39652, 54784):
        if 2 * s > n:
            continue
        diffs = [i for i in range(s) if data[i] != data[s + i]]
        lines.append(f"  S={s} diffs={len(diffs)}/{s} ({len(diffs)/s:.4f}) first={diffs[:15]}")

    # 2328 position candidate
    lines.append("\n== T3 position neighborhood @2328 and HP/time ==")
    lines.append(hexdump_mac_roman(data[2280:2400]))
    lines.append(f"  u16@2328={u16(data,2328)} u16@2330={u16(data,2330)}")
    lines.append(f"  time u32@1786={u32(data,1786)} seconds={u32(data,1786)/60:.2f}")
    lines.append(f"  u16@1876={u16(data,1876)} u16@1878={u16(data,1878)}")

    # search u16be 60,60 near a 0
    lines.append("\n== u16be 60,60 pairs (HP) ==")
    for i in range(0, n - 4, 2):
        if u16(data, i) == 60 and u16(data, i + 2) == 60:
            lines.append(f"  @{i} ctx={data[i-8:i+16].hex(' ') if i>=8 else data[:i+16].hex(' ')}")

    # search u16 0 (level) near u16 6 and u16 2
    lines.append("\n== u16 triples (level=0,x=6,y=2) any order within 16 bytes ==")
    for i in range(0, min(n - 16, 40000), 2):
        vals = [u16(data, i + k) for k in range(0, 16, 2)]
        if 0 in vals and 6 in vals and 2 in vals:
            lines.append(f"  @{i} u16s={vals} hex={data[i:i+16].hex(' ')}")

    # 04=1 unit: 24 and 8
    lines.append("\n== u16 triples (0, 24, 8) within 16 bytes ==")
    for i in range(0, min(n - 16, 40000), 2):
        vals = [u16(data, i + k) for k in range(0, 16, 2)]
        if 0 in vals and 24 in vals and 8 in vals:
            lines.append(f"  @{i} u16s={vals} hex={data[i:i+16].hex(' ')}")

    # BIT 114 in L0
    lines.append("\n== T2(c) bit 114 in Ground Floor level block ==")
    lines.append("  L0 first 64:")
    lines.append(hexdump_mac_roman(b0[:64]))
    lines.extend(bit_test(b0, 114))
    # also treat first 50 bytes as 400-bit item bitmap
    lines.append("  L0[0:50] as 400-bit item bitmap:")
    lines.extend(bit_test(b0[:50], 114))
    # scan L0 for i16==114
    hits = [i for i in range(0, LEVEL_STRIDE - 1) if b0[i : i + 2] == b"\x00\x72"]
    lines.append(f"  L0 i16be 114 at relative {hits}")
    # L0 vs every other level: bytes that are unique to L0
    lines.append("\n== L0 bytes that differ from majority of other levels (sample) ==")
    # compare L0 to L24 (likely unused)
    b24 = data[LEVEL_BASE + 24 * LEVEL_STRIDE : LEVEL_BASE + 25 * LEVEL_STRIDE]
    d0_24 = [i for i in range(LEVEL_STRIDE) if b0[i] != b24[i]]
    lines.append(f"  L0 vs L24 diffs={len(d0_24)}")
    for i in d0_24[:40]:
        lines.append(f"    Lrel {i} L0={b0[i]:02x} L24={b24[i]:02x}")

    # item 114: look at L0 offset 14 (byte 14 of a bitmap at start)
    lines.append(f"  L0[14]={b0[14]:02x} bits LSB {[(k, bool(b0[14]>>k & 1)) for k in range(8)]}")

    # search 50-byte windows in L0 with few nonzeros — item bitmap?
    lines.append("\n== L0 low-density 50-byte windows (candidate item bitmaps) ==")
    for i in range(0, LEVEL_STRIDE - 50, 2):
        w = b0[i : i + 50]
        nz = sum(1 for x in w if x)
        if 1 <= nz <= 8:
            bit114_byte = w[14]
            lines.append(f"  @{i} nz={nz} b14={bit114_byte:02x} {w.hex(' ')}")

    # whole-file: two regions that differ by few bytes (the actual experiment)
    # sliding compare of 39652-byte player prefix against later? 
    # compare 0:20000 with each offset
    lines.append("\n== search near-copy of first 8KB (step 64) ==")
    prefix = data[:8192]
    best = []
    for off in range(4096, n - 8192, 64):
        diffs = sum(1 for a, b in zip(prefix, data[off : off + 8192], strict=True) if a != b)
        if diffs < 4000:
            best.append((diffs, off))
    best.sort()
    lines.append(f"  hits diffs<4000: {best[:15]}")

    # AppleDouble sidecar
    ad = ROOT / "data/saves/Saved Games.zip"
    import zipfile

    with zipfile.ZipFile(ad) as zf:
        raw = zf.read("__MACOSX/._Saved Games")
    lines.append(f"\n== AppleDouble sidecar {len(raw)} bytes ==")
    lines.append(raw.hex(" "))

    # dpin g=3 vs inventory
    dpin = DPIN.read_bytes()
    g3 = dpin[596 + 3 * 80 : 596 + 4 * 80]
    lines.append("\n== dpin group 3 (80 bytes) vs save inv @2560 ==")
    lines.append(f"  dpin g3 {g3.hex(' ')}")
    lines.append(f"  save    {data[2560:2560+80].hex(' ')}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
