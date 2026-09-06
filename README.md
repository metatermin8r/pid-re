# pid-re

File format documentation and parsing tools for **Pathways Into Darkness**
(Bungie Software, 1993, Macintosh).

The game's source code was never released. This repository is the result of
reverse-engineering its data files from the shipped binaries, building on
fan documentation written between 1994 and 2000.

Pathways Into Darkness is © Bungie Software. **This repository contains no game code or assets.** Get your own.

---

## Credits

This work stands on documentation produced by the Pathways community long
before this repository existed:

- **Loren Petrich** — the original map format research (2000), without which
  this project would have taken months longer
- **Ben Semmler** — *Torch*, a PID map editor, and the sector-behaviour
  documentation that came with it
- **Chuck Gray** — identified and published the corpse-script encryption
  in 1994
- **Alan Earhart** — hand-drawn level maps
- **Alain Roy** — save-game editing tools and the PowerPC conversion

Their conclusions were used as leads and independently verified against the
bytes. Where this documentation and theirs disagree, `docs/FORMAT.md` says so
and shows the evidence. All code here is written from the observed data.

---

## What's solved

The **map format is fully decoded.** All 25 levels parse cleanly, and the
renders produced from them match a sector map independently created in 2000
from the same data — at 100% agreement on every level.

Also decoded:

- **Wall and movement semantics**, including which wall values are colliders
  and which are render-only. Every playable level resolves to a single
  connected region.
- **The level transition graph** — 118 edges, with the arrival-coordinate
  semantics that make it work.
- **Corpse dialogue.** The game's 28 "conversations with the dead" scripts,
  their encryption, and the mapping from each corpse in the world to its
  script.
- **Sound resources.** All 86, extracted and converted.
- **`.256` art.** The packed stream is a two-opcode run/literal loop in
  CODE 8, not PackBits. All 50 shape resources decompress to the declared
  size. Tiles extract with class-dependent geometry and per-resource
  palettes.
- **`dpin` 128.** It is the save-file initialiser: a 2,876-byte header plus
  the 25 pristine world-state blocks written into a new `Saved Games`.
- **The save format.** Live player X/Y (10-bit fixed point), facing
  (512-unit circle, 0 = west), and dungeon; an inventory *tree* at file
  `+0x0A30` (word 3 is next-sibling, not an instance id); the 71×16 item
  catalog (weight, points, container fill/limit — not magazine capacity);
  weapon proficiencies; and 25 × 9,112-byte world-state blocks starting at
  byte 30,540, with `Sector.item` as the object-table chain head.
- **Vertical geometry.** No stored player Z. Wall height is 1,023 raw
  units; the eye sits at about 60% of that span. Vertical FOV is
  `2*atan(0.6)` ≈ 61.93°, horizontal `2*atan(0.8)` ≈ 77.32°. The HUD
  `height10` field is metres of fall, not world scale.
- **The 68020 application.** A Capstone inventory of 771 functions, 355
  jump-table entries, and 232 A5 globals. The binary is 68020, not 68000.

Partially decoded: the four smaller tables inside each world-state block
(monsters, object→item links, door runtime), and a handful of `.256`
header words.

Still unsolved: the `$217F` wall-descriptor anomaly on levels 7–15; the
Labyrinth (L13) maze generator; object sprite vertical extents; and the
behavioural layer — combat, monster AI, most item effects. See
`docs/FORMAT.md` for the full open-questions list.

---

## Contents

```
docs/
  FORMAT.md              the specification — byte offsets, enums,
                         semantics, disproven hypotheses, open questions
  JOURNAL.md             how it was solved, in order, including the
                         dead ends
PID_PROJECT_CONTEXT.md   short current-state list (constraints, save
                         table, disproven claims, vertical constants)
formats/
  pid_level.ksy          Kaitai Struct definition; generates parsers in
                         Python, C#, and anything else Kaitai targets
tools/
  export_level.py        emit levels as JSON
  level_viewer.py        render levels as annotated PNGs
  decode_256.py          .256 decompressor (CODE 8 @2206)
  extract_256.py         tiles, contact sheets, per-resource manifest
  save_editor.py         inspect / warp / give / equip Saved Games
  save_editor_gui.py     inventory-tree GUI over the same editor
  build_code_inventory.py
                         68020 function inventory (Capstone M68K_020)
  decrypt_scri.py        corpse-dialogue XOR
  extract_sounds.py      snd resources → WAV
  ...                    dumpers, diffing scripts, analysis utilities
reference/
  README.md              which tool regenerates each local output
                         directory
  INDEX.md               analysis index
  docs/                  written analysis (round notes, inventories)
  docs/code/inventory/   771-function 68020 inventory (local regenerate)
                       extracted art / audio / JSON / renders stay local
```

---

## Getting started

You'll need a copy of the game. It has been available online since Bungie
released it as freeware, the Macintosh Garden archive is a great source for that.

```bash
pip install rsrcfork

# Classic Mac files have two forks. On Windows and Linux, extract with `unar`
# rather than 7-Zip — resource forks are written as AppleDouble (._name)
# sidecars, and rsrcfork reads those directly. Do not delete them.
unar Pathways.sit

python tools/export_level.py 0        # Ground Floor as JSON
python tools/export_level.py          # all 25 levels
python tools/level_viewer.py 0        # rendered PNG
```

The Kaitai spec is the canonical format definition. If you want to read the
maps in another language, compile `formats/pid_level.ksy` rather than porting
the Python by hand.

---

## Format summary

Levels are fixed-size 16,834-byte records with no file header — 25 of them,
concatenated. Each holds a 450-byte header (name, height, textures, doors,
level changes, monsters) followed by a 32×32 grid of 16-byte sectors.

Everything is big-endian; this is 68k Macintosh data. Strings are Pascal-style,
with a leading length byte and no terminator. Text is Mac Roman.

Sectors carry a type (void, normal, door, level change, trigger, secret door,
corpse, pillar, save rune), an item id, and six wall slots — two edges and four
corners. Levels use one of two wall-construction styles, which turns out to
matter a great deal for collision.

Full detail, including the parts that are wrong in the older fan
documentation, is in `docs/FORMAT.md`.