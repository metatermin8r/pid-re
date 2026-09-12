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
range 0..399 globally, shared across sector types. It is the head of
a chain into the 500-entry object table at world-state `+$03D8`
(CODE 5 @17190). It is not a catalog index and not a dpin row.

---

## Dead ends that looked promising

Several early readings failed cleanly and stayed failed.

**`dpin` as a directory.** The first four bytes look like `0x000c0b3c`
as a u32, which exceeds the resource. They are `u16be 12, 2876`.
409 × 564 divides the file and scores almost nothing on a stride scan;
the blockmap is diagonal. Treating the payload as 2,876 rows of 80 was
a failed model. `dpin` is the save-file initialiser: a 2,876-byte
header plus 25 × 9,112-byte world-state blocks (CODE 2 @9262). Closed.

**`scri 128+N` as level N.** No level-name bytes appear in any `scri`.
Gray and Semmler both call these corpse-dialogue scripts. The working
map is `scri_id = 128 + Sector.TypeAddl` on a Type 6 sector. TypeAddl
values are globally unique: `{0..27}` plus one `200` (Carlos). Dead
Scripts headings skip 129 and 135; both resources exist and decrypt to
real dialogue (Lock&Load’s Cold Guy, Ascension’s Joachim).

**`clut` 256 as the game palette.** It is the 1993 Bungie copyright
notice stored under type `'clut'`. The real palettes are `clut`
128–135, eight 15-colour Mac tables.

**The 25 save blocks at 39,392 as templates.** That filing is
void. The blocks **are** live world state. Only the offset was
wrong: homes start at **30,540**, stride 9,112, indices 0–24. A
second name adding 9,112 bytes is per-save file growth, not
evidence that the 25 homes are immutable. Pickup flag bits on the
player island (`0x0840` / `0x0864`) exist in addition to the
block `FSWrite`, not instead of it.

**The 2,876-byte player stride as unproven.** Confirmed. Record
`k` is at `k*2876`. Bytes `[0, 1780)` of the file are a separate
name and level table read into A5 `-$1ADC`; they overlap record 0
on disk but are not part of it. The live island begins at
`k*2876 + 0x06F4`. 2,876 is the player-record stride; 9,112 is
per-save file growth. They are unrelated.

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
for X / Y / level do not apply. Live X / Y are 10-bit fixed point at
`+0x074A` / `+0x074E`; the integer words at `+0x090C` / `+0x0918` /
`+0x091A` are inert display mirrors (confirmed in game). Inventory is
8-byte records `(id, state, qty, catalog)` starting at `+0x0A00`.
Catalog numbers are a lazy free-list, not an index into another table.

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

## The same method, one more time (2026-09-03, later)

The `.256` decoder was the first time this project stopped
modelling bytes and read the instruction stream. That same
sequence — type literal, jump table, linear disassembly — then
answered the descriptor, the object table, and the 9,112-byte
save block.

The `.256` type literal `2E 32 35 36` sits in CODE 5. Following
it to `GetResource` and through the jump table landed on CODE 8
@2206. Four rounds of statistical modelling of the packed stream
had failed (PackBits; five high-bit RLE variants; “a colour-table
byte is a literal”; “sections 1–3 are stored uncompressed”).
Hamming nearest-neighbour ranked sparse blocks as nearest to
everything. The disassembly answered the codec in two rounds:
the 88-byte loop, then the decompressed header.

The jump table had to be resolved first. CODE 0 holds 355 entries
of 8 bytes from offset 16, base `A5+0x20`. The table’s segment
field is +4 versus every segment header; trusting the headers
mis-targets every JSR. The binary also contains 68020
instructions (`EXTB.L`, `MULU.L`, scaled index extensions). A
68000 decoder silently wrecks those sites.

