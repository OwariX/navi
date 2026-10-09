# Engines: what NAVI runs on

NAVI doesn't need any particular AI. A council runs on an **engine**: an agent program (the thing that reads files,
runs commands and edits code) plus the models behind it. You pick one when you install NAVI, and you can switch at
any time.

| Engine | Runs on | Members | Hard guard | Permission cards | Cost shown |
|---|---|---|---|---|---|
| **Claude** | Claude Code, your Anthropic account | registered, each with its model | yes | yes | yes |
| **Local (Ollama)** | Claude Code on your own models through Ollama | registered, each with its model | yes | yes | free, $0 |
| **Codex** | OpenAI's Codex CLI, your ChatGPT or OpenAI account | one by one (`navi run`), each with its model | yes | no | tokens only |
| **Local (Ollama) via Codex** | Codex on your own models through Ollama | one by one (`navi run`) | yes | no | free |
| **Gemini** | Google's Gemini CLI, your Google account | one by one (`navi run`) | yes | no | tokens only |

- **Members.** A council's members are its other agents (the reviewers, the recorder, the guard).
  - On Claude Code they are registered as subagents, each with its own model and the session's effort.
  - Elsewhere NAVI runs each member itself with `navi run <agent>`: its instructions, its model, its last message
    back to the moderator.
- **Hard guard.** NAVI's guard is plain code, not an AI. It runs before every tool call and blocks keys, `.env` and
  state files before anything is read.
  - Claude Code, Codex and Gemini CLI all run it as a hook.
  - Codex and headless Gemini can't pause to ask you, so where NAVI would ask, it denies and tells the agent to ask you
    through NAVI first.
- **Permission cards.** When something isn't allowed, a card in NAVI can ask you. Only Claude Code can stop and wait
  for that answer. On the others, what isn't allowed is refused.

## Tiers: how councils pick models

A council doesn't name models. It names a **tier** for each seat, and each engine maps the tiers to its own models:

| Tier | Seat | Claude | Local (example) | Codex (example) |
|---|---|---|---|---|
| strong | the lead: designs and builds | Opus | qwen3-coder:30b | gpt-6.1-sol |
| balanced | reviewers | Sonnet | qwen3-coder:30b | gpt-6-sol |
| fast | the recorder, light checks | Haiku | qwen2.5:7b | gpt-6-luna |

So The Knights, and every council you make, run on whichever engine you pick. Claude's names keep working everywhere:
opus and fable count as strong, sonnet as balanced, haiku as fast. A seat can also name one specific model.

## Choosing and switching

```bash
navi engine                       # the wizard: what's installed and ready, the models per tier, a quick test
navi engine list                  # every engine, ready or what it needs, your default marked
navi engine use local             # make Local your default (--strong / --balanced / --fast to pick the models)
navi engine test [name]           # one short question: does it answer, how fast
navi --engine codex               # just this time: plain `navi` (or `navi --engine codex tui`) on another engine
./install.sh --engine local       # pick it while installing, no questions asked
```

In the browser, **Settings > Engine** does the same, and its **Test it** button sends one short question. The
launch sheet also has an Engine row: a different engine picked there applies to that council only. A session keeps
its engine when you continue it later.

## Local models (Ollama)

Free and private: with *Local* nothing leaves your machine. NAVI also turns off Claude Code's telemetry and update
checks for these runs.

