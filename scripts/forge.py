"""
forge.py - the persona workshop: library paths, the standard's evaluator (lint), and the headless
generator / deep reviewer that run `claude -p` with every tool disabled (text in, text out).

Zero dependencies.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
BUNDLED = HOME / "agents"
STANDARD = BUNDLED / "STANDARD.md"
USER_LIB = Path(os.environ.get("NAVI_LIBRARY", "~/.config/navi/agents")).expanduser()
AGENT_MODELS = ("", "opus", "sonnet", "haiku", "fable")      # Claude's names ("" = inherit); engines.py also takes tiers
VAGUE = ("best practice", "as needed", "as appropriate", "etc.", "various", "and so on", "where applicable", "if necessary")
BYPASS = re.compile(r"(?i)\b(ignore|bypass|skip|disable|override)\b[^.\n]{0,30}\b(warden|gate|policy|redact|human|user)\b")
SECRET_READ = re.compile(r"(?i)\b(read|cat|open|print|show)\b[^.\n]{0,30}(\.env\b|tfstate|id_rsa|\.pem\b|secrets?/|kubeconfig)")
# "Never skip the gate", "don't read .env": the same words, as a rule to keep (a negation earlier in the same sentence)
NEGATED = re.compile(r"(?i)\b(never|not|no|don't|doesn't|mustn't|cannot|can't|won't|avoid|refuse to)\b[^.\n;:!?]{0,24}$")


def unsafe(text: str):
    """The first instruction that would bypass WARDEN, the gate or the human, or read a secret; None when there's
    none. A negated one ("never bypass WARDEN") is the opposite, and fine."""
    for rx in (BYPASS, SECRET_READ):
        for m in rx.finditer(text or ""):
            if not NEGATED.search(re.split(r"[.\n;:!?]", text[max(0, m.start() - 60):m.start()])[-1]):
                return m
    return None


# ---------------------------------------------------------------- library

def persona_dirs(project_navi: Path | None) -> list[tuple[str, Path]]:
    """Lowest to highest precedence: bundled < my library < this project."""
    dirs = [("builtin", BUNDLED), ("library", USER_LIB)]
    if project_navi:
        dirs.append(("project", project_navi / "agents"))
    return dirs


def persona_files(project_navi: Path | None) -> dict[str, tuple[str, Path]]:
    out: dict[str, tuple[str, Path]] = {}
    for scope, d in persona_dirs(project_navi):
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                if p.stem.upper() != "STANDARD":
                    out[p.stem] = (scope, p)
    return out


def examples(n: int = 3) -> list[str]:
    names = ("warden", "adversary", "scribe", "architect", "ledger")
    return [(BUNDLED / f"{x}.md").read_text(encoding="utf-8") for x in names[:n] if (BUNDLED / f"{x}.md").exists()]


# ---------------------------------------------------------------- evaluator (deterministic)

# what the NAVI rules (navi.py AGENT_RULES) already give every agent: inbox, message kinds and verdict format,
# evidence, status lines, when to ask the human
RULES_COVER = {"protocol-inbox", "protocol-kinds", "end-state", "evidence", "status", "human"}


def lint(name: str, role: str, description: str, directive: str, color: str = "", others: list[dict] | None = None) -> dict:
    """Score a persona against STANDARD.md. -> {score, grade, findings:[{level, rule, msg, fix}]}"""
    t = directive or ""
    low = t.lower()
    F: list[dict] = []

    def check(ok: bool, weight: int, rule: str, msg_ok: str, msg_bad: str, fix: str, warn: bool = False):
        if not ok and rule in RULES_COVER:      # NAVI adds its rules to every agent: the persona needn't repeat them
            ok, msg_ok = True, f"{msg_ok} (from the NAVI rules, added to every agent automatically)"
        F.append({"level": "ok" if ok else ("warn" if warn else "fail"), "rule": rule,
                  "msg": msg_ok if ok else msg_bad, "fix": "" if ok else fix, "weight": weight, "pass": ok})

    ident = re.search(r"you are \*\*([a-z0-9_-]+)\*\*", low[:300])
    check(bool(ident), 12, "identity", "starts with an identity line",
          "no `You are **NAME**, ...` identity line at the top", f"Start with: You are **{(name or 'NAME').upper()}**, the council's {role or '<role>'}.")
    if ident and name:
        check(ident.group(1) == name.lower(), 3, "identity-name", "identity matches the agent name",
              f"identity says {ident.group(1).upper()} but the agent is {name.upper()}", "Use the same name in the identity line.", warn=True)
    check(bool(role and 1 <= len(role.split()) <= 5), 4, "role", "role is short and set",
          "role is missing or too long", "Give a 1-3 word role, e.g. 'terraform reviewer'.", warn=True)
    check(bool(description and len(description) <= 200), 5, "description", "has a one-line description",
          "missing one-line description (shown when the node is clicked)", "Add one sentence: what this agent does for the council.", warn=True)
    check("inbox" in low, 10, "protocol-inbox", "reads its inbox before acting",
          "never mentions reading its inbox", "Add: Read your inbox before acting, and answer every message addressed to you.")
    kinds = [k for k in ("challenge", "verdict", "proposal", "revision", "artifact", "note") if k in low]
    check(len(kinds) >= 2, 10, "protocol-kinds", f"uses message kinds ({', '.join(kinds)})",
          "doesn't say which message kinds it sends", "Name the kinds: reviewers send `challenge` + `verdict`, leads `proposal` + `revision`, recorders `artifact`.")
    check(bool(re.search(r"verdict|approve|deliverable|artifact|writes? .*(file|\.md)|report the|summary", low)), 10, "end-state",
          "has a clear end state (verdict or deliverable)", "no verdict or deliverable: the round never ends",
          "Add: End each round with a `verdict`: approve, approve with conditions, or needs work (or name the files you produce).")
    check(any(w in low for w in ("gate", "evidence", "file:line", "real code", "source of truth", "metadata")), 8, "evidence",
          "grounds claims in real code (and gates reads)", "no rule about evidence or gating reads",
          "Add: Back claims with the actual code or config. Gate every read with `navi gate` first.")
    check("status" in low, 5, "status", "sets status before slow work", "never sets a status (the node looks frozen)",
          "Add: Set `navi status <me> \"...\"` before slow work.", warn=True)
    check("ask" in low and ("human" in low or "user" in low), 5, "human", "knows when to ask the human",
          "no rule for asking the human", "Add: Use `navi ask` only when the human's choice changes the outcome.", warn=True)
    check(bool(re.search(r"\bnever\b|\bdon't\b|\bdo not\b", low)), 8, "boundaries", "has explicit boundaries",
          "no explicit 'never' or 'don't': nothing it must avoid", "Add a hard boundary, e.g. Never read secrets, never rubber-stamp.")
    lens = bool(re.search(r"\byour lens\b|\blens\b|belongs? to\b|\bleaves? (it |them |that )?to\b|\bnot your job\b|\byou don't (redesign|fix|build|edit)", low))
    check(lens, 6, "lens", "names its lens and what it leaves to others", "doesn't say what it checks that the others don't",
          "Add a line: Your lens is <what only you check>. <What you leave> belongs to the other members.", warn=True)
    runnable = len(re.findall(r"`[^`\n]{2,60}`", t)) + len(re.findall(r"\b(measure|run|grep|count|file:line|ls -l|plan|validate|test)\b", low))
    check(runnable >= 3, 8, "checks", "names concrete checks", "no concrete checks: what does it run, measure or point at?",
          "Turn opinions into checks: a command in backticks, a measurement, or a criterion someone else could verify.", warn=True)
    bullets = len(re.findall(r"(?m)^\s*[-*] ", t))
    check(bullets >= 4, 6, "structure", f"{bullets} concrete bullets", f"only {bullets} bullet(s): behaviour isn't concrete",
          "Write 5-9 bullets, each one a testable behaviour.")
    vague = [v for v in VAGUE if v in low]
    check(not vague, 6, "concrete", "no vague filler", f"vague wording: {', '.join(vague)}", "Replace the vague words with the actual checks.", warn=True)
    n = len(t)
    check(500 <= n <= 3500, 4, "length", f"{n} characters", f"{n} characters (aim for ~600-3000)",
          "Trim to the essentials." if n > 3500 else "Add concrete behaviours.", warn=True)
    bad = unsafe(t)
    check(not bad, 14, "safety", "nothing that bypasses WARDEN, the gate or the human",
          f"unsafe instruction: \"{bad.group(0)[:60]}\"" if bad else "", "Remove it. Agents must never bypass WARDEN, the gate or the human.")
    if others:
        clash = [o["name"] for o in others if o["name"] != name and color and o.get("color", "").lower() == color.lower()]
        check(not clash, 0, "color", "colour is distinct", f"same colour as {', '.join(clash)}", "Pick a distinct colour.", warn=True)

    total = sum(f["weight"] for f in F) or 1
    got = sum(f["weight"] for f in F if f["pass"])
    score = round(100 * got / total)
    grade = "A" if score >= 90 else "B" if score >= 78 else "C" if score >= 64 else "D" if score >= 50 else "F"
    for f in F:
        f.pop("weight")
        f.pop("pass")
    return {"score": score, "grade": grade, "findings": F}


# ---------------------------------------------------------------- headless LLM (generator + deep review)

PALETTE = ("#7fe7ff", "#ff2a4a", "#ffb347", "#e8e2d0", "#5dffb5", "#b18cff", "#ff8fd8", "#7b9cff", "#ffd24a",
           "#4fd1c5", "#f6ad55", "#9ae6b4", "#fc8181", "#90cdf4", "#d6bcfa", "#fbd38d")


def pick_color(taken: list[str]) -> str:
    used = {c.lower() for c in taken if c}
    return next((c for c in PALETTE if c not in used), "#b18cff")


def llm_available() -> str | None:
    return "claude" if shutil.which("claude") else None


def run_llm(prompt: str, model: str = "sonnet", timeout: int = 240) -> str:
    """Text in, text out. Every tool disabled, nothing persisted. Raises RuntimeError with a readable reason."""
    if not llm_available():
        raise RuntimeError("the `claude` CLI isn't on PATH, so headless generation is unavailable")
    cmd = ["claude", "-p", "--tools", "", "--no-session-persistence", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    try:
        r = subprocess.run(cmd + [prompt], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, cwd=str(Path.home()))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"generation timed out after {timeout}s")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or f"claude exited {r.returncode}").strip()[:400])
    return r.stdout.strip()


# The research behind NAVI's workflow (docs/research.md), condensed for the prompts that design councils and write agents.
RESEARCH = """What makes a council work (from the research behind NAVI; follow it):
- A seat is a lens, not a character. Persona voice and backstory don't change results; a distinct thing to check,
  concrete checks and evidence do. Write checks someone else could run or verify, never "review the code".
