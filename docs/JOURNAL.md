# How the Pathways Into Darkness format was solved

Phase 0 of this project was data archaeology: take the shipped Macintosh
files, write a parser that matches the bytes, and draw a level that a
player would recognise. That exit criterion is met. This is the record
of how we got there, in the order the facts arrived. The machine-readable
spec is `docs/FORMAT.md` and `formats/pid_level.ksy`.

All parsers here were written from the byte layout. Loren Petrich, Ben
Semmler, Chuck Gray, Alan Earhart and Alain Roy named the fields; their
code is not in this repository.

---

## What we started with

Pathways Into Darkness (Bungie, 1993) never released source. Classic Mac
files have a data fork and a resource fork; both matter. The application
resource fork holds `STR#` string lists, `scri` corpse scripts, one
`dpin` blob, and the usual Mac chrome. Level geometry lives in a sibling
file named `Maps` that has **no** resource map — it is a raw data fork.

The working copy is v2.0 from `Pathways_1995.dsk`. Demo, v1.1 installer
floppies, and the Japanese disks were harvested for comparison. Fan
notes from the Pathways extras CD (Petrich’s `PIDMapReader.h`, Semmler’s
Torch docs, Gray’s Dead Scripts, Earhart’s Descriptions / height list,
Roy’s ItemCheatFile) were read as hypotheses and then checked against
bytes. Aleph One / Marathon formats were not used; they are not
compatible.

---

## Harvest (2026-09-01)

Windows, `unar`, and a small HFS reader (`tools/extract_hfs.py`) pulled
the disk images apart. Resource forks survived as raw `.rsrc` maps or
AppleDouble sidecars. `tools/rsrc.py` lists both.

Playable trees on disk:

- Demo: loose Maps (50502 bytes) + app / Shapes / Sounds.
- v2.0: Maps (420850 bytes) + app (`vers` 1 = v2.0).

`STR#` 2018 in the full app is the published 28-name list. The demo
lacks 2018 and 2021. Demo Maps is three records; v2.0 is twenty-five.

---

## The 16834-byte stride

Level names sit in the Maps data fork at `i * 0x41C2`. 0x41C2 is 16834.
v2.0 is exactly 25 × 16834; the demo is exactly 3 × 16834. That is the
record size. It was not invented from Petrich — the names land on that
period and the file sizes divide evenly.

Each record opens with a Pascal name in a 128-byte slot. Unused tail
bytes are leftover text (record 0 still has `o Darkness…`). `STR#` 2018
and the Maps names disagree on a few spellings (`Feel The Power` vs
`Feel the Power`; a missing ellipsis here and there). Interior of the
record was still unknown.

---

## Reading other people’s notes, then checking them

Petrich’s `PID_Level` is a 450-byte header plus 1024 sectors of 16
bytes. Semmler’s Torch docs name the sector types (Void, Normal, Door,
ChangeLevel, DoorTrigger, SecretDoor, Corpse, Pillar, OtherTrigger,
Save) and say a corpse’s additional info is a global index into `scri`.
Gray published the Dead Scripts dump and an XOR description that was
off by two bytes.

The first 2048 hex of Maps showed one Pascal name at offset 0, then the
rest of the 128-byte slot. Height in metres × 10 sits at 0x84 and
matches Earhart’s list on all 25 records (level 24 is −32768). An
earlier hex reading that put a different field at 0x84 was a misaligned
line, not a field swap.

`formats/pid_level.ksy` and `tools/pid_level.py` were written from that
layout. Zero wall-type or sector-type violations in 25 × 1024 sectors.
Petrich’s `sector_types_sqr` sheet matches 100% at origin 16, 4 pixels
per sector, pitch 144.

---

## What a sector actually is

Sixteen bytes: six `(type, texture)` wall slots, an `i16be` Item, an
`u8` type, an `u8` type_addl.

The six wall slots are **not** six barriers. Slots 0 and 1 are the
north (−Y) and west (−X) edges. Slots 2–5 are decorative corners.
South and east faces belong to the neighbouring sector. Only `Wall`
(32) and `Wall_FancyCorners` (33) on those two edges isolate regions.
Short walls (64 / 96 / 128) sit on the same edges and do not change
reachability on any of the 25 levels. `CutoffCorner` (160) lives only
on corners.

Sector index is row-major, `i = y*32 + x`, x right, y down. Ground
Floor under that rule is a T with the stem south, matching the
published map. Transpose (`i = x*32 + y`) lays the T on its side and
is wrong.

