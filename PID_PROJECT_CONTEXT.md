# Pathways Into Darkness — project context (current)

Companion to `PROJECT.md`. The running spec is `docs/FORMAT.md`.
This file is the short current-state list: save format, disproven
claims, and open items ranked by engine impact.

---

## 9. Save format

v2.0 `Saved Games` is one file. Size = `267452 + (n_names - 1) * 9112`.
Names are 128-byte Pascal strings at `k*128`.

**Player records** start at offset 0, **stride 2,876**. Relative
offsets: `+0x074A` clock (u32be, 60 Hz); `+0x0754`/`+0x0756`
current/max HP (u16be); `+0x090C` level; `+0x0918`/`+0x091A` X/Y;
`+0x091C` facing; `+0x0A00` inventory as 8-byte `(id, state, qty,
catalog)` records, `FFFF`-terminated.

Confirmed by experiment: **HP and max HP take effect**. **Level, X,
Y, and facing do not.** Object positions are 10-bit fixed point, so
the live player pose is almost certainly fixed point too; those
integer fields are display mirrors.

**The 25 × 9,112-byte blocks at file offset 39,392 are per-level
live world state**, not static templates.

- CODE 4 @1466 (JT 152): `NewPtr $2398` → `-$1A86(A5)`.
- CODE 2 @10066: `SetFPos` `index * $2398`, `FSRead` `$A002`.
- CODE 2 @10174: matching `FSWrite` `$A003`.

Internal layout (JT 164 + every `LEA` off `-$1A86(A5)`):

| Offset | Size | Contents |
|---|---|---|
| 0x0000 | u16 | count, max 60 |
| 0x0002 | 480 | 60 × 8-byte records |
| 0x01E2 | u16 | count, max 30 |
| 0x01E4 | 120 | 30 × 4-byte records |
| 0x025C | 320 | 40 × 8-byte records |
| 0x039C | 60 | 15 × 4-byte records |
| 0x03D8 | 8000 | **500 × 16-byte object table** |
| 0x2318 | 128 | 128 bytes of 1 |
| total | 9112 | |

Object entry: `+0x00` X u32be, `+0x04` Y u32be (10-bit fixed,
`ASR.L #10` / `LSL.L #10 + $200`), `+0x08` packed descriptor,
`+0x0A` flags (`$8000`/`$4000`/`$2000`; bits 4–7 as
`(v >> 4) & 15`), `+0x0C` unread, `+0x0E` next-index
(`$FFFE` free, `$FFFF` end). JT 157 insert, 159 update, 158 free,
164 wipe.

`Sector.item` is that table’s index (CODE 5 @17190). Item 0 is
valid. Positions are not in Maps. A fresh game’s layout comes from
`dpin` 128.

`dpin` 128 **initialises the save file**. CODE 2 @9262:
`GetResource('dpin', 128)`, `HLock`, FSWrite 28,760 + 2,876 at
file position 8 + 227,800 from offset 2,876, `ReleaseResource`.
Handle never lands in an A5 global.

Shape descriptor (wall pairs and object `+0x08`): bits 0–6 s1
index, 7–12 selector into the 128-slot cache at `-$17B6(A5)`
(+64 unless tag == 6), 13–15 tag. Tag 0 is never drawn. Pillars
go through CODE 5 @1454, not @1618.

The binary contains 68020 instructions. Jump-table segment field
is +4 versus segment headers.

**Corpus vs CODE:** every local v2.0 save, parsed as this layout,
has 500 “live” object entries (0 × `$FFFE` at +0x0E), a trailer
that is not 128 bytes of 1, and a 100% `Sector.item` position
miss. The CODE is established. The captured files still look like
the `dpin` image. `tools/save_editor.py world|objects --level N`.

---

## 10. Disproven

| Claim | Why it fails |
|---|---|
| The 25 blocks at 39,392 are static level templates | They are live per-level world state, `FSRead`/`FSWrite`n by index. |
| `dpin` 128’s purpose is unknown; Semmler guessed item templates | It is the save-file initialiser image. |
| `Sector.Item` is a dpin loot-group index, or a save-state flag key | Both were close. It indexes the object table inside the 9,112-byte block. |
| The 2,876-byte player stride is inferred and suspect | Confirmed. 2,876 is the player stride; 9,112 is per-save file growth. Unrelated. |
| Pillars are solid map geometry | They are objects with continuous positions, drawn through @1454. |
| Wall type and texture are two independent bytes | They are one 16-bit descriptor. |

Full table: `docs/FORMAT.md` **Disproven**. Do not import Marathon
or Aleph One. Do not decode as 68000.

---

## 11. Open items (engine impact)

Closed this arc: `.256` decoding; `dpin` purpose.

1. **`$217F` anomaly** — 4,101 pairs on levels 7–15, s1 index 127
   against resource 194’s 14 records. No CODE compare. Not solved.
2. **Player’s live position encoding** — integer level/X/Y/facing
   do not take effect.
3. **The 60- and 8-byte (and 4-byte) record tables** inside the
   9,112-byte block.
4. **L13 maze generator.**
5. Player-island flag bits; floor/ceiling selection; unverified s1
   words; captured-save vs in-memory world block.