- One builder: only the lead edits project files and runs the checks; reviewers read and run read-only checks on the
  built result, write their findings before seeing anyone else's, and change position only on new evidence.
- Every finding carries evidence (file:line, a command and its output, a repro), a severity (high: breaks, leaks or costs
  real money now; medium: under a stated condition; low: a note, never a blocker), the fix, and the check that proves it.
- Different lenses beat more of the same: two reviewers with the same job add cost, not insight. Two reviewers is the
  norm, three for security-critical work, never more than four.
- Reviewers judge best on a different model than the lead (e.g. the balanced tier when the lead runs on strong); light
  recorders run on the fast tier.
- If the checks pass, the verdict is "approve, no blockers". Nobody invents findings to look useful.
- The NAVI rules (inbox, message kinds, verdict format, brevity, status, when to ask the human, no secrets) are added to
  every agent automatically: never repeat them in a persona."""


def repair_prompt(text: str, findings: list[dict]) -> str:
    """The checker's findings, back to the model that wrote the persona: fix exactly these."""
    issues = "\n".join(f"- {f['msg']}: {f['fix']}" for f in findings if f.get("level") != "ok")
    return ("NAVI's checker scored this persona file and found these problems:\n" + issues +
            "\n\nRewrite the whole file so each of them is fixed. Keep everything else: the frontmatter, the voice, the "
            "checks it already names. Return only the file, starting with ---.\n\n" + text)


