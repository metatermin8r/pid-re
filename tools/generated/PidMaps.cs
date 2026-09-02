// This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild

using Kaitai;
using System.Collections.Generic;

namespace Pid.Formats
{
    public partial class PidMaps : KaitaiStruct
    {
        public static PidMaps FromFile(string fileName)
        {
            return new PidMaps(new KaitaiStream(fileName));
        }


        public enum DoorDirection
        {
            XNegative = 0,
            YNegative = 1,
            XPositive = 2,
            YPositive = 3,
        }

        public enum LevelChangeType
        {
            Unused = -1,
            Upward = 0,
            Downward = 1,
            SecretDownward = 2,
            SecretUpward = 3,
            Undocumented4 = 4,
        }

        public enum MonsterType
        {
            None = -1,
            Nightmare = 0,
            Headless = 1,
            Phantasm = 2,
            Ghoul = 3,
            Zombie = 4,
            Ooze = 5,
            Wraith = 6,
            ShockingSphere = 7,
            BlueMeanie = 8,
            Barney = 9,
            Skitter = 10,
            Sentinel = 11,
            Ghast = 12,
            GreenOoze = 13,
            Demon = 14,
            GreaterNightmare = 15,
            VenomousSkitter = 16,
        }

        public enum SectorType
        {
            Void = 0,
            Normal = 1,
            Door = 2,
            ChangeLevel = 3,
            DoorTrigger = 4,
            SecretDoor = 5,
            Corpse = 6,
            Pillar = 7,
            OtherTrigger = 8,
            Save = 9,
        }

        public enum WallType
        {
            None = 0,
            SwitchableCorner = 1,
            Wall = 32,
            WallFancyCorners = 33,
            WallShortLow = 64,
            WallShortHigh = 96,
            WallShortBoth = 128,
            CutoffCorner = 160,
        }
        public PidMaps(KaitaiStream p__io, KaitaiStruct p__parent = null, PidMaps p__root = null) : base(p__io)
        {
            m_parent = p__parent;
            m_root = p__root ?? this;
            _read();
        }
        private void _read()
        {
            _levels = new List<PidLevel>();
            {
                var i = 0;
                while (!m_io.IsEof) {
                    _levels.Add(new PidLevel(m_io, this, m_root));
                    i++;
                }
            }
        }
        public partial class PidDoor : KaitaiStruct
        {
            public static PidDoor FromFile(string fileName)
            {
                return new PidDoor(new KaitaiStream(fileName));
            }

