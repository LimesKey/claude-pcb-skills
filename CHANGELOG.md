# Changelog

Landed backlog entries and fixes, newest at the top. Reference only: the open
work is in [BACKLOG.md](BACKLOG.md).

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
