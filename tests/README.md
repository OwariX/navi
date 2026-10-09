# NAVI tests

End to end, in a real browser and a real pseudo-terminal, against a **fake `claude`** (`tests/fake-claude`) that logs how it was
launched and plays a tiny moderator (and, for the Council Generator, answers its prompts with canned JSON). Nothing costs tokens,
nothing touches your `~/.config/navi`, and every run picks its own free ports, so several runs can't collide.

```bash
tests/run.sh                # everything (the first run installs Playwright + Chromium into tests/e2e/node_modules)
tests/run.sh ui demo        # some suites (tests/run.sh lists them all): ui · engines · enginesui · install · headless · tui ...
```

Every engine runs against a fake here: `fake-claude`, `fake-codex` and `fake-gemini` (on the PATH in place of the real
programs, printing their real output formats) and `fake_ollama.py`, with a CODEX_HOME, Gemini home and OLLAMA_HOST of
the run's own. The fake Codex sandboxes its commands the way the real one does (no network in there), so a member that
couldn't reach its model fails here too. The install suite installs and uninstalls NAVI in a home folder of its own;
nothing touches yours.

The test project is a real git repo (`main` plus `feature/demo`, one uncommitted change) with a saved session, a second open
session on pace Quick, and two project files that session built (a page, and a script that must never be run by a click).

| Suite | What it proves |
|---|---|
| `ui` | Home: the folder, branch and git state in plain words; switching and creating a branch; switching folders and back. The launch sheet (model, effort, pace, data, "new branch for this session"); continuing keeps the session's pace. Panels open and close with Esc. Agents and councils (read-only built-ins, the roster, add a new agent inline). A session page: the folder and branch in the top bar, the branch the session works on, the stepper, a finished session ending on Done, feed filters, Files (open the real project file, show it in Finder, a script only ever shown), Markdown deliverables, the palette, rename, the switchboard. |
| `councilgen` | "New" offers start from scratch or generate; describe → draft → review (rewrite, add, remove, seats, models) → create writes the new agents and the council, and never touches a session's log. |
| `demo` | The scripted demo runs to CONSENSUS; the question is answered in your own words (empty answers refused); your line reaches the council, the ADR and the hello page, as text (never HTML); CONSENSUS lists what was built. |
| `headless` | A launch with pace Quick and Sonnet passes `--effort low --model sonnet`; "new branch for this session" makes `navi/<name>` and the feed says so; the live trace, slash commands and history; CONSENSUS shows the time, turns and cost; the idle moderator leaves after the end; writing afterwards wakes NAVI on the same conversation (`--resume`); the council shows offline and NAVI answers in the feed (chat mode). |
| `replay` | Replay speed and pause. |
| `tour` | The first-session tour shows once, highlights the feed and the console, in sentence case. |
| `wizard` | First-run setup is one page, starts with grain and edge darkness off and the moderator in the background, and lands on home. |
| `terminal` | `navi` → START → the web menu sees the waiting terminal → the launch sheet starts the council in that terminal (no `-p`). |
| `engines` | Every engine's command lines, models, environment and output parsing; `navi engine list/use/test`, `--engine`; the guard in Codex's dialect (no "ask" there) and shell writes outside the project; member runs (`navi run`, `--bg`, stopped with their session) and from inside Codex's sandbox (started outside it, or refused at once when nobody can); a council through the server on Local, Codex (Ask me, in the background, Allow all; its own thread resumed after the end) and Gemini (its guard as a BeforeTool hook in a home of NAVI's); a moderator that says it's done and stops: NAVI asks you; Settings' engine test; the generators on a local model; `navi down` stopping members too; the benchmark runner (bench/run.py) on the fake Claude. |
| `enginesui` | Settings > Engine (models per tier from Ollama, Test it, save), the launch sheet's Engine row (models, effort and permissions follow it), `?engine=`, a council on Local with its header, the model pickers in the agent and council editors. |
| `enginewizard` | `navi engine` in a real terminal: pick with the arrows, the checks and suggested models, keep or change them per tier, the free test, Cancel changes nothing. |
| `phone` | On an iPhone-sized screen: nothing scrolls sideways; Agents and Councils show their list first and an item opens with a way back; a session's top bar keeps NAVI, New session, ⌘K and the feed on screen. |
| `updates` | Home's update line, with the server's answers faked in the browser: a newer release in green with Update; Updating…, then ✔ Update installed with Restart; Restart brings the page back; a refusal while a council runs; nothing when up to date; Settings' Update NAVI automatically. (`update` does the real thing against a throwaway origin: Update and Restart in the interface, the terminal menu, auto updates.) |
| `writing` | Room to write, and attachments in plain sight: home's box grows and has a big writing view; a text file attaches on home; the start window shows the whole task; an open question gets a roomy answer box with Attach; the session's task opens in full from the header. |
| `install` | `install.sh` and `navi uninstall` in a home of their own: the command, the skill links, the permission rules (only NAVI's removed, a backup kept), `--purge`, idempotent re-runs. The Claude Code plugin (manifest, marketplace, no personas as subagents) and its guard hook (only while a session is open). On Windows, the message pointing to WSL. |
| `tui` | `navi tui`: a long task wraps over several lines, Alt+Enter adds one, a file dragged onto the terminal becomes an attachment that reaches the council, Ctrl+V pastes the clipboard's image, FILES removes one, FOLDER refuses a folder that isn't there, BRANCH switches for real, Ctrl+O gives the task the screen; the start form launches a background moderator even when the setting says terminal; the proposal reaches the graph and the feed; a question answered with one key; a typed line reaches `/say`; `q` asks first while the council works; a resize stacks the graph above the feed; CONSENSUS; the terminal is restored. |

Screenshots land in the scratch folder printed at the end. `tests/fixtures/session` is one saved session (the Flappy Bird
council) used as data.
