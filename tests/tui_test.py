"""Drive `navi tui` in a real pseudo-terminal against the fake Claude: start a council from the start screen, watch the
proposal arrive in the graph and the feed, answer a question, resize, see CONSENSUS, quit, and check that the terminal
was put back the way it was.

usage: python3 -I tui_test.py <project-dir> <scratch-dir>
The fake Claude (tests/fake-claude) must be first on PATH as `claude`, and `navi` must run this checkout: run.sh arranges both.
NAVI_TUI_SNAPSHOTS=<dir> also writes each screen as plain text there.
"""
import codecs
import fcntl
import hashlib
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unicodedata

proj, sp = sys.argv[1:3]
snaps = os.environ.get("NAVI_TUI_SNAPSHOTS", "")


class Vt:
    """Just enough of a terminal to read what the TUI drew: cursor moves, clears, the alternate screen, wide text."""
    TOK = re.compile(r"\x1b\[([0-9;?]*)[ -/]*([@-~])|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[^\[\]]|[\x00-\x1f]|[^\x00-\x1f\x1b]+")
    PARTIAL = re.compile(r"\x1b(\[[0-9;?]*[ -/]*|\][^\x07\x1b]*)?$")

    def __init__(self, cols, rows):
        self.cols, self.rows, self.x, self.y, self.rest, self.alt = cols, rows, 0, 0, "", False
        self.clear()

    def clear(self):
        self.grid = [[" "] * self.cols for _ in range(self.rows)]

    def resize(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.clear()

    def feed(self, data: str):
        data = self.rest + data
        m = self.PARTIAL.search(data)
        self.rest, data = (data[m.start():], data[:m.start()]) if m else ("", data)
        for m in self.TOK.finditer(data):
            tok = m.group(0)
            if m.group(2):
                params, final = m.group(1), m.group(2)
                if final in "Hf":
                    r, _, c = params.partition(";")
                    self.y, self.x = min(self.rows - 1, int(r or 1) - 1), min(self.cols - 1, int(c or 1) - 1)
                elif final == "J" and params in ("2", "3"):
                    self.clear()
                elif final == "K":
                    self.grid[self.y][self.x:] = [" "] * (self.cols - self.x)
                elif final in "hl" and params == "?1049":
                    self.alt = final == "h"
                    self.clear()
            elif tok == "\r":
                self.x = 0
            elif tok == "\n":
                self.y = min(self.rows - 1, self.y + 1)
            elif tok[0] >= " " and tok[0] != "\x1b":
                for ch in tok:
                    w = 0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in "WF" else 1
                    if w and self.x < self.cols:
                        self.grid[self.y][self.x] = ch
                        if w == 2 and self.x + 1 < self.cols:
                            self.grid[self.y][self.x + 1] = ""
                    self.x = min(self.cols - 1, self.x + w) if self.x + w < self.cols else self.cols   # no autowrap

    def text(self) -> str:
        return "\n".join("".join(r).rstrip() for r in self.grid)


CLIP = os.path.join(sp, "clip.png")             # stands in for an image on the clipboard (^V)
open(CLIP, "wb").write(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002"
                                     "00000100e221bc330000000049454e44ae426082"))
env = {**os.environ, "NAVI_CLIPBOARD_FILE": CLIP, "NAVI_CONFIG": f"{sp}/home/config.json", "NAVI_LIBRARY": f"{sp}/home/agents",
       "NAVI_COUNCILS": f"{sp}/home/councils", "NAVI_NO_INTRO": "1", "BROWSER": "true", "FAKE_LOG": f"{sp}/ufake.log",
       "FAKE_SLEEP": "40", "TERM": "xterm-256color", "COLORTERM": "truecolor"}
for k in ("NAVI_DIR", "NAVI_SESSION", "NAVI_HOST_ID"):
    env.pop(k, None)
