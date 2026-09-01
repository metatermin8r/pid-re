"""List every file under data/hfs/ and rsrcfork-list each one.

Does not skip Maps or data-fork-only files. Writes a size inventory and
per-file resource lists. Flags PICT, snd , and type codes not seen in
the v2.0 application fork.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from list_resources import _fourcc, list_one  # noqa: E402
from mac_containers import load_resource_payload  # noqa: E402

APP_TYPES = {
    "ALRT", "BNDL", "CODE", "DITL", "DLOG", "FOND", "FONT", "FREF", "ICN#",
    "ICON", "MBAR", "MENU", "NFNT", "SIZE", "STR ", "STR#", "WDEF", "cfrg",
    "cicn", "clut", "crsr", "dctb", "dpin", "icl4", "icl8", "ics#", "ics4",
    "ics8", "ppat", "påth", "scri", "vers",
}


def relabel(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    return "__".join(rel.parts).replace(" ", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT / "data" / "hfs"))
    parser.add_argument("--out", default=str(ROOT / "reference"))
    args = parser.parse_args()

    scan = Path(args.root).resolve()
    out = Path(args.out).resolve()
    lists_dir = out / "rsrc_lists"
    lists_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in scan.rglob("*") if p.is_file())
    type_files: dict[str, list[str]] = defaultdict(list)
    lines = [
        f"scan_root: {scan}",
        f"file_count: {len(files)}",
        "",
        "path\tsize\tappledouble_or_rsrc\thas_resource_map\tdata_fork_note",
    ]

    for path in files:
        rel = path.relative_to(scan).as_posix()
        size = path.stat().st_size
        sidecar = path.name.startswith("._") or path.suffix.lower() == ".rsrc"
        payload = load_resource_payload(path)
        has_map = payload is not None
        note = ""
        if path.name.lower() == "maps":
            note = "DATA-FORK Maps file (no resource map expected)"
        if path.name == "Pathways Into Darkness" and not path.name.endswith(".rsrc"):
            note = f"application DATA fork, {size} bytes (cfrg present in resource fork)"
        lines.append(f"{rel}\t{size}\t{sidecar}\t{has_map}\t{note}")

        listing = list_one(path)
        if listing is None:
            (lists_dir / (relabel(path, scan) + ".none.txt")).write_text(
                f"# {path.as_posix()}\nsize: {size}\nno resource map\n",
                encoding="utf-8",
            )
            continue
        dump_path = lists_dir / (relabel(path, scan) + ".rsrc.txt")
        dump_path.write_text(listing, encoding="utf-8")
        import rsrcfork

        rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False)
        for type_code in rf:
            label = _fourcc(type_code)
            type_files[label].append(f"{rel} x{len(rf[type_code])}")

    wanted = ["PICT", "snd ", "snd", ".256"]
    lines += ["", "=== types of interest ===", ""]
    for label in sorted(type_files):
        flag = ""
        if label in ("PICT", "snd ", ".256"):
            flag = "  ** LOOK **"
        elif label not in APP_TYPES:
            flag = "  ** not in v2.0 app fork **"
        lines.append(f"'{label}'{flag}")
        for row in type_files[label]:
            lines.append(f"  {row}")

    report = out / "hfs_inventory.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.write("\n".join(lines) + "\n")
    print(f"wrote {report}")
    print(f"lists in {lists_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