            public PidDoor(KaitaiStream p__io, PidMaps.PidLevel p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _x = m_io.ReadS2be();
                _y = m_io.ReadS2be();
                _direction = ((PidMaps.DoorDirection) m_io.ReadS2be());
                _texture = m_io.ReadS2be();
            }
            private short _x;
            private short _y;
            private DoorDirection _direction;
            private short _texture;
            private PidMaps m_root;
            private PidMaps.PidLevel m_parent;
            public short X { get { return _x; } }
            public short Y { get { return _y; } }
            public DoorDirection Direction { get { return _direction; } }
            public short Texture { get { return _texture; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps.PidLevel M_Parent { get { return m_parent; } }
        }
        public partial class PidLevel : KaitaiStruct
        {
            public static PidLevel FromFile(string fileName)
            {
                return new PidLevel(new KaitaiStream(fileName));
            }

            public PidLevel(KaitaiStream p__io, PidMaps p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _nameLen = m_io.ReadU1();
                _name = m_io.ReadBytes(NameLen);
                _nameUnused = m_io.ReadBytes(127 - NameLen);
                _levelNumber = m_io.ReadS4be();
                _height10 = m_io.ReadS2be();
                _unknown1 = new List<int>();
                for (var i = 0; i < 2; i++)
                {
                    _unknown1.Add(m_io.ReadS4be());
                }
                _textureList = new List<short>();
                for (var i = 0; i < 8; i++)
                {
                    _textureList.Add(m_io.ReadS2be());
                }
                _doorList = new List<PidDoor>();
                for (var i = 0; i < 15; i++)
                {
                    _doorList.Add(new PidDoor(m_io, this, m_root));
                }
                _levelChangeList = new List<PidLevelChange>();
                for (var i = 0; i < 20; i++)
                {
                    _levelChangeList.Add(new PidLevelChange(m_io, this, m_root));
                }
                _monsterList = new List<PidMonster>();
                for (var i = 0; i < 3; i++)
                {
                    _monsterList.Add(new PidMonster(m_io, this, m_root));
                }
                _sectorList = new List<PidSector>();
                for (var i = 0; i < 1024; i++)
                {
                    _sectorList.Add(new PidSector(m_io, this, m_root));
                }
            }
            private byte _nameLen;
            private byte[] _name;
            private byte[] _nameUnused;
            private int _levelNumber;
            private short _height10;
            private List<int> _unknown1;
            private List<short> _textureList;
            private List<PidDoor> _doorList;
            private List<PidLevelChange> _levelChangeList;
            private List<PidMonster> _monsterList;
            private List<PidSector> _sectorList;
            private PidMaps m_root;
            private PidMaps m_parent;
            public byte NameLen { get { return _nameLen; } }
            public byte[] Name { get { return _name; } }
            public byte[] NameUnused { get { return _nameUnused; } }
            public int LevelNumber { get { return _levelNumber; } }
            public short Height10 { get { return _height10; } }
            public List<int> Unknown1 { get { return _unknown1; } }
            public List<short> TextureList { get { return _textureList; } }
            public List<PidDoor> DoorList { get { return _doorList; } }
            public List<PidLevelChange> LevelChangeList { get { return _levelChangeList; } }
            public List<PidMonster> MonsterList { get { return _monsterList; } }
            public List<PidSector> SectorList { get { return _sectorList; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps M_Parent { get { return m_parent; } }
        }
        public partial class PidLevelChange : KaitaiStruct
        {
            public static PidLevelChange FromFile(string fileName)
            {
                return new PidLevelChange(new KaitaiStream(fileName));
            }

            public PidLevelChange(KaitaiStream p__io, PidMaps.PidLevel p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _type = ((PidMaps.LevelChangeType) m_io.ReadS2be());
                _level = m_io.ReadS2be();
                _x = m_io.ReadS2be();
                _y = m_io.ReadS2be();
            }
            private LevelChangeType _type;
            private short _level;
            private short _x;
            private short _y;
            private PidMaps m_root;
            private PidMaps.PidLevel m_parent;
            public LevelChangeType Type { get { return _type; } }
            public short Level { get { return _level; } }
            public short X { get { return _x; } }
            public short Y { get { return _y; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps.PidLevel M_Parent { get { return m_parent; } }
        }
        public partial class PidMonster : KaitaiStruct
        {
            public static PidMonster FromFile(string fileName)
            {
                return new PidMonster(new KaitaiStream(fileName));
            }

            public PidMonster(KaitaiStream p__io, PidMaps.PidLevel p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _type = ((PidMaps.MonsterType) m_io.ReadS2be());
                _frequency = m_io.ReadS2be();
            }
            private MonsterType _type;
            private short _frequency;
            private PidMaps m_root;
            private PidMaps.PidLevel m_parent;
            public MonsterType Type { get { return _type; } }
            public short Frequency { get { return _frequency; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps.PidLevel M_Parent { get { return m_parent; } }
        }
        public partial class PidSector : KaitaiStruct
        {
            public static PidSector FromFile(string fileName)
            {
                return new PidSector(new KaitaiStream(fileName));
            }

            public PidSector(KaitaiStream p__io, PidMaps.PidLevel p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _walls = new List<PidWall>();
                for (var i = 0; i < 6; i++)
                {
                    _walls.Add(new PidWall(m_io, this, m_root));
                }
                _item = m_io.ReadS2be();
                _type = ((PidMaps.SectorType) m_io.ReadU1());
                _typeAddl = m_io.ReadU1();
            }
            private List<PidWall> _walls;
            private short _item;
            private SectorType _type;
            private byte _typeAddl;
            private PidMaps m_root;
            private PidMaps.PidLevel m_parent;
            public List<PidWall> Walls { get { return _walls; } }
            public short Item { get { return _item; } }
            public SectorType Type { get { return _type; } }
            public byte TypeAddl { get { return _typeAddl; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps.PidLevel M_Parent { get { return m_parent; } }
        }
        public partial class PidWall : KaitaiStruct
        {
            public static PidWall FromFile(string fileName)
            {
                return new PidWall(new KaitaiStream(fileName));
            }

            public PidWall(KaitaiStream p__io, PidMaps.PidSector p__parent = null, PidMaps p__root = null) : base(p__io)
            {
                m_parent = p__parent;
                m_root = p__root;
                _read();
            }
            private void _read()
            {
                _type = ((PidMaps.WallType) m_io.ReadU1());
                _texture = m_io.ReadU1();
            }
            private WallType _type;
            private byte _texture;
            private PidMaps m_root;
            private PidMaps.PidSector m_parent;
            public WallType Type { get { return _type; } }
            public byte Texture { get { return _texture; } }
            public PidMaps M_Root { get { return m_root; } }
            public PidMaps.PidSector M_Parent { get { return m_parent; } }
        }
        private List<PidLevel> _levels;
        private PidMaps m_root;
        private KaitaiStruct m_parent;
        public List<PidLevel> Levels { get { return _levels; } }
        public PidMaps M_Root { get { return m_root; } }
        public KaitaiStruct M_Parent { get { return m_parent; } }
    }
}
