# Pathways Into Darkness — project context (current)

Companion to `PROJECT.md`. The running spec is `docs/FORMAT.md`.
This file is the short current-state list: constraints, layout,
save format, disproven claims, open items, and vertical constants.

---

## 3. Hard constraints

1. **No game data in git.** `data/` is gitignored. Commit `checksums.txt` instead.
2. **No GPL code in this project.** Aleph One is GPL. Reading it to understand the
   problem domain is fine. Copying or closely transliterating it is not.
3. **Never invent an offset.** Cite the CODE id and file offset, or mark the
   claim open. Do not import Marathon / Aleph One / Wolfenstein 3D / Doom
   layouts. Decode the application as **68020**, not 68000.
4. **Do not name a routine’s purpose from resemblance.** The function
   inventory at `reference/docs/code/inventory/` reports instructions,
   offsets, operands, and call targets only.

---

## 4. Repository layout

```
pid-re/
  data/            # extracted originals — GITIGNORED
  reference/       # rsrcfork dumps, hex dumps, CODE bins, inventory
  reference/docs/code/inventory/   # 771-function 68020 inventory
  formats/         # Kaitai Struct .ksy specs
  tools/           # Python dumpers, save editor, 2D viewer
  docs/
    FORMAT.md      # the running format specification
    JOURNAL.md     # dated log of attempts, including failures
  PID_PROJECT_CONTEXT.md
  checksums.txt
  .gitignore
```

---

## 9. Save format

v2.0 `Saved Games` is one file. Size = `267452 + (n_names - 1) * 9112`.
Names are 128-byte Pascal strings at `k*128`. Creator `påth`.

**2,876 is the player-record stride. 9,112 is the per-save file
growth. They are unrelated.** Player record `k` is at `k*2876`.
File bytes `[0, 1780)` are a separate name and level table read
into A5 `-$1ADC` (CODE 2 @9638 / @9704). They overlap record 0 on
disk but are not part of it.

The live island begins at `k*2876 + 0x06F4` with
`{u16 12, u16 2876, u16 slot k, u32 counter, u16 flag}`, then
zeros to `+0x0748`.

| Rel | Type | Field |
|---|---|---|
| +0x0748 | u16be | dungeon. Load path → A5 `-$1AD8` via CODE 2 @8546. Written with live X/Y, this word warps (in-game: a save for level 7 loaded a crystal-walled floor with ghouls). 0 on all nine captured records. |
| +0x074A | u32be | **live player X**, 10-bit fixed point. **Not a clock.** In-game edit teleports, including into a wall. |
| +0x074E | u32be | **live player Y**, 10-bit fixed point |
| +0x0752 | u16be | facing, 512-unit circle. CODE 4 @1028 returns 0..511 vs table at `-$1A96`; CODE 4 @4 (JT 331) wraps by `±$200`. 0 = west, 128 = north, 256 = east, 384 = south. |
| +0x0754 / +0x0756 | u16be | current / max HP. Confirmed in game. |
| +0x090C | u16be | level. **INERT** (confirmed in game). |
| +0x0918 / +0x091A | u16be | integer X / Y. **INERT** (confirmed in game). |
| +0x091C | u16be | 0 / 1 / 2 / 12 on the nine records. **UNTESTED** (was filed as confirmed inert without a test). |
| +0x0A00 | 8 × u16be | inventory `(id, state, qty, catalog)`, `FFFF`-terminated |

CODE 2 @8546 builds X and Y at @8762–8788 with `LSL.L #10` then
`ADD.L #$200` and copies eight bytes to player+0x56 at @8830.
No stored Z.

**The 25 × 9,112-byte blocks start at file offset 30,540**,
indices 0–24. `file_pos = index * 9112 + 30540`. 39,392 was
8,852 bytes late; the live-state claim was right, the offset
was not.

- CODE 4 @1466 (JT 152): `NewPtr $2398` → `-$1A86(A5)`.
- CODE 2 @10066: `SetFPos` `index*9112 + 30540`, `FSRead`.
- CODE 2 @10174: matching `FSWrite`.
- File `0x06C2` is a sink (CODE 2 @8436 writes it FROM `-$1AD8`).

Internal layout (sums to 9,112):

| Offset | Size | Contents |
|---|---|---|
| 0x0000 | u16 | count0 |
| 0x0002 | 480 | 60 × 8 |
| 0x01E2 | u16 | count1 |
| 0x01E4 | 120 | 30 × 4 |
| 0x025C | 320 | 40 × 8 |
| 0x039C | 60 | 15 × 4 |
| 0x03D8 | 8000 | **500 × 16 object table** |
| 0x2318 | 128 | zeros (`CLR.B`, JT 164) |

