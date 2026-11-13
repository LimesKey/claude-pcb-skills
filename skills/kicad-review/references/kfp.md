# kfp.py - footprints as files

Reads, lints, plots, compares and edits footprints. kpcb answers where a placed part
sits; kfp answers whether the footprint itself is right, and how a board copy differs
from its library.

```bash
F=<skill>/scripts/kfp.py
python3 $F lib/footprints.pretty lint                 # every footprint in a library
python3 $F lib/footprints.pretty/X.kicad_mod show     # pads, pitch, gaps, mask web, body, courtyard, model
python3 $F Package_SON:VSONP-8-1EP_5x6_P1.27mm lint   # Lib:Name via fp-lib-table (--proj DIR if not in the project)
python3 $F board.kicad_pcb show U2                  # the BOARD's copy, back in library form
python3 $F board.kicad_pcb view J1 -o j1.png        # kicad-cli's plot, pads sketched + numbered
python3 $F board.kicad_pcb diff [REF..]             # board copies vs their libraries (0.4 s, whole board)
python3 $F board.kicad_pcb libs                     # where footprints and 3D models come from
python3 $F board.kicad_pcb vendor [--apply]         # copy the out-of-repo ones into the project (dry run)
python3 $F X.kicad_mod edit OP.. -o OUT               # scripted edits; `edit` alone lists the ops
```

**A board copy** (`BOARD.kicad_pcb REF`) is turned back into library form before
anything reads it: the footprint's rotation is taken off pad and text angles (a board
stores them absolute), a back-side part is un-mirrored (KiCad stores its local y
negated, layers F<->B, text `justify mirror`), and nets, uuids, sheet paths, teardrops
and symbol fields are dropped. So `show`/`lint`/`view` on `board.kicad_pcb U2` describe
the footprint as placed, in the library's frame.

Geometry comes from kpcb's own `Board` parser (the footprint wrapped in a one-part temp
board at 0,0), so pads, custom-pad primitives, courtyard rings and silk lines read the
same as in kpcb.

## lint

KLC F5.1-F5.3 (silk, Fab, courtyard; numbers from the KLC source, gitlab
kicad/libraries/klc) plus the assembly checks a fab cares about. One line per footprint
per rule. Exit 2 on an ERROR.

| rule | fires on |
| --- | --- |
| CRTYD | none (ERROR); not one closed outline; copper outside it (placement DRC cannot protect those pads); clearance to body+pads under KLC's class value (0.25, 0.15 under 1.5 mm, 0.5 connectors / crystals / canned caps, 1.0 BGA/WLCSP; class from name + tags, never descr); off the 0.01 grid; width not 0.05 |
| FAB | no closed body outline on Fab (marker circles alone are not the housing); no `${REFERENCE}` on Fab |
| SILK | silk over a pad (ERROR); closer than max(line width, mask expansion) (KLC F5.1, 0.2 recommended); silk under an SMD body |
| WIDTH | silk outside 0.10-0.15, Fab outside 0.10-0.15, courtyard not 0.05 |
| PADNUM | a thermal via inside an exposed pad under another number (ERROR: KiCad nets pads by number, so the via is not on the EP's net); repeated numbers |
| PADOVER | differently numbered pads overlap: on a board copy an ERROR only across two nets (a FET's drain pads into its tab share one); in a library a WARN, since only the symbol knows |
| PADMASK / PADPASTE | an SMD pad with no mask opening (WARN); an exposed pad with no paste and no paste windows (WARN: no joint); other pads without paste (INFO: test points, fiducials) |
| MASKWEB | the thinnest mask dam between pads, and how many pairs are under ~0.1 mm (fabs open those as one window) |
| PASTE | an exposed pad with a full paste aperture (EPs usually take ~50-80%; check the datasheet) |
| ORIGIN | an SMD footprint's origin > 0.1 mm from its body (or copper) centre: the CPL places by origin |
| ATTR | smd with plated holes (thermal vias in a pad excepted), through_hole with none, neither; a library that sets dnp/exclude flags |
| MODEL | none (INFO); an undefined `${VAR}`; a file that does not exist |
| FORMAT | saved by a nightly (stable cannot open it); legacy `(module ...)` KiCad 5 format |

A tight courtyard (U2's 0.165 mm vs KLC's 1.0 for WLCSP) is often deliberate: the WARN
says what KLC asks, the design decides.

## diff (board vs library)

Follows KiCad's own comparison (`FOOTPRINT::FootprintNeedsUpdate`,
`pcbnew/drc/drc_test_provider_library_parity.cpp`) in two tiers:

1. **What DRC's lib_footprint_mismatch counts**: smd/through_hole type, pads (number,
   type, fab property, position, orientation - any angle on a circle and a half turn on
   rect/oval/roundrect are the same pad - shape, size, roundrect/chamfer, drill, offset,
   primitives), graphic shapes (geometry, fill, layer; stroke only on copper), rule areas.
   Field by field: `pad 1: size 0.56 0.62 -> 0.6 0.6`, `keepout -24,-27.75 .. 24,-6.75 (48 x
   21 mm)` vs the board's.
