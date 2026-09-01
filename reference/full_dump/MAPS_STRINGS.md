# Maps data-fork string anchors

Observed Pascal-style names (Mac Roman) at the start of each hit.
All offsets are file offsets, hex, from a harvest — not a claimed header.

## Size check

`0x41C2` = 16834 decimal.

| File | Size | Size / 0x41C2 |
|---|---|---|
| v2.0 `data/hfs/Pathways_1995/Maps` | 420850 | **25 exactly** |
| Demo `.../PathwaysDemo/.../Maps` | 50502 | **3 exactly** |

Hypothesis (size-checked, not internally parsed): the Maps data fork is a
sequence of fixed `0x41C2`-byte records, each beginning with a Pascal
level name. Fields after the name are unknown.

## v2.0 names at `i * 0x41C2`

Spelling here is the Maps file, not `STR#` 2018. Differences vs the
resource list are marked.

| i | offset | Maps Pascal name | vs STR# 2018 |
|---|---|---|---|
| 0 | `00000000` | Ground Floor | same |
| 1 | `000041c2` | Never Stop Firing | same |
| 2 | `00008384` | Lock&Load | same |
| 3 | `0000c546` | They May Be Slow… | same (ellipsis is Mac Roman) |
| 4 | `00010708` | …But They’re Hungry | same |
| 5 | `000148ca` | Evil Undead Phantasms Must Die! | same |
| 6 | `00018a8c` | Ascension | same |
| 7 | `0001cc4e` | Wrong Way! | same |
| 8 | `00020e10` | Welcome, Tasty Primate | same |
| 9 | `00024fd2` | We Can See In The Dark… Can You? | same |
| 10 | `00029194` | Feel the Power | STR# has `Feel The Power` |
| 11 | `0002d356` | A Plague of Demons | same |
| 12 | `00031518` | Beware of Low-Flying Nightmares | same |
| 13 | `000356da` | The Labyrinth | same |
| 14 | `0003989c` | Happy Happy, Carnage Carnage | same |
| 15 | `0003da5e` | Need a Light? | STR# has `Need A Light?` |
| 16 | `00041c20` | Lasciate Ogne Speranza, Voi Ch’Intrate | same |
| 17 | `00045de2` | Watch Your Step | same |
| 18 | `00049fa4` | I’d Rather Be Surfing | same |
| 19 | `0004e166` | Warning: Earthquake Zone | same |
| 20 | `00052328` | Don’t Get Poisoned! | STR# has `Don’t Get Poisoned` (no `!`) |
| 21 | `000564ea` | Please Excuse Our Dust | same |
| 22 | `0005a6ac` | But Wait!— That’s Not All! | same |
| 23 | `0005e86e` | Where Only Fools Dare Tread | STR# has `Fool` (singular) |
| 24 | `00062a30` | Ok, Who Else Wants Some? | same |

`STR#` 2018 also has three names that do **not** appear as Maps records:
Entrance To Hell, Search Me!, Carnage From Above.

A next record at `00062a30 + 0x41C2` would start at `00066bf2`, past EOF
(`00066b32`).

## Demo names

| i | offset | Maps Pascal name |
|---|---|---|
| 0 | `00000000` | Pathways into Darkness… |
| 1 | `000041c2` | Never Stop Firing |
| 2 | `00008384` | Witness Total Carnage |

Demo record 0 is not “Ground Floor”. Record 2 is not in the full-game
`STR#` 2018 list.
