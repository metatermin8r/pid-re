#!/usr/bin/env python3
"""Think C DATAINIT expander for Pathways Into Darkness CODE 11.

Format derived from the 68020 listing of JT 305 (CODE 11 file offset 4),
not from MPW %_DATAINIT docs and not from tools/decode_256.py.

CODE 11 file +0..+3 is the 4-byte segment header (`09 88 00 01`).
The expander begins at file +4.
Header is LEA'd at file +$1B2 (434): `49 FA 01 A8` with PC of the
extension word at +10, +10+$1A8 = +434.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

CODE11_PATH = ROOT / "reference" / "docs" / "code" / "CODE_11.bin"
CODE0_PATH = ROOT / "reference" / "docs" / "code" / "CODE_00.bin"
APP_RSRC = ROOT / "data" / "hfs" / "Pathways_1995" / "Pathways Into Darkness.rsrc"
OUT_IMAGE = ROOT / "out" / "a5_image.bin"

# File offsets inside CODE 11, from the listing.
EXPANDER_FILE = 4
HEADER_FILE = 0x1B2  # 434; LEA target
HEADER_LEN = 20
UNCOMPRESS_FILE = 94
GET_RL_FILE = 190
RELOC_FILE = 274
ZERO_FILE = 366


class StreamError(Exception):
    pass


class PackStream:
    """A0 in the uncompress / get_rl listing: `move.b (a0)+, …`."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.i = 0

    def u8(self) -> int:
        if self.i >= len(self.data):
            raise StreamError(f"src overrun at {self.i} of {len(self.data)}")
        b = self.data[self.i]
        self.i += 1
        return b


def get_rl(s: PackStream) -> tuple[int, int | None]:
    """CODE 11 @190. Returns (d0, optional new d3).

    @190  70 00         moveq #$0, d0
    @192  10 18         move.b (a0)+, d0
    @194  6A 42         bpl → @262 rts          ; d0 < $80: value is the byte
    @196  08 00 00 06   btst.b #$6, d0
    @200  67 34         beq → @254              ; $80..$BF
    @202  08 00 00 05   btst.b #$5, d0
    @206  67 20         beq → @240              ; $C0..$DF
    @208  08 00 00 04   btst.b #$4, d0
    @212  67 0A         beq → @224              ; $E0..$EF
    @214  bsr get_rl / move.l d0,d3 / bsr get_rl / exg d0,d3 / rts  ; $F0..$FF
    """
    d0 = s.u8()
    if d0 < 0x80:
        return d0, None
    if (d0 & 0x40) == 0:
        # @254 andi.b #$3F / asl.l #8 / move.b (a0)+, d0
        return ((d0 & 0x3F) << 8) | s.u8(), None
    if (d0 & 0x20) == 0:
        # @240 andi.b #$1F / asl.l #8 / byte / asl.l #8 / byte
        return ((d0 & 0x1F) << 16) | (s.u8() << 8) | s.u8(), None
    if (d0 & 0x10) == 0:
        # @224 four move.b (a0)+, d0 with asl.l #8; control nibble discarded
        v = (s.u8() << 24) | (s.u8() << 16) | (s.u8() << 8) | s.u8()
        return v, None
    first, _ = get_rl(s)
    second, _ = get_rl(s)
    return first, second


def uncompress(src: bytes, dest_size: int) -> tuple[bytearray, dict]:
    """CODE 11 @94. dest is a contiguous image, A1 walking from 0.

    Control byte:
      low nibble  = copy count; 0 → get_rl (0 terminates); else nibble*2
      high nibble = skip count; 0 → get_rl; else nibble>>3
    Then: A1 += skip; copy `count` literals; repeat that pair d3 times.
    d3 starts at 1 each control (`76 01` @106) and is replaced only by
    a $F0..$FF get_rl. Gaps stay zero from the prior ZEROBUFFER.
    """
    s = PackStream(src)
    dest = bytearray(dest_size)
    a1 = 0
    ops = 0
    while True:
        d3 = 1  # @106 moveq #$1, d3
        b = s.u8()
        d1 = b & 0x0F
        d2 = b & 0xF0
        extra = None
        if d1 == 0:
            d1, extra = get_rl(s)
            if extra is not None:
                d3 = extra
            if d1 == 0:
                break
        else:
            d1 = d1 * 2  # @130 add.w d1, d1
        if d2 == 0:
            d2, extra = get_rl(s)
            if extra is not None:
                d3 = extra
        else:
            d2 >>= 3  # @146 lsr.w #$3, d2
        while True:
            a1 += d2
            if a1 + d1 > dest_size:
                raise StreamError(f"dest overrun a1={a1} d1={d1} size={dest_size}")
            for _ in range(d1):
                dest[a1] = s.u8()
                a1 += 1
            d3 -= 1
            if d3 == 0:
                break
        ops += 1
    stats = {
        "src_consumed": s.i,
        "src_len": len(src),
        "src_remaining": len(src) - s.i,
        "dest_size": dest_size,
        "dest_high_water": a1,
        "control_ops": ops,
        "terminated_on_zero_copy": True,
    }
    return dest, stats


