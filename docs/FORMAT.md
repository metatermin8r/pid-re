# Pathways Into Darkness — file format specification

Phase 0 standalone spec. Every offset, field size, and type here has been
seen in the v2.0 bytes (or is marked as still open). Hypotheses stay in
**Open questions**. Dead ends stay in **Disproven**.

Kaitai: `formats/pid_level.ksy`. Hand parser: `tools/pid_level.py`.
Generated parsers: `tools/generated/pid_maps.py` (Python) and
`tools/generated/PidMaps.cs` (C#, Unity). Unity import JSON:
`tools/export_level.py`.

Per-file type/ID dumps: `reference/` (see `reference/INDEX.md`).
The narrative of how this was solved is `docs/JOURNAL.md`.

---

## What we have on disk

Local copies live under gitignored `data/`. These are observations about
*which files exist* and *which resource types/IDs they contain*, not a
Map-file struct layout.

| Label | Where | Notes |
|---|---|---|
| Demo | `data/extracted/PathwaysDemo/` | Loose app + Maps + Shapes + Sounds. `vers` 128 text includes `DEMO`. |
| Full v2.0 | `data/hfs/Pathways_1995/` | From `Pathways_1995.dsk`. `vers` 1 text includes `v2.0`. App data fork 213600 bytes (`cfrg`). Maps is a data-fork file (420850, no resource map). Art is `Shapes.rsrc` type `.256` ×50. Audio is `Sounds.rsrc` type `snd ` ×86. No `._*` sidecars; resource forks are `*.rsrc`. Full tree: `reference/hfs_inventory.txt`. |
| v1.1 floppies | `data/hfs/Pathways 1`–`3`, `Installer_Disk_*` | DiskCopy/HFS installer payloads, not a loose app+Maps tree. |
| Japanese | `data/hfs/PID_Japanese_*` | Installer payloads, not yet expanded to loose Maps. |
| v2.0 sit | `data/extracted/Pathways_-_2.0/` | Updaters only (68k/PPC + Shapes). |
| Trainers / guide | extracted sits + `data/hfs/Pathways_Extras/` | Includes fan `PIDMapReader` sources (local only). |

---

## Resource-fork inventory

`unar` on Windows wrote AppleDouble `.rsrc` sidecars (`magic 0x00051607`).
`extract_hfs.py` writes raw Resource Manager maps as `.rsrc`.
`tools/rsrc.py` accepts both.

### Application — demo (`Pathways into Darkness.rsrc`)

27 types. Custom (non-system) types seen: `scri` (18), `dpin` (1, 24258 bytes),
`påth` (1). Meaning not asserted.

`STR#` IDs: 128, 1000, 1001, 1002. **2018 and 2021 are absent** in the demo.

`CODE` IDs: 0–15.

### Application — v2.0 (`data/hfs/Pathways_1995/Pathways Into Darkness.rsrc`)

32 types. Also has `cfrg` (PPC fragment), `WDEF`, `STR ` (1).
Custom types seen: `scri` (30), `dpin` (1). `scri` is corpse
dialogue. `dpin` 128 is the save-file initialiser (see below).

`STR#` IDs observed: 128, 1000–1004, 2000–2021.

`STR#` is the published Resource Manager format (u16be count, then
Pascal strings). Decoded as Mac Roman. Full lists:
`reference/full_dump/strings/hfs__Pathways_1995__Pathways_Into_Darkness.rsrc.strings.md`

| ID | Count | Content (from the strings, not guessed) |
|---|---|---|
| 128 | 17 | Startup / missing-file / RAM / Saved Games errors |
| 1000 | 8 | Inventory action failures (`^1` / `^2` slots) |
| 1001 | 71 | Item examine / use text (weapons, crystals, bomb, …) |
| 1002 | 17 | Rest / save / bomb / beacon prompts |
| 1003 | 26 | Death messages (named monster types) |
| 1004 | 6 | Endings (escaped pyramid / bomb / beacon) |
| 2000 | 71 | Item *names* — same count as 1001 |
| 2001 | 17 | (see dump) |
| 2002 | 18 | (see dump) |
| 2003–2017 | various | UI / scoring / shorter lists |
| 2018 | 28 | Level names (resource-fork copy) |
| 2019 | 2 | Floor&Ceiling Textures / Plain Floors&Ceilings |
| 2020 | 5 | Demo file names (Demo Maps, Demo Shapes, …) |
| 2021 | 3 | Ground Floor, Charon Doesn't Make Change, Come And Take Your Medicine |

`STR#` 2000 and 1001 both have 71 entries. That is a count observation
only; pairing is not proven.

`CODE` IDs: 0–16 (one more segment than the demo).

The application also has a **data fork** (213600 bytes). Not opened yet.

### Reading the 68k / 68020 binary

The v2.0 application **contains 68020 instructions**. Observed encodings
include `EXTB.L` (`49 C0`), `MULU.L` (`4C 01 08 00`), and address-index
extensions with scale bits set. Any future disassembly must decode as
68020; a 68000 decoder will misread those sites.

Jump table: CODE 0, **355** entries of 8 bytes starting at offset 16.
Base is `A5+0x20`. Each entry is `{u16 routine offset, u16 3F3C, u16
segment, u16 A9F0}`. Entry index = `(displacement - 0x20 - 2) / 8`.
The table’s segment field is **+4 versus every segment header**; trust
the table, not the header. File offset of a routine = `4 + routine
offset`.

A function inventory of that decode lives at
`reference/docs/code/inventory/`: **771** functions across CODE 1–16
(355 jump-table entries, 416 internal), 46,024 instructions, 13
UNKNOWN sites, 2,249 call-graph edges, 232 A5 globals. Trap counts
match an independent even-offset A-line scan on all 17 CODE
resources. CODE 11 and CODE 15 are C runtime (`_doprnt`,
`ZEROBUFFER`, `DATAINIT`) and contain no game logic.

### Shapes

| Build | Types | IDs seen |
|---|---|---|
| Demo `Shapes.rsrc` | `.256` only | 128–131, 133, 148, 152–159, 190–192, 194 |
| v2.0 `Shapes.rsrc` | see dump | larger set; still dominated by `.256` |

`.256` is a four-character type code. Fan text `Ident256ShapeRsrcs.txt`
exists in the local docs zip; not copied here.

### Sounds

| Build | Types |
|---|---|
| Demo `Sounds.rsrc` | `snd ` ×32 |
| v2.0 `Sounds.rsrc` | `snd ` ×86 |

v2.0: all 86 parse as Sound Manager **format 1**, `stdSH`, 8-bit mono PCM.
None are format 2, `extSH`, or compressed (`cmpSH`). Sample rates are the
classic Mac clocks: 72 at 11127.3 Hz, 14 at 22254.5–22257.0 Hz. Durations
0.040 s (10630) to 4.739 s (10720). Extracted to `reference/sounds/snd_<id>.wav`
by `tools/extract_sounds.py`. Report: `reference/docs/sounds.txt`.

### Maps (data fork)

No resource map. Sizes:

| Build | Path | Bytes | Bytes / 0x41C2 |
|---|---|---|---|
| Demo | `data/extracted/PathwaysDemo/.../Maps` | 50502 | **3** |
| v2.0 | `data/hfs/Pathways_1995/Maps` | 420850 | **25** |

`0x41C2` (16834) is not invented: every harvested level name in both
files sits at `i * 0x41C2`, and both file sizes divide evenly by that
stride. See `reference/full_dump/MAPS_STRINGS.md`.

Machine-readable spec: `formats/pid_level.ksy`. Parser: `tools/pid_level.py`.
Kaitai-generated Python: `tools/generated/pid_maps.py`. Kaitai-generated
C#: `tools/generated/PidMaps.cs` (namespace `Pid.Formats`; needs NuGet
`KaitaiStruct.Runtime.CSharp`). JSON export: `tools/export_level.py`.

Field knowledge comes from Petrich/Semmler (`PIDMapReader.h` / Torch,
CD extras). Their **code** is not in this repo. Offsets below were
checked against the v2.0 Maps bytes and against
`reference/docs/sector_types_sqr.png` (100% sector-type agreement on
all 25 levels, 4 px/sector, origin 16, pitch 144).

### Record header (450 bytes)

| Offset | Type | Field |
|---|---|---|
| 0x00 | u8 + 127 payload | Pascal name in a 128-byte slot. Unused tail is leftover text (record 0 still has `o Darkness…`). |
| 0x80 | i32be | `level_number` (0..24, matches file order) |
| 0x84 | i16be | `height10` (metres × 10). HUD depth readout only. All 25 match Hex reps_notes **by name**. Record 24 is −32768. The 3D path never reads this word. |
| 0x86 | i32be × 2 | `unknown1`. High words are 0; low words vary. Unknown. No runtime effect observed (Semmler / Torch). Not any tested checksum (u16 sum / XOR / byte-sum / CRC-16 CCITT / CRC-16 IBM). Deprioritised. |
| 0x8E | i16be × 8 | `texture_list`. −1 = none. Low 12 bits + 128 = `.256` id (loader `ADD.W #$0080` confirms). High 4 bits = variation 0–3 (all four occur). Slot 0 is always walls (192/193/194). Slots 5–7 are often −1. Slot 7 is **never** set. No slot maps to floor/ceiling resources 195–202. |
| 0x9E | 15 × 8 | `door_list`: i16 x, y, direction (0–3), texture |
| 0x116 | 20 × 8 | `level_change_list`: i16 type, dest level, dest x, y. `x,y` is the drop tile on the dest level, not the departure. |
| 0x1B6 | 3 × 4 | `monster_list`: i16 type, frequency |
| 0x1C2 | 1024 × 16 | `sector_list` |

An earlier hex dump that put `0x41d9` at 0x84 was misaligned. Height10
at 0x84 is 0 for Ground Floor.

The 3D renderer never reads `height10`. The only consumer is a text
formatter at CODE 3 @8762 (LINK `A6,#$FE86`). It loads the word from
the live level record at `-$1A82(A5)+$84`, does `DIVS.W #10`, `SWAP`s
for the tenths remainder, calls `jsr $a7a(a5)` (absolute value), and
draws the string (`_DrawString` A-line `$A884`). It is the HUD depth
readout in metres and tenths, not the world’s vertical scale.

`unknown1` is **not** uncleared name-slot garbage: the values change
with the level.

Level-change `type` 4 appears (But Wait → Ground Floor). The ksy enum
stores it as `undocumented_4`; meaning is unknown. Unused slots are
`type = -1`.

Sector index is **row-major**: `i = y*32 + x`, x right, y down. Ground
Floor under that rule is a T with the stem south, matching the
published map. Transpose (`i = x*32 + y`) rotates the T onto its side
(stem east) and is wrong. Confirmed by `reference/levels/L00_rowmajor.png`
vs `L00_transposed.png`.

### Sector wall model (six WallList slots)

Each 16-byte sector stores **six** 16-bit shape descriptors
(see **Shape descriptor**). They are not two independent type/texture
bytes. Offsets and roles:

| Off | Slot | Face |
|---|---|---|
| `+0` (0) | 0 | north edge (Y=0) |
| `+2` (2) | 1 | west edge (X=0) |
| `+4` (4) | 2 | NE corner diagonal |
| `+6` (6) | 3 | NW corner diagonal |
| `+8` (8) | 4 | SE corner diagonal |
| `+$A` (10) | 5 | SW corner diagonal |

South and east edges are the **neighbouring** cell’s slot 0 and slot 1.

The renderer’s four emit gates (CODE 5 @12188 / @12248 / @12292 /
@12336) read the **current** cell’s slots 3, 5, 2, 4 with dir 4, 6, 5,
7. The @12740 path reads neighbour slots 0/1 via a 4-entry table at
A5 `-$179E` (6046) = `{3, 2, 0, 1}`, indexed by void-neighbour
direction. JT 155 (CODE 4 @1566) maps dir to word:

| dir | word |
|---|---|
| 0 | current `+$2` (2) (W) |
| 1 | south neighbour `+0` (this S) |
| 2 | east neighbour `+$2` (2) (this E) |
| 3 | current `+0` (N) |
| 4 | slot 3 |
| 5 | slot 2 |
| 6 | slot 5 |
| 7 | slot 4 |

Corner words are emitted **before** the void skip, so void cells
contribute chamfers though they draw no floor.

Only slots 0 and 1 are movement walls. This is the stored-edge model,
not four independent walls per tile.

| Index | Petrich name | Role |
|---|---|---|
| 0 | `Wall_Y` | own north / −Y edge |
| 1 | `Wall_X` | own west / −X edge |
| 2 | `Corner_HighX_LowY` | corner. Never blocks. |
| 3 | `Corner_LowX_LowY` | corner. Never blocks. |
| 4 | `Corner_HighX_HighY` | corner. Never blocks. |
| 5 | `Corner_LowX_HighY` | corner. Never blocks. |

Petrich’s names are correct. Semmler’s Torch line “Wall X is top,
Wall Y is left” is **transposed**: treating slot 1 as north and slot
0 as west breaks Ground Floor (178 / 214 reachable; the T collapses).

The assignment is not a naming preference. It was brute-forced over
all 30 ordered slot pairs and all 4 direction conventions (N/W, S/E,
N/E, S/W) on those pairs (`tools/round22_slots.py`,
`tools/round23_dirs.py`). The only combination that keeps Ground
Floor 214 / 214 as a T (stem south at x≈15–17, bar north at x=4–28),
keeps L3 / L4 Type 5 secret closets sealed, and does not invent
phantom corridors is **slots (0, 1) as N / W**.

Census over all 25600 sectors:

| Slot | types 32+33 | type 160 | other non-zero |
|---|---|---|---|
| 0 | 12205 | 0 | 1, 64, 96, 128 |
| 1 | 12177 | 0 | 1, 64, 96, 128 |
| 2–5 | **0** | 1807–1856 each | type 1 only (1024, L13) |

Slots 2–5 never hold a movement wall. Using any of them as an “edge”
is the same as having no barrier in that direction.

### Movement rule

`blocks_movement` is true only for wall type **32**. Everything else
on an edge is either a drawn face or generator / decoration data.

| Type | Name | Movement | Where it lives |
|---|---|---|---|
| 32 | `Wall` | **blocks** | edges 0 / 1 only |
| 33 | `Wall_FancyCorners` | **draw-only** | edges 0 / 1 only |
| 64 / 96 / 128 | short low / high / both | do not block | edges 0 / 1 |
| 1 | `SwitchableWallCorner` | not a collider | L13 only: 207 + 204 on edges, **1024 on every corner slot** (all 4096 corner slots; unique in the file). Not a maze-generator input — see **The Labyrinth (L13)** |
| 160 | `CutoffCorner` | decorative | slots 2–5 only |

Type 32 and type 33 form a **hard partition by level**. No level
mixes them on edges. That is an authoring-tool signature (two
wall-placement modes), not two textures for one wall type.

| Band | Levels | Edge solids | Short 64/96/128 | Theme |
|---|---|---|---|---|
| Surface / deep | 0–6, 16–24 | all **32** | used | ordinary masonry |
| Mid-pyramid | 7–15 | all **33** | **zero** | crystal walls (`.256` 194) |

Treating 33 as a collider shatters 7–15 (L9 → 324 components,
largest 7; L10 → 140, largest 43). That is not authored sealing.
Under `{32}`-only the arrival flood covers every non-Void tile on
the playable floors except L3 / L4 Type 5 secret closets (real
type-32 barriers). Extra components elsewhere are void-separated
islands, designed traps (L20), or the L24 credit graphic — not
shattered type-33 walls. L9 is 415 / 415, L10 is 574 / 574, stored
L13 is 525 / 525. Report: `reference/docs/phase0_table.txt`. Final
renders: `reference/levels/L00.png` … `L24.png`.

**The Labyrinth (L13) is authored.** The earlier “L13 = 202, corners
boxed” target treated type 33 as solid. Under the real `{32}`-only
rule the stored floor is **525 / 525** connected walkable (499 void,
521 normal, 4 authored change-level). There is **no** maze generator.

