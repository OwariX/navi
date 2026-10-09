"""The engines (scripts/engines.py), against fake programs and a fake Ollama: never yours.
usage: python3 -I engines_test.py <navi.py> <scratch dir> <port>    (tests/run.sh sets the PATH, CODEX_HOME, OLLAMA_HOST...)
- the module: tiers, every engine's command lines, models, environment, and how each one's output is read
- the CLI: navi engine list | use | test, --engine · the guard hook in Codex's dialect (no "ask" there)
- members from inside Codex's sandbox (no network there): NAVI outside it starts them, or says at once that it can't
- through the server: a council on each engine (Local's environment; Codex with a member run, its tokens and its thread
  resumed after the end; Codex's sandbox: Ask me, in the background, Allow all; Gemini), the engine test in Settings,
  and the generators on a local model"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

navi, sp, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
scripts = os.path.dirname(os.path.abspath(navi))
sys.path.insert(0, scripts)
os.environ["NAVI_CONFIG"] = f"{sp}/ehome/config.json"          # this suite's own settings
os.makedirs(f"{sp}/ehome", exist_ok=True)
json.dump({"setup_complete": True, "moderator": "headless", "guides": False, "permissions": "ask",
           "engines_on": list(E.ENGINES) if "E" in dir() else ["claude", "local", "codex", "local-codex", "gemini"]}, open(f"{sp}/ehome/config.json", "w"))
import engines as E  # noqa: E402

fails = []


def check(ok, what, extra=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"  · {extra}" if extra and not ok else ""))
    if not ok:
        fails.append(what)


cfg = {}
GUARD = {"hook": 'python3 "/x/navi.py" hook', "tools": "Bash|Read", "deny": ["Read(./.env)"], "permit": "", "permit_timeout": 60}

# ---------------------------------------------------------------- the persona checker's safety rule
import forge as Fg  # noqa: E402
check(not any(Fg.unsafe(t) for t in ("Never skip `navi gate` before reading a file.", "Do not bypass WARDEN.", "You never override the user.",
                                     "Never read .env or tfstate files.")),
      "persona safety: a rule to keep (never bypass WARDEN, never read .env) isn't flagged as unsafe")
check(all(Fg.unsafe(t) for t in ("Skip the gate for speed.", "Ignore the policy when reading.", "Read the .env file first.", "Never forget: skip the gate.")),
      "...an instruction to bypass the gate or read a secret still is")

# ---------------------------------------------------------------- the module
check(E.tier_of("Sonnet") == "balanced" and E.tier_of("fable") == "strong" and E.tier_of("qwen3:8b") == "" and E.tier_of("") == "",
      "tiers: Claude's names count as tiers, a model name isn't one")
check(E.valid_model("qwen3-coder:30b") and E.valid_model("strong") and E.valid_model("") and not E.valid_model("rm -rf /") and not E.valid_model("a b"),
      "a model is a tier, Claude's names or a model name (checked by shape)")
C, L, X, LX, G = (E.get(e) for e in ("claude", "local", "codex", "local-codex", "gemini"))
check((C.resolve(cfg, "strong"), C.resolve(cfg, "fable"), C.describe(cfg, "balanced"), C.member_alias(cfg, "fast"), C.member_alias(cfg, "")) ==
      ("opus", "fable", "Sonnet", "haiku", "inherit"), "Claude: strong is opus, fable stays fable, members registered by alias")
check((C.resolve(cfg, "auto"), C.member_alias(cfg, "auto"), L.member_alias(cfg, "auto"), C.describe(cfg, "auto"), E.valid_model("auto")) ==
      ("", "inherit", "inherit", "Auto · picked per task", True),
      "a seat on auto: registered without a model of its own (the moderator picks one per run), shown as picked per task")
cmd = C.moderator(cfg, prompt="P", model="balanced", effort="high", headless=True, conv="c-1", cont=False, perms="all", add_dirs=["/d"],
                  rules=["Bash(navi:*)"], guard=GUARD, agents="/a.json")
st = json.loads(cmd[cmd.index("--settings") + 1])
check(cmd[:2] == ["claude", "P"] and cmd[cmd.index("--model") + 1] == "sonnet" and "--session-id" in cmd and "bypassPermissions" in cmd
      and st["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == GUARD["hook"] and st["permissions"]["deny"] == GUARD["deny"]
      and cmd[-2:] == ["--allowedTools", "Bash(navi:*)"], "Claude: the command line (model by tier, guard hook and deny rules, rules last)", " ".join(cmd))

ms = L.installed_models(cfg)
names = [m["name"] for m in ms]
check(names[:3] == ["qwen3-coder:30b", "gpt-oss:20b", "qwen2.5:7b"] and "nomic-embed-text:latest" not in names
      and next(m for m in ms if m["name"] == "tinyllama:latest")["tools"] is False,
      "Local: Ollama's models, the best tool users first (no embedding models)", str(names))
tm = L.tier_models(cfg)
check(tm == {"strong": "qwen3-coder:30b", "balanced": "qwen3-coder:30b", "fast": "qwen2.5:7b"}, "Local: tiers suggested from what's installed", str(tm))
env = L.env(cfg)
check(env["ANTHROPIC_BASE_URL"] == "http://" + os.environ["OLLAMA_HOST"] and env["ANTHROPIC_AUTH_TOKEN"] == "ollama" and env["ANTHROPIC_API_KEY"] == ""
      and env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "qwen3-coder:30b-navi64k" and env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "qwen2.5:7b-navi64k"
      and env["ANTHROPIC_DEFAULT_FABLE_MODEL"] == "qwen3-coder:30b-navi64k" and env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "65536"
      and env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1" and env["CLAUDE_CODE_SUBAGENT_MODEL"] is None,
      "Local: Claude Code pointed at Ollama, every Claude name on a 64k copy of a local model, your key never sent, the window it has", json.dumps(env))
made = L.prepare(cfg)          # (another suite may have made one of them already: it's the same fake Ollama)
names = {t["name"] for t in E._get_json(L.url(cfg) + "/api/tags").get("models") or []}
check({"qwen2.5:7b-navi64k", "qwen3-coder:30b-navi64k"} <= names and L.prepare(cfg) == [],
      "Local: before a run it makes the 64k copies the tiers need, once", f"made {made}; has {sorted(n for n in names if 'navi' in n)}")
check(not any("navi64k" in m["name"] for m in L.installed_models(cfg)) and L.describe(cfg, "balanced") == "Balanced · qwen3-coder:30b",
      "...and they never show up as models of their own; you see your model's name")
check(L.member_alias(cfg, "balanced") == "sonnet" and L.resolve(cfg, "haiku") == "qwen2.5:7b" and L.describe(cfg, "strong") == "Strong · qwen3-coder:30b"
      and L.can["auto"] is False and L.efforts == (), "Local: members by alias, shown by their real model; no auto mode, no effort")
check(all(c[0] for c in L.checks(cfg)) and L.ask(cfg, "Reply with exactly these two words and nothing else: NAVI ONLINE") == "NAVI ONLINE",
      "Local: checks pass, and a question goes straight to Ollama")
mine = {"engines": {"local": {"models": {"strong": "gone:70b", "balanced": "qwen2.5:7b", "fast": "qwen2.5:7b"}}}}
check(any(not ok and "gone:70b" in what for ok, what, _ in L.checks(mine)), "Local: a tier model that isn't pulled is named, with the pull command")

check(X.tier_models(cfg) == {"strong": "gpt-test-sol", "balanced": "gpt-test-sol-2", "fast": "gpt-test-luna"},
      "Codex: tiers from its own model list (the hidden ones left out)", str(X.tier_models(cfg)))
cmd = X.moderator(cfg, prompt="P", model="strong", effort="high", headless=True, conv="", cont=False, perms="ask", add_dirs=[], rules=[], guard=GUARD, agents="")
hook = next(c for c in cmd if c.startswith("hooks.PreToolUse="))
check(cmd[:4] == ["codex", "exec", "--json", "--skip-git-repo-check"] and cmd[cmd.index("-m") + 1] == "gpt-test-sol"
      and 'model_reasoning_effort="high"' in cmd and 'sandbox_mode="workspace-write"' in cmd and '"python3 \\"/x/navi.py\\" hook"' in hook
      and "--dangerously-bypass-hook-trust" in cmd and cmd[-1] == "P",
      "Codex: exec --json, the model by tier, effort, the workspace sandbox, NAVI's guard as this run's hook", " ".join(cmd))
cmd = X.moderator(cfg, prompt="P", model="", effort="", headless=True, conv="th-1", cont=True, perms="all", add_dirs=[], rules=[], guard=GUARD, agents="")
check(cmd[-3:] == ["resume", "th-1", "P"] and 'sandbox_mode="danger-full-access"' in cmd and cmd.index('sandbox_mode="danger-full-access"') < cmd.index("resume"),
      "Codex: resuming puts every flag before `resume <thread>` (it refuses some after)", " ".join(cmd))
cmd = X.moderator(cfg, prompt="P", model="", effort="", headless=True, conv="", cont=False, perms="skip", add_dirs=[], rules=[], guard=GUARD, agents="")
check("--dangerously-bypass-approvals-and-sandbox" in cmd and not any(c.startswith("hooks.") for c in cmd), "Codex: Skip permissions has no sandbox and no guard")
cmd = X.moderator(cfg, prompt="P", model="", effort="", headless=True, conv="", cont=False, perms="auto", add_dirs=[], rules=[], guard=GUARD, agents="")
check("--approve-for-me" in cmd, "Codex: Auto is its own reviewer")
m = X.member(cfg, prompt="P", model="fast", effort="low", perms="ask", add_dirs=[], rules=[], guard=GUARD)
check("--ephemeral" in m and m[m.index("-m") + 1] == "gpt-test-luna", "Codex: a member runs on its own model and leaves no session behind")
cmd = LX.moderator(cfg, prompt="P", model="strong", effort="max", headless=True, conv="", cont=False, perms="ask", add_dirs=[], rules=[], guard=GUARD, agents="")
check(cmd[cmd.index("--oss") + 1:cmd.index("--oss") + 3] == ["--local-provider", "ollama"] and cmd[cmd.index("-m") + 1] == "qwen3-coder:30b-navi64k"
      and 'model_reasoning_effort="none"' in cmd, "Local via Codex: --oss on Ollama (the 64k copy), reasoning off for a model that can't think", " ".join(cmd))
cmd = LX.moderator(cfg, prompt="P", model="gpt-oss:20b", effort="max", headless=True, conv="", cont=False, perms="ask", add_dirs=[], rules=[], guard=GUARD, agents="")
check('model_reasoning_effort="high"' in cmd, "...and kept (at most high) for one that can", " ".join(cmd))
cmd = G.moderator(cfg, prompt="P", model="balanced", effort="", headless=True, conv="11111111-aaaa", cont=False, perms="ask", add_dirs=[],
                  rules=["Bash(navi:*)", "Bash(git status:*)", "Read(./x)"], guard={}, agents="")
check(cmd[:5] == ["gemini", "-p", "P", "-o", "stream-json"] and cmd[cmd.index("-m") + 1] == "gemini-2.5-flash" and "auto_edit" in cmd
      and [cmd[i + 1] for i, c in enumerate(cmd) if c == "--allowed-tools"] == ["run_shell_command(navi)", "run_shell_command(git status)"]
      and cmd[-2:] == ["--session-id", "11111111-aaaa"], "Gemini: -p stream-json, edits allowed, only NAVI's commands for the shell", " ".join(cmd))
cmd = G.moderator(cfg, prompt="P", model="", effort="", headless=True, conv="11111111-aaaa", cont=True, perms="all", add_dirs=[], rules=[], guard={}, agents="")
check("yolo" in cmd and cmd[-2:] == ["-r", "11111111-aaaa"] and G.can["guard"] is True, "Gemini: Allow all is yolo, a session resumes by id")
# Gemini's guard: a home of NAVI's own, linking yours, its settings yours plus the hook (Gemini has no per-run hooks flag)
gh_real = f"{sp}/gem-real"
os.makedirs(f"{gh_real}/.gemini/tmp/sessions", exist_ok=True)
open(f"{gh_real}/.gemini/oauth_creds.json", "w").write("{}")
yours = {"security": {"auth": {"selectedType": "oauth-personal"}}, "hooksConfig": {"disabled": ["navi-guard", "theirs-off"]},
         "hooks": {"BeforeTool": [{"matcher": "write_file", "hooks": [{"name": "their-own", "type": "command", "command": "true"}]}]}}
json.dump(yours, open(f"{gh_real}/.gemini/settings.json", "w"))
saved_home = os.environ.get("GEMINI_CLI_HOME")
os.environ["GEMINI_CLI_HOME"] = gh_real
genv = G.guard_env({"hook": GUARD["hook"], "home": f"{sp}/gem-navi"})
gst = json.load(open(f"{sp}/gem-navi/.gemini/settings.json"))
bt = gst["hooks"]["BeforeTool"]
check(genv == {"GEMINI_CLI_HOME": f"{sp}/gem-navi", "NAVI_GEMINI_USER_HOME": gh_real} and os.path.islink(f"{sp}/gem-navi/.gemini/oauth_creds.json")
      and os.path.realpath(f"{sp}/gem-navi/.gemini/tmp") == os.path.realpath(f"{gh_real}/.gemini/tmp"),
      "Gemini's guard: a home of NAVI's that links yours (sign-in, sessions)", json.dumps(genv))
check(bt[0]["matcher"] == "*" and bt[0]["hooks"][0]["command"] == GUARD["hook"] and bt[0]["hooks"][0]["timeout"] == 30000
      and bt[1]["hooks"][0]["name"] == "their-own" and gst["hooksConfig"] == {"enabled": True, "disabled": ["theirs-off"]}
      and gst["security"] == yours["security"],
      "...its settings: yours, plus the guard on every tool, hooks on, and the guard never switched off", json.dumps(gst)[:300])
check(json.load(open(f"{gh_real}/.gemini/settings.json")) == yours, "...and your own settings are untouched")
os.environ["GEMINI_CLI_HOME"] = f"{sp}/gem-navi"          # a member started from inside a Gemini run NAVI started
os.environ["NAVI_GEMINI_USER_HOME"] = gh_real
G.guard_env({"hook": GUARD["hook"], "home": f"{sp}/gem-navi"})
check(os.path.realpath(f"{sp}/gem-navi/.gemini/oauth_creds.json") == os.path.realpath(f"{gh_real}/.gemini/oauth_creds.json"),
      "...from inside a run NAVI started, it still links your real home (never itself)")
os.environ.pop("NAVI_GEMINI_USER_HOME")
if saved_home is None:
    os.environ.pop("GEMINI_CLI_HOME")
else:
    os.environ["GEMINI_CLI_HOME"] = saved_home

out = subprocess.run([os.path.join(os.path.dirname(scripts), "tests", "fake-codex"), "exec", "--json", "-m", "gpt-test-sol", "## Your assignment x"],
                     capture_output=True, text=True, env={**os.environ, "NAVI_AGENT": "adversary", "FAKE_LOG": os.devnull, "PATH": "/usr/bin:/bin"}).stdout
ps = X.stream("gpt-test-sol")
traces = [t for line in out.splitlines() for t in ps.feed(json.loads(line))]
r = ps.finish()
check(ps.conv and any(t["kind"] == "tool" and t["tool"] == "Bash" for t in traces) and not any("bypass-hook-trust" in t.get("text", "") for t in traces)
      and ps.last.startswith("approve") and ps.live["gpt-test-sol"]["in"] == 4000 and ps.live["gpt-test-sol"]["cache_read"] == 20000
      and r["modelUsage"]["gpt-test-sol"]["costUSD"] == 0 and r["session_id"].startswith(ps.conv),
      "Codex's output: its thread, the commands, its last message, tokens (cached apart), no notices, no made-up cost", json.dumps(r)[:300])
out = subprocess.run([os.path.join(os.path.dirname(scripts), "tests", "fake-gemini"), "-p", "## Your assignment x", "-o", "stream-json", "-m", "gemini-2.5-flash"],
                     capture_output=True, text=True, env={**os.environ, "NAVI_AGENT": "ledger", "FAKE_LOG": os.devnull, "PATH": "/usr/bin:/bin"}).stdout
gs = G.stream("gemini-2.5-flash")
traces = [t for line in out.splitlines() for t in gs.feed(json.loads(line))]
res = gs.result
check(gs.conv and gs.last.startswith("approve, no blockers (ledger") and any(t["kind"] == "tool" for t in traces) and res
      and res["modelUsage"]["gemini-2.5-flash"]["inputTokens"] == 18000 and res["modelUsage"]["gemini-2.5-flash"]["thinkingTokens"] == 200,
      "Gemini's output: its session, the message from its pieces, tools, tokens per model", json.dumps(res)[:300])
lc = E.LocalStream("qwen3-coder:30b")
lc.feed({"type": "result", "total_cost_usd": 0.057, "modelUsage": {"qwen3-coder:30b": {"inputTokens": 14000, "costUSD": 0.057}}, "num_turns": 1})
check(lc.result["total_cost_usd"] == 0 and lc.result["modelUsage"]["qwen3-coder:30b"]["costUSD"] == 0, "Local: Claude Code's made-up price for a local model becomes $0")

# ---------------------------------------------------------------- the CLI
envc = {**os.environ}


def nv(*a, extra=None, cwd=None):
    return subprocess.run([sys.executable, navi, *a], capture_output=True, text=True, timeout=60, env={**envc, **(extra or {})}, cwd=cwd or sp)


r = nv("engine", "list")
check(r.returncode == 0 and all(e in r.stdout for e in E.ENGINES) and "● claude" in r.stdout, "navi engine list: every engine, the default marked", r.stdout[-400:])
r = nv("engine", "use", "local", "--fast", "qwen2.5:7b")
c = json.load(open(os.environ["NAVI_CONFIG"]))
check(r.returncode == 0 and c["engine"] == "local" and c["engines"]["local"]["models"]["fast"] == "qwen2.5:7b" and c["engine_chosen"] is True,
      "navi engine use local --fast ...: the default and one tier's model", r.stdout)
r = nv("engine", "use", "nope")
check(r.returncode != 0 and "no engine" in r.stderr, "navi engine use with a name that isn't one says so")
r = nv("engine", "test")
check(r.returncode == 0 and "NAVI ONLINE" in r.stdout, "navi engine test: one question to the default (Local, the fake Ollama)", r.stdout + r.stderr)
r = nv("engine", "test", "codex")
check(r.returncode == 0 and "NAVI ONLINE" in r.stdout, "...to Codex", r.stdout + r.stderr)
r = nv("engine", "test", "gemini")
check(r.returncode == 0 and "NAVI ONLINE" in r.stdout, "...to Gemini", r.stdout + r.stderr)
r = nv("engine", "test", "claude")
check(r.returncode == 0 and "NAVI ONLINE" in r.stdout, "...to Claude", r.stdout + r.stderr)
r = nv("--engine", "gemini", "doctor")
check("engine: Gemini" in r.stdout, "navi --engine gemini: this command on Gemini", r.stdout[:300])
r = nv("--engine", "nope", "doctor")
check(r.returncode != 0 and "--engine: one of" in r.stderr, "--engine with a name that isn't one says which there are")
nv("engine", "use", "claude")

# the guard hook in Codex's dialect: its shell command as Bash, its edits as apply_patch, and no "ask" (it would fail open)
hp = f"{sp}/hookproj"
os.makedirs(hp, exist_ok=True)
nv("init", "--task", "hook test", "--ask", "*.private", extra={"NAVI_DIR": f"{hp}/.navi"}, cwd=hp)


def hook(payload, engine):
    r = subprocess.run([sys.executable, navi, "hook"], input=json.dumps({"cwd": hp, **payload}), capture_output=True, text=True,
                       timeout=30, env={**envc, "NAVI_ENGINE": engine, "NAVI_DIR": f"{hp}/.navi"}, cwd=hp)
    return (json.loads(r.stdout).get("hookSpecificOutput") or {}) if r.stdout.strip() else {}


def ghook(tool, ti):
    """The guard as Gemini's BeforeTool hook: what it prints (Gemini reads only {"decision": ...})."""
    r = subprocess.run([sys.executable, navi, "hook"], input=json.dumps({"cwd": hp, "hook_event_name": "BeforeTool", "tool_name": tool, "tool_input": ti}),
                       capture_output=True, text=True, timeout=30, env={**envc, "NAVI_ENGINE": "gemini", "NAVI_DIR": f"{hp}/.navi"}, cwd=hp)
    return json.loads(r.stdout) if r.stdout.strip() else {}


