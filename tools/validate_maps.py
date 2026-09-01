# -*- coding: utf-8 -*-
"""Hard checks on a parsed Maps file (round 5 task 3)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import (  # noqa: E402
    GRID,
    SECTOR_TYPE_NAME,
    WALL_TYPES,
    load_maps,
)

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
OUT = ROOT / "reference" / "docs"


def main() -> None:
    levels = load_maps(MAPS)
    assert len(levels) == 25
    lines: list[str] = [f"levels={len(levels)}"]

    wall_bad: list[str] = []
    type_bad: list[str] = []
    addl_bad: list[str] = []
    dest_bad: list[str] = []
    dest_ok: list[str] = []

    for li, level in enumerate(levels):
        counts: Counter[int] = Counter()
        for si, sec in enumerate(level.sector_list):
            x, y = si % GRID, si // GRID
            loc = f"L{li}({level.name!r}) sec={si} ({x},{y})"
            for wi, wall in enumerate(sec.walls):
                if wall.type not in WALL_TYPES:
                    wall_bad.append(f"{loc} wall[{wi}] type={wall.type}")
            if sec.type not in range(10):
                type_bad.append(f"{loc} type={sec.type}")
            counts[sec.type] += 1
            if sec.type == 2 and sec.type_addl >= 15:
                addl_bad.append(f"{loc} Door TypeAddl={sec.type_addl} (>=15)")
            if sec.type == 3:
                if sec.type_addl >= 20:
                    addl_bad.append(
                        f"{loc} ChangeLevel TypeAddl={sec.type_addl} (>=20)"
                    )
                else:
                    dest = level.level_change_list[sec.type_addl]
                    if dest.level < 0 or dest.level > 24:
                        dest_bad.append(
                            f"{loc} dest_level={dest.level} "
                            f"chg={dest.type},{dest.level},{dest.x},{dest.y}"
                        )
                    else:
                        dest_name = levels[dest.level].name if dest.level < len(levels) else "?"
                        dest_ok.append(
                            f"{li:2d} {level.name!r} ({x:2d},{y:2d}) addl={sec.type_addl} "
                            f"-> L{dest.level} {dest_name!r} "
                            f"type={dest.type} xy=({dest.x},{dest.y})"
                        )
            if sec.type == 6 and sec.type_addl > 27:
                addl_bad.append(f"{loc} Corpse TypeAddl={sec.type_addl} (not 0-27)")

        lines.append(f"\n## {li:02d} {level.name}  height10={level.height10}  lv#={level.level_number}")
        lines.append(
            "  types: "
            + " ".join(
                f"{SECTOR_TYPE_NAME[t]}={counts[t]}" for t in range(10) if counts[t]
            )
        )
        lines.append(
            f"  save={counts[9]} corpse={counts[6]} change_level={counts[3]} "
            f"door={counts[2]} secret_door={counts[5]}"
        )

    report = [
        f"wall_type_violations: {len(wall_bad)}",
        *wall_bad,
        f"sector_type_violations: {len(type_bad)}",
        *type_bad,
        f"type_addl_violations: {len(addl_bad)}",
        *addl_bad,
        f"dest_level_violations: {len(dest_bad)}",
        *dest_bad,
        f"change_level_links: {len(dest_ok)}",
        *dest_ok,
        "",
        *lines,
        "",
    ]
    text = "\n".join(report) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "maps_validate.txt"
    dest.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
