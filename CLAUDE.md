# claude-pcb-skills

Two Claude Code skills (`skills/kicad-review`, `skills/part-search`) and a
`pcb-reviewer` agent, shipped as a plugin. What each tool does: [README.md](README.md).

## Rules for skill work

- **Stdlib-only Python >= 3.12.** A third-party import must be optional
  (`try: ... except ImportError`); the selftest fails on any other.
- **Project-agnostic.** No board, refdes, net name or path from one project in
  logic or defaults. A refdes in a comment naming the case that motivated a rule is
  fine; quote measured numbers as "the reference board". A board's own config
  belongs in its `kpcb.json` / `knet.json` / `kdrc.json`, never in a script.
- Each `SKILL.md` is a router; the detail lives in its `references/*.md`. Read
  only the one you need.
- **Backlog:** read [BACKLOG.md](BACKLOG.md) (only Open; never read CHANGELOG.md
  to work it). Fix whatever else you find on the way if it is in a script already
  in context or is a small change the selftest covers; log it only if it needs a
  new script, new fixtures or a cross-script refactor. Every landed fix, queued or
  found, gets an entry at the top of [CHANGELOG.md](CHANGELOG.md).
- New behaviour gets one selftest case: grep `selftest.py` for the command and
  extend the fixture builder it uses (recipes.md, "self-test"). Iterate with
  `selftest.py -k LABEL`.
- Run `tools/verify.sh` once at the end, not per fix. When the change can move
  any tool's output, run it with a real project: `tools/verify.sh HEAD DIR
  [EXTRA.json]`. A pure refactor must read N/N unchanged.
- The writers (`-o OUT`) never modify their input.