def generate_prompt(name: str, role: str, color: str, description: str, council: list[dict]) -> str:
    team = "\n".join(f"- {a['name']} ({a.get('role', '')}): {a.get('description', '')}" for a in council) or "- (none yet)"
    ex = "\n\n".join(f"<example>\n{e.strip()}\n</example>" for e in examples())
    return f"""You write council-member personas for NAVI, a multi-agent council tool. Follow the standard exactly and match the style of the examples.

<standard>
{STANDARD.read_text(encoding="utf-8")}
</standard>

<research>
{RESEARCH}
</research>

{ex}

<current_council>
{team}
</current_council>

<request>
name: {name}
role: {role or "(choose a 1-3 word role)"}
color: {color or "(choose a distinct hex colour)"}
what the user wants: {description}
</request>

Write the complete persona file for "{name}": frontmatter (name, description, role, color, model: "") then the directive.
It must have its own lens (nothing the current council already checks), say what it leaves to the others, and list
concrete checks with how it proves a finding and rates its severity. No backstory, no persona voice, no NAVI protocol.
Output ONLY the file contents, starting with --- . No commentary, no code fences."""


def edit_prompt(name: str, role: str, color: str, description: str, directive: str, change: str) -> str:
    """One change to a persona the user already likes: edit that, keep the rest word for word (the editor shows the diff)."""
    return f"""<task>navi-edit-persona</task>
You edit council-member personas for NAVI. The user likes this persona and wants one change. Make that change and
nothing else.

<standard>
{STANDARD.read_text(encoding="utf-8")}
</standard>

<persona>
---
name: {name}
description: {description}
role: {role}
color: {color}
model: ""
---
{directive}
</persona>

<change>
{change}
</change>

Rules:
- Every line the change doesn't need stays exactly as it is: same words, same order, same formatting.
- Change, add or remove only the lines the change needs. A new check goes next to the checks like it.
- Change the description or the role only if the change alters what the agent does.
- If the change would break the standard (its own lens, how it proves a finding, what it leaves to others), make it in
  the way that keeps the standard.
Output ONLY the complete file, starting with --- . No commentary, no code fences."""