def parse_header(code11: bytes, hdr: int = HEADER_FILE) -> dict:
    if hdr + HEADER_LEN > len(code11):
        raise StreamError(f"CODE 11 too short for header at +{hdr}")
    raw = code11[hdr : hdr + HEADER_LEN]
    dest_size = struct.unpack_from(">I", raw, 0)[0]
    flag = struct.unpack_from(">H", raw, 4)[0]
    unk6 = struct.unpack_from(">H", raw, 6)[0]
    off_data = struct.unpack_from(">I", raw, 8)[0]
    off_rel = struct.unpack_from(">I", raw, 12)[0]
    unk16 = struct.unpack_from(">I", raw, 16)[0]
    return {
        "file": hdr,
        "raw": raw,
        "dest_size": dest_size,
        "flag": flag,
        "unk6": unk6,
        "off_data": off_data,
        "off_rel": off_rel,
        "unk16": unk16,
        "packed_file": hdr + off_data,
        "reloc_file": hdr + off_rel,
    }


def expand_code11(code11: bytes) -> tuple[bytes, dict]:
    """Run the expander's zero + uncompress. Relocs add runtime A5; not applied."""
    if len(code11) < 8:
        raise StreamError("CODE 11 too short")
    seg0 = struct.unpack_from(">H", code11, 0)[0]
    seg2 = struct.unpack_from(">H", code11, 2)[0]
    hdr = parse_header(code11)
    if hdr["flag"] != 1:
        raise StreamError(f"header +4 is {hdr['flag']}, expander requires 1 (`subq.w #1` / `beq`)")
    packed = code11[hdr["packed_file"] : hdr["reloc_file"]]
    dest, stats = uncompress(packed, hdr["dest_size"])
    info = {
        "seg_header": (seg0, seg2),
        "header": hdr,
        **stats,
        "reloc_bytes": len(code11) - hdr["reloc_file"],
    }
    return bytes(dest), info


def a5_to_image(disp: int, dest_size: int) -> int:
    """A5 displacement (negative) → offset in the contiguous image.

    @24 movea.l a5, a3 / @26 suba.l (a4), a3  → image base = A5 - dest_size.
    image[i] lives at A5 + (i - dest_size).
    """
    if disp > 0:
        raise ValueError("below-A5 displacements are negative")
    off = dest_size + disp
    if off < 0 or off > dest_size:
        raise ValueError(f"disp {disp} maps to {off} outside 0..{dest_size}")
    return off


def load_code11() -> tuple[bytes, str]:
    if CODE11_PATH.is_file():
        blob = CODE11_PATH.read_bytes()
        return blob, str(CODE11_PATH)
    from mac_containers import resources_of_type

    codes = resources_of_type(APP_RSRC, b"CODE")
    if 11 not in codes:
        raise FileNotFoundError("CODE 11 not in application rsrc")
    return codes[11], f"{APP_RSRC} CODE 11"


def below_a5_from_code0(code0: bytes) -> int:
    """CODE 0 +4 u32be = below-A5 size."""
    return struct.unpack_from(">I", code0, 4)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Expand Think C DATAINIT from CODE 11")
    ap.add_argument("-o", "--output", type=Path, default=OUT_IMAGE)
    args = ap.parse_args()

    code11, src = load_code11()
    image, info = expand_code11(code11)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)

    below = below_a5_from_code0(CODE0_PATH.read_bytes()) if CODE0_PATH.is_file() else None
    hdr = info["header"]
    rem = info["src_remaining"]
    if rem == 0:
        term = "clean: terminator then 0 bytes of packed input left"
    else:
        term = f"UNCLEAN: terminator with {rem} packed bytes still unread"

    print(f"source {src} len={len(code11)}")
    print(f"seg header +0 u16be=${info['seg_header'][0]:04X} +2 u16be=${info['seg_header'][1]:04X}")
    print(f"header +{hdr['file']} (0x{hdr['file']:X}) raw={hdr['raw'].hex().upper()}")
    print(f"  dest_size={hdr['dest_size']} ($1DA8=7592) flag={hdr['flag']} unk6={hdr['unk6']}")
    print(f"  off_data={hdr['off_data']} packed_file=+{hdr['packed_file']}")
    print(f"  off_rel={hdr['off_rel']} reloc_file=+{hdr['reloc_file']} reloc_bytes={info['reloc_bytes']}")
    print(f"consumed={info['src_consumed']} packed_len={info['src_len']} remaining={rem}")
    print(f"emitted={len(image)} dest_high_water={info['dest_high_water']} ops={info['control_ops']}")
    print(f"termination: {term}")
    print(f"CODE 0 belowA5={below} image_len={len(image)} match={below == len(image)}")
    print(f"wrote {args.output} {len(image)} bytes")
    return 0 if rem == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
