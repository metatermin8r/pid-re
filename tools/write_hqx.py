# -*- coding: utf-8 -*-
"""Write a clean .hqx from SuperdudeSavedGame.txt for unar."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/cd/pathwaysintodarkness/docs_web/SuperdudeSavedGame.txt"
OUT = ROOT / "reference/saves/Yoyoby.hqx"

text = SRC.read_bytes().decode("latin-1")
marker = "(This file must be converted with BinHex 4.0)"
idx = text.find(marker)
region = text[idx:]
# keep from first colon after marker through last colon
first = region.find(":")
last = region.rfind(":")
body = region[first : last + 1]
# drop news quoting artifacts that are not HQX alphabet or colon/newline
hqx_ok = set(
    '!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr:\r\n'
)
clean = "".join(ch if ch in hqx_ok else "" for ch in body)
OUT.write_text(
    "(This file must be converted with BinHex 4.0)\r\n" + clean + "\r\n",
    encoding="ascii",
)
print(f"wrote {OUT} body_chars={len(clean)}")
