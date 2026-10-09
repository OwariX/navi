#!/bin/sh
# Make a NAVI release: VERSION, a commit, the vX.Y.ZZZ tag and the GitHub release (its notes are the version's
# CHANGELOG.md section). Versions are MAJOR.MINOR.BUILD, BUILD three digits that count every release.
#   scripts/release.sh 0.9.002        (write its "## 0.9.002 (date)" section in CHANGELOG.md first)
set -e
cd "$(dirname "$0")/.."
V="$1"
echo "$V" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]{3}$' || { echo "usage: scripts/release.sh MAJOR.MINOR.BUILD (BUILD has three digits, e.g. 0.9.002)"; exit 1; }
git rev-parse -q --verify "refs/tags/v$V" >/dev/null && { echo "v$V is already released"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no -- . ':!VERSION' ':!CHANGELOG.md')" ] || { echo "commit your other changes first"; exit 1; }
NOTES=$(awk -v v="$V" '/^## /{p = index($0, "## " v " ") == 1 || $0 == "## " v} p' CHANGELOG.md | sed '1d')
[ -n "$NOTES" ] || { echo "CHANGELOG.md has no '## $V (date)' section yet"; exit 1; }
printf '%s\n' "$V" > VERSION
python3 - "$V" <<'PY'          # the Claude Code plugin carries the same version
import json, sys
p = ".claude-plugin/plugin.json"
d = json.load(open(p))
d["version"] = sys.argv[1]
open(p, "w").write(json.dumps(d, indent=2) + "\n")
PY
git add VERSION CHANGELOG.md .claude-plugin/plugin.json
git commit -q -m "Release $V"
git tag -a "v$V" -m "NAVI $V"
git push -q origin HEAD "v$V"
gh release create "v$V" --title "NAVI $V" --notes "$NOTES" >/dev/null
echo "released NAVI $V: $(gh release view "v$V" --json url -q .url)"
