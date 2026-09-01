"""scri correlations: length vs u16 words, fourcc groups, 0-27 scans."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(ROOT / "reference" / "scri"))
    parser.add_argument(
        "--out",
        default=str(ROOT / "reference" / "scri_stats.txt"),
    )
    args = parser.parse_args()

    blobs = {}
    for path in sorted(Path(args.dir).glob("*.bin"), key=lambda p: int(p.stem)):
        rid = int(path.stem)
        if 128 <= rid <= 155:
            blobs[rid] = path.read_bytes()

    lines: list[str] = []
    lines.append("=== per-resource header words ===")
    lines.append("id  len  u16@0  u16@2  u16@4  u16@6  bytes10-13  as_u16@10  as_u16@12")
    rows = []
    for rid, data in blobs.items():
        u = [struct.unpack(">H", data[i : i + 2])[0] for i in (0, 2, 4, 6)]
        tag = data[10:14]
        tag_s = tag.decode("mac_roman")
        t0, t1 = struct.unpack(">HH", tag)
        rows.append((rid, len(data), u[0], u[1], u[2], u[3], tag_s, t0, t1))
        lines.append(
            f"{rid}  {len(data)}  {u[0]}  {u[1]}  {u[2]}  {u[3]}  "
            f"{tag_s!r}  {t0}  {t1}"
        )

    def corr(xs: list[int], ys: list[int]) -> float:
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        if dx == 0 or dy == 0:
            return float("nan")
        return num / (dx * dy)

    lengths = [r[1] for r in rows]
    w2 = [r[3] for r in rows]
    w4 = [r[4] for r in rows]
    lines += [
        "",
        "=== correlation with resource length (Pearson r) ===",
        f"u16be @ offset 2 vs len: r={corr(w2, lengths):.6f}",
        f"u16be @ offset 4 vs len: r={corr(w4, lengths):.6f}",
        "",
        "pairs (id, len, u16@2, u16@2/len, len/u16@2 if nonzero, u16@4, u16@4/len, len/u16@4):",
    ]
    for rid, ln, _u0, a, b, _u6, _tag, _t0, _t1 in rows:
        r2 = f"{a / ln:.6f}" if ln else "-"
        d2 = f"{ln / a:.6f}" if a else "-"
        r4 = f"{b / ln:.6f}" if ln else "-"
        d4 = f"{ln / b:.6f}" if b else "-"
        lines.append(f"  {rid}  {ln}  {a}  {r2}  {d2}  {b}  {r4}  {d4}")

    lines += ["", "=== bytes 10-13 by ID (file order) ==="]
    for rid, _ln, _u0, _a, _b, _u6, tag, t0, t1 in rows:
        lines.append(f"  {rid}  {tag}  u16be={t0},{t1}  hex={blobs[rid][10:14].hex()}")

    lines += ["", "=== group membership ==="]
    groups: dict[str, list[int]] = {}
    for rid, _ln, _u0, _a, _b, _u6, tag, _t0, _t1 in rows:
        groups.setdefault(tag, []).append(rid)
    for tag, ids in groups.items():
        contig = all(ids[i] + 1 == ids[i + 1] for i in range(len(ids) - 1))
        lines.append(f"  {tag!r}: {ids}  contiguous={contig}  count={len(ids)}")

    lines += [
        "",
        "=== u16be (even offsets) in range 0-27, per resource ===",
        "offset_list is every even offset where the u16be is 0..27",
    ]
    for rid, data in blobs.items():
        hits = []
        for off in range(0, len(data) - 1, 2):
            val = struct.unpack(">H", data[off : off + 2])[0]
            if val <= 27:
                hits.append((off, val))
        freq: dict[int, int] = {}
        for _off, val in hits:
            freq[val] = freq.get(val, 0) + 1
        freq_s = " ".join(f"{k}:{freq[k]}" for k in range(28) if k in freq)
        lines.append(f"scri {rid}  len={len(data)}  hits={len(hits)}  freq {freq_s}")
        lines.append("  " + " ".join(f"{off:04x}={val}" for off, val in hits))

    text = "\n".join(lines) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
