# NEWPCSESSION: everything about NAVI, so you can resume on a new computer

> Written 2026-10-06 at the end of the first build session. It lives in the repo, so it moves with the code.
> It covers what NAVI is, every decision made and why, how it's built, what's tested, what isn't, and what's next.

---

## 0. How to resume on the new PC

1. `git clone https://github.com/OwariX/navi` (private; log in as **OwariX** with `gh auth login`). Then, in the clone,
   `git config user.name OwariX && git config user.email 338736666+OwariX@users.noreply.github.com`: every commit is
   made as OwariX, nothing else. Optionally copy `~/.config/navi/`
   (look, default council, recent folders); without it you just get the first-run setup again.
2. You need **Python 3.10+** and the **Claude Code CLI**. Nothing else (zero dependencies).
3. Run `cd navi && ./install.sh`. It:
   - writes `~/.local/bin/navi` (the `navi` command, with this folder's absolute path baked in),
   - symlinks `~/.claude/skills/navi` and `~/.codex/skills/navi` to this folder,
   - tells you if `~/.local/bin` isn't on your PATH.
4. Test: `cd` into any project, run `navi`, pick **START** (opens the web main menu) or **DEMO**.
5. To continue building NAVI with Claude, open Claude Code **inside the navi folder** and paste:

```
Read NEWPCSESSION.md in this folder. It's the full handoff of how we built NAVI (a multi-agent council skill
with a Lain-style web interface). Get familiar with the architecture (scripts/navi.py, scripts/guard.py,
scripts/forge.py, web/index.html, SKILL.md), then tell me what you'd do next from the "Open items" and
"Roadmap" sections. Don't change anything yet.
```

---

## 1. What NAVI is (the vision)

**Goal:** an agent skill that works with Claude Code, Codex and others, and could reach the top of GitHub stars.
Inspired by an article about OpenAI agents with names and inboxes working together.

**NAVI** (named after the computer in *Serial Experiments Lain*) is:

- a **council of named agents** (architect, adversary, ledger, warden, scribe, ...) who **propose, challenge, revise,
  give verdicts, build and record**, communicating only through **file-based inboxes** and an **append-only event log**;
- a **live web interface** ("the Wired") in a CRT / Lain aesthetic: grain, scanlines, glow, power lines, glitch text,
  nodes, and packets travelling between agents. **The browser is the user's terminal**: you answer agents there,
  talk to them, attach files, manage agents and councils, and sign off on work;
- a **portable protocol**: plain files plus one Python CLI, so any agent host that can run shell commands can take part;
- **WARDEN**, a data guard: three layers so secrets and personal data never enter agent context;
- **councils**: templates (lead / reviewers / recorder / guard plus a model per member), e.g. a Terraform review council
  (PR description from the repo's template, no cost review).

Primary use: software development, architecture, cloud / IaC (Terraform among others).

---

## 2. Timeline: what you asked for and what was built (in order)

1. **Brainstorm.** Concept: "NAVI / the wired", a portable council skill with a live visualizer. Pitch: the visual demo GIF
   sells it; useful outputs (ADR, threat model, IaC skeleton) keep people around.
2. **MVP scaffold** (`navi/`): `SKILL.md`, `AGENTS.md`, `scripts/navi.py` (protocol CLI + SSE server), `web/index.html`
   (canvas visualizer: boot sequence "PRESENT DAY. PRESENT TIME.", hub, nodes, packets, feed, artifacts, consensus overlay,
   synthesized sound), `agents/*.md`, and a demo session (an Azure event pipeline debate).
3. **Discussion: a continuous docs agent?** Verdict: don't run an agent that rewrites docs on every message (token cost,
   documents things that later get reversed, overlaps SCRIBE). Better: a free transcript from the log
   (`navi log --md` idea), and SCRIBE writing at checkpoints. *Not built: the `--md` export is still an idea.*
4. **Security expert / data safety.** The key insight: once an agent has *read* something, it has already leaked, so the
   check must happen before reading, based on metadata only. That led to **WARDEN, three layers** (all built, see §6).
5. **First live test:** a Flappy Bird clone run through the council. It worked. Lesson: I wrote LEDGER's "over 15 KB"
   message before measuring (the file was 11 KB), so **measure before claiming**. That's now part of the personas.
6. **Big interface upgrade:**
   - a first-run setup wizard (palettes, grain, scanlines, edge darkness, glow, sound), saved per user;
   - agents can **ask the user** in the interface (beacon + toast + answer modal), and the answer goes back to the
     blocking CLI;
   - node **statuses** with spinners and timers, so long work doesn't look frozen;
   - a **console** for talking to the council;
   - "done?" sign-off, then CONSENSUS with new task or close;
   - **the interface is the terminal**: Claude is only used to start it.
   - The setup gate was tested live: you went through the wizard and chose "public"; for the style question you said
     "u decide", so the Wired style was picked.
7. **Sessions + launcher + agents:**
   - saved sessions with history, view / replay / resume;
   - reloading restores the session instantly (no replay of every animation);
   - a `navi` terminal command plus `install.sh`;
   - add / edit / remove agents in the UI;
   - click any node for an info card (what it does, status, stats);
   - an **ASCII boot animation** with a custom NAVI logo in the terminal, and the same logo decoding on the web boot screen.
8. **Terminal main menu:** `navi` shows the intro, then an arrow-key menu.
9. **Round 3 (the big one):**
   - **START** (top of the terminal menu) opens a **web main menu**; the terminal waits and launches whatever you pick;
   - **model choice** before starting, per-agent models, and **mid-session model changes** (the moderator restarts with
     `claude --continue --model X`);
   - agent **on/off switches**, headless **generation** that follows a written **standard**, an **evaluator**
     (instant lint score + optional AI deep review);
   - **council templates** (incl. a Terraform/work council) and a **council builder** ("describe what you want → it
     suggests seats, generates missing agents, saves");
   - **every session picks a council**; the default council is **THE KNIGHTS** (after the Knights of the Eastern
     Calculus); you can change your default; **built-in agents and councils are read-only** (duplicate them to edit);
   - full **mouse navigation**;
   - **AUTO**: NAVI recruits and releases agents (or writes new ones) whenever the work needs it;
   - **attachments**: paste, drop or 📎 files, images and PDFs, shown as `[Image #1]` like in the terminal;
   - **`@agent` autocomplete**;
   - **URL routing**: `/` is always the main menu, `/s/<session-id>` is one session, and **several sessions can be live
     at once** (one terminal moderator each).
10. **Codex:** its flags are unverified (Codex wasn't installed on the build machine). NAVI hides hosts that aren't
    installed.

---

## 3. Repo map

```
navi/
├── SKILL.md              # the skill: moderator instructions (Claude Code / Codex skill format)
├── AGENTS.md             # entry point for AGENTS.md hosts (Codex, Gemini CLI, Cursor) -> points to SKILL.md
├── README.md             # GitHub-facing docs
├── NEWPCSESSION.md       # this file
├── install.sh            # puts `navi` on PATH, links the skill into ~/.claude/skills and ~/.codex/skills
├── .gitignore            # .navi/, __pycache__/, .DS_Store
├── scripts/
│   ├── navi.py           # ~2600 lines: protocol CLI, launcher, terminal menu + intro, sessions, councils, HTTP/SSE server
│   ├── guard.py          # ~270 lines: WARDEN core (policy, gate decisions from metadata, outbound secret/PII scanner)
│   └── forge.py          # ~270 lines: persona library paths, STANDARD evaluator (lint), headless `claude -p` generator / reviewer / council suggester
├── web/index.html        # ~2100 lines: the entire interface (canvas, CSS, JS, no dependencies, no network)
├── agents/               # bundled personas (READ-ONLY in the UI)
│   ├── STANDARD.md       # the persona standard (generator follows it, evaluator scores against it)
│   └── architect.md  adversary.md  ledger.md  scribe.md  warden.md   # The Knights (session 2 removed the rest)
├── councils/             # bundled council templates (READ-ONLY)
│   └── knights.json      # THE KNIGHTS (default, the only built-in since session 2; users create their own)
└── demo/hello/index.html # the page the demo council "builds" (served at /demo/hello); the demo script itself is in web/index.html
```

**Per project** (created in whatever repo you run `navi` in):

```
<project>/.navi/
├── current               # id of the "current" session (for CLI calls without a bound host)
├── policy.json           # WARDEN perimeter (per project)
├── rulings.json          # WARDEN/user rulings on grey-area access (per project)
├── server.json           # {pid, port} of this project's interface server
├── launcher.json         # present while a terminal is waiting after START
├── launch.json           # the web menu's choice, picked up by the waiting terminal
├── hosts/<hid>.json      # live launcher-managed moderators {pid, host, model, session, ...}
├── hosts/<hid>.relaunch.json   # pending model switch for that moderator
├── agents/*.md           # project personas
├── uploads/              # files pasted or dropped in the interface
├── drafts/               # generated persona drafts
├── serve.log
└── sessions/<YYYYmmdd-HHMMSS>/
    ├── log.jsonl         # append-only event stream (the source of truth; the UI tails it)
    ├── session.json      # {id, task, started, ended, summary}
    ├── council.json      # the seated council
    ├── inbox/<agent>/NNNN-<from>.md (+ read/)   # messages with frontmatter; inbox/navi = moderator inbox (user input)
    ├── replies/<ask-id>.json
    └── out/              # deliverables (`navi out` prints the path)
```

**Per user** (`~/.config/navi/`): `config.json` (look + last host/model/council + default council),
`agents/` (your persona **library**, shared across projects), `councils/` (**your** councils).
Env overrides: `NAVI_CONFIG`, `NAVI_LIBRARY`, `NAVI_COUNCILS`, `NAVI_DIR`, `NAVI_SESSION`, `NAVI_HOST_ID`, `NAVI_NO_INTRO`.

Old layouts (a single session in `.navi/`, plus `.navi/archive/`) are **migrated automatically** into `sessions/`.

---

## 4. How it runs (processes)

```
terminal: `navi` ─► intro + main menu
   ├─ START ─► starts the project server (if needed), opens http://127.0.0.1:<port>/  (web main menu)
   │           writes .navi/launcher.json and WAITS for .navi/launch.json
   │           web menu "START SESSION" ─► POST /launch ─► launch.json ─► terminal picks it up
   ├─ NEW / CONTINUE / RESUME directly in the terminal (pick a council, task, host, model)
   └─ perform_launch ─► open_session (new session dir, council seated) ─► run_host:
        runs `claude [--continue] [--model X] "/navi <notes>"` as a CHILD process with env NAVI_HOST_ID=<hid>
        and writes .navi/hosts/<hid>.json {pid, session, model}
        when the child exits and hosts/<hid>.relaunch.json exists ─► restart with --continue --model <new>
server (one per project, detached): `navi.py serve --port N` (NAVI_DIR=.navi)
   GET /  and /s/<id> ─► index.html (token injected)   GET /events?session=<id> ─► SSE tail of that session's log
moderator (Claude Code running SKILL.md) calls `navi ...` CLI ─► thanks to NAVI_HOST_ID every call targets ITS session
```

**Session resolution order (CLI):** `NAVI_SESSION` env > the host's bound session (`NAVI_HOST_ID` → `hosts/<hid>.json`)
> `.navi/current`. When a moderator runs `navi init --reset` (a new task), its host file moves to the new session and a
`next` event is written into the old one, so the browser tab follows.

**Server request binding:** each POST binds to the explicit `session` in its body (thread-local context). Without a
session, writes are dropped instead of leaking into another session. GET `/status` without a session falls back to current.

---

## 5. Protocol (what agents and the moderator use)

| Command | Purpose |
|---|---|
| `navi init --task T [--council C] [--sensitivity S] [--scope ..] [--deny ..] [--reset]` | new session (seats the council) |
| `navi join <agent> [--model m] [--role r] [--color #hex]` / `navi leave <agent>` | council membership |
| `navi send --from A --to B\|all --kind K --subject S --body ...` | message (kinds: proposal, challenge, revision, ack, reject, verdict, request, note) |
| `navi inbox <agent>` / `navi think <agent> "..."` / `navi status <agent> "..." --state working\|waiting\|blocked\|done\|idle` | read mail / think aloud / show status |
| `navi ask --from A --question Q --option X ...` (blocks) / `navi wait <id>` | ask the human in the UI; prints `choice:` / `text:` |
| `navi listen [--timeout 0]` | user input from the UI (console, roster changes, model switches, new task, exit...) |
| `navi out` / `navi artifact <agent> <file> --title T` | deliverables folder / register a deliverable (bare names resolve in `out/`) |
| `navi log [--full]` / `navi end --summary ...` | transcript / close the session |
| `navi councils` / `navi council [use <name> [--keep]]` | list / show / seat a council |
| `navi agents [--json]` / `navi persona <name> ... [--scope project\|library] [--join]` / `navi lint-persona <file>` | personas |
| `navi model <agent\|navi> <model>` / `navi relaunch [--model M]` | per-agent model / restart the moderator on another model |
| `navi sessions` / `navi resume [id]` / `navi up` / `navi down` / `navi setup [--wait\|--reset]` | sessions, server, interface |
| `navi gate ...` / `navi rule ...` / `navi scan` / `navi policy` / `navi hook` / `navi guard-config --write` | WARDEN |

**Exit codes:** gate 0 = allow, 3 = ask, 2 = deny. Waiting commands exit **4** on timeout (just run them again).
Blocking waits default to 540 s, so they fit the Bash tool's 10-minute limit.

**User → moderator intents** (in `inbox/navi`, read with `listen`): `message`, `feedback`, `new-task`, `exit`, `resume`,
`roster`, `agent-generate`, `model`, `council`. Messages may carry **attachments** (paths in `.navi/uploads/`).

**Event types in log.jsonl:** boot, policy, council, join, leave, model, host, think, status, message, ask, reply,
artifact, gate, ruling, redact, upload, roster, resume, next, end. The SSE stream adds `reset` + `sync` (history before
`sync` is rebuilt instantly, without animation).

**Rounds (by seat; the council's instructions win where they differ):** propose (lead) → challenge (reviewers) →
revise (lead) → verdict (reviewers; at most 3 revision rounds, then unresolved points become accepted risks) →
build (lead runs the real checks, reviewers re-check) → record (recorder writes deliverables, the guard scans them) →
**ask the human "done?"** → `end` → `listen` loop (new task / feedback / exit).

---

## 6. WARDEN (data safety): three layers + an outgoing filter

1. **Perimeter:** sensitivity (public / internal / confidential), read scope, extra deny patterns → `.navi/policy.json`.
   Asked once (in the UI, or chosen in the web menu).
2. **Gate:** `navi gate` decides from **metadata only** (path, name, command line), never by reading the file.
   - **Hard deny** (28 patterns): `.env*` (except `.env.example` etc.), keys, `*.tfstate`, `~/.ssh`, kubeconfig, `secrets/`,
     cloud CLI config dirs, and commands like bare `env`, `printenv`, `terraform state pull`, `terraform show`,
     `kubectl get secret(s)`, `az keyvault secret show`, `gh auth token`...
   - **Ask** (19 patterns): `*.tfvars`, `*.csv`, `*.sql`, `prod/*`, `data/*`... plus `psql`, `terraform output`, and
     `curl`/`wget` with upload flags.
   - **Ask** results go to WARDEN, which rules allow / deny (with a safer alternative) / escalate to the user. Rulings
     can't override hard denies. In confidential mode WARDEN can't allow on its own.
3. **Hard guard (Claude Code only):** a `PreToolUse` hook (`navi hook`) enforces the same policy on
   Read / Write / Edit / Bash / Grep / WebFetch, plus `permissions.deny` rules. Installed with `navi guard-config --write`
   into the project's `.claude/settings.local.json`. Not installed by default.
- **Outgoing filter:** every send / think / status / ask / artifact / end and every user reply or console message is
  scanned for AWS / Azure / GitHub / Slack / Google / LLM keys, JWTs, bearer tokens, private keys and assigned
  passwords, plus email / IBAN / Swedish personal numbers in confidential mode. Hits are redacted (or blocked with
  `outbound: block`). Uploaded text files are scanned too.
- **Honest limits:** enforcement only exists on hosts with pre-tool hooks (Claude Code). Pattern matching is best-effort,
  so keep secret scanning in CI as well.

**Server security:** binds 127.0.0.1 only; a per-run token is embedded in the page and required as the `X-Navi-Token`
header on every POST; Host and Origin checks block DNS rebinding and cross-site requests. Uploads and artifacts have
path-traversal checks, and HTML/SVG uploads are served as text/plain.

---

## 7. Councils, agents, models

**Council template schema** (`councils/*.json`, yours in `~/.config/navi/councils/`):
`name, title, description, lead, reviewers[], recorder, guard, extra[], models{agent: opus|sonnet|haiku|fable},
sensitivity, instructions, outputs[], mode ("auto" or "")`.

| Council | Lead | Reviewers | Recorder | Notes |
|---|---|---|---|---|
| **knights** ★ default | architect | adversary, ledger | scribe | THE KNIGHTS, the original council |

Session 2 removed the other built-ins (app-dev, terraform, security-review, auto) on purpose: users create their own,
and you'll add examples later. AUTO mode (`"mode": "auto"` in a council file) still works in the code and SKILL.md,
but no bundled council uses it and the council editor has no toggle for it yet. The iac-engineer / iac-reviewer /
pr-scribe / ux personas are still bundled.

Councils have the guard `warden`. Bundled councils and agents are **read-only**; DUPLICATE them to customize.
You can set your own default council with ★ SET AS DEFAULT (stored as `default_council` in config.json).

**Persona standard** (`agents/STANDARD.md`): frontmatter (name, description, role, color, model) + an identity line
`You are **NAME**, the council's <role>.` + mission and boundary + 5-9 testable bullets covering inbox, message kinds,
evidence/gate, status, when to ask the human, verdict or deliverable, and at least one "never"; concrete wording; ~600-3000 characters; safe.
**Evaluator** (`forge.lint`): weighted checks → score / grade A-F, with fixes; the UI shows "+ add" buttons that insert
them. All bundled personas score 95-100 (A). **Deep review**: `claude -p` against a rubric returns JSON
(score, verdict, strengths, issues, improved_directive).

**Generation** (UI "✦ GENERATE", or a council builder that creates missing agents): headless
`claude -p --tools "" --no-session-persistence --output-format text --model sonnet`, a prompt with STANDARD.md + 3 bundled
examples + the current council. Verified for real: haiku produced a k8s reviewer scoring 95/A in about 25 s. If the
`claude` CLI is missing, it falls back to asking the moderator (`agent-generate` intent).
**Council builder** ("✦ CREATE A COUNCIL"): `claude -p` returns a JSON design (seats, models, instructions, outputs,
new_agents with briefs, why). Verified: for "Azure terraform PRs, cost doesn't matter" it reused
iac-engineer / iac-reviewer / adversary / pr-scribe and dropped ledger. There's an offline keyword fallback.

**Models:**
- Moderator: `MODERATOR_MODELS = {"claude": ["", "opus", "sonnet", "haiku", "fable"], "codex": [""]}` (`""` = the
  host's default). Verified: `claude --model` accepts the aliases `fable`, `opus` and `sonnet` or a full name, and
  `-c/--continue` continues the latest conversation in the folder.
- Agents: `"" (inherit) | opus | sonnet | haiku | fable`. These are hints the moderator passes when it spawns subagents
  (the Agent tool's `model` param). If the host can't choose subagent models, the moderator plays the persona itself.
- Switching mid-session: agents switch on their next turn. The moderator switches via relaunch "at next checkpoint"
  (the moderator runs `navi relaunch`) or "now" (the server kills it, and the launcher restarts it with `--continue --model X`).
  This only works when NAVI's launcher started the moderator; otherwise use `/model` in Claude Code.

---

## 8. The interface (web/index.html)

- **Routes:** `/` = main menu (always). `/s/<id>` = a session (its own SSE stream). `/s/<id>?replay=1` = animated replay.
  Deep links: `#settings #agents #sessions #councils #menu`.
- **Main menu:** logo decode, launcher/moderator status line, NEW SESSION (task + 📎 attachments, council cards (★ DEFAULT,
  ◇ for auto-mode councils, plus a ✦ CREATE YOUR OWN card that opens the builder), host, moderator model, data sensitivity), and tiles: CONTINUE, SESSIONS (live count), AGENTS,
  COUNCILS, SETTINGS, THE WIRED.
- **Session page:** the canvas graph (hub NAVI, agent nodes with role · model, status line + timer, spinner while
  working, ◆ NEEDS YOU beacon, lock flashes for gate decisions, WARDEN perimeter hexagon), the feed, the artifacts
  panel, a console (📎, paste/drop, `@` autocomplete), the bottom bar (moderator host/model, activity, waiting count,
  clickable shortcuts), a "NO MODERATOR ON THIS SESSION → CONTINUE IN TERMINAL" bar, and the CONSENSUS overlay
  (new task / close / stay).
- **Panels:** ◷ SESSIONS (open / replay / continue; LIVE / OPEN / ENDED badges), ◉ AGENTS (switches, model, scope
  project/library, live standard score, generate, deep review, template, duplicate), ⬡ COUNCILS (list, read-only
  built-ins, duplicate, editor with seats / chips / models / instructions / outputs, ✦ builder, USE NOW, USE FOR NEXT
  SESSION, ★ SET AS DEFAULT), ⚙ SETTINGS (the same wizard).
- **Node card** (click any node): description, status + timer, sent/received counts, last signal; for agents, a model
  select + DIRECTIVE / REMOVE; for NAVI, the moderator host/model + switch AT NEXT CHECKPOINT / NOW; for YOU, open console.
- **Keys:** `/` console · `h` menu · `s` sessions · `a` agents · `c` councils · `,` settings · `m` sound · `f` fullscreen · `esc` close.
  Everything is also clickable, and clicking the dark backdrop closes a panel.
- **Settings** (config.json): preset (wired / phosphor / amber / vapor / ice / dusk), accent, accent2, grain, scanlines,
  vignette ("edge darkness", default 55; you chose 0), glow, flicker, sound, setup_complete, last_host / last_model /
  last_council, default_council.
- **Reloads** restore instantly (history before `sync` renders without animation), and the boot only plays once per tab.

**Terminal:** `intro()` decodes the NAVI block logo out of static, adds a horizontal tear, draws the
`──◉────◎────◉──` wire, types "T H E   W I R E D", the boot log, PRESENT DAY / PRESENT TIME, then the menu.
Menu keys: ↑↓ / j k, ⏎, q, Tab = host, m = moderator model. NEW SESSION asks for the task, then shows a council picker.

---

## 9. What's tested and what isn't

**Tested here (CLI / HTTP / process level):**
- protocol end to end; WARDEN gate on 9 file cases and 10 commands; rulings; redaction / block; hook JSON; guard-config idempotence;
- SSE tail + sync; token / Host / Origin checks (403s); path traversal (403);
- ask → reply round trip; console → listen; setup --wait; sessions and migration of the old layout;
- **two live sessions at once** with separate fake moderators; session-scoped messages;
- a moderator `init --reset` moving to a new session + the `next` event;
- the START hand-off; **moderator relaunch with `--continue --model sonnet`** (fake claude);
- councils (seat / switch / exclusive / read-only); agent toggle / model; lint;
- **real** `claude -p` generation and council suggestion; uploads + attachments + WARDEN on uploads; menu-page writes not leaking;
- the terminal menu in a real pseudo-terminal; JavaScript syntax (`node --check`) after every change.

**Not verified (no browser available on this machine):** the visual result of the newest web pieces: the web main
menu, councils panel, agents switches / lint panel, attachment chips / drop zone, `@` dropdown, node-card model
controls. Expect some layout or CSS polish to be needed. **Codex flags are unverified** (its binary was removed).

**Bugs found and fixed along the way:**
- path-resolution bug in the hook (macOS `/var` vs `/private/var`);
- `status --state` argument order;
- the terminal menu hung on EOF and swallowed typed-ahead keys;
- menu-page uploads and generation leaked events into the current session;
- zsh `echo` mangled JSON in my test harness (a test-only issue).

---

## 10. Open items / decisions waiting for you (updated 2026-10-06 night)

1. **LICENSE:** your call (MIT is the usual choice for a skill like this). The README has no license badge until then.
2. **Going public:** the repo is private. Before flipping it, check the README renders as you like on GitHub.
3. **Themes** (CRT, liquid glass, minimal, Evangelion-inspired, each with its own sounds): being built; see §15.
4. **A Terraform council of your own:** Councils → New → Generate one, with your PR template and conventions.
5. **Phone layout** for the session page.
6. Codex is hidden from the UI on purpose (Claude only); the code path is still there if it's ever wanted.

---

## 11. Roadmap / ideas backlog (from our discussions)

- **demo.gif** (15 s) at the top of the README. The single most important thing for stars.
- `navi log --md` → a SESSION.md transcript for free (from the docs-agent discussion), plus SCRIBE checkpoint docs.
- A **terminal viewer** (TUI) for SSH/tmux users, mirroring the web graph and feed.
- **Package as a Claude Code plugin** so the WARDEN hook ships bundled.
- An installer via `npx` / `curl | sh`.
- **Mermaid diagram artifacts** rendered in the viewer.
- Repo-aware review with `file:line` citations everywhere.
- More personas: OPERATOR (SRE), CARTOGRAPHER (diagrams), a compliance / GDPR agent.
- A replay from any `log.jsonl` file (`serve --replay path`).
- Optional: let the server start a headless moderator when no terminal is waiting (rejected for now: permissions risk).
- ~~More Lain references~~: the user asked to **tone them down** (2026-10-06): NAVI, the Knights, "layer" and the
  1998 README label stay as quiet nods; no "the wired", no PRESENT DAY / PRESENT TIME at start.

---

## 12. Your preferences and context (for whoever continues)

- You love the **dark CRT / grain** look, but wanted the edges less dark (hence the vignette slider; you set it to 0).
- **Start in the terminal, do everything else in the browser.** The terminal is the launcher; the web is the main
  interface. Everything must be **mouse-navigable**.
- Strong focus on **data safety** (don't feed sensitive data to agents) and on agent quality via **standards + an evaluator**.
- Likes "immersive" touches (ASCII intro, glitch, sounds); Lain references only as quiet nods now (see §11).
- **Ice** is their favourite palette and the default. **Information clarity first:** where am I (folder, branch),
  what's uncommitted or unpushed, what is each agent doing, what did it cost.
- Communication style: casual and fast; send ideas mid-turn. Expects things to work end to end, with honest status.

---

## 13. Key design decisions (and why)

- **File-based protocol + one zero-dependency Python CLI:** any agent host works, sessions can be diffed and replayed, and nothing needs installing.
- **The log is the single source of truth:** the UI only tails it, so reloads, replays and multiple tabs are free.
- **Blocking CLI waits (`ask` / `listen` / `setup --wait`)** are how the browser talks back to an agent that only runs
  shell commands. A 540 s timeout with exit 4 = "run it again".
- **The launcher runs the host as a child (not exec):** that's what makes model relaunch with `--continue` possible and
  lets one terminal own one session (`NAVI_HOST_ID`).
- **Gate on metadata, never content:** reading to decide is already a leak.
- **Headless generation uses `claude -p --tools ""`:** pure text in, text out; no tool permissions, no saved session.
- **Built-ins are read-only:** they're the reference examples for the standard and the generator.
- **One server per project, many sessions:** `/s/<id>` routing; writes must name their session explicitly.

---

## 14. Session 2 (2026-10-06, the new Mac)

- Moved here: code in `~/Documents/navi`, test projects (flappy, pug-quest, scroll-demo) in `~/Documents/test`.
  `./install.sh` was run: `~/.local/bin/navi`, and `~/.claude/skills/navi` + `~/.codex/skills/navi` link to this folder.
  `~/.config/navi/config.json` wasn't copied, so the first `navi` START shows the setup wizard.
- **Visual + functional QA in a real browser (headless Chrome + Playwright) and a real pseudo-terminal**, with a fake
  `claude` binary so no tokens were spent:
  - terminal START -> web menu "TERMINAL LAUNCHER READY" -> pick council -> START SESSION -> the terminal launches
    `claude "/navi"` bound to the new session -> the browser follows it live (agents seated, moderator, messages);
  - terminal NEW SESSION (council picker), CONTINUE, RESUME, AGENTS, QUIT;
  - every web menu tile, Esc / backdrop close, START without a terminal (clear error), CONTINUE without a moderator
    (the CONTINUE IN TERMINAL bar), MENU / THE WIRED navigation, sessions panel actions, the `a` `c` `s` keys;
  - the session page, node cards, `@` autocomplete, the agents / councils / settings / sessions panels.
- **Fixed:**
  - closing any panel on `/` (Esc, backdrop, CLOSE) left you on an empty wired page: it now returns to the main menu;
  - the "◇ AUTO" menu card and the auto council shared the name `auto` (both cards lit up, and the ◇ card's
    "seats the best-fitting council" never ran). The terminal menu also listed `auto` twice;
  - clicking a council card re-ran the whole menu, including the logo animation: it now just selects the card;
  - the menu didn't fit a 1280x720 screen (START SESSION below the fold) and broke on narrow windows: it's responsive now;
  - the missing favicon (a 404 on every load): it's an inline SVG now;
  - RESUME printed your default council instead of the session's own; the terminal picker cut names without an ellipsis.
- Real `claude` 2.1.291 flags checked: `--model`, `-c/--continue` exist. Codex flags are still unverified.

### Session 2, part 2 (the same evening): the big refinement pass

You asked for: faster starts, Knights-only agents, a less cluttered UI, no terminal in the background, boot sounds, a
one-page settings screen, a volume slider, an interactive demo, and local version control. All done; `git log` has it in
three commits on top of the baseline.

**Why starting took 2-3 minutes (from your real log in `~/Documents/.navi`):** the council was seated at 16:48:38, the
moderator's first visible action came at 16:50:43. Claude Code started, then worked through SKILL.md one Bash call at a
time (`up`, `setup --wait`, `sessions`, `council`, `agents`, five persona files), each needing your approval. Fixes:
- `navi brief`: one call that prints the interface URL, setup state, the moderator's mode, the policy (and whether you
  chose it), the council with seats/models/instructions/deliverables, unread user messages, and every seated persona's
  full directive. SKILL.md now says: brief, then straight to the rounds; no taste questions up front; reviewers in parallel.
- `install.sh` adds `Bash(navi:*)` allow rules to `~/.claude/settings.json`, and the launcher passes `--allowedTools` too.
- The NAVI hub shows `moderator connecting… · 0:08` from the host event until the moderator's first real event.

**Headless moderator (default):** the server runs `claude -p` itself (`spawn_headless` in navi.py): prompt first, then
`--session-id <uuid>`, `--model`, `--effort`, `-p --output-format text --permission-prompts none`,
`--permission-mode acceptEdits` (guarded) or `bypassPermissions` (full), `--settings <WARDEN hook + deny rules>`, and a
comma-joined `--allowedTools` (navi rules + GUARDED_RULES + the user's extras). Env: `BASH_DEFAULT_TIMEOUT_MS=600000`.
A supervisor thread restarts it on the same conversation (`--resume <uuid>`) for model switches and `navi relaunch
--allow`, restarts an early exit up to 3 times (budget resets after 10 min of work), and stays down on STOP / `navi down`.
The log is `.navi/hosts/<session>.log` (MODERATOR LOG on the NAVI node). A waiting terminal (START) always takes
precedence, so terminal mode still works exactly as before. Flag combination verified against the real `claude` 2.1.291.
Per-user settings: `moderator` (headless|terminal), `permissions` (guarded|full), `allow_extra`, `volume`, `last_effort`.

**UI:** settings is one page (also the first connection) with grain and edge darkness off by default, a volume slider,
and the moderator section; the menu's host/model/effort/data live under a collapsed OPTIONS row with explanations; the
council editor explains the seats and hides models/data under ADVANCED; the agents panel leads with "describe it, NAVI
writes the directive"; a ◈ DEMO tile; boot sound (a swell + ticks) behind a "click or press a key to connect" gate,
because browsers only allow sound after a gesture.

**Demo:** `/demo` runs a scripted session in the browser (`DEMO_SCRIPT` in web/index.html): The Knights build
"hello, wired", you answer one question (the closing line; roleplay only), CONSENSUS offers OPEN THE PAGE →
`/demo/hello` (demo/hello/index.html, 6.7 KB, no dependencies). `navi demo` serves it standalone.

**Not yet:** a real end-to-end headless run with the real Claude (only the flag check was real; the rest used a fake
`claude`), Codex flags, the README demo.gif, LICENSE, GitHub.

### Session 2, part 3: sessions you can navigate, and a moderator you can see

You came back, found nothing visibly changed (the old tab and the old `navi` process were still showing the old
version: reload + re-run `navi` is all it needed), then asked for better session handling and a premium, uncluttered
UI, and left again. Done and tested (`tests/run.sh`), four more commits:

- **Sessions** are named from the task (`session_name()`), renamable inline in the breadcrumb, trashed (never deleted)
  to `.navi/trash/`. `/sessions` now carries `name`, `awaiting` (asks without replies), `lines`, `council`, `cost`.
- **Header**: the wordmark is home, breadcrumb `› SESSIONS › name`, `+ NEW SESSION`, `⊞ SESSIONS`, `◉ AGENTS`, `⚙`,
  `COMMANDS ⌘K`. A **strip** of live/open sessions with ◆ badges sits under the task. `/#new` opens the menu with the
  task box focused; `/all` opens the switchboard.
- **Switchboard** (`#sessionsP`, also `/all`): cards with state, needs-you, council dots, last lines, cost, OPEN /
  REPLAY / CONTINUE / DELETE, filters ALL/LIVE/OPEN/ENDED. The menu's CONTINUE tile picks the most useful open session.
- **⌘K palette**: commands + "switch to" sessions, filtered by name/task. Keys: `n` new, `s` sessions, `k`/⌘K palette,
  `h` home, `a` agents, `c` councils, `,` settings.
- **Feed**: filter chips (ALL/MESSAGES/THOUGHTS/WARDEN/SYSTEM), ROUND dividers, follows only when you're at the
  bottom (↓ N NEW pill otherwise), empty state. Artifacts and attachments ending in .md render as Markdown (`md()`).
- **Headless trace**: the moderator runs with `--output-format stream-json --verbose`; `pump_stream()` condenses it
  into `hosts/<sid>.trace.jsonl` (+ a readable `.log`), `_tail()` streams new lines as `trace` SSE events (never in
  the session log), the NAVI node shows the current tool call unless the moderator set its own status in the last
  20 s, the NAVI card lists the last 7 ("WHAT CLAUDE IS DOING"). The final `result` message's cost/turns/duration
  accumulate in `session.json.cost` (cards, CONSENSUS, the "finished" host event).
- **Console**: `/end /new /feedback /model /agents /sessions /replay /export /help`, hints while typing, ↑ history
  (localStorage per session). **Replay**: 1×/2×/4× + pause. Hovering a node lifts its wires. LINK LOST banner.
  Browser notifications (opt-in, ⚙) when any session needs you. `navi log --md` / `GET /export` transcript.
- **First-session tour** (4 cards, once, `localStorage navi.tour`), node monograms, `navi doctor`.
- **Real headless run, by accident and for real:** a menu test on the QA server (which still had the real `claude` on
  its PATH) launched a real headless moderator on an empty project with the task "test". It was visible in 18 s
  (16:20:36 → 16:20:54), asked its question non-blocking exactly as SKILL.md says, and went on to gate and draft.
  I stopped it after a minute; its log is in the scratch folder, not the repo. The QA server now has the fake on PATH.

---

## 15. Session 3 (2026-10-06 night): speed, clarity, chat, GitHub

What was built, in order (all on `main`, every suite in `tests/run.sh` green, pushed to OwariX/navi):

- **Pace drives effort.** Quick = low effort, Standard/Auto = medium, Thorough = high, unless chosen in the launch sheet. Continuing
  a session keeps its own pace. Measured on the real machine: a test page went from 7 min 25 s to 34 s.
- **Idle background moderators leave** ~3 min after `end` (`NAVI_AFTER_END_WAIT`), instead of re-reading their whole
  conversation every 9 minutes forever; writing afterwards wakes the **same conversation** (`--resume`, the id is kept in
  `sessions/<id>/claude_session`). CONSENSUS shows how long the session took, and the cost when the moderator leaves.
- **Chat mode:** after `end` the council goes offline (nodes dim, header chip) and NAVI answers as one agent with `navi chat`;
  "Run the council again" starts a new linked session. Terminal moderators just hand the terminal back.
- **Where you are:** home says "Working in <folder> on <branch>" plus the git state in words (uncommitted, not pushed, to pull,
  local only, last commit); folder picker (recent, browse, paste) switches the server in place; branch picker switches or
  creates (locked while a council works there); "New branch for this session" makes `navi/<name>`; branch changes during a
  session are logged live (`branch` events from `emit()`); `.navi/.gitignore` keeps NAVI's files out of git status.
- **Research-based workflow** (`docs/research.md`, 59 sources): checks over debate, one builder, reviewers read-only and blind,
  ≤2 rounds, "Done when: <checks>". The **NAVI rules** (15, in `AGENT_RULES`) are added to every agent automatically:
  `navi brief` prints them, `navi prompt <agent>` gives a subagent rules + seat + task + directive; `navi send --kind verdict`
  enforces the format and evidence for "needs work"; the grader no longer docks personas for omitting protocol.
- **Council Generator** (Councils → New → Generate one): describe → draft → review (rewrite, add, remove) → create.
- **TUI** (`navi tui`, `scripts/tui.py`): the council in the terminal, a client of the same server API (token in
  `.navi/server.json`, mode 0600), follows the configured palette.
- **Terminal menu:** START (this terminal runs the council), START IN BACKGROUND (frees the terminal), START TUI, and a line
  under the menu that explains the highlighted option.
- **Deliverables:** `navi artifact` registers real project files in place (scrubbed snapshot kept); Files tab and CONSENSUS
  have Open / Show in Finder (scripts and apps are only ever shown); "Start it" / `/run` asks the council to run it.
- **Demo:** you write the line the page types; the hello page follows the palette; one PRESENT DAY clock as the easter egg.
- **Look:** ice is the default palette; Lain references toned down (see §11); README rebuilt with the 1998 Owari Labs header,
  the ice GIF, four screenshots, a diagram and the paces.
- **GitHub:** OwariX/navi (private), history rewritten so every commit is OwariX's.
- **Tests:** 9 suites (ui, councilgen, demo, headless, replay, tour, wizard, terminal, tui) on random free ports.

Still being merged at the time of writing: the themes (CRT, liquid glass, minimal, Evangelion-inspired + sounds).

### Session 3, later the same night

- **Look:** ice is the in-app default (red Wired stays one click away). Themes: The Wired (default), CRT, Liquid glass,
  Minimal, Minimal dark, MAGI (Evangelion, quietly: colourways 01/02/03/08/+1.0). Reference themes change the home
  tagline. No theme adds grain. Every open tab follows a theme change. All text keeps 4.5:1 in every theme.
- **Your own skins:** `~/.config/navi/themes/<key>.json` + `.css`, `navi theme new|check|list`, guide in `docs/THEMES.md`.
- **Research round 2** (on the real logs): permission denials came from multi-line navi calls (now one-line with `\n`),
  the cost meter double-counted resumes (fixed), QUICK verdicts are labelled "Quick check". Not done yet from that list:
  a PermissionRequest hook, lean/cache-stable launch flags (verify they exist in your `claude` first), live status from
  the stream, `navi check`, the eval harness, `--agents` for reviewers, evidence in the "done?" card, per-pace budgets.
- **Agents:** STANDARD.md and the five Knights rewritten as lenses with real checks; the generator and council designer
  carry the research. You choose at launch: the council's models, or everyone on the moderator's model; nodes show the
  model each agent really uses (in QUICK, the moderator's).
- **Terminal:** menu order START (background) / START TUI / START IN THIS TERMINAL; `navi --end-all`; `navi --onboarding`.
  TUI: one-button CONSENSUS (⏎ OK) into chat mode, `/new`, `/cd`, the folder in the prompt; the web console has `/cd`, `/pwd`.
- **Onboarding:** welcome → the one-page setup → "You're set" (demo or first council).
- **README:** the demo GIF in ice, a TUI GIF, the themes grid, "Built on research" with all 59 sources.
- **Themes:** eight built in: The Wired (default), CRT, Liquid glass, Minimal, Minimal dark, MAGI (01/02/03/08/+1.0),
  Himmel (Frieren, Fern, Stark) and Pochita (Denji, Makima, Power); the README gallery shows all eight plus "your own".
- **README:** a split-view screenshot (docs/screens/split.png): the TUI at 84 columns beside an editor and the built page.
- **Open:** LICENSE; going public.

### Session 4 (2026-10-07): permissions, real models and effort, tokens, the TUI demo

- **Permission modes, chosen at launch** (web launch sheet, TUI form, Settings has the default; stored per session in
  `session.json`, shown in the session header): *Ask me* (default), *Auto* (Claude Code's auto mode), *Allow all*
  (bypassPermissions, WARDEN hooks still on), *Skip permissions* (`--dangerously-skip-permissions`, nothing checked).
- **Permission cards:** background moderators get a PermissionRequest hook (`navi permit`). Verified with the real CLI:
  in `-p` with `--permission-prompts none` the hook is consulted for anything that would prompt. A card in the bar,
  the feed, "needs you" and the TUI: Allow once / For this session (Claude Code's own rule suggestion, given back as a
  session rule and remembered in `permits.json` for restarts) / Deny. Unanswered after 9 min (`NAVI_PERMIT_WAIT`):
  denied, and the moderator is told to carry on.
- **Models and effort that really run:** every council member is written to `sessions/<id>/agents.json` and passed as
  `claude --agents` (instructions = `navi prompt`, the member's model, the session's effort). The brief tells the
  moderator to spawn members as `subagent_type "<name>"`. Verified for real: a registered agent defined as sonnet/xhigh
  ran on Sonnet while the main session was on Haiku (`modelUsage`).
- **Tokens:** Claude Code's `modelUsage` from every run is kept per model in `session.json` (`usage`), plus NAVI's own
  tokens live in `usage_live.json` during a run. Shown in the session header chip (hover: per model), the NAVI card,
  CONSENSUS and the TUI header.
- **Chat mode is the default after CONSENSUS:** "Back to chat" is the primary (⏎) in web and TUI, with a one-time intro
  (the council rests, NAVI works alone like any coding agent, ask in words for the council). Offline agents are grey,
  still and struck through on the graph.
- **Fixes:** `/end` closes a session no moderator runs; a console message while NAVI waits on a question answers it;
  writing to a paused session resumes NAVI; every slash command says what really happened (web has `/stop`,
  `/continue`, `/resume` too); "No moderator · Continue" is now "Paused · Resume NAVI"; `/tmp` vs `/private/tmp` no
  longer hides a running server; boot lines in web and terminal are much faster (the logo keeps its pace), and the
  browser opens while the terminal intro plays.
- **Themes:** a Themes window (Settings shows your current theme; groups NAVI / Stories / Yours; colourway dots; search).
  Renamed to real references without character names on the Chainsaw Man skin: *Journey's End* (Frieren default,
  Himmel, Fern, Stark) and *Devil Hunter* (Chainsaw, Control, Blood; "Pull the cord."). MAGI: researched unit colours
  (00 Rei's blue-white refit, 01 default, 02, 03 black with white trim, 08, +1.0 the rainbow halo), tagline "You are
  (not) alone.". Old settings carry over (RENAMED_THEMES / RENAMED_VARIANTS).
- **Council Generator:** seats filled with your own agents get a Yours / New one switch, and one button writes fresh
  agents (own names) for the switched seats.
- **TUI demo:** `navi tui --demo` (and DEMO TUI in the menu) plays `demo/script.json`, the same script the browser demo
  now loads; demo sessions can never start a real moderator.
- **Tests:** new suites `permit`, `server`, `tuidemo`; headless checks the agents file and the token counters.
- **Sources of truth:** "folder ~/x", "mcp name", "skill name", for the project (`.navi/sources.json`, the launch sheet)
  or one agent (its persona's `sources:` line, the agent editor). Each member's instructions get "Your sources of
  truth"; skills are preloaded in its agent definition; folders get `--add-dir`, and WARDEN allows reads inside them
  (`sources.json` "folders", written at launch) while deny patterns like `.env` still apply.
- **README:** the theme gallery shows Journey's End and Devil Hunter; WARDEN, the outgoing filter and the research
  bullets are explained in plain words.
- **Open:** LICENSE; going public.

### Session 4, later: guides, sound, releases 0.9.004, sources in your own words, Examples

- **0.9.004 released** (guides on every screen, sound split into alerts/clicks/ambience, Recommended tags, remove
  sessions, `--end-all` closes sessions). `~/Documents/navi-update-test` is a clone held at 0.9.003 to try
  `navi update` on.
- **Sources of truth, rebuilt:** entries are "kind value | note" (kinds folder, mcp, skill, web). The note goes into
  the agents' instructions (`source_line`). *Add a source of truth* opens a box: describe it, `/sources/describe` runs
  haiku via `forge.sources_prompt` (or `read_sources_offline` without `claude`; the app falls back to it if the model
  fails), `read_sources` checks every row (`check_source`: folder exists + `folder_summary`, MCP name in
  `known_mcp` = ~/.claude.json user + project entries + .mcp.json, names only; skills from ~/.claude/skills), offers
  `find_vaults()` (folders with .obsidian in the usual places; `NAVI_VAULT_HOME` for tests) and asks when something's
  missing. `/sources/check` validates before an agent's Save; `/agents/sources` keeps a built-in agent's sources in
  `agent-sources.json` next to the config (`own_sources` merges them). Named websites become
  `WebFetch(domain:...)` allow rules at launch (`source_sites`); the guard still asks in confidential sessions.
- **Examples window** (`#exm`, from Agents, Councils, New + and the generator's More examples…): EX_COUNCILS (platform
  team, small and quick, PR and architecture review, Terraform on Azure) and EX_AGENTS (10, two of them built-ins that
  just open). Use this idea prefills the generator (want + size) or a new agent (name, role, description, sources, or
  the Add a source box with the words); nothing is generated or saved until the user presses the button.
- **Tests:** new suites `sources` and `examples`; the server suite covers notes, websites, the reader, the model path,
  built-in sources and named sites.
- **Server restarts:** the token is new on every start; `post()` and uploads retry once with a fresh token read from
  the page (`freshToken`) when the server refuses the old one (HTML 403, not our JSON errors).
- Known gap: below 900px wide the Agents/Councils lists (and their buttons) are hidden; the editors still work.

### Session 4, evening: engines (0.9.007)

- **Engines** (`scripts/engines.py`, one adapter class each, no NAVI imports): claude (Claude Code), local (Claude Code
  on Ollama's Anthropic API: ANTHROPIC_BASE_URL/AUTH_TOKEN, the DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL vars per tier,
  key set empty, CLAUDE_CODE_MAX_CONTEXT_TOKENS = Ollama's window, nonessential traffic off), codex (`codex exec --json`,
  resume by thread id with every flag BEFORE `resume`, sandbox via -c, NAVI's guard as a per-run PreToolUse hook via
  `-c hooks.PreToolUse=...` + `--dangerously-bypass-hook-trust`; verified for real with local qwen through --oss),
  local-codex (`--oss --local-provider ollama`, reasoning "none" unless the model can think, '' resolves to the strong
  tier so Codex never pulls gpt-oss on its own), gemini (`gemini -p -o stream-json`, --session-id / -r, auto_edit +
  --allowed-tools from NAVI's rules, no hard guard).
- **Tiers:** strong/balanced/fast; opus/fable=strong, sonnet=balanced, haiku=fast. Knights now say tiers. `E.valid_model`
  accepts tiers, Claude names and model ids by shape; generator drafts keep tiers only.
- **Plumbing:** config `engine`, `engines` (per engine: models, url), `engine_chosen`; session.json `engine` (a session
  keeps it; `pick_engine` = launch's ask > session's > NAVI_ENGINE > default); host_env sets NAVI_ENGINE + engine env;
  `guard_spec()` is engine-neutral (Claude builds settings from it via `E.claude_settings`); pump_stream takes the
  engine's Stream; conversation ids: claude_session (Claude Code) or conversation.<engine>; generators call `llm()` on
  the default engine (local: straight to Ollama /api/chat).
- **Members without registration:** `navi run <agent> [--bg]`, `navi runs [--wait]`; inherits the moderator's model
  when the seat has none; traces tagged with the agent; costs via add_cost. The brief tells non-Claude moderators.
- **CLI:** `navi engine` (wizard / list / use / test), `navi --engine X`, `navi uninstall [--purge] [--yes]`,
  install.sh `--engine`, `--no-wizard`, `--uninstall`; skill also linked to ~/.agents/skills.
- **UI:** launch sheet Engine row (models/effort/permissions follow), Settings > Engine with Test it (/engine/test),
  engine chip in the session header, model labels like "Balanced · qwen3-coder:30b"; TUI ENGINE field.
- **Local context window:** Local runs on `<model>-navi64k` copies (Ollama /api/create with num_ctx; `Engine.prepare()`
  makes them before every run, `run_model()` names them, `describe()` keeps your model's name; NAVI_COPY filters them
  from model lists). Settings > Engine > Window (32k/64k/128k, engines.local.context). Real result: at 32k qwen3-coder
  printed the page instead of using tools (three restarts); the 64k run is the comparison.
- **Real runs (this Mac, scratch projects, harness in the session scratchpad):**
  - Local (Claude Code + qwen3-coder:30b): full Quick council in 853 s, $0, 618k tokens in.
  - Local via Codex: 189 s, with one deviation: it ended without asking "done?".
  - Local via Codex in *Ask me* (Codex's sandbox): the first try's reviewer died at once ("OSS setup failed: No running
    Ollama server detected"). After the fix below, two reviewers ran in parallel, flagged a missing charset, the lead
    fixed it, both approved and the moderator ran `navi end`: 988 s, $0, 954k tokens in.
  - Writing to an ended Local via Codex session woke the moderator with `exec resume <its real thread id>`.
  - At 32k the model never used tools. The first 64k run wrote ~/hello.html via `cd ~ && echo >` (removed). That led to
    two fixes: the guard's `write_targets` and the project folder stated in the brief, the first prompt and
    agent_prompt.
  - Gemini: Google refuses this client's free personal login (IneligibleTierError, "migrate to Antigravity"); an API
    key works.
  - Codex on OpenAI: usage limit until reset. Both errors now show via `E.why()`.
- **Fixes found by real runs:** Codex names its own threads (`own_ids`), so NAVI keeps the thread id from its output
  (pump_stream on_conv) rather than one it made up. The fake now refuses unknown threads. `stop_runs()` stops member
  runs with their session, and a stopped `navi run` stops its program.
- **Codex's sandbox and members** (verified with `codex sandbox -- ...`):
  - Commands inside Codex's sandbox see `CODEX_SANDBOX=seatbelt` and `CODEX_SANDBOX_NETWORK_DISABLED=1`. Even
    localhost is blocked, and a nested sandbox fails (`sandbox-exec: sandbox_apply: Operation not permitted`). So a
    member started from in there can't reach its model or sandbox its own commands.
  - Fix: inside the sandbox, `navi run` (`run_outside`) writes `.navi/runq/<hid>.<sid>.<agent>.json` and waits.
    `serve_member_runs`, a thread of whoever launched the moderator (spawn_headless or run_host, for engines without
    subagents), starts `navi run <agent> --task-file` outside the sandbox.
  - Records go `queued` → `running` → done/failed. The broker validates the model name. With no launcher (NAVI_HOST_ID
    missing, or no host file), `navi run` fails at once.
  - From inside a sandbox, `os.kill(pid, 0)` on an outside process raises PermissionError, so `pid_alive` treats that
    as alive.
  - The fake Codex now sandboxes the same way, and a fake Codex started inside a sandbox fails like the real one.
- **Tests:** engines (70 checks: commands, parsers, CLI, hook dialect, member runs inside Codex's sandbox, councils on
  each engine through the server, Ask me / background / Allow all on Codex),
  enginesui (22, browser), install (22, fake HOME). Fakes: tests/fake-codex, tests/fake-gemini, tests/fake_ollama.py.
- **Machine facts (this Mac):**
  - Ollama 0.30.8 with qwen3-coder:30b (pulled for tests), context 32k. NAVI made the copies `qwen3-coder:30b-navi64k`
    and `qwen2.5:7b-navi64k` (`ollama rm` removes them).
  - Codex 0.159.3: out of OpenAI tokens until reset, but `--oss` works.
  - Gemini CLI 0.60.0 signed in.
  - Docs: docs/ENGINES.md.
- **Uninstall/reinstall, done for real on this Mac:** `navi uninstall --yes` stopped the server and removed the command,
  both skill links and the 4 rules. Its backup equalled the original, and only the navi rules differed.
  `./install.sh --no-wizard` put everything back, including ~/.agents/skills/navi; settings.json came back identical.
  The server was restarted on 7701, and `navi doctor` is all good.

### Session 4, night: ready for strangers (0.9.008)

- **Repo:** MIT LICENSE (Copyright OwariX), CONTRIBUTING.md, SECURITY.md (private vulnerability reports: turn on
  "Private vulnerability reporting" in Settings > Security when the repo goes public; it isn't available on a private
  repo), issue/PR templates, description + topics set with `gh repo edit`. **Still private** (the user's call).
  docs/social-preview.png (1280x640) is ready, but GitHub only takes it in the web UI: Settings > Social preview.
- **CI:** .github/workflows/tests.yml: every suite on ubuntu-latest (Python 3.12, Chrome, ~11 min) and the Python
  suites on 3.9. The whole suite also passes on macOS's own Python 3.9.6 (so README says 3.9+). One flake fixed
  (sources: 5 s wait -> 15 s). GitHub once returned "Internal Server Error" to every git push for ~20 min (API writes
  worked): wait and retry.
- **Plugin:** .claude-plugin/{plugin.json,marketplace.json} (the repo is its own marketplace, source "./"),
  hooks/hooks.json -> hooks/guard.sh (shell fast path: no .navi/policy.json up the tree = exit 0 without Python;
  NAVI_HOST_ID set = exit 0, the run has its own guard; else `navi hook` with NAVI_HOOK_FROM=plugin, which only acts
  while a session is open there), bin/navi (Claude Code puts a plugin's bin/ on its PATH). `"agents": []` is needed:
  a plugin's agents/ dir loads as subagents (NAVI's personas would show up everywhere). Gotcha: with the manifest
  present, the install.sh symlink ~/.claude/skills/navi loads as plugin `navi@skills-dir` (hook included); `claude
  plugin details` shows it with 0 skills, but a real session still lists the skill as `navi` (checked with a haiku
  `claude -p`). Marketplace installs name it `navi:navi`. SKILL.md has `allowed-tools: Bash(navi:*), Bash(navi *)`.
  release.sh writes the plugin version too. Tested: `claude plugin validate`, an isolated CLAUDE_CONFIG_DIR install
  (CLI only: an isolated config isn't logged in), install_test checks.
- **Gemini guard:** Gemini CLI 0.60 hooks: settings `hooks.BeforeTool`, stdout `{"decision":"deny","reason":...}`;
  Claude's hookSpecificOutput is ignored; a hook that crashes, times out or prints nothing lets the call through; "ask"
  would hang -p. No per-run flag, and GEMINI_CLI_SYSTEM_SETTINGS_PATH is ignored unless root owns the file and its
  parents. So `Gemini.guard_env()` builds GEMINI_CLI_HOME=<.navi>/hosts/gemini-home whose .gemini links everything in
  the user's (NAVI_GEMINI_USER_HOME remembers the real one for nested runs) and has a copy of settings.json with the
  hook first, hooksConfig.enabled, navi-guard never disabled. navi.py `guard_env()` adds it to every launch (not in
  Skip permissions). Tool names: read_file, write_file, replace, run_shell_command, grep_search, read_many_files,
  web_fetch (URLs inside `prompt`). The fake Gemini runs BeforeTool hooks like the real one; FAKE_PEEK=1 tries .env.
- **"Done?" question:** supervise(): exit 0, not ended, and the moderator's last navi status since this start is
  "done" -> ask_if_done() posts an ask (kind "end", END_OPTIONS) and stops; /reply "Yes, end the session" closes the
  session with that status as the summary, anything else wakes it (the usual reply path). The brief for engines
  without subagents says `navi` is a shell command (a local model called a tool "navi_status").
- **Codex in its sandbox (Ask me/Auto):** see "Codex's sandbox and members" above; on hold otherwise (the user will
  look at Codex later: no permission cards on Codex for now).
- **Windows:** main() refuses on os.name == "nt" (except --version/--help) with the WSL steps; docs/WINDOWS.md (not run
  on Windows yet: it says so).
- **Phones:** `.split` panels (Agents, Councils) are list-then-detail under 900px (`detail(panel, on)`, back buttons
  #aBack/#coBack, close buttons in the lists); session top bar under 560px keeps #modPill (ellipsis), #bNew (icon),
  #bPal, #bSide; the hub's status lines are left to the pill on narrow stages (`narrowStage`, set in layout());
  `ringRadii()` makes an ellipse on tall stages. tests/e2e/phone.js (iPhone 13).
- **Launch sheet copy:** pace texts now say build-then-check (web, TUI, CLI, demo); the Agents line groups agents by
  model.
- **Benchmarks:** bench/tasks/<name>/{task.json, project/, check.py} (each check proven both ways: passes on a reference
  fix, fails on the untouched project), bench/run.py (own server + settings, Allow all, answers questions, times to
  the session's end: a moderator lingers after `navi end` for follow-up chat, so NAVI_AFTER_END_WAIT=5),
  bench/report.py -> docs/BENCHMARKS.md. The runner refuses permission cards (Allow all still asks outside the
  project; a local model read `/users.py` at the disk's root and the unanswered cards ate the run) and writes to
  NAVI_BENCH_RESULTS when set (tests). Found by it: `navi down` (stop_headless) left `navi run` members running; a
  member held qwen3-coder for 3 hours and voided every later local run. Fixed in 0.9.009. Results: Claude 4/4 (21 s to 3 min, $0.25-$1.25); Local passes the quick
  ones in ~3 min and doesn't finish Standard/Thorough in 30 min (members via `navi run`, three Claude Codes on one
  GPU, a reviewer rewriting the code).

### Versions and releases (from 0.9.001)

- `VERSION` holds MAJOR.MINOR.BUILD (BUILD three digits, +1 every release; 1.0.000 = the public launch).
- To release: write the `## X.Y.ZZZ (date)` section in `CHANGELOG.md`, commit everything else, then
  `scripts/release.sh X.Y.ZZZ` (writes VERSION, commits "Release X.Y.ZZZ", tags vX.Y.ZZZ, pushes, creates the GitHub
  release from that changelog section). The repo's git identity is OwariX.
- Users: `navi update` (fast-forward to the newest tag, refuses over local changes, prints the new changelog
  sections), `navi update --check`, `navi --version`. The server checks for a newer release once a day in the
  background (`~/.config/navi/update.json`); Settings and the terminal intro say when one is out.
- End sessions: home has an End sessions button (this one or all open ones); `/effort` exists in web and TUI.