d = ghook("read_file", {"file_path": ".env"})
check(d.get("decision") == "deny" and ".env" in d.get("reason", ""), "Gemini: read_file .env is denied, in Gemini's words", json.dumps(d))
check(ghook("run_shell_command", {"command": "cat .env"}).get("decision") == "deny", "Gemini: `cat .env` through its shell is denied")
d = ghook("read_file", {"file_path": "notes.private"})
check(d.get("decision") == "deny" and "navi ask" in d.get("reason", ""), "Gemini: a grey area is denied with how to ask you (headless Gemini would wait forever)", json.dumps(d))
check(ghook("read_many_files", {"include": ["src/app.py", ".env"]}).get("decision") == "deny", "Gemini: read_many_files with .env among them is denied")
check(ghook("read_file", {"file_path": "src/app.py"}) == {} and ghook("grep_search", {"pattern": "x", "dir_path": "src"}) == {},
      "Gemini: ordinary reads and searches pass, silently")
d = hook({"tool_name": "Bash", "tool_input": {"command": "cat .env"}}, "codex")
check(d.get("permissionDecision") == "deny", "Codex: `cat .env` through its shell is denied", json.dumps(d))
d = hook({"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch\n*** Update File: src/app.py\n@@\n*** Add File: .env\n+X=1\n*** End Patch"}}, "codex")
check(d.get("permissionDecision") == "deny" and ".env" in d.get("permissionDecisionReason", ""), "Codex: a patch that touches .env is denied (every file in it is checked)", json.dumps(d))
d = hook({"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch\n*** Update File: src/app.py\n*** End Patch"}}, "codex")
check(d == {}, "Codex: an ordinary patch passes")
d = hook({"tool_name": "Read", "tool_input": {"file_path": f"{hp}/notes.private"}}, "claude")
check(d.get("permissionDecision") == "ask", "Claude: a grey area asks you", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": "cat notes.private"}}, "codex")
check(d.get("permissionDecision") == "deny" and "navi ask" in d.get("permissionDecisionReason", ""),
      "Codex: the same grey area is denied with how to ask you (a hook's ask would let it run)", json.dumps(d))

# shell writes outside the project ask like the file tools' writes (a weak model once wrote ~/hello.html after `cd ~`)
d = hook({"tool_name": "Bash", "tool_input": {"command": "cd ~ && echo '<h1>hi</h1>' > hello.html"}}, "claude")
check(d.get("permissionDecision") == "ask" and "outside the project" in d.get("permissionDecisionReason", ""),
      "a shell write outside the project asks, even after a `cd` (cd ~ && echo > hello.html)", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": "printf x>~/glued.txt; cmd 2>&1 | tee ~/out.txt"}}, "codex")
check(d.get("permissionDecision") == "deny", "...a glued redirect or tee too (on Codex: denied, it can't ask)", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": "echo x > hello.html && echo y > /tmp/scratch.md && ls 2>/dev/null && git commit -m 'a > b'"}}, "claude")
check(d == {}, "...while writes in the project, to /tmp or /dev/null, and a quoted > pass", json.dumps(d))
# words are not files: a NAVI message or a commit message that mentions a sensitive file doesn't read it, and a ; or |
# inside quotes doesn't start a new command (a real council's `navi send --body "...variables.tfvars..."` was asked about)
d = hook({"tool_name": "Bash", "tool_input": {"command": 'navi send --from architect --to all --kind note --subject "groups" --body '
          '"- settings: environments/<env>/variables.tfvars | dev; prod" && navi ask --from architect --question "Which way?" --option "A) reuse"'}}, "claude")
check(d == {}, "NAVI's own messages may mention a sensitive file (quoted ; and | stay in the message)", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": 'git commit -m "handle prod.tfvars; tidy" && echo "see customers.csv"'}}, "claude")
check(d == {}, "...a commit message or an echo too", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": 'echo "$(cat .env)"'}}, "claude")
check(d.get("permissionDecision") == "deny", "...but a command inside $( ) still runs, quoted or not: denied", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": "grep -rn region --include='*.tfvars' . | head"}}, "claude")
check(d.get("permissionDecision") == "ask", "...and a grep through *.tfvars still asks", json.dumps(d))
d = hook({"tool_name": "Bash", "tool_input": {"command": "navi artifact architect .env --title keys"}}, "claude")
check(d.get("permissionDecision") == "deny", "...as does a file handed to NAVI (navi artifact .env)", json.dumps(d))

# a member run in the background stops when its session's runs are stopped, and takes its program with it
rp = f"{sp}/runproj"
os.makedirs(rp, exist_ok=True)
renv = {"NAVI_DIR": f"{rp}/.navi", "NAVI_ENGINE": "codex", "FAKE_MEMBER_SLEEP": "30", "FAKE_LOG": os.devnull}
nv("init", "--task", "slow member", "--council", "knights", extra=renv, cwd=rp)
r = nv("run", "adversary", "check it slowly", "--bg", extra=renv, cwd=rp)
rsid = open(f"{rp}/.navi/current").read().strip()
rec = f"{rp}/.navi/sessions/{rsid}/runs/adversary.json"
import navi as N  # noqa: E402
fake_running = lambda: subprocess.run(["pgrep", "-f", "fake-codex.*check it slowly|codex exec.*check it slowly"], capture_output=True, text=True).stdout.split()
for _ in range(50):
    if fake_running():
        break
    time.sleep(.2)
check(r.returncode == 0 and json.load(open(rec)).get("state") == "running" and bool(fake_running()), "navi run --bg: the member works in the background", r.stdout + r.stderr)
check(N.stop_runs(Path(f"{rp}/.navi/sessions/{rsid}")) == 1, "stopping the session's runs reaches it")
for _ in range(50):
    if not fake_running() and json.load(open(rec)).get("state") != "running":
        break
    time.sleep(.2)
check(not fake_running() and json.load(open(rec)).get("state") == "failed", "...it stops, and so does its program: nothing left running alone", json.dumps(json.load(open(rec))))
# `navi down` stops a moderator's members too, not just the moderator (a real benchmark found one left running for hours)
r = nv("run", "adversary", "check it slowly", "--bg", extra=renv, cwd=rp)
for _ in range(50):
    if fake_running():
        break
    time.sleep(.2)
mod = subprocess.Popen(["sleep", "60"])                 # stands in for the headless moderator
json.dump({"id": "abcd1234", "pid": mod.pid, "mode": "headless", "session": rsid}, open(f"{rp}/.navi/hosts/abcd1234.json", "w"))
had = bool(fake_running())
N.stop_headless(Path(f"{rp}/.navi"))
for _ in range(50):
    if not fake_running():
        break
    time.sleep(.2)
mod.wait(timeout=10)
check(had and not fake_running() and json.load(open(rec)).get("state") != "running", "navi down: the moderator stops, and so do the members it started",
      json.dumps(json.load(open(rec))))
# inside Codex's sandbox a member's program can't reach its model: with no NAVI outside to start it, say so at once
SANDBOX = {"CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}
r = nv("run", "adversary", "check it", extra={**renv, **SANDBOX, "NAVI_HOST_ID": "deadbeef"}, cwd=rp)
check(r.returncode != 0 and "can't start from here" in r.stderr and json.load(open(rec)).get("state") == "failed",
      "navi run inside Codex's sandbox, nobody outside: it says so at once (no member that can't reach its model)", r.stdout + r.stderr)
# a run waiting to be started outside is cancelled by a stop, before it starts
os.makedirs(f"{rp}/.navi/runq", exist_ok=True)
qf = f"{rp}/.navi/runq/abcdef12.{rsid}.adversary.json"
json.dump({"session": rsid, "agent": "adversary"}, open(qf, "w"))
json.dump({"agent": "adversary", "pid": 0, "state": "queued", "task": "x"}, open(rec, "w"))
N.stop_runs(Path(f"{rp}/.navi/sessions/{rsid}"))
check(not os.path.exists(qf) and json.load(open(rec)).get("state") == "stopped", "a stop cancels a run still waiting to start")
# what the sandbox asks for is checked outside it: a "model" that's really a flag isn't started, and the run says why
import threading  # noqa: E402
json.dump({"agent": "adversary", "pid": 0, "state": "queued", "task": "x"}, open(rec, "w"))
open(f"{rp}/.navi/sessions/{rsid}/runs/adversary.task.md", "w").write("check it")
json.dump({"session": rsid, "agent": "adversary", "model": "--dangerously-bypass-approvals-and-sandbox"}, open(qf, "w"))
until = time.time() + 2.5
th = threading.Thread(target=N.serve_member_runs, args=(Path(f"{rp}/.navi"), "abcdef12", lambda: time.time() < until))
th.start()
th.join()
r = json.load(open(rec))
check(not os.path.exists(qf) and r.get("state") == "failed" and "isn't a model name" in r.get("last", "") and not fake_running(),
      "NAVI outside the sandbox checks what it's asked: a flag posing as a model isn't started, and the run says why", json.dumps(r))
check(N.pid_alive(os.getpid()) and not N.pid_alive(0) and not N.pid_alive(None) and not N.pid_alive(999999),
      "pid_alive: this process yes; 0 (the whole group), nothing, a gone one: no")
# a seat on auto: the brief tells the moderator to pick its model per assignment, and `navi run --model` is what it runs on
nv("join", "adversary", "--model", "auto", extra=renv, cwd=rp)
b = nv("brief", extra=renv, cwd=rp).stdout
check("adversary [auto: you pick]" in b and "auto seats (adversary): you pick the model for each assignment" in b and "--model strong|balanced|fast" in b,
      "auto: the brief says the moderator picks that seat's model, and how (navi run --model on Codex)", b[b.find("council:"):][:900])
fenv = {**renv, "FAKE_MEMBER_SLEEP": "0"}
nv("run", "adversary", "a light check", "--model", "fast", extra=fenv, cwd=rp)
fast_model = json.load(open(rec)).get("model")
nv("run", "adversary", "a light check", extra=fenv, cwd=rp)
check(fast_model == E.get("codex").tier_models(N.load_config())["fast"] and json.load(open(rec)).get("model") == "",
      "...navi run --model fast runs it on the fast model; without one, on the moderator's (never a model called auto)", f"{fast_model} / {json.load(open(rec))}")

# ---------------------------------------------------------------- through the server: a council on each engine
proj = f"{sp}/eproj"
os.makedirs(f"{proj}/.navi", exist_ok=True)
subprocess.run(["git", "init", "-q", proj])
flog = f"{sp}/efake.log"
senv = {**envc, "NAVI_DIR": f"{proj}/.navi", "FAKE_LOG": flog, "FAKE_END": "1", "FAKE_SLEEP": "1", "NAVI_AFTER_END_WAIT": "2", "FAKE_PEEK": "1"}
srv = subprocess.Popen([sys.executable, navi, "serve", "--port", str(port)], cwd=proj, env=senv, stdout=subprocess.DEVNULL, stderr=open(f"{sp}/eserve.log", "w"))
tok = ""
for _ in range(60):
    try:
        tok = json.load(open(f"{proj}/.navi/server.json"))["token"]
        urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=1)
        break
    except Exception:
        time.sleep(.2)


def post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "X-Navi-Token": tok})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"status": e.code, **(json.loads(e.read() or b"{}") if e.headers.get("content-type", "").startswith("application/json") else {})}


def get(path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20).read())


def job(jid):
    for _ in range(150):
        j = get(f"/jobs?id={jid}")
        if j.get("state") != "running":
            return j
        time.sleep(.2)
    return {"state": "timeout"}


def ended(sid, secs=60):
    end = time.time() + secs
    while time.time() < end:
        if any(json.loads(x).get("type") == "end" for x in open(f"{proj}/.navi/sessions/{sid}/log.jsonl") if x.strip()) \
                and not any(h.get("session") == sid for h in [json.load(open(f)) for f in Path(f"{proj}/.navi/hosts").glob("*.json") if not f.name.endswith("relaunch.json")]):
            return True
        time.sleep(.5)
    return False


def meta(sid):
    return json.load(open(f"{proj}/.navi/sessions/{sid}/session.json"))


try:
    st = get("/status")
    ids = [e["id"] for e in st.get("engines") or []]
    check(ids == list(E.ENGINES) and all(e["ready"] for e in st["engines"]) and st.get("engine") == "claude",
          "/status: every engine with whether it's ready, and the default", str([(e["id"], e["ready"], e["why"]) for e in st.get("engines") or []]))
    r = post("/launch", {"action": "new", "task": "a page on local", "engine": "local", "council": "knights", "pace": "quick"})
    sid = r.get("session", "")
    check(r.get("via") == "headless" and r.get("engine") == "local", "/launch on Local", json.dumps(r))
    ok = ended(sid, 40)
    logtxt = open(flog).read()
    check(ok and f"engine=local base=http://{os.environ['OLLAMA_HOST']}" in logtxt and "token=ollama key= " in logtxt
          and "balanced=qwen3-coder:30b-navi64k" in logtxt and "ctx=65536 offline=1" in logtxt,
          "Local: Claude Code ran with Ollama's address, every tier on a 64k copy of a local model, no key of yours", logtxt[-600:])
    check(meta(sid).get("engine") == "local", "the session remembers its engine")
    check((meta(sid).get("cost") or {}).get("usd") == 0 and all(v.get("usd") == 0 for v in ((meta(sid).get("usage") or {}).get("models") or {}).values()),
          "Local: Claude Code prices it like Claude ($0.42 here); NAVI shows $0", json.dumps(meta(sid).get("cost")))
    # Codex: a member run on its own, tokens from both, the thread kept for later
    open(flog, "w").close()
    r = post("/launch", {"action": "new", "task": "a page on codex", "engine": "codex", "council": "knights", "pace": "standard", "model": "balanced"})
    sid = r.get("session", "")
    ok = ended(sid, 60)
    logtxt = open(flog).read()
    check(ok and "codex argv:" in logtxt and "[exec]" in logtxt and "[--json]" in logtxt and "--dangerously-bypass-hook-trust" in logtxt,
          "Codex: the council ran on `codex exec --json` with NAVI's guard", logtxt[:500])
    run = json.load(open(f"{proj}/.navi/sessions/{sid}/runs/architect.json")) if os.path.exists(f"{proj}/.navi/sessions/{sid}/runs/architect.json") else {}
    check(run.get("state") == "done" and run.get("engine") == "codex" and run.get("model") == "gpt-test-sol-2" and "approve" in run.get("last", ""),
          "Codex: `navi run architect` ran the lead on its own (no model of its own: the moderator's), its last message", json.dumps(run))
    check("engine=codex agent=architect" in logtxt, "...as a member: NAVI told it which agent it is")
    check("run exit 0" in logtxt and "no network" not in logtxt and '[sandbox_mode="workspace-write"]' in logtxt,
          "Codex, Ask me: the moderator's `navi run` comes from inside its sandbox, and NAVI outside it starts the member", logtxt[-800:])
    evs = [json.loads(x) for x in open(f"{proj}/.navi/sessions/{sid}/log.jsonl") if x.strip()]
    check(any(e.get("type") == "message" and e.get("agent") == "architect" and e.get("kind") == "verdict" for e in evs),
          "...and it spoke through navi like any member")
    u = (meta(sid).get("usage") or {}).get("models") or {}
    check(set(u) == {"gpt-test-sol-2"} and u["gpt-test-sol-2"]["cache_read"] == 40000 and (meta(sid).get("cost") or {}).get("usd") == 0,
          "Codex: tokens from the moderator and the member, per model, no made-up dollars", json.dumps(meta(sid).get("usage")))
    conv = open(f"{proj}/.navi/sessions/{sid}/conversation.codex").read().strip() if os.path.exists(f"{proj}/.navi/sessions/{sid}/conversation.codex") else ""
    made = open(os.path.join(os.environ["CODEX_HOME"], "fake_threads")).read().split()
    check(conv in made, "Codex: the thread it named itself is kept to resume (not an id NAVI made up)", f"{conv} not in {made[-3:]}")
    trace = open(f"{proj}/.navi/hosts/{sid}.trace.jsonl").read() if os.path.exists(f"{proj}/.navi/hosts/{sid}.trace.jsonl") else ""
    check('"tool": "Bash"' in trace and '"agent": "architect"' in trace, "the NAVI card's trace shows Codex's commands, the member's marked as its own")
    open(flog, "w").close()
    r = post("/say", {"session": sid, "text": "make the title bigger"})
    woke = False
    for _ in range(80):
        txt = open(flog).read()
        if "followup handled" in txt:
            woke = True
            break
        time.sleep(.25)
    check(woke and "[resume]" in txt and f"[{conv}]" in txt, "after the end, writing wakes Codex on its own thread (exec resume <thread>)", txt[:600])
    # Codex's sandbox: in the background (`navi run --bg`, then `navi runs --wait`), and with Allow all (no sandbox)
    for perms, what in (("ask", "Codex, Ask me, in the background: started outside the sandbox, `navi runs --wait` waits for it in there"),
                        ("all", "Codex, Allow all: no sandbox, the moderator starts the member itself")):
        open(flog, "w").close()
        r = post("/launch", {"action": "new", "task": "a page on codex [bg]" if perms == "ask" else "a page on codex",
                             "engine": "codex", "council": "knights", "pace": "standard", "permissions": perms})
        sid = r.get("session", "")
        ok = ended(sid, 60)
        logtxt = open(flog).read()
        run = json.load(open(f"{proj}/.navi/sessions/{sid}/runs/architect.json")) if os.path.exists(f"{proj}/.navi/sessions/{sid}/runs/architect.json") else {}
        mode = "workspace-write" if perms == "ask" else "danger-full-access"
        check(ok and ("runs --wait exit 0" if perms == "ask" else "run exit 0") in logtxt and "no network" not in logtxt
              and f'[sandbox_mode="{mode}"]' in logtxt and run.get("state") == "done" and "approve" in run.get("last", ""), what, logtxt[-800:])
    # Gemini: the moderator tries to read .env (FAKE_PEEK); the guard, as Gemini's hook, stops it
    open(flog, "w").close()
    r = post("/launch", {"action": "new", "task": "a page on gemini", "engine": "gemini", "council": "knights", "pace": "standard"})
    sid = r.get("session", "")
    ok = ended(sid, 60)
    logtxt = open(flog).read()
    check(ok and "gemini argv:" in logtxt and "[stream-json]" in logtxt and "[--session-id]" in logtxt, "Gemini: the council ran on `gemini -p -o stream-json`", logtxt[:400])
    gevs = [json.loads(x) for x in open(f"{proj}/.navi/sessions/{sid}/log.jsonl") if x.strip()]
    check("hook denied read_file" in logtxt and "hook denied run_shell_command" in logtxt and "read the file .env" not in logtxt
          and any(e.get("type") == "gate" and e.get("decision") == "deny" and "[hook]" in str(e.get("body")) for e in gevs),
          "Gemini: NAVI's guard runs as its hook: reading .env, or `cat .env`, is blocked, and the feed shows it", logtxt[-700:])
    ghome = os.path.realpath(f"{proj}/.navi/hosts/gemini-home")
    check(f"agent= home={ghome}" in logtxt and f"agent=architect home={ghome}" in logtxt,
          "...for its members too (a Gemini home of NAVI's, in the project's .navi)", logtxt[:900])
    u = (meta(sid).get("usage") or {}).get("models") or {}
    check(any(k.startswith("gemini") for k in u), "Gemini: its tokens per model", json.dumps(u))

    # a moderator that says it's done and stops without closing the session: NAVI asks you, instead of restarting it
    def asked_end(sid, secs=30):
        end = time.time() + secs
        while time.time() < end:
            evs = [json.loads(x) for x in open(f"{proj}/.navi/sessions/{sid}/log.jsonl") if x.strip()]
            a = next((e for e in evs if e.get("type") == "ask" and e.get("kind") == "end"), None)
            if a:
                return a, evs
            time.sleep(.5)
        return None, []
    for answer in ("Yes, end the session", "No, keep going"):
        open(flog, "w").close()
        sid = post("/launch", {"action": "new", "task": "a page on gemini [says-done]", "engine": "gemini", "council": "knights", "pace": "quick"}).get("session", "")
        a, evs = asked_end(sid)
        if answer.startswith("Yes"):
            check(a and "the page is built and checked" in a["body"] and a["options"] == ["Yes, end the session", "No, keep going"]
                  and not any(e.get("type") == "host" and "restarting" in str(e.get("body")) for e in evs),
                  "a moderator that says it's done and stops: NAVI asks you if it's done, no restart", json.dumps(a))
        r = post("/reply", {"id": (a or {}).get("id", "00000000"), "session": sid, "choice": answer})
        if answer.startswith("Yes"):
            check(r.get("ended") and meta(sid).get("summary") == "the page is built and checked",
                  "...you say yes: the session ends with what it said it did", json.dumps(r))
        else:
            woke = False
            for _ in range(60):
                if "[-r]" in open(flog).read():
                    woke = True
                    break
                time.sleep(.5)
            check(r.get("ok") and not r.get("ended") and woke, "...you say keep going: it's woken on the same conversation", json.dumps(r))
    # Settings > Test it, and the generators on a local model
    r = post("/engine/test", {"engine": "local", "engines": {"local": {"models": {"fast": "qwen2.5:7b"}}}})
    j = job(r.get("job", ""))
    check(j.get("state") == "done" and j["result"]["ok"] and j["result"]["model"] == "qwen2.5:7b", "/engine/test: one question, with the models just picked", json.dumps(j))
    check(post("/engine/test", {"engine": "nope"}).get("status") == 400, "/engine/test refuses an engine that isn't one")
    nv("engine", "use", "local")
    open(f"{sp}/ollama.log", "a").write("--- generate\n")
    r = post("/agents/generate", {"name": "local-tester", "role": "tester", "description": "checks things on a local model"})
    j = job(r.get("job", ""))
    olog = open(f"{sp}/ollama.log").read().split("--- generate")[-1]
    check(j.get("state") == "done" and "LOCAL-TESTER" in (j.get("result") or {}).get("directive", "") and '"/api/chat"' in olog and "qwen3-coder:30b" in olog,
          "Write it for me on Local: the instructions come from your local model", json.dumps(j)[:300])
    check(((j.get("result") or {}).get("lint") or {}).get("score") == 100 and olog.count('"/api/chat"') == 2 and "Your lens is" in (j.get("result") or {}).get("directive", ""),
          "...and a draft that falls short of NAVI's own standard is fixed once more before you see it: 100", json.dumps((j.get("result") or {}).get("lint", {}))[:300])
    nv("engine", "use", "claude")
    # the benchmark runner (bench/run.py) end to end on the fake Claude: launch, follow, check, one line of results
    bres = f"{sp}/bench.jsonl"
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(scripts), "bench", "run.py"), "--engine", "claude", "--tasks", "quick-hello", "--minutes", "2"],
                       capture_output=True, text=True, timeout=240, env={**envc, "NAVI_BENCH_RESULTS": bres, "FAKE_END": "1", "FAKE_SLEEP": "1", "FAKE_LOG": os.devnull})
    br = json.loads(open(bres).read().splitlines()[-1]) if os.path.exists(bres) else {}
    check(r.returncode == 0 and br.get("ended") is True and br.get("check") == "fail" and br.get("why") == "no hello.html" and br.get("engine") == "claude",
          "bench/run.py: a council on a task, followed to its end, then the task's own check (the fake builds nothing: fail)", (r.stdout + r.stderr)[-400:] + json.dumps(br))
finally:
    srv.terminate()
print("ENGINES SUITE PASSED" if not fails else f"ENGINES SUITE FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