From the same cache the loader fills, CODE 5 @1618 unpacks a
16-bit wall word: bits 0–6 s1 index, 7–12 selector, 13–15 tag.
A `PID_Sector` `{u8 wall_type, u8 texture}` pair is that word,
not two independent bytes. Tag 0 is never drawn. Pillars never
enter @1618. They enter @12052 when `(type & 0x0F) != 0`, call
@17190, and reach the sibling unpacker @1454. `Sector.item` is
the index: `rec = [-$1A86(A5)] + $03D8 + item*16`.

`-$1A86(A5)` is a 9,112-byte buffer (`NewPtr $2398` at CODE 4
@1466, JT 152). CODE 2 @10066 `SetFPos` to `index*9112 + 30540`
then `FSRead`; @10174 is the matching `FSWrite`. The 25 home
blocks start at file offset **30,540**. An earlier window at
39,392 was 8,852 bytes late — the live-state claim was right,
the offset was not. The object table is 500 × 16 bytes at
+0x03D8: X/Y as 10-bit fixed point with a `$200` centre, a
packed descriptor, flags, unused `+0x0C` (zero on 27,904 live
objects), and a next-index link (`$FFFE` free, `$FFFF` end).
JT 157/159/158/164 insert, update, free, and wipe.

`dpin` 128 is the save-file initialiser. CODE 2 @9262
`GetResource`s it, `HLock`s, writes 28,760 + 2,876 @ position 8
+ 227,800 from offset 2,876, and `ReleaseResource`s. The handle
is never stored. Semmler’s item-template guess, and this
project’s long “purpose unknown”, are closed.

The lesson is the same as `.256` and is now load-bearing:
several long-standing open items were data questions only in
appearance. They were code questions. Static analysis of Maps,
saves, and `dpin` could not have closed them, because the
answers are displacements, trap numbers, and bit fields in the
68020 stream. Four modelling rounds on `.256` produced
confidence and nothing else. Reading CODE 8 @2206 produced the
decoder.

The 100% `Sector.item` position miss was the tool using
`(raw − $200) >> 10`. With `raw >> 10`, all 5,866 map refs on
the 25 home blocks resolve directly (zero failures) on all four
unique saves. Homes 0–24 are byte-identical to `dpin` 128 at
`2,876 + N*9,112`. That — not a clock — is why the captured
saves are a pristine corpus.

Still open after this pass: the `$217F` anomaly; what CODE 5
@17190 uses as an object’s vertical extents; the four smaller
tables inside the 9,112-byte block; the L13 maze generator.

---

## The vertical constants, and the inventory (2026-09-05)

The rest of this arc is the same method applied past the
object table.

`.256` was solved by disassembly after four statistical models
failed. The descriptor format (CODE 5 @1618 / @1454) and the
object table (CODE 5 @17190, world block `+$03D8`) came next.
World state is the 9,112-byte block at file offset 30,540, not
a template bank at 39,392. `dpin` 128 is that save file’s
initial image: 2,876-byte header plus 25 blocks.

`+0x074A` had been decoded correctly from the first save pass
and labelled wrongly for months. It is live X, 10-bit fixed
point, not a game clock. The derived “113–119 seconds into
play” is void. Confirmed in game: editing it teleports,
including into a wall — the load path applies it without
validation. CODE 2 @8546 builds X and Y at @8762–8788 with
`LSL.L #10` then `ADD.L #$200` and copies eight bytes to
player+0x56 at @8830. `+0x074E` is Y. `+0x0752` is facing on a
512-unit circle (CODE 4 @1028 returns 0..511; CODE 4 @4 / JT
331 wraps by `±$200`; 0 = west, 128 = north, 256 = east, 384 =
south). Writing `+0x0748` together with those two longs warps
level: a save written for level 7 arrived on a crystal-walled
floor populated with ghouls (in-game test).

Proven inert in game: `+0x090C` (level), `+0x0918` / `+0x091A`
(integer X/Y), and file `0x06C2` (CODE 2 @8436 writes it FROM
`-$1AD8` — a sink). `+0x091C` was written up as confirmed inert
without ever being tested; it holds 0, 1, 2, 12 across the nine
records and is UNTESTED.