1. Install [Ollama](https://ollama.com) and start it (the app, or `ollama serve`).
2. Pull a model that can use tools.
   - `qwen3-coder:30b` (about 19 GB, needs 32 GB of RAM) runs a council well.
   - On less memory, try `qwen3:8b` (5 GB).
   - `navi engine` lists what you have and marks the models that can use tools.
3. Run `navi engine` and pick **Local**.

**The context window.** Claude Code's instructions alone are about 14,000 tokens, and Ollama recommends at least 64k.
Ollama often loads a model with 4-32k, and past that it silently drops the start of the prompt, which is where the
instructions live. In a real test on qwen3-coder:30b at 32k, the model wrote the page into its answer instead of using its
tools.

So before a local run, NAVI makes a copy of each tier model with a 64k window, e.g. `qwen3-coder:30b-navi64k`. A copy is
a few KB of settings: same weights, nothing to download. NAVI also tells Claude Code that window, so it compacts in time.
Settings > Engine > Window picks 32k (less memory), 64k or 128k (long councils, more memory). The copies don't show up
as models to pick, and `ollama rm` removes them like any model.

Local models are slower and weaker than the big hosted ones, and the first answer waits while the model loads.

What a real test on this machine showed (qwen3-coder:30b on an Apple M4 Pro, Quick pace, "make a hello page"):
- **The council ran from start to finish in about 14 minutes** (a minute or so on Claude).
  - The lead built the page and posted the evidence.
  - Two reviewers checked it in parallel, each on its tier's model.
  - The recorder wrote the ADR.
  - NAVI asked "done?" and closed the session.
  - It cost $0 and took about 620k tokens, all on this machine.
- **Local via Codex ran the same task in *Ask me*, inside Codex's sandbox.**
  - Two reviewers ran in parallel, started outside the sandbox by NAVI.
  - They flagged a missing charset, the lead fixed it, and both approved.
  - The moderator closed the session itself.
  - About 16 minutes, $0.
- **At Ollama's usual 32k window the model never used its tools.** That's why NAVI runs 64k copies.
- **It follows the protocol loosely.**
  - The first answer takes up to two minutes.
  - It sometimes invents a tool name before using the right `navi` command.
  - It once wrote a file outside the project. The guard now asks first for that.
  - Saying the project folder outright, as NAVI now does, kept it in place.

Use the Quick pace and the *Small and quick* council (Examples) for everyday work. Prefer the strongest coder model your
memory allows. *Local via Codex* is the same with Codex as the program, for when you'd rather not install Claude Code.

## Codex

Sign in with `codex login`. NAVI runs `codex exec --json` and resumes each session's own thread.

- **The guard:** passed to Codex as a hook for that run only. Codex normally runs a hook only once you've trusted it
  in its `/hooks` screen, so NAVI adds `--dangerously-bypass-hook-trust`. NAVI vets its own hook, and the flag holds
  only for that run.
- **Sandbox:**
  - *Ask me* runs in Codex's workspace sandbox: edits inside the project, nothing outside it, and no network.
  - *Allow all* has no sandbox.
  - *Auto* is Codex's own reviewer deciding what runs, in the same sandbox.
- **Members in the sandbox.** A member is a Codex run of its own, and from inside the moderator's sandbox it couldn't
  reach its model (no network there), nor start a sandbox of its own (macOS can't nest them). So when the moderator
  runs `navi run`, the NAVI that started the moderator starts the member outside the sandbox, with Codex's sandbox
  around the member's own commands. `navi run` waits for it as usual. A Codex you start by hand, outside NAVI, has
  nobody outside to do that: there, `navi run` says so at once.
- **Other providers** (xAI's Grok, OpenRouter, your own server): Codex can use any provider that speaks the OpenAI
  *Responses* API. Add it in `~/.codex/config.toml`, then use the Codex engine with that provider's model names:
  ```toml
  model_provider = "xai"
  model = "grok-code-fast-1"
  [model_providers.xai]
  name = "xAI"
  base_url = "https://api.x.ai/v1"
  env_key = "XAI_API_KEY"
  wire_api = "responses"
  ```
  This route is untested here; whether a given provider's Responses API is complete enough is up to that provider.

## Gemini

Set `GEMINI_API_KEY` (a key from Google AI Studio), or run `gemini` once and sign in. Google stopped supporting this
client's free personal login ("Gemini Code Assist for individuals") in favour of its Antigravity products. If
`navi engine test gemini` says so, an API key still works. NAVI runs `gemini -p -o stream-json` and resumes each session
by its id.

- *Ask me* allows edits and only NAVI's own commands plus the usual read-only checks in the shell. Everything else is
  refused.
- *Allow all* is Gemini's yolo mode.
- **The guard** is a `BeforeTool` hook. Gemini takes hooks only from its settings files, so each run gets a Gemini home
  of NAVI's own (`hosts/gemini-home` in the project's NAVI data, `~/.navi/projects/…`): it links everything in your `~/.gemini` (sign-in, sessions,
  history) and has a copy of your settings with the hook added. Your own files are never changed. A setting you change
  inside a NAVI run in the terminal stays in that copy.

## Adding an engine

Engines live in [`scripts/engines.py`](../scripts/engines.py), one class each. To add one:

1. Subclass `Engine` and set `id`, `name`, `program`, `blurb`, `install_hint`, the tier `defaults`, `efforts` and `can`.
2. Write `moderator()` (the command line that starts NAVI on it, headless or in a terminal, new or resumed) and
   `member()` (one council member, run by `navi run`).
3. Write `ask()`: one question, every tool off. It's used by Write it for me, the council generator and the sources
   reader.
4. Write a `Stream` subclass that reads the program's JSON output. It returns trace lines, the conversation id, tokens
   per model, and a final result shaped like Claude Code's.
5. Add `checks()` for what it needs, then add the class to `ENGINES`.
6. Test it the way the others are tested: a fake program in `tests/` that prints the real output format (see
   `tests/fake-codex`), and checks in `tests/engines_test.py`.
