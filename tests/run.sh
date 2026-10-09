#!/bin/sh
# NAVI end-to-end tests: a real browser (Playwright + Chrome) and a real pseudo-terminal, against a FAKE `claude`
# (tests/fake-claude) so nothing costs tokens. Everything runs in a throwaway folder; your own ~/.config/navi is untouched.
#
#   tests/run.sh             run everything (installs playwright into tests/e2e/node_modules on first run)
#   tests/run.sh ui demo     run only some suites: ui themes councilgen sources examples enginesui phone updates writing demo headless permit server tuidemo update install engines enginewizard tour replay wizard terminal tui
HERE=$(cd "$(dirname "$0")" && pwd)
NAVI="$HERE/../scripts/navi.py"
SP=$(mktemp -d /tmp/navi-tests.XXXXXX)
mkdir -p "$HERE/bin" "$SP/home" "$SP/proj/.navi/sessions/20261006-144220" "$SP/shots"
ln -sf "$HERE/fake-claude" "$HERE/bin/claude"; ln -sf "$HERE/fake-codex" "$HERE/bin/codex"; ln -sf "$HERE/fake-gemini" "$HERE/bin/gemini"
chmod +x "$HERE/fake-claude" "$HERE/fake-codex" "$HERE/fake-gemini"
printf '#!/bin/sh\nexec python3 "%s" "$@"\n' "$NAVI" > "$HERE/bin/navi"; chmod +x "$HERE/bin/navi"
export PATH="$HERE/bin:$PATH"
cp -R "$HERE/fixtures/session/." "$SP/proj/.navi/sessions/20261006-144220/"
cp "$HERE/fixtures/policy.json" "$SP/proj/.navi/"
echo 20261006-144220 > "$SP/proj/.navi/current"
echo '{"setup_complete": true, "vignette": 0, "moderator": "headless", "guides": false, "permissions": "ask", "engines_on": ["claude", "local", "codex", "local-codex", "gemini"]}' > "$SP/home/config.json"   # the tour suite turns guides on for itself; Ask me: the suites test its cards; every engine in use: the suites switch between them
export NAVI_CONFIG="$SP/home/config.json" NAVI_LIBRARY="$SP/home/agents" NAVI_COUNCILS="$SP/home/councils" NAVI_NO_INTRO=1 BROWSER=true
export NAVI_HOME="$SP/navihome"      # projects' NAVI data: never your ~/.navi
export NAVI_KEEP_DOT_NAVI=1          # the shared suites use the old <project>/.navi layout on purpose (install_test tests the move)
export FAKE_LOG="$SP/fake.log" FAKE_SLEEP=6
# the engines: fakes on the PATH (above), and a Codex, a Gemini and an Ollama of their own, never yours
mkdir -p "$SP/codex" "$SP/ghome/.gemini"; echo '{}' > "$SP/codex/auth.json"; echo '{}' > "$SP/ghome/.gemini/oauth_creds.json"
cat > "$SP/codex/models_cache.json" <<'JSON'
{"models": [{"slug": "gpt-test-sol", "display_name": "GPT-Test-Sol", "visibility": "list", "priority": 1, "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]},
            {"slug": "gpt-test-terra", "display_name": "GPT-Test-Terra", "visibility": "list", "priority": 2},
            {"slug": "gpt-test-sol-2", "display_name": "GPT-Test-Sol 2", "visibility": "list", "priority": 3},
            {"slug": "gpt-test-luna", "display_name": "GPT-Test-Luna", "visibility": "list", "priority": 4},
            {"slug": "gpt-hidden", "display_name": "Hidden", "visibility": "hide", "priority": 5}]}
JSON
P_OL=$(python3 -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])")
( python3 -I "$HERE/fake_ollama.py" "$P_OL" "$SP/ollama.log" > /dev/null 2>&1 & )
export CODEX_HOME="$SP/codex" GEMINI_CLI_HOME="$SP/ghome" OLLAMA_HOST="127.0.0.1:$P_OL"
# the project is a git repo: main + feature/demo, one uncommitted change (the folder and branch UI shows all of it)
mkrepo() { (cd "$1" && git init -q -b main && git config user.email t@navi.test && git config user.name navi-tests &&
            echo hello > index.html && printf 'echo hi\n' > start.sh && git add index.html start.sh && git commit -qm "first page" &&
            git branch feature/demo && echo more >> index.html); }
