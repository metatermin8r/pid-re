"""Thin rsrcfork front-end that peels AppleDouble / MacBinary first.

Usage (venv active, from repo root):
    python tools/rsrc.py list path/to/file.rsrc
    python tools/rsrc.py read path/to/file.rsrc STR# 128
    python tools/rsrc.py read path/to/file.rsrc STR# 128 --text
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import (  # noqa: E402
    decode_mac_roman,
    format_string_list,
    hexdump_mac_roman,
    parse_menu,
    parse_str,
    parse_str_list,
    parse_vers,
)


def _open_rf(path: Path):
    import rsrcfork

    payload = load_resource_payload(path)
    if payload is None:
        raise SystemExit(f"no resource map found in {path}")
    return rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False), payload


def _type_bytes(label: str) -> bytes:
    raw = label.encode("mac_roman")
    if len(raw) > 4:
        raise SystemExit(f"type code longer than 4 bytes: {label!r}")
    return raw.ljust(4)


def cmd_list(path: Path) -> None:
    from list_resources import list_one

    text = list_one(path)
    if text is None:
        raise SystemExit(f"no resource map found in {path}")
    sys.stdout.write(text)


def _print_text_resource(type_code: bytes, data: bytes) -> None:
    if type_code == b"STR#":
        parsed = parse_str_list(data)
        if parsed is None:
            raise SystemExit("STR# did not parse as count + Pascal strings")
        print(f"count: {len(parsed)}")
        print(format_string_list(parsed))
        return
    if type_code == b"STR ":
        parsed = parse_str(data)
        if parsed is None:
            raise SystemExit("STR  did not parse as a Pascal string")
        print(parsed.replace("\r", "\n"))
        return
    if type_code == b"MENU":
        parsed = parse_menu(data)
        if parsed is None:
            raise SystemExit("MENU did not parse")
        print(f"menu_id: {parsed['id']}")
        print(f"title: {parsed['title']}")
        print(format_string_list(parsed["items"]))
        return
    if type_code == b"vers":
        parsed = parse_vers(data)
        if parsed is None:
            raise SystemExit("vers did not parse")
        print(f"short: {parsed['short']}")
        print(f"long: {parsed['long']}")
        return
    text = decode_mac_roman(data).replace("\r", "\n")
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def cmd_read(path: Path, type_code: str, res_id: int, as_text: bool) -> None:
    rf, payload = _open_rf(path)
    key = _type_bytes(type_code)
    if key not in rf:
        raise SystemExit(f"type {type_code!r} not in {path} (source={payload.source})")
    if res_id not in rf[key]:
        raise SystemExit(f"{type_code} ({res_id}) not in {path}")
    res = rf[key][res_id]
    data = res.data
    header = f"Resource {type_code!r} ({res_id}): {len(data)} bytes, source={payload.source}"
    if res.name:
        name = decode_mac_roman(res.name) if isinstance(res.name, bytes) else res.name
        header += f", name={name}"
    print(header)
    if as_text:
        _print_text_resource(key, data)
        return
    print(hexdump_mac_roman(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List types and IDs")
    p_list.add_argument("path", type=Path)

    p_read = sub.add_parser("read", help="Dump one resource")
    p_read.add_argument("path", type=Path)
    p_read.add_argument("type")
    p_read.add_argument("id", type=int)
    p_read.add_argument("--text", action="store_true", help="MacRoman text instead of hex")

    args = parser.parse_args()
    if args.cmd == "list":
        cmd_list(args.path)
        return 0
    cmd_read(args.path, args.type, args.id, args.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
