# -*- coding: utf-8 -*-
"""Extract Pathways Into Darkness 'snd ' resources to WAV.

Mac Sound Manager format 1 / 2 (Inside Macintosh: Sound). Writes
reference/sounds/snd_<id>.wav and a format report.
"""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mac_containers import resources_of_type  # noqa: E402

SOUNDS = ROOT / "data/hfs/Pathways_1995/Sounds.rsrc"
OUT = ROOT / "reference/sounds"
REPORT = ROOT / "reference/docs/sounds.txt"

# Sound Manager
SAMPLED_SYNTH = 5
BUFFER_CMD = 80
SOUND_CMD = 81
STD_SH = 0x00
EXT_SH = 0xFF
CMP_SH = 0xFE


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _fixed_hz(raw: int) -> float:
    return raw / 65536.0


def _pcm_from_header(data: bytes, off: int) -> dict:
    if off + 22 > len(data):
        raise ValueError(f"sound header truncated at {off}")
    sample_ptr = _u32(data, off)
    encode = data[off + 20]
    if encode == EXT_SH:
        if off + 64 > len(data):
            raise ValueError("extSH truncated")
        channels = _u32(data, off + 4)
        rate = _fixed_hz(_u32(data, off + 8))
        num_frames = _u32(data, off + 22)
        sample_size = _u16(data, off + 48)
        payload = data[off + 64 :]
        width = max(1, sample_size // 8)
        need = num_frames * max(1, channels) * width
        samples = payload[:need] if need else payload
        return {
            "encode": "extSH",
            "sample_ptr": sample_ptr,
            "channels": channels or 1,
            "sample_rate": rate,
            "sample_size": sample_size or 8,
            "frames": num_frames,
            "samples": samples,
        }
    if encode == CMP_SH:
        return {
            "encode": "cmpSH",
            "sample_ptr": sample_ptr,
            "channels": _u32(data, off + 4) if off + 8 <= len(data) else 1,
            "sample_rate": _fixed_hz(_u32(data, off + 8)) if off + 12 <= len(data) else 0.0,
            "sample_size": 8,
            "frames": 0,
            "samples": b"",
            "error": "compressed SoundHeader (MACE/IMA) not converted",
        }
    # stdSH
    length = _u32(data, off + 4)
    rate = _fixed_hz(_u32(data, off + 8))
    payload = data[off + 22 :]
    samples = payload[:length] if length <= len(payload) else payload
    return {
        "encode": "stdSH",
        "sample_ptr": sample_ptr,
        "channels": 1,
        "sample_rate": rate,
        "sample_size": 8,
        "frames": len(samples),
        "samples": samples,
    }


def parse_snd(data: bytes) -> dict:
    if len(data) < 6:
        raise ValueError(f"resource too small ({len(data)})")
    fmt = _u16(data, 0)
    if fmt == 1:
        n_synth = _u16(data, 2)
        pos = 4
        synths = []
        for _ in range(n_synth):
            if pos + 6 > len(data):
                raise ValueError("synth list truncated")
            synths.append((_u16(data, pos), _u32(data, pos + 2)))
            pos += 6
        n_cmd = _u16(data, pos)
        pos += 2
    elif fmt == 2:
        synths = []
        _ref = _u16(data, 2)
        n_cmd = _u16(data, 4)
        pos = 6
    else:
        raise ValueError(f"not a standard snd format (got {fmt})")

    header = None
    commands = []
    for _ in range(n_cmd):
        if pos + 8 > len(data):
            raise ValueError("command list truncated")
        raw_cmd = _u16(data, pos)
        param1 = struct.unpack_from(">h", data, pos + 2)[0]
        param2 = _u32(data, pos + 4)
        pos += 8
        offset_follows = bool(raw_cmd & 0x8000)
        cmd = raw_cmd & 0x7FFF
        commands.append((cmd, param1, param2, offset_follows))
        if cmd in (BUFFER_CMD, SOUND_CMD):
            hoff = param2 if offset_follows else (pos if param2 == 0 else param2)
            if 0 <= hoff < len(data):
                header = _pcm_from_header(data, hoff)

    if header is None:
        # last-ditch: scan for a plausible stdSH after the command table
        raise ValueError("no bufferCmd/soundCmd sample header")

    return {
        "format": fmt,
        "synths": synths,
        "commands": commands,
        **header,
    }


def _to_wav_frames(info: dict) -> bytes:
    samples = info["samples"]
    bits = info["sample_size"]
    if bits <= 8:
        return samples
    if bits == 16:
        # Mac snd 16-bit is big-endian signed
        n = len(samples) // 2
        be = struct.unpack(f">{n}h", samples[: n * 2])
        return struct.pack(f"<{n}h", *be)
    raise ValueError(f"unsupported sample_size {bits}")


def write_wav(path: Path, info: dict) -> float:
    frames = _to_wav_frames(info)
    rate = int(round(info["sample_rate"])) or 22254
    ch = int(info["channels"] or 1)
    sampwidth = 1 if info["sample_size"] <= 8 else 2
    nframes = len(frames) // (ch * sampwidth)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(frames)
    return nframes / float(rate) if rate else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    blobs = resources_of_type(SOUNDS, b"snd ")
    lines = [
        f"source: {SOUNDS}",
        f"count: {len(blobs)}",
        "",
        f"{'id':>6} {'fmt':>4} {'encode':<7} {'Hz':>8} {'bits':>4} "
        f"{'ch':>2} {'bytes':>7} {'sec':>7} note",
    ]
    ok = fail = 0
    for rid in sorted(blobs):
        raw = blobs[rid]
        note = ""
        try:
            info = parse_snd(raw)
            if info.get("error"):
                fail += 1
                note = info["error"]
                lines.append(
                    f"{rid:6d} {info['format']:4d} {info['encode']:<7} "
                    f"{info['sample_rate']:8.1f} {info['sample_size']:4d} "
                    f"{info['channels']:2d} {len(raw):7d} {'—':>7} {note}"
                )
                print(f"FAIL {rid}: {note}")
                continue
            dest = OUT / f"snd_{rid}.wav"
            dur = write_wav(dest, info)
            ok += 1
            lines.append(
                f"{rid:6d} {info['format']:4d} {info['encode']:<7} "
                f"{info['sample_rate']:8.1f} {info['sample_size']:4d} "
                f"{info['channels']:2d} {len(raw):7d} {dur:7.3f}"
            )
            print(f"wrote {dest.name}  {info['sample_rate']:.1f} Hz  {dur:.3f}s")
        except Exception as exc:
            fail += 1
            lines.append(
                f"{rid:6d} {'?':>4} {'?':<7} {'?':>8} {'?':>4} "
                f"{'?':>2} {len(raw):7d} {'—':>7} {exc}"
            )
            print(f"FAIL {rid}: {exc}")
    lines.append("")
    lines.append(f"converted={ok}  failed={fail}  total={len(blobs)}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")
    print(f"converted={ok} failed={fail}")


if __name__ == "__main__":
    main()
