# Changelog

Landed backlog entries and fixes, newest at the top. Reference only: the open
work is in a local, untracked `BACKLOG.md`.

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
