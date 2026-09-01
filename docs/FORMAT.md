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
| Full v2.0 | `data/hfs/Pathways_1995/` | From `Pathways_1995.dsk`. `vers` 1 text includes `v2.0`. |
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

A MacRoman dump of `STR#` 2018 contains the published level-name list
(Ground Floor, Never Stop Firing, …). `STR#` 2021 dump contains three
strings (Ground Floor, Charon Doesn't Make Change, Come And Take Your
Medicine). This confirms the PROJECT.md examples; it is not a Map-file
directory.

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

No resource map. Sizes observed:

| Build | Path | Bytes |
|---|---|---|
| Demo | `data/extracted/PathwaysDemo/.../Maps` | 50502 |
| v2.0 | `data/hfs/Pathways_1995/Maps` | 420850 |

Demo file begins with bytes `17 50 61 74 68 77 61 79 73...`
(`0x17` then `Pathways into D...`). That is an observation, not a
declared header struct.

---

## Map file data fork

Not yet opened beyond the first-16-byte peek above. Do not invent a
directory layout.

---

## Negative results

- Demo application resource fork does not contain `STR#` 2018 or 2021.
- `pathways-i-d-11.sit` and the Japanese `.dc42` images are installer
  disks, not a ready-to-parse loose Maps file.
- `Pathways_-_2.0.sit` is patchers, not a standalone v2.0 tree. The
  playable v2.0 tree came from `Pathways_1995.dsk`.
