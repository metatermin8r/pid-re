# Pathways Into Darkness — file format notes

Canonical *observed* layout. No offset, field size, or type belongs here
until it has been seen in bytes. Hypotheses go in a clearly marked section
and are moved here only after a parser assertion passes.

Kaitai specs in `formats/` are the machine-readable counterpart. Update
this file in the same commit as any parser change.

Per-file type/ID dumps: `reference/` (see `reference/INDEX.md`).

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
Custom types seen: `scri` (30), `dpin` (1). Meaning not asserted.

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
| Demo / v2.0 `Sounds.rsrc` | `snd ` only |

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
Kaitai-generated Python: `tools/generated/pid_maps.py`.

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
| 0x84 | i16be | `height10` (metres × 10). All 25 match Hex reps_notes **by name**. Record 24 is −32768. |
| 0x86 | i32be × 2 | `unknown1`. High words are 0; low words vary. Unknown. No runtime effect observed (Semmler / Torch). Not any tested checksum (u16 sum / XOR / byte-sum / CRC-16 CCITT / CRC-16 IBM). Deprioritised. |
| 0x8E | i16be × 8 | `texture_list`. −1 = none. Low 12 bits + 128 = `.256` id. High 4 bits = variation 0–3 (all four occur). Slot 0 is always walls (192/193/194). Slots 5–7 are often −1. Slot 7 is **never** set. No slot maps to floor/ceiling resources 195–202. |
| 0x9E | 15 × 8 | `door_list`: i16 x, y, direction (0–3), texture |
| 0x116 | 20 × 8 | `level_change_list`: i16 type, level, x, y |
| 0x1B6 | 3 × 4 | `monster_list`: i16 type, frequency |
| 0x1C2 | 1024 × 16 | `sector_list` |

An earlier hex dump that put `0x41d9` at 0x84 was misaligned. Height10
at 0x84 is 0 for Ground Floor.

`unknown1` is **not** uncleared name-slot garbage: the values change
with the level.

Level-change `type` 4 appears (But Wait → Ground Floor). The documented
0–3 enum does not cover it.

### Sector (16 bytes) at `record + 450 + 16*i`

| Offset | Type | Field |
|---|---|---|
| 0 | 6 × (u8 type, u8 texture) | walls: Y, X, then four corners |
| 12 | i16be | item (−1 = none). Per-level instance id, not a catalog / loot index. Unique within each level. Range 0..399 globally; 376, 377, 378, 383, 393 unused on all 25. Shared across sector types. |
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

### `dpin` 128 (230676 bytes)

Not a directory of file-size offsets: `0x000c0b3c` as a u32 exceeds the
file. First four bytes as u16be pair: `12`, `2876`.

Stride scan (`tools/stride_finder.py`, zero-pairs excluded):

- Top scores are **every multiple of 16** (16 → 0.551, 32 → 0.520, …
  80 → 0.470). Non-multiples of 16 sit at ~0.05.
- `409` and `564` divide the file exactly (`409×564`) but score ~0.0045.
  Blockmap width 409 is **diagonal** (wrong phase).
- `2876×80 + 596 = 230676` exactly, and u16be at `0x02` is `2876`.
  Bytes around `0x254` (596) are zeros. Blockmap width 80 is **vertical**.
  After offset 596: 2876 rows of 80; 2836 rows have at least one nonzero.
- Inside those 80-byte rows, nonzero-column counts repeat every 16 bytes.

Prefix hex and u16be runs: `reference/dpin_header.txt` (24 nonzero bytes
in 596). Column counts: `reference/dpin_columns.txt`. Slot test:
`reference/dpin_slots.txt` — five 16-byte slots are **not** identical
(`all five profiles identical: False`) and slot 0 is **not** a distinct
header profile. u16 range histograms: `reference/dpin_u16_ranges.txt`.

Plots: `reference/stride_scores.png`, `reference/dpin_blockmap_w*.png`.

Hypothesis *Sector.Item → dpin group index* is **not supported**:
- Observed: every `Item != -1` is in `0..399` (5866 hits, 395 unique,
  none `>= 2876`). Range does not falsify an index into 2876 groups.
