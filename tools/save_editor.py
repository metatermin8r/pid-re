# -*- coding: utf-8 -*-
"""Inspect and edit Pathways Into Darkness 2.0 Saved Games files.

Player-region base B is found by scanning, not assumed. Relative field
offsets are the live island (dungeon, fixed-point X/Y, HP) plus the
inert integer mirrors (level, X, Y, facing) and inventory. They are
accepted only when a candidate B passes all six validation gates
against the v2.0 level JSON.

Usage:
  python tools/save_editor.py inspect <savefile>
  python tools/save_editor.py world <savefile> --level N [--fixed] [--centred]
  python tools/save_editor.py objects <savefile> --level N [--fixed] [--centred]
  python tools/save_editor.py catalog <savefile>
  python tools/save_editor.py blockmap <savefile>
  python tools/save_editor.py set-block <savefile> --index N -o <out>
      # writes table[9][0] at 0x06C2 (sink FROM -$1AD8). NOT +0x090C.
  python tools/save_editor.py set-dungeon <savefile> --level N -o <out>
      # writes player+0x54 at file B+0x0748 (load-path dungeon). NEVER in place.
  python tools/save_editor.py set-position <savefile> --x N --y N -o <out>
      # live X/Y at +0x074A / +0x074E (10-bit fixed). NOT the clock.
  python tools/save_editor.py set-position <savefile> --x N --y N --yaw 128 --hp 999 --maxhp 999 -o <out>
      # also write live facing at +0x0752 (512-unit circle) and HP.
  python tools/save_editor.py set-position <savefile> --arrival LEVEL -o <out>
      # dungeon + arrival cell-centre. NEVER in place.
  python tools/save_editor.py objects <savefile> --block N --level M [--fixed]
  python tools/save_editor.py warp <savefile> --level N --arrival -o <out>
      # +0x090C / +0x0918 / +0x091A are INERT (confirmed in game).
  python tools/save_editor.py warp <savefile> --x X --y Y -o <out>
  python tools/save_editor.py warp <savefile> --level N --arrival-from M -o <out>
  python tools/save_editor.py set <savefile> [--hp N] [--maxhp N] [--facing N] -o <out>
  python tools/save_editor.py item <savefile> --list [--base B]
  python tools/save_editor.py item <savefile> --slot N --value Q -o <out>
  python tools/save_editor.py give <savefile> --id N [--into SLOT] [--count N] -o <out>
  python tools/save_editor.py equip <savefile> --slot N -o <out>
  python tools/save_editor.py export-item-catalog
  python tools/save_editor.py export-objects
      # pristine object tables from dpin 128 into reference/export/objects_LNN.json
  python tools/save_editor.py verify <savefile>
  python tools/save_editor.py diff <a> <b>
  python tools/save_editor.py gui [savefile]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "reference" / "export"

# Relative offsets inside a player region. Not file offsets until B is found.
OFF_DUNGEON = 0x0748  # player+0x54 in the I/O blob (k*2876 + 0x0748)
OFF_X_FP = 0x074A  # live X, u32be 10-bit fixed. NOT a clock (disproven).
OFF_Y_FP = 0x074E  # live Y, u32be 10-bit fixed
OFF_U752 = 0x0752  # live facing / yaw; 512-unit binary angle (0..511)
OFF_HP = 0x0754
OFF_MAXHP = 0x0756
OFF_LEVEL = 0x090C
OFF_X = 0x0918
OFF_Y = 0x091A
OFF_FACING = 0x091C
# Player I/O blob starts at B+0x06F4 (A5 -$1A8A). mem+d = B+0x06F4+d.
# +0x0A00 is player+$30C — 48 bytes BEFORE the inventory array.
# The live tree is at player+$33C = B+0x0A30. There is no separate
# packed serialisation; the save is a raw dump of the A5 blob.
OFF_PLAYER = 0x06F4
OFF_POINTS = 0x06FE  # player+$0A, u16be
OFF_TREASURE = 0x0700  # player+$0C, u32be
OFF_READY_CRYSTAL = 0x0886  # player+$192
OFF_READY_WEAPON = 0x088C  # player+$198
OFF_SHOT_COUNTER = 0x088E  # player+$19A
OFF_INV_HEAD = 0x0A2E  # player+$33A, start slot (0 on captured saves)
OFF_INV = 0x0A30  # player+$33C, 256 x 8
INV_MAX = 256
SCAN_NEED = 0x0A08

GRID = 32
N_LEVELS = 25

# Per-level world-state blocks. CODE 2 @10328:
#   file_pos = table_word * $2398 + $774C   ($774C = 30540)
# dpin 128 writes 25 * 9112 bytes from dpin+2876 at this file position.
# Indices 25+ are per-named-save LIVE copies (one extra 9112 per name).
# The old 39392 window was 8852 bytes late (8852 = 16*553+4) and is how
# the object table appeared 4 bytes off. Do not use 39392.
WORLD_BASE = 30540
WORLD_STRIDE = 9112
WORLD_COUNT = 25
WORLD_BYTES = WORLD_COUNT * WORLD_STRIDE  # 227800
WORLD_END = WORLD_BASE + WORLD_BYTES  # 258340
# Aliases: older call sites used "template" for this region.
TEMPLATE_BASE = WORLD_BASE
TEMPLATE_STRIDE = WORLD_STRIDE
TEMPLATE_BYTES = WORLD_BYTES
TEMPLATE_END = WORLD_END

# -$1ADC handle is a 1780-byte copy of save[0:1780].
# +0x0000: 10 x 128-byte Pascal names; +0x0500: 10 x 25 u16be block indices.
BLOCKMAP_OFF = 0x0500
BLOCKMAP_SLOTS = 10
BLOCKMAP_COLS = 25
BLOCKMAP_ROW = 50
# Every CODE 2 caller of @10066/@10174 pushes slot 9 as $000A(A6).
# I/O therefore always reads word[0] of slot 9 = file +0x06C2.
IO_SLOT = 9
IO_COL = 0
IO_FILE_OFF = BLOCKMAP_OFF + IO_SLOT * BLOCKMAP_ROW + IO_COL * 2  # 0x06C2

OBJ_TABLE_OFF = 0x03D8
OBJ_COUNT = 500
OBJ_STRIDE = 16
LINK_FREE = 0xFFFE
LINK_END = 0xFFFF
FIXED_SHIFT = 10
FIXED_UNIT = 1 << FIXED_SHIFT  # 1024
FIXED_CENTER = 0x200

# World-block subtables (sentinel initialiser, JT 164, and every LEA).
WORLD_T0_COUNT_OFF = 0x0000
WORLD_T0_OFF = 0x0002
WORLD_T0_MAX = 60
WORLD_T0_REC = 8
WORLD_T1_COUNT_OFF = 0x01E2
WORLD_T1_OFF = 0x01E4
WORLD_T1_MAX = 30
WORLD_T1_REC = 4
WORLD_T2_OFF = 0x025C
WORLD_T2_MAX = 40
WORLD_T2_REC = 8
WORLD_T3_OFF = 0x039C
WORLD_T3_MAX = 15
WORLD_T3_REC = 4
WORLD_TRAILER_OFF = 0x2318
WORLD_TRAILER_LEN = 128

# Named-save title slots (Pascal strings). Observed, not a full struct claim.
NAME_SLOT = 128
NAME_SLOTS = 8
PLAYER_STRIDE = 2876  # confirmed: record k is at k*2876

KNOWN_FIELDS = (
    (OFF_DUNGEON, 2, "dungeon_load_path"),
    (OFF_X_FP, 4, "x_live"),
    (OFF_Y_FP, 4, "y_live"),
    (OFF_U752, 2, "unknown_0x0752"),
    (OFF_HP, 2, "hp"),
    (OFF_MAXHP, 2, "max_hp"),
    (OFF_LEVEL, 2, "level_INERT"),
    (OFF_X, 2, "x_INERT"),
    (OFF_Y, 2, "y_INERT"),
    (OFF_FACING, 2, "facing"),
    (OFF_POINTS, 2, "points"),
    (OFF_TREASURE, 4, "treasure"),
    (OFF_READY_CRYSTAL, 2, "ready_crystal"),
    (OFF_READY_WEAPON, 2, "ready_weapon"),
    (OFF_SHOT_COUNTER, 2, "shot_counter"),
    (OFF_INV_HEAD, 2, "inv_head"),
    (OFF_INV, 0, "inventory"),  # 256 x 8 starting at player+$33C
)


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def i32(data: bytes, off: int) -> int:
    return struct.unpack_from(">i", data, off)[0]


def put_u16(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into(">H", buf, off, value)


def put_u32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into(">I", buf, off, value)


def refuse_in_place(src: Path, dst: Path) -> None:
    if dst.resolve() == src.resolve():
        raise SystemExit("error: refuse to modify in place; -o must be a different path")


def require_u16(name: str, value: int) -> int:
    if value < 0 or value > 0xFFFF:
        raise SystemExit(f"error: {name}={value} does not fit u16be (0..65535); refused")
    return value


def require_u32(name: str, value: int) -> int:
    if value < 0 or value > 0xFFFFFFFF:
        raise SystemExit(f"error: {name}={value} does not fit u32be (0..4294967295); refused")
    return value


class LevelIndex:
    def __init__(self, export_dir: Path) -> None:
        self.export_dir = export_dir
        self.names: list[str] = []
        self.types: list[list[int]] = []
        self.type_names: list[list[str]] = []
        self.items: list[list[int]] = []
        self.arrivals: list[list[dict]] = []
        self.texture_resources: list[set[int]] = []
        for n in range(N_LEVELS):
            path = export_dir / f"L{n:02d}.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            types = [[-1] * GRID for _ in range(GRID)]
            tnames = [[""] * GRID for _ in range(GRID)]
            items = [[-1] * GRID for _ in range(GRID)]
            for s in doc["sectors"]:
                types[s["y"]][s["x"]] = s["type"]
                tnames[s["y"]][s["x"]] = s["type_name"]
                items[s["y"]][s["x"]] = int(s["item"])
            self.names.append(doc["name"])
            self.types.append(types)
            self.type_names.append(tnames)
            self.items.append(items)
            self.arrivals.append(list(doc.get("arrivals") or []))
            tex: set[int] = set()
            for t in doc.get("texture_list") or []:
                sid = t.get("shape_id")
                if sid is not None:
                    tex.add(int(sid))
            self.texture_resources.append(tex)

    def sector(self, level: int, x: int, y: int) -> tuple[int, str]:
        return self.types[level][y][x], self.type_names[level][y][x]

    def item_at(self, level: int, x: int, y: int) -> int:
        return self.items[level][y][x]

    def sectors_with_item(self, level: int) -> list[tuple[int, int, int, int, str]]:
        """(x, y, item, type, type_name) for every sector whose item != -1."""
        out: list[tuple[int, int, int, int, str]] = []
        for y in range(GRID):
            for x in range(GRID):
                item = self.items[level][y][x]
                if item != -1:
                    out.append(
                        (x, y, item, self.types[level][y][x], self.type_names[level][y][x])
                    )
        return out


def is_standable(sector_type: int) -> bool:
    return sector_type not in (0, 7)


def format_arrivals(levels: LevelIndex, level: int) -> list[str]:
    lines: list[str] = []
    for a in levels.arrivals[level]:
        x, y = int(a["x"]), int(a["y"])
        st, sn = levels.sector(level, x, y)
        lines.append(
            f"  arrival L{level} ({x},{y}) from_level={a.get('from_level')} "
            f"from_name={a.get('from_name')!r} change_type={a.get('change_type_name')} "
            f"list_index={a.get('list_index')} type={st} {sn} "
            f"standable={'yes' if is_standable(st) else 'no'}"
        )
    return lines


def select_standable_arrival(
    levels: LevelIndex, level: int, from_level: int | None = None
) -> dict:
    """First standable arrival; ties broken by lowest list_index.

    Does not special-case any level. Raises SystemExit if none qualify.
    """
    if not (0 <= level <= 24):
        raise SystemExit(f"error: --level {level} not in 0..24")
    pool = list(levels.arrivals[level])
    if from_level is not None:
        pool = [a for a in pool if int(a.get("from_level", -1)) == from_level]
    if not pool:
        listing = "\n".join(format_arrivals(levels, level)) or "  (none)"
        extra = f" from_level={from_level}" if from_level is not None else ""
        raise SystemExit(
            f"error: L{level} has no arrival{extra}\n{listing}"
        )
    standable: list[tuple[int, int, dict, int, str]] = []
    skipped = 0
    for i, a in enumerate(pool):
        x, y = int(a["x"]), int(a["y"])
        st, sn = levels.sector(level, x, y)
        if is_standable(st):
            idx = a.get("list_index")
            key = int(idx) if idx is not None else 10**9
            standable.append((key, i, a, st, sn))
        else:
            skipped += 1
    if not standable:
        listing = "\n".join(format_arrivals(levels, level)) or "  (none)"
        extra = f" from_level={from_level}" if from_level is not None else ""
        raise SystemExit(
            f"error: L{level} has no standable arrival{extra}\n{listing}"
        )
    standable.sort(key=lambda t: (t[0], t[1]))
    _key, _i, chosen, st, sn = standable[0]
    x, y = int(chosen["x"]), int(chosen["y"])
    print(
        f"arrival_used L{level} ({x},{y}) type={st} {sn} "
        f"from_level={chosen.get('from_level')} from_name={chosen.get('from_name')!r} "
        f"change_type={chosen.get('change_type_name')} "
        f"list_index={chosen.get('list_index')} "
        f"skipped_unstandable={skipped} other_standable={len(standable) - 1}"
    )
    return chosen


def max_block_index(file_len: int) -> int:
    if file_len < WORLD_BASE + WORLD_STRIDE:
        return -1
    return (file_len - WORLD_BASE) // WORLD_STRIDE - 1


def world_span_end(file_len: int) -> int:
    n = max_block_index(file_len) + 1
    if n <= 0:
        return WORLD_BASE
    return WORLD_BASE + n * WORLD_STRIDE


def in_world_region(offset: int) -> bool:
    # Home blocks [30540, 258340) plus any extra live 9112-byte copies.
    return offset >= WORLD_BASE


def in_template_region(offset: int) -> bool:
    """Alias: the 9,112-byte region is live world state, not templates."""
    return in_world_region(offset)


def gate_flags(data: bytes, base: int, levels: LevelIndex) -> tuple[list[bool], dict]:
    """Return (6 bools, decoded fields). Decoded values are raw even on fail."""
    n = len(data)
    decoded = {
        "base": base,
        "level": None,
        "x": None,
        "y": None,
        "type": None,
        "type_name": None,
        "hp": None,
        "max_hp": None,
        "x_fp": None,
        "y_fp": None,
        "x_live": None,
        "y_live": None,
        "dungeon": None,
        "u752": None,
        "facing": None,
    }
    flags = [False] * 6
    if base < 0 or base + SCAN_NEED > n:
        return flags, decoded

    level = u16(data, base + OFF_LEVEL)
    x = u16(data, base + OFF_X)
    y = u16(data, base + OFF_Y)
    hp = u16(data, base + OFF_HP)
    max_hp = u16(data, base + OFF_MAXHP)
    x_fp = u32(data, base + OFF_X_FP)
    y_fp = u32(data, base + OFF_Y_FP)
    x_live = sector_of(x_fp)
    y_live = sector_of(y_fp)
    decoded.update(
        level=level,
        x=x,
        y=y,
        hp=hp,
        max_hp=max_hp,
        x_fp=x_fp,
        y_fp=y_fp,
        x_live=x_live,
        y_live=y_live,
        dungeon=u16(data, base + OFF_DUNGEON),
        u752=u16(data, base + OFF_U752),
        facing=u16(data, base + OFF_FACING),
    )
    flags[0] = 0 <= level <= 24
    flags[1] = 0 <= x <= 31
    flags[2] = 0 <= y <= 31
    if flags[0] and flags[1] and flags[2]:
        st, sn = levels.sector(level, x, y)
        decoded["type"] = st
        decoded["type_name"] = sn
        flags[3] = st not in (0, 7)
    flags[4] = 0 < hp <= max_hp < 10000
    flags[5] = 0 <= x_live <= 31 and 0 <= y_live <= 31
    return flags, decoded


def scan_bases(data: bytes, levels: LevelIndex) -> dict:
    n = len(data)
    last = n - SCAN_NEED
    out = {
        "size": n,
        "too_small": last < 0,
        "n_candidates": 0,
        "gate_pass": [0] * 6,
        "n_gates_hist": [0] * 7,
        "all6": [],
        "best10": [],
    }
    if last < 0:
        return out
    out["n_candidates"] = last // 2 + 1
    best: list[tuple] = []
    for base in range(0, last + 1, 2):
        flags, decoded = gate_flags(data, base, levels)
        for i, ok in enumerate(flags):
            if ok:
                out["gate_pass"][i] += 1
        score = sum(flags)
        out["n_gates_hist"][score] += 1
        rec = (score, -base, base, tuple(flags), decoded)
        if score == 6:
            out["all6"].append(decoded)
        if len(best) < 10:
            best.append(rec)
            best.sort(reverse=True)
        elif rec > best[-1]:
            best[-1] = rec
            best.sort(reverse=True)
    out["best10"] = best
    return out


def read_inventory(
    data: bytes, base: int, limit: int = INV_MAX
) -> list[tuple[int, int, int, int]]:
    """Records at B+0x0A30 until id=$FFFF. Does not include the terminator."""
    recs: list[tuple[int, int, int, int]] = []
    off = base + OFF_INV
    for _ in range(limit):
        if off + 8 > len(data):
            break
        rec = struct.unpack_from(">4H", data, off)
        if rec[0] == 0xFFFF:
            break
        recs.append(rec)
        off += 8
    return recs


def read_inventory_slot(data: bytes, base: int, slot: int) -> tuple[int, int, int, int]:
    if slot < 0 or slot >= INV_MAX:
        raise EditRefused(f"slot {slot} not in 0..{INV_MAX - 1}")
    off = base + OFF_INV + slot * 8
    if off + 8 > len(data):
        raise EditRefused(f"slot {slot} is past the end of the file")
    return struct.unpack_from(">4H", data, off)


def inventory_file_off(base: int, slot: int, word: int = 0) -> int:
    return base + OFF_INV + slot * 8 + word * 2


# ---------------------------------------------------------------------------
# Item catalog (A5 -$14D6) and inventory tree
# ---------------------------------------------------------------------------

CODE_DIR = ROOT / "reference" / "docs" / "code"
APP_RSRC = ROOT / "data" / "hfs" / "Pathways_1995" / "Pathways Into Darkness.rsrc"
ITEM_CATALOG_JSON = EXPORT_DIR / "item_catalog.json"
CATALOG_A5 = 0x14D6
CATALOG_N = 71
DATAINIT_HDR = 0x1B2  # CODE 11 +434; compressed payload at +454
CLASS_POTION = 2
CLASS_WEAPON = 3
CLASS_CRYSTAL = 4
CEDAR_BOX_ID = 8
YELLOW_CRYSTAL_ID = 64
W7_ANY = 0xFFFF
W7_AK_MAGS = 0xFFFA  # ids 53-55
W7_40MM = 0xFFFB  # ids 58-60

_ITEM_CATALOG: dict | None = None


class _PackStream:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.i = 0

    def u8(self) -> int:
        if self.i >= len(self.data):
            raise EOFError(f"DATAINIT src overrun at {self.i}")
        b = self.data[self.i]
        self.i += 1
        return b


def _datainit_get_rl(s: _PackStream) -> tuple[int, int | None]:
    d0 = s.u8()
    if d0 < 0x80:
        return d0, None
    if (d0 & 0x40) == 0:
        return ((d0 & 0x3F) << 8) | s.u8(), None
    if (d0 & 0x20) == 0:
        return ((d0 & 0x1F) << 16) | (s.u8() << 8) | s.u8(), None
    if (d0 & 0x10) == 0:
        v = (s.u8() << 24) | (s.u8() << 16) | (s.u8() << 8) | s.u8()
        return v, None
    first, _ = _datainit_get_rl(s)
    second, _ = _datainit_get_rl(s)
    return first, second


def datainit_uncompress(src: bytes, dest_size: int) -> bytes:
    """Think C _DATAINIT decompressor (CODE 11 @4 / JT 305)."""
    s = _PackStream(src)
    dest = bytearray(dest_size)
    a1 = 0
    while True:
        d3 = 1
        b = s.u8()
        d1 = b & 0x0F
        d2 = b & 0xF0
        extra_d3 = None
        if d1 == 0:
            d1, extra_d3 = _datainit_get_rl(s)
            if extra_d3 is not None:
                d3 = extra_d3
            if d1 == 0:
                break
        else:
            d1 = d1 * 2
        if d2 == 0:
            d2, extra_d3 = _datainit_get_rl(s)
            if extra_d3 is not None:
                d3 = extra_d3
        else:
            d2 >>= 3
        while True:
            a1 += d2
            if a1 + d1 > dest_size:
                raise ValueError(f"DATAINIT dest overrun a1={a1} d1={d1} size={dest_size}")
            for _ in range(d1):
                dest[a1] = s.u8()
                a1 += 1
            d3 -= 1
            if d3 == 0:
                break
    return bytes(dest)


def _load_str_list(rsrc_id: int) -> list[str]:
    if not APP_RSRC.is_file():
        return []
    from mac_containers import resources_of_type
    from mac_text import parse_str_list

    payload = resources_of_type(APP_RSRC, b"STR#").get(rsrc_id)
    if not payload:
        return []
    return parse_str_list(payload) or []


def load_item_catalog(*, write_json: bool = True) -> dict:
    """71x16 catalog at A5 -$14D6, plus the 15-word Cedar admit list at -$1066."""
    global _ITEM_CATALOG
    if _ITEM_CATALOG is not None:
        return _ITEM_CATALOG

    code11 = (CODE_DIR / "CODE_11.bin").read_bytes()
    hdr = DATAINIT_HDR
    dest_size = struct.unpack(">I", code11[hdr : hdr + 4])[0]
    off_data = struct.unpack(">I", code11[hdr + 8 : hdr + 12])[0]
    off_rel = struct.unpack(">I", code11[hdr + 12 : hdr + 16])[0]
    packed_off = hdr + off_data
    src = code11[packed_off : hdr + off_rel]
    world = datainit_uncompress(src, dest_size)
    cat_off = dest_size - CATALOG_A5
    raw = world[cat_off : cat_off + CATALOG_N * 16]
    if len(raw) != CATALOG_N * 16:
        raise SystemExit(f"error: catalog slice len={len(raw)} expected {CATALOG_N * 16}")
    cedar_off = dest_size - 0x1066
    cedar_ids = list(struct.unpack(">15H", world[cedar_off : cedar_off + 30]))

    names = _load_str_list(2000)
    examine = _load_str_list(1001)
    entries = []
    for i in range(CATALOG_N):
        words = list(struct.unpack_from(">8H", raw, i * 16))
        w3 = words[3]
        entries.append(
            {
                "id": i,
                "name": names[i] if i < len(names) else "",
                "examine": examine[i] if i < len(examine) else "",
                "words": words,
                "w0": words[0],
                "w1": words[1],
                "w2": words[2],
                "w3": w3,
                "w4": words[4],
                "w5": words[5],
                "w6": words[6],
                "w7": words[7],
                "sprite_s1": words[0] & 0x7F,
                "weight_units": w3,
                "weight_kg": round(w3 / 28.0, 4),
            }
        )
    ammo_ids: set[int] = set()
    for e in entries:
        w7 = e["w7"]
        if e["w6"] > 0:
            if w7 < CATALOG_N:
                ammo_ids.add(w7)
            elif w7 == W7_AK_MAGS:
                ammo_ids.update((53, 54, 55))
            elif w7 == W7_40MM:
                ammo_ids.update((58, 59, 60))
    doc = {
        "source": (
            f"CODE 11 header +{hdr} (0x{hdr:X}), compressed payload +{packed_off} "
            f"(CODE 11 +454), dest_size={dest_size}, catalog at dest-{CATALOG_A5:#x}"
        ),
        "cedar_admit_ids": cedar_ids,
        "ammo_ids": sorted(ammo_ids),
        "entries": entries,
    }
    if write_json:
        ITEM_CATALOG_JSON.parent.mkdir(parents=True, exist_ok=True)
        ITEM_CATALOG_JSON.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {ITEM_CATALOG_JSON} entries={len(entries)}")
    _ITEM_CATALOG = doc
    return doc


def catalog_entry(item_id: int) -> dict | None:
    cat = load_item_catalog()
    if 0 <= item_id < len(cat["entries"]):
        return cat["entries"][item_id]
    return None


def item_name(item_id: int) -> str:
    if item_id == 0xFFFF:
        return "(end)"
    e = catalog_entry(item_id)
    if e and e["name"]:
        return e["name"]
    return f"id:{item_id}"


def w7_admits(w7: int, item_id: int) -> bool:
    if w7 == W7_ANY:
        return True
    if w7 == W7_40MM:
        return 58 <= item_id <= 60
    if w7 == W7_AK_MAGS:
        return 53 <= item_id <= 55
    return w7 == item_id


def interpret_word2(item_id: int, value: int) -> str:
    e = catalog_entry(item_id)
    if e is None:
        return f"value={value}"
    if e["w6"] > 0:
        if value == 0xFFFF:
            return "child_slot=FFFF (empty)"
        return f"child_slot={value}"
    if e["w1"] == CLASS_CRYSTAL:
        return f"charge={value}"
    cat = load_item_catalog()
    if item_id in cat["ammo_ids"]:
        return f"rounds={value}"
    return f"value={value} (overloaded)"


def children_of(recs: list[tuple[int, int, int, int]], parent_slot: int) -> list[int]:
    if parent_slot < 0 or parent_slot >= len(recs):
        return []
    first = recs[parent_slot][2]
    out: list[int] = []
    seen: set[int] = set()
    cur = first
    while cur != 0xFFFF:
        if cur in seen:
            break
        if cur < 0 or cur >= len(recs):
            break
        seen.add(cur)
        out.append(cur)
        cur = recs[cur][3]
    return out


def sibling_chain(recs: list[tuple[int, int, int, int]], start: int) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    cur = start
    while cur != 0xFFFF:
        if cur in seen or cur < 0 or cur >= len(recs):
            break
        seen.add(cur)
        out.append(cur)
        cur = recs[cur][3]
    return out


def container_fill(recs: list[tuple[int, int, int, int]], parent_slot: int) -> int:
    total = 0
    for slot in children_of(recs, parent_slot):
        e = catalog_entry(recs[slot][0])
        if e:
            total += e["w4"]
    return total


def first_free_slot(data: bytes, base: int) -> int:
    for slot in range(INV_MAX):
        rec = read_inventory_slot(data, base, slot)
        if rec[0] == 0xFFFF:
            return slot
    return -1


def write_inv_record(
    data: bytes,
    buf: bytearray,
    base: int,
    slot: int,
    rec: tuple[int, int, int, int],
    changes: list[tuple[int, int, int, str]],
) -> None:
    off = inventory_file_off(base, slot)
    names = ("id", "state", "value", "next_sibling")
    for i, (field, value) in enumerate(zip(names, rec)):
        write_u16_field(data, buf, off + i * 2, value, f"inv[{slot}].{field}", changes)


def print_inventory_tree(data: bytes, base: int, prefix: str = "") -> None:
    recs = read_inventory(data, base)
    head = u16(data, base + OFF_INV_HEAD)
    cat = load_item_catalog()
    print(
        f"{prefix}inventory B+0x0A30 (player+$33C) n={len(recs)} "
        f"head(+0x0A2E/+$33A)={head} "
        f"terminator_slot={len(recs)}"
    )
    if recs:
        term_off = inventory_file_off(base, len(recs))
        term = struct.unpack_from(">4H", data, term_off)
        print(
            f"{prefix}  terminator file_off=0x{term_off:X} "
            f"words=({' '.join(f'{w:04X}' for w in term)}) "
            f"(first word FFFF; other six bytes are leftover, not a record)"
        )
    child_of: set[int] = set()
    for i, rec in enumerate(recs):
        e = catalog_entry(rec[0])
        if e and e["w6"] > 0:
            child_of.update(children_of(recs, i))
    roots = sibling_chain(recs, head if head != 0xFFFF and head < len(recs) else 0)

    def emit(slot: int, indent: int, seen: set[int]) -> None:
        if slot < 0 or slot >= len(recs):
            print(f"{prefix}  {'  ' * indent}slot={slot} OUT_OF_RANGE")
            return
        if slot in seen:
            print(f"{prefix}  {'  ' * indent}slot={slot} CYCLE")
            return
        seen.add(slot)
        rec = recs[slot]
        e = catalog_entry(rec[0])
        w3 = e["w3"] if e else 0
        kg = w3 / 28.0
        role = interpret_word2(rec[0], rec[2])
        print(
            f"{prefix}  {'  ' * indent}slot={slot} {item_name(rec[0])} "
            f"id={rec[0]} state={rec[1]} {role} "
            f"next_sibling={rec[3] if rec[3] != 0xFFFF else 'FFFF'} "
            f"w3={w3} kg={kg:.2f} "
            f"raw={data[inventory_file_off(base, slot):inventory_file_off(base, slot) + 8].hex()}"
        )
        if e and e["w6"] > 0:
            for child in children_of(recs, slot):
                emit(child, indent + 1, seen)

    seen: set[int] = set()
    for slot in roots:
        emit(slot, 0, seen)
    orphans = [i for i in range(len(recs)) if i not in seen]
    if orphans:
        print(f"{prefix}  orphans_not_reachable_from_head={orphans}")
        for slot in orphans:
            emit(slot, 0, seen)

    sum_w3 = sum((catalog_entry(r[0]) or {"w3": 0})["w3"] for r in recs)
    print(
        f"{prefix}  total_weight sum(w3)={sum_w3} / 28 = {sum_w3 / 28.0:.2f} kg "
        f"(JT 217 FODIV #$1C). UI string is STR# 2016."
    )
    print(
        f"{prefix}  points(+0x06FE/+$0A)={u16(data, base + OFF_POINTS)} "
        f"treasure(+0x0700/+$0C)={u32(data, base + OFF_TREASURE)} "
        f"ready_crystal(+0x0886/+$192)={u16(data, base + OFF_READY_CRYSTAL)} "
        f"ready_weapon(+0x088C/+$198)={u16(data, base + OFF_READY_WEAPON)} "
        f"shot_counter(+0x088E/+$19A)={u16(data, base + OFF_SHOT_COUNTER)}"
    )
    _ = cat


def apply_wipe_inventory(
    data: bytes,
    buf: bytearray,
    base: int,
    changes: list[tuple[int, int, int, str]],
) -> None:
    empty = (0xFFFF, 0, 0, 0xFFFF)
    for slot in range(INV_MAX):
        write_inv_record(data, buf, base, slot, empty, changes)
    write_u16_field(data, buf, base + OFF_INV_HEAD, 0xFFFF, "inv_head", changes)


def apply_give(
    data: bytes,
    decoded: dict,
    item_id: int,
    *,
    into: int | None = None,
    count: int | None = None,
    state: int = 0,
) -> tuple[bytearray, list[tuple[int, int, int, str]], dict, list[str]]:
    """Append one inventory record. --into links it as a child."""
    base = decoded["base"]
    if in_world_region(base):
        raise EditRefused(f"B={base} is inside the world-state region; refused")
    e = catalog_entry(item_id)
    if e is None:
        raise EditRefused(f"id={item_id} is not in the 71-entry catalog")
    if item_id < 0 or item_id > 0xFFFE:
        raise EditRefused(f"id={item_id} does not fit")

    buf = bytearray(data)
    # Work against the buffer so sequential gives in one process see prior writes.
    work = bytes(buf)
    recs = read_inventory(work, base)
    slot = first_free_slot(work, base)
    if slot < 0:
        raise EditRefused(f"inventory is full ({INV_MAX} slots)")

    if e["w6"] > 0:
        value = 0xFFFF
    elif count is not None:
        value = count
    else:
        value = 0
    if count is not None:
        if count < 0 or count > 0xFFFF:
            raise EditRefused(f"--count {count} does not fit u16be")
        if e["w6"] == 0:
            value = count

    new_rec = (item_id, state, value, 0xFFFF)

    changes: list[tuple[int, int, int, str]] = []
    if into is not None:
        if into < 0 or into >= len(recs):
            raise EditRefused(f"--into {into} is not an occupied slot (n={len(recs)})")
        parent = recs[into]
        pe = catalog_entry(parent[0])
        if pe is None or pe["w6"] == 0:
            raise EditRefused(
                f"--into {into} ({item_name(parent[0])}) catalog w6=0; not a container"
            )
        if not w7_admits(pe["w7"], item_id):
            raise EditRefused(
                f"--into {into} w7={pe['w7']:04X} does not admit id={item_id} "
                f"({item_name(item_id)})"
            )
        if parent[0] == CEDAR_BOX_ID:
            admit = load_item_catalog()["cedar_admit_ids"]
            if parent[2] != 0xFFFF:
                raise EditRefused(
                    f"Cedar Box slot {into} is not empty (word2={parent[2]}); "
                    f"CODE 6 @616 refuses a second child"
                )
            if item_id not in admit:
                raise EditRefused(
                    f"id={item_id} ({item_name(item_id)}) is not in the Cedar "
                    f"admit list at A5 -$1066 ({admit})"
                )
        fill = container_fill(recs, into)
        new_fill = fill + e["w4"]
        if pe["w6"] < new_fill:
            raise EditRefused(
                f"container fill {fill} + candidate w4={e['w4']} = {new_fill} "
                f"exceeds parent w6={pe['w6']} (CODE 6 @616 BLT)"
            )
        kids = children_of(recs, into)
        if not kids:
            parent_rec = (parent[0], parent[1], slot, parent[3])
            write_inv_record(data, buf, base, into, parent_rec, changes)
        else:
            last = kids[-1]
            last_rec = recs[last]
            write_inv_record(
                data, buf, base, last, (last_rec[0], last_rec[1], last_rec[2], slot), changes
            )
        write_inv_record(data, buf, base, slot, new_rec, changes)
    else:
        head = u16(work, base + OFF_INV_HEAD)
        if head == 0xFFFF or not recs:
            write_u16_field(data, buf, base + OFF_INV_HEAD, slot, "inv_head", changes)
        else:
            chain = sibling_chain(recs, head if head < len(recs) else 0)
            if not chain:
                write_u16_field(data, buf, base + OFF_INV_HEAD, slot, "inv_head", changes)
            else:
                last = chain[-1]
                last_rec = recs[last]
                write_inv_record(
                    data,
                    buf,
                    base,
                    last,
                    (last_rec[0], last_rec[1], last_rec[2], slot),
                    changes,
                )
        write_inv_record(data, buf, base, slot, new_rec, changes)

    if slot + 1 < INV_MAX:
        nxt = read_inventory_slot(bytes(buf), base, slot + 1)
        if nxt[0] != 0xFFFF:
            write_u16_field(
                data, buf, inventory_file_off(base, slot + 1), 0xFFFF, f"inv[{slot + 1}].id", changes
            )

    print(
        f"give slot={slot} id={item_id} {item_name(item_id)} "
        f"state={state} value={value} into={into} "
        f"w3={e['w3']} kg={e['w3'] / 28.0:.2f} w4={e['w4']} w6={e['w6']}"
    )
    return buf, changes, {}, []


def apply_equip(
    data: bytes,
    decoded: dict,
    slot: int,
) -> tuple[bytearray, list[tuple[int, int, int, str]], dict, list[str]]:
    base = decoded["base"]
    if in_world_region(base):
        raise EditRefused(f"B={base} is inside the world-state region; refused")
    recs = read_inventory(data, base)
    if slot < 0 or slot >= len(recs):
        raise EditRefused(f"--slot {slot} is not an occupied slot (n={len(recs)})")
    rec = recs[slot]
    e = catalog_entry(rec[0])
    if e is None:
        raise EditRefused(f"slot {slot} id={rec[0]} has no catalog entry")
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    if e["w1"] == CLASS_CRYSTAL:
        write_u16_field(data, buf, base + OFF_READY_CRYSTAL, slot, "ready_crystal", changes)
        print(f"equip crystal slot={slot} id={rec[0]} {item_name(rec[0])} -> player+$192")
    elif e["w1"] == CLASS_WEAPON:
        write_u16_field(data, buf, base + OFF_READY_WEAPON, slot, "ready_weapon", changes)
        print(f"equip weapon slot={slot} id={rec[0]} {item_name(rec[0])} -> player+$198")
    else:
        raise EditRefused(
            f"slot {slot} {item_name(rec[0])} class w1={e['w1']}; "
            f"equip needs class 3 (weapon) or 4 (crystal)"
        )
    if rec[1] != 1:
        write_u16_field(
            data, buf, inventory_file_off(base, slot, 1), 1, f"inv[{slot}].state", changes
        )
    return buf, changes, {}, []


def apply_set_inventory(
    data: bytes,
    decoded: dict,
    records: list[tuple[int, int, int, int]],
    *,
    head: int = 0,
) -> tuple[bytearray, list[tuple[int, int, int, str]], dict, list[str]]:
    """Replace the tree. `records[i]` becomes slot i. Refuses a full tree."""
    base = decoded["base"]
    if in_world_region(base):
        raise EditRefused(f"B={base} is inside the world-state region; refused")
    if len(records) > INV_MAX:
        raise EditRefused(f"inventory would have {len(records)} records; max {INV_MAX}")
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    old_n = len(read_inventory(data, base))
    limit = max(old_n, len(records)) + 1
    if limit > INV_MAX:
        limit = INV_MAX
    empty = (0xFFFF, 0, 0, 0xFFFF)
    for slot in range(limit):
        rec = records[slot] if slot < len(records) else empty
        write_inv_record(data, buf, base, slot, rec, changes)
    write_u16_field(
        data, buf, base + OFF_INV_HEAD, 0xFFFF if not records else head, "inv_head", changes
    )
    return buf, changes, {}, []


def pascal_name(data: bytes, off: int) -> str | None:
    if off >= len(data):
        return None
    nlen = data[off]
    if nlen == 0 or nlen > 63:
        return None
    if off + 1 + nlen > len(data):
        return None
    raw = data[off + 1 : off + 1 + nlen]
    return raw.decode("mac_roman", errors="replace")


def list_save_names(data: bytes) -> list[tuple[int, str]]:
    names: list[tuple[int, str]] = []
    for i in range(NAME_SLOTS):
        off = i * NAME_SLOT
        name = pascal_name(data, off)
        if name:
            names.append((off, name))
    return names


def sidecar_report(path: Path) -> list[str]:
    lines: list[str] = []
    local = path.parent / ("._" + path.name)
    if local.exists():
        lines.append(f"ntfs_sidecar path={local} size={local.stat().st_size}")
    else:
        lines.append("ntfs_sidecar=ABSENT")
    for zpath in sorted(path.parent.glob("*.zip")):
        # Only the zip that wraps this exact file, not every zip in the folder.
        if zpath.stem != path.name and zpath.name != path.name + ".zip":
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                for name in zf.namelist():
                    if "._" not in Path(name).name:
                        continue
                    info = zf.getinfo(name)
                    raw = zf.read(name)
                    magic = raw[:4].hex() if raw else ""
                    lines.append(
                        f"zip_sidecar zip={zpath.name} entry={name} "
                        f"size={info.file_size} magic={magic}"
                    )
        except (OSError, zipfile.BadZipFile) as exc:
            lines.append(f"zip_sidecar zip={zpath.name} error={exc}")
    return lines


def field_name_at(file_off: int, bases: list[int]) -> str:
    labels: list[str] = []
    if BLOCKMAP_OFF <= file_off < BLOCKMAP_OFF + BLOCKMAP_SLOTS * BLOCKMAP_ROW:
        rel = file_off - BLOCKMAP_OFF
        slot = rel // BLOCKMAP_ROW
        col = (rel % BLOCKMAP_ROW) // 2
        tag = "block_index_authority_UNTESTED" if file_off == IO_FILE_OFF else "blockmap"
        labels.append(f"{tag}[{slot}][{col}]")
    if in_world_region(file_off):
        block = (file_off - WORLD_BASE) // WORLD_STRIDE
        labels.append(f"world_block_{block}")
    for base in bases:
        rel = file_off - base
        if rel < 0:
            continue
        if OFF_INV <= rel < OFF_INV + INV_MAX * 8:
            slot = (rel - OFF_INV) // 8
            within = (rel - OFF_INV) % 8
            field = ("id", "state", "value", "next_sibling")[within // 2]
            labels.append(f"B{base}+inv[{slot}].{field}")
            continue
        for off, size, name in KNOWN_FIELDS:
            if name == "inventory":
                continue
            if off <= rel < off + size:
                labels.append(f"B{base}+{name}")
                break
    return ",".join(labels) if labels else "-"


def select_targets(scan: dict, base_arg: int | None) -> list[dict]:
    live = [d for d in scan["all6"] if not in_world_region(d["base"])]
    ghost = [d for d in scan["all6"] if in_world_region(d["base"])]
    print(f"all6_count={len(scan['all6'])} pre_world={len(live)} in_world={len(ghost)}")
    for d in scan["all6"]:
        print(
            f"  hit B={d['base']} (0x{d['base']:X}) in_world={in_world_region(d['base'])} "
            f"L{d['level']} ({d['x']},{d['y']})"
        )
    if base_arg is not None:
        chosen = [d for d in scan["all6"] if d["base"] == base_arg]
        if not chosen:
            raise SystemExit(f"error: --base {base_arg} did not pass all 6 gates")
        if in_world_region(base_arg):
            raise SystemExit(
                f"error: --base {base_arg} is inside the per-level world-state region "
                f">={WORLD_BASE}; refuse to write a world block as a player base"
            )
        return chosen
    if len(live) == 0:
        raise SystemExit("error: no pre-world-region base passed all 6 gates")
    if len(live) > 1:
        listing = " ".join(f"B={d['base']}" for d in live)
        raise SystemExit(
            f"error: {len(live)} pre-world-region bases passed the gate ({listing}); "
            f"pass --base B to choose one. Named saves in one file are different games."
        )
    return live


def record_bytes(
    data: bytes,
    buf: bytearray,
    off: int,
    n: int,
    name: str,
    changes: list[tuple[int, int, int, str]],
) -> None:
    for i in range(n):
        if data[off + i] == buf[off + i]:
            continue
        print(
            f"change_byte {name} file_off={off + i} (0x{off + i:X}) "
            f"old={data[off + i]:02X} new={buf[off + i]:02X}"
        )
        changes.append((off + i, data[off + i], buf[off + i], name))


def write_u16_field(
    data: bytes,
    buf: bytearray,
    off: int,
    new: int,
    name: str,
    changes: list[tuple[int, int, int, str]],
) -> None:
    old = u16(data, off)
    if old == new:
        print(f"unchanged {name} @{off} (0x{off:X}) = {old}")
        return
    put_u16(buf, off, new)
    print(
        f"change {name} file_off={off} (0x{off:X}) "
        f"old_u16={old} new_u16={new} "
        f"old_bytes={data[off]:02X} {data[off + 1]:02X} "
        f"new_bytes={buf[off]:02X} {buf[off + 1]:02X}"
    )
    record_bytes(data, buf, off, 2, name, changes)


def write_u32_field(
    data: bytes,
    buf: bytearray,
    off: int,
    new: int,
    name: str,
    changes: list[tuple[int, int, int, str]],
) -> None:
    old = u32(data, off)
    if old == new:
        print(f"unchanged {name} @{off} (0x{off:X}) = {old}")
        return
    put_u32(buf, off, new)
    print(
        f"change {name} file_off={off} (0x{off:X}) "
        f"old_u32={old} new_u32={new} "
        f"old_bytes={' '.join(f'{data[off + i]:02X}' for i in range(4))} "
        f"new_bytes={' '.join(f'{buf[off + i]:02X}' for i in range(4))}"
    )
    record_bytes(data, buf, off, 4, name, changes)


def commit_output(
    out_path: Path,
    data: bytes,
    buf: bytearray,
    targets: list[dict],
    levels: LevelIndex,
    changes: list[tuple[int, int, int, str]],
    *,
    allow_overheal: bool = False,
    expect: dict | None = None,
    dry_run: bool = False,
) -> int:
    out_bytes = bytes(buf)
    out_scan = scan_bases(out_bytes, levels)
    for decoded in targets:
        flags, after = gate_flags(out_bytes, decoded["base"], levels)
        failed = [i + 1 for i, ok in enumerate(flags) if not ok]
        overheal_only = (
            allow_overheal
            and failed == [5]
            and after["hp"] is not None
            and after["max_hp"] is not None
            and after["hp"] > after["max_hp"]
            and after["max_hp"] < 10000
            and after["hp"] > 0
        )
        if overheal_only:
            print(
                f"WARNING: output B={decoded['base']} fails G5 "
                f"(hp={after['hp']} > max_hp={after['max_hp']}); "
                f"writing anyway because --allow-overheal. "
                f"Game behaviour with cur > max is UNTESTED."
            )
        elif not all(flags):
            raise SystemExit(
                f"error: output fails gate at B={decoded['base']} failed={failed}; not writing"
            )
        if expect is not None:
            for key, want in expect.items():
                if after.get(key) != want:
                    raise SystemExit(
                        f"error: output B={decoded['base']} decoded {key}="
                        f"{after.get(key)} != requested {want}; not writing"
                    )
    if not out_scan["all6"] and not allow_overheal:
        raise SystemExit("error: output has zero all-6 bases; not writing")
    if dry_run:
        print(f"DRY-RUN would write {out_path} bytes={len(out_bytes)} changes={len(changes)}")
        print("DRY-RUN no write")
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)
    print(f"wrote {out_path} bytes={len(out_bytes)} changes={len(changes)}")
    print(f"WROTE {out_path}")
    print(
        "WARNING: output is unverified until loaded in Infinite Mac. "
        "No checksum was computed or updated; whether saves carry one is unknown."
    )
    return 0


class EditRefused(Exception):
    """A write was refused. Message is safe to show in a UI."""


def apply_player_edits(
    data: bytes,
    decoded: dict,
    levels: LevelIndex,
    *,
    hp: int | None = None,
    max_hp: int | None = None,
    facing: int | None = None,
    yaw: int | None = None,
    level: int | None = None,
    x: int | None = None,
    y: int | None = None,
    item_qtys: dict[int, int] | None = None,
    points: int | None = None,
    treasure: int | None = None,
    allow_overheal: bool = False,
) -> tuple[bytearray, list[tuple[int, int, int, str]], dict, list[str]]:
    """Apply field edits to one live player base. Raises EditRefused."""
    base = decoded["base"]
    if in_world_region(base):
        raise EditRefused(
            f"B={base} is inside the per-level world-state region "
            f">={WORLD_BASE}; refuse to write a world block as a player base"
        )

    def check_u16(name: str, value: int) -> int:
        if value < 0 or value > 0xFFFF:
            raise EditRefused(f"{name}={value} does not fit u16be (0..65535)")
        return value

    warnings: list[str] = []
    new_hp = decoded["hp"] if hp is None else check_u16("hp", hp)
    new_max = decoded["max_hp"] if max_hp is None else check_u16("maxhp", max_hp)
    if new_hp > new_max and not allow_overheal:
        raise EditRefused(
            f"hp={new_hp} exceeds maxhp={new_max}; "
            f"enable Allow overheal to write anyway (game behaviour UNTESTED)"
        )
    if new_hp > new_max and allow_overheal:
        warnings.append(
            f"writing hp={new_hp} > maxhp={new_max}. "
            f"Game behaviour with cur > max is UNTESTED."
        )

    if facing is not None:
        check_u16("facing", facing)
    if yaw is not None:
        check_u16("yaw", yaw)

    new_level = decoded["level"] if level is None else level
    new_x = decoded["x"] if x is None else x
    new_y = decoded["y"] if y is None else y
    if level is not None or x is not None or y is not None:
        if not (0 <= new_level <= 24):
            raise EditRefused(f"level={new_level} not in 0..24")
        if not (0 <= new_x <= 31 and 0 <= new_y <= 31):
            raise EditRefused(f"x/y out of 0..31 ({new_x},{new_y})")
        st, sn = levels.sector(new_level, new_x, new_y)
        if st in (0, 7):
            raise EditRefused(
                f"refuse warp to L{new_level} ({new_x},{new_y}) type={st} {sn} "
                f"(not standable: Void or Pillar)"
            )

    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    expect: dict = {}

    if hp is not None or max_hp is not None:
        print(
            "hp_copies=1 write_only=+0x0754/+0x0756 "
            "(Task A: no second copy in all 9 records)"
        )
    if hp is not None:
        write_u16_field(data, buf, base + OFF_HP, new_hp, "hp", changes)
        expect["hp"] = new_hp
    if max_hp is not None:
        write_u16_field(data, buf, base + OFF_MAXHP, new_max, "max_hp", changes)
        expect["max_hp"] = new_max
    if yaw is not None:
        print(
            "yaw writes live facing at +0x0752 (player+0x5E). "
            "512-unit binary angle; CODE 4 @4 wraps to 0..511. "
            "+0x091C is a different field."
        )
        write_u16_field(data, buf, base + OFF_U752, yaw, "yaw_live", changes)
        expect["u752"] = yaw
    if facing is not None:
        print(
            "facing_width=UNKNOWN corpus_+0x091C_not_always_0 "
            "(nine live records hold 0,1,2,12). "
            "This writes the INERT +0x091C word, not +0x0752."
        )
        old_b0 = data[base + OFF_FACING]
        old_b1 = data[base + OFF_FACING + 1]
        print(
            f"facing_before u16be={u16(data, base + OFF_FACING)} "
            f"b+0x091C={old_b0} (0x{old_b0:02X}) "
            f"b+0x091D={old_b1} (0x{old_b1:02X})"
        )
        if facing > 255:
            warnings.append(
                f"--facing {facing} sets +0x091C nonzero; "
                f"nine live records hold 0,1,2,12 at +0x091C. Width UNTESTED."
            )
        write_u16_field(data, buf, base + OFF_FACING, facing, "facing", changes)
        new_b0 = buf[base + OFF_FACING]
        new_b1 = buf[base + OFF_FACING + 1]
        print(
            f"facing_after u16be={u16(bytes(buf), base + OFF_FACING)} "
            f"b+0x091C={new_b0} (0x{new_b0:02X}) "
            f"b+0x091D={new_b1} (0x{new_b1:02X})"
        )
        expect["facing"] = facing
    if level is not None or x is not None or y is not None:
        print(
            "INERT +0x090C/+0x0918/+0x091A confirmed in game: writing these "
            "fields does nothing. Block-index authority is u16be at 0x06C2 "
            "(set-block, UNTESTED)."
        )
    if level is not None:
        write_u16_field(data, buf, base + OFF_LEVEL, new_level, "level_INERT", changes)
        expect["level"] = new_level
    if x is not None:
        write_u16_field(data, buf, base + OFF_X, new_x, "x_INERT", changes)
        expect["x"] = new_x
    if y is not None:
        write_u16_field(data, buf, base + OFF_Y, new_y, "y_INERT", changes)
        expect["y"] = new_y

    if points is not None:
        check_u16("points", points)
        write_u16_field(data, buf, base + OFF_POINTS, points, "points", changes)
    if treasure is not None:
        if treasure < 0 or treasure > 0xFFFFFFFF:
            raise EditRefused(f"treasure={treasure} does not fit u32be")
        write_u32_field(data, buf, base + OFF_TREASURE, treasure, "treasure", changes)

    if item_qtys:
        recs = read_inventory(data, base)
        for slot, qty in sorted(item_qtys.items()):
            check_u16(f"inv[{slot}].value", qty)
            if slot < 0 or slot >= len(recs):
                raise EditRefused(
                    f"slot {slot} is not an occupied inventory slot (n={len(recs)})"
                )
            rec_off = inventory_file_off(base, slot)
            before = recs[slot]
            print(
                f"item_before slot={slot} id={before[0]} {item_name(before[0])} "
                f"state={before[1]} value={before[2]} next_sibling={before[3]}"
            )
            write_u16_field(data, buf, rec_off + 4, qty, f"inv[{slot}].value", changes)
            after = struct.unpack_from(">4H", bytes(buf), rec_off)
            print(
                f"item_after slot={slot} id={after[0]} {item_name(after[0])} "
                f"state={after[1]} value={after[2]} next_sibling={after[3]}"
            )
            if after[0] != before[0] or after[1] != before[1] or after[3] != before[3]:
                raise EditRefused("id/state/next_sibling changed; not writing")
            if after[2] != qty:
                raise EditRefused("value write did not stick; not writing")

    if not changes:
        raise EditRefused("no fields changed")
    return buf, changes, expect, warnings


def print_decoded(decoded: dict, data: bytes, prefix: str = "") -> None:
    base = decoded["base"]
    in_world = in_world_region(base)
    io_word = None
    if len(data) > IO_FILE_OFF + 1:
        io_word = u16(data, IO_FILE_OFF)
    x_fp = decoded.get("x_fp")
    y_fp = decoded.get("y_fp")
    print(
        f"{prefix}B={base} (0x{base:X}) in_world_region={in_world} "
        f"level_INERT(+0x090C)={decoded['level']} name={decoded.get('level_name', '')!r} "
        f"x_INERT(+0x0918)={decoded['x']} y_INERT(+0x091A)={decoded['y']} "
        f"sector_type={decoded['type']} sector_type_name={decoded['type_name']} "
        f"hp={decoded['hp']} max_hp={decoded['max_hp']} "
        f"dungeon_load_path(+0x0748)={decoded.get('dungeon')} "
        f"x_live(+0x074A)={x_fp} >>10={decoded.get('x_live')} "
        f"y_live(+0x074E)={y_fp} >>10={decoded.get('y_live')} "
        f"facing_INERT(+0x091C)={decoded['facing']} "
        f"yaw_live(+0x0752)={decoded['u752']} "
        f"block_index_authority_SINK(+0x06C2)={io_word}"
    )
    print_inventory_tree(data, base, prefix=prefix)


def enrich(decoded: dict, levels: LevelIndex) -> dict:
    out = dict(decoded)
    lv = decoded.get("level")
    if lv is not None and 0 <= lv <= 24:
        out["level_name"] = levels.names[lv]
    else:
        out["level_name"] = None
    return out


def world_block_offset(index: int) -> int:
    if index < 0:
        raise SystemExit(f"error: block index {index} is negative")
    return WORLD_BASE + index * WORLD_STRIDE


def require_world_block(data: bytes, index: int) -> tuple[int, bytes]:
    off = world_block_offset(index)
    end = off + WORLD_STRIDE
    if end > len(data):
        raise SystemExit(
            f"error: file is {len(data)} bytes; world block index={index} "
            f"needs [{off},{end}); max_index={max_block_index(len(data))}"
        )
    return off, data[off:end]


def read_blockmap(data: bytes) -> list[list[int]]:
    if len(data) < BLOCKMAP_OFF + BLOCKMAP_SLOTS * BLOCKMAP_ROW:
        raise SystemExit(
            f"error: file is {len(data)} bytes; blockmap needs "
            f"[{BLOCKMAP_OFF},{BLOCKMAP_OFF + BLOCKMAP_SLOTS * BLOCKMAP_ROW})"
        )
    rows: list[list[int]] = []
    for slot in range(BLOCKMAP_SLOTS):
        rec = data[BLOCKMAP_OFF + slot * BLOCKMAP_ROW : BLOCKMAP_OFF + (slot + 1) * BLOCKMAP_ROW]
        rows.append(list(struct.unpack(">25H", rec)))
    return rows


def blockmap_file_off(slot: int, col: int) -> int:
    return BLOCKMAP_OFF + slot * BLOCKMAP_ROW + col * 2


def unpack_descriptor(word: int) -> dict:
    s1_index = word & 0x7F
    selector = (word >> 7) & 0x3F
    tag = (word >> 13) & 7
    cache_slot = selector if tag == 6 else selector + 64
    return {
        "word": word,
        "s1_index": s1_index,
        "selector": selector,
        "tag": tag,
        "cache_slot": cache_slot,
        "resource": cache_slot + 128,
    }


def format_descriptor(desc: dict) -> str:
    return (
        f"desc=0x{desc['word']:04X} tag={desc['tag']} "
        f"selector={desc['selector']} s1={desc['s1_index']} "
        f"cache_slot={desc['cache_slot']} resource={desc['resource']}"
    )


def format_flags(flags: int) -> str:
    bits = []
    if flags & 0x8000:
        bits.append("$8000")
    if flags & 0x4000:
        bits.append("$4000")
    if flags & 0x2000:
        bits.append("$2000")
    bit_s = ",".join(bits) if bits else "none"
    return f"flags=0x{flags:04X} nibble4_7={(flags >> 4) & 15} tested_bits={bit_s}"


def sector_of(raw: int) -> int:
    """Reader: ASR.L #10. CODE 4 @3590, CODE 7 @6976."""
    return raw >> FIXED_SHIFT


