#!/bin/sh
# Zip each skill into dist/NAME.skill, the bundle claude.ai's skill upload takes.
cd "$(dirname "$0")/../skills" || exit 1
mkdir -p ../dist
for d in */; do
    d=${d%/}
    [ -f "$d/SKILL.md" ] || continue
    rm -f "../dist/$d.skill"
    zip -q -r -D "../dist/$d.skill" "$d" -x '*__pycache__*' '*.pyc' || exit 1
    echo "packed dist/$d.skill ($(du -h "../dist/$d.skill" | cut -f1))"
done
