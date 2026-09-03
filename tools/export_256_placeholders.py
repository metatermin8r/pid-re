"""Export raw .256 payloads as placeholder PNGs. Does not decode compression."""
from __future__ import annotations

import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mac_containers import iter_resources, load_resource_payload

SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/256"
EXPORT = ROOT / "reference/export"

STRIDE_FOR_TAG = {
    0x99: 5,
    0xFF: 8,
    0x9B: 7,
    0xC5: 8,
    0xD0: 8,
    0x88: 5,
    0x8C: 5,
}
STRIDE_FOR_ID = {161: 5, 162: 5, 189: 5, 167: 8, 142: 7, 164: 7}


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from(">I", b, o)[0]


def table_stride(rid: int, tag: int) -> int:
    if rid in STRIDE_FOR_ID:
        return STRIDE_FOR_ID[rid]
    return STRIDE_FOR_TAG[tag]


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


def decode_entry(blob: bytes, off: int, stride: int) -> tuple[int, tuple[int, int, int]]:
    idx = u16(blob, off)
    rest = blob[off + 2 : off + stride]
    if stride == 8 and len(rest) == 6:
        r, g, b = struct.unpack(">HHH", rest)
        return idx, (r >> 8, g >> 8, b >> 8)
    if stride == 5 and len(rest) == 3:
        return idx, (rest[0], rest[1], rest[2])
    if stride == 7 and len(rest) == 5:
        # unresolved; last three bytes as a stand-in, reported as HYPOTHESIS
        return idx, (rest[2], rest[3], rest[4])
    g = rest[0] if rest else 0
    return idx, (g, g, g)


def find_runs(blob: bytes, min_n: int = 4) -> list[tuple[int, int, int, int, int]]:
    """All non-overlapping ascending runs, n>=min_n, strides 5/7/8."""
    hits: list[tuple[int, int, int, int, int]] = []
    covered = set()
    for stride in (5, 7, 8):
        off = 0
        while off + stride * min_n <= len(blob):
            if off in covered:
                off += 1
                continue
            first, n, end = ascending_run(blob, off, stride)
            if n >= min_n and 0 <= first <= 255 and first + n - 1 <= 255:
                hits.append((off, stride, first, n, end))
                for p in range(off, end):
                    covered.add(p)
                off = end
            else:
                off += 1
    hits.sort(key=lambda t: t[0])
    return hits


def merge_palette(blob: bytes, runs: list) -> tuple[dict[int, tuple[int, int, int]], list]:
    """Merge runs. On conflict prefer stride-8 ColorSpec over stride-5-as-u8-RGB.

    Stride-5 bytes on 195-202 are (3, gray, 0x81) — treating them as RGB
    is the A3 reading, but they are not a Mac colour. Reported as conflicts.
    """
    pal: dict[int, tuple[int, int, int]] = {}
    source: dict[int, int] = {}
    conflicts = []
    for off, stride, first, n, end in runs:
        for i in range(n):
            idx, rgb = decode_entry(blob, off + i * stride, stride)
            if idx not in pal:
                pal[idx] = rgb
                source[idx] = stride
            elif pal[idx] != rgb:
                conflicts.append((idx, pal[idx], rgb, off + i * stride, stride, source[idx]))
                if stride == 8 and source[idx] != 8:
                    pal[idx] = rgb
                    source[idx] = 8
    return pal, conflicts


def palette_table(
    pal: dict[int, tuple[int, int, int]],
    unmapped: tuple[int, int, int] | None,
) -> list[int]:
    table: list[int] = []
    for i in range(256):
        if i in pal:
            table.extend(pal[i])
        elif unmapped is None:
            table.extend((i, i, i))
        else:
            table.extend(unmapped)
    return table


def write_indexed(
    path: Path,
    pix: bytes,
    w: int,
    h: int,
    pal: dict[int, tuple[int, int, int]],
    unmapped: tuple[int, int, int] | None,
):
    img = Image.frombytes("P", (w, h), pix)
    img.putpalette(palette_table(pal, unmapped))
    img.save(path)