def encode_fixed(sector: int) -> int:
    """Writer: LSL.L #10 then ADD.L #$200. Cell centre."""
    return (sector << FIXED_SHIFT) + FIXED_CENTER


def wall_resource_for_level(level: int) -> int:
    if level <= 6:
        return 192
    if level <= 15:
        return 194
    return 193


def first_standable_arrival_json(levels: LevelIndex, level: int) -> dict:
    """First standable arrival in JSON-export order. Not list_index order."""
    if not (0 <= level <= 24):
        raise SystemExit(f"error: --arrival {level} not in 0..24")
    listing = "\n".join(format_arrivals(levels, level)) or "  (none)"
    if not levels.arrivals[level]:
        raise SystemExit(
            f"error: L{level} {levels.names[level]!r} has no arrivals\n{listing}"
        )
    for a in levels.arrivals[level]:
        x, y = int(a["x"]), int(a["y"])
        st, sn = levels.sector(level, x, y)
        if is_standable(st):
            print(
                f"arrival_used L{level} {levels.names[level]!r} ({x},{y}) "
                f"type={st} {sn} from_level={a.get('from_level')} "
                f"from_name={a.get('from_name')!r} "
                f"change_type={a.get('change_type_name')} "
                f"list_index={a.get('list_index')} "
                f"wall_resource={wall_resource_for_level(level)} "
                f"(JSON-export first standable)"
            )
            return a
    raise SystemExit(
        f"error: L{level} {levels.names[level]!r} has no standable arrival\n{listing}"
    )


