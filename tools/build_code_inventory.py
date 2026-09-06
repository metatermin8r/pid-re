#!/usr/bin/env python3
"""68020 CODE function inventory. Read-only on game data. Instruction reporting only."""
from __future__ import annotations

import argparse
import json
import re
import struct
from collections import defaultdict
from pathlib import Path

from capstone import CS_ARCH_M68K, CS_MODE_M68K_020, Cs
from capstone.m68k import M68K_OP_IMM, M68K_OP_MEM, M68K_OP_REG

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "reference" / "docs" / "code"
OUT_DIR = CODE_DIR / "inventory"

EXPECTED_LEN = {
    0: 2856, 1: 10526, 2: 20968, 3: 25196, 4: 8058, 5: 20560, 6: 9094,
    7: 19128, 8: 5400, 9: 1666, 10: 128, 11: 4944, 12: 2536, 13: 4092,
    14: 1528, 15: 7596, 16: 130,
}
EXPECTED_TRAPS = {
    0: 355, 1: 109, 2: 355, 3: 655, 4: 25, 5: 109, 6: 10, 7: 0, 8: 121,
    9: 49, 10: 5, 11: 15, 12: 5, 13: 42, 14: 0, 15: 6, 16: 5,
}

# A-line names used in this binary (plus common Toolbox/OS). Unknown -> null.
TRAP_NAMES = {
    0xA000: "_Open", 0xA001: "_Close", 0xA002: "_Read", 0xA003: "_Write",
    0xA004: "_Control", 0xA005: "_Status", 0xA006: "_KillIO",
    0xA009: "_GetEOF", 0xA00A: "_SetEOF", 0xA00C: "_GetVol", 0xA00D: "_SetVol",
    0xA011: "_GetFileInfo", 0xA013: "_SetFPos", 0xA014: "_FlushVol",
    0xA01F: "OS_A01F", 0xA023: "OS_A023", 0xA024: "_SetEOF",
    0xA029: "_HLock", 0xA02A: "_HUnlock", 0xA02E: "_BlockMove",
    0xA044: "_SetFPos", 0xA049: "_HPurge", 0xA04A: "_HNoPurge",
    0xA055: "OS_A055", 0xA058: "_HGetState", 0xA059: "_HSetState",
    0xA064: "_MoveHHi",
    0xA11E: "_NewPtr", 0xA11F: "_DisposPtr", 0xA122: "_NewHandle",
    0xA123: "_DisposHandle", 0xA124: "_SetHandleSize", 0xA125: "_GetHandleSize",
    0xA128: "_ReallocHandle", 0xA129: "_HLock", 0xA12A: "_HUnlock",
    0xA146: "_PtrToHand",
    0xA746: "OS_A746", 0xA346: "OS_A346", 0xA1AD: "OS_A1AD",
    0xA3AD: "OS_A3AD",
    0xA808: "_InitGraf", 0xA850: "_InitCursor", 0xA851: "_SetCursor",
    0xA852: "_HideCursor", 0xA853: "_ShowCursor", 0xA85D: "_LocalToGlobal",
    0xA861: "_Random", 0xA86E: "_InitGraf", 0xA86F: "_OpenPort",
    0xA871: "_SetPortBits", 0xA873: "_SetPort", 0xA874: "_GetPort",
    0xA875: "_SetPBits", 0xA877: "_SetOrigin", 0xA878: "_SetOrigin",
    0xA879: "_SetClip", 0xA87B: "_ClipRect", 0xA87C: "_BackPat",
    0xA87D: "_GetClip", 0xA87E: "_SetClip",
    0xA883: "_DrawChar", 0xA884: "_DrawString", 0xA885: "_DrawText",
    0xA886: "_DrawJust", 0xA887: "_TextFont", 0xA888: "_TextFace",
    0xA889: "_TextMode", 0xA88A: "_TextSize", 0xA88B: "_GetFontInfo",
    0xA88C: "_StringWidth", 0xA88D: "_CharWidth", 0xA88E: "_TextWidth",
    0xA891: "_LineTo", 0xA892: "_Line", 0xA893: "_MoveTo", 0xA894: "_Move",
    0xA898: "_GetPenState", 0xA899: "_SetPenState", 0xA89A: "_GetPen",
    0xA89B: "_PenSize", 0xA89C: "_PenMode", 0xA89D: "_PenPat", 0xA89E: "_PenNormal",
    0xA8A1: "_FrameRect", 0xA8A2: "_PaintRect", 0xA8A3: "_EraseRect",
    0xA8A4: "_InvertRect", 0xA8A5: "_FillRect", 0xA8A6: "_EqualRect",
    0xA8A7: "_SetRect", 0xA8A8: "_OffsetRect", 0xA8A9: "_InsetRect",
    0xA8AA: "_SectRect", 0xA8AB: "_UnionRect", 0xA8AC: "_Pt2Rect",
    0xA8AD: "_PtInRect", 0xA8AE: "_EmptyRect",
    0xA8B0: "_FrameRoundRect", 0xA8B4: "_OffsetRgn",
    0xA8C0: "_FrameArc", 0xA8C5: "_FillArc",
    0xA8C9: "_PaintPoly", 0xA8D2: "_CopyRgn", 0xA8D8: "_NewRgn",
    0xA8D9: "_DisposRgn", 0xA8DA: "_OpenRgn", 0xA8DB: "_CloseRgn",
    0xA8DC: "_CopyRgn", 0xA8DE: "_SetEmptyRgn", 0xA8E1: "_OffsetRgn",
    0xA8E8: "_PtInRgn", 0xA8E9: "_RectInRgn",
    0xA8EC: "_CopyBits", 0xA8ED: "_SeedFill", 0xA8EE: "_CalcMask",
    0xA8EF: "_CopyMask", 0xA8F0: "_OpenPicture", 0xA8F1: "_PicComment",
    0xA8F2: "_ClosePicture", 0xA8F3: "_OpenPicture", 0xA8F4: "_ClosePicture",
    0xA8F6: "_DrawPicture", 0xA8F8: "_ScalePt", 0xA8F9: "_MapPt",
    0xA8FA: "_MapRect", 0xA8FB: "_MapRgn",
    0xA8FE: "_InitFonts", 0xA8FF: "_GetFNum",
    0xA909: "_NewWindow", 0xA90A: "_GetNewWindow", 0xA90B: "_DisposeWindow",
    0xA90C: "_GetWMgrPort", 0xA90D: "_ShowHide", 0xA90E: "_HiliteWindow",
    0xA90F: "_GetWRefCon", 0xA910: "_SetWRefCon", 0xA911: "_GetWTitle",
    0xA912: "_InitWindows", 0xA913: "_NewWindow", 0xA914: "_GetNewWindow",
    0xA915: "_ShowWindow", 0xA916: "_HideWindow", 0xA917: "_GetWRefCon",
    0xA918: "_SetWRefCon", 0xA919: "_GetWTitle", 0xA91A: "_DragWindow",
    0xA91B: "_MoveWindow", 0xA91C: "_GrowWindow", 0xA91D: "_SizeWindow",
    0xA91E: "_TrackGoAway", 0xA91F: "_SelectWindow", 0xA920: "_SelectWindow",
    0xA921: "_EndUpdate", 0xA922: "_BeginUpdate", 0xA923: "_EndUpdate",
    0xA924: "_FrontWindow", 0xA925: "_BringToFront", 0xA926: "_SendBehind",
    0xA927: "_GetWVariant", 0xA928: "_InvalRect", 0xA929: "_InvalRgn",
    0xA92A: "_ValidRect", 0xA92B: "_SetWTitle", 0xA92C: "_SelectWindow",
    0xA92D: "_HideWindow", 0xA92E: "_ShowWindow",
    0xA930: "_InitMenus", 0xA931: "_NewMenu", 0xA932: "_DisposeMenu",
    0xA933: "_AppendMenu", 0xA934: "_ClearMenuBar", 0xA935: "_InsertMenu",
    0xA936: "_DeleteMenu", 0xA937: "_DrawMenuBar", 0xA938: "_HiliteMenu",
    0xA939: "_EnableItem", 0xA93A: "_DisableItem", 0xA93B: "_GetMenuBar",
    0xA93C: "_SetMenuBar", 0xA93D: "_MenuSelect", 0xA93E: "_MenuKey",
    0xA941: "_SetItem", 0xA942: "_GetItem", 0xA946: "_GetItem",
    0xA94D: "_AddResMenu", 0xA950: "_InitControls", 0xA951: "_NewControl",
    0xA953: "_DisposeControl", 0xA954: "_KillControls", 0xA955: "_ShowControl",
    0xA956: "_HideControl", 0xA958: "_GetCRefCon", 0xA959: "_SetCRefCon",
    0xA95A: "_SetCtlValue", 0xA95B: "_GetCtlValue", 0xA95C: "_SetMinCtl",
    0xA95D: "_HiliteControl", 0xA960: "_TrackControl", 0xA961: "_DrawControls",
    0xA968: "_FindControl",
    0xA970: "_GetNextEvent", 0xA971: "_EventAvail", 0xA972: "_GetMouse",
    0xA973: "_StillDown", 0xA974: "_Button", 0xA975: "_TickCount",
    0xA976: "_GetKeys", 0xA977: "_WaitNextEvent",
    0xA97B: "_InitDialogs", 0xA97C: "_GetNewDialog", 0xA97D: "_NewDialog",
    0xA980: "_DrawDialog", 0xA982: "_CloseDialog", 0xA983: "_DisposDialog",
    0xA985: "_CouldAlert", 0xA986: "_FreeAlert", 0xA987: "_CouldDialog",
    0xA988: "_FreeDialog", 0xA98B: "_ParamText", 0xA98C: "_ErrorSound",
    0xA98D: "_GetDItem", 0xA98E: "_SetDItem", 0xA98F: "_SetIText",
    0xA990: "_GetIText", 0xA991: "_ModalDialog", 0xA992: "_DetachDialog",
    0xA994: "_IsDialogEvent", 0xA995: "_DialogSelect", 0xA996: "_DrawDialog",
    0xA997: "_OpenResFile", 0xA998: "_UseResFile", 0xA999: "_UpdateResFile",
    0xA99A: "_CloseResFile", 0xA99B: "_SetResLoad", 0xA99C: "_CountResources",
    0xA99D: "_GetIndResource", 0xA99F: "_Count1Resources",
    0xA9A0: "_GetResource", 0xA9A1: "_GetNamedResource", 0xA9A2: "_LoadResource",
    0xA9A3: "_ReleaseResource", 0xA9A4: "_HomeResFile", 0xA9A5: "_SizeRsrc",
    0xA9A6: "_GetResAttrs", 0xA9A7: "_SetResAttrs", 0xA9A8: "_GetResInfo",
    0xA9A9: "_ChangedResource", 0xA9AA: "_AddResource", 0xA9AB: "_AddReference",
    0xA9AD: "_RmveResource", 0xA9AF: "_ResError", 0xA9B0: "_WriteResource",
    0xA9B1: "_CreateResFile", 0xA9B2: "_SystemEvent", 0xA9B3: "_SystemClick",
    0xA9B4: "_SystemTask", 0xA9B5: "_SystemMenu", 0xA9B6: "_OpenDeskAcc",
    0xA9B8: "_GetPattern", 0xA9B9: "_GetCursor", 0xA9BA: "_GetString",
    0xA9BB: "_GetIcon", 0xA9BC: "_GetPicture", 0xA9BD: "_GetNewWindow",
    0xA9BE: "_GetNewControl", 0xA9BF: "_GetRMenu",
    0xA9C0: "_GetNewMBar", 0xA9C1: "_UniqueID", 0xA9C2: "_SystemEdit",
    0xA9C3: "_KeyCrsr", 0xA9C8: "_GetMaxResourceSize",
    0xA9C9: "_ResourceCountChanged", 0xA9CA: "_SetResPurge",
    0xA9CB: "_RsrcMapEntry", 0xA9CC: "_TEInit", 0xA9CD: "_TEDispose",
    0xA9CE: "_TETextBox", 0xA9CF: "_TESetText",
    0xA9E1: "_GetTrapAddress", 0xA9E2: "_SetTrapAddress",
    0xA9E6: "_InitAllPacks", 0xA9E7: "_InitPack",
    0xA9E9: "_Pack2", 0xA9EA: "_Pack3", 0xA9EB: "_FP68K", 0xA9EC: "_Elems68K",
    0xA9ED: "_Pack6", 0xA9EE: "_Pack7", 0xA9EF: "_PtrAndHand",
    0xA9F0: "_LoadSeg", 0xA9F1: "_UnloadSeg", 0xA9F2: "_Launch",
    0xA9F3: "_Chain", 0xA9F4: "_ExitToShell", 0xA9F5: "_GetAppParms",
    0xA9F6: "_GetResFileAttrs", 0xA9F7: "_SetResFileAttrs",
    0xA9FC: "_ZeroScrap", 0xA9FD: "_GetScrap", 0xA9FE: "_PutScrap",
    0xAA2A: "_GetMBarHeight", 0xAA31: "_PinRect", 0xAA45: "_NewCWindow",
    0xAA46: "_GetNewCWindow", 0xAA4A: "_SetWinColor",
    0xAA51: "_RGBForeColor", 0xAA52: "_RGBBackColor",
    0xAA60: "_ProtectEntry", 0xAA62: "_ReserveEntry",
    0xAA95: "_DisposeCTable",
}

