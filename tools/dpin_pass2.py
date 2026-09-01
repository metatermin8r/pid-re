"""dpin header dump, column occupancy, slot test, u16 range histograms."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 596
ROW = 80
SLOT = 16
SLOTS = 5


def hex_uncollapsed(data: bytes, base: int = 0) -> list[str]:
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off : off + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + off:08x}  {hexpart:<48}  |{ascii_part}|")
    return lines


def u16_runs(data: bytes, base: int = 0) -> list[str]:
    """Decode as u16be. Skip zero runs; report their lengths."""
    if len(data) % 2:
        data = data[:-1]
    lines = []
    i = 0
    n = len(data)
    while i < n:
        val = struct.unpack(">H", data[i : i + 2])[0]
        if val == 0:
            run = 0
            while i < n and struct.unpack(">H", data[i : i + 2])[0] == 0:
                run += 1
                i += 2
            lines.append(f"  {base + i - 2 * run:08x}  zero_u16_run  count={run}  bytes={run * 2}")
            continue
        lines.append(f"  {base + i:08x}  u16be={val}  (0x{val:04x})")
        i += 2
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "reference" / "dpin_128.bin"),
    )
    parser.add_argument("--out-dir", default=str(ROOT / "reference"))
    args = parser.parse_args()

    raw = Path(args.path).read_bytes()
    out = Path(args.out_dir)
    prefix = raw[:PREFIX]
    body = raw[PREFIX:]
    assert len(body) == 2876 * ROW, (len(body), 2876 * ROW)
    grid = np.frombuffer(body, dtype=np.uint8).reshape(2876, ROW)

    # --- A ---
    a = [
        f"file: {args.path}",
        f"prefix_bytes: {PREFIX}  range: 0x000-0x{PREFIX:03x} exclusive",
        f"size: {len(raw)}",
        "",
        "=== hex 0x000-0x253 (596 bytes, no collapse) ===",
        "",
    ]
    a += hex_uncollapsed(prefix)
    nz = [i for i, b in enumerate(prefix) if b != 0]
    a += ["", f"=== nonzero byte offsets in prefix ({len(nz)}) ===", ""]
    for i in nz:
        a.append(f"  0x{i:04x}  {prefix[i]:02x}  ({prefix[i]})")
    a += ["", "=== prefix as u16be, zero runs reported by length ===", ""]
    a += u16_runs(prefix)
    header_path = out / "dpin_header.txt"
    header_path.write_text("\n".join(a) + "\n", encoding="utf-8")

    # --- B ---
    col_nz = (grid != 0).sum(axis=0)
    b = ["# nonzero count per column, wrap=80, start=596, rows=2876", ""]
    for i in range(80):
        b.append(f"{i} {int(col_nz[i])}")
    (out / "dpin_columns.txt").write_text("\n".join(b) + "\n", encoding="utf-8")

    # --- C ---
    c = [
        "model: 5 slots of 16 bytes in each 80-byte row",
        "slots: 0=[0:16] 1=[16:32] 2=[32:48] 3=[48:64] 4=[64:80]",
        f"rows: {grid.shape[0]}",
        "",
    ]
    slot_profiles = []
    for s in range(SLOTS):
        sl = grid[:, s * SLOT : (s + 1) * SLOT]
        per_col = (sl != 0).sum(axis=0)
        all_zero_rows = int((sl == 0).all(axis=1).sum())
        words = sl.reshape(2876, 8, 2)
        # u16be
        hi = words[:, :, 0].astype(np.uint16)
        lo = words[:, :, 1].astype(np.uint16)
        u16 = (hi << 8) | lo
        ffff = (u16 == 0xFFFF).sum(axis=0)
        slot_profiles.append(tuple(int(x) for x in per_col))
        c.append(f"=== slot {s}  bytes {s * SLOT}-{s * SLOT + 15} ===")
        c.append("per-column nonzero (16):")
        for i in range(16):
            c.append(f"  {i} {int(per_col[i])}")
        c.append(f"rows entirely zero: {all_zero_rows}")
        c.append("u16be positions 0,2,4,6,8,10,12,14  count of 0xffff:")
        for i in range(8):
            c.append(f"  u16[{i}] @byte {i * 2}  ffff={int(ffff[i])}")
        c.append("")
    c.append("slot nonzero-column profiles equal?")
    for s in range(SLOTS):
        c.append(f"  slot {s}: {slot_profiles[s]}")
    c.append(f"all five profiles identical: {len(set(slot_profiles)) == 1}")

    (out / "dpin_slots.txt").write_text("\n".join(c) + "\n", encoding="utf-8")

    # --- D ---
    # 16-byte unit: treat body as sequence of 16-byte slots (2876*5)
    nslots = 2876 * 5
    slots = grid.reshape(nslots, 16)
    words = slots.reshape(nslots, 8, 2)
    u16 = (words[:, :, 0].astype(np.uint32) << 8) | words[:, :, 1].astype(np.uint32)
    d = [
        "region: offset 596, as successive 16-byte units (2876*5 = 14380 slots)",
        "each slot: 8 u16be fields at bytes 0,2,4,6,8,10,12,14",
        "ranges: 0 | 0xffff | 1-27 | 28-2875 | 2876-32767 | 32768-65535",
        "",
    ]
    for i in range(8):
        col = u16[:, i]
        d.append(f"=== u16 column {i}  byte {i * 2} ===")
        d.append(f"  0: {(col == 0).sum()}")
        d.append(f"  0xffff: {(col == 0xFFFF).sum()}")
        d.append(f"  1-27: {((col >= 1) & (col <= 27)).sum()}")
        d.append(f"  28-2875: {((col >= 28) & (col <= 2875)).sum()}")
        d.append(f"  2876-32767: {((col >= 2876) & (col <= 32767)).sum()}")
        d.append(f"  32768-65535: {(col >= 32768).sum()}")
        # raw extras: min/max of nonzero-non-ffff
        mid = col[(col != 0) & (col != 0xFFFF)]
        if mid.size:
            d.append(f"  nonzero_non_ffff min={int(mid.min())} max={int(mid.max())}")
        d.append("")

    (out / "dpin_u16_ranges.txt").write_text("\n".join(d) + "\n", encoding="utf-8")

    # stdout: A in full as requested, then pointers
    sys.stdout.write("\n".join(a) + "\n")
    print("--- wrote ---")
    print(header_path)
    print(out / "dpin_columns.txt")
    print(out / "dpin_slots.txt")
    print(out / "dpin_u16_ranges.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