Vertical geometry was measured from screenshots three times and
got 1,080 raw units for wall height. One disassembly got the
constants exactly. CODE 3 @13656 stores −614 and @13664 stores
+409 on the view record at A5 `-$1542`. Wall height is 1,023 —
one short of a sector; 614 + 410 would be 1,024. The eye sits
at 614/1023 ≈ 60% of wall height, not half. Vertical FOV is
fixed at `2*atan(0.6)` = 61.9275° (CODE 5 @9856,
`view+$1C = trunc(5*H/6)`). Horizontal is `2*atan(0.8)` =
77.3196° (CODE 5 @9806, 5/8). The tangent ratio is 4/3.
`height10` at level `+0x084` is the HUD depth readout (CODE 3
@8762, `DIVS.W #10`, `_DrawString`), not the world’s vertical
scale. The player has no stored Z.

The 68020 function inventory is at
`reference/docs/code/inventory/`: 771 functions, 355
jump-table entries, 46,024 instructions, 13 unknowns, 2,249
call-graph edges, 232 A5 globals. Trap counts match an
independent scan on all 17 CODE resources. CODE 11 and CODE 15
are C runtime (`_doprnt`, `ZEROBUFFER`, `DATAINIT`) and contain
no game logic.

Two methodological traps are worth keeping. Nearest-neighbour
Hamming distance ranks sparse blocks as nearest to everything;
that produced a false `.256` match against a resource nobody
had visited. And a field can be decoded correctly and labelled
wrongly for months, as `+0x074A` was.

The recurring lesson is now load-bearing: several long-standing
open items looked like data questions and were code questions.
Static analysis of Maps, saves, and `dpin` could not have
closed them. The answers were displacements, trap numbers, and
immediates in the 68020 stream.

The behavioural layer — combat, monster AI, most item effects,
door triggers — is still unread. The catalog, the inventory
tree, and the fire → magazine path are not.
**[later:]** the fire path (CODE 7 @16404), damage switch
(@17570), hitscan, RoF timer, and the four `_NewCWindow` panels
are now in `docs/FORMAT.md`. **[later:]** creature AI (state
@1434, detection, pathing, attack, death, L13/L24 spawn) is in
`docs/FORMAT.md` **Creature AI**. Most item effects remain open.
It is searchable:
225 functions have zero traps and exceed 100 bytes; 89 A5
globals are written in exactly one place.

---

## Two fields equal is not a name (2026-09-05)

The item catalog at A5 `-$14D6` is 71 × 16 bytes, installed by
Think C `_DATAINIT` (JT 305, CODE 11 @4) from a packed block in
CODE 11. JT 217 formats STR# 2016 (`Total Weight: %3.2f kg.`)
from a sum of catalog w3 divided by 28 (`MOVEQ #$1C`, `_FP68K`
`$0006`). That is the weight field. w5 is a different
accumulator: pickup adds it to player `+$0C`, drop subtracts it.
w4 and w6 are the per-item fill and the container limit in
CODE 6 @508 / @616.

A previous pass named w4 and w6 “magazine capacity” and “weapon
capacity” because every weapon/magazine pair held the same
number. Two fields being equal shows they hold the same *kind*
of quantity. It does not identify the quantity. The pairing was
written up as a clean cross-check when nothing had been checked
against the running game. A Walther magazine holds eight rounds
(UI, saves, `dpin` t2: max 8, 155/180 authored as 8). Catalog
w4 for that id is 10. The M-79 is single-shot and its w6 is 5.
The live round count is the instance record’s +$4, authored per
world item and copied on pickup. Fire decrements player `+$19A`
and then the magazine’s +$4; JT 257 sets `+$19A` to 1 on ready.
**[later:]** `+$19A` is the rate-of-fire timer in ticks, not
ammo. The decrement is the magazine **child’s word 2** (that
record’s +$4) at CODE 7 @16730, reached as `+$198` → weapon →
word 2 child slot. JT 257 still sets `+$19A` = 1 on ready.

