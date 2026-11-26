# Changelog

Landed backlog entries and fixes, newest at the top. Reference only: the open
work is in a local, untracked `BACKLOG.md`.

- [x] kicad-review/kpcb_text - PcbText, the text-surgery layer every writer uses, sat in kpcb_edit with the writer
      commands, so 9 modules imported a command module to write a file. Done: PcbText, num, qs and norm_ang in
      their own kpcb_text.py (no command imports); every importer points there (kpcb_edit re-exports them for
      old callers). The rest of the layering entry (a query layer for _planes, _clearance_fn, skipped/Exact,
      dead_copper, fp_local; the 124 deferred imports) stays open. Goldens 39/39 unchanged. 2026-11-26.
- [x] kicad-review/kpcb_board.Buckets - 7 hand-rolled 2-D bucket indexes, each with its own cell size, box-to-cells
      loop and dedupe. Done: `Buckets(cell)`: `put(obj, box, *tag)` (tag: a layer or net), `near(box, *tag,
      key=id)` yielding each object once, cells x-major then y, a cell in insertion order (each copy's order, so
      output is byte-identical); used by kpcb_copper.Copper, kpcb_move.World, kpcb_silk.Silk, kpcb_edit.prune
      and renet, kpcb_smooth._reach/_near and kpcb_viapad (its int() cells became floor(): the same for board
      coordinates >= 0). Goldens 39/39 unchanged, loops/tidy/silk timings unchanged. Selftest: near's order,
      dedupe and tag. 2026-11-26.
- [x] kicad-review/kcommon.project_sheets (+SchInfo, ksheet, kfp_vendor) - "which sheets are the design" had four
      answers; SchInfo took every *.kicad_sch in the netlist's directory (no subfolders), kfp_vendor walked
      Sheetfile links (subfolders followed). Done: kfp_vendor's walker is `kcommon.project_sheets(d)` (root +
      top-level sheets, else every sheet in d, then every Sheetfile link relative to the sheet naming it), used
      by SchInfo, ksheet's plots and kfp_vendor: a sub-sheet in a subfolder now has positions, notes and NC
      flags in knet/ksheet. Not taken: a [(file, path, page, uuid)] for all four. kdrc.discover_roots answers
      "which are roots" and ksheet.page_order reads page numbers from cached parses (45 ms); folding them in
      would parse every sheet for kdrc too. The staleness checks keep sch_files (an mtime glob per call, not
      a read of every sheet). Goldens 39/39 unchanged. Selftest: `knet around` on a sheet moved to sheets/.
      2026-11-26.
- [x] kicad-review/kpcb_board (+kpcb_route, kpcb_zones, kpcb_silk) - the project's rules were read by 9 functions,
      each with its own glob (5 unsorted), except tuple and dru regex (two the same clearance regex; three did
      not drop `#` comments). Done: `Board.rules` (cached): the first sorted .kicad_pro's design rules, classes,
      assignments and patterns, and every sorted .kicad_dru parsed once, comments dropped, as [(layer,
      {constraint: min}, condition)] per rule block (a condition before its constraint now reads too);
      `Board.design_min(key, floor)`. edge_clearance, netclass, _netclass, _hole_clr, _type_rules,
      _clearance_build and silk `limits` read it. Reference board goldens 39/39 unchanged. Selftest: two
      .kicad_pro (first wins), a commented-out rule ignored, condition-first hole rule. 2026-11-26.