`Sector.Item` is a per-level instance id, unique within each record,
range 0..399 globally, shared across sector types. It is not a catalog
index, not a loot-group index, and not a save-block key.

---

## Dead ends that looked promising

Several early readings failed cleanly and stayed failed.

**`dpin` as a directory.** The first four bytes look like `0x000c0b3c`
as a u32, which exceeds the resource. They are `u16be 12, 2876`.
409 × 564 divides the file and scores almost nothing on a stride scan;
the blockmap is diagonal. The vertical reading is 596 bytes of prefix
then 2876 rows of 80. Inventory-shaped 8-byte records exist in there.
They are not selected by `Sector.Item`. What `dpin` *is* remains open.

**`scri 128+N` as level N.** No level-name bytes appear in any `scri`.
Gray and Semmler both call these corpse-dialogue scripts. The working
map is `scri_id = 128 + Sector.TypeAddl` on a Type 6 sector. TypeAddl
values are globally unique: `{0..27}` plus one `200` (Carlos). Dead
Scripts headings skip 129 and 135; both resources exist and decrypt to
real dialogue (Lock&Load’s Cold Guy, Ascension’s Joachim).

**`clut` 256 as the game palette.** It is the 1993 Bungie copyright
notice stored under type `'clut'`. The real palettes are `clut`
128–135, eight 15-colour Mac tables.

**The 25 save blocks as live world state.** A two-name `Saved Games`
file is 276564 bytes. Blocks 0–24 at 39392 are **templates**. They do
not shrink when you pick something up. A second save name adds 9112
bytes, not 25 × 9112. PID *does* persist pickups — as sparse flag bits
on the player island, not by rewriting the map copy.

**A proven 2876-byte player struct.** Two clocks sit 2876 bytes apart
in the two-name file. Bytes 0–1865 of that span are leftover. Only the
island from ~1866 is live. 2876 is an offset that appears, not a parsed
record.

---

## Corpse talk

Gray’s XOR starts at the wrong offset. Skip the first two bytes (they
are an unencrypted `u16be` length equal to the resource size), then
XOR the rest with `00 01 02 …` wrapping at 256. After that transform,
scri 128 contains the plaintext `Who are you?  Am I dead?`.

Stubs 156 and 157 are 14 bytes and do not share a prefix with the
bodies. The published “Mumble, mumble…” line is not in 156.

---

## Shapes: enough to know we cannot paint them yet

v2.0 `Shapes.rsrc` holds 50 `.256` resources. Most have a 7-byte
header and a four-word offset table at byte 7 into a *decompressed*
buffer whose size is `u32@0`. Floor and ceiling resources 195–202 all
store 33144 and share one offset pattern that looks like two 128×128
8-bit images plus headers.

Each resource carries **its own** colour table. Index spaces overlap
because resources reuse slots. There is no master 256-colour union.

The pixel encoding is still unknown. PackBits, high-bit RLE, 0x90 RLE,
per-row resets, and several discriminator-aware schemes miss 33144 or
leave kilobytes unread. A raw dump from packed offset 258 is a
recognisable mottled gray and is the current viewer stand-in, not the
codec. This is the item that blocks textured rendering.

`texture_list` in the map header (eight i16be) encodes a `.256` id in
the low 12 bits plus 128 and a variation 0–3 in the high nibble. Slot
0 is always walls (192 / 193 / 194). No slot maps to floor/ceiling
resources 195–202. How a level picks its floor and ceiling is unknown.

---

## Saves, briefly

One real `Saved Games` file is 267452 bytes with a single Pascal name.
Two named games live in one file (276564). ItemCheat’s v1.1 offsets
for X / Y / level do not apply; v2.0 stores sector coordinates as
plain integers at 2328 / 2330 and the level at 2316. Inventory is
8-byte records `(id, state, qty, catalog)` starting at 2560, the same
shape as the inventory-like rows in `dpin`. Catalog numbers are a
lazy free-list, not an index into another table.

The 32×32 explored-bitmap for Ground Floor sits in a 260-byte header
near the end of the file (156 tiles in the captured save, including
the save rune at (6,2)).

---

## Drawing Ground Floor, then walking it

`tools/level_viewer.py` and later `round17_walls.py` /
`round18_walls.py` draw a 32×32 grid: Void black, Normal tan, thick
lines on edges 0/1, corners as marks. Ground Floor is the published T.
That is Phase 0’s exit picture.

