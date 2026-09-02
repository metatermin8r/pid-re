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

# ItemCheat / FORMAT.md names. Display only; ids are the source of truth.
ITEM_NAMES: dict[int, str] = {
    0x00: "Map",
    0x01: "Digital Watch",
    0x02: "Flashlight",
    0x03: "IR goggles",
    0x04: "Cuban gas mask",
    0x06: "Canvas sack",
    0x08: "Aromatic box",
    0x09: "Velvet red bag",
    0x0A: "Lead box",
    0x0C: "Empty elaborate vial",
    0x0E: "Red cloak",
    0x10: "Nuclear device",
    0x11: "Radio beacon",
    0x12: "Blue liquid vial",
    0x13: "Red liquid vial",
    0x14: "Brown liquid vial",
    0x15: "Violet liquid vial",
    0x16: "Mein Kampf",
    0x17: "Small pamphlet",
    0x18: "Bird's Egg",
    0x1C: "Bad Walther P4",
    0x2C: "Ceremonial Mask",
    0x2D: "Survival Knife",
    0x2E: "Walther P4",
    0x2F: "Colt .45",
    0x30: "Schmeisser MP-41",
    0x31: "AK-47",
    0x32: "M-79 Grenade Launcher",
    0x33: "Walther P4 Ammo",
    0x40: "Yellow Crystal",
    0x41: "Blue Crystal",
    0x42: "Orange Crystal",
    0x44: "Mottled Crystal",
    0x45: "Green Crystal",
    0x46: "Black Crystal",
}

WARN_UNVERIFIED = (
    "Output is unverified until loaded in Infinite Mac. "
    "No checksum is computed; whether saves carry one is unknown."
)


