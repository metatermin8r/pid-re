# Pathways Into Darkness — Unity port mapping

How `docs/FORMAT.md` maps onto the Unity port. Each item is marked
**DERIVED** (matches the original’s rule) or **ACCOMMODATION**
(chosen to look right). The spec is implementation-neutral; this
file is not.

---

## Units

**DERIVED** scale.

| quantity | raw | Unity |
|---|---|---|
| 1 cell | `$400` (1024) | `PidConst.SectorSize` = 3.0 |
| metres | — | `RawToMetres` = 3/1024 |
| wall height | 1023 | `WallHeight` = 3 × 1023/1024 = 2.997 |
| eye height | 614 | `EyeHeight` = 3 × 614/1024 = 1.799 |

Keep all game logic in integer raw units; convert only at the
transform.

---

## Camera

**DERIVED, already correct.**

Game view locked 4:3. Camera vertical FOV = 61.927513. Because
`tan(HFOV/2) = tan(VFOV/2) * 4/3` exactly, this reproduces PID’s
horizontal 77.3196 degrees exactly. No change needed.

Both authored original viewports (272 × 204 and 384 × 288) are 4:3
and both give `tan(HFOV/2) = 0.8`, `tan(VFOV/2) = 0.6`.

---

## Movement

`walkSpeed` 3.0 units/sec is **DERIVED-EQUIVALENT**: 17 units per
VBL at 60 Hz = 1020 units/sec = 0.996 cells/sec. Running should be
6.0 (34 units/VBL).

24 is **not** the walk step; it is run-backward and run-strafe.
Red Cloak (`+$134`) does not scale the JT 145 step.

---

## What is currently an accommodation

Honest list. These do **not** match the original’s rule.

- Textures are baked to RGB per palette variation. This makes PID’s
  shading model unreproducible; see **The shading pipeline**.
- Floors and ceilings are meshed as quads. The original renders
  neither.
- Wall spans by tag are not implemented; every wall is emitted full
  width. Original spans: tag 1 = 0–1024, tag 2 = 256–1024, tag 3 =
  0–768, tag 4 = 256–768. Tag 0 is never drawn. Tag 5 is the door
  slab.
- `PidDoor.slideTime` defaults to 0.6 s; the original is 1.422 s for
  texture 0/1 (12 units/tick; also 1.017 s for tex 3/4/5, 0.683 s for
  tex 6). The travel axis is inferred from void neighbours rather
  than read from `door_list.direction`. The panel is a single quad
  rather than a three-face slab (+256, +768, leading cap). Collision
  keys on `IsOpen` rather than `position > 512` (JT 161: 512 passes,
  513 blocks).
- `clampObjectsToCeiling` exists because billboard vertical extents
  (CODE 5 @17522–@17650 within @17190) are not yet implemented.
- Mouse look; the original turns in `±2`, `±4` or `±8` steps of a
  512-unit circle (0 = west, 128 = north, 256 = east, 384 = south).

---

## The shading pipeline (planned, not yet built)

**DERIVED** plan.

Export tiles as R8 index textures (point filter, no mips, no sRGB)
plus a 256×16 RGBA ramp texture per palette variation where texel
`(i, band)` is the RGB that `out[band][i]` resolves to, row 15 forced
to slot `$0F` (15).

Fragment shader samples the index, computes the band from a
**vertex-interpolated** `(depth + |lateral|/2)` rather than
per-fragment distance, and looks up the ramp.

```
band = ((15 * (depth + |lateral|/2)) / view+$14) >> 10, clamped to 15
```

`view+$14` is 7 (IR), 5 (flashlight), or 3 (else). A5 `-$1BCC` is
dead (always 0); do not implement its branch.

Index 2 remains the billboard alpha key.

---

## Floor and ceiling (planned)

**DERIVED** plan.

Keep floors in the **collision** mesh only. Remove both from the
render mesh. Replace with a full-screen vertical gradient behind all
geometry, knots at 2/5 and 3/5 of screen height when lit, 3/10 and
7/10 unlit.

Rows `[0, d4)` and `[d5, n)` are the `$6A..$79` (106..121) fade ramp;
`[d4, d5)` is `$0F0F0F0F` black. The dark band is wider without a
light — the flashlight’s second effect (`view+$14` is the first).

---

## TODO (gaps in the source prompt, not invented)

- Whether the port already implements JT 161’s 512/513 split, void
  keep-out `$199` (409) / `$266` (614), or the @3242 proximity revert
  is not stated above.
- Creature movers, projectiles-through-doors, and automap opacity
  are not mapped here.