def centred_sector_of(raw: int) -> int:
    """Writer-side cell centre only. LSL.L #10 then ADD.L #$200. Not the reader."""
    return (raw - FIXED_CENTER) >> FIXED_SHIFT


def fixed_decode(raw: int) -> dict:
    """10-bit fixed point. Sector is ASR.L #10 (raw >> 10)."""
    return {
        "raw": raw,
        "div": raw / float(FIXED_UNIT),
        "asr": sector_of(raw),
        "sector": sector_of(raw),
        "centred": centred_sector_of(raw),
        "centered": (raw - FIXED_CENTER) / float(FIXED_UNIT),
    }


def format_fixed(name: str, raw: int, *, fixed: bool, centred: bool = False) -> str:
    d = fixed_decode(raw)
    parts = [f"{name}_raw={d['raw']} (0x{d['raw'] & 0xFFFFFFFF:08X})"]
    if fixed:
        parts.append(f"{name}/1024={d['div']:.6f}")
        parts.append(f"{name}_sector=raw>>10={d['sector']}")
        if centred:
            parts.append(f"{name}_centred=(raw-$200)>>10={d['centred']}")
    elif centred:
        parts.append(f"{name}_sector=raw>>10={d['sector']}")
        parts.append(f"{name}_centred=(raw-$200)>>10={d['centred']}")
    return " ".join(parts)