M68K_REG_A5 = 14
HEX_ADDR = re.compile(r"\$([0-9A-Fa-f]+)")
IMM_MNEMS = {
    "move", "moveq", "cmpi", "addi", "subi", "andi", "ori",
    "muls", "mulu", "divs", "divu",
}
SHIFT_MNEMS = {"asl", "asr", "lsl", "lsr", "rol", "ror", "roxl", "roxr"}
BRANCH_PREFIXES = (
    "bra", "bcc", "bcs", "beq", "bne", "bge", "bgt", "ble", "blt",
    "bhi", "bls", "bmi", "bpl", "bvc", "bvs", "bhs", "blo",
    "dbra", "dbf", "dbeq", "dbne", "dbge", "dbgt", "dble", "dblt",
    "dbhi", "dbls", "dbmi", "dbpl", "dbvc", "dbvs", "dbcc", "dbcs",
    "dbt",
)


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def i16(b: bytes, o: int) -> int:
    return struct.unpack_from(">h", b, o)[0]


def i32(b: bytes, o: int) -> int:
    return struct.unpack_from(">i", b, o)[0]


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def mnem_base(m: str) -> str:
    return m.split(".", 1)[0]


def mnem_size(m: str) -> str | None:
    if "." in m:
        s = m.rsplit(".", 1)[-1]
        if s in ("b", "w", "l", "s"):
            return "b" if s == "s" else s
    if m == "moveq":
        return "l"
    return None


