"""Decode all .256 resources with the CODE 8 @2206 algorithm. Write PNGs."""
from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mac_containers import iter_resources, load_resource_payload

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/256"
MAGENTA = (255, 0, 255)


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from(">I", b, o)[0]


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def load_256() -> dict[int, bytes]:
    payload = load_resource_payload(SHAPES)
    if payload is None:
        raise FileNotFoundError(SHAPES)
    found: dict[int, bytes] = {}
    for typ, rid, blob in iter_resources(payload.data):
        if typ == b".256":
            found[rid] = blob
    return found


def decompress(src: bytes) -> dict:
    """Exactly the CODE 8 @2206 loop. Does not guess or recover."""
    if len(src) < 4:
        return {
            "ok": False,
            "declared": 0,
            "out": b"",
            "consumed": 0,
            "stop_p": 0,
            "stop_reason": "src shorter than 4",
        }
    declared = u32(src, 0)
    p = 4
    out = bytearray()
    stop_reason = "loop_done"
    while declared > len(out):
        if p >= len(src):
            stop_reason = "eof_opcode"
            break
        b = src[p]
        p += 1
        if b < 0x80:
            n = b + 3
            if p >= len(src):
                stop_reason = "eof_run_value"
                break
            v = src[p]
            p += 1
            out.extend([v] * n)
        else:
            n = b - 0x7F
            if p + n > len(src):
                stop_reason = "eof_literal"
                break
            out.extend(src[p : p + n])
            p += n
    emitted = bytes(out)
    exact = len(emitted) == declared
    consumed_all = p == len(src)
    return {
        "ok": exact and consumed_all and stop_reason == "loop_done",
        "declared": declared,
        "out": emitted,
        "consumed": p,
        "stop_p": p,
        "stop_reason": stop_reason,
        "exact": exact,
        "consumed_all": consumed_all,
    }


def parse_header(buf: bytes) -> dict | None:
    if len(buf) < 18:
        return None
    return {
        "tile_count": u16(buf, 0),
        "v1": u32(buf, 2),
        "v2": u32(buf, 6),
        "v3": u32(buf, 10),
        "v4": u32(buf, 14),
    }


def ascending_run(blob: bytes, start: int, stride: int) -> tuple[int, int, int]:
    if start + stride > len(blob):
        return 0, 0, start
    first = u16(blob, start)
    n = 0
    off = start
    expect = first
    while off + stride <= len(blob):
        if u16(blob, off) != expect:
            break
        n += 1
        expect += 1
        off += stride
    return first, n, off


def find_runs(blob: bytes, min_n: int = 4) -> list[tuple[int, int, int, int, int]]:
    """Ascending u16be-index records at strides 4,5,6,7,8. Non-overlapping."""
    hits: list[tuple[int, int, int, int, int]] = []
    covered: set[int] = set()
    for stride in (4, 5, 6, 7, 8):
        off = 0
        while off + stride * min_n <= len(blob):
            if off in covered:
                off += 1
                continue
            first, n, end = ascending_run(blob, off, stride)
            if n >= min_n and 0 <= first <= 255 and first + n - 1 <= 255:
                hits.append((off, stride, first, n, end))
                for q in range(off, end):
                    covered.add(q)
                off = end
            else:
                off += 1
    hits.sort(key=lambda t: t[0])
    return hits


def decode_rgb(blob: bytes, off: int, stride: int) -> tuple[int, tuple[int, int, int]] | None:
    if off + stride > len(blob):
        return None
    idx = u16(blob, off)
    rest = blob[off + 2 : off + stride]
    if stride == 8 and len(rest) == 6:
        r, g, b = struct.unpack(">HHH", rest)
        return idx, (r >> 8, g >> 8, b >> 8)
    if stride == 5 and len(rest) == 3:
        return idx, (rest[0], rest[1], rest[2])
    if stride == 7 and len(rest) == 5:
        return idx, (rest[2], rest[3], rest[4])
    if stride == 6 and len(rest) == 4:
        return idx, (rest[1], rest[2], rest[3])
    if stride == 4 and len(rest) == 2:
        return idx, (rest[0], rest[1], rest[0])
    return idx, (0, 0, 0)


