"""Extract one PNG per tile from decompressed .256 resources.

s2 record: u32be offset, u16be A, u16be B, 8 zero bytes.
  class 1-5 (WALL): (offset, HEIGHT=A, WIDTH=B), row-major.
  class 6 (SPRITE): selected by s1.u16[0], not by resource id.
    READ_A: (offset, WIDTH=A, HEIGHT=B), row-major
    READ_B: (offset, HEIGHT=A, WIDTH=B), column-major
  Both sprite readings are transposes of the wall reading.

Index 2 is transparent. --magenta paints it opaque magenta.

s1.u16[0] is not a palette selector. RGB table used for painting is
table (record_index % table_count) — HYPOTHESIS.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from decode_256 import decompress, load_256, parse_header, u16, u32

OUT = ROOT / "reference/docs/256"
EXPORT = ROOT / "reference/export"
MAGENTA = (255, 0, 255, 255)
INDEX_TRANSPARENT = 2


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def i16(b: bytes, o: int) -> int:
    return struct.unpack_from(">h", b, o)[0]


def align4(n: int) -> int:
    return (n + 3) & ~3


def s2_count(hdr: dict) -> int:
    return (hdr["v3"] - hdr["v2"]) // 16


def s1_count(hdr: dict) -> int:
    return (hdr["v2"] - hdr["v1"]) // 32


def parse_tables(buf: bytes, hdr: dict) -> list[dict]:
    ntab = u16(buf, 0x14)
    nent = u16(buf, 0x16)
    tables = []
    off = 24
    for i in range(ntab):
        pal: dict[int, tuple[int, int, int]] = {}
        start = off
        first = u16(buf, off) if off + 2 <= len(buf) else None
        for _ in range(nent):
            if off + 8 > len(buf):
                break
            idx = u16(buf, off)
            r, g, b = struct.unpack_from(">HHH", buf, off + 2)
            pal[idx] = (r >> 8, g >> 8, b >> 8)
            off += 8
        last = first + nent - 1 if first is not None else None
        tables.append(
            {
                "i": i,
                "start": start,
                "n": nent,
                "first": first,
                "last": last,
                "end": off,
                "pal": pal,
            }
        )
    return tables


def parse_s2(buf: bytes, hdr: dict) -> list[dict]:
    """Wall layout: offset, height, width. Record count is (v3-v2)/16."""
    n = s2_count(hdr)
    tiles = []
    for i in range(n):
        base = hdr["v2"] + i * 16
        rec = buf[base : base + 16]
        off = u32(buf, base)
        height = u16(buf, base + 4)
        width = u16(buf, base + 6)
        tiles.append(
            {
                "i": i,
                "off": off,
                "a": height,
                "b": width,
                "h": height,
                "w": width,
                "wh": width * height,
                "raw": rec,
                "u16": [u16(rec, j * 2) for j in range(8)],
                "u32": [u32(rec, j * 4) for j in range(4)],
            }
        )
    return tiles


def parse_s1(buf: bytes, hdr: dict) -> list[dict]:
    n = s1_count(hdr)
    rows = []
    for i in range(n):
        base = hdr["v1"] + i * 32
        rec = buf[base : base + 32]
        rows.append(
            {
                "i": i,
                "raw": rec,
                "u16": [u16(rec, j * 2) for j in range(16)],
                "i16": [i16(rec, j * 2) for j in range(16)],
                "u32": [u32(rec, j * 4) for j in range(8)],
            }
        )
    return rows


def tile_in_s3(t: dict, v4: int) -> bool:
    if t["a"] <= 0 or t["b"] <= 0:
        return False
    if t["a"] > 4096 or t["b"] > 4096:
        return False
    if t["off"] < 0 or t["wh"] < 0:
        return False
    return t["off"] + t["wh"] <= v4


ISOTROPY_DELTA = 0.15


def tile_class_tag(s1: list[dict], tile_index: int) -> int | None:
    if tile_index < len(s1):
        return s1[tile_index]["u16"][0]
    tags = [r["u16"][0] for r in s1]
    if not tags:
        return None
    if all(t == tags[0] for t in tags):
        return tags[0]
    return Counter(tags).most_common(1)[0][0]


def resource_class_tags(s1: list[dict]) -> list[int]:
    return [r["u16"][0] for r in s1]


def is_sprite_tag(tag: int | None) -> bool:
    return tag == 6


def is_wall_tag(tag: int | None) -> bool:
    return tag is not None and 1 <= tag <= 5


def decode_plane(raw: bytes, a: int, b: int, mode: str) -> np.ndarray:
    """Return index plane shaped (height, width).

    baseline / WALL: A=height, B=width, row-major
    READ_A: swap fields, row-major → (height=B, width=A)
    READ_B: keep fields, column-major → (height=A, width=B)
    """
    pix = np.frombuffer(raw, dtype=np.uint8)
    if pix.size != a * b:
        raise ValueError(f"payload {pix.size} != {a}*{b}")
    if mode == "baseline":
        return pix.reshape((a, b))
    if mode == "A":
        return pix.reshape((b, a))
    if mode == "B":
        return pix.reshape((b, a)).T
    raise ValueError(mode)


def display_wh(a: int, b: int, mode: str) -> tuple[int, int]:
    if mode == "A":
        return a, b
    return b, a


def is_isotropic(v: float | None, h: float | None, delta: float = ISOTROPY_DELTA) -> bool:
    if v is None or h is None:
        return False
    return abs(v - h) <= delta


def mean_vh(rows: list[dict]) -> tuple[float | None, float | None]:
    vs = [r["v_corr"] for r in rows if r["v_corr"] is not None]
    hs = [r["h_corr"] for r in rows if r["h_corr"] is not None]
    return (
        float(np.mean(vs)) if vs else None,
        float(np.mean(hs)) if hs else None,
    )


def palette_lut(pal: dict[int, tuple[int, int, int]], magenta: bool) -> np.ndarray:
    lut = np.zeros((256, 4), dtype=np.uint8)
    lut[:, 0] = 255
    lut[:, 1] = 0
    lut[:, 2] = 255
    lut[:, 3] = 255
    for idx, (r, g, b) in pal.items():
        lut[idx] = (r, g, b, 255)
    if magenta:
        lut[INDEX_TRANSPARENT] = (255, 0, 255, 255)
    else:
        lut[INDEX_TRANSPARENT] = (0, 0, 0, 0)
    return lut


def render_plane(
    plane: np.ndarray,
    pal: dict[int, tuple[int, int, int]],
    path: Path,
    magenta: bool,
) -> tuple[int, int]:
    lut = palette_lut(pal, magenta)
    arr = lut[plane]
    keys = np.zeros(256, dtype=bool)
    for idx in pal:
        keys[idx] = True
    trans = int((plane == INDEX_TRANSPARENT).sum())
    unmapped = int(((plane != INDEX_TRANSPARENT) & ~keys[plane]).sum())
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path)
    return trans, unmapped


def render_tile(
    pixels: bytes,
    w: int,
    h: int,
    pal: dict[int, tuple[int, int, int]],
    path: Path,
    magenta: bool,
) -> tuple[int, int]:
    """Row-major RGBA. Index 2 is transparent unless magenta=True."""
    pix = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w))
    return render_plane(pix, pal, path, magenta)


def pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 2:
        return None
    sa = float(a.std())
    sb = float(b.std())
    if sa == 0.0 and sb == 0.0:
        return 1.0 if np.array_equal(a, b) else None
    if sa == 0.0 or sb == 0.0:
        return None
    return float(np.corrcoef(a.astype(np.float64), b.astype(np.float64))[0, 1])


def opaque_correlations(pix: np.ndarray) -> dict:
    """Vertical and horizontal Pearson on index values where both samples are opaque."""
    h, w = pix.shape
    opaque = pix != INDEX_TRANSPARENT
    v_left: list[int] = []
    v_right: list[int] = []
    if h >= 2:
        a = pix[:-1]
        b = pix[1:]
        m = opaque[:-1] & opaque[1:]
        if m.any():
            v_left = a[m].tolist()
            v_right = b[m].tolist()
    h_left: list[int] = []
    h_right: list[int] = []
    if w >= 2:
        a = pix[:, :-1]
        b = pix[:, 1:]
        m = opaque[:, :-1] & opaque[:, 1:]
        if m.any():
            h_left = a[m].tolist()
            h_right = b[m].tolist()
    v = pearson(np.array(v_left, dtype=np.float64), np.array(v_right, dtype=np.float64)) if v_left else None
    hh = pearson(np.array(h_left, dtype=np.float64), np.array(h_right, dtype=np.float64)) if h_left else None
    return {
        "v_corr": v,
        "h_corr": hh,
        "v_pairs": len(v_left),
        "h_pairs": len(h_left),
        "opaque": int(opaque.sum()),
        "n": int(pix.size),
    }


def reshape_stride(pixels: bytes, stride: int) -> np.ndarray | None:
    if stride <= 0:
        return None
    n = len(pixels)
    rows = n // stride
    if rows < 2:
        return None
    return np.frombuffer(pixels[: rows * stride], dtype=np.uint8).reshape((rows, stride))


def checkerboard(w: int, h: int, cell: int = 8) -> np.ndarray:
    yy, xx = np.indices((h, w))
    bit = ((yy // cell) + (xx // cell)) & 1
    arr = np.empty((h, w, 3), dtype=np.uint8)
    arr[bit == 0] = (180, 180, 180)
    arr[bit == 1] = (100, 100, 100)
    return arr


def write_contact_sheet(rid: int, tiles: list[dict], images: list[Image.Image], path: Path) -> None:
    if not tiles:
        return
    label_h = 16
    pad = 6
    max_row = 2048
    rows: list[list[int]] = []
    cur: list[int] = []
    cur_w = pad
    cur_h = 0
    heights: list[int] = []
    for i, (t, im) in enumerate(zip(tiles, images)):
        cw = im.width + pad
        ch = im.height + label_h + pad
        if cur and cur_w + cw > max_row:
            rows.append(cur)
            heights.append(cur_h)
            cur = []
            cur_w = pad
            cur_h = 0
        cur.append(i)
        cur_w += cw
        cur_h = max(cur_h, ch)
    if cur:
        rows.append(cur)
        heights.append(cur_h)
    sheet_w = 0
    for row in rows:
        rw = pad
        for i in row:
            rw += images[i].width + pad
        sheet_w = max(sheet_w, rw)
    sheet_h = pad + sum(heights)
    sheet = Image.new("RGB", (max(sheet_w, 1), max(sheet_h, 1)), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for row, rh in zip(rows, heights):
        x = pad
        for i in row:
            t = tiles[i]
            im = images[i]
            bg = Image.fromarray(checkerboard(im.width, im.height), "RGB")
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            bg.paste(im, (0, 0), im)
            sheet.paste(bg, (x, y + label_h))
            draw.text((x, y), f"{t['i']:02d} {t['w']}x{t['h']}", fill=(255, 255, 0))
            x += im.width + pad
        y += rh
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def dump_s1(label: str, rec: dict) -> list[str]:
    lines = [f"  {label}  {hx(rec['raw'])}"]
    lines.append("       u16 " + " ".join(f"{v:7d}" for v in rec["u16"]))
    lines.append("       i16 " + " ".join(f"{v:7d}" for v in rec["i16"]))
    lines.append("       u32 " + " ".join(f"{v:10d}" for v in rec["u32"]))
    return lines


def load_decoded(blobs: dict[int, bytes]) -> dict[int, dict]:
    out = {}
    for rid, src in sorted(blobs.items()):
        dec = decompress(src)
        buf = dec["out"]
        hdr = parse_header(buf)
        out[rid] = {
            "buf": buf,
            "hdr": hdr,
            "exact": dec["exact"],
            "tables": parse_tables(buf, hdr) if hdr else [],
            "s1": parse_s1(buf, hdr) if hdr else [],
            "s2": parse_s2(buf, hdr) if hdr else [],
        }
    return out


def count_s3_reserved(s3: bytes, tiles: list[dict]) -> dict:
    raw = np.frombuffer(s3, dtype=np.uint8)
    tile_parts = []
    for t in tiles:
        if tile_in_s3(t, len(s3)):
            tile_parts.append(raw[t["off"] : t["off"] + t["wh"]])
    tile_bytes = np.concatenate(tile_parts) if tile_parts else np.array([], dtype=np.uint8)
    return {
        "s3_n": int(raw.size),
        "s3_0": int((raw == 0).sum()),
        "s3_1": int((raw == 1).sum()),
        "s3_2": int((raw == 2).sum()),
        "tile_n": int(tile_bytes.size),
        "tile_0": int((tile_bytes == 0).sum()) if tile_bytes.size else 0,
        "tile_1": int((tile_bytes == 1).sum()) if tile_bytes.size else 0,
        "tile_2": int((tile_bytes == 2).sum()) if tile_bytes.size else 0,
    }


def s1_geom_correlations(s1: list[dict], s2: list[dict]) -> list[dict]:
    n = min(len(s1), len(s2))
    if n < 2:
        return []
    w = np.array([s2[i]["w"] for i in range(n)], dtype=np.float64)
    h = np.array([s2[i]["h"] for i in range(n)], dtype=np.float64)
    targets = {
        "w": w,
        "h": h,
        "w/2": w / 2.0,
        "h/2": h / 2.0,
        "-w/2": -w / 2.0,
        "-h/2": -h / 2.0,
    }
    hits = []
    for col in range(16):
        col_v = np.array([s1[i]["i16"][col] for i in range(n)], dtype=np.float64)
        for tname, tv in targets.items():
            r = pearson(col_v, tv)
            if r is None:
                continue
            hits.append({"col": col, "target": tname, "r": r, "n": n})
    hits.sort(key=lambda x: abs(x["r"]), reverse=True)
    return hits


def score_tile(raw: bytes, a: int, b: int, mode: str) -> dict:
    plane = decode_plane(raw, a, b, mode)
    c = opaque_correlations(plane)
    w, h = display_wh(a, b, mode)
    c["w"] = w
    c["h"] = h
    c["mode"] = mode
    return c


def fmt_vh(v: float | None, h: float | None) -> str:
    vs = "   None" if v is None else f"{v:7.4f}"
    hs = "   None" if h is None else f"{h:7.4f}"
    iso = "ISO" if is_isotropic(v, h) else "ANI"
    return f"{vs}  {hs}  {iso}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--magenta",
        action="store_true",
        help="paint index 2 as opaque magenta instead of transparent",
    )
    ap.add_argument(
        "--sprite-read",
        choices=("A", "B", "none"),
        default="A",
        help="class-6 reading: A=swap fields row-major (default), B=column-major, none=wall reading",
    )
    args = ap.parse_args()
    magenta = args.magenta
    sprite_read = None if args.sprite_read == "none" else args.sprite_read

    blobs = load_256()
    decoded = load_decoded(blobs)
    print(f"loaded {len(blobs)} .256 resources  magenta={magenta}  sprite_read={sprite_read}")
    print()

    rows = []
    for rid in sorted(decoded):
        d = decoded[rid]
        hdr = d["hdr"]
        s3 = d["buf"][hdr["v3"] : hdr["v3"] + hdr["v4"]]
        for t in d["s2"]:
            if not tile_in_s3(t, hdr["v4"]):
                continue
            raw = s3[t["off"] : t["off"] + t["wh"]]
            if len(raw) != t["wh"]:
                continue
            tag = tile_class_tag(d["s1"], t["i"])
            base = score_tile(raw, t["a"], t["b"], "baseline")
            ra = score_tile(raw, t["a"], t["b"], "A")
            rb = score_tile(raw, t["a"], t["b"], "B")
            rows.append(
                {
                    "rid": rid,
                    "i": t["i"],
                    "tag": tag,
                    "a": t["a"],
                    "b": t["b"],
                    "square": t["a"] == t["b"],
                    "raw": raw,
                    "baseline": base,
                    "A": ra,
                    "B": rb,
                }
            )
            t["class"] = tag
            t["payload"] = raw

    print("==== A1 per-tile baseline ====")
    print("  id  tile  class    A    B  sq   mean_v   mean_h  iso")
    for r in rows:
        b = r["baseline"]
        print(
            f"  {r['rid']:3d}  {r['i']:4d}  {r['tag']!s:>5}  {r['a']:4d}  {r['b']:4d}  "
            f"{int(r['square'])}  {fmt_vh(b['v_corr'], b['h_corr'])}"
        )

    class6 = [r for r in rows if is_sprite_tag(r["tag"])]
    class15 = [r for r in rows if is_wall_tag(r["tag"])]
    sq = [r for r in class6 if r["square"]]
    nsq = [r for r in class6 if not r["square"]]

    def iso_of(r, mode="baseline"):
        c = r[mode]
        return is_isotropic(c["v_corr"], c["h_corr"])

    n_sq_iso = sum(1 for r in sq if iso_of(r))
    n_sq_ani = sum(1 for r in sq if not iso_of(r))
    n_ns_iso = sum(1 for r in nsq if iso_of(r))
    n_ns_ani = sum(1 for r in nsq if not iso_of(r))
    sq_flag = np.array([1.0 if r["square"] else 0.0 for r in class6], dtype=np.float64)
    iso_flag = np.array([1.0 if iso_of(r) else 0.0 for r in class6], dtype=np.float64)
    phi = pearson(sq_flag, iso_flag)

    print()
    print("==== A2 square vs isotropic (class-6 tiles, baseline) ====")
    print(f"  class6 tiles={len(class6)}  square={len(sq)}  nonsquare={len(nsq)}")
    print(f"  square-and-isotropic       {n_sq_iso}")
    print(f"  square-and-anisotropic     {n_sq_ani}")
    print(f"  nonsquare-and-isotropic    {n_ns_iso}")
    print(f"  nonsquare-and-anisotropic  {n_ns_ani}")
    print(f"  pearson(is_square, is_isotropic)={phi}")

    print()
    print("==== A3 per-resource mean_v/mean_h  baseline / READ_A / READ_B ====")
    print("  id  class  n   base_v   base_h   A_v      A_h      B_v      B_h")
    per_res = {}
    for rid in sorted(decoded):
        rs = [r for r in rows if r["rid"] == rid]
        if not rs:
            continue
        tags = resource_class_tags(decoded[rid]["s1"])
        tag_s = ",".join(str(x) for x in sorted(set(tags))) if tags else "?"
        bv, bh = mean_vh([r["baseline"] for r in rs])
        av, ah = mean_vh([r["A"] for r in rs])
        b2v, b2h = mean_vh([r["B"] for r in rs])
        per_res[rid] = {
            "n": len(rs),
            "tags": tags,
            "sprite": all(is_sprite_tag(t) for t in tags) if tags else False,
            "wall": all(is_wall_tag(t) for t in tags) if tags else False,
            "base": (bv, bh),
            "A": (av, ah),
            "B": (b2v, b2h),
        }
        print(
            f"  {rid:3d}  {tag_s:>6}  {len(rs):2d}  {fmt_vh(bv, bh)}  "
            f"{fmt_vh(av, ah)}  {fmt_vh(b2v, b2h)}"
        )

    sprite_ids = [rid for rid, p in per_res.items() if p["sprite"]]
    wall_ids = [rid for rid, p in per_res.items() if p["wall"]]

    def n_iso_res(ids, mode):
        n = 0
        for rid in ids:
            v, h = per_res[rid][mode]
            if is_isotropic(v, h):
                n += 1
        return n

    print()
    print("==== A4 isotropic resource counts ====")
    print(
        f"  class-6 resources n={len(sprite_ids)}  "
        f"baseline={n_iso_res(sprite_ids, 'base')}  "
        f"READ_A={n_iso_res(sprite_ids, 'A')}  "
        f"READ_B={n_iso_res(sprite_ids, 'B')}"
    )
    print(
        f"  class-1-5 resources n={len(wall_ids)}  "
        f"baseline={n_iso_res(wall_ids, 'base')}  "
        f"READ_A={n_iso_res(wall_ids, 'A')}  "
        f"READ_B={n_iso_res(wall_ids, 'B')}"
    )
    print(
        f"GO/NO-GO: class6_iso baseline={n_iso_res(sprite_ids, 'base')}/{len(sprite_ids)}  "
        f"READ_A={n_iso_res(sprite_ids, 'A')}/{len(sprite_ids)}  "
        f"READ_B={n_iso_res(sprite_ids, 'B')}/{len(sprite_ids)}  "
        f"controls_if_changed baseline={n_iso_res(wall_ids, 'base')}/{len(wall_ids)}  "
        f"READ_A={n_iso_res(wall_ids, 'A')}/{len(wall_ids)}  "
        f"READ_B={n_iso_res(wall_ids, 'B')}/{len(wall_ids)}"
    )
    print(f"  class-6 ids: {sprite_ids}")
    print(f"  class-1-5 ids: {wall_ids}")
    print("  class-6 isotropic under baseline:", [rid for rid in sprite_ids if is_isotropic(*per_res[rid]["base"])])
    print("  class-6 isotropic under READ_A:", [rid for rid in sprite_ids if is_isotropic(*per_res[rid]["A"])])
    print("  class-6 isotropic under READ_B:", [rid for rid in sprite_ids if is_isotropic(*per_res[rid]["B"])])
    print("  class-1-5 isotropic under baseline:", [rid for rid in wall_ids if is_isotropic(*per_res[rid]["base"])])
    print("  class-1-5 isotropic under READ_A:", [rid for rid in wall_ids if is_isotropic(*per_res[rid]["A"])])
    print("  class-1-5 isotropic under READ_B:", [rid for rid in wall_ids if is_isotropic(*per_res[rid]["B"])])

    print()
    print("==== B1 compare renders ====")
    compare = OUT / "compare"
    compare.mkdir(parents=True, exist_ok=True)
    targets = [
        (163, 0),
        (163, 1),
        (128, 0),
        (128, 25),
        (129, 2),
        (129, 12),
        (187, 0),
        (191, 0),
    ]
    for rid, idx in targets:
        d = decoded[rid]
        t = d["s2"][idx]
        raw = t.get("payload")
        if raw is None:
            continue
        tables = d["tables"]
        pal = tables[idx % len(tables)]["pal"] if tables else {}
        for mode, suffix in (("A", "A"), ("B", "B")):
            plane = decode_plane(raw, t["a"], t["b"], mode)
            path = compare / f"{rid}_{idx}_{suffix}.png"
            render_plane(plane, pal, path, magenta)
            print(f"  wrote {path} shape={plane.shape[1]}x{plane.shape[0]}")

    if sprite_read is None:
        print()
        print("C skipped (--sprite-read A|B not set)")
        return

    print()
    print(f"==== C apply READ_{sprite_read} to class 6, wall reading unchanged ====")
    print("  id  wrote  mean_v   mean_h  iso")
    for rid in sorted(decoded):
        d = decoded[rid]
        hdr = d["hdr"]
        tables = d["tables"]
        ntab = len(tables)
        out_dir = OUT / str(rid)
        if out_dir.exists():
            for old in out_dir.glob("tile_*.png"):
                old.unlink()
        imgs = []
        meta = []
        scores = []
        for t in d["s2"]:
            raw = t.get("payload")
            if raw is None:
                continue
            tag = t.get("class")
            mode = sprite_read if is_sprite_tag(tag) else "baseline"
            plane = decode_plane(raw, t["a"], t["b"], mode)
            w, h = display_wh(t["a"], t["b"], mode)
            t["w"] = w
            t["h"] = h
            sel = (t["i"] % ntab) if ntab else 0
            pal = tables[sel]["pal"] if ntab else {}
            path = out_dir / f"tile_{t['i']:02d}_{w}x{h}.png"
            render_plane(plane, pal, path, magenta)
            imgs.append(Image.open(path).convert("RGBA"))
            meta.append(t)
            scores.append(opaque_correlations(plane))
        mv, mh = mean_vh(scores)
        print(f"  {rid:3d}  {len(imgs):5d}  {fmt_vh(mv, mh)}")
        write_contact_sheet(rid, meta, imgs, OUT / f"{rid}_sheet.png")

    print()
    print("==== C4 sheets written for 128,129,133,139,163 ====")
    for rid in (128, 129, 133, 139, 163):
        dims = [(t["i"], t["w"], t["h"]) for t in decoded[rid]["s2"] if "payload" in t]
        print(f"  id={rid} n={len(dims)} {dims}")


if __name__ == "__main__":
    main()