JT 164 rewrites all six wall words of all 1024 cells at load as
`(voidNeighbourFlag & 7) << 13 | $100 (256) | (rng & 1)`: tag from
void adjacency, selector fixed at 66, s1index a coin flip between 0
and 1. Only slots 0 and 1 receive the flag; slots 2–5 are written 0.
Cells on x=0 keep their stored slot-1 word and cells on y=0 keep
their stored slot-0 word (64 words total, all `$0000` (0)). There is
**no visible randomisation**: one bit of shape index on faces that
are mostly not drawn (tag 0). L13’s type-1
`SwitchableWallCorner` on all 4096 corner slots (plus 411 edge hits)
is unique in the file. Semmler: “used on The Labyrinth to change the
direction of walls.” That is not a runtime generator.

### Transition semantics

Arrival `(x, y)` for level N lives in the **source** level’s
`LevelChangeList`, not on the destination, **except on L13** (the
only level where transitions do not read from the source). A level’s
own Type 3 sectors are departures. Type 3 `type_addl` indexes that
list. Southmost-non-Void is not an entrance. Flood seeds = every live
entry with dest Level == N, plus the dest’s Type 9 saves.

L13 ends up with **eight** change-level cells: the four authored
corners (1,1), (30,1), (1,30), (30,30) with `type_addl` 0..3, plus
four promoted by @5266 at (2,1), (29,1), (2,30), (29,30) with the
same `type_addl`. Arrival is on the **promoted** cell, and the source
level’s change-list `.xy` is ignored: from L14 → (2,1), L12 → (29,1),
L15 → (2,30), L16 → (29,30).

`level_change_list`: 20 slots. Empty unused is `Type=-1, Level=0,
x=0, y=0` (368 slots). A few Type=-1 slots hold leftover dest
coords and are skipped. Live entries are Type 0–3 with dest level
0–24 and x,y on the 32-grid: **118 edges**. Type 4 is undocumented
(But Wait → Ground Floor). Graph: `reference/export/transition_graph.json`.

Ladders are two-way. Teleporters and traps are one-way. Happy
Happy’s north and south teleporters (`SecretDownward`) both drop
into the isolated 3×3 room on Don’t Get Poisoned (L20 (2,2), Items
210–218, no Type 3 exit) — a designed trap.

L24 (Ok, Who Else Wants Some?) is not a floor plan. Petrich’s
sector-type sheet draws a 1993 / snail credit graphic. Arrival is
(14,19) from L23, a 33-tile hub among 34 void-separated islands.

### Doors

`door_list` is at level `+$9E` (158), 15 × 8 bytes: x, y, direction,
texture. Type 2 `type_addl` is the `door_list` index (0–14).

Runtime **t3**: 15 slots × 4 bytes at A5 `-$1A86` `+$39C` (924).
`+0` command, `+2` position `0..$400` (1024). Initial state is
**authored per level** inside the 9112-byte (`$2398`) world image,
read wholesale by `FSRead`. There is no code initialiser.

Doors that ship **open** (position 0): L2[9], L4[0,1], L6[0,4–7],
L14[5,6], L18[5], L19[5]. All others ship at `$400` (1024), closed.

Ticker @15230: command 1 subtracts `(rate * dt)` toward 0; command 2
adds toward `$400` (1024) and clamps; command 0 or any other value is
ignored (@15270–@15280), so 0 is the stable freeze value.

Rates from a stride-16 table at A5 `-$8E0` (2272) indexed by
`door_list.texture`. JT 254 builds **two** descriptors from the row:
`face_s1` with tag 1, `cap_s1` with tag 4.

**`+0` is not the rate.** It reads 0, 0, 2, 2, 2, 1 on textures
0 / 1 / 3 / 4 / 5 / 6 and its meaning is UNKNOWN. The per-tick rate
is at `+$A` (10), duplicated at `+$C` (12) (open and close are equal
on every row). Texture 2 never appears in any level’s `door_list`.

| tex | +0 UNKNOWN | +2 face s1 | +4 cap s1 | +$A (10) rate | raw 16 |
|---|---|---|---|---|---|
| 0 | 0 | 12 | 13 | `$0C` (12) | `00 00 00 0C 00 0D 28 14 28 14 00 0C 00 0C 00 00` |
| 1 | 0 | 12 | 13 | `$0C` (12) | `00 00 00 0C 00 0D 28 14 28 14 00 0C 00 0C 00 00` |
| 3 | 2 | 9 | 10 | `$11` (17) | `00 02 00 09 00 0A 28 14 28 14 00 11 00 11 00 00` |
| 4 | 2 | 12 | 13 | `$11` (17) | `00 02 00 0C 00 0D 28 14 28 14 00 11 00 11 00 00` |
| 5 | 2 | 6 | 7 | `$11` (17) | `00 02 00 06 00 07 28 14 28 14 00 11 00 11 00 00` |
| 6 | 1 | 11 | 12 | `$19` (25) | `00 01 00 0B 00 0C 29 90 29 90 00 19 00 19 00 00` |

| texture | units/tick | 1024 / rate | seconds at 60 tick/s |
|---|---|---|---|
| 0, 1 | 12 | 85.33 ticks | 1.422 s |
| 3, 4, 5 | 17 | 61 ticks | 1.017 s |
| 6 | 25 | 41 ticks | 0.683 s |

**Collision.** A nibble-2 sector blocks iff position `> $200` (512)
or command `== 2`. JT 161 (CODE 4 @3690), `cmpi.w #$200` / `bgt`, so
**513 blocks and 512 passes.** Confirmed in game: at position 512 the
player walks through; at 513 the player is blocked. The player is a
point against the leaf: no collision radius and no `(1024 − position)`
term. Projectiles ignore doors entirely (@5450): a ray stops only on
nibble 0 (void) and nibble 7 (pillar). A closed door does not stop a
bullet. The automap explored flood (@10432) treats a door as opaque
only when position `> $200` (512).

Creature **pathing** uses the same `position > 512` / `command == 2`
predicate via JT 16 (CODE 1 @2444 / @2688), producing `$08` (8)
blocked or `$80` (128) open. The creature **walk write** path
(CODE 7 @6976 → JT 159) has no door test. **OPEN:** whether an
actively pursuing creature can walk through a door at position
`<= 512`. Not yet observed in game.

**Four operation mechanisms:**

1. **Proximity.** Adjacent nibble-4 trigger with `type_addl` 128
   (close), 129 (open), 131 (open if Silver Key id 34), 132 (open if
   Gold Key id 36), 141 (open if player `+$139`, i.e. carrying the
   Alien Gemstone), via @14142 which steps four neighbours and calls
   @15020 with the neighbour’s `type_addl` as the `door_list` index.
2. **Explicit index.** Trigger cases 12, 13 and 23 name door indices
   directly.
3. **Item use on a sector.** `type_addl` 130 with the Alien Pipes
   (id 33), handled by JT 214 CODE 6 @2844, opening doors 0 and 1.
   Requires **both** nibble 4 and `type_addl` 130. The Pipes are not
   consumed.
4. **Incremental subtraction.** L1 cases 7 and 8 each subtract `$199`
   (409) from door 0’s position, with no clamp. From 1024: one pull
   leaves 615 (still blocked), two leave 206 (passable). Two chains,
   both required.

Trigger `type_addl` 24 is **not** a door_list index. It is the level
exit: it sets player `+$52` (82), read by JT 72 to run the ending at
@6106. 130 and 141 are trigger sectors (Alien Pipes; gemstone-gated
door), not door sectors.

Every OpenNgbr* trigger on the 25 levels is 4-adjacent to exactly one
Type 2. Opening that door (ignore a type 32 when stepping onto or off
the Type 2) and re-flooding to a fixed point grows L11 / L12 / L14.
It does not move L7, L8, or L15: those Type 2 tiles sit in already-open
corridors. L9 / L10 / L13 have zero Type 2 and zero Type 4. Silver /
gold keys are progression gates (Welcome, Tasty Primate; Beware of
Low-Flying Nightmares), not extra-tile unlocks from the start set.
L1 cases 7 and 8 are not 4-adjacent to a door; Torch’s “door index 0”
matches L1.

Leaf geometry (slab, three quads, dir/anchor, screenshot confirmation)
is under **Rendering — door geometry**.

**Secret doors (nibble 5)** are a cut feature. Passage requires
`type_addl >= 4`. No site anywhere writes `type_addl >= 4` onto a
nibble-5 sector. All six authored instances have `type_addl < 4` and
are permanently impassable. Drawn as normal walls via @13440
(CODE 5 @17190 dispatch: nibble 5 → @17146 → @13440):

| Level | Cell |
|---|---|
| L3 | (15,6), (5,28), (8,28) |
| L4 | (23,29) |
| L5 | (21,23) |
| L14 | (3,28) |

L9 / L10 (and all of 7–15) use type 33 only. Those bytes mark drawn
faces. Light Phobic (L9 (9,17) scri 138) and Walter (L10 (14,14)
scri 139) sit in the main reachable blob. Item ids are not
contiguous `0..N` except on L13. Reports: `round19_doors.txt`,
`round20_arrive.txt`, `round21_walls.txt`, `round22_slots.txt`,
`round23_dirs.txt`, `round24_style.txt`.

### Sector (16 bytes) at `record + 450 + 16*i`

| Offset | Type | Field |
|---|---|---|
| 0 | 6 × (u8 type, u8 texture) | walls: Y, X, then four corners |
| 12 | i16be | item (−1 = none). **Head of a chain** into the 500-entry object table at world-state `+$03D8` (CODE 5 @17190: `rec = [-$1A86(A5)] + $03D8 + item*16`; descriptor at `rec+$08`; next at `rec+$0E`). `$000E` = next object in the same cell; `$FFFF` ends the chain; `$FFFE` is a free slot. Item 0 is a valid entry (9 pillars use it). Values are distinct per level and run 0..398. 376, 377, 378, 383, 393 unused on all 25. Shared across sector types. Object **positions live in save state**, not in Maps; a fresh game’s layout comes from `dpin` 128. |
| 14 | u8 | sector type 0–9 |
| 15 | u8 | type_addl |

Wall types seen: `{0, 1, 32, 33, 64, 96, 128, 160}` — 0 violations in
25600 sectors. Sector types 0–9 — 0 violations.

`type_addl`: Door < 15, ChangeLevel < 20, Corpse 0–27 except one
**200** on Where Only Fools Dare Tread (Torch: Carlos sprite).

Corpse `type_addl` N → `scri` id `128+N` (observed on every corpse
except 200).

STR# 2018 entries 0–24 match Maps record order. Entries 25–27
(Entrance To Hell, Search Me!, Carnage From Above) have no record.

Resource-fork names still differ in spelling (the / The, extra `!`).
Demo record 0 is `Pathways into Darkness…`, not Ground Floor.

### Enums (observed)

Wall type: `0` none, `1` switchable corner, `32` wall, `33` wall fancy
corners, `64` short low, `96` short high, `128` short both, `160` cutoff.

Sector type: `0` void, `1` normal, `2` door, `3` change-level, `4` door
trigger, `5` secret door, `6` corpse, `7` pillar, `8` other trigger,
`9` save.

Door direction: `0` −X, `1` −Y, `2` +X, `3` +Y.

Level-change type: `0` up, `1` down, `2` secret down, `3` secret up,
plus undocumented `4`.

Monster type (header list): `−1` none, `0` nightmare … `16` venomous
skitter (see `formats/pid_level.ksy`). Frequency pairing not verified.

---

### Shape descriptor (16-bit)

A `PID_Sector` `{u8 wall_type, u8 texture}` pair is **one** big-endian
word. CODE 5 @1618 (walls) and CODE 5 @1454 (objects / pillars) unpack
the same bit fields:

| Bits | Field |
|---|---|
| 0–6 | `s1` index within a `.256` resource |
| 7–12 | selector into the resource cache at `-$17B6(A5)` |
| 13–15 | tag, equal to `wall_type >> 5` |

Cache: 128 slots of **8** bytes `{u32 handle, u16 flags}`, allocated
`$400` at CODE 5 @108. Slot N holds `.256` resource **N+128**. The
selector is used as-is when tag == 6; otherwise the engine adds 64
before indexing (`$00(A0,D0.L*8)`). Tag 6 therefore selects slots 0–63
= resources 128–191 (the sprite resources). **No sector pair word in
any of the 25 levels has tag 6.** Tag 6 is the object / pillar path.

Jump table entry 184 (CODE 5 @1138) loads the cache on demand: loop 1
releases slots where flags bit 1 is set and bit 0 is clear; loop 2
loads slots where flags bit 0 is set and the handle is null, by JSR
to the `.256` loader at CODE 5 @4892.

Tag 0 is **never drawn**. Emit gate CODE 5 @12202 (`C2 40`) /
@12206 (`67 16`), testing `(w >> 13) & 7 == 0`. Four identical
gates for slots `$6` (6), `$A` (10), `$4` (4), `$8` (8). CODE 5
@13440 remaps tag 0 to 1 at @13488 for **placement only**, after
the emit gate has already rejected it. That remap does not cause
tag 0 to be drawn.

Per-band selector results, all 25 levels:

| Levels | selector | resource | texture bit 7 |
|---|---|---|---|
| 0–6 | 0 | 192 | clear |
| 7–15 | 2 | 194 | — |
| 16–24 | 1 | 193 | **SET** on all 15,230 drawn pairs |

@1454 (objects) reads s1 fields `+$0008`, `+$000A`, `+$000C` into three
output longs, plus a `$2000` bit from s1 `+$0002`. It does **no** s2
lookup. @1618 (walls) reads s1 `+$0004` and s1 `+$0006` as `<<4`
indices into s2.

**`$217F` (closed).** 4,101 pairs on levels 7–15 are exactly `$217F`
(8575): tag 1, selector 66, s1index 127, on 4101 faces. s1index 127
is out of range for a 14-entry shape directory and is not bounds
checked; it resolves 4064 bytes into the decompressed blob and lands
in pixel data. Never on a walkable/void boundary. Harmless; skip
rather than emulate.

Pillars are objects, not map geometry. They enter the per-cell draw
dispatcher at CODE 5 @17190 via the object chain from `sector+$C`
(12) through world `+$3D8` (984). That path reaches @1454, not the
wall path at @1618. In game they stand at the sector centre and
block movement; they do not fill the sector as a solid block.
Billboard vertical extents are @17522–@17650 **within** @17190, not
the label of the whole routine.

---

### `dpin` 128 (230676 bytes)

**`dpin` 128 is the save-file initialiser.** It is not a runtime
table and it is not “2,876 records of 80 bytes.” CODE 2 @9262 does
`GetResource('dpin', 128)`, `HLock`, then three `FSWrite` (`$A003`)
calls — **28,760** bytes from the start of the resource, **2,876**
bytes at file position 8, and **227,800** bytes from dpin offset
2,876 — then `ReleaseResource`. The handle is never stored in an
A5 global. 227,800 = 25 × 9,112.

Resource layout:

| Offset | Size | Contents |
|---|---|---|
| 0 | 2,876 | header (first u16be pair is `12`, `2876`) |
| 2,876 | 227,800 | 25 world-state blocks of 9,112 bytes |

The four captured v2.0 saves’ home blocks 0–24 are byte-identical
to `dpin` at offset `2,876 + N*9,112`. Open item 2 is **closed**.

`0x000c0b3c` as a u32 is not a directory pointer; it is that
`u16be 12, 2876` pair. An earlier stride scan that treated the
payload as 2,876 rows of 80 was fitting structure onto the 25
world-state images. Those notes remain under `reference/dpin_*.txt`
as the failed model.

`Sector.item` indexes the object table inside each 9,112-byte
block, not a row of this resource.

### `scri` 128–157

28 non-stub resources (128–155) and two 14-byte stubs (156, 157).
**No** level-name bytes appear in any `scri` blob (raw or Pascal).

Chuck Gray (1994) and Torch 0.9.1 docs both call these corpse-dialogue
scripts, not per-level logic. Do not map `scri 128+N` to level N.
Map a **corpse sector** to a script with `scri_id = 128 + TypeAddl`.

