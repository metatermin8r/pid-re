# -*- coding: utf-8 -*-
import struct
from pathlib import Path

d = Path("data/saves/Saved Games").read_bytes()
out = []

off = 2328 + 23008
out.append(f"XY at 2328+23008={off} {d[off:off+16].hex(' ')} u16={struct.unpack_from('>4H', d, off)}")

out.append("second HP neighborhood")
for o in range(24840, 24920, 16):
    out.append(f"  {o:08x} {d[o:o+16].hex(' ')}")

base = 39392
hits = []
for i in range(0, 9112 - 8, 8):
    a, b, c, e = struct.unpack_from(">4H", d, base + i)
    if 114 in (a, b, c, e):
        hits.append((i, a, b, c, e, d[base + i : base + i + 8].hex(" ")))
out.append(f"8-aligned 114 in L0 n={len(hits)} {hits[:20]}")

b0 = d[base : base + 9112]
rel = [i for i in range(len(b0) - 1) if b0[i : i + 2] == b"\x00\x72"]
out.append(f"L0 unaligned i16 114: {rel}")
for i in rel:
    out.append(f"  L0+{i} {b0[max(0, i-8):i+8].hex(' ')}")

relp = [i for i in range(4000) if d[i : i + 2] == b"\x00\x72"]
out.append(f"player 0-4000 i16 114: {relp}")

out.append("u16 2312-2334:")
for o in range(2312, 2336, 2):
    out.append(f"  {o} {struct.unpack_from('>H', d, o)[0]}")

out.append(f"time@1786={struct.unpack_from('>I', d, 1786)[0]}")
out.append("u16 1860-1920: " + str([struct.unpack_from(">H", d, o)[0] for o in range(1860, 1920, 2)]))

# L0 records from 256 as 8-byte: first 20
out.append("L0 from 256 as 8-byte:")
for i in range(20):
    o = 256 + i * 8
    rec = b0[o : o + 8]
    out.append(f"  +{o} {rec.hex(' ')} {struct.unpack('>4H', rec)}")

Path("reference/docs/round11_saves4.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
