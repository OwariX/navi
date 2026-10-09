# Security

NAVI points AI agents at real repositories, so its guard matters. If you find a way around it, please tell us
privately first.

## What to report

- An agent reads, or gets into its context, a file the guard denies (`.env`, keys, state files, your off-limits paths).
- A way to skip or switch off the hard guard (the `PreToolUse` hook) in a mode that should have it.
- Something that runs without the permission mode chosen at launch (*Ask me*, *Auto*, *Allow all*).
- A secret or personal data that passes the outgoing filter into messages, the log, the transcript or the screen.
- Another website or process talking to NAVI's local server (it checks a per-run token, Host and Origin).

Known limits, in the README: *Skip permissions* turns every check off on purpose, permission cards exist only on
Claude Code (elsewhere what isn't allowed is refused), and the outgoing filter matches patterns, best effort.

## How to report

Use **Report a vulnerability** on the repository's **Security** tab (GitHub's private vulnerability reporting). Say
which engine and permission mode, the NAVI version (`navi --version`) and the steps. We aim to answer within a week
and to fix confirmed issues in the next release, with credit if you'd like it.

Please don't open a public issue for these, and don't test against repositories or machines that aren't yours.

## Supported versions

The newest release. `navi update` gets it.