def merge_palette(blob: bytes, runs: list) -> tuple[dict[int, tuple[int, int, int]], list]:
    """Merge runs. On conflict prefer stride 8, then 5."""
    pal: dict[int, tuple[int, int, int]] = {}
    source: dict[int, int] = {}
    conflicts = []
    rank = {8: 3, 5: 2, 7: 1, 6: 1, 4: 0}

    def better(new_s: int, old_s: int) -> bool:
        return rank.get(new_s, 0) > rank.get(old_s, 0)

    for off, stride, first, n, end in runs:
        for i in range(n):
            dec = decode_rgb(blob, off + i * stride, stride)
            if dec is None:
                continue
            idx, rgb = dec
            if idx not in pal:
                pal[idx] = rgb
                source[idx] = stride
            elif pal[idx] != rgb:
                conflicts.append((idx, pal[idx], rgb, off + i * stride, stride, source[idx]))
                if better(stride, source[idx]):
                    pal[idx] = rgb
                    source[idx] = stride
    return pal, conflicts


def section_of(off: int, hdr: dict) -> str:
    v1, v2, v3, v4 = hdr["v1"], hdr["v2"], hdr["v3"], hdr["v4"]
    if off < 0x12:
        return "header"
    if off < v1:
        return "s0[0x12,v1)"
    if off < v2:
        return "s1[v1,v2)"
    if off < v3:
        return "s2[v2,v3)"
    if off < v3 + v4:
        return "s3[v3,v3+v4)"
    return "after"


