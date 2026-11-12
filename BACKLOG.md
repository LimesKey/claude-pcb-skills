# Skill backlog

Bugs, papercuts and feature ideas for the `kicad-review` and `part-search`
skills. During board work, log them **when noticed** and move on; during skill
work, fix them on the way. Append newest at the bottom of Open. When one lands,
cut it from here and add it, with a `Done:` line (what changed, date), to the
**top** of [CHANGELOG.md](CHANGELOG.md). Fixes made on the way get an entry too.

While iterating on one fix, `python3 skills/kicad-review/references/selftest.py -k LABEL`
runs only the matching cases plus the cases that write their inputs (~1 s; `--list`
names them). Verify any skill change at the end with one command (all must pass):

```bash
tools/verify.sh                          # selftests, pyflakes, router lint
tools/verify.sh HEAD ~/my-board [x.json] # + goldens: HEAD's scripts vs the working tree
```

Format per entry:

```
- [ ] <skill>/<script> - <what's wrong or wanted>. Repro/context: <one line>.
      Logged <YYYY-MM-DD>.
```

## Open

<!-- append entries here -->