def expand_reg_list(s: str) -> list[str]:
    out: list[str] = []
    s = s.strip()
    if not s:
        return out
    for part in s.split("/"):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            kind = a[0]
            lo, hi = int(a[1:]), int(b[1:])
            for n in range(lo, hi + 1):
                out.append(f"{kind}{n}")
        else:
            out.append(part)
    return out


class Dec:
    def __init__(self) -> None:
        self.md = Cs(CS_ARCH_M68K, CS_MODE_M68K_020)
        self.md.detail = True

    def one(self, blob: bytes, pc: int) -> dict:
        if pc + 2 > len(blob):
            return {"pc": pc, "size": 0, "raw": b"", "text": "END", "ok": False, "insn": None}
        word = u16(blob, pc)
        if 0xA000 <= word <= 0xAFFF:
            raw = blob[pc : pc + 2]
            return {
                "pc": pc,
                "size": 2,
                "raw": raw,
                "text": f"A-line 0x{word:04X}",
                "ok": True,
                "insn": None,
                "aline": word,
            }
        window = blob[pc : min(len(blob), pc + 12)]
        insns = list(self.md.disasm(window, pc))
        if insns and insns[0].address == pc and insns[0].size >= 2:
            insn = insns[0]
            return {
                "pc": pc,
                "size": insn.size,
                "raw": bytes(insn.bytes),
                "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                "ok": True,
                "insn": insn,
            }
        raw = blob[pc : pc + 2]
        return {
            "pc": pc,
            "size": 2,
            "raw": raw,
            "text": f"UNKNOWN {hx(raw)}",
            "ok": False,
            "insn": None,
        }


def parse_jt(code0: bytes) -> list[dict]:
    entries = []
    for i in range(355):
        off = 16 + i * 8
        routine, magic, seg, trap = struct.unpack_from(">HHHH", code0, off)
        entries.append(
            {
                "i": i,
                "routine": routine,
                "magic": magic,
                "seg": seg,
                "trap": trap,
                "file": 4 + routine,
                "a5": 0x20 + 2 + i * 8,
            }
        )
    return entries


def even_trap_count(blob: bytes, start: int = 0) -> int:
    n = 0
    for o in range(start, len(blob) - 1, 2):
        w = u16(blob, o)
        if 0xA000 <= w <= 0xAFFF:
            n += 1
    return n


def is_link(r: dict) -> bool:
    return r["text"].startswith("link")


def is_unlk(r: dict) -> bool:
    return r["text"].startswith("unlk")


def is_rts(r: dict) -> bool:
    t = r["text"]
    return t == "rts" or t.startswith("rts")


def is_computed_jmp(r: dict) -> bool:
    raw = r["raw"]
    if len(raw) < 2:
        return False
    w = (raw[0] << 8) | raw[1]
    if w in (0x4EFB, 0x4EF3):
        return True
    # JMP (An), JMP (An)+, JMP -(An), JMP (d16,An)
    if 0x4ED0 <= w <= 0x4EDF or 0x4EE8 <= w <= 0x4EEF:
        return True
    return False


def skip_switch_table(blob: bytes, jmp_pc: int, jmp_size: int) -> tuple[int, int] | None:
    """After 4EFB, skip a following word table. Returns (offset, length) or None."""
    raw = blob[jmp_pc : jmp_pc + jmp_size]
    if len(raw) < 2 or ((raw[0] << 8) | raw[1]) != 0x4EFB:
        return None
    table = jmp_pc + jmp_size
    if table + 2 > len(blob):
        return None
    bases = (jmp_pc, jmp_pc + 2, table)
    targets: list[int] = []
    p = table
    for _ in range(256):
        if p + 2 > len(blob):
            break
        w = u16(blob, p)
        if w in (0x4E56, 0x4E75, 0x4E5E):
            break
        sw = i16(blob, p)
        ok = False
        for b in bases:
            t = b + sw
            if table < t < len(blob) and (t - table) < 1024:
                targets.append(t)
                ok = True
        if not ok and targets:
            break
        p += 2
        if targets and p >= min(targets):
            break
    if len(targets) < 2:
        return None
    first = min(t for t in targets if t > table)
    if first <= table or first - table > 512:
        return None
    return table, first - table


