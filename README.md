# pid-re

File format documentation and parsing tools for **Pathways Into Darkness**
(Bungie Software, 1993, Macintosh). The game’s source was never released.
This repository reverse-engineers the shipped 68020 binaries and data files,
building on fan documentation written between 1994 and 2000.

Pathways Into Darkness is © Bungie Software. **This repository contains no
game code or assets.** Get your own.

---

## Credits

Leads from the Pathways community, independently checked against the bytes.
Where this documentation and theirs disagree, `docs/FORMAT.md` says so.

- **Loren Petrich** — original map format research (2000)
- **Ben Semmler** — *Torch* and its sector-behaviour notes
- **Chuck Gray** — corpse-script encryption (1994)
- **Alan Earhart** — hand-drawn level maps
- **Alain Roy** — save-game tools and the PowerPC conversion

---

## Status

Solved to implementation depth. Numbers and sites live in `docs/FORMAT.md`.

- **Maps.** 25 records of `$41C2` (16834) bytes: 450-byte header + 32×32
  16-byte sectors. Six wall words: `+0` north (Y=0), `+2` west (X=0),
  `+4` NE, `+6` NW, `+8` SE, `+$A` (10) SW. South and east are the
  neighbouring cell’s slot 0 and 1. Type 32 blocks; type 33 is draw-only
  (levels 7–15). Transition graph: 118 edges. Sector types match
  Petrich’s 2000 sheet at 100%.
- **Descriptors and tag spans.** `tag = w >> 13`. Tag 0 is never drawn.
  Tag 1: 0..`$400` (1024); tag 2: `$100` (256)..1024; tag 3: 0..`$300`
  (768); tag 4: 256..768. `$217F` (8575) is tag 1 / selector 66 /
  s1index 127 on 4101 faces (L7–15); out of range, harmless — skip.
- **Corner chamfers.** Tag 5 is the 45° chamfer (dirs 4–7, CODE 5
  @13550), not a door. Door thickness is @16202.
- **`.256` RLE and overlays.** CODE 8 @2206: `$00..$7F` repeat `n=b+3`
  (emit 3..130); `$80..$FF` literal `n=b-$7F` (emit **1..128**). Resource
  192 s1 14–17 blit a 49×48 patch at dest `$1147` (4423) via @2030. The
  11,372-byte packed tail is UNKNOWN.
- **Renderer.** HFOV `2*atan(0.8)` = 77.3196°, VFOV `2*atan(0.6)` =
  61.9275°, both viewports 272×204 and 384×288 exactly 4:3. Band =
  `((15*(depth+|lateral|/2))/view+$14)>>10` clamp 15; `view+$14` is 3 /
  5 / 7. Floor/ceiling is the A5 `-$17FA` (6138) scanline table (fade
  `$6A..$78` (106..120); `$79` (121) never emitted). Near clip 51; no
  far plane; unbounded BFS. `height10` is HUD metres of fall, not
  world scale.
- **Doors.** World t3 at `+$39C` (924): command + position 0..`$400`
  (1024). Rate at A5 `-$8E0` (2272) `+$A` (10) — `$0C` (12) / `$11`
  (17) / `$19` (25). JT 161: position `> $200` (512) blocks (513+).
  Three-quad slab @16202.
- **Triggers.** Door open/close from the trigger dispatch (proximity
  `type_addl` 128/129/131/132/141, explicit 12/13/23, Alien Pipes 130,
  L1 chain). PID has no walk-up auto-open.
- **Time, health, status.** 1 tick = 1/60 s. HP at save `+0x0754`.
  Worn flags `+$132`..`+$137` (IR, watch, Red Cloak, flashlight, rings).
  Rest quantum `$6270` (25200); Red Cloak selects `$3138` (12600).
- **Items and Cedar Box.** Catalog 71×16 at A5 `-$14D6` (5334).
  Inventory tree at save `+0x0A30` (word 3 = next-sibling). Cedar Box
  (id 8) is JT 227 on player `+$144` (324) = 3600 ticks, not rest-gated.
- **Saves.** `dpin` 128 initialises a new file: 2,876-byte header + 25 ×
  9,112-byte world blocks starting at byte 30,540. Live X/Y are 10-bit
  fixed point; facing is a 512-unit circle (0 = west).
- **Creatures.** Names are STR# 2001; world t0 `type` indexes those
  names. Catalog rows exist; AI is open. Corpse dialogue: 28 `scri`
  scripts, XOR, `scri_id = 128 + TypeAddl`. 86 `'snd '` resources
  extract as 8-bit mono; the sound *engine* is still open.
- **L13.** Authored (499 void, 521 normal, 4 change-level, 525
  walkable). JT 164 rewrites the six wall words only — no generator.
- **Billboards.** `bottom = view+$0C` (12) (−614) + s1 lift (`+$C`);
  `top = bottom + s1 height` (`+$A`); width at `+$8`. No vertical clip.
  Yaw-only. Of 654 shapes: 337 lift 0, 177 negative, 140 positive
  (−240..+1050).
- **68020 inventory.** 771 functions, 355 jump-table entries, 232 A5
  globals. Decode as 68020; a 68000 decoder is silently wrong.

Levels are big-endian 68k data. Strings are Pascal (leading length
byte). Text is Mac Roman. Cell is `$400` (1024) world units.

---

## Open questions

`docs/PID_HANDOFF.md`. Short list: creature AI and door behaviour; the
unreproduced door-500 clip; `type_addl` 134/135; trigger cases 18–21;
JT 246; STR# 2001 blanks 8/9/13; A5 `-$17FA` (6138) fifth bank; the
`+$1B8` (440) poke; the 11,372 trailing packed bytes; conversations,
the Search dialog, potions, sound, level 24, and the endgame.

---

## Contents

```
docs/FORMAT.md           spec — offsets, enums, disproven, open questions
docs/PID_HANDOFF.md      current working state
docs/UNITY_PORT.md       DERIVED vs ACCOMMODATION for the Unity port
docs/JOURNAL.md          how it was solved, including dead ends
formats/pid_level.ksy    Kaitai map-record parser (not the full spec)
tools/export_level.py    levels → JSON
tools/level_viewer.py    levels → annotated PNGs
tools/decode_256.py      .256 decompressor (CODE 8 @2206)
tools/extract_256.py     tiles / contact sheets
tools/export_256_indices.py
                         R8 index PNGs + shade LUTs under out/
tools/save_editor.py     inspect / warp / give / equip Saved Games
tools/save_editor_gui.py inventory-tree GUI
tools/build_code_inventory.py
                         68020 function inventory (Capstone M68K_020)
tools/decrypt_scri.py    corpse-dialogue XOR
tools/extract_sounds.py  snd → WAV
reference/docs/code/inventory/
                         771-function inventory (local regenerate)
```

---

## Getting started

You need a copy of the game. Bungie released it as freeware; Macintosh
Garden is a common source.

```bash
pip install rsrcfork

# Classic Mac files have two forks. On Windows and Linux, extract with
# `unar` rather than 7-Zip — resource forks become AppleDouble (._name)
# sidecars. rsrcfork reads those. Do not delete them.
unar Pathways.sit

python tools/export_level.py 0        # Ground Floor as JSON
python tools/export_level.py          # all 25 levels
python tools/level_viewer.py 0        # rendered PNG
```

To read maps in another language, compile `formats/pid_level.ksy`.
Everything else — renderer, doors, items, saves — is in `docs/FORMAT.md`.
