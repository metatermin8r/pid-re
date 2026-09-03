"""Instruction-shape scan of CODE 1-16. Candidates only. No scheme names.

Every even offset from 4 is tested; operand words that match an opcode
pattern are false-positive candidates, not decoded instructions.
"""
from __future__ import annotations

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mac_containers import iter_resources, load_resource_payload

APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
WIN = 80


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def i16(b: bytes, o: int) -> int:
    return struct.unpack_from(">h", b, o)[0]


def hx(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def is_move_b_postinc_src(w: int) -> bool:
    """move.b (An)+, Dn  = 0x1018 | (Dn<<9) | An"""
    for dn in range(8):
        for an in range(8):
            if w == (0x1018 | (dn << 9) | an):
                return True
    return False


def is_move_b_postinc_dst(w: int) -> bool:
    """move.b Dn, (An)+  = 0x10C0 | (An<<9) | Dn"""
    for an in range(8):
        for dn in range(8):
            if w == (0x10C0 | (an << 9) | dn):
                return True
    return False


def is_dbra(w: int) -> bool:
    return 0x51C8 <= w <= 0x51CF


def is_cmpi_b_dn(w: int) -> bool:
    """cmpi.b #imm, Dn  0x0C00 | Dn  (A1 category)."""
    return 0x0C00 <= w <= 0x0C07


def is_cmpi_b(w: int) -> bool:
    """CMPI.B #imm, <ea> candidate: 0000 1100 00 mmm rrr."""
    return (w & 0xFFC0) == 0x0C00


def is_cmpi_w(w: int) -> bool:
    return (w & 0xFFC0) == 0x0C40


def is_cmp_b(w: int) -> bool:
    """CMP.B <ea>, Dn: 1011 DDD 000 mmm rrr."""
    return (w & 0xF1C0) == 0xB000


def is_tst_b(w: int) -> bool:
    return (w & 0xFFC0) == 0x4A00


def is_btst_dyn(w: int) -> bool:
    """BTST Dn, <ea>: 0000 DDD 100 mmm rrr."""
    return (w & 0xF1C0) == 0x0100


def is_btst_imm(w: int) -> bool:
    """BTST #imm, <ea>: 0000 1000 00 mmm rrr."""
    return (w & 0xFFC0) == 0x0800


def load_codes() -> dict[int, bytes]:
    payload = load_resource_payload(APP)
    codes = {rid: blob for t, rid, blob in iter_resources(payload.data) if t == b"CODE"}
    return codes


def scan_words(blob: bytes) -> list[tuple[int, int]]:
    out = []
    n = len(blob)
    off = 4
    while off + 2 <= n:
        out.append((off, u16(blob, off)))
        off += 2
    return out


def classify_a1(w: int) -> str | None:
    if is_move_b_postinc_src(w):
        return "move_b_(An)+_Dn"
    if is_move_b_postinc_dst(w):
        return "move_b_Dn_(An)+"
    if is_dbra(w):
        return "dbra"
    if is_cmpi_b_dn(w):
        return "cmpi.b_Dn"
    if w == 0x4E75:
        return "rts"
    if w == 0x4E56:
        return "link"
    return None


def dbra_target(off: int, blob: bytes) -> tuple[int, int] | None:
    if off + 4 > len(blob):
        return None
    disp = i16(blob, off + 2)
    target = (off + 2) + disp
    return disp, target


def window_shapes(blob: bytes, start: int, end: int) -> dict:
    """Re-scan even offsets in [start, end)."""
    n_src = n_dst = n_dbra = n_cmpib = 0
    dbras = []
    moves_src = []
    moves_dst = []
    cmpibs = []
    off = start if start % 2 == 0 else start + 1
    if off < 4:
        off = 4
    while off + 2 <= min(end, len(blob)):
        w = u16(blob, off)
        if is_move_b_postinc_src(w):
            n_src += 1
            moves_src.append(off)
        if is_move_b_postinc_dst(w):
            n_dst += 1
            moves_dst.append(off)
        if is_dbra(w):
            n_dbra += 1
            dbras.append(off)
        if is_cmpi_b_dn(w) or is_cmpi_b(w):
            n_cmpib += 1
            cmpibs.append(off)
        off += 2
    return {
        "n_src": n_src,
        "n_dst": n_dst,
        "n_move": n_src + n_dst,
        "n_dbra": n_dbra,
        "n_cmpib": n_cmpib,
        "dbras": dbras,
        "moves_src": moves_src,
        "moves_dst": moves_dst,
        "cmpibs": cmpibs,
    }


def rank_key(win: dict, blob: bytes) -> tuple:
    both = 1 if (win["n_src"] and win["n_dst"]) else 0
    has_cmp = 1 if win["n_cmpib"] else 0
    back_inside = 0
    for d in win["dbras"]:
        dt = dbra_target(d, blob)
        if dt is None:
            continue
        _disp, tgt = dt
        if tgt < d and win["start"] <= tgt < win["end"]:
            back_inside = 1
            break
    return (both, has_cmp, back_inside)


def has_backward_dbra(win: dict, blob: bytes) -> bool:
    for d in win["dbras"]:
        dt = dbra_target(d, blob)
        if dt is None:
            continue
        _disp, tgt = dt
        if tgt < d:
            return True
    return False


def cmp_decode(blob: bytes, off: int, w: int) -> list[dict]:
    """Candidate comparison decodes at this even offset. Unsure -> UNKNOWN."""
    hits = []
    n = len(blob)
    if is_cmpi_b(w):
        if off + 4 <= n:
            immw = u16(blob, off + 2)
            imm = immw & 0xFF
            hits.append(
                {
                    "kind": "cmpi.b",
                    "bytes": blob[off : off + 4],
                    "imm": imm,
                    "immw": immw,
                    "mnemonic": f"CMPI.B #${imm:02X}, ea={w & 0x3F:02X}  [cand]",
                }
            )
        else:
            hits.append(
                {
                    "kind": "cmpi.b",
                    "bytes": blob[off : off + 2],
                    "imm": None,
                    "immw": None,
                    "mnemonic": "UNKNOWN truncated cmpi.b candidate",
                }
            )
    if is_cmpi_w(w):
        if off + 4 <= n:
            immw = u16(blob, off + 2)
            hits.append(
                {
                    "kind": "cmpi.w",
                    "bytes": blob[off : off + 4],
                    "imm": immw,
                    "immw": immw,
                    "mnemonic": f"CMPI.W #${immw:04X}, ea={w & 0x3F:02X}  [cand]",
                }
            )
        else:
            hits.append(
                {
                    "kind": "cmpi.w",
                    "bytes": blob[off : off + 2],
                    "imm": None,
                    "immw": None,
                    "mnemonic": "UNKNOWN truncated cmpi.w candidate",
                }
            )
    if is_cmp_b(w):
        dn = (w >> 9) & 7
        hits.append(
            {
                "kind": "cmp.b",
                "bytes": blob[off : off + 2],
                "imm": None,
                "immw": None,
                "mnemonic": f"CMP.B ea={w & 0x3F:02X}, D{dn}  [cand]",
            }
        )
    if is_tst_b(w):
        hits.append(
            {
                "kind": "tst.b",
                "bytes": blob[off : off + 2],
                "imm": None,
                "immw": None,
                "mnemonic": f"TST.B ea={w & 0x3F:02X}  [cand]",
            }
        )
    if is_btst_imm(w):
        if off + 4 <= n:
            immw = u16(blob, off + 2)
            bit = immw & 0xFF
            hits.append(
                {
                    "kind": "btst#",
                    "bytes": blob[off : off + 4],
                    "imm": bit,
                    "immw": immw,
                    "mnemonic": f"BTST #{bit}, ea={w & 0x3F:02X}  [cand]",
                }
            )
        else:
            hits.append(
                {
                    "kind": "btst#",
                    "bytes": blob[off : off + 2],
                    "imm": None,
                    "immw": None,
                    "mnemonic": "UNKNOWN truncated btst# candidate",
                }
            )
    if is_btst_dyn(w):
        dn = (w >> 9) & 7
        hits.append(
            {
                "kind": "btst Dn",
                "bytes": blob[off : off + 2],
                "imm": None,
                "immw": None,
                "mnemonic": f"BTST D{dn}, ea={w & 0x3F:02X}  [cand]",
            }
        )
    return hits


def find_functions(blob: bytes) -> list[tuple[int, int, int]]:
    """Each 4E56 paired with the next 4E75 after it. Candidate only."""
    links = []
    rts = []
    for off, w in scan_words(blob):
        if w == 0x4E56:
            links.append(off)
        elif w == 0x4E75:
            rts.append(off)
    funcs = []
    for s in links:
        ends = [e for e in rts if e > s]
        if not ends:
            continue
        e = ends[0]
        funcs.append((s, e + 2, (e + 2) - s))
    return funcs


def traps_in(blob: bytes, start: int, end: int) -> int:
    n = 0
    off = start if start % 2 == 0 else start + 1
    while off + 2 <= min(end, len(blob)):
        w = u16(blob, off)
        if 0xA000 <= w <= 0xAFFF:
            n += 1
        off += 2
    return n


def jsrs_in(blob: bytes, start: int, end: int) -> list[dict]:
    hits = []
    off = start if start % 2 == 0 else start + 1
    while off + 2 <= min(end, len(blob)):
        w = u16(blob, off)
        if w == 0x4EB8 and off + 4 <= len(blob):
            op = u16(blob, off + 2)
            hits.append(
                {
                    "off": off,
                    "bytes": blob[off : off + 4],
                    "form": "4EB8 abs.W",
                    "operand": op,
                    "note": f"abs.W=${op:04X}",
                }
            )
        elif w == 0x4EBA and off + 4 <= len(blob):
            disp = i16(blob, off + 2)
            tgt = (off + 2) + disp
            hits.append(
                {
                    "off": off,
                    "bytes": blob[off : off + 4],
                    "form": "4EBA pc-rel",
                    "operand": disp,
                    "note": f"disp={disp} target={tgt} (0x{tgt:X})",
                }
            )
        elif w == 0x4EAD and off + 4 <= len(blob):
            disp = i16(blob, off + 2)
            hits.append(
                {
                    "off": off,
                    "bytes": blob[off : off + 4],
                    "form": "4EAD (d16,A5)",
                    "operand": disp,
                    "note": f"A5_disp={disp} (0x{disp & 0xFFFF:04X})",
                }
            )
        off += 2
    return hits


def main() -> None:
    codes = load_codes()
    print("METHOD: every even offset from 4. Hits are CANDIDATES (operand words may match).")
    print(f"CODE ids present={[k for k in sorted(codes) if k != 0]} n={len([k for k in codes if k!=0])}")

    all_hits: dict[int, dict[str, list[int]]] = {}
    print("\n========== A1 per-resource counts ==========")
    print("id  n_words  move_src  move_dst  move_any  dbra  cmpi.b_Dn  rts  link")
    for rid in range(1, 17):
        blob = codes[rid]
        cats = defaultdict(list)
        for off, w in scan_words(blob):
            c = classify_a1(w)
            if c:
                cats[c].append(off)
        all_hits[rid] = cats
        nsrc = len(cats["move_b_(An)+_Dn"])
        ndst = len(cats["move_b_Dn_(An)+"])
        print(
            f"{rid:2d}  {(len(blob)-4)//2:7d}  {nsrc:8d}  {ndst:8d}  {nsrc+ndst:8d}  "
            f"{len(cats['dbra']):4d}  {len(cats['cmpi.b_Dn']):9d}  "
            f"{len(cats['rts']):3d}  {len(cats['link']):4d}"
        )

    print("\n========== A2 windows <=80B with postinc move AND dbra ==========")
    windows = []
    for rid in range(1, 17):
        blob = codes[rid]
        cats = all_hits[rid]
        moves = cats["move_b_(An)+_Dn"] + cats["move_b_Dn_(An)+"]
        for d in cats["dbra"]:
            d_end = d + 4
            near = []
            for m in moves:
                m_end = m + 2
                start = min(m, d)
                end = max(m_end, d_end)
                if end - start <= WIN:
                    near.append(m)
            if not near:
                continue
            start = min(near + [d])
            end = max([m + 2 for m in near] + [d + 4])
            if end - start > WIN:
                continue
            sh = window_shapes(blob, start, end)
            rec = {
                "id": rid,
                "start": start,
                "end": end,
                "len": end - start,
                "key_dbra": d,
                **sh,
            }
            rec["rank"] = rank_key(rec, blob)
            rec["back"] = has_backward_dbra(rec, blob)
            windows.append(rec)

    # unique by (id, start, end)
    uniq = {}
    for w in windows:
        uniq[(w["id"], w["start"], w["end"])] = w
    windows = sorted(uniq.values(), key=lambda x: (x["id"], x["start"]))
    print(f"A2 unique windows n={len(windows)}")
    for w in windows:
        blob = codes[w["id"]]
        print(
            f"  CODE {w['id']} [{w['start']},{w['end']}) len={w['len']} "
            f"src={w['n_src']} dst={w['n_dst']} dbra={w['n_dbra']} cmpi.b={w['n_cmpib']} "
            f"rank={w['rank']} backward_dbra={w['back']}"
        )
        print(f"    hex={hx(blob[w['start']:w['end']])}")

    print("\n========== A3 ranked ==========")
    ranked = sorted(windows, key=lambda x: (x["rank"], -x["len"]), reverse=True)
    for i, w in enumerate(ranked, 1):
        print(
            f"  #{i:02d} CODE {w['id']} [{w['start']},{w['end']}) len={w['len']} "
            f"both_src_dst={w['rank'][0]} cmpi.b={w['rank'][1]} "
            f"dbra_back_inside={w['rank'][2]} back_any={w['back']} "
            f"src={w['n_src']} dst={w['n_dst']} dbra={w['n_dbra']}"
        )

    print("\n========== A4 every dbra ==========")
    tight = []
    n_dbra_all = 0
    n_dbra_back = 0
    n_dbra_fwd = 0
    n_dbra_bad = 0
    for rid in range(1, 17):
        blob = codes[rid]
        for d in all_hits[rid]["dbra"]:
            n_dbra_all += 1
            w = u16(blob, d)
            dt = dbra_target(d, blob)
            if dt is None:
                n_dbra_bad += 1
                print(f"  CODE {rid} dbra @{d} (0x{d:X}) word={w:04X} UNKNOWN no disp word")
                continue
            disp, tgt = dt
            back = tgt < d
            dist = d - tgt if back else tgt - d
            if back:
                n_dbra_back += 1
            else:
                n_dbra_fwd += 1
            flag = ""
            if back and dist < WIN:
                flag = " TIGHT_BACK_LT_80"
                tight.append((rid, d, disp, tgt, dist))
            print(
                f"  CODE {rid} dbra @{d} (0x{d:X}) word={w:04X} bytes={hx(blob[d:d+4])} "
                f"disp={disp} target={tgt} (0x{tgt:X}) "
                f"{'BACK' if back else 'FWD'} dist={dist}{flag}"
            )
    print(
        f"A4 dbra n={n_dbra_all} back={n_dbra_back} fwd={n_dbra_fwd} truncated={n_dbra_bad} "
        f"tight_back_lt_80 n={len(tight)}"
    )

    go = [w for w in windows if w["back"]]
    go_ids = sorted({w["id"] for w in go})
    print("\n========== GO ==========")
    print(
        f"windows<=80 with postinc-byte-move AND backward-dbra n={len(go)} "
        f"CODE_ids={go_ids}"
    )

    print("\n========== B1 comparisons inside A2 windows ==========")
    for w in windows:
        blob = codes[w["id"]]
        print(f"\n--- CODE {w['id']} [{w['start']},{w['end']}) ---")
        n_comp = 0
        off = w["start"] if w["start"] % 2 == 0 else w["start"] + 1
        while off + 2 <= w["end"]:
            word = u16(blob, off)
            for dec in cmp_decode(blob, off, word):
                n_comp += 1
                imm_s = ""
                if dec["imm"] is not None:
                    imm_s = f" imm=0x{dec['imm']:X} ({dec['imm']})"
                print(
                    f"  off={off} (0x{off:X}) kind={dec['kind']} "
                    f"bytes={hx(dec['bytes'])} {dec['mnemonic']}{imm_s}"
                )
            off += 2
        print(f"  comparison_candidates n={n_comp}")

    print("\n========== B2 cmpi.b immediate histogram CODE 1-16 ==========")
    imm_hist = Counter()
    imm_locs = defaultdict(list)
    n_cmpi_b = 0
    n_cmpi_b_hi = 0
    for rid in range(1, 17):
        blob = codes[rid]
        for off, w in scan_words(blob):
            if not is_cmpi_b(w):
                continue
            if off + 4 > len(blob):
                continue
            n_cmpi_b += 1
            immw = u16(blob, off + 2)
            if immw & 0xFF00:
                n_cmpi_b_hi += 1
            imm = immw & 0xFF
            imm_hist[imm] += 1
            imm_locs[imm].append((rid, off, immw))
    print(f"cmpi.b candidates n={n_cmpi_b} with_nonzero_imm_high_byte n={n_cmpi_b_hi}")
    print("top 30 imm_lo (value count):")
    for imm, c in imm_hist.most_common(30):
        print(f"  imm=0x{imm:02X} ({imm:3d}) n={c}")

    print("\n========== B3 selected cmpi.b immediates ==========")
    wanted = [0x80, 0x81, 0x02, 0x03, 0x11, 0x12, 0x18, 0xC0]
    for imm in wanted:
        locs = imm_locs.get(imm, [])
        print(f"cmpi.b #0x{imm:02X} n={len(locs)}")
        for rid, off, immw in locs:
            print(
                f"  CODE {rid} off={off} (0x{off:X}) bytes={hx(codes[rid][off:off+4])} "
                f"immw=0x{immw:04X}"
            )

    print("\n========== B4 every btst candidate ==========")
    n_btst = 0
    for rid in range(1, 17):
        blob = codes[rid]
        for off, w in scan_words(blob):
            if is_btst_imm(w):
                n_btst += 1
                if off + 4 <= len(blob):
                    immw = u16(blob, off + 2)
                    bit = immw & 0xFF
                    print(
                        f"  CODE {rid} off={off} (0x{off:X}) BTST# bytes={hx(blob[off:off+4])} "
                        f"bit={bit} (0x{bit:X}) ea={w & 0x3F:02X} immw=0x{immw:04X}  [cand]"
                    )
                else:
                    print(f"  CODE {rid} off={off} BTST# UNKNOWN truncated bytes={hx(blob[off:off+2])}")
            elif is_btst_dyn(w):
                n_btst += 1
                dn = (w >> 9) & 7
                print(
                    f"  CODE {rid} off={off} (0x{off:X}) BTST D{dn} bytes={hx(blob[off:off+2])} "
                    f"ea={w & 0x3F:02X}  [cand]"
                )
    print(f"B4 btst candidates n={n_btst}")

    print("\n========== C1 candidate functions LINK..next RTS ==========")
    all_funcs = {}
    longest = []
    for rid in range(1, 17):
        funcs = find_functions(codes[rid])
        all_funcs[rid] = funcs
        print(f"CODE {rid} functions n={len(funcs)}")
        for s, e, ln in funcs:
            longest.append((ln, rid, s, e))
    longest.sort(reverse=True)
    print("20 longest:")
    for ln, rid, s, e in longest[:20]:
        print(f"  CODE {rid} [{s},{e}) len={ln}")
    print(f"C1 total functions n={sum(len(v) for v in all_funcs.values())}")

    print("\n========== C2 window -> function ==========")
    win_funcs = []
    for w in windows:
        funcs = all_funcs[w["id"]]
        owners = [f for f in funcs if f[0] <= w["start"] and w["end"] <= f[1]]
        if not owners:
            print(
                f"  CODE {w['id']} window [{w['start']},{w['end']}) NO containing LINK..RTS"
            )
            win_funcs.append((w, None))
        else:
            for s, e, ln in owners:
                print(
                    f"  CODE {w['id']} window [{w['start']},{w['end']}) "
                    f"func [{s},{e}) len={ln}"
                )
                win_funcs.append((w, (s, e, ln)))

    print("\n========== C3 jsr in those functions ==========")
    seen_fn = set()
    for w, fn in win_funcs:
        if fn is None:
            continue
        key = (w["id"], fn[0], fn[1])
        if key in seen_fn:
            continue
        seen_fn.add(key)
        blob = codes[w["id"]]
        s, e, ln = fn
        js = jsrs_in(blob, s, e)
        print(f"\nCODE {w['id']} func [{s},{e}) len={ln} jsr_cand n={len(js)}")
        for j in js:
            print(
                f"  off={j['off']} (0x{j['off']:X}) {j['form']} "
                f"bytes={hx(j['bytes'])} {j['note']}"
            )

    print("\n========== C4 those functions with zero A000-AFFF words ==========")
    seen_fn = set()
    n_pure = 0
    for w, fn in win_funcs:
        if fn is None:
            continue
        key = (w["id"], fn[0], fn[1])
        if key in seen_fn:
            continue
        seen_fn.add(key)
        s, e, ln = fn
        nt = traps_in(codes[w["id"]], s, e)
        flag = "NO_TRAPS" if nt == 0 else f"traps={nt}"
        if nt == 0:
            n_pure += 1
        print(f"  CODE {w['id']} func [{s},{e}) len={ln} {flag}")
    print(f"C4 window-functions with no A-line traps n={n_pure}")

    print("\n========== DONE ==========")


if __name__ == "__main__":
    main()