cols, rows = 120, 36
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
before = termios.tcgetattr(slave)
# a shell leads the session, like in a real terminal; after the TUI it prints the tty flags, as the next command would see them
probe = f'"{sys.executable}" -I -c "import termios; a = termios.tcgetattr(0); print(\'TTYFLAGS\', a[0], a[3])"'
p = subprocess.Popen(["sh", "-c", f"navi tui; code=$?; {probe}; exit $code"], cwd=proj, env=env,
                     stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
os.close(slave)
vt, raw, utf8 = Vt(cols, rows), b"", codecs.getincrementaldecoder("utf-8")("replace")
fails = []


def pump(secs):
    global raw
    end = time.time() + secs
    while time.time() < end:
        if select.select([master], [], [], 0.05)[0]:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                return
            raw += chunk
            vt.feed(utf8.decode(chunk))


def wait_for(pred, secs, what):
    end = time.time() + secs
    while time.time() < end:
        pump(0.2)
        if pred(vt.text()):
            return True
    fails.append(what)
    print(f"--- TIMEOUT waiting for: {what}\n{vt.text()}")
    return False


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        fails.append(what)


def snap(name):
    print(f"--- screen: {name} ({vt.cols}x{vt.rows})\n{vt.text()}\n--- end of screen")
    if snaps:      # the text, and the raw stream so far (replay it in any terminal to see the colours)
        os.makedirs(snaps, exist_ok=True)
        with open(os.path.join(snaps, f"{name}.txt"), "w", encoding="utf-8") as f:
            f.write(vt.text() + "\n")
        with open(os.path.join(snaps, f"{name}.ans"), "wb") as f:
            f.write(raw)


def key(b, settle=0.4):
    os.write(master, b)
    pump(settle)


def data_dir(root):
    """Where NAVI keeps a project's data (guard.data_dir): outside the project, under NAVI_HOME."""
    root = os.path.realpath(root)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(root) or "root").strip("-.")[:40] or "project"
    return os.path.join(os.environ["NAVI_HOME"], "projects", f"{name}-{hashlib.sha1(root.encode()).hexdigest()[:8]}")


NAVID = data_dir(proj)


def sid():
    return open(f"{NAVID}/current").read().strip()


def navi(*args):
    e = {**env, "NAVI_DIR": NAVID, "NAVI_SESSION": sid()}
    return subprocess.run(["navi", *args], env=e, capture_output=True, text=True, timeout=30)


