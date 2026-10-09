"""
guard.py - WARDEN's deterministic core: data policy, access decisions and the outbound secret scanner.

Pure functions, zero dependencies. Decisions are made from METADATA ONLY (paths, file names,
command lines). Nothing in here ever opens the file being judged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from fnmatch import fnmatchcase
from pathlib import Path

ALLOW, ASK, DENY = "allow", "ask", "deny"
SEVERITY = {ALLOW: 0, ASK: 1, DENY: 2}
SENSITIVITY = ("public", "internal", "confidential")

DEFAULT_POLICY = {
    "version": 1,
    "sensitivity": "internal",   # public | internal | confidential
    "scope": ["."],              # what agents may read, relative to the project root
    "outbound": "redact",        # redact | block - what to do when a secret shows up in agent output
    "allow": [".env.example", ".env.sample", ".env.template", "*.tfvars.example"],
    "deny": [
        ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.kdbx",
        "id_rsa*", "id_ed25519*", "id_ecdsa*", "*.tfstate", "*.tfstate.*",
        "kubeconfig", "*.kubeconfig", ".kube/*", ".ssh/*", ".aws/*", ".azure/*", ".gnupg/*",
        ".docker/config.json", ".npmrc", ".pypirc", ".netrc", ".git-credentials",
        "secrets/*", "*.secret", "*.secrets",
    ],
    "ask": [
        "*.tfvars", "*.auto.tfvars", "*.sql", "*.csv", "*.tsv", "*.parquet", "*.xlsx", "*.xls",
        "*.bak", "*.dump", "*.db", "*.sqlite", "*.log",
        "data/*", "dumps/*", "backup*/*", "prod/*", "production/*", "customers/*",
    ],
    # a trailing $ means "exactly this command, no arguments" (e.g. bare `env` dumps the environment)
    "deny_commands": [
        "env$", "set$", "export$", "export -p", "printenv", "history",
        "terraform state pull", "terraform show",
        "az keyvault secret show", "az keyvault secret download", "az account get-access-token",
        "aws secretsmanager get-secret-value", "aws ssm get-parameter", "aws sts get-session-token",
        "gcloud secrets versions access", "gcloud auth print-access-token",
        "kubectl get secret", "kubectl get secrets", "kubectl describe secret",
        "gh auth token", "security find-generic-password",
    ],
    "ask_commands": [
        "terraform output", "terraform console", "az keyvault secret list", "kubectl exec",
        "psql", "mysql", "sqlcmd", "mongosh", "redis-cli", "scp", "rsync", "nc", "ncat", "ftp",
    ],
}

UPLOADERS = {"curl", "wget", "http", "https", "httpie", "xh"}
UPLOAD_FLAGS = re.compile(r"^(-d|--data.*|-F|--form.*|-T|--upload-file|--post-file.*|--body-file.*|@.+)$")


# ---------------------------------------------------------------- policy

def load_policy(navi: Path) -> dict | None:
    p = navi / "policy.json"
    if not p.exists():
        return None
    try:
        user = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        user = {}
    try:      # folders and files the user named as sources of truth (NAVI writes them at launch): reading them is fine
        named = json.loads((navi / "sources.json").read_text(encoding="utf-8"))
        folders = (named.get("folders") or []) + (named.get("files") or [])
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        folders = []
    return {**DEFAULT_POLICY, **user, "sources": [f for f in folders if isinstance(f, str)]}


def save_policy(navi: Path, pol: dict):
    (navi / "policy.json").write_text(json.dumps(pol, indent=2) + "\n", encoding="utf-8")


def load_rulings(navi: Path) -> list[dict]:
    try:
        return json.loads((navi / "rulings.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def add_ruling(navi: Path, ruling: dict):
    rulings = [r for r in load_rulings(navi) if (r["action"], r["key"]) != (ruling["action"], ruling["key"])]
    rulings.append(ruling)
    (navi / "rulings.json").write_text(json.dumps(rulings, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- where NAVI keeps a project's data
# Never inside the project: ~/.navi/projects/<folder>-<id>/ holds a project's sessions, policy, agents and server state
# (project.json there names the project folder), so nothing of NAVI's ends up in your repository. ~/.navi/roots lists
# the project folders NAVI knows, for the plugin's hook to tell at once whether a folder is one of them. An old
# <project>/.navi/ is still read, until NAVI moves it out (navi.py project_dir).
NAVI_HOME = Path(os.environ.get("NAVI_HOME") or "~/.navi").expanduser()


def data_dir(root: Path) -> Path:
    root = Path(root).expanduser().resolve()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name or "root").strip("-.")[:40] or "project"
    return NAVI_HOME / "projects" / f"{name}-{hashlib.sha1(str(root).encode()).hexdigest()[:8]}"


def project_root(navi: Path) -> Path:
    """The project folder a NAVI data dir belongs to."""
    navi = Path(navi)
    if navi.name == ".navi":                     # the old layout (and the tests, which point NAVI_DIR at one)
        return navi.parent
    try:
        return Path(json.loads((navi / "project.json").read_text(encoding="utf-8"))["root"])
    except (OSError, ValueError, KeyError, TypeError):
        return navi.parent


def find_navi(start: Path) -> Path | None:
    """The NAVI data (with a policy.json) of the project this folder is in: walking up from start, the old
    <folder>/.navi/ or the folder's own dir under ~/.navi/projects/."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / ".navi" / "policy.json").exists():
            return d / ".navi"
        if (data_dir(d) / "policy.json").exists():
            return data_dir(d)
    return None


