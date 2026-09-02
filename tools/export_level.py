# -*- coding: utf-8 -*-
"""Export a Pathways Into Darkness Maps record as Unity-import JSON.

Usage:
  python tools/export_level.py                 # all 25 levels → reference/export/
  python tools/export_level.py 0               # Ground Floor only
  python tools/export_level.py 0 out.json      # one file
  python tools/export_level.py --maps PATH     # other Maps fork
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from decrypt_scri import decrypt  # noqa: E402
from mac_containers import resources_of_type  # noqa: E402
from mac_text import decode_mac_roman  # noqa: E402
from pid_level import (  # noqa: E402
    GRID,
    DOOR_DIRECTION_NAME,
    LEVEL_CHANGE_TYPE_NAME,
    RECORD_SIZE,
    SECTOR_TYPE_NAME,
    WALL_TYPE_NAME,
    PidLevel,
    load_maps,
)

WALL_INDEX_NAME = (
    "wall_y",  # 0  north / -Y
    "wall_x",  # 1  west  / -X
    "corner_high_x_low_y",
    "corner_low_x_low_y",
    "corner_high_x_high_y",
    "corner_low_x_high_y",
)

MONSTER_NAME = {
    -1: "none",
    0: "nightmare",
    1: "headless",
    2: "phantasm",
    3: "ghoul",
    4: "zombie",
    5: "ooze",
    6: "wraith",
    7: "shocking_sphere",
    8: "blue_meanie",
    9: "barney",
    10: "skitter",
    11: "sentinel",
    12: "ghast",
    13: "green_ooze",
    14: "demon",
    15: "greater_nightmare",
    16: "venomous_skitter",
}


def _texture_slot(value: int) -> dict:
    if value < 0:
        return {"raw": value, "shape_id": None, "variation": None}
    return {
        "raw": value,
        "shape_id": (value & 0x0FFF) + 128,
        "variation": (value >> 12) & 0xF,
    }


def _is_empty_change(c) -> bool:
    return c.type == -1 and c.level == 0 and c.x == 0 and c.y == 0


def _is_live_change(c) -> bool:
    return (
        c.type in (0, 1, 2, 3)
        and 0 <= c.level <= 24
        and 0 <= c.x < GRID
        and 0 <= c.y < GRID
    )


def _used_door_indices(level: PidLevel) -> set[int]:
    return {s.type_addl for s in level.sector_list if s.type == 2}


def _used_change_indices(level: PidLevel) -> set[int]:
    return {s.type_addl for s in level.sector_list if s.type == 3}


def wall_json(w, index: int) -> dict:
    return {
        "index": index,
        "slot": WALL_INDEX_NAME[index],
        "type": w.type,
        "type_name": WALL_TYPE_NAME.get(w.type, f"unknown_{w.type}"),
        "texture": w.texture,
        "blocks_movement": w.type == 32,
    }


def sector_json(level: PidLevel, index: int) -> dict:
    sec = level.sector_list[index]
    x, y = index % GRID, index // GRID
    return {
        "index": index,
        "x": x,
        "y": y,
        "type": sec.type,
        "type_name": SECTOR_TYPE_NAME.get(sec.type, f"unknown_{sec.type}"),
        "type_addl": sec.type_addl,
        "item": sec.item,
        "walls": [wall_json(w, i) for i, w in enumerate(sec.walls)],
    }


def door_json(d, index: int, referenced: bool) -> dict:
    return {
        "index": index,
        "x": d.x,
        "y": d.y,
        "direction": d.direction,
        "direction_name": DOOR_DIRECTION_NAME.get(d.direction, f"?{d.direction}"),
        "texture": d.texture,
        "referenced_by_type2": referenced,
    }


def change_json(c, index: int, referenced: bool, src: PidLevel) -> dict:
    empty = _is_empty_change(c)
    live = _is_live_change(c)
    return {
        "index": index,
        "type": c.type,
        "type_name": LEVEL_CHANGE_TYPE_NAME.get(c.type, f"?{c.type}"),
        "source_level": src.level_number,
        "source_name": src.name,
        "dest_level": c.level,
        "dest_x": c.x,
        "dest_y": c.y,
        "empty": empty,
        "live": live,
        "referenced_by_type3": referenced,
    }


def monster_json(m, index: int) -> dict:
    return {
        "index": index,
        "type": m.type,
        "type_name": MONSTER_NAME.get(m.type, f"?{m.type}"),
        "frequency": m.frequency,
    }


def transition_graph(levels: list[PidLevel]) -> list[dict]:
    used = [_used_change_indices(lv) for lv in levels]
    edges = []
    for src in levels:
        for i, c in enumerate(src.level_change_list):
            if not _is_live_change(c):
                continue
            dest = levels[c.level] if 0 <= c.level < len(levels) else None
            dest_sec = None
            if dest is not None and 0 <= c.x < GRID and 0 <= c.y < GRID:
                ds = dest.sector_at(c.x, c.y)
                dest_sec = {
                    "type": ds.type,
                    "type_name": SECTOR_TYPE_NAME.get(ds.type, f"?{ds.type}"),
                    "item": ds.item,
                    "type_addl": ds.type_addl,
                }
            edges.append(
                {
                    "from_level": src.level_number,
                    "from_name": src.name,
                    "list_index": i,
                    "change_type": c.type,
                    "change_type_name": LEVEL_CHANGE_TYPE_NAME.get(c.type, f"?{c.type}"),
                    "to_level": c.level,
                    "to_name": dest.name if dest is not None else None,
                    "to_x": c.x,
                    "to_y": c.y,
                    "to_sector": dest_sec,
                    "referenced_by_source_type3": i in used[src.level_number],
                }
            )
    return edges


def arrivals_for(levels: list[PidLevel], dest_n: int) -> list[dict]:
    out = []
    for src in levels:
        for i, c in enumerate(src.level_change_list):
            if _is_live_change(c) and c.level == dest_n:
                out.append(
                    {
                        "x": c.x,
                        "y": c.y,
                        "from_level": src.level_number,
                        "from_name": src.name,
                        "list_index": i,
                        "change_type": c.type,
                        "change_type_name": LEVEL_CHANGE_TYPE_NAME.get(c.type, f"?{c.type}"),
                    }
                )
    return out


def scri_dialogue(raw: bytes) -> str:
    """XOR-decrypt, then keep the spoken lines after the keyword table."""
    plain = decrypt(raw, 2, 0)
    text = decode_mac_roman(plain).replace("\r", "\n")
    marker = text.find("STOP")
    if marker >= 0:
        text = text[marker + 4 :]
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    text = re.sub(r"[a-z]{16,}", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def corpses_json(levels: list[PidLevel], scri: dict[int, bytes] | None) -> list[dict]:
    out = []
    for lv in levels:
        for i, s in enumerate(lv.sector_list):
            if s.type != 6:
                continue
            rid = 128 + s.type_addl
            dialogue = None
            if scri is not None and rid in scri:
                dialogue = scri_dialogue(scri[rid])
            out.append(
                {
                    "level": lv.level_number,
                    "level_name": lv.name,
                    "x": i % GRID,
                    "y": i // GRID,
                    "item": s.item,
                    "type_addl": s.type_addl,
                    "scri_id": rid,
                    "dialogue": dialogue,
                }
            )
    return out


def level_json(level: PidLevel, levels: list[PidLevel] | None = None) -> dict:
    used_doors = _used_door_indices(level)
    used_changes = _used_change_indices(level)
    doc: dict = {
        "format": "pid_level_v1",
        "movement_rule": "{32}",
        "grid": GRID,
        "record_size": RECORD_SIZE,
        "level_number": level.level_number,
        "name": level.name,
        "height10": level.height10,
        "unknown1": list(level.unknown1),
        "texture_list": [_texture_slot(v) for v in level.texture_list],
        "doors": [
            door_json(d, i, i in used_doors) for i, d in enumerate(level.door_list)
        ],
        "level_changes": [
            change_json(c, i, i in used_changes, level)
            for i, c in enumerate(level.level_change_list)
        ],
        "monsters": [monster_json(m, i) for i, m in enumerate(level.monster_list)],
        "sectors": [sector_json(level, i) for i in range(len(level.sector_list))],
        "departures": [
            {
                "x": i % GRID,
                "y": i // GRID,
                "type_addl": s.type_addl,
                "item": s.item,
            }
            for i, s in enumerate(level.sector_list)
            if s.type == 3
        ],
        "saves": [
            {"x": i % GRID, "y": i // GRID, "item": s.item, "type_addl": s.type_addl}
            for i, s in enumerate(level.sector_list)
            if s.type == 9
        ],
    }
    if levels is not None:
        doc["arrivals"] = arrivals_for(levels, level.level_number)
    return doc


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_level(payload: dict, level: PidLevel) -> list[str]:
    errors: list[str] = []
    if payload["level_number"] != level.level_number:
        errors.append("level_number")
    if payload["name"] != level.name:
        errors.append("name")
    if payload["height10"] != level.height10:
        errors.append("height10")
    if payload["unknown1"] != list(level.unknown1):
        errors.append("unknown1")
    if len(payload["sectors"]) != len(level.sector_list):
        errors.append(f"sector count {len(payload['sectors'])}")
        return errors
    for i, sec in enumerate(level.sector_list):
        js = payload["sectors"][i]
        if js["type"] != sec.type or js["type_addl"] != sec.type_addl or js["item"] != sec.item:
            errors.append(f"sector {i} fields")
            break
        if js["x"] != i % GRID or js["y"] != i // GRID:
            errors.append(f"sector {i} xy")
            break
        for wi, w in enumerate(sec.walls):
            jw = js["walls"][wi]
            if jw["type"] != w.type or jw["texture"] != w.texture:
                errors.append(f"sector {i} wall {wi}")
                break
            if jw["blocks_movement"] != (w.type == 32):
                errors.append(f"sector {i} wall {wi} blocks_movement")
                break
        else:
            continue
        break
    for i, d in enumerate(level.door_list):
        jd = payload["doors"][i]
        if jd["x"] != d.x or jd["y"] != d.y or jd["direction"] != d.direction or jd["texture"] != d.texture:
            errors.append(f"door {i}")
            break
    for i, c in enumerate(level.level_change_list):
        jc = payload["level_changes"][i]
        if (
            jc["type"] != c.type
            or jc["dest_level"] != c.level
            or jc["dest_x"] != c.x
            or jc["dest_y"] != c.y
            or jc["source_level"] != level.level_number
        ):
            errors.append(f"change {i}")
            break
    for i, m in enumerate(level.monster_list):
        jm = payload["monsters"][i]
        if jm["type"] != m.type or jm["frequency"] != m.frequency:
            errors.append(f"monster {i}")
            break
    tex = payload["texture_list"]
    if len(tex) != len(level.texture_list):
        errors.append("texture_list count")
    else:
        for i, raw in enumerate(level.texture_list):
            if tex[i]["raw"] != raw:
                errors.append(f"texture {i}")
                break
            if raw >= 0 and tex[i]["shape_id"] != (raw & 0x0FFF) + 128:
                errors.append(f"texture {i} shape_id")
                break
    return errors


def validate_all(levels: list[PidLevel], outdir: Path, graph: list[dict], corpses: list[dict]) -> int:
    bad = 0
    for lv in levels:
        path = outdir / f"L{lv.level_number:02d}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        errs = validate_level(payload, lv)
        n_arrive = sum(1 for e in graph if e["to_level"] == lv.level_number)
        if len(payload.get("arrivals", [])) != n_arrive:
            errs.append(f"arrivals {len(payload.get('arrivals', []))} != {n_arrive}")
        if errs:
            bad += 1
            print(f"VALIDATE FAIL L{lv.level_number:02d}: {errs}")
        else:
            print(f"VALIDATE OK   L{lv.level_number:02d} {lv.name}")
    expected_corpses = sum(1 for lv in levels for s in lv.sector_list if s.type == 6)
    if len(corpses) != expected_corpses:
        bad += 1
        print(f"VALIDATE FAIL corpses.json count {len(corpses)} != {expected_corpses}")
    else:
        print(f"VALIDATE OK   corpses.json  n={len(corpses)}")
    if len(graph) != 118:
        bad += 1
        print(f"VALIDATE FAIL transition_graph edges {len(graph)} != 118")
    else:
        print(f"VALIDATE OK   transition_graph.json  edges={len(graph)}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("level", nargs="?", type=int, help="level number 0-24; omit for all")
    ap.add_argument("outfile", nargs="?", type=Path, help="output JSON path")
    ap.add_argument(
        "--maps",
        type=Path,
        default=ROOT / "data/hfs/Pathways_1995/Maps",
        help="Maps data-fork path",
    )
    ap.add_argument(
        "--outdir",
        type=Path,
        default=ROOT / "reference/export",
        help="directory for the all-levels export",
    )
    args = ap.parse_args()

    levels = load_maps(args.maps)
    if args.level is not None:
        if not (0 <= args.level < len(levels)):
            raise SystemExit(f"level {args.level} out of range 0..{len(levels) - 1}")
        payload = level_json(levels[args.level], levels)
        out = args.outfile or (args.outdir / f"L{args.level:02d}.json")
        write_json(out, payload)
        errs = validate_level(json.loads(out.read_text(encoding="utf-8")), levels[args.level])
        print(f"wrote {out}  sectors={len(payload['sectors'])} arrivals={len(payload['arrivals'])}")
        if errs:
            raise SystemExit(f"validate failed: {errs}")
        print("VALIDATE OK")
        return

    args.outdir.mkdir(parents=True, exist_ok=True)
    graph = transition_graph(levels)
    write_json(args.outdir / "transition_graph.json", graph)
    try:
        scri = resources_of_type(
            ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc",
            b"scri",
        )
    except Exception as exc:
        print(f"scri load failed ({exc}); corpses.json will have dialogue=null")
        scri = None
    corpses = corpses_json(levels, scri)
    write_json(args.outdir / "corpses.json", corpses)
    for lv in levels:
        payload = level_json(lv, levels)
        out = args.outdir / f"L{lv.level_number:02d}.json"
        write_json(out, payload)
        print(f"wrote {out.name}  {lv.name}")
    print(f"wrote {args.outdir / 'transition_graph.json'}  edges={len(graph)}")
    print(f"wrote {args.outdir / 'corpses.json'}  n={len(corpses)}")
    bad = validate_all(levels, args.outdir, graph, corpses)
    if bad:
        raise SystemExit(f"validation failed on {bad} check(s)")
    print("round-trip OK: every JSON field matches the parser")


if __name__ == "__main__":
    main()
