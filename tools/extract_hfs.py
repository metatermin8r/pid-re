"""Extract HFS (and DiskCopy 4.2-wrapped HFS) images under data/extracted.

Data forks become regular files. Resource forks become sibling ``.rsrc``
files containing a raw Resource Manager map (not AppleDouble).

DiskCopy 4.2: if the image is not raw HFS, retry after skipping the
published 84-byte DC42 header. That 84-byte size is the DC42 spec, not a
PID offset.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import machfs

ROOT = Path(__file__).resolve().parents[1]
DC42_HEADER_SIZE = 84
IMAGE_SUFFIXES = {".dsk", ".image", ".dc42", ".img"}
SKIP_NAMES = {"Icon\r", "Desktop Folder", "TheVolumeSettingsFolder", "Trash"}


def _safe_name(name: str) -> str:
    cleaned = name.replace("\r", "").replace("\n", "").rstrip(" .")
    for bad in '<>:"/\\|?*':
        cleaned = cleaned.replace(bad, "_")
    return cleaned or "unnamed"


def _try_read_volume(blob: bytes) -> machfs.Volume | None:
    vol = machfs.Volume()
    try:
        vol.read(blob)
        return vol
    except ValueError:
        return None


def open_volume(path: Path) -> tuple[machfs.Volume, str]:
    blob = path.read_bytes()
    vol = _try_read_volume(blob)
    if vol is not None:
        return vol, "raw-hfs"
    if len(blob) > DC42_HEADER_SIZE:
        vol = _try_read_volume(blob[DC42_HEADER_SIZE:])
        if vol is not None:
            return vol, "dc42"
    raise ValueError(f"not an HFS image I can read: {path}")


def write_file(dest_dir: Path, name: str, node) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = dest_dir / _safe_name(name)
    data = node.data or b""
    rsrc = node.rsrc or b""
    if data:
        base.write_bytes(data)
    if rsrc:
        rsrc_path = base.with_name(base.name + ".rsrc")
        rsrc_path.write_bytes(rsrc)


def walk(node, dest_dir: Path) -> int:
    written = 0
    if not hasattr(node, "keys"):
        return 0
    for name in node.keys():
        if name in SKIP_NAMES:
            continue
        child = node[name]
        if hasattr(child, "data") and hasattr(child, "rsrc"):
            write_file(dest_dir, name, child)
            written += 1
            continue
        if hasattr(child, "keys"):
            written += walk(child, dest_dir / _safe_name(name))
    return written


def extract_image(image: Path, out_root: Path) -> int:
    vol, kind = open_volume(image)
    dest = out_root / _safe_name(image.stem)
    dest.mkdir(parents=True, exist_ok=True)
    count = walk(vol, dest)
    print(f"{image}: {kind}, {count} files -> {dest}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan",
        default=str(ROOT / "data" / "extracted"),
        help="Find disk images under this tree",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "hfs"),
        help="Output root for extracted files",
    )
    args = parser.parse_args()

    scan = Path(args.scan)
    out_root = Path(args.out)
    images = [
        path
        for path in sorted(scan.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and not path.name.endswith(".rsrc")
    ]
    if not images:
        print(f"no disk images under {scan}", file=sys.stderr)
        return 1

    total = 0
    failures = 0
    for image in images:
        try:
            total += extract_image(image, out_root)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {image}: {exc}", file=sys.stderr)
    print(f"extracted {total} files, {failures} images failed")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