mkrepo "$SP/proj"; mkdir -p "$SP/other"
# a skin of your own (docs/THEMES.md), with a CSS line that tries to load from outside: NAVI must strip it
NAVI_DIR="$SP/proj/.navi" python3 "$NAVI" theme new acme --name "Acme" >/dev/null
printf '@import url("https://evil.example/x.css");\n:root[data-theme="acme"] .composer{background-image:url(https://evil.example/p.png)}\n' >> "$SP/home/themes/acme.css"
# a second, still-open session with pace Quick (continuing it must keep that pace), started on main
NAVI_DIR="$SP/proj/.navi" python3 "$NAVI" init --task "a quick landing page" --council knights --pace quick >/dev/null
# ...which built two real project files: a page, and a script (NAVI must only ever show that one, never run it)
(cd "$SP/proj" && NAVI_DIR="$SP/proj/.navi" python3 "$NAVI" artifact architect index.html --title "the landing page" >/dev/null &&
 NAVI_DIR="$SP/proj/.navi" python3 "$NAVI" artifact architect start.sh --title "the start script" >/dev/null)

cd "$HERE/e2e"
[ -d node_modules/playwright ] || { echo "installing playwright..."; npm init -y >/dev/null 2>&1; npm i playwright >/dev/null 2>&1; npx playwright install chromium >/dev/null 2>&1 || true; }

free_port() { python3 -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])"; }
serve() {   # serve <port> <navi dir> [VAR=value ...]: start a NAVI server and wait until it answers FOR THIS DIR
  port=$1; dir=$2; shift 2
  ( env "$@" NAVI_DIR="$dir" python3 "$NAVI" serve --port "$port" > "$SP/serve-$port.log" 2>&1 & )   # subshell: no job noise on exit
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    curl -s "http://127.0.0.1:$port/session" 2>/dev/null | grep -qF "$(basename "$SP")/${dir#"$SP"/}" && return 0; sleep 0.3; done
  echo "server on $port did not start for $dir (port taken by another run?)"; exit 1
}
P_UI=$(free_port); P_HL=$(free_port); P_WZ=$(free_port); P_PM=$(free_port)    # random free ports: parallel test runs never collide
cleanup() {   # stop only what the tests started: servers whose environment points into $SP (the terminal test's `navi` server too)
  for pid in $(pgrep -f "navi.py serve" 2>/dev/null); do
    case "$(ps eww -p "$pid" -o command= 2>/dev/null)" in *"$(basename "$SP")"*) kill "$pid" 2>/dev/null;; esac   # its env names $SP
  done
  pkill -f "$HERE/bin/claude" 2>/dev/null; pkill -f "fake_ollama.py $P_OL" 2>/dev/null; echo "scratch: $SP"
}
trap cleanup EXIT
# sources of truth: a Claude Code of its own (one MCP server, one skill) and a home with an Obsidian vault, never yours
mkdir -p "$SP/claude/skills/terraform-review" "$SP/vhome/Documents/Brain/.obsidian"
echo '{"mcpServers": {"team-wiki": {"command": "wiki"}}}' > "$SP/claude/.claude.json"; echo '# skill' > "$SP/claude/skills/terraform-review/SKILL.md"
serve "$P_UI" "$SP/proj/.navi" NAVI_OPEN_LOG="$SP/opened.log" CLAUDE_CONFIG_DIR="$SP/claude" NAVI_VAULT_HOME="$SP/vhome"
WANT="$*"; FAILED=""
want() { [ -z "$WANT" ] && return 0; case " $WANT " in *" $1 "*) return 0;; *) return 1;; esac; }
run() { name=$1; shift; echo "## $name"; "$@" || FAILED="$FAILED $name"; }

