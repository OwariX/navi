"""install.sh and `navi uninstall`, in a home folder of their own (yours is never touched).
usage: python3 -I install_test.py <navi repo> <scratch dir>
- install: the command, the skill links (Claude Code, Codex, ~/.agents), the permission rules (yours kept), the engine
- again: nothing doubled · uninstall: all of it gone, yours kept, a backup made, settings kept · --purge: settings too
- uninstall without --yes and no terminal refuses · nothing installed: says so"""
import json
import os
import subprocess
import sys

repo, sp = sys.argv[1], sys.argv[2]
home = os.path.join(sp, "ihome")
fails = []


def check(ok, what, extra=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"  · {extra}" if extra and not ok else ""))
    if not ok:
        fails.append(what)


for d in (".claude", ".codex", ".gemini"):
    os.makedirs(os.path.join(home, d), exist_ok=True)
json.dump({"permissions": {"allow": ["Bash(npm test:*)"]}, "model": "opus"}, open(os.path.join(home, ".claude", "settings.json"), "w"))
real = os.path.expanduser("~/.claude/settings.json")
real_before = os.path.getmtime(real) if os.path.exists(real) else None
fbin = os.path.join(home, ".local", "bin")
env = {"HOME": home, "PATH": f"{fbin}:/usr/bin:/bin:/usr/sbin:/sbin", "NAVI_BIN": fbin, "NAVI_UNINSTALL_KEEP_RUNNING": "1",
       "NAVI_NO_INTRO": "1", "LANG": "en_US.UTF-8"}


def sh(*args, stdin=subprocess.DEVNULL):
    return subprocess.run(list(args), env=env, capture_output=True, text=True, timeout=60, stdin=stdin, cwd=home)


r = sh("sh", os.path.join(repo, "install.sh"), "--engine", "local")
navi = os.path.join(fbin, "navi")
check(r.returncode == 0 and os.access(navi, os.X_OK), "install puts a navi command on the PATH", r.stdout + r.stderr)
check("scripts/navi.py" in open(navi).read(), "...a wrapper that runs this NAVI")
v = sh(navi, "--version")
check(v.returncode == 0 and "NAVI" in v.stdout, "...and it runs", v.stdout + v.stderr)
links = [os.path.join(home, x, "navi") for x in (".claude/skills", ".codex/skills", ".agents/skills")]
check(all(os.path.islink(x) and os.path.realpath(x) == os.path.realpath(repo) for x in links),
      "the skill is linked for Claude Code, Codex and ~/.agents (Codex, Gemini)", str([os.path.islink(x) for x in links]))
st = json.load(open(os.path.join(home, ".claude", "settings.json")))
allow = st["permissions"]["allow"]
check("Bash(navi:*)" in allow and "Bash(npm test:*)" in allow and st.get("model") == "opus",
      "Claude Code may run navi without asking; your own rules and settings stay", str(allow))
cfg = json.load(open(os.path.join(home, ".config", "navi", "config.json")))
check(cfg.get("engine") == "local" and cfg.get("engine_chosen") is True, "--engine local: NAVI runs on Local now", json.dumps(cfg)[:200])
r = sh("sh", os.path.join(repo, "install.sh"), "--no-wizard")
allow2 = json.load(open(os.path.join(home, ".claude", "settings.json")))["permissions"]["allow"]
check(r.returncode == 0 and len(allow2) == len(allow), "installing again changes nothing (idempotent)", str(allow2))
check("· NAVI runs on Claude" in r.stdout or "navi engine" in r.stdout, "without a terminal it says how to pick the engine, no wizard", r.stdout)
cfg = json.load(open(os.path.join(home, ".config", "navi", "config.json")))
check(cfg.get("engine") == "local", "...and keeps the engine you picked")
lst = sh(navi, "engine", "list")
check(lst.returncode == 0 and "● local" in lst.stdout, "navi engine list marks the default", lst.stdout[-300:])
# uninstall: refuses without a terminal or --yes, then removes what install added and only that
r = sh(navi, "uninstall")
check(r.returncode != 0 and "--yes" in (r.stdout + r.stderr) and os.path.exists(navi), "uninstall without a terminal asks for --yes and changes nothing")
r = sh(navi, "uninstall", "--yes")
check(r.returncode == 0 and not os.path.exists(navi), "navi uninstall removes the command", r.stdout + r.stderr)
check(not any(os.path.lexists(x) for x in links), "...the skill links")
st = json.load(open(os.path.join(home, ".claude", "settings.json")))
check(st["permissions"]["allow"] == ["Bash(npm test:*)"] and st.get("model") == "opus", "...only NAVI's permission rules (yours stay)", str(st))
check(os.path.exists(os.path.join(home, ".claude", "settings.json.navi-backup")), "...with a backup of the settings it changed")
check(os.path.isdir(repo) and os.path.exists(os.path.join(home, ".config", "navi", "config.json")), "...and keeps your NAVI settings and the NAVI folder")
check("keep" in r.stdout and "install.sh" in r.stdout, "it says what it kept and how to put NAVI back", r.stdout)
r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "navi.py"), "uninstall", "--yes"], env=env, capture_output=True, text=True, timeout=60, cwd=home)
check(r.returncode == 0 and "isn't installed" in r.stdout, "uninstalling again: nothing to remove, it says so", r.stdout)
# reinstall, then the full uninstall through install.sh
r = sh("sh", os.path.join(repo, "install.sh"), "--no-wizard")
check(r.returncode == 0 and os.path.exists(navi) and all(os.path.islink(x) for x in links), "install again: all back")
r = sh("sh", os.path.join(repo, "install.sh"), "--uninstall", "--purge", "--yes")
check(r.returncode == 0 and not os.path.exists(navi) and not os.path.exists(os.path.join(home, ".config", "navi")),
      "install.sh --uninstall --purge removes the settings, agents and councils too", r.stdout + r.stderr)
