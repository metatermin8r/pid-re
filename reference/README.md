# reference/

Local output derived from **your** copy of Pathways Into Darkness.
Nothing in this directory is committed except this README, `INDEX.md`,
and written analysis (inventories, offset tables, round notes).

Regenerate the ignored subdirectories:

| Directory | Tool | Command |
|---|---|---|
| `docs/256/` | `tools/extract_256.py`, `tools/decode_256.py` | `python tools/extract_256.py` |
| `sounds/` | `tools/extract_sounds.py` | `python tools/extract_sounds.py` |
| `export/` | `tools/export_level.py` | `python tools/export_level.py` |
| `levels/` | `tools/level_viewer.py` | `python tools/level_viewer.py` |
| `docs/code/` | `tools/scan_256_loader.py` | `python tools/scan_256_loader.py` |
| `docs/scri_dec/` | `tools/decrypt_scri.py` | `python tools/decrypt_scri.py` |
| `docs/sectors/` | `tools/render_sectors.py` | `python tools/render_sectors.py` |
| `palettes/` | `tools/round8_shapes.py` | `python tools/round8_shapes.py` |
| `shapes/` | `tools/round9_shapes.py` | `python tools/round9_shapes.py` |
| `aleph_shapes/` | `tools/round9_aleph_shapes.py` | `python tools/round9_aleph_shapes.py` (needs AOPID, not PID) |
| `saves/` | — | **FLAG: not regenerable.** User-captured saves / Bomb Code. |
| `scri/` | — | **FLAG: no writer in `tools/`.** Raw `scri` blobs; read them from the app rsrc. |
| `dpin_128.bin` | — | **FLAG: no writer in `tools/`.** Extract `dpin` 128 from the app rsrc. |
| `dpin_blockmap_*.png` | `tools/blockmap.py` | `python tools/blockmap.py` (needs `dpin_128.bin`) |
| `stride_scores.png` | `tools/stride_finder.py` | `python tools/stride_finder.py` (needs `dpin_128.bin`) |
| `palette.png` | `tools/shapes_pass1.py` | `python tools/shapes_pass1.py` |
