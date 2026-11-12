# Changelog

Landed backlog entries and fixes, newest at the top. Reference only: the open
work is in [BACKLOG.md](BACKLOG.md).

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