# ---------------------------------------------------------------- decisions

def _under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def _match(patterns: list[str], parts: tuple[str, ...]) -> str | None:
    """Patterns without '/' match any path component; patterns with '/' match any path suffix."""
    low = [x.lower() for x in parts]
    for raw in patterns:
        pat = raw.strip().rstrip("/").lower()
        if not pat:
            continue
        if "/" in pat:
            if any(fnmatchcase("/".join(low[i:]), pat) for i in range(len(low))):
                return raw
        elif any(fnmatchcase(part, pat) for part in low):
            return raw
    return None


def resolve(target: str, cwd: Path) -> Path:
    p = Path(os.path.expanduser(target.strip()))
    return (p if p.is_absolute() else cwd / p).resolve()


def key_for(action: str, target: str, cwd: Path) -> str:
    if action in ("read", "write"):
        return str(resolve(target, cwd))
    return " ".join(target.split())


def decide_path(pol: dict, navi: Path, action: str, target: str, cwd: Path, scoped: bool = True):
    p = resolve(target, cwd)
    root = project_root(navi)
    inside = _under(p, root)
    parts = p.relative_to(root).parts if inside else p.parts[1:]
    if _under(p, navi) or _under(p, Path(__file__).resolve().parent.parent):
        return ALLOW, "navi workspace"
    if _match(pol["allow"], parts):
        return ALLOW, "explicitly allowed"
    pat = _match(pol["deny"], parts)
    if pat:
        return DENY, f"matches deny pattern '{pat}'"
    if str(p) in (pol.get("made") or ()):
        return ALLOW, "the council made it in this session"
    if action == "write":
        return (ALLOW, "write inside project") if inside or not scoped else (ASK, "write outside the project root")
    pat = _match(pol["ask"], parts)
    if pat:
        if pol["sensitivity"] == "public":
            return ALLOW, f"'{pat}' allowed in a public session"
        return ASK, f"matches sensitive pattern '{pat}'"
    if not scoped:
        return ALLOW, "no sensitive pattern"
    if any(_under(p, Path(f).expanduser().resolve()) for f in pol.get("sources") or []):
        return ALLOW, "a source of truth you named"
    strict = DENY if pol["sensitivity"] == "confidential" else ASK
    if not inside:
        return strict, "outside the project root"
    scopes = [resolve(s, root) for s in pol["scope"]] or [root]
    if not any(_under(p, s) for s in scopes):
        return strict, "outside the agreed scope (" + ", ".join(pol["scope"]) + ")"
    return ALLOW, "in scope"


def _cmd_match(toks: list[str], spec: str) -> bool:
    exact = spec.endswith("$")
    want = spec.rstrip("$").lower().split()
    return toks == want if exact else toks[:len(want)] == want