def review_prompt(name: str, role: str, description: str, directive: str, findings: list[dict]) -> str:
    lint_txt = "\n".join(f"- [{f['level']}] {f['rule']}: {f['msg']}" for f in findings if f["level"] != "ok") or "- none"
    return f"""You review council-member personas for NAVI against this standard:

<standard>
{STANDARD.read_text(encoding="utf-8")}
</standard>

<persona name="{name}" role="{role}" description="{description}">
{directive}
</persona>

<automatic_lint_findings>
{lint_txt}
</automatic_lint_findings>

Judge how well this persona will actually work in a council: clarity of mission, testable behaviour, protocol use,
boundaries, overlap risk, and safety. Return ONLY a JSON object, no fences:
{{"score": <0-100>, "verdict": "<one sentence>", "strengths": ["..."], "issues": [{{"severity": "high|medium|low", "issue": "...", "fix": "..."}}],
 "improved_directive": "<the full improved directive body (no frontmatter), keeping the author's intent>"}}"""


def parse_persona(text: str) -> tuple[dict, str]:
    t = text.strip()
    t = re.sub(r"^```[a-z]*\n|\n```$", "", t)
    meta, body = {}, t
    if t.startswith("---"):
        end = t.find("\n---", 3)
        if end != -1:
            for line in t[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.split("#", 1)[0].strip().strip('"')
            body = t[end + 4:].lstrip("\n")
    return meta, body.rstrip()


def parse_json(text: str) -> dict:
    t = text.strip()
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise RuntimeError("the model didn't answer with JSON")
    return json.loads(t[a:b + 1])


def sources_prompt(text: str, mcp: list[str], skills: list[str]) -> str:
    """'Describe it in your own words' -> sources of truth (navi.py checks every one and shows them before saving)."""
    return f"""<task>navi-read-sources</task>
The user is telling NAVI where its agents should check facts before they state them: their "sources of truth".
Anything they trust can be one. Turn their words into a list. Kinds:
- folder: a folder on this machine (docs, an Obsidian vault, a folder of PDFs, a wiki cloned with git).
  value: the path exactly as they wrote it (~/..., /... or relative like docs/).
- file: one file on this machine (a single note, a PDF, a spec). value: its path exactly as they wrote it.
- mcp: an MCP server their agent program has. value: its name. Their servers: {", ".join(mcp) or "(none found)"}.
- skill: a Claude Code skill. value: its name. Their skills: {", ".join(skills) or "(none found)"}.
- web: a website or online docs. value: the https:// address of the most specific part they named.
- other: anything else they trust (a Confluence space, a book, a database, "ask the platform team"). value: what it
  is, in their words, at most 150 characters.
Rules:
- Only what they said. Never invent a path, name or address: if they name a folder or file without saying where it
  is (say "my vault"), add it with value "" and ask for it in "question".
- Match loose names to theirs: "the obsidian mcp" is the server whose name contains obsidian.
- Read through an MCP server -> mcp; a vault or wiki folder -> folder; one note or document -> file. Both named -> both.
- What fits no other kind is "other": never drop something they named.
- note: what the source covers, in their words, at most 80 characters ("the team's runbooks", "Azure docs").
Answer with JSON only: {{"sources": [{{"kind": "folder", "value": "~/Notes", "note": "my notes"}}], "question": ""}}

Their words:
<words>
{text}
</words>"""


# ---------------------------------------------------------------- council builder

COUNCIL_SIZES = {"small": "3-4", "medium": "5-6", "large": "7-9"}     # members in total, the guard included


def suggest_council_prompt(description: str, personas: list[dict], size: str = "") -> str:
    lib = "\n".join(f"- {p['name']} ({p.get('role', '')}): {p.get('description', '')}" for p in personas)
    many = f"{size} ({COUNCIL_SIZES[size]} members in total, counting the guard)" if size in COUNCIL_SIZES \
        else "auto (the smallest council that does this well, usually 4-6 members)"
    return f"""<task>navi-design-council</task>
You design councils for NAVI, a multi-agent tool where named agents plan, build and check work:
the LEAD plans, builds and runs the checks, REVIEWERS check the built result through their own lens and give verdicts, the RECORDER writes
the deliverables, the GUARD (always "warden") protects data, and MEMBERS ("extra") join only when the moderator needs them.

<research>
{RESEARCH}
</research>

<existing_personas>
{lib}
</existing_personas>

<what_the_user_wants>
{description}
</what_the_user_wants>

Size: {many}.
Reuse existing personas when they fit. Only invent a new persona when nothing existing covers a needed responsibility,
never give a new persona the name of an existing one, and don't add roles the user said they don't care about.
Give every reviewer a different lens. Models are tiers (NAVI maps them to whatever engine the user runs): "" (the
moderator's own) or "strong" for the lead, "balanced" for reviewers (a different model than the lead judges it more
fairly), "fast" for the recorder and light checks.
Return ONLY a JSON object, no fences:
{{"name": "<kebab-case, max 32>", "title": "<max 60 chars>", "description": "<one sentence>",
 "lead": "<persona>", "reviewers": ["<persona>", ...], "recorder": "<persona>", "guard": "warden", "extra": ["<persona>", ...],
 "models": {{"<persona>": "strong|balanced|fast"}}, "sensitivity": "public|internal|confidential",
 "instructions": "<3-6 sentences for the moderator: what to do, what is out of scope, hard rules>",
 "outputs": ["<deliverable>", ...],
 "new_agents": [{{"name": "<kebab-case>", "role": "<1-3 words>", "color": "#rrggbb", "description": "<one sentence>",
                 "brief": "<2-4 sentences: its lens and the concrete checks it runs, for the persona writer>"}}],
 "briefs": {{"<each member>": "<one sentence: what this member checks or does in this council>"}},
 "why": "<2 sentences explaining the design>"}}"""


def suggest_council_offline(description: str, personas: list[dict], size: str = "") -> dict:
    """No LLM available: pick seats from the bundled personas by keywords."""
    d = description.lower()
    names = {p["name"] for p in personas}
    if any(w in d for w in ("security", "threat", "audit", "pentest", "red team")):
        base = {"lead": "architect", "reviewers": ["adversary"], "recorder": "scribe", "models": {"adversary": "balanced", "scribe": "fast"},
                "outputs": ["threat model", "prioritized fixes"]}
    else:
        base = {"lead": "architect", "reviewers": ["adversary", "ledger"], "recorder": "scribe",
                "models": {"adversary": "balanced", "ledger": "balanced", "scribe": "fast"},
                "outputs": ["working code", "short ADR"]}
    if "don't care about cost" in d or "no cost" in d or "cost doesn't matter" in d or size == "small":
        base["reviewers"] = [r for r in base["reviewers"] if r != "ledger"]
    words = re.findall(r"[a-z0-9]+", d)[:3] or ["my"]
    return {"name": ("-".join(words)[:24] + "-council").strip("-"), "title": description[:60], "description": description[:300],
            "guard": "warden", "sensitivity": "internal", "new_agents": [],
            "instructions": f"The user wants: {description[:400]}", "why": "Picked offline from keywords (no engine was ready to write it).",
            **{k: v for k, v in base.items()}, "reviewers": [r for r in base["reviewers"] if r in names]}


def draft_agent_prompt(want: str, agent: dict, council: dict, taken: list[str]) -> str:
    """One council member, drafted from the user's words (agent = {}) or redrafted with a change (agent = the current draft)."""
    team = "\n".join(f"- {m['name']} ({m.get('role') or 'no role yet'}, {m.get('seat') or 'member'}): {m.get('brief', '')}"
                     for m in council.get("members", [])) or "- (nobody yet)"
    if agent.get("name"):
        keep = ("It is an existing agent from the user's library: the change makes it a NEW agent, so give it a new name."
                if agent.get("existing") else "Keep its name unless the change calls for a different one.")
        ask = f"""<current_agent name="{agent['name']}" role="{agent.get('role', '')}">
{agent.get('brief', '')}
</current_agent>

<change>
{want}
</change>

Redraft this agent with the change applied. {keep}"""
    else:
        ask = f"""<request>
{want}
</request>

Draft one new agent for this request. It must complement the members above rather than duplicate them."""
    return f"""<task>navi-draft-agent</task>
You draft council members for NAVI, a multi-agent tool where named agents plan, build and check work:
the LEAD plans, builds and runs the checks, REVIEWERS check the built result through their own lens, the RECORDER writes the deliverables,
the GUARD protects data.

<research>
{RESEARCH}
</research>

<council title="{council.get('title', '')}">
{council.get('description', '')}
Members:
{team}
</council>

<taken_names>
{', '.join(taken)}
</taken_names>

{ask}
Return ONLY a JSON object, no fences:
{{"name": "<kebab-case, max 32, not in taken_names>", "role": "<1-3 words>", "description": "<one sentence>",
 "brief": "<2-4 sentences: what this agent must check or do, for the persona writer>", "seat": "lead|reviewer|recorder|member"}}"""


_STOP = set("a an the and or but for from with without who that which what when where how someone something agent agents one "
            "our my your their this these those them they it its is are be been all any every each more most before after "
            "into onto about makes make checks check sure also only just very really should would could can will".split())


def draft_agent_offline(want: str, agent: dict) -> dict:
    """No LLM available: keep the user's own words (a redraft appends them to the current brief)."""
    if agent.get("name"):
        return {"name": agent["name"], "role": agent.get("role", ""), "description": "",
                "brief": f"{agent.get('brief', '').strip()}\n{want.strip()}".strip()}
    words = [w for w in re.findall(r"[a-z0-9]+", want.lower()) if w not in _STOP and len(w) > 2][:2]
    return {"name": "-".join(words) or "agent", "role": " ".join(words) or "specialist", "description": "", "brief": want.strip()}