def branch_target(r: dict) -> int | None:
    t = r["text"]
    base = mnem_base(t.split()[0] if t else "")
    if base == "bsr":
        return None
    if not (base.startswith("b") or base.startswith("db")):
        return None
    if not any(t.startswith(p) for p in BRANCH_PREFIXES):
        return None
    raw = r["raw"]
    pc = r["pc"]
    if len(raw) >= 2:
        op = (raw[0] << 8) | raw[1]
        # DBcc: 50C8-57CF with low nibble 8-F
        if 0x50C8 <= op <= 0x57CF and (op & 0xF) >= 8 and len(raw) >= 4:
            return pc + 2 + i16(raw, 2)
        hi = raw[0]
        if hi == 0x60 or 0x62 <= hi <= 0x6F:
            if raw[1] == 0x00 and len(raw) >= 4:
                return pc + 2 + i16(raw, 2)
            if raw[1] == 0xFF and len(raw) >= 6:
                return pc + 2 + i32(raw, 2)
            return pc + 2 + struct.unpack(">b", raw[1:2])[0]
    m = HEX_ADDR.search(t)
    if m:
        return int(m.group(1), 16)
    return None


def pcrel_call_target(r: dict) -> tuple[int, int] | None:
    """Return (disp, target) for JSR (d16,PC) / BSR."""
    raw = r["raw"]
    pc = r["pc"]
    t = r["text"]
    if t.startswith("jsr") and len(raw) >= 4 and raw[0] == 0x4E and raw[1] == 0xBA:
        disp = i16(raw, 2)
        return disp, pc + 2 + disp
    if t.startswith("bsr") or (len(raw) >= 2 and raw[0] == 0x61):
        if len(raw) >= 2 and raw[0] == 0x61:
            if raw[1] == 0xFF and len(raw) >= 6:
                disp = i32(raw, 2)
                return disp, pc + 2 + disp
            if raw[1] == 0x00 and len(raw) >= 4:
                disp = i16(raw, 2)
                return disp, pc + 2 + disp
            disp = struct.unpack(">b", raw[1:2])[0]
            return disp, pc + 2 + disp
    return None


def a5_call(r: dict) -> int | None:
    raw = r["raw"]
    t = r["text"]
    if len(raw) >= 4 and raw[0] == 0x4E and raw[1] in (0xAD, 0xED):
        return i16(raw, 2)
    if (t.startswith("jsr") or t.startswith("jmp")) and "(a5)" in t:
        m = HEX_ADDR.search(t)
        if m:
            v = int(m.group(1), 16)
            if v >= 0x8000:
                v -= 0x10000
            return v
    return None


def abs_call_target(r: dict) -> int | None:
    raw = r["raw"]
    t = r["text"]
    if not t.startswith("jsr"):
        return None
    if len(raw) >= 6 and raw[0] == 0x4E and raw[1] == 0xB9:
        return struct.unpack_from(">I", raw, 2)[0]
    if len(raw) >= 4 and raw[0] == 0x4E and raw[1] == 0xB8:
        return u16(raw, 2)
    return None


def resolve_a5(disp: int, jt: list[dict]) -> dict | None:
    if (disp - 0x22) % 8 != 0:
        return None
    entry = (disp - 0x20 - 2) // 8
    if 0 <= entry < len(jt):
        return jt[entry]
    return None


def is_jt_disp(disp: int) -> bool:
    return (disp - 0x22) % 8 == 0 and 0 <= (disp - 0x22) // 8 < 355


def a5_mem_ops(insn) -> list[tuple[int, str]]:
    """List of (disp, role src|dst) for A5 memory operands."""
    if insn is None:
        return []
    out = []
    try:
        ops = list(insn.operands)
    except Exception:
        return []
    n = len(ops)
    for i, op in enumerate(ops):
        if op.type != M68K_OP_MEM:
            continue
        if op.mem.base_reg != M68K_REG_A5:
            continue
        disp = int(op.mem.disp)
        if disp >= 0x8000:
            disp -= 0x10000
        role = "dst" if i == n - 1 and n >= 2 else "src"
        if n == 1:
            role = "src"
        out.append((disp, role))
    return [] if not out else out


def access_rw(text: str, role: str) -> str:
    m = mnem_base(text.split()[0] if text else "")
    if m in ("tst", "cmp", "cmpi", "cmpa", "cmpm", "pea", "lea", "jsr", "jmp"):
        return "r"
    if role == "dst":
        return "w"
    return "r"


def signed_imm(val: int, size: str | None) -> int:
    if size == "b":
        v = val & 0xFF
        return v - 0x100 if v >= 0x80 else v
    if size == "w":
        v = val & 0xFFFF
        return v - 0x10000 if v >= 0x8000 else v
    if size == "l":
        v = val & 0xFFFFFFFF
        return v - 0x100000000 if v >= 0x80000000 else v
    if val > 0x7FFFFFFF:
        return val - 0x100000000
    return val


def is_jmp_an(r: dict) -> bool:
    raw = r["raw"]
    if len(raw) < 2:
        return False
    w = (raw[0] << 8) | raw[1]
    return 0x4ED0 <= w <= 0x4EDF


def is_uncond_xfer(r: dict) -> bool:
    raw = r["raw"]
    if len(raw) < 2:
        return False
    w = (raw[0] << 8) | raw[1]
    if w in (0x4EFB, 0x4EF3):
        return False
    if raw[0] == 0x60:
        return True
    if w in (0x4EF8, 0x4EF9, 0x4EFA):
        return True
    return is_jmp_an(r)


def xfer_target(r: dict) -> int | None:
    raw = r["raw"]
    pc = r["pc"]
    if len(raw) < 2:
        return None
    w = (raw[0] << 8) | raw[1]
    if raw[0] == 0x60:
        if raw[1] == 0x00 and len(raw) >= 4:
            return pc + 2 + i16(raw, 2)
        if raw[1] == 0xFF and len(raw) >= 6:
            return pc + 2 + i32(raw, 2)
        return pc + 2 + struct.unpack(">b", raw[1:2])[0]
    if w == 0x4EF9 and len(raw) >= 6:
        return struct.unpack_from(">I", raw, 2)[0]
    if w == 0x4EF8 and len(raw) >= 4:
        return u16(raw, 2)
    if w == 0x4EFA and len(raw) >= 4:
        return pc + 2 + i16(raw, 2)
    return None