Corpse `TypeAddl` values are **globally unique** across all 25 levels
(Semmler, not per-level). 29 corpse sectors. The set is `{0..27}` plus
one `200` on Where Only Fools Dare Tread (Carlos). No repeats. Every
`0..27` is used once. `128 + TypeAddl` matches DeadScripts `scri N`
for all 28 in-range corpses. `TypeAddl=200` has no `scri 328`.

DeadScripts headings omit `129` and `135`. Both resources exist and
decrypt to dialogue: `129` (209 bytes) is Lock&Load SE “Cold Guy”
(`I’m cold, so cold …`); `135` is Ascension Joachim. They are not
unused. Stub `scri 156` has a heading but no corpse.

Derived decrypt (Gray was off by 2): skip the first **2** bytes, then
XOR the rest with `00 01 02 …` wrapping at 256. Confirmed: plaintext
`Who are you?  Am I dead?` sits in scri 128 after that transform.

- u16be at 0 equals the resource length because those two bytes are
  **not** XOR'd.
- Raw `04 04 06 0d` at 6..9 is ciphertext of `00 01 00 0a`.
- Raw `fhpb` at 10..13 decrypts to `nazi` (the other two groups are the
  same four-byte field under the same keystream).

Stubs 156/157 are 14 bytes; published “Mumble, mumble…” is not in 156.

Stubs do **not** share a 14-byte prefix with the bodies. They start
`00 00` and both contain `35 5c` at offset 8. First u16 is 0, not 14.

---

### Palettes (`clut`)

`clut` **256** (578 bytes) is **not** a palette. It is a Pascal / Mac
Roman string: the 1993 Bungie copyright notice, stored under type
`'clut'`.

The real palettes are `clut` 128–135: 128 bytes each.

| Field | Type | Observed |
|---|---|---|
| seed | u32be | 0 |
| flags | u16be | 0 |
| size | u16be | 14 (→ 15 colours) |
| entries | 15 × (u16 index, u16 R, u16 G, u16 B) | index 0..14; Mac 16-bit channel, 8-bit = value >> 8 |

Eight tables, matching eight `texture_list` slots. Variations observed
on maps are only 0–3, so `variation N → clut 128+N` is **not** 1:1 with
all eight tables. PNGs: `reference/palettes/clut_128.png` … `clut_135.png`.

### `.256` — art resources

50 resources in v2.0 `Shapes.rsrc`, IDs 128–137, 139–142, 148–167,
187–202. Packed bytes are **not** a header plus a raster. Offset 0
is a `u32be` decompressed size; offset 4 is the first opcode of a
compressed stream. The decoder was **read from the 68020
disassembly** of CODE 8 at offset 2206 (the `.256` loader’s
`(source, destination)` call) and is implemented in
`tools/decode_256.py`. It emits exactly the declared size on 50/50.
37/50 also consume the packed input in full; 13 stop when the
output is complete and leave an unread packed tail. That is the
original engine’s behaviour: the loop is copied from it.

Extractor: `tools/extract_256.py`. Per-tile PNGs:
`reference/docs/256/<id>/tile_<nn>_<w>x<h>.png`. Contact sheets:
`reference/docs/256/<id>_sheet.png`.

#### How it was solved

Four rounds of statistical modelling of the packed bytes all
failed: PackBits; five literal-default RLE variants keyed on the
high bit; “a byte already in the colour table is a literal”; and
“sections 1–3 are stored uncompressed.” Those models were pointed
at a stream of opcodes, which is why they produced geometric
high-bit histograms and why 196’s 0.4% expansion (32628 → 32768)
looked impossible for a per-literal opcode.

The working decoder was not inferred. The type literal
`2E 32 35 36` (`.256`) sits in CODE 5. Following that site to
`GetResource` and through the jump table lands on CODE 8 offset
2206. The routine is 88 bytes and a two-opcode loop; it is not
PackBits.

#### Decompression (CODE 8 @2206)

Read from the disassembly, not inferred. Instruction
correspondence: `MOVE.L (A2),D4` reads the size; `ADDQ.W #4,A3`
sets the stream start; `MOVE.B (A3)+,D0` fetches the opcode;
`CMPI.W #$0080,D0` / `BGE` splits the cases; `ADDQ.W #3,D0` is
the run bias; `SUBI.W #$007F,D0` the literal bias; `CMP.L D2,D4`
/ `BGT` loops while size > total.

```
size = read_u32be(src[0:4])       // NOT part of the stream
p = 4; out = []
while size > len(out):
    b = src[p]; p += 1
    if b < 0x80:                  // RUN
        n = b + 3                 // 3..130
        v = src[p]; p += 1
        out += [v] * n
    else:                         // LITERAL
        n = b - 0x7F              // 1..128
        out += src[p:p+n]; p += n
```

| control | meaning | consume | emit |
|---|---|---|---|
| `$00..$7F` (0..127) | repeat, `n = b + 3`, of the next byte | 2 | 3..130 |
| `$80..$FF` (128..255) | literal, `n = b - $7F` (127) | 1+n | 1..128 |

Stop when emitted >= the declared u32be at src+0. There is no skip
opcode, no transparent run, and no 16-bit length.

ANOMALY: 11,372 bytes of packed data remain after the declared
count is met on resource 192, starting `13 14 15 16`. Purpose
UNKNOWN. It is not missing tile data. 13/50 resources leave an
unread packed tail the same way; that is the engine’s stop
condition (`CMP.L D2,D4` / `BGT`).

There is no format tag, no 23-byte packed header, and no
raw/compressed boundary inside the resource. Packed offset 4 is
the first opcode. The four “malformed directories” (161 / 162 /
167 / 189) were short first literal runs.

#### Decompressed header — 18 bytes

Verified on all 50.

| Offset | Type | Field |
|---|---|---|
| 0x00 | u16be | tile count |
| 0x02 | u32be | v1 |
| 0x06 | u32be | v2 |
| 0x0A | u32be | v3 |
| 0x0E | u32be | v4 |

Sections: s0 = `[0x12, v1)`, s1 = `[v1, v2)`, s2 = `[v2, v3)`,
s3 = `[v3, v3+v4)`. Relations, 50/50:

- `tile_count == (v2 - v1) / 32` — tile count is the s1 record count
- `v3 + v4 == size` — v4 is the **length** of s3, not a fifth offset

s2 record count is `(v3 - v2) / 16` and is **not** always
`tile_count`. Iterate s2 by that quotient. Resource 192 has 22 s1
records and 23 s2 records; 193 gives 13, 194 gives 14, 195–202
give 2 (those match `tile_count`). s3 is not one raster: it is
the s2 rectangles plus align-4 padding between them.

| ID | tiles (s1) | s2 | v1 | v2 | v3 | v4 | first tiles (W×H) |
|---|---|---|---|---|---|---|---|
| 192 | 22 | 23 | 1944 | 2648 | 3016 | 182976 | 113×113, 113×85, 113×84 |
| 193 | 13 | 13 | 2616 | 3032 | 3240 | 100988 | 120×119, 120×90, 120×88 |
| 194 | 14 | 14 | 2072 | 2520 | 2744 | 180604 | 120×120, 120×120, 121×119 |
| 195–202 | 2 | 2 | 280 | 344 | 376 | 32768 | 128×128, 128×128 |

None of 192 / 193 / 194’s v4 values divide by 128. 195–202 are
the uniform case: two 128×128 images, 128×128×2 = 32768 = v4.
`[0x12, v1)` is byte-identical across those eight. 192’s extra
s2 record is tile 22 (113×84); that rectangle is the 9,492-byte
tail that a `tile_count`-only walk missed.

#### s0 — colour tables

Six bytes at 0x12, all 50: `u16be 0x0200`, `u16be` table count,
`u16be` entries per table. Tables begin at decompressed offset
**24**, first index **3**, stride **8** (Mac ColorSpec: `u16be`
index + three `u16be` channels; 8-bit = value >> 8). They sit at
fixed offsets counted **back from v1**: last table ends at v1 on
50/50. Enumerated table count matches `u16be@0x14` on 50/50.
Within one resource every table has the same first/last index.

| ID | tables | entries | first | last | last-end == v1 |
|---|---|---|---|---|---|
| 192 | 3 | 80 | 3 | 82 | yes (1944) |
| 193 | 4 | 81 | 3 | 83 | yes (2616) |
| 194 | 4 | 64 | 3 | 66 | yes (2072) |
| 195–202 | 2 | 16 | 3 | 18 | yes (280) |

Each resource has its **own** tables. Index values conflict
between resources. 192’s three tables cover the same 3–82 range
with different RGB. 195–202’s two tables both cover 3–18;
merging them produces 15 RGB conflicts. There is no global
256-entry palette.

`tools/extract_256.py` paints with table `(record_index %
table_count)`. That is a HYPOTHESIS for which table supplies RGB.
Coverage does not depend on which in-range table is chosen: every
table in a resource spans the same index range.

#### Reserved indices

Colour tables universally begin at index 3, so 0 / 1 / 2 are
reserved.

- **Index 2 is transparent.** With index 2 treated as alpha, **0/50**
  resources have unmapped pixels. Across the earlier 35 resources
  that showed “unmapped” bytes, every such byte was index 2.
- **Index 1 never appears** anywhere in s3.
- **Index 0 appears only as inter-tile padding**, never as a tile
  pixel: 485 bytes across all 50, exactly the padding total.

Resources with zero index-2 bytes are the opaque ones: 187–191,
193, 194, 195–202. Default extract writes RGBA with index 2 as
alpha 0. `--magenta` paints it opaque magenta instead.

#### s1 — 32 bytes per record, class tag (NOT geometry)

s1 does **not** hold pixel width, pixel height, or s3 offsets
(those are s2). A brute-force of every u16 pair as pixel dimensions
and every u16/u32 column as an s3 offset returned **0** passing
layouts (`sum(w×h)` plus align-4 equals v4 and the offsets
partition `[0, v4)`). Object s1 world-space width/height/lift live
at `+$8`/`+$A`/`+$C` (see **Billboards**).

`u16[0]` is a **class tag**. It selects how s2 is read. It is
**not** a palette selector: its range does not fit
`0 .. (table_count-1)` under any 0-based, 1-based, or modulo
reading.

| Class | Role | Resources |
|---|---|---|
| 1–5 | walls and floors | 192, 193 use `{1,2,3,4,5}`; 194 uses `{1,4}`; 195–202 use `{1}` |
| 6 | everything else | every record of 128–191 |

HYPOTHESIS: the specific values 1–5 mark scale or level-of-detail.
192’s first five tiles are 113×113, 113×85, 113×84, 113×57, 114×42
with class tags 1, 3, 2, 4, 5 — descending sizes of the same wall.
Not verified.

Object s1 (CODE 5 @1454): `+$8` (8) width, `+$A` (10) height,
`+$C` (12) lift. Billboard bottom = `view+$0C` (12) (−614) + lift.
Some class-6 records’ `i16[4]` / `i16[5]` are integer multiples of
that tile’s dimensions (`i16[4] == k * height`, `i16[5] == k *
width` on 128, 134, 141, 153, 155–161, 163, 165, 187–191). 192–202
have zeros there except the overlay group (see **Composited tiles**).
`i16[6]` is the lift (`-w/2` on 128 tile 0).

#### Composited tiles (s1 overlay)

s1 records 14–17 of resource 192 all point at s2[14] (113×113) and
carry an **overlay**: `u16[3]` names a second shape (s2 15/16/17/18,
each 49×48 of solid stone) and a u32be at s1 `+$E` (14) gives the
destination offset, 4423 (`$1147`) = `39*113 + 16`, rect
(16, 39)–(64, 88), 48×49.

CODE 5 @2030 tests s1 `+$6` (6) and blits via @42: long-copy,
width/4 longs per row, `dest_skip = 113 - 48 = 65`. **No
transparency test** — it is an unconditional paste. Before
compositing those tiles contain 2352 texels of index 2 in that
rect, emitted as 49 identical `2D 02` repeat runs, one per row.

This is a memory saving: four wall variants stored as one
12,769-byte base plus four 2,352-byte patches. It is **not** a
decoder bug — the RLE stream and the opcode table are both correct.
Export (`tools/export_256_indices.py` `native_plane`) applies the
blit. Across all 50 resources only these four s1 records have
`u16[3] != 0`.

`u16[2]` on 192 is the base s2 index (records 14–17 share
`u16[2]=14`).

163 s1 is a different shape (nonzero `u16[1]=8192` and later
words). Do not read sprite s1 with the wall overlay layout.

#### s2 — 16 bytes per record, geometry

`u32be` offset into s3, then two `u16be` dimensions, then 8 zero
bytes. Storage is **row-major** in both classes; the classes
record the two dimensions in opposite order. `extract_256.py`
selects the reading from `s1.u16[0]`, not from a hardcoded
resource ID.

| Class | Field order | Pixel `(x, y)` |
|---|---|---|
| 1–5 | `(offset, HEIGHT, WIDTH)` | `src[y * width + x]` |
| 6 | `(offset, WIDTH, HEIGHT)` | `src[y * width + x]` |

Class 1–5 is confirmed non-vacuously: 192 tiles 15–18 declare
`u16[2]=49`, `u16[3]=48` and they patch the hole in tile 14 that
is 48 wide and 49 tall. The overlay words only match in
row-major 113-wide coordinates.

Class 6 is confirmed by content. Square tiles cannot distinguish
`(h, w)` from `(w, h)`: 128 tile 25 (43×43 grey sentinel with a
lamp stack) and 129 tile 2 (101×101 one-eyed green creature)
render correctly under either order. Every non-square class-6
tile sheared under the class 1–5 order (horizontal correlation
kept, vertical destroyed). Under the class-6 order, 129 tile 12
is a standing creature, 187 tile 0 is an upright jungle /
pyramid landscape, 191 tile 0 is the readable “PATHWAYS INTO
DARKNESS” chrome logo, and 128 tile 1 is the 357×20 wordmark.
All four are sideways if class 6 is read as class 1–5, or if
class 6 is read column-major (that alternative is a diagonal
flip of the correct image; it also transposes the already-correct
squares). Class-6 resources reaching isotropy (mean vertical and
horizontal opaque-pixel correlation within 0.15): **1/39**
before the field-order fix, **34/39** after.

Applying the class-6 order to class 1–5 walls drops the control
group from 10/11 isotropic to 8/11 (192 and 194 shear; 195–202
are square and cannot show it). Do not use one field order for
both classes.

The leftover anisotropic class-6 resources are 131, 151, 155,
157, 163. 131 (wraith), 155 (ladders / floor rune), 157
(mushroom mounds / puddles), and 163 (two wide 8-point stars)
are recognisable; the remaining Δ is content. **151 tile 2
(105×39) is still sheared under both orders** — tiles 0 and 1
of that resource are coherent first-person gun barrels. That
tile is not fixed by the class tag.

#### Partition arithmetic — 50/50 PASS

`sum(width * height)` across all s2 records, plus align-4
padding **between tiles**, equals v4 exactly. The offsets
partition `[0, v4)` with no gaps and no overlaps. Padding is
after each rectangle, not after each row: 494/494 tiles have
`gap == align4(w * h)`. A stride sweep of declared width ±4
found no control-like vertical-correlation peak.

192 without the 23rd s2 record left 9,492 bytes (84×113) plus
align-4; that was an off-by-one in the walker, not a bad model.

#### Resource identification

Walls by level band: 192 (levels 0–6), 194 (7–15), 193 (16–24).
A `texture_list` index plus 128 is the resource ID. That rule
appears in the shipped loader as `ADD.W #$0080`, independently
of the data-side derivation Loren Petrich published in 2000.

Decorations: 153–167, referenced by `texture_list` slots 1–7.
Unreferenced by any level: 128–152, 187–191, 195–202.

Identified from rendered content:

| ID | What it is |
|---|---|
| 128 | Inventory / HUD art: wordmark, books, knife, chest, potion bottles, rug, lamp, M16, AK, shotgun, crystals, sentinel |
| 129 | One-eyed floating creature, walk / turn / death frames |
| 133 | Skeletal mummy with split headdress, walk and attack |
| 139 | Bulky humanoids, walk, attack, prone death |
| 151 | First-person weapon barrels |
| 163 | Two 8-point compass stars (177×40, 174×41) |
| 187 | Title landscape, jungle and stepped pyramid |
| 190 | Automap and compass: 34 8×8 glyphs (corridors, junctions, stairs, direction arrows) plus a 64×100 parchment compass |
| 191 | “PATHWAYS INTO DARKNESS” chrome logo, 401×101 |
| 195–202 | Two 128×128 tiles each, floor / ceiling shaped, not referenced by `texture_list`; selection mechanism unknown |

