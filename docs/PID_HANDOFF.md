# Pathways Into Darkness — session handoff

Companion to `docs/FORMAT.md` (the spec) and `docs/UNITY_PORT.md`
(the port mapping). This file is current working state: what
the port does, what is still open, and the disproven list for
this phase.

Do not re-open a closed item without new bytes.

---

## Where the port is

The 1993 interface is built. Four panels laid out from the
measured rectangles (view 384×288 at (4, 23), messages 384×119
at (4, 336), player 238×184 at (396, 23), inventory 238×223 at
(396, 232)). An inventory tree with selection, expanding
containers, drag and drop, and double-click to use. Modal
dialogs with the real wordmark and item icons. A message log, a
pause veil, and a developer console with commands for items,
proficiency and level warping.

Combat fires, consumes ammunition, reloads, animates and
computes damage. Nothing can be hit because there are no
creatures.

The next milestone is picking items up, dropping them and
looting bodies.

---

## Methodology

Several results this phase came from design reasoning and from
contemporary player documentation rather than static analysis:

- the Cedar Box cadence (1993 FAQ) matching `+$144` (324) = 3600 ticks
- the seven-minute rest tick matching `$6270` (25200)
- the fourteen-item admit list matching a separately published
  disassembly
- the twenty-minute beacon window matching `$11940` (72000)
- the crystal wear model predicted from the printed manual and then
  confirmed in the A5 `-$870` (2160) table

In-game observation corrected static analysis twice: the 512/513
door boundary (JT 161 `cmpi.w #$200` / `bgt`, so 513 blocks and 512
passes), and the door leaf’s anchor side (L0 door 0 dir 3 is
high-edge: leaf on high Y / south).

The fire rate was chased three times by feel before anyone read
the routine. Reading CODE 7 @16404 settled every question in one
pass. The two shade-table bugs were found by comparing a
resolved tile against a known-good render and matching on pixel
counts, which are unique per colour and therefore unambiguous.

---

## Disproven