def walk_function(dec: Dec, blob: bytes, start: int, jt_starts: set[int]) -> list[dict]:
    rows: list[dict] = []
    pc = start
    first = dec.one(blob, start)
    depth = 1 if is_link(first) else 0
    had_link = is_link(first)
    next_jt = min((s for s in jt_starts if s > start), default=len(blob))
    limit = 30000
    for _ in range(limit):
        if pc >= len(blob) or pc >= next_jt:
            break
        r = dec.one(blob, pc)
        if r["size"] <= 0:
            break
        # New function, not A2 nesting: LINK after the outer frame closed,
        # or LINK after an unconditional transfer that does not skip over it.
        if pc != start and is_link(r):
            if depth <= 0:
                break
            if rows and is_uncond_xfer(rows[-1]):
                tgt = xfer_target(rows[-1])
                if tgt is None or tgt <= pc:
                    break
        rows.append(r)
        if is_link(r) and pc != start:
            depth += 1
        if is_unlk(r) and depth > 0:
            depth -= 1
        if is_computed_jmp(r) and r["raw"][:2] == b"\x4E\xFB":
            skip = skip_switch_table(blob, r["pc"], r["size"])
            if skip:
                off, ln = skip
                if off + ln > next_jt:
                    ln = max(0, next_jt - off)
                if ln:
                    rows.append(
                        {
                            "pc": off,
                            "size": ln,
                            "raw": blob[off : off + ln],
                            "text": f"TABLE {ln}",
                            "ok": True,
                            "insn": None,
                            "table": True,
                        }
                    )
                pc = off + ln
                continue
        if is_rts(r):
            extra_seen = any(x["pc"] != start and is_link(x) and not x.get("table") for x in rows)
            if not had_link or depth <= 0 or (depth == 1 and not extra_seen):
                break
        # UNLK already closed the frame; JMP (An) is the tail return.
        if is_jmp_an(r) and depth <= 0:
            break
        pc += r["size"]
    return rows


def analyze(
    code_id: int,
    start: int,
    rows: list[dict],
    jt: list[dict],
    jt_at: dict[int, list[dict]],
    extra_links: list[int],
) -> dict:
    insn_rows = [r for r in rows if not r.get("table")]
    if not insn_rows:
        end = start
        length = 0
    else:
        last = insn_rows[-1]
        end = last["pc"] + last["size"] - 1
        length = end - start + 1
    first = insn_rows[0] if insn_rows else None
    frame = None
    if first and is_link(first) and first["insn"] is not None:
        try:
            imm = int(first["insn"].operands[1].imm) & 0xFFFF
            frame = imm - 0x10000 if imm >= 0x8000 else imm
        except Exception:
            if len(first["raw"]) >= 4:
                frame = i16(first["raw"], 2)
    saved: list[str] = []
    for r in insn_rows[:4]:
        if r["text"].startswith("movem") and "-(a7)" in r["text"]:
            left = r["text"].split(",", 1)[0]
            regs = left.split(None, 1)[-1] if " " in left else ""
            saved = expand_reg_list(regs)
            break

    traps = []
    calls_a5 = []
    calls_pcrel = []
    calls_abs = []
    a5g = []
    imms = []
    shifts = []
    branches = []
    loops = []
    computed = []
    table_data = []
    unk = 0
    n_insn = 0

    for r in rows:
        if r.get("table"):
            table_data.append({"offset": r["pc"], "length": r["size"]})
            continue
        n_insn += 1
        if not r["ok"]:
            unk += 1
        if "aline" in r:
            w = r["aline"]
            traps.append({"offset": r["pc"], "word": w, "name_or_null": TRAP_NAMES.get(w)})
        t = r["text"]
        insn = r["insn"]
        raw = r["raw"]

        if is_computed_jmp(r):
            computed.append({"offset": r["pc"], "mnemonic": t.split()[0], "raw_bytes": hx(raw)})

        ad = a5_call(r)
        if ad is not None:
            ent = resolve_a5(ad, jt)
            calls_a5.append(
                {
                    "offset": r["pc"],
                    "displacement": ad,
                    "resolved_entry": None if ent is None else ent["i"],
                    "resolved_code_id": None if ent is None else ent["seg"],
                    "resolved_offset": None if ent is None else ent["file"],
                }
            )

        pt = pcrel_call_target(r)
        if pt is not None:
            disp, tgt = pt
            calls_pcrel.append({"offset": r["pc"], "displacement": disp, "target_offset": tgt})

        at = abs_call_target(r)
        if at is not None:
            calls_abs.append({"offset": r["pc"], "target": at})

        if insn is not None:
            for disp, role in a5_mem_ops(insn):
                if mnem_base(t.split()[0]) in ("jsr", "jmp"):
                    continue
                sz = mnem_size(t.split()[0]) or "l"
                a5g.append(
                    {
                        "offset": r["pc"],
                        "displacement": disp,
                        "access": access_rw(t, role),
                        "size": sz,
                    }
                )
            mb = mnem_base(t.split()[0])
            if mb in IMM_MNEMS or (mb == "move" and "#" in t):
                try:
                    for op in insn.operands:
                        if op.type == M68K_OP_IMM:
                            sz = mnem_size(t.split()[0]) or "l"
                            imms.append(
                                {
                                    "offset": r["pc"],
                                    "value": signed_imm(int(op.imm), sz),
                                    "size": sz,
                                }
                            )
                except Exception:
                    pass
            if mb in SHIFT_MNEMS:
                count: int | str | None = None
                try:
                    ops = list(insn.operands)
                    if ops and ops[0].type == M68K_OP_IMM:
                        count = int(ops[0].imm)
                    elif ops and ops[0].type == M68K_OP_REG:
                        count = f"r{int(ops[0].reg)}"
                    elif "#" in t:
                        m = re.search(r"#\$?([0-9A-Fa-f]+)|#(\d+)", t)
                        if m:
                            count = int(m.group(1) or m.group(2), 16 if m.group(1) else 10)
                    elif len(raw) >= 2:
                        # implicit #1 encoded in op
                        count = 1
                except Exception:
                    count = None
                shifts.append({"offset": r["pc"], "mnemonic": t.split()[0], "count_or_register": count})

        bt = branch_target(r)
        if bt is not None:
            branches.append(
                {
                    "offset": r["pc"],
                    "mnemonic": t.split()[0],
                    "target": bt,
                    "backward": bt < r["pc"],
                }
            )
            if start <= bt <= end and bt < r["pc"]:
                loops.append({"start": bt, "end": r["pc"]})

    jts = jt_at.get((code_id, start), [])
    primary = jts[0] if jts else None
    return {
        "code_id": code_id,
        "start_offset": start,
        "end_offset": end,
        "length_bytes": length,
        "jump_table_entry": None if primary is None else primary["i"],
        "a5_relative_address": None if primary is None else primary["a5"],
        "extra_link_offsets": extra_links,
        "frame_size": frame,
        "saved_registers": saved,
        "instruction_count": n_insn,
        "unknown_count": unk,
        "traps": traps,
        "calls_a5": calls_a5,
        "calls_pcrel": calls_pcrel,
        "calls_absolute": calls_abs,
        "a5_globals": a5g,
        "immediates": imms,
        "shifts": shifts,
        "branches": branches,
        "loops": loops,
        "computed_jumps": computed,
        "table_data": table_data,
    }