- Observed: group 42 (offset `596+42*80`) is not Ground Floor loot.
  Ten 8-byte rows look like coordinate/flag pairs, not inventory.
  No field equals quantity 8, 7, 3, or 4 as an item count.
- Observed: groups that *are* inventory-shaped (`u16be id, state, qty,
  catalog` with `id` matching ItemCheatFile `00..46`) sit mostly at
  indices `600+` and are **never** a `Sector.Item` value.
- Observed: corpse `Item` groups (e.g. John Doe `114`) are empty /
  `ff fe` tails, not Walther + Mein Kampf.
- Inferred: dpin contains item-shaped 8-byte records, but
  `Sector.Item` does not select a floor-loot group. Prefix is still
  `u16be 12, 2876` plus 22 other nonzero bytes in 596; not a 0th group.

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

### `.256` shapes

50 resources in v2.0 `Shapes.rsrc`. IDs: 128–137, 139–142, 148–167,
187–202.

Header (7 bytes) then four `u32be` offsets at byte 7. Those offsets
are into the **decompressed** buffer (`u32@0`), not the packed file.
Confirmed on 46/50.

| Bytes | Observed |
|---|---|
| 0–3 | u32be size (inferred decompressed). 195–202 all store **33144**. |
| 4–5 | `u16be`. `0x99` on most; also `ff`/`c5`/`81`/`88`/`8c`/`9b`/`d0`. Not a codec id. |
| 6 | frame / image count, **not** a colour count (128→59 vs 15-ish clut entries). Floor/ceiling = 2. |

Section sizes differ by role. Floor/ceiling 195–202 share one pattern:
`offs = [280, 344, 376, 32768]`, sizes `[280, 64, 32, 32392, 376]`.
`offs[3] == 32768 == 2×16384`. `u32@0 - offs[3] == 376 == 2×188`.
`byte6 == 2`. Two 128×128 8bpp images plus two 188-byte headers.

Each resource carries **its own** colour table. Index spaces overlap
because resources reuse slots differently — that is expected, not a
conflict. Do not build a master 256-colour union. Petrich’s “128 sets
overall color table” is approximate.

- Compact 5-byte records from offset 29: `u16be index, u8 kind=3, u8 gray, u8 0x81`.
  On 195 **and** 198 this is indices 3–16 = `FF, EE, …, 22` (true gray).
  198 also has kind=4 records mentioning index 18.
- 8-byte Mac clut runs later on some resources (high byte == low byte
  per channel). Use that resource’s table for that resource’s pixels.
- Resource 128 covers 20–33, 36–40, 52–56, 68–81, … (not 0–N).

#### Packed layout on 195–202 (round 10)

Bytes **200–256 are identical** across all eight floor/ceiling
resources. The first byte that varies is **257**. Shared fields just
before pixels: `u16be` 128 at file offsets 229, 233, 237, 244, 251,
253; `u16be` 16384 at 249; `u16be` 256 at 235. Packed `[23:211]`
(188 bytes) is the shared compact gray + start of the 8-byte clut —
format constants, **not** a per-image compression flag.

The last 376 packed bytes differ in every position across 195–202
(pixel / RLE payload).

#### Discriminator (rsrc 195 own table = indices 3–16)

Packed slice `258..end` (31370 bytes):

| | 195 (31628) | 196 (32727) | 198 (18545) |
|---|---|---|---|
| in 3–16 | 25242/31370 = **0.8047** | 28880/32469 = 0.8895 | 10440/18287 = **0.5709** |
| OOR / KB | **195.35** | 110.54 | **429.10** |
| 0x80+ / KB | 85.2 | 31.0 | 119.2 |
| 0x00–0x02 / KB | 92.3 | 31.1 | 95.3 |

198/195 OOR-density ratio = **2.197** (more OOR/KB in the most
compressed resource). 198 also has 2548 × `0x11` and 1184 × `0x12`;
those are outside 3–16 but 198’s own records mention index 18, so
they may be extra pixel slots. Subtracting them, remaining OOR/KB
is ~225 vs 195’s 195. The **0x80+** density still tracks packed size.

195 OOR gaps (first 200): median **2**, 102/200 gaps are 2, 155/200
≤ 8. Clustered, not uniform blocks, not random. Hex at `0x110+`:
`00 08 88 0a … 00 09 81 08` — RLE controls interleaved with 3–16
literals. Histogram of `00`/`01`/`02` is geometric (1793 / 763 / 338).