| Claim | How it died |
|---|---|
| Tag 0 is drawn / remapped to tag 1 | @13488’s remap is a placement fallback after the emit gate at @12202 / @12206 has already rejected it. |
| The Labyrinth is visually randomised | Only s1index bit 0 varies, selector is fixed at 66, and most affected faces are tag 0 and not drawn. |
| There is an L13 maze generator | The grid is authored (499 void, 521 normal, 4 change-level, 525 connected walkable). JT 164 writes only wall words. |
| Containers hide their contents from id lookups as a general rule | The walker at CODE 6 @5838 descends into every container by default. The Lead Box / Alien Gemstone case is hard-coded in callback @6874 (target id 32 AND node id 10 AND state bit 1 clear). A gemstone in a Cedar Box still drains. |
| JT 224’s second argument is a descend flag no caller sets | Refuted twice: polarity is inverted (1 = do **not** descend) and two callers pass 1 (CODE 2 @18434 flashlight/dark, CODE 7 @17936 JT 259). |
| Nibble-5 secret doors are openable | Passage requires `type_addl >= 4`. No site writes that. All six authored instances are permanently impassable. Cut feature. |
| The Cedar Box is rest-gated | It is an arm/disarm countdown on player `+$144` (324). Also: clone orphaning via sibling overwrite (H2). |
| Game time runs 60× real time | 1 tick = 1/60 s, 1:1 with real time. |
| A far plane exists in the renderer | No depth cutoff anywhere. Distant geometry is fully emitted and shaded to black by band 15. |
| The player has a collision radius against the door leaf | The mover contains no radius and no `(1024 − position)` term anywhere. |
| A5 `-$1BCA` (7114) is runtime state | It is not. DATAINIT 1, no writer. **Hardcode 1.** A port **must run** the SET branches: creature proximity revert @3242, VBL path CODE 1 @940, JT 164 path CODE 4 @4348. Opposite of `-$1BCC`. |
| A5 `-$1BCC` (7116) is runtime state | It is not. DATAINIT 0, no writer. **Hardcode 0.** A port **must omit** the CLEAR branch (JT 239 returning `view+$14` (20) = 5). Opposite of `-$1BCA`. |
| GPU affine-per-triangle reproduces the engine's affine-per-column texture mapping | Refuted in game: near walls smear. The supporting measurement used symmetric test cases whose errors cancelled at the sampled midpoint. |
| Eye height and FOV were fitted to screenshots | Both are derived from the code arithmetic. |
| The two authored viewports are portrait / differ in FOV | `_SetRect` high word is the bottom, not the right. The windows are already 4:3 (272×204 / 384×288). The portrait reading was the transpose. |
| The player walk step is 24 | 24 is run-backward and run-strafe. Walk forward is 17. |
| player `+$134` is an unidentified dt modifier | It is the Red Cloak (id 14). Doubles dt on JT 248 door/creature/projectile; does not scale JT 145. |
| The sector carries only two wall words | Six: two edges, four corners. South/east are the neighbour’s slot 0/1. |
| Tag 5 is the door slab | It is the corner chamfer (dirs 4–7, @13550). Door thickness is @16202. |
| Chamfer UV is world-pinned like a tag span | Both @14006 branches emit 0..`$10000` (65536) for every face; the tile is stretched. |
| The white blocks in Ground Floor walls are a decoder bug | They are index-2 placeholder regions filled by an unconditional overlay blit at @2030. RLE is correct. |
| `door_rates` +0 is the per-tick rate | The rate is at `+$A` (10), duplicated at `+$C` (12). +0 is UNKNOWN (0,0,2,2,2,1). |
| The player has a collision radius | He is a point; `$199` (409) / `$266` (614) is a clamp against nibble-0 faces only. |
| The billboard pitches to face the camera | Yaw-only. |
| Sprites are uniformly floor-anchored | Bottom = −614 + per-shape lift. |
| The `+$C2` / `+$D6` shots and hits arrays are read with a different index space than they are written with | JT 260 uses the same 5-entry table index fire writes. |
| @616’s “already has a child” test is the general one-child rule | The general rule is w6 fill capacity against the sum of children’s w4; the child test is a Cedar Box extra. |
| Closed containers hide their contents from everything | Too strong: the default walker descends on JT 207 alone. Only the panel and the Lead Box hard case consult the open bit. |
| `+$19A` is a readiness flag | It is the rate-of-fire timer in ticks. |
| Proficiency affects accuracy | It affects **damage**; there is no to-hit roll. |
| The player projectile list is `+$2DA` | That list is the **creature** projectiles; player fire is hitscan and never touches it. |
| The M-79 has splash damage | All three 40mm types are hitscan with no radius. |
| DITL 2013 supplies REST / SEARCH / MAP | Those labels are STR# 2010. DITL 2013 is ALRT 2007’s first-search tutorial. |
| JT 141 draws the Messages REST / SEARCH / MAP controls | @9618 is not a JT entry. JT 141 (@22422) pushes 2010 as a DLOG id. |
| Catalog `+$50` is the creature’s walk speed | It is projectile speed; walk is `+$0E`. |
| Catalog `+$58` / `+$5A` are creature attack cooldowns | They are projectile frame periods; the attack period is `+$36`. |
| The creature state field is 6 bits with up to 64 states | Only 0–4 exist; bits 6 and 7 are separate flags. |
| CODE 7 @6460 is the creature state dispatch | It is the walk / anim body for states 0 and 1; the dispatch is at @1434. |
| Creature detection uses the octile JT 151 metric with a catalog threshold | It uses Manhattan JT 331 with immediate thresholds. |
| Creatures can open doors | No door-command writer on the creature tick. JT 16 @2688 refuses a closed leaf (`cmpi.w #$200` (512)). |
| The four Player headings are literals | STR# 2013[0..3] via `pea.l $7DD` + JT 271. |
| Progress is three lines / [4] and [5] concatenate | One of [4] or [5]; `_TETextBox` one paragraph. |
| Message ring feeds 1000, 1002, 1003, 2000, 2001 | ParamText / `%s` names. Ring: 2002, 2005[0–19], 2015, 2018, JT 78 C-strings. |
| w7 is an automatic-fire flag | It picks a random muzzle flash and ends the flash early. Every weapon fires while the button is held. |
| The overlay descriptor has a two-bit tag | Three-bit tag, six-bit selector (bits 12 to 7). |
| The r8 exporter shears tiles wider than 256 | It does not. The wordmark was a shade-table bug (`plant_clut`). |
| The tile’s lift applies to the weapon overlay | It does not. Overlay is bottom-centre, scaled by the view. |
| Index 0 is the transparent colour | It is padding and is discarded. Index 2 is transparent. |
| STR# 2008[0] is a general unequipped default | Empty-magazine label only. Ids outside 51–57 never reach it. |

