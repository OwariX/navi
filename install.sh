#!/bin/sh
# NAVI installer: puts a `navi` command on your PATH, links the skill into the agent programs you have (Claude Code,
# Codex, Gemini CLI), lets Claude Code run `navi` without a permission prompt on every call, and asks which engine NAVI
# runs on. Re-run it any time; it's idempotent.
#   ./install.sh                     everything (in a terminal it ends with `navi engine`, the engine wizard)
#   ./install.sh --engine local      pick the engine without the wizard (claude | local | codex | local-codex | gemini)
#   ./install.sh --no-wizard         don't ask anything (the engine is Claude, updates are announced; change both later)
#   ./install.sh --auto-update       NAVI installs new releases by itself (--no-auto-update: it only tells you)
#   ./install.sh --no-permissions    skip the Claude Code permission rules
#   ./install.sh --uninstall [--purge] [--yes]     take NAVI off this machine again (same as `navi uninstall`)
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
BIN="${NAVI_BIN:-$HOME/.local/bin}"
ENGINE=""; WIZARD=1; PERMS=1; AUTO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) shift; exec python3 "$DIR/scripts/navi.py" uninstall "$@" ;;
    --engine) ENGINE="$2"; shift 2 ;;
    --engine=*) ENGINE="${1#--engine=}"; shift ;;
    --no-wizard) WIZARD=0; shift ;;
    --no-permissions) PERMS=0; shift ;;
    --auto-update) AUTO=on; shift ;;
    --no-auto-update) AUTO=off; shift ;;
    *) echo "install.sh: unknown option $1 (see the top of install.sh)"; exit 2 ;;
  esac
done
command -v python3 >/dev/null 2>&1 || { echo "! NAVI needs python3 (3.9 or newer)"; exit 1; }

mkdir -p "$BIN"
cat > "$BIN/navi" <<WRAP
#!/bin/sh
exec python3 "$DIR/scripts/navi.py" "\$@"
WRAP
chmod +x "$BIN/navi"
echo "✓ navi command  -> $BIN/navi"

# The skill: Claude Code reads ~/.claude/skills, Codex and Gemini CLI read ~/.agents/skills (Codex also its own).
link() {
  mkdir -p "$1"
  if [ -L "$1/navi" ] || [ ! -e "$1/navi" ]; then
    ln -sfn "$DIR" "$1/navi"
    echo "✓ skill linked  -> $1/navi"
  else
    echo "! $1/navi exists and is not a link - left untouched"
  fi
}
[ -d "$HOME/.claude" ] && link "$HOME/.claude/skills"
[ -d "$HOME/.codex" ] && link "$HOME/.codex/skills"
{ [ -d "$HOME/.codex" ] || [ -d "$HOME/.gemini" ] || [ -d "$HOME/.agents" ]; } && link "$HOME/.agents/skills"

# Claude Code asks before every Bash command it hasn't been allowed. A council runs dozens of `navi` calls,
# so allow those once, in the user settings (nothing else is allowed here).
if [ "$PERMS" = 1 ] && [ -d "$HOME/.claude" ]; then
  python3 - "$DIR" <<'PY'
import json, os, sys
p = os.path.expanduser("~/.claude/settings.json")
try:
    s = json.load(open(p))
except Exception:
    s = {}
me = f"{sys.argv[1]}/scripts/navi.py"
rules = ["Bash(navi:*)", "Bash(navi *)", f"Bash(python3 {me}:*)", f"Bash(python3 {me} *)"]
allow = s.setdefault("permissions", {}).setdefault("allow", [])
new = [r for r in rules if r not in allow]
allow.extend(new)
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "w") as f:
    json.dump(s, f, indent=2)
    f.write("\n")
print(f"✓ permissions   -> {p} ({len(new)} navi rule(s) added)" if new else f"✓ permissions   -> already in {p}")
PY
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "! $BIN is not on your PATH. Add it:  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc" ;;
esac

# Which AI NAVI runs on: Claude, your own models through Ollama, Codex or Gemini.
if [ -n "$ENGINE" ]; then
  python3 "$DIR/scripts/navi.py" engine use "$ENGINE"
elif [ "$WIZARD" = 1 ] && [ -t 0 ] && [ -t 1 ]; then
  python3 "$DIR/scripts/navi.py" engine
else
  echo "· NAVI runs on Claude unless you pick another engine: navi engine"
fi
# Updates: by itself (like Claude Code), or a note on home and in the menu when one is out
if [ -n "$AUTO" ]; then
  python3 "$DIR/scripts/navi.py" update --auto "$AUTO"
elif [ "$WIZARD" = 1 ] && [ -t 0 ] && [ -t 1 ]; then
  printf "Update NAVI automatically when a new release is out? Never during a council. [Y/n] "
  read -r ans || ans=""
  case "$ans" in n*|N*) python3 "$DIR/scripts/navi.py" update --auto off ;; *) python3 "$DIR/scripts/navi.py" update --auto on ;; esac
fi
echo "Done. cd into any project and type: navi    (take it off again: navi uninstall)"
