# Full dump

Mac Roman throughout. `STR#` / `STR ` / `MENU` / `vers` use published
Resource Manager layouts, not a raw-blob decode.

| File | What |
|---|---|
| `CATALOG.md` | Every resource type code across 85 files |
| `MAPS_STRINGS.md` | Maps data-fork name anchors (`i * 0x41C2`) |
| `strings/` | Decoded / harvested text per resource file |
| `harvest/` | Maps data forks only |

Primary reads:

- `strings/hfs__Pathways_1995__Pathways_Into_Darkness.rsrc.strings.md` — full v2.0 app (28 `STR#` lists, menus, `scri` harvest)
- `strings/extracted__PathwaysDemo__Pathways_Demo_ƒ__Pathways_into_Darkness.rsrc.strings.md` — demo app
- `harvest/hfs__Pathways_1995__Maps.harvest.md`
- `harvest/extracted__PathwaysDemo__Pathways_Demo_ƒ__Maps.harvest.md`

`python tools/dump_all.py data` regenerates this tree.