Full historical table, including earlier harvest dead ends:
`docs/FORMAT.md` **Disproven**.

---

## Corrections to the open-items list

| Was | Now |
|---|---|
| Object vertical extents at CODE 5 @17190 | The routine is the **per-cell draw dispatcher**. Billboard extents are @17522–@17650 within it. |
| L13 maze generator | **CLOSED.** No generator exists. Grid authored; JT 164 writes only wall words. |
| Door triggers 130 / 141 / 24 on Ground Floor are not `door_list` indices | **CLOSED.** They are trigger sectors, not door sectors. 130 = Alien Pipes, 141 = gemstone-gated door, 24 = the level exit (sets player `+$52` (82), read by JT 72 to run the ending at @6106). |
| `$217F` | **CLOSED** as an out-of-range s1index (tag 1, selector 66, s1index 127, 4101 faces, 4064 bytes into the blob). Harmless; skip. |
| Cedar Box clone gate | **CLOSED.** Arm/disarm on `+$144` (324); not rest-gated. Sibling overwrite orphans clones (H2). |
| Creature door behaviour: whether an actively pursuing creature walks through a door at position `<= 512` | **RESOLVED.** Creatures cannot open doors: no door-command writer on the creature tick, and JT 16 @2688 (`cmpi.w #$200` (512), `$2(a2)`) refuses to route through a closed leaf. The walk-versus-path asymmetry is real but is **not** permission: a path computed while the leaf was passable is stepped without a second check, so a creature already moving through an open door keeps going as it closes. That is **staleness**, not an open-door capability. |
| Creature AI | **CLOSED.** Five states (0–4) dispatched at CODE 7 @1434; walk `+$0E`; projectile `+$50`; Manhattan JT 331 wake; no kill score / treasure / drop. `docs/FORMAT.md` **Creature AI**. |
| Shade tables differ per level | **CLOSED.** Every `(resource, variation)` table is identical across levels. The merge made them look level-dependent. Palette variation is the variation field. |
| Window rectangles at 640×480 | **CLOSED.** View 384×288 at (4, 23); messages 384×119 at (4, 336); player 238×184 at (396, 23); inventory 238×223 at (396, 232). High word of a SetRect long is the bottom. |
| w7 as semi vs automatic | **CLOSED.** Random muzzle flash. |
| Class 5 `(on wrist)` collision | **CLOSED as unreachable.** No class 5 item is ever seen equipped. |

---

## Still open

