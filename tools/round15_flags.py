# -*- coding: utf-8 -*-
"""Dump the 2080-2220 flag region and test bitmap start hypotheses."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mac_text import hexdump_mac_roman  # noqa: E402

ONE = (ROOT / "reference/saves/Saved Games").read_bytes()
TWO = (ROOT / "reference/saves/Saved Games r14").read_bytes()
SLOT = 2876
ALCOVE = {43, 44, 45, 53, 57}
SECTORS = {5 + 1 * 32: (5, 1, 53), 6 + 1 * 32: (6, 1, 43), 7 + 1 * 32: (7, 1, 57),
           5 + 2 * 32: (5, 2, 44), 7 + 3 * 32: (7, 3, 45)}


def bits_set(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """(abs_off, bit, global_index_from_start) for set bits in [start,end)."""
    out = []
    for i, b in enumerate(data[start:end]):
        for bit in range(8):
            if b & (1 << bit):
                out.append((start + i, bit, i * 8 + bit))
    return out


def main() -> None:
    sa, sb, s1 = TWO[0:SLOT], TWO[SLOT:2 * SLOT], ONE[0:SLOT]
    print("=== hex 2080-2220 ===")
    for label, s in (("AAA", sa), ("AAB", sb), ("one", s1)):
        print(f"\n{label}")
        print(hexdump_mac_roman(s[2080:2220]))

    print("\n=== set bits 2080-2200 (LSB index from 2080) ===")
    for label, s in (("AAA", sa), ("AAB", sb), ("one", s1)):
        bs = bits_set(s, 2080, 2200)
        print(f"{label}: {bs}")

    print("\n=== which start S makes a flipped AAB bit equal alcove Item or sector ===")
    aab_bits = bits_set(sb, 2080, 2200)
    # also include only the AAA->AAB new bits
    aaa_set = {(off, bit) for off, bit, _ in bits_set(sa, 2080, 2200)}
    new_bits = [(off, bit) for off, bit, _ in aab_bits if (off, bit) not in aaa_set]
    print(f"new AAB bits (off, LSB bit): {new_bits}")

    for S in range(2048, 2160):
        hits = []
        for off, bit in new_bits:
            idx_lsb = (off - S) * 8 + bit
            idx_msb = (off - S) * 8 + (7 - bit)
            if idx_lsb in ALCOVE or idx_lsb in SECTORS:
                hits.append(("LSB", idx_lsb, off, bit))
            if idx_msb in ALCOVE or idx_msb in SECTORS:
                hits.append(("MSB", idx_msb, off, bit))
        if hits:
            print(f"  S={S}: {hits}")

    print("\n=== one-name extra bits vs AAB ===")
    one_bits = bits_set(s1, 2080, 2200)
    aab_pairs = {(o, b) for o, b, _ in aab_bits}
    extra = [(o, b, i) for o, b, i in one_bits if (o, b) not in aab_pairs]
    print(f"one extra: {extra}")
    print(f"one all LSB-from-2080: {[i for _,_,i in one_bits]}")
    print(f"AAB all LSB-from-2080: {[i for _,_,i in aab_bits]}")

    print("\n=== 0x0750/0752 as possible score/weight ===")
    import struct
    for label, s in (("AAA", sa), ("AAB", sb), ("one", s1)):
        a = struct.unpack_from(">H", s, 1872)[0]
        b = struct.unpack_from(">H", s, 1874)[0]
        clk = struct.unpack_from(">I", s, 1866)[0]
        print(f"  {label} clk={clk} 750={a} 752={b} sum={a+b} diff={a-b}")


if __name__ == "__main__":
    main()
