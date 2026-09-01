# -*- coding: utf-8 -*-
"""Round 9 Task 5: Ground Floor save runes + Pathways Into Cheating DITL/STR#."""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import decode_mac_roman, format_string_list, hexdump_mac_roman, parse_str_list  # noqa: E402
from pid_level import SECTOR_TYPE_NAME, load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
CHEAT = next((ROOT / "data/hfs/Pathways_Extras").glob("Pathways Into Cheating*/Pathways Into Cheating.rsrc"))
OUT = ROOT / "reference/docs/round9_cheating.txt"


def parse_ditl(data: bytes) -> list[dict]:
    """Inside Macintosh DITL: i16 count-1, then items."""
    if len(data) < 2:
        return []
    n_minus_1 = struct.unpack_from(">h", data, 0)[0]
    count = n_minus_1 + 1
    pos = 2
    items = []
    for i in range(count):
        if pos + 14 > len(data):
            items.append({"i": i, "error": f"truncated at {pos}"})
            break
        placeholder = struct.unpack_from(">i", data, pos)[0]
        top, left, bottom, right = struct.unpack_from(">hhhh", data, pos + 4)
        itype = data[pos + 12]
        dlen = data[pos + 13]
        pos += 14
        payload = data[pos : pos + dlen]
        pos += dlen
        if pos % 2:
            pos += 1  # word align
        kind = itype & 0x7F
        enabled = (itype & 0x80) == 0
        kind_name = {
            0: "userItem",
            1: "helpItem",
            4: "button",
            5: "checkBox",
            6: "radio",
            7: "control",
            8: "staticText",
            16: "editText",
            32: "icon",
            64: "picItem",
        }.get(kind, f"type_{kind}")
        text = ""
        if kind in (4, 5, 6, 8, 16) and payload:
            text = decode_mac_roman(payload)
        items.append(
            {
                "i": i,
                "placeholder": placeholder,
                "rect": (top, left, bottom, right),
                "type": kind_name,
                "enabled": enabled,
                "data_len": dlen,
                "text": text,
                "raw": payload.hex(" ") if kind not in (4, 5, 6, 8, 16) else "",
            }
        )
    return items


def main() -> None:
    lines: list[str] = []
    levels = load_maps(MAPS)
    gf = levels[0]
    lines.append(f"== Ground Floor name={gf.name!r} height10={gf.height10} ==")
    saves = []
    corpses = []
    for i, sec in enumerate(gf.sector_list):
        x, y = gf.sector_xy(i)
        if sec.type == 9:
            saves.append((x, y, i, sec.item, sec.type_addl))
        if sec.type == 6:
            corpses.append((x, y, i, sec.item, sec.type_addl))
    lines.append(f"save-rune count={len(saves)}")
    for x, y, i, item, addl in saves:
        lines.append(f"  SAVE (x={x}, y={y}) sector={i} Item={item} TypeAddl={addl}")
    lines.append(f"corpse count={len(corpses)}")
    for x, y, i, item, addl in corpses:
        lines.append(f"  CORPSE (x={x}, y={y}) sector={i} Item={item} TypeAddl={addl}")

    import rsrcfork

    payload = load_resource_payload(CHEAT)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    lines.append(f"\n== Pathways Into Cheating types={[t.decode('latin-1', 'replace') for t in rf]} ==")

    if b"STR#" in rf:
        lines.append("\n== STR# ==")
        for rid in rf[b"STR#"]:
            res = rf[b"STR#"][rid]
            data = res.data_raw
            name = res.name or ""
            parsed = parse_str_list(data)
            lines.append(f"STR# {rid} name={name!r} size={len(data)}")
            if parsed:
                lines.append(format_string_list(parsed))
            else:
                lines.append(hexdump_mac_roman(data))

    if b"DITL" in rf:
        lines.append("\n== DITL ==")
        for rid in rf[b"DITL"]:
            res = rf[b"DITL"][rid]
            data = res.data_raw
            name = res.name or ""
            lines.append(f"\n--- DITL {rid} name={name!r} size={len(data)} ---")
            items = parse_ditl(data)
            for it in items:
                extra = f" text={it['text']!r}" if it.get("text") else ""
                raw = f" raw={it['raw']}" if it.get("raw") else ""
                err = f" ERR={it['error']}" if it.get("error") else ""
                lines.append(
                    f"  [{it['i']:02d}] {it.get('type','?'):12s} rect={it.get('rect')} "
                    f"en={it.get('enabled')}{extra}{raw}{err}"
                )

    if b"MENU" in rf:
        from mac_text import parse_menu

        lines.append("\n== MENU (field names) ==")
        for rid in rf[b"MENU"]:
            res = rf[b"MENU"][rid]
            m = parse_menu(res.data_raw)
            if m:
                lines.append(f"MENU {rid} title={m['title']!r} items={m['items']}")

    dest = OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n... wrote {dest}")


if __name__ == "__main__":
    main()
