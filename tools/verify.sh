#!/usr/bin/env bash
# Every check a skill change must pass, in one command:
#
#   tools/verify.sh [REV [PROJECT_DIR [EXTRA.json]]]
#
# Always: both selftests (fixtures, offline), pyflakes, and the SKILL.md router lint.
# With PROJECT_DIR (a real KiCad project, the .kicad_pro's stem names the board and
# netlist: STEM.kicad_pcb, STEM-merged.net else STEM.net) it also runs the goldens:
# REV's scripts (default HEAD, or a directory holding a copy of this repo) record the
# real board's outputs on a frozen copy of the project, then the working tree's
# scripts diff against that same copy, so KiCad saving mid-run can't fake a diff.
# EXTRA.json adds the board's own golden commands (see selftest.py's docstring).
#
# Exit 0 = all pass, 1 = a test, lint or pyflakes failed, 2 = only the goldens moved.
# A pure refactor must read N/N unchanged; a feature's diff is expected - read it,
# don't waive it. Known non-regressions: a part.py diff that is only `fx: 1 USD = ...`
# and the prices it scales (the FX rate refreshes daily: rerun), and a golden command
# REV doesn't know yet (it records as REV's usage error until committed). Snapshot
# the repo (`cp -r . /tmp/S`) before a refactor on top of uncommitted work and pass
# that directory as REV, since HEAD would then diff the earlier work too.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
K=skills/kicad-review P=skills/part-search
REV=${1:-HEAD} PROJ=${2:-} EXTRA=${3:-}
[ -n "$EXTRA" ] && EXTRA=$(realpath "$EXTRA")
fail=0 moved=0

echo "== kicad-review selftest"
python3 "$ROOT/$K/references/selftest.py" | grep -v '^ok ' || fail=1
echo "== part-search offline selftest"
python3 "$ROOT/$P/scripts/part.py" selftest --offline || fail=1
echo "== pyflakes"
if command -v uvx >/dev/null; then PF=(uvx pyflakes)
elif python3 -m pyflakes --version >/dev/null 2>&1; then PF=(python3 -m pyflakes)
else PF=(); echo "skipped: neither uvx nor python3 -m pyflakes"; fi
[ ${#PF[@]} = 0 ] || { "${PF[@]}" "$ROOT"/skills/*/scripts/*.py "$ROOT/$K/references/selftest.py" && echo clean; } || fail=1

if [ -n "$PROJ" ]; then
    PROJ=$(cd "$PROJ" && pwd) || exit 1
    pro=$(ls "$PROJ"/*.kicad_pro 2>/dev/null | head -1)
    [ -n "$pro" ] || { echo "no .kicad_pro in $PROJ"; exit 1; }
    stem=$(basename "$pro" .kicad_pro) pcb=$stem.kicad_pcb net=$stem-merged.net
    [ -f "$PROJ/$net" ] || net=$stem.net
    [ -f "$PROJ/$pcb" ] && [ -f "$PROJ/$net" ] || { echo "goldens need $PROJ/$pcb and a netlist ($stem-merged.net or $stem.net)"; exit 1; }
    echo "== goldens: $REV's scripts vs the working tree, on a frozen copy of $PROJ"
    F=$(mktemp -d) H=$(mktemp -d)
    trap 'rm -rf "$F" "$H"' EXIT
    if [ -d "$REV" ]; then cp -r "$REV/skills" "$H/"
    else git -C "$ROOT" archive "$REV" skills | tar -x -C "$H" || exit 1; fi
    for x in "$PROJ"/*; do                  # project files copied (frozen), folders linked
        if [ -d "$x" ]; then ln -s "$x" "$F/"
        else case $x in *.kicad_*|*.net|*.json|*lib-table) cp -p "$x" "$F/";; esac; fi
    done
    for T in "$H" "$ROOT"; do               # REV records, the working tree diffs
        (cd "$F" && python3 "$T/$K/references/selftest.py" --golden g "$pcb" "$net" ${EXTRA:+"$EXTRA"} \
                    | grep -v '^same') || moved=1
        (cd "$F" && python3 "$T/$P/scripts/part.py" selftest --golden pg "$net" \
                    | grep -v '^same') || moved=1
    done
fi

if [ $fail = 1 ]; then echo "== FAIL"; exit 1; fi
if [ $moved = 1 ]; then echo "== tests pass; goldens CHANGED vs $REV (read the diff above)"; exit 2; fi
echo "== all pass${PROJ:+, goldens unchanged vs $REV}"