A flood from the southmost non-Void tile reaches **214 / 214** Ground
Floor sectors. All four saves and all four ladders are on that
component. The side wings open through doors. The fan map that omits
those wings is incomplete, not evidence of sealed content.

The same southmost-start rule on later levels is wrong. Levels 7–15
are entered by ladder and have no southern door. A union flood from
every Type 3 and Type 9 still left large sealed regions on those
floors. Short walls were not the cause (variant A = only 32/33 block;
variant B = also 64/96/128; both match, Ground Floor stays 214/214).

---

## Doors start closed

PID does not open a door by walking into it. A Type 4 `DoorTrigger`
sector does, and `TypeAddl` selects the action: 129 open neighbour,
131 silver, 132 gold, 141 flag, 130 Alien Pipes, 6/7 chain, 128 close.
Every `OpenNgbr*` trigger on the 25 levels is 4-adjacent to exactly
one Type 2 door. Opening that door (ignore 32/33 when stepping onto or
off it) and re-flooding to a fixed point grows L11, L12 and L14. It
does not move L7, L8 or L15: those Type 2 tiles sit in already-open
corridors. L9, L10 and L13 have zero Type 2 and zero Type 4.

Silver and gold keys are real progression gates (Welcome, Tasty
Primate; Beware of Low-Flying Nightmares). From the start set they do
not unlock extra *tiles* — the keyed doors we can reach are the
no-op corridor case, and the ones that would matter sit on the sealed
side.

---

## Arrival coordinates live in the other level

`PID_LevelChange` is `{ i16 Type; i16 Level; i16 x; i16 y }`. Petrich
annotates x,y as “the coordinates of the sector to go to.” Semmler:
“The coordinates are where the player is dropped in the level.” A
level’s own Type 3 sectors are **departures**. Arrival tiles for
level N are every live `LevelChangeList` entry, in *any* of the 25
records, whose destination Level is N.

Unused slots are `Type=-1, Level=0, x=0, y=0` (368 of them). A few
Type=-1 slots hold leftover coordinates and are skipped. Live entries
are Type 0–3 with a dest level 0–24 and x,y on the 32-grid (118).
Type 4 is undocumented and appears as a But Wait → Ground Floor
pointer.

Seeding from own Type 3s is why The Labyrinth’s four corners looked
boxed under the old rule: they are exits, not entries. The real drops
are (16,17) (void in the stored template — L12 / L14 / L15) and
(16,18) (walkable, from L16). Descriptions says the Labyrinth reforms
every visit. The stored geometry is a template, not the walkable
floor. Under the real movement rule (type 32 blocks; type 33 is
draw-only) that template is one 525-tile component — the earlier
“202, corners boxed” count treated 33 as solid and is dropped.

The transition graph agrees with Descriptions on the famous
connections: Lock&Load’s two ladders, They May Be Slow’s west/east
teleporters, the Labyrinth’s four corners, Happy Happy’s west/east
ladders and its north/south traps. Happy Happy’s traps both
SecretDownward-drop at L20 (2,2), a void-isolated 3×3 with Items
210–218 and no exit. That “sealed” region is working as designed.

Level 24 (Ok, Who Else Wants Some?) is not a floor plan. Petrich’s
sector-type sheet draws a 1993 / snail credit graphic in that cell.
Arrival is (14,19) from L23, a 33-tile hub among 34 void-separated
islands. Treat it as special.

One-way transitions are teleporters or traps. Bidirectional pairs are
ladders.

---

## L9 and L10 were never sealed

Under the wrong collider (type 33 blocks) two crystal-theme levels
looked almost entirely boxed: L9 12 / 415, L10 4 / 574. Both have
empty DoorLists, no Type 2, no Type 4, no Type 5, no Type 8. Arrival
tiles looked like one-tile closets.

`SwitchableWallCorner` (type 1) is not the answer. It appears 4507
times in the whole file, **all on L13**. Petrich (“everywhere in The
Labyrinth”) and Semmler (“used on The Labyrinth to change the
direction of walls”) are right about the clustering and wrong as an
L9/L10 theory. L9 and L10 have zero type-1 walls.

Every frontier edge of those closets is type 33, texture **127**.
Texture 127 is the dominant type-33 face on 7–15 (581 on L9, 499 on
L10). It is not a holographic marker. Treating every 127 wall as
passable also opens L7, so that shortcut is wrong.

