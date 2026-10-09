# Changelog

NAVI's versions are **MAJOR.MINOR.BUILD**. BUILD has three digits and counts every release (0.9.001, 0.9.002, ...);
1.0.000 is the public launch. `navi update` brings your copy to the newest release, `navi --version` says which you have.

## 0.9.020 (2026-10-09)

- **`navi update` follows NAVI's repository if it ever starts over.** When the history on GitHub is reset (the
  repository made again from a fresh commit), a copy sitting on a release moves to the new one instead of refusing.
  A copy with changes or commits of its own is never touched: it says to update by hand, as before.

## 0.9.019 (2026-10-09)

- **"A new version is out" shows up when it should.** NAVI asked GitHub at most once a day and showed that answer
  everywhere, so a release could go unnoticed for a day. Now it asks every hour (one quick `git ls-remote`), the
  terminal menu asks while its intro plays (the notice is there the first time you open it), and the interface asks
  in the background when its answer is over an hour old.

## 0.9.018 (2026-10-09)

- **Nothing of NAVI's in your projects any more.** A project's sessions, policy, agents and server state live in
  `~/.navi/projects/<folder>-<id>/`, never in a `.navi/` folder inside the project, so there's nothing to commit or
  push by mistake. An existing `.navi/` moves out by itself the first time NAVI runs there while nothing of NAVI's is
  using it. `navi doctor` says where a project's data is; `navi uninstall --purge` removes it too.
- **NAVI's guard stays out of your own Claude Code.** Claude Code loads NAVI as a plugin, and its guard used to check
  every conversation in a folder with an open NAVI session, so your own `/init` or review got WARDEN's questions. Now
  it guards only the conversation that runs a council (it has run `navi` itself). Everything else is left alone.
- The plugin's guard read the wrong input in projects found through `~/.navi/roots` (a shell detail): fixed, and tested.
- **WARDEN says it plainly.** "NAVI's guard (WARDEN): this touches csv/resources.csv, and *.csv files can hold secrets
  or personal data. OK it only if you're sure it holds none." Before, it repeated the whole command and the reason came last.
- NAVI never moves a project's old `.navi/` while a TUI, a server or a council still uses it.

## 0.9.017 (2026-10-08)

- **🎃 Spooky season.** A little jack-o'-lantern sits by the logo on the home screen (click it), on the TUI's start
  screen, and in the terminal menu. October only: it's gone by itself on November 1st.

## 0.9.016 (2026-10-08)

