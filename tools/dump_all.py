"""Full Mac Roman dump of text-bearing resources and data-fork harvests.

Writes UTF-8 reports under reference/full_dump/. Does not invent Map
offsets: harvest hits record where printable bytes were found.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from list_resources import SKIP_DIR_NAMES, SKIP_SUFFIXES, _fourcc  # noqa: E402
from mac_containers import load_resource_payload  # noqa: E402
from mac_text import (  # noqa: E402
    decode_mac_roman,
    format_string_list,
    harvest_pascal_strings,
    harvest_text_runs,
    parse_menu,
    parse_str,
    parse_str_list,
    parse_vers,
)

STRING_TYPES = {b"STR#", b"STR ", b"TEXT", b"MENU", b"vers"}
HARVEST_TYPES = {b"scri", b"DITL", b"ALRT", b"dpin"}
HARVEST_FILENAMES = {"maps"}


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
        rel = Path(path.name)
    return "__".join(rel.parts).replace(" ", "_")


def open_rf(path: Path):
    import rsrcfork

    payload = load_resource_payload(path)
    if payload is None:
        return None, None
    try:
        rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False)
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc}"
    return (rf, payload), None


def dump_resource_strings(path: Path, rf, payload, out_dir: Path) -> tuple[int, list[str]]:
    lines = [
        f"# {path.as_posix()}",
        f"source: {payload.source}",
        "",
    ]
    string_count = 0
    type_summary: list[str] = []

    for type_code in sorted(rf, key=lambda t: t):
        label = _fourcc(type_code)
        resources = rf[type_code]
        type_summary.append(f"{label}\t{len(resources)}")
        if type_code not in STRING_TYPES and type_code not in HARVEST_TYPES:
            named = []
            for res_id in sorted(resources):
                name = resources[res_id].name
                if name:
                    named.append(f"  ({res_id}) name={_name_text(name)}")
            if named:
                lines += [f"## '{label}' resource names", *named, ""]
            continue

        lines.append(f"## '{label}'")
        for res_id in sorted(resources):
            res = resources[res_id]
            data = res.data
            name = _name_text(res.name) if res.name else ""
            header = f"### {label} ({res_id}) {len(data)} bytes"
            if name:
                header += f" name={name}"
            lines.append(header)

            if type_code == b"STR#":
                parsed = parse_str_list(data)
                if parsed is None:
                    lines.append("(STR# parse failed — not listed)")
                else:
                    string_count += len(parsed)
                    lines.append(f"count: {len(parsed)}")
                    lines.append(format_string_list(parsed))
            elif type_code == b"STR ":
                parsed = parse_str(data)
                if parsed is None:
                    lines.append("(STR  parse failed)")
                else:
                    string_count += 1
                    lines.append(parsed.replace("\r", "\n"))
            elif type_code == b"TEXT":
                string_count += 1
                lines.append(decode_mac_roman(data).replace("\r", "\n"))
            elif type_code == b"MENU":
                parsed = parse_menu(data)
                if parsed is None:
                    lines.append("(MENU parse failed)")
                else:
                    string_count += 1 + len(parsed["items"])
                    lines.append(f"menu_id: {parsed['id']}")
                    lines.append(f"title: {parsed['title']}")
                    lines.append(format_string_list(parsed["items"]))
            elif type_code == b"vers":
                parsed = parse_vers(data)
                if parsed is None:
                    lines.append("(vers parse failed)")
                else:
                    string_count += 2
                    lines.append(f"version: {parsed['major']}.{parsed['minor']:02x}")
                    lines.append(f"short: {parsed['short']}")
                    lines.append(f"long: {parsed['long']}")
            else:
                pascal = harvest_pascal_strings(data, min_len=3)
                runs = harvest_text_runs(data, min_len=8)
                lines.append(f"pascal_hits: {len(pascal)}")
                for off, text in pascal:
                    string_count += 1
                    lines.append(f"  @{off:08x}  {text.replace(chr(13), ' / ')}")
                if type_code == b"scri":
                    lines.append(f"text_runs: {len(runs)}")
                    for off, text in runs:
                        lines.append(f"  @{off:08x}  {text.replace(chr(13), ' / ')}")
            lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / (relabel(path, ROOT / "data") + ".strings.md")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return string_count, type_summary


def _name_text(name: object) -> str:
    if name is None:
        return ""
    if isinstance(name, bytes):
        return decode_mac_roman(name)
    return str(name)


def harvest_file(path: Path, out_dir: Path, min_len: int = 6) -> int:
    data = path.read_bytes()
    pascal = harvest_pascal_strings(data, min_len=4)
    runs = harvest_text_runs(data, min_len=min_len)
    lines = [
        f"# {path.as_posix()}",
        f"size: {len(data)}",
        f"pascal_hits: {len(pascal)}",
        f"text_runs: {len(runs)}",
        "",
        "## Pascal-style hits",
        "",
    ]
    for off, text in pascal:
        lines.append(f"- `{off:08x}` ({len(text)}) {text.replace(chr(13), ' / ')}")
    lines += ["", "## Printable Mac Roman runs", ""]
    for off, text in runs:
        shown = text.replace("\r", " / ").replace("\n", " / ")
        if len(shown) > 400:
            shown = shown[:400] + "…"
        lines.append(f"- `{off:08x}` ({len(text)}) {shown}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / (relabel(path, ROOT / "data") + ".harvest.md")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(pascal) + len(runs)


def interesting_data_fork(path: Path) -> bool:
    """Only the Maps data fork. Installers and disk images are too noisy."""
    return path.name.lower() == "maps"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(ROOT / "data"))
    parser.add_argument("--out", default=str(ROOT / "reference" / "full_dump"))
    args = parser.parse_args()

    scan_root = Path(args.root).resolve()
    out_root = Path(args.out).resolve()
    strings_dir = out_root / "strings"
    harvest_dir = out_root / "harvest"
    out_root.mkdir(parents=True, exist_ok=True)

    catalog: dict[str, list[tuple[str, int]]] = defaultdict(list)
    index: list[str] = ["# Full dump", "", f"scan_root: {scan_root}", ""]
    total_strings = 0
    rsrc_files = 0

    for path in iter_files(scan_root):
        opened, err = open_rf(path)
        if opened:
            rf, payload = opened
            rsrc_files += 1
            count, type_summary = dump_resource_strings(path, rf, payload, strings_dir)
            total_strings += count
            rel = path.relative_to(scan_root).as_posix()
            index.append(f"- strings: {rel} ({count} decoded/harvested)")
            for row in type_summary:
                label, n = row.split("\t")
                catalog[label].append((rel, int(n)))
            print(f"dumped {path} ({count})")
        elif err:
            print(f"skip rsrc {path}: {err}", file=sys.stderr)

        if interesting_data_fork(path) or path.name == "Maps":
            hits = harvest_file(path, harvest_dir)
            index.append(f"- harvest: {path.relative_to(scan_root).as_posix()} ({hits} hits)")
            print(f"harvested {path} ({hits})")

    cat_lines = [
        "# Resource type catalog",
        "",
        "Every type code seen, with file counts. Type codes decoded as Mac Roman.",
        "",
        f"resource_files: {rsrc_files}",
        "",
    ]
    for label in sorted(catalog, key=lambda s: s.lower()):
        files = catalog[label]
        total = sum(n for _, n in files)
        cat_lines.append(f"## '{label}' — {total} resources in {len(files)} files")
        for rel, n in files:
            cat_lines.append(f"- {n}  {rel}")
        cat_lines.append("")

    (out_root / "CATALOG.md").write_text("\n".join(cat_lines), encoding="utf-8")
    index += ["", f"resource_files: {rsrc_files}", f"decoded_or_harvested_strings: {total_strings}", ""]
    (out_root / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    print(f"wrote {out_root} ({rsrc_files} resource files, {total_strings} strings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
