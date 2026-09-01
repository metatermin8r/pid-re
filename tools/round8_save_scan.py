# -*- coding: utf-8 -*-
"""Task 2 scans against the decoded (still DiskDoubler-compressed) save."""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "reference/saves/superdude.bin"
RSRC = ROOT / "reference/saves/superdude.bin.rsrc"
OUT = ROOT / "reference/docs/round8_save_scan.txt"
SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"


def findall(blob: bytes, pat: bytes) -> list[int]:
    out = []
    start = 0
    while True:
        i = blob.find(pat, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def main() -> None:
    data = DATA.read_bytes()
    rsrc = RSRC.read_bytes() if RSRC.exists() else b""
    lines = [
        f"data={len(data)} rsrc={len(rsrc)} magic={data[:8].hex()}",
        "magic ABCD0054 = DiskDoubler (not a raw PID save)",
        "",
        "== 0x4000 / 16384 as i16be and u16be ==",
    ]
    for label, blob in (("data", data), ("rsrc", rsrc)):
        hits_be = []
        hits_le = []
        for i in range(0, len(blob) - 1):
            if blob[i : i + 2] == b"\x40\x00":
                hits_be.append(i)
            if blob[i : i + 2] == b"\x00\x40":
                hits_le.append(i)
        lines.append(f"  {label} 40 00 offs={hits_be[:20]} n={len(hits_be)}")
        lines.append(f"  {label} 00 40 offs={hits_le[:20]} n={len(hits_le)}")

    # i16 0..399 runs of length >= 8
    lines.append("\n== runs of i16be in 0..399, len>=8 ==")
    for label, blob in (("data", data), ("rsrc", rsrc)):
        i = 0
        found = 0
        while i + 2 <= len(blob):
            run = []
            j = i
            while j + 2 <= len(blob):
                v = struct.unpack_from(">h", blob, j)[0]
                if 0 <= v <= 399:
                    run.append(v)
                    j += 2
                else:
                    break
            if len(run) >= 8:
                lines.append(f"  {label} @{i} n={len(run)} first={run[:12]}")
                found += 1
                if found >= 12:
                    break
                i = j
            else:
                i += 2
        if found == 0:
            lines.append(f"  {label}: none")

    # 50-byte windows with high bit density
    lines.append("\n== 50-byte windows with 20-45 nonzero bytes (bitmap-ish) ==")
    for label, blob in (("data", data),):
        hits = 0
        for i in range(0, len(blob) - 50, 2):
            w = blob[i : i + 50]
            nz = sum(1 for b in w if b)
            if 20 <= nz <= 45 and w[0] not in (0xAB,):
                # skip obvious compressed noise: high entropy
                uniq = len(set(w))
                if 8 <= uniq <= 30:
                    lines.append(f"  @{i} nz={nz} uniq={uniq} {w[:16].hex()}")
                    hits += 1
                    if hits >= 8:
                        break
        lines.append(f"  shown {hits}")

    # rsrc 128 around 0x22
    import io
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from mac_containers import load_resource_payload
    import rsrcfork

    payload = load_resource_payload(SHAPES)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    s128 = rf[b".256"][128].data_raw
    lines.append("\n== rsrc 128 bytes 0x00-0x80 ==")
    for i in range(0, 0x80, 16):
        row = s128[i : i + 16]
        lines.append(f"{i:04x}  {row.hex(' ')}")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
