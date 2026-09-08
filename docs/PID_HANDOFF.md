# Pathways Into Darkness — working state

Companion to `docs/FORMAT.md` (the spec) and `docs/UNITY_PORT.md`
(the port mapping). This file is current working state: open items,
the disproven list for this phase, corrections, and methodology.

Do not re-open a closed item without new bytes.

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
| A5 `-$1BCA` (7114) and `-$1BCC` (7116) are runtime state | Both are DATAINIT-only with **no writer** in any CODE segment. `-$1BCA` is permanently 1 (its branches are live). `-$1BCC` is permanently 0 (its branch, `view+$14` = 5, is unreachable). Hardcode; do not implement. |
| Eye height and FOV were fitted to screenshots | Both are derived from the code arithmetic. |
| The two authored viewports are portrait / differ in FOV | Both are 4:3 (272 × 204 and 384 × 288) and both give exactly 0.8 and 0.6. |
| The player walk step is 24 | 24 is run-backward and run-strafe. Walk forward is 17. |
| player `+$134` is an unidentified dt modifier | It is the Red Cloak (id 14). Doubles dt on JT 248 door/creature/projectile; does not scale JT 145. |

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

---

## Still open

| Item | One line |
|---|---|
| Creature door behaviour | Whether an actively pursuing creature walks through a door at position `<= 512`. Untested; idle creatures proved nothing. |
| The unreproduced door-500 clip | One session where the player was blocked at position 500 with the freeze intact. Every geometric hypothesis searched and refuted; the traced mover passes at 0, 200, 350, 500 and 512. Most likely the @3242 creature proximity revert, but player `+$216` (534) was 0 in the save. Retry once; do not spend more. |
| `type_addl` 134 and 135 (L15) | No reader anywhere. |
| Trigger cases 18, 19, 20, 21 | Four distinct values, identical behaviour (`addq.w #3`, player `+$142` (322)), 16 uses on L17. |
| JT 246 Stalker poke | Pokes `$00FF` (255) into creature catalog entry 14 (Stalker) field `+$08` at level apply. |
| STR# 2001 indices 8, 9, 13 | Blank names, full catalog rows, placed in levels: type 8 on L15 ×1 (HP 12000), type 9 on L19 ×1 (HP 5500), type 13 on L19 ×6 (HP 240). Entry 13’s `+$04` is `$100B` (4107) against Ooze’s `$000B` (11) — a greater-Ooze variant. Entries 8 and 9 unexplained; very high HP and single placements suggest impassable obstacles rather than enemies. Fan sources name Flying Rat, Greed, Flying Reptile, Malice and Deceit, none of which appear in any STR#. |
| A5 `-$17FA` (6138) | Role beyond the floor/ceiling gradient; and the fifth `$1000` (4096) bank. |
| `+$1B8` (440) monster-frequency poke | CODE 2 @8710 writes `#$F` (15) to slot 0 only while d7 iterates 0..2 over a stride-4 table. Indexed compare, unindexed write. Probable original bug; confirm before replicating. |
| Creature AI | Movement, pathing, aggro, attack selection, respawn. |
| Remaining systems | The conversation system, the Search dialog, potions, per-item use effects, sound, level 24 and the endgame, text and dialog rendering. |

Lower-impact leftovers that remain in `docs/FORMAT.md` (do not treat
as closed): player-island flag bits (`0x0840` / `0x0864`);
`unknown1`; unverified s1 world-size words; level-change type 4;
Carlos `TypeAddl=200`; `+0x091C` untested; Colt .45 / M-16
proficiency slots never written by the decoded fire table; the
encumbered lock.

---

## TODO (gaps in the source prompt, not invented)

- Door texture 2 is absent from the published rate table (0/1, 3/4/5, 6).
- View-record fields not tabulated in FORMAT.md are unnamed.
