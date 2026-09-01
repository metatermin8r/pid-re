# Pathways Into Darkness — Reverse Engineering & Reimplementation

Project context for AI coding assistants. Read this fully before touching code.

---

## 1. What this project is

Reverse-engineer the data formats of **Pathways Into Darkness** (Bungie, 1993, Macintosh)
and build an open-source reimplementation of the engine, eventually in Unity.

The model is **Daggerfall Unity**: ship the engine only. Users supply their own copy of
the original game data. No game assets are ever committed to this repository.

The original source code was never released. Everything here is derived from binary
analysis of shipped files plus publicly available fan documentation.

### Current phase

**Phase 0 — data archaeology.** No Unity. No engine code. The only deliverables right now
are a documented file format and a parser that proves it. Do not scaffold Unity projects,
do not write rendering code, do not design a component architecture. Those are premature
and will be thrown away.

Phase 0 exits when a top-down 2D viewer renders a recognizable level from original data.

---

## 2. Ground truth

Facts established from research. Treat these as reliable starting assumptions; anything
not in this section is a hypothesis until verified against bytes.

### The game

- Bungie Software, released August 1993 for Macintosh. 68k, later a PowerPC conversion.
- First-person, texture-mapped, 256 colors only. Predecessor to Marathon.
- Adventure/RPG hybrid: inventory, NPC interaction (talking to corpses), crystals with
  special powers, resting to heal, end-of-game scoring.
- Copy protection: manual lookup at startup. Clues are scattered through the printed
  manual. Once activated and saved, it stops prompting.

### Where the data lives

- Classic Mac files have two forks. Both matter here.
- **Application resource fork** — standard typed chunks. Confirmed to contain `STR#`
  resources holding level name lists (IDs 2018 and 2021 are known examples).
- **Map file data fork** — the actual level geometry. This is the opaque blob and the
  real target. Level name strings appear here too, and *do not always match* the names
  in the application's resource fork.

### Available versions

| Version | Notes |
|---|---|
| v1.1 (68k) | Earliest widely available build |
| v2.0 (68k) | Latest original build |
| PowerPC conversion | Alain Roy credited with this work |
| Demos v1.0, v2.0, "Version A1" | Separate Map files, different level sets |
| Japanese localization | Same structure, different text |
| macOS Cocoa port | Man Up Time, LLC; free; Bungie-sanctioned |

### The Cocoa port — important

Described publicly as an all-Cocoa port with PPC code stripped out and **the old resource
fork preserved**. This means it is a genuine reimplementation that reads the original data
files. Its Objective-C binary is therefore a working reader for the format we want, and
its class and method names are effectively free documentation.

Get the **direct download**, not the Mac App Store build — App Store binaries are
FairPlay-encrypted and will not disassemble.

### Aleph One — read carefully, trust cautiously

- Aleph One is the open-source Marathon engine. Marathon is PID's loose sequel.
- **The formats are NOT compatible.** Despite persistent rumors, pointing Aleph One at
  PID data files crashes it. Do not assume Marathon's map structures apply to PID.
- W'rkncacnter's "Aleph One: Pathways Into Darkness" is a *recreation built as a Marathon
  scenario in Lua*, not a data-driven port. Its readme documents deliberate divergences.
- **Correct use:** behavioral and design reference only. Combat feel, item semantics,
  level flow.
- **Incorrect use:** as a source of struct layouts, offsets, or field ordering.

### Prior art worth mining

- `pid.bungie.org` — 25+ year fan archive. Level names, monster data, walkthroughs, and
  mailing-list threads containing 1990s-era hex-level analysis.
- Existing **PID save game reader** tool — reads current location, single-use trigger
  flags, and other state, for both full game and demo saves. Someone has already
  reversed a large part of the runtime state model.
- **Trainers** (`Pathways into Cheating`, `p3trainer`) — whoever wrote these located the
  player struct and inventory encoding. Reversing a trainer inherits that work.
- **Fan guide** (`PathwaysGuide`) — includes full game maps and "editing tips," implying
  contemporary map-format investigation.

---

## 3. Hard constraints

