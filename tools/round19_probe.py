# -*- coding: utf-8 -*-
"""Quick dump: Type 2 / Type 4 / DoorList vs boxed arrivals on L7-15, L20, L24."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pid_level import GRID, load_maps  # noqa: E402
from round18_walls import SOLID_A, entry_points, nonvoid_coords, union_flood  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"

ACTION = {
    6: "Chain1",
    7: "Chain2",
    12: "Unknown_HHCC_1",
    13: "Unknown_HHCC_2",
    14: "CloseNgbrDoor_Flag",
    17: "Unknown_HHCC_3",
    24: "EndGame",
    128: "CloseNgbrDoor",
    129: "OpenNgbrDoor",
    130: "AlienPipes",
    131: "OpenNgbrDoor_Silver",
    132: "OpenNgbrDoor_Gold",
    134: "Unknown_NAL_1",
    135: "Unknown_NAL_2",
    136: "Unknown_WYS",
    137: "Unknown_LOS_1",
    138: "Unknown_LOS_2",
    139: "Unknown_LOS_3",
    141: "OpenNgbrDoor_Flag",
}


def n4(x, y):
    return [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]


def main() -> None:
    levels = load_maps(MAPS)
    for n in list(range(7, 16)) + [0, 1, 20, 24]:
        lv = levels[n]
        reach = union_flood(lv, SOLID_A)
        print(f"\n======== L{n:02d} {lv.name} nv={sum(1 for s in lv.sector_list if s.type != 0)} "
              f"reach={len(reach)} ========")
        print("DoorList (x!=-1):")
        for i, d in enumerate(lv.door_list):
            if d.x == -1 and d.y == -1:
                continue
            sec = lv.sector_at(d.x, d.y) if 0 <= d.x < 32 and 0 <= d.y < 32 else None
            st = f"type={sec.type} addl={sec.type_addl} Item={sec.item}" if sec else "?"
            print(f"  door[{i}] ({d.x},{d.y}) dir={d.direction} tex={d.texture} sector={st}")
        print("Type 2 Door sectors:")
        for i, s in enumerate(lv.sector_list):
            if s.type != 2:
                continue
            x, y = i % GRID, i // GRID
            tag = "R" if (x, y) in reach else "S"
            walls = ",".join(str(w.type) for w in s.walls)
            print(f"  ({x:2d},{y:2d}) {tag} Item={s.item:4d} addl={s.type_addl} walls={walls}")
        print("Type 4 DoorTrigger:")
        for i, s in enumerate(lv.sector_list):
            if s.type != 4:
                continue
            x, y = i % GRID, i // GRID
            tag = "R" if (x, y) in reach else "S"
            act = ACTION.get(s.type_addl, f"?{s.type_addl}")
            adj2 = []
            for nx, ny in n4(x, y):
                if 0 <= nx < 32 and 0 <= ny < 32 and lv.sector_at(nx, ny).type == 2:
                    adj2.append(f"({nx},{ny})addl={lv.sector_at(nx, ny).type_addl}")
            print(f"  ({x:2d},{y:2d}) {tag} Item={s.item:4d} addl={s.type_addl} {act} adj4_doors={adj2 or '-'}")
        print("Start set:")
        for x, y in entry_points(lv):
            s = lv.sector_at(x, y)
            walls = ",".join(str(w.type) for w in s.walls[:2])
            nbrs = []
            for nx, ny in n4(x, y):
                if 0 <= nx < 32 and 0 <= ny < 32:
                    ns = lv.sector_at(nx, ny)
                    nbrs.append(f"({nx},{ny})t={ns.type}a={ns.type_addl}")
            print(f"  ({x},{y}) type={s.type} Item={s.item} addl={s.type_addl} WY,WX={walls} nbrs={nbrs}")


if __name__ == "__main__":
    main()
