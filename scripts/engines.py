"""NAVI's engines: the agent programs a council runs on, and the models behind them.

An engine is one adapter. It knows how to start NAVI (the moderator) on its program, how to run one council member on
its own (`navi run`), how to ask one quick question (the generators: Write it for me, the council generator, the sources
reader), what its program prints and how to read it, and what to check before it can run.

Councils name a TIER per seat: strong (the lead), balanced (reviewers), fast (the recorder, light checks). Each engine maps
the tiers to its own models, so The Knights run on whichever engine you pick. Claude's names keep working everywhere:
opus and fable are strong, sonnet is balanced, haiku is fast.

To add an engine: subclass Engine, fill in what differs, add it to ENGINES. This module imports nothing from NAVI; the
caller passes in what it needs (the guard's settings, permission rules). Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TIERS = ("strong", "balanced", "fast")
TIER_WORDS = {"strong": "Strong", "balanced": "Balanced", "fast": "Fast"}
TIER_NOTES = {"strong": "the lead: designs and builds", "balanced": "reviewers", "fast": "the recorder and light checks"}
ALIASES = {"opus": "strong", "fable": "strong", "sonnet": "balanced", "haiku": "fast"}     # Claude's names, as tiers
MODEL_ID = re.compile(r"^[A-Za-z0-9][\w.:/@+-]{0,79}$")      # a concrete model name: qwen3-coder:30b, gpt-5.1-codex, ...
AUTO = "auto"       # a seat on auto: the moderator picks its model for each assignment (strong, balanced or fast)


def is_auto(value) -> bool:
    return str(value or "").strip().lower() == AUTO


def tier_of(value) -> str:
    """'strong' | 'balanced' | 'fast' for a tier or one of Claude's names; '' for the moderator's own model or a concrete name."""
    v = str(value or "").strip().lower()
    return v if v in TIERS else ALIASES.get(v, "")


def valid_model(value) -> bool:
    """What a council seat, a persona or a launch may name as a model: '' (inherit), a tier, Claude's names, or a concrete
    model of some engine (checked by shape only: whether it exists is the engine's business)."""
    v = str(value or "")
    return v == "" or bool(tier_of(v)) or bool(MODEL_ID.match(v))


def _get_json(url: str, timeout: float = 3, data: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"content-type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


# ---------------------------------------------------------------- reading what a program prints

class Stream:
    """One run's output, line by line (JSON): what to show (trace lines), tokens as they come in (`live`, per model), the
    conversation id (to resume it), and at the end a Claude-shaped result for NAVI's token and cost counters."""
    def __init__(self, model: str = ""):
        self.model, self.conv, self.live, self.result, self.t0, self.turns = model, "", {}, None, time.time(), 0

    def feed(self, m: dict) -> list[dict]:
        return []

    def finish(self) -> dict | None:
        """At the end of the output: the result, if the program didn't print one itself."""
        return None


def _usage(t: dict, inp: int = 0, out: int = 0, cache_read: int = 0, cache_write: int = 0, thinking: int = 0):
    t["in"] = t.get("in", 0) + int(inp or 0)
    t["out"] = t.get("out", 0) + int(out or 0)
    t["cache_read"] = t.get("cache_read", 0) + int(cache_read or 0)
    t["cache_write"] = t.get("cache_write", 0) + int(cache_write or 0)
    t["thinking"] = t.get("thinking", 0) + int(thinking or 0)
    t.setdefault("usd", 0)


class ClaudeStream(Stream):
    """Claude Code's stream-json: assistant messages (tool calls, text, per-message usage) and one result at the end,
    which carries Claude Code's own full count, subagents included."""
    free = False        # local models: Claude Code prices them as if they were Anthropic's; they cost nothing

    def __init__(self, model: str = ""):
        super().__init__(model)
        self.counted: set = set()
        self.last = ""

    def feed(self, m: dict) -> list[dict]:
        out, t = [], m.get("type")
        if t == "assistant":
            msg = m.get("message") if isinstance(m.get("message"), dict) else {}
            for c in msg.get("content") or []:
                if c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    text = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("description") or inp.get("prompt") or json.dumps(inp)[:200]
                    out.append({"kind": "tool", "tool": c.get("name", ""), "text": str(text)[:300]})
                elif c.get("type") == "text" and (c.get("text") or "").strip():
                    self.last = c["text"].strip()
                    out.append({"kind": "text", "text": self.last[:400]})
            if isinstance(msg.get("usage"), dict) and msg.get("id") not in self.counted:
                self.counted.add(msg.get("id"))
                u = msg["usage"]
                _usage(self.live.setdefault(str(msg.get("model") or self.model or "model"), {}), u.get("input_tokens"), u.get("output_tokens"),
                       u.get("cache_read_input_tokens"), u.get("cache_creation_input_tokens"))
        elif t == "result":
            if self.free:
                m = {**m, "total_cost_usd": 0, "modelUsage": {k: {**v, "costUSD": 0} for k, v in (m.get("modelUsage") or {}).items() if isinstance(v, dict)}}
            self.result = m
            self.last = str(m.get("result") or self.last).strip()
            out.append({"kind": "result", "text": f"{m.get('subtype', '')} · ${float(m.get('total_cost_usd') or 0):.2f} · "
                                                  f"{m.get('num_turns', 0)} turns · {int((m.get('duration_ms') or 0) / 1000)}s"})
        elif t == "system" and m.get("subtype") == "init":
            self.conv = str(m.get("session_id") or self.conv)
            out.append({"kind": "init", "text": f"model {m.get('model', '')} · {len(m.get('tools') or [])} tools",
                        **({"mode": str(m["permissionMode"])} if m.get("permissionMode") else {}), "model": str(m.get("model") or "")})
        return out


# ---------------------------------------------------------------- engines

class Engine:
    id = ""
    name = ""             # what the wizard and the interface call it
    program = ""          # the command it runs
    blurb = ""            # one line: what it is, what it needs
    install_hint = ""     # how to get the program
    defaults: dict = {}   # tier -> model, the engine's own names
    efforts: tuple = ("low", "medium", "high", "xhigh", "max")
    # what NAVI can do on it: native subagents (members registered with their model), a hard guard (hooks that block
    # secrets before anything is read), permission cards, auto mode, real costs, resuming a conversation, a terminal mode
    can: dict = {"subagents": False, "guard": False, "cards": False, "auto": False, "cost": False, "resume": True, "terminal": True}
    Stream = Stream
    own_ids = False       # the program names its conversations itself (Codex): NAVI reads the id from its output

    # -- settings
    def settings(self, cfg: dict) -> dict:
        return dict(((cfg or {}).get("engines") or {}).get(self.id) or {})

    def tier_models(self, cfg: dict) -> dict:
        mine = self.settings(cfg).get("models") or {}
        return {t: str(mine.get(t) or self.defaults.get(t) or "") for t in TIERS}

    def resolve(self, cfg: dict, value) -> str:
        """A seat's model on this engine: '' stays '' (the program's default, or the moderator's own), a tier or one of
        Claude's names becomes this engine's model for that tier, a concrete name passes through."""
        v = str(value or "").strip()
        if is_auto(v):
            return ""          # nobody picked one for this run: the moderator's own
        t = tier_of(v)
        return self.tier_models(cfg)[t] if t else v

    def run_model(self, cfg: dict, value) -> str:
        """The model as the program is given it (Local runs NAVI's copy with the bigger window)."""
        return self.resolve(cfg, value)

    def describe(self, cfg: dict, value) -> str:
        """How the interface names a model on this engine: 'Strong · qwen3-coder:30b'."""
        if is_auto(value):
            return "Auto · picked per task"
        t, m = tier_of(value), self.resolve(cfg, value)
        return f"{TIER_WORDS[t]} · {m}" if t and m else (m or "default")

    def choices(self, cfg: dict) -> list[dict]:
        """The models a picker offers: the tiers (with the model each one is here), then any other installed ones."""
        tm = self.tier_models(cfg)
        return [{"value": t, "label": TIER_WORDS[t], "model": tm[t], "note": TIER_NOTES[t]} for t in TIERS]

    # -- the machine
    def path(self) -> str | None:
        return shutil.which(self.program) if self.program else None

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        """(ok, what, how to fix): the program is here, and whatever else this engine needs. Quick unless `deep` (then
        it may run the program, e.g. for its version: the wizard and `navi doctor`, never a page load)."""
        p = self.path()
        return [(bool(p), f"{self.program} installed" + (f" ({p})" if p else ""), self.install_hint)]

    def ready(self, cfg: dict) -> tuple[bool, str]:
        bad = next((c for c in self.checks(cfg) if not c[0]), None)
        return (True, "") if not bad else (False, f"{bad[1]}: {bad[2]}" if bad[2] else bad[1])

    def env(self, cfg: dict) -> dict:
        """Environment for the program on this engine (added to NAVI's own)."""
        return {}

    def prepare(self, cfg: dict) -> list[str]:
        """Right before a run: anything to set up first. -> what it did, for the session log."""
        return []

    def guard_env(self, guard: dict) -> dict:
        """Environment that puts NAVI's guard in place, for engines that take it that way (the rest take it in their
        command line)."""
        return {}

    def default(self, cfg: dict) -> str:
        """The model it runs when NAVI names none ('' when only the program knows)."""
        return ""

    def info(self, cfg: dict) -> dict:
        ok, why = self.ready(cfg)
        return {"id": self.id, "name": self.name, "program": self.program, "blurb": self.blurb, "installed": bool(self.path()),
                "ready": ok, "why": why, "can": dict(self.can), "efforts": list(self.efforts), "tiers": self.tier_models(cfg),
                "choices": self.choices(cfg), "default": self.default(cfg)}

    # -- running (each returns the command line; env() is added by the caller)
    def moderator(self, cfg: dict, *, prompt: str, model: str, effort: str, headless: bool, conv: str, cont: bool,
                  perms: str, add_dirs: list, rules: list, guard: dict, agents: str) -> list[str]:
        raise NotImplementedError

    def member(self, cfg: dict, *, prompt: str, model: str, effort: str, perms: str, add_dirs: list, rules: list,
               guard: dict) -> list[str]:
        raise NotImplementedError

    def ask(self, cfg: dict, prompt: str, model: str = "", timeout: int = 240) -> str:
        """One question, one answer, every tool off. Raises RuntimeError with a readable reason."""
        raise NotImplementedError

    def stream(self, model: str = "") -> Stream:
        return self.Stream(model)


def claude_settings(guard: dict) -> dict:
    """Claude Code's settings for NAVI's guard: the hard PreToolUse hook, the PermissionRequest hook that turns what
    nothing allowed into a card in NAVI (background runs), and the deny rules. `guard` is the engine-neutral description
    NAVI passes to every engine: {hook, tools, deny, permit, permit_timeout}."""
    hooks: dict = {"PreToolUse": [{"matcher": guard["tools"], "hooks": [{"type": "command", "command": guard["hook"]}]}]}
    if guard.get("permit"):
        hooks["PermissionRequest"] = [{"matcher": "*", "hooks": [{"type": "command", "command": guard["permit"],
                                                                 "timeout": int(guard.get("permit_timeout") or 600)}]}]
    return {"hooks": hooks, "permissions": {"deny": list(guard.get("deny") or [])}}


ERROR_WORDS = re.compile(r"error|limit|not supported|eligible|unauthori|sign ?in|log ?in|quota|denied|not found|refused|invalid|expired|credit", re.I)


def why(text: str) -> str:
    """The line that says what went wrong in a program's error output: not its stack trace, its echo of the prompt, or
    its warnings. 'You've hit your usage limit... try again at 3:36 PM.'"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not re.match(r"^(at |[\[\]{}()]|\w+: '|warning\b)", ln.strip(), re.I)]
    hit = next((ln for ln in lines if ERROR_WORDS.search(ln)), lines[-1] if lines else "")
    return re.sub(r"^(error|ERROR)\s*[:]\s*", "", hit)[:400]


def _run(cmd: list, timeout: int, env: dict | None = None, cwd: str | None = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           cwd=cwd or str(Path.home()), env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"no answer within {timeout}s")
    except OSError as e:
        raise RuntimeError(str(e))
    if r.returncode != 0:
        raise RuntimeError(why(f"{r.stderr}\n{r.stdout}") or f"exited {r.returncode}")
    return r.stdout.strip()


class Claude(Engine):
    id, name, program = "claude", "Claude", "claude"
    blurb = "Claude Code on your Anthropic account. Everything NAVI has: hard guard, permission cards, registered members."
    install_hint = "install Claude Code: https://claude.com/claude-code"
    defaults = {"strong": "opus", "balanced": "sonnet", "fast": "haiku"}
    can = {"subagents": True, "guard": True, "cards": True, "auto": True, "cost": True, "resume": True, "terminal": True}
    Stream = ClaudeStream
    alias = {"strong": "opus", "balanced": "sonnet", "fast": "haiku"}     # what a registered member's model field says

    def choices(self, cfg: dict) -> list[dict]:
        tm = self.tier_models(cfg)
        return [{"value": "fable", "label": "Fable", "model": "fable", "note": "top tier"},
                {"value": "opus", "label": "Opus", "model": "opus", "note": "top tier" + (" · strong" if tm["strong"] == "opus" else "")},
                {"value": "sonnet", "label": "Sonnet", "model": "sonnet", "note": "fast and capable"},
                {"value": "haiku", "label": "Haiku", "model": "haiku", "note": "fastest, lightest"}]

    def resolve(self, cfg: dict, value) -> str:
        v = str(value or "").strip()
        return v if v.lower() in ("opus", "sonnet", "haiku", "fable") else super().resolve(cfg, v)

    def describe(self, cfg: dict, value) -> str:
        if is_auto(value):
            return Engine.describe(self, cfg, value)
        m = self.resolve(cfg, value)
        return m.capitalize() if m in ("opus", "sonnet", "haiku", "fable") else (m or "default")

    def member_alias(self, cfg: dict, value) -> str:
        """A registered member's model ('--agents' takes opus | sonnet | haiku | fable | inherit)."""
        m = self.resolve(cfg, value)
        return m if m in ("opus", "sonnet", "haiku", "fable") else "inherit"

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        rows = super().checks(cfg)
        if rows[0][0] and deep:
            try:
                v = _run([self.program, "--version"], 20)
            except RuntimeError as e:
                v = f"? ({e})"
            rows.append((bool(v) and not v.startswith("?"), f"{self.program} version {v}", f"run `{self.program} --version` by hand"))
        return rows

    def _flags(self, *, model: str, effort: str, headless: bool, perms: str, add_dirs: list, rules: list, guard: dict, agents: str) -> list[str]:
        cmd = []
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        if headless:
            # -p: no terminal. Anything not allowed becomes a permission card in NAVI (the `permit` hook) and waits for
            # you. stream-json lets the server show what it's doing live and read the final cost.
            cmd += ["-p", "--output-format", "stream-json", "--verbose", "--permission-prompts", "none"]
        if perms == "skip":              # the user chose it at launch: nothing is checked, not even WARDEN's guard
            cmd += ["--dangerously-skip-permissions"]
        elif headless or perms in ("auto", "all"):
            cmd += ["--permission-mode", {"auto": "auto", "all": "bypassPermissions"}.get(perms, "acceptEdits")]
            if guard and (headless or perms == "all"):
                cmd += ["--settings", json.dumps(claude_settings(guard))]     # the guard stays hard even with bypassPermissions
        for folder in add_dirs or []:      # sources of truth outside the project: it may read there
            cmd += ["--add-dir", folder]
        if agents:      # the members as registered subagent types (agents.json): with -p a file, in a terminal the JSON
            cmd += ["--agents", agents if headless else Path(agents).read_text(encoding="utf-8")]
        cmd += ["--allowedTools", ",".join(dict.fromkeys(rules))]
        return cmd

    def moderator(self, cfg, *, prompt, model, effort, headless, conv, cont, perms, add_dirs, rules, guard, agents):
        # The prompt comes FIRST so the variadic --allowedTools can't swallow it
        cmd = [self.program, prompt]
        if conv:
            cmd += ["--resume", conv] if cont else ["--session-id", conv]
        elif cont:
            cmd += ["--continue"]
        return cmd + self._flags(model=self.run_model(cfg, model), effort=effort, headless=headless, perms=perms,
                                 add_dirs=add_dirs, rules=rules, guard=guard, agents=agents)

    def member(self, cfg, *, prompt, model, effort, perms, add_dirs, rules, guard):
        return [self.program, prompt] + self._flags(model=self.run_model(cfg, model), effort=effort, headless=True, perms=perms,
                                                    add_dirs=add_dirs, rules=rules, guard=guard, agents="")

    def ask(self, cfg, prompt, model="", timeout=240):
        if not self.path():
            raise RuntimeError(f"the `{self.program}` command isn't installed")
        m = self.resolve(cfg, model or "balanced")
        env = {k: v for k, v in self.env(cfg).items() if v is not None}
        return _run([self.program, "-p", "--tools", "", "--no-session-persistence", "--output-format", "text"]
                    + (["--model", m] if m else []) + [prompt], timeout, env=env)


OLLAMA_URL = "http://localhost:11434"
LOCAL_CONTEXT = 65536       # Claude Code's own instructions are ~14k tokens; Ollama itself asks for 64k
NAVI_COPY = re.compile(r"-navi\d+k$")      # NAVI's copies of your models with a bigger context window (same weights)
# tool-capable open models that run a council well, best first (any installed model with tools can be picked)
LOCAL_PICKS = ("qwen3-coder:30b", "qwen3-coder", "gpt-oss:120b", "gpt-oss:20b", "qwen3:32b", "qwen3:30b", "devstral",
               "qwen2.5-coder:32b", "qwen3:14b", "qwen2.5:32b", "qwen2.5-coder:14b", "qwen2.5:14b", "qwen3:8b", "qwen2.5:7b",
               "llama3.1:8b", "qwen3:4b", "qwen2.5:3b")


class LocalStream(ClaudeStream):
    free = True


class Local(Claude):
    """Your own models through Ollama, run by Claude Code: Ollama speaks the Anthropic API, so everything NAVI has
    (the hard guard, permission cards, registered members) works the same. The tiers map Claude's names to your models."""
    id, name = "local", "Local (Ollama)"
    blurb = "Open models on this machine through Ollama (Qwen, gpt-oss, Llama...), run by Claude Code. Free and private; slower."
    install_hint = "install Ollama (https://ollama.com) and Claude Code"
    defaults = {"strong": "", "balanced": "", "fast": ""}
    efforts = ()            # local models take no effort setting
    can = {"subagents": True, "guard": True, "cards": True, "auto": False, "cost": False, "resume": True, "terminal": True}
    Stream = LocalStream

    def url(self, cfg: dict) -> str:
        u = self.settings(cfg).get("url") or os.environ.get("OLLAMA_HOST") or OLLAMA_URL
        u = u if u.startswith("http") else f"http://{u}"
        return u.rstrip("/")

    _cache: dict = {}

    def installed_models(self, cfg: dict) -> list[dict]:
        """Ollama's models: [{name, size (GB), params, tools}], tool-capable ones first, best picks first. Remembered for
        a few seconds (the interface asks often), so a page load never waits on Ollama twice."""
        url = self.url(cfg)
        hit = self._cache.get(url)
        if hit and time.time() - hit[0] < 8:
            return hit[1]
        try:
            tags = (_get_json(url + "/api/tags", 2).get("models")) or []
        except (OSError, ValueError, urllib.error.URLError):
            self._cache[url] = (time.time(), [])
            return []
        out = []
        for t in tags:
            name = str(t.get("name") or "")
            if not name or "embed" in name or NAVI_COPY.search(name):
                continue
            caps = t.get("capabilities")
            if caps is None:
                try:
                    caps = _get_json(self.url(cfg) + "/api/show", 3, {"model": name}).get("capabilities") or []
                except (OSError, ValueError, urllib.error.URLError):
                    caps = []
            out.append({"name": name, "size": round(int(t.get("size") or 0) / 1e9, 1),
                        "params": str((t.get("details") or {}).get("parameter_size") or ""), "tools": "tools" in caps,
                        "thinking": "thinking" in caps})
        rank = {n: i for i, n in enumerate(LOCAL_PICKS)}
        out = sorted(out, key=lambda m: (not m["tools"], rank.get(m["name"], rank.get(m["name"].split(":")[0], 99)), -m["size"]))
        self._cache[url] = (time.time(), out)
        return out

    def suggest(self, cfg: dict) -> dict:
        """Tier models from what's installed: the best for strong, a lighter one for fast."""
        ms = [m for m in self.installed_models(cfg) if m["tools"]]
        if not ms:
            return {t: "" for t in TIERS}
        best = ms[0]["name"]
        by_size = sorted(ms, key=lambda m: m["size"])
        light = next((m["name"] for m in by_size if 4 <= m["size"] < 12), by_size[-1]["name"] if len(by_size) == 1 else by_size[0]["name"])
        return {"strong": best, "balanced": best, "fast": light}

    def tier_models(self, cfg: dict) -> dict:
        mine = self.settings(cfg).get("models") or {}
        if all(mine.get(t) for t in TIERS):
            return {t: str(mine[t]) for t in TIERS}
        sug = self.suggest(cfg)
        return {t: str(mine.get(t) or sug.get(t) or "") for t in TIERS}

    def choices(self, cfg: dict) -> list[dict]:
        base = Engine.choices(self, cfg)
        tm = set(self.tier_models(cfg).values())
        return base + [{"value": m["name"], "label": m["name"], "model": m["name"], "note": f"{m['params'] or m['size']}"}
                       for m in self.installed_models(cfg) if m["tools"] and m["name"] not in tm]

    def resolve(self, cfg: dict, value) -> str:
        return Engine.resolve(self, cfg, value)

    def run_model(self, cfg: dict, value) -> str:
        return self.copy_of(cfg, self.resolve(cfg, value))

    def describe(self, cfg: dict, value) -> str:
        return Engine.describe(self, cfg, value)

    def default(self, cfg: dict) -> str:
        return self.tier_models(cfg)["strong"]       # ANTHROPIC_MODEL in env()

    def info(self, cfg: dict) -> dict:
        return {**super().info(cfg), "context": self.context(cfg)}

    def member_alias(self, cfg: dict, value) -> str:
        """Members are registered with Claude's names; env() points each name at the local model for its tier."""
        t = tier_of(value)
        return {"strong": "opus", "balanced": "sonnet", "fast": "haiku"}.get(t, "inherit") if t or not value else "inherit"

    def env(self, cfg: dict) -> dict:
        tm = {t: self.copy_of(cfg, m) for t, m in self.tier_models(cfg).items()}
        # what `ollama launch claude` sets, per tier (on NAVI's copies with the bigger window). The key is set empty so an Anthropic key of yours never goes to (or
        # is tried against) the local server; no telemetry or update checks, so it all stays on this machine; and Claude
        # Code compacts at the window Ollama really has (it would assume 200k and lose the start of the conversation).
        return {"ANTHROPIC_BASE_URL": self.url(cfg), "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": "",
                "ANTHROPIC_MODEL": tm["strong"], "ANTHROPIC_DEFAULT_OPUS_MODEL": tm["strong"], "ANTHROPIC_DEFAULT_FABLE_MODEL": tm["strong"],
                "ANTHROPIC_DEFAULT_SONNET_MODEL": tm["balanced"], "ANTHROPIC_DEFAULT_HAIKU_MODEL": tm["fast"],
                "CLAUDE_CODE_SUBAGENT_MODEL": None, "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(self.context(cfg))}

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        rows = [(bool(self.path()), "Claude Code installed (it runs the local models)", "install Claude Code: https://claude.com/claude-code")]
        ms = self.installed_models(cfg)
        if not ms and not self._answers(cfg):
            rows.append((False, f"Ollama answering at {self.url(cfg)}", "install Ollama from https://ollama.com and start it (the app, or `ollama serve`)"))
            return rows
        rows.append((True, f"Ollama answering at {self.url(cfg)}", ""))
        tools = [m for m in ms if m["tools"]]
        rows.append((bool(tools), f"{len(tools)} local model(s) that can use tools" + (f": {', '.join(m['name'] for m in tools[:4])}" if tools else ""),
                     "pull one: `ollama pull qwen3-coder:30b` (about 19 GB; needs 32 GB of RAM) or `ollama pull qwen3:8b` (5 GB)"))
        tm = self.tier_models(cfg)
        names = {m["name"] for m in ms}
        missing = sorted({m for m in tm.values() if m and m not in names and f"{m}:latest" not in names})
        if missing:
            rows.append((False, f"tier models pulled ({', '.join(missing)} missing)", f"`ollama pull {missing[0]}`, or pick installed ones: `navi engine`"))
        return rows

    def context(self, cfg: dict) -> int:
        """The context window the models run with: your setting (Settings > Engine), else 64k."""
        n = self.settings(cfg).get("context")
        return n if isinstance(n, int) and n >= 8192 else LOCAL_CONTEXT

    def copy_of(self, cfg: dict, model: str) -> str:
        """The copy of a model NAVI runs: the same weights with NAVI's context window (Ollama often loads a model with
        4-32k, and silently drops the start of a longer prompt: the instructions)."""
        return f"{model}-navi{self.context(cfg) // 1024}k" if model and not NAVI_COPY.search(model) else model

    def prepare(self, cfg: dict) -> list[str]:
        """Make the copies the tiers need (a few KB each, no download); the first run of each loads it once."""
        try:
            have = {str(t.get("name")) for t in (_get_json(self.url(cfg) + "/api/tags", 3).get("models") or [])}
        except (OSError, ValueError, urllib.error.URLError):
            return []
        made = []
        for base in dict.fromkeys(m for m in self.tier_models(cfg).values() if m):
            copy = self.copy_of(cfg, base)
            if copy not in have and f"{copy}:latest" not in have and base in have | {h.removesuffix(":latest") for h in have}:
                try:
                    _get_json(self.url(cfg) + "/api/create", 120, {"model": copy, "from": base, "stream": False,
                                                                   "parameters": {"num_ctx": self.context(cfg)}})
                    made.append(copy)
                except (OSError, ValueError, urllib.error.URLError):
                    pass          # it runs with Ollama's own window then; the wizard says how to raise it
        self._cache.clear()
        return made

    def _answers(self, cfg: dict) -> bool:
        try:
            _get_json(self.url(cfg) + "/api/version", 2)
            return True
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def ask(self, cfg, prompt, model="", timeout=240):
        """Straight to Ollama: no program in between, so it's quick."""
        m = self.resolve(cfg, model or "balanced") or self.tier_models(cfg)["strong"]
        if not m:
            raise RuntimeError("no local model picked yet: run `navi engine`")
        try:
            r = _get_json(self.url(cfg) + "/api/chat", timeout, {"model": m, "stream": False, "messages": [{"role": "user", "content": prompt}],
                                                                  "options": {"num_ctx": 16384}})
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Ollama said {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        except (OSError, ValueError, urllib.error.URLError) as e:
            raise RuntimeError(f"Ollama isn't answering at {self.url(cfg)} ({e})")
        return str((r.get("message") or {}).get("content") or "").strip()


# ---------------------------------------------------------------- Codex

def _toml_str(v: str) -> str:
    return json.dumps(v)        # a JSON string is a valid TOML basic string


class CodexStream(Stream):
    """`codex exec --json`: thread.started (the conversation id), items (commands, file changes, messages, MCP calls) and
    turn.completed with the thread's running token total."""
    def __init__(self, model: str = ""):
        super().__init__(model)
        self.last, self.failed = "", ""

    def feed(self, m: dict) -> list[dict]:
        out, t = [], m.get("type")
        if t == "thread.started":
            self.conv = str(m.get("thread_id") or "")
            out.append({"kind": "init", "text": f"model {self.model or 'default'} · thread {self.conv[:8]}"})
        elif t in ("item.started", "item.completed"):
            it = m.get("item") if isinstance(m.get("item"), dict) else {}
            k = it.get("type")
            if k == "command_execution" and t == "item.started":
                cmd = it.get("command")
                out.append({"kind": "tool", "tool": "Bash", "text": (" ".join(cmd) if isinstance(cmd, list) else str(cmd or ""))[:300]})
            elif k == "file_change" and t == "item.completed":
                for c in it.get("changes") or []:
                    out.append({"kind": "tool", "tool": {"add": "Write", "delete": "Delete"}.get(c.get("kind"), "Edit"), "text": str(c.get("path") or "")[:300]})
            elif k == "mcp_tool_call" and t == "item.started":
                out.append({"kind": "tool", "tool": f"mcp__{it.get('server')}__{it.get('tool')}", "text": json.dumps(it.get("arguments"))[:300]})
            elif k == "web_search" and t == "item.started":
                out.append({"kind": "tool", "tool": "WebSearch", "text": str(it.get("query") or "")[:300]})
            elif k == "agent_message" and t == "item.completed" and str(it.get("text") or "").strip():
                self.last = str(it["text"]).strip()
                out.append({"kind": "text", "text": self.last[:400]})
            elif k == "error" and not any(w in str(it.get("message") or "") for w in CODEX_NOTICES):
                out.append({"kind": "text", "text": f"error: {str(it.get('message') or '')[:300]}"})
        elif t == "turn.completed":
            self.turns += 1
            u = m.get("usage") or {}
            cached = int(u.get("cached_input_tokens") or 0)
            self.live = {self.model or "codex": {"in": max(0, int(u.get("input_tokens") or 0) - cached), "out": int(u.get("output_tokens") or 0),
                                                 "cache_read": cached, "cache_write": int(u.get("cache_write_input_tokens") or 0),
                                                 "thinking": int(u.get("reasoning_output_tokens") or 0), "usd": 0}}
        elif t in ("turn.failed", "error"):
            self.failed = str(((m.get("error") or {}) if isinstance(m.get("error"), dict) else {}).get("message") or m.get("message") or "")[:300]
            out.append({"kind": "result", "text": f"failed: {self.failed}"})
        return out

    def finish(self) -> dict | None:
        if not (self.conv or self.live):
            return None
        mu = {k: {"inputTokens": v["in"], "outputTokens": v["out"], "cacheReadInputTokens": v["cache_read"],
                  "cacheCreationInputTokens": v["cache_write"], "thinkingTokens": v["thinking"], "costUSD": 0, "canonicalModel": k}
              for k, v in self.live.items()}
        # each run its own key: whether a resumed thread's total includes the earlier runs isn't documented, and a sum
        # is the safer mistake than losing a run
        return {"type": "result", "subtype": "error" if self.failed else "success", "session_id": f"{self.conv or 'run'}:{int(self.t0)}",
                "total_cost_usd": 0, "duration_ms": int((time.time() - self.t0) * 1000), "num_turns": self.turns, "modelUsage": mu,
                "result": self.last}


CODEX_NOTICES = ("bypass-hook-trust", "Model metadata for")      # Codex reports these as "error" items; they're notices


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


class Codex(Engine):
    """OpenAI's Codex CLI. Background runs are `codex exec --json`, resumed by thread id; members run as their own Codex
    runs (`navi run`); NAVI's guard is a Codex PreToolUse hook passed for the run (a hook can't ask, so NAVI's "ask"
    becomes a deny that says to ask you first). `codex exec` never stops to ask a human: no permission cards."""
    id, name, program = "codex", "Codex", "codex"
    blurb = "OpenAI's Codex CLI on your ChatGPT or OpenAI account. Members run as their own Codex runs."
    install_hint = "install Codex: `npm i -g @openai/codex`, then `codex login`"
    defaults = {"strong": "", "balanced": "", "fast": ""}
    efforts = ("low", "medium", "high", "xhigh", "max")
    can = {"subagents": False, "guard": True, "cards": False, "auto": True, "cost": False, "resume": True, "terminal": True}
    Stream = CodexStream
    own_ids = True
    oss = False         # Codex on local models (Ollama) instead of OpenAI's

    def default_model(self) -> str:
        """What Codex runs when NAVI names no model: the `model = ...` at the top of its config.toml."""
        try:
            top = (codex_home() / "config.toml").read_text(encoding="utf-8").split("\n[", 1)[0]
        except OSError:
            return ""
        m = re.search(r'(?m)^\s*model\s*=\s*"([^"]+)"', top)
        return m.group(1) if m else ""

    def stream(self, model: str = "") -> Stream:
        return self.Stream(model or self.default_model() or self.id)

    def default(self, cfg: dict) -> str:
        return self.default_model()

    def catalog(self) -> list[dict]:
        """Codex's own list of models (models_cache.json), the ones it shows, best first."""
        try:
            d = json.loads((codex_home() / "models_cache.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        ms = [m for m in (d.get("models") or []) if isinstance(m, dict) and m.get("slug") and m.get("visibility") != "hide"]
        return [{"slug": m["slug"], "name": m.get("display_name") or m["slug"],
                 "efforts": [x.get("effort") for x in m.get("supported_reasoning_levels") or [] if isinstance(x, dict)]}
                for m in sorted(ms, key=lambda m: m.get("priority") or 99)]

    def tier_models(self, cfg: dict) -> dict:
        mine = self.settings(cfg).get("models") or {}
        cat = [m["slug"] for m in self.catalog()]
        strong = cat[0] if cat else ""
        fast = next((c for c in cat if any(w in c for w in ("luna", "mini", "lite", "nano"))), "")
        balanced = next((c for c in cat[1:] if c not in (strong, fast) and "sol" in c), next((c for c in cat[1:] if c not in (strong, fast)), strong))
        sug = {"strong": strong, "balanced": balanced, "fast": fast or balanced}
        return {t: str(mine.get(t) or sug.get(t) or "") for t in TIERS}

    def choices(self, cfg: dict) -> list[dict]:
        tm = set(self.tier_models(cfg).values())
        return Engine.choices(self, cfg) + [{"value": m["slug"], "label": m["name"], "model": m["slug"], "note": ""}
                                            for m in self.catalog() if m["slug"] not in tm]

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        rows = super().checks(cfg)
        if rows[0][0] and not self.oss:
            signed = (codex_home() / "auth.json").exists() or bool(os.environ.get("OPENAI_API_KEY"))
            rows.append((signed, "signed in to Codex" if signed else "signed in to Codex", "run `codex login`"))
        if rows[0][0] and deep:
            try:
                v = _run([self.program, "--version"], 20)
            except RuntimeError as e:
                v = f"? ({e})"
            rows.append((bool(v) and not v.startswith("?"), f"{self.program} version {v}", f"run `{self.program} --version` by hand"))
        return rows

    def _effort(self, cfg: dict, model: str, effort: str) -> str:
        return effort

    def _guard(self, guard: dict) -> list[str]:
        """NAVI's guard as a hook for this run only. Codex runs a hook only once you've trusted it in its /hooks screen;
        NAVI vets its own hook (it's this file's sibling), so the run skips that for the hooks it was given."""
        hook = [{"matcher": ".*", "hooks": [{"type": "command", "command": guard["hook"], "timeout": 60}]}]
        val = "[" + ",".join("{matcher=%s,hooks=[%s]}" % (_toml_str(h["matcher"]), ",".join(
            "{type=%s,command=%s,timeout=%d}" % (_toml_str(x["type"]), _toml_str(x["command"]), x["timeout"]) for x in h["hooks"])) for h in hook) + "]"
        return ["-c", f"hooks.PreToolUse={val}", "--dangerously-bypass-hook-trust"]

    def _flags(self, cfg: dict, *, model: str, effort: str, perms: str, guard: dict, headless: bool) -> list[str]:
        f = []
        if self.oss:
            f += ["--oss", "--local-provider", "ollama"]
        m = self.run_model(cfg, model)
        if m:
            f += ["-m", m]
        effort = self._effort(cfg, self.resolve(cfg, model), effort)
        if effort:
            f += ["-c", f"model_reasoning_effort={_toml_str(effort)}"]
        if perms == "skip":                                   # nothing is checked: no sandbox, no guard
            return f + ["--dangerously-bypass-approvals-and-sandbox"]
        if perms == "auto" and headless:
            f += ["--approve-for-me"]                         # Codex's reviewer decides, in the workspace sandbox
        else:
            # ask: edits inside the project, nothing outside it (reads are fine anywhere); all: no sandbox at all
            f += ["-c", f"sandbox_mode={_toml_str('danger-full-access' if perms == 'all' else 'workspace-write')}"]
        if perms != "all" and (guard or {}).get("data") and Path(guard["data"]).name != ".navi":
            # NAVI keeps the project's data outside it (~/.navi/projects): `navi send` and the rest must write there
            f += ["-c", f"sandbox_workspace_write.writable_roots=[{_toml_str(guard['data'])}]"]
        if guard:
            f += self._guard(guard)
        return f

    def moderator(self, cfg, *, prompt, model, effort, headless, conv, cont, perms, add_dirs, rules, guard, agents):
        flags = self._flags(cfg, model=model, effort=effort, perms=perms, guard=guard, headless=headless)
        if not headless:                                      # its own terminal UI
            return [self.program] + flags + (["resume", conv] if cont and conv else ["resume", "--last"] if cont else []) + [prompt]
        cmd = [self.program, "exec", "--json", "--skip-git-repo-check"] + flags
        return cmd + (["resume", conv, prompt] if cont and conv else [prompt])

    def member(self, cfg, *, prompt, model, effort, perms, add_dirs, rules, guard):
        return [self.program, "exec", "--json", "--skip-git-repo-check", "--ephemeral"] + \
            self._flags(cfg, model=model, effort=effort, perms=perms, guard=guard, headless=True) + [prompt]

    def ask(self, cfg, prompt, model="", timeout=240):
        if not self.path():
            raise RuntimeError(f"the `{self.program}` command isn't installed")
        m = self.resolve(cfg, model or "balanced")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "answer.txt"
            _run([self.program, "exec", "--skip-git-repo-check", "--ephemeral", "-c", 'sandbox_mode="read-only"', "-o", str(out)]
                 + (["--oss", "--local-provider", "ollama"] if self.oss else []) + (["-m", m] if m else [])
                 + ["-c", 'model_reasoning_effort="medium"'] * (not self.oss) + [prompt], timeout, cwd=tmp)
            try:
                return out.read_text(encoding="utf-8").strip()
            except OSError:
                raise RuntimeError("Codex finished without an answer")


class LocalCodex(Codex):
    """Your Ollama models, run by Codex (`--oss`): for when you'd rather not use Claude Code."""
    id, name = "local-codex", "Local (Ollama) via Codex"
    blurb = "Open models on this machine through Ollama, run by Codex. Free and private; no permission cards."
    install_hint = "install Ollama (https://ollama.com) and Codex (`npm i -g @openai/codex`)"
    efforts = ()
    can = {"subagents": False, "guard": True, "cards": False, "auto": False, "cost": False, "resume": True, "terminal": True}
    oss = True

    def _local(self) -> "Local":
        return ENGINES["local"]

    def resolve(self, cfg: dict, value) -> str:
        """No model named: the strong tier (Codex's own local default would be a 13 GB download you didn't ask for)."""
        return Engine.resolve(self, cfg, value or "strong")

    def default(self, cfg: dict) -> str:
        return self.tier_models(cfg)["strong"]

    def stream(self, model: str = "") -> Stream:
        return self.Stream(model or self.id)

    def run_model(self, cfg: dict, value) -> str:
        return self._local().copy_of(cfg, self.resolve(cfg, value))

    def info(self, cfg: dict) -> dict:
        return {**super().info(cfg), "context": self._local().context(cfg)}

    def prepare(self, cfg: dict) -> list[str]:
        loc = {**(cfg.get("engines") or {}).get("local", {}), "models": self.tier_models(cfg)}
        return self._local().prepare({**cfg, "engines": {**(cfg.get("engines") or {}), "local": loc}})

    def _effort(self, cfg: dict, model: str, effort: str) -> str:
        """Your Codex settings may ask for reasoning a local model doesn't have (Ollama then refuses the request): off,
        unless the model can think."""
        thinks = next((m["thinking"] for m in self._local().installed_models(cfg) if m["name"] == model), False)
        return ({"xhigh": "high", "max": "high"}.get(effort, effort) or "medium") if thinks else "none"

    def tier_models(self, cfg: dict) -> dict:
        mine = self.settings(cfg).get("models") or {}
        loc = self._local().tier_models(cfg)
        return {t: str(mine.get(t) or loc.get(t) or "") for t in TIERS}

    def choices(self, cfg: dict) -> list[dict]:
        tm = set(self.tier_models(cfg).values())
        return Engine.choices(self, cfg) + [{"value": m["name"], "label": m["name"], "model": m["name"], "note": m["params"]}
                                            for m in self._local().installed_models(cfg) if m["tools"] and m["name"] not in tm]

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        return [(bool(self.path()), "Codex installed (it runs the local models)", "install Codex: `npm i -g @openai/codex`")] + \
            self._local().checks(cfg)[1:]

    def ask(self, cfg, prompt, model="", timeout=240):
        return self._local().ask(cfg, prompt, self.resolve(cfg, model or "balanced"), timeout)


# ---------------------------------------------------------------- Gemini

class GeminiStream(Stream):
    """`gemini -o stream-json`: init (session id, model), messages (whole or in deltas), tool_use / tool_result, and a
    result with the run's token stats."""
    def __init__(self, model: str = ""):
        super().__init__(model)
        self.buf, self.last = "", ""

    def _flush(self) -> list[dict]:
        t, self.buf = self.buf.strip(), ""
        if t:
            self.last = t
            return [{"kind": "text", "text": t[:400]}]
        return []

    def feed(self, m: dict) -> list[dict]:
        out, t = [], m.get("type")
        if t == "init":
            self.conv = str(m.get("session_id") or "")
            self.model = str(m.get("model") or self.model)
            out.append({"kind": "init", "text": f"model {self.model or 'default'}"})
        elif t == "message" and m.get("role") == "assistant":
            self.buf += str(m.get("content") or "")
            if not m.get("delta"):
                out += self._flush()
        elif t == "tool_use":
            out += self._flush()
            p = m.get("parameters") if isinstance(m.get("parameters"), dict) else {}
            text = p.get("command") or p.get("file_path") or p.get("absolute_path") or p.get("pattern") or p.get("url") or json.dumps(p)[:200]
            out.append({"kind": "tool", "tool": str(m.get("tool_name") or ""), "text": str(text)[:300]})
        elif t == "tool_result" and m.get("status") == "error":
            out.append({"kind": "text", "text": f"tool error: {str((m.get('error') or {}).get('message') if isinstance(m.get('error'), dict) else m.get('error') or '')[:300]}"})
        elif t == "error":
            out.append({"kind": "text", "text": f"error: {str(m.get('message') or '')[:300]}"})
        elif t == "result":
            out += self._flush()
            st = m.get("stats") if isinstance(m.get("stats"), dict) else {}
            per = st.get("models") if isinstance(st.get("models"), dict) else {}
            usage = {}
            for name, v in per.items() if per else [(self.model or "gemini", st)]:
                v = v if isinstance(v, dict) else {}
                tok = v.get("tokens") if isinstance(v.get("tokens"), dict) else v
                cached = int(tok.get("cached") or 0)
                usage[name] = {"inputTokens": max(0, int(tok.get("input_tokens") or tok.get("prompt") or tok.get("input") or 0) - cached),
                               "outputTokens": int(tok.get("output_tokens") or tok.get("candidates") or 0), "cacheReadInputTokens": cached,
                               "cacheCreationInputTokens": 0, "thinkingTokens": int(tok.get("thoughts") or 0), "costUSD": 0, "canonicalModel": name}
            self.result = {"type": "result", "subtype": str(m.get("status") or "success"), "session_id": f"{self.conv or 'run'}:{int(self.t0)}",
                           "total_cost_usd": 0, "duration_ms": int(st.get("duration_ms") or (time.time() - self.t0) * 1000),
                           "num_turns": int(st.get("tool_calls") or 0), "modelUsage": usage, "result": self.last}
            out.append({"kind": "result", "text": f"{m.get('status', '')} · {int(st.get('total_tokens') or 0)} tokens"})
        return out


GEMINI_TOOLS = {"Bash": "run_shell_command"}


class Gemini(Engine):
    """Google's Gemini CLI. Background runs are `gemini -p -o stream-json`, resumed by session id; members run as their
    own Gemini runs (`navi run`). Headless Gemini denies whatever would need your approval, so: no permission cards.
    NAVI's guard is a BeforeTool hook. Gemini takes hooks only from its settings files (a system file only when root
    owns it), so each run gets a Gemini home of NAVI's own: yours, linked in, with the hook added (guard_env)."""
    id, name, program = "gemini", "Gemini", "gemini"
    blurb = "Google's Gemini CLI on your Google account. Members run as their own Gemini runs; no permission cards."
    install_hint = "install Gemini CLI: `npm i -g @google/gemini-cli`, then set GEMINI_API_KEY (a key from Google AI Studio) or sign in with `gemini`"
    defaults = {"strong": "gemini-2.5-pro", "balanced": "gemini-2.5-flash", "fast": "gemini-3.1-flash-lite"}
    efforts = ()
    can = {"subagents": False, "guard": True, "cards": False, "auto": False, "cost": False, "resume": True, "terminal": True}
    Stream = GeminiStream
    HOOK = "navi-guard"

    def guard_env(self, guard: dict) -> dict:
        """GEMINI_CLI_HOME = a folder of NAVI's (guard["home"]) whose .gemini links everything in yours (sign-in,
        sessions, history, extensions) except settings.json: a copy of yours with NAVI's guard as a BeforeTool hook,
        hooks switched on, and the guard never on the list of switched-off hooks."""
        if not guard.get("hook") or not guard.get("home"):
            return {}
        home = Path(guard["home"])
        # yours: inside a run NAVI started, GEMINI_CLI_HOME is already NAVI's (a member started from there)
        base = Path(os.environ.get("NAVI_GEMINI_USER_HOME") or os.environ.get("GEMINI_CLI_HOME") or Path.home())
        if base.resolve() == home.resolve():
            base = Path.home()
        real = base / ".gemini"
        mine = home / ".gemini"
        mine.mkdir(parents=True, exist_ok=True)
        keep = set()
        for x in sorted(real.iterdir()) if real.is_dir() else []:
            if x.name == "settings.json":
                continue
            keep.add(x.name)
            link = mine / x.name
            if link.is_symlink() and os.readlink(link) == str(x):
                continue
            if link.is_dir() and not link.is_symlink():
                continue                            # Gemini made it here first (sessions before you had any): keep it
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(x)
        for x in mine.iterdir():                    # gone from yours: gone from here
            if x.is_symlink() and x.name not in keep:
                x.unlink()
        try:
            st = json.loads((real / "settings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        st = st if isinstance(st, dict) else {}
        hooks = st.get("hooks") if isinstance(st.get("hooks"), dict) else {}
        theirs = [h for h in hooks.get("BeforeTool") or [] if isinstance(h, dict)
                  and not any(isinstance(x, dict) and x.get("name") == self.HOOK for x in h.get("hooks") or [])]
        # every tool: a timeout or a crash would let the call through (Gemini fails open), so the hook itself never fails open
        ours = {"matcher": "*", "hooks": [{"name": self.HOOK, "type": "command", "command": guard["hook"], "timeout": 30000,
                                           "description": "NAVI's guard: keys, .env and state files stay out of every agent's context"}]}
        st["hooks"] = {**hooks, "BeforeTool": [ours] + theirs}
        hc = st.get("hooksConfig") if isinstance(st.get("hooksConfig"), dict) else {}
        st["hooksConfig"] = {**hc, "enabled": True, "disabled": [d for d in hc.get("disabled") or [] if d not in (self.HOOK, guard["hook"])]}
        tmp = mine / "settings.json.tmp"
        tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
        os.replace(tmp, mine / "settings.json")
        return {"GEMINI_CLI_HOME": str(home), "NAVI_GEMINI_USER_HOME": str(base)}

    def choices(self, cfg: dict) -> list[dict]:
        tm = set(self.tier_models(cfg).values())
        extra = ["gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
        return Engine.choices(self, cfg) + [{"value": m, "label": m, "model": m, "note": ""} for m in extra if m not in tm]

    def checks(self, cfg: dict, deep: bool = False) -> list[tuple[bool, str, str]]:
        rows = super().checks(cfg)
        if rows[0][0]:
            home = Path(os.environ.get("GEMINI_CLI_HOME") or Path.home()) / ".gemini"
            signed = (home / "oauth_creds.json").exists() or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            rows.append((signed, "signed in to Gemini" if not os.environ.get("GEMINI_API_KEY") else "a Gemini API key",
                         "set GEMINI_API_KEY (a key from Google AI Studio), or run `gemini` once and sign in"))
        return rows

    @staticmethod
    def _allowed(rules: list) -> list[str]:
        """Claude-style rules ('Bash(navi:*)') as Gemini's allowed tools ('run_shell_command(navi)')."""
        out = []
        for r in rules or []:
            m = re.fullmatch(r"(\w+)\((.*?)(?::\*| \*)?\)", r)
            if m and m.group(1) in GEMINI_TOOLS:
                out.append(f"{GEMINI_TOOLS[m.group(1)]}({m.group(2).strip()})")
        return list(dict.fromkeys(out))

    def _flags(self, cfg: dict, *, model: str, perms: str, rules: list) -> list[str]:
        f = []
        m = self.resolve(cfg, model)
        if m:
            f += ["-m", m]
        if perms in ("all", "skip"):
            f += ["--approval-mode", "yolo"]
        else:      # ask: edits go through, shell commands only the allowed ones (navi, the usual checks); the rest is denied
            f += ["--approval-mode", "auto_edit"] + [x for a in self._allowed(rules) for x in ("--allowed-tools", a)]
        return f + ["--skip-trust"]

    def moderator(self, cfg, *, prompt, model, effort, headless, conv, cont, perms, add_dirs, rules, guard, agents):
        flags = self._flags(cfg, model=model, perms=perms, rules=rules)
        resume = (["-r", conv] if cont and conv else ["-r", "latest"] if cont else (["--session-id", conv] if conv else []))
        if not headless:
            return [self.program] + flags + resume + ["-i", prompt]
        return [self.program, "-p", prompt, "-o", "stream-json"] + flags + resume

    def member(self, cfg, *, prompt, model, effort, perms, add_dirs, rules, guard):
        return [self.program, "-p", prompt, "-o", "stream-json"] + self._flags(cfg, model=model, perms=perms, rules=rules)

    def ask(self, cfg, prompt, model="", timeout=240):
        if not self.path():
            raise RuntimeError(f"the `{self.program}` command isn't installed")
        m = self.resolve(cfg, model or "balanced")
        with tempfile.TemporaryDirectory() as tmp:
            raw = _run([self.program, "-p", prompt, "-o", "json", "--approval-mode", "plan", "--skip-trust"] + (["-m", m] if m else []), timeout, cwd=tmp)
        try:
            j = json.loads(raw[raw.find("{"):])
        except ValueError:
            return raw
        if j.get("error"):
            raise RuntimeError(str((j["error"] or {}).get("message") if isinstance(j["error"], dict) else j["error"])[:300])
        return str(j.get("response") or "").strip()


ENGINES: dict = {e.id: e for e in (Claude(), Local(), Codex(), LocalCodex(), Gemini())}
DEFAULT_ENGINE = "claude"


def get(engine_id: str | None) -> Engine:
    return ENGINES.get(str(engine_id or "")) or ENGINES[DEFAULT_ENGINE]


def clean_settings(raw) -> dict:
    """The `engines` part of the config, as the interface or the wizard sends it: per engine, its tier models and url."""
    out = {}
    for eid, s in (raw or {}).items() if isinstance(raw, dict) else []:
        if eid not in ENGINES or not isinstance(s, dict):
            continue
        e = {}
        models = s.get("models") if isinstance(s.get("models"), dict) else {}
        e["models"] = {t: str(models[t]) for t in TIERS if isinstance(models.get(t), str) and (models[t] == "" or MODEL_ID.match(models[t]))}
        if isinstance(s.get("url"), str) and re.fullmatch(r"https?://[\w.:\-\[\]]+(/[\w./-]*)?", s["url"]):
            e["url"] = s["url"].rstrip("/")
        if isinstance(s.get("context"), int) and 8192 <= s["context"] <= 262144:
            e["context"] = s["context"]
        out[eid] = e
    return out
