# -*- coding: utf-8 -*-
"""Inspect and edit Pathways Into Darkness 2.0 Saved Games files.

Player-region base B is found by scanning, not assumed. Relative field
offsets are the ItemCheat / pid-re set (clock, HP, level, X, Y, facing,
inventory). They are accepted only when a candidate B passes all six
validation gates against the v2.0 level JSON.

Usage:
  python tools/save_editor.py inspect <savefile>
  python tools/save_editor.py warp <savefile> --level N --x X --y Y -o <out>
  python tools/save_editor.py warp <savefile> --level N --arrival -o <out>
  python tools/save_editor.py set <savefile> [--hp N] [--maxhp N] [--clock SEC] [--facing N] -o <out>
  python tools/save_editor.py item <savefile> --list [--base B]
  python tools/save_editor.py item <savefile> --slot N --qty Q -o <out>
  python tools/save_editor.py verify <savefile>
  python tools/save_editor.py diff <a> <b>
  python tools/save_editor.py gui [savefile]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "reference" / "export"

# Relative offsets inside a player region. Not file offsets until B is found.
OFF_CLOCK = 0x074A
OFF_U750 = 0x0750
OFF_U752 = 0x0752
OFF_HP = 0x0754
OFF_MAXHP = 0x0756
OFF_LEVEL = 0x090C
OFF_X = 0x0918
OFF_Y = 0x091A
OFF_FACING = 0x091C
OFF_INV = 0x0A00
SCAN_NEED = 0x0A08

CLOCK_MAX = 60 * 60 * 60 * 24  # 5_184_000 ticks = 24 h at 60 Hz
GRID = 32
N_LEVELS = 25

# Established: 25 static 9112-byte templates at this file offset.
TEMPLATE_BASE = 39392
TEMPLATE_STRIDE = 9112
TEMPLATE_BYTES = 25 * TEMPLATE_STRIDE  # 227800
TEMPLATE_END = TEMPLATE_BASE + TEMPLATE_BYTES  # 267192

# Named-save title slots (Pascal strings). Observed, not a full struct claim.
NAME_SLOT = 128
NAME_SLOTS = 8
PLAYER_STRIDE = 2876  # confirmed: record k is at k*2876

KNOWN_FIELDS = (
    (OFF_CLOCK, 4, "clock"),
    (OFF_U750, 2, "unknown_0x0750"),
    (OFF_U752, 2, "unknown_0x0752"),
    (OFF_HP, 2, "hp"),
    (OFF_MAXHP, 2, "max_hp"),
    (OFF_LEVEL, 2, "level"),
    (OFF_X, 2, "x"),
    (OFF_Y, 2, "y"),
    (OFF_FACING, 2, "facing"),
    (OFF_INV, 0, "inventory"),  # open-ended; tagged separately
)


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


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
        self.arrivals: list[list[dict]] = []
        for n in range(N_LEVELS):
            path = export_dir / f"L{n:02d}.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            types = [[-1] * GRID for _ in range(GRID)]
            tnames = [[""] * GRID for _ in range(GRID)]
            for s in doc["sectors"]:
                types[s["y"]][s["x"]] = s["type"]
                tnames[s["y"]][s["x"]] = s["type_name"]
            self.names.append(doc["name"])
            self.types.append(types)
            self.type_names.append(tnames)
            self.arrivals.append(list(doc.get("arrivals") or []))

    def sector(self, level: int, x: int, y: int) -> tuple[int, str]:
        return self.types[level][y][x], self.type_names[level][y][x]


def in_template_region(offset: int) -> bool:
    return TEMPLATE_BASE <= offset < TEMPLATE_END


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
        "clock": None,
        "u750": None,
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
    clock = u32(data, base + OFF_CLOCK)
    decoded.update(
        level=level,
        x=x,
        y=y,
        hp=hp,
        max_hp=max_hp,
        clock=clock,
        u750=u16(data, base + OFF_U750),
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
    flags[5] = clock < CLOCK_MAX
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


def read_inventory(data: bytes, base: int, limit: int = 64) -> list[tuple[int, int, int, int]]:
    recs: list[tuple[int, int, int, int]] = []
    off = base + OFF_INV
    for _ in range(limit):
        if off + 8 > len(data):
            break
        rec = struct.unpack_from(">4H", data, off)
        recs.append(rec)
        if rec[0] == 0xFFFF:
            break
        off += 8
    return recs


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
    if in_template_region(file_off):
        block = (file_off - TEMPLATE_BASE) // TEMPLATE_STRIDE
        labels.append(f"template_block_{block}")
    for base in bases:
        rel = file_off - base
        if rel < 0:
            continue
        if OFF_INV <= rel < OFF_INV + 512:
            slot = (rel - OFF_INV) // 8
            within = (rel - OFF_INV) % 8
            field = ("id", "state", "qty", "catalog")[within // 2]
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
    live = [d for d in scan["all6"] if not in_template_region(d["base"])]
    ghost = [d for d in scan["all6"] if in_template_region(d["base"])]
    print(f"all6_count={len(scan['all6'])} pre_template={len(live)} in_template={len(ghost)}")
    for d in scan["all6"]:
        print(
            f"  hit B={d['base']} (0x{d['base']:X}) in_template={in_template_region(d['base'])} "
            f"L{d['level']} ({d['x']},{d['y']})"
        )
    if base_arg is not None:
        chosen = [d for d in scan["all6"] if d["base"] == base_arg]
        if not chosen:
            raise SystemExit(f"error: --base {base_arg} did not pass all 6 gates")
        if in_template_region(base_arg):
            raise SystemExit(
                f"error: --base {base_arg} is inside the static template region "
                f"[{TEMPLATE_BASE},{TEMPLATE_END}); refuse to write templates"
            )
        return chosen
    if len(live) == 0:
        raise SystemExit("error: no pre-template base passed all 6 gates")
    if len(live) > 1:
        listing = " ".join(f"B={d['base']}" for d in live)
        raise SystemExit(
            f"error: {len(live)} pre-template bases passed the gate ({listing}); "
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)
    print(f"wrote {out_path} bytes={len(out_bytes)} changes={len(changes)}")
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
    clock_seconds: int | None = None,
    facing: int | None = None,
    level: int | None = None,
    x: int | None = None,
    y: int | None = None,
    item_qtys: dict[int, int] | None = None,
    allow_overheal: bool = False,
) -> tuple[bytearray, list[tuple[int, int, int, str]], dict, list[str]]:
    """Apply field edits to one live player base. Raises EditRefused."""
    base = decoded["base"]
    if in_template_region(base):
        raise EditRefused(
            f"B={base} is inside the static template region "
            f"[{TEMPLATE_BASE},{TEMPLATE_END}); refuse to write templates"
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

    clock_ticks = None
    if clock_seconds is not None:
        if clock_seconds < 0:
            raise EditRefused(f"clock seconds={clock_seconds} is negative")
        clock_ticks = clock_seconds * 60
        if clock_ticks > 0xFFFFFFFF:
            raise EditRefused(f"clock seconds={clock_seconds} does not fit u32be ticks")
        if clock_ticks >= CLOCK_MAX:
            raise EditRefused(
                f"clock {clock_seconds}s stores {clock_ticks} ticks; "
                f"G6 requires ticks < {CLOCK_MAX}"
            )

    if facing is not None:
        check_u16("facing", facing)

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
    if clock_ticks is not None:
        write_u32_field(data, buf, base + OFF_CLOCK, clock_ticks, "clock", changes)
        expect["clock"] = clock_ticks
    if facing is not None:
        print(
            "facing_width=UNKNOWN corpus_+0x091C_always_0=YES "
            "observed_values_live_in_+0x091D"
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
                f"every corpus record has +0x091C=0. Width UNTESTED."
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
    if level is not None:
        write_u16_field(data, buf, base + OFF_LEVEL, new_level, "level", changes)
        expect["level"] = new_level
    if x is not None:
        write_u16_field(data, buf, base + OFF_X, new_x, "x", changes)
        expect["x"] = new_x
    if y is not None:
        write_u16_field(data, buf, base + OFF_Y, new_y, "y", changes)
        expect["y"] = new_y

    if item_qtys:
        recs = read_inventory(data, base)
        term = next((i for i, rec in enumerate(recs) if rec[0] == 0xFFFF), None)
        if term is None:
            raise EditRefused(
                f"inventory at B={base} has no FFFF terminator within the read limit"
            )
        for slot, qty in sorted(item_qtys.items()):
            check_u16(f"inv[{slot}].qty", qty)
            if slot < 0 or slot > term:
                raise EditRefused(
                    f"slot {slot} is past the FFFF terminator at slot {term}"
                )
            if recs[slot][0] == 0xFFFF:
                raise EditRefused(f"slot {slot} is the FFFF terminator; refused")
            rec_off = base + OFF_INV + slot * 8
            before = recs[slot]
            print(
                f"item_before slot={slot} id={before[0]} state={before[1]} "
                f"qty={before[2]} catalog={before[3]}"
            )
            write_u16_field(data, buf, rec_off + 4, qty, f"inv[{slot}].qty", changes)
            after = struct.unpack_from(">4H", bytes(buf), rec_off)
            print(
                f"item_after slot={slot} id={after[0]} state={after[1]} "
                f"qty={after[2]} catalog={after[3]}"
            )
            if after[0] != before[0] or after[1] != before[1] or after[3] != before[3]:
                raise EditRefused("id/state/catalog changed; not writing")
            if after[2] != qty:
                raise EditRefused("qty write did not stick; not writing")

    if not changes:
        raise EditRefused("no fields changed")
    return buf, changes, expect, warnings


def print_decoded(decoded: dict, data: bytes, prefix: str = "") -> None:
    base = decoded["base"]
    clock = decoded["clock"]
    clock_s = clock / 60.0 if clock is not None else float("nan")
    in_tmpl = in_template_region(base)
    print(
        f"{prefix}B={base} (0x{base:X}) in_template_region={in_tmpl} "
        f"level={decoded['level']} name={decoded.get('level_name', '')!r} "
        f"x={decoded['x']} y={decoded['y']} "
        f"sector_type={decoded['type']} sector_type_name={decoded['type_name']} "
        f"hp={decoded['hp']} max_hp={decoded['max_hp']} "
        f"clock_ticks={clock} clock_s={clock_s:.4f} "
        f"facing={decoded['facing']} u16@0x0750={decoded['u750']} "
        f"u16@0x0752={decoded['u752']}"
    )
    recs = read_inventory(data, base)
    print(f"{prefix}inventory_from B+0x0A00 until id=FFFF n={len(recs)}")
    for i, rec in enumerate(recs):
        print(
            f"{prefix}  inv[{i}] id={rec[0]} state={rec[1]} "
            f"qty={rec[2]} catalog={rec[3]} raw={data[base+OFF_INV+i*8:base+OFF_INV+i*8+8].hex()}"
        )


def enrich(decoded: dict, levels: LevelIndex) -> dict:
    out = dict(decoded)
    lv = decoded.get("level")
    if lv is not None and 0 <= lv <= 24:
        out["level_name"] = levels.names[lv]
    else:
        out["level_name"] = None
    return out


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
        "G5_hp={4} G6_clock={5}".format(*scan["gate_pass"])
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
            raw_ck = data[base + OFF_CLOCK : base + OFF_CLOCK + 4].hex()
            print(
                f"  B={base} (0x{base:X}) score={score}/6 failed_gates={failed} "
                f"lv={decoded['level']} x={decoded['x']} y={decoded['y']} "
                f"hp={decoded['hp']} max_hp={decoded['max_hp']} clock={decoded['clock']} "
                f"raw L={raw_l} X={raw_x} Y={raw_y} HP={raw_hp} MX={raw_mx} CLK={raw_ck}"
            )
        return 1
    for decoded in scan["all6"]:
        print_decoded(enrich(decoded, levels), data)
    return 0


def resolve_warp_target(
    args: argparse.Namespace, levels: LevelIndex
) -> tuple[int, int, int]:
    level = args.level
    if not (0 <= level <= 24):
        raise SystemExit(f"error: --level {level} not in 0..24")
    if args.arrival:
        arrivals = levels.arrivals[level]
        if not arrivals:
            raise SystemExit(f"error: L{level} has an empty arrivals list")
        first = arrivals[0]
        x, y = int(first["x"]), int(first["y"])
        print(
            f"arrival_used L{level} ({x},{y}) from_level={first.get('from_level')} "
            f"from_name={first.get('from_name')!r} change_type={first.get('change_type_name')}"
        )
        return level, x, y
    if args.x is None or args.y is None:
        raise SystemExit("error: warp needs --x and --y, or --arrival")
    if not (0 <= args.x <= 31 and 0 <= args.y <= 31):
        raise SystemExit(f"error: --x/--y out of 0..31 ({args.x},{args.y})")
    return level, args.x, args.y


def cmd_warp(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    data = path.read_bytes()
    out_path = Path(args.output)
    refuse_in_place(path, out_path)

    level, x, y = resolve_warp_target(args, levels)
    st, sn = levels.sector(level, x, y)
    if st in (0, 7):
        raise SystemExit(
            f"error: refuse warp to L{level} ({x},{y}) type={st} {sn} "
            f"(not standable: Void or Pillar)"
        )

    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)

    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        base = decoded["base"]
        write_u16_field(data, buf, base + OFF_LEVEL, level, "level", changes)
        write_u16_field(data, buf, base + OFF_X, x, "x", changes)
        write_u16_field(data, buf, base + OFF_Y, y, "y", changes)

    return commit_output(
        out_path, data, buf, targets, levels, changes, expect={"level": level, "x": x, "y": y}
    )


def cmd_set(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    if args.hp is None and args.maxhp is None and args.clock is None and args.facing is None:
        raise SystemExit("error: set requires at least one of --hp --maxhp --clock --facing")
    data = path.read_bytes()
    out_path = Path(args.output)
    refuse_in_place(path, out_path)

    scan = scan_bases(data, levels)
    targets = select_targets(scan, args.base)

    if args.hp is not None:
        require_u16("--hp", args.hp)
    if args.maxhp is not None:
        require_u16("--maxhp", args.maxhp)
    clock_ticks = None
    if args.clock is not None:
        if args.clock < 0:
            raise SystemExit(f"error: --clock {args.clock} is negative; refused")
        clock_ticks = require_u32("--clock ticks (seconds*60)", args.clock * 60)
        if clock_ticks >= CLOCK_MAX:
            raise SystemExit(
                f"error: --clock {args.clock}s stores {clock_ticks} ticks; "
                f"G6 requires ticks < {CLOCK_MAX}; refused"
            )
    if args.facing is not None:
        require_u16("--facing", args.facing)

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
        if clock_ticks is not None:
            write_u32_field(data, buf, base + OFF_CLOCK, clock_ticks, "clock", changes)
            print(
                f"clock_seconds_in={args.clock} clock_ticks_stored={clock_ticks} "
                f"(x60)"
            )
        if args.facing is not None:
            # Width of facing is UNKNOWN. Corpus: +0x091C is always 0x00;
            # observed values 0,1,2,12 live in the byte at +0x091D. Writing
            # N as u16be at +0x091C reproduces that layout when N < 256.
            # HYPOTHESIS, not a width claim.
            old_b0 = data[base + OFF_FACING]
            old_b1 = data[base + OFF_FACING + 1]
            old_u16 = u16(data, base + OFF_FACING)
            print(
                f"facing_width=UNKNOWN corpus_+0x091C_always_0=YES "
                f"observed_values_live_in_+0x091D"
            )
            print(
                f"facing_before u16be={old_u16} "
                f"b+0x091C={old_b0} (0x{old_b0:02X}) "
                f"b+0x091D={old_b1} (0x{old_b1:02X})"
            )
            if args.facing > 255:
                print(
                    f"WARNING: --facing {args.facing} sets +0x091C nonzero; "
                    f"every corpus record has +0x091C=0. Width UNTESTED."
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
    if clock_ticks is not None:
        expect["clock"] = clock_ticks
    return commit_output(
        out_path,
        data,
        buf,
        targets,
        levels,
        changes,
        allow_overheal=bool(args.allow_overheal),
        expect=expect or None,
    )


def cmd_item(path: Path, levels: LevelIndex, args: argparse.Namespace) -> int:
    data = path.read_bytes()
    scan = scan_bases(data, levels)

    if args.list and args.slot is None:
        if args.base is not None:
            targets = select_targets(scan, args.base)
        else:
            live = [d for d in scan["all6"] if not in_template_region(d["base"])]
            if not live:
                raise SystemExit("error: no pre-template base passed all 6 gates")
            print(
                f"all6_count={len(scan['all6'])} pre_template={len(live)} "
                f"(listing all live bases; pass --base to restrict)"
            )
            targets = live
        for decoded in targets:
            print_decoded(enrich(decoded, levels), data)
        return 0

    if args.slot is None or args.qty is None:
        raise SystemExit("error: item write needs --slot N and --qty Q (or --list)")
    if args.output is None:
        raise SystemExit("error: item write needs -o <out>")
    out_path = Path(args.output)
    refuse_in_place(path, out_path)
    require_u16("--qty", args.qty)
    if args.slot < 0:
        raise SystemExit(f"error: --slot {args.slot} is negative; refused")

    targets = select_targets(scan, args.base)
    buf = bytearray(data)
    changes: list[tuple[int, int, int, str]] = []
    for decoded in targets:
        base = decoded["base"]
        recs = read_inventory(data, base)
        term = next((i for i, rec in enumerate(recs) if rec[0] == 0xFFFF), None)
        if term is None:
            raise SystemExit(
                f"error: inventory at B={base} has no FFFF terminator within the read limit; refused"
            )
        if args.slot > term:
            raise SystemExit(
                f"error: --slot {args.slot} is past the FFFF terminator at slot {term}; refused"
            )
        if recs[args.slot][0] == 0xFFFF:
            raise SystemExit(
                f"error: --slot {args.slot} is the FFFF terminator (id=65535); refused"
            )
        rec_off = base + OFF_INV + args.slot * 8
        before = recs[args.slot]
        print(
            f"item_before slot={args.slot} id={before[0]} state={before[1]} "
            f"qty={before[2]} catalog={before[3]} "
            f"raw={data[rec_off:rec_off + 8].hex()}"
        )
        qty_off = rec_off + 4
        write_u16_field(data, buf, qty_off, args.qty, f"inv[{args.slot}].qty", changes)
        after = struct.unpack_from(">4H", bytes(buf), rec_off)
        print(
            f"item_after slot={args.slot} id={after[0]} state={after[1]} "
            f"qty={after[2]} catalog={after[3]} "
            f"raw={bytes(buf[rec_off:rec_off + 8]).hex()}"
        )
        if after[0] != before[0] or after[1] != before[1] or after[3] != before[3]:
            raise SystemExit("error: id/state/catalog changed; not writing")
        if after[2] != args.qty:
            raise SystemExit("error: qty write did not stick; not writing")

    return commit_output(out_path, data, buf, targets, levels, changes)


def cmd_verify(path: Path, levels: LevelIndex) -> int:
    data = path.read_bytes()
    print(f"file={path}")
    print(f"size={len(data)}")
    scan = scan_bases(data, levels)
    print(f"candidates={scan['n_candidates']} too_small={scan['too_small']}")
    print(
        "gate_pass G1_level={0} G2_x={1} G3_y={2} G4_standable={3} "
        "G5_hp={4} G6_clock={5}".format(*scan["gate_pass"])
    )
    print("n_gates_hist=" + " ".join(f"{i}:{n}" for i, n in enumerate(scan["n_gates_hist"])))
    print(f"all6_count={len(scan['all6'])}")
    names = ("G1_level", "G2_x", "G3_y", "G4_standable", "G5_hp", "G6_clock")

    def emit(base: int, tag: str) -> None:
        flags, decoded = gate_flags(data, base, levels)
        parts = " ".join(
            f"{name}={'PASS' if ok else 'FAIL'}" for name, ok in zip(names, flags)
        )
        print(
            f"{tag} B={base} (0x{base:X}) score={sum(flags)}/6 {parts} "
            f"lv={decoded['level']} x={decoded['x']} y={decoded['y']} "
            f"hp={decoded['hp']} max_hp={decoded['max_hp']} clock={decoded['clock']}"
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
    return 0 if scan["all6"] else 1


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

    warp = sub.add_parser("warp", help="write a new save with relocated player")
    warp.add_argument("savefile", type=Path)
    warp.add_argument("--level", type=int, required=True)
    warp.add_argument("--x", type=int, default=None)
    warp.add_argument("--y", type=int, default=None)
    warp.add_argument("--arrival", action="store_true")
    warp.add_argument("--base", type=int, default=None, help="player-region base if several pass")
    warp.add_argument("-o", "--output", type=Path, required=True)

    s = sub.add_parser("set", help="write hp / maxhp / clock / facing on one player base")
    s.add_argument("savefile", type=Path)
    s.add_argument("--hp", type=int, default=None)
    s.add_argument("--maxhp", type=int, default=None)
    s.add_argument("--clock", type=int, default=None, help="game time in seconds (stored as seconds*60)")
    s.add_argument("--facing", type=int, default=None, help="written as u16be at +0x091C; width UNKNOWN")
    s.add_argument(
        "--allow-overheal",
        action="store_true",
        help="allow current HP > max HP (game behaviour UNTESTED)",
    )
    s.add_argument("--base", type=int, default=None)
    s.add_argument("-o", "--output", type=Path, required=True)

    item = sub.add_parser("item", help="list or change quantity of an existing inventory record")
    item.add_argument("savefile", type=Path)
    item.add_argument("--list", action="store_true")
    item.add_argument("--slot", type=int, default=None)
    item.add_argument("--qty", type=int, default=None)
    item.add_argument("--base", type=int, default=None)
    item.add_argument("-o", "--output", type=Path, default=None)

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
    args = build_parser().parse_args(argv)
    levels = LevelIndex(args.export_dir)
    if args.cmd == "inspect":
        return cmd_inspect(args.savefile, levels)
    if args.cmd == "warp":
        return cmd_warp(args.savefile, levels, args)
    if args.cmd == "set":
        return cmd_set(args.savefile, levels, args)
    if args.cmd == "item":
        return cmd_item(args.savefile, levels, args)
    if args.cmd == "verify":
        return cmd_verify(args.savefile, levels)
    if args.cmd == "diff":
        return cmd_diff(args.a, args.b, levels)
    if args.cmd == "gui":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from save_editor_gui import run_gui

        return run_gui(args.savefile, args.export_dir)
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
