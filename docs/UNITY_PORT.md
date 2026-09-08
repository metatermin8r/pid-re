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

## Implemented (DERIVED)

These were accommodations or “planned” when this file was first
written. They now follow the original’s rule.

| item | port | original |
|---|---|---|
| textures | R8 index (point, no mips, no sRGB) | `.256` palette index |
| shade LUTs | one 256×16 per `(level, resource, variation)` | `out[band][i] = i + ((N-1-off)*band)/14`; band 15 = `$0F` (15) |
| shader | `PID/Indexed`: band + hash dither | octagonal metric + Galois LFSR (`#$B400` (46080)) |
| `PidShade` | `view+$14` 3/5/7 | JT 239 |
| floors / ceilings | collision mesh only; not in the render mesh | no floor/ceiling geometry |
| `PidBackdrop` | full-screen gradient, knots 2/5+3/5 lit, 3/10+7/10 unlit | JT 179 / A5 `-$17FA` (6138) |
| tag spans | 1: 0..1024; 2: 256..1024; 3: 0..768; 4: 256..768 | CODE 5 @13440 / @13722 |
| corner chamfers | tag 5, dirs 4–7 | @13550 |
| `PidDoor` | position 0..1024; three-quad slab in two submeshes; texture-driven rates; collide at 512 | @16202; A5 `-$8E0` (2272) `+$A`; JT 161 `cmpi.w #$200` / `bgt` |
| billboard lift | bottom = −614 + s1 lift; top = bottom + s1 height | CODE 5 @1454 / @17522 |

Band formula (octagonal metric; interpolate `(depth + |lateral|/2)`
at the vertex, not per-fragment Euclidean):

```
band = ((15 * (depth + |lateral|/2)) / view+$14) >> 10, clamped to 15
```

`view+$14` is 7 (IR), 5 (flashlight), or 3 (else). A5 `-$1BCC` (7116)
is dead (always 0); do not implement its branch.

Index 2 remains the billboard alpha key. Wall overlays paste
unconditionally over index-2 placeholders (CODE 5 @2030); the R8
export already composites those.

---

## What is currently an accommodation

Honest list. These do **not** match the original’s rule.

- **Hash dither.** The original advances a Galois LFSR (tap
  `#$B400` (46080)) per pixel from ctx `+$14` (20), free-running
  across the scene (draw-order dependent). A fragment shader cannot
  reproduce that sequence. The hash of screen position and time has
  the same distribution; it is the correct compromise.
- **`_AffineUV` default OFF.** The original is affine **per
  column**. A GPU triangle interpolator cannot reproduce that.
  Affine-per-triangle smears near walls (confirmed in game). The
  port uses **perspective-correct** sampling as the closer of the
  two GPU options. It is an **ACCOMMODATION**, not a derived match.
  Reproducing the original needs per-column `u` (vertical strips
  at mesh time, or the divide in the fragment shader).
- **Backdrop `_Edge` colour.** The port picked 0.12 grey by eye.
  The exact bright end after clut 129 at index 106 is
  (30, 30, 30) = 30/255 = 0.1176. Dark end dithers (2, 2, 2) vs
  `$0F` black; `$79` (121) is leftover unique (245, 171, 94) and
  is never emitted by @4742.
- **Proximity door auto-open.** PID has no such thing. Doors open
  from the trigger dispatch, not from walking near them.
- **Door initial position hardcoded closed.** The level JSON does
  not carry t3 (`+$3D4` (980), 50 bytes).
- **Door resource hardcoded to 192.** The manifest already has
  `wall_resource` per level (192 / 193 / 194).
- Mouse look; the original turns in `±2`, `±4` or `±8` steps of a
  512-unit circle (0 = west, 128 = north, 256 = east, 384 = south).

---

## TODO (gaps in the source prompt, not invented)

- Creature movers, projectiles-through-doors, and automap opacity
  are not mapped here.
