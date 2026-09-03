"""Byte-scan CODE resources for .256 type literal and A-line traps.

Read-only on game data. Writes extracted CODE blobs under reference/docs/code/.
Does not name or classify any compression scheme.
"""
from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mac_containers import iter_resources, load_resource_payload

APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
OUT = ROOT / "reference/docs/code"

TYPE256 = b".256"  # 2E 32 35 36
NEEDLE = bytes.fromhex("2E323536")
MOVE_L_IMM_SP = bytes.fromhex("2F3C2E323536")
PEA_ABSL = bytes.fromhex("48792E323536")
PEA_ABSW_PREFIX = bytes.fromhex("4878")  # only 16-bit ext; report if 2E32 follows

TRAPS_OF_INTEREST = {
    0xA9A0: "A9A0",
    0xA9A6: "A9A6",
    0xA11E: "A11E",
    0xA122: "A122",
    0xA029: "A029",
    0xA02A: "A02A",
    0xA9A3: "A9A3",
    0xA992: "A992",
    0xA025: "A025",
}

GETRES = {0xA9A0, 0xA9A6}
ALLOC = {0xA11E, 0xA122}


def hx(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def findall(hay: bytes, needle: bytes) -> list[int]:
    out = []
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def load_rsrc(path: Path):
    payload = load_resource_payload(path)
    if payload is None:
        raise SystemExit(f"no resource map in {path}")
    items = iter_resources(payload.data)
    return payload, items


def context(blob: bytes, off: int, before: int, after: int) -> tuple[bytes, bytes]:
    lo = max(0, off - before)
    hi = min(len(blob), off + after)
    return blob[lo:off], blob[off:hi]


def scan_traps(blob: bytes) -> list[tuple[int, int]]:
    """Even offsets from 4: (offset, word)."""
    hits = []
    n = len(blob)
    off = 4
    while off + 2 <= n:
        w = struct.unpack_from(">H", blob, off)[0]
        if 0xA000 <= w <= 0xAFFF:
            hits.append((off, w))
        off += 2
    return hits


def find_immediates(window: bytes, win_base: int) -> list[tuple[int, str, int]]:
    """Report 8-bit and 16-bit BE occurrences of 23, 7, 4, 6. No interpretation."""
    targets = (23, 7, 4, 6)
    found = []
    for i, b in enumerate(window):
        if b in targets:
            found.append((win_base + i, "u8", b))
    for i in range(0, len(window) - 1):
        w = (window[i] << 8) | window[i + 1]
        if w in targets:
            found.append((win_base + i, "u16be", w))
    found.sort(key=lambda t: (t[0], t[1]))
    return found


def main() -> None:
    print(f"APP exists={APP.exists()} size={APP.stat().st_size}")
    print(f"SHAPES exists={SHAPES.exists()} size={SHAPES.stat().st_size}")

    _pay, app_items = load_rsrc(APP)
    codes = {rid: blob for typ, rid, blob in app_items if typ == b"CODE"}
    print(f"CODE resources n={len(codes)} ids={sorted(codes)}")
    if set(codes) != set(range(17)):
        print(f"ANOMALY CODE ids expected 0..16 got {sorted(codes)}")

    OUT.mkdir(parents=True, exist_ok=True)

    print("\n========== A1 extract CODE ==========")
    print("id length first16")
    for rid in sorted(codes):
        blob = codes[rid]
        path = OUT / f"CODE_{rid:02d}.bin"
        path.write_bytes(blob)
        print(f"{rid:2d} {len(blob):6d} {hx(blob[:16])}  wrote {path.name}")

    print("\n========== A2 2E323536 in CODE ==========")
    code_hits: list[tuple[int, int]] = []
    for rid in sorted(codes):
        blob = codes[rid]
        offs = findall(blob, NEEDLE)
        for off in offs:
            code_hits.append((rid, off))
            before, at = context(blob, off, 32, 16)
            print(f"HIT CODE id={rid} off={off} (0x{off:X}) n={len(blob)}")
            print(f"  before32: {hx(before)}")
            print(f"  at16:     {hx(at)}")
            print(f"  ctx48:    {hx(before + at)}")
    print(f"A2 total CODE hits n={len(code_hits)}")
    if not code_hits:
        print("A2 NONE — type literal not present as raw 2E323536 in any CODE")

    print("\n========== A3 2E323536 all resources APP + SHAPES ==========")
    print("--- Pathways Into Darkness.rsrc ---")
    app_type_hits = []
    for typ, rid, blob in app_items:
        for off in findall(blob, NEEDLE):
            app_type_hits.append((typ, rid, off, len(blob)))
            tdisp = typ.decode("latin-1") if all(32 <= c < 127 for c in typ) else typ.hex()
            print(f"  type={tdisp!r} {typ.hex()} id={rid} off={off} (0x{off:X}) len={len(blob)}")
    print(f"APP resource-payload hits n={len(app_type_hits)}")

    # also raw file (map + payloads) as control
    app_raw = APP.read_bytes()
    raw_offs = findall(app_raw, NEEDLE)
    print(f"APP raw-file hits n={len(raw_offs)} offs={raw_offs}")

    print("--- Shapes.rsrc ---")
    _sp, shape_items = load_rsrc(SHAPES)
    shape_hits = []
    for typ, rid, blob in shape_items:
        for off in findall(blob, NEEDLE):
            shape_hits.append((typ, rid, off, len(blob)))
    print(f"SHAPES resource-payload hits n={len(shape_hits)}")
    by_type: Counter = Counter()
    for typ, rid, off, ln in shape_hits:
        by_type[typ] += 1
    for typ, n in sorted(by_type.items(), key=lambda x: (-x[1], x[0])):
        tdisp = typ.decode("latin-1") if all(32 <= c < 127 for c in typ) else typ.hex()
        print(f"  type={tdisp!r} {typ.hex()} n={n}")
    # map control: raw file
    sh_raw = SHAPES.read_bytes()
    sh_raw_offs = findall(sh_raw, NEEDLE)
    print(f"SHAPES raw-file hits n={len(sh_raw_offs)}")

    print("\n========== A4 move.l #imm,-(sp) and pea ==========")
    print("pattern 2F 3C 2E 32 35 36  (move.l #imm, -(sp))")
    n_movel = 0
    for rid in sorted(codes):
        for off in findall(codes[rid], MOVE_L_IMM_SP):
            n_movel += 1
            print(f"  MOVE.L CODE id={rid} off={off} (0x{off:X}) bytes={hx(codes[rid][off:off+6])}")
    print(f"move.l #imm,-(sp) hits n={n_movel}")

    print("pattern 48 79 2E 32 35 36  (pea abs.L)")
    n_pea_l = 0
    for rid in sorted(codes):
        for off in findall(codes[rid], PEA_ABSL):
            n_pea_l += 1
            print(f"  PEA.L CODE id={rid} off={off} (0x{off:X}) bytes={hx(codes[rid][off:off+6])}")
    print(f"pea abs.L hits n={n_pea_l}")

    print("pattern 48 78 2E 32  (pea abs.W + first two type bytes; incomplete type)")
    n_pea_w = 0
    for rid in sorted(codes):
        for off in findall(codes[rid], PEA_ABSW_PREFIX + NEEDLE[:2]):
            n_pea_w += 1
            print(f"  PEA.W CODE id={rid} off={off} (0x{off:X}) bytes={hx(codes[rid][off:off+4])}")
    print(f"pea abs.W 2E32 hits n={n_pea_w}")

    print("pattern 2X 3C 2E 32 35 36  (move.l #imm, Dn) X=0..7")
    n_moved = 0
    for rid in sorted(codes):
        blob = codes[rid]
        for dn in range(8):
            pat = bytes([0x20 + (dn << 1), 0x3C]) + NEEDLE
            for off in findall(blob, pat):
                n_moved += 1
                print(
                    f"  MOVE.L #imm,D{dn} CODE id={rid} off={off} (0x{off:X}) "
                    f"bytes={hx(blob[off:off+6])}"
                )
    print(f"move.l #imm,Dn hits n={n_moved}")

    print("pattern 48 7A / 48 7B (pea pc-rel) — type not inline; list 487A/487B words only if 2E323536 within 8 bytes after")
    n_pea_pc = 0
    for rid in sorted(codes):
        blob = codes[rid]
        for i in range(4, len(blob) - 1, 2):
            w = struct.unpack_from(">H", blob, i)[0]
            if w in (0x487A, 0x487B):
                window = blob[i : i + 10]
                if NEEDLE in window:
                    n_pea_pc += 1
                    print(f"  PEA.PC CODE id={rid} off={i} (0x{i:X}) bytes={hx(window)}")
    print(f"pea pc-rel with nearby type n={n_pea_pc}")

    print("\n========== GO line ==========")
    print(
        f"CODE 2E323536 occurrences n={len(code_hits)} "
        f"sites={[f'CODE {r} @{o}' for r, o in code_hits]}"
    )

    print("\n========== B1 trap histogram even offs from 4 ==========")
    all_traps: Counter = Counter()
    per_res: dict[int, list[tuple[int, int]]] = {}
    for rid in sorted(codes):
        hits = scan_traps(codes[rid])
        per_res[rid] = hits
        hist = Counter(w for _o, w in hits)
        all_traps.update(hist)
        print(f"\nCODE {rid} n_words_scanned={(len(codes[rid]) - 4) // 2} n_traps={len(hits)} distinct={len(hist)}")
        for w, c in hist.most_common():
            tag = TRAPS_OF_INTEREST.get(w, "")
            extra = f" {tag}" if tag else ""
            print(f"  {w:04X} {c:5d}{extra}")

    print("\n========== B2 named trap totals ==========")
    for w, name in TRAPS_OF_INTEREST.items():
        print(f"  {name} n={all_traps[w]}")

    print("\n========== B3 every A9A0 / A9A6 ==========")
    getres_sites: list[tuple[int, int, int]] = []
    for rid in sorted(codes):
        for off, w in per_res[rid]:
            if w not in GETRES:
                continue
            getres_sites.append((rid, off, w))
            before, _ = context(codes[rid], off, 64, 0)
            print(
                f"GETRES CODE id={rid} off={off} (0x{off:X}) word={w:04X} "
                f"prev64={hx(before)}"
            )
            # also mark if NEEDLE in those 64
            has = NEEDLE in before
            print(f"  needle_in_prev64={has}")
    print(f"B3 A9A0+A9A6 n={len(getres_sites)}")

    print("\n========== B4 A9A0/A9A6 with 2E323536 in prev 64 ==========")
    loaders = []
    for rid, off, w in getres_sites:
        before, _ = context(codes[rid], off, 64, 0)
        if NEEDLE in before:
            needle_at = before.rfind(NEEDLE)
            # offset of needle in resource
            n_off = off - len(before) + needle_at
            loaders.append((rid, off, w, n_off))
            print(
                f"LOADER CODE id={rid} trap_off={off} (0x{off:X}) word={w:04X} "
                f"needle_off={n_off} (0x{n_off:X}) delta={off - n_off}"
            )
    print(f"B4 loader sites n={len(loaders)}")
    if not loaders:
        print("B4 NONE")

    print("\n========== C1 every A11E / A122 ==========")
    alloc_sites = []
    for rid in sorted(codes):
        for off, w in per_res[rid]:
            if w not in ALLOC:
                continue
            alloc_sites.append((rid, off, w))
            before, _ = context(codes[rid], off, 64, 0)
            print(
                f"ALLOC CODE id={rid} off={off} (0x{off:X}) word={w:04X} "
                f"prev64={hx(before)}"
            )
    print(f"C1 NewPtr+NewHandle n={len(alloc_sites)}")

    print("\n========== C2 alloc within 256 bytes of a B4 loader ==========")
    near = []
    for arid, aoff, aw in alloc_sites:
        for lrid, loff, lw, n_off in loaders:
            if arid != lrid:
                continue
            dist = abs(aoff - loff)
            if dist <= 256:
                near.append((arid, aoff, aw, loff, lw, dist))
                print(
                    f"NEAR CODE id={arid} alloc={aw:04X} @{aoff} loader={lw:04X} @{loff} "
                    f"dist={dist}"
                )
    print(f"C2 near-pairs n={len(near)}")
    if not near:
        print("C2 NONE")

    print("\n========== C3 header-offset literals in ±256 of each B4 site ==========")
    for lrid, loff, lw, n_off in loaders:
        blob = codes[lrid]
        lo = max(0, loff - 256)
        hi = min(len(blob), loff + 256)
        window = blob[lo:hi]
        print(
            f"\n--- CODE {lrid} loader trap @{loff} (0x{loff:X}) window [{lo},{hi}) "
            f"n={len(window)} word={lw:04X} ---"
        )
        imms = find_immediates(window, lo)
        print(f"  literal 23/7/4/6 occurrences n={len(imms)}")
        for abs_off, kind, val in imms:
            rel = abs_off - loff
            print(f"    abs={abs_off} (0x{abs_off:X}) rel={rel:+d} {kind} val={val} (0x{val:02X})")

    print("\n========== DONE ==========")


if __name__ == "__main__":
    main()