- **Permission cards speak plainly.** A card leads with what the agent wants to do and why, in its own words, then
  what the command does, worked out by NAVI from the command itself ("It runs: search files, read a commit, look up
  Azure (ad group)"). The raw command is behind **Show the command** (in the TUI: `c`). Agents are told to write each
  command's description for you: what, and why.
- **What you allow, you allow everywhere.** When you let a kind of file through ("For this session" on WARDEN's card,
  or *yes, read the logs*), agents no longer keep asking about it. Their own check (`navi gate`) and the brief know it
  too, and a pattern ruling (`navi rule --target '*.log' --decision allow`) covers the whole session. In Auto,
  `navi gate` says go ahead on grey areas: nobody is there to ask.

## 0.9.015 (2026-10-08)

- **Auto never waits for you.** Pick Auto and walk away.
  - Claude Code's own auto mode decides where it can. It can't on every account or model (it needs Opus or Sonnet 4.6
    or later, Haiku 5.5 or a Fable model, and a Team or Enterprise admin can turn it off), and then it quietly asks
    about everything. NAVI now decides those at once, in plain code, without a card: the work runs (reading,
    building, testing, editing the project, read-only cloud queries). Pushes, deploys, cloud and cluster changes,
    uploads, `sudo`, `curl … | sh`, folder deletes and writes outside the project are refused; the council is told
    to do it another way, and the feed shows what was refused.
  - When Claude Code isn't really in auto mode, the session says so once, and why.
- **No questions about NAVI's own files.** What the council writes in a session (a file, a script, a redirect),
  it may read, change and run without a card or a WARDEN question, even an example `*.tfvars` or `report.csv`.
  `.env`, keys and state files are never its own.

## 0.9.014 (2026-10-08)

- **Only the engines you use show up.** The engine wizard (`navi engine`) starts with *Which AI programs do you use?*:
  space ticks, ⏎ done, and it asks which runs NAVI by default only when you ticked several. Everywhere else (the
  start window, Settings, the council editor, the TUI) offers just those, so nothing you didn't choose looks like it
  came with NAVI.
  - More later: `navi engine add` (the same ticks, or `add <name>`), `navi engine remove <name>`, or Settings >
    Engine > *Add an engine*.
  - After this update, NAVI offers your default engine only. Add the others you use once.

## 0.9.013 (2026-10-08)

- **Auto works like Claude Code's auto mode: leave it and let it cook.**
  - WARDEN leaves its grey areas (`*.tfvars`, `*.csv`, folders outside the project) to the engine's own judge. It
    still blocks keys, `.env` and state files, and a Confidential session still asks.
  - A card the engine itself raises (say a `cd` out of the project) waits 90 seconds. If nobody answers, the council
    goes on another way instead of stalling for 9 minutes.
  - Agents name folders instead of `cd`-ing into them (`git -C`, absolute paths), which Claude Code would stop to ask about.
- **WARDEN, fewer false alarms.**
  - A message that mentions a file no longer counts as reading it: `navi send --body "...variables.tfvars..."`, a
    commit message, an echo. A `;` or `|` inside quotes no longer splits a command, and `$(...)` is still checked.
  - In Ask me, its cards have **For this session**, which lets that pattern (`*.tfvars`) through until the session ends.
- **Long questions read as written.** `navi ask` keeps its line breaks, as `navi send` does. In the TUI, the box grows
  wider, shows lists and headings, and scrolls (PgUp/PgDn). In the browser, a question is formatted text in a wider,
  scrolling window.
- **Edit an agent without starting over.** Once an agent has instructions, the box says *Change something*. NAVI
  changes only that and shows the change line by line, with **Undo**. *Write it again from scratch* is still there.
- **Sources of truth: anything.** One file (a single Obsidian note, a PDF), a folder, an MCP server, a skill, a
  website, or something else in your words. A path that isn't on this machine is kept as you wrote it, after a warning.
  WARDEN lets agents read exactly the named file, not the folder around it.
- **Auto models.** A seat can be on *Auto*: the moderator picks its model for each assignment (strong for hard design
  and security, fast for summaries). The start window has *NAVI picks per task* for every agent at once.
- **TUI:**
  - Typing `@` or `/` in the console shows the agents or commands that fit, as you type (↑↓, tab).
  - The start screen has **END ALL SESSIONS** and **QUIT**.

## 0.9.012 (2026-10-08)

- **The tour and the guides stay seen.** They used to come back after an update. A browser keeps its memory per
  address, and a NAVI restarted on another port looked like a new site. NAVI now keeps what you've seen in your
  settings; Settings > Guides still shows them all again.
- **The TUI's start form, rearranged:** what (TASK, FILES), where (FOLDER, BRANCH) and how (council, pace, engine and the
  rest), with a gap between each group.
  - **FILES** shows what goes with the task.
  - **Ctrl+V pastes an image** from the clipboard, or files copied in Finder or your file manager. A terminal can't
    paste an image by itself, so NAVI asks the system for it, as Claude Code does. A Cmd+V that arrives empty does the
    same. On Linux it needs wl-clipboard or xclip, and says so.
  - Ctrl+V works in answers and the console too.
  - **FOLDER** switches to another project folder: your recent ones, or type a path. The TUI starts again there.
  - **BRANCH** switches branch, or makes a new one. Not while a council works there.
- **The terminal menu has END SESSIONS:** this one, or all open in this folder. Each one's NAVI stops; nothing is
  deleted, and any can be resumed.

## 0.9.011 (2026-10-08)

- **Room to write a real task.**
  - In `navi tui`, TASK is no longer one line: it wraps, grows to six lines, and Alt+Enter (or Shift+Enter, Ctrl+J)
    starts a new line. Ctrl+O gives it most of the screen, and Ctrl+G opens it in your own editor.
  - Answers to NAVI's questions get the same multi-line box in the TUI.
  - In the browser, home's box grows to half the screen, and ⤢ opens a big writing view. An open question ("what
    should the council work on?") gets a roomy answer box.
  - The start window shows the whole task (it used to stop at 220 characters), and clicking the task in a session's
    header opens it in full.
