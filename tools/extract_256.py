"""Extract one PNG per tile from decompressed .256 resources.

s2 record: u32be offset, u16be A, u16be B, 8 zero bytes.
  class 1-5 (WALL): (offset, HEIGHT=A, WIDTH=B), row-major.
  class 6 (SPRITE): selected by s1.u16[0], not by resource id.
    READ_A: (offset, WIDTH=A, HEIGHT=B), row-major
    READ_B: (offset, HEIGHT=A, WIDTH=B), column-major
  Both sprite readings are transposes of the wall reading.

Index 2 is transparent. --magenta paints it opaque magenta.

s1.u16[3] != 0 is an overlay: CODE 5 @2030/@42 blits that s2 tile
onto the base plane at the u32be dest offset at s1+$E (row-major).
The compressor stores index 2 in that rectangle as a placeholder.

s1.u16[0] is not a palette selector. Colour table is selected by
texture_list variation (upper 4 bits of the slot word), not by
tile_index % table_count (disproven). --palette N paints with table
N; --all-palettes writes every table into <id>/pal<N>/.
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


def s1_overlay_dest_off(rec: dict) -> int:
    """u32be at s1+$E. 4423 = 39*113+16 for r192 s1 14-17."""
    return (rec["u16"][7] << 16) | rec["u16"][8]


def apply_s1_overlay(
    plane: np.ndarray,
    rec: dict,
    s2: list[dict],
    s3: bytes,
    cls: int,
) -> np.ndarray:
    """CODE 5 @2030 + @42. Blit overlay s2 onto the base plane.

    @2030 tst.w $6(a3): skip if s1.u16[3]==0.
    Dest pointer = base pixels + u32 at s1+$E.
    @42 copies width/4 longs per row, then adda dest_skip
    (base_w - overlay_w). No transparency test.
    """
    ov_i = rec["u16"][3]
    if ov_i == 0:
        return plane
    if not (0 <= ov_i < len(s2)):
        return plane
    ov = s2[ov_i]
    raw = s3[ov["off"] : ov["off"] + ov["wh"]]
    if len(raw) != ov["wh"] or ov["wh"] <= 0:
        return plane
    mode = "A" if is_sprite_tag(cls) else "baseline"
    patch = decode_plane(raw, ov["a"], ov["b"], mode)
    dest_off = s1_overlay_dest_off(rec)
    h, w = plane.shape
    ph, pw = patch.shape
    if w <= 0 or dest_off < 0 or dest_off >= h * w:
        return plane
    y, x = divmod(dest_off, w)
    if x + pw > w or y + ph > h:
        return plane
    out = plane.copy()
    out[y : y + ph, x : x + pw] = patch
    return out


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


def s2_wh_for_class(s2_rec: dict, cls: int) -> tuple[int, int]:
    """Class-appropriate (width, height). parse_s2 stores +4 as a, +6 as b."""
    if cls == 6:
        return s2_rec["a"], s2_rec["b"]
    return s2_rec["b"], s2_rec["a"]


def resolve_png_path(rid: int, s2_index: int, width: int, height: int) -> tuple[str, bool]:
    """Legacy root-level tile. Prefer palN paths via resolve_png_variants."""
    expected = f"{rid}/tile_{s2_index:02d}_{width}x{height}.png"
    if (OUT / expected).is_file():
        return expected, True
    folder = OUT / str(rid)
    if folder.is_dir():
        matches = sorted(folder.glob(f"tile_{s2_index:02d}_*.png"))
        if matches:
            return f"{rid}/{matches[0].name}", True
    return expected, False


def resolve_png_variants(
    rid: int, s2_index: int, width: int, height: int, table_count: int
) -> dict[str, str]:
    """Every colour-table variant. Paths are relative to reference/docs/256/."""
    png: dict[str, str] = {}
    ntab = table_count if table_count > 0 else 1
    for n in range(ntab):
        expected = f"{rid}/pal{n}/tile_{s2_index:02d}_{width}x{height}.png"
        if (OUT / expected).is_file():
            png[str(n)] = expected
            continue
        folder = OUT / str(rid) / f"pal{n}"
        if folder.is_dir():
            matches = sorted(folder.glob(f"tile_{s2_index:02d}_*.png"))
            if matches:
                png[str(n)] = f"{rid}/pal{n}/{matches[0].name}"
                continue
        fallback, exists = resolve_png_path(rid, s2_index, width, height)
        if exists:
            png[str(n)] = fallback
            continue
        png[str(n)] = expected
    return png


def png_field_str(png: str | dict) -> str:
    if isinstance(png, dict):
        return "{" + ", ".join(f"{k}:{v}" for k, v in png.items()) + "}"
    return str(png)


def collect_level_palettes(export_dir: Path) -> dict[str, dict]:
    """texture_list slot 0 → wall resource + variation for each level."""
    levels: dict[str, dict] = {}
    for lv in range(25):
        data = json.loads((export_dir / f"L{lv:02d}.json").read_text(encoding="utf-8"))
        slot0 = data["texture_list"][0]
        levels[str(lv)] = {
            "wall_resource": slot0["shape_id"],
            "wall_variation": slot0["variation"],
        }
    return levels


def build_resource_entry(rid: int, d: dict) -> tuple[dict, dict]:
    """One manifest resource. Extra notes are not written into the JSON."""
    hdr = d["hdr"]
    s1 = d["s1"]
    s2 = d["s2"]
    n_s2 = len(s2)
    table_count = len(d.get("tables") or [])
    tiles = []
    class1_heights: list[int] = []
    oob: list[dict] = []
    s2_users: dict[int, list[int]] = defaultdict(list)
    png_mismatch: list[dict] = []
    png_missing: list[dict] = []
    for rec in s1:
        cls = rec["u16"][0]
        flags = rec["u16"][1]
        s2i = rec["u16"][2]
        s2_users[s2i].append(rec["i"])
        if 0 <= s2i < n_s2:
            w, h = s2_wh_for_class(s2[s2i], cls)
        else:
            w, h = 0, 0
            oob.append({"s1_index": rec["i"], "s2_index": s2i, "s2_count": n_s2})
        png = resolve_png_variants(rid, s2i, w, h, table_count)
        for n, rel in png.items():
            expected = f"{rid}/pal{n}/tile_{s2i:02d}_{w}x{h}.png"
            exists = (OUT / rel).is_file()
            if exists and rel != expected:
                png_mismatch.append(
                    {
                        "s1_index": rec["i"],
                        "s2_index": s2i,
                        "palette": int(n),
                        "expected": expected,
                        "actual": rel,
                    }
                )
            if not exists:
                png_missing.append(
                    {
                        "s1_index": rec["i"],
                        "s2_index": s2i,
                        "palette": int(n),
                        "path": rel,
                    }
                )
        if cls == 1 and 0 <= s2i < n_s2:
            class1_heights.append(h)
        tiles.append(
            {
                "s1_index": rec["i"],
                "cls": cls,
                "flags": flags,
                "s2_index": s2i,
                "width": w,
                "height": h,
                "world_w": rec["i16"][4],
                "world_h": rec["i16"][5],
                "lift": rec["i16"][6],
                "png": png,
            }
        )
    if class1_heights:
        full_height = class1_heights[0]
        if len(set(class1_heights)) == 1:
            fh_note = f"class-1 height {full_height} (n={len(class1_heights)})"
        else:
            fh_note = (
                f"class-1 heights vary {sorted(set(class1_heights))}; "
                f"used first class-1 height {full_height}"
            )
    elif tiles:
        full_height = tiles[0]["height"]
        fh_note = (
            f"no class-1 tile; used first s1 tile height {full_height} "
            f"(cls={tiles[0]['cls']})"
        )
    else:
        full_height = 0
        fh_note = "no class-1 and no s1 records; used 0"
    entry = {
        "resource": rid,
        "tile_count": hdr["tile_count"] if hdr else len(s1),
        "full_height": full_height,
        "table_count": table_count,
        "tiles": tiles,
    }
    notes = {
        "s1_count": len(s1),
        "s2_count": n_s2,
        "header_tile_count": hdr["tile_count"] if hdr else None,
        "full_height_note": fh_note,
        "oob": oob,
        "s2_users": {k: v for k, v in s2_users.items()},
        "png_mismatch": png_mismatch,
        "png_missing": png_missing,
        "table_count": table_count,
    }
    return entry, notes


def build_manifest(decoded: dict[int, dict]) -> tuple[dict, dict]:
    resources = []
    notes: dict[int, dict] = {}
    for rid in sorted(decoded):
        d = decoded[rid]
        if not d["hdr"]:
            notes[rid] = {"skipped": "no header"}
            continue
        entry, extra = build_resource_entry(rid, d)
        resources.append(entry)
        notes[rid] = extra
    return {"resources": resources, "levels": collect_level_palettes(EXPORT)}, notes


def write_manifest(doc: dict, path: Path | None = None) -> Path:
    dest = path or (OUT / "manifest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return dest


def unpack_wall_word(word: int) -> dict:
    tag = (word >> 13) & 7
    selector = ((word >> 7) & 0x3F) + (0 if tag == 6 else 64)
    s1index = word & 0x7F
    return {
        "word": word,
        "tag": tag,
        "selector": selector,
        "s1index": s1index,
        "resource": selector + 128,
    }


def collect_level_wall_pairs(export_dir: Path) -> dict[int, dict]:
    """Per-level distinct (resource, s1index) from nonzero-tag sector walls."""
    out = {}
    for lv in range(25):
        path = export_dir / f"L{lv:02d}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        pairs: dict[tuple[int, int], dict] = {}
        n_words = 0
        n_drawn = 0
        word_counts: Counter = Counter()
        for sec in data["sectors"]:
            for w in sec["walls"]:
                n_words += 1
                word = ((w["type"] & 0xFF) << 8) | (w["texture"] & 0xFF)
                desc = unpack_wall_word(word)
                if desc["tag"] == 0:
                    continue
                n_drawn += 1
                word_counts[word] += 1
                key = (desc["resource"], desc["s1index"])
                if key not in pairs:
                    pairs[key] = {
                        "resource": desc["resource"],
                        "s1index": desc["s1index"],
                        "tag": desc["tag"],
                        "selector": desc["selector"],
                        "word": word,
                        "n": 0,
                    }
                pairs[key]["n"] += 1
        out[lv] = {
            "name": data.get("name", ""),
            "n_words": n_words,
            "n_drawn": n_drawn,
            "pairs": pairs,
            "word_counts": word_counts,
        }
    return out


def print_world_size_report(decoded: dict[int, dict]) -> None:
    """B1/B2: s1 i16[4]=world_w i16[5]=world_h i16[6]=lift vs tile w/h."""
    print("==== world size s1 i16[4]=world_w i16[5]=world_h i16[6]=lift ====")
    print("  id  s1  cls    tw    th   i16[4]  i16[5]  lift    k_h    k_w")
    per_res: dict[int, list[dict]] = {}
    for rid in sorted(decoded):
        d = decoded[rid]
        if not d.get("hdr"):
            continue
        s1 = d["s1"]
        s2 = d["s2"]
        n_s2 = len(s2)
        rows = []
        for rec in s1:
            cls = rec["u16"][0]
            s2i = rec["u16"][2]
            if 0 <= s2i < n_s2:
                w, h = s2_wh_for_class(s2[s2i], cls)
            else:
                w, h = 0, 0
            ww = rec["i16"][4]
            wh = rec["i16"][5]
            lift = rec["i16"][6]
            k_h = (wh / h) if h else None
            k_w = (ww / w) if w else None
            row = {
                "s1": rec["i"],
                "cls": cls,
                "w": w,
                "h": h,
                "world_h": wh,
                "world_w": ww,
                "lift": lift,
                "k_h": k_h,
                "k_w": k_w,
            }
            rows.append(row)
            khs = "  None" if k_h is None else f"{k_h:6.3f}"
            kws = "  None" if k_w is None else f"{k_w:6.3f}"
            print(
                f"  {rid:3d}  {rec['i']:2d}  {cls:3d}  {w:4d}  {h:4d}  "
                f"{ww:6d}  {wh:6d}  {lift:5d}  {khs}  {kws}"
            )
        per_res[rid] = rows
        ks = []
        for r in rows:
            if r["k_h"] is not None and r["k_w"] is not None:
                if abs(r["k_h"] - r["k_w"]) < 1e-6:
                    ks.append(r["k_h"])
                else:
                    ks.append((r["k_h"], r["k_w"]))
        uniq = []
        for k in ks:
            if k not in uniq:
                uniq.append(k)
        if not rows:
            note = "no s1"
        elif all(r["world_w"] == 0 and r["world_h"] == 0 for r in rows):
            note = "ALL_ZERO"
        elif len(uniq) == 1:
            note = f"k_consistent {uniq[0]}"
        else:
            note = f"k_varies {uniq}"
        print(f"  {rid:3d} SUMMARY n={len(rows)} {note}")

    print()
    print("==== B2 known objects (value/1024 sectors) ====")
    for rid, s1i, label in (
        (128, 0, "save_rune"),
        (153, 0, "pillar_0"),
        (153, 1, "pillar_1"),
        (153, 2, "pillar_2"),
    ):
        rows = per_res.get(rid, [])
        rec = next((r for r in rows if r["s1"] == s1i), None)
        if rec is None:
            print(f"  {label} resource={rid} s1={s1i} MISSING")
            continue
        print(
            f"  {label} resource={rid} s1={s1i} "
            f"world_w={rec['world_w']} world_h={rec['world_h']} "
            f"sectors_w={rec['world_w'] / 1024:.6f} "
            f"sectors_h={rec['world_h'] / 1024:.6f} "
            f"tile={rec['w']}x{rec['h']} k_w={rec['k_w']} k_h={rec['k_h']}"
        )


def print_manifest_report(doc: dict, notes: dict, export_dir: Path) -> dict:
    by_res = {r["resource"]: r for r in doc["resources"]}
    lookup = {}
    for r in doc["resources"]:
        for t in r["tiles"]:
            lookup[(r["resource"], t["s1_index"])] = t

    print("==== A2 resources 192 193 194 ====")
    for rid in (192, 193, 194):
        r = by_res.get(rid)
        extra = notes.get(rid, {})
        if r is None:
            print(f"  resource {rid}: MISSING from manifest")
            continue
        print(
            f"  resource={rid} tile_count={r['tile_count']} "
            f"table_count={r.get('table_count')} "
            f"s1_count={extra.get('s1_count')} s2_count={extra.get('s2_count')} "
            f"full_height={r['full_height']} ({extra.get('full_height_note')})"
        )
        print("  s1  cls  flags   s2    w    h  png")
        for t in r["tiles"]:
            print(
                f"  {t['s1_index']:2d}  {t['cls']:3d}  "
                f"0x{t['flags']:04X}  {t['s2_index']:3d}  "
                f"{t['width']:4d} {t['height']:4d}  {png_field_str(t['png'])}"
            )

    print()
    print("==== A3 s2 out-of-range / shared s2 ====")
    any_oob = False
    any_shared = False
    for rid in sorted(notes):
        extra = notes[rid]
        if extra.get("skipped"):
            print(f"  resource {rid} skipped: {extra['skipped']}")
            continue
        for row in extra.get("oob", []):
            any_oob = True
            print(
                f"  OOB resource={rid} s1={row['s1_index']} "
                f"s2_index={row['s2_index']} s2_count={row['s2_count']}"
            )
        for s2i, users in sorted(extra.get("s2_users", {}).items()):
            if len(users) > 1:
                any_shared = True
                print(
                    f"  SHARED resource={rid} s2={s2i} "
                    f"s1_indices={users} n={len(users)}"
                )
        for row in extra.get("png_mismatch", []):
            print(
                f"  PNG_NAME_MISMATCH resource={rid} s1={row['s1_index']} "
                f"s2={row['s2_index']} pal={row.get('palette')} "
                f"expected={row['expected']} actual={row['actual']}"
            )
        for row in extra.get("png_missing", []):
            if rid in (192, 193, 194):
                print(
                    f"  PNG_MISSING resource={rid} s1={row['s1_index']} "
                    f"s2={row['s2_index']} pal={row['palette']} path={row['path']}"
                )
        s1c = extra.get("s1_count")
        htc = extra.get("header_tile_count")
        if s1c is not None and htc is not None and s1c != htc:
            print(f"  TILE_COUNT_MISMATCH resource={rid} header={htc} s1={s1c}")
    if not any_oob:
        print("  OOB: none")
    if not any_shared:
        print("  SHARED: none")

    print()
    print("==== A3 full_height notes (every resource) ====")
    for rid in sorted(notes):
        extra = notes[rid]
        if extra.get("skipped"):
            continue
        r = by_res[rid]
        print(f"  {rid}: full_height={r['full_height']} {extra['full_height_note']}")

    levels = collect_level_wall_pairs(export_dir)
    print()
    print("==== A4 level wall (resource, s1index) vs manifest ====")
    unresolved_all: dict[tuple[int, int], dict] = {}
    per_level = []
    for lv in range(25):
        info = levels[lv]
        n = len(info["pairs"])
        bad = []
        for key, meta in sorted(info["pairs"].items()):
            if key not in lookup:
                bad.append(meta)
                slot = unresolved_all.setdefault(
                    key,
                    {
                        "resource": meta["resource"],
                        "s1index": meta["s1index"],
                        "tag": meta["tag"],
                        "word": meta["word"],
                        "levels": [],
                        "n": 0,
                    },
                )
                slot["levels"].append(lv)
                slot["n"] += meta["n"]
        ok = n - len(bad)
        print(
            f"  L{lv:02d} {info['name']!r} drawn_words={info['n_drawn']} "
            f"distinct_pairs={n} resolved={ok} unresolved={len(bad)}"
        )
        for meta in bad:
            print(
                f"    UNRESOLVED word=0x{meta['word']:04X} "
                f"resource={meta['resource']} s1={meta['s1index']} "
                f"tag={meta['tag']} selector={meta['selector']} n={meta['n']}"
            )
        per_level.append({"lv": lv, "n": n, "ok": ok, "bad": bad, "info": info})

    print()
    print("==== A4 unresolved pairs (union) ====")
    if not unresolved_all:
        print("  none")
    for key, meta in sorted(unresolved_all.items()):
        print(
            f"  resource={meta['resource']} s1={meta['s1index']} "
            f"word=0x{meta['word']:04X} tag={meta['tag']} "
            f"n_drawn={meta['n']} levels={meta['levels']}"
        )

    print()
    print("==== B1 per-level wall tiles ====")
    band_pngs = {0: set(), 1: set(), 2: set()}
    for lv in range(25):
        info = levels[lv]
        rows = []
        for (res, s1i), meta in info["pairs"].items():
            tile = lookup.get((res, s1i))
            if tile is None:
                rows.append(
                    {
                        "s1": s1i,
                        "res": res,
                        "cls": None,
                        "w": None,
                        "h": None,
                        "png": "UNRESOLVED",
                    }
                )
            else:
                rows.append(
                    {
                        "s1": s1i,
                        "res": res,
                        "cls": tile["cls"],
                        "w": tile["width"],
                        "h": tile["height"],
                        "png": tile["png"],
                    }
                )
                variants = (
                    list(tile["png"].values())
                    if isinstance(tile["png"], dict)
                    else [tile["png"]]
                )
                band = 0 if lv <= 6 else 1 if lv <= 15 else 2
                for p in variants:
                    band_pngs[band].add(p)
        rows.sort(key=lambda r: (r["s1"], r["res"]))
        print(f"  L{lv:02d} {info['name']!r} n={len(rows)}")
        for r in rows:
            print(
                f"    resource={r['res']} s1={r['s1']} cls={r['cls']} "
                f"w={r['w']} h={r['h']} png={png_field_str(r['png'])}"
            )

    print()
    print("==== B2 union PNGs per band ====")
    labels = [(0, "levels 0-6", 0), (1, "levels 7-15", 1), (2, "levels 16-24", 2)]
    for _i, label, key in labels:
        pngs = sorted(band_pngs[key])
        print(f"  {label} n={len(pngs)}")
        for p in pngs:
            print(f"    {p}")

    print()
    print("==== levels (texture_list slot 0) ====")
    for lv_s, meta in (doc.get("levels") or {}).items():
        print(
            f"  L{int(lv_s):02d} wall_resource={meta['wall_resource']} "
            f"wall_variation={meta['wall_variation']}"
        )

    print()
    print("==== B5 wall-descriptor resolve + palette PNG counts ====")
    for rid in (192, 193, 194):
        extra = notes.get(rid, {})
        n_missing = len(extra.get("png_missing") or [])
        ntab = extra.get("table_count") or 0
        written = 0
        for n in range(ntab):
            folder = OUT / str(rid) / f"pal{n}"
            if folder.is_dir():
                written += len(list(folder.glob("tile_*.png")))
        print(
            f"  resource={rid} table_count={ntab} pngs_on_disk={written} "
            f"manifest_png_missing={n_missing}"
        )

    print()
    print("==== B3 height histogram per class on 192/193/194 ====")
    for rid in (192, 193, 194):
        r = by_res.get(rid)
        if r is None:
            print(f"  resource {rid}: MISSING")
            continue
        by_cls: dict[int, Counter] = defaultdict(Counter)
        for t in r["tiles"]:
            by_cls[t["cls"]][t["height"]] += 1
        print(f"  resource {rid}")
        for cls in sorted(by_cls):
            hist = by_cls[cls]
            heights = sorted(hist)
            if len(heights) == 1:
                print(
                    f"    class {cls}: ALWAYS height={heights[0]} "
                    f"n={hist[heights[0]]}"
                )
            else:
                parts = " ".join(f"{h}:{hist[h]}" for h in heights)
                print(f"    class {cls}: VARIES {parts}")

    return {
        "unresolved": unresolved_all,
        "per_level": per_level,
        "lookup": lookup,
    }


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


def parse_ids(raw: str | None) -> set[int] | None:
    if raw is None or raw.strip() == "":
        return None
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out


def opaque_rgb_stats(img: Image.Image) -> dict:
    arr = np.asarray(img.convert("RGBA"))
    mask = arr[:, :, 3] > 0
    opaque = arr[mask][:, :3]
    if opaque.size == 0:
        return {
            "mean_r": None,
            "mean_g": None,
            "mean_b": None,
            "n_opaque": 0,
            "n_distinct": 0,
        }
    mean = opaque.mean(axis=0)
    uniq = np.unique(opaque, axis=0)
    return {
        "mean_r": float(mean[0]),
        "mean_g": float(mean[1]),
        "mean_b": float(mean[2]),
        "n_opaque": int(opaque.shape[0]),
        "n_distinct": int(uniq.shape[0]),
    }


def write_palette_strip(
    rid: int,
    images: list[tuple[int, Image.Image]],
    path: Path,
) -> list[dict]:
    """Side-by-side labelled palette variants of one tile."""
    if not images:
        return []
    label_h = 22
    pad = 8
    widths = [im.width for _n, im in images]
    heights = [im.height for _n, im in images]
    sheet_w = pad + sum(w + pad for w in widths)
    sheet_h = pad + label_h + max(heights) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    stats = []
    x = pad
    for n, im in images:
        rgba = im.convert("RGBA")
        bg = Image.fromarray(checkerboard(im.width, im.height), "RGB")
        bg.paste(rgba, (0, 0), rgba)
        sheet.paste(bg, (x, pad + label_h))
        draw.text((x, pad), f"{rid} tile0 pal{n}", fill=(255, 255, 0))
        st = opaque_rgb_stats(rgba)
        st["palette"] = n
        st["w"] = im.width
        st["h"] = im.height
        stats.append(st)
        x += im.width + pad
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return stats


def palette_indices_for(ntab: int, all_palettes: bool, palette: int | None) -> list[int]:
    if ntab <= 0:
        return [0]
    if all_palettes:
        return list(range(ntab))
    sel = 0 if palette is None else palette
    if not (0 <= sel < ntab):
        raise SystemExit(f"error: --palette {sel} not in 0..{ntab - 1}")
    return [sel]


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
    ap.add_argument(
        "--manifest-only",
        action="store_true",
        help="write reference/docs/256/manifest.json and print A/B reports; no re-render",
    )
    ap.add_argument(
        "--palette",
        type=int,
        default=None,
        help="colour-table index (0-based). Default 0. Not tile_index %% table_count.",
    )
    ap.add_argument(
        "--all-palettes",
        action="store_true",
        help="write every colour table under <id>/pal<N>/",
    )
    ap.add_argument(
        "--ids",
        default=None,
        help="comma-separated .256 resource ids to render (default: all)",
    )
    args = ap.parse_args()
    if args.all_palettes and args.palette is not None:
        raise SystemExit("error: --all-palettes cannot be combined with --palette")
    magenta = args.magenta
    sprite_read = None if args.sprite_read == "none" else args.sprite_read
    id_filter = parse_ids(args.ids)

    blobs = load_256()
    decoded = load_decoded(blobs)
    print(
        f"loaded {len(blobs)} .256 resources  magenta={magenta}  "
        f"sprite_read={sprite_read}  all_palettes={args.all_palettes}  "
        f"palette={args.palette}  ids={sorted(id_filter) if id_filter else 'ALL'}"
    )
    print()

    doc, notes = build_manifest(decoded)
    dest = write_manifest(doc)
    print(f"wrote {dest} resources={len(doc['resources'])}")
    if args.manifest_only:
        print_world_size_report(decoded)
        print_manifest_report(doc, notes, EXPORT)
        return

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
        pal = tables[0]["pal"] if tables else {}
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
    print("  colour table is --palette / --all-palettes, never tile_index % table_count")
    print("  id  pal  wrote  mean_v   mean_h  iso")
    written_counts: dict[int, dict[int, int]] = {}
    for rid in sorted(decoded):
        if id_filter is not None and rid not in id_filter:
            continue
        d = decoded[rid]
        tables = d["tables"]
        ntab = len(tables)
        try:
            pals = palette_indices_for(ntab, args.all_palettes, args.palette)
        except SystemExit as e:
            raise SystemExit(f"{e} (resource {rid} table_count={ntab})") from e
        out_dir = OUT / str(rid)
        written_counts[rid] = {}
        for pal_i in pals:
            pal = tables[pal_i]["pal"] if ntab else {}
            pal_dir = out_dir / f"pal{pal_i}"
            if pal_dir.exists():
                for old in pal_dir.glob("tile_*.png"):
                    old.unlink()
            pal_dir.mkdir(parents=True, exist_ok=True)
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
                path = pal_dir / f"tile_{t['i']:02d}_{w}x{h}.png"
                render_plane(plane, pal, path, magenta)
                imgs.append(Image.open(path).convert("RGBA"))
                meta.append(t)
                scores.append(opaque_correlations(plane))
            written_counts[rid][pal_i] = len(imgs)
            mv, mh = mean_vh(scores)
            print(f"  {rid:3d}  {pal_i:3d}  {len(imgs):5d}  {fmt_vh(mv, mh)}")
            if rid in (192, 193, 194) or not args.all_palettes:
                sheet_name = (
                    f"{rid}_sheet_pal{pal_i}.png"
                    if args.all_palettes
                    else f"{rid}_sheet.png"
                )
                write_contact_sheet(rid, meta, imgs, OUT / sheet_name)

    print()
    print("==== palette PNG counts ====")
    for rid, by_pal in written_counts.items():
        total = sum(by_pal.values())
        parts = " ".join(f"pal{n}={c}" for n, c in sorted(by_pal.items()))
        print(f"  resource={rid} total={total} {parts}")

    doc, notes = build_manifest(decoded)
    dest = write_manifest(doc)
    print(f"rewrote {dest} resources={len(doc['resources'])} levels={len(doc['levels'])}")
    print_manifest_report(doc, notes, EXPORT)

    print()
    print("==== C palette comparison strips (tile 0) ====")
    compare_dir = OUT / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    for rid in (192, 193, 194):
        if id_filter is not None and rid not in id_filter:
            continue
        d = decoded[rid]
        if not d["s2"] or "payload" not in d["s2"][0]:
            print(f"  {rid} tile0 MISSING")
            continue
        t0 = d["s2"][0]
        ntab = len(d["tables"])
        images = []
        for pal_i in range(ntab):
            path = OUT / str(rid) / f"pal{pal_i}" / f"tile_00_{t0['w']}x{t0['h']}.png"
            if not path.is_file():
                print(f"  {rid} pal{pal_i} {path.name} MISSING")
                continue
            images.append((pal_i, Image.open(path)))
        out_path = compare_dir / f"{rid}_tile00_palettes.png"
        stats = write_palette_strip(rid, images, out_path)
        print(f"  wrote {out_path} n={len(images)}")
        for st in stats:
            print(
                f"    pal{st['palette']} {st['w']}x{st['h']} "
                f"meanRGB=({st['mean_r']:.2f},{st['mean_g']:.2f},{st['mean_b']:.2f}) "
                f"opaque={st['n_opaque']} distinct={st['n_distinct']}"
            )

    print()
    print("==== C4 sheets written for 128,129,133,139,163 ====")
    for rid in (128, 129, 133, 139, 163):
        if id_filter is not None and rid not in id_filter:
            continue
        dims = [(t["i"], t.get("w"), t.get("h")) for t in decoded[rid]["s2"] if "payload" in t]
        print(f"  id={rid} n={len(dims)} {dims}")


if __name__ == "__main__":
    main()
