# -*- coding: utf-8 -*-
"""Derive and apply scri XOR from published Dead Scripts plaintext."""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import load_resource_payload  # noqa: E402
from mac_text import decode_mac_roman  # noqa: E402
from pid_level import load_maps  # noqa: E402

APP = ROOT / "data/hfs/Pathways_1995/Pathways Into Darkness.rsrc"
MAPS = ROOT / "data/hfs/Pathways_1995/Maps"
PART1 = ROOT / "data/cd/pathwaysintodarkness/docs_web/DeadScriptsPart1.txt"
PART2 = ROOT / "data/cd/pathwaysintodarkness/docs_web/DeadScriptsPart2.txt"
OUT = ROOT / "reference/docs"


def load_scri() -> dict[int, bytes]:
    import rsrcfork

    payload = load_resource_payload(APP)
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=True)
    return {rid: rf[b"scri"][rid].data_raw for rid in rf[b"scri"]}


def load_published() -> dict[int, str]:
    text = ""
    for path in (PART1, PART2):
        text += decode_mac_roman(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
    blocks: dict[int, str] = {}
    parts = re.split(r"^-----scri (\d+).*-----\s*$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        body = re.split(r"^Chuck Gray", parts[i + 1], flags=re.M)[0].strip("\n")
        blocks[int(parts[i])] = body
    return blocks


def decrypt(raw: bytes, start: int = 2, counter0: int = 0) -> bytes:
    return bytes(
        (raw[start + i] ^ ((counter0 + i) & 0xFF)) for i in range(len(raw) - start)
    )


def norm(s: str) -> str:
    s = s.replace("!", "'")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def line_match(decrypted: str, published: str) -> float:
    pub_lines = [norm(ln) for ln in published.splitlines() if norm(ln)]
    if not pub_lines:
        return 0.0
    blob = norm(decrypted)
    hits = sum(1 for ln in pub_lines if ln in blob)
    return 100.0 * hits / len(pub_lines)


def main() -> None:
    scri = load_scri()
    published = load_published()
    raw = scri[128]
    dec = decrypt(raw, 2, 0)
    ks = bytes(((i) & 0xFF) for i in range(32))
    lines = [
        "scheme: skip 2 bytes (u16be length), XOR remainder with 00 01 02 ... wrap 256",
        f"scri128 raw_len={len(raw)} u16be@0={int.from_bytes(raw[:2], 'big')}",
        f"keystream_first32={ks.hex(' ')}",
        f"dec128_first64={dec[:64].hex(' ')}",
        f"dec128_ascii={decode_mac_roman(dec[:200])!r}",
        f"raw[6:10]={raw[6:10].hex(' ')}  dec[4:8]={dec[4:8].hex(' ')}",
        "",
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    scores = []
    for rid in range(128, 158):
        if rid not in scri:
            continue
        blob = scri[rid]
        plain = decrypt(blob, 2, 0)
        text = decode_mac_roman(plain).replace("\r", "\n")
        (OUT / "scri_dec" / f"{rid}.txt").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "scri_dec" / f"{rid}.txt").write_text(text, encoding="utf-8")
        pub = published.get(rid, "")
        pct = line_match(text, pub) if pub else None
        scores.append((rid, len(blob), pct, pub[:40].replace("\n", " ") if pub else "NO_PUB"))
        lines.append(
            f"scri {rid}: raw={len(blob):5d} match={pct if pct is not None else 'n/a'} "
            f"pub={pub[:40]!r}"
        )

    # Corpse TypeAddl -> scri 128+addl
    levels = load_maps(MAPS)
    lines.append("")
    lines.append("corpse TypeAddl -> scri 128+addl")
    for li, level in enumerate(levels):
        corpses = [
            (i % 32, i // 32, sec.type_addl)
            for i, sec in enumerate(level.sector_list)
            if sec.type == 6
        ]
        if not corpses:
            continue
        lines.append(f"  L{li} {level.name!r}")
        for x, y, addl in corpses:
            rid = 128 + addl if addl <= 27 else addl
            note = f"scri {128 + addl}" if addl <= 27 else f"SPECIAL {addl} (Torch Carlos=200)"
            lines.append(f"    ({x},{y}) addl={addl} -> {note}")

    dest = OUT / "scri_derive.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
