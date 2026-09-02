# -*- coding: utf-8 -*-
"""Diff live@267192 packed list vs GF/L24 templates; hunt a second live list."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import load_maps  # noqa: E402

SAVE = ROOT / "reference/saves/Saved Games r14"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference/docs/round14_listdiff.txt"

LEVEL_BASE = 39392
STRIDE = 9112
LIVE = 267192


def rec4(d, o):
    return struct.unpack_from(">4H", d, o)


def live_packed(block, start=256):
    recs = []
    off = start
    while off + 8 <= len(block):
        rec = rec4(block, off)
        if rec[0] == 0xFFFF:
            return recs, off
        recs.append((off, rec))
        off += 8
    return recs, off


def match_pct(a, b):
    n = min(len(a), len(b))
    return 100.0 * sum(1 for i in range(n) if a[i] == b[i]) / n


def main():
    data = SAVE.read_bytes()
    levels = load_maps(MAPS)
    lines = []
    templates = [data[LEVEL_BASE + n * STRIDE : LEVEL_BASE + (n + 1) * STRIDE] for n in range(25)]
    live = data[LIVE : LIVE + STRIDE]

    lines.append("== body[256:] match vs each template ==")
    for n in range(25):
        p = match_pct(live[256:], templates[n][256:])
        ph = match_pct(live[:256], templates[n][:256])
        lines.append(f"  L{n:02d} {levels[n].name!r:40s} header={ph:6.2f} body={p:6.2f}")

    for label, blk in (("LIVE", live), ("T0", templates[0]), ("T24", templates[24])):
        recs, term = live_packed(blk)
        lines.append(f"\n{label} n={len(recs)} term={term}")
        for i, (off, r) in enumerate(recs):
            mark = ""
            if 44 in r:
                mark += " **44**"
            if 0x33 in r or r[0] == 51:
                mark += " ammo"
            if 7 in r:
                mark += " q7"
            if r[0] == 35 and r[2] in (43, 44, 45, 53, 57):
                mark += " alcove"
            lines.append(f"  [{i:03d}] +{off} {r}{mark}")

    # record-by-record LIVE vs T0
    lr, _ = live_packed(live)
    t0, _ = live_packed(templates[0])
    t24, _ = live_packed(templates[24])
    lines.append(f"\n== LIVE vs T0 (n {len(lr)} vs {len(t0)}) ==")
    same = 0
    for i, ((_, a), (_, b)) in enumerate(zip(lr, t0)):
        if a == b:
            same += 1
        else:
            lines.append(f"  rec[{i}] T0={b} LIVE={a}")
    lines.append(f"  pairwise equal={same}/{min(len(lr), len(t0))}")
    if len(lr) != len(t0):
        extra = lr[len(t0) :] if len(lr) > len(t0) else t0[len(lr) :]
        lines.append(f"  extras={extra}")

    lines.append(f"\n== LIVE vs T24 (n {len(lr)} vs {len(t24)}) ==")
    same = 0
    for i, ((_, a), (_, b)) in enumerate(zip(lr, t24)):
        if a == b:
            same += 1
        else:
            lines.append(f"  rec[{i}] T24={b} LIVE={a}")
    lines.append(f"  pairwise equal={same}/{min(len(lr), len(t24))}")

    # shift test LIVE vs T0 if counts differ by 1
    if len(lr) == len(t0) - 1:
        di = next((i for i, ((_, a), (_, b)) in enumerate(zip(lr, t0)) if a != b), len(lr))
        lines.append(f"  shrink vs T0 first diverge {di} removed? {t0[di][1]}")
        a_from = live[256 + di * 8 : 256 + len(lr) * 8 + 8]
        b_from = templates[0][256 + (di + 1) * 8 : 256 + len(t0) * 8 + 8]
        lines.append(f"  LIVE[di:]==T0[di+1:] {a_from == b_from}")

    # search entire file for record containing 44 as a u16be in an 8-byte rec
    lines.append("\n== 8-aligned records containing u16be 44 ==")
    hits = []
    for off in range(0, len(data) - 7, 2):
        r = rec4(data, off)
        if 44 in r and r[0] < 400:
            hits.append((off, r))
    lines.append(f"  n={len(hits)}")
    for off, r in hits[:40]:
        lines.append(f"    @{off} {r}")

    # search for a second list whose first rec equals LIVE[0] or T0[0]
    lines.append("\n== other packed-list starts (first rec match LIVE or T0) ==")
    live0 = lr[0][1]
    t00 = t0[0][1]
    seen = set()
    for off in range(0, len(data) - 8, 8):
        r = rec4(data, off)
        if r not in (live0, t00):
            continue
        recs, term = live_packed(data[off - 256 if off >= 256 else 0 :], 256 if off >= 256 else off)
        # simpler: count from off
        recs2 = []
        p = off
        while p + 8 <= len(data):
            rr = rec4(data, p)
            if rr[0] == 0xFFFF:
                break
            recs2.append(rr)
            p += 8
            if len(recs2) > 200:
                break
        if 70 <= len(recs2) <= 120:
            key = (off, len(recs2), recs2[0], recs2[-1])
            if key in seen:
                continue
            seen.add(key)
            same_t0 = recs2 == [x[1] for x in t0]
            same_live = recs2 == [x[1] for x in lr]
            lines.append(
                f"  list@{off} n={len(recs2)} sameT0={same_t0} sameLIVE={same_live} "
                f"first={recs2[0]} last={recs2[-1]}"
            )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print(f"... wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