190, 128, 187 and 191 are art that published fan sprite rips do
not contain, consistent with those rips having been captured
from gameplay rather than extracted from the file.

#### Open questions (this type)

Pixel decoding, s2 geometry, class-dependent field order,
reserved index 2, the s3 partition, and **which s1 tile a wall
descriptor selects** (bits 0–6) are established. `$217F` is closed
(out-of-range s1index; skip). PID does **not** render floors or
ceilings as geometry (see **Rendering — floors and ceilings**);
`.256` 195–202 exist as art and are not referenced by
`texture_list`. s1 `+$8`/`+$A`/`+$C` (width / height / lift) are
under **Billboards**.

---

### Saved Games — file layout

v2.0 `Saved Games` is one file holding every named slot. File size is
**267,452 + (n_names − 1) × 9,112**. One name: 267,452. Two names:
276,564. r16 (more names) is 294,788. Creator `påth`. Names are
128-byte Pascal strings at `k*128`.

**2,876 is the player-record stride. 9,112 is the per-save file
growth. They are unrelated quantities.** Player record `k` lives at
file offset `k*2876`. File bytes `[0, 1780)` are the name table
(10 × 128 Pascal strings) and the 10 × 25 u16be block-index table
starting at `0x0500`. CODE 2 @9638 / @9704 `FSRead` / `FSWrite`s
those 1,780 bytes into A5 `-$1ADC`. They overlap record 0 on disk
but are **not** part of the player I/O blob.

The live island begins at `k*2876 + 0x06F4`. CODE 2 @9788 / @9872
`SetFPos` to that offset and `FSRead` / `FSWrite` 2,876 bytes
into / from A5 `-$1A8A`. The save blob is a raw dump of that
live player buffer. Mapping: `mem+d = file k*2876+0x06F4+d`
throughout — there is no separate serialisation. Inventory is
at live `+$33C` = file `+0x0A30`. File `+0x0A00` is live
`+$30C` (48 bytes of zeros), not the tree.