r = sh("sh", os.path.join(repo, "install.sh"), "--bogus")
check(r.returncode == 2 and "unknown option" in r.stdout, "install.sh says when an option doesn't exist")
check((os.path.getmtime(real) if os.path.exists(real) else None) == real_before, "your real ~/.claude/settings.json was never touched")

# ---- the Claude Code plugin (this repo is its own marketplace): `/plugin marketplace add OwariX/navi`
plug = json.load(open(os.path.join(repo, ".claude-plugin", "plugin.json")))
market = json.load(open(os.path.join(repo, ".claude-plugin", "marketplace.json")))
check(plug["name"] == "navi" and plug["version"] == open(os.path.join(repo, "VERSION")).read().strip() and plug.get("license") == "MIT",
      "plugin: named navi, the same version as NAVI, MIT", json.dumps(plug)[:200])
check(plug.get("agents") == [], "plugin: NAVI's personas (agents/) never load as Claude Code subagents")
check([x.get("source") for x in market.get("plugins", []) if x.get("name") == "navi"] == ["./"], "plugin: the repo is its own marketplace")
hooks = json.load(open(os.path.join(repo, "hooks", "hooks.json")))["hooks"]["PreToolUse"][0]
check("${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh" in hooks["hooks"][0]["command"] and "Read" in hooks["matcher"] and "Bash" in hooks["matcher"],
      "plugin: the guard is its PreToolUse hook, on reads and the shell", json.dumps(hooks))
check(os.access(os.path.join(repo, "bin", "navi"), os.X_OK) and os.access(os.path.join(repo, "hooks", "guard.sh"), os.X_OK),
      "plugin: bin/navi (Claude Code's shell gets `navi`) and the hook are executable")
skill_head = open(os.path.join(repo, "SKILL.md")).read().split("\n---\n", 1)[0]
check("allowed-tools: Bash(navi:*)" in skill_head, "the skill may run `navi` without a prompt each time (plugin users have no install.sh rules)")
# NAVI's data lives outside the project (~/.navi/projects), and an old <project>/.navi moves out once nothing runs on it
gp = os.path.join(sp, "ghook")
os.makedirs(os.path.join(gp, "proj", "sub"), exist_ok=True)
nhome = os.path.join(home, ".navi")
nenv = {**env, "NAVI_CONFIG": os.path.join(gp, "config.json")}
navi_py = [sys.executable, os.path.join(repo, "scripts", "navi.py")]
nrun = lambda cwd, *a, extra=None: subprocess.run(navi_py + list(a), env={**nenv, **(extra or {})}, cwd=cwd, capture_output=True, text=True, timeout=60)
nrun(os.path.join(gp, "proj"), "init", "--task", "hook test")
data = [os.path.join(nhome, "projects", x) for x in os.listdir(os.path.join(nhome, "projects"))] if os.path.isdir(os.path.join(nhome, "projects")) else []
check(not os.path.exists(os.path.join(gp, "proj", ".navi")) and len(data) == 1 and os.path.basename(data[0]).startswith("proj-"),
      "a project gets no .navi folder: its NAVI data is in ~/.navi/projects/<folder>-<id>", str(data))
pj = json.load(open(os.path.join(data[0], "project.json"))) if data else {}
check(os.path.realpath(pj.get("root", "")) == os.path.realpath(os.path.join(gp, "proj")) and os.path.isfile(os.path.join(data[0], "policy.json")),
      "...which says which folder it belongs to, with the project's policy", json.dumps(pj))
check(os.path.realpath(os.path.join(gp, "proj")) in open(os.path.join(nhome, "roots")).read().split("\n"), "...and the folder is listed for the plugin's hook")
b = nrun(os.path.join(gp, "proj", "sub"), "brief")
check("project: " + os.path.realpath(os.path.join(gp, "proj")) in b.stdout or "project: " + os.path.join(gp, "proj") in b.stdout,
      "commands in the project find it (the brief names the project folder)", b.stdout[:300] + b.stderr[-300:])
d = nrun(os.path.join(gp, "proj"), "doctor").stdout
check(".navi/projects/proj-" in d and "nothing in the project" in d, "navi doctor says where the data is", d[-600:])