try:
    # 1. the start screen: logo, folder, the form
    wait_for(lambda s: "START THE COUNCIL" in s and "The Knights" in s, 25, "the start screen with the council form")
    check("TASK" in vt.text() and "PACE" in vt.text() and "uproj" in vt.text(), "the form shows task, pace and the project folder")
    check("PERMISSIONS" in vt.text() and "ask me" in vt.text(), "the form shows the permission mode (Ask me by default)")
    # 1b. a long task: it wraps over several lines, alt+enter adds a line, a dropped file becomes an attachment
    longer = ("tui e2e: a longer task that goes on and on about the page, its sections, its tone and what done looks like, "
              "so it can't fit on one line of the form")
    key(longer.encode(), 0.6)
    rows = [r for r in vt.text().splitlines() if "goes on and on" in r or "what done looks like" in r or "fit on one line" in r]
    check(len(rows) >= 2, "a long task wraps over several lines of the form (it used to be one line)")
    key(b"\x1b\r", 0.2)                          # alt+enter
    key(b"second paragraph", 0.4)
    check("second paragraph" in vt.text() and "alt+enter" not in vt.text(), "alt+enter starts a new line in the task")
    check("FILES" in vt.text() and "^V pastes an image or a copied file" in vt.text() and "drag files onto this window" in vt.text(),
          "a FILES row says how: ^V pastes an image, or drag files onto the window")
    note = os.path.join(sp, "tui-note.txt")
    open(note, "w").write("a note for the council\n")
    key(b"\x1b[200~" + note.encode() + b"\x1b[201~", 1.5)     # a file dragged onto the terminal: its path, pasted
    wait_for(lambda s: "▤ tui-note.txt" in s, 10, "the dropped file as an attachment chip")
    check(any(f.endswith("tui-note.txt") for f in os.listdir(f"{NAVID}/uploads")) if os.path.isdir(f"{NAVID}/uploads") else False,
          "...uploaded to NAVI's own folder for the project (not into the project)")
    key(b"\x16", 1.0)                             # ctrl+v: the clipboard's image
    wait_for(lambda s: "▣ clip.png" in s, 10, "ctrl+v attaches the clipboard's image (a terminal can't paste one itself)")
    key(b"\x0f", 0.4)                             # ctrl+o: more room
    check("^O smaller" in vt.text() and "▀███" not in vt.text(), "ctrl+o gives the task most of the screen (the logo steps aside)")
    key(b"\x0f", 0.4)
    key(b"\x15", 0.3)                             # ctrl+u: the text goes, the attachment stays
    check("goes on and on" not in vt.text() and "▤ tui-note.txt" in vt.text(), "ctrl+u clears the text, the attachments stay")
    key(b"\x1b[B", 0.2)                           # down to FILES
    key(b"\x7f", 0.4)                             # backspace there: the last one goes
    check("▣ clip.png" not in vt.text() and "▤ tui-note.txt" in vt.text(), "⌫ on FILES removes the last attachment")
    # 1c. FOLDER and BRANCH: where the council works, switched right here
    check("FOLDER" in vt.text() and "BRANCH" in vt.text() and "⏎ another folder" in vt.text(), "the form has FOLDER and BRANCH rows")
    key(b"\x1b[B", 0.2)                           # FOLDER
    key(b"\r", 1.0)
    wait_for(lambda s: "Work in another folder" in s and "type a path" in s, 10, "FOLDER opens a list of folders, and a way to type one")
    for _ in range(12):                            # the last item: type a path
        if "▸ ✎ type a path" in vt.text():
            break
        key(b"\x1b[B", 0.15)
    key(b"\r", 0.3)
    key(b"\x15" + b"/no/such/folder", 0.3)
    key(b"\r", 0.5)
    check("that folder doesn't exist" in vt.text(), "...a folder that isn't there is refused, plainly")
    key(b"\x1b", 0.3)
    key(b"\x1b", 0.3)
    check("Work in another folder" not in vt.text(), "esc closes it")
    key(b"\x1b[B", 0.2)                           # BRANCH
    key(b"\r", 1.0)
    wait_for(lambda s: "Switch branch" in s and "feature/demo" in s, 10, "BRANCH lists the branches")
    for _ in range(6):
        if "▸   feature/demo" in vt.text():
            break
        key(b"\x1b[B", 0.15)
    key(b"\r", 1.5)
    wait_for(lambda s: "Switch branch" not in s and re.search(r"BRANCH\s+feature/demo", s) is not None, 10, "picking a branch switches to it")
    check(subprocess.run(["git", "-C", proj, "branch", "--show-current"], capture_output=True, text=True).stdout.strip() == "feature/demo",
          "...for real (git says so)")
    key(b"\r", 1.0)                               # and back to main
    for _ in range(6):
        if "▸   main" in vt.text():
            break
        key(b"\x1b[B", 0.15)
    key(b"\r", 1.5)
    for _ in range(4):
        key(b"\x1b[A", 0.15)                       # back up to the task
    key(b"tui e2e: a hello page", 0.6)
    check("tui e2e: a hello page" in vt.text(), "the task field echoes what was typed")
    snap("start")
    check(not os.path.exists(f"{proj}/.navi") and os.path.isfile(f"{NAVID}/project.json"), "NAVI keeps its data out of the project folder (no .navi in it)")
    check("✕ QUIT" in vt.text(), "the start screen has QUIT (and END ALL SESSIONS when any are open)")
    key(b"\r", 0.2)
    # 2. the session: the fake moderator seats the council and ARCHITECT sends its proposal
    wait_for(lambda s: "e2e proposal" in s, 45, "the fake moderator's proposal in the feed")
    pump(2.0)                                                # let the packets land
    screen = vt.text()
    snap("session")
    wait_for(lambda s: "N A V I" in s, 6, "the hub is drawn")       # the rings sweep over its label now and then: wait for a frame
    names = ["ARCHITECT", "ADVERSARY", "LEDGER", "SCRIBE", "WARDEN"]
    check(all(n in screen for n in names), "every agent of The Knights is on the graph: " + ", ".join(names))
    check("PROPOSAL" in screen and "ARCHITECT → ALL" in screen, "the feed says who sent what to whom")
    check(re.search(r"[⠁-⣿]", screen) is not None, "rings and wires are drawn in braille")
    check("tui e2e: a hello page" in screen.splitlines()[0], "the header carries the task")
    # 3. a question from an agent: the box, an option, the answer reaches the server
    # (written the way a moderator writes it: one line, \n for line breaks, Markdown, and longer than the screen)
    long_q = "tui e2e: which style?\\n\\n**A) Wired:** neon on black, the council's own look\\n" + "\\n".join(f"- point {i:02d} of the plan" for i in range(40))
    r = navi("ask", "--from", "architect", "--question", long_q, "--option", "Wired", "--option", "Classic", "--no-wait")
    m = re.search(r"id ([0-9a-f]{8})", r.stdout)
    qid = m.group(1) if m else ""
    check(bool(qid), "navi ask opened a question")
    wait_for(lambda s: "asks you" in s and "which style?" in s and "Classic" in s, 15, "the question box")
    snap("ask")
    scr = vt.text()
    own_line = re.search(r"│\s+tui e2e: which style\?\s+│", scr) is not None        # on a line of its own
    check("\\n" not in scr and own_line and "• point 00 of the plan" in scr and re.search(r"A\) Wired: neon", scr) is not None,
          "a long question reads as written: its line breaks, bullets, no ** or \\n")
    check("more lines · PgDn" in scr and "point 39" not in scr, "...and what doesn't fit says so (↓ more · PgDn)")
    for _ in range(5):
        key(b"\x1b[6~", 0.3)
    check("point 39" in vt.text() and "point 00" not in vt.text(), "PgDn scrolls to the rest of it")
    key(b"2", 0.2)
    reply = f"{NAVID}/sessions/{sid()}/replies/{qid}.json"
    end = time.time() + 10
    while time.time() < end and not os.path.exists(reply):
        pump(0.2)
    check(os.path.exists(reply) and json.load(open(reply)).get("choice") == "Classic", "picking option 2 answered 'Classic' through /reply")
    wait_for(lambda s: "which style?" not in s or "answered: Classic" in s, 10, "the box closes after the answer")
    # 3b. a permission card: a background moderator's command that nothing allowed waits for your OK (y: allow once)
    hid = next((f[:-5] for f in os.listdir(f"{NAVID}/hosts") if f.endswith(".json") and ".relaunch" not in f
                and json.load(open(f"{NAVID}/hosts/{f}")).get("session") == sid()), "")
    check(bool(hid), "the background moderator has a host record")
    req = {"hook_event_name": "PermissionRequest", "tool_name": "Bash",
           "tool_input": {"command": "npm install left-pad", "description": "tui e2e: this needs your OK"},
           "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm install:*"}],
                                       "behavior": "allow", "destination": "localSettings"}]}
    hook = subprocess.Popen(["navi", "permit"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            env={**env, "NAVI_DIR": NAVID, "NAVI_HOST_ID": hid})
    hook.stdin.write(json.dumps(req))
    hook.stdin.close()
    wait_for(lambda s: "wants to run" in s and "tui e2e: this needs your OK" in s and "It runs: Use npm" in s and "For this session" in s, 15, "the permission box")
    snap("permit")
    check("› npm install left-pad" not in vt.text() and "c shows the command" in vt.text(), "the box says it in words; the command itself on c")
    key(b"c", 0.4)
    check("› npm install left-pad" in vt.text(), "c shows the command")
    key(b"y", 0.3)
    end = time.time() + 10
    while time.time() < end and hook.poll() is None:
        pump(0.2)
    out = json.loads(hook.stdout.read() or "{}") if hook.poll() is not None else {}
    dec = out.get("hookSpecificOutput", {}).get("decision", {})
    check(dec.get("behavior") == "allow" and "updatedPermissions" not in dec, "y allowed it once: the waiting hook answered allow")
    wait_for(lambda s: "you allowed it once" in s, 10, "the feed says you allowed it once")
    # 4. talk to the council from the input line: @ suggests the agents as you type, tab takes one
    key(b"\r", 0.2)
    key(b"@a", 0.4)
    scr = vt.text()
    check("@architect" in scr and "@adversary" in scr and "@all" in scr and "take it" in scr, "typing @ suggests the council's agents (and @all), as you type")
    key(b"r", 0.3)
    check("@architect" in vt.text() and "@adversary" not in vt.text(), "...narrowing with each letter")
    key(b"\t", 0.3)
    check(re.search(r"› @architect\s", vt.text()) is not None and "take it" not in vt.text(), "tab takes it: @architect, and the list closes")
    key(b"\x15", 0.2)               # ctrl-u: clear the line
    key(b"/en", 0.3)
    check("/end" in vt.text() and "wrap up" in vt.text(), "/ suggests the commands, with what each does")
    key(b"\x1b", 0.3)
    check("wrap up" not in vt.text(), "esc closes the list (the text stays)")
    key(b"\x15", 0.2)
    key(b"hello from the tui", 0.3)
    key(b"\r", 1.5)
    log = open(f"{NAVID}/sessions/{sid()}/log.jsonl").read()
    check('"agent": "user"' in log and "hello from the tui" in log, "a typed line reaches the council through /say")
    key(b"\x1b", 0.2)
    # 5. q while the council works: it asks first, and says the council keeps running
    key(b"q", 0.8)
    check("Leave the TUI?" in vt.text() and "background" in vt.text(), "q asks first while the council works, and says it keeps running")
    key(b"n", 0.6)
    check("Leave the TUI?" not in vt.text(), "n keeps the TUI open")
    # 6. resize below 100 columns: the graph stacks above the feed
    cols, rows = 90, 34
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    vt.resize(cols, rows)
    os.killpg(p.pid, signal.SIGWINCH)       # what the terminal does on a resize (the shell ignores it)
    pump(1.5)
    lines = vt.text().splitlines()
    graph_row = next((i for i, ln in enumerate(lines) if "▌ ARCHITECT" in ln), -1)       # the agent's chip and name
    feed_row = next((i for i, ln in enumerate(lines) if ln.strip().startswith("FEED")), -1)
    check(0 < graph_row < feed_row and any("ARCHITECT →" in ln for ln in lines[feed_row:]) and max(len(ln) for ln in lines) <= cols,
          f"narrow: the graph (ARCHITECT on row {graph_row}) sits above the feed (row {feed_row})")
    snap("narrow")
    # 7. the end: CONSENSUS, then q leaves without asking
    navi("end", "--summary", "tui e2e: the council agrees on a single hello page")
    # 40s: on a busy machine the test's own terminal emulator falls behind the TUI's animation (the feed shows the end first)
    wait_for(lambda s: "L A Y E R" in s and "the council agrees" in s, 40, "the CONSENSUS screen with the summary")
    pump(1.5)
    snap("consensus")
    check("⏎  OK" in vt.text() and "/new <task>" in vt.text(), "CONSENSUS shows one button, OK, and says what comes next")
    key(b"\r", 0.8)
    pump(0.5)
    wait_for(lambda s: "Back in the chat" in s and "Want them back?" in s, 10, "the first time back in the chat: what changed")
    snap("chat-intro")
    key(b"x", 0.6)
    check("Back in the chat" not in vt.text(), "any key closes it")
    cfg = json.load(open(f"{sp}/home/config.json"))
    check(cfg.get("chat_intro_seen") is True, "...and it won't show again (chat_intro_seen saved)")
    check("offline" in vt.text() and "chat with NAVI" in vt.text(), "OK goes back to the session: the council offline, a chat with NAVI")
    snap("chat")
    key(b"/end", 0.2); key(b"\r", 0.6)
    check("already done" in vt.text(), "/end after the end explains /new and /quit")
    key(b"\x1b", 0.3)
    key(b"q", 0.5)
    end = time.time() + 15
    while p.poll() is None and time.time() < end:
        pump(0.2)
    pump(0.3)
    code = p.poll()
    check(code == 0, f"navi tui exits cleanly (code {code})")
    # 8. the terminal is back: main screen, cursor, line discipline
    tail = raw[raw.rfind(b"\x1b[?1049h"):] if b"\x1b[?1049h" in raw else b""
    check(b"\x1b[?1049l" in tail and tail.rfind(b"\x1b[?25h") > tail.rfind(b"\x1b[?25l"), "left the alternate screen with the cursor shown")
    m = re.search(rb"TTYFLAGS (\d+) (\d+)", raw)
    iflag, lflag = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
    want = termios.ECHO | termios.ICANON | termios.ISIG
    check(bool(m) and lflag & want == before[3] & want and iflag == before[0],
          f"echo, line editing, signals and input flags are back for the next command (lflag {lflag:#x} vs {before[3]:#x})")
    flog = open(f"{sp}/ufake.log").read() if os.path.exists(f"{sp}/ufake.log") else ""
    check("[-p]" in flog and "[stream-json]" in flog, "the moderator ran headless (the setting says terminal: /launch mode headless won)")
finally:
    if p.poll() is None:
        os.killpg(p.pid, signal.SIGKILL)
print("TUI SUITE PASSED" if not fails else "TUI SUITE FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