def parse_records(block: bytes, off: int, count: int, rec_size: int) -> list[bytes]:
    out: list[bytes] = []
    for i in range(count):
        start = off + i * rec_size
        out.append(block[start : start + rec_size])
    return out


def rec_u16s(rec: bytes) -> list[int]:
    return list(struct.unpack(">" + "H" * (len(rec) // 2), rec))


def parse_object_entry(rec: bytes, index: int) -> dict:
    x = i32(rec, 0)
    y = i32(rec, 4)
    desc = unpack_descriptor(u16(rec, 8))
    flags = u16(rec, 10)
    unk_c = u16(rec, 12)
    link = u16(rec, 14)
    return {
        "index": index,
        "x": x,
        "y": y,
        "desc": desc,
        "flags": flags,
        "unknown_0c": unk_c,
        "link": link,
        "free": link == LINK_FREE,
        "hex": rec.hex(),
    }


def parse_world_block(data: bytes, index: int, *, dungeon: int | None = None) -> dict:
    file_off, block = require_world_block(data, index)
    anomalies: list[str] = []
    if len(block) != WORLD_STRIDE:
        anomalies.append(f"block_len={len(block)} expected={WORLD_STRIDE}")

    count0 = u16(block, WORLD_T0_COUNT_OFF)
    count1 = u16(block, WORLD_T1_COUNT_OFF)
    if count0 > WORLD_T0_MAX:
        anomalies.append(f"t0_count={count0} exceeds max {WORLD_T0_MAX}")
    if count1 > WORLD_T1_MAX:
        anomalies.append(f"t1_count={count1} exceeds max {WORLD_T1_MAX}")

    objects = [
        parse_object_entry(block[OBJ_TABLE_OFF + i * OBJ_STRIDE : OBJ_TABLE_OFF + (i + 1) * OBJ_STRIDE], i)
        for i in range(OBJ_COUNT)
    ]
    live = [o for o in objects if not o["free"]]
    free_n = OBJ_COUNT - len(live)
    bad_links = [
        o["index"]
        for o in objects
        if o["link"] not in (LINK_FREE, LINK_END) and o["link"] >= OBJ_COUNT
    ]
    if bad_links:
        anomalies.append(f"link_out_of_range n={len(bad_links)} first={bad_links[:8]}")

    trailer = block[WORLD_TRAILER_OFF : WORLD_TRAILER_OFF + WORLD_TRAILER_LEN]
    if len(trailer) != WORLD_TRAILER_LEN:
        anomalies.append(f"trailer_len={len(trailer)}")
    zeros = sum(1 for b in trailer if b == 0)
    if zeros != WORLD_TRAILER_LEN:
        anomalies.append(
            f"trailer_zeros={zeros}/{WORLD_TRAILER_LEN} (JT 164 CLR.B writes 128 zeros)"
        )

    empty_plus2 = sum(
        1 for o in objects if o["hex"] == "0000fffe000000000000000000000000"
    )
    all_zero = sum(1 for o in objects if o["hex"] == "00" * 16)
    if free_n == 0:
        anomalies.append(
            "link_$FFFE_count=0 (JT 164 marks free slots at +0x0E; "
            "this block does not)"
        )

    return {
        "level": dungeon if dungeon is not None else index,
        "index": index,
        "file_off": file_off,
        "block": block,
        "count0": count0,
        "recs0": parse_records(block, WORLD_T0_OFF, WORLD_T0_MAX, WORLD_T0_REC),
        "count1": count1,
        "recs1": parse_records(block, WORLD_T1_OFF, WORLD_T1_MAX, WORLD_T1_REC),
        "recs2": parse_records(block, WORLD_T2_OFF, WORLD_T2_MAX, WORLD_T2_REC),
        "recs3": parse_records(block, WORLD_T3_OFF, WORLD_T3_MAX, WORLD_T3_REC),
        "objects": objects,
        "live": live,
        "free_n": free_n,
        "empty_plus2": empty_plus2,
        "all_zero": all_zero,
        "trailer": trailer,
        "anomalies": anomalies,
    }


def print_record_row(tag: str, index: int, rec: bytes) -> None:
    words = " ".join(f"{w:04X}" for w in rec_u16s(rec))
    print(f"  {tag}[{index:02d}] hex={rec.hex()} u16be=[{words}]")


def print_object_row(
    obj: dict, *, fixed: bool, prefix: str = "  ", centred: bool = False
) -> None:
    link = obj["link"]
    if link == LINK_END:
        link_s = "0xFFFF(end)"
    elif link == LINK_FREE:
        link_s = "0xFFFE(free)"
    else:
        link_s = f"{link}"
    print(
        f"{prefix}obj[{obj['index']:03d}] "
        f"{format_fixed('x', obj['x'], fixed=fixed, centred=centred)} "
        f"{format_fixed('y', obj['y'], fixed=fixed, centred=centred)} "
        f"{format_descriptor(obj['desc'])} "
        f"{format_flags(obj['flags'])} "
        f"u16@+0x0C=0x{obj['unknown_0c']:04X} "
        f"link={link_s}"
    )


def walk_chain(objects: list[dict], start: int) -> list[dict]:
    """Walk $000E from start. hop 0 is the head. Stops at $FFFF/$FFFE, OOR, cycle."""
    out: list[dict] = []
    seen: set[int] = set()
    idx = start
    hop = 0
    while True:
        if idx in (LINK_FREE, LINK_END):
            break
        if idx < 0 or idx >= OBJ_COUNT:
            out.append(
                {
                    "hop": hop,
                    "index": idx,
                    "obj": None,
                    "sx": None,
                    "sy": None,
                    "stop": "out_of_range",
                }
            )
            break
        if idx in seen:
            obj = objects[idx]
            out.append(
                {
                    "hop": hop,
                    "index": idx,
                    "obj": obj,
                    "sx": sector_of(obj["x"]),
                    "sy": sector_of(obj["y"]),
                    "stop": "cycle",
                }
            )
            break
        seen.add(idx)
        obj = objects[idx]
        out.append(
            {
                "hop": hop,
                "index": idx,
                "obj": obj,
                "sx": sector_of(obj["x"]),
                "sy": sector_of(obj["y"]),
                "stop": None,
            }
        )
        nxt = obj["link"]
        if nxt in (LINK_FREE, LINK_END):
            break
        idx = nxt
        hop += 1
        if hop > OBJ_COUNT:
            break
    return out


def format_chain_nodes(chain: list[dict]) -> str:
    parts: list[str] = []
    for node in chain:
        obj = node["obj"]
        if obj is None:
            parts.append(f"({node['index']},?,?,oor)")
            continue
        desc = obj["desc"]["word"]
        parts.append(
            f"({node['index']},{node['sx']},{node['sy']},0x{desc:04X})"
        )
        if node["stop"] == "cycle":
            parts.append("CYCLE")
    return "[" + ", ".join(parts) + "]"


def print_world_block(world: dict, *, fixed: bool, centred: bool = False) -> None:
    lv = world["level"]
    print(
        f"world L{lv} index={world.get('index', lv)} "
        f"file_off={world['file_off']} (0x{world['file_off']:X}) "
        f"size={WORLD_STRIDE}"
    )
    if world["anomalies"]:
        print("world_anomalies " + " | ".join(world["anomalies"]))
        print("world_head_32 " + world["block"][:32].hex())
        print("world_obj0_32 " + world["block"][OBJ_TABLE_OFF : OBJ_TABLE_OFF + 32].hex())
        print(
            "world_patterns empty_0000FFFE_at_+0="
            f"{world['empty_plus2']} all_zero={world['all_zero']} "
            f"link_FFFE={world['free_n']}"
        )
    print(
        f"t0 +0x0000 count={world['count0']} max={WORLD_T0_MAX} "
        f"rec=8 used={min(world['count0'], WORLD_T0_MAX)}"
    )
    for i in range(min(world["count0"], WORLD_T0_MAX)):
        print_record_row("t0", i, world["recs0"][i])
    print(
        f"t1 +0x01E2 count={world['count1']} max={WORLD_T1_MAX} "
        f"rec=4 used={min(world['count1'], WORLD_T1_MAX)}"
    )
    for i in range(min(world["count1"], WORLD_T1_MAX)):
        print_record_row("t1", i, world["recs1"][i])
    print(f"t2 +0x025C count_field=NONE max={WORLD_T2_MAX} rec=8")
    for i, rec in enumerate(world["recs2"]):
        print_record_row("t2", i, rec)
    print(f"t3 +0x039C count_field=NONE max={WORLD_T3_MAX} rec=4")
    for i, rec in enumerate(world["recs3"]):
        print_record_row("t3", i, rec)
    print(
        f"objects +0x03D8 entries={OBJ_COUNT} live={len(world['live'])} "
        f"free={world['free_n']} (free <=> link==0xFFFE)"
    )
    for obj in world["live"]:
        print_object_row(obj, fixed=fixed, centred=centred)
    trailer = world["trailer"]
    print(
        f"trailer +0x2318 len={len(trailer)} "
        f"zeros={sum(1 for b in trailer if b == 0)} "
        f"ones={sum(1 for b in trailer if b == 1)} "
        f"hex={trailer.hex()}"
    )
    print(
        f"OK world L{lv} live={len(world['live'])} free={world['free_n']} "
        f"anomalies={len(world['anomalies'])}"
    )


def xref_objects(
    world: dict,
    levels: LevelIndex,
    *,
    fixed: bool,
    verbose: bool = True,
    centred: bool = False,
    print_unresolved: bool = True,
) -> dict:
    lv = world["level"]
    objects = world["objects"]
    refs = levels.sectors_with_item(lv)
    free_hits = 0
    pos_miss = 0
    range_miss = 0
    ok = 0
    hop1 = hop2 = hop3p = 0
    unresolved: list[dict] = []
    left_then_back = 0
    if verbose:
        print(
            f"objects_xref L{lv} map_item_sectors={len(refs)} "
            f"table_live={len(world['live'])} table_free={world['free_n']} "
            f"sector=raw>>10"
        )
    for x, y, item, st, sn in refs:
        flag = None
        obj = None
        chain: list[dict] = []
        if item < 0 or item >= OBJ_COUNT:
            flag = "item_out_of_range"
            range_miss += 1
            unresolved.append(
                {
                    "level": lv,
                    "x": x,
                    "y": y,
                    "type": st,
                    "type_name": sn,
                    "item": item,
                    "chain": [],
                    "why": "out_of_range",
                }
            )
        else:
            obj = objects[item]
            chain = walk_chain(objects, item)
            sx = sector_of(obj["x"])
            sy = sector_of(obj["y"])
            if obj["free"]:
                flag = "item_points_at_free_slot"
                free_hits += 1
                unresolved.append(
                    {
                        "level": lv,
                        "x": x,
                        "y": y,
                        "type": st,
                        "type_name": sn,
                        "item": item,
                        "chain": chain,
                        "why": "free_slot",
                    }
                )
            elif sx == x and sy == y:
                ok += 1
                in_sector = True
                left = False
                returned = False
                for node in chain[1:]:
                    if node["obj"] is None:
                        continue
                    here = node["sx"] == x and node["sy"] == y
                    if here:
                        if left:
                            returned = True
                        in_sector = True
                    else:
                        if in_sector:
                            left = True
                        in_sector = False
                if returned:
                    left_then_back += 1
            else:
                flag = "position_not_in_referencing_sector"
                pos_miss += 1
                match_hop = None
                left = False
                returned = False
                in_sector = False
                for node in chain:
                    if node["obj"] is None:
                        continue
                    here = node["sx"] == x and node["sy"] == y
                    if here:
                        if match_hop is None:
                            match_hop = node["hop"]
                        elif left:
                            returned = True
                        in_sector = True
                    else:
                        if in_sector:
                            left = True
                        in_sector = False
                if returned:
                    left_then_back += 1
                if match_hop is None:
                    unresolved.append(
                        {
                            "level": lv,
                            "x": x,
                            "y": y,
                            "type": st,
                            "type_name": sn,
                            "item": item,
                            "chain": chain,
                            "why": "chain_miss",
                        }
                    )
                elif returned:
                    # In, out, in again: not counted as a chain-walk hit.
                    unresolved.append(
                        {
                            "level": lv,
                            "x": x,
                            "y": y,
                            "type": st,
                            "type_name": sn,
                            "item": item,
                            "chain": chain,
                            "why": f"leave_then_back_first_hop={match_hop}",
                        }
                    )
                elif match_hop == 1:
                    hop1 += 1
                elif match_hop == 2:
                    hop2 += 1
                else:
                    hop3p += 1
        if verbose:
            print(
                f"  sector ({x},{y}) type={st} {sn} item={item}"
                + (f" FLAG={flag}" if flag else " MATCH")
            )
            if obj is not None:
                print_object_row(obj, fixed=fixed, prefix="    ", centred=centred)
                if flag == "position_not_in_referencing_sector":
                    print(
                        f"    implied_sector=({sector_of(obj['x'])},{sector_of(obj['y'])}) "
                        f"map_sector=({x},{y}) "
                        f"centred=({centred_sector_of(obj['x'])},{centred_sector_of(obj['y'])})"
                    )
                    print(f"    chain {format_chain_nodes(chain)}")
    chain_resolved = hop1 + hop2 + hop3p
    still = len(unresolved)
    if verbose:
        print(
            f"xref_counts L{lv} map_refs={len(refs)} direct={ok} "
            f"miss={len(refs) - ok} "
            f"chain_hop1={hop1} chain_hop2={hop2} chain_hop3plus={hop3p} "
            f"chain_resolved={chain_resolved} unresolved={still} "
            f"free_slot={free_hits} out_of_range={range_miss} "
            f"left_then_back={left_then_back}"
        )
        print(f"OK objects L{lv} direct={ok} unresolved={still}")
        if print_unresolved:
            for u in unresolved:
                print(
                    f"UNRESOLVED L{u['level']} sector=({u['x']},{u['y']}) "
                    f"type={u['type']} {u['type_name']} item={u['item']} "
                    f"why={u['why']} chain={format_chain_nodes(u['chain'])}"
                )
    return {
        "map_refs": len(refs),
        "match": ok,
        "direct": ok,
        "miss": len(refs) - ok,
        "free_slot": free_hits,
        "position_miss": pos_miss,
        "out_of_range": range_miss,
        "hop1": hop1,
        "hop2": hop2,
        "hop3p": hop3p,
        "chain_resolved": chain_resolved,
        "unresolved": still,
        "unresolved_rows": unresolved,
        "left_then_back": left_then_back,
        "mismatch_total": still,
        "live": len(world["live"]),
        "free": world["free_n"],
        "anomalies": list(world["anomalies"]),
    }


def xref_all_levels(
    data: bytes,
    levels: LevelIndex,
    *,
    label: str,
    print_unresolved: bool = True,
    verbose_rows: bool = False,
) -> dict:
    totals = {
        "map_refs": 0,
        "direct": 0,
        "miss": 0,
        "hop1": 0,
        "hop2": 0,
        "hop3p": 0,
        "chain_resolved": 0,
        "unresolved": 0,
        "left_then_back": 0,
        "live": 0,
        "free": 0,
        "unresolved_rows": [],
        "per_level": [],
    }
    print(f"xref_all file={label} sector=raw>>10")
    for lv in range(N_LEVELS):
        world = parse_world_block(data, lv, dungeon=lv)
        xref = xref_objects(
            world,
            levels,
            fixed=False,
            verbose=verbose_rows,
            print_unresolved=False,
        )
        totals["map_refs"] += xref["map_refs"]
        totals["direct"] += xref["direct"]
        totals["miss"] += xref["miss"]
        totals["hop1"] += xref["hop1"]
        totals["hop2"] += xref["hop2"]
        totals["hop3p"] += xref["hop3p"]
        totals["chain_resolved"] += xref["chain_resolved"]
        totals["unresolved"] += xref["unresolved"]
        totals["left_then_back"] += xref["left_then_back"]
        totals["live"] += xref["live"]
        totals["free"] += xref["free"]
        totals["unresolved_rows"].extend(xref["unresolved_rows"])
        totals["per_level"].append(xref)
        print(
            f"A2 L{lv:02d} {levels.names[lv]!r} map_refs={xref['map_refs']} "
            f"direct={xref['direct']} miss={xref['miss']}"
        )
        print(
            f"A3 L{lv:02d} hop1={xref['hop1']} hop2={xref['hop2']} "
            f"hop3plus={xref['hop3p']} unresolved={xref['unresolved']} "
            f"left_then_back={xref['left_then_back']} "
            f"live={xref['live']} free={xref['free']}"
        )
        if print_unresolved:
            for u in xref["unresolved_rows"]:
                print(
                    f"A4 UNRESOLVED L{u['level']} sector=({u['x']},{u['y']}) "
                    f"type={u['type']} {u['type_name']} item={u['item']} "
                    f"why={u['why']} chain={format_chain_nodes(u['chain'])}"
                )
    print(
        f"A_FILE {label} map_refs={totals['map_refs']} direct={totals['direct']} "
        f"chain_hop1={totals['hop1']} chain_hop2={totals['hop2']} "
        f"chain_hop3plus={totals['hop3p']} chain_resolved={totals['chain_resolved']} "
        f"unresolved={totals['unresolved']} left_then_back={totals['left_then_back']}"
    )
    return totals


def cmd_catalog(path: Path, levels: LevelIndex) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    print("B1 descriptor histogram live objects, 25 home blocks")
    desc_rows: dict[int, dict] = {}
    flag_hist: dict[int, int] = {}
    flag_bit_types: dict[int, dict[str, int]] = {}
    type_flag_bits: dict[str, dict[int, int]] = {}
    unk_c_nonzero: list[str] = []
    obj_res_by_level: list[set[int]] = [set() for _ in range(N_LEVELS)]
    for lv in range(N_LEVELS):
        world = parse_world_block(data, lv, dungeon=lv)
        objects = world["objects"]
        refs = levels.sectors_with_item(lv)
        item_to_types: dict[int, set[str]] = {}
        for x, y, item, st, sn in refs:
            chain = walk_chain(objects, item)
            for node in chain:
                if node["obj"] is None:
                    continue
                item_to_types.setdefault(node["index"], set()).add(f"{st}:{sn}")
        for obj in world["live"]:
            word = obj["desc"]["word"]
            row = desc_rows.setdefault(
                word,
                {
                    "count": 0,
                    "desc": obj["desc"],
                    "types": set(),
                    "levels": set(),
                },
            )
            row["count"] += 1
            row["levels"].add(lv)
            row["types"].update(item_to_types.get(obj["index"], set()))
            obj_res_by_level[lv].add(obj["desc"]["resource"])
            flags = obj["flags"]
            flag_hist[flags] = flag_hist.get(flags, 0) + 1
            types = item_to_types.get(obj["index"], set())
            for bit in range(16):
                mask = 1 << bit
                if flags & mask:
                    bucket = flag_bit_types.setdefault(mask, {})
                    if types:
                        for t in types:
                            bucket[t] = bucket.get(t, 0) + 1
                    else:
                        bucket["(unreferenced)"] = bucket.get("(unreferenced)", 0) + 1
                    for t in types or {"(unreferenced)"}:
                        tb = type_flag_bits.setdefault(t, {})
                        tb[mask] = tb.get(mask, 0) + 1
            if obj["unknown_0c"] != 0:
                unk_c_nonzero.append(
                    f"L{lv} obj[{obj['index']:03d}] +0x0C=0x{obj['unknown_0c']:04X} "
                    f"desc=0x{word:04X}"
                )
    for word in sorted(desc_rows):
        row = desc_rows[word]
        d = row["desc"]
        types = ",".join(sorted(row["types"])) if row["types"] else "(none)"
        print(
            f"B1 desc=0x{word:04X} count={row['count']} tag={d['tag']} "
            f"selector={d['selector']} cache_slot={d['cache_slot']} "
            f"resource={d['resource']} s1={d['s1_index']} "
            f"levels={sorted(row['levels'])} sector_types={types}"
        )
    print(f"B1 distinct_descriptors={len(desc_rows)} live_total={sum(r['count'] for r in desc_rows.values())}")

    bands = (("0-6", range(0, 7)), ("7-15", range(7, 16)), ("16-24", range(16, 25)))
    for band_name, band in bands:
        print(f"B2 band={band_name}")
        for lv in band:
            obj_res = obj_res_by_level[lv]
            tex = levels.texture_resources[lv]
            inn = sorted(obj_res & tex)
            out = sorted(obj_res - tex)
            print(
                f"B2 L{lv:02d} {levels.names[lv]!r} "
                f"obj_resources={sorted(obj_res)} "
                f"texture_list={sorted(tex)} "
                f"in_texture_list={inn} not_in_texture_list={out}"
            )
        band_obj = set().union(*(obj_res_by_level[lv] for lv in band))
        band_tex = set().union(*(levels.texture_resources[lv] for lv in band))
        print(
            f"B2 band={band_name} union_obj={sorted(band_obj)} "
            f"union_tex={sorted(band_tex)} "
            f"in={sorted(band_obj & band_tex)} "
            f"not_in={sorted(band_obj - band_tex)}"
        )

    print("B3 flags histogram live objects")
    for flags in sorted(flag_hist):
        bits = [f"${1 << b:04X}" for b in range(16) if flags & (1 << b)]
        print(
            f"B3 flags=0x{flags:04X} count={flag_hist[flags]} "
            f"bits={','.join(bits) if bits else 'none'}"
        )
    print("B3 flag-bit vs referencing sector types")
    for mask in sorted(flag_bit_types):
        pairs = flag_bit_types[mask]
        body = " ".join(f"{t}={n}" for t, n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])))
        print(f"B3 bit=0x{mask:04X} {body}")
    print("B3 sector-type vs flag bits")
    for t in sorted(type_flag_bits):
        bits = type_flag_bits[t]
        body = " ".join(f"0x{m:04X}={n}" for m, n in sorted(bits.items()))
        print(f"B3 type={t} {body}")

    print("B4 +0x0C on this file")
    print(f"B4 this_file nonzero_count={len(unk_c_nonzero)}")
    for line in unk_c_nonzero:
        print(f"B4 {line}")

    print("B4 +0x0C all local unique saves, all 25 home blocks, live objects")
    files = discover_save_files()
    grand_nonzero = 0
    grand_live = 0
    for fpath in files:
        fdata = fpath.read_bytes()
        file_nz = 0
        file_live = 0
        for lv in range(N_LEVELS):
            world = parse_world_block(fdata, lv, dungeon=lv)
            for obj in world["live"]:
                file_live += 1
                if obj["unknown_0c"] != 0:
                    file_nz += 1
                    print(
                        f"B4 NONZERO file={fpath.name} L{lv} "
                        f"obj[{obj['index']:03d}] +0x0C=0x{obj['unknown_0c']:04X} "
                        f"desc=0x{obj['desc']['word']:04X} "
                        f"x_raw={obj['x']} y_raw={obj['y']}"
                    )
        grand_nonzero += file_nz
        grand_live += file_live
        print(
            f"B4 file={fpath.name} live={file_live} "
            f"unknown_0c_nonzero={file_nz}"
        )
    print(
        f"B4 ALL_SAVES live={grand_live} unknown_0c_nonzero={grand_nonzero} "
        f"ever_nonzero={'YES' if grand_nonzero else 'NO'}"
    )
    print("OK catalog")
    return 0