def corr_pair(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2:
        return float("nan")
    if float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return float("nan")
    return float(np.corrcoef(a.astype(np.float64), b.astype(np.float64))[0, 1])


def width_scores(pixels: bytes, v4: int) -> list[tuple[int, int, float, float]]:
    """Return (width, height, vcorr, hcorr) for every width 8..512 that divides v4."""
    arr = np.frombuffer(pixels, dtype=np.uint8)
    out = []
    for w in range(8, 513):
        if v4 % w != 0:
            continue
        h = v4 // w
        img = arr.reshape(h, w)
        if h >= 2:
            v = corr_pair(img[:-1].ravel(), img[1:].ravel())
        else:
            v = float("nan")
        if w >= 2:
            ho = corr_pair(img[:, :-1].ravel(), img[:, 1:].ravel())
        else:
            ho = float("nan")
        out.append((w, h, v, ho))
    return out


def best_widths(scores: list[tuple[int, int, float, float]]):
    def key(t):
        v = t[2]
        return -1.0 if v != v else v  # nan last

    ranked = sorted(scores, key=key, reverse=True)
    return ranked


def render_png(pixels: bytes, width: int, pal: dict[int, tuple[int, int, int]], path: Path) -> None:
    height = len(pixels) // width
    if height * width != len(pixels):
        raise ValueError(f"v4 {len(pixels)} not divisible by width {width}")
    table = []
    for i in range(256):
        rgb = pal.get(i, MAGENTA)
        table.extend(rgb)
    img = Image.frombytes("P", (width, height), pixels)
    img.putpalette(table)
    img.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    blobs = load_256()
    ids = sorted(blobs)
    print(f"loaded {len(ids)} .256 ids={ids}")

    results: dict[int, dict] = {}
    exact_and_full = 0
    exact_only = 0
    print()
    print("=" * 72)
    print("A2 per-resource decode")
    print("  id  packed  declared  emitted  consumed  leftover  full  exact")
    for rid in ids:
        src = blobs[rid]
        r = decompress(src)
        results[rid] = r
        leftover = len(src) - r["consumed"]
        if r["exact"] and r["consumed_all"]:
            exact_and_full += 1
        if r["exact"]:
            exact_only += 1
        print(
            f"  {rid:3d}  {len(src):6d}  {r['declared']:8d}  {len(r['out']):7d}  "
            f"{r['consumed']:8d}  {leftover:8d}  {str(r['consumed_all']):5s}  "
            f"{str(r['exact']):5s}  {r['stop_reason']}"
        )

    print()
    print(f"A3 emitted==declared EXACTLY: {exact_only} / {len(ids)}")
    print(f"A3 emitted==declared AND input fully consumed: {exact_and_full} / {len(ids)}")
    failures = [rid for rid in ids if not (results[rid]["exact"] and results[rid]["consumed_all"])]
    if not failures:
        print("A3 failures: none")
    else:
        print("A3 failures:")
        for rid in failures:
            r = results[rid]
            src = blobs[rid]
            p = r["stop_p"]
            ctx = src[p : p + 16]
            print(
                f"  id={rid} declared={r['declared']} emitted={len(r['out'])} "
                f"consumed={r['consumed']}/{len(src)} reason={r['stop_reason']}"
            )
            print(f"    16 bytes at stop p={p}: {hx(ctx)}")

    print()
    print("=" * 72)
    print("A4 decompressed header")
    print("  id  tiles      v1      v2      v3      v4  v3+v4==size  size")
    headers: dict[int, dict] = {}
    for rid in ids:
        r = results[rid]
        if not r["exact"]:
            print(f"  {rid:3d}  SKIP not exact")
            continue
        hdr = parse_header(r["out"])
        if hdr is None:
            print(f"  {rid:3d}  SKIP header short")
            continue
        headers[rid] = hdr
        size = r["declared"]
        ok = (hdr["v3"] + hdr["v4"]) == size
        print(
            f"  {rid:3d}  {hdr['tile_count']:5d}  {hdr['v1']:7d}  {hdr['v2']:7d}  "
            f"{hdr['v3']:7d}  {hdr['v4']:7d}  {str(ok):5s}  {size}"
        )

    print()
    print("=" * 72)
    print("B1 section sizes  s0=[0x12,v1)  s1=v2-v1  s2=v3-v2  s3=v4")
    print("  id   s0     s1     s2      s3     v1")
    for rid in ids:
        if rid not in headers:
            continue
        h = headers[rid]
        s0 = h["v1"] - 0x12
        s1 = h["v2"] - h["v1"]
        s2 = h["v3"] - h["v2"]
        print(f"  {rid:3d}  {s0:5d}  {s1:5d}  {s2:5d}  {h['v4']:7d}  {h['v1']:5d}")

    family = [i for i in range(195, 203) if i in headers]
    print()
    print("=" * 72)
    print("B2 decompressed [0x12, v1) for 195-202")
    dumps = {}
    for rid in family:
        h = headers[rid]
        buf = results[rid]["out"]
        chunk = buf[0x12 : h["v1"]]
        dumps[rid] = chunk
        print(f"  id={rid} len={len(chunk)} v1={h['v1']}")
        for off in range(0, len(chunk), 16):
            print(f"    {0x12 + off:5d}  {hx(chunk[off : off + 16])}")
    if dumps:
        lens = {len(v) for v in dumps.values()}
        print(f"  dump lengths: {sorted(lens)}")
        if len(lens) == 1:
            n = next(iter(lens))
            identical = []
            differ = []
            for i in range(n):
                vals = {dumps[rid][i] for rid in family}
                if len(vals) == 1:
                    identical.append((0x12 + i, next(iter(vals))))
                else:
                    differ.append(0x12 + i)
            print(f"  identical bytes across 8: {len(identical)} / {n}")
            print(f"  differing offsets: {differ}")
            if identical:
                print("  identical map (offset, value):")
                for off, val in identical:
                    print(f"    {off:5d}  {val:02X}")
        else:
            print("  HYPOTHESIS skipped bytewise compare: lengths differ")

    print()
    print("=" * 72)
    print("B3 ascending-index runs in decompressed space")
    all_runs: dict[int, list] = {}
    for rid in ids:
        if rid not in headers:
            continue
        buf = results[rid]["out"]
        h = headers[rid]
        runs = find_runs(buf)
        all_runs[rid] = runs
        print(f"  id={rid} runs={len(runs)}")
        for off, stride, first, n, end in runs:
            rel = (
                f"off-v1={off - h['v1']:+d} off-v2={off - h['v2']:+d} "
                f"off-v3={off - h['v3']:+d} sect={section_of(off, h)}"
            )
            print(
                f"    start={off:5d} stride={stride} first={first:3d} n={n:3d} "
                f"end={end:5d} {rel}"
            )

    print()
    print("B3 consistency vs v1/v2/v3")
    by_rel: dict[tuple, list[int]] = {}
    for rid, runs in all_runs.items():
        h = headers[rid]
        for off, stride, first, n, end in runs:
            key = (off - h["v1"], stride, first, n)
            by_rel.setdefault(key, []).append(rid)
    print("  runs sharing (off-v1, stride, first, n) across 2+ resources:")
    shared = [(k, v) for k, v in by_rel.items() if len(v) >= 2]
    shared.sort(key=lambda t: (-len(t[1]), t[0]))
    for (rel, stride, first, n), rids in shared:
        print(f"    off-v1={rel:+d} stride={stride} first={first} n={n} ids={rids}")
    if not shared:
        print("    none")

    print()
    print("=" * 72)
    print("B4 final-section [v3, v3+v4) histogram")
    hist_ids = [i for i in (192, 193, 194, *range(195, 203)) if i in headers]
    for rid in hist_ids:
        h = headers[rid]
        buf = results[rid]["out"]
        sec = buf[h["v3"] : h["v3"] + h["v4"]]
        if len(sec) != h["v4"]:
            print(f"  id={rid} ANOMALY section len {len(sec)} != v4 {h['v4']}")
        c = Counter(sec)
        print(
            f"  id={rid} bytes={len(sec)} distinct={len(c)} min={min(sec) if sec else None} "
            f"max={max(sec) if sec else None}"
        )
        top = c.most_common(12)
        print(f"    top12: {[(v, n) for v, n in top]}")

    print()
    print("=" * 72)
    print("C1 best width by vertical correlation")
    print("  id   best_w  best_h   vcorr    hcorr   runner_w  runner_h  r_vcorr   r_hcorr")
    best: dict[int, tuple] = {}
    for rid in ids:
        if rid not in headers:
            continue
        h = headers[rid]
        buf = results[rid]["out"]
        sec = buf[h["v3"] : h["v3"] + h["v4"]]
        if len(sec) != h["v4"] or h["v4"] == 0:
            print(f"  {rid:3d}  SKIP empty/short section")
            continue
        scores = width_scores(sec, h["v4"])
        ranked = best_widths(scores)
        if not ranked:
            print(f"  {rid:3d}  SKIP no divisor widths")
            continue
        b0 = ranked[0]
        b1 = ranked[1] if len(ranked) > 1 else None
        best[rid] = b0
        if b1:
            print(
                f"  {rid:3d}  {b0[0]:6d}  {b0[1]:6d}  {b0[2]:7.4f}  {b0[3]:7.4f}  "
                f"{b1[0]:7d}  {b1[1]:7d}  {b1[2]:8.4f}  {b1[3]:8.4f}"
            )
        else:
            print(
                f"  {rid:3d}  {b0[0]:6d}  {b0[1]:6d}  {b0[2]:7.4f}  {b0[3]:7.4f}  "
                f"{'none':>7s}"
            )

    print()
    print("C2 195-202 best widths")
    fam_w = {rid: best[rid][0] for rid in family if rid in best}
    print(f"  widths: {fam_w}")
    print(f"  unique widths: {sorted(set(fam_w.values()))}")
    for rid in family:
        if rid not in best or rid not in headers:
            continue
        w, hgt, vc, hc = best[rid]
        tiles = headers[rid]["tile_count"]
        v4 = headers[rid]["v4"]
        rows = v4 // w if w else 0
        print(
            f"  id={rid} best_w={w} height={hgt} tiles={tiles} "
            f"v4/w={rows} (v4/w)/tiles={rows / tiles if tiles else None} "
            f"v4/(w*tiles)={v4 / (w * tiles) if tiles and w else None}"
        )

    print()
    print("=" * 72)
    print("C3 render")
    for rid in ids:
        if rid not in headers or rid not in best:
            continue
        h = headers[rid]
        buf = results[rid]["out"]
        sec = buf[h["v3"] : h["v3"] + h["v4"]]
        runs = all_runs.get(rid, [])
        pal, conflicts = merge_palette(buf, runs)
        w = best[rid][0]
        path = OUT / f"{rid}_decoded.png"
        render_png(sec, w, pal, path)
        print(
            f"  wrote {path.name} {w}x{len(sec)//w} pal_entries={len(pal)} "
            f"conflicts={len(conflicts)} unmapped_in_pixels="
            f"{sum(1 for x in sec if x not in pal)}"
        )

    print()
    print("=" * 72)
    print("C4 192 / 193 / 194")
    for rid in (192, 193, 194):
        if rid not in headers:
            print(f"  id={rid} missing")
            continue
        h = headers[rid]
        r = results[rid]
        s0 = h["v1"] - 0x12
        s1 = h["v2"] - h["v1"]
        s2 = h["v3"] - h["v2"]
        b = best.get(rid)
        print(
            f"  id={rid} packed={len(blobs[rid])} declared={r['declared']} "
            f"emitted={len(r['out'])} tiles={h['tile_count']}"
        )
        print(f"    v1={h['v1']} v2={h['v2']} v3={h['v3']} v4={h['v4']}")
        print(f"    sections s0={s0} s1={s1} s2={s2} s3={h['v4']}")
        if b:
            print(f"    best_w={b[0]} best_h={b[1]} vcorr={b[2]:.4f} hcorr={b[3]:.4f}")
            print(f"    png={OUT / f'{rid}_decoded.png'}")

    print()
    print(
        f"GO/NO-GO: {exact_and_full}/{len(ids)} decode to declared size "
        f"with input fully consumed; exact-size-only {exact_only}/{len(ids)}"
    )


if __name__ == "__main__":
    main()
