# Work journal

Dated log of attempts, including failures.

---

## 2026-09-01

Set up the Phase 0 working environment on Windows.

- Repo layout from `PROJECT.md`.
- `.venv` + `requirements.txt`: `rsrcfork` 1.8.0, Pillow, numpy,
  kaitaistruct, `machfs` (MIT) / `macresources`.
- Windows `unar`/`lsar` in `tools/bin/` (from
  `https://cdn.theunarchiver.com/downloads/unarWindows.zip`).
- Tools: `unpack_archives.py`, `extract_hfs.py`, `list_resources.py`,
  `rsrc.py`, `write_checksums.py`, `mac_containers.py`.

Original archives were already on `Desktop/PIDOriginalData/`. Copied into
gitignored `data/archives/` (not TheUnarchiver.dmg).

`unar` unpacked every archive. Resource forks survived as AppleDouble
`.rsrc` files (not `._*` sidecars, not NTFS streams).

HFS extract: raw `.dsk` mounts directly; `.image` / `.dc42` mount after
skipping the published 84-byte DiskCopy 4.2 header. Japanese disk 1
worked once we stopped printing Unicode to the console.

Playable trees now on disk:

- Demo: loose Maps (50502 bytes) + app/Shapes/Sounds resource forks.
- v2.0: `Pathways_1995.dsk` → Maps (420850) + app (`vers` 1 = v2.0).

`rsrcfork` via `tools/rsrc.py` listed 85 resource files. Full-game
`STR#` 2018/2021 match the published level-name examples. Demo lacks
those two IDs.

Not done: Japanese/v1.1 installer payload expansion. Fan `PIDMapReader`
sources sit in `data/hfs/Pathways_Extras/PID_Docs Folder/` — not copied
into git.

---

## 2026-09-01 (later)

Raw `--text` on `STR#` was wrong: it decoded the whole blob as Mac Roman
and left Pascal length bytes in the stream. Added `tools/mac_text.py`
(Inside Macintosh `STR#` / `STR ` / `MENU` / `vers`) and
`tools/dump_all.py`. Hex dumps now use a Mac Roman gutter.

Full dump in `reference/full_dump/`: 85 resource files, type catalog,
every v2.0 `STR#` list decoded. Harvest on installers/disk images was
noise and was discarded; only Maps harvests kept.

String-anchored the Maps data fork. Level names sit at `i * 0x41C2`.
v2.0 file is exactly 25 × 0x41C2; demo is exactly 3 × 0x41C2. Names
diverge from `STR#` 2018 in a few spellings. Interior of each record
still unknown.

---

## 2026-09-01 (dpin / scri)

`tools/stride_finder.py`, `tools/blockmap.py`, `tools/scri_compare.py`.

dpin self-similarity is dominated by a 16-byte period; 409×564 is a
factorization only (blockmap diagonals). 80-byte rows after a 596-byte
zero gap line up vertically and `2876` in the header matches
`(size-596)/80`. Not parsed beyond that.

scri 128–155: first u16be == length; shared `04 04 06 0d` then a
4-byte ASCII group. Level names are not in the blobs. 14-byte stubs
are a different layout, not a stripped header.

---

## 2026-09-01 (inventory + dpin/scri pass 2)

`tools/inventory_hfs.py` — 145 files under `data/hfs/`. Game art/audio
are sibling files, not the app fork. `tools/dpin_pass2.py`,
`tools/scri_stats.py`. Slot profiles similar but not equal. u16@2 and
u16@4 both correlate with scri length (r≈0.94 / 0.97); ratio is not
constant. Groups fhpb / l|nn / k|he are contiguous by ID.

---

## 2026-09-01 (CD zip inventory)

`pathwaysintodarkness.zip` from Desktop/PIDOriginalData is a preservation
archive of HFS disk images + PDFs/fan text, not a loose CD filesystem.
No `._*` sidecars in the zip. HFS extract to `data/cd/hfs/` is the same
`Pathways_1995` tree already studied: Maps data fork, Shapes `.256`,
Sounds `snd `, dpin 230676 / 12 / 2876. No second asset layout.
`reference/cd/INVENTORY.txt`.