REDIRECT = re.compile(r"^(\d*|&)(>>?|>\|)(.*)$")       # > f, >> f, 2> f, &> f, >f (glued); not >&2
SCRATCH = tuple(dict.fromkeys(Path(p).resolve() for p in ("/tmp", "/var/folders", os.environ.get("TMPDIR") or "/tmp", "/dev")
                              if Path(p).exists()))


def shell_words(seg: str) -> list[str]:
    """A command's words with its operators apart (`x>~/f` is x, >, ~/f) and quoted text kept whole ('a > b')."""
    try:
        lex = shlex.shlex(seg, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return seg.split()
    return [w for i, w in enumerate(words) if not (w.isdigit() and i + 1 < len(words) and words[i + 1][:1] == ">")]   # 2>f


def write_targets(toks: list[str]) -> list[str]:
    """Where a shell command writes: redirects, tee, the destination of cp / mv / ln / install, touch and mkdir."""
    out, plain, i = [], [], 0
    while i < len(toks):
        m = REDIRECT.match(toks[i])
        if m and not toks[i].startswith("-"):
            t = m.group(3) or (toks[i + 1] if i + 1 < len(toks) else "")
            i += 1 if m.group(3) else 2
            if t and not t.startswith("&"):
                out.append(t)
            continue
        plain.append(toks[i])
        i += 1
    name, args = (Path(plain[0]).name if plain else ""), [t for t in plain[1:] if not t.startswith("-")]
    if name == "tee":
        out += args
    elif name in ("cp", "mv", "ln", "install", "rsync") and len(args) >= 2:
        out.append(args[-1])
    elif name in ("touch", "mkdir"):
        out += args
    return out


def split_commands(cmd: str) -> list[str]:
    """A shell line -> its simple commands: split on ; | || & && and newlines outside quotes, so the text of a quoted
    message (`git commit -m "a; b"`, `navi send --body "x | y"`) stays one word. $(...) and `...` run even inside double
    quotes: each is a command of its own too. When the quoting doesn't add up, split everywhere (check more, not less)."""
    legacy = lambda: re.split(r"\|\||&&|[;|\n]|\$\(|`", cmd)
    segs, subs, cur, q, i, n = [], [], [], "", 0, len(cmd)
    while i < n:
        c = cmd[i]
        if q == "'":                            # single quotes: nothing inside is special
            q = "" if c == "'" else q
            cur.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "`" or cmd.startswith("$(", i):
            if c == "`":
                end = cmd.find("`", i + 1)
                if end < 0:
                    return legacy()
                inner, j = cmd[i + 1:end], end + 1
            else:
                depth, j = 1, i + 2
                while j < n and depth:
                    depth += {"(": 1, ")": -1}.get(cmd[j], 0)
                    j += 1
                if depth:
                    return legacy()
                inner = cmd[i + 2:j - 1]
            subs += split_commands(inner)
            cur.append(cmd[i:j])
            i = j
            continue
        if c in "\"'":
            q = "" if q == c else (c if not q else q)
            cur.append(c)
            i += 1
            continue
        if not q and c in ";|&\n":
            prev, nxt = cmd[i - 1:i], cmd[i + 1:i + 2]
            if c == "&" and (prev in "<>" and prev or nxt == ">"):      # 2>&1, &> f: a redirect, not a new command
                cur.append(c)
                i += 1
                continue
            if c == "|" and prev == ">":                                # >| f
                cur.append(c)
                i += 1
                continue
            segs.append("".join(cur))
            cur = []
            i += 2 if (c in "&|" and nxt in "&|") else 1
            continue
        cur.append(c)
        i += 1
    if q:
        return legacy()
    segs.append("".join(cur))
    return [x for x in segs + subs if x.strip()]


TEXT_FLAGS = {"-m", "--message", "--body", "--subject", "--title", "--description", "--summary", "--question", "--option",
              "--reason", "--note", "--text"}      # what follows them is words (a commit message, a NAVI message), not a path


def path_words(toks: list[str], here: Path) -> list[str]:
    """The words of a command that may name a file it reads. Not the text after -m / --body and the like, not NAVI's own
    messages (`navi send`, `navi ask`, `navi status`: words for the council, checked by NAVI's outgoing filter), and
    not quoted words with spaces that are no file here."""
    prog = Path(toks[0]).name.lower() if toks else ""
    if prog in ("python", "python3") and len(toks) > 1 and Path(toks[1]).name == "navi.py":
        toks, prog = toks[1:], "navi"
    if prog in ("navi", "navi.py"):
        sub = next((t for t in toks[1:] if not t.startswith("-")), "")
        if sub != "artifact":                   # `navi artifact <agent> <file>` names a file; the rest are words
            return [t.split("=", 1)[1] if "=" in t else t for t in toks[1:] if t.startswith("--") and t.split("=", 1)[0].endswith("-file")]
    out, skip = [], False
    for tok in toks[1:]:
        if skip:
            skip = False
            continue
        if tok in TEXT_FLAGS:
            skip = True
            continue
        if "=" in tok and tok.split("=", 1)[0] in TEXT_FLAGS:
            continue
        if any(ch.isspace() for ch in tok):
            try:
                if not resolve(tok.strip("'\""), here).exists():
                    continue
            except (OSError, ValueError, RuntimeError):
                continue
        out.append(tok)
    return out


def shell_writes(cmd: str, cwd: Path) -> list[Path]:
    """The files a shell command writes (redirects, tee, cp/mv/install targets, touch), resolved, following its `cd`s."""
    out, here = [], cwd
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        if toks and toks[0] == "cd":
            here = resolve(os.path.expandvars(toks[1]) if len(toks) > 1 and toks[1] != "-" else "~", here)
            continue
        out += [resolve(os.path.expandvars(t), here) for t in write_targets(shell_words(seg))]
    return out


RUNNERS = {"sh", "bash", "zsh", "python", "python3", "node", "deno", "bun", "ruby", "perl", "pwsh", "open", "cat", "less",
           "head", "tail", "wc", "chmod", "terraform", "tflint", "shellcheck", "npx", "bats"}


def runs_made(cmd: str, cwd: Path, made) -> bool:
    """True when every part of a shell command works on files the council made this session: runs one (`./deploy.sh`,
    `bash out/check.sh`, `python3 gen.py`) or `cd`s. Then it needs no card: it's the council's own work."""
    made, here, hit = set(made or ()), cwd, False
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            return False
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
            toks.pop(0)
        if not toks:
            continue
        if toks[0] == "cd":
            here = resolve(os.path.expandvars(toks[1]) if len(toks) > 1 and toks[1] != "-" else "~", here)
            continue
        prog = toks[0]
        if str(resolve(prog, here)) in made and "/" in prog:
            hit = True
            continue
        args = [t for t in toks[1:] if not t.startswith("-")]
        if Path(prog).name in RUNNERS and args and str(resolve(args[0], here)) in made:
            hit = True
            continue
        return False
    return hit


# ---------------------------------------------------------------- Auto, when the engine has no judge of its own
# You chose Auto and went to eat. Claude Code's auto mode decides with a model; where it can't (the account or the model
# doesn't have it: Claude Code then quietly asks about everything), NAVI decides here, at once, in plain code: the work
# runs, and what changes the world outside the project is refused (the council is told why and finds another way).
# WARDEN's hard denies are checked before any of this, as always.
MUTATE = {
    "az": {"create", "delete", "update", "set", "add", "remove", "assign", "start", "stop", "restart", "deploy", "import",
           "purge", "reset", "rotate", "grant", "revoke", "upload", "move", "swap", "scale", "invoke", "apply", "approve",
           "attach", "detach", "enable", "disable", "renew", "regenerate", "rollback", "run-command", "lock", "unlock"},
    "gcloud": {"create", "delete", "update", "deploy", "set", "add-iam-policy-binding", "remove-iam-policy-binding", "start",
               "stop", "reset", "resize", "import", "patch", "apply", "rollback"},
    "gsutil": {"cp", "mv", "rm", "rb", "mb", "rsync", "setmeta", "acl", "iam"},
    "gh": {"merge", "create", "delete", "close", "edit", "comment", "review", "archive", "transfer", "rename", "upload",
           "reopen", "lock", "set", "remove", "sync", "deploy"},
    "docker": {"push", "login", "rm", "rmi", "prune"}, "podman": {"push", "login", "rm", "rmi", "prune"},
    "npm": {"publish", "unpublish", "deprecate", "owner", "token", "adduser", "login"}, "pnpm": {"publish"},
    "yarn": {"publish", "npm"}, "cargo": {"publish", "yank", "owner"}, "twine": {"upload"}, "gem": {"push", "yank"},
    "kubectl": {"apply", "create", "delete", "patch", "replace", "scale", "rollout", "edit", "drain", "cordon", "label",
                "annotate", "set", "expose", "run", "taint", "uncordon", "exec", "cp"},
    "helm": {"install", "upgrade", "uninstall", "delete", "rollback", "push"},
    "terraform": {"apply", "destroy", "import", "taint", "untaint", "force-unlock", "rm", "mv", "push", "replace-provider"},
    "tofu": {"apply", "destroy", "import", "taint", "untaint", "force-unlock", "rm", "mv", "push"},
    "terragrunt": {"apply", "destroy", "run-all", "import"}, "pulumi": {"up", "destroy", "import", "refresh"},
    "vercel": {"deploy", "--prod", "rm", "remove"}, "netlify": {"deploy"}, "flyctl": {"deploy", "destroy"}, "fly": {"deploy", "destroy"},
    "firebase": {"deploy"}, "heroku": {"create", "destroy", "deploy", "config:set"},
}
AWS_MUTATE = re.compile(r"^(create|delete|put|update|modify|terminate|run|start|stop|attach|detach|associate|disassociate|remove|add|set|"
                        r"reboot|restore|import|register|deregister|revoke|authorize|invoke|publish|send|tag|untag|deploy|enable|disable)\b")
REBUILT = {"node_modules", "dist", "build", "out", ".next", ".nuxt", "coverage", "target", ".venv", "venv", "__pycache__",
           ".pytest_cache", ".mypy_cache", ".ruff_cache", ".terraform", ".turbo", ".parcel-cache", "tmp", ".cache"}   # made again by a build
NEVER = {"sudo": "runs as another user", "su": "runs as another user", "doas": "runs as another user", "shutdown": "stops the machine",
         "reboot": "restarts the machine", "mkfs": "formats a disk", "diskutil": "changes disks", "launchctl": "changes system services",
         "systemctl": "changes system services", "crontab": "changes scheduled jobs", "ssh": "works on another machine",
         "scp": "copies to another machine", "sftp": "copies to another machine", "nc": "opens network connections",
         "ncat": "opens network connections", "telnet": "opens network connections"}


def auto_judge(pol: dict, navi: Path, tool: str, ti: dict, cwd: Path) -> tuple[bool, str]:
    """-> (runs, why not). Everything the work needs runs; pushes, deploys, cloud and cluster changes, uploads, folder
    deletes, other users and writes outside the project don't."""
    root, made = project_root(navi), set(pol.get("made") or ())
    inside = lambda p: _under(p, root) or str(p) in made or any(_under(p, Path(f).expanduser().resolve()) for f in pol.get("sources") or []) \
        or any(_under(p, s) for s in SCRATCH)
    if tool.startswith("mcp__"):
        verb = tool.split("__")[-1].lower()
        bad = next((w for w in ("create", "delete", "update", "send", "post", "publish", "merge", "remove", "write", "push", "deploy",
                                "transition", "assign", "comment") if w in verb), "")
        return (False, f"{tool} changes something outside ({bad})") if bad else (True, "")
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        f = ti.get("file_path") or ti.get("notebook_path")
        if f and not inside(resolve(str(f), cwd)):
            return False, f"writes outside the project ({f}): write inside {root}, or ask the user with `navi ask`"
        return True, ""
    if tool != "Bash" or not isinstance(ti.get("command"), str):
        return True, ""
    cmd = ti["command"]
    if re.search(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|python3?|node|perl|ruby)\b", cmd):
        return False, "runs a script straight from the internet"
    for t in shell_writes(cmd, cwd):
        if not inside(t) and str(t) != "/dev/null":
            return False, f"writes outside the project ({t})"
    here = cwd
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in ("command", "exec", "time", "nohup", "env")):
            toks.pop(0)
        if not toks:
            continue
        prog, low = Path(toks[0]).name.lower(), [t.lower() for t in toks]
        words = [t for t in low[1:] if not t.startswith("-")]
        if prog == "cd":
            here = resolve(os.path.expandvars(toks[1]) if len(toks) > 1 and toks[1] != "-" else "~", here)
            continue
        if prog in NEVER:
            return False, f"`{prog}` {NEVER[prog]}"
        if prog == "git" and words[:1] == ["push"]:
            return False, "`git push` sends work to a remote: leave that to the user"
        if prog == "git" and (" ".join(low[1:3]) == "reset --hard" or (words[:1] == ["clean"] and any("f" in t for t in low if t.startswith("-")))
                              or (words[:1] in (["branch"], ["tag"]) and any(t in ("-d", "-D", "--delete") for t in toks))
                              or words[:1] in (["filter-branch"], ["filter-repo"])):
            return False, "throws work away in git"
        if prog == "rm":
            targets = [resolve(t, here) for t in toks[1:] if not t.startswith("-")]
            recursive = any(t.startswith("-") and ("r" in t.lower()) for t in toks[1:]) or "--recursive" in low
            if any(not inside(t) for t in targets):
                return False, "deletes files outside the project"
            if recursive and any(str(t) not in made and not _under(t, navi) and t.name not in REBUILT for t in targets):
                return False, "deletes folders the council didn't make"
        if prog in ("chmod", "chown") and any(t.startswith("-") and "R" in t for t in toks[1:]):
            return False, f"`{prog} -R` changes permissions on whole folders"
        if Path(prog).name in UPLOADERS and any(UPLOAD_FLAGS.match(t) for t in toks[1:]):
            return False, f"{prog} with an upload flag sends data out"
        if prog == "aws" and len(words) >= 2 and (AWS_MUTATE.match(words[1]) or (words[0] == "s3" and words[1] in ("cp", "mv", "rm", "sync", "rb", "mb"))):
            return False, f"`aws {words[0]} {words[1]}` changes AWS"
        if prog == "gh" and words[:1] == ["api"] and any(t.upper() in ("POST", "PUT", "PATCH", "DELETE") for t in toks):
            return False, "`gh api` with a write method changes GitHub"
        hit = next((w for w in words if w in MUTATE.get(prog, ())), "")
        if hit:
            return False, f"`{prog} … {hit}` changes something outside the project (infrastructure, a cluster, a registry, GitHub)"
    return True, ""


