# claude-pcb-skills

[![verify](https://github.com/LimesKey/claude-pcb-skills/actions/workflows/verify.yml/badge.svg)](https://github.com/LimesKey/claude-pcb-skills/actions/workflows/verify.yml)

Claude Code skills for reviewing and editing KiCad projects and for choosing
electronic parts. They give Claude command-line tools that read the netlist,
board, footprints, schematics and datasheets directly, so an answer about what
connects to what, or what sits where, comes from the files on disk instead of
from memory or a screenshot.

Everything is stdlib Python. There is nothing to `pip install`.

## What's inside

**`kicad-review`** (skill)

| tool | reads | answers |
| --- | --- | --- |
| `knet.py` | netlist `.net` | connectivity, pins, values, BOM, rails, divider voltages, I2C addresses, power tree, what a reversed battery does |
| `kpcb.py` | board `.kicad_pcb` | placement, clearance, edges, courtyards, pour coverage, trace current (IPC-2221 and a field solve through the real fills), 50 ohm RF lines, silkscreen, board height, routing quality. Its writers place, route, widen, stitch and clean up tracks on a scratch copy (`-o OUT`, never the input) |
| `kdrc.py` | board + schematics | KiCad's own DRC and ERC, folded and suppressible, stale zone fills flagged |
| `kfp.py` | `.kicad_mod`, `.pretty`, board | footprint lint (KLC courtyard, fab, silk, mask, paste), edits, and why a board footprint no longer matches its library |
| `ksheet.py` | `.kicad_sch` + netlist | where a part sits on its sheet, drawing lint, PNG of a region |
| `ksch.py` | a small text spec | draws a circuit with real KiCad symbols |
| `kdoc.py` | datasheet PDFs | index once, then grep and render pages |
| `kmerge.py`, `kproj.py`, `kverify.py`, `kfront.py` | `.kicad_pro` + sheets | whole-project netlists for multi-root projects, sheet rename / reorder / renumber with proof nothing else changed, front-matter pages that quote stale refdes |

**`part-search`** (skill)

| tool | answers |
| --- | --- |
| `part.py` | LCSC / JLCPCB / DigiKey / Mouser search, parametric `pick` ("an MLCC, 4.7-100 uF, >= 25 V, 0805, cheapest in stock"), drop-in alternates, whole-board pricing, JLCPCB Basic vs Extended, footprint and value vs the assigned LCSC part, verified datasheet download |
| `kcap.py` | MLCC capacitance at the real DC bias, and voltage-stress life |

**`pcb-reviewer`** (agent): runs the whole review sequence on a project, filters
what the project has already accepted, verifies each finding against the
datasheet or the netlist, and returns a ranked report. It never edits files.

Things to ask once installed:

- "What does U2 pin 9 connect to?"
- "Is U8 too close to the antenna? Is there room for a 10 x 6 mm logo on the back?"
- "Where should the input and output caps of U13 go?"
- "Can the path from Q16 to R41 carry 6 A?"
- "Does the board pass DRC? Which PWR_FLAGs are redundant?"
- "Find me a 3.3 V LDO in SOT-23-5 with the lowest Iq."
- "Price the whole board for 5 units and tell me what blocks JLC assembly."

## Requirements

- **Python 3.12 or newer** (CI runs 3.12 and 3.15 on every push).
- **KiCad 10 `kicad-cli`** for DRC/ERC, multi-root netlists, plots and board
  height. Found on `PATH`, else in the macOS app bundle or a Windows install;
  `$KICAD_CLI` overrides. Files saved by a 10.99 nightly need
  `kicad-cli-nightly`, which the tools pick automatically.
- **poppler-utils** (`pdftotext`, `pdftoppm`, `pdfinfo`) for `kdoc.py`.
- Optional: `rsvg-convert` (librsvg) for PNG views, `tesseract` for
  `kdoc --ocr`, numpy to speed up `kpcb ampacity --fills`.
- `part-search` needs network access. LCSC and JLCPCB need no key; DigiKey and
  Mouser are optional (setup in
  [endpoints.md](skills/part-search/references/endpoints.md)).
- Developed on Linux. macOS should work. Windows is untested (the scripts call
  `ps` and assume POSIX paths).

## Install

**As a Claude Code plugin** (the skills show up as `pcb-skills:kicad-review` and
`pcb-skills:part-search`, plus the agent):

```
/plugin marketplace add LimesKey/claude-pcb-skills
/plugin install pcb-skills@claude-pcb-skills
```

**From a clone, by symlink** (what you want if you will edit the tools):

```bash
git clone https://github.com/LimesKey/claude-pcb-skills ~/src/claude-pcb-skills
S=~/src/claude-pcb-skills

# in one project only
mkdir -p .claude/skills .claude/agents
ln -s $S/skills/kicad-review $S/skills/part-search .claude/skills/
ln -s $S/agents/pcb-reviewer.md .claude/agents/

# or in every project
ln -s $S/skills/kicad-review $S/skills/part-search ~/.claude/skills/
```

Install both skills: `part-search` imports `kicad-review`'s netlist parser for
`bom`, `jlc` and `fpcheck`.

**On claude.ai**: `tools/pack.sh` zips each skill into `dist/NAME.skill`, which
you can upload as a custom skill.

## Setting up a project

1. **Export a netlist beside the board.** `knet` and `kpcb sync` read it:

   ```bash
   kicad-cli sch export netlist -o board.net board.kicad_sch
   ```

   A project with several top-level sheets (KiCad 10.99) needs the whole-project
   netlist: `python3 <kicad-review>/scripts/kmerge.py board-merged.net board.kicad_sch`.
   After that, any loader re-runs kmerge itself when a sheet is newer than the
   netlist (about 3 s; `KREVIEW_NO_REGEN=1` turns it off).

2. **Optional per-board config**, JSON files beside the board. Commit them.

   | file | holds | reference |
   | --- | --- | --- |
   | `kpcb.json`, `knet.json` | board defaults (rails, current per net, thresholds) and a `suppress` list of confirmed non-bugs | [kpcb.md](skills/kicad-review/references/kpcb.md), [knet.md](skills/kicad-review/references/knet.md) |
   | `kdrc.json` | DRC/ERC classes or single findings to mute, ERC roots | [kdrc.md](skills/kicad-review/references/kdrc.md) |
   | `fpcheck.json` | footprint/package pairs confirmed equivalent, written by `part.py fpcheck --confirm` | [part-search SKILL.md](skills/part-search/SKILL.md) |

3. **Datasheets** go in `docs/datasheets/` (one subfolder per schematic sheet
   works too). `part.py ds C42409135 --save` downloads a verified PDF there and
   indexes it for `kdoc.py grep`.

4. **part-search defaults** to USD and DigiKey's US site. Set your own in
   `~/.config/partsearch/config.json`, for example
   `{"currency": "CAD", "site": "CA"}` (or `$PARTSEARCH_CURRENCY` /
   `$PARTSEARCH_SITE`).

5. **Recommended `.claude/settings.json`** for a symlinked install: allow the
   scripts without a prompt, and refresh a multi-root netlist at session start.

   ```json
   {
     "permissions": {
       "allow": [
         "Bash(python3 .claude/skills/kicad-review/scripts/*)",
         "Bash(python3 .claude/skills/part-search/scripts/*)",
         "Bash(kicad-cli *)"
       ]
     },
     "hooks": {
       "SessionStart": [{"hooks": [{"type": "command",
         "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 .claude/skills/kicad-review/scripts/kmerge.py --if-stale board-merged.net board.kicad_sch; exit 0"}]}]
     }
   }
   ```

6. **Tell Claude about the board in the project's `CLAUDE.md`**: the stackup,
   the findings you have accepted, and the decisions that are settled. The
   `pcb-reviewer` agent reads it and skips what it lists. Keep coordinates and
   connectivity out of it: those go stale, and the tools are the source of truth.

## Repository layout

```
.claude-plugin/        plugin.json + marketplace.json
skills/
  kicad-review/
    SKILL.md           router: which tool answers which question
    scripts/           the tools; kcommon.py is the shared parser and models
    references/        one manual per tool, recipes.md, gotchas.md
    tests/             selftest.py and its fixtures
  part-search/
    SKILL.md
    scripts/           part.py (+ part_*.py modules), kcap.py
    references/        pick, best, endpoints, kcap
agents/pcb-reviewer.md
tools/verify.sh        every check a change must pass
tools/pack.sh          dist/*.skill bundles for claude.ai
CHANGELOG.md           what landed
CLAUDE.md              rules for working on the skills
```

## Development

```bash
tools/verify.sh                         # both selftests, pyflakes, router lint (~30 s)
tools/verify.sh HEAD ~/my-board         # + goldens on a real project
tools/verify.sh HEAD ~/my-board x.json  # + that board's own golden commands
python3 skills/kicad-review/tests/selftest.py -k 'kpcb edit'   # a subset, ~1 s
```

Exit 0 means everything passed, 1 a test failed, 2 only the goldens moved.
GitHub Actions runs `tools/verify.sh` (no goldens) on Python 3.12 and 3.15 for
every push and pull request; Dependabot keeps the pinned actions current.
The goldens run HEAD's scripts and the working tree's on the same frozen copy of
the project and diff the outputs: a pure refactor must read N/N unchanged.
`x.json` lists commands that name the board's own refs or nets, as argv lists:
`[["kpcb.py", "{pcb}", "ic", "U13"], ["knet.py", "{net}", "divider", "U8.TS"]]`.

Bugs and ideas go in a local, untracked `BACKLOG.md`; the workflow is in
[CLAUDE.md](CLAUDE.md). Numbers the references quote for "the reference board"
come from the 4-layer, ~470-footprint board the tools were developed on.

## License

MIT, see [LICENSE](LICENSE).