def discover_and_decode(dec: Dec, code_id: int, blob: bytes, jt: list[dict]) -> list[dict]:
    jt_here = [e for e in jt if e["seg"] == code_id]
    jt_at: dict[int, list[dict]] = defaultdict(list)
    for e in jt_here:
        jt_at[(code_id, e["file"])].append(e)
        jt_at[e["file"]].append(e)  # type: ignore

    starts: set[int] = set()
    for e in jt_here:
        if 4 <= e["file"] < len(blob):
            starts.add(e["file"])
    if len(blob) >= 6 and u16(blob, 4) == 0x4E56:
        starts.add(4)

    decoded: dict[int, dict] = {}
    covered: list[tuple[int, int]] = []  # inclusive ranges

    def in_covered(pc: int) -> tuple[int, int] | None:
        for a, b in covered:
            if a <= pc <= b:
                return a, b
        return None

    for _pass in range(24):
        added = False
        for st in sorted(starts):
            if st in decoded:
                continue
            cov = in_covered(st)
            if cov is not None and cov[0] != st:
                rec = decoded.get(cov[0])
                jt_files = {e["file"] for e in jt_here}
                if st in jt_files and rec is not None:
                    rec["end_offset"] = st - 1
                    rec["length_bytes"] = rec["end_offset"] - rec["start_offset"] + 1
                    covered[:] = [
                        (a, b) if a != rec["start_offset"] else (a, rec["end_offset"])
                        for a, b in covered
                    ]
                    if st in rec["extra_link_offsets"]:
                        rec["extra_link_offsets"].remove(st)
                    # fall through and decode this JT start as its own function
                else:
                    if rec is not None and st not in rec["extra_link_offsets"]:
                        r0 = dec.one(blob, st)
                        if is_link(r0):
                            rec["extra_link_offsets"].append(st)
                            rec["extra_link_offsets"].sort()
                    continue
            rows = walk_function(dec, blob, st, {e["file"] for e in jt_here})
            extra = [r["pc"] for r in rows if r["pc"] != st and is_link(r) and not r.get("table")]
            rec = analyze(code_id, st, rows, jt, jt_at, extra)
            decoded[st] = rec
            covered.append((rec["start_offset"], rec["end_offset"]))
            added = True
            for c in rec["calls_pcrel"]:
                tgt = c["target_offset"]
                if 4 <= tgt < len(blob) and tgt not in starts:
                    starts.add(tgt)
                    added = True
        # 4E56 on an even offset in a gap is a function start. Mid-gap
        # after string padding is common (00 00 4E 56).
        covered.sort()
        pos = 4
        if pos % 2:
            pos += 1
        while pos + 2 <= len(blob):
            hit = in_covered(pos)
            if hit:
                pos = hit[1] + 1
                if pos % 2:
                    pos += 1
                continue
            if u16(blob, pos) == 0x4E56 and pos not in starts:
                starts.add(pos)
                added = True
            pos += 2
        if not added:
            break

    recs = [decoded[k] for k in sorted(decoded)]
    return recs


def load_codes() -> dict[int, bytes]:
    out = {}
    for i, n in EXPECTED_LEN.items():
        p = CODE_DIR / f"CODE_{i:02d}.bin"
        b = p.read_bytes()
        if len(b) != n:
            raise SystemExit(f"CODE {i} length {len(b)} != {n}")
        out[i] = b
    return out


def fn_key(code_id: int, start: int) -> str:
    return f"{code_id}:{start}"


def covering(recs: list[dict], off: int) -> dict | None:
    for r in recs:
        if r["start_offset"] <= off <= r["end_offset"]:
            return r
    return None