Raw 16384 from 258 is recognisable mottled gray with salt-and-pepper
(`reference/shapes/195_raw_a.png`). Second chunk from 16642 has 14986
bytes available (overrun 1398); in-palette 0.7664 with no sudden
OOR spike — not “first image raw, second compressed”. 198 cannot
hold a second raw 16384 (only 1903 bytes left).

#### Tried decompressors (none closed)

`packbits_until` / `highbit_until` always emit exactly `target` if
input remains; “EXACT” is not a natural boundary. Leftover packed
bytes are the tell.

From packed `@23`, restarting at each decompressed section:

| scheme | s0–s2 | s3 (32392) | leftover |
|---|---|---|---|
| packbits | exact | exact, cons 14954, end 15390 | **16238** |
| highbit_run | exact | **31362 / 32392** (short 1030) | 0 |
| rle90 | exact | 31586 / 32392 | 0 |
| unsigned_literal | exact | 29845 / 32392 | 0 |

Two independent 16384 runs after a 376-byte PackBits header `@23`:
PackBits A+B exact, end 15278, leftover **16350**. Whole-stream
PackBits `@23` ≈ 67263 ≈ 2×33144 — leftover is the rest of an
over-expanding stream, not a second valid image. PackBits on the
first 376 bytes destroys the compact clut (`0x81` treated as a
repeat opcode).

highbit `@258` two 16384: A exact cons 16392 (barely compressed
because leading 3–16 bytes are eaten as copy-counts), B
14707/16384. Same ~1170-class short as the whole-stream miss.

Discriminator-aware RLE (3–16 = literal, `00–02` = copy, `80+` =
repeat) overshoots 195 (40605) and undershoots 198 (20981).
Per-row PackBits/highbit (restart every 128 pixels) produces both
128×128 frames on 195 but leaves 12 KB unread and shears the stone.

#### Four resources that fail the 4-word table

Byte 6 is still a small frame count (same character as the other 46).

| ID | packed | u32@0 | b6 | u4 | table | Petrich |
|---|---|---|---|---|---|---|
| 161 | 14200 | 28992 | 5 | `0x8800` | 2-entry OK `[864, 1024]`; 3rd word garbage | corpses |
| 162 | 5090 | 14172 | 4 | `0x8c00` | **3-entry OK** `[608, 736, 768]` | rat things |
| 167 | 9231 | 21184 | 16 | `0x8100` | first u32@7 = 65432 junk; `u32@11` = `[664, 808, 20376, …]` | vine scenery |
| 189 | 12738 | 23272 | 6 | `0x8100` | first u32@7 = 38040 junk; `u32@11` = `[344, 440, 22832]` | ? |

167 and 189 likely use a **3-entry** table starting at offset 11
(one `u32` later than the usual offset 7). Fourth word on several
of these is `33554433` (`0x02000001`).

#### Walls (192) vs AOPID

rsrc 192: packed 167155, u32@0 185992, b6=22,
`offs=[1944, 2648, 3016, 182976]`, own table 62 slots. PackBits
16384-runs from 23: 13/22 exact then EOF. AOPID luma-histogram L1
vs collections 17–21 is 246–358 (weak / inconclusive; remapped).

Floor/ceiling encoding is **not** in `texture_list` (no slot → 195–202).

Viewer: `tools/level_viewer.py` writes `reference/levels/`.
Numbers: `reference/docs/round10_256.txt`.

---

### Saved Games (one real file, 2026-09-01)

File: `data/saves/Saved Games` **267452** bytes. AppleDouble sidecar
creator `påth` (PID). One Pascal name at offset 0:
`Pathways Out of Darkness` in a ~128-byte slot, leftover
`You have scored %d of %d points…`. No second name. Autocorrelation
top nonzero-pair score is only **0.284** at stride 18224 — not a
slot size. Adjacent-pair `data[0:s]==data[s:2s]` never exceeds 0.57
(zeros). This file is **one populated save**, not two near-identical
slots. Unused space is leftover garbage (68k strings `uncompress_world`,
`DATAINIT`), not a zero-filled slot array. Longest zero run = 598.

