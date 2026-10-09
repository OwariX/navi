#!/bin/sh
# NAVI's hard guard as the plugin's PreToolUse hook. It guards a Claude Code conversation only while that conversation
# runs a NAVI council (it has run `navi` itself): your own work in Claude Code, `/init` and the rest, is never touched.
# Most folders aren't NAVI projects at all: answer at once, without starting Python. In one that is (a folder NAVI lists
# in ~/.navi/roots, or an old .navi/ here or above), scripts/navi.py decides, reading the tool call from stdin.
# A run NAVI started (NAVI_HOST_ID) brings its own guard: answering here too would report every ruling twice.
[ -n "${NAVI_HOST_ID:-}" ] && exit 0
here=$(cd "$(dirname "$0")/.." && pwd)
roots="${NAVI_HOME:-$HOME/.navi}/roots"
for start in "$PWD" "${CLAUDE_PROJECT_DIR:-}"; do
  [ -n "$start" ] || continue
  start=$(cd "$start" 2>/dev/null && pwd -P) || continue      # the real path, as NAVI lists it (/tmp is /private/tmp on macOS)
  hit=
  if [ -f "$roots" ]; then
    while IFS= read -r r; do         # (the loop reads the list on its stdin: Python starts after it, with the tool call)
      [ -n "$r" ] || continue
      case "$start/" in "$r"/*) hit=1; break ;; esac
    done < "$roots"
  fi
  [ -n "$hit" ] && NAVI_HOOK_FROM=plugin exec python3 "$here/scripts/navi.py" hook
  d=$start
  while [ -n "$d" ]; do
    [ -f "$d/.navi/policy.json" ] && NAVI_HOOK_FROM=plugin exec python3 "$here/scripts/navi.py" hook
    [ "$d" = / ] && break
    d=$(dirname "$d")
  done
done
exit 0
