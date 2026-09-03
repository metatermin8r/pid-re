"""Test two .256 structural claims. Read-only on Shapes.rsrc. Writes PNGs."""
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
FLOORS = list(range(195, 203))
PAL_LO, PAL_HI = 3, 17
MAGENTA = (255, 0, 255)

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


def parse_header(blob: bytes):
    size = u32(blob, 0)
    tag, z, tiles = blob[4], blob[5], blob[6]
    v1, v2, v3, v4 = struct.unpack_from(">4I", blob, 7)
    return size, tag, z, tiles, v1, v2, v3, v4


def table_stride(rid: int, tag: int) -> int:
    if rid in STRIDE_FOR_ID:
        return STRIDE_FOR_ID[rid]
    return STRIDE_FOR_TAG.get(tag, 5)


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


def rawend(blob: bytes, rid: int, tag: int) -> int:
    stride = table_stride(rid, tag)
    first, n, end = ascending_run(blob, 29, stride)
    return end if n >= 1 else 29


def pearson_adj(img: np.ndarray, axis: int) -> float:
    if axis == 1:
        a = img[:, :-1].reshape(-1).astype(np.float64)
        b = img[:, 1:].reshape(-1).astype(np.float64)
    else:
        a = img[:-1, :].reshape(-1).astype(np.float64)
        b = img[1:, :].reshape(-1).astype(np.float64)
    if a.size == 0:
        return float("nan")
    sa, sb = a.std(), b.std()
    if sa == 0.0 or sb == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def raster_from(pay: bytes, w: int, h: int) -> np.ndarray:
    need = w * h
    buf = pay[:need] + bytes(max(0, need - len(pay)))
    return np.frombuffer(buf[:need], dtype=np.uint8).reshape(h, w)


def hexdump(b: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(b), width):
        chunk = b[i : i + width]
        hx = " ".join(f"{x:02x}" for x in chunk)
        lines.append(f"    +{i:04x}  {hx}")
    return "\n".join(lines)


def stride5_table(blob: bytes) -> dict[int, tuple[int, int, int]]:
    pal = {}
    first, n, end = ascending_run(blob, 29, 5)
    for i in range(n):
        off = 29 + i * 5
        idx = u16(blob, off)
        kind, inten, flag = blob[off + 2], blob[off + 3], blob[off + 4]
        # intensity is the only varying channel; kind=0x03 flag=0x81
        pal[idx] = (inten, inten, inten)
        pal[idx] = pal[idx]  # keep
        _ = (kind, flag)
    return pal


def stride8_table(blob: bytes) -> dict[int, tuple[int, int, int]]:
    pal = {}
    first, n, end = ascending_run(blob, 115, 8)
    for i in range(n):
        off = 115 + i * 8
        idx = u16(blob, off)
        r, g, b = struct.unpack_from(">HHH", blob, off + 2)
        pal[idx] = (r >> 8, g >> 8, b >> 8)
    return pal


def write_tiled(path: Path, pay: bytes, pal0, pal1):
    need = 32768
    buf = pay[:need] + bytes(max(0, need - len(pay)))
    buf = buf[:need]
    rgb = np.zeros((256, 128, 3), dtype=np.uint8)
    for y in range(256):
        pal = pal0 if y < 128 else pal1
        for x in range(128):
            v = buf[y * 128 + x]
            rgb[y, x] = pal.get(v, MAGENTA)
    Image.fromarray(rgb, "RGB").save(path)


# ----- B4 decoders -----

def dec_inrange_literal_rest_skip(pay: bytes) -> int:
    return sum(1 for b in pay if PAL_LO <= b <= PAL_HI)


def dec_opcode_len_then_pixel(pay: bytes) -> tuple[int, int]:
    """Out-of-range: [op][len][pix] emit pix `len` times. In-range: emit 1."""
    i, n, emitted = 0, len(pay), 0
    while i < n:
        b = pay[i]
        if PAL_LO <= b <= PAL_HI:
            emitted += 1
            i += 1
        else:
            if i + 2 >= n:
                return emitted, n - i
            ln = pay[i + 1]
            emitted += ln
            i += 3
    return emitted, 0


