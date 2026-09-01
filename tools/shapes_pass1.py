# -*- coding: utf-8 -*-
"""Texture list cross-tab, .256 128 header, app clut 256 -> palette.png."""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import hexdump_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
SHAPES = ROOT / "data/hfs/Pathways_1995/Shapes.rsrc"
APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
OUT = ROOT / "reference/docs"

# Petrich Ident256ShapeRsrcs.txt (resource ID -> note). Map value = ID-128.
IDENT = {
    128: "Pickup items / dialog PID title / save rune / overall color table",
    129: "Nightmare, Greater Nightmare",
    130: "Headless",
    131: "Phantasm",
    132: "Ghoul",
    133: "Zombie, Ghast",
    134: "Shocking sphere",
    135: "Blue Meanie",
    136: "Barney?",
    137: "Demon",
    139: "Ooze, Green Ooze",
    140: "Wraith",
    141: "Sentinel",
    142: "Skitter, Venomous Skitter",
    148: "Walther Pistol",
    149: "MP-41 Submachine Gun",
    150: "AK-47 Assault Rifle",
    151: "M-79 Grenade Launcher",
    152: "Survival knife",
    153: "Plain-theme pillars",
    154: "Plain-theme scenery",
    155: "Plain-theme ladders",
    156: "Corpses",
    157: "Crystal-theme scenery",
    158: "Crystal-theme pillars",
    159: "Crystal-theme ladders",
    160: "Corpses",
    161: "Corpses",
    162: "Rat things",
    163: "Crystal-theme extra scenery",
    164: "Vine-theme pillars, ladders",
    165: "Corpses",
    166: "Lizard things, exploding pods",
    167: "Vine-theme scenery",
    187: "Pyramid-blowing-up cutscene?",
    188: "Game-selection graphics",
    189: "?",
    190: "Map-display graphics",
    191: "About-box graphics",
    192: "Plain-theme walls",
    193: "Vine-theme walls",
    194: "Crystal-theme walls",
    195: "Mottled gray floor/ceiling",
    196: "Pink/gray checkerboard floor/ceiling",
    197: "Blue or green floor/ceiling with black splotches",
    198: "Big cyan polkadotted floor/ceiling",
    199: "Dark purple floor/ceiling with inscriptions",
    200: "?",
    201: "?",
    202: "Irregular-orientation green-striped floor/ceiling",
}


def decode_texture(value: int) -> str:
    if value == -1:
        return "-1 none"
    variation = (value >> 12) & 0xF
    texset = value & 0x0FFF
    resid = texset + 128
    ident = IDENT.get(resid, "?")
    return f"{value} var={variation} set={texset} rsrc={resid} {ident}"


def theme_of(values: tuple[int, ...]) -> str:
    sets = []
    for v in values:
        if v == -1:
            continue
        sets.append(v & 0x0FFF)
    walls = sets[0] if sets else None
    if walls == 64:
        return "plain (walls 64 -> 192)"
    if walls == 65:
        return "vine (walls 65 -> 193)"
    if walls == 66:
        return "crystal (walls 66 -> 194)"
    return f"other/mixed walls_set={walls}"


def load_type(path: Path, type_code: bytes, rid: int) -> bytes:
    import rsrcfork

    payload = load_resource_payload(path)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return rf[type_code][rid].data_raw


def parse_clut(data: bytes) -> list[tuple[int, int, int, int]]:
    if len(data) < 8:
        raise ValueError("clut too small")
    seed, flags, size = struct.unpack(">IHH", data[:8])
    entries = []
    pos = 8
    for _ in range(size + 1):
        if pos + 8 > len(data):
            break
        index, r, g, b = struct.unpack(">HHHH", data[pos : pos + 8])
        entries.append((index, r, g, b))
        pos += 8
    return entries


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    levels = load_maps(MAPS)
    lines = ["# texture_list (i16be x8). map value low 12 bits + 128 = .256 id"]
    for i, level in enumerate(levels):
        lines.append(f"\n## {i:02d} {level.name}  theme={theme_of(level.texture_list)}")
        for slot, val in enumerate(level.texture_list):
            lines.append(f"  [{slot}] {decode_texture(val)}")

    shape = load_type(SHAPES, b".256", 128)
    lines.append(f"\n# .256 128 size={len(shape)}")
    lines.append(hexdump_mac_roman(shape[:256]))

    clut256 = load_type(APP, b"clut", 256)
    lines.append(f"\n# clut 256 size={len(clut256)} -- NOT a color table")
    credit = clut256[:160].decode("mac_roman", errors="replace").replace("\r", "\n")
    lines.append(credit)

    # Real cluts are 128-135: 128 bytes, size=14 -> 15 colors.
    img = Image.new("RGB", (16, 8))
    pix = img.load()
    for row, rid in enumerate(range(128, 136)):
        blob = load_type(APP, b"clut", rid)
        entries = parse_clut(blob)
        lines.append(
            f"clut {rid}: {len(blob)} bytes entries={len(entries)} "
            f"first={entries[0] if entries else None}"
        )
        for i, (index, r, g, b) in enumerate(entries[:16]):
            pix[i, row] = (r >> 8, g >> 8, b >> 8)
    scaled = img.resize((256, 128), Image.Resampling.NEAREST)
    pal_path = ROOT / "reference/palette.png"
    scaled.save(pal_path)
    lines.append(f"wrote {pal_path} from clut 128-135 (15 colors each)")

    dest = OUT / "shapes_pass1.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:80]))
    print(f"... wrote {dest}")
    print(f"clut entries={len(entries)} palette={pal_path}")


if __name__ == "__main__":
    main()
