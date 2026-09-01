# -*- coding: utf-8 -*-
"""Round 10 follow-up: render packbits sections, leftover stream, decoded headers."""

from __future__ import annotations

import io
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from round10_256 import (  # noqa: E402
    compact_gray,
    highbit_until,
    load_all_256,
    packbits_until,
    render128,
)
from round9_shapes import header, packbits, rle_highbit, section_offs  # noqa: E402

SHAPEDIR = ROOT / "reference/shapes"
OUT = ROOT / "reference/docs/round10_followup.txt"


def main() -> None:
    shapes = load_all_256()
    lines: list[str] = []
    d195 = shapes[195]
    pal = compact_gray(d195)

    # decoded first 376 via packbits from 23
    hdr, c0 = packbits_until(d195[23:], 376)
    lines.append(f"== decoded 376 via packbits@23 cons={c0} out={len(hdr)} ==")
    lines.append(hexdump_mac_roman(hdr))
    u16s = [(i, struct.unpack_from(">H", hdr, i)[0]) for i in range(0, 375, 2)]
    hits = [(i, v) for i, v in u16s if v in (128, 16384, 188, 2, 256, 8, 16, 32, 64, 280, 344, 376)]
    lines.append(f"  interesting u16: {hits}")
    lines.append(f"  hdr[0:188] vs hdr[188:376] identical? {hdr[:188] == hdr[188:376]}")

    # two images after the 376
    a, ca = packbits_until(d195[23 + c0 :], 16384)
    b, cb = packbits_until(d195[23 + c0 + ca :], 16384)
    end = 23 + c0 + ca + cb
    left = d195[end:]
    lines.append(f"\n== packbits images A/B cons={ca}/{cb} end={end} leftover={len(left)} ==")
    render128(a, pal, SHAPEDIR / "195_pb_sec_a.png")
    render128(b, pal, SHAPEDIR / "195_pb_sec_b.png")
    # leftover as another pair
    if left:
        a2, ca2 = packbits_until(left, 16384)
        b2, cb2 = packbits_until(left[ca2:], 16384)
        h2, ch2 = packbits_until(left, 376)
        lines.append(f"  leftover packbits: A2={len(a2)} cons={ca2} B2={len(b2)} cons={cb2} hdr2={len(h2)} cons={ch2}")
        render128(a2, pal, SHAPEDIR / "195_pb_left_a.png")
        if len(b2) >= 1000:
            render128(b2, pal, SHAPEDIR / "195_pb_left_b.png")
        # full leftover packbits length
        full_left = packbits(left)
        lines.append(f"  leftover packbits FULL out={len(full_left)} vs 33144 d={len(full_left)-33144:+d} vs 16572 d={len(full_left)-16572:+d}")

    # highbit two 16384 from 258
    ha, hca = highbit_until(d195[258:], 16384)
    hb, hcb = highbit_until(d195[258 + hca :], 16384)
    lines.append(f"\n== highbit @258 A={len(ha)} cons={hca} B={len(hb)} cons={hcb} ==")
    render128(ha, pal, SHAPEDIR / "195_hb_a.png")
    render128(hb, pal, SHAPEDIR / "195_hb_b.png")

    # highbit whole from 258
    hb_full = rle_highbit(d195[258:])
    lines.append(f"  highbit full @258 out={len(hb_full)}")

    # 198 own palette range
    lines.append("\n== 198 compact / clut range ==")
    pal198 = compact_gray(shapes[198])
    filled198 = [i for i in range(256) if pal198[i] is not None]
    lines.append(f"  compact filled={filled198}")
    # histogram vs own range
    sl = shapes[198][258:]
    own = set(filled198)
    in_own = sum(1 for b in sl if b in own)
    # also treat 0x00-0x02 and 0x80+ as controls
    lines.append(f"  198 @258 in own compact {in_own}/{len(sl)}")

    # fair OOR: exclude 0x80+ and 0x00-0x12 if they're in 198's expanded pixel set
    # report 198 histogram of 0x80+ density vs 195
    def hi_density(data: bytes) -> float:
        n = sum(1 for b in data if b >= 0x80)
        return 1000 * n / len(data) if data else 0

    lines.append("  0x80+ density per KB:")
    for rid in (195, 196, 197, 198, 199, 200, 201, 202):
        d = shapes[rid]
        lines.append(
            f"    {rid} packed={len(d)} 80plus/KB={hi_density(d[258:]):.1f} "
            f"00-02/KB={1000*sum(1 for b in d[258:] if b<=2)/len(d[258:]):.1f}"
        )

    # apply packbits per-section to 196 and 198
    lines.append("\n== packbits per-section 196/198 from @23 ==")
    for rid in (196, 198):
        d = shapes[rid]
        p = compact_gray(d)
        offs = section_offs(d)
        u0, _, b6 = header(d)
        bounds = [0] + offs + [u0]
        sizes = [bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)]
        pos = 23
        parts = []
        for exp in sizes:
            out, cons = packbits_until(d[pos:], exp)
            parts.append(f"{len(out)}/{exp} cons={cons}")
            pos += cons
        lines.append(f"  {rid} {parts} end={pos} left={len(d)-pos}")
        # two 16384 after 376
        h, c0 = packbits_until(d[23:], 376)
        aa, ca = packbits_until(d[23 + c0 :], 16384)
        bb, cb = packbits_until(d[23 + c0 + ca :], 16384)
        render128(aa, p, SHAPEDIR / f"{rid}_pb_sec_a.png")
        render128(bb, p, SHAPEDIR / f"{rid}_pb_sec_b.png")
        lines.append(f"    images A={len(aa)} B={len(bb)} leftover={len(d)-23-c0-ca-cb}")

    # 167/189: table starting at offset 11
    lines.append("\n== T6 refined table at offset 11 ==")
    for rid in (161, 162, 167, 189):
        d = shapes[rid]
        u0, _, b6 = header(d)
        o11 = [struct.unpack_from(">I", d, 11 + i * 4)[0] for i in range(4)]
        ok = all(o11[i] < o11[i + 1] for i in range(3)) and o11[3] < u0
        lines.append(f"  {rid} b6={b6} u0={u0} u32@11={o11} ok4={ok} leftover={u0-o11[3] if o11[3]<u0 else 'n/a'}")

    dest = OUT
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
