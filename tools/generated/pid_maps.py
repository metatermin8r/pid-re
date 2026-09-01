# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class PidMaps(KaitaiStruct):

    class DoorDirection(IntEnum):
        x_negative = 0
        y_negative = 1
        x_positive = 2
        y_positive = 3

    class LevelChangeType(IntEnum):
        upward = 0
        downward = 1
        secret_downward = 2
        secret_upward = 3

    class MonsterType(IntEnum):
        none = -1
        nightmare = 0
        headless = 1
        phantasm = 2
        ghoul = 3
        zombie = 4
        ooze = 5
        wraith = 6
        shocking_sphere = 7
        blue_meanie = 8
        barney = 9
        skitter = 10
        sentinel = 11
        ghast = 12
        green_ooze = 13
        demon = 14
        greater_nightmare = 15
        venomous_skitter = 16

    class SectorType(IntEnum):
        void = 0
        normal = 1
        door = 2
        change_level = 3
        door_trigger = 4
        secret_door = 5
        corpse = 6
        pillar = 7
        other_trigger = 8
        save = 9

    class WallType(IntEnum):
        none = 0
        switchable_corner = 1
        wall = 32
        wall_fancy_corners = 33
        wall_short_low = 64
        wall_short_high = 96
        wall_short_both = 128
        cutoff_corner = 160
    def __init__(self, _io, _parent=None, _root=None):
        super(PidMaps, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self
        self._read()

    def _read(self):
        self.levels = []
        i = 0
        while not self._io.is_eof():
            self.levels.append(PidMaps.PidLevel(self._io, self, self._root))
            i += 1



    def _fetch_instances(self):
        pass
        for i in range(len(self.levels)):
            pass
            self.levels[i]._fetch_instances()


    class PidDoor(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidDoor, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.x = self._io.read_s2be()
            self.y = self._io.read_s2be()
            self.direction = KaitaiStream.resolve_enum(PidMaps.DoorDirection, self._io.read_s2be())
            self.texture = self._io.read_s2be()


        def _fetch_instances(self):
            pass


    class PidLevel(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidLevel, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.name_len = self._io.read_u1()
            self.name = self._io.read_bytes(self.name_len)
            self.name_unused = self._io.read_bytes(127 - self.name_len)
            self.level_number = self._io.read_s4be()
            self.height10 = self._io.read_s2be()
            self.unknown1 = []
            for i in range(2):
                self.unknown1.append(self._io.read_s4be())

            self.texture_list = []
            for i in range(8):
                self.texture_list.append(self._io.read_s2be())

            self.door_list = []
            for i in range(15):
                self.door_list.append(PidMaps.PidDoor(self._io, self, self._root))

            self.level_change_list = []
            for i in range(20):
                self.level_change_list.append(PidMaps.PidLevelChange(self._io, self, self._root))

            self.monster_list = []
            for i in range(3):
                self.monster_list.append(PidMaps.PidMonster(self._io, self, self._root))

            self.sector_list = []
            for i in range(1024):
                self.sector_list.append(PidMaps.PidSector(self._io, self, self._root))



        def _fetch_instances(self):
            pass
            for i in range(len(self.unknown1)):
                pass

            for i in range(len(self.texture_list)):
                pass

            for i in range(len(self.door_list)):
                pass
                self.door_list[i]._fetch_instances()

            for i in range(len(self.level_change_list)):
                pass
                self.level_change_list[i]._fetch_instances()

            for i in range(len(self.monster_list)):
                pass
                self.monster_list[i]._fetch_instances()

            for i in range(len(self.sector_list)):
                pass
                self.sector_list[i]._fetch_instances()



    class PidLevelChange(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidLevelChange, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.type = KaitaiStream.resolve_enum(PidMaps.LevelChangeType, self._io.read_s2be())
            self.level = self._io.read_s2be()
            self.x = self._io.read_s2be()
            self.y = self._io.read_s2be()


        def _fetch_instances(self):
            pass


    class PidMonster(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidMonster, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.type = KaitaiStream.resolve_enum(PidMaps.MonsterType, self._io.read_s2be())
            self.frequency = self._io.read_s2be()


        def _fetch_instances(self):
            pass


    class PidSector(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidSector, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.walls = []
            for i in range(6):
                self.walls.append(PidMaps.PidWall(self._io, self, self._root))

            self.item = self._io.read_s2be()
            self.type = KaitaiStream.resolve_enum(PidMaps.SectorType, self._io.read_u1())
            self.type_addl = self._io.read_u1()


        def _fetch_instances(self):
            pass
            for i in range(len(self.walls)):
                pass
                self.walls[i]._fetch_instances()



    class PidWall(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(PidMaps.PidWall, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.type = KaitaiStream.resolve_enum(PidMaps.WallType, self._io.read_u1())
            self.texture = self._io.read_u1()


        def _fetch_instances(self):
            pass



