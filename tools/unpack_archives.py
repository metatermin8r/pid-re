"""Unpack Mac archives under data/archives with unar (resource-fork safe)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNAR = ROOT / "tools" / "bin" / "unar.exe"
ARCHIVE_SUFFIXES = {".sit", ".hqx", ".bin", ".sea", ".zip"}


def find_unar() -> Path:
    if UNAR.exists():
        return UNAR
    on_path = shutil.which("unar")
    if on_path:
        return Path(on_path)
    raise FileNotFoundError(
        "unar.exe not found. Download the Windows build into tools/bin/ "
        "(https://cdn.theunarchiver.com/downloads/unarWindows.zip)."
    )


def unpack_one(unar: Path, archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    # -f overwrite, -D do not create an extra wrapper dir if the archive
    # already has a top-level folder. We still isolate per-archive.
    target = dest / archive.stem
    target.mkdir(parents=True, exist_ok=True)
    cmd = [str(unar), "-f", "-o", str(target), str(archive)]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archives",
        default=str(ROOT / "data" / "archives"),
        help="Folder of .sit/.hqx/.zip files",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "extracted"),
        help="Output folder",
    )
    args = parser.parse_args()

    archives_dir = Path(args.archives)
    out_dir = Path(args.out)
    if not archives_dir.exists():
        print(f"missing archives dir: {archives_dir}", file=sys.stderr)
        return 1

    unar = find_unar()
    archives = [
        path
        for path in sorted(archives_dir.iterdir())
        if path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES
    ]
    if not archives:
        print(f"no archives in {archives_dir}", file=sys.stderr)
        return 1

    for archive in archives:
        unpack_one(unar, archive, out_dir)
    print(f"unpacked {len(archives)} archives into {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
