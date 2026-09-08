#!/usr/bin/env python3
"""Re-export .256 tiles as native index R8 PNGs plus shade LUTs.

Ports CODE 5 collect @2986, remap @3670/@4, run group @3884/@2862,
shade fill @4044 from bytes. Writes only under out/.
"""
from __future__ import annotations

import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from decode_256 import decompress, load_256, parse_header, u16, u32  # noqa: E402
from extract_256 import (  # noqa: E402
    apply_s1_overlay,
    decode_plane,
    is_sprite_tag,
    parse_s1,
    parse_s2,
    parse_tables,
    s1_overlay_dest_off,
    s2_wh_for_class,
    tile_class_tag,
    tile_in_s3,
)
from mac_containers import resources_of_type  # noqa: E402
from pid_level import load_maps  # noqa: E402
from shapes_pass1 import parse_clut  # noqa: E402

MAPS_CANDIDATES = (
    ROOT / "data/hfs/Pathways_1995/Maps",
    ROOT / "data/cd/hfs/Pathways_1995/Maps",
)
APP_CANDIDATES = (
    ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc",
    ROOT / "data/cd/hfs/Pathways_1995/Pathways Into Darkness.rsrc",
)
EXPORT = ROOT / "reference/export"
RGB_ROOT = ROOT / "reference/docs/256"
OUT = ROOT / "out"
R8_DIR = OUT / "256-r8"
LUT_DIR = OUT / "256-lut"
VERIFY_DIR = OUT / "_verify_rgb"
MANIFEST_PATH = OUT / "256-manifest.json"
REPORT_PATH = OUT / "task-r8-report.txt"

INDEX_TRANSPARENT = 2
INDEX_PAD = 0
SLOT_BLACK = 0x0F  # 15
CLUT_PLANT = 0x6A  # 106
N_CLUT_PLANT = 15  # @3214 moveq #$f; copies unique[106..120]
FADE_LAST = 0x79  # 121; JT 178 range $6A..$79

# JT 240 CODE 7 @4: word at A5-$104A + type*$5C +$4. DATAINIT dest_size-$104A.
# slot = word & $FFF, variation = (word >> 12) & $F. Types 0..16 used in maps.
_JT240_WORDS: dict[int, int] | None = None


def jt240_words() -> dict[int, int]:
    """Monster type -> JT 180 request word. Read from DATAINIT bytes."""
    global _JT240_WORDS
    if _JT240_WORDS is not None:
        return _JT240_WORDS
    from save_editor import CODE_DIR, DATAINIT_HDR, datainit_uncompress

    code11 = (CODE_DIR / "CODE_11.bin").read_bytes()
    hdr = DATAINIT_HDR
    dest_size = struct.unpack(">I", code11[hdr : hdr + 4])[0]
    off_data = struct.unpack(">I", code11[hdr + 8 : hdr + 12])[0]
    off_rel = struct.unpack(">I", code11[hdr + 12 : hdr + 16])[0]
    world = datainit_uncompress(code11[hdr + off_data : hdr + off_rel], dest_size)
    off = dest_size - 0x104A
    out: dict[int, int] = {}
    for i in range(17):
        out[i] = struct.unpack_from(">H", world, off + i * 0x5C + 4)[0]
    _JT240_WORDS = out
    return out


def door_rate_table(textures: list[int]) -> list[dict]:
    """A5 -$8E0, stride 16. JT 254. DATAINIT dest_size-$8E0."""
    from save_editor import CODE_DIR, DATAINIT_HDR, datainit_uncompress

    code11 = (CODE_DIR / "CODE_11.bin").read_bytes()
    hdr = DATAINIT_HDR
    dest_size = struct.unpack(">I", code11[hdr : hdr + 4])[0]
    off_data = struct.unpack(">I", code11[hdr + 8 : hdr + 12])[0]
    off_rel = struct.unpack(">I", code11[hdr + 12 : hdr + 16])[0]
    world = datainit_uncompress(code11[hdr + off_data : hdr + off_rel], dest_size)
    off = dest_size - 0x8E0
    rows = []
    for tex in textures:
        base = off + tex * 16
        raw = world[base : base + 16]
        rows.append(
            {
                "texture": tex,
                "rate": struct.unpack_from(">h", raw, 0)[0] if len(raw) == 16 else None,
                "face_s1": struct.unpack_from(">h", raw, 2)[0] if len(raw) == 16 else None,
                "cap_s1": struct.unpack_from(">h", raw, 4)[0] if len(raw) == 16 else None,
                "raw": " ".join(f"{b:02X}" for b in raw),
            }
        )
    return rows


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def i16(b: bytes, o: int) -> int:
    return struct.unpack_from(">h", b, o)[0]


def first_existing(paths: tuple[Path, ...]) -> Path:
    for p in paths:
        if p.is_file():
            return p
    raise FileNotFoundError(paths[0])