1. **No game data in git.** `data/` is gitignored. Commit `checksums.txt` instead.
2. **No GPL code in this project.** Aleph One is GPL. Reading it to understand the
   problem domain is fine. Copying or closely transliterating it is not. This project
   targets a permissive license so the engine can be distributed the way Daggerfall
   Unity is. This is far easier to maintain than to retrofit.
3. **Never invent an offset.** See section 6.

---

## 4. Repository layout

```
pid-re/
  data/            # extracted originals — GITIGNORED
  reference/       # rsrcfork dumps, hex dumps, disassembly notes
  formats/         # Kaitai Struct .ksy specs — the canonical format definition
  tools/           # Python dumpers, diffing scripts, the 2D viewer
  docs/
    FORMAT.md      # the running format specification
    JOURNAL.md     # dated log of attempts, including failures
  checksums.txt
  .gitignore
```

---

## 5. Toolchain

Host is **Windows**. Substitutions from the usual macOS advice are already applied.

| Job | Tool | Notes |
|---|---|---|
| Unpack `.sit` / `.hqx` / `.bin` | `unar` (Windows CLI build) | Not 7-Zip — it mangles resource forks |
| Disk images | HFSExplorer | Java |
| Resource forks | `rsrcfork` (`pip install rsrcfork`) | Reads AppleDouble + MacBinary sidecars |
| Hex editing | ImHex or HxD | ImHex has a pattern language and entropy view |
| Format specs | Kaitai Struct + `ksv` | Generates Python *and* C# — feeds Unity later |
| Binary diff | `vbindiff`, or ImHex | Essential for cross-version comparison |
| Disassembly | Ghidra | Has 68k, PPC, and Mach-O/Obj-C support |
| Reference behavior | Basilisk II (68k), Infinite Mac (browser) | 256-color required; Mini vMac won't do |
| Scripting | Python 3, Pillow, numpy | |

### Resource fork handling on Windows

NTFS has no concept of a resource fork, so `unar` writes them as AppleDouble sidecars
(`._Filename`) or `.rsrc` files. **These are not junk. Do not delete them.** `rsrcfork`
reads them directly.

---

## 6. Working method

### The core rule

**The human inspects bytes. The assistant builds tooling around confirmed hypotheses.**

LLMs are unreliable at reading raw hex and highly prone to confabulating plausible
structure. They are excellent at turning a stated hypothesis into a parser, an annotated
dump, a diff script, or a test.

Therefore:

- **Never assert an offset, field size, or type that has not been observed.** If you are
  reasoning by analogy — to Marathon, to other 1993 engines, to common practice — say so
  explicitly and label it a hypothesis.
- Prefer writing a script that *tests* a hypothesis over asserting a conclusion.
- When a guess is disproven, record it in `FORMAT.md`. Negative results are load-bearing.

### Techniques that work here

- **String anchoring.** Known level names are already published. Find them in the Map
  file; the table containing them is likely a level directory, and directories contain
  offsets.
- **Differential analysis.** Multiple versions (v1.1, v2.0, three demos, Japanese
  localization) contain the same structures with different content. Fields that differ
  across the Japanese build are text; fields identical across it are structure.
- **Sanity checks over guesses.** A candidate polygon count should be plausible. Offsets
  should land inside the file. Counts should multiply out to region sizes. Write these
  as assertions in the parser, not as prose.

### Conventions

- Big-endian throughout. This is 68k Macintosh data.
- Classic Mac strings are usually Pascal-style: leading length byte, not NUL-terminated.
- Formats are defined in Kaitai `.ksy` files, not hand-rolled struct parsers.
- `FORMAT.md` is updated in the same commit as any parser change.

---

## 7. Immediate next steps

1. Download everything from the Macintosh Garden PID page (~35 MB total), including the
   demos, the Japanese build, the trainers, the fan guide, and the manual PDF.
2. `unar` each archive. Verify the AppleDouble sidecars survived.
3. `rsrcfork list` every application binary and Map file. Save output to `reference/`.
4. Record the full resource type/ID inventory in `FORMAT.md`.
5. Open the demo's Map file data fork in ImHex. Search for known level name strings.
6. Build the level directory hypothesis from whatever table those strings sit in.

Do not proceed past step 6 until steps 1–5 have produced committed artifacts.