Object entry: `+0x00` X, `+0x04` Y (u32be, 10-bit fixed; sector =
`raw >> 10`; writer adds `$200`), `+0x08` packed descriptor,
`+0x0A` flags (`$8000` / `$4000` / `$2000` tested), `+0x0C`
unused (zero on 27,904 live objects), `+0x0E` link (`$FFFE`
free, `$FFFF` end). JT 157 insert, 159 update, 158 free, 164
wipe.

`Sector.item` is the head of that chain (CODE 5 @17190:
`[-$1A86(A5)] + $03D8 + item*16`). All 5,866 map refs on the
25 home blocks resolve with `raw >> 10`, zero failures.

`dpin` 128 **initialises the save file**. CODE 2 @9262:
`GetResource('dpin', 128)`, `HLock`, FSWrite 28,760 + 2,876 at
file position 8 + 227,800 from offset 2,876, `ReleaseResource`.
Handle never lands in an A5 global. 227,800 = 25 × 9,112.
Layout: 2,876-byte header plus 25 world-state blocks. The four
captured saves’ homes 0–24 are byte-identical to
`dpin[2876 + N*9112]`.

The binary contains 68020 instructions (`EXTB.L`, `MULU.L` /
`MULS.L` / `DIVS.L`, scaled index extensions). Jump-table
segment field is +4 versus every segment header; trust the
table. Inventory: 771 functions, 355 jump-table entries, 46,024
instructions, 13 unknowns, 2,249 call-graph edges, 232 A5
globals. CODE 11 and CODE 15 are C runtime and contain no game
logic.

---

## 10. Disproven

| Claim | Why it fails |
|---|---|
| The 25 blocks of live world state begin at 39,392 | Offset only. They are live; homes start at 30,540. |
| `Sector.Item` is a dpin loot-group index, or a save-state flag key | It is the object-table chain head at world-state `+$03D8` (CODE 5 @17190). |
| The 2,876-byte player stride is inferred and suspect | Confirmed. 2,876 is the player stride; 9,112 is per-save file growth. Unrelated. |
| `+0x090C` is the level the game loads | INERT (in-game). Load-path dungeon is `+0x0748`. |
| `+0x0918` / `+0x091A` are the position the game loads | INERT (in-game). Live X/Y are `+0x074A` / `+0x074E`. |
| File `0x06C2` is the block-index authority | CODE 2 @8436 writes it FROM `-$1AD8`. Sink. |
| `+0x074A` is a game clock | Live player X. In-game edit teleports. |
| `+0x091C` is confirmed inert | Never tested. Mark UNTESTED. |
| `height10` gives the world’s vertical scale | CODE 3 @8762 is HUD text (`DIVS.W #10`, `_DrawString`). |
| The eye sits at half wall height | 614/1023 ≈ 60% (CODE 3 @13656 / @13664). |
| `dpin` is 2,876 records of 80 bytes / purpose unknown | 2,876-byte header plus 25 × 9,112 (CODE 2 @9262). |

Full table: `docs/FORMAT.md` **Disproven**. Do not import Marathon
or Aleph One. Do not decode as 68000.

---

## 11. Open items (engine impact)

Closed this arc: `.256` pixel decoding; `dpin` 128; `Sector.item`;
live X/Y/facing; world-block role and offset 30,540; vertical FOV
and eye height.

1. **`$217F` anomaly** — resource 194, s1 index 127, 4,101 wall
   faces on levels 7–15, never on a walkable/void boundary. Not
   solved.
2. **Object vertical extents at CODE 5 @17190.**
3. **The four smaller tables** inside the 9,112-byte block
   (`+0x0002`, `+0x01E4`, `+0x025C`, `+0x039C`).
4. **L13 maze generator.**

The behavioural layer — combat, monster AI, item effects, the
crystals, door triggers — is entirely undecoded. The inventory
makes it searchable: 225 functions have zero traps and exceed
100 bytes; 89 A5 globals are written in exactly one place.

---

## 14. Vertical geometry

Measured from the 68020 stream, not from screenshots. A
screenshot that put wall height at 1,080 raw units is
superseded. The old “~2.7 m vertically per height10, so ~3 m
per sector keeps proportions sane” estimate is void:
`height10` is HUD text, not scale.

- No stored player Z. Two longs only (CODE 2 @8546).
- Floor / ceiling on the view record at A5 `-$1542`: **−614**
  (CODE 3 @13656) and **+409** (CODE 3 @13664). Wall height
  **1,023**. Eye at 614/1023 ≈ 60%, not half.
- vFOV fixed `2*atan(0.6)` = **61.9275°** (CODE 5 @9856,
  `view+$1C = trunc(5*H/6)`). hFOV `2*atan(0.8)` = **77.3196°**
  (CODE 5 @9806). Tangent ratio 4/3.
- `height10` at level `+0x084`: CODE 3 @8762, `DIVS.W #10`,
  `_DrawString`.