def rgb8_from_u16(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return (rgb[0] >> 8, rgb[1] >> 8, rgb[2] >> 8)


def color_specs(buf: bytes, variation: int) -> list[tuple[int, tuple[int, int, int]]]:
    """ColorSpec run for one table. index + 3×u16 RGB, stride 8 from +$18."""
    ntab = u16(buf, 0x14)
    nent = u16(buf, 0x16)
    if variation < 0 or variation >= ntab:
        return []
    off = 24 + variation * nent * 8
    out: list[tuple[int, tuple[int, int, int]]] = []
    for _ in range(nent):
        if off + 8 > len(buf):
            break
        idx = u16(buf, off)
        rgb = (u16(buf, off + 2), u16(buf, off + 4), u16(buf, off + 6))
        out.append((idx, rgb))
        off += 8
    return out


def lookup_rgb(unique: list[tuple[int, int, int]], rgb: tuple[int, int, int]) -> int:
    """CODE 5 @2916. Returns match index, or len(unique) if none."""
    for i, u in enumerate(unique):
        if u[0] == rgb[0] and u[1] == rgb[1] and u[2] == rgb[2]:
            return i
    return len(unique)


def keep_in_run(start: tuple[int, int, int], cand: tuple[int, int, int]) -> bool:
    """CODE 5 @2862: keep (d0=0) iff start >= cand on all three u16 channels."""
    return start[0] >= cand[0] and start[1] >= cand[1] and start[2] >= cand[2]


def collect_unique(
    decoded: dict[int, dict], loaded: dict[int, int]
) -> list[tuple[int, int, int]]:
    """CODE 5 @2986. Slot order 0..$7F. First-seen 6-byte RGB wins."""
    unique: list[tuple[int, int, int]] = []
    for slot in range(0x80):
        if slot not in loaded:
            continue
        rid = slot + 128
        d = decoded.get(rid)
        if not d or not d.get("buf"):
            continue
        var = loaded[slot]
        for _idx, rgb in color_specs(d["buf"], var):
            if lookup_rgb(unique, rgb) == len(unique):
                unique.append(rgb)
    return unique


def plant_clut(
    unique: list[tuple[int, int, int]], clut_rgbs: list[tuple[int, int, int]]
) -> list[tuple[int, int, int]]:
    """@3214 writes 15 clut RGBs at unique+$27C = index 106. Does not bump d6."""
    buf = list(unique) + [(0, 0, 0)] * max(0, CLUT_PLANT + N_CLUT_PLANT - len(unique))
    for i, rgb in enumerate(clut_rgbs[:N_CLUT_PLANT]):
        dest = CLUT_PLANT + i
        if dest < len(buf):
            buf[dest] = rgb
        else:
            buf.append(rgb)
    return buf


def group_runs(unique: list[tuple[int, int, int]], count: int) -> list[tuple[int, int]]:
    """CODE 5 @3884. Returns (start, N) runs covering 0..count-1.

    @2862 is called with -$6(a6) = the previous entry (copied at @4000),
    not unique[start]. Pairwise: keep iff previous >= candidate on all
    three u16 channels. Comparing only to the run start is wrong when a
    later pair rises on one channel ( >= on RGB triples is not enough
    to collapse that case into one run).
    """
    runs: list[tuple[int, int]] = []
    start = 0
    n = 0
    while True:
        start = start + n
        n = 0
        if start >= count:
            break
        while start + n < count:
            if n != 0 and not keep_in_run(unique[start + n - 1], unique[start + n]):
                break
            n += 1
        if n == 0:
            break
        runs.append((start, n))
    return runs


def shade_table(unique: list[tuple[int, int, int]], count: int) -> np.ndarray:
    """CODE 5 @4044 / JT 336. out[band][i], 16×256, prefilled $0F."""
    out = np.full((16, 256), SLOT_BLACK, dtype=np.uint8)
    for start, n in group_runs(unique, count):
        for off in range(n):
            idx = start + off
            for band in range(15):
                # divs.l #$e  (14). All non-negative here.
                out[band, idx] = idx + ((n - 1 - off) * band) // 14
            out[15, idx] = SLOT_BLACK
    return out


def remap_table(
    buf: bytes,
    variation: int,
    unique: list[tuple[int, int, int]],
    count: int,
    force_nonzero: bool = True,
) -> np.ndarray:
    """CODE 5 @3670 with $1b==0. Key = table-0 ColorSpec index."""
    lut = np.zeros(256, dtype=np.uint8)
    specs0 = color_specs(buf, 0)
    specs_v = color_specs(buf, variation)
    n = min(len(specs0), len(specs_v))
    for i in range(n):
        idx0, _rgb0 = specs0[i]
        _idxv, rgbv = specs_v[i]
        g = lookup_rgb(unique[:count], rgbv)
        if force_nonzero and g == 0:
            g = 1
        if 0 <= idx0 <= 255:
            lut[idx0] = g & 0xFF
    # remap[byte $12] = 0. Header +$12 high byte of $0200 = 2.
    lut[INDEX_TRANSPARENT] = 0
    return lut


def loaded_slots_for_level(level) -> tuple[dict[int, int], list[str]]:
    """CODE 4 @6094 + JT 180(0). texture_list, then monsters, then slot 0."""
    notes: list[str] = []
    loaded: dict[int, int] = {}
    for raw in level.texture_list:
        if raw < 0:
            continue
        slot = raw & 0x0FFF
        var = (raw >> 12) & 0xF
        loaded[slot] = var
        notes.append(f"tex slot={slot}({slot}=0x{slot:X}) rid={slot+128} var={var} raw={raw}")
    words = jt240_words()
    for mi, mon in enumerate(level.monster_list):
        if mon.type < 0:
            continue
        word = words.get(mon.type)
        if word is None:
            notes.append(f"monster[{mi}] type={mon.type} UNKNOWN no JT240 row")
            continue
        slot = word & 0x0FFF
        var = (word >> 12) & 0xF
        loaded[slot] = var
        notes.append(
            f"monster[{mi}] type={mon.type} JT240+4=${word:04X} "
            f"slot={slot} rid={slot+128} var={var}"
        )
    loaded[0] = 0
    notes.append("JT 180(0) slot=0 rid=128 var=0")
    return loaded, notes


def used_texture_pairs(levels) -> list[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for lv in levels:
        for raw in lv.texture_list:
            if raw < 0:
                continue
            pairs.add(((raw & 0x0FFF) + 128, (raw >> 12) & 0xF))
    return sorted(pairs)


def palette_rgb8(unique: list[tuple[int, int, int]], count: int) -> np.ndarray:
    pal = np.zeros((256, 3), dtype=np.uint8)
    for i in range(min(count, 256)):
        pal[i] = rgb8_from_u16(unique[i])
    if count > SLOT_BLACK:
        pal[SLOT_BLACK] = rgb8_from_u16(unique[SLOT_BLACK])
    return pal


def native_plane(d: dict, s1_index: int) -> np.ndarray | None:
    hdr = d["hdr"]
    s1 = d["s1"]
    s2 = d["s2"]
    if s1_index < 0 or s1_index >= len(s1):
        return None
    rec = s1[s1_index]
    s2i = rec["u16"][2]
    cls = rec["u16"][0]
    if not (0 <= s2i < len(s2)):
        return None
    t = s2[s2i]
    if not tile_in_s3(t, hdr["v4"]):
        return None
    s3 = d["buf"][hdr["v3"] : hdr["v3"] + hdr["v4"]]
    raw = s3[t["off"] : t["off"] + t["wh"]]
    if len(raw) != t["wh"]:
        return None
    mode = "A" if is_sprite_tag(cls) else "baseline"
    plane = decode_plane(raw, t["a"], t["b"], mode)
    return apply_s1_overlay(plane, rec, s2, s3, cls)


def rgb_from_native(plane: np.ndarray, pal: dict[int, tuple[int, int, int]]) -> np.ndarray:
    """extract_256.palette_lut / render_plane, magenta=False."""
    lut = np.zeros((256, 4), dtype=np.uint8)
    lut[:, 0] = 255
    lut[:, 1] = 0
    lut[:, 2] = 255
    lut[:, 3] = 255
    for idx, (r, g, b) in pal.items():
        lut[idx] = (r, g, b, 255)
    lut[INDEX_TRANSPARENT] = (0, 0, 0, 0)
    return lut[plane]


def find_existing_rgb(rid: int, s2_index: int, w: int, h: int) -> Path | None:
    names = [
        RGB_ROOT / str(rid) / f"pal0/tile_{s2_index:02d}_{w}x{h}.png",
        RGB_ROOT / str(rid) / f"tile_{s2_index:02d}_{w}x{h}.png",
    ]
    folder = RGB_ROOT / str(rid)
    if folder.is_dir():
        names.extend(sorted(folder.glob(f"tile_{s2_index:02d}_*.png")))
        pal0 = folder / "pal0"
        if pal0.is_dir():
            names.extend(sorted(pal0.glob(f"tile_{s2_index:02d}_*.png")))
    for p in names:
        if p.is_file():
            return p
    return None


def emit_lut_png(
    path: Path,
    remap: np.ndarray,
    shade: np.ndarray,
    pal: np.ndarray,
    slot15: tuple[int, int, int],
) -> None:
    """256×16 RGBA. texel (i, band) = final RGB of native index i at band."""
    arr = np.zeros((16, 256, 4), dtype=np.uint8)
    for band in range(16):
        for i in range(256):
            g = int(remap[i])
            shaded = int(shade[band, g])
            if band == 15:
                rgb = slot15
            elif shaded < len(pal):
                rgb = tuple(int(x) for x in pal[shaded])
            else:
                rgb = slot15
            alpha = 0 if i == INDEX_TRANSPARENT else 255
            arr[band, i] = (rgb[0], rgb[1], rgb[2], alpha)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path)


def main() -> int:
    lines: list[str] = []

    def log(s: str = "") -> None:
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", "replace").decode("ascii"))
        lines.append(s)

    # ---- GO/NO-GO -------------------------------------------------------
    log("REPORT THIS FIRST -- GO/NO-GO")
    log("Per-sector schema (tools/export_level.py sector_json / current Lxx.json):")
    log("  index, x, y, type, type_name, type_addl, item,")
    log("  walls[6] = {index, slot, type, type_name, texture, blocks_movement}")
    log("  slot names: wall_y, wall_x,")
    log("    corner_high_x_low_y, corner_low_x_low_y,")
    log("    corner_high_x_high_y, corner_low_x_high_y")
    log("  Six words at +0,+2,+4,+6,+8,+$A stored as type=high byte, texture=low byte.")
    sizes = []
    all_six = True
    for i in range(25):
        p = EXPORT / f"L{i:02d}.json"
        if not p.is_file():
            log(f"  MISSING {p}")
            all_six = False
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        n = len(doc["sectors"][0]["walls"])
        sizes.append((p.name, p.stat().st_size, n))
        if n != 6:
            all_six = False
    for name, sz, n in sizes:
        log(f"  {name} bytes={sz} ({sz}=0x{sz:X}) walls0={n}")
    log("")
    if all_six:
        log("Are all six wall words present per sector?  YES")
        log("No level re-export. Field names unchanged.")
    else:
        log("Are all six wall words present per sector?  NO")
        return 1

    maps_path = first_existing(MAPS_CANDIDATES)
    app_path = first_existing(APP_CANDIDATES)
    levels = load_maps(maps_path)
    blobs = load_256()
    decoded = {}
    for rid, src in blobs.items():
        dec = decompress(src)
        buf = dec["out"]
        hdr = parse_header(buf)
        decoded[rid] = {
            "buf": buf,
            "hdr": hdr,
            "tables": parse_tables(buf, hdr) if hdr else [],
            "s1": parse_s1(buf, hdr) if hdr else [],
            "s2": parse_s2(buf, hdr) if hdr else [],
        }
    cluts = resources_of_type(app_path, b"clut")
    clut_rgbs: dict[int, list[tuple[int, int, int]]] = {}
    for cid, blob in sorted(cluts.items()):
        try:
            entries = parse_clut(blob)
        except ValueError:
            continue
        clut_rgbs[cid] = [(r, g, b) for _i, r, g, b in entries]

    log("")
    log("ARITH")
    log(f"  $0F={SLOT_BLACK} recheck={0x0F}")
    log(f"  $6A={CLUT_PLANT} recheck={0x6A}")
    log(f"  $79={FADE_LAST} recheck={0x79}")
    log(f"  $27C={0x27C}  {0x27C}/6={0x27C // 6} -> index {CLUT_PLANT}")
    log(f"  $80={0x80} slots  rid=slot+128")
    log(f"  $1A={0x1A} ColorSpec RGB (table+$18+2)")
    log(f"  $E={14} shade divisor")
    log(f"  $1000={0x1000} shade table bytes 16*256")
    log(f"  maps={maps_path} levels={len(levels)}")
    log(f"  .256 count={len(decoded)}")
    log(f"  clut ids={sorted(clut_rgbs)}")

    # ---- A --------------------------------------------------------------
    log("")
    log("=" * 78)
    log("A. LOAD-TIME PALETTE REMAP")
    log("=" * 78)
    log("1. s3 bytes ARE remapped in place. They do NOT already hold global indices.")
    log("   Site: CODE 5 @3670 builds 256-byte LUT at -$10C(a6);")
    log("   @3868 jsr @4 applies dest[i]=remap[dest[i]] over v3..v3+v4.")
    log("   @4  20 6F 00 04 / 12 10 / 10 F1 10 00  move.b (a1,d1.w),(a0)+")
    log("   On disk: per-resource ColorSpec indices (first typically 3).")
    log("   After JT 184: global unique-list indices. Native 2 -> 0 (@3812 clr.b remap[$12]).")
    log("   Therefore tile index bytes ARE level-dependent after remap.")
    log("   Export C uses NATIVE per-resource indices; remap is folded into LUT D.")
    log("")
    log("2. Global palette construction order (JT 184 @1138 -> @2986):")
    log("   a. Unload slots: flags bit1 set and bit0 clear. Handle released.")
    log("   b. Load slots: flags bit0 set and handle null. @4892 GetResource('.256', slot+$80)")
    log("      then JT 279 decompress. flags cleared after load.")
    log("   c. @2986 collect: slot d4=0..$7F, live handle only.")
    log("      nent=$16; d0=variation*nent+entry; lea $1a(a0,d0.l*8) RGB.")
    log("      Compare 3xu16 against -$600(a6) stride 6. First-seen wins. d6=count.")
    log("   d. @3586/@3670 remap every live handle (variation at slot+$6).")
    log("   e. @3200 move.b #1, -$17A4. @4986 GetResource('clut', -$17A6+$81)")
    log("      if -$17A4 set, else clut 128. @3200 always sets the flag.")
    log("   f. @3214 copy 15 clut RGBs to unique+$27C (index 106=$6A). d6 NOT incremented.")
    log("   g. @3262 SetEntryColor unique[0..d6-1]; usage slot0=2 else $C.")
    log("      then 26 colors from -$6F8 at d6..d6+$19; then d6+$1A..$FF from -$656.")
    log("   h. ActivatePalette. @3448 -> @4044 shade fill.")
    log("")
    log("   Who sets flags (CODE 4 @1526 JT 154, after map load):")
    log("   @6094 walks map+$8E texture_list[8], word != $FFFF -> JT 180(word).")
    log("   then monster_list[3] at +$1B6, type != $FFFF -> JT 240(type) -> JT 180.")
    log("   JT 240 CODE 7 @4: word = (A5-$104A + type*$5C)+$4 from DATAINIT.")
    log("   then JT 180(0): slot 0 resource 128 variation 0.")
    log("   then if A5-$1A8A+$198 != $FF and -$1BCA: JT 255 -> JT 180 (player item, not level-static).")
    log("   JT 180 @794: slot=word&$FFF, flags|=1, var=(word>>12)&$F. Scale *8 on slot.")
    log("")
    log("3. Global palette is rebuilt whenever JT 184 runs: startup CODE 2 @2298")
    log("   and level load CODE 4 @1558. Loaded .256 set differs per level.")
    log("   NOT built once for all levels.")
    log("")
    log("4. Slot $0F: shade band 15 stores literal $0F (11 BC 00 0F @4168).")
    log("   JT 336 prefills the 16x256 table with $0F. Device slot $0F = unique[15]")
    log("   via SetEntryColor. No writer forces unique[15]=black in @2986.")
    log("   $6A..$78: @3214 plants 15 clut RGBs at unique[106..120].")
    log("   $6A..$79: JT 178 forces those 16 indices to $0F in a 2D/floor snapshot.")
    log("   $79 is in the fade range but is NOT planted by @3214 (15 entries).")
    log("   Tile index bytes (native) are NOT level-dependent.")
    log("   Remapped (runtime) indices ARE level-dependent.")

    gf = levels[0]
    loaded0, load_notes = loaded_slots_for_level(gf)
    unique0 = collect_unique(decoded, loaded0)
    d6_0 = len(unique0)
    # default clut: @6374 clr.w d1 → -$17A6=0 → clut 129
    clut_id_default = 129
    clut_used = clut_rgbs.get(clut_id_default) or clut_rgbs.get(128) or []
    unique0_planted = plant_clut(unique0, clut_used)
    shade0 = shade_table(unique0_planted, d6_0)
    runs0 = group_runs(unique0_planted, d6_0)

    log("")
    log(f"Ground Floor loaded slots (n={len(loaded0)}):")
    for n in load_notes:
        log(f"  {n}")
    log(f"  unique d6={d6_0} ({d6_0}=0x{d6_0:X})  plant clobbers 106+? {d6_0 > CLUT_PLANT}")
    log(f"  clut used id={clut_id_default if clut_id_default in clut_rgbs else 'FALLBACK'} n={len(clut_used)}")
    if d6_0 > SLOT_BLACK:
        u15 = unique0[SLOT_BLACK]
        log(
            f"  unique[15=$0F] u16=({u15[0]},{u15[1]},{u15[2]}) "
            f"rgb8={rgb8_from_u16(u15)}"
        )
    if d6_0 > CLUT_PLANT and clut_used:
        before = unique0[CLUT_PLANT]
        after = unique0_planted[CLUT_PLANT]
        log(f"  unique[106=$6A] before plant u16={before} after={after}")

    # ---- B --------------------------------------------------------------
    log("")
    log("=" * 78)
    log("B. RUN GROUPING  @3884 / @2862 / @4044")
    log("=" * 78)
    log(f"Ground Floor runs n={len(runs0)}")
    log("  start N  first_rgb8              last_rgb8")
    for start, n in runs0:
        first = rgb8_from_u16(unique0_planted[start])
        last = rgb8_from_u16(unique0_planted[start + n - 1])
        log(
            f"  {start:5d} {n:3d}  {first}  {last}  "
            f"u16_first={unique0_planted[start]} u16_last={unique0_planted[start+n-1]}"
        )
    no_run = 256 - d6_0
    log(f"2. entries in no run: {no_run} (indices {d6_0}..255)")
    log("   JT 336 prefills all 4096 bytes with $0F, so out[band][i]=$0F for those.")
    log("3. band-14 verification (must equal run last entry):")
    sample_ok = 0
    sample_n = 0
    for start, n in runs0:
        for off in (0, n // 2, n - 1):
            idx = start + off
            got = int(shade0[14, idx])
            expect = start + n - 1
            ok = got == expect
            sample_ok += int(ok)
            sample_n += 1
            if off == 0 or off == n - 1 or not ok:
                log(
                    f"  run start={start} N={n} i={idx} out[14][{idx}]={got} "
                    f"expect={expect} {'OK' if ok else 'FAIL'}"
                )
        b15 = int(shade0[15, start])
        log(f"  run start={start} out[15][{start}]={b15} expect={SLOT_BLACK}")
    log(f"  sample band14 ok={sample_ok}/{sample_n}")
    log(f"  out[0][first]={int(shade0[0, runs0[0][0]])} (band 0 = identity)")
    # extra: a few global indices through all bands
    probe = [0, 1, 3, 15, 16, d6_0 - 1 if d6_0 else 0, 200]
    log("  probe out[band][i]:")
    for i in probe:
        row = " ".join(f"{int(shade0[b, i]):3d}" for b in range(16))
        log(f"    i={i:3d} {row}")

    # ---- per-level remaps -----------------------------------------------
    level_state: list[dict] = []
    for lv in levels:
        loaded, notes = loaded_slots_for_level(lv)
        unique = collect_unique(decoded, loaded)
        d6 = len(unique)
        planted = plant_clut(unique, clut_used)
        shade = shade_table(planted, d6)
        remaps: dict[tuple[int, int], list[int]] = {}
        for slot, var in loaded.items():
            rid = slot + 128
            if rid in decoded and decoded[rid]["buf"]:
                remaps[(rid, var)] = remap_table(
                    decoded[rid]["buf"], var, planted, d6
                ).tolist()
        level_state.append(
            {
                "lv": lv.level_number,
                "name": lv.name,
                "loaded": loaded,
                "d6": d6,
                "unique": planted,
                "shade": shade,
                "remaps": remaps,
                "notes": notes,
            }
        )

    collisions = []
    pair_remaps: dict[tuple[int, int], list[tuple[int, list[int]]]] = defaultdict(list)
    for st in level_state:
        for pair, rm in st["remaps"].items():
            pair_remaps[pair].append((st["lv"], rm))
    for pair, items in sorted(pair_remaps.items()):
        uniq = {tuple(rm) for _lv, rm in items}
        if len(uniq) > 1:
            collisions.append((pair, items))

    log("")
    log(f"remap collisions across levels for texture_list (rid,var): {len(collisions)}")
    if collisions:
        log("  Remaps ARE level-dependent. LUT filenames will be per-level.")
        for pair, items in collisions[:8]:
            log(f"  {pair} distinct={len({tuple(rm) for _lv, rm in items})} levels={[lv for lv, _ in items]}")
    else:
        log("  No collisions among texture_list pairs with this loaded-set model.")

    # ---- C R8 -----------------------------------------------------------
    log("")
    log("=" * 78)
    log("C. EXPORT R8 INDEX TILES  (native per-resource ColorSpec indices)")
    log("=" * 78)
    if R8_DIR.exists():
        for old in R8_DIR.rglob("*.png"):
            old.unlink()
    r8_count = 0
    r8_bytes = 0
    r8_rel: dict[tuple[int, int], str] = {}
    for rid in sorted(decoded):
        d = decoded[rid]
        if not d["hdr"]:
            continue
        dest_dir = R8_DIR / str(rid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for rec in d["s1"]:
            s1i = rec["i"]
            plane = native_plane(d, s1i)
            if plane is None:
                continue
            path = dest_dir / f"s1_{s1i:02d}.png"
            Image.fromarray(plane, "L").save(path)
            r8_count += 1
            r8_bytes += path.stat().st_size
            r8_rel[(rid, s1i)] = f"256-r8/{rid}/s1_{s1i:02d}.png"

    log(f"  files={r8_count} total_bytes={r8_bytes} ({r8_bytes}=0x{r8_bytes:X})")

    # verification: 192 s1 0 through table 0 vs RGB
    verify_rid, verify_s1 = 192, 0
    d192 = decoded.get(verify_rid)
    mismatch = -1
    verify_note = "SKIP no resource 192"
    if d192 and d192["s1"]:
        plane = native_plane(d192, verify_s1)
        tables = d192["tables"]
        pal0 = tables[0]["pal"] if tables else {}
        if plane is not None:
            got = rgb_from_native(plane, pal0)
            rec = d192["s1"][verify_s1]
            s2i = rec["u16"][2]
            h, w = plane.shape
            existing = find_existing_rgb(verify_rid, s2i, w, h)
            VERIFY_DIR.mkdir(parents=True, exist_ok=True)
            ref_path = VERIFY_DIR / f"r{verify_rid}_s1_{verify_s1:02d}.png"
            Image.fromarray(got, "RGBA").save(ref_path)
            if existing is not None:
                ref = np.array(Image.open(existing).convert("RGBA"))
                src = "existing " + str(existing.relative_to(ROOT))
            else:
                ref = got
                src = "IN-MEMORY extract_256 table0 (no PNG under reference/docs/256/)"
            if ref.shape != got.shape:
                mismatch = -2
                verify_note = f"shape {got.shape} vs {ref.shape} src={src}"
            else:
                mismatch = int(np.sum(np.any(ref != got, axis=-1)))
                verify_note = f"src={src} shape={got.shape[1]}x{got.shape[0]}"
    log(f"  verify rid={verify_rid} s1={verify_s1} {verify_note}")
    log(f"  mismatch_pixels={mismatch}")

    # ---- D LUTs ---------------------------------------------------------
    log("")
    log("=" * 78)
    log("D. SHADE LUTS")
    log("=" * 78)
    if LUT_DIR.exists():
        for old in LUT_DIR.glob("*.png"):
            old.unlink()
    lut_files: list[str] = []
    pair_to_luts: dict[int, list[str]] = defaultdict(list)

    if collisions:
        for st in level_state:
            pal = palette_rgb8(st["unique"], st["d6"])
            slot15 = tuple(int(x) for x in pal[SLOT_BLACK])
            for (rid, var), rm in st["remaps"].items():
                name = f"lut_L{st['lv']:02d}_r{rid}_v{var}.png"
                emit_lut_png(
                    LUT_DIR / name,
                    np.array(rm, dtype=np.uint8),
                    st["shade"],
                    pal,
                    slot15,
                )
                lut_files.append(name)
                pair_to_luts[rid].append(name)
    else:
        # one LUT per (rid,var); use first level that contains the pair
        emitted: set[tuple[int, int]] = set()
        for st in level_state:
            pal = palette_rgb8(st["unique"], st["d6"])
            slot15 = tuple(int(x) for x in pal[SLOT_BLACK])
            for (rid, var), rm in st["remaps"].items():
                if (rid, var) in emitted:
                    continue
                name = f"lut_r{rid}_v{var}.png"
                emit_lut_png(
                    LUT_DIR / name,
                    np.array(rm, dtype=np.uint8),
                    st["shade"],
                    pal,
                    slot15,
                )
                lut_files.append(name)
                pair_to_luts[rid].append(name)
                emitted.add((rid, var))

    log(f"  lut_count={len(lut_files)} per_level={bool(collisions)}")
    # Ground Floor wall resource = texture_list[0]
    wall0 = gf.texture_list[0]
    wall_rid = (wall0 & 0x0FFF) + 128
    wall_var = (wall0 >> 12) & 0xF
    gf_lut_name = (
        f"lut_L00_r{wall_rid}_v{wall_var}.png"
        if collisions
        else f"lut_r{wall_rid}_v{wall_var}.png"
    )
    gf_lut_path = LUT_DIR / gf_lut_name
    log(f"  Ground Floor wall rid={wall_rid} var={wall_var} file={gf_lut_name}")
    if gf_lut_path.is_file():
        lut_im = np.array(Image.open(gf_lut_path).convert("RGBA"))
        for band, label in ((0, "row0"), (15, "row15")):
            triples = []
            for i in range(16):
                r, g, b, a = (int(x) for x in lut_im[band, i])
                triples.append(f"({r},{g},{b},a={a})")
            log(f"  {label} first16: {' '.join(triples)}")

    # ---- E manifest -----------------------------------------------------
    log("")
    log("=" * 78)
    log("E. MANIFEST")
    log("=" * 78)
    resources_out = []
    for rid in sorted(decoded):
        d = decoded[rid]
        hdr = d["hdr"]
        if not hdr:
            continue
        s1 = d["s1"]
        s2 = d["s2"]
        class1_h = []
        tiles = []
        variations = sorted({v for (r, v) in pair_remaps if r == rid})
        lut_pattern = (
            "lut_L{level:02d}_r{resource}_v{variation}.png"
            if collisions
            else "lut_r{resource}_v{variation}.png"
        )
        for rec in s1:
            s1i = rec["i"]
            cls = rec["u16"][0]
            flags = rec["u16"][1]
            s2i = rec["u16"][2]
            if 0 <= s2i < len(s2):
                w, h = s2_wh_for_class(s2[s2i], cls)
            else:
                w, h = 0, 0
            if cls == 1 and h:
                class1_h.append(h)
            ov_s2 = rec["u16"][3]
            tile = {
                "s1_index": s1i,
                "cls": cls,
                "flags": flags,
                "s2_index": s2i,
                "width": w,
                "height": h,
                "world_w": rec["i16"][4],
                "world_h": rec["i16"][5],
                "lift": rec["i16"][6],
                "png": r8_rel.get((rid, s1i)),
            }
            if ov_s2:
                tile["overlay_s2"] = ov_s2
                tile["overlay_dest_off"] = s1_overlay_dest_off(rec)
                tile["overlay_x"] = rec["u16"][9]
                tile["overlay_y"] = rec["u16"][10]
            tiles.append(tile)
        full_height = class1_h[0] if class1_h else (tiles[0]["height"] if tiles else 0)
        resources_out.append(
            {
                "resource": rid,
                "tile_count": hdr["tile_count"],
                "full_height": full_height,
                "table_count": len(d["tables"]),
                "tiles": tiles,
                "lut": {
                    "pattern": lut_pattern,
                    "variations": variations,
                    "files": sorted(set(pair_to_luts.get(rid, []))),
                },
            }
        )

    levels_out = {}
    for lv in levels:
        slot0 = lv.texture_list[0]
        levels_out[str(lv.level_number)] = {
            "name": lv.name,
            "wall_resource": (slot0 & 0x0FFF) + 128 if slot0 >= 0 else None,
            "wall_variation": (slot0 >> 12) & 0xF if slot0 >= 0 else None,
            "texture_list": [
                {
                    "raw": raw,
                    "shape_id": (raw & 0x0FFF) + 128 if raw >= 0 else None,
                    "variation": (raw >> 12) & 0xF if raw >= 0 else None,
                }
                for raw in lv.texture_list
            ],
        }

    door_textures = sorted(
        {d.texture for lv in levels for d in lv.door_list if 0 <= d.texture <= 6}
    )
    door_rates = door_rate_table(door_textures)
    log("")
    log("door_rates A5-$8E0 stride 16")
    for row in door_rates:
        log(
            f"  tex={row['texture']} rate={row['rate']} face_s1={row['face_s1']} "
            f"cap_s1={row['cap_s1']} raw={row['raw']}"
        )

    manifest = {
        "resources": resources_out,
        "levels": levels_out,
        "door_rates": door_rates,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    example = None
    for res in resources_out:
        if res["resource"] == wall_rid and res["tiles"]:
            example = {"resource": {k: res[k] for k in res if k != "tiles"}, "tile0": res["tiles"][0]}
            break
    log("schema:")
    log("  resources[]: resource, tile_count, full_height, table_count, tiles[], lut")
    log("  tiles[]: s1_index, cls, flags, s2_index, width, height,")
    log("           world_w=i16[4], world_h=i16[5], lift=i16[6], png=ONE r8 path")
    log("  lut: {pattern, variations[], files[]}")
    log(f"  wrote {MANIFEST_PATH} bytes={MANIFEST_PATH.stat().st_size}")
    log("example:")
    log(json.dumps(example, indent=2))
    log("")
    log("The world_w/world_h swap has been removed. world_w is s1 i16[4],")
    log("world_h is s1 i16[5]. The consumer must stop compensating for the swap.")

    # ---- F --------------------------------------------------------------
    log("")
    log("=" * 78)
    log("F. UNITY RE-IMPORT")
    log("=" * 78)
    log(f"  NEW  out/256-r8/**/s1_*.png          count={r8_count}  bytes={r8_bytes}")
    log(f"  NEW  out/256-lut/lut_*.png            count={len(lut_files)}")
    log(f"  REPLACE  out/256-manifest.json        (was palette-map png dict)")
    log("  SUPERSEDE  reference/docs/256/<rid>/pal<N>/tile_*.png")
    log("             (RGB-per-palette tiles). Do not import those as the mesh atlas.")
    log("  SUPERSEDE  reference/docs/256/<rid>/tile_*.png  (legacy RGB)")
    log("  SUPERSEDE  reference/docs/256/manifest.json     (old path + swapped w/h)")
    log("  KEEP  reference/export/L00.json .. L24.json     (already have 6 walls)")
    log("  DELETE rather than overwrite:")
    log("    any Unity import of pal0/pal1/pal2 RGB tiles for the same s1")
    log("    (R8 path is per s1, not per palette; old palN copies are wrong assets)")
    if collisions:
        log("  LUT names are per-level (remap collision). Delete any prior")
        log("    lut_r*_v*.png that assumed a single global remap.")
    log(f"  verify mismatch_pixels={mismatch} (must be 0)")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {REPORT_PATH}")
    if mismatch != 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