- [x] kicad-review/kcommon.doc_for (+ kpcb, knet, ksheet) - `TOOL.py FILE CMD -h` printed CMD's docstring lines only,
      so kpcb's ~120 flag help strings were never shown and had drifted: 22% of the reference board's transcript
      flag uses named a flag CMD's help did not (`copper --net` 82, `view -r` 68, `copper --layers` 43, `smooth
      --box` 31, ...), each really read. Owner's call: show them, as part.py does. Done: `doc_for(doc, cmd, ap)`
      appends `CMD flags:`, every flag whose help names CMD (`for `a`/`b` and `c --x`:` clauses, or a leading
      `a/b:` as kfp/ksheet/kdoc/part.py write), other commands' clauses cut; a writer (its entry takes -o) also
      gets the `for the writers` flags. An AST walk of each command's reads (its function and the helpers it
      passes `a` to) found 19 kpcb commands and 6 knet ones under-listed; fixed (-r, --net, --layers, --box,
      --pads, --side, --cols, --amps, --dt, --px, --via-cost; knet -d, --through, --fanout, --rail,
      --peer-max, --max). The footer said `--help` "lists every command and flag"; it lists the commands.
      SKILL.md names `CMD -h`. Selftest: `where -h` and `copper --help` show their flags. 2026-11-26.
- [x] kicad-review/kcommon.project_cfg - knet.json / kpcb.json / kdrc.json were loaded by 6 hand-written blocks
      and `suppress` parsed by the same 5 lines in knet and kpcb; kpcb_amp (`ilim`) and kfront (`i2c`, twice)
      dropped a malformed knet.json silently, so a typo made `kpcb ampacity` lose the ilim table without a
      word. Done: `project_cfg(path, name)` ({} when absent; {} plus one stderr line per file per run when bad
      JSON or not an object) and `suppress_map(cfg, off)`, used by all six. Selftest: `ampacity` beside a
      truncated knet.json names it. 2026-11-26.
- [x] kicad-review/kpcb_tracks `loops` - greedy longest-first removal cut a decoupling cap's run to its IC's
      supply pin and kept a longer path through another pin (reference board C4: VIN run cut, the 1.7 mm
      diagonal to ON kept, an acute V at U23.4). Done: per cap pad, its direct run to another pad (a power pin's
      first, else the shortest) is tried last, and a removal that leaves a new two-track node turning >= 91 deg
      (the census's `acute`) is refused. Also faster, output identical: one track/via list, Index and prune memo
      per kill set instead of per candidate (the per-track `kill | k2` union is gone), `prune` builds its 1 mm
      grid once per call and skips killed items rather than rebuilding it every round, and `_newly_dead` takes
      a memo of each net's dead copper before the rip. Reference board `loops` 6.7 -> 3.6 s (the rest is
      piece_parts / dead_copper Copper builds per candidate). Selftest: 2 cases (a cap's supply run, an acute V).
      2026-11-26.
- [x] kicad-review/kpcb_tracks `widen` - widened sub-width stubs at a via into a disc while the run beyond stayed
      narrow (reference board VBUS f24b332a 12 um 0.8->1.5 and 1f582d8c 43 um 1.0->1.5, PD_LDO_3V3 72adc009
      0.11 mm 0.15->0.5; the first two came from the per-segment power pass, not --uniform-power). Done: after
      every pass, a widened track shorter than its new width with one end on a via and every track at its other
      end narrower goes back to its width. Reference board: exactly those 3 dropped, CHG_VBUS's 1.7 mm widen
      kept. A zero class no longer prints in the tally. Selftest: a via stub fixture. 2026-11-26.
- [x] kicad-review/kpcb_zoneshape `zonemerge` - the merged zone kept the higher-priority zone's name, a script
      band's ('route +BATT' / 'fatten X'), so the designer's name vanished (4 hand renames on the reference
      board). Done: when only the higher one is a band, the merged zone takes the other's name. Selftest: the
      split -o check reads zg's name. 2026-11-26.
- [x] kicad-review/kpcb_move, kpcb_rf, kpcb_zones, kpcb_tracks, kpcb_board - zero-cost speedups found by an
      architecture audit, output byte-identical on the reference board. Done: `drag_set` skips tracks and vias
      off f's pad nets or outside its pads' box (it did 33.7M via distance tests for `tidy`); `refslots` scans
      only the reference-layer tracks whose reach meets the signal track's box, in the old order; `clr` memoises
      each net's netclass clearance (3.5M netclass asks in a `movecheck --scan`) and skips the pair lookup when
      the .kicad_dru has no pair rule; `widen` computed `skipped(b)` once per track (4224x) inside a
      comprehension; `_keepouts` reads the rule areas Board's own parse kept instead of re-reading the file
      (0.14 s a call, 1-2 calls per routing/census command). Reference board: tidy 4.8 -> 1.0 s, refslots 3.7 ->
      1.1 s, `movecheck REF --scan` 19.9 -> 4.6 s, movecheck 0.96 -> 0.57 s, widen 11.5 -> 7.4 s, vscan 0.70 ->
      0.57 s. 2026-11-26.
- [x] kicad-review/kpcb_zoneshape - `zoneshape ZONE -o` reshaped one zone a call, two kicad-cli refills each: a
      clean-up of the reference board's 22 zones over the bar was 22 calls, ~5 min. Done: `zoneshape --over-bar
      [--redraw] [-o OUT]` proposes every one at once (refused ones named, left out), -o writes them all and
      verifies with one refill pair (pieces per net, with --redraw copper per zone <= 1% / 0.5 mm2); a failing
      zone goes back to its old outline, is named, and OUT alone is refilled again. `_verify` now takes a list
      of (label, net, layers, box). Reference board: 14 written, 3 dropped (-BATT -1.33, SOLAR +0.77, +3V3
      +1.02 mm2), 11 verified in 28 s. Selftest: `zoneshape --over-bar` + an -o check. 2026-11-26.
- [x] kicad-review/kpcb_tracks - `zones over own-net zone` said "keep both ... trim it by hand" for 8 of the
      reference board's 10 pairs. Done: `zonemerge A B [-o OUT]` puts the pair's union (rastered on
      kpcb_power's 0.05 grid, 0/45/90, sharp + fillet) on the higher-priority zone on their shared layers;
      layers outside it keep the old outline (a multi-layer hand zone under a one-layer band splits). Refused
      on a clearance difference, a same-net pad the two connection modes join differently (thru_hole_only vs
      yes: plated holes only; refusing on the label alone blocked all 8), another net's zone ranked between,
      or a union in pieces. -o verifies like zoneshape. The zonedup rows print the command. Reference board:
      4 of 8 merge, refill-verified (copper +0.03..+0.17 mm2, pieces the same). Selftest: 4 cases + 2 -o checks.
      2026-11-26.
- [x] part-search/part_pick - `alt` held a range rating by its first figure ('Voltage - Supply' 1.6V~5.5V became
      `>=1.6`: a 1.2-5.5 V part failed, a 3.0-3.6 V one passed; an eFuse's 2.7V~23V became `--volt '>=2.7'`).
      Done: new spec `[lo..hi]` (a range value covering all of it: lower <= lo, upper >= hi), which `alt`
      holds for a range value of any `>=` or equal-text rating (`--volt` too). C78541 now holds
      `Voltage - Supply=[1.6..5.5]`. Selftest: pick checks. 2026-11-26.
- [x] part-search/part_pick - `alt` of a connector found nothing: it held housing text equal (colour, plastic and
      contact material, flammability), and its package never reached JLC's filter. Owner's call taken by
      default: in a connector/header/socket/terminal category the housing text is not held (named on a `not
      held, housing only` line to add back). And the package: `_one_pkg` read 'SMD,P=2mm,Surface Mount,Right
      Angle' (2+ commas) as an any-of, and LCSC's spelling is not JLC's (JLC writes 'Surface Mount，Right Angle',
      a full-width comma; its filter is exact). Now WORD,<size>,... is one name and `alt` / `pick --like` take
      JLC's own spelling (`jlc_annotate` keeps `jpkg`). `alt C295747` (JST PH) 0 -> 6 PH-compatible parts. A
      female header (C46635853) still finds none, honestly: its pin count is on 6% of the category, and
      dropping it (a 10% cut was tried) offered 2x7 and 2x10 parts. Selftest: pick checks. 2026-11-26.
- [x] kicad-review/kpcb_board - `dead_copper(GND)` 1.30 -> 0.95 s on the reference board, byte-identical
      (`dead_copper` GND/+3V3 and `dead_all` compared). `PolyIndex.touches` built a whole-polygon edge grid for
      each of 160 fills (10k+ points a pour) and ray-cast every vertex. Done: `rows` holds every edge in ring
      order (a horizontal one too: each reader's `(y1 > y) != (y2 > y)` skips it), `cells(k)` builds a grid
      row from it on first use (same cell contents, same order, so `_fill_cross` is unchanged), and a point
      with no edge within tol takes its edge-free cell's cached inside-ness (190k ray casts -> 65k). 2026-11-26.
- [x] kicad-review/kpcb_route - a `Grid` build, exact speedups (every router, Clear and zoneshape window):
      `paint` is a method with a disk's and a capsule's row interval inlined, comparisons for min/max (30M
      builtin calls; ties resolve the same); a hole disk inside its via's concentric disk on the same raster
      is skipped (a subset cell for cell: every step is monotone); a `vias=False` grid paints no pour raster
      (only `astar` reads it; the planes were 43% of a Clear grid). `kpcb_smooth._paint`, a copy, now calls it.
      `Clear.seg` gathers its samples' raster bytes with `itemgetter` and finds the blocked ones in C, and
      `on_old` prefilters by box. `tracks --kind jog --max 999` 7.8 -> 5.3 s byte-identical, `smooth --all`
      82 -> 71 s identical bar uuids, 100 6x4 mm Clear grids 1.22 -> 0.90 s (same raster hash). 2026-11-26.
- [x] part-search/part_pick - `alt` held every parameter the original lists, including ones its JLC category
      does not carry or lists on a handful of parts, so every candidate failed them: on the current tree 10 of
      the 12 parts the reference board's sessions `alt`'d found nothing, and so did `alt C25744` (a 0402 10k
      1%: `--volt '>=50'` resolves to 'Voltage Rating', on 12 of 110,716 chip resistors, so the server pool
      was those 12). `bom --alt N` went through the same path. Done: a hold (or alt's own --volt/--tol/...)
      whose attribute is absent from the category's facets or listed on under 1% of its parts (+ package) is
      dropped and named on a `not held:` line with its count (the gap measured: <= 0.03% vs >= 13% for every
      hold that left rows). C25744 0 -> 59 matches, C29269950 (3k 0.1% thin film) 0 -> 4, the PTC fuse and
      the 74LV1T34 buffer 0 -> 4 and 2; a connector/header still finds none (its colour/plastic text holds:
      logged). Selftest: `_rare` in the pick checks. 2026-11-25.
- [x] part-search/part - `part.py CMD -h` printed the whole 6.1 KB docstring for every command (11 lookups in 30
      days on the reference board; 4 sessions then re-ran it, grepped `add_argument` or read part_bom.py to find
      `bom --json` / `--lcsc-csv`). Done: `cmd_help` prints CMD's docstring entries plus the flags whose help
      names CMD (`bom:`, `pick/alt:`, `ds --save:`; the untagged help strings got their commands), one line for
      the 33 shared constraint flags: `bom -h` 1.3 KB, `show -h` 1.0 KB, `jlc -h` 0.4 KB. On the way: `show MPN
      --provider mouser|digikey` with no key said "not found on LCSC or in JLC's library"; it now says no key was
      set and nothing was searched, and `show MPN --provider jlc` found nothing (`resolve` had no jlc branch;
      `search --provider jlc` found the same MPN): it takes JLC's top hit. Selftest: `bom -h` in the offline
      checks. 2026-11-25.
- [x] kicad-review/kpcb_assembly - a leadless part whose land runs past its Fab body (SOD-882) was not listed as
      needing paste, and big lands tied into a pour were not reported (owner's call, 2026-11-25). Done: a
      two-terminal SMD part with a body <= 1.05 x 0.65 mm counts a pad as under it when more than half the land
      sits under the body (SOD-882 0.75, every 0402 chip on the reference board 0.33-0.45: a size rule alone
      would list every 0402, whose body is as small). New `heat-sinked lands` section: a land >= 4 mm2 (a pad
      number's pads together: an edge SMA's 2 is four) joined solid, not through thermal spokes, to >= 50 mm2
      of its net's fill over every layer it reaches, largest pour first, parts already in the reflow list left
      out. Reference board: D24 D25 added; 7 lands (J13.2 1613 mm2, BT1/BT2 179 and 80). 2026-11-25.
- [x] kicad-review/kpcb_jogs - partial jog collapses went down to 20% of the way (a 0.96 mm jog left at 0.77): an
      edit with no visible gain, each one DRC risk. Done: 90, 80 or 70% only (owner's call). On the way: the
      `tracks --kind jog` verdict promised `fix: smooth --jogs (A)` for a collapse `smooth` refuses (plane neck
      or a bend inside its own antipad): it now runs the pass's own `keeps` + `neck_ok` and says why instead.
      Cusp selftest updated, `kpcb tracks jog antipad cusp` added. 2026-11-25.
- [x] kicad-review/kpcb_tracks - `corners` counted a corner whose short leg ends before the two legs' inner edges
      cross: its end cap fills the inside of the turn, so the copper reads as a blob, not a V (5 of the
      reference board's 6 `acute` rows, checked in close-up views: 0.2 mm stubs of 0.8-1.3 mm tracks into a
      via or pad centre). Done: `cap_rounds` (the edges cross (r1 cos a + r2) / sin a out along leg 1), in the
      census and smooth's corner pass alike. Reference board: acute 6 -> 1 (D27-K at U23.4, a real V), 46-90
      deg 21 -> 6 (the 15 dropped have 1-11 um legs or a 0.12 mm stub). Selftest `kpcb tracks acute stub cap`.
      2026-11-25.
- [x] kicad-review/kpcb_smooth - `smooth --all` 145 -> 85 s on a reference board scratch, output identical bar
      the new segments' random uuids: `pass_chains` reuses a chain's re-lay when the chain and every track and
      via within reach of its Clear box are as in an earlier round (rounds 2-3 re-solved all 1,710 chains),
      and the corners/square/joints/pads/micro passes copy the tracks as loaded instead of a second
      `Board(path)` (0.8 s each). `load_sexp` keeps the last big file as marshal bytes, so a re-read of one
      pass's hidden scratch board (never disk-cached) is a fresh tree at load speed. A boxed no-op run: 6.4 s.
      Round 1's solves remain (BACKLOG). 2026-11-25.
- [x] kicad-review/kpcb_tracks - `--kind pad` reloaded the board for `pass_pads` (it edits its board): now a
      shallow copy with its own track dicts. 1.68 -> 1.11 s on the reference board, output identical.
      2026-11-25.
- [x] kicad-review/kpcb_copper - `_label` scanned every pad, fill (sorted per call), ideal node and via per dead
      branch: per-node first-hit maps built once per `dead_copper`. GND 1.44 -> 1.28 s (second build 0.64 ->
      0.49), identical. The fill-to-fill touch test stays open. 2026-11-25.
- [x] kicad-review/kdoc - real-PDF extraction had no test. Done: `kdoc_pdf` writes a two-page PDF with the
      stdlib (p1 Helvetica text, p2 no text layer); `kdoc index real pdf` (2 pages, `scan 1/2`) and `kdoc grep
      real pdf`, skipped with a line when poppler is missing. 2026-11-25.
- [x] kicad-review/tests - the route suite's in-process checks built boards in the temp root, so their rules
      came from whichever suite wrote a `.kicad_pro` there first (3 `WARN` lines on a full run). Done: their own
      `inproc/` dir with a rules-free `.kicad_pro` + `.kicad_dru` (and the hole board's project written before
      it is read). No WARN; 370/370. The backlog's selftest-split entry was already done by 4399250.
      2026-11-25.
- [x] kicad-review/tests - `selftest.py` (3056 lines, 238 KB) was touched by 21 of the last 30 commits and was
      the most-grepped file in skill sessions (~50 grep/sed calls a run to find where a command's cases and
      builders sit): its cases were appended in date order, every tool interleaved in one 1235-line `main()`,
      and its docstring's "one line in CASES" no longer held. Done: split by a script into the runner
      (`selftest.py`), `st_common.py` (paths, `run`, `check`, shared builders) and one `st_*.py` per tool
      family (knet, kpcb read-only, kpcb copper, kpcb edits, schematic tools, kfp/kdoc/kdrc), each a
      `suite()` generator: cases, `yield`, then its ad-hoc checks. Proven a pure move: the same 309 cases
      (label, argv, exit, needles), byte-identical fixtures after the build phase, every result line kept.
      Then: cases run in parallel (chains by overlapping temp paths, plus env vars like KDOC_CACHE that the
      tool's source reads; `-j 1` for serial): 32 s -> 7 s, `verify.sh` 8 s; 10 runs at `-j 24` all green.
      Default output is FAIL lines + the total (`-v` for every line; sessions used to `| head` it, which hid
      the failures at the end). `--list` prints each case's file:line. A needle may be `!absent` or a
      callable, so the six label-specific checks in the run loop moved into their cases. New coverage check:
      every tool command (a `CMDS` key or `--help` choice) has a case and a line in its reference. It found
      the router lint never checked kpcb/knet/kdoc/ksch commands (their `--help` prints the docstring, so no
      choices were read; now taken from `CMDS`), 6 commands without a case (`knet unconnected`, `kpcb
      unplaced`/`review`, `ksch syms`/`help`, `kdrc flags`: cases added; the kicad-cli ones are `NO_CASE`),
      and `kdrc both` / `ksch check` missing from their references (added). The self-test section of
      recipes.md (developer-only text in a reference board sessions read) moved into the docstring;
      CLAUDE.md and skill-improver point at `--list`. Goldens on the reference board 39/39 + 18/18
      unchanged. 2026-11-25.
- [x] kicad-review/kdrc - `--baseline` could not tell a report from another kicad-cli build (the JSON says only
      `10.99.0`): kicad-nightly upgraded mid-session (6416 -> 6896, 2026-11-25) and every later run read 199+
      new `line_width` rows against r0.json. Done: `--report` adds `kicad_build` (`kicad-cli version --format
      about`), and `--baseline` prints a `!!` line naming both builds when they differ. kdrc selftest check.
      2026-11-25.
- [x] kicad-review/kcommon - `FILE` with no command (`knet.py X.net`, `kpcb.py X.kicad_pcb`) printed argparse's
      usage block and "required: cmd" (2 sessions in 30 days, each a retry). Done: `parse_args` prints the
      `--help` text under `TOOL.py: error: no command given`, exit 2, for every tool; a mistyped command
      still gets argparse's `invalid choice`. Selftest `knet no cmd`. 2026-11-25.
- [x] kicad-review/kcommon - `kid()` built the whole `kids()` list to take [0] (175k calls a Board load): an
      early-exit loop. Board load 0.344 -> 0.327 s on the reference board, byte-identical. 2026-11-25.

- [x] kicad-review/kdrc - every writer prints `verify: kdrc.py OUT drc ...` and recipes.md runs DRC on each
      step's `-o n.kicad_pcb`, but kicad-cli reads the rules from `<stem>.kicad_pro` only: beside
      `parsnip.kicad_pro` that board was checked on KiCad's defaults (the 2026-11-25 clean-up pass read 944
      errors, 1183 new vs the baseline, for 39 harmless edits; the unedited board renamed read 947). Done:
      `drc` runs a board with no .kicad_pro of its own, beside exactly one project, as that project's board
      in a temp `copy_project` (`--refill-save` copies it back; a git-tracked board is still refused) and
      names the borrowed rules in its header. Same pass: 124 -> 124, 0 new. 2026-11-25.
- [x] kicad-review/kpcb_board - a custom pad's stroked `gr_poly` primitive was read without its stroke
      (gr_rect/circle/line had it): 8 pads on the reference board (TPS2595 U15) read 0.05 mm small all round,
      so `smooth` laid +5V 0.053 mm from U15.7 (DRC 0.1). Done: each stroked edge adds a box half the width
      out. Ad-hoc selftest check. 2026-11-25.
- [x] kicad-review/kpcb_smooth corners - the corner pass cut a corner where a 0.3 mm neck meets a 0.8 mm run,
      laying the connector at the wide width where only the neck cleared (`Clear` passes samples on the old
      centreline): +5V 0.058 mm from 5V_RAW (rule 0.127) and a mask bridge at U15. The census already
      names such a corner `width step`. Done: `corner_nodes` skips a width step. Ad-hoc check. 2026-11-25.
- [x] kicad-review/kpcb_route Grid - the router grid (route, smooth's `Clear`, place, stitch, jogs) painted
      holes into the via raster only, so a track kept off a PTH by ring + copper clearance (0.25 + 0.1) but
      not by the hole rule (0.28 from the drill): `smooth --jogs` slid the USB pair to 0.271 mm from U5's EP
      thermal via. Done: every foreign drill paints `_hole_clr` (moved here from kpcb_smooth) + w/2 into the
      track rasters (a soft via's into its soft raster). Ad-hoc check. 2026-11-25.
- [x] kicad-review/kpcb reroute - kept any route whose length + 1.5 mm per via dropped 5%: SDA/SPI_CS went
      95.8 mm / 1 via -> 78.4 mm / 8 vias, 45 mm of it on the In1/In2 planes at 0.15 mm, weaving through the
      densest block (seen side by side); ANT_DETECT 2 -> 5 vias. Higher `--via-cost 6 --inner-cost 3` still
      gave 5-7 vias. Done: also refused when it adds a via, adds > 0.5 mm on an inner plane layer, or runs
      > 1.5 mm per pad thinner than the net's narrowest; the line names which. 2026-11-25.
- [x] kicad-review/kpcb zones - "what cuts the ground plane" had no command: the 2026-11-18 4-vs-6-layer
      session regexed the board file for track mm per layer (In1 2202 mm on 61 nets), and `zones` printed 56
      rows of 0-2% power pours with edge margins that mean nothing for them (long net names broke the columns).
      Done: a non-GND pour under 5% folds into one `+ N local pour(s)` line per layer (`--all` a row each,
      `--json` unchanged plus a `planes` key); net column sized to the names; a **plane layers** section per
      layer where one net's fill covers > 30% (the `--voids` test): pieces, other nets' track mm and count,
      the five longest. Reference board: 70 rows -> 25 lines, In1 reads 2202 mm / 61 nets as the session found.
      Selftest case `kpcb zones planes` (the voids fixture gains a 1 mm2 +5V pour). 2026-11-25.
- [x] kicad-review/kpcb check ESD (new rule) - no placement rule checked that a TVS/ESD clamp sits at the
      connector it protects. Done: per connector pin on a net with a clamp (value/MPN ESD, TVS, TPDn, PESD,
      USBLC, SRV05, RCLAMP, PRTR, SMF/SMAJ..., with a GND pad; its own supply pin by `SUP_PIN` skipped; DNP
      skipped), the straight-line distance to the nearest clamp pad, worst net per (connector, clamp); WARN past
      `--esd` (10 mm, kpcb.json) or when an IC's pad is > 1 mm nearer the pin than the clamp. Per connector, so
      a shared I2C bus with a clamp per connector reads each against its own. Reference board: 4 WARN (J4.3 20 mm
      from D28; J1.6, J16.3, J7.B7 10.6-12.5 mm). Selftest case `kpcb check ESD` (crtyd fixture). 2026-11-25.
- [x] kicad-review/kpcb place - on a placed part `place REF` never showed where it sits, so a ranked spot could
      not be read against it (one session ran `place R4 --near` 8 times). And once `--max` rows were shown,
      all blocked, the first CLEAR spot was not printed though `-o` writes it (R44 on the reference board).
      Done: a `now` row scored the same way, and a last line counting clear spots with a shorter ratsnest
      (ratsnest, not score: the anchor term pulls every spot to the middle of a long net, which made C116 read
      "better elsewhere" at 8.0 vs 2.6 mm); the first clear spot always prints. Scoring moved into one
      `score_at`. Selftest case `kpcb place now`. 2026-11-25.
- [x] kicad-review/kpcb assembly (new) - "how hard is this board to hand-assemble" had no command: two
      reference-project sessions (2026-11-12 PCBWay quote, 2026-11-19) wrote 7 inline scripts over
      `Board.fps` with hand-typed package-name regexes (`QFN|DFN|SON|LGA|...`), and the first said its
      filter "missed three parts that are just as hard". Done: `kpcb.py FILE assembly` (`kpcb_assembly.py`)
      reads geometry only: parts to fit per side (not DNP, in the BOM), BOM lines, SMD/THT pads (a plated
      hole numbered as an SMD pad is a thermal via), counts by Fab body size, and per footprint and side the
      parts that need paste + reflow or hot air: an SMD pad wholly inside the Fab outline (not for an
      edge-launch part) or ringed by the other pads (an exposed pad, also without a Fab outline), or pitch
      <= 0.5 mm; finest pitch first, with pitch, smallest pad, pads under, body. The reference board: 21
      rows / 33 parts in 0.5 s, every part of the session's hand list (incl. the no-Fab easyeda QFNs) plus
      J7 and RN1 (0.5 mm pitch). Selftest case `kpcb assembly`, in GOLDEN. 2026-11-19.
- [x] kicad-review/selftest - knet's `comp`, `net`, `pin`, `find`, `notes`, `sheets` had no case (knet comp
      18 calls, knet net 23 in the reference project's 30 days). Done: one case each on `selftest.net` /
      the repeated-sheet project (its root sheet gains a 1 mm text note, so `notes` prints a SMALL one).
      `unconnected` and kpcb `unplaced`/`review`/`height` stay goldens-only (they need a real board).
      2026-11-19.
- [x] kicad-review/kpcb tracks - each shown `jog` row scanned the whole board: `blockers` ran the clearance
      rule and an exact distance for every via, track and pad (1.2M rule look-ups for 171 rows), and `verdict`
      built a fresh Clear (a 0.1 s raster) per jog though jogs share chains (171 jogs, 118 chains). `tracks
      --max 999` took 19.6 s on the reference board (11 such calls in the transcripts), `--kind jog --max 999`
      13.4 s. Done: `blockers` skips an item whose box is beyond its clearance of the changed polyline's box
      (distance >= the axis gap, so exact) and memoises the rule per (net, kind, own clearance); the display
      keeps one Clear per chain (`verdict(cks=)`); Grid's `paint` skips a shape wholly left or right of its
      raster and, with `vias=False`, the via raster's rule look-ups. Now 12.0 s and 7.5 s, `smooth --jogs`
      20.3 -> 16.6 s; `tracks`, both `--max 999` outputs and the `smooth`/`smooth --jogs` boards (fresh uuids
      aside) byte-identical. 2026-11-18.
- [x] kicad-review/kpcb_copper - a second Copper of the same net (`clip_only`'s clip-free build, `review`'s
      two) redid the fill-to-fill touch test, ~0.35 s of GND's 0.75 s build. Done: the result is memoised per
      PolyIndex pair (stale exactly when `_pidx` is). `net GND` 2.38 -> 2.01 s, `review` 3.32 -> 2.89 s,
      identical output. 2026-11-18.
- [x] kicad-review/kdoc - the most-called tool (311 calls in 8 days on the reference project: grep 183,
      text 58, page 48) had one CLI selftest case, a usage error; the `text DOC 5-7` crash of 2026-11-13 was
      in an untested path. Done: `kdoc_docs` builds an uploader page container (3 pages, an image) and a
      csv in a temp `KDOC_CACHE` (the suite never touches `~/.cache/kdoc`), plus a doc whose source is then
      deleted; 12 cases: index, grep (line-wrap, dash and `keep-out` folding, `-p`, no hits), `text DOC 2-3`,
      `page DOC p1`, near, toc, csv, list (source gone), prune. 2026-11-18.
- [x] kicad-review/kpcb tracks - `--kind K` printed only K's rows but ran the whole census first (12 s on
      the reference board; 17 of 34 `tracks` calls in a week passed `--kind`), and a misspelt kind listed
      nothing. Done: `census_rows(kinds=)` runs only the passes the asked kinds need (`cleanup`/`deadend`
      ~5 s, corner kinds and `zonepts` ~1 s), the header counts only those kinds, `--kind` is checked by
      argparse (exit 2, the kinds listed). Every kind's rows and header line byte-identical to the full
      census on the reference board; the full census unchanged. 2026-11-17.
- [x] part-search/alt - `alt` held only the ratings LCSC lists; JLC lists more for some parts. Done:
      `_merge_jlc` adds JLC's ranked parameters LCSC lacks (C408972 now holds Voltage Dropout <= 125 mV,
      C89600 Resistance Tolerance), skipping a JLC alias of an LCSC name (`standby current`, `Voltage -
      Supply`) and text no rule ranks (`Noise`); one cached JLC call `jlc_annotate` made anyway. C85402 now
      holds JLC's Junction Capacitance <= 152 pF (finds C20235797), and the TVS/ESD "lists no capacitance,
      so none is held" note no longer prints when a junction capacitance is held. 2026-11-17.
- [x] tools - an improvement run had to be scoped by hand each time. Done: `.claude/agents/skill-improver.md`,
      a project-scoped agent (not shipped with the plugin) that surveys BACKLOG Open, usage.py over every
      transcript dir that ran the tools, output size, runtime, selftest coverage and churn, picks 1-3 by
      evidence over effort, implements and verifies under CLAUDE.md, commits per CLAUDE.local.md's git rule,
      logs leftovers to BACKLOG. It never asks questions (AskUserQuestion disallowed). 2026-11-17.
- [x] part-search/bom - pricing N boards with a variant on some, across suppliers, took two hand-written
      scripts (a per-sheet buy list, an LCSC vs DigiKey.ca comparison) and a browser session. Done: `bom
      --sheet-qty SHEET=N` (a sheet and its children bought for N boards; per-board cost of the base and each
      variant), every line buys up to a price break when that costs less (also `check`), `--vs digikey,mouser`
      (exact-MPN offers with stock, no-code MPN parts included, cheapest supplier set with config.json
      `shipping`), `--alt N` (`alt` on the N costliest lines, saving per line), `--lcsc-csv OUT` (LCSC BOM tool
      upload). Offline selftest: breaks, sheet matching, split with and without free-shipping thresholds.
      2026-11-17.
- [x] part-search/alt - a part whose LCSC record lists no parameters (C113132, a 470 nH 2% wirewound) held
      only its package, so a 400 ohm ferrite bead came back as its drop-in. Done: `alt` takes JLC's parameters
      when LCSC lists none, and refuses when nothing beyond the package is held.
      2026-11-17.
- [x] kicad-review/kfp_vendor - `vendor` skipped stock footprints, so a stock part whose 3D model KiCad never
      shipped had to be copied by hand (lib file, board lib_id, sch Footprint field, board-side overrides).
      Done: `vendor REF.. [--model PATH]` vendors the named parts' footprints whatever their library (stock, or
      one in no table: the board copy is written), every instance of that footprint moving with it; `--model`
      replaces their missing model (else their only one), PATH copied in like any outside model. Moved stock
      footprints drop out of the "Update Footprint would change" list. Selftest: a library-less footprint with a
      missing model, dry run, apply, result. 2026-11-15.
- [x] kicad-review/router - the inline scripts usage.py counted, checked against the commands. Done: `knet bom
      --csv BOM.csv` cross-checks a fab BOM CSV against the netlist per ref (either side only, MPN / LCSC /
      DNP, column names KiCad's, JLC's and others'; `R1-R4` ranges; exit 2 on a difference; the reference board's
      427 refs agree); `knet summary` prints the next free number per prefix; `kfp libs` lists parts with no 3D
      model (padless art left out); FP answers `vars()`, `dict()` and `.items()` too (5 of the 29 raised). Router
      rows for all three, plus the existing `where --pads`. 2026-11-15.
- [x] kicad-review - the ad-hoc query import and its data model (FP, pad, track, via, fill, zone and
      Netlist fields) moved from recipes.md into SKILL.md, so they load with the skill: usage.py found 235
      inline scripts in 65 sessions, many opening with a `dir()` probe, while recipes.md was read 5 times.
      `print(fp)` shows ref, value, layer, position and pad count instead of `<FP object>`; selftest checks
      it. 2026-11-14.
- [x] tools - `tools/usage.py PROJECT_DIR [--since D] [--dev] [--max N]`: the transcript mining behind the two
      entries below, kept. Per tool and command call counts, Skill loads and reference reads; CLI crashes by
      frame + exception and argparse errors, each marked `[script changed since]` when git touched the script
      after the last one; -h lookups; inline scripts importing the skill modules (how many raised and why, the
      model attributes and internals they reach for, the newest few). Skill-development sessions (an edit under
      skills/<name>/) are left out; duplicated tool_use ids count once. `--selftest` (synthetic transcript) and
      pyflakes run in verify.sh; CLAUDE.md's backlog rule points at it. 2026-11-14.
- [x] kicad-review/kpcb - what a month of inline library scripts kept re-deriving (~200 in the reference
      project's use sessions, 1 in 10 raising). Done: `where REF --pads` lists every copper pad (num, xy, layers,
      size, rot, pin, net; `--origin` applies); `net NET` adds one `zonedef` line per zone (uuid, priority, layers,
      name, outline bbox), the lookup scripts did by uuid; FP and Zone answer `f['pads']`, `z['net']`, `.get()`
      (the guesses that raised), the tuple unpack unchanged. Router: `copper` (box / point, --net, --layers) gets
      its own row instead of the head of the `edit` row, which now points at `edit`'s own op list (-330 chars).
      2026-11-14.
- [x] kicad-review + part-search - papercuts mined from a month of the reference project's sessions (3840 tool
      calls). Done: (1) `-h`/`--help` failed with "the following arguments are required" on knet, kpcb, kdoc and
      kcap unless FILE and CMD were both given (~17 wasted calls); `kcommon.parse_args` now answers it first for
      the add_help=False parsers, and `TOOL FILE CMD -h` prints only CMD's docstring entries (`doc_for`). (2)
      kpcb's docstring lacked review, sync, zones, ampacity, vias, copper, edit, fatten, stitch. (3) `kdoc.py text
      DOC 5-7` raised ValueError (only `-p 5-7` took a range) and a bad page token crashed `_pagespan`; the
      positional page goes through `_pageset`. (4) `kpcb summary` printed one line per zone (101 of 136 lines on
      the reference board): one line per layer, net xN. (5) recipes.md's ad-hoc import says which fields are
      attributes and which dict keys (`b.fps['C29']['pads']` and `zone.net` crashed inline scripts), and `Zone`
      has `.net` / `.layers`. 2026-11-14.
- [x] kicad-review/kpcb - `tracks --kind cleanup` GUI check, follow-ups. Done: (1) reran the 341e42d~1 board in
      10.99 with "Refill zones" ticked (KiCad asked to refill out-of-date fills: yes) and "inside pads" off: the same
      result as the unticked runs, 0 merges, the same 12 tracks + 2 vias deleted; the refill only regenerated one
      unrelated teardrop. (2) a `deadend` row now says when KiCad's dangling pass differs from it, from ripup's
      prune run over the row as it lies (`prune(test=)`, no _newly_dead: KiCad keeps a cycle whose every end
      joins something): `KiCad's Cleanup takes 4 of its 23 (its pour holds the rest)` (+BATT), `... and 1 more it
      then leaves dangling: 894570b6` (-BATT; the earlier entry put that 31 um stub on +BATT), `takes UUID whole
      (it cannot cut a track back)`. Both reference rows match the GUI item for item. Found on the way: prune
      let one item credit both ends of a track (KiCad's TestTrackEndpointDangling credits the nearer, getMinDist),
      so `ripup --deadend` left that stub: it now deletes the 10 KiCad does; dead_copper's "join piece on the
      attach node" clause took a whole track when only one piece of it was the loop, and a cut-back keeping zero
      length now reads wholly dead. 2026-11-13.
- [x] kicad-review/kfp - `vendor --apply` rewrote every `.kicad_sch` under the project dir, backups in ./orig/
      included. Done: the sheet set is the hierarchy (project root and top-level sheets, then each Sheetfile
      relative to the sheet naming it, as eeschema loads them; a flat glob only when no root is known), for the
      Footprint fields and the symbol plan alike. 2026-11-13.
- [x] kicad-review/kfp - `vendor` called a board copy that only LACKS a field both stock copies have "a local fix".
      Done: `_adds` pairs each board-only pad with a library twin of the same number whose fields are a strict
      superset; when nothing is board-only otherwise the row reads `stale: the board copy only lacks what stock
      has, nothing board-only: worth pulling` (reference board FID1-FID6, `pad_prop_fiducial_glob`). 2026-11-13.
- [x] kicad-review/kpcb - `movecheck` "new hits only" hid a clash the part already had. Done: the current spot's
      hits are named first; one a candidate keeps prints `STILL` and blocks it (exit 2, and `--scan` counts it).
      2026-11-13.
- [x] kicad-review/kpcb - `movecheck` ignored a pad's own `(clearance X)`. Done: pads carry `lclr` (pad, else
      footprint `(clearance)`); `_clearance_fn`'s clr takes o1/o2 and, as KiCad's drc_engine, the larger override
      REPLACES netclass and rules, floored at the board min_clearance (not max(netclass, local): a local 0.1 on a
      0.2 class is 0.1 in KiCad). movecheck, route, smooth and jogs pass it. Reference FID6: its current spot
      already reads 0.55 mm from a GND via, needs 0.60. 2026-11-13.
- [x] kicad-review/kpcb - `freebox f W H` crashed (IndexError) on art left of the outline. Done: a raster span's
      end is clamped to its start, so a negative end no longer shrinks the row via slice assignment. 2026-11-13.
- [x] kicad-review/kpcb - confirm `tracks --kind cleanup` in the GUI. Done: ran Tools -> Cleanup Tracks & Vias in
      10.99 (g8304096633) on a private Xvnc display (`Xvnc :99 -rfbport -1 -rfbunixpath`, its own
      KICAD_CONFIG_HOME, xdotool aimed at :99 only) on scratch copies of the reference board at 341e42d~1. KiCad
      merged 0 of the 22 predicted joints: testMergeCollinearSegments asks the whole net island (GetConnectedItems
      returns the cluster) on every layer, and ZONE::HitTest is the OUTLINE within max(w/2, 0.1 mm) (a corner
      within 2x), so teardrops hold joints near pad/via entries; PAD::HitTest(pos, acc) takes every padstack layer.
      cleanup_rows now models both (teardrop outlines kept by the loader as a 4th tuple element), keys joints by
      exact nm (a 1.4 nm leg merged that the 1 um buckets never saw), builds KiCad's min/max merged box from
      either pair order (`sub-um leg` = may), and lists zero-length segments. Result: the board predicts 0 (GUI:
      0); with every zone stripped, all 14 + 15 "merges" rows merged in two GUI runs, no "may" row is wrong.
      Dangling: the -BATT deadend row went exactly; on the +BATT row (with a pour) KiCad took only the tips past
      the pour, plus a 31 um attach stub inside the track it hangs off (documented in kpcb.md). 2026-11-13.
- [x] kicad-review/kpcb - no way to carry a verified scratch result onto the real board: replaying the command log
      diverges (fresh uuids per run, refilled vs stale fills), and the scratch kicad-cli saved must never be handed
      back. Done: `kpcb.py BOARD diff SCRATCH --patch [--base COPY] -o OUT` - by uuid, the tracks and vias SCRATCH
      dropped/changed/added (verbatim text; the changed copper's teardrops dropped), its changed zones' layers,
      fill settings (fillet) and outline spliced into BOARD's own zone text with the fill dropped, added zones
      unfilled; `--base` (the copy SCRATCH started from) carries only SCRATCH's changes and keeps what BOARD changed
      since (a clash is left as BOARD has it; without it a note says BOARD's later edits are overwritten); OUT is
      re-read and checked item by item. Reference board (HEAD): a refilled, kicad-cli-saved `ripup --deadend`
      scratch patched back in 2.8 s, 33 changes, byte-identical to the direct `ripup -o`. 2026-11-13.

- [x] kicad-review/kpcb - a `tracks` `ends at a pad edge ... fix: smooth --pads` row named a fix the pass then
      declined ("0 of 2"): GND's stub from Q2.2's centre ends in its own pour (a pour tie, not a graze). Done:
      `pad_ends` (the rows and `smooth --pads`) skips an end inside its own net's saved fill, and a listed row is
      priced when shown (the pass run once on a fresh copy): PPHV at U8.9's custom pad now reads `smooth --pads
      finds no clear way onto the centre: by hand`. 2026-11-13.
- [x] kicad-review/kpcb - `smooth --micro` tilted neighbours by fractions of a degree (its 0/45/90 check tolerated a
      30-50 um end move on a long track): 54 merges took the board's 0.02-2 deg slants 22 -> 44. Done: the merge is
      angle-exact - the neighbours slide along their own lines onto one end (a via centre never moves, a pad end
      only within its pad) or onto where their lines cross within 0.15 mm; a stub off a via centre its neighbour
      does not point at, a chamfer whose merge leaves a 90 and a micro lane jog are left and say so. Reference
      board (HEAD): 29 merged + 10 deleted (was 58 + 10), slants 22 -> 22, kdrc 0 new, unconnected 2 -> 2.
      2026-11-13.

- [x] kicad-review/kpcb - `tracks --kind deadend` / `ripup --deadend` missed a dead power band: a `route +BATT` band
      round a 39 mm B.Cu run, hanging off one 4-via cluster in a pad and serving no pad, listed only as the 2.2 mm
      stub past it; and `ripup` left -BATT's first 0.13 mm segment (bb0f2c8e, inside the trunk's end cap). Done
      (`dead_copper`): a via cluster (neighbours <= 1 mm, all within 2 mm, joining exactly the same copper) is one
      node, so a pour off it is a leaf, not a cycle through the pad and the In2 pour its barrels also join; a
      parallel leaf (a track weaving out of the band and back) lives while its node does but no longer holds that
      node up; a script band (`route`/`fatten` zone) is never a pad's heatsink; a join piece left on the attach node
      that meets only the branch goes with it. Reference board (HEAD): one 47.1 mm, 57 mm2 row with zone cba8f8d8,
      -BATT 19.2 mm with bb0f2c8e; `ripup --deadend` then 32 items, refill + kdrc 0 new, unconnected 2 -> 2; the
      current board's rows unchanged (BT1-- pour islands stitched across 4 mm stay live). 2026-11-13.
- [x] kicad-review/kpcb - `tracks` off-45 tolerance (0.3 deg) hid sub-degree slants on long runs (I2C_HOST_SDA
      10.35 mm at 0.28 deg, 50 um of drift). Done: `octi` also wants the far end within 10 um of the 0/45/90 line
      (`tracks` row `10.35 mm, end 50 um off 90 deg`), so `smooth` now folds such a drift into a neighbouring leg
      (3V3_GNSS 37 um, +3V3_EXT 14 um). Found on
      the way: the chain DP itself laid crooked runs (GPIO_10 three segments -> one 32.8 mm at 89.74 deg, 149 um of
      drift) and doglegs with a leg under 0.05 mm (-BATT: a 42 um leg, a new `stub` row): both refused now;
      `--square` dragged a co-track at the moved end off 0/45/90 (never now) and on a tie moved the end in the
      smaller pad (SDA: off D29.3's anchor; now the bigger pad's end moves). `zoneshape --redraw` keeps the angle-only
      test (a knee for a drift is a < 0.3 mm edge). 2026-11-13.
- [x] kicad-review/kpcb - `tracks` had no row for a joint held only by overlapping copper (two same-net dead ends
      sharing no vertex, Q11-G B.Cu 247 um apart held by 3 um of cap; SDA 50 um), which also splits the chain so
      the jog in it is never a lane jog; and its follow-up, no writer for them. Done: `joint` rows (end, gap,
      priced when shown: `fix: smooth --joints` or why not) and `smooth --joints` (in `--all` after `--micro`),
      angle-exact: both dead ends along their own lines onto where they cross, collinear ends end to end, an
      off-axis T onto the other's axis; a near-parallel pair is left (a snap tilts one); only a dead end moves,
      `Clear`, no leg < 0.05 mm, moves bounded by the joint (gap + w/2), not 0.15 mm: Q11-G's in-line close is
      0.247. Reference board (HEAD): 10 rows, 3 closed (one under its pour), kdrc 0 new; the rest are runs
      5-35 um apart side to side (re-lay by hand) or a 1.15 mm -BATT joint whose close leaves a 0.05 mm leg.
      2026-11-13.
- [x] kicad-review/kpcb - `tracks` never listed a signal end inside a small pad but off its anchor (folded into
      "more end inside their pad off centre: fine"). Done: `anchor` rows - a signal net's dead end inside a pad
      <= 1.5 mm across (custom primitives counted), >= 10 um off its anchor, largest first, fix by hand; a bend
      vertex inside the pad (two tracks meet: the route goes on) is not an end, and an end whose cap also grazes the
      track's own via (Q11-G at U8.24) still counts. Reference board (HEAD): 137 rows, U8.24 45 um and the SDA spur
      450 um off D29.3 among them. 2026-11-13.
- [x] kicad-review/kdoc - no way to drop cache slots whose source file was deleted: `list` kept them and unscoped
      `grep` hit them. Done: `kdoc.py prune [-d NAME]` removes them; `list` tags them `source gone`, and a grep with
      hits in one names it. 2026-11-13.

- [x] kicad-review/kpcb - the heavy writers were slow on the reference board (17 MB): smooth 46 s, widen 17 s, stitch
      GND 15 s, reroute 230 s. Done: route's Grid rejects pads and tracks on raw coordinates before any bbox (exact:
      a pad's rotated half-extent is <= sx/2 + sy/2), fill_rows assigns slices, astar keeps best cost in per-layer
      arrays (came holds the same keys, so `g.seen` is unchanged), pad_box skips bbox() for plain pads; smooth's
      Clear samples each segment once, checks a 0/90 segment by raster slices (its samples visit exactly the cells
      between its ends), skips the contact test when the net has no own copper there, and paints its 0.5 mm allow
      zone as one capsule per run of touching samples (a disk per 0.01 mm sample was 98% overlap; <= 25 nm
      scallops); `_netclass` / `_clearance_fn` / `_hole_clr` read the project once per board (widen re-read the
      .kicad_pro ~20k times); stitch scans the r1 box, not the window. smooth 46 -> 30 s, --all 54 -> 39, --jogs
      21 -> 16, widen 17 -> 12, stitch GND 15 -> 9.7, --sparse 28 -> 21, reroute (3 nets) 55 -> 45; every output
      byte-identical HEAD vs now (written boards too, fresh uuids aside), goldens 38/38 + 18/18. 2026-11-13.
- [x] kicad-review/kcommon - `load_sexp`'s disk cache was a FIFO: prune drops the oldest write, and 18 MB snapshots
      of one-off scratch copies (reroute's temp boards, test copies) filled the 512 MB cap and evicted the board read
      daily. Done: a hit bumps the snapshot's mtime (LRU), and a writer's hidden scratch board (basename `.`*) is
      never snapshotted. 2026-11-13.
- [x] kicad-review/knet, kdoc - `knet FILE path|net|find|walk|diff|divider|comp|pin|around` and `kdoc grep|near`
      without their arguments died with an IndexError (comp/pin/around printed nothing). Done: the docstring's usage
      line, exit 1; `knet diff MISSING.net` says "no such netlist" (exit 3) instead of a traceback, and `kpcb diff
      MISSING` says "no such board" instead of a bare path. 2026-11-13.
- [x] kicad-review/kpcb, ksheet - `--box`, `--avoid`, `--keep` were split by each command itself: `--box 1,2` was
      an IndexError deep in the `tracks` census, `--box abc` a ValueError, a reversed box an empty region. Done:
      `kcommon.box_arg`, an argparse type checking 4 numbers per box (`;`-joined for --avoid/--keep) and sorting
      the corners. 2026-11-13.
- [x] kicad-review/kpcb - `reroute` cut the router's failure line at 70 chars, mid-sentence, before the width and
      the "boxed in by" list that names the blockers. Done: the whole line, minus the net prefix the row already
      shows. 2026-11-13.

- [x] kicad-review/kpcb - `tracks --kind cleanup` calibrated against master's `pcbnew/tracks_cleaner.cpp`,
      `pcb_track.cpp`, `seg.cpp`, `connectivity_data.cpp` and the dialog's defaults (read 2026-11-13; a GUI run is
      still impossible headless). Done: a merge needs both legs unlocked, nm-equal width and within 1 nm of one
      line (SEG::ApproxCollinear: the old 0.05 deg test, taken at the 1 um-rounded joint, both kept 1-27 nm bends
      and missed exactly-45 deg sub-0.1 mm legs, read as 0.1-0.6 deg); the joint is held only by another track's
      END or a via centred exactly there (IsPointOnEnds, nm) or a same-net pad within w/2 (it was any track within
      w/2, any via disk, a pad only containing the joint); a segment touched by any different-width trace never
      starts a merge (per segment, not per end), so one necking leg reads "may merge (its pair order decides)" and
      two never merge; joints freed by the dangling pass (dead tracks, vias met on one layer) merge, as KiCad
      merges again after it. Redundant vias as KiCad walks them (stacked with the same layers: each unlocked one
      meeting another goes, the last survives unless a locked twin does; before the dangling pass); "tracks fully
      inside pads" rows say that option is off by default; duplicates and in-pad deletes skip locked tracks.
      Reference board 21 -> 22 rows (18 merges, 4 "may"; 10 old rows dropped by the rules above, 11 new), each
      traced to its rule. 2026-11-13.
- [x] kicad-review/kpcb - `zoneshape ZONE --redraw`: the outline redrawn along what its fill keeps to anyway.
      Done: `dontcare` (a Grid raster of a 0-width centreline: other-net copper + clearance, edge band, off-board;
      plus no-pour rule areas and saved fills of its own net or of a zone out-ranking it, ZONE::HigherPriority
      with the uuid tie-break); corners go greedily where the region between the old run and one new edge (two
      on 0/45/90, tried first) is all don't-care save within eps of the old run, a same-net pad never changes
      side, no new edge crosses the ring. `-o`'s refill proof now prints the net's copper round the zone (union
      of fills, mm2) and, with --redraw, fails if it moves > 1% / 0.5 mm2. Reference board on a scratch copy:
      +5V F.Cu 115 -> 71 vertices (plain 84), off-45 55 -> 3; PPHV B.Cu 79 -> 56, off-45 47 -> 13; VSYS In2 85 ->
      51 (plain 53: the band crosses a GND plane it out-ranks, so its outline is the design); refilled copper
      moved +0.41/-0.42/+0.06 mm2, pieces the same. Courtyards are not boundaries (they shape no fill). Found on
      the way: the `zonepts` census row now names `--redraw`. 2026-11-13.

- [x] kicad-review/kfp - `vendor`, the symbol half. Done: symbols from a library outside the repo, and those
      kicad-cli ERC calls `lib_symbol_mismatch` (edited in the schematic, any library; `--erc REPORT.json` reads a
      saved report), are written from each schematic's lib_symbols cache into `--symlib NICK` (default: the one
      repo library in sym-lib-table; Reference cut to its prefix, units renamed with the symbol); lib_id re-pointed
      on every instance and cache entry (lib_name dropped), Footprint fields inside the copied symbols follow the
      vendored footprints in library and cache; a second version of a name gets NAME_1, NAME_2; NICK's own copy is
      replaced only when nothing in the project uses it; sym-lib-table entry added if missing. Reference board on a
      scratch copy: 24 symbols (2 replacing), 32 instances in 9 sheets; kverify ERC 0 added, 20 lib_symbol_mismatch
      removed, sync identical, netlist only the 18 re-pointed Footprint fields; stable and nightly kicad-cli load the
      library and nightly's re-save is identical; a second dry run has nothing to do. Found on the way: stock symbol
      libraries were listed as "outside the repo" (`kicad_env` knew no stock symbol dir; now `KICADn_SYMBOL_DIR`
      too), "models: 0 file(s) from ," printed an empty list, and "already self-contained" was claimed while a KEEP
      left a model outside the repo. 2026-11-13.

- [x] kicad-review/kdrc - `--baseline` given kdrc's own `--json` output (finding rows, a list) crashed in
      `_against` (`'list' object has no attribute 'get'`). Those rows carry no items to match on, so it now exits
      naming the right file (`--report OLD.json`, kicad-cli's raw report); `--help` says "not --json output".
      Selftest check added. 2026-11-12.
- [x] kicad-review/kpcb - silk tables. Done: `Board` reads PCB `(table ...)` on *.SilkS: the table box in
      `.silk` (so `freebox` and `diff` see it), its drawn border/header/separator lines as board art, each visible
      cell (span 0 = covered, skipped) a `silktexts` entry of kind `table` placed by its justify and margins (a
      knockout cell is its filled box). `silk` reviews cells like board text (named "table cell"; a knockout cell
      skips the h/9 text-knockout margin rule), `silk --box` lists them, `diff` counts "table cells N added, M
      removed", `view --layers silk` now draws board art (it drew none) and knockout fills. Writer: `pinlabels REF
      --table [TITLE] [--title-col]` emits one upright table, a row per pin on the pin pitch, knockout title row or
      a row-spanned title column on the far side; refuses a horizontal pin row (10.99 skews rotated tables), an
      uneven pitch or a pitch too small for the text. KiCad nightly loads and plots its output. Reference board:
      the 9 existing tables add 26 SILK-UNDER (cells inside J1/J3/J14/J15 courtyards, same rule board text
      already got) and 4 SILK-SIZE (0.9 mm cells). The checkpoint diff now reads "45 added, 4 removed" cells
      where it read "0 new". 2026-11-12.
- [x] kicad-review/kpcb - `diff` pairs footprints by uuid, then by reference among the leftovers; a reference
      change on a paired footprint shows as `renamed` (not for `~dupN` renumbering). The entry's repro (one of nine
      REF** logos deleted) went from 5 moved/3 rotated/1 flipped/1 removed to 1 moved/1 removed. 2026-11-12.
- [x] kicad-review/kpcb - `zoneshape`: zones ranked by how far from hand-drawn (vertices, off-45 edges,
      micro-edges < 0.3 mm, faceted arc runs, vertices the proposal drops, count over the `zonepts` designer bar);
      `zoneshape ZONE [--eps E] [-o OUT]` proposes one outline (unround, Douglas-Peucker at E, octilinear at E/2),
      dry-run checks simple / same-net pads still inside / on the board / max move, and with -o writes it (fill
      dropped), refills temp copies of input and OUT with kicad-cli and compares the net's copper pieces (OUT is
      never the kicad-cli save). `tracks --kind zonepts` points at it. Reference board: 85 of 102 zones flagged;
      `route VSYS` In2 85 -> 53 vertices, off-45 44 -> 10, moved <= 0.092 mm, VSYS one piece after refill. Not
      done: snapping to natural boundaries (new entry). 2026-11-12.
- [x] kicad-review/kpcb - KiCad's Cleanup Tracks & Vias cannot run headless: `kicad-cli-nightly api-server`
      (10.99.0-6416) answers RunAction("pcbnew.GlobalEdit.cleanupTracksAndVias") with "RunAction is not available
      in headless mode" (probed with a stdlib nng/protobuf client); stable 10.0.8's SWIG pcbnew has no cleaner;
      kicad-cli `pcb` has no cleanup. So `tracks --kind cleanup` predicts it from its rules: a collinear same-width
      joint with nothing else there (merged), a segment wholly inside one same-net pad (deleted, the "end pushed to
      the pad centre" case), duplicate segments and vias, a via on a same-net through-hole pad. Reference board: 21
      collinear joints. Calibration against a real GUI cleanup is a new entry. 2026-11-12.
- [x] kicad-review/kfp - `vendor [--lib NICK] [--models DIR] [--apply [--force]]`: footprints from libraries
      outside the repo copied into the project library (the library file when the board matches it, else the
      board's copy, so Update Footprint is a no-op), 3D models outside the repo copied with .step/.wrl siblings and
      re-pointed to ${KIPRJMOD} (a different file already there is never overwritten), lib ids re-pointed on the
      board and in placed symbols' Footprint fields (never the lib_symbols cache), fp-lib-table entry added if
      missing; lists symbol libs used from outside the repo; ranks stock footprints Update Footprint would change
      by direction against a second KiCad install's stock copy. Dry run by default, refused while KiCad holds the
      project. Reference board on a scratch copy: 13 footprints, 18 model files, 19 paths, 18 Footprint fields;
      kverify ERC 0 added + sync identical, `kpcb diff` no change, `kfp diff` identical; U1/fiducials/logos read
      as local fixes. Found on the way: `kfp libs` labelled untracked repo models "outside the repo". Symbol
      copying is a new entry. 2026-11-12.
- [x] part-search/part.py - LCSC "Other Suppliers" marketplace: `POST wmsc.lcsc.com/ftps/wm/search/third`
      (found by logging the product page's XHR with Patchright; plain HTTP works). `show` lists each offer
      (seller code, stock, MOQ, lead days, price at the buy qty vs LCSC's own, FAR UNDER below 0.5x, batch);
      `bom`/`check` add a line under a LOW STOCK row, `alt` under its header; `pick` never ranks on it. The
      detail's `hasThirdPartyStock` reads false on parts with offers, so it is not used as a gate. Offline
      selftest case on a recorded answer. 2026-11-12.
- [x] part-search, kicad-review/kdoc - Patchright: no integration needed today. `ds` over the reference
      board's 151 LCSC parts hit no 403 or challenge page (one part has no link at all), and the marketplace
      endpoint is plain HTTP. endpoints.md records the method instead: capture a blocked page's XHR once in a
      stealth browser, then call its JSON endpoint from urllib. 2026-11-12.
- [x] repo - CI matrix 3.12 + 3.15 (README follows). 3.15.2 runs both selftests clean; its only new warning was
      `os.path.commonprefix` deprecation in part.py's TI datasheet naming, now an inline common-prefix length.
      2026-11-12.
- [x] repo - CI. Done: `.github/workflows/verify.yml` runs `tools/verify.sh` on Python
      3.12 and 3.14 (ubuntu-latest, actions/checkout v7.0.1 and setup-python v7.1.0
      pinned by SHA, read-only token, no persisted credentials, librsvg for the PNG
      views); `.github/dependabot.yml` bumps the actions weekly with a 7-day
      cooldown. actionlint and zizmor clean. Found on the way: the selftest failed
      3 `kpcb view` PNG cases wherever `rsvg-convert` is missing (the docs call it
      optional); it now skips them with a note. Python 3.12 checked locally on a
      runner-like PATH and empty HOME: 285/285 + 3 skipped. 2026-11-12.
- [x] kicad-review - selftest.py and its fixtures moved from `references/` to `tests/`,
      so `references/` holds only the manuals the router links. Paths in recipes.md,
      README, BACKLOG and verify.sh follow; verify.sh still baselines against a REV
      from before the move. 288/288, goldens 38/38 + 18/18 unchanged. 2026-11-12.
- [x] part-search brands.md - covers resistors and capacitors now, not only MLCC:
      20 makers plus 8 part-researched ones, each scored 2Q+D+E (quality, checkable
      data, conduct) with sourced, dated facts (cartel pleas and fines, civil
      settlements, RBA membership, ownership, HQ). Adds a price-tie rule (within
      10% on `ext`: highest score wins), and SKILL.md routes ties to it. `pick` stays
      brand-blind. YAGEO and Walsin drop below the old "tier 1": no per-part
      DC-bias tool found for either. 2026-11-12.
- [x] repo - split out of the board project the tools were developed on. Done:
      the skills live under `skills/` as a Claude Code plugin (`.claude-plugin/`),
      with a generic `pcb-reviewer` agent, `tools/verify.sh` (goldens on any project
      via `PROJECT_DIR [EXTRA.json]`) and `tools/pack.sh` (claude.ai bundles in
      `dist/`). Project specifics stripped: example file names are `board.*`,
      measurements are quoted as "the reference board", selftest's golden commands
      that named a ref or net moved to the project's EXTRA.json. part-search
      currency/site default to USD/US (config `currency`/`site` or
      `$PARTSEARCH_CURRENCY`/`$PARTSEARCH_SITE`); the fx line follows the chosen
      currency. kicad-cli falls back to the macOS bundle / Windows install path when
      it is not on PATH. part-search finds kicad-review through a symlinked install's
      real path. 2026-11-12.
