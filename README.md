# pid-re

File format documentation and parsing tools for **Pathways Into Darkness**
(Bungie Software, 1993, Macintosh).

The game's source code was never released. This repository is the result of
reverse-engineering its data files from the shipped binaries, building on
fan documentation written between 1994 and 2000.

**No game data is distributed here.** Get your own.

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

Partially decoded: the save format (player state and inventory yes, per-level
world state no).

Still unsolved: the `.256` sprite and texture compression, and the purpose of
the `dpin` resource. See `docs/FORMAT.md` for the full open-questions list.

---

## Contents

```
docs/
  FORMAT.md        the specification — byte offsets, enums, semantics,
                   disproven hypotheses, open questions
  JOURNAL.md       how it was solved, in order, including the dead ends
formats/
  pid_level.ksy    Kaitai Struct definition; generates parsers in Python,
                   C#, and anything else Kaitai targets
tools/
  export_level.py  emit levels as JSON
  level_viewer.py  render levels as annotated PNGs
  ...              dumpers, diffing scripts, analysis utilities
reference/
  levels/          rendered maps for all 25 levels
  export/          JSON exports + transition graph + corpse index
  sounds/          extracted audio
  docs/            raw analysis output
```

---

## Getting started

You'll need a copy of the game. It has been available online since Bungie
released it as freeware, the Macintosh Garden archive is a great source for multiple versions of the game.

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

Pathways Into Darkness is © Bungie Software. This repository contains no game
code or assets.