def resolve_world_args(args: argparse.Namespace) -> tuple[int, int | None]:
    """Return (file_block_index, dungeon_level_or_None)."""
    block = getattr(args, "block", None)
    level = getattr(args, "level", None)
    if block is None and level is None:
        raise SystemExit("error: need --level N and/or --block N")
    if level is not None and not (0 <= level <= 24):
        raise SystemExit(f"error: --level {level} not in 0..24")
    if block is not None and block < 0:
        raise SystemExit(f"error: --block {block} is negative")
    if block is not None:
        return block, level
    assert level is not None
    return level, level


def cmd_world(path: Path, args: argparse.Namespace) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    print(f"world_base={WORLD_BASE} max_index={max_block_index(len(data))}")
    index, dungeon = resolve_world_args(args)
    world = parse_world_block(data, index, dungeon=dungeon)
    print_world_block(
        world,
        fixed=bool(getattr(args, "fixed", False)),
        centred=bool(getattr(args, "centred", False)),
    )
    return 0


def cmd_objects(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    print(f"world_base={WORLD_BASE} max_index={max_block_index(len(data))}")
    if getattr(args, "all_levels", False):
        xref_all_levels(
            data,
            levels,
            label=str(path),
            print_unresolved=True,
            verbose_rows=bool(getattr(args, "verbose", False)),
        )
        return 0
    index, dungeon = resolve_world_args(args)
    if dungeon is None:
        raise SystemExit("error: objects xref needs --level N (dungeon 0..24)")
    world = parse_world_block(data, index, dungeon=dungeon)
    if world["anomalies"]:
        print("world_anomalies " + " | ".join(world["anomalies"]))
        print("world_head_32 " + world["block"][:32].hex())
    xref_objects(
        world,
        levels,
        fixed=bool(getattr(args, "fixed", False)),
        centred=bool(getattr(args, "centred", False)),
    )
    return 0


def cmd_blockmap(path: Path) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    nmax = max_block_index(len(data))
    print(
        f"world_base={WORLD_BASE} stride={WORLD_STRIDE} "
        f"home_count={WORLD_COUNT} max_index={nmax} "
        f"io_slot={IO_SLOT} io_col={IO_COL} io_file_off={IO_FILE_OFF} "
        f"(0x{IO_FILE_OFF:X})"
    )
    rows = read_blockmap(data)
    for slot, words in enumerate(rows):
        nlen = data[slot * 128] if slot * 128 < len(data) else 0
        raw = data[slot * 128 + 1 : slot * 128 + 1 + min(nlen, 127)]
        try:
            name = raw.decode("mac_roman")
        except Exception:
            name = raw.decode("latin-1", errors="replace")
        print(f"slot {slot} nlen={nlen} name={name!r} u16be={words}")
    io_word = rows[IO_SLOT][IO_COL]
    io_pos = WORLD_BASE + io_word * WORLD_STRIDE
    print(
        f"io_word=table[{IO_SLOT}][{IO_COL}]={io_word} "
        f"file_pos={io_pos} (0x{io_pos:X}) "
        f"fits={io_pos + WORLD_STRIDE <= len(data)}"
    )
    print("OK blockmap")
    return 0


def cmd_set_block(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    slot = args.slot if args.slot is not None else IO_SLOT
    col = args.col if args.col is not None else IO_COL
    if not (0 <= slot < BLOCKMAP_SLOTS):
        raise SystemExit(f"error: --slot {slot} not in 0..{BLOCKMAP_SLOTS - 1}")
    if not (0 <= col < BLOCKMAP_COLS):
        raise SystemExit(f"error: --col {col} not in 0..{BLOCKMAP_COLS - 1}")
    require_u16("--index", args.index)
    data = path.read_bytes()
    nmax = max_block_index(len(data))
    if args.index > nmax:
        raise SystemExit(
            f"error: --index {args.index} has no 9112-byte block in this file "
            f"(max_index={nmax}, need [{WORLD_BASE + args.index * WORLD_STRIDE},"
            f"{WORLD_BASE + (args.index + 1) * WORLD_STRIDE}))"
        )
    out_path = require_write_output(path, args)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, getattr(args, "base", None))
    off = blockmap_file_off(slot, col)
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    print(
        f"set-block slot={slot} col={col} file_off={off} (0x{off:X}) "
        f"old={u16(data, off)} new={args.index} "
        f"file_pos_new={WORLD_BASE + args.index * WORLD_STRIDE} "
        f"THIS is the block-index authority (0x06C2 when slot=9 col=0). "
        f"+0x090C / +0x0918 / +0x091A are INERT (confirmed in game). "
        f"0x06C2 is UNTESTED in game."
    )
    write_u16_field(
        data, buf, off, args.index, f"blockmap[{slot}][{col}]", changes
    )
    if not changes:
        raise SystemExit("error: no fields changed")
    return commit_output(
        out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
    )


def cmd_set_dungeon(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    """Write the load-path dungeon word at player+0x54 = file B+0x0748.

    This is NOT stride-record +0x54 (name-table / prefix). CODE 2 load
    path pushes player+0x54, which maps to k*2876+0x0748.
    """
    require_u16("--level", args.level)
    data = path.read_bytes()
    out_path = require_write_output(path, args)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, getattr(args, "base", None))
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    print(
        f"set-dungeon writes u16be at B+0x{OFF_DUNGEON:04X} "
        f"(player+0x54 / k*2876+0x0748). "
        f"NOT B+0x0054 (stride prefix / name table). "
        f"+0x090C is INERT. 0x06C2 is a sink written FROM -$1AD8."
    )
    for decoded in targets:
        base = decoded["base"]
        off = base + OFF_DUNGEON
        print(
            f"  target B={base} (0x{base:X}) file_off={off} (0x{off:X}) "
            f"old={u16(data, off)} new={args.level} "
            f"inert_+0x090C={u16(data, base + OFF_LEVEL)}"
        )
        write_u16_field(data, buf, off, args.level, "dungeon_load_path", changes)
    if not changes:
        raise SystemExit("error: no fields changed")
    return commit_output(
        out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
    )


def cmd_set_position(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    """Write live X/Y at +0x074A / +0x074E. Optionally dungeon at +0x0748."""
    arrival_level = getattr(args, "arrival", None)
    raw = bool(getattr(args, "raw", False))
    if arrival_level is not None and (args.x is not None or args.y is not None):
        raise SystemExit("error: --arrival cannot be combined with --x/--y")
    if arrival_level is None and (args.x is None or args.y is None):
        raise SystemExit("error: set-position requires --x and --y, or --arrival LEVEL")
    if raw and arrival_level is not None:
        raise SystemExit("error: --raw applies to --x/--y only, not --arrival")

    dungeon = getattr(args, "dungeon", None)
    if arrival_level is not None:
        chosen = first_standable_arrival_json(levels, arrival_level)
        sx, sy = int(chosen["x"]), int(chosen["y"])
        x_raw = encode_fixed(sx)
        y_raw = encode_fixed(sy)
        if dungeon is None:
            dungeon = arrival_level
        print(
            f"set-position arrival L{arrival_level} sector=({sx},{sy}) "
            f"encoded x={x_raw} (0x{x_raw:X}) y={y_raw} (0x{y_raw:X}) "
            f"(sector<<10)+$200"
        )
    elif raw:
        x_raw = require_u32("--x", args.x)
        y_raw = require_u32("--y", args.y)
        print(
            f"set-position --raw x={x_raw} (0x{x_raw:X}) >>10={sector_of(x_raw)} "
            f"y={y_raw} (0x{y_raw:X}) >>10={sector_of(y_raw)}"
        )
    else:
        if not (0 <= args.x <= 31 and 0 <= args.y <= 31):
            raise SystemExit(f"error: --x/--y out of 0..31 ({args.x},{args.y})")
        x_raw = encode_fixed(args.x)
        y_raw = encode_fixed(args.y)
        print(
            f"set-position sector=({args.x},{args.y}) "
            f"encoded x={x_raw} (0x{x_raw:X}) y={y_raw} (0x{y_raw:X}) "
            f"(sector<<10)+$200"
        )

    if dungeon is not None:
        require_u16("--dungeon", dungeon)
    if getattr(args, "yaw", None) is not None:
        require_u16("--yaw", args.yaw)
    if getattr(args, "hp", None) is not None:
        require_u16("--hp", args.hp)
    if getattr(args, "maxhp", None) is not None:
        require_u16("--maxhp", args.maxhp)

    data = path.read_bytes()
    out_path = require_write_output(path, args)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, getattr(args, "base", None))
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    print(
        "set-position writes u32be at B+0x074A (X) and B+0x074E (Y). "
        "These are the live load-path fields (player+0x56 / +0x5A). "
        "+0x0918 / +0x091A are INERT. +0x074A is NOT a clock."
    )
    for decoded in targets:
        base = decoded["base"]
        print(
            f"  target B={base} (0x{base:X}) "
            f"old_x={u32(data, base + OFF_X_FP)} old_y={u32(data, base + OFF_Y_FP)} "
            f"new_x={x_raw} new_y={y_raw} "
            f"inert=({u16(data, base + OFF_X)},{u16(data, base + OFF_Y)}) "
            f"inert_L={u16(data, base + OFF_LEVEL)}"
        )
        write_u32_field(data, buf, base + OFF_X_FP, x_raw, "x_live", changes)
        write_u32_field(data, buf, base + OFF_Y_FP, y_raw, "y_live", changes)
        if dungeon is not None:
            write_u16_field(
                data, buf, base + OFF_DUNGEON, dungeon, "dungeon_load_path", changes
            )
        yaw = getattr(args, "yaw", None)
        if yaw is not None:
            print(
                "yaw writes live facing at +0x0752 (player+0x5E). "
                "512-unit binary angle; CODE 4 @4 wraps to 0..511. "
                "0=west (decreasing X), 128=north (decreasing Y), 256=east, 384=south. "
                "+0x091C is not this field."
            )
            write_u16_field(data, buf, base + OFF_U752, yaw, "yaw_live", changes)
        new_hp = decoded["hp"] if getattr(args, "hp", None) is None else args.hp
        new_max = decoded["max_hp"] if getattr(args, "maxhp", None) is None else args.maxhp
        if getattr(args, "hp", None) is not None or getattr(args, "maxhp", None) is not None:
            if new_hp > new_max and not getattr(args, "allow_overheal", False):
                raise SystemExit(
                    f"error: hp={new_hp} exceeds maxhp={new_max}; "
                    f"pass --allow-overheal to write anyway (game behaviour UNTESTED)"
                )
            print(
                "hp_copies=1 write_only=+0x0754/+0x0756 "
                "(Task A: no second copy in all 9 records)"
            )
        if getattr(args, "hp", None) is not None:
            write_u16_field(data, buf, base + OFF_HP, new_hp, "hp", changes)
        if getattr(args, "maxhp", None) is not None:
            write_u16_field(data, buf, base + OFF_MAXHP, new_max, "max_hp", changes)
    if not changes:
        raise SystemExit("error: no fields changed")
    expect = {"x_fp": x_raw, "y_fp": y_raw}
    if getattr(args, "yaw", None) is not None:
        expect["u752"] = args.yaw
    if getattr(args, "hp", None) is not None:
        expect["hp"] = args.hp
    if getattr(args, "maxhp", None) is not None:
        expect["max_hp"] = args.maxhp
    return commit_output(
        out_path,
        data,
        buf,
        targets,
        levels,
        changes,
        expect=expect,
        dry_run=bool(args.dry_run),
        allow_overheal=bool(getattr(args, "allow_overheal", False)),
    )


def discover_save_files() -> list[Path]:
    """Every local file large enough to hold the 25 world blocks."""
    roots = [ROOT / "reference" / "saves", ROOT / "data" / "saves"]
    skip_suffix = {".zip", ".png", ".hqx", ".sea", ".rsrc", ".txt"}
    skip_names = {"bombcode.bin", "bombcode_1995.bin"}
    found: list[Path] = []
    seen_path: set[str] = set()
    seen_hash: set[bytes] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() in skip_suffix:
                continue
            if path.name.lower() in skip_names:
                continue
            if path.stat().st_size < WORLD_END:
                continue
            key = str(path.resolve()).lower()
            if key in seen_path:
                continue
            seen_path.add(key)
            full = hashlib.sha256(path.read_bytes()).digest()
            if full in seen_hash:
                print(f"selftest skip_duplicate {path}")
                continue
            seen_hash.add(full)
            found.append(path)
    return found


def dpin_home_slice(dpin: bytes, level: int) -> bytes:
    off = 2876 + level * WORLD_STRIDE
    return dpin[off : off + WORLD_STRIDE]


def load_dpin() -> bytes:
    path = ROOT / "reference" / "dpin_128.bin"
    if not path.is_file():
        raise SystemExit(f"error: dpin not found at {path}")
    data = path.read_bytes()
    need = 2876 + WORLD_BYTES
    if len(data) < need:
        raise SystemExit(f"error: dpin size={len(data)} need>={need}")
    return data


def parse_object_table(block: bytes) -> list[dict]:
    """500 object records from a 9,112-byte world block. Raw numbers only."""
    need = OBJ_TABLE_OFF + OBJ_COUNT * OBJ_STRIDE
    if len(block) < need:
        raise SystemExit(f"error: block len={len(block)} < {need}")
    out = []
    for i in range(OBJ_COUNT):
        rec = block[OBJ_TABLE_OFF + i * OBJ_STRIDE : OBJ_TABLE_OFF + (i + 1) * OBJ_STRIDE]
        link = u16(rec, 14)
        out.append(
            {
                "index": i,
                "x_raw": u32(rec, 0),
                "y_raw": u32(rec, 4),
                "descriptor": u16(rec, 8),
                "flags": u16(rec, 10),
                "unk_c": u16(rec, 12),
                "link": link,
                "free": link == LINK_FREE,
            }
        )
    return out


def cmd_export_objects(levels: LevelIndex, out_dir: Path) -> int:
    """Write pristine per-level object tables from dpin 128."""
    dpin = load_dpin()
    out_dir.mkdir(parents=True, exist_ok=True)
    grand_live = 0
    grand_free = 0
    grand_refs = 0
    grand_ok = 0
    failures: list[str] = []
    total_bytes = 0
    print(f"export-objects source=dpin size={len(dpin)} out={out_dir}")
    print("fields=index,x_raw,y_raw,descriptor,flags,link  live_only=link!=0xFFFE")
    for lv in range(N_LEVELS):
        block = dpin_home_slice(dpin, lv)
        if len(block) != WORLD_STRIDE:
            raise SystemExit(f"error: L{lv} dpin slice len={len(block)}")
        table = parse_object_table(block)
        live = [o for o in table if not o["free"]]
        free_n = OBJ_COUNT - len(live)
        descs = sorted({o["descriptor"] for o in live})
        objects = [
            {
                "index": o["index"],
                "x_raw": o["x_raw"],
                "y_raw": o["y_raw"],
                "descriptor": o["descriptor"],
                "flags": o["flags"],
                "link": o["link"],
            }
            for o in live
        ]
        doc = {"level": lv, "source": "dpin", "objects": objects}
        text = json.dumps(doc, indent=2) + "\n"
        path = out_dir / f"objects_L{lv:02d}.json"
        path.write_text(text, encoding="utf-8")
        total_bytes += len(text.encode("utf-8"))
        grand_live += len(live)
        grand_free += free_n
        print(
            f"L{lv:02d} {levels.names[lv]!r} live={len(live)} free={free_n} "
            f"distinct_descriptors={len(descs)} wrote={path} bytes={len(text.encode('utf-8'))}"
        )

        refs = levels.sectors_with_item(lv)
        ok = 0
        for x, y, item, st, sn in refs:
            grand_refs += 1
            if item < 0 or item >= OBJ_COUNT:
                msg = (
                    f"FAIL L{lv} sector=({x},{y}) type={st} {sn} item={item} "
                    f"why=item_out_of_range"
                )
                failures.append(msg)
                print(msg)
                continue
            obj = table[item]
            if obj["free"]:
                msg = (
                    f"FAIL L{lv} sector=({x},{y}) type={st} {sn} item={item} "
                    f"why=free_slot link=0x{obj['link']:04X}"
                )
                failures.append(msg)
                print(msg)
                continue
            sx = obj["x_raw"] >> FIXED_SHIFT
            sy = obj["y_raw"] >> FIXED_SHIFT
            if sx != x or sy != y:
                msg = (
                    f"FAIL L{lv} sector=({x},{y}) type={st} {sn} item={item} "
                    f"why=sector_mismatch obj_sector=({sx},{sy}) "
                    f"x_raw={obj['x_raw']} y_raw={obj['y_raw']}"
                )
                failures.append(msg)
                print(msg)
                continue
            ok += 1
            grand_ok += 1
        print(
            f"  xref map_refs={len(refs)} resolved={ok} failed={len(refs) - ok}"
        )
    print(
        f"export-objects total_live={grand_live} total_free={grand_free} "
        f"map_refs={grand_refs} resolved={grand_ok} failed={len(failures)} "
        f"bytes_written={total_bytes}"
    )
    print("assets_included=none (coordinates and descriptors only)")
    if failures:
        print(f"CROSSCHECK_FAILED n={len(failures)}")
        return 1
    print("OK export-objects")
    return 0


def selftest_saves(levels: LevelIndex) -> int:
    files = discover_save_files()
    print(f"selftest files={len(files)} world_base={WORLD_BASE}")
    dpin_path = ROOT / "reference" / "dpin_128.bin"
    dpin = dpin_path.read_bytes() if dpin_path.is_file() else b""
    print(f"dpin path={dpin_path} size={len(dpin)}")
    grand_live = 0
    grand_free = 0
    grand_direct = 0
    grand_chain = 0
    grand_unresolved = 0
    grand_refs = 0
    for path in files:
        data = path.read_bytes()
        print(f"file={path} size={len(data)} max_index={max_block_index(len(data))}")
        if len(dpin) >= 2876 + WORLD_BYTES:
            same = 0
            for lv in range(N_LEVELS):
                if data[WORLD_BASE + lv * WORLD_STRIDE : WORLD_BASE + (lv + 1) * WORLD_STRIDE] == dpin_home_slice(dpin, lv):
                    same += 1
            print(f"  dpin_home_match={same}/{N_LEVELS}")
        rows = read_blockmap(data)
        print(
            f"  io_word=table[{IO_SLOT}][{IO_COL}]={rows[IO_SLOT][IO_COL]} "
            f"slot0[0]={rows[0][0]}"
        )
        totals = xref_all_levels(
            data, levels, label=str(path), print_unresolved=True, verbose_rows=False
        )
        grand_live += totals["live"]
        grand_free += totals["free"]
        grand_direct += totals["direct"]
        grand_chain += totals["chain_resolved"]
        grand_unresolved += totals["unresolved"]
        grand_refs += totals["map_refs"]
    print(
        f"selftest_totals files={len(files)} live_entries={grand_live} "
        f"free_slots={grand_free} map_refs={grand_refs} "
        f"direct={grand_direct} chain_resolved={grand_chain} "
        f"unresolved={grand_unresolved}"
    )
    print("OK selftest")
    return 0


def cmd_inspect(path: Path, levels: LevelIndex) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    for line in sidecar_report(path):
        print(line)
    names = list_save_names(data)
    print("name_slots=" + " ".join(f"{off}:{name!r}" for off, name in names))
    scan = scan_bases(data, levels)
    print(f"candidates={scan['n_candidates']} too_small={scan['too_small']}")
    print(
        "gate_pass G1_level={0} G2_x={1} G3_y={2} G4_standable={3} "
        "G5_hp={4} G6_xy_live={5}".format(*scan["gate_pass"])
    )
    print("n_gates_hist=" + " ".join(f"{i}:{n}" for i, n in enumerate(scan["n_gates_hist"])))
    print(f"all6_count={len(scan['all6'])}")
    if not scan["all6"]:
        print("all6=NONE -- best10:")
        for score, _neg, base, flags, decoded in scan["best10"]:
            failed = [i + 1 for i, ok in enumerate(flags) if not ok]
            raw_l = data[base + OFF_LEVEL : base + OFF_LEVEL + 2].hex()
            raw_x = data[base + OFF_X : base + OFF_X + 2].hex()
            raw_y = data[base + OFF_Y : base + OFF_Y + 2].hex()
            raw_hp = data[base + OFF_HP : base + OFF_HP + 2].hex()
            raw_mx = data[base + OFF_MAXHP : base + OFF_MAXHP + 2].hex()
            raw_xfp = data[base + OFF_X_FP : base + OFF_X_FP + 4].hex()
            raw_yfp = data[base + OFF_Y_FP : base + OFF_Y_FP + 4].hex()
            print(
                f"  B={base} (0x{base:X}) score={score}/6 failed_gates={failed} "
                f"lv={decoded['level']} x={decoded['x']} y={decoded['y']} "
                f"hp={decoded['hp']} max_hp={decoded['max_hp']} "
                f"x_fp={decoded.get('x_fp')} y_fp={decoded.get('y_fp')} "
                f"raw L={raw_l} X={raw_x} Y={raw_y} HP={raw_hp} MX={raw_mx} "
                f"XFP={raw_xfp} YFP={raw_yfp}"
            )
        print("REFUSED no all-6 player base")
        return 1
    for decoded in scan["all6"]:
        print_decoded(enrich(decoded, levels), data)
    print("OK inspect")
    return 0


def resolve_warp_target(
    args: argparse.Namespace, levels: LevelIndex
) -> tuple[int | None, int, int, bool]:
    arrival_mode = bool(args.arrival) or args.arrival_from is not None
    if arrival_mode:
        if args.level is None:
            raise SystemExit("error: --arrival/--arrival-from requires --level")
        chosen = select_standable_arrival(levels, args.level, args.arrival_from)
        return args.level, int(chosen["x"]), int(chosen["y"]), True
    if args.x is None or args.y is None:
        raise SystemExit("error: warp needs --x and --y, or --arrival")
    if not (0 <= args.x <= 31 and 0 <= args.y <= 31):
        raise SystemExit(f"error: --x/--y out of 0..31 ({args.x},{args.y})")
    if args.level is None:
        return None, args.x, args.y, False
    if not (0 <= args.level <= 24):
        raise SystemExit(f"error: --level {args.level} not in 0..24")
    return args.level, args.x, args.y, True


def require_write_output(path: Path, args: argparse.Namespace) -> Path:
    dry = bool(getattr(args, "dry_run", False))
    if args.output is None:
        if dry:
            return Path("<dry-run>")
        raise SystemExit("error: -o <out> is required unless --dry-run")
    out_path = Path(args.output)
    if not dry:
        refuse_in_place(path, out_path)
    return out_path


def cmd_warp(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    data = path.read_bytes()
    out_path = require_write_output(path, args)
    dry = bool(args.dry_run)

    print(
        "warp writes INERT fields +0x090C / +0x0918 / +0x091A "
        "(confirmed in game: no effect). Use set-block for 0x06C2 "
        "block-index authority (UNTESTED)."
    )
    level, x, y, write_level = resolve_warp_target(args, levels)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)

    if write_level:
        assert level is not None
        st, sn = levels.sector(level, x, y)
        if not is_standable(st):
            raise SystemExit(
                f"error: refuse warp to L{level} ({x},{y}) type={st} {sn} "
                f"(not standable: Void or Pillar)"
            )
    else:
        for decoded in targets:
            cur_lv = decoded["level"]
            st, sn = levels.sector(cur_lv, x, y)
            if not is_standable(st):
                raise SystemExit(
                    f"error: refuse warp to L{cur_lv} ({x},{y}) type={st} {sn} "
                    f"(not standable: Void or Pillar)"
                )

    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        base = decoded["base"]
        if write_level:
            assert level is not None
            write_u16_field(data, buf, base + OFF_LEVEL, level, "level_INERT", changes)
        write_u16_field(data, buf, base + OFF_X, x, "x_INERT", changes)
        write_u16_field(data, buf, base + OFF_Y, y, "y_INERT", changes)

    expect: dict = {"x": x, "y": y}
    if write_level:
        expect["level"] = level
    return commit_output(
        out_path, data, buf, targets, levels, changes, expect=expect, dry_run=dry
    )


def cmd_set(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    if args.hp is None and args.maxhp is None and args.facing is None and getattr(args, "yaw", None) is None:
        raise SystemExit("error: set requires at least one of --hp --maxhp --facing --yaw")
    data = path.read_bytes()
    out_path = require_write_output(path, args)

    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)

    if args.hp is not None:
        require_u16("--hp", args.hp)
    if args.maxhp is not None:
        require_u16("--maxhp", args.maxhp)
    if args.facing is not None:
        require_u16("--facing", args.facing)
    if getattr(args, "yaw", None) is not None:
        require_u16("--yaw", args.yaw)

    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        base = decoded["base"]
        new_hp = decoded["hp"] if args.hp is None else args.hp
        new_max = decoded["max_hp"] if args.maxhp is None else args.maxhp
        if new_hp > new_max and not args.allow_overheal:
            raise SystemExit(
                f"error: hp={new_hp} exceeds maxhp={new_max}; "
                f"pass --allow-overheal to write anyway (game behaviour UNTESTED)"
            )
        if new_hp > new_max and args.allow_overheal:
            print(
                f"WARNING: writing hp={new_hp} > maxhp={new_max}. "
                f"Game behaviour with cur > max is UNTESTED."
            )
        if args.hp is not None or args.maxhp is not None:
            print(
                "hp_copies=1 write_only=+0x0754/+0x0756 "
                "(Task A: no second copy in all 9 records)"
            )
        if args.hp is not None:
            write_u16_field(data, buf, base + OFF_HP, new_hp, "hp", changes)
        if args.maxhp is not None:
            write_u16_field(data, buf, base + OFF_MAXHP, new_max, "max_hp", changes)
        if getattr(args, "yaw", None) is not None:
            print(
                "yaw writes live facing at +0x0752 (player+0x5E). "
                "512-unit binary angle; CODE 4 @4 wraps to 0..511. "
                "+0x091C is not this field."
            )
            write_u16_field(data, buf, base + OFF_U752, args.yaw, "yaw_live", changes)
        if args.facing is not None:
            # +0x091C is a separate word. Nine live records hold 0,1,2,12.
            # Writing N as u16be at +0x091C. This is NOT the live yaw.
            old_b0 = data[base + OFF_FACING]
            old_b1 = data[base + OFF_FACING + 1]
            old_u16 = u16(data, base + OFF_FACING)
            print(
                "facing_width=UNKNOWN corpus_+0x091C_not_always_0 "
                "nine_live=0,1,2,12. Writes INERT +0x091C, not +0x0752."
            )
            print(
                f"facing_before u16be={old_u16} "
                f"b+0x091C={old_b0} (0x{old_b0:02X}) "
                f"b+0x091D={old_b1} (0x{old_b1:02X})"
            )
            if args.facing > 255:
                print(
                    f"WARNING: --facing {args.facing} sets +0x091C nonzero; "
                    f"nine live records hold 0,1,2,12. Width UNTESTED."
                )
            write_u16_field(data, buf, base + OFF_FACING, args.facing, "facing", changes)
            new_b0 = buf[base + OFF_FACING]
            new_b1 = buf[base + OFF_FACING + 1]
            print(
                f"facing_after u16be={u16(bytes(buf), base + OFF_FACING)} "
                f"b+0x091C={new_b0} (0x{new_b0:02X}) "
                f"b+0x091D={new_b1} (0x{new_b1:02X})"
            )

    expect = {}
    if args.hp is not None:
        expect["hp"] = args.hp
    if args.maxhp is not None:
        expect["max_hp"] = args.maxhp
    if getattr(args, "yaw", None) is not None:
        expect["u752"] = args.yaw
    return commit_output(
        out_path,
        data,
        buf,
        targets,
        levels,
        changes,
        allow_overheal=bool(args.allow_overheal),
        expect=expect or None,
        dry_run=bool(args.dry_run),
    )


def cmd_item(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    load_item_catalog()
    data = path.read_bytes()
    scan = scan_bases(data, levels)

    if args.list and args.slot is None and not getattr(args, "wipe", False):
        if args.base is not None:
            targets = select_targets(scan, args.base)
        else:
            live = [d for d in scan["all6"] if not in_world_region(d["base"])]
            if not live:
                raise SystemExit("error: no pre-world-region base passed all 6 gates")
            print(
                f"all6_count={len(scan['all6'])} pre_world={len(live)} "
                f"(listing all live bases; pass --base to restrict)"
            )
            targets = live
        for decoded in targets:
            print_decoded(enrich(decoded, levels), data)
        print("OK item-list")
        return 0

    if getattr(args, "wipe", False):
        out_path = require_write_output(path, args)
        targets = select_targets(scan, args.base)
        buf = bytearray(data)
        changes: list[tuple[int, int, int, str]] = []
        for decoded in targets:
            apply_wipe_inventory(data, buf, decoded["base"], changes)
        return commit_output(
            out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
        )

    value = args.value if args.value is not None else args.qty
    if args.slot is None or value is None:
        raise SystemExit("error: item write needs --slot N and --value Q (or --list)")
    out_path = require_write_output(path, args)
    require_u16("--value", value)
    if args.slot < 0:
        raise SystemExit(f"error: --slot {args.slot} is negative; refused")

    targets = select_targets(scan, args.base)
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        base = decoded["base"]
        recs = read_inventory(data, base)
        if args.slot >= len(recs):
            raise SystemExit(
                f"error: --slot {args.slot} is not an occupied slot (n={len(recs)}); refused"
            )
        rec_off = inventory_file_off(base, args.slot)
        before = recs[args.slot]
        print(
            f"item_before slot={args.slot} id={before[0]} {item_name(before[0])} "
            f"state={before[1]} value={before[2]} next_sibling={before[3]} "
            f"{interpret_word2(before[0], before[2])} "
            f"raw={data[rec_off:rec_off + 8].hex()}"
        )
        write_u16_field(data, buf, rec_off + 4, value, f"inv[{args.slot}].value", changes)
        after = struct.unpack_from(">4H", bytes(buf), rec_off)
        print(
            f"item_after slot={args.slot} id={after[0]} {item_name(after[0])} "
            f"state={after[1]} value={after[2]} next_sibling={after[3]} "
            f"{interpret_word2(after[0], after[2])} "
            f"raw={bytes(buf[rec_off:rec_off + 8]).hex()}"
        )
        if after[0] != before[0] or after[1] != before[1] or after[3] != before[3]:
            raise SystemExit("error: id/state/next_sibling changed; not writing")
        if after[2] != value:
            raise SystemExit("error: value write did not stick; not writing")

    return commit_output(
        out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
    )


def cmd_give(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    load_item_catalog()
    data = path.read_bytes()
    out_path = require_write_output(path, args)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        try:
            piece, ch, _expect, _warn = apply_give(
                bytes(buf),
                decoded,
                args.id,
                into=args.into,
                count=args.count,
            )
        except EditRefused as exc:
            raise SystemExit(f"error: {exc}") from exc
        buf = piece
        changes.extend(ch)
        print_inventory_tree(bytes(buf), decoded["base"])
    return commit_output(
        out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
    )


def cmd_equip(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    load_item_catalog()
    data = path.read_bytes()
    out_path = require_write_output(path, args)
    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        try:
            piece, ch, _expect, _warn = apply_equip(bytes(buf), decoded, args.slot)
        except EditRefused as exc:
            raise SystemExit(f"error: {exc}") from exc
        buf = piece
        changes.extend(ch)
        print_inventory_tree(bytes(buf), decoded["base"])
    return commit_output(
        out_path, data, buf, targets, levels, changes, dry_run=bool(args.dry_run)
    )


def cmd_export_item_catalog() -> int:
    global _ITEM_CATALOG
    _ITEM_CATALOG = None
    doc = load_item_catalog(write_json=True)
    print(f"OK export-item-catalog n={len(doc['entries'])} cedar={doc['cedar_admit_ids']}")
    return 0


def cmd_verify(path: Path, levels: LevelIndex) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    scan = scan_bases(data, levels)
    print(f"candidates={scan['n_candidates']} too_small={scan['too_small']}")
    print(
        "gate_pass G1_level={0} G2_x={1} G3_y={2} G4_standable={3} "
        "G5_hp={4} G6_xy_live={5}".format(*scan["gate_pass"])
    )
    print("n_gates_hist=" + " ".join(f"{i}:{n}" for i, n in enumerate(scan["n_gates_hist"])))
    print(f"all6_count={len(scan['all6'])}")
    names = ("G1_level", "G2_x", "G3_y", "G4_standable", "G5_hp", "G6_xy_live")

    def emit(base: int, tag: str) -> None:
        flags, decoded = gate_flags(data, base, levels)
        parts = " ".join(
            f"{name}={'PASS' if ok else 'FAIL'}" for name, ok in zip(names, flags)
        )
        print(
            f"{tag} B={base} (0x{base:X}) score={sum(flags)}/6 {parts} "
            f"lv={decoded['level']} x={decoded['x']} y={decoded['y']} "
            f"hp={decoded['hp']} max_hp={decoded['max_hp']} "
            f"x_live={decoded.get('x_live')} y_live={decoded.get('y_live')}"
        )

    print("stride_k*2876:")
    for k in range(NAME_SLOTS):
        base = k * PLAYER_STRIDE
        if base + SCAN_NEED > len(data):
            print(f"  k={k} B={base} SKIP too_short")
            continue
        emit(base, f"  k={k}")
    print("all6_hits:")
    if not scan["all6"]:
        print("  NONE")
        print("best10:")
        for score, _neg, base, flags, decoded in scan["best10"]:
            emit(base, "  best")
    else:
        for decoded in scan["all6"]:
            emit(decoded["base"], "  hit")
    if scan["all6"]:
        print("OK verify")
        return 0
    print("REFUSED no all-6 player base")
    return 1


def cmd_diff(path_a: Path, path_b: Path, levels: LevelIndex) -> int:
    a = path_a.read_bytes()
    b = path_b.read_bytes()
    scan_a = scan_bases(a, levels)
    bases = [d["base"] for d in scan_a["all6"]]
    print(f"a={path_a} size={len(a)} all6_bases={[d['base'] for d in scan_a['all6']]}")
    print(f"b={path_b} size={len(b)} all6_bases={[d['base'] for d in scan_bases(b, levels)['all6']]}")
    n = min(len(a), len(b))
    diffs = 0
    for i in range(n):
        if a[i] != b[i]:
            print(f"{i:08d} 0x{i:08X} {a[i]:02X} {b[i]:02X} {field_name_at(i, bases)}")
            diffs += 1
    if len(a) != len(b):
        longer, label = (a, "a") if len(a) > len(b) else (b, "b")
        for i in range(n, len(longer)):
            old = a[i] if i < len(a) else None
            new = b[i] if i < len(b) else None
            old_s = f"{old:02X}" if old is not None else "--"
            new_s = f"{new:02X}" if new is not None else "--"
            print(f"{i:08d} 0x{i:08X} {old_s} {new_s} size_tail_{label}")
            diffs += 1
    print(f"diff_count={diffs} min_len={n} a_len={len(a)} b_len={len(b)}")
    print("OK diff")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--export-dir",
        type=Path,
        default=EXPORT_DIR,
        help="directory of L00.json..L24.json (default: reference/export)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    inspect = sub.add_parser("inspect", help="scan and print every all-6 player base")
    inspect.add_argument("savefile", type=Path)

    world = sub.add_parser(
        "world",
        help="parse the 9,112-byte per-level world-state block",
    )
    world.add_argument("savefile", type=Path)
    world.add_argument("--level", type=int, default=None, help="dungeon 0..24 (home block)")
    world.add_argument(
        "--block",
        type=int,
        default=None,
        help="raw I/O block index (file_pos = 30540 + index*9112)",
    )
    world.add_argument(
        "--fixed",
        action="store_true",
        help="print positions as raw, /1024, and sector=raw>>10",
    )
    world.add_argument(
        "--centred",
        action="store_true",
        help="also print writer-only (raw-$200)>>10 alongside the reader sector",
    )

    objects = sub.add_parser(
        "objects",
        help="cross-reference the object table against L{N}.json Sector.item",
    )
    objects.add_argument("savefile", type=Path)
    objects.add_argument("--level", type=int, default=None, help="dungeon 0..24 for xref")
    objects.add_argument(
        "--block",
        type=int,
        default=None,
        help="raw I/O block index; default is the home block for --level",
    )
    objects.add_argument(
        "--all",
        dest="all_levels",
        action="store_true",
        help="run xref on home blocks 0..24 and print A2/A3/A4 counts",
    )
    objects.add_argument(
        "--verbose",
        action="store_true",
        help="with --all, print every map-ref row",
    )
    objects.add_argument(
        "--fixed",
        action="store_true",
        help="print positions as raw, /1024, and sector=raw>>10",
    )
    objects.add_argument(
        "--centred",
        action="store_true",
        help="also print writer-only (raw-$200)>>10 alongside the reader sector",
    )

    catalog = sub.add_parser(
        "catalog",
        help="descriptor/flags/+0x0C histograms and texture_list cross-check",
    )
    catalog.add_argument("savefile", type=Path)

    exp_obj = sub.add_parser(
        "export-objects",
        help="write pristine per-level object tables from dpin 128 (not from a save)",
    )
    exp_obj.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=EXPORT_DIR,
        help="directory for objects_L00.json .. objects_L24.json (default: reference/export)",
    )

    blockmap = sub.add_parser(
        "blockmap",
        help="print the 10x25 u16be table at +0x0500 (block-index authority)",
    )
    blockmap.add_argument("savefile", type=Path)

    set_block = sub.add_parser(
        "set-block",
        help=(
            "write the block-index authority (default file 0x06C2 = slot 9 col 0). "
            "UNTESTED in game. NOT +0x090C (INERT)."
        ),
    )
    set_block.add_argument("savefile", type=Path)
    set_block.add_argument("--index", type=int, required=True, help="block index to store")
    set_block.add_argument("--slot", type=int, default=None, help="row 0..9 (default 9)")
    set_block.add_argument("--col", type=int, default=None, help="column 0..24 (default 0)")
    set_block.add_argument("--base", type=int, default=None)
    set_block.add_argument("-o", "--output", type=Path, default=None)
    set_block.add_argument("--dry-run", action="store_true")

    selftest = sub.add_parser(
        "selftest",
        help="count live/free object-table entries and D2 mismatches on every local save",
    )

    warp = sub.add_parser(
        "warp",
        help=(
            "write INERT +0x090C/+0x0918/+0x091A (confirmed no effect in game). "
            "For the live block index use set-block (0x06C2, UNTESTED)."
        ),
    )
    warp.add_argument("savefile", type=Path)
    warp.add_argument("--level", type=int, default=None)
    warp.add_argument("--x", type=int, default=None)
    warp.add_argument("--y", type=int, default=None)
    warp.add_argument("--arrival", action="store_true")
    warp.add_argument(
        "--arrival-from",
        type=int,
        default=None,
        dest="arrival_from",
        help="pick the arrival whose from_level is N (still standable-gated)",
    )
    warp.add_argument("--base", type=int, default=None, help="player-region base if several pass")
    warp.add_argument("-o", "--output", type=Path, default=None)
    warp.add_argument("--dry-run", action="store_true", help="print changes and do not write")

    dungeon = sub.add_parser(
        "set-dungeon",
        help=(
            "write u16be dungeon at player+0x54 = file B+0x0748 "
            "(load-path argument). Never in place."
        ),
    )
    dungeon.add_argument("savefile", type=Path)
    dungeon.add_argument("--level", type=int, required=True, help="dungeon index written as u16be")
    dungeon.add_argument("--base", type=int, default=None, help="player-region base if several pass")
    dungeon.add_argument("-o", "--output", type=Path, default=None)
    dungeon.add_argument("--dry-run", action="store_true", help="print changes and do not write")

    pos = sub.add_parser(
        "set-position",
        help=(
            "write live X/Y u32be at +0x074A / +0x074E (10-bit fixed). "
            "--arrival LEVEL also writes dungeon at +0x0748. Never in place."
        ),
    )
    pos.add_argument("savefile", type=Path)
    pos.add_argument("--x", type=int, default=None, help="sector X, or raw u32 with --raw")
    pos.add_argument("--y", type=int, default=None, help="sector Y, or raw u32 with --raw")
    pos.add_argument(
        "--raw",
        action="store_true",
        help="treat --x/--y as raw u32be fixed-point values, not sector numbers",
    )
    pos.add_argument(
        "--arrival",
        type=int,
        default=None,
        help="first standable arrival in that level's JSON export (also writes dungeon)",
    )
    pos.add_argument(
        "--dungeon",
        type=int,
        default=None,
        help="also write u16be dungeon at +0x0748 (implied by --arrival)",
    )
    pos.add_argument(
        "--yaw",
        type=int,
        default=None,
        help="live facing u16be at +0x0752; 512-unit circle, 128=north",
    )
    pos.add_argument("--hp", type=int, default=None, help="current HP u16be at +0x0754")
    pos.add_argument("--maxhp", type=int, default=None, help="max HP u16be at +0x0756")
    pos.add_argument(
        "--allow-overheal",
        action="store_true",
        help="allow current HP > max HP (game behaviour UNTESTED)",
    )
    pos.add_argument("--base", type=int, default=None)
    pos.add_argument("-o", "--output", type=Path, default=None)
    pos.add_argument("--dry-run", action="store_true", help="print changes and do not write")

    s = sub.add_parser("set", help="write hp / maxhp / facing on one player base")
    s.add_argument("savefile", type=Path)
    s.add_argument("--hp", type=int, default=None)
    s.add_argument("--maxhp", type=int, default=None)
    s.add_argument("--facing", type=int, default=None, help="written as u16be at +0x091C; INERT, not live yaw")
    s.add_argument("--yaw", type=int, default=None, help="live facing u16be at +0x0752; 512-unit circle")
    s.add_argument(
        "--allow-overheal",
        action="store_true",
        help="allow current HP > max HP (game behaviour UNTESTED)",
    )
    s.add_argument("--base", type=int, default=None)
    s.add_argument("-o", "--output", type=Path, default=None)
    s.add_argument("--dry-run", action="store_true", help="print changes and do not write")

    item = sub.add_parser(
        "item",
        help="print the inventory tree, or change word 2 of an existing record",
    )
    item.add_argument("savefile", type=Path)
    item.add_argument("--list", action="store_true")
    item.add_argument("--slot", type=int, default=None)
    item.add_argument(
        "--value",
        type=int,
        default=None,
        help="overloaded word 2 (rounds / child slot / charge)",
    )
    item.add_argument("--qty", type=int, default=None, help="alias for --value")
    item.add_argument(
        "--wipe",
        action="store_true",
        help="write id=FFFF in all 256 slots and head=FFFF",
    )
    item.add_argument("--base", type=int, default=None)
    item.add_argument("-o", "--output", type=Path, default=None)
    item.add_argument("--dry-run", action="store_true", help="print changes and do not write")

    give = sub.add_parser(
        "give",
        help="append an inventory record; --into links it as a child",
    )
    give.add_argument("savefile", type=Path)
    give.add_argument("--id", type=int, required=True)
    give.add_argument("--into", type=int, default=None, help="parent slot")
    give.add_argument("--count", type=int, default=None, help="word 2 (rounds/charge)")
    give.add_argument("--base", type=int, default=None)
    give.add_argument("-o", "--output", type=Path, default=None)
    give.add_argument("--dry-run", action="store_true")

    equip = sub.add_parser(
        "equip",
        help="set ready-weapon +$198 or ready-crystal +$192 from a slot",
    )
    equip.add_argument("savefile", type=Path)
    equip.add_argument("--slot", type=int, required=True)
    equip.add_argument("--base", type=int, default=None)
    equip.add_argument("-o", "--output", type=Path, default=None)
    equip.add_argument("--dry-run", action="store_true")

    exp_cat = sub.add_parser(
        "export-item-catalog",
        help="decompress CODE 11 and write reference/export/item_catalog.json",
    )

    ver = sub.add_parser("verify", help="re-run the six-gate scan; print pass/fail per base")
    ver.add_argument("savefile", type=Path)

    diff = sub.add_parser("diff", help="byte-level greppable save diff")
    diff.add_argument("a", type=Path)
    diff.add_argument("b", type=Path)

    gui = sub.add_parser("gui", help="open the save-editor window")
    gui.add_argument("savefile", type=Path, nargs="?", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    try:
        args = build_parser().parse_args(argv)
        levels = LevelIndex(args.export_dir)
        if args.cmd == "inspect":
            return cmd_inspect(args.savefile, levels)
        if args.cmd == "world":
            return cmd_world(args.savefile, args)
        if args.cmd == "objects":
            return cmd_objects(args.savefile, levels, args)
        if args.cmd == "catalog":
            return cmd_catalog(args.savefile, levels)
        if args.cmd == "export-objects":
            return cmd_export_objects(levels, args.output_dir)
        if args.cmd == "blockmap":
            return cmd_blockmap(args.savefile)
        if args.cmd == "set-block":
            return cmd_set_block(args.savefile, levels, args)
        if args.cmd == "set-dungeon":
            return cmd_set_dungeon(args.savefile, levels, args)
        if args.cmd == "set-position":
            return cmd_set_position(args.savefile, levels, args)
        if args.cmd == "selftest":
            return selftest_saves(levels)
        if args.cmd == "warp":
            return cmd_warp(args.savefile, levels, args)
        if args.cmd == "set":
            return cmd_set(args.savefile, levels, args)
        if args.cmd == "item":
            return cmd_item(args.savefile, levels, args)
        if args.cmd == "give":
            return cmd_give(args.savefile, levels, args)
        if args.cmd == "equip":
            return cmd_equip(args.savefile, levels, args)
        if args.cmd == "export-item-catalog":
            return cmd_export_item_catalog()
        if args.cmd == "verify":
            return cmd_verify(args.savefile, levels)
        if args.cmd == "diff":
            return cmd_diff(args.a, args.b, levels)
        if args.cmd == "gui":
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from save_editor_gui import run_gui

            return run_gui(args.savefile, args.export_dir)
        raise SystemExit(f"unknown command {args.cmd}")
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, str):
            text = code[7:] if code.startswith("error: ") else code
            if not text.startswith("REFUSED"):
                print(f"REFUSED {text}")
            else:
                print(text)
            return 1
        raise
    except Exception as exc:
        print(f"REFUSED exception {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    sys.exit(main())
