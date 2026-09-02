# -*- coding: utf-8 -*-
"""Parse a Pathways Into Darkness Maps data fork.

Layout is formats/pid_level.ksy. This module is written from the
confirmed byte layout, not transcribed from third-party source.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

RECORD_SIZE = 16834
HEADER_SIZE = 450
SECTOR_COUNT = 1024
SECTOR_SIZE = 16
GRID = 32

WALL_TYPES = frozenset({0, 1, 32, 33, 64, 96, 128, 160})
SECTOR_TYPES = frozenset(range(10))

WALL_TYPE_NAME = {
    0: "none",
    1: "switchable_corner",
    32: "wall",
    33: "wall_fancy_corners",
    64: "wall_short_low",
    96: "wall_short_high",
    128: "wall_short_both",
    160: "cutoff_corner",
}

SECTOR_TYPE_NAME = {
    0: "void",
    1: "normal",
    2: "door",
    3: "change_level",
    4: "door_trigger",
    5: "secret_door",
    6: "corpse",
    7: "pillar",
    8: "other_trigger",
    9: "save",
}

LEVEL_CHANGE_TYPE_NAME = {
    -1: "unused",
    0: "upward",
    1: "downward",
    2: "secret_downward",
    3: "secret_upward",
    4: "undocumented_4",
}

DOOR_DIRECTION_NAME = {
    0: "x_negative",
    1: "y_negative",
    2: "x_positive",
    3: "y_positive",
}


@dataclass(frozen=True)
class PidDoor:
    x: int
    y: int
    direction: int
    texture: int


@dataclass(frozen=True)
class PidLevelChange:
    type: int
    level: int
    x: int
    y: int


@dataclass(frozen=True)
class PidMonster:
    type: int
    frequency: int


@dataclass(frozen=True)
class PidWall:
    type: int
    texture: int


@dataclass(frozen=True)
class PidSector:
    walls: tuple[PidWall, ...]
    item: int
    type: int
    type_addl: int


@dataclass(frozen=True)
class PidLevel:
    name: str
    name_unused: bytes
    level_number: int
    height10: int
    unknown1: tuple[int, int]
    texture_list: tuple[int, ...]
    door_list: tuple[PidDoor, ...]
    level_change_list: tuple[PidLevelChange, ...]
    monster_list: tuple[PidMonster, ...]
    sector_list: tuple[PidSector, ...]

    def sector_xy(self, index: int) -> tuple[int, int]:
        return index % GRID, index // GRID

    def sector_at(self, x: int, y: int) -> PidSector:
        return self.sector_list[y * GRID + x]


def _pascal_name(record: bytes) -> tuple[str, bytes]:
    length = record[0]
    if length > 127:
        raise ValueError(f"name length {length} exceeds 127-byte payload")
    name = record[1 : 1 + length].decode("mac_roman")
    unused = record[1 + length : 128]
    return name, unused


def parse_level(record: bytes) -> PidLevel:
    if len(record) != RECORD_SIZE:
        raise ValueError(f"record size {len(record)} != {RECORD_SIZE}")
    name, unused = _pascal_name(record)
    level_number = struct.unpack_from(">i", record, 0x80)[0]
    height10 = struct.unpack_from(">h", record, 0x84)[0]
    unknown1 = struct.unpack_from(">2i", record, 0x86)
    texture_list = struct.unpack_from(">8h", record, 0x8E)
    doors = []
    pos = 0x9E
    for _ in range(15):
        x, y, direction, texture = struct.unpack_from(">4h", record, pos)
        doors.append(PidDoor(x, y, direction, texture))
        pos += 8
    changes = []
    for _ in range(20):
        typ, level, x, y = struct.unpack_from(">4h", record, pos)
        changes.append(PidLevelChange(typ, level, x, y))
        pos += 8
    monsters = []
    for _ in range(3):
        typ, freq = struct.unpack_from(">2h", record, pos)
        monsters.append(PidMonster(typ, freq))
        pos += 4
    if pos != HEADER_SIZE:
        raise ValueError(f"header ended at {pos}, expected {HEADER_SIZE}")
    sectors = []
    for i in range(SECTOR_COUNT):
        off = HEADER_SIZE + i * SECTOR_SIZE
        walls = []
        for w in range(6):
            wtype, wtex = record[off + w * 2], record[off + w * 2 + 1]
            walls.append(PidWall(wtype, wtex))
        item = struct.unpack_from(">h", record, off + 12)[0]
        stype = record[off + 14]
        saddl = record[off + 15]
        sectors.append(PidSector(tuple(walls), item, stype, saddl))
    return PidLevel(
        name=name,
        name_unused=unused,
        level_number=level_number,
        height10=height10,
        unknown1=(unknown1[0], unknown1[1]),
        texture_list=texture_list,
        door_list=tuple(doors),
        level_change_list=tuple(changes),
        monster_list=tuple(monsters),
        sector_list=tuple(sectors),
    )


def parse_maps(data: bytes) -> list[PidLevel]:
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(f"file size {len(data)} is not a multiple of {RECORD_SIZE}")
    count = len(data) // RECORD_SIZE
    return [parse_level(data[i * RECORD_SIZE : (i + 1) * RECORD_SIZE]) for i in range(count)]


def load_maps(path: Path) -> list[PidLevel]:
    return parse_maps(path.read_bytes())