want ui       && run ui       node ui.js         "http://127.0.0.1:$P_UI/" "$SP/shots" "$SP"
want themes   && run themes   node themes.js     "http://127.0.0.1:$P_UI/" "$SP/shots"
want demo     && run demo     node demo.js       "http://127.0.0.1:$P_UI/" "$SP/shots"
want tour     && run tour     node tour.js       "http://127.0.0.1:$P_UI/" "$SP/shots"
want replay   && run replay   node replayshot.js "http://127.0.0.1:$P_UI/" "$SP/shots"
want councilgen && run councilgen node councilgen.js "http://127.0.0.1:$P_UI/" "$SP/shots"
want sources  && run sources  node sources.js    "http://127.0.0.1:$P_UI/" "$SP/shots" "$SP"
want examples && run examples node examples.js   "http://127.0.0.1:$P_UI/" "$SP/shots"
want enginesui && run enginesui node engines.js "http://127.0.0.1:$P_UI/" "$SP/shots"
want phone    && run phone    node phone.js      "http://127.0.0.1:$P_UI/" "$SP/shots"
want updates  && run updates  node updates.js    "http://127.0.0.1:$P_UI/" "$SP/shots"
want writing  && run writing  node writing.js    "http://127.0.0.1:$P_UI/" "$SP/shots" "$SP"
if want headless; then
  mkdir -p "$SP/hproj/.navi"; : > "$SP/hfake.log"; mkrepo "$SP/hproj"
  serve "$P_HL" "$SP/hproj/.navi" FAKE_SLEEP=20 FAKE_END=1 FAKE_LISTEN=1 NAVI_AFTER_END_WAIT=2 FAKE_LOG="$SP/hfake.log"
  run headless node headless.js "http://127.0.0.1:$P_HL/" "$SP/shots" "$SP/hfake.log"
fi
if want permit; then    # permission cards: the fake moderator runs three commands nothing allowed
  mkdir -p "$SP/pproj/.navi"; : > "$SP/pfake.log"; mkrepo "$SP/pproj"
  serve "$P_PM" "$SP/pproj/.navi" FAKE_PERMIT=1 FAKE_SLEEP=2 FAKE_END=1 NAVI_PERMIT_WAIT=10 FAKE_LOG="$SP/pfake.log"
  run permit node permit.js "http://127.0.0.1:$P_PM/" "$SP/shots" "$SP/pfake.log" "$SP/pproj/.navi"
fi
want server && run server python3 -I "$HERE/server_test.py" "$NAVI" "$SP" "$(free_port)"
want tuidemo && run tuidemo python3 -I "$HERE/tui_demo_test.py" "$SP"
want update && run update python3 -I "$HERE/update_test.py" "$NAVI" "$SP"
want install && run install python3 -I "$HERE/install_test.py" "$HERE/.." "$SP"
want engines && run engines python3 -I "$HERE/engines_test.py" "$NAVI" "$SP" "$(free_port)"
want enginewizard && run enginewizard python3 -I "$HERE/engine_wizard_test.py" "$SP"
if want wizard; then
  mkdir -p "$SP/wproj/.navi" "$SP/whome"; echo '{"setup_complete": false, "guides": false}' > "$SP/whome/config.json"
  serve "$P_WZ" "$SP/wproj/.navi" NAVI_CONFIG="$SP/whome/config.json"
  run wizard node wizard.js "http://127.0.0.1:$P_WZ/" "$SP/shots"
fi
if want terminal; then
  mkdir -p "$SP/tproj"; echo '{"setup_complete": true, "moderator": "terminal", "permissions": "ask", "engines_on": ["claude", "local", "codex", "local-codex", "gemini"]}' > "$SP/home/config.json"
  run terminal python3 -I "$HERE/term_start.py" "$SP/tproj" "$SP" knights "terminal e2e"
fi
if want tui; then     # the setting says "terminal": the TUI must still get a background moderator
  mkdir -p "$SP/uproj"; mkrepo "$SP/uproj"; echo '{"setup_complete": true, "moderator": "terminal", "permissions": "ask", "engines_on": ["claude", "local", "codex", "local-codex", "gemini"]}' > "$SP/home/config.json"
  run tui python3 -I "$HERE/tui_test.py" "$SP/uproj" "$SP"
fi
echo "screenshots: $SP/shots"
[ -z "$FAILED" ] && echo "ALL SUITES PASSED" || { echo "FAILED:$FAILED"; exit 1; }