---

## 2026-09-01 (read the extras docs; stop binary analysis)

Cancelled Maps/Shapes/dpin/scri recon. Printed Petrich `PIDMapReader.h`
(Maps structs), Semmler Torch 0.9.1 (REALbasic map editor, **no TMPL**),
Gray Dead Scripts (`scri` = corpse talk, XOR after 4-byte length),
Petrich `.256` ID list, fan save/item notes. Sector diagram PNG at
`reference/docs/sector_types_sqr.png` (736×752). Maps first 2048 hex
in `reference/docs/maps_first_2048.hex`: one Pascal name at 0, then
the 128-byte name slot (leftover `o Darkness…`). 25 record names at
`i * 0x41C2`. STR# extras still absent from Maps.

---

## 2026-09-01 (parser)

Height10 is at 0x84 and matches all 25 named metre values. The earlier
`0x41d9` reading was a misaligned hex line, not a field swap.

`formats/pid_level.ksy` + `tools/pid_level.py`. 0 wall/type violations
in 25600 sectors. Lock&Load 2 corpses / Need a Light 5. One Corpse
TypeAddl=200 (Carlos). Sheet compare 100% on all 25 at origin 16,
scale 4, pitch 144 (`tools/render_sectors.py`).

scri: XOR from offset 2 with 00 01 02…. clut 256 is Bungie copyright
text, not a 256-color table. Real cluts are 128–135 (15 colors).

---

## 2026-09-01 (corpse scope + dpin item groups)

C1: Corpse `TypeAddl` is global. 29 sectors, values `{0..27}` plus
`200`, no repeats. Semmler (`scri` 128+N) holds; Petrich “contiguous
from 0” is global IDs, not per-level.

C2: Counts match Descriptions (incl. Lock&Load 2, Need a Light 5,
Happy Happy 5, Fools 2, Labyrinth 0, Lasciate 0). Named DeadScripts
headings join to the same corpses. Headings skip 129 and 135; both
are real scripts (Cold Guy, Joachim). Carlos is `TypeAddl=200`.

D1: `Sector.Item` range `0..399` does not falsify a dpin index, but
group 42 and corpse groups are not Descriptions loot. Inventory-shaped
dpin rows exist at unused high indices. Hypothesis fails the group-42
and per-level tests. `tools/round6_corpse_dpin.py`,
`tools/round6_d1_refine.py`, `tools/round6_d1_john.py`.

---

## 2026-09-01 (Phase 0 close / shapes open)

T1: `Item != -1` is unique **within each level** (0 duplicates / 25).
Go for instance-id. Not contiguous `0..N` except The Labyrinth.
Descriptions `Ni` matches neither all-Item nor Type==1 counts.
Range 0..399 is shared across sector types. Five unused values are
unused on every level.

T2: `unknown1` matches the stated sample values. No tested checksum
hits 25/25. `-hacks.txt` modification check is `CODE 1` `67`→`60`.

T3: `.256` offset-8 as raw u32 directory fails. `value>>8` gives 3
sections, not per-sprite frames. Byte 6 looks like a count
(floor/ceil=2, walls=22, items=59).

T4: `clut` 256 recorded as copyright text. Palettes 128–135 dumped.
`texture_list` variation 0–3; slot 7 never used; no slot → 195–202.

T5: `tools/level_viewer.py` → `reference/levels/`. FORMAT.md
finalised with Disproven + Credits. Maps format is solved; shapes
are not.

---

## 2026-09-01 (save + shapes offset 7)

Superdude BinHex decodes to DiskDoubler SEA `Yoyoby.sea` (APPL/DSEA,
data 63414, rsrc 8822). BinHex CRC fails; `unar` cannot expand DD
(`ABCD0054`). Not a raw PID save. `reference/saves/superdude.bin`.