def gaps_for(blob: bytes, recs: list[dict]) -> list[dict]:
    covered = [False] * len(blob)
    for r in recs:
        for i in range(r["start_offset"], r["end_offset"] + 1):
            if 0 <= i < len(blob):
                covered[i] = True
    # header 0-3 is not a gap of interest as "code"
    gaps = []
    i = 4
    while i < len(blob):
        if covered[i]:
            i += 1
            continue
        j = i
        while j < len(blob) and not covered[j]:
            j += 1
        ln = j - i
        if ln > 32:
            gaps.append(
                {
                    "offset": i,
                    "length": ln,
                    "first_32_hex": hx(blob[i : i + min(32, ln)]),
                }
            )
        i = j
    return gaps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma CODE ids, e.g. 8,10,16")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else set()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    codes = load_codes()
    jt = parse_jt(codes[0])
    dec = Dec()

    all_recs: dict[int, list[dict]] = {}
    per_res_meta = {}

    ids = [i for i in range(1, 17) if not only or i in only]
    for cid in ids:
        print(f"DECODE CODE {cid} ({len(codes[cid])} bytes) ...", flush=True)
        recs = discover_and_decode(dec, cid, codes[cid], jt)
        all_recs[cid] = recs
        path = OUT_DIR / f"CODE_{cid:02d}.json"
        path.write_text(json.dumps({"code_id": cid, "functions": recs}, indent=2) + "\n", encoding="utf-8")
        print(f"  functions={len(recs)} wrote {path.name}", flush=True)

    # ---- aggregates ----
    fn_index: dict[tuple[int, int], dict] = {}
    for cid, recs in all_recs.items():
        for r in recs:
            fn_index[(cid, r["start_offset"])] = r

    totals_fn = sum(len(v) for v in all_recs.values())
    totals_jt = sum(1 for recs in all_recs.values() for r in recs if r["jump_table_entry"] is not None)
    totals_int = totals_fn - totals_jt
    totals_insn = sum(r["instruction_count"] for recs in all_recs.values() for r in recs)
    totals_unk = sum(r["unknown_count"] for recs in all_recs.values() for r in recs)
    totals_traps = sum(len(r["traps"]) for recs in all_recs.values() for r in recs)
    a5_res = a5_un = 0
    for recs in all_recs.values():
        for r in recs:
            for c in r["calls_a5"]:
                if c["resolved_entry"] is None:
                    a5_un += 1
                else:
                    a5_res += 1
    totals_computed = sum(len(r["computed_jumps"]) for recs in all_recs.values() for r in recs)

    # A4 JT misses
    jt_misses = []
    for e in jt:
        if e["seg"] == 0 or e["seg"] not in all_recs:
            continue
        starts = {r["start_offset"] for r in all_recs[e["seg"]]}
        extras = {x for r in all_recs[e["seg"]] for x in r["extra_link_offsets"]}
        if e["file"] not in starts:
            jt_misses.append(
                {
                    "entry": e["i"],
                    "seg": e["seg"],
                    "file": e["file"],
                    "a5": e["a5"],
                    "in_extra_link": e["file"] in extras,
                    "inside": None
                    if covering(all_recs[e["seg"]], e["file"]) is None
                    else covering(all_recs[e["seg"]], e["file"])["start_offset"],
                }
            )

    counts = {cid: len(all_recs[cid]) for cid in sorted(all_recs)}
    jt_counts = {
        cid: sum(1 for r in all_recs[cid] if r["jump_table_entry"] is not None)
        for cid in sorted(all_recs)
    }

    # B2 longest
    flat = [r for recs in all_recs.values() for r in recs]
    longest = sorted(flat, key=lambda r: r["length_bytes"], reverse=True)[:30]
    longest_out = [
        {
            "code_id": r["code_id"],
            "start_offset": r["start_offset"],
            "length_bytes": r["length_bytes"],
            "trap_count": len(r["traps"]),
            "call_count": len(r["calls_a5"]) + len(r["calls_pcrel"]) + len(r["calls_absolute"]),
        }
        for r in longest
    ]
    zero_trap_long = [
        {
            "code_id": r["code_id"],
            "start_offset": r["start_offset"],
            "length_bytes": r["length_bytes"],
            "instruction_count": r["instruction_count"],
            "call_count": len(r["calls_a5"]) + len(r["calls_pcrel"]) + len(r["calls_absolute"]),
        }
        for r in sorted(flat, key=lambda r: (-r["length_bytes"], r["code_id"], r["start_offset"]))
        if len(r["traps"]) == 0 and r["length_bytes"] > 100
    ]

    # C1 callgraph
    edges = []
    inbound: dict[str, int] = defaultdict(int)
    for recs in all_recs.values():
        for r in recs:
            src = {"code_id": r["code_id"], "start_offset": r["start_offset"]}
            for c in r["calls_a5"]:
                if c["resolved_entry"] is None:
                    continue
                dst = {"code_id": c["resolved_code_id"], "start_offset": c["resolved_offset"]}
                edges.append({"from": src, "to": dst, "kind": "a5", "call_offset": c["offset"]})
                inbound[fn_key(dst["code_id"], dst["start_offset"])] += 1
            for c in r["calls_pcrel"]:
                tgt = c["target_offset"]
                dst_rec = covering(all_recs.get(r["code_id"], []), tgt)
                if dst_rec is None:
                    continue
                dst = {"code_id": r["code_id"], "start_offset": dst_rec["start_offset"]}
                edges.append({"from": src, "to": dst, "kind": "pcrel", "call_offset": c["offset"]})
                inbound[fn_key(dst["code_id"], dst["start_offset"])] += 1
            for c in r["calls_absolute"]:
                edges.append(
                    {
                        "from": src,
                        "to": {"target": c["target"]},
                        "kind": "absolute",
                        "call_offset": c["offset"],
                    }
                )

    (OUT_DIR / "callgraph.json").write_text(
        json.dumps({"edge_count": len(edges), "edges": edges}, indent=2) + "\n",
        encoding="utf-8",
    )

    # C2 no inbound, no JT
    no_in = []
    for r in flat:
        if r["jump_table_entry"] is not None:
            continue
        if inbound[fn_key(r["code_id"], r["start_offset"])] > 0:
            continue
        seg_has_cjmp = any(x["computed_jumps"] for x in all_recs[r["code_id"]])
        no_in.append(
            {
                "code_id": r["code_id"],
                "start_offset": r["start_offset"],
                "length_bytes": r["length_bytes"],
                "reason": "possibly_computed_jump_or_pointer"
                if seg_has_cjmp
                else "no_resolved_inbound",
            }
        )

    # C3 a5 globals
    gmap: dict[int, list] = defaultdict(list)
    gcount: dict[int, int] = defaultdict(int)
    gfuns: dict[int, set] = defaultdict(set)
    gwrites: dict[int, list] = defaultdict(list)
    for r in flat:
        for g in r["a5_globals"]:
            d = g["displacement"]
            gmap[d].append(
                {
                    "code_id": r["code_id"],
                    "start_offset": r["start_offset"],
                    "insn_offset": g["offset"],
                    "access": g["access"],
                    "size": g["size"],
                }
            )
            gcount[d] += 1
            gfuns[d].add(fn_key(r["code_id"], r["start_offset"]))
            if g["access"] == "w":
                gwrites[d].append(
                    {
                        "code_id": r["code_id"],
                        "start_offset": r["start_offset"],
                        "insn_offset": g["offset"],
                        "size": g["size"],
                    }
                )

    a5_out = {
        str(d): {
            "displacement": d,
            "access_count": gcount[d],
            "function_count": len(gfuns[d]),
            "sites": gmap[d],
        }
        for d in sorted(gmap)
    }
    (OUT_DIR / "a5globals.json").write_text(json.dumps(a5_out, indent=2) + "\n", encoding="utf-8")

    top40 = sorted(gcount.items(), key=lambda kv: (-kv[1], kv[0]))[:40]
    one_write = {
        str(d): w
        for d, w in sorted(gwrites.items())
        if len(w) == 1
    }

    # C5 immediates
    imm_fn: dict[int, set] = defaultdict(set)
    imm_n: dict[int, int] = defaultdict(int)
    for r in flat:
        for im in r["immediates"]:
            v = im["value"]
            imm_n[v] += 1
            imm_fn[v].add(fn_key(r["code_id"], r["start_offset"]))
    hist = [
        {"value": v, "count": imm_n[v], "distinct_functions": len(imm_fn[v])}
        for v in sorted(imm_n, key=lambda x: (-len(imm_fn[x]), -imm_n[x], x))
        if len(imm_fn[v]) >= 3
    ]

    # D1 traps
    trap_scan = {}
    for cid, blob in codes.items():
        if only and cid not in only and cid != 0:
            continue
        ev = even_trap_count(blob, 0)
        ev4 = even_trap_count(blob, 4 if cid else 0)
        in_fn = sum(len(r["traps"]) for r in all_recs.get(cid, []))
        trap_scan[cid] = {
            "even_offset": ev,
            "even_offset_from_4": ev4,
            "in_functions": in_fn,
            "expected": EXPECTED_TRAPS[cid],
            "even_offset_match": ev == EXPECTED_TRAPS[cid],
        }

    # D2 known functions
    known = [
        {"code_id": 5, "start_offset": 4892},
        {"code_id": 8, "start_offset": 2192},
        {"code_id": 8, "start_offset": 2206, "length_bytes": 88, "trap_count": 0, "call_count": 0},
        {"code_id": 5, "start_offset": 1618},
        {"code_id": 5, "start_offset": 1454, "caller_at": [5, 17506]},
        {"code_id": 5, "start_offset": 12052},
        {"code_id": 5, "start_offset": 13440},
        {"code_id": 5, "start_offset": 17190},
        {"code_id": 4, "start_offset": 1028},
        {"code_id": 4, "start_offset": 1362},
        {"code_id": 4, "start_offset": 1466},
        {"code_id": 2, "start_offset": 8546},
        {"code_id": 2, "start_offset": 9262},
        {"code_id": 2, "start_offset": 9788},
        {"code_id": 2, "start_offset": 10066},
        {"code_id": 3, "start_offset": 8762},
    ]
    known_rep = []
    for k in known:
        rec = fn_index.get((k["code_id"], k["start_offset"]))
        item = dict(k)
        item["found"] = rec is not None
        mismatches = []
        if rec is None:
            mismatches.append("missing")
        else:
            if "length_bytes" in k and rec["length_bytes"] != k["length_bytes"]:
                mismatches.append(f"length {rec['length_bytes']} != {k['length_bytes']}")
            if "trap_count" in k and len(rec["traps"]) != k["trap_count"]:
                mismatches.append(f"traps {len(rec['traps'])} != {k['trap_count']}")
            if "call_count" in k:
                cc = len(rec["calls_a5"]) + len(rec["calls_pcrel"]) + len(rec["calls_absolute"])
                if cc != k["call_count"]:
                    mismatches.append(f"calls {cc} != {k['call_count']}")
            if "caller_at" in k:
                cid, off = k["caller_at"]
                callers = all_recs.get(cid, [])
                src = covering(callers, off)
                ok = False
                if src:
                    for c in src["calls_pcrel"]:
                        if c["target_offset"] == k["start_offset"]:
                            ok = True
                if not ok:
                    mismatches.append(f"no pcrel caller at CODE {cid} @{off}")
            item["length_bytes_found"] = rec["length_bytes"]
            item["trap_count_found"] = len(rec["traps"])
            item["jump_table_entry"] = rec["jump_table_entry"]
        item["mismatches"] = mismatches
        known_rep.append(item)

    # D3 coverage
    coverage = {}
    all_gaps = {}
    for cid, recs in all_recs.items():
        blob = codes[cid]
        code_bytes = len(blob) - 4
        covered_n = 0
        seen = [False] * len(blob)
        for r in recs:
            for i in range(r["start_offset"], r["end_offset"] + 1):
                if 4 <= i < len(blob) and not seen[i]:
                    seen[i] = True
                    covered_n += 1
        gs = gaps_for(blob, recs)
        all_gaps[cid] = gs
        coverage[cid] = {
            "resource_bytes": len(blob),
            "code_bytes_from_4": code_bytes,
            "function_bytes": covered_n,
            "percent_of_code_from_4": round(100.0 * covered_n / code_bytes, 3) if code_bytes else 0,
            "gap_over_32_count": len(gs),
        }

    index = {
        "A": {
            "functions_per_resource": counts,
            "jump_table_functions_per_resource": jt_counts,
            "functions_total": totals_fn,
            "jump_table_functions_total": totals_jt,
            "internal_only_total": totals_int,
            "jt_targets_not_function_start": jt_misses,
        },
        "B": {
            "functions": totals_fn,
            "instructions": totals_insn,
            "unknowns": totals_unk,
            "traps_in_functions": totals_traps,
            "a5_calls_resolved": a5_res,
            "a5_calls_unresolved": a5_un,
            "computed_jumps": totals_computed,
            "longest_30": longest_out,
            "zero_traps_length_over_100": zero_trap_long,
        },
        "C": {
            "callgraph_edges": len(edges),
            "no_inbound_no_jt": no_in,
            "a5_globals_distinct": len(gmap),
            "a5_top_40": [
                {
                    "displacement": d,
                    "access_count": gcount[d],
                    "function_count": len(gfuns[d]),
                }
                for d, _ in top40
            ],
            "a5_written_exactly_once_count": len(one_write),
            "a5_written_exactly_once": one_write,
            "immediate_histogram_ge_3_functions": hist,
        },
        "D": {
            "trap_scan": trap_scan,
            "known_functions": known_rep,
            "coverage": coverage,
            "gaps_over_32": all_gaps,
        },
    }
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote index.json functions={totals_fn} insns={totals_insn}", flush=True)


if __name__ == "__main__":
    main()