def dec_opcode_minus_c_run_following(pay: bytes, c: int) -> tuple[int, int]:
    """Out-of-range: run length = (op - c) of the following byte. In-range: emit 1."""
    i, n, emitted = 0, len(pay), 0
    while i < n:
        b = pay[i]
        if PAL_LO <= b <= PAL_HI:
            emitted += 1
            i += 1
        else:
            if i + 1 >= n:
                return emitted, n - i
            ln = (b - c) & 0xFF
            emitted += ln
            i += 2
    return emitted, 0


def dec_opcode_is_literal_count(pay: bytes, c: int = 0) -> tuple[int, int]:
    """Out-of-range: copy next (op - c) bytes verbatim as pixels."""
    i, n, emitted = 0, len(pay), 0
    while i < n:
        b = pay[i]
        if PAL_LO <= b <= PAL_HI:
            emitted += 1
            i += 1
        else:
            ln = (b - c) & 0xFF
            i += 1
            take = min(ln, n - i)
            emitted += take
            i += take
            if take < ln:
                return emitted, n - i
    return emitted, 0


def dec_opcode_run_of_prev(pay: bytes, c: int) -> tuple[int, int]:
    """Out-of-range: repeat previous pixel (op - c) times. No prev => skip."""
    i, n, emitted = 0, len(pay), 0
    prev = None
    while i < n:
        b = pay[i]
        if PAL_LO <= b <= PAL_HI:
            emitted += 1
            prev = b
            i += 1
        else:
            ln = (b - c) & 0xFF
            if prev is None:
                i += 1
                continue
            emitted += ln
            i += 1
    return emitted, 0


def dec_opcode_run_of_following_raw(pay: bytes, c: int) -> tuple[int, int]:
    """Same as minus-c but run length is the opcode byte itself if c is None sentinel.
    Unused — kept for the c=0 case already covered.
    """
    return dec_opcode_minus_c_run_following(pay, c)


def first_row_is_colorspec(pay: bytes) -> tuple[bool, list[int]]:
    """Would the first 128 bytes parse as the packed-115 ColorSpec run?"""
    if len(pay) < 112:
        return False, []
    idxs = []
    ok = True
    for i in range(14):
        off = i * 8
        if off + 8 > len(pay):
            ok = False
            break
        idx = u16(pay, off)
        idxs.append(idx)
        if idx != 4 + i:
            ok = False
    return ok, idxs