| Rel | Type | Field |
|---|---|---|
| +0x06F4 | u16be | 12 |
| +0x06F6 | u16be | 2876 |
| +0x06F8 | u16be | slot `k` |
| +0x06FA | u32be | counter (CODE 2 `ADD.L` to mem+6) |
| +0x06FE | u16be | player `+$0A` **points**. CODE 6 @8206 adds catalog w2 on pickup/drop. Shown live in the Progress panel as “scored %d of 41”. Catalog Map w2 is **0**; Gold Ingot w2 is 1. 1 on the one-name save and r16 k=3, 0 on the other seven — that 1 is not the Map. **Not** a boolean flag. |
| +0x0700 | u32be | player `+$0C` **treasure** accumulator. CODE 6 @8206 adds catalog w5. 0 on all nine captured records. |
| +0x0704–+0x0747 | — | zeros on all nine captured records |
| +0x0748 | u16be | dungeon argument. Load path pushes this into A5 `-$1AD8` via CODE 2 @8546. **0x0000 in all nine captured records.** Written together with `+0x074A` / `+0x074E`, this word **warps**: a save written for level 7 loaded a crystal-walled floor populated with ghouls (in-game test). |
| +0x074A | u32be | **live player X**, 10-bit fixed point |
| +0x074E | u32be | **live player Y**, 10-bit fixed point |
| +0x0752 | u16be | **live facing / yaw**. 512-unit circle (0..511). See below. |
| +0x0754 / +0x0756 | u16be | current / max HP. **Confirmed in game**: editing takes effect |
| +0x075A | 7 × 6 bytes | player `+$66`: weapon-proficiency records, keyed by STR# 2006 index 0..6. Each record is `u16be` rank (0 hidden, 1 Beginner, 2 Novice, 3 Expert) then `u32be` accumulated hit-damage. See Weapon proficiencies. |
| +0x07B2 | u32be | player `+$BE` total damage credited on hit (CODE 7 @16404 @17012) |
| +0x07B6 / +0x07CA | 5 × u32be | player `+$C2` / `+$D6`: shots fired / hits, keyed by the 5-entry weapon table at A5 `-$810` (not by STR# 2006 index) |
| +0x0826 | u8 | player `+$132` Infra-Red Goggles worn. See Worn gear |
| +0x0827 | u8 | player `+$133` Digital Watch worn |
| +0x0828 | u8 | player `+$134` Red Cloak worn |
| +0x0829 | u8 | player `+$135` Flashlight worn |
| +0x082A | u8 | player `+$136` Ruby Ring worn |
| +0x082B | u8 | player `+$137` Amethyst Ring worn |
| +0x0838 / +0x083A / +0x083C | u16be | player `+$144` / `+$146` / `+$148`: Cedar Box clone timer (armed to 3600), remembered item id, remembered word 2. See Cedar Box. |
| +0x0886 | u16be | player `+$192` ready-crystal slot (`$FFFF` = none). Yellow crystal is id 64. |
| +0x088C / +0x088E | u16be | player `+$198` ready-weapon slot / `+$19A` shot counter |
| +0x090C | u16be | level 0..24. **INERT** (confirmed in game: writing does nothing) |
| +0x0918 / +0x091A | u16be | integer X / Y 0..31. **INERT** (confirmed in game: writing does nothing) |
| +0x091C | u16be | holds 0, 1, 2, 12 across the nine captured records. **UNTESTED** — earlier text called this confirmed inert; it had never been edited. |
| +0x0A00 | 48 bytes | player `+$30C` through `+$339`. Zeros on the captured saves. **Not** the inventory. |
| +0x0A2E | u16be | player `+$33A`, inventory walk head (0 on all nine captured records — slot 0 is the Map). |
| +0x0A30 | 256 × 8 | player `+$33C`, inventory records. Same four-word tree as the live A5 array. First-word `$FFFF` ends a linear scan; the other six terminator bytes are leftover, not a record. |

`+0x074A` is **not** a game clock. That reading is disproven. The
values 6903, 6989, 6808, 6963, 6780, 7133, 6910, 6828 are X
coordinates (`raw >> 10` = 6 on every captured record). There is
no derived “113–119 seconds into play.” The four unique local
saves are still a pristine corpus because home blocks 0–24 are
byte-identical to `dpin` 128 `[2876 + N*9112]`, not because of
any time field.

Live X/Y use the object-table encoding: sector = `raw >> 10`
(`ASR.L #10`). The writer (CODE 2 @8762–8788) does `LSL.L #10`
then `ADD.L #$200` and stores the two longs at `(A4)` and
`$0004(A4)`. @8830 copies those eight bytes to player+0x56.
player+0x56 is file `k*2876 + 0x074A`. The player has **no stored Z
coordinate**: the live position is those two longs only. CODE 2
@8546 writes exactly eight position bytes (`MOVE.L (A1)+,(A0)+`
twice). Confirmed in game: editing `+0x074A` teleports the player
on the same level, including into a wall — the load path writes
the position with no collision or sector check. `+0x0750` is the
low 16 bits of Y, not a separate field.

`+0x0752` is player+0x5E, the live facing. CODE 4 @1028 is an
arctangent that returns 0..511 against a table at A5 `-$1A96`.
CODE 4 @3836 does `SUB.W $5e(a0),d7` (angle minus facing). CODE 4
@4 (jump table 331) wraps into 0..511 by adding or subtracting
`$200`. **0 = west, 128 = north, 256 = east, 384 = south.** Nine
captured records hold 200, 202, 298, 302, 310, 318, 342, 422 at
this word — not four cardinals. `+0x091C` is a different field
and is **untested**. Do not assume degrees, and do not assume 0
is north.

**Vertical geometry** is in the next section. A screenshot
measurement that put wall height at 1,080 raw units (pillar
capital flush with the ceiling) is superseded: the 3D path
stores −614 and +409, span 1,023.

`+0x074A >> 10` does **not** match the inert X mirror on all nine
records, and `+0x074E >> 10` does not match the inert Y mirror
on all nine. Both live words are sector (6, 2) on every capture
because dungeon `+0x0748` is 0. The inert mirrors on r16 hold
the other-level display ((6,5) and (8,6)). AAA’s inert X is 7
while live X is still sector 6. Axis assignment is X then Y from
the CODE 2 store order (same as the object table) and the
in-game `+0x074A` edit, not from a perfect mirror match.

File offset **`0x06C2`** (not a player-record relative) is
`table[9][0]`. CODE 2 @8436 **writes** `-$1AD8` **into** it. It
is a sink, not a block-index authority. `set-block` still writes
the word. Do not confuse it with `+0x090C`.

ItemCheat’s v1.1 X=1868 / Y=1872 / level=1875 do **not** apply to 2.0.

Inventory records are four `u16be` and form a **tree**, the same
8-byte shape as world-item rows in `dpin` t2:

| Off | Field | Meaning |
|---|---|---|
| +0 | id | indexes the item catalog and STR# 2000 / 1001 |
| +2 | state | suffix / ready / worn / on-off; STR# 2008 |
| +4 | word 2 | **overloaded by item class**: container first-child slot; magazine round count; crystal charge threshold (CODE 7 @16002 `ADD.W` to +$4); flashlight battery. Flashlight instance word 2 (`+$4`) is battery charge. Zero means the item will not toggle. Shipped saves carry 2880 (`$0B40`). World-item flashlights on the ground carry 0 |
| +6 | next-sibling | slot index of the next item in the same container (or the next top-level item). `$FFFF` ends the chain |

Word 3 is **not** a catalog instance id and not a lazy free-list.
The knife’s `0003` is a sibling slot, not an instance number assigned
from holes 1, 2, 5, 8. Containers hold children via +$4; a magazine
sits inside a weapon the same way. Live records are at A5 `-$1A8A`
+ `$33C`, stride 8 (`ASL.L #3`), max 256. The save I/O blob is a
raw dump of that array: file `k*2876 + 0x0A30`. There is no
separate packed serialisation. Slot numbers in word 2 / word 3
are the same indices the running game uses. File `+0x0A00` is
player `+$30C` (48 bytes before the array), the `+$30C` offset
that was wrongly called the live inventory earlier. A linear
scan of `+0x0A00` treats six zero words as fake Maps and shifts
every sibling pointer by 6; the tree only coheres from `+0x0A30`.
The terminator is a **single** `$FFFF` word, not an 8-byte
`$FFFF` record. Early 3-item saves can leave a dangling
sibling (Flashlight `next=5` with only slots 0–2 written) — a
stale default, not a hidden record past the terminator.

One-name file (`data/saves/Saved Games` / `reference/saves/Saved
Games`, 267,452, SHA-256 prefix `a4f03eb9b09e0470`): name
`Pathways Out of Darkness` at 0; live X/Y 6903 / 2669 (sectors
6, 2); dungeon 0; HP 60/60; inert level 0 at (6, 2); inventory
Map / Watch / Flashlight / Walther ammo / Walther / sack / Colt /
… leftover 68k strings `uncompress_world`, `DATAINIT` in unused
space. Longest zero run = 598. This is one populated save, not
two near-identical slots. Home blocks 0–24 match `dpin` 128.

Two-name files (`Saved Games AAA-AAB`, `Saved Games r14`): names
`AAA` @0, `AAB` @128. Live X at `0x074A` and `0x074A+2876`. r14
X 6808 vs 6963 (both sector 6). Player-island AAA vs AAB differs
in the live X/Y longs, `u16@0x0752`, inventory append, knife
sibling slot, plus flag bytes **`0x0840`** and **`0x0864`**. Pickup
persistence as sparse player-island flag bits is still observed;
it is not the only world-state mechanism (see the 9,112-byte
blocks). The 32×32 explored-bitmap for Ground Floor sits in the
260-byte tail (156 tiles in the captured save, including (6, 2)).

#### Per-level world state (9,112-byte blocks)

The 25 home blocks of 9,112 bytes start at file offset **30,540**
(`$774C`), indices 0–24. Extra live copies sit at indices 25+.
`file_pos = index * 9112 + 30540`. File **`0x06C2`**
(`table[9][0]`) is a sink: CODE 2 @8436 writes it FROM
`-$1AD8`. It is not the block-index authority. `+0x090C` is an
INERT display mirror (confirmed in game). Load-path dungeon is
`+0x0748`.

- CODE 4 @1466 (jump table entry 152) does `NewPtr $2398` (9,112)
  into A5 `-$1A86` (and `$41C2` into `-$1A82`, `$0B3C` into
  `-$1A8A`).
- CODE 2 @10066 `SetFPos` to `index*9112 + 30540` then `FSRead`.
- CODE 2 @10174 is the matching `FSWrite`.

An earlier window at **39,392** was 8,852 bytes late. The claim
that those 25 blocks are live world state was **correct**; only
the offset was wrong. Do not use 39,392.

Internal layout, from the sentinel initialiser (jump table entry
164) and every `LEA` displacement observed against `-$1A86(A5)`:

| Offset | Size | Contents |
|---|---|---|
| 0x0000 | u16 | t0 count, max 60 |
| 0x0002 | 480 | t0: 60 × 8, monsters `(type, hp, 0, object index)`. type indexes STR# 2001 |
| 0x01E2 | u16 | t1 count, max 30 |
| 0x01E4 | 120 | t1: 30 × 4, `(object index, t2 slot)` |
| 0x025C | 320 | t2: 40 × 8, world item instances. Same four-word tree as an inventory record: `(id, state, word2, next-sibling)`. `$FFFF` in word 0 marks empty. Word 2 is the authored round count on magazines (see Item catalog). |
| 0x039C | 60 | t3: 15 × 4, door runtime. `+0` command, `+2` position `0..$400` (1024). Authored in the 9112-byte world image; no code initialiser. See **Doors** |
| 0x03D8 | 8000 | **500 records of 16 bytes — the object table** |
| 0x2318 | 128 | 128 zeros (JT 164 `CLR.B`) |
| **total** | **9112** | `$2398` |

t0 / t1 field meanings beyond the columns above are still thin.
t3 command/position are under **Doors**. t2 is the world-item tree,
not an OPEN blob.

Home blocks 0–24 at 30,540 are byte-identical to `dpin` 128
`[2876 + N*9112]` on every captured v2.0 save (25/25). They are
also identical across the four unique local files. Extra blocks
at 25+ are per-named-save live copies and do differ. Level 0
home: 144 live, 356 free (`$FFFE` at +0x0E), trailer 128 zeros.

#### Object table at +0x03D8

500 entries of 16 bytes. Field map from every read and write of
a displacement 0..15 off `[-$1A86(A5)] + $03D8`:

| Off | Type | Field |
|---|---|---|
| 0x00 | u32be | X, 10-bit fixed point |
| 0x04 | u32be | Y, 10-bit fixed point |
| 0x08 | u16be | packed shape descriptor (same format as wall pairs) |
| 0x0A | u16be | flags. Bits `$8000`, `$4000`, `$2000` are tested; bits 4–7 read as `(value >> 4) & 15` |
| 0x0C | u16be | unused. Zero on all 27,904 live objects |
| 0x0E | u16be | next-index link. `$FFFE` = free slot. `$FFFF` = end of chain |

Sector derivation is **`raw >> 10`** (`ASR.L #10`). Sites: CODE 4
@3590, CODE 7 @6976. The writer (CODE 2 @8754) does `LSL.L #10`
then `ADD.L #$200` to place an object at a cell centre. `$200`
is a **writer-side centring constant only**. `(raw − $200) >> 10`
agrees with the reader **only** when `raw` ends in `$200`.
Off-centre objects were previously reported one cell west and
north.

`Sector.item` is the **head of a chain**. `$000E` links objects
that share a cell. Worked example, one-name save, level 0, the
only corpse at sector (14,6):

```
item=114
114 → 87 → 56 → 55 → 54 → 49 → 31 → $FFFF
x_raw ~14800–14960, y_raw ~6600–6660  →  (14,6) via raw>>10
descriptors 0xC030, 0xC015, 0xC02D (resource 128) and 0xCE00
(resource 156)
```

That chain is the corpse’s inventory, not a second sector.

Confirmed identifications (level 0 dump, one-name save):

- Save runes at (6,2), (26,2), (5,10), (27,10) = obj[000],
  obj[052], obj[090], obj[091], all `desc=0xC000` (tag 6,
  selector 0, cache slot 0, resource 128, s1 index 0).
- Pillars `desc=0xCC80` / `0xCC81` / `0xCC82` → resource 153.
  `texture_list` slot 1 on levels 0–6 is 153.
- Pillars and corpses are **billboarded sprites at cell
  centres**, confirmed in game and by exact `.5` coordinates
  (`raw` ending in `$200` → `raw/1024 = N + 0.5`).

The table is a **linked free list**. Jump table entry 157
inserts, 159 updates, 158 frees by writing `$FFFE` to +0x0E, 164
wipes all 500 links to `$FFFE`.

`Sector.item` is an index into this table, not a template id and
not content. Because the table lives in save state, a fresh
game’s object layout comes from `dpin` 128.

### Item catalog (A5 `-$14D6`)

71 entries of 16 bytes (1,136 bytes) at A5 `-$14D6` through
`-$1066`. Indexed by item id. Installed once at startup by Think C
`_DATAINIT` (JT 305, CODE 11 @4) from a packed constant block in
CODE 11 (header at +`$1B2`, compressed payload at +454, dest size
7,592). Not a resource. Names are STR# 2000 (71 entries, 0-based);
examine text is STR# 1001.

Eight `u16be` per entry. A site that **uses** the word is required
to name it. Values looking plausible are not a name.

| Word | Off | What the code does | Name |
|---|---|---|---|
| w0 | +0 | JT 211 CODE 6 @578: `(w0 & $7F) \| $C000` builds the sprite descriptor. Bits 7–15 are 0 on all 71 entries. | s1 index in the low 7 bits |
| w1 | +2 | JT 214 CODE 6 @1534 dispatches use by this class: 2 potions, 3 weapons, 4 crystals, 5 specials, 6–9 worn gear | item class |
| w2 | +4 | CODE 6 @448 reads it. On pickup / drop, CODE 6 @8206 adds it to player `+$0A` (pickup multiplier +1 at JT 216 @3686; drop multiplier −1 at JT 215 @3164) | points credited while carried |
| w3 | +6 | CODE 6 @478 reads it. CODE 6 @5634 adds it into a running sum. JT 217 CODE 6 @3870 converts the sum with `_FP68K` and divides by **28**, then JT 272 formats STR# 2016 (`$7E0`) as `%3.2f kg` | **weight**. Unit is 1/28 kilogram. Printed kg = Σ w3 / 28 |
| w4 | +8 | CODE 6 @508 returns this word (dead branch: if w1==1, returns w4 + record `+$4`; no catalog row has w1==1). CODE 6 @5690 adds that value over children | per-item contribution to a container’s fill. **Not** a round count |
| w5 | +$A | CODE 6 @418 reads it. CODE 6 @4354 / @5758 accumulate it (children included when w6>0). @8206 does `MULS.W` by the pickup/drop multiplier and `ADD.L` into player `+$0C` | treasure accumulator credited on pickup/drop. **Not** the kg field. Shown in the live Progress panel (STR# 2013) |
| w6 | +$C | JT 207 CODE 6 @4: boolean `w6 > 0` (is a container / magazine holder). CODE 6 @616: insert allowed only if `w6 >= current_child_fill + @508(candidate)` | limit on the sum of children’s w4, and the is-container predicate. **Not** a round count |
| w7 | +$E | CODE 6 @794: equals the accepted child id, or `$FFFF` (any), or `$FFFB` (−5 → ids 58–60), or `$FFFA` (−6 → ids 53–55) | compatibility |

**Weight display (JT 217).** Arg slot `$FFFF` is the total: CODE 6
@4240 walks the inventory tree from player `+$33A` with callback
@5634 (add w3). Otherwise it formats one item: w3 of that record,
plus children if JT 207 says w6>0, via walker @5590 starting at
record `+$4`. `_FP68K` opcodes on the stack (`pea` src, `pea` dest,
`move.w` op): `$200E` (16-bit int → extended; 2-byte src / 10-byte
dest), `$1010` (extended → double), `$100E` (double → extended),
`$0006` (`FODIV`, dest /= src). The divisor is `MOVEQ #$1C`.
STR# 2016 [0] `Total Weight: %3.2f kg.` / [1] `Weight: %3.2f kg.`
@5634 does **not** multiply by record `+$4`. Id 9 (Red Velvet Bag)
sets a walk flag and skips adding its own w3.

**Container fill (CODE 6 @616).** Current fill is @4284: sum of
@508 over children. A candidate is admitted if @794(container, id)
is true and `catalog[container].w6 >= fill + @508(candidate)`
(`CMP.L` / `BLT` fails). Cedar Box (id 8) is special: if `+$4 ==
$FFFF` the candidate id must appear in the **14-word** table at A5
`-$1066` (immediately after the catalog). The loop is
`moveq #$e,d2` / `cmp.w d7,d2` / `bgt` — indices 0..13 only:

`2, 45, 46, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61`
(Flashlight, Survival Knife, Walther P4 Pistol, every magazine
and 40mm cartridge, Silver Medal).

The next word at `-$104A` is **0**. That is the first word of a
stride-`$5C` table read by JT 240 (CODE 7 @4), not a 15th admit
entry and not a Map-id pick-list. If the box already has a child
(`+$4 != $FFFF`) the extra gate returns false and the insert
fails. Catalog w1 for the box is **0**. JT 214’s switch (CODE 6
@1624–1638) sends class 0 and class 1 to the same stub:
`moveq #3, d6` then `bra` to the epilogue at @2998. **Use does
not clone.** Pickup of world items is JT 216 / JT 229, not JT 227.

Weapon / broken-weapon rows have w6 equal to the admitted
magazine’s (or cartridge’s) w4, so the ratio is 1: one magazine
or one 40mm round at a time. That is the same *kind* of quantity
as the bag limits (Cedar 100, Lead 190, Canvas 400, Velvet
12000). It is not a round count: a Walther magazine holds 8
(observed; catalog w4 = 10), and the M-79 is single-shot with
w6 = 5. Canvas / Velvet have w4 = `$FFFF`, so @508 returns 65535
and they do not fit inside any other container.

Bags do **not** have `w6 / admitted.w4` always integer (Map w4=18
into Canvas 400 is not whole). Equality of a weapon’s w6 with
its magazine’s w4 shows they hold the same kind of quantity and
nothing more.

**Round count is not a catalog field.** A fresh Walther magazine’s
8 lives in the instance record’s +$4. `dpin` 128 t2 has 180 rows
with id 51 across the 25 levels: qty `{1,3,4,5,6,7,8}`, 155 of
them 8, **maximum 8**. Pickup (JT 216) copies the t2 record.

**STR# 2013 is the live Progress panel, not an end-of-game recap.**
CODE 3 @8762 draws it into the GrafPort at A5 `-$1596`. JT 109
(CODE 3 @7708) and JT 110 (@7892) call @8762 per row. JT 105
(@6988) and JT 108 (@7530) refresh that port; the rest handler
(JT 231) calls both before opening the rest dialog. The six
strings are:

- [0] `Health` [1] `Power` [2] `Progress` [3] `Weapon Proficiencies`
- [4] `You are %d.%dm above ground.  You have scored %d of %d points and recovered $%d.%d%s in treasure.`
- [5] the same sentence with `below ground`

Player `+$0A` (points) and `+$0C` (treasure) are formatted into
that sentence while the panel is up. Catalog w2 is the per-item
point value: a Gold Ingot (id 37, w2=1) reads as 1 point on the
panel. The denominator **41** is a hardcoded `moveq #$29` at
CODE 3 @8944. It is **not** computed from the catalog. Σ w2 over
all 71 rows is **44**.

The on-screen **REST** control is not a DITL/CNTL item of this
panel. There is no CNTL resource. STR# 2010 is `[0] REST
[1] SEARCH [2] MAP`, drawn in a custom window (CODE 3 @9618 /
JT 141). CODE 3 @10176 calls `_FindControl` (CODE 3 @18778) and
dispatches part **1** → JT 231, part 2 → JT 232 (Search), part
3 → JT 88 (Check Map). The Actions menu (MENU 131, id `$83`)
item **3** “Rest” (Command-R) is the same JT 231, from the
MenuSelect dispatcher at CODE 2 @1622 / jump table @2094.

DITL 2000 (DLOG `$7D0`) is the in-progress rest dialog: userItem
1, **Stop** button item 2, static text “You are resting…”. JT 84
loops `_ModalDialog` until item 2.

JT 227 (CODE 6 @5098) writes a newly created record’s id from
player `+$146` and its word 2 from `+$148`. That is the Cedar
Box clone, not pickup. Fire (CODE 7 @16404) decrements player
`+$19A` and, when that hits 0, reads and decrements the magazine
record’s +$4. JT 257 (CODE 7 @17270) sets `+$19A` to **1** on
ready — it does not copy the magazine’s +$4. No catalog word for
id 51 is 8.

**Cedar Box — OBSERVED IN GAME.** Item id 8 clones ammunition.
Test sequence on a constructed save (editor wrote the tree; the
running insert path was not used):

1. Box containing one Walther P4 Magazine: nothing immediately.
2. Magazine removed from the box.
3. Player rested. A Map (id 0) appeared in the box.
4. Map removed, magazine put back. From then on the box cloned
   the magazine — a second magazine, original still inside.

The box remembers the last item placed in it. That memory
survives removal. The clone appears on rest, not on insert and
not on Use.

Mechanism, from the 68020 stream:

- JT 212 (CODE 6 @898) is the inventory move/insert. After the
  @616 gate it calls CODE 6 @7314. If the destination slot’s id
  is 8 it writes `player+$146 = item.id`, `player+$148 =
  item.word2`, `player+$144 = $0E10` (3600). Removing the last
  child from a box whose timer is already 0 also arms +$144 to
  3600 but does **not** change +$146 / +$148. No code writes the
  box record’s word 0 or word 1 on a non-empty box. The remember
  slot is not in the box record.
- JT 231 (CODE 6 @7620) is Rest. It refuses on player `+$139`
  (byte; STR# 1002[11]), `+$2D8` (STR# 1002[1]), `+$142`
  (STR# 1002[12]), `+$13E` (STR# 1002[3]). If HP == max HP it
  asks STR# 1002[2] via JT 91. Then `clr.w +$194`, JT 108, JT
  105, JT 84.
- JT 84 (CODE 2 @10846) opens DLOG 2000 and passes filter
  CODE 2 @15980 to `_ModalDialog` (`lea $3e6c(pc)` at @10970).
  The static call graph of JT 231 does **not** include this
  filter; it is not a `jsr`.
- Every 60 ticks the filter calls JT 249 (CODE 7 @9428). That
  advances player `+$12E` by `$6270`, heals, and calls CODE 7
  @12696 with flag 1 and time `$6270` or `$3138`.
- @12696 is the timed-effects pulse (poison / crystal charge /
  HP). It always ends with JT 227. On rest (flag=1) it also
  `clr.w +$144` if the timer had not yet reached 0. JT 248
  (CODE 7 @9242, main-loop tick via CODE 2 @4) calls the same
  pulse with flag 0 whenever JT 8 returns nonzero — so JT 227
  is not rest-only in the stream.
- JT 227 (CODE 6 @5098) calls JT 224 (@4800) with args
  `(8, 0)`: walk the inventory for item id 8. JT 224’s second
  argument is inverted from an earlier reading: **1 = do not
  descend**. Two callers pass 1 (CODE 2 @18434 flashlight/dark,
  CODE 7 @17936 JT 259). Arg 0 here does descend. On hit it
  allocates a free slot and writes `id = +$146`, `state = 0`,
  `word2 = +$148`, `sibling = $FFFF`. If the box is empty it
  sets the box’s first-child to the new slot; otherwise it
  writes the new slot as the **first child’s sibling**,
  overwriting any previous sibling pointer. There is no fill
  check and no `+$144 == 0` test inside JT 227.

The constructed `out/item-tests/cedar-box` save has
`+$144 = +$146 = +$148 = 0`. First rest therefore created item
id 0 (Map). That is **not** a missing-Map fallback. JT 88
(Check Map) is the only rest-adjacent id-0 test: JT 224
`(0, 0)`, and on `$FFFF` it shows STR# 1002[7] (“You don’t
seem to be able to find your map…”) and does **not** create
one. No rest-time path creates a Map because the player lacks
one. The Map in the observation is the clone of a zeroed
remember slot.

**Weapon proficiencies.** STR# 2006 has 8 strings (index 7
empty): Melee Combat, Colt .45 Pistol, Walther P4 Pistol,
MP-41 Submachine Gun, M-16 Rifle, AK-47 Assault Rifle, M-79
Grenade Launcher, `""`. STR# 2007 has 3 ranks: Beginner,
Novice, Expert. CODE 3 @8762 rows `d7 >= 4` call @9462, which
walks player `+$66` with stride 6, skips a slot whose rank
word is 0, and returns the STR# 2006 index plus the rank.
The rank string is STR# 2007[`rank - 1`].

Each `+$66` record is: `u16be` rank, `u32be` XP. JT 235
(CODE 6 @8402), called from fire @16980 on a hit, adds the
hit’s damage into that long and promotes the rank against two
thresholds at A5 `-$A2C` + 8×(STR# 2006 index):

| index | name | t1 (→ Novice) | t2 (→ Expert) |
|---|---|---|---|
| 0 | Melee Combat | 0 | 0 |
| 1 | Colt .45 | 0 | 0 |
| 2 | Walther P4 | 4000 | 10000 |
| 3 | MP-41 | 8000 | 30000 |
| 4 | M-16 | 12000 | 30000 |
| 5 | AK-47 | 6000 | 30000 |
| 6 | M-79 | 0 | 0 |

`t1 = t2 = 0` means the first JT 235 call with XP ≥ 0 writes
rank 3 (Expert). Fire looks up the ready weapon’s item id in
a 5-record table at A5 `-$810`, stride `$1E`, loop
`moveq #$5,d3` / `bgt` (indices 0..4):

| table i | item id | table +2 (STR# 2006 index) |
|---|---|---|
| 0 | 45 Survival Knife | 0 Melee Combat |
| 1 | 46 Walther P4 | 2 |
| 2 | 48 MP-41 | 3 |
| 3 | 49 AK-47 | 5 |
| 4 | 50 M-79 | 6 |

Melee Combat is not an item. It is slot 0 of the same table;
the Survival Knife’s word 1 is 0, so knife hits write `+$66`
slot 0. Fire also `addq.l #1` into `+$C2` (shots) and `+$D6`
(hits) keyed by the **5-entry table index**, and adds damage
to `+$BE`. JT 260 formats those for the DITL 2019 Accuracy
panel. Ready (JT 257) does not touch `+$66`.

Colt .45 (id 47) and M-16 are **not** in the 5-entry fire
table (no record has STR# index 1 or 4). The catalog has no
working M-16 rifle — only Broken M-16 (id 25) and M-16
Magazine (id 56). Those two panel rows have `+$66` slots and
thresholds; the decoded fire path never writes them.

### Vertical geometry

Read from the 68020 stream. A screenshot measurement that put
wall height at 1,080 raw units is **not** the renderer’s figure.
Full projection, view record, FOV arithmetic, wall/door geometry,
shading, floors, and clipping are in **Rendering**.

- The player has **no stored Z**. Live position is two longs
  (`+0x074A`, `+0x074E`). CODE 2 @8546 writes exactly eight
  position bytes (`LSL.L #10` then `ADD.L #$200` (512) at @8762–8788;
  eight-byte copy to player+0x56 at @8830). All geometry derives
  height from the two eye-relative constants below.
- CODE 3 @13656 stores **−614** and @13664 stores **+409** on the
  view record at A5 `-$1542` (5410), stored as longs. Wall height is
  **1023** raw units. 614 + 409 = 1023. The eye sits at 614/1023 ≈
  **60%** of wall height, not half.
- Field of view is **derived from the arithmetic**, not fitted to
  screenshots. `tan(HFOV/2) = 0.8`, `tan(VFOV/2) = 0.6` at both
  authored 4:3 viewports (272 × 204 and 384 × 288). HFOV =
  `2*atan(0.8)` = **77.3196°**. VFOV = `2*atan(0.6)` = **61.9275°**.
  CODE 5 @9856 computes `view+$1C = trunc(5*H/6)`; column height
  divides by that word, so the port height cancels. Horizontal
  `view+$1A = trunc(5*W/8)` from the 5/8 factor at CODE 5 @9806.
  `tan(HFOV/2) = tan(VFOV/2) * 4/3` exactly.
- `height10` at level record `+0x084` is **not** vertical scale.
  The 3D path never reads it. CODE 3 @8762 does `DIVS.W #10`,
  takes the remainder as tenths, and calls `_DrawString` — it is
  the HUD depth readout in metres.

CODE 5 @17190 is the **per-cell draw dispatcher**, not an “object
vertical extents” routine. Billboard extents are @17522–@17650
within it.

---

## Rendering

Implementation-neutral. Every constant below is from the 68020
stream. Hex constants are given with decimal alongside.

### Coordinate system and units

Cell is `$400` (1024) world units square. Grid is 32 × 32, row-major.
Wall height is 1023 raw units. Eye-relative floor −614, ceiling +409
(CODE 3 @13656 / @13664, stored as longs). 614 + 409 = 1023.
There is no stored Z anywhere. All geometry derives height from those
two. Cell centre = `(cell << 10) + $200` (512). Object positions are
10-bit fixed point.

### Projection

Rotation: JT 146 (CODE 4 @116). Eye at `view+$40` (64), angle at
`view+$48` (72).

```
dx = P.x - eye.x ; dy = P.y - eye.y
cos = word[A5-$1A8E (6798) + angle*2] ; sin = word[A5-$1A92 (6802) + angle*2]
depth   = (cos*dx + sin*dy) >> 10
lateral = (cos*dy - sin*dx) >> 10
```

Facing is a 512-unit circle: 0 = west, 128 = north, 256 = east,
384 = south.

Screen X (CODE 5 @14178):

```
sx = (lateral * view+$1A (26) + $200 (512)) / depth + view+$20 (32)
```

Screen Y: same shape using `view+$24` (36) (floor scale) and
`view+$28` (40) (ceiling scale), against centre `view+$22` (34).

`$200` (512) is a **pre-divide bias** on the numerator, not a
half-screen term. Half-screen is `view+$20` (32) / `view+$22` (34),
added after the divide.

**ANOMALY, PRESERVE:** X always adds `$200` (512) on the unclipped
path (@14186 and @14240). Y adds it only on the `d7 < d6` branch
(the four Y divides at @14278 / @14302 / @14326 / @14350) and **not**
on the `d7 >= d6` branch (@14474 and its three siblings). Shift
magnitude is `512/depth` pixels: 10.04 px at the near clip 51, 0.50 px
at depth `$400` (1024), 0.17 px at 3000. It is a winding-dependent
rounding / half-pixel bias, not a larger geometric offset. The
branches also swap which depth is used first and flip `$18` (24) /
`$1C` (28) / `$20` (32) orientation.

### View record fields

| Off | Contents |
|---|---|
| `+$00` (0) | 10-byte SANE 0.5 |
| `+$08` (8) | screen width |
| `+$0A` (10) | screen height |
| `+$0C` (12) | −614 floor |
| `+$10` (16) | +409 ceiling |
| `+$14` (20) | shade divisor (see Distance shading) |
| `+$1A` (26) | `trunc(5W/8)` |
| `+$1C` (28) | `trunc(5H/6)` |
| `+$1E` (30) | `trunc(512 * atan_term / 2pi + 1)` |
| `+$20` (32) | W/2 |
| `+$22` (34) | H/2 |
| `+$24` (36) | `+$1C * +$0C` |
| `+$28` (40) | `+$1C * +$10` |
| `+$34` (52) | `+$14 * $400` (1024) |
| `+$40` (64) | eye XY |
| `+$48` (72) | facing |

### Field of view

Two authored 3D viewport sizes, from `_SetRect` in CODE 3 @13312:
**272 × 204** and **384 × 288**. Both are exactly 4:3.

(An earlier session reported this pair transposed as 204×272 /
288×384 and concluded the small port was a few tenths of a degree
off. That was wrong.)

```
tan(HFOV/2) = (W/2) / trunc(5W/8)
  at 384: 192/240 = 0.8
  at 272: 136/170 = 0.8
tan(VFOV/2) = (H/2) / trunc(5H/6)
  at 288: 144/240 = 0.6
  at 204: 102/170 = 0.6
```

HFOV = `2*atan(0.8)` = **77.3196 degrees**. VFOV = `2*atan(0.6)` =
**61.9275 degrees**. Both exact at both sizes.
`tan(HFOV/2) = tan(VFOV/2) * 4/3` exactly.

These are **derived from the arithmetic**, not fitted to screenshots.

### Wall geometry

Descriptor is one 16-bit word: `tag = w >> 13`,
`selector = ((w >> 7) & $3F (63)) + 64` (0 for tag 6),
`s1index = w & $7F` (127). Wall slots 0 = north, 1 = west.

Tag 0 is **never drawn**. Emit gate CODE 5 @12202 (`C2 40`) /
@12206 (`67 16`), testing `(w >> 13) & 7 == 0`. Four identical gates
for slots `$6` (6), `$A` (10), `$4` (4), `$8` (8).

Walls have **zero perpendicular extent**: one face, no pair, no gap
(CODE 5 @13440, @13722).

The tag also selects a **horizontal span** along the cell edge.
Vertical extent is the full wall height in every case.

| tag | span along the face |
|---|---|
| 1 | 0 to `$400` (1024) (full) |
| 2 | `$100` (256) to `$400` (1024) |
| 3 | 0 to `$300` (768) |
| 4 | `$100` (256) to `$300` (768) (centred half) |
| 5 | **corner chamfer**, dirs 4–7 only (not a door) |

Tag selects a horizontal span on the cell edge (CODE 5 @13440 /
@13722). Vertical extent is the full wall height in every case.
dir 0..3 places the span on one cell boundary: Y=0, Y=`$400` (1024),
X=0, or X=`$400` (1024).

Tag 5 is the **corner chamfer**, a 45-degree face with endpoints on
two different cell edges (@13550), cutting the `$100`×`$100`
(256×256) notch tags 2/3/4 leave open:

| dir | slot | endpoints |
|---|---|---|
| 4 | 3 | NW (`$100` (256), 0)– (0, `$100` (256)) |
| 5 | 2 | NE (`$300` (768), 0)– (`$400` (1024), `$100` (256)) |
| 6 | 5 | SW (0, `$300` (768))– (`$100` (256), `$400` (1024)) |
| 7 | 4 | SE (`$300` (768), `$400` (1024))– (`$400` (1024), `$300` (768)) |

Door thickness comes from @16202, not from tag 5.

**UV is not world-pinned.** Both @14006 branches leave `span+$18` (24)
= 0 and `span+$1C` (28) = `$10000` (65536) for cardinals **and**
chamfers, i.e. 0..`$400` (1024) raw: the tile is **stretched** to
whatever face it lands on. Tag spans place geometry only; they are
never stored as U. Doors are the sole exception — @16202 overwrites
`$18` (24) / `$1C` (28) from the leaf position.

Census, slots 0+1, all 25 levels: tag 0 = 18578, tag 1 = 24382,
tag 2 = 2073, tag 3 = 2075, tag 4 = 4092, tags 5–7 = 0. Levels 7–15
have **zero** tag 2/3/4. Levels 0–6 carry 3244 tag 2/3/4 faces. On
L0 every nonzero slot 2–5 word is tag 5, selector 64, resource 192,
s1 4 (128 of them) or s1 9 (12).

CODE 5 @13440 remaps tag 0 to 1 at @13488 for **placement only**,
after the emit gate has already rejected it. That remap does not
cause tag 0 to be drawn.

`$217F` (8575): tag 1, selector 66, s1index 127, on 4101 faces across
levels 7–15. s1index 127 is out of range for a 14-entry shape
directory and is not bounds checked; it resolves 4064 bytes into the
decompressed blob and lands in pixel data. Never on a walkable/void
boundary. Harmless; skip rather than emulate.

### Distance shading

Shading is a **palette index remap**, not a colour blend and not fog.

Texel output: `move.b (a1),d1` / `move.b (a2,d1.w),d1` /
`move.b d1,(a1)` at CODE 5 @8270 and siblings @8082, @8096, @8202,
@8330.

Band selection (span drawer @5708, @6230–@6312):

```
band = ((15 * d5) / view+$14) >> 10, clamped to 15
```

where `d5 = depth + (|lateral| / 2)` — an **octagonal** metric, not
Euclidean. It over-darkens toward screen edges relative to true
distance.

The band value is **interpolated across the span**: `span+$10` (16)
is the start, `span+$14` (20) the step, computed as
`(U_end − U_start) / (x2 − x1)`. One wall face can straddle several
bands. This is Gouraud-like, not flat per face.

`a3 = a2 + $100` (256): a **second**, adjacent band used for
dithering between the two.

`view+$14` (20) from JT 239 (CODE 6 @9046), in precedence order:

| condition | view+$14 | full darkness at |
|---|---|---|
| A5 `-$1BCC` (7116) set | 5 | 5 cells |
| player `+$132` (306) (Infra-Red Goggles) | 7 | 7 cells |
| player `+$135` (309) (Flashlight) | 5 | 5 cells |
| else | 3 | 3 cells |

A5 `-$1BCC` (7116) is **DEAD**: no writer anywhere; always 0. Its
branch (`view+$14` = 5 from this flag) is unreachable.

Shade table generation, CODE 5 @4044 (fill @4090–@4168), reached via
JT 184 @1138 → @2986 → @3448:

```
out[band][i] = i + ((N - 1 - off) * band) / 14     for band 0..14
out[15][i]   = $0F (15)
```

where the palette is grouped into runs of N entries with
monotonically decreasing RGB, and `off` is i’s offset within its run.
Band 0 is identity; band 14 lands on the run’s dark end; band 15 is
forced to slot `$0F` (15).

Runs are collected by @2986 from the unique 6-byte RGB records of
every loaded `.256` (`$16` (22) count, entries at `+$1A` (26)),
grouped by @3884. **Not** from a clut and **not** from a fixed ROM
ramp.

Rebuilt when JT 184 runs: startup (CODE 2 @2298) and level
load/unload (CODE 3 @24450 / @24922). **Not** rebuilt on flashlight
toggle.

`$0F` (15) is a runtime ColorSpec slot, black on the L0 wall table.
It is **not** `.256` index 15, which is (21, 35, 21).

The four `$1000` (4096) banks are 256 × 16 remaps (selectors 0–3).
Filled by @4332 with a divide by 15 and a window origin:

| A5 | selector | fill | role |
|---|---|---|---|
| `-$17BA` (6074) | 0 | @4044 identity-lerp | 2D/PICT remap; floor/ceiling pass 1 |
| `-$17C2` (6082) | 1 | window (`$F` (15), `$10` (16)) = 15 entries from index 16 | |
| `-$17BE` (6078) | 2 | window (`$F` (15), `$1F` (31)) = 15 entries from index 31 | |
| `-$17C6` (6086) | 3 | window (`$F` (15), `$00` (0)) = 15 entries from index 0 | |
| `-$17CA` (6090) | 4 | `$100` (256) table via @4544 | |
| `-$17CE` (6094) | 5 | `$100` (256) table via @4544 | |

Windows are 15 entries, not 16, and origins 0 / 16 / 31 are not
contiguous: index 15 (`$0F`) is deliberately skipped because it is
the reserved black slot. The fifth `$1000` (4096) allocation is
A5 `-$17FA` (6138) (floor/ceiling scanline table); any extra role
is OPEN.

JT 178 (@484): copies band 9 of `-$17BA` (6074) and forces palette
indices `$6A..$79` (106..121) to `$0F` (15) in a 256-byte local used
by a 2D CopyBits snapshot. The fade @4742 only emits `$6A..$78`
(106..120), fifteen entries. `$79` (121) is never emitted — leftover
unique rgb8 (245, 171, 94). JT 178’s blackout therefore covers one
index the fade never uses. ANOMALY, preserve; do not shrink the
range. Deliberate, three sites.

### Door geometry

Doors are the **only** geometry with thickness. Leaf is a slab with
two parallel faces at perpendicular `+$100` (256) and `+$300` (768)
— 512 units thick, centred in the 1024 cell — at full wall height.

Emitted as **three** quads by CODE 5 @16202 via @14006: the +256 face
(@16324), the +768 face (@16498), and a leading cap across the moving
edge (@16630), the cap suppressed when position `== $400` (1024).

`door_list` is at level `+$9E` (158), 8 bytes: x, y, direction,
texture. `dir & 1` selects the slide axis (1 = Y). `(dir >> 1) & 1`
selects the anchor:

| anchor | dir | fixed | moving |
|---|---|---|---|
| low | 0, 1 | S0 | S0 + position |
| high | 2, 3 | S0 + `$400` (1024) | fixed − position |

Texture v runs `$400`−pos to `$400` (1024) when the dir bits differ,
0 to pos when they match. The texture stays pinned to the world
rather than stretching.

Position 0 skips the draw entirely (@15512 `tst.w` / `beq`).

**Confirmed by screenshot:** door 0 on L0 (21,6) dir 3, viewed facing
east, has the leaf on the high-Y (south, right) side and the gap on
the low-Y (north, left) side, spanning full wall height with a
visible leading cap.

### Floors and ceilings

PID does **not** render floors or ceilings as geometry. There is no
floor texture and no ceiling texture.

A precomputed u32 scanline table at A5 `-$17FA` (6138) (allocated
`$1000` (4096) in JT 177 @168) is blitted directly as pixel data by
@7536 / @7946, source = `-$17FA + (y << 2)`, one long per screen row,
`move.l (a2)+,(a1)+` over the span.

Filled by JT 179, length = view dimension at A5 `-$1538` (5432), with
knots:

| lighting | d4 | d5 |
|---|---|---|
| lit (flashlight or IR) | `2n/5` | `3n/5` |
| unlit | `3n/10` | `7n/10` |

| rows | fill |
|---|---|
| `[0, d4)` | @4742 (`$EF` (239) `* i / (d4-1)`), packed longs of `$6A..$78` (106..120) / `$0F` (15), 4-way dither |
| `[d4, d5)` | `$0F0F0F0F` (black) |
| `[d5, n)` | fade back down (same @4742, phase from the far edge) |

@4742 (`4E 56 FF FE` … `4E 75`, file 4742–4891, 150 bytes):
`phase/16` selects the coarse index `d6`; `phase%16` indexes a
16-word table at A5 `-$17F6` (6134); `row%4` picks a 4-bit nibble
(`asr` 0/4/8/12). DATAINIT words at `-$17F6`:

| i | word | hex |
|---|---|---|
| 0 | 0 | `$0000` |
| 1 | 32768 | `$8000` |
| 2 | 32800 | `$8020` |
| 3 | 40992 | `$A020` |
| 4 | 41120 | `$A0A0` |
| 5 | 42144 | `$A4A0` |
| 6 | 42145 | `$A4A1` |
| 7 | 42401 | `$A5A1` |
| 8 | 42405 | `$A5A5` |
| 9 | 58789 | `$E5A5` |
| 10 | 58805 | `$E5B5` |
| 11 | 62901 | `$F5B5` |
| 12 | 62965 | `$F5F5` |
| 13 | 65013 | `$FDF5` |
| 14 | 65015 | `$FDF7` |
| 15 | 65527 | `$FFF7` |

No CODE writer (one read: `lea.l -$17f6(a5)` at @4750). DATAINIT only.

Each long is four dithered pixels choosing `lo = $6A+d6` vs
`hi = $6B+d6`, except `d6==14` forces `hi=$0F` (15) so `$79` (121)
is **never emitted**. Phase 0 (outer edge) is `$6A`/`$6B`; phase
239 (band edge) is `$78`/`$0F`. The ramp is linear in **row →
phase**, then quantized to 15 index pairs — not linear in RGB.

Ground Floor global palette **after** the clut 129 plant at index
106 (`$6A`). 15 planted greys, then leftover unique `$79`:

| idx | rgb8 |
|---|---|
| `$6A` (106) | (30, 30, 30) |
| `$6B` (107) | (28, 28, 28) |
| `$6C` (108) | (26, 26, 26) |
| `$6D` (109) | (24, 24, 24) |
| `$6E` (110) | (22, 22, 22) |
| `$6F` (111) | (20, 20, 20) |
| `$70` (112) | (18, 18, 18) |
| `$71` (113) | (16, 16, 16) |
| `$72` (114) | (14, 14, 14) |
| `$73` (115) | (12, 12, 12) |
| `$74` (116) | (10, 10, 10) |
| `$75` (117) | (8, 8, 8) |
| `$76` (118) | (6, 6, 6) |
| `$77` (119) | (4, 4, 4) |
| `$78` (120) | (2, 2, 2) |
| `$79` (121) | (245, 171, 94) UNIQUE leftover; not used by @4742 |

Bright end of each fade is (30, 30, 30), **not** white. Dark end
dithers (2, 2, 2) against slot `$0F` (15) black. 30/255 = 0.1176.

The dark band across the middle is **wider** without a light, and
narrowing it is the flashlight’s second effect (the first being
`view+$14`). The emitted fade is `$6A..$78` (106..120). JT 178
blackouts `$6A..$79` (106..121), one index past the fade — see
Distance shading.

### Clipping and traversal

Near clip is 51 world units (@15746 `moveq #$33` (51), compared
against rotated depth; repeated at @15776 and @15978). Objects:
@17454 skips rotated X `<= 51`.

There is **no far plane**. No depth cutoff exists anywhere. Distant
geometry is fully emitted and shaded to black by band 15.

The per-cell walk (@12052) is an unbounded 4-way BFS with a 32×32
visited bitset at A5 `-$2EA` (746) and a 6-byte queue. No radius, no
ring limit. A walkable path can traverse the whole grid (32 cells =
32768 world units).

Per-cell draw dispatch is CODE 5 @17190:

| nibble | dest |
|---|---|
| 2 | @16202 (door) |
| 3 | @16912 |
| 5 | @17146 (secret door, drawn as a normal wall via @13440) |
| then | object chain from `sector+$C` (12) through world `+$3D8` (984) |

Billboard vertical extents are @17522–@17650 **within** @17190, using
CODE 5 @1454 (s1 unpack of `object+$8`) and `view+$1A` / `+$1C` /
`+$20` / `+$22`. Earlier docs labelled @17190 as “object vertical
extents”; that is the second half of the routine only.

`.256` palette index 2 is transparent.

### Billboards

CODE 5 @1454 unpacks object s1: `+$8` (8) width, `+$A` (10) height,
`+$C` (12) lift. Billboard vertical extents @17522–@17650:

```
bottom = view+$0C (12) (−614) + s1 lift
top    = bottom + s1 height
```

No vertical clip. Yaw-only (the billboard does not pitch to face
the camera). Sprites are not uniformly floor-anchored: the lift
word is per-shape.

### Affine texture mapping

The engine’s wall texture mapping is **affine per column**: `u` is
recomputed for every screen column from the projected span, and
column `v` is a fixed 16.16 step. That is **not** GPU
affine-per-triangle (`noperspective`).

A triangle-based interpolator cannot reproduce it. Constant `u`
**down** each edge says nothing about how `u` varies **across**
the quad, which is where the perspective divide matters. The
difference grows as the two edges of a face diverge in depth —
the near-wall corridor case. Confirmed in game: affine-per-triangle
smears near walls badly.

Of the two options a GPU offers, **perspective-correct is closer**.
It is wrong in a direction that is not visually objectionable;
affine-per-triangle is wrong in a direction that is.

Reproducing the original properly requires per-column `u`: either
split wall quads into vertical strips at mesh time, or do the
divide in the fragment shader.

An earlier midpoint test (U 0..`$400` (1024), 45° in camera xz,
depths 600/3000 or a true 1024-unit wall, viewport 384) reported
0 texels of error between affine-per-triangle and affine-per-column
because both cases were **symmetric about the sampled midpoint**,
so the errors cancelled there. The measurement could not
discriminate; it did not show the methods agree.

### Dither LFSR

Pixel loops (CODE 5 @7998 and siblings) load a 16-bit Galois LFSR
from **ctx `+$14` (20)**, `lsr.w #1` / `eori.w #$B400` (46080) per
pixel, compare against ctx `+$16` (22), and write the state back
at @8118 `move.w d0, $14(a0)`. Next band when `lfsr <` the 16.16
shade fraction.

A5 `-$17A0` (6048) is the scene-wide seed. DATAINIT word = 1.
Wall span drawer @5708 copies it into ctx `+$14` (`-$24(a6)` at
@5892), then writes the advanced value back (@6382). **Not** reset
per span or per column: free-running across the scene, so the
pattern depends on draw order.

@11586 `move.w #$1, -$17a0(a5)` runs in @11164 when
`view+$16` (22) is 0. Meaning of `view+$16` is NOT FOUND. JT 150
is a separate LFSR at `-$1A98` (6808), same tap, not used here.

---

## Player movement

Player step is applied in the VBL (CODE 1 @642 → @902 → @998),
~60/sec. 26-entry key table at A5 `-$1B98` (7064), 6 bytes each.

Step sizes, world units per application:

| key | walk | run |
|---|---|---|
| forward | 17 | 34 |
| backward | 12 | 24 |
| strafe (heading `± $80` (128)) | 12 | 24 |

Run toggle is A5 `-$1BCE` (7118) (DATAINIT 0; written by CODE 3
@14402). Running also caps the VBL accumulator at 7 instead of 14 and
doubles JT 8’s delta before its `>= 2` test.

**Correction:** 24 is **not** the walk step. 24 is run-backward and
run-strafe.

Turn keys change facing by `±2` or `±4` per VBL out of 512, or set a
continuous-turn latch of `±8` on `device+$1C` (28).

JT 145 (CODE 4 @38): `delta = table[facing] * speed >> 10`, added to
`device+$14` (20) (X) and `+$18` (24) (Y). Tables are 512 words at
A5 `-$1A8E` (6798) / `-$1A92` (6802), heap-filled by JT 147.

Player is a **point** against geometry. There is no collision radius
against walls or against the door leaf.

Keep-out from nibble-0 (void) faces only: the player is clamped to
cell-relative `$199` (409) or `$266` (614) (CODE 7 @12090 / @12102 /
@12112 / @12124). Corner chamfer adds `$199` (409) at @12278 when two
void flags are set.

Creature proximity revert (@3242), gated on A5 `-$1BCA` (7114)
(DATAINIT 1, no writer, always on): for each runtime creature on
player `+$216` (534) (stride 16 at `+$218` (536)), if JT 151 distance
from the destination is `< $154` (340) and the step moves closer, the
old XY is copied back over the destination. JT 151 (CODE 4 @1362) is
an octile metric: `min + (max >> 1)`.

Door collision (JT 161, position `> $200` (512) or command `== 2`)
is under **Doors**.

---

## Worn gear

All toggled by JT 214 (CODE 6 @2556) by catalog id:

| player | item | catalog id |
|---|---|---|
| `+$132` (306) | Infra-Red Goggles | 3 |
| `+$133` (307) | Digital Watch | 1 |
| `+$134` (308) | Red Cloak | 14 |
| `+$135` (309) | Flashlight | 2 |
| `+$136` (310) | Ruby Ring | 29 |
| `+$137` (311) | Amethyst Ring | 30 |

**Correction:** `+$134` was previously an unidentified dt modifier.
It is the Red Cloak. It doubles dt on the door / creature /
projectile path in JT 248 and selects the shorter rest quantum
(`$3138` (12600) rather than `$6270` (25200)). It does **not** scale
the player’s JT 145 step.

---

## Global RNG

JT 150 (CODE 4 @1304) is a 16-bit Galois LFSR, taps `$B400` (46080),
seed at A5 `-$1A98` (6808), seeded from Mac low-memory Time (`$20C`
(524)) via JT 149. Different every play. Nothing needs to reproduce
the sequence.

## Writer-less DATAINIT tables

Three A5 locations are filled only by Think C `_DATAINIT` (JT 305)
and have **no writer** in any CODE segment. They are not runtime
state. A port should hardcode the reachable path, not allocate
them as mutable globals.

| A5 | size | DATAINIT | Writers | Reachable path | Port |
|---|---|---|---|---|---|
| `-$1BCA` (7114) | byte | 1 | none | Branches are **LIVE**: creature proximity revert @3242, VBL path CODE 1 @940, JT 164 path CODE 4 @4348 | Hardcode 1; **implement** those branches |
| `-$1BCC` (7116) | byte | 0 | none | Its branch (`view+$14` (20) = 5 from this flag) is **UNREACHABLE** | Hardcode 0; do not implement that branch. `view+$14` is 7 / 5 / 3 from JT 239 only |
| `-$17F6` (6134) | 16 words | the @4742 dither pattern (see Floors and ceilings) | none (one read: `lea.l -$17f6(a5)` @4750) | Always the DATAINIT table | Hardcode the 16 words; do not generate them |

`-$17A0` (6048) is DATAINIT 1 but **has** writers (@6382, @11586).
It does not belong on this list.

## Bomb Code (closed)

`reference/saves/BombCode.bin` == `BombCode_1995.bin` ==
`data/hfs/Pathways_1995/Bomb Code`: **321 bytes, 0 diffs**.
Mac Roman text. Arming code **2870334**, deadline 1400 Friday.
Static game content, not per-playthrough state. No further work.

---

## Disproven

| Claim | Why it fails |
|---|---|
| `dpin` 128 is a directory of file-size offsets (`0x000c0b3c` as u32) | That u32 exceeds the resource. It is `u16be 12, 2876`. |
| `dpin` is 409×564 records | Divides the file but stride score ~0.0045; blockmap is diagonal. |
| `scri 128+N` is level N’s script | `scri` is corpse dialogue. Level names never appear. Mapping is `scri 128+TypeAddl`. |
| `clut` 256 is the game palette | It is the Bungie copyright string. Palettes are `clut` 128–135. |
| `Sector.Item` values restart per sector type / are a shape class | Same 0..399 range is shared by pillars, corpses, ladders, saves. 324 values appear with more than one sector type. |
| Descriptions `Ni` (“29i”, “40i”) is the count of `Item != -1` or of Type==1 items | No level matches (Ground Floor 116 / 66 vs 29i). |
| `unknown1` is u16-sum, XOR-fold, byte-sum, CRC-16 CCITT, or CRC-16 IBM of the sector array, whole record (ex-field), name, or header | 0/25 matches on every combination tested. |
| `.256` has a 23-byte packed header | Artifact of reading the first literal run of the compressed stream as a header. Packed offset 0 is only the u32be size; offset 4 is the first opcode. |
| `.256` packed offset 4 is a format tag | Same artifact. That byte is the first opcode (b<0x80 = run, else literal). |
| `.256` colour-table stride is 5 / 7 / 8 selected by that tag | Same artifact. Decompressed s0 is ColorSpec stride 8 on 50/50. |
| `.256` colour tables begin raw at packed offset 29 | Same artifact. First stride-8 run in decompressed space starts at offset 24. |
| `.256` has a RAWEND raw/compressed boundary after the first table | Same artifact. The whole payload after the size word is one compressed stream. |
| `.256` 161 / 162 / 167 / 189 have malformed directories | Same artifact: those four were short first literal runs, not a second directory format. |
| `.256` offset 8 is a raw `u32be` chunk directory | Packed offset 8 is inside the first opcodes, not a directory. The four u32be values live at decompressed 0x02. |
| `.256` bytes 4–5 are a `u16be` | Packed 4–5 are opcode bytes. There are no packed u8 fields at 4, 5, 6. |
| `.256` `v1`/`v2`/`v3` partition the packed stream | `v4 < packed` on 0/50 and `packed - v3 == v4` on 0/50. 195–202 share one decompressed header while packed sizes run 18545–32727. |
| `.256` `v4` is a fourth decompressed offset | On 50/50 `v4 == decompressed_size - v3`. It is the length of s3. |
| `.256` resources share one 256-entry palette | Each resource has its own s0 tables; overlapping indices are normal reuse. Do not union into a master palette. Petrich “128 sets overall color table” is approximate. |
| Byte 6 of packed `.256` is a colour count or tile count | Packed byte 6 is inside the first opcodes. Tile count is decompressed u16be at 0x00. |
| `.256` s1 holds width, height, and s3 offsets | Geometry is not in s1. Brute-force of every u16 pair as dimensions and every u16/u32 column as an offset: 0 passing layouts. Those fields are in s2. |
| `.256` tile rectangles pack s3 with no padding / s2 count equals tile_count | Raw `sum(w×h)` leaves 1–3 byte gaps (and 192’s extra s2 record). Iterate s2 by `(v3-v2)/16`; pad is `align4(w×h)` after each tile. 50/50 with that model. |
| `.256` pixels are PackBits | 0/50 exact, 49/50 truncated. Failed identically from three different start offsets. The real loop was read from CODE 8 @2206; it is not PackBits. |
| `.256` pixels are literal-default RLE keyed on the high bit (`>= 0x80` = run) | All five variants 0/50 exact. The high bit is not an escape flag. The real rule is the opposite: `b < 0x80` is a run of length `b+3`. |
| `.256` “a byte already present in the colour table is a literal” | 189 distinct out-of-range values spanning 0–255. The stream is opcodes, not a palette-aware filter. |
| `.256` sections 1–3 are stored uncompressed | Compressed-looking bytes begin before v1. The whole payload after the size word is one CODE 8 @2206 stream. |
| `.256` rows are padded to a stride other than the declared width | A stride sweep of width ±4 found no control-like vertical-correlation peak. Padding is per tile (`align4(w×h)`), not per row. |
| `.256` `s1.u16[0]` is a palette selector | Its range does not fit `0..(table_count-1)` under any 0-based, 1-based, or modulo reading. It is the class tag that selects s2 field order. |
| The L0 packed list shrinks when a floor item is taken | AAA/AAB file and the mid-game save both have the same 85 L0 records. Pickup appends inventory only. |
| `save_AAA` / `save_AAB` are two standalone save files | PID 2.0 wrote both names into one `Saved Games` file (276564). |
| The 25 blocks of live world state begin at file offset 39,392 | The **claim** (live world state, 25 × 9,112) is correct. The **offset** is not: homes start at 30,540 (`index * $2398 + $774C`). 39,392 is 8,852 bytes late. |
| `dpin` 128’s purpose is unknown / Semmler’s item-template guess / “2,876 records of 80 bytes” | CODE 2 @9262 writes it into a new save (FSWrite 28,760 + 2,876 @ pos 8 + 227,800 from offset 2,876) and releases the handle. Layout is a 2,876-byte header plus 25 world-state blocks. |
| The 2,876-byte player stride is inferred and suspect | **Confirmed**, not inferred. Player record `k` is at `k*2876`. 2,876 is the player-record stride; 9,112 is per-save file growth. They are unrelated. |
| `+0x090C` is the level the game loads | **INERT.** Confirmed in game: writing it does nothing. Load-path dungeon is `+0x0748` → A5 `-$1AD8`. |
| `+0x0918` / `+0x091A` are the position the game loads | **INERT.** Confirmed in game. Live X/Y are `+0x074A` / `+0x074E`. |
| File `0x06C2` is the block-index authority that selects the world block | CODE 2 @8436 writes it FROM `-$1AD8`. It is a sink. |
| `+0x074A` is a game clock (u32be, 60ths of a second) | It is live player X, 10-bit fixed point. In-game edit teleports. CODE 2 @8762–@8830 writes object-style `<<10 + $200` into player+0x56 = file `+0x074A`. |
| `height10` gives the world’s vertical scale | The 3D path never reads level-record offset `0x084`. CODE 3 @8762 is a HUD text formatter (`DIVS.W #10`, `_DrawString`). |
| The eye sits at half wall height | CODE 3 @13656 / @13664 store −614 and +409 on the view record at `-$1542(A5)`. Eye = 614/1023 ≈ 60% of the 1,023-unit wall. |
| `+0x091C` is confirmed inert | It was **never tested**. Values 0, 1, 2, 12 on the nine captured records. Mark UNTESTED. |
| PID does not persist world state | The engine `FSWrite`s the 9,112-byte block on level exit. Player-island flag bits (`0x0840` / `0x0864`) are an additional pickup map, not the only mechanism. |
| Pillars are solid map geometry filling the sector | They are objects with continuous 10-bit positions, drawn through CODE 5 @1454, not the wall path @1618. In game they stand at the sector centre and block movement. |
| Wall type and texture are two independent bytes | They are one 16-bit descriptor: bits 0–6 s1 index, 7–12 selector, 13–15 tag. |
| WallList corners (indices 2–5) are barriers | Only edges 0 and 1 isolate regions. Corners never cut a flood. `CutoffCorner` (160) is corner-only. |
| Some other `(i,j)` pair is the true north/west assignment | Slots 2–5 have zero type 32/33. Using them as edges opens secret closets. `(1,0)` fails Ground Floor (178/214). |
| Walls are stored on the south/east (or mixed) faces | S/E, N/E, S/W on (0,1) all increase sealed vs N/W and fail Ground Floor and/or Type 5. |
| Seed a level’s flood from its own Type 3 sectors | Those tiles are departures. Arrival `(x,y)` lives in the *source* level’s `LevelChangeList`. |
| Type 33 (`Wall_FancyCorners`) is a collider | 33 is a drawn face. Treating it as solid shatters 7–15 (L9 → 324 components). Under `{32}` those floors are one component. No level mixes 32 and 33. |
| `SwitchableWallCorner` (type 1) is the L9 / L10 mechanic | Zero type-1 walls on L9 or L10. All 4507 instances sit on L13. Treating type-1 as passable gains 0 tiles on L9 / L10. |
| Texture 127 is a holographic / walk-through marker | 127 is the dominant type-33 face texture on 7–15 (581 on L9, 499 on L10). Treating every 127 wall as passable also opens L7. |
| Crystals open walls | Descriptions and the Guide list crystals as talk / freeze / burn / lightning / earthquake / stone. L10 is reachable from Ground Floor’s SE ladder with no crystal. |
| L9 / L10 are sealed content | Walkthroughs treat both as ordinary maps. The “sealed” reading was type 33 as a collider. Under `{32}` they are 415/415 and 574/574. |
| The stored Labyrinth is 202 tiles with boxed corners | That count treated 33 as solid. Stored L13 is 525/525 connected walkable (499 void, 521 normal, 4 authored change-level). |
| Inventory record word 3 is a catalog instance id assigned lazily from the lowest free slot | It is a next-sibling slot. `$FFFF` ends the chain. The inventory is a tree (CODE 6 @5838 walks `+$4` children then `+$6` siblings). The knife’s `0003` is a sibling index, not an instance number. |
| Catalog w4 is a magazine’s round capacity | A Walther P4 Magazine (id 51) holds 8 (UI and eighteen save records; `dpin` t2 max 8). Catalog w4 for id 51 is 10. Live rounds are the instance record’s +$4. CODE 6 @508 / @616 use w4 as a container-fill contribution. |
| Catalog w6 is a weapon’s round capacity | Same pairing error. Walther w6 = 10 against an 8-round magazine; M-79 (id 50) is single-shot with w6 = 5. w6 is the limit compared to Σ children’s w4 (CODE 6 @616) and the is-container test (JT 207, `w6 > 0`). |
| File `+0x0A00` is a packed / serialised inventory with different slot numbers than the live array | The save blob is a raw dump of the live player buffer at A5 `-$1A8A`. File offset = live offset + `0x06F4` throughout. Inventory is the live tree at file `+0x0A30` = player `+$33C`. `+0x0A00` is player `+$30C` (48 zero bytes on the captured saves). Parsing from `+0x0A00` invents six phantom Map records and makes every sibling chain look cyclic. |
| STR# 2013 is an end-of-game recap / not a live score HUD | It is the live Progress panel (Health / Power / Progress / Weapon Proficiencies). CODE 3 @8762 formats live `+$0A` / `+$0C` with a hardcoded 41-point denominator. Catalog w2 is the per-item point value (Gold Ingot w2=1). |
| The Cedar Box duplicates or transforms its contents on Use | JT 214 class 0 is a no-op stub. Clone is JT 227 on the rest-time pulse, id from player `+$146`. |
| A rest-time fallback creates a Map when the player carries none | JT 88 tests for id 0 and only alerts STR# 1002[7]. The Map in the constructed-save rest test is JT 227 cloning `+$146 == 0`. |
| The Cedar admit list at `-$1066` is 15 words and includes Map | The empty-box loop runs 14 words (d2=`$0E`). The following 0 is the first word of the stride-`$5C` table at `-$104A` (JT 240). |
| Tag 0 is drawn / remapped to tag 1 | @13488’s remap is a placement fallback after the emit gate at @12202 / @12206 has already rejected it. |
| The Labyrinth is visually randomised | Only s1index bit 0 varies, selector is fixed at 66, and most affected faces are tag 0 and not drawn. |
| There is an L13 maze generator | The grid is authored. JT 164 writes only wall words: `(voidNeighbourFlag & 7) << 13 \| $100 (256) \| (rng & 1)`. |
| Containers hide their contents from id lookups as a general rule | The walker at CODE 6 @5838 descends into every container by default. The Lead Box / Alien Gemstone case is hard-coded in callback @6874 (target id 32 AND node id 10 AND state bit 1 clear). A gemstone in a Cedar Box still drains. |
| JT 224’s second argument is a descend flag no caller sets | Polarity is inverted (1 = do **not** descend) and two callers pass 1 (CODE 2 @18434 flashlight/dark, CODE 7 @17936 JT 259). |
| Nibble-5 secret doors are openable | Passage requires `type_addl >= 4`. No site writes that. All six authored instances have `type_addl < 4` and are permanently impassable. Drawn as normal walls. Cut feature. |
| The Cedar Box is rest-gated | It is an arm/disarm countdown on player `+$144` (324). Clone orphaning is via sibling overwrite. |
| Game time runs 60× real time | 1 tick = 1/60 s, 1:1 with real time. |
| A far plane exists in the renderer | No depth cutoff. Distant geometry is emitted and shaded to black by band 15. |
| The player has a collision radius against the door leaf | The mover contains no radius and no `(1024 − position)` term. JT 161 is `position > $200` (512) (`bgt`, so 513+) or `command == 2`. |
| A5 `-$1BCA` (7114) is runtime state | DATAINIT 1, no writer. Permanently **SET**. Branches **always run**: creature proximity revert @3242, VBL path CODE 1 @940, JT 164 path CODE 4 @4348. A port **must implement** them. Hardcode 1. |
| A5 `-$1BCC` (7116) is runtime state | DATAINIT 0, no writer. Permanently **CLEAR**. Its branch (JT 239 returning `view+$14` (20) = 5) is **unreachable**. A port should **omit** it. Hardcode 0. |
| GPU affine-per-triangle reproduces the engine’s affine-per-column texture mapping | Refuted in game: near walls smear. The supporting measurement used symmetric test cases whose errors cancelled at the sampled midpoint. A triangle interpolator cannot reproduce per-column `u`. |
| Eye height and FOV were fitted to screenshots | Both are derived from the code arithmetic (floor −614, ceiling +409; `tan(HFOV/2) = 0.8`, `tan(VFOV/2) = 0.6`). |
| The two authored viewports are portrait / differ in FOV | Both are 4:3 (272 × 204 and 384 × 288) and both give exactly 0.8 and 0.6. |
| The player walk step is 24 | 24 is run-backward and run-strafe. Walk forward is 17; run forward is 34. |
| player `+$134` is an unidentified dt modifier | It is the Red Cloak (catalog id 14). Doubles dt on the JT 248 door/creature/projectile path and selects rest quantum `$3138` (12600) rather than `$6270` (25200). Does not scale JT 145. |
| The sector carries only two wall words | Six: two edges (+0 N, +2 W) and four corners. South/east are the neighbour’s slot 0/1. Emit gates @12188/@12248/@12292/@12336 read current slots 3,5,2,4. |
| Tag 5 is the door slab | Tag 5 is the corner chamfer (dirs 4–7, @13550). Door thickness is @16202. |
| Chamfer UV is world-pinned like a tag span | Both @14006 branches emit `span+$18=0`, `span+$1C=$10000` (65536) for every face; the tile is stretched. Doors are the only `$18`/`$1C` overwrite. |
| The white blocks in Ground Floor walls are a decoder bug | Index-2 placeholder 49×48 at (16,39), 49× `2D 02` repeats. Unconditional overlay blit at @2030/@42 from s1 `+$6`. RLE opcode table is correct. |
| `door_rates` +0 is the per-tick rate | +0 is 0,0,2,2,2,1 (UNKNOWN). Rate is at `+$A` (10), duplicated at `+$C` (12): `$0C` (12) / `$11` (17) / `$19` (25). |
| The player has a collision radius | He is a point. `$199` (409) / `$266` (614) is a clamp against nibble-0 faces only. |
| The billboard pitches to face the camera | Yaw-only. |
| Sprites are uniformly floor-anchored | Bottom = `view+$0C` (12) (−614) + per-shape s1 lift; top = bottom + s1 height. |

---

## Credits

Field knowledge used here comes from third-party work. **All parsers
and Kaitai specs in this repo are independently written** and are not
transcriptions of their sources.

| Who | What |
|---|---|
| Loren Petrich | `PIDMapReader.h` / `PID_Level` layout; `.256` resource ident list; `sector_types_sqr` sheet |
| Ben Semmler | Torch 0.9.1 docs: sector types, corpse → `scri`, item-group theory, “duplicate pillar item number crashes” |
| Chuck Gray | Dead Scripts dump; XOR description (counter starts at offset 2, not 4) |
| Alan Earhart | PID Maps folder: Descriptions, Hex reps_notes, heights |
| Alain Roy | save / item ID notes (`ItemCheatFile`); Pathways Into Cheating DITL/STR# field names |
| W'rkncacnter | AOPID 1.4 (`Shapes.shpA`) used as decoded-art reference only |

---

## Open questions (engine impact, ranked)

Closed: `.256` pixel decoding (CODE 8 @2206); `dpin` 128 as the
save-file initialiser (CODE 2 @9262); `Sector.item` as the object-
table chain head (CODE 5 @17190); live X/Y/facing; the 9,112-byte
block’s role and its start at 30,540; vertical FOV and eye height
(derived, not fitted; both viewports 4:3); the item catalog at A5
`-$14D6` (weight = w3, printed kg = Σw3/28; w4/w6 = container
fill/limit, not rounds; inventory word 3 = next-sibling; save
inventory is the live tree at `+0x0A30`); Cedar Box clone (JT 227,
remembered id at player `+$146`; arm/disarm on `+$144`, not
rest-gated); live Progress panel (STR# 2013) and weapon
proficiencies at `+$66`; `$217F` (out-of-range s1index; skip);
L13 maze generator (none; grid authored, JT 164 writes wall words
only); door triggers 130 / 141 / 24 (trigger sectors: Pipes,
gemstone-gated door, level exit via player `+$52` / JT 72 @6106);
CODE 5 @17190 label (per-cell draw dispatcher; billboard extents
@17522–@17650 within it).

Working-state list and methodology: `docs/PID_HANDOFF.md`.
Port mapping: `docs/UNITY_PORT.md`.

What remains, ranked by engine impact — see also **Still open** in
`docs/PID_HANDOFF.md`:

1. **Creature door behaviour** — whether an actively pursuing
   creature walks through a door at position `<= 512`. Untested;
   idle creatures proved nothing.
2. **The unreproduced door-500 clip** — one session where the
   player was blocked at position 500 with the freeze intact. Every
   geometric hypothesis searched and refuted; the traced mover
   passes at 0, 200, 350, 500 and 512. Most likely the @3242
   creature proximity revert, but player `+$216` was 0 in the save.
   Retry once; do not spend more.
3. **t0 / t1 field details** inside the 9,112-byte block. t2 at
   `+0x025C` is the world-item tree. t3 command/position are under
   **Doors**.
4. **Creature AI** — movement, pathing, aggro, attack selection,
   respawn. The conversation system, the Search dialog, potions,
   per-item use effects, sound, level 24 and the endgame, text and
   dialog rendering.

The catalog, the inventory tree, pickup/drop accumulators, the
fire → magazine `+$4` path, door collision, door operation, and
the renderer (projection, shading, floors, door leaf) are no
longer in that unread bucket. The function inventory makes the rest
searchable: **225** functions have zero traps and exceed 100
bytes, and **89** A5 globals are written in exactly one place.

Also unsolved, lower impact (do not treat as closed):

- Player-island flag bits (`0x0840` / `0x0864`); `unknown1`
  (0x86–0x8D); level-change type 4; Carlos `TypeAddl=200`.
- `type_addl` 134 and 135 (L15): no reader anywhere.
- Trigger cases 18, 19, 20, 21: four distinct values, identical
  behaviour (`addq.w #3`, player `+$142` (322)), 16 uses on L17.
- JT 246 pokes `$00FF` (255) into creature catalog entry 14
  (Stalker) field `+$08` at level apply.
- STR# 2001 indices 8, 9 and 13 are blank but have full catalog
  rows and are placed in levels: type 8 on L15 ×1 (HP 12000),
  type 9 on L19 ×1 (HP 5500), type 13 on L19 ×6 (HP 240). Entry
  13’s `+$04` is `$100B` (4107) against Ooze’s `$000B` (11), so it
  is a greater-Ooze variant. Entries 8 and 9 are unexplained; their
  very high HP and single placements suggest impassable obstacles
  rather than enemies. Fan sources name Flying Rat, Greed, Flying
  Reptile, Malice and Deceit, none of which appear in any STR#.
- A5 `-$17FA` (6138)’s role beyond the floor/ceiling gradient; and
  the fifth `$1000` (4096) bank.
- 11,372 trailing packed bytes on resource 192 after the declared
  count (starts `13 14 15 16`). Purpose UNKNOWN. Not missing tile data.
- The `+$1B8` (440) monster-frequency poke (CODE 2 @8710) writes
  `#$F` (15) to slot 0 only while d7 iterates 0..2 over a stride-4
  table. Indexed compare, unindexed write. Probable original bug;
  confirm before replicating.
- `+0x091C` (values 0 / 1 / 2 / 12) is **untested**.
- How Colt .45 (id 47) and the M-16 proficiency slot (STR# 2006[1]
  and [4]) ever become nonzero: the decoded fire table at `-$810`
  has five records and never writes those two indices.
- The encumbered lock (STR# 1000[0]) — JT 217 is the display, not
  the movement gate.

`.256` 195–202 remain unreferenced by `texture_list`. They are not
a missing floor/ceiling selector: PID does not render floors or
ceilings as geometry.

---

## Negative results (harvest)

- Demo application resource fork does not contain `STR#` 2018 or 2021.
- `pathways-i-d-11.sit` and the Japanese `.dc42` images are installer
  disks, not a ready-to-parse loose Maps file.
- `Pathways_-_2.0.sit` is patchers, not a standalone v2.0 tree. The
  playable v2.0 tree came from `Pathways_1995.dsk`.

---

## TODO (gaps in the source prompt, not invented)

- View-record `+$16` (22) gates the @11586 LFSR reset to 1. No writer
  identified. Other untabulated view fields (`+$2C`, `+$30`, `+$38`,
  …) are unnamed here.
- The fifth `$1000` (4096) bank next to A5 `-$17FA` is still open
  (see PID_HANDOFF). Texture 2 is absent from every level’s
  `door_list` (see **Doors**).