- **Files, images and links, in plain sight.**
  - In the TUI, drag a file onto the terminal to attach it: in the start form, an answer or the console. It uploads
    at once and shows as a chip; Backspace on an empty field removes the last one.
  - In the browser, every place you write says files, images and links are welcome, and the question box has
    *Attach files or images*.
- **Fix:** attaching a text file before a session existed (home's box) failed on the server. Images worked, which
  hid it.

## 0.9.010 (2026-10-08)

- **Generated agents meet NAVI's own standard.** The checker's safety rule now understands "never" and "don't":
  "never skip the gate" and "don't read .env" are rules to keep, not bypasses. A generated read-only agent was marked
  "bypasses WARDEN or the gate" for writing exactly that. A draft that still scores below 100 gets one round to fix
  what the checker found (Write it for me and the council generator).
- **README:** a lighter top (the terminal GIF smaller, under the browser one), links to each section, a cleaner quick
  start, and "Does it work?" with the benchmark results.

## 0.9.009 (2026-10-08)

- **`navi down` stops the members too.** It stopped a session's moderator but left the members it had started with
  `navi run` running. A benchmark found one still holding a local model three hours later, so every run after it
  waited on Ollama. Stopping from the interface (STOP, End) already stopped them; now `navi down` does as well.
- **Benchmarks:** Local's results, and a note on which engines aren't measured yet and why.
- **NAVI says when it can be updated.**
  - Home and the terminal menu say it in green when a new release is out. **Update** installs it, then home shows
    "✔ Update installed · Restart to update" with **Restart**. `navi tui` shows it too.
  - You can let NAVI update itself: the installer asks, Settings has *Update NAVI automatically*, or run
    `navi update --auto on`. It never updates while a council runs anywhere on the machine, nor over your own changes.
  - A terminal menu that updates itself starts again on the new version and says so.
- **Councils say what they start with.** Councils > *When it starts* holds the engine, model, effort, permissions,
  pace and data. The start window starts from them and says "the council's default", and you can still change each
  one. A launch that names none of them (the terminal menu, the TUI, the CLI) gets the council's.
- **Auto is the default permission mode for new installs.** On an engine without an auto mode (Local, Gemini), NAVI
  asks you instead. Settings you already saved stay as they are.

## 0.9.008 (2026-10-07)

- **NAVI is MIT licensed.** The repo has a LICENSE, CONTRIBUTING.md (setup, tests, how to add an engine), SECURITY.md
  (how to report a way past the guard privately) and issue templates.
- **A Claude Code plugin.** `/plugin marketplace add OwariX/navi`, then `/plugin install navi@navi`. It brings the skill,
  `navi` in Claude Code's shell, and NAVI's guard as a hook. The hook acts only in a folder with an open NAVI session;
  everywhere else it does nothing, without even starting Python. NAVI's personas don't load as Claude Code subagents.
  If you installed with `install.sh`, the hook now comes with your linked skill too.
- **The hard guard on Gemini CLI too**, as its `BeforeTool` hook. Reading `.env`, `cat .env` and the rest of NAVI's
  hard denies are blocked there as on Claude Code and Codex. Gemini takes hooks only from its settings files, so each
  run gets a Gemini home of NAVI's own that links yours (sign-in, sessions) with the hook added; your files stay as
  they are. Where NAVI would ask you, Gemini (like Codex) can't stop to ask, so it's refused with how to ask in NAVI.
- **When a moderator says it's done but stops without closing the session**, NAVI asks you "Is the work done?"
  instead of restarting it up to three times. Smaller local models did this often. *Yes* ends the session with what
  it said it did; *No, keep going* wakes it on the same conversation. On engines without registered members, the
  brief also says plainly that `navi` is a shell command (a local model kept calling a tool named `navi_status`).
- **Windows:** NAVI runs inside WSL, with a step-by-step guide in docs/WINDOWS.md (local models included). Started
  natively on Windows, it says so and points there, instead of failing later.
- **Benchmarks:** `bench/run.py` runs real councils on small tasks a script can check (a page, a failing test, a rate
  limiter, an SQL injection), on any engine; docs/BENCHMARKS.md has the results.
- **NAVI on a phone.** Agents and Councils show their list first, and an item opens with a way back (on a narrow
  screen the list used to be hidden, with no way to reach the other agents). In a session, the top bar keeps NAVI,
  New session, ⌘K and the feed on screen. The graph leaves NAVI's status to the pill, so it doesn't run into the agents.
- **Tests run on GitHub Actions** on every push: the whole suite on Linux, and the Python suites on Python 3.9.
- **Python 3.9 or newer**, now tested: the whole suite passes on the Python 3.9 that ships with macOS.
- **The launch sheet says what each pace does now.** Standard is "Build, then the reviewers check the result", and
  Thorough is "Proposal, challenges, ADR and threat model". The old text described the debate-first workflow. The
  Agents line groups agents by model: "Adversary and Ledger on Balanced · gpt-oss:20b".
- **README:** shorter "Why NAVI", the engine picker in a screenshot, the Knights by tier, the guard on Codex too, and
  the newer commands (`navi engine`, `navi run`, `navi uninstall`).

## 0.9.007 (2026-10-07)

- **NAVI isn't only for Claude anymore.** A council runs on an *engine*:
  - **Claude:** Claude Code.
  - **Local:** your own models through Ollama, run by Claude Code. Free, and nothing leaves your machine.
  - **Codex:** OpenAI's Codex CLI.
  - **Local via Codex:** your own models, run by Codex.
  - **Gemini:** Google's Gemini CLI.
- **Tiers, not model names.** Councils name a tier per seat (strong for the lead, balanced for reviewers, fast for the
  recorder), and each engine maps the tiers to its models. The Knights run on any engine; Claude's names still work.
- **Picking one:**
  - `install.sh` ends with `navi engine`, a wizard that shows what's installed and ready, the models per tier, and a
    quick test.
  - `navi engine use <name>` switches, and `navi --engine <name>` runs once on another engine.
  - In the browser: **Settings > Engine** (with *Test it*), and an Engine row in the launch sheet.
- **On Codex and Gemini, members run one by one.** `navi run <agent>` runs each member with its own instructions and
  model (`--bg` and `navi runs --wait` for several at once). Codex runs resume their own thread after the end: NAVI
  keeps the id Codex gives its thread.
- **Members work inside Codex's sandbox.** In *Ask me* and *Auto*, Codex runs the moderator's commands in a sandbox
  with no network, and macOS can't put a second sandbox inside it. A member started from in there couldn't reach its
  model, which a real test caught. Now the NAVI that started the moderator starts the member outside the sandbox, with
  Codex's own sandbox around the member's commands. `navi run` waits for it as before.
- **The guard runs on Codex too, as a hook.** Codex can't pause to ask, so where NAVI would ask you, it refuses and
  tells the agent to ask you in NAVI.
- **What's available, honestly.** The launch sheet and Settings say what each engine can do: registered members, the
  hard guard, permission cards, auto mode, effort.
- **Local models:**
  - **64k window:** NAVI runs your local models with a 64k context window. It makes a copy of each tier model with that
    window (same weights, no download). In a real test, qwen3-coder:30b at Ollama's usual 32k lost its instructions
    and wrote the page into its answer.
  - **Settings > Engine > Window** picks 32k, 64k or 128k.
  - Cost shows as $0, and Claude Code's telemetry is off.
- **The guard also checks where shell commands write.** A redirect, `tee`, `cp`/`mv`/`ln` or `touch` that would land
  outside the project now asks first, as a file write already did, and it follows `cd`. A real test caught a local
  model writing a page into the home folder with `cd ~ && echo ... > hello.html`.
- **Stopping a session stops everything it started.** That includes the members `navi run` started, along with their
  own programs. NAVI's instructions and every member's now state the project folder.
- **`navi uninstall`** (or `install.sh --uninstall`) removes the command, the skill links and the permission rules
  `install.sh` added. Your settings stay unless you add `--purge`. Sessions in your projects are never touched.
- `navi doctor` checks the engine you picked. The skill is also linked into `~/.agents/skills`, where Codex and
  Gemini CLI look.

## 0.9.006 (2026-10-07)

- **End sessions is always on the home screen.** It used to disappear when the folder had no sessions left, which made
  it look gone. With nothing to end, its window now says so and how to end sessions later (here, or `navi end`).

## 0.9.005 (2026-10-07)

- **Add a source of truth in your own words:** "my Obsidian vault", "the PDFs in ~/Documents/specs",
  "learn.microsoft.com for Azure". A model (haiku, every tool off, secrets taken out first) fills in the details, or
  a plain reader does without `claude`. NAVI checks each one before you add it: the folder exists (and what's in it,
  "an Obsidian vault with 214 notes"), the MCP server is in your Claude Code, the address is a website. It offers the
  Obsidian vaults it finds when you don't say where yours is, and shows the exact line each agent is told.
- **Websites** are a kind of source now, and agents may fetch from the ones you name without asking each time.
  Every source can carry a short note ("the team's runbooks") that goes into the agents' instructions.
- **Built-in agents can have sources too**, kept for them in your config, in every project.
- **Examples:** a new window, from Agents, Councils, New + and the generator, with ideas to start from. Councils:
  a platform team (GitHub expert, wiki keeper on your vault, red and blue team, Azure docs checker), a small and quick
  one, a PR and architecture review, Terraform on Azure. Ten agent ideas, each with where it checks its facts.
  **Use this idea** fills in the generator or a new agent, and nothing is saved until you say so.
- A page left open keeps working when NAVI's server restarts (after `navi update` or `navi stop`): it picks up the
  server's new key by itself instead of failing every click until you reload.

## 0.9.004 (2026-10-07)

- **Guides on every screen:** the first time you open home, a session, Councils, Agents, Settings, the launch sheet,
  the Themes window or the Council Generator, a short walkthrough shows you around. The **?** on a screen replays it,
  and Settings > Guides shows them all again or replays the welcome.
- **Recommended:** The Knights, generating a council, and letting NAVI write an agent are marked as the recommended
  way, with the research they come from readable right in NAVI.
- **Sound in three parts:** alerts, clicks and ambience (the CRT hum and static) each have their own switch.
- **Remove sessions for good** (the ended ones, or all), from the same window as End sessions; files in your project
  are never touched.
- `navi --end-all` now also closes the open sessions, so nothing is left waiting; `navi stop` stops everything and
  keeps them open (use it after `navi update`).
- In the app, WARDEN is described as it works: a guard in plain code blocks keys and .env files before anything is
  read, and the WARDEN agent rules on grey areas from file names alone.

## 0.9.003 (2026-10-07)

- `navi end` ends the open session in this folder (its NAVI stops if it runs); `navi end --all` ends every open one
  there; `navi --end` works too. A moderator still closes its own session with `navi end --summary "..."`.
- A typo like `navi --stop` gets a short hint ("Did you mean `navi end` or `navi --end-all`?") instead of the full
  usage dump.

## 0.9.002 (2026-10-07)

- `navi tui --demo`: if the TUI is killed or its terminal closes (instead of quitting with q), the demo's server now
  ends by itself and removes its throwaway folder.

## 0.9.001 (2026-10-07)

The first numbered release.

- **Permissions, your call:** pick *Ask me*, *Auto*, *Allow all* or *Skip permissions* when a council starts. In the
  background, anything not allowed becomes a card in NAVI (Allow once, For this session, Deny) instead of failing.
- **The models and effort you pick are the ones that run:** every council member is registered with Claude Code with
  its own model and your effort; `/effort` and `/model` switch NAVI at its next checkpoint.
- **Tokens per model** in every session, as Claude Code counts them (subagents included).
- **Sources of truth:** folders (an Obsidian vault, your docs), MCP servers and skills, for the project or one agent.
- **After CONSENSUS, back to chat:** NAVI keeps working with you as one agent; the council rests until you ask.
- **End sessions** from home (this one or all), `navi --end-all` from a terminal.
- **The TUI:** `navi tui`, and `navi tui --demo` for the demo in the terminal.
- **Themes:** a Themes window; The Wired, CRT, Liquid glass, Minimal, Minimal dark, MAGI, Journey's End (Frieren in
  mellow white and her green), Devil Hunter; your own skins with `navi theme new`.
- **WARDEN:** a hard guard in plain code keeps keys and `.env` files out of every agent's context.
- `navi update` and version numbers.