The error survived because the numbers looked plausible (10
rounds in a Walther, 5 in a grenade launcher) and no independent
observation was sought until the game contradicted them. The
inventory’s fourth word was the same class of mistake: small
integers in a hole-filled array were named “catalog instance
ids” when CODE 6 @5838 uses them as next-sibling slots. Equality
and plausibility are not a code site.

File `+0x0A00` was the same class of leftover: an earlier brief
called player `+$30C` the live inventory, so the save editor
parsed 48 bytes of zeros as six Maps and concluded the
serialised form used different slot numbers. The I/O blob is a
raw dump. Inventory is at `+$33C` = file `+0x0A30`. The tree
is coherent there; it is not a second format.

STR# 2013 formats player `+$0A` / `+$0C` as “scored %d of %d
points and recovered $%d.%d%s in treasure.” That is a recap
drawn into a GrafPort (CODE 3 @8762 `_TETextBox`), not a live
HUD. Calling it a score system overstated what the call sites
show.
**[later:]** it *is* the live Progress panel on the Player
window (Health / Power / Progress / Weapon Proficiencies), not
an end-of-game recap. The Cedar Box’s class-0 Use path is a no-op stub; calling
it a puzzle container overstated the insert gate.

---

## The catalog was already in the A5 image (2026-09-10)

The item catalog was assumed to need an emulator dump: seventy-one
records of initialised globals, compressed by a Think C runtime
nobody had read because CODE 11 was labelled “no game logic” and
skipped. The location was already in the notes — A5 `-$14D6`,
installed by JT 305 — but the bytes had never been expanded.

The expander was read from CODE 11 at file offset 4 (68020) and
reimplemented in `tools/expand_datainit.py` from those
instructions, not from MPW `%_DATAINIT` docs and not from the
`.256` RLE. The packed stream is 4447 bytes at CODE 11 +454; it
terminates on its own and emits 7592 bytes, matching CODE 0’s
below-A5 size. Mapping is `image_offset = 7592 + a5_displacement`.

The mapping was proven by prediction: the fourteen-value Cedar
Box admit list at A5 `-$1066` was known before the image was
cut, and the expanded bytes at image +3394 were exactly
`2, 45, 46, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61`.

Three values withheld from the extraction prompt as a blind
test all matched: the proficiency thresholds at `-$A2C`
(indices 0–6), the sum of catalog w2 across 71 rows (44), and
the identity of item id 9 (Red Velvet Bag, w3 = 2).

The first pass at JT 209 (CODE 6 +106) omitted eight bytes
between the `and.w $2(a3), d0` and the `bne` — the
compare-to-1 idiom — and annotated that branch backwards as a
result. A second pass printed every offset. Cost of an
incomplete listing: one extra round, and a published suffix
rule that had the empty-magazine string as a general default
and the sense of state bit 0 flipped.

---

## Reading the fire routine, and two shade-table bugs (2026-09-12)

The fire rate was chased three times by feel before anyone read
the routine. Reading CODE 7 @16404 to @17100 settled every
question in one pass: the table at A5 `-$810` is five records
of fifteen words; w7 is a random muzzle-flash flag, not
semi-versus-automatic; w13 is both the frame count and the
mirror offset because the mirrored tiles sit next to the
unmirrored ones; the poll is coarse (JT 8 returns 0 under two
ticks) but the timer counts down at the full rate; reload
happens when that timer expires, not when you fire; a new
burst overwrites the rounds just counted with w9; damage is
`base + (rank - cells) * base / 5` with no roll; player shots
including the M-79 are hitscan.

The overlay is tag 6, resource `128 + w2`, drawn bottom centre
of a 384×288 view. Index 0 is padding and must be discarded;
index 2 is the artwork’s transparent colour. The tile lift is
not used on the gun.