# the plugin's hook (Claude Code loads NAVI as a plugin, so it runs in every conversation): it guards only a conversation
# that is a council's moderator here, never your own work in the same folder (`/init`, a review: a user's report)
def plugin_hook(cwd, payload, **extra):
    r = subprocess.run(["sh", os.path.join(repo, "hooks", "guard.sh")], input=json.dumps({"cwd": cwd, **payload}),
                       env={**nenv, "PWD": cwd, **extra}, cwd=cwd, capture_output=True, text=True, timeout=30)
    return (json.loads(r.stdout).get("hookSpecificOutput") or {}).get("permissionDecision", "") if r.stdout.strip() else ""


sub = os.path.join(gp, "proj", "sub")
read_env = {"tool_name": "Read", "tool_input": {"file_path": ".env"}}
open(os.path.join(gp, "proj", "resources.csv"), "w").write("a,b\n")
check(plugin_hook(sub, {**read_env, "session_id": "your-own-chat"}) == "" and
      plugin_hook(sub, {"tool_name": "Bash", "tool_input": {"command": "head -3 resources.csv"}, "session_id": "your-own-chat"}) == "",
      "plugin hook: your own Claude Code in a project with an open council is left alone (/init reading a .csv: no question)")
plugin_hook(sub, {"tool_name": "Bash", "tool_input": {"command": "navi brief"}, "session_id": "council-moderator"})
check(plugin_hook(sub, {**read_env, "session_id": "council-moderator"}) == "deny",
      "...the conversation that runs the council (it ran `navi`) is guarded: reading .env is denied")
check(plugin_hook(sub, {**read_env, "session_id": "your-own-chat"}) == "", "...and your other conversation still isn't")
check(plugin_hook(sub, {**read_env, "session_id": "council-moderator"}, NAVI_HOST_ID="abcd1234") == "",
      "...in a run NAVI started it stays out (that run has the guard already)")
nrun(os.path.join(gp, "proj"), "end", "--summary", "done")
check(plugin_hook(sub, {**read_env, "session_id": "council-moderator"}) == "", "...once the session is over, it's ordinary work again")
check(plugin_hook(home, {**read_env, "session_id": "council-moderator"}) == "", "...and where NAVI has never run, it does nothing (no Python started)")

# an old project with a .navi folder: moved out the first time NAVI runs there and nothing of NAVI's is running on it
old = os.path.join(gp, "oldproj")
os.makedirs(old, exist_ok=True)
nrun(old, "init", "--task", "an old session", extra={"NAVI_DIR": os.path.join(old, ".navi")})
sid0 = open(os.path.join(old, ".navi", "current")).read().strip()
busy = subprocess.Popen(["sleep", "60"])
os.makedirs(os.path.join(old, ".navi", "hosts"), exist_ok=True)
json.dump({"id": "deadbeef", "pid": busy.pid, "session": sid0}, open(os.path.join(old, ".navi", "hosts", "deadbeef.json"), "w"))
nrun(old, "doctor")
check(os.path.isdir(os.path.join(old, ".navi")), "an old project's .navi stays where it is while a council runs on it")
busy.kill(); busy.wait()
r = nrun(old, "log")
moved = [x for x in os.listdir(os.path.join(nhome, "projects")) if x.startswith("oldproj-")]
check(not os.path.exists(os.path.join(old, ".navi")) and len(moved) == 1 and os.path.isdir(os.path.join(nhome, "projects", moved[0], "sessions", sid0)),
      "...and moves out to ~/.navi/projects once nothing runs on it, sessions and all", str(moved))
check(r.returncode == 0 and "an old session" in (r.stdout + nrun(old, "brief").stdout), "...where NAVI carries on with it", r.stdout[-300:] + r.stderr[-300:])

# a fresh install starts on Auto (where an engine has no auto mode, a council falls back to Ask me)
r = subprocess.run([sys.executable, os.path.join(repo, "scripts", "navi.py"), "doctor"], capture_output=True, text=True, timeout=60,
                   env={**env, "NAVI_CONFIG": os.path.join(gp, "fresh-config.json")})
check("permissions auto" in r.stdout, "a fresh install: permissions start on Auto", r.stdout[-300:])
# Windows: NAVI says to use WSL rather than failing later (pseudo-terminals, file locks, process groups)
win = [sys.executable, "-c", "import sys, os; sys.path.insert(0, sys.argv[1]); import navi; os.name = 'nt'; sys.argv = ['navi'] + sys.argv[2:]; navi.main()",
       os.path.join(repo, "scripts")]
r = subprocess.run(win + ["doctor"], capture_output=True, text=True, timeout=60, env={**env, "NAVI_CONFIG": os.path.join(gp, "config.json")})
check(r.returncode == 1 and "inside WSL" in r.stderr and "docs/WINDOWS.md" in r.stderr, "on Windows: NAVI says to run it inside WSL, and where the steps are", r.stdout + r.stderr)
r = subprocess.run(win + ["--version"], capture_output=True, text=True, timeout=60, env={**env, "NAVI_CONFIG": os.path.join(gp, "config.json")})
check(r.returncode == 0 and "NAVI" in r.stdout, "...while `navi --version` still answers there")
print("INSTALL SUITE PASSED" if not fails else f"INSTALL SUITE FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