`.256` table at offset 7 as raw u32be gives 3 in-range offsets
(1256, 3144, 4088) then breaks. No 256-entry clut in 0..0x200.
Entropy 4–6.5 bits/byte (not packed). Floor/ceil `u32@0=33144`
= 2×128×128 + 376 (inferred). Cocoa port is App Store only; no
public DMG found.

---

## 2026-09-01 (round 9 — .256 decode)

T3(c): PackBits from after the header/clut does **not** consume the
file and emit 33144. Lengths: packbits@32 = 67257; highbit_run =
31985; 0x90 RLE ≈ 31985. Forcing PackBits to stop at 33144 leaves
~16 KB unread. M1 i16 line codec: 0 lines.

T1(b): mac-filtered 8-byte clut union fills **140/256**. **1842
conflicts**. Shared-palette model fails. 128 covers 20–33+ later
bands, not 0–N. Byte 6 ≠ colour count.

T2: 46/50 four-offset tables OK vs `u32@0`. 195–202:
`[280, 344, 376, 32768]`. `376 == 2×188`, `32768 == 2×16384`.
Fails: 161, 162, 167, 189.

Visual: compact gray records at +29 (`index, 03, gray, 81`) plus
raw pixels from packed **offset 258** → mottled gray 128×128
(`reference/shapes/195_a.png`). Matches Petrich.

T4: AOPID 1.4 from
`simplici7y.s3.amazonaws.com/.../AOPID_v1.4.zip`. `Shapes.shpA`
9.3 MB, 32 M2 collections. Coll 0 has 59 bitmaps (same count as
`.256` 128). Coll 12 names Blue/Orange Nightmare, Headless, …
Coll 17–21 are wall-type. Sprites are column-packed (0 raw
exports). `reference/aleph_shapes/`.

T5: Basilisk II is not on this machine; no controlled save.
Ground Floor save runes: (6,2), (26,2), (5,10), (27,10). John Doe
at (14,6) Item=114. Pathways Into Cheating DITL 129 fields:
Vitality, Maximum Vitality, Left-Handed, All Items, Add/Delete.
STR# 128 is the error list. MENU 135 is the item catalog (id
suffixes). Report: `reference/docs/round9_cheating.txt`.

---

## 2026-09-01 (round 10 — .256 discriminator)

Palette-union conflicts do not falsify anything. Dropped the
master-palette goal. Each `.256` uses its own table.

T1(b) 195 `@258..end`: in 3–16 = 25242/31370 = **0.8047**.
OOR/KB = 195.35. Gaps median 2 (102/200 are 2) → RLE controls.

T1(e) 198 `@258..end`: in 3–16 = 10440/18287 = **0.5709**.
OOR/KB = 429.10. Ratio 198/195 = **2.197**. More OOR/KB in the
most-compressed resource. Caveat: 198 has 2548×`0x11` + 1184×`0x12`
(likely extra pixel slots; kind=4 record mentions index 18).
Fair control signal is `0x80+`/KB: 195=85.2, 196=31.0, 198=119.2.

T2: per-section restart. `*_until` always hits target; leftover
is the tell. PackBits leftover 16238. highbit s3 short 1030.
Two 16384 PackBits runs leave ~16 KB — same over-expansion as
round 9. PackBits on the 376-byte header destroys the clut.

T3: `195_raw_a.png` / `195_raw_b.png`. B has 14986 real bytes,
padded 1398. No sudden OOR cliff → not “first raw, second
compressed”. 198 B_avail=1903.

T4: packed `[23:211]` identical on 195–202 (shared clut). First
varying byte is **257**. u16 128 and 16384 sit at 244/249 on all
eight. Last 376 packed bytes vary everywhere. Decoded 376 via
PackBits is garbage, not two 188-byte image headers.

T5: rsrc 192 PackBits 13/22 frames; AOPID L1 246–358, inconclusive.

T6: 161=2-entry `[864,1024]`; 162=3-entry `[608,736,768]`;
167/189 table likely starts at offset 11. b6 still a frame count.

Encoding identified as RLE-class, not closed. Tools:
`tools/round10_256.py`, `round10_followup.py`, `round10_disc_rle.py`.

---

## 2026-09-01 (Saved Games — one real file)