def verdict(ratio: float) -> str:
    if ratio >= 0.97:
        return "GOOD"
    if ratio >= 0.90:
        return "FAIR"
    return "UNUSABLE"


def main():
    payload = load_resource_payload(SHAPES)
    blobs = {rid: b for t, rid, b in iter_resources(payload.data) if t == b".256"}
    ids = sorted(blobs)
    print(f"loaded {len(ids)} .256 from {SHAPES.name}")

    floors = list(range(195, 203))
    OUT.mkdir(parents=True, exist_ok=True)

    print("\n========== A1/A2/A3/A4 195-202 ==========")
    stats = {}
    for rid in floors:
        blob = blobs[rid]
        tag = blob[4]
        stride0 = table_stride(rid, tag)
        first, n, rawend = ascending_run(blob, 29, stride0)
        pay = blob[rawend:]
        size = u32(blob, 0)
        v1, v2, v3, v4 = struct.unpack_from(">4I", blob, 7)
        runs = find_runs(blob, 4)
        pal, conflicts = merge_palette(blob, runs)
        idxs = sorted(pal)
        gaps = []
        if idxs:
            for a, b in zip(idxs, idxs[1:]):
                if b > a + 1:
                    gaps.append((a + 1, b - 1))
        pay_hist = Counter(pay)
        distinct = set(pay_hist)
        covered_vals = distinct & set(pal)
        mapped_bytes = sum(c for v, c in pay_hist.items() if v in pal)
        pct_bytes = 100.0 * mapped_bytes / len(pay) if pay else 0.0

        stats[rid] = dict(
            blob=blob,
            tag=tag,
            stride0=stride0,
            rawend=rawend,
            pay=pay,
            v4=v4,
            size=size,
            pal=pal,
            runs=runs,
            conflicts=conflicts,
            ntab0=n,
            idx0=first,
            distinct=len(distinct),
            covered_vals=len(covered_vals),
            mapped_bytes=mapped_bytes,
            pct_bytes=pct_bytes,
        )

        print(f"\n--- id={rid} tag=0x{tag:02X} first_stride={stride0} RAWEND={rawend} "
              f"n0={n} idx0={first} packed={len(blob)} v4={v4} ---")
        print("  runs (start, stride, idx0, n, end):")
        for rec in runs:
            print(f"    {rec}")
        lo, hi = (idxs[0], idxs[-1]) if idxs else (None, None)
        print(f"  merged n_idx={len(pal)} lo={lo} hi={hi} gaps={gaps}")
        print(f"  conflicts n={len(conflicts)}")
        for c in conflicts[:8]:
            print(
                f"    idx={c[0]} kept_was={c[1]} new={c[2]} @{c[3]} "
                f"newS={c[4]} oldS={c[5]} -> prefer ColorSpec if newS==8"
            )

        s5 = [r for r in runs if r[1] == 5]
        s8 = [r for r in runs if r[1] == 8]
        if s5:
            off, S, *_ = s5[0]
            print("  stride-5 first 10 as (index, r, g, b) u8:")
            for i in range(min(10, s5[0][3])):
                idx, rgb = decode_entry(blob, off + i * 5, 5)
                print(f"    ({idx}, {rgb[0]}, {rgb[1]}, {rgb[2]})")
        if s8:
            off, S, first8, n8, _ = s8[0]
            print("  stride-8 first 10 as (index, r>>8, g>>8, b>>8):")
            for i in range(min(10, n8)):
                idx, rgb = decode_entry(blob, off + i * 8, 8)
                rec = blob[off + i * 8 : off + i * 8 + 8]
                raw = struct.unpack(">4H", rec)
                print(f"    ({idx}, {rgb[0]}, {rgb[1]}, {rgb[2]}) raw_u16={raw}")

        print(f"  payload[{rawend}:] n={len(pay)} distinct={len(distinct)} "
              f"distinct_in_pal={len(covered_vals)} "
              f"bytes_on_mapped={mapped_bytes}/{len(pay)} = {pct_bytes:.4f}%")

    r196 = stats[196]
    print("\n========== GO 196 ==========")
    print(
        f"196 mapped_indices={len(r196['pal'])} "
        f"payload_distinct={r196['distinct']} "
        f"payload_bytes_on_mapped={r196['mapped_bytes']}/{len(r196['pay'])} "
        f"= {r196['pct_bytes']:.4f}%"
    )

    print("\n========== B export ==========")
    print("id payload v4 ratio mapped_px% verdict files")
    MAGENTA = (255, 0, 255)
    for rid in floors:
        s = stats[rid]
        pay = s["pay"]
        v4 = s["v4"]
        raster = pay[:32768] + bytes(max(0, 32768 - len(pay)))
        raster = raster[:32768]
        pal = s["pal"]
        mapped_px = sum(1 for b in raster if b in pal)
        pct_px = 100.0 * mapped_px / 32768
        ratio = len(pay) / v4 if v4 else 0.0
        q = verdict(ratio)

        write_indexed(OUT / f"{rid}_128x256_raw.png", raster, 128, 256, pal, MAGENTA)
        write_indexed(OUT / f"{rid}_128x128_top.png", raster[:16384], 128, 128, pal, MAGENTA)
        write_indexed(OUT / f"{rid}_128x256_raw_grey.png", raster, 128, 256, pal, None)
        write_indexed(OUT / f"{rid}_128x128_top_grey.png", raster[:16384], 128, 128, pal, None)

        print(
            f"{rid} {len(pay):5d} {v4:5d} {ratio:.6f} "
            f"mapped_px={mapped_px}/32768 = {pct_px:.4f}% {q} "
            f"{rid}_128x256_raw.png + _top + _grey"
        )
        s["ratio"] = ratio
        s["verdict"] = q
        s["pct_px"] = pct_px

    print("\n========== C texture_list ==========")
    all256 = set(ids)
    by_id_levels: dict[int, list[int]] = defaultdict(list)
    by_id_slots: dict[int, Counter] = defaultdict(Counter)
    slot_ids: dict[int, Counter] = defaultdict(Counter)
    for lv in range(25):
        doc = json.loads((EXPORT / f"L{lv:02d}.json").read_text(encoding="utf-8"))
        tex = doc["texture_list"]
        if len(tex) != 8:
            print(f"WARN L{lv} texture_list len={len(tex)}")
        for slot, ent in enumerate(tex):
            sid = ent.get("shape_id")
            if sid is None:
                continue
            by_id_levels[sid].append(lv)
            by_id_slots[sid][slot] += 1
            slot_ids[slot][sid] += 1

    print("shape_id  n_levels  levels  slots")
    for sid in sorted(by_id_levels):
        levels = by_id_levels[sid]
        print(
            f"  {sid:3d}  {len(set(levels)):2d}  {sorted(set(levels))}  "
            f"slots={dict(by_id_slots[sid])}"
        )

    never = sorted(all256 - set(by_id_levels))
    print(f"\nC2 never referenced by any texture_list: n={len(never)} {never}")
    extra = sorted(set(by_id_levels) - all256)
    print(f"C2 texture_list IDs not in the 50 .256: {extra}")

    print("\nC3 195-202 in texture_list?")
    for rid in floors:
        if rid in by_id_levels:
            print(f"  {rid} YES levels={sorted(set(by_id_levels[rid]))} slots={dict(by_id_slots[rid])}")
        else:
            print(f"  {rid} NO")

    print("\nslot usage (slot -> shape_id: n_levels):")
    for slot in range(8):
        print(f"  slot {slot}: {dict(slot_ids[slot])}")

    print("\n========== DONE ==========")


if __name__ == "__main__":
    main()
