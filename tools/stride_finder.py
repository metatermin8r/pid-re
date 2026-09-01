"""Self-similarity stride scan. Does not claim a record layout.

Score for stride s: among positions i where data[i] or data[i+s] is
nonzero, the fraction where data[i] == data[i+s]. All-zero pairs are
dropped so the empty regions do not flatten every stride.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def scores_for_file(data: np.ndarray, min_stride: int, max_stride: int) -> np.ndarray:
    n = len(data)
    max_stride = min(max_stride, n - 1)
    out = np.zeros(max_stride + 1, dtype=np.float64)
    considered = np.zeros(max_stride + 1, dtype=np.int64)
    matched = np.zeros(max_stride + 1, dtype=np.int64)
    for s in range(min_stride, max_stride + 1):
        a = data[:-s]
        b = data[s:]
        live = (a != 0) | (b != 0)
        count = int(live.sum())
        considered[s] = count
        if count == 0:
            continue
        hits = int(((a == b) & live).sum())
        matched[s] = hits
        out[s] = hits / count
    return out, considered, matched


def plot_scores(
    scores: np.ndarray,
    min_stride: int,
    out_path: Path,
    marked: list[int],
) -> None:
    width, height = 1200, 400
    img = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(img)
    usable = scores[min_stride:]
    peak = float(usable.max()) if usable.size else 1.0
    if peak <= 0:
        peak = 1.0
    n = len(usable)
    for x in range(width):
        i = min_stride + int(x * n / width)
        if i >= len(scores):
            break
        y = int((1.0 - scores[i] / peak) * (height - 20)) + 10
        draw.line([(x, height - 1), (x, y)], fill=(70, 140, 220))
    for s in marked:
        x = int((s - min_stride) * width / max(n, 1))
        draw.line([(x, 0), (x, height - 1)], fill=(220, 80, 60))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "reference" / "dpin_128.bin"),
    )
    parser.add_argument("--min", type=int, default=2)
    parser.add_argument("--max", type=int, default=4096)
    parser.add_argument(
        "--plot",
        default=str(ROOT / "reference" / "stride_scores.png"),
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "reference" / "stride_scores.txt"),
    )
    args = parser.parse_args()

    path = Path(args.path)
    data = np.fromfile(path, dtype=np.uint8)
    size = int(data.size)
    nonzero = int((data != 0).sum())
    scores, considered, matched = scores_for_file(data, args.min, args.max)

    ranked = sorted(
        range(args.min, min(args.max, size - 1) + 1),
        key=lambda s: (scores[s], considered[s]),
        reverse=True,
    )
    top = ranked[:20]

    lines = [
        f"file: {path}",
        f"size: {size}",
        f"nonzero_bytes: {nonzero} ({100.0 * nonzero / size:.2f}%)",
        f"stride_range: {args.min}..{min(args.max, size - 1)}",
        f"score: matches / positions where data[i] or data[i+s] != 0",
        "",
        "arithmetic_leads (not assumed):",
        f"  230676 / 409 = {size / 409:.6f}  remainder {size % 409}",
        f"  230676 / 564 = {size / 564:.6f}  remainder {size % 564}",
        f"  2876 * 80 = {2876 * 80}  leftover {size - 2876 * 80}",
        f"  score[409] = {scores[409]:.6f}  considered={considered[409]}  divides={size % 409 == 0}  count={size // 409 if size % 409 == 0 else 'n/a'}",
        f"  score[564] = {scores[564]:.6f}  considered={considered[564]}  divides={size % 564 == 0}  count={size // 564 if size % 564 == 0 else 'n/a'}",
        f"  score[80]  = {scores[80]:.6f}  considered={considered[80]}  divides={size % 80 == 0}",
        "",
        "top 20 by nonzero-pair match rate:",
        "",
    ]
    header = (
        f"{'rank':>4}  {'stride':>6}  {'score':>8}  {'matched':>8}  "
        f"{'live':>8}  {'divides':>7}  {'count':>8}"
    )
    lines.append(header)
    for i, s in enumerate(top, 1):
        divides = size % s == 0
        count = str(size // s) if divides else "-"
        lines.append(
            f"{i:4d}  {s:6d}  {scores[s]:8.6f}  {matched[s]:8d}  "
            f"{considered[s]:8d}  {str(divides):>7}  {count:>8}"
        )

    text = "\n".join(lines) + "\n"
    Path(args.report).write_text(text, encoding="utf-8")
    plot_scores(scores, args.min, Path(args.plot), top[:8])
    sys.stdout.write(text)
    print(f"plot: {args.plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
