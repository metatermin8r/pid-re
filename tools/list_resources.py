"""Inventory Mac resource maps under data/ and write dumps to reference/.

Usage (from repo root, venv active):
    python tools/list_resources.py
    python tools/list_resources.py data/extracted --out reference
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402

SKIP_SUFFIXES = {".sit", ".hqx", ".zip", ".dmg", ".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png"}
SKIP_DIR_NAMES = {".git", ".venv", "venv", "tools", "docs", "formats"}


def _fourcc(raw: bytes) -> str:
    try:
        return raw.decode("mac_roman")
    except UnicodeDecodeError:
        return raw.hex()


def list_one(path: Path) -> str | None:
    payload = load_resource_payload(path)
    if payload is None:
        return None

    import rsrcfork

    try:
        rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    except Exception as exc:  # noqa: BLE001 — inventory must not die on one file
        return f"# {path.as_posix()}\nsource: {payload.source}\nerror: {exc}\n"

    lines = [
        f"# {path.as_posix()}",
        f"source: {payload.source}",
        f"resource_bytes: {len(payload.data)}",
        f"types: {len(rf)}",
        "",
    ]
    for type_code in sorted(rf, key=lambda t: t):
        resources = rf[type_code]
        label = _fourcc(type_code)
        lines.append(f"'{label}': {len(resources)} resources:")
        for res_id in sorted(resources):
            res = resources[res_id]
            name = res.name if res.name else ""
            extra = f"  name={name!r}" if name else ""
            lines.append(f"  ({res_id}): {res.length} bytes{extra}")
        lines.append("")
    return "\n".join(lines) + "\n"


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def relabel(path: Path, scan_root: Path) -> str:
    try:
        rel = path.relative_to(scan_root)
    except ValueError:
        rel = path
    return "__".join(rel.parts).replace(" ", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=str(ROOT / "data"),
        help="Directory to walk (default: data/)",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "reference"),
        help="Directory for per-file dumps (default: reference/)",
    )
    args = parser.parse_args()

    scan_root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not scan_root.exists():
        print(f"missing scan root: {scan_root}", file=sys.stderr)
        return 1

    hits = 0
    misses = 0
    index_lines = ["# Resource-fork inventory", "", f"scan_root: {scan_root}", ""]

    for path in iter_files(scan_root):
        text = list_one(path)
        if text is None:
            misses += 1
            continue
        hits += 1
        dump_name = relabel(path, scan_root) + ".rsrc.txt"
        dump_path = out_dir / dump_name
        dump_path.write_text(text, encoding="utf-8")
        index_lines.append(f"- {path.relative_to(scan_root).as_posix()} -> {dump_name}")
        print(f"listed {path}")

    index_lines += ["", f"files_with_resources: {hits}", f"files_skipped: {misses}", ""]
    (out_dir / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    print(f"done: {hits} resource files, {misses} skipped, index at {out_dir / 'INDEX.md'}")
    return 0 if hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