2. **What else differs** (DRC says nothing, Update Footprint from Library still resets it):
   pad overrides (`zone_connect 2` from `edit solid`, thermal settings, mask/paste margins),
   3D model path, silk/Fab/courtyard line widths, user texts, footprint-level settings and
   the board-only/exclude flags.

A third bucket, **sub-um rounding only**: the coordinates differ by less than 1 um (a
rotation round trip leaves 1.399999 for 1.4). KiCad sorts shapes and pads by exact position
before pairing them, so it can still flag such a footprint; nothing physical differs, and
Update Footprint clears the flag. On the reference board (2026-11-12) KiCad's 21 mismatches were
exactly the 14 of tier 1 plus 7 of this bucket.

Normalised away, as KiCad does: a rect stored as a 4-point polygon, repeated polygon
vertices (easyeda2kicad doubles every one), arc direction (a flip reverses it), `fill none`
vs `no`, KiCad 5 custom-pad primitives (filled without a fill token), `*.Cu` vs an explicit
copper stack. Not compared: nets, field text and positions.

## libs

Every board footprint grouped by where its library lives: `repo` (tracked),
`repo, UNTRACKED`, `outside the repo` (a global library such as easyeda2kicad: a clone
cannot refresh, lint or render those), `stock`, `NOT IN LIBRARY`, `NO LIBRARY`. Then the
project libraries' footprints no part uses, and every 3D model by where it resolves
(`${VARS}` from the environment, kicad_common.json, `${KIPRJMOD}` and KiCad's stock
`KICADn_3DMODEL_DIR`, which 10.99 defines for n = 10 and 11 alike), listing missing
files and models outside the repo (an untracked repo model is listed as `repo, UNTRACKED`).

## vendor

`kfp.py BOARD vendor [--lib NICK] [--models DIR] [--apply [--force]]`: make the project
self-contained. Every footprint from a library outside the repo goes into the project library
NICK (default: the one in the project fp-lib-table): the library file verbatim when the board
copy matches it, else the board's copy in library form (Reference `REF**`, version line added),
so Update Footprint becomes a no-op; instances that differ from the one written are named
(they keep their board copy). Every 3D model resolving outside the repo is copied into DIR
(default: where the repo's models already are, else `lib/3dmodels`) with its .step/.wrl
siblings and re-pointed as `${KIPRJMOD}/...`; a different file already there is never
overwritten (that path stays). Lib ids move on the board and in every placed symbol's Footprint
field, never in the `lib_symbols` cache (that would read as lib_symbol_mismatch); NICK joins
the fp-lib-table if missing. Also listed: symbol libraries used from outside the repo (not
copied), and stock footprints Update Footprint would change, by direction against another
KiCad install's stock copy (stable beside nightly): the board equal to the older copy = worth
pulling; both stock copies equal = a local fix it would undo. Dry run by default; --apply
writes in place, refused while KiCad holds the project. Prove it after: `kfp libs` (nothing
outside), `kverify .` (ERC and sync PASS; the netlist row is only the re-pointed Footprint
fields), `kpcb diff OLD` ("no change": geometry is untouched). Reference board 2026-11-12, on a
scratch copy: 13 footprints (all board copies, each with board-side fixes) and 18 model files,
19 paths re-pointed, 18 Footprint fields; ERC 0 added, sync identical, `kpcb diff` no change,
`kfp diff Q5 U13 BT1` identical.

## edit

Library footprints only (`.kicad_mod` or `Lib:Name`); a board copy follows by fixing the
library and Update Footprint in KiCad. `-o OUT` required; OUT may be the input only with
`--in-place`. Ops run in order:

| op | does |
| --- | --- |
| `crtyd CLR\|klc` | replace the courtyard with one 0.05 rect round body+pads, CLR mm out (`klc`: the class value), snapped outward to 0.01 |
| `fab WxH\|pads` | replace the Fab outline (marker circles stay) with a centred W x H body with KLC's pin-1 bevel (1 mm or 25%, the smaller) at the corner nearest pad 1/A1; adds `${REFERENCE}` sized to fit |
| `origin body\|pads\|X,Y` | move the origin to the body / copper centre / X,Y: everything shifts, pad primitives stay pad-local |
| `pad SEL K=V[,V][;K=V]` | SEL a number or glob; keys `size=W,H at=X,Y shape=S rratio=R drill=D mask=M paste=M pasteratio=R layers=L,.. num=N` |
| `widths` | KLC widths: silk 0.12, Fab 0.10, courtyard 0.05 |
| `model PATH\|none` | the 3D model (`${KIPRJMOD}/lib/...` keeps the repo self-contained) |
| `rename NAME`, `descr TEXT` | the name (and Value), the description |

It prints each op's result and the lint delta (`- [ERROR] CRTYD ...` gone, `+ ...` new).
The file is written in KiCad's layout from the parsed tree; KiCad reformats it on its next
save. Legacy `(module ...)` files are refused: `kicad-cli fp upgrade DIR -o NEW.pretty`
first. After an edit: `kfp.py OUT view` to look, then in KiCad Update Footprint and
`kpcb.py BOARD sync`.