The known walk-through walls in this game are Type 5 `SecretDoor`
sectors. Descriptions marks them as “False Wall” on They May Be Slow,
…But They’re Hungry, Evil Undead Phantasms, and Happy Happy. The
Guide’s line for the Blue Crystal on L3 is “Walk through the wall.”
L9 and L10 have no Type 5.

The actual fix is the movement rule: **type 32 blocks; type 33 is a
drawn face.** No level mixes the two. Levels 7–15 are the crystal
wall theme (`.256` 194) and store only 33. Under `{32}` L9 is
415 / 415 and L10 is 574 / 574. The “sealed content” reading is
disproven.

---

## Crystals do not open those walls

The item table has Yellow (Talk, 0x40), Blue (Freeze, 0x41), Orange
(Burn, 0x42), Mottled / Purple (0x44), Green (0x45), Black (0x46).
Descriptions places them here:

| Crystal | Level | Before L9 / L10? |
|---|---|---|
| Yellow | L1 Never Stop Firing | Yes, if you take the upper path first |
| Blue | L3 They May Be Slow | Yes |
| Orange | L7 Wrong Way! | Yes, on the recommended route |
| Violet | L13 The Labyrinth | After |
| Green | L17 Watch Your Step | After |
| Black | L23 Where Only Fools Dare Tread | After |

L10 is on Ground Floor’s south-east ladder. A player can walk there
with no crystal at all.

The harvested `docs_web` tree does not contain files named
`BasicSurvivalGuide_1_1.txt` or `Walkthrough.txt`. The same text
lives in Pathways Guide v1.1 and in `ItemCheatFile_3_10.txt`:

- Feel the Power — “Problem(s): None / Solution(s): None.” SW ladder
  up to Ground Floor, NW down to A Plague of Demons.
- We Can See in the Dark — “Problem(s): Frenzy rats / Solution(s):
  turn off flashlight.” SW up to Welcome, Tasty Primate; NE down to
  Happy Happy.

Neither walkthrough mentions a sealed wall, a crystal discharge, or a
hidden passage on those floors. They treat both as ordinary
traversable maps.

Decrypted `scri` agrees. L9’s corpse (scri 138, Light Phobic) is
about winged rats and a flashlight: “Get that light away from me!”
L10’s corpse (scri 139, Walter) is about gold ingots and invisible
demons on the level below. The only “walked through the opposite
wall” line is scri 131, on L3 next to the Blue Crystal’s Type 5
secret door — a different mechanic, already identified.

Nothing needed to open those walls. Type 33 was never a collider.
Crystals are talk / freeze / burn / lightning / quake / stone. L10
is on Ground Floor’s south-east ladder; a player can walk there with
no crystal at all.

---

## Phase 0 result table

Movement `{32}`. Reachable = arrivals from other levels’ `LevelChangeList`
plus Type 9, then door-trigger fixed-point. Components counted on
non-Void tiles. Extra components are Type 5 closets (L3/L4), designed
traps / void islands, or the L24 credit graphic — not shattered type-33
walls. Ground Floor 214/214 is Earhart’s T (stem south, bar x=4–28).

| Lv | Name | Non-void | Reach | Comp | Item | Corpse | Trigger |
|---|---|---|---|---|---|---|---|
| 0 | Ground Floor | 214 | 214 | 1 | 116 | 1 | 3 |
| 1 | Never Stop Firing | 478 | 478 | 1 | 175 | 0 | 7 |
| 2 | Lock&Load | 500 | 500 | 1 | 228 | 2 | 19 |
| 3 | They May Be Slow… | 456 | 449 | 8 | 215 | 2 | 0 |
| 4 | …But They’re Hungry | 504 | 503 | 4 | 240 | 1 | 2 |
| 5 | Evil Undead Phantasms Must Die! | 563 | 563 | 2 | 159 | 1 | 0 |
| 6 | Ascension | 195 | 195 | 1 | 109 | 1 | 17 |
| 7 | Wrong Way! | 515 | 515 | 1 | 313 | 1 | 29 |
| 8 | Welcome, Tasty Primate | 459 | 459 | 1 | 316 | 1 | 2 |
| 9 | We Can See In The Dark… Can You? | 415 | 415 | 1 | 289 | 1 | 0 |
| 10 | Feel the Power | 574 | 574 | 1 | 350 | 1 | 0 |
| 11 | A Plague of Demons | 537 | 537 | 1 | 330 | 1 | 10 |
| 12 | Beware of Low-Flying Nightmares | 521 | 521 | 1 | 314 | 1 | 16 |
| 13 | The Labyrinth | 525 | 525 | 1 | 294 | 0 | 0 |
| 14 | Happy Happy, Carnage Carnage | 446 | 446 | 1 | 275 | 5 | 8 |
| 15 | Need a Light? | 505 | 505 | 1 | 300 | 5 | 17 |
| 16 | Lasciate Ogne Speranza, Voi Ch’Intrate | 472 | 472 | 1 | 296 | 0 | 4 |
| 17 | Watch Your Step | 496 | 496 | 1 | 247 | 1 | 52 |
| 18 | I’d Rather Be Surfing | 521 | 521 | 1 | 240 | 1 | 8 |
| 19 | Warning: Earthquake Zone | 172 | 172 | 1 | 138 | 1 | 31 |
| 20 | Don’t Get Poisoned! | 437 | 437 | 5 | 187 | 0 | 0 |
| 21 | Please Excuse Our Dust | 529 | 529 | 4 | 207 | 0 | 0 |
| 22 | But Wait!— That’s Not All! | 496 | 496 | 2 | 255 | 0 | 16 |
| 23 | Where Only Fools Dare Tread | 519 | 519 | 5 | 258 | 2 | 0 |
| 24 | Ok, Who Else Wants Some? | 181 | 33 | 34 | 15 | 0 | 0 |