| Item | One line |
|---|---|
| The unreproduced door-500 clip | One session where the player was blocked at position 500 with the freeze intact. Every geometric hypothesis searched and refuted; the traced mover passes at 0, 200, 350, 500 and 512. Most likely the @3242 creature proximity revert, but player `+$216` (534) was 0 in the save. Retry once; do not spend more. |
| `type_addl` 134 and 135 (L15) | No reader anywhere. |
| Trigger cases 18, 19, 20, 21 | Four distinct values, identical behaviour (`addq.w #3`, player `+$142` (322)), 16 uses on L17. Alias among themselves; four values, one path. |
| JT 246 Stalker poke | Pokes `$00FF` (255) into creature catalog entry 14 (Stalker) field `+$08` at level apply. |
| STR# 2001 indices 8, 9, 13 | Blank names, full catalog rows, placed in levels: type 8 on L15 ×1 (HP 12000), type 9 on L19 ×1 (HP 5500), type 13 on L19 ×6 (HP 240). Entry 13’s `+$04` is `$100B` (4107) against Ooze’s `$000B` (11) — a greater-Ooze variant. Entries 8 and 9 unexplained; very high HP and single placements suggest impassable obstacles rather than enemies. Fan sources name Flying Rat, Greed, Flying Reptile, Malice and Deceit, none of which appear in any STR#. |
| A5 `-$17FA` (6138) fifth bank | Role beyond the floor/ceiling gradient; and the fifth `$1000` (4096) bank. |
| `+$1B8` (440) monster-frequency poke | CODE 2 @8710 writes `#$F` (15) to slot 0 only while d7 iterates 0..2 over a stride-4 table. Indexed compare, unindexed write. Probable original bug; confirm before replicating. |
| 11,372 trailing packed bytes | Resource 192 leftover after declared count, starts `13 14 15 16`. UNKNOWN. Not missing tile data. |
| Pickup, drop, looting | Next milestone. Conversations, the Search dialog, potions, sound, level 24 and the endgame remain after that. |
| State word bits 2–15 | No isolated reader. Fourteen unused bits is a lot of room. |
| Negative damage past rank + 5 cells | No clamp. JT 237’s behaviour with a negative value is UNKNOWN. UNTESTED whether the range is reachable in play. |
| Item id 9 (Red Velvet Bag) | Named in STR# 2000[9]. JT 217 skips its w3 and does not descend, so it and its contents weigh nothing. Name known; behaviour unexplained. |
| WDEF 128 | Shipped (2102 bytes), apparently unused. Every `_NewCWindow` site passes procID 0, 1 or 8, never `16 * 128`. |
| Message-ring STR# remainder | **Closed.** JT 112 feeds: STR# 2002, 2005[0–19], 2015, 2018, and JT 78 C-strings. 1000/1002/1003 are `_ParamText`. 2000/2001 only as `%s` inside 2005. `out/PANEL_STRINGS.md`. |
| STR# 2006[4] M-16 | Proficiency row and `-$A2C` thresholds (t1=12000, t2=30000). Catalog: Broken M-16 id 25, Magazine id 56 only. No `-$810` row. Absent, not a crash. No known writer of `+$66` index 4. |
| JT 225 / 218 / 226 | Autoload’s magazine pick and unlink. Not read. The port walks the tree itself. |
| Cedar Box `+$144` expiry | Timer is set to `$E10` (3600). What runs when it hits zero is unknown. |
| Emulator tick rate | Port fire rates match the table. The emulator looks slower. |
| Ground Floor mesh | Reports `wallQuads` 390 and `submeshes` 22 against a verified 250 and 20. Every other figure on that line matches. |
| Original chrome run | `@3214` does not advance the unique index, so the original probably blacks out resource 128’s chrome when drawn through the world palette. |

Lower-impact leftovers that remain in `docs/FORMAT.md` (do not treat
as closed): player-island flag bits (`0x0840` / `0x0864`);
`unknown1`; level-change type 4; Carlos `TypeAddl=200`; `+0x091C`
untested; STR# 2006[4] M-16 (thresholds at `-$A2C`, catalog only
Broken M-16 id 25 and Magazine id 56, no `-$810` row — absent,
not a Colt-style crash); the encumbered lock.

---

## TODO (gaps in the source prompt, not invented)

- View-record `+$16` (22) gates the @11586 LFSR reset to 1. No writer identified.
