# Work journal

Dated log of attempts, including failures.

---

## 2026-09-01

Set up the Phase 0 working environment on Windows.

- Repo layout from `PROJECT.md`.
- `.venv` + `requirements.txt`: `rsrcfork` 1.8.0, Pillow, numpy,
  kaitaistruct, `machfs` (MIT) / `macresources`.
- Windows `unar`/`lsar` in `tools/bin/` (from
  `https://cdn.theunarchiver.com/downloads/unarWindows.zip`).
- Tools: `unpack_archives.py`, `extract_hfs.py`, `list_resources.py`,
  `rsrc.py`, `write_checksums.py`, `mac_containers.py`.

Original archives were already on `Desktop/PIDOriginalData/`. Copied into
gitignored `data/archives/` (not TheUnarchiver.dmg).

`unar` unpacked every archive. Resource forks survived as AppleDouble
`.rsrc` files (not `._*` sidecars, not NTFS streams).

HFS extract: raw `.dsk` mounts directly; `.image` / `.dc42` mount after
skipping the published 84-byte DiskCopy 4.2 header. Japanese disk 1
worked once we stopped printing Unicode to the console.

Playable trees now on disk:

- Demo: loose Maps (50502 bytes) + app/Shapes/Sounds resource forks.
- v2.0: `Pathways_1995.dsk` → Maps (420850) + app (`vers` 1 = v2.0).

`rsrcfork` via `tools/rsrc.py` listed 85 resource files. Full-game
`STR#` 2018/2021 match the published level-name examples. Demo lacks
those two IDs.

Not done: Japanese/v1.1 installer payload expansion; Map data-fork
directory (PROJECT.md step 5–6). Fan `PIDMapReader` sources sit in
`data/hfs/Pathways_Extras/PID_Docs Folder/` for later reading — not
copied into git.