## What Phase 0 ships

- `docs/FORMAT.md` — standalone spec: Maps layout and enums, the
  two-edge / four-corner sector model, arrival semantics, `scri`
  encryption, corpse mapping, save island, `.256` decompression
  and per-tile layout, per-resource colour tables, Disproven,
  Open questions, credits.
- `formats/pid_level.ksy` — compiles with kaitai-struct-compiler 0.11
  to Python (`tools/generated/pid_maps.py`) and C#
  (`tools/generated/PidMaps.cs`, namespace `Pid.Formats`). The
  generated Python matches `tools/pid_level.py` on all 25 v2.0
  records.
- `tools/export_level.py` — Unity import JSON: 32×32 sectors (type,
  item, type_addl), per-wall `blocks_movement` from `{32}`, doors,
  source/dest level changes, monsters, resolved `.256` ids, arrivals
  into each level, `transition_graph.json` (118 edges),
  `corpses.json` (scri 128+TypeAddl + decrypted dialogue).
- `reference/levels/L00.png` … `L24.png` — final `{32}` renders.
  Ground Floor 214/214 matches Earhart’s T.
- `reference/sounds/snd_*.wav` — all 86 `'snd '` resources.

Phase 0 is closed. Phase 1 can import a level. The `.256` decoder is
no longer the block on textured walls (see below). The Labyrinth
still waits on its load-time generator.

---

## `.256` was a stream of opcodes (2026-09-03)

The “Shapes: enough to know we cannot paint them yet” section above
is the state at Phase 0 close. Four more rounds of statistical
modelling of the packed bytes all failed: PackBits (0/50 exact,
49/50 truncated, identical failure from three start offsets); five
literal-default RLE variants keyed on the high bit (0/50 exact);
“a byte already present in the colour table is a literal” (189
distinct out-of-range values, 0–255); and “sections 1–3 are stored
uncompressed” (compressed-looking bytes begin before v1). Nearest-
neighbour Hamming distance was actively misleading on this format:
it ranked sparse blocks as nearest to everything and produced a
false match against a resource nobody had visited. That trap is
general, not specific to `.256`.

The answer did not come from the packed bytes. The type literal
`2E 32 35 36` sits in CODE 5. Following it to `GetResource`,
resolving the jump-table entry, and reading the 88-byte routine at
CODE 8 offset 2206 gave a two-opcode loop: `b < 0x80` is a run of
length `b+3`, else a literal of length `b-0x7F`. It emits exactly
the declared size on 50/50. The lesson is explicit: the packed
bytes were a stream of opcodes, so every model that treated a
fixed prefix as a header was fitting structure to data that had
none. The 23-byte packed header, the format tag at packed offset
4, colour-table strides 5/7/8, “raw tables at packed offset 29”,
the RAWEND boundary, and the four “malformed directories”
(161/162/167/189) were one artifact — the first literal run of
that stream.