def item_name(item_id: int) -> str:
    if item_id == 0xFFFF:
        return "(end)"
    return ITEM_NAMES.get(item_id, "")


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
        root.minsize(880, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self._build()
        self._set_status("Open a Pathways Into Darkness 2.0 Saved Games file.")

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=8)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        top = ttk.Frame(main)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        top.columnconfigure(1, weight=1)
        ttk.Button(top, text="Open…", command=self.open_file).grid(row=0, column=0)
        self.path_var = tk.StringVar(value="(no file)")
        ttk.Label(top, textvariable=self.path_var).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(top, text="Export As…", command=self.export_file).grid(row=0, column=2)

        meta = ttk.LabelFrame(main, text="Save slot", padding=8)
        meta.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)
        meta.columnconfigure(1, weight=1)
        ttk.Label(meta, text="Live game").grid(row=0, column=0, sticky="w")
        self.slot_var = tk.StringVar()
        self.slot_combo = ttk.Combobox(
            meta, textvariable=self.slot_var, state="disabled", width=70
        )
        self.slot_combo.grid(row=0, column=1, sticky="ew", padx=6)
        self.slot_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_slot())
        self.gates_var = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self.gates_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.unknown_var = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self.unknown_var, foreground="#555").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        player = ttk.LabelFrame(main, text="Player", padding=8)
        player.grid(row=2, column=0, sticky="nsew", **pad)
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

        self.clock = self._entry(player, "Clock (whole seconds)", 3)
        self.clock_ticks_var = tk.StringVar(value="stored ticks: —")
        ttk.Label(player, textvariable=self.clock_ticks_var, foreground="#555").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        self.facing = self._entry(player, "Facing (u16 at +0x091C)", 5)
        self.facing_note = tk.StringVar(value="width UNKNOWN; observed values live in +0x091D")
        ttk.Label(player, textvariable=self.facing_note, foreground="#555").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Separator(player).grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(player, text="Position").grid(row=8, column=0, columnspan=2, sticky="w")

        ttk.Label(player, text="Level").grid(row=9, column=0, sticky="w", pady=2)
        self.level_var = tk.StringVar()
        self.level_combo = ttk.Combobox(
            player, textvariable=self.level_var, state="disabled", width=36
        )
        self.level_combo.grid(row=9, column=1, sticky="ew", pady=2)
        self.level_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_sector())
        self.level_combo.bind("<KeyRelease>", lambda _e: self._refresh_sector())

        self.x = self._entry(player, "X (0–31)", 10)
        self.y = self._entry(player, "Y (0–31)", 11)
        self.x.bind("<KeyRelease>", lambda _e: self._refresh_sector())
        self.y.bind("<KeyRelease>", lambda _e: self._refresh_sector())

        self.sector_var = tk.StringVar(value="sector: —")
        ttk.Label(player, textvariable=self.sector_var).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(4, 4)
        )
        ttk.Button(
            player, text="Jump to first arrival on this level", command=self.use_arrival
        ).grid(row=13, column=0, columnspan=2, sticky="w")

        inv = ttk.LabelFrame(
            main,
            text="Inventory (quantity of existing records only)",
            padding=8,
        )
        inv.grid(row=2, column=1, sticky="nsew", **pad)
        inv.columnconfigure(0, weight=1)
        inv.rowconfigure(0, weight=1)

        cols = ("slot", "name", "id", "state", "qty", "catalog")
        self.tree = ttk.Treeview(inv, columns=cols, show="headings", height=16, selectmode="browse")
        headings = {
            "slot": ("#", 40),
            "name": ("Name", 150),
            "id": ("ID", 50),
            "state": ("State", 50),
            "qty": ("Qty", 70),
            "catalog": ("Catalog", 70),
        }
        for key, (title, width) in headings.items():
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=(key == "name"), anchor="w")
        scroll = ttk.Scrollbar(inv, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_inv_select())

        qty_row = ttk.Frame(inv)
        qty_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(qty_row, text="Selected qty").pack(side="left")
        self.qty_var = tk.StringVar()
        self.qty_entry = ttk.Entry(qty_row, textvariable=self.qty_var, width=10)
        self.qty_entry.pack(side="left", padx=6)
        ttk.Button(qty_row, text="Set quantity", command=self.apply_qty).pack(side="left")
        ttk.Label(
            qty_row,
            text="Cannot add, remove, or reorder records.",
            foreground="#555",
        ).pack(side="left", padx=8)

        bottom = ttk.Frame(main)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        bottom.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status_var, wraplength=840).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(bottom, text=WARN_UNVERIFIED, wraplength=840, foreground="#555").grid(
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

        live = [d for d in scan["all6"] if not se.in_template_region(d["base"])]
        if not live:
            messagebox.showerror(
                "Not a usable 2.0 save",
                "No pre-template player record passed all six gates.\n"
                "This editor only accepts Pathways Into Darkness 2.0 Saved Games "
                "(not version 1.1 or demo saves).",
            )
            return

        self.path = path
        self.data = data
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
        self._fill_from_current()
        self._set_status(f"Loaded {path.name}. Choose a slot, edit, then Export As…")

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
        self._fill_from_current()

    def _fill_from_current(self) -> None:
        decoded = self._current()
        if decoded is None or self.data is None:
            return
        self._filling = True
        try:
            self.qty_edits.clear()
            flags, _ = se.gate_flags(self.data, decoded["base"], self.levels)
            names = ("G1 level", "G2 X", "G3 Y", "G4 standable", "G5 HP", "G6 clock")
            self.gates_var.set(
                "  ".join(
                    f"{n}={'PASS' if ok else 'FAIL'}" for n, ok in zip(names, flags)
                )
            )
            self.unknown_var.set(
                f"u16@+0x0750={decoded['u750']}   u16@+0x0752={decoded['u752']}  "
                f"(unidentified; not edited here)"
            )
            self._set(self.hp, decoded["hp"])
            self._set(self.maxhp, decoded["max_hp"])
            clock = decoded["clock"] or 0
            self._set(self.clock, clock // 60)
            self.clock_ticks_var.set(
                f"stored ticks: {clock}  ({clock / 60.0:.4f} s). "
                f"Export writes whole seconds × 60; only written if you change this box."
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
            self._refresh_sector()
            self._fill_inventory(decoded)
        finally:
            self._filling = False

    def _fill_inventory(self, decoded: dict) -> None:
        assert self.data is not None
        self.inventory = se.read_inventory(self.data, decoded["base"])
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for i, rec in enumerate(self.inventory):
            qty = self.qty_edits.get(i, rec[2])
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(i, item_name(rec[0]), rec[0], rec[1], qty, rec[3]),
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
        arrivals = self.levels.arrivals[level]
        if not arrivals:
            messagebox.showerror("Arrival", f"L{level} has an empty arrivals list")
            return
        first = arrivals[0]
        self._set(self.x, int(first["x"]))
        self._set(self.y, int(first["y"]))
        self._refresh_sector()
        self._set_status(
            f"Arrival L{level} ({first['x']},{first['y']}) "
            f"from_level={first.get('from_level')} "
            f"{first.get('from_name')!r} {first.get('change_type_name')}"
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
        values[4] = qty
        self.tree.item(sel[0], values=values)
        self._set_status(f"Queued inv[{slot}] qty {rec[2]} → {qty} (written on Export As…)")

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

        clock_s = parse_int("clock", self._val(self.clock))
        if clock_s != (decoded["clock"] or 0) // 60:
            kwargs["clock_seconds"] = clock_s

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
            messagebox.showerror("Invalid value", str(exc))
            return

        suggested = self.path.parent / (self.path.name + ".edited")
        picked = filedialog.asksaveasfilename(
            title="Export edited save (will not overwrite the opened file)",
            initialdir=str(self.path.parent),
            initialfile=suggested.name,
        )
        if not picked:
            return
        out_path = Path(picked)
        try:
            se.refuse_in_place(self.path, out_path)
        except SystemExit as exc:
            messagebox.showerror("Export refused", str(exc).removeprefix("error: "))
            return

        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
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
        except se.EditRefused as exc:
            messagebox.showerror("Export refused", str(exc))
            return
        except SystemExit as exc:
            messagebox.showerror("Export refused", str(exc).removeprefix("error: "))
            return

        detail = log.getvalue().strip()
        messagebox.showinfo(
            "Exported",
            f"Wrote {out_path}\n{len(changes)} byte(s) changed.\n\n"
            f"{WARN_UNVERIFIED}\n\n{detail}",
        )
        self._set_status(f"Wrote {out_path}  changes={len(changes)}")


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
