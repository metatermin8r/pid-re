"""Compare raw 'scri' resources. Tests, does not assume, the level mapping.

Hypothesis under test: scri ID 128+N is level N from STR# 2018
(28 names, 28 non-stub scri IDs 128-155).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_text import hexdump_mac_roman, parse_str_list  # noqa: E402
from mac_containers import load_resource_payload  # noqa: E402


def load_str2018(app_rsrc: Path) -> list[str] | None:
    import io

    import rsrcfork

    payload = load_resource_payload(app_rsrc)
    if payload is None:
        return None
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False)
    if b"STR#" not in rf or 2018 not in rf[b"STR#"]:
        return None
    return parse_str_list(rf[b"STR#"][2018].data)


def extract_scri(app_rsrc: Path, dest: Path) -> None:
    import io

    import rsrcfork

    payload = load_resource_payload(app_rsrc)
    if payload is None:
        raise SystemExit(f"no resource map in {app_rsrc}")
    rf = rsrcfork.ResourceFile(io.BytesIO(payload.data), close=False)
    dest.mkdir(parents=True, exist_ok=True)
    for res_id, res in sorted(rf[b"scri"].items()):
        (dest / f"{res_id}.bin").write_bytes(res.data)


def locate(data: bytes, needle: bytes) -> list[int]:
    hits = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return hits
        hits.append(pos)
        start = pos + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rsrc",
        default=str(ROOT / "data" / "hfs" / "Pathways_1995" / "Pathways Into Darkness.rsrc"),
    )
    parser.add_argument("--out", default=str(ROOT / "reference" / "scri"))
    parser.add_argument(
        "--report",
        default=str(ROOT / "reference" / "scri_compare.txt"),
    )
    args = parser.parse_args()

    dest = Path(args.out)
    extract_scri(Path(args.rsrc), dest)
    names = load_str2018(Path(args.rsrc)) or []

    files = sorted(dest.glob("*.bin"), key=lambda p: int(p.stem))
    blobs = {int(p.stem): p.read_bytes() for p in files}

    lines: list[str] = []
    lines.append(f"scri_count: {len(blobs)}")
    lines.append("sizes:")
    for rid, data in blobs.items():
        lines.append(f"  {rid}: {len(data)}")

    # Common prefix length across ALL, and across non-stubs only.
    all_ids = sorted(blobs)
    body_ids = [i for i in all_ids if len(blobs[i]) > 14]
    stub_ids = [i for i in all_ids if len(blobs[i]) <= 14]

    def common_prefix(ids: list[int]) -> bytes:
        if not ids:
            return b""
        prefix = blobs[ids[0]]
        for rid in ids[1:]:
            data = blobs[rid]
            n = 0
            while n < len(prefix) and n < len(data) and prefix[n] == data[n]:
                n += 1
            prefix = prefix[:n]
        return prefix

    cp_all = common_prefix(all_ids)
    cp_body = common_prefix(body_ids)
    cp_stub = common_prefix(stub_ids)
    lines += [
        "",
        f"non_stub_ids: {body_ids[0]}..{body_ids[-1]} ({len(body_ids)})" if body_ids else "non_stub_ids: none",
        f"stub_ids: {stub_ids}",
        f"common_prefix_all: {len(cp_all)} bytes  {cp_all.hex(' ')}",
        f"common_prefix_nonstub: {len(cp_body)} bytes  {cp_body.hex(' ')}",
        f"common_prefix_stubs: {len(cp_stub)} bytes  {cp_stub.hex(' ')}",
        "",
        "first 16 bytes of each (or full blob if shorter):",
    ]
    for rid, data in blobs.items():
        chunk = data[:16]
        u16 = struct.unpack(">H", data[:2])[0] if len(data) >= 2 else None
        u32 = struct.unpack(">I", data[:4])[0] if len(data) >= 4 else None
        lines.append(
            f"  {rid:3d} len={len(data):5d}  {chunk.hex(' '):48s}  "
            f"u16be[0]={u16}  u32be[0]={u32}"
        )

    lines += ["", "hex of stubs:"]
    for rid in stub_ids:
        lines.append(f"--- scri {rid} ({len(blobs[rid])} bytes) ---")
        lines.append(hexdump_mac_roman(blobs[rid]))

    # 14-byte header hypothesis: first 14 of each body vs each stub
    lines += ["", "14-byte-header hypothesis:"]
    if stub_ids:
        stub0 = blobs[stub_ids[0]][:14]
        lines.append(f"  stub {stub_ids[0]} bytes: {stub0.hex(' ')}")
        same_as_stub = [rid for rid in body_ids if blobs[rid][:14] == stub0]
        lines.append(f"  non-stubs whose first 14 equal stub: {same_as_stub}")
        first14 = [blobs[rid][:14] for rid in body_ids]
        unique14 = {x.hex(" ") for x in first14}
        lines.append(f"  unique first-14 among non-stubs: {len(unique14)}")
        for hex14 in sorted(unique14):
            members = [rid for rid in body_ids if blobs[rid][:14].hex(" ") == hex14]
            lines.append(f"    {hex14}  -> {members}")

    # u16be[0] vs remaining length
    lines += ["", "u16be at 0 vs (len-2) / (len-14):"]
    for rid, data in blobs.items():
        if len(data) < 2:
            continue
        count = struct.unpack(">H", data[:2])[0]
        lines.append(
            f"  {rid}: u16={count}  len={len(data)}  len-2={len(data)-2}  "
            f"len-14={len(data)-14}  u16==len={count == len(data)}  "
            f"u16==(len-2)={count == len(data)-2}  u16==(len-14)={count == len(data)-14}"
        )

    # Level-name hypothesis
    lines += ["", "STR# 2018 level-name hypothesis (scri 128+N == name N):"]
    lines.append(f"  STR#2018 count: {len(names)}")
    lines.append(f"  non-stub scri count: {len(body_ids)}")
    if names:
        for n, name in enumerate(names):
            rid = 128 + n
            raw = name.encode("mac_roman")
            pascal = bytes([len(raw)]) + raw
            if rid not in blobs:
                lines.append(f"  N={n:02d} scri {rid}: MISSING  name={name!r}")
                continue
            data = blobs[rid]
            exact = locate(data, raw)
            pascal_hits = locate(data, pascal)
            # also search every OTHER scri for this name
            others = [i for i in body_ids if i != rid and raw in blobs[i]]
            lines.append(
                f"  N={n:02d} scri {rid} name={name!r}  "
                f"raw_hits={exact}  pascal_hits={pascal_hits}  "
                f"also_in_scri={others}"
            )

    report = Path(args.report)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.write("\n".join(lines) + "\n")
    print(f"wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