def decide_exec(pol: dict, navi: Path, cmd: str, cwd: Path):
    worst = (ALLOW, "no sensitive command or path")
    here = cwd                  # follows `cd` through the command: `cd ~ && echo x > f` writes ~/f, not ./f
    for seg in split_commands(cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in ("sudo", "command", "exec", "time", "nohup")):
            toks.pop(0)
        if not toks:
            continue
        low = [t.lower() for t in toks]
        found = None
        if low[0] == "cd":
            here = resolve(os.path.expandvars(toks[1]) if len(toks) > 1 and toks[1] != "-" else "~", here)
            continue
        for t in write_targets(shell_words(seg)):     # a write outside the project asks, as the file tools' writes do
            t = os.path.expandvars(t)
            if any(_under(resolve(t, here), s) for s in SCRATCH):
                continue
            dec, why = decide_path(pol, navi, "write", t, here)
            if dec != ALLOW and (not found or SEVERITY[dec] > SEVERITY[found[0]]):
                found = (dec, f"writes '{t}': {why}")
        for spec in pol["deny_commands"]:
            if _cmd_match(low, spec):
                found = (DENY, f"command '{spec.rstrip('$')}' exposes secrets")
                break
        if not found:
            for spec in pol["ask_commands"]:
                if _cmd_match(low, spec):
                    found = (ASK, f"command '{spec}' can touch live data")
                    break
        if not found and Path(low[0]).name in UPLOADERS and any(UPLOAD_FLAGS.match(t) for t in toks[1:]):
            found = (ASK, f"{low[0]} with an upload flag - possible data exfiltration")
        if not found:
            for tok in path_words(toks, here):
                t = re.sub(r"^\d*[<>]+&?", "", tok)
                if t.startswith("-") and "=" in t:
                    t = t.split("=", 1)[1]
                t = t.strip("()'\"$`").lstrip("@")
                if not t or t.startswith("-") or "://" in t:
                    continue
                dec, why = decide_path(pol, navi, "read", t, here, scoped=False)
                if dec != ALLOW:
                    found = (dec, f"touches '{t}': {why}")
                    if dec == DENY:
                        break
        if found and SEVERITY[found[0]] > SEVERITY[worst[0]]:
            worst = found
    return worst


