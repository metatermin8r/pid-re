# -*- coding: utf-8 -*-
"""Inventory data/cd/: every file, every resource map, dpin/Maps checks."""

from __future__ import annotations

import argparse
import io
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from list_resources import _fourcc, list_one  # noqa: E402
from mac_containers import load_resource_payload  # noqa: E402
from mac_text import decode_mac_roman, harvest_text_runs  # noqa: E402

KNOWN_1995_APP_TYPES = {
    "ALRT", "BNDL", "CODE", "DITL", "DLOG", "FOND", "FONT", "FREF", "ICN#",
    "ICON", "MBAR", "MENU", "NFNT", "SIZE", "STR ", "STR#", "WDEF", "cfrg",
    "cicn", "clut", "crsr", "dctb", "dpin", "icl4", "icl8", "ics#", "ics4",
    "ics8", "ppat", "scri", "vers",
}
KNOWN_1995_ALL_TYPES = KNOWN_1995_APP_TYPES | {".256", "snd "}

IMAGE_SUFFIXES = {".dsk", ".iso", ".img", ".image", ".toast", ".dmg", ".bin", ".cue"}
TOOL_HINTS = (
    "edit", "debug", "test", "tool", "trainer", "cheat", "map", "hex",
    "reader", "torch", "guide", "hack", "docs", "source",
)


def relabel(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return "__".join(rel.parts).replace(" ", "_")


def hex64(data: bytes) -> str:
    lines = []
    chunk = data[:64]
    for off in range(0, len(chunk), 16):
        part = chunk[off : off + 16]
        hx = " ".join(f"{b:02x}" for b in part)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in part)
        lines.append(f"  {off:08x}  {hx:<48}  |{asc}|")
    return "\n".join(lines)