Observed fields (this file only):

| Field | Offset | Value | Notes |
|---|---|---|---|
| time | 1786 u32be | 5204 | 86.73 s. ItemCheat **correct**. |
| HP / HPmax | 1876, 1878 u16be | 60, 60 | ItemCheat’s 1877/1879 are the low bytes. |
| X, Y | 2328, 2330 u16be | 6, 2 | Sector coords, **not** ×4. Matches save rune (6,2). |
| level | 2316 u16be | 0 | Ground Floor. ItemCheat 1875 = `0x2e` is wrong here. |
| facing | 2332 u16be | 1 then `80 ff` | |
| inventory | 2560 | 8-byte records | ItemCheat **correct** for the first/only game. |

ItemCheat X=1868 / Y=1872 / level=1875 do **not** match. Hex reps_notes
“04 = 1 map unit” does not apply: (6,2) is stored as 6, 2. Not a
constant header shift (deltas 460 / 458 / 441).

Inventory records are `u16be (id, state, qty, catalog)` — same 8-byte
shape as `dpin` elements. This save: Map(cat 1), Watch(worn), Flashlight
(on, qty 2880), Walther ammo×8, Walther(wielded), sack, Colt, Colt ammo,
knife, more Walther clips, Mein Kampf. `FFFF` catalog = last / contained.
Region runs until `FFFF` + non-item garbage at 2728 (~21 record slots
used of a larger table). `dpin` group 3 is a **subset template**
(watch/flashlight/sack/colt/knife), not this live list.

A 9112-byte period with 25 similar `00 00 ff fe` headers starts at
39392 (25 × 9112 = 227800, tail 260). All 25 blocks are unique and
populated (1205–4337 nonzero). Bytes 0–255 of every block are
**identical** (`00 00 ff fe` every 16 bytes, then zeros). Tail
~7644–9111 is the same frame. ItemCheat X/Y/level describe a **1.1**
layout; this file is **2.0**. Coordinates are plain sector indices,
not ×4.

8-byte records from byte 0 of the block (1139 slots) do **not** index
by `Sector.Item`. Live counts vs map Item sets:

| Level | map Items | f0_live | rec[Item]≠0 |
|---|---|---|---|
| 0 Ground Floor | 116 | 74 | 91 |
| 6 Ascension | 109 | 79 | 78 |
| 13 Labyrinth | 294 | 115 | 267 |

No record has any u16 field = 114. Record 114 is
`(51, 0, 8, FFFF)` (Walther ammo ×8), not John Doe. Packed list from
offset 256 looks like typed objects (`f0=0x23/0x3c/0x33…`), not an
Item-indexed array.

`Sector.Item` 114: **not confirmed** as a save-block index. No
before/after pair in this file.

### Saved Games AAA / AAB (two named games, 2026-09-01)

File: `reference/saves/Saved Games AAA-AAB` **276564** bytes
(+9112 vs the one-name file). Not two loose files. Pascal names
`AAA` @0 and `AAB` @128 (two 128-byte name slots). Protocol: knife
only, kill one Headless, save AAA, pick up one Walther magazine,
return, save AAB.

There is **one** Ground Floor packed list. It is **85 records** —
same count and same bytes as the earlier mid-game save’s L0 list.
Pickup did **not** shrink or mutate that list. It is a level
template, not live loot. The 26th 9112-byte region (39392+25×9112)
is **not** a second L0: its header[132:] is a 32×32 LSB bitmap of
explored Ground Floor sectors (save alcove and John Doe set).
L0–L24 headers remain the identical `00 00 ff fe` frame.

Player copies sit **2876** bytes apart (same number as the `dpin`
row count). Isolated AAA vs AAB deltas:

| Where | AAA @2560 | AAB @5436 |
|---|---|---|
| time @0x074A / +2876 | 6989 (116.48 s) | 7010 (116.83 s) |
| X,Y | (7,2) | (7,2) |
| inv[9] | leftover `FFFF 4E56 0000 48E7` (68k `LINK`) | `00 33 00 00 00 07 FF FF` Walther ammo ×7 |
| knife catalog | `FFFF` | `0003` |

