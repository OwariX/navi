# Contributing to NAVI

Thanks for helping. NAVI is small on purpose: Python's standard library, one HTML file, plain files on disk. Keep it
that way and most of this guide follows.

## Set up

```bash
git clone https://github.com/OwariX/navi && cd navi
./install.sh --no-wizard        # optional: puts `navi` on your PATH and links the skill
python3 scripts/navi.py demo    # or run straight from the folder, no install
```

There is nothing to `pip install`. Python 3.9 or newer, on macOS or Linux (on Windows, in WSL: [docs/WINDOWS.md](docs/WINDOWS.md)).

## Where things are

| Path | What it is |
|---|---|
| `SKILL.md` | The moderator's instructions: the protocol every engine follows |
| `scripts/navi.py` | The `navi` command and the local server |
| `scripts/engines.py` | One class per engine (Claude Code, Ollama, Codex, Gemini): command lines, output, models |
| `scripts/guard.py` | The hard guard: what a hook allows, asks about or denies |
| `scripts/forge.py` | Council and agent generation, persona grading |
| `scripts/tui.py` | `navi tui` |
| `web/index.html` | The whole browser interface, no build step and no external requests |
| `agents/`, `councils/` | The built-in agents and The Knights |
| `docs/` | Engines, themes, the research behind the workflow |

## Tests

```bash
tests/run.sh                 # all 23 suites, about 20 minutes
tests/run.sh engines ui      # some suites; tests/run.sh lists them all
```

The suites drive the real interface in Chrome (Playwright, installed into `tests/e2e/node_modules` on the first run)
and the real terminal UI in a pseudo-terminal. Every engine is a fake (`tests/fake-claude`, `fake-codex`,
`fake-gemini`, `fake_ollama.py`) that prints the real program's output format, so nothing costs tokens and nothing
touches your own settings. You need Node.js and Google Chrome.

Every fix comes with a check that would have caught it. When you change how NAVI talks to an engine, change its fake
too, so the fake keeps behaving like the real program.

## How the code reads

- No dependencies, in Python or in the page. No external fonts, scripts or requests from `web/index.html`.
- Text people read is plain English in sentence case: say what happens and what to do, not how it's built.
- Errors say what went wrong and how to fix it.
- Comments explain why, not what.

## Adding an engine

See [docs/ENGINES.md](docs/ENGINES.md#adding-an-engine): a subclass in `scripts/engines.py`, a fake program in
`tests/`, and checks in `tests/engines_test.py`.

## Pull requests

- One change per pull request, with what it changes for the person using NAVI and how you tested it.
- `tests/run.sh` passes (`.github/workflows/tests.yml` can run it on GitHub too).
- Releases are made by the maintainers: a `CHANGELOG.md` section, then `scripts/release.sh X.Y.ZZZ`.

By contributing you agree that your work is released under the [MIT license](LICENSE).
