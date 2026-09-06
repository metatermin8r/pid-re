# -*- coding: utf-8 -*-
"""Desktop window for Pathways Into Darkness 2.0 save editing.

Uses the same validation and write path as tools/save_editor.py.
Never overwrites the file that was opened.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import save_editor as se

def item_name(item_id: int) -> str:
    if item_id == 0xFFFF:
        return "(end)"
    try:
        return se.item_name(item_id)
    except Exception:
        return f"id:{item_id}"

WARN_UNVERIFIED = (
    "Output is unverified until loaded in Infinite Mac. "
    "No checksum is computed; whether saves carry one is unknown."
)

WARN_CONFIRMED = (
    "Current HP and max HP are confirmed to take effect in the game. "
    "Live position is +0x074A / +0x074E (10-bit fixed X/Y), not a clock. "
    "+0x090C Level, +0x0918 X, +0x091A Y, and +0x091C facing are INERT "
    "(confirmed in game: writing them does nothing). "
    "0x06C2 is a sink written FROM -$1AD8, not a block-index authority."
)


def parse_int(label: str, raw: str) -> int:
    text = raw.strip()
    if not text:
        raise se.EditRefused(f"{label} is empty")
    try:
        return int(text, 10)
    except ValueError as exc:
        raise se.EditRefused(f"{label} is not an integer: {raw!r}") from exc


class SaveEditorApp:
    def __init__(self, root: tk.Tk, levels: se.LevelIndex) -> None:
        self.root = root
        self.levels = levels
        self.path: Path | None = None
        self.data: bytes | None = None
        self.live: list[dict] = []
        self.names: list[tuple[int, str]] = []
        self.inventory: list[tuple[int, int, int, int]] = []
        self.qty_edits: dict[int, int] = {}
        self._filling = False

        root.title("PID Save Editor")
        root.minsize(960, 780)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self._build()
        try:
            se.load_item_catalog()
        except Exception as exc:
            self._set_status(f"Item catalog failed to load: {exc}")
        else:
            self._set_status("Open a Pathways Into Darkness 2.0 Saved Games file.")

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=8)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(3, weight=2)
        main.rowconfigure(4, weight=1)
        main.rowconfigure(5, weight=0)

        top = ttk.Frame(main)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        top.columnconfigure(1, weight=1)
        ttk.Button(top, text="Open…", command=self.open_file).grid(row=0, column=0)
        self.path_var = tk.StringVar(value="(no file)")
        ttk.Label(top, textvariable=self.path_var).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(top, text="Export As…", command=self.export_file).grid(row=0, column=2)

        warn = ttk.Label(
            main,
            text=WARN_CONFIRMED,
            wraplength=920,
            foreground="#8a0000",
            font=("Segoe UI", 9, "bold"),
        )
        warn.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)

        meta = ttk.LabelFrame(main, text="Live player slots in this file", padding=8)
        meta.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        meta.columnconfigure(0, weight=1)
        slot_cols = ("base", "name", "level", "xy", "sector", "hp", "xy_live")
        self.slot_tree = ttk.Treeview(
            meta, columns=slot_cols, show="headings", height=4, selectmode="browse"
        )
        slot_head = {
            "base": ("Base offset", 110),
            "name": ("Name", 140),
            "level": ("Level +0x090C INERT", 220),
            "xy": ("(x,y)", 70),
            "sector": ("Sector", 120),
            "hp": ("HP", 80),
            "xy_live": ("Live X/Y +0x074A/+0x074E", 180),
        }
        for key, (title, width) in slot_head.items():
            self.slot_tree.heading(key, text=title)
            self.slot_tree.column(key, width=width, stretch=(key in ("name", "level")), anchor="w")
        slot_scroll = ttk.Scrollbar(meta, orient="vertical", command=self.slot_tree.yview)
        self.slot_tree.configure(yscrollcommand=slot_scroll.set)
        self.slot_tree.grid(row=0, column=0, sticky="ew")
        slot_scroll.grid(row=0, column=1, sticky="ns")
        self.slot_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_slot_tree())
        ttk.Label(meta, text="Editing slot").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.slot_var = tk.StringVar()
        self.slot_combo = ttk.Combobox(
            meta, textvariable=self.slot_var, state="disabled", width=70
        )
        self.slot_combo.grid(row=2, column=0, sticky="ew", padx=0, pady=(2, 0))
        self.slot_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_slot())
        self.gates_var = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self.gates_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.unknown_var = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self.unknown_var, foreground="#555").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )

        player = ttk.LabelFrame(main, text="Player", padding=8)
        player.grid(row=3, column=0, sticky="nsew", **pad)
        for i in range(2):
            player.columnconfigure(i, weight=1)

        self.hp = self._entry(player, "Current HP", 0)
        self.maxhp = self._entry(player, "Max HP", 1)
        self.overheal = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            player,
            text="Allow overheal (cur > max is UNTESTED in-game)",
            variable=self.overheal,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.live_xy_var = tk.StringVar(value="live X/Y +0x074A/+0x074E: —")
        ttk.Label(player, textvariable=self.live_xy_var, foreground="#555").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        self.facing = self._entry(player, "Facing (u16 at +0x091C)", 5)
        self.facing_note = tk.StringVar(value="width UNKNOWN; observed values live in +0x091D")
        ttk.Label(player, textvariable=self.facing_note, foreground="#555").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Separator(player).grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(
            player,
            text="Position (+0x090C / +0x0918 / +0x091A INERT — confirmed in game)",
        ).grid(row=8, column=0, columnspan=2, sticky="w")

        ttk.Label(player, text="Level +0x090C INERT").grid(row=9, column=0, sticky="w", pady=2)
        self.level_var = tk.StringVar()
        self.level_combo = ttk.Combobox(
            player, textvariable=self.level_var, state="disabled", width=36
        )
        self.level_combo.grid(row=9, column=1, sticky="ew", pady=2)
        self.level_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_sector())
        self.level_combo.bind("<KeyRelease>", lambda _e: self._refresh_sector())

        self.x = self._entry(player, "X +0x0918 INERT (0–31)", 10)
        self.y = self._entry(player, "Y +0x091A INERT (0–31)", 11)
        self.x.bind("<KeyRelease>", lambda _e: self._refresh_sector())
        self.y.bind("<KeyRelease>", lambda _e: self._refresh_sector())

        self.sector_var = tk.StringVar(value="sector: —")
        ttk.Label(player, textvariable=self.sector_var).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(4, 4)
        )
        ttk.Button(
            player, text="Jump to first standable arrival on this level", command=self.use_arrival
        ).grid(row=13, column=0, columnspan=2, sticky="w")

        inv = ttk.LabelFrame(
            main,
            text="Inventory tree (word 2 is overloaded: rounds / child / charge)",
            padding=8,
        )
        inv.grid(row=3, column=1, sticky="nsew", **pad)
        inv.columnconfigure(0, weight=1)
        inv.rowconfigure(0, weight=1)

        cols = ("slot", "name", "id", "state", "value", "next_sibling", "kg")
        self.tree = ttk.Treeview(
            inv, columns=cols, show="tree headings", height=16, selectmode="browse"
        )
        headings = {
            "slot": ("Slot", 44),
            "name": ("Name", 150),
            "id": ("ID", 40),
            "state": ("State", 48),
            "value": ("Word 2", 140),
            "next_sibling": ("Sibling", 60),
            "kg": ("kg", 50),
        }
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=20, stretch=False)
        for key, (title, width) in headings.items():
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=(key in ("name", "value")), anchor="w")
        scroll = ttk.Scrollbar(inv, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_inv_select())
        self.weight_var = tk.StringVar(value="")
        ttk.Label(inv, textvariable=self.weight_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        qty_row = ttk.Frame(inv)
        qty_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(qty_row, text="Selected word 2").pack(side="left")
        self.qty_var = tk.StringVar()
        self.qty_entry = ttk.Entry(qty_row, textvariable=self.qty_var, width=10)
        self.qty_entry.pack(side="left", padx=6)
        ttk.Button(qty_row, text="Set value", command=self.apply_qty).pack(side="left")

        give_row = ttk.Frame(inv)
        give_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(give_row, text="Give id").pack(side="left")
        self.give_id = tk.StringVar()
        ttk.Entry(give_row, textvariable=self.give_id, width=6).pack(side="left", padx=4)
        ttk.Label(give_row, text="into slot").pack(side="left")
        self.give_into = tk.StringVar()
        ttk.Entry(give_row, textvariable=self.give_into, width=6).pack(side="left", padx=4)
        ttk.Label(give_row, text="count").pack(side="left")
        self.give_count = tk.StringVar()
        ttk.Entry(give_row, textvariable=self.give_count, width=6).pack(side="left", padx=4)
        ttk.Button(give_row, text="Give…", command=self.do_give).pack(side="left", padx=6)
        ttk.Button(give_row, text="Equip selected…", command=self.do_equip).pack(side="left")

        log_frame = ttk.LabelFrame(main, text="Tool output (full stdout / stderr)", padding=6)
        log_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", **pad)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        world_bar = ttk.Frame(log_frame)
        world_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(world_bar, text="World home block 0–24").pack(side="left")
        self.world_level_var = tk.StringVar(value="0")
        self.world_level = ttk.Spinbox(
            world_bar,
            from_=0,
            to=24,
            textvariable=self.world_level_var,
            width=4,
            state="disabled",
        )
        self.world_level.pack(side="left", padx=6)
        self.fixed_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            world_bar,
            text="--fixed (raw, /1024, sector=raw>>10)",
            variable=self.fixed_var,
        ).pack(side="left", padx=6)
        self.centred_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            world_bar,
            text="--centred (raw-$200)>>10 compare only",
            variable=self.centred_var,
        ).pack(side="left", padx=6)
        self.io_word_var = tk.StringVar(value="0x06C2 = — (block-index authority, UNTESTED)")
        ttk.Label(world_bar, textvariable=self.io_word_var, foreground="#8a0000").pack(
            side="left", padx=8
        )
        ttk.Button(world_bar, text="World dump", command=self.dump_world).pack(
            side="left", padx=4
        )
        ttk.Button(
            world_bar, text="Objects xref", command=self.dump_objects
        ).pack(side="left", padx=4)
        ttk.Label(
            world_bar,
            text="Prints the 9,112-byte block and Sector.item cross-check.",
            foreground="#555",
        ).pack(side="left", padx=8)

        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.grid(row=1, column=0, sticky="nsew")
        log_scroll.grid(row=1, column=1, sticky="ns")

        bottom = ttk.Frame(main)
        bottom.grid(row=5, column=0, columnspan=2, sticky="ew", **pad)
        bottom.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status_var, wraplength=920).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(bottom, text=WARN_UNVERIFIED, wraplength=920, foreground="#555").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )

        self.root.bind("<Control-o>", lambda _e: self.open_file())
        self.root.bind("<Control-s>", lambda _e: self.export_file())

    def _entry(self, parent: ttk.LabelFrame, label: str, row: int) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=16)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        entry._var = var  # type: ignore[attr-defined]
        return entry

    def _val(self, entry: ttk.Entry) -> str:
        return entry._var.get()  # type: ignore[attr-defined]

    def _set(self, entry: ttk.Entry, value: object) -> None:
        entry._var.set(str(value))  # type: ignore[attr-defined]

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _append_log(self, text: str) -> None:
        if not text:
            return
        if not text.endswith("\n"):
            text = text + "\n"
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _capture_io(self, fn):
        stdout = io.StringIO()
        stderr = io.StringIO()
        result = None
        err: BaseException | None = None
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = fn()
        except BaseException as exc:
            err = exc
        captured = stdout.getvalue()
        err_text = stderr.getvalue()
        if captured:
            self._append_log(captured)
        if err_text:
            self._append_log(err_text)
        if err is not None:
            raise err
        return result

    def _current(self) -> dict | None:
        if not self.live:
            return None
        idx = self.slot_combo.current()
        if idx < 0 or idx >= len(self.live):
            return self.live[0]
        return self.live[idx]

    def open_file(self, path: Path | None = None) -> None:
        if path is None:
            initial = se.ROOT / "reference" / "saves"
            if not initial.is_dir():
                initial = Path.home()
            picked = filedialog.askopenfilename(
                title="Open PID 2.0 Saved Games",
                initialdir=str(initial),
            )
            if not picked:
                return
            path = Path(picked)
        self.load_path(path)

    def load_path(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Open failed", str(exc))
            return
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            scan = se.scan_bases(data, self.levels)
        finally:
            self.root.config(cursor="")

        live = [d for d in scan["all6"] if not se.in_world_region(d["base"])]
        if not live:
            messagebox.showerror(
                "Not a usable 2.0 save",
                "No player record outside the world-state region passed all six gates.\n"
                "This editor only accepts Pathways Into Darkness 2.0 Saved Games "
                "(not version 1.1 or demo saves).",
            )
            return

        self.path = path
        self.data = data
        if len(data) > se.IO_FILE_OFF + 1:
            io_word = se.u16(data, se.IO_FILE_OFF)
            self.io_word_var.set(
                f"0x06C2 = {io_word} (block-index authority, UNTESTED)"
            )
        self.live = [se.enrich(d, self.levels) for d in live]
        self.names = se.list_save_names(data)
        self.path_var.set(f"{path}  ({len(data)} bytes, {len(self.live)} live slot(s))")
        labels = []
        for d in self.live:
            name = self._name_for_base(d["base"])
            labels.append(
                f"B={d['base']}  {name}  L{d['level']} {d.get('level_name') or ''} "
                f"({d['x']},{d['y']})  HP {d['hp']}/{d['max_hp']}"
            )
        self.slot_combo.configure(values=labels, state="readonly")
        self.slot_combo.current(0)
        self.level_combo.configure(
            values=[f"{i}  {self.levels.names[i]}" for i in range(se.N_LEVELS)],
            state="readonly",
        )
        self._fill_slot_tree()
        self._fill_from_current()
        self._append_log(
            f"loaded {path} bytes={len(data)} live_slots={len(self.live)}\n"
            + "\n".join(labels)
        )
        self._set_status(f"Loaded {path.name}. Choose a slot, edit, then Export As…")

    def _fill_slot_tree(self) -> None:
        for iid in self.slot_tree.get_children():
            self.slot_tree.delete(iid)
        if self.data is None:
            return
        for i, d in enumerate(self.live):
            name = self._name_for_base(d["base"])
            lv = d["level"]
            lname = d.get("level_name") or self.levels.names[lv]
            st, sn = self.levels.sector(lv, d["x"], d["y"])
            self.slot_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    f"{d['base']} (0x{d['base']:X})",
                    name,
                    f"L{lv} {lname}",
                    f"({d['x']},{d['y']})",
                    f"{st} {sn}",
                    f"{d['hp']}/{d['max_hp']}",
                    f"({d.get('x_live')},{d.get('y_live')}) raw={d.get('x_fp')},{d.get('y_fp')}",
                ),
            )
        if self.live:
            self.slot_tree.selection_set("0")
            self.slot_tree.see("0")

    def _name_for_base(self, base: int) -> str:
        if base % se.PLAYER_STRIDE == 0:
            k = base // se.PLAYER_STRIDE
            off = k * se.NAME_SLOT
            for n_off, name in self.names:
                if n_off == off:
                    return repr(name)
        return "(unnamed)"

    def _on_slot(self) -> None:
        if self._filling:
            return
        idx = self.slot_combo.current()
        if 0 <= idx < len(self.live):
            self._filling = True
            try:
                self.slot_tree.selection_set(str(idx))
                self.slot_tree.see(str(idx))
            finally:
                self._filling = False
        self._fill_from_current()

    def _on_slot_tree(self) -> None:
        if self._filling:
            return
        sel = self.slot_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx != self.slot_combo.current():
            self.slot_combo.current(idx)
            self._fill_from_current()

    def _fill_from_current(self) -> None:
        decoded = self._current()
        if decoded is None or self.data is None:
            return
        self._filling = True
        try:
            self.qty_edits.clear()
            flags, _ = se.gate_flags(self.data, decoded["base"], self.levels)
            names = ("G1 level", "G2 X", "G3 Y", "G4 standable", "G5 HP", "G6 live XY")
            self.gates_var.set(
                "  ".join(
                    f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in zip(names, flags)
                )
            )
            self.unknown_var.set(
                f"u16@+0x0752={decoded['u752']}  "
                f"(+0x0750 is the low 16 bits of live Y; not a separate field)"
            )
            self._set(self.hp, decoded["hp"])
            self._set(self.maxhp, decoded["max_hp"])
            self.live_xy_var.set(
                f"live X/Y +0x074A/+0x074E: raw {decoded.get('x_fp')} / {decoded.get('y_fp')}  "
                f">>10 = ({decoded.get('x_live')},{decoded.get('y_live')}). "
                f"Use set-position to write these; this window does not."
            )
            self._set(self.facing, decoded["facing"])
            b091d = self.data[decoded["base"] + se.OFF_FACING + 1]
            self.facing_note.set(
                f"width UNKNOWN; +0x091D byte is {b091d} (0x{b091d:02X}). "
                f"Export writes a u16be at +0x091C."
            )
            lv = decoded["level"]
            self.level_var.set(f"{lv}  {self.levels.names[lv]}")
            self._set(self.x, decoded["x"])
            self._set(self.y, decoded["y"])
            self.world_level.configure(state="normal")
            self.world_level_var.set(str(decoded["level"]))
            self._refresh_sector()
            self._fill_inventory(decoded)
        finally:
            self._filling = False

    def _fill_inventory(self, decoded: dict) -> None:
        assert self.data is not None
        try:
            se.load_item_catalog()
        except Exception as exc:
            self.weight_var.set(f"catalog load failed: {exc}")
        self.inventory = se.read_inventory(self.data, decoded["base"])
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        recs = self.inventory
        head = se.u16(self.data, decoded["base"] + se.OFF_INV_HEAD)
        child_slots: set[int] = set()
        for i, rec in enumerate(recs):
            e = se.catalog_entry(rec[0])
            if e and e["w6"] > 0:
                child_slots.update(se.children_of(recs, i))
        start = head if head != 0xFFFF and head < len(recs) else 0
        roots = se.sibling_chain(recs, start) if recs else []
        seen: set[int] = set()

        def insert_node(slot: int, parent: str) -> None:
            if slot < 0 or slot >= len(recs) or slot in seen:
                return
            seen.add(slot)
            rec = recs[slot]
            value = self.qty_edits.get(slot, rec[2])
            e = se.catalog_entry(rec[0])
            kg = f"{(e['w3'] / 28.0):.2f}" if e else ""
            sib = "FFFF" if rec[3] == 0xFFFF else str(rec[3])
            self.tree.insert(
                parent,
                "end",
                iid=str(slot),
                values=(
                    slot,
                    item_name(rec[0]),
                    rec[0],
                    rec[1],
                    se.interpret_word2(rec[0], value),
                    sib,
                    kg,
                ),
            )
            if e and e["w6"] > 0:
                for child in se.children_of(recs, slot):
                    insert_node(child, str(slot))

        for slot in roots:
            insert_node(slot, "")
        for i in range(len(recs)):
            if i not in seen:
                insert_node(i, "")
        for iid in self.tree.get_children(""):
            self.tree.item(iid, open=True)
            for child in self.tree.get_children(iid):
                self.tree.item(child, open=True)
        sum_w3 = sum((se.catalog_entry(r[0]) or {"w3": 0})["w3"] for r in recs)
        self.weight_var.set(
            f"n={len(recs)} head={head}  sum(w3)={sum_w3} / 28 = {sum_w3 / 28.0:.2f} kg"
        )
        self.qty_var.set("")

    def _refresh_sector(self) -> None:
        if self._filling:
            return
        try:
            level = parse_int("level", self.level_var.get().split()[0])
            x = parse_int("x", self._val(self.x))
            y = parse_int("y", self._val(self.y))
        except (se.EditRefused, IndexError):
            self.sector_var.set("sector: —")
            return
        if not (0 <= level <= 24 and 0 <= x <= 31 and 0 <= y <= 31):
            self.sector_var.set("sector: out of range")
            return
        st, sn = self.levels.sector(level, x, y)
        stand = "standable" if st not in (0, 7) else "NOT standable"
        self.sector_var.set(f"sector: type {st} {sn} — {stand}")

    def use_arrival(self) -> None:
        try:
            level = parse_int("level", self.level_var.get().split()[0])
        except (se.EditRefused, IndexError):
            messagebox.showerror("Arrival", "Select a level first.")
            return
        if not (0 <= level <= 24):
            messagebox.showerror("Arrival", f"level {level} not in 0..24")
            return
        try:
            chosen = self._capture_io(
                lambda: se.select_standable_arrival(self.levels, level, None)
            )
        except SystemExit as exc:
            msg = str(exc.code) if isinstance(exc.code, str) else str(exc)
            if msg.startswith("error: "):
                msg = msg[7:]
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Arrival refused", msg)
            return
        self._set(self.x, int(chosen["x"]))
        self._set(self.y, int(chosen["y"]))
        self._refresh_sector()
        self._set_status(
            f"Arrival L{level} ({chosen['x']},{chosen['y']}) "
            f"from_level={chosen.get('from_level')} "
            f"{chosen.get('from_name')!r} {chosen.get('change_type_name')}"
        )

    def _on_inv_select(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        slot = int(sel[0])
        rec = self.inventory[slot]
        if rec[0] == 0xFFFF:
            self.qty_var.set("")
            return
        self.qty_var.set(str(self.qty_edits.get(slot, rec[2])))

    def apply_qty(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Inventory", "Select a row first.")
            return
        slot = int(sel[0])
        rec = self.inventory[slot]
        if rec[0] == 0xFFFF:
            messagebox.showerror("Inventory", "Cannot edit the FFFF terminator.")
            return
        try:
            qty = parse_int("qty", self.qty_var.get())
            if qty < 0 or qty > 0xFFFF:
                raise se.EditRefused(f"qty={qty} does not fit u16be (0..65535)")
        except se.EditRefused as exc:
            messagebox.showerror("Inventory", str(exc))
            return
        if qty == rec[2]:
            self.qty_edits.pop(slot, None)
        else:
            self.qty_edits[slot] = qty
        values = list(self.tree.item(sel[0], "values"))
        values[4] = se.interpret_word2(rec[0], qty)
        self.tree.item(sel[0], values=values)
        self._set_status(f"Queued inv[{slot}] value {rec[2]} → {qty} (written on Export As…)")

    def _pick_output(self, title: str) -> Path | None:
        if self.path is None:
            return None
        suggested = self.path.parent / (self.path.name + ".edited")
        picked = filedialog.asksaveasfilename(
            title=title,
            initialdir=str(self.path.parent),
            initialfile=suggested.name,
        )
        if not picked:
            self._append_log("REFUSED export cancelled (no output path)")
            return None
        out_path = Path(picked)
        try:
            se.refuse_in_place(self.path, out_path)
        except SystemExit as exc:
            msg = str(exc).removeprefix("error: ")
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Export refused", msg)
            return None
        return out_path

    def do_give(self) -> None:
        if self.path is None or self.data is None:
            messagebox.showinfo("Give", "Open a save file first.")
            return
        decoded = self._current()
        if decoded is None:
            return
        try:
            item_id = parse_int("id", self.give_id.get())
            into_raw = self.give_into.get().strip()
            into = parse_int("into", into_raw) if into_raw else None
            count_raw = self.give_count.get().strip()
            count = parse_int("count", count_raw) if count_raw else None
        except se.EditRefused as exc:
            messagebox.showerror("Give", str(exc))
            return
        out_path = self._pick_output("Give: write a new save (will not overwrite the opened file)")
        if out_path is None:
            return

        def _do():
            buf, changes, expect, warnings = se.apply_give(
                self.data, decoded, item_id, into=into, count=count
            )
            for w in warnings:
                print(f"WARNING: {w}")
            se.commit_output(
                out_path, self.data, buf, [decoded], self.levels, changes, expect=expect or None
            )
            return changes

        try:
            changes = self._capture_io(_do)
        except se.EditRefused as exc:
            self._append_log(f"REFUSED {exc}")
            messagebox.showerror("Give refused", str(exc))
            return
        except SystemExit as exc:
            msg = str(exc.code) if isinstance(exc.code, str) else str(exc)
            msg = msg.removeprefix("error: ")
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Give refused", msg)
            return
        self._append_log(f"WROTE {out_path}")
        self._set_status(f"WROTE {out_path}  give changes={len(changes)}")

    def do_equip(self) -> None:
        if self.path is None or self.data is None:
            messagebox.showinfo("Equip", "Open a save file first.")
            return
        decoded = self._current()
        if decoded is None:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Equip", "Select an inventory row first.")
            return
        slot = int(sel[0])
        out_path = self._pick_output("Equip: write a new save (will not overwrite the opened file)")
        if out_path is None:
            return

        def _do():
            buf, changes, expect, warnings = se.apply_equip(self.data, decoded, slot)
            for w in warnings:
                print(f"WARNING: {w}")
            se.commit_output(
                out_path, self.data, buf, [decoded], self.levels, changes, expect=expect or None
            )
            return changes

        try:
            changes = self._capture_io(_do)
        except se.EditRefused as exc:
            self._append_log(f"REFUSED {exc}")
            messagebox.showerror("Equip refused", str(exc))
            return
        except SystemExit as exc:
            msg = str(exc.code) if isinstance(exc.code, str) else str(exc)
            msg = msg.removeprefix("error: ")
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Equip refused", msg)
            return
        self._append_log(f"WROTE {out_path}")
        self._set_status(f"WROTE {out_path}  equip changes={len(changes)}")

    def _collect_edits(self) -> dict:
        decoded = self._current()
        if decoded is None:
            raise se.EditRefused("no live slot selected")
        kwargs: dict = {"allow_overheal": bool(self.overheal.get())}

        hp = parse_int("hp", self._val(self.hp))
        maxhp = parse_int("maxhp", self._val(self.maxhp))
        if hp != decoded["hp"]:
            kwargs["hp"] = hp
        if maxhp != decoded["max_hp"]:
            kwargs["max_hp"] = maxhp

        facing = parse_int("facing", self._val(self.facing))
        if facing != decoded["facing"]:
            kwargs["facing"] = facing

        level = parse_int("level", self.level_var.get().split()[0])
        x = parse_int("x", self._val(self.x))
        y = parse_int("y", self._val(self.y))
        if level != decoded["level"]:
            kwargs["level"] = level
        if x != decoded["x"]:
            kwargs["x"] = x
        if y != decoded["y"]:
            kwargs["y"] = y

        if self.qty_edits:
            kwargs["item_qtys"] = dict(self.qty_edits)
        if len(kwargs) == 1:
            raise se.EditRefused("no fields changed")
        return kwargs

    def _world_level(self) -> int:
        raw = self.world_level_var.get().strip()
        level = parse_int("world level", raw)
        if not (0 <= level <= 24):
            raise se.EditRefused(f"world level={level} not in 0..24")
        return level

    def dump_world(self) -> None:
        if self.path is None or self.data is None:
            messagebox.showinfo("World", "Open a save file first.")
            return
        try:
            level = self._world_level()
        except se.EditRefused as exc:
            messagebox.showerror("World", str(exc))
            return

        class Args:
            pass

        args = Args()
        args.level = level
        args.block = None
        args.fixed = bool(self.fixed_var.get())
        args.centred = bool(self.centred_var.get())
        try:
            self._capture_io(lambda: se.cmd_world(self.path, args))
            self._set_status(f"World dump L{level} written to the pane below.")
        except SystemExit as exc:
            msg = str(exc.code) if isinstance(exc.code, str) else str(exc)
            if msg.startswith("error: "):
                msg = msg[7:]
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("World refused", msg)

    def dump_objects(self) -> None:
        if self.path is None or self.data is None:
            messagebox.showinfo("Objects", "Open a save file first.")
            return
        try:
            level = self._world_level()
        except se.EditRefused as exc:
            messagebox.showerror("Objects", str(exc))
            return

        class Args:
            pass

        args = Args()
        args.level = level
        args.block = None
        args.all_levels = False
        args.verbose = False
        args.fixed = bool(self.fixed_var.get())
        args.centred = bool(self.centred_var.get())
        try:
            self._capture_io(lambda: se.cmd_objects(self.path, self.levels, args))
            self._set_status(f"Objects xref L{level} written to the pane below.")
        except SystemExit as exc:
            msg = str(exc.code) if isinstance(exc.code, str) else str(exc)
            if msg.startswith("error: "):
                msg = msg[7:]
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Objects refused", msg)

    def export_file(self) -> None:
        if self.path is None or self.data is None:
            messagebox.showinfo("Export", "Open a save file first.")
            return
        decoded = self._current()
        if decoded is None:
            return
        try:
            kwargs = self._collect_edits()
        except se.EditRefused as exc:
            self._append_log(f"REFUSED {exc}")
            messagebox.showerror("Invalid value", str(exc))
            return

        suggested = self.path.parent / (self.path.name + ".edited")
        picked = filedialog.asksaveasfilename(
            title="Export edited save (will not overwrite the opened file)",
            initialdir=str(self.path.parent),
            initialfile=suggested.name,
        )
        if not picked:
            self._append_log("REFUSED export cancelled (no output path)")
            return
        out_path = Path(picked)
        try:
            se.refuse_in_place(self.path, out_path)
        except SystemExit as exc:
            msg = str(exc).removeprefix("error: ")
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Export refused", msg)
            return

        try:
            def _do_write():
                buf, changes, expect, warnings = se.apply_player_edits(
                    self.data, decoded, self.levels, **kwargs
                )
                for w in warnings:
                    print(f"WARNING: {w}")
                se.commit_output(
                    out_path,
                    self.data,
                    buf,
                    [decoded],
                    self.levels,
                    changes,
                    allow_overheal=bool(self.overheal.get()),
                    expect=expect or None,
                )
                return changes

            changes = self._capture_io(_do_write)
        except se.EditRefused as exc:
            self._append_log(f"REFUSED {exc}")
            messagebox.showerror("Export refused", str(exc))
            return
        except SystemExit as exc:
            msg = str(exc).removeprefix("error: ")
            self._append_log(f"REFUSED {msg}")
            messagebox.showerror("Export refused", msg)
            return
        except Exception as exc:
            self._append_log(f"REFUSED exception {type(exc).__name__}: {exc}")
            messagebox.showerror("Export failed", str(exc))
            return

        self._append_log(f"WROTE {out_path}")
        self._set_status(f"WROTE {out_path}  changes={len(changes)}")


def run_gui(savefile: Path | None = None, export_dir: Path | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    levels = se.LevelIndex(export_dir or se.EXPORT_DIR)
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    app = SaveEditorApp(root, levels)
    if savefile is not None:
        root.after(50, lambda: app.load_path(Path(savefile)))
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else None
    return run_gui(path)


if __name__ == "__main__":
    sys.exit(main())
