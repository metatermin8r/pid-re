# Pathways Into Darkness

Open-source reimplementation of Bungie's 1993 Macintosh game. Engine only;
users supply original data. See `PROJECT.md` for constraints and method.

**Current phase:** data archaeology. No Unity.

## Setup (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`unar.exe` lives in `tools/bin/` (downloaded from The Unarchiver's Windows
CLI zip). Original archives go in `data/` — that folder is gitignored.

## Everyday commands

```powershell
.\.venv\Scripts\Activate.ps1

# Inventory every resource fork under data/
python tools/list_resources.py data

# Inspect one file (AppleDouble or raw .rsrc)
python tools/rsrc.py list "data\hfs\Pathways_1995\Pathways Into Darkness.rsrc"
python tools/rsrc.py read "data\hfs\Pathways_1995\Pathways Into Darkness.rsrc" STR# 2018 --text

# Full Mac Roman dump (STR# parsed as Pascal lists)
python tools/dump_all.py data
```

`--text` on `STR#` / `STR ` / `MENU` / `vers` uses Mac Roman and the
published Resource Manager layouts. Hex dumps use a Mac Roman gutter.

Dumps land in `reference/full_dump/`. Observed layout goes in `docs/FORMAT.md`.