Decompressed space then fell out: an 18-byte header, s0 colour
tables (ColorSpec stride 8, first index 3), s1 32-byte records
counted by `tile_count`, s2 16-byte geometry records counted by
`(v3-v2)/16`, s3 pixels. Index 2 is transparent. `s1.u16[0]` is a
class tag: 1–5 walls (`offset, HEIGHT, WIDTH`, row-major), 6
everything else (`offset, WIDTH, HEIGHT`, row-major). Geometry is
not in s1. Padding is `align4(w×h)` between tiles, 50/50.

Rendered content identified art that published fan sprite rips do
not contain — 128 (HUD and inventory), 187 and 191 (title
landscape and chrome logo), 190 (automap glyphs and compass).
That is consistent with those rips having been captured from
gameplay rather than extracted from the file.

What remains is selection, not pixels: which of 192’s descending
tiles the engine draws for a given wall; how floors and ceilings
(195–202) are chosen, since no `texture_list` slot names them;
and whether s1 `i16[4]` / `i16[5]` / `i16[6]` are world-space
size and a draw origin.

---

## Dated log (compressed)

The experiments that produced the paragraphs above, in the order they
were run. Reports live under `reference/docs/`.

- **2026-09-01** — Toolchain, harvest, `STR#` decode, Maps stride,
  dpin / scri first pass, Petrich / Semmler / Gray read, first
  parser, sheet compare, clut 256 identified as copyright, corpse
  TypeAddl global, Item ≠ dpin group.
- **2026-09-01 (later)** — `.256` offset table at byte 7, per-resource
  palettes, PackBits and friends fail, raw-from-258 viewer.
- **2026-09-01 / 02** — Saves: templates vs player island, 8-byte
  inventory, flag bits, 0750/0752 unidentified, 2876 is not a struct.
- **2026-09-02 r17** — Row-major confirmed. Ground Floor 214/214.
- **2026-09-02 r18** — Corners are not walls. Short walls do not seal.
- **2026-09-02 r19** — DoorTrigger adj4 fixed-point. L11/L12/L14 grow.
  L9/L10/L13 have no doors.
- **2026-09-02 r20** — Arrivals from source `LevelChangeList`. L13
  4→202. L20 trap identified. L24 marked special.
- **2026-09-02 r21** — Type-1 is Labyrinth-only. L9/L10 frontier is
  ordinary type-33 / tex-127. Crystals and walkthroughs do not open
  those walls. Phase 0 deliverables written.
- **2026-09-02 r22** — Brute-forced all 30 WallList edge pairs.
  Slots 0 and 1 are the only slots that ever hold type 32/33.
  Slots 2–5 are corners (CutoffCorner only). `(0,1)` is the only
  assignment that passes GF 214/214, the T shape, L13 centre, and
  L3/L4 secret-closet gates. `(1,0)` breaks Ground Floor. Opening
  L9/L10 by using corner slots as edges also opens hidden Type 5
  closets — those pairs are “no walls,” not a correct layout.
  The L9/L10 mechanic is elsewhere.
- **2026-09-02 r23** — Four direction conventions on (0,1) and on the
  mixed slot pairs. Only N/W (0,1) passes every gate. L9 is the
  densest 32/33 level (0.890) and is ringed; L10 is mid-pack. Sealed
  masses hold the corpses and almost all loot, are geometrically one
  blob, and are *not* walkable under stored walls. Item ids are not
  contiguous. Connectivity unexplained under every wall reading.
- **2026-09-02 r24** — Type 32 vs 33 is a perfect band split (0–6/16–24
  all 32; 7–15 all 33, no shorts). 33-as-solid shatters 7–15.
  Winner: 32 blocks, 33 is drawn only. L9/L10 become 1 component and
  fully reachable. L13 stored maze also becomes 1×525 (no 32s).
  Sector types untouched (Petrich sheet still 100%).
- **2026-09-02 closeout** — Dropped the L13=202 gate (artifact of 33
  as collider). 32/33 recorded as a hard per-level partition
  (authoring-tool signature; 7–15 = crystal theme). Final `{32}`
  renders, Unity JSON + 118-edge graph + corpses.json, 86 `'snd '`
  WAVs. Phase 0 result table below.
- **2026-09-03** — `.256` decoder read from CODE 8 @2206, not
  inferred. Four statistical models of the packed stream had
  failed; Hamming nearest-neighbour had ranked sparse blocks as
  nearest to everything. Decompressed layout 50/50; index 2
  transparent; s2 field order class-dependent; s3 partition with
  align-4 between tiles 50/50. 128 / 187 / 190 / 191 are file-only
  art, absent from published gameplay rips.