ASKED = re.compile(r"matches sensitive pattern '([^']+)'")


def asked_pattern(why: str) -> str:
    """The sensitive pattern an 'ask' was about ('*.tfvars'), so you can let it through for the rest of a session."""
    m = ASKED.search(str(why or ""))
    return m.group(1) if m else ""


def decide(pol: dict, navi: Path, action: str, target: str, cwd: Path):
    """-> (decision, reason). Hard denies always win; WARDEN/user rulings can only settle 'ask'."""
    if action in ("read", "write"):
        dec, why = decide_path(pol, navi, action, target, cwd)
    elif action == "exec":
        dec, why = decide_exec(pol, navi, target, cwd)
    elif action == "fetch":
        dec, why = (ASK, "network fetch in a confidential session") if pol["sensitivity"] == "confidential" \
            else (ALLOW, "fetch allowed")
    else:
        return ASK, f"unknown action '{action}'"
    if dec == ASK:
        k = key_for(action, target, cwd)
        for r in load_rulings(navi):
            if r["action"] == action and r["key"] == k:
                return r["decision"], f"ruled by {r['by']}: {r.get('reason', '')}".rstrip(": ")
    return dec, why


# ---------------------------------------------------------------- outbound scanner

_NOT_A_VALUE = r"(?!var\.|local\.|data\.|module\.|\$\{|\{\{|<|\*{3})"
SECRET_RULES = [
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", 0),
    ("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 0),
    ("azure-account-key", r"AccountKey=[A-Za-z0-9+/=]{20,}", 0),
    ("azure-shared-key", r"SharedAccessKey=[A-Za-z0-9+/=]{20,}", 0),
    ("sas-signature", r"\bsig=[A-Za-z0-9%+/=]{20,}", 0),
    ("github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})", 0),
    ("slack-token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}", 0),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}", 0),
    ("llm-api-key", r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}", 0),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", 0),
    ("bearer-token", r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*", 0),
    ("conn-password", r"(?i)\b(?:password|pwd)=" + _NOT_A_VALUE + r"([^;\s'\"]{4,})", 1),
    ("assigned-secret", r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?key|client[_-]?secret|token)\b[\"']?\s*[:=]\s*[\"']?"
     + _NOT_A_VALUE + r"([^\s\"',;]{8,})", 1),
]
PII_RULES = [
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", 0),
    ("iban", r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b", 0),
    ("personal-id-se", r"\b(?:19|20)?\d{6}[-+]\d{4}\b", 0),
]
_COMPILED = [(n, re.compile(rx), g) for n, rx, g in SECRET_RULES]
_COMPILED_PII = [(n, re.compile(rx), g) for n, rx, g in PII_RULES]


def redact(text: str, pol: dict | None = None) -> tuple[str, list[str]]:
    """-> (redacted text, names of rules that fired). PII rules only apply in confidential sessions."""
    if not text:
        return text, []
    rules = _COMPILED + (_COMPILED_PII if pol and pol.get("sensitivity") == "confidential" else [])
    hits: list[str] = []
    for name, rx, grp in rules:
        def sub(m, name=name, grp=grp):
            hits.append(name)
            tag = f"[REDACTED:{name}]"
            if not grp:
                return tag
            s, e = m.start(grp) - m.start(0), m.end(grp) - m.start(0)
            return m.group(0)[:s] + tag + m.group(0)[e:]
        text = rx.sub(sub, text)
    return text, hits