Ammo pickup **appends** an 8-byte record at the first free inventory
slot. Quantity is **7**, not 8 — matches Descriptions’ Pink (×7),
not Red (×8), unless one round was spent. Clock delta is only 21
ticks (0.35 s); treat the 2876 stride as a candidate slot, not a
proven two-body layout.

West save alcove Type==1 Items: (5,1)=53, (6,1)=43, (7,1)=57,
(5,2)=44, (7,3)=45. Type-35 `f2` in the L0 template contains 53,
43, 57, 45 but **never 44** (missing in both saves). (5,2) Item=44
is the alcove object that is not a type-35 template entry.

### Bomb Code (closed)

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
| `Sector.Item` is a loot-group index into `dpin` | Group 42 and corpse groups are not Descriptions loot. Inventory-shaped `dpin` rows sit at unused indices ≥600. |
| `Sector.Item` values restart per sector type / are a shape class | Same 0..399 range is shared by pillars, corpses, ladders, saves. 324 values appear with more than one sector type. |
| Descriptions `Ni` (“29i”, “40i”) is the count of `Item != -1` or of Type==1 items | No level matches (Ground Floor 116 / 66 vs 29i). |
| `unknown1` is u16-sum, XOR-fold, byte-sum, CRC-16 CCITT, or CRC-16 IBM of the sector array, whole record (ex-field), name, or header | 0/25 matches on every combination tested. |
| `.256` offset 8 is a raw `u32be` chunk directory | First word exceeds the resource. The four-entry table starts at offset **7**. |
| `.256` resources share one 256-entry palette | Each resource has its own table; overlapping indices are normal reuse, not a decode error. Do not union into a master palette. Petrich “128 sets overall color table” is approximate. |
| Byte 6 of `.256` is a colour count | 128 has b6=59 vs ~15 clut entries; 195 has b6=2 vs 13–15 colours. |
| The L0 packed list shrinks when a floor item is taken | AAA/AAB file and the mid-game save both have the same 85 L0 records. Pickup appends inventory only. |
| `save_AAA` / `save_AAB` are two standalone save files | PID 2.0 wrote both names into one `Saved Games` file (276564). |

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

## Still unexplained (engine blockers first)

1. **`.256` full decompressor** — discriminator says RLE (controls = `00–02` and `80+`; literals in the per-resource table). Per-row reset, u16be row-length prefixes, 128-entry offset tables near 240–280, column-major 128×128, and skip-N-at-row all fail to emit 33144 and consume a 195–202 resource. 198 plus1+highbit per-row/column hits 16384 leftover **85** packed bytes (still RLE-shaped). Raw-from-258 is still the best *view*, not the encoding.
2. **Floor / ceiling selection** — not in `texture_list`, not identified in `dpin`. Resources 195–202 exist.
3. **`dpin` semantics** — 596-byte prefix + 2876×80. Contains inventory-shaped 8-byte rows and other row kinds. Not the `Sector.Item` table. 2876 also appears as a player-copy stride in the two-name save.
4. **`Sector.Item` payload** — unique per level (instance id). The L0 packed list is a **template** (85 records, identical in the mid-game save and the AAA/AAB file; pickup does not shrink it). Type-35 `f2` matches many map Items but not all (44 never present). Live taken-state is unidentified. The 26th 9112-byte region’s header looks like an explored-sector bitmap, not a second L0.
5. **`unknown1` (0x86–0x8D)** — not the tested checksums. `-hacks.txt` patches `CODE 1` BEQ→BRA (`67`→`60`) at 0x02E0 (v1.0) / 0x02CE (v1.1) to skip a “modification check”; the check’s input is unidentified.
6. **Monster / door / level-change runtime** — structs are parsed; spawn and texture pairing not verified.
7. **Level-change type 4** — used (But Wait → Ground Floor); enum 0–3 does not cover it.
8. **Carlos `TypeAddl=200`** — documented draw hack; no `scri 328`.

---

## Negative results (harvest)

- Demo application resource fork does not contain `STR#` 2018 or 2021.
- `pathways-i-d-11.sit` and the Japanese `.dc42` images are installer
  disks, not a ready-to-parse loose Maps file.
- `Pathways_-_2.0.sit` is patchers, not a standalone v2.0 tree. The
  playable v2.0 tree came from `Pathways_1995.dsk`.