def main() -> None:
    payload = load_resource_payload(SHAPES)
    blobs = {rid: b for t, rid, b in iter_resources(payload.data) if t == b".256"}
    ids = sorted(blobs)
    print(f"loaded {len(blobs)} .256")

    rows = []
    for rid in ids:
        blob = blobs[rid]
        size, tag, z, tiles, v1, v2, v3, v4 = parse_header(blob)
        packed = len(blob)
        start_v3 = 23 + v3
        stream = packed - start_v3
        re = rawend(blob, rid, tag)
        stream_re = packed - re
        rows.append(
            {
                "id": rid,
                "blob": blob,
                "size": size,
                "tag": tag,
                "tiles": tiles,
                "v1": v1,
                "v2": v2,
                "v3": v3,
                "v4": v4,
                "packed": packed,
                "start_v3": start_v3,
                "stream": stream,
                "rawend": re,
                "stream_re": stream_re,
            }
        )

    # ========== A ==========
    print("\n========== A1 all 50 ==========")
    print("id tiles v1 v2 v3 v4 packed 23+v3 packed-(23+v3) RAWEND packed-RAWEND")
    for r in rows:
        print(
            f"{r['id']:3d} {r['tiles']:2d} {r['v1']:7d} {r['v2']:7d} {r['v3']:7d} {r['v4']:7d} "
            f"{r['packed']:6d} {r['start_v3']:7d} {r['stream']:8d} "
            f"{r['rawend']:4d} {r['stream_re']:8d}"
        )

    ok_hyp = [r for r in rows if r["stream"] > 0]
    bad_hyp = [r for r in rows if r["stream"] <= 0]
    print(f"\nA2 packed > 23+v3 : {len(ok_hyp)}/{len(rows)}")
    print(f"A2 violations n={len(bad_hyp)}")
    for r in bad_hyp:
        print(
            f"  VIOLATION id={r['id']} packed={r['packed']} 23+v3={r['start_v3']} "
            f"stream={r['stream']} v3={r['v3']} size={r['size']} tag=0x{r['tag']:02X}"
        )

    print("\nA3 ratio v4 / stream  (v3-start vs RAWEND-start)")
    print("id  r_v3=v4/(packed-(23+v3))  r_re=v4/(packed-RAWEND)  pay/v4_v3  pay/v4_re")
    ratios_v3 = []
    ratios_re = []
    pays_v3 = []
    pays_re = []
    for r in rows:
        if r["stream"] > 0:
            rv = r["v4"] / r["stream"]
            pv = r["stream"] / r["v4"] if r["v4"] else float("nan")
            ratios_v3.append(rv)
            pays_v3.append(pv)
            rv_s = f"{rv:.6f}"
            pv_s = f"{pv:.6f}"
        else:
            rv_s, pv_s = "UNDEF", "UNDEF"
        if r["stream_re"] > 0 and r["v4"] > 0:
            rr = r["v4"] / r["stream_re"]
            pr = r["stream_re"] / r["v4"]
            ratios_re.append(rr)
            pays_re.append(pr)
            rr_s = f"{rr:.6f}"
            pr_s = f"{pr:.6f}"
        else:
            rr_s, pr_s = "UNDEF", "UNDEF"
        print(f"{r['id']:3d}  {rv_s:>12}  {rr_s:>12}  {pv_s:>10}  {pr_s:>10}")

    def spread(xs: list[float]) -> tuple[float, float, float, float]:
        a = np.array(xs, dtype=np.float64)
        return float(a.min()), float(a.max()), float(a.max() - a.min()), float(a.std())

    print(f"\nA3 defined n_v3={len(ratios_v3)} n_re={len(ratios_re)}")
    if ratios_v3 and ratios_re:
        mn, mx, sp, sd = spread(ratios_v3)
        print(f"  v3-start  v4/stream : min={mn:.6f} max={mx:.6f} spread={sp:.6f} std={sd:.6f}")
        mn, mx, sp, sd = spread(ratios_re)
        print(f"  RAWEND    v4/stream : min={mn:.6f} max={mx:.6f} spread={sp:.6f} std={sd:.6f}")
        mn, mx, sp, sd = spread(pays_v3)
        print(f"  v3-start  stream/v4 : min={mn:.6f} max={mx:.6f} spread={sp:.6f} std={sd:.6f}")
        mn, mx, sp, sd = spread(pays_re)
        print(f"  RAWEND    stream/v4 : min={mn:.6f} max={mx:.6f} spread={sp:.6f} std={sd:.6f}")
        tighter = spread(ratios_v3)[2] < spread(ratios_re)[2]
        print(f"  v3-start spread vs RAWEND spread (v4/stream): {'TIGHTER' if tighter else 'LOOSER'}")
        tighter_p = spread(pays_v3)[2] < spread(pays_re)[2]
        print(f"  v3-start spread vs RAWEND spread (stream/v4): {'TIGHTER' if tighter_p else 'LOOSER'}")

    print("\nA3 195-202 only")
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        print(
            f"  {r['id']} stream_v3={r['stream']} stream_re={r['stream_re']} "
            f"v4={r['v4']} r_v3={r['v4']/r['stream']:.6f} r_re={r['v4']/r['stream_re']:.6f} "
            f"pay/v4_v3={r['stream']/r['v4']:.6f} pay/v4_re={r['stream_re']/r['v4']:.6f}"
        )

    print("\n========== A4 195-202 hex ==========")
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        blob = r["blob"]
        rem = blob[227:303]
        s23 = blob[303:399]
        print(f"\n--- id={r['id']} packed 227..303 n={len(rem)} (section-1 remainder) ---")
        print(hexdump(rem))
        print(f"--- id={r['id']} packed 303..399 n={len(s23)} (sec2 64 + sec3 32) ---")
        print(hexdump(s23))
        # classify
        uniq_rem = len(set(rem))
        uniq_s23 = len(set(s23))
        print(
            f"  rem distinct={uniq_rem} min={min(rem) if rem else None} max={max(rem) if rem else None}"
        )
        print(
            f"  s23 distinct={uniq_s23} min={min(s23) if s23 else None} max={max(s23) if s23 else None}"
        )

    print("\n========== A5 section-2 per-tile 32B ==========")
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        rec0 = r["blob"][303:335]
        rec1 = r["blob"][335:367]
        print(f"\n--- id={r['id']} ---")
        for name, rec in (("tile0", rec0), ("tile1", rec1)):
            u16s = [u16(rec, i) for i in range(0, 32, 2)]
            pairs = [(rec[i], rec[i + 1]) for i in range(0, 32, 2)]
            print(f"  {name} hex={rec.hex()}")
            print(f"  {name} u16be={u16s}")
            print(f"  {name} u8pairs={pairs}")
        same = rec0 == rec1
        ham = sum(a != b for a, b in zip(rec0, rec1))
        print(f"  records_equal={same} hamming={ham}/32")

    # compare remainder / s23 across the eight
    print("\nA4/A5 cross-id identity")
    rems = {r["id"]: r["blob"][227:303] for r in rows if r["id"] in FLOORS}
    s23s = {r["id"]: r["blob"][303:399] for r in rows if r["id"] in FLOORS}
    rec0s = {r["id"]: r["blob"][303:335] for r in rows if r["id"] in FLOORS}
    rec1s = {r["id"]: r["blob"][335:367] for r in rows if r["id"] in FLOORS}
    sec3s = {r["id"]: r["blob"][367:399] for r in rows if r["id"] in FLOORS}
    print(f"  rem 227..303 all_equal={len(set(rems.values())) == 1} n_unique={len(set(rems.values()))}")
    print(f"  s23 303..399 all_equal={len(set(s23s.values())) == 1} n_unique={len(set(s23s.values()))}")
    print(f"  rec0 303..335 all_equal={len(set(rec0s.values())) == 1} n_unique={len(set(rec0s.values()))}")
    print(f"  rec1 335..367 all_equal={len(set(rec1s.values())) == 1} n_unique={len(set(rec1s.values()))}")
    print(f"  sec3 367..399 all_equal={len(set(sec3s.values())) == 1} n_unique={len(set(sec3s.values()))}")
    # pairwise rem equality
    ids_f = FLOORS
    for i, a in enumerate(ids_f):
        for b in ids_f[i + 1 :]:
            if rems[a] == rems[b]:
                print(f"  rem {a}=={b}")
            if s23s[a] == s23s[b]:
                print(f"  s23 {a}=={b}")

    # ========== B ==========
    print("\n========== B1 195-202 payload @23+v3 ==========")
    family_oor = Counter()
    family_n = 0
    family_oor_n = 0
    family_oor_values = set()
    pays = {}
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        pay = r["blob"][r["start_v3"] :]
        pays[r["id"]] = pay
        n = len(pay)
        in_pal = sum(1 for b in pay if PAL_LO <= b <= PAL_HI)
        oor = Counter(b for b in pay if not (PAL_LO <= b <= PAL_HI))
        oor_n = n - in_pal
        family_oor.update(oor)
        family_n += n
        family_oor_n += oor_n
        family_oor_values.update(oor)
        print(
            f"\n--- id={r['id']} n={n} in_3_17={in_pal} {100.0*in_pal/n:.4f}% "
            f"oor_n={oor_n} {100.0*oor_n/n:.4f}% distinct_oor={len(oor)} ---"
        )
        print(f"  full OOR histogram sorted by freq (value:count):")
        items = oor.most_common()
        print("   ", " ".join(f"{v}:{c}" for v, c in items))
        print("  top20:")
        for v, c in items[:20]:
            print(f"    val={v:3d} 0x{v:02x} count={c} frac={c/n:.6f}")

    print("\n========== B GO family ==========")
    print(
        f"FAMILY 195-202 distinct_oor={len(family_oor_values)} "
        f"oor_bytes={family_oor_n}/{family_n} = {100.0*family_oor_n/family_n:.4f}%"
    )
    print(f"  family distinct OOR values sorted: {sorted(family_oor_values)}")
    print(f"  family OOR value count={len(family_oor)} (should match distinct)")
    print("  family OOR histogram:")
    for v, c in family_oor.most_common():
        print(f"    val={v:3d} 0x{v:02x} count={c}")

    # B2
    print("\n========== B2 concentration ==========")
    n_possible = 256 - (PAL_HI - PAL_LO + 1)
    print(f"  palette range 3..17 inclusive = {PAL_HI - PAL_LO + 1} values")
    print(f"  out-of-range possible = {n_possible}")
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        pay = pays[r["id"]]
        oor_set = {b for b in pay if not (PAL_LO <= b <= PAL_HI)}
        print(
            f"  {r['id']} distinct_oor={len(oor_set)} / {n_possible} possible "
            f"span={min(oor_set) if oor_set else None}..{max(oor_set) if oor_set else None} "
            f"has_0={0 in oor_set} has_1={1 in oor_set} has_2={2 in oor_set} "
            f"has_18={18 in oor_set} n_ge_128={sum(1 for v in oor_set if v >= 128)} "
            f"n_lt_3={sum(1 for v in oor_set if v < 3)} "
            f"n_18_to_127={sum(1 for v in oor_set if 18 <= v <= 127)}"
        )
    print(
        f"  FAMILY distinct_oor={len(family_oor_values)} / {n_possible} "
        f"span={min(family_oor_values)}..{max(family_oor_values)}"
    )
    concentrated = len(family_oor_values) <= 8
    print(
        f"  B2 verdict: {'CONCENTRATED handful' if concentrated else 'SPREAD — kills in-palette-means-literal as a small escape set'}"
    )

    # B3
    print("\n========== B3 context of most frequent OOR ==========")
    # per-id and family
    fam_top, fam_top_n = family_oor.most_common(1)[0]
    print(f"  family most frequent OOR val={fam_top} 0x{fam_top:02x} n={fam_top_n}")
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        pay = pays[r["id"]]
        oor = Counter(b for b in pay if not (PAL_LO <= b <= PAL_HI))
        if not oor:
            print(f"  {r['id']} no OOR")
            continue
        top, topn = oor.most_common(1)[0]
        print(f"\n--- id={r['id']} top_oor={top} 0x{top:02x} n={topn} ---")
        hits = [i for i, b in enumerate(pay) if b == top]
        # 20 separate occurrences, spaced
        if len(hits) <= 20:
            pick = hits
        else:
            step = max(1, len(hits) // 20)
            pick = [hits[i * step] for i in range(20)]
        for k, pos in enumerate(pick[:20]):
            lo = max(0, pos - 8)
            hi = min(len(pay), pos + 9)
            ctx = pay[lo:hi]
            mark = pos - lo
            hx = " ".join(f"{x:02x}" for x in ctx)
            after = pay[pos + 1 : pos + 9]
            before = pay[max(0, pos - 8) : pos]
            print(
                f"    #{k:02d} @{pos} mark={mark} "
                f"before={[x for x in before]} after={[x for x in after]} "
                f"hex={hx}"
            )

    # B4
    print("\n========== B4 decoder variants emitted vs v4 ==========")
    constants = list(range(0, 33)) + [0x80, 0x81, 0x7F, 18, 19]
    constants = sorted(set(constants))
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        pay = pays[r["id"]]
        v4 = r["v4"]
        print(f"\n--- id={r['id']} n_in={len(pay)} v4={v4} ---")
        lit_only = dec_inrange_literal_rest_skip(pay)
        print(f"  literals_only (skip OOR): emitted={lit_only} vs v4={v4} delta={lit_only - v4}")

        em, left = dec_opcode_len_then_pixel(pay)
        print(
            f"  op+[len]+[pix] run of pix: emitted={em} leftover_in={left} vs v4={v4} "
            f"delta={em - v4} exact={em == v4 and left == 0}"
        )

        # opcode minus c = run of following
        hits_follow = []
        for c in constants:
            em, left = dec_opcode_minus_c_run_following(pay, c)
            if em == v4:
                hits_follow.append((c, em, left))
        print(f"  op-c = runlen of FOLLOWING: exact_hits={hits_follow}")
        # always print a few representative c
        for c in (0, 18, 0x80, 0x81):
            em, left = dec_opcode_minus_c_run_following(pay, c)
            print(
                f"    c={c} emitted={em} leftover={left} vs v4={v4} delta={em - v4} exact={em == v4}"
            )

        hits_lit = []
        for c in constants:
            em, left = dec_opcode_is_literal_count(pay, c)
            if em == v4:
                hits_lit.append((c, em, left))
        print(f"  op-c = count of verbatim literals: exact_hits={hits_lit}")
        for c in (0, 18, 0x80, 0x81):
            em, left = dec_opcode_is_literal_count(pay, c)
            print(
                f"    c={c} emitted={em} leftover={left} vs v4={v4} delta={em - v4} exact={em == v4}"
            )

        hits_prev = []
        for c in constants:
            em, left = dec_opcode_run_of_prev(pay, c)
            if em == v4:
                hits_prev.append((c, em, left))
        print(f"  op-c = run of PREVIOUS pixel: exact_hits={hits_prev}")
        for c in (0, 18, 0x80):
            em, left = dec_opcode_run_of_prev(pay, c)
            print(
                f"    c={c} emitted={em} leftover={left} vs v4={v4} delta={em - v4} exact={em == v4}"
            )

    # extra: scan all 8 for any exact hit summary
    print("\nB4 exact-match summary across 195-202")
    any_exact = False
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        pay = pays[r["id"]]
        v4 = r["v4"]
        em, left = dec_opcode_len_then_pixel(pay)
        if em == v4:
            print(f"  {r['id']} EXACT op+[len]+[pix] leftover={left}")
            any_exact = True
        for label, fn in (
            ("follow", dec_opcode_minus_c_run_following),
            ("litcnt", dec_opcode_is_literal_count),
            ("prev", dec_opcode_run_of_prev),
        ):
            for c in constants:
                em, left = fn(pay, c)
                if em == v4:
                    print(f"  {r['id']} EXACT {label} c={c} leftover={left}")
                    any_exact = True
    if not any_exact:
        print("  NO exact emitted==v4 on any tried variant for any of 195-202")

    # ========== C ==========
    print("\n========== C re-render @23+v3 ==========")
    print("id start_v3 n_pay RAWEND n_pay_re h_v3 v_v3 h_re v_re dv first_row_ColorSpec")
    OUT.mkdir(parents=True, exist_ok=True)
    for r in rows:
        if r["id"] not in FLOORS:
            continue
        blob = r["blob"]
        pay = blob[r["start_v3"] :]
        pay_re = blob[r["rawend"] :]
        img = raster_from(pay, 128, 256)
        img_re = raster_from(pay_re, 128, 256)
        h_v3 = pearson_adj(img, 1)
        v_v3 = pearson_adj(img, 0)
        h_re = pearson_adj(img_re, 1)
        v_re = pearson_adj(img_re, 0)
        pal5 = stride5_table(blob)
        pal8 = stride8_table(blob)
        outp = OUT / f"{r['id']}_v3start_128x256.png"
        write_tiled(outp, pay, pal5, pal8)
        cs_ok, idxs = first_row_is_colorspec(pay)
        # also check if first 128 bytes equal packed 115..243
        row0 = pay[:128]
        packed_ct = blob[115:243]
        print(
            f"{r['id']} {r['start_v3']} {len(pay)} {r['rawend']} {len(pay_re)} "
            f"h_v3={h_v3:.6f} v_v3={v_v3:.6f} h_re={h_re:.6f} v_re={v_re:.6f} "
            f"dv={v_v3 - v_re:+.6f} ColorSpec_row0={cs_ok} idxs={idxs[:4]} "
            f"row0==packed115_128={row0 == packed_ct} "
            f"row0_hex={row0[:16].hex()}"
        )
        print(f"  pal5 n={len(pal5)} keys={sorted(pal5)} pal8 n={len(pal8)} keys={sorted(pal8)}")
        print(f"  wrote {outp.name}")

    print("\n========== DONE ==========")


if __name__ == "__main__":
    main()
