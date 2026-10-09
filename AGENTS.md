# NAVI (for Codex, Gemini CLI, Cursor and other AGENTS.md hosts)

When the user asks for **/navi**, a NAVI session, an architecture council, a design review or a
red-team of a design, follow [`SKILL.md`](./SKILL.md) in this directory exactly. It is the canonical spec.

Shortcut:
- `<skill-dir>` = the directory containing this file.
- CLI: `python3 <skill-dir>/scripts/navi.py --help`
- Personas: `<skill-dir>/agents/*.md`

**Data safety:** before reading files, running data-touching commands or fetching URLs, run
`navi.py gate`. Exit 0 = go, 3 = ask WARDEN, 2 = denied. Never paste raw file contents into messages.

Council members: `navi brief` says how they run on your engine. Where they aren't registered as subagents,
`navi run <agent> "<assignment>"` runs one for you on its own model (`--bg` and `navi runs --wait` for several at once).
Every message still goes through `navi send`, so the live viewer and the log stay accurate.