`data/saves/Saved Games` 267452, creator `påth`. Supersedes the
DiskDoubler blob. **Not two near-identical slots.** One Pascal name,
one (6,2)+facing, one time 5204, HP 60/60 at 1876. Autocorrelation
max 0.284 @ 18224. Second `00 3c 00 3c` at 24884 is not a second
player (no name, no XY, +23008 is zeros).

T2(c): no before/after pair. Cannot test Sector.Item 114.
File has 238× `i16be==114`. L0 8-aligned: none. Bit 114 of L0 = 0.
Inventory already has Walther + Mein Kampf (John Doe loot) — this
looks like the AFTER state only.

T3: ItemCheat time@1786 and inv@2560 and HP low-bytes **correct**.
X/Y/level offsets **wrong**. True X/Y = u16be 6,2 @2328/2330.
Level 0 @2316. Hex “×4 map unit” not used.

T4: 8-byte `(id,state,qty,cat)` matches dpin. ~21 slots from 2560.

T5: (6,2) is a save rune, level_number 0. 25×9112 table @39392 all
populated.

Reports: `reference/docs/round11_saves.txt` … `round11_saves4.txt`.

---

## 2026-09-01 (round 12 — level blocks + RLE follow-byte)

T1(e)(f): 8-byte-from-0, index=Item is **false**.
L0/L6/L13 f0_live = 74 / 79 / 115 vs expected 116 / 109 / 294.
rec[114] = `(51,0,8,FFFF)`. No field equals 114 in L0.
Bytes 0–255 identical on all 25 levels.

T1(g): 9112÷8=1139; 9112-256=8856÷8=1107. 12 does not divide
9112. 16-byte view is the `fffe` frame, not cleaner.

T2: 4287 bytes zero-across-25; 246 constant `ff fe`; 4579 vary.
No bitmap. “Coord pairs” are misread (type,0,id,1) records.
Middle of the block is 16-byte objects with `2007`/`ffff` (dpin-like).

T3: Bomb Code 321 bytes, exported == 1995 tree, 0 diffs. Mac Roman
text. Arming code **2870334**. `Don\xd5t` = Don’t.

T4(d): after 00/01/02 the next byte is a **pixel** (3–16):
1774/1793, 752/763, 336/338. Opcodes with a pixel operand.
T4(e): no scheme hits 33144 and consumes to EOF. Closest full-stream
shorts are still ~1900–2600. @257 vs @258 does not close the gap.

Tools: `round12_level_rle.py`, `round12_followup.py`.
User will capture a two-name save (talk, no loot).

---

## 2026-09-01 (round 13 — AAA/AAB pickup + RLE gap)

Source is one file `reference/saves/Saved Games AAA-AAB` (276564),
not `save_AAA` + `save_AAB`. Names at 0 and 128.

T2(a): L0 live **85 in both views**. The packed list did **not**
shrink to 84. It is byte-identical to the earlier mid-game L0 list
(85 type-35-heavy records). Pickup does not remove a record.
L1–L24 counts unchanged in role (only one world copy). A 26th
9112-byte region exists; it is not a second L0.

T2(b)(c): no removed record. No field equals a disappearing 0x33/8
pair that is unique to the pickup. Type-35 `f2` never contains
alcove Item **44**.

T2(d): no in-place L0 field change vs the old save either.

T4: ammo **appends** `00 33 00 00 00 07 ff ff` at inventory slot 9
(2560+2876). Knife catalog `FFFF`→`0003`. Qty 7 = Descriptions Pink.

T5: row-length prefixes fail (first u16 is 0x900B-class, not a
length). No increasing 128-entry table in the first 512. Column-major
reset is the same 128×128 decoder as per-row; 198 leftover 85 bytes
still look like RLE (`01 08 80 09…`). Skip-N-at-boundary does not
hit 33144.

T6: Bomb Code already identical; recorded as static content.

Reports: `reference/docs/round13_pickup_rle.txt`,
`round13_save_diff.txt`, `round13_refine.txt`, `round13_bitmap.txt`.