def identify(data: bytes) -> str:
    if data[:4] == b"\x00\x05\x16\x07":
        return "AppleDouble"
    if len(data) >= 4 and data[0] == 0 and 1 <= data[1] <= 63:
        if b"MacBinary" in data[:128] or (len(data) > 122 and data[102:106] == b"mBIN"):
            return "MacBinary?"
    if data[:4] == b"SIT!" or data[:4] == b"Stuff":
        return "StuffIt?"
    if data[:8] == b"\x00\x00\x00\x00\x00\x00\x00\x00" and b"HFS" in data[:1024]:
        return "maybe HFS"
    if data[0x400:0x402] == b"BD" or data[0x400:0x402] == b"H+":
        return "HFS/HFS+ volume (BD/H+ at 0x400)"
    if data[:2] == b"%P" or data[:5] == b"%PDF-":
        return "PDF"
    if data[:2] == b"\xff\xd8":
        return "JPEG"
    if data[:4] == b"\x00\x01\x00\x00" or data[:4] == b"true":
        return "maybe TrueType/other"
    if b"VISE" in data[:4096] or b"Vise" in data[:4096]:
        return "Installer VISE?"
    if data[:4] == b"PACT" or data[:2] == b"\x1f\x9d":
        return "Compact Pro / compress?"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT / "data" / "cd"))
    parser.add_argument("--out", default=str(ROOT / "reference" / "cd"))
    args = parser.parse_args()

    scan = Path(args.root).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in scan.rglob("*") if p.is_file())
    listing = [
        f"scan_root: {scan}",
        f"file_count: {len(files)}",
        "",
        "path\tsize\thidden_or_dot\tzero_data_fork\thas_rsrc_sibling_or_map",
    ]

    type_union: dict[str, list[str]] = defaultdict(list)
    dpin_hits: list[str] = []
    maps_hits: list[str] = []
    large_data: list[Path] = []

    for path in files:
        rel = path.relative_to(scan).as_posix()
        size = path.stat().st_size
        hidden = path.name.startswith(".") or path.name.startswith("._")
        payload = load_resource_payload(path)
        sibling_rsrc = path.with_name(path.name + ".rsrc").exists() or path.suffix.lower() == ".rsrc"
        zero = size == 0
        listing.append(
            f"{rel}\t{size}\t{hidden}\t{zero}\t{payload is not None or sibling_rsrc}"
        )
        if path.name.lower() == "maps" or "map" in path.name.lower():
            maps_hits.append(f"{rel} size={size} rsrc={payload is not None}")

        if payload is not None:
            text = list_one(path) or ""
            (out / (relabel(path, scan) + ".rsrc.txt")).write_text(text, encoding="utf-8")
            import rsrcfork

            rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False)
            for type_code in rf:
                label = _fourcc(type_code)
                type_union[label].append(f"{rel} x{len(rf[type_code])}")
                if label == "dpin":
                    for res_id, res in rf[type_code].items():
                        head = res.data[:16]
                        u0 = struct.unpack(">H", res.data[0:2])[0] if len(res.data) >= 2 else None
                        u2 = struct.unpack(">H", res.data[2:4])[0] if len(res.data) >= 4 else None
                        n80 = None
                        if u2 and (len(res.data) - 596) % 80 == 0:
                            n80 = (len(res.data) - 596) // 80
                        dpin_hits.append(
                            f"{rel} id={res_id} size={len(res.data)} "
                            f"first16={head.hex(' ')} u16@0={u0} u16@2={u2} "
                            f"size==596+N*80 -> N={n80} match_u2={n80 == u2}"
                        )
        elif size == 0:
            (out / (relabel(path, scan) + ".empty.txt")).write_text(
                f"# {rel}\nsize 0 data fork\n", encoding="utf-8"
            )

        if size >= 1024 and path.suffix.lower() not in {".rsrc", ".pdf", ".jpg", ".jpeg", ".png", ".txt", ".md"}:
            if payload is None:
                large_data.append(path)

    listing += ["", "=== resource type union ===", ""]
    for label in sorted(type_union, key=lambda s: s.lower()):
        listing.append(f"'{label}'")
        for row in type_union[label]:
            listing.append(f"  {row}")

    cd_types = set(type_union)
    listing += [
        "",
        "=== compare vs known 1995 app+shapes+sounds types ===",
        f"cd_only: {sorted(cd_types - KNOWN_1995_ALL_TYPES)}",
        f"known_1995_missing_on_cd_tree: {sorted(KNOWN_1995_ALL_TYPES - cd_types)}",
        "",
        "=== PICT / snd / .256 ===",
        f"PICT: {type_union.get('PICT', [])}",
        f"snd : {type_union.get('snd ', [])}",
        f".256: {type_union.get('.256', [])}",
        "",
        "=== dpin ===",
    ]
    listing.extend(dpin_hits or ["(none)"])
    listing += ["", "=== map-named files ==="]
    listing.extend(maps_hits or ["(none)"])

    listing += ["", "=== name hints (tool/edit/debug/test/map/docs) ==="]
    for path in files:
        rel = path.relative_to(scan).as_posix().lower()
        if any(h in rel for h in TOOL_HINTS):
            listing.append(f"{path.relative_to(scan).as_posix()}\t{path.stat().st_size}")

    listing += ["", "=== large non-resource-map files: first 64 hex + strings in 4KB ==="]
    for path in large_data:
        data = path.read_bytes()
        rel = path.relative_to(scan).as_posix()
        ident = identify(data)
        runs = harvest_text_runs(data[:4096], min_len=6)
        listing.append(f"--- {rel} size={len(data)} {ident} ---")
        listing.append(hex64(data))
        for off, text in runs[:20]:
            listing.append(f"  str@{off:04x} {text[:80].replace(chr(13), '/')}")

    report = out / "INVENTORY.txt"
    report.write_text("\n".join(listing) + "\n", encoding="utf-8")
    sys.stdout.write("\n".join(listing) + "\n")
    print(f"wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
