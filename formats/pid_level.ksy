# Pathways Into Darkness ? one Maps file record and the file that
# contains them. Layout confirmed against the v2.0 Maps data fork
# (25 * 16834 = 420850). Field knowledge from Petrich/Semmler
# documentation, rewritten here; do not treat this file as a copy of
# their header.
#
# Endian: big (68k). Text: Mac Roman Pascal strings.
# Generate:
#   kaitai-struct-compiler formats/pid_level.ksy -t python --outdir tools/generated
#   kaitai-struct-compiler formats/pid_level.ksy -t csharp --dotnet-namespace Pid.Formats --outdir tools/generated
meta:
  id: pid_maps
  title: Pathways Into Darkness Maps file
  endian: be
  ks-version: 0.11

seq:
  - id: levels
    type: pid_level
    repeat: eos

types:
  pid_level:
    seq:
      - id: name_len
        type: u1
      - id: name
        size: name_len
      - id: name_unused
        size: 127 - name_len
      - id: level_number
        type: s4
      - id: height10
        type: s2
      - id: unknown1
        type: s4
        repeat: expr
        repeat-expr: 2
      - id: texture_list
        type: s2
        repeat: expr
        repeat-expr: 8
      - id: door_list
        type: pid_door
        repeat: expr
        repeat-expr: 15
      - id: level_change_list
        type: pid_level_change
        repeat: expr
        repeat-expr: 20
      - id: monster_list
        type: pid_monster
        repeat: expr
        repeat-expr: 3
      - id: sector_list
        type: pid_sector
        repeat: expr
        repeat-expr: 1024

  pid_door:
    seq:
      - id: x
        type: s2
      - id: y
        type: s2
      - id: direction
        type: s2
        enum: door_direction
      - id: texture
        type: s2

  pid_level_change:
    seq:
      - id: type
        type: s2
        enum: level_change_type
      - id: level
        type: s2
      - id: x
        type: s2
      - id: y
        type: s2

  pid_monster:
    seq:
      - id: type
        type: s2
        enum: monster_type
      - id: frequency
        type: s2

  pid_wall:
    seq:
      - id: type
        type: u1
        enum: wall_type
      - id: texture
        type: u1

  pid_sector:
    seq:
      - id: walls
        type: pid_wall
        repeat: expr
        repeat-expr: 6
      - id: item
        type: s2
      - id: type
        type: u1
        enum: sector_type
      - id: type_addl
        type: u1

enums:
  door_direction:
    0: x_negative
    1: y_negative
    2: x_positive
    3: y_positive

  level_change_type:
    -1: unused
    0: upward
    1: downward
    2: secret_downward
    3: secret_upward
    4: undocumented_4

  monster_type:
    -1: none
    0: nightmare
    1: headless
    2: phantasm
    3: ghoul
    4: zombie
    5: ooze
    6: wraith
    7: shocking_sphere
    8: blue_meanie
    9: barney
    10: skitter
    11: sentinel
    12: ghast
    13: green_ooze
    14: demon
    15: greater_nightmare
    16: venomous_skitter

  wall_type:
    0: none
    1: switchable_corner
    32: wall
    33: wall_fancy_corners
    64: wall_short_low
    96: wall_short_high
    128: wall_short_both
    160: cutoff_corner

  sector_type:
    0: void
    1: normal
    2: door
    3: change_level
    4: door_trigger
    5: secret_door
    6: corpse
    7: pillar
    8: other_trigger
    9: save