The two shade-table bugs were found by comparing a resolved
tile against a known-good render and matching on pixel counts,
which are unique per colour and therefore unambiguous.
`plant_clut` overwrote `unique[106..120]` without advancing its
index and erased resource 128’s blue chrome; `force_nonzero`
remapped later whites to 238 238 238. Both are fixed in
`build_own_lut_arrays`. All 216 tables were re-emitted from
each resource’s own ColorSpecs; 210 changed. The tables were
never level-dependent — the merge made them look that way.

The four window rectangles had been transposed. `_SetRect` is
Pascal order, so a long’s high word is the bottom. At 640×480
the view is 384×288 at (4, 23), and the composition closes
exactly.

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
  inventory, flag bits. `+0x0750` later identified as the low 16
  bits of live Y. `+0x0752` still unidentified. 2876 is the I/O
  blob, not a fully parsed struct. `+0x074A` was labelled a clock
  from this pass; that label is void.
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
- **2026-09-03 (later)** — Same method past `.256`: jump table
  (355 × 8, segment field +4), 68020 decode required. Descriptor
  bit fields; pillars via @1454 not @1618; `Sector.item` is an
  object-table index; `-$1A86(A5)` is the 9,112-byte world-state
  block, FSRead/FSWrite by level; `dpin` 128 initialises the save
  file. Several “data” open items were code questions. The
  later `raw >> 10` pass resolved all 5,866 `Sector.item` refs.
- **2026-09-03 (position)** — `+0x074A` had been decoded and
  mislabelled as a game clock from the first save pass. Three
  rounds searched `0x0000–0x0749` for a live pose that was
  already in the table. The in-game test that found it was one
  edit of `+0x074A`: the player teleported, including into a
  wall. Companion `+0x074E` is Y. Same 10-bit fixed encoding as
  the object table (`raw >> 10`; writer adds `$200`). CODE 2
  @8546 / @8762–8788 / @8830 writes those two longs to
  player+0x56 = file `k*2876 + 0x074A`. The “113–119 seconds
  into play” reading is void. The corpus is still pristine
  because home blocks 0–24 are byte-identical to `dpin` 128.
- **2026-09-05** — World-state offset corrected to 30,540; object
  table 5,866/5,866 with `raw >> 10`; `dpin` layout is header plus
  25 blocks. Vertical constants from CODE 3 @13656 / @13664 and
  CODE 5 @9856 / @9806; screenshot 1,080 and half-height eye are
  void. Level warp via `+0x0748` plus live X/Y confirmed in game.
  `+0x091C` marked untested. Function inventory 771 / 355 JT.
- **2026-09-05 (catalog)** — Item catalog w3 is weight (printed
  kg = Σw3/28, JT 217 / STR# 2016). w4/w6 are container fill
  and limit, not round counts: Walther magazine holds 8 against
  w4/w6 of 10; M-79 w6 is 5. Inventory word 3 is next-sibling,
  word 2 is overloaded. Method: two fields equal was treated as
  confirmation of what those values meant.
- **2026-09-05 (save inventory)** — File `+0x0A00` is player
  `+$30C`, not a packed serialisation. The live tree is at
  `+0x0A30` (`+$33C`); slot numbers survive I/O unchanged.
  `+0x06FE` is points (`+$0A`), not a flag. STR# 2013 is a
  status-window recap (`_TETextBox` in CODE 3 @8762), not a live
  HUD. **[later:]** live Progress panel, not an end-of-game
  recap. Cedar Box class 0 is a JT 214 no-op; it does not
  duplicate its child. Test saves in `out/item-tests/`.
- **2026-09-10** — Think C DATAINIT image expanded from CODE 11
  (JT 305). Mapping proven by the 14-word Cedar admit list.
  Catalog class domain 0 and 2–8. JT 209 inventory line: 2008[0]
  is empty-magazine only; class map is not class−3. First
  disassembly of that routine dropped eight bytes and reversed
  a branch. See the narrative section above.
- **2026-09-12** — Weapon table named (15 words). Fire path
  read in one pass after three feel-based rate chases. Shade
  tables rebuilt from each resource’s own ColorSpecs; 210 of
  216 changed. Window rectangles un-transposed. See the
  narrative section above.
