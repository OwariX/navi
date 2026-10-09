"""tui.py - NAVI in the terminal: the council as a live ANSI graph, the feed, questions and CONSENSUS.

`navi tui [--session SID]` (navi.cmd_tui -> run). One session at a time. It is a client of the interface server, like
web/index.html: it starts the server when it isn't running, launches with POST /launch (always a background
moderator), answers with /reply, talks with /say, stops with /moderator/stop, and follows the session by tailing
the session's log.jsonl (in ~/.navi/projects). Quitting never stops the council. Zero dependencies: stdlib, Python 3.10+, a Unix tty.
"""
from __future__ import annotations

import colorsys
import io
import json
import math
import os
import random
import re
import select
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from queue import Empty, Queue
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

try:
    import termios
except ImportError:      # Windows: no tty control, no TUI
    termios = None

# ---------------------------------------------------------------- palette (follows the interface's: ice by default)

RED, CYAN, INK, DIM, OK = "#ff2a4a", "#7fe7ff", "#d9d4c7", "#464254", "#5dffb5"
AMBER, WHITE = "#ffd24a", "#ffffff"
MUTED = "#8a8597"      # secondary text, between ink and dim
WIRE = "#3b3747"       # idle wires
BG = (11, 10, 16)      # what fades fade into: dark, like nearly every terminal
AGENT_COLORS = {"architect": "#7fe7ff", "adversary": "#ff2a4a", "ledger": "#ffb347", "scribe": "#e8e2d0", "warden": "#5dffb5"}
KIND_COLOR = {"proposal": CYAN, "revision": CYAN, "challenge": RED, "reject": RED, "verdict": WHITE, "ack": "#8dffb0",
              "request": AMBER, "note": INK, "ask": AMBER, "reply": WHITE, "artifact": "#e8e2d0"}
KIND_LABEL = {"ack": "ACCEPTED", "reject": "REJECTED"}
DECISION_COLOR = {"allow": OK, "ask": AMBER, "escalate": AMBER, "deny": RED}
PERMIT_WORDS = {"once": "you allowed it once", "always": "you allowed it for this session", "deny": "you said no",
                "timeout": "nobody answered, so it didn't run", "gone": "the moderator stopped before anyone answered"}
PERMIT_VERB = {"Bash": "wants to run", "WebFetch": "wants to fetch", "WebSearch": "wants to search", "Read": "wants to read",
               "Write": "wants to write", "Edit": "wants to change", "MultiEdit": "wants to change", "NotebookEdit": "wants to change"}


PERMS_INFO = {"ask": "edits and the usual checks run; anything else waits for your OK",
              "auto": "nothing waits for you: the work runs; pushes, deploys, cloud changes and uploads are refused",
              "all": "anything runs without asking; the guard still blocks keys and .env files",
              "skip": "nothing is checked, not even the guard (--dangerously-skip-permissions)"}


def fmt_tok(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{round(n / 1e3)}k" if n >= 1e3 else str(n)


def permit_verb(ev: dict) -> str:
    return PERMIT_VERB.get(str(ev.get("tool") or ""), f"wants to use {ev.get('tool') or 'a tool'}")


def permit_opts(ev: dict) -> list[tuple[str, str]]:
    """A permission card's answers: (label, decision). "For this session" only when NAVI can name the rule it adds."""
    rules = [str(r) for r in ev.get("rules") or []] + ([f"{ev['pattern']} (WARDEN won't ask again)"] if ev.get("pattern") else [])
    return [("Allow once", "once")] + ([("For this session · " + ", ".join(rules), "always")] if rules else []) + [("Deny", "deny")]
STATE_ICON = {"working": "▸", "waiting": "◆", "blocked": "✕", "done": "✓", "idle": "·", "offline": "○"}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
GLYPHS = "▓▒░#@$%&01/\\<>*"
CONNECTING = "moderator connecting…"
PACE_INFO = {"auto": "NAVI picks the pace from the task", "quick": "one pass: plan, build, check · a minute or two",
             "standard": "build, then the reviewers check the result", "thorough": "proposal, challenges, ADR and threat model"}
MODEL_INFO = {"": "your Claude Code default", "opus": "top tier", "sonnet": "fast and capable", "haiku": "fastest, lightest",
              "fable": "top tier"}
TIERS = ("strong", "balanced", "fast")
TIER_OF = {"strong": "strong", "balanced": "balanced", "fast": "fast", "opus": "strong", "fable": "strong", "sonnet": "balanced", "haiku": "fast"}
EFFORTS = ("", "low", "medium", "high")
EFFORTS_ALL = ("", "low", "medium", "high", "xhigh", "max")
COMMANDS = {"new": "after the end: run the council again on a new task (/new <task>)",
            "cd": "work in another folder (/cd <path>, relative to where you are; /cd alone says where you are)",
            "end": "ask the council to wrap up and close the session", "stop": "pause NAVI on this session (/continue resumes it)",
            "continue": "resume NAVI on this session (it picks up where it left off)",
            "effort": "how hard NAVI and its members think: /effort low|medium|high|xhigh|max (at its next checkpoint)",
            "model": "NAVI's model: /model <a tier: strong|balanced|fast, or a model name> (at its next checkpoint)", "help": "keys and commands", "quit": "leave the TUI"}
# the interface's palettes (web/index.html PRESETS): accent, second accent, ink, background
PALETTES = {"ice": ("#5cc8ff", "#ffffff", "#e2ecf7", (8, 16, 25)), "wired": ("#ff2a4a", "#7fe7ff", "#d9d4c7", (11, 10, 16)),
            "phosphor": ("#39ff88", "#d4ff5a", "#c8f7d6", (2, 7, 3)), "amber": ("#ffb000", "#ff6a2a", "#f3dcae", (11, 7, 3)),
            "vapor": ("#ff4fd8", "#6fe3ff", "#eadcff", (12, 6, 22)), "dusk": ("#ff6b8b", "#9ad7ff", "#efe9f7", (23, 20, 31))}


def apply_palette(preset: str):
    """Use the same palette as the browser (Settings > Look): the accents, the ink and the background."""
    global RED, CYAN, INK, BG
    RED, CYAN, INK, BG = PALETTES.get(preset, PALETTES["ice"])
    KIND_COLOR.update({"proposal": CYAN, "revision": CYAN, "challenge": RED, "reject": RED, "note": INK})
    DECISION_COLOR["deny"] = RED


TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or os.environ.get("TERM_PROGRAM") != "Apple_Terminal"


def rgb(c) -> tuple:
    if isinstance(c, tuple):
        return c
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a, b, t: float) -> tuple:
    """a -> b by t, in sixteenths, so fades reuse a handful of styles."""
    a, b = rgb(a), rgb(b)
    t = round(max(0.0, min(1.0, t)) * 16) / 16
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _c256(r: int, g: int, b: int) -> int:
    if max(r, g, b) - min(r, g, b) < 12:          # a grey: use the 24-step ramp
        return 16 if r < 8 else 231 if r > 246 else 232 + round((r - 8) / 247 * 23)
    q = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40  # noqa: E731
    return 16 + 36 * q(r) + 6 * q(g) + q(b)


@lru_cache(maxsize=4096)
def sty(fg=None, bg=None, bold=False, italic=False, under=False) -> str:
    """One self-contained SGR sequence (it starts with a reset, so nothing leaks from the previous cell)."""
    p = ["0"]
    if bold:
        p.append("1")
    if italic:
        p.append("3")
    if under:
        p.append("4")
    for base, c in ((38, fg), (48, bg)):
        if c is not None:
            r, g, b = rgb(c)
            p.append(f"{base};2;{r};{g};{b}" if TRUECOLOR else f"{base};5;{_c256(r, g, b)}")
    return "\x1b[" + ";".join(p) + "m"


def agent_color(name: str, given: str = "") -> str:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", given or ""):
        return given
    if name in AGENT_COLORS:
        return AGENT_COLORS[name]
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.72, 0.75)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


# ---------------------------------------------------------------- text: untrusted, sometimes wide

_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufe0e\ufe0f\ufeff\ud800-\udfff]")


def clean(s) -> str:
    """Text from agents and the log -> safe to print: no escape sequences, no control or invisible characters."""
    return _UNSAFE.sub("", str(s if s is not None else "").replace("\t", "  "))


def oneline(s) -> str:
    return " ".join(clean(s).split())


@lru_cache(maxsize=8192)
def cw(c: str) -> int:
    """Display width of one character: 0 (combining), 1, or 2 (CJK, emoji)."""
    if c < "\u0300":
        return 1
    if unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def tw(s: str) -> int:
    return len(s) if s.isascii() else sum(cw(c) for c in s)


def cut(s: str, w: int) -> str:
    """The longest prefix of s that is at most w cells wide."""
    if s.isascii():
        return s[:max(0, w)]
    n = 0
    for i, c in enumerate(s):
        n += cw(c)
        if n > w:
            return s[:i]
    return s


def fit(s: str, w: int) -> str:
    if w <= 0:
        return ""
    return s if tw(s) <= w else cut(s, w - 1).rstrip() + "…"


def wrap(s: str, w: int, first: int | None = None) -> list[str]:
    """Word-wrap to w cells (the first line may be narrower); words longer than a line are split."""
    out, line, lw = [], "", 0
    width = lambda: first if first is not None and not out else w  # noqa: E731
    for word in s.split():
        ww = tw(word)
        if line and lw + 1 + ww <= width():
            line, lw = f"{line} {word}", lw + 1 + ww
            continue
        if line:
            out.append(line)
            line, lw = "", 0
        while ww > width():
            head = cut(word, width()) or word[0]
            out.append(head)
            word = word[len(head):]
            ww = tw(word)
        line, lw = word, ww
    if line:
        out.append(line)
    return out


def paragraphs(s: str, w: int) -> list[str]:
    """wrap(), but line breaks survive (one blank line at most between paragraphs)."""
    out: list[str] = []
    for para in s.splitlines():
        rows = wrap(para, w)
        if rows:
            out += rows
        elif out and out[-1]:
            out.append("")
    while out and not out[-1]:
        out.pop()
    return out


LIST_ITEM = re.compile(r"^(\s*)([-*•]|\d{1,2}[.)]|[A-Za-z][)])\s+(.*)$")


def md_lines(s: str, w: int) -> list[tuple[str, bool]]:
    """A question as an agent wrote it (Markdown, more or less) -> lines to show: headings bold, list items with a
    hanging indent (• for - and *, A) and 1. kept), **bold** and `code` marks dropped, line breaks kept."""
    out: list[tuple[str, bool]] = []
    for raw in s.splitlines():
        line = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m.group(1) or m.group(2), raw.rstrip())
        line = re.sub(r"`([^`]+)`", r"\1", line)
        if not line.strip():
            if out and out[-1][0]:
                out.append(("", False))
            continue
        h = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if h:
            if out and out[-1][0]:
                out.append(("", False))
            out += [(x, True) for x in wrap(h.group(1), w)]
            continue
        m = LIST_ITEM.match(line)
        if m:
            ind, mark, text = min(len(m.group(1)), 6), m.group(2), m.group(3)
            mark = "•" if mark in "-*•" else mark
            pre = " " * ind + mark + " "
            rows = wrap(text, max(10, w - len(pre))) or [""]
            out += [((pre if i == 0 else " " * len(pre)) + r, False) for i, r in enumerate(rows)]
            continue
        out += [(x, False) for x in wrap(line, w)]
    while out and not out[-1][0]:
        out.pop()
    return out


# HALLOWEEN 2026: delete at the start of November (the pumpkin by the logo on the start screen, see draw_start).
# It only shows in October anyway: NAVI_HALLOWEEN=0 hides it, =1 shows it any month.
PUMPKIN = ("   _)_    ", " ,'^ ^`.  ", "(  vvv  ) ", " `.___,'  ")


def halloween() -> bool:
    v = os.environ.get("NAVI_HALLOWEEN", "")
    return v == "1" or (v != "0" and datetime.now().month == 10)


def epoch(ts) -> float | None:
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except (TypeError, ValueError):
        return None


def hhmm(ts) -> str:
    try:
        return datetime.fromisoformat(str(ts)).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return "     "


def dur(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def home(p: Path) -> str:
    s, h = str(p), str(Path.home())
    return "~" + s[len(h):] if s == h or s.startswith(h + os.sep) else s


def git_branch(d: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(d), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    b = r.stdout.strip() if r.returncode == 0 else ""
    return "detached" if b == "HEAD" else clean(b)


# a block font for CONSENSUS, in the same hand as the NAVI logo
BIG = {
    "C": [" ▄█████", "██▀    ", "██     ", "██▄    ", " ▀█████"],
    "O": [" ▄███▄ ", "██▀ ▀██", "██   ██", "██▄ ▄██", " ▀███▀ "],
    "N": ["██▄  ██", "███▄ ██", "██ ▀███", "██  ▀██", "██   ██"],
    "S": [" ▄█████", "██▄    ", " ▀███▄ ", "    ▀██", "█████▀ "],
    "E": ["███████", "██     ", "██████ ", "██     ", "███████"],
    "U": ["██   ██", "██   ██", "██   ██", "██▄ ▄██", " ▀███▀ "],
}


def big(word: str) -> list[str]:
    return [" ".join(BIG[c][r] for c in word) for r in range(5)]


# ---------------------------------------------------------------- the screen: a cell grid, flushed as a diff

class Screen:
    """Draw a whole frame into a grid, then write only the cells that changed since the last frame (no flicker)."""

    def __init__(self, write):
        self.write = write
        self.w = self.h = 0
        self.ch: list[list[str]] = []
        self.st: list[list[str]] = []
        self.pch: list[list[str]] | None = None     # what the terminal shows now (None = unknown: redraw everything)
        self.pst: list[list[str]] | None = None

    def begin(self, w: int, h: int):
        if (w, h) != (self.w, self.h):
            self.w, self.h, self.pch = w, h, None
        self.ch = [[" "] * w for _ in range(h)]
        self.st = [[""] * w for _ in range(h)]

    def invalidate(self):
        self.pch = None

    def put(self, x: int, y: int, s: str, style: str = "", maxw: int | None = None) -> int:
        """Write s at (x, y), clipped to the screen (and to maxw cells). Returns the x after it."""
        if not s or y < 0 or y >= self.h:
            return x
        end = self.w if maxw is None else min(self.w, x + maxw)
        rc, rs = self.ch[y], self.st[y]
        if s.isascii():
            if x < 0:
                s, x = s[-x:], 0
            n = min(len(s), end - x)
            if n <= 0:
                return x
            if rc[x] == "" and x > 0:         # we cut a wide character in half: blank its other half
                rc[x - 1] = " "
            rc[x:x + n] = s[:n]
            rs[x:x + n] = [style] * n
            if x + n < self.w and rc[x + n] == "":
                rc[x + n] = " "
            return x + n
        for c in s:
            k = cw(c)
            if k == 0:
                if 0 < x <= self.w:
                    j = x - 1 if rc[x - 1] != "" else x - 2
                    if j >= 0:
                        rc[j] += c
                continue
            if x + k > end:
                break
            if x >= 0:
                if rc[x] == "" and x > 0:
                    rc[x - 1] = " "
                rc[x], rs[x] = c, style
                if k == 2:
                    rc[x + 1], rs[x + 1] = "", style
                elif x + 1 < self.w and rc[x + 1] == "":
                    rc[x + 1] = " "
            x += k
        return x

    def cell(self, x: int, y: int, c: str, style: str):
        """One narrow character, no checks beyond the bounds (the braille canvas uses it)."""
        if 0 <= x < self.w and 0 <= y < self.h:
            rc = self.ch[y]
            if rc[x] == "" or (x + 1 < self.w and rc[x + 1] == ""):
                return                           # never split a wide character
            rc[x], self.st[y][x] = c, style

    def halo(self, x: int, y: int, w: int):
        """Clear braille dots from x-1 .. x+w on row y, so a label never touches a wire or a ring."""
        if 0 <= y < self.h:
            rc = self.ch[y]
            for i in range(max(0, x - 1), min(self.w, x + w + 1)):
                if "\u2800" <= rc[i] <= "\u28ff":
                    rc[i] = " "

    def label(self, x: int, y: int, s: str, style: str = "") -> int:
        self.halo(x, y, tw(s))
        return self.put(x, y, s, style)

    def dim(self, style: str):
        """Everything drawn so far fades into the background (behind a dialog)."""
        for rc, rs in zip(self.ch, self.st):
            for i, ch in enumerate(rc):
                if ch != " ":
                    rs[i] = style

    def fill(self, x: int, y: int, w: int, h: int, style: str = ""):
        for r in range(max(0, y), min(self.h, y + h)):
            a, b = max(0, x), min(self.w, x + w)
            if a < b:
                if self.ch[r][a] == "" and a > 0:
                    self.ch[r][a - 1] = " "
                if b < self.w and self.ch[r][b] == "":
                    self.ch[r][b] = " "
                self.ch[r][a:b] = [" "] * (b - a)
                self.st[r][a:b] = [style] * (b - a)

    def flush(self):
        out, full, cur, cx, cy = [], self.pch is None, None, -1, -1
        W = self.w
        if full:
            out.append("\x1b[0m\x1b[2J")
        for y in range(self.h):
            rc, rs = self.ch[y], self.st[y]
            if not full:
                pc, ps = self.pch[y], self.pst[y]
                if rc == pc and rs == ps:
                    continue
            x = 0
            while x < W:
                c = rc[x]
                if c == "":
                    x += 1
                    continue
                wide = x + 1 < W and rc[x + 1] == ""
                if full:
                    changed = c != " " or rs[x] != ""
                else:
                    changed = c != pc[x] or rs[x] != ps[x] or (wide and pc[x + 1] != "")
                if not changed:
                    x += 1
                    continue
                if cy != y or cx != x:
                    out.append(f"\x1b[{y + 1};{x + 1}H")
                if rs[x] != cur:
                    cur = rs[x]
                    out.append(cur or "\x1b[0m")
                out.append(c)
                x += 2 if wide else 1
                cx, cy = x, y
        self.pch, self.pst = self.ch, self.st
        if out:
            self.write("\x1b[?2026h" + "".join(out) + "\x1b[0m\x1b[?2026l")

    def text(self) -> str:
        """The frame as plain text (for debugging and snapshots)."""
        return "\n".join("".join(r).rstrip() for r in self.ch)


# braille: 2 x 4 dots per cell, so lines and rings get sub-cell resolution (and its dots are about square)
DOT = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.bits: dict = {}
        self.col: dict = {}

    def dot(self, x: float, y: float, color, z: int = 0):
        x, y = int(x), int(y)
        if 0 <= x < self.w * 2 and 0 <= y < self.h * 4:
            k = (x >> 1, y >> 2)
            self.bits[k] = self.bits.get(k, 0) | DOT[y & 3][x & 1]
            old = self.col.get(k)
            if old is None or z >= old[0]:
                self.col[k] = (z, color)

    def path(self, pts, color, z: int = 0, dash: tuple | None = None, phase: int = 0):
        for i, (x, y) in enumerate(pts):
            if dash is None or (i - phase) % dash[0] < dash[1]:
                self.dot(x, y, color, z)

    def ring(self, cx: float, cy: float, r: float, color, z: int = 0, a0: float = 0.0, span: float = math.tau, dash=None, phase=0):
        n = max(10, int(abs(span) * r * 1.6))
        self.path([(cx + math.cos(a0 + span * i / n) * r, cy + math.sin(a0 + span * i / n) * r) for i in range(n + 1)],
                  color, z, dash, phase)

    def blit(self, scr: Screen, ox: int, oy: int, bold: bool = False):
        for (x, y), b in self.bits.items():
            scr.cell(ox + x, oy + y, chr(0x2800 | b), sty(self.col[(x, y)][1], bold=bold))


def bez(a: tuple, b: tuple, bend: float, t: float) -> tuple:
    """A point on the quadratic curve from a to b that bows sideways by `bend` (0 = straight)."""
    (ax, ay), (bx, by) = a, b
    cx, cy = (ax + bx) / 2 - (by - ay) * bend, (ay + by) / 2 + (bx - ax) * bend
    u = 1 - t
    return u * u * ax + 2 * u * t * cx + t * t * bx, u * u * ay + 2 * u * t * cy + t * t * by


def outward(a: tuple, b: tuple, hub: tuple, k: float = .28) -> float:
    """The bend that bows the curve from a to b away from the hub, so agent-to-agent traffic goes around it."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    nx, ny = -(b[1] - a[1]), b[0] - a[0]          # the curve's control point moves along this normal
    return k if (mx - hub[0]) * nx + (my - hub[1]) * ny >= 0 else -k


# ---------------------------------------------------------------- keys

class Keys:
    """Raw tty bytes -> key names ('up', 'enter', 'ctrl-c', ...), printable characters, and ('paste', text)."""
    CSI = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "Z": "btab"}
    TILDE = {"1": "home", "2": "ins", "3": "del", "4": "end", "5": "pgup", "6": "pgdn", "7": "home", "8": "end"}
    CTRL = {"\r": "enter", "\n": "ctrl-j", "\t": "tab", "\x7f": "bs", "\x08": "bs", "\x03": "ctrl-c", "\x04": "ctrl-d",
            "\x01": "ctrl-a", "\x05": "ctrl-e", "\x0b": "ctrl-k", "\x0c": "ctrl-l", "\x15": "ctrl-u", "\x17": "ctrl-w",
            "\x1a": "ctrl-z", "\x0e": "down", "\x10": "up", "\x07": "ctrl-g", "\x0f": "ctrl-o", "\x16": "ctrl-v"}
    SEQ = re.compile(rb"\x1b\[([0-9;?]*)([\x40-\x7e])")
    PART = re.compile(rb"\x1b\[[0-9;?]*")

    def __init__(self, fd: int):
        self.fd, self.buf = fd, b""

    def read(self) -> list:
        try:
            data = os.read(self.fd, 65536)
        except OSError:          # the terminal is gone
            raise EOFError
        if not data:
            raise EOFError
        self.buf += data
        keys: list = []
        while True:
            got, stuck = self._parse(final=False)
            keys += got
            if not stuck:
                return keys
            if select.select([self.fd], [], [], 0.03)[0]:     # the rest of an escape sequence is on its way
                try:
                    more = os.read(self.fd, 65536)
                except OSError:
                    raise EOFError
                if more:
                    self.buf += more
                    continue
            if self.buf.startswith(b"\x1b[200~") and len(self.buf) < 1 << 20:
                return keys                                     # a long paste: wait for its end marker
            keys += self._parse(final=True)[0]
            return keys

    def _parse(self, final: bool):
        out, b, i, n = [], self.buf, 0, len(self.buf)
        while i < n:
            c = b[i]
            if c == 0x1b:
                if b.startswith(b"\x1b[200~", i):                # bracketed paste
                    j = b.find(b"\x1b[201~", i + 6)
                    if j < 0 and not final:
                        self.buf = b[i:]
                        return out, True
                    end = n if j < 0 else j
                    out.append(("paste", b[i + 6:end].decode("utf-8", "replace")))
                    i = n if j < 0 else j + 6
                    continue
                if i + 1 >= n:
                    if not final:
                        self.buf = b[i:]
                        return out, True
                    out.append("esc")
                    i += 1
                    continue
                nx = b[i + 1]
                if nx == 0x5b:                                   # CSI
                    m = self.SEQ.match(b, i)
                    if not m:
                        if not final and self.PART.fullmatch(b, i):
                            self.buf = b[i:]
                            return out, True
                        i += 2
                        continue
                    i = m.end()
                    params, fin = m.group(1).decode(), m.group(2).decode()
                    parts = params.split(";")
                    key = self.TILDE.get(parts[0]) if fin == "~" else self.CSI.get(fin)
                    mod = parts[1] if len(parts) > 1 else ""
                    if (fin == "u" and parts[0] == "13" and mod) or (fin == "~" and parts[0] == "27" and parts[-1] == "13"):
                        key = "shift-enter"                     # kitty's keys, or xterm's modifyOtherKeys: enter with a modifier
                    if key and mod in ("3", "5") and key in ("left", "right"):
                        key = "word-" + key
                    elif key and mod == "2" and key in ("up", "down"):
                        key = "pgup" if key == "up" else "pgdn"
                    if key:
                        out.append(key)
                    continue
                if nx == 0x4f:                                   # SS3: arrows in application mode
                    if i + 2 >= n and not final:
                        self.buf = b[i:]
                        return out, True
                    key = self.CSI.get(chr(b[i + 2])) if i + 2 < n else None
                    out.append(key or "esc")
                    i += 3
                    continue
                if nx == 0x1b:
                    out.append("esc")
                    i += 1
                    continue
                out.append({0x7f: "ctrl-w", 0x62: "word-left", 0x66: "word-right", 0x0d: "alt-enter", 0x0a: "alt-enter"}.get(nx, "esc"))   # alt+key
                i += 2
                continue
            ln = 1 if c < 0x80 else 2 if c >> 5 == 6 else 3 if c >> 4 == 14 else 4 if c >> 3 == 30 else 1
            if i + ln > n:
                if not final:
                    self.buf = b[i:]
                    return out, True
                break
            ch = b[i:i + ln].decode("utf-8", "replace")
            i += ln
            if ch in self.CTRL:
                out.append(self.CTRL[ch])
            elif ch >= " " and ch != chr(0xFFFD):       # not a stray byte that wasn't UTF-8
                out.append(ch)
        self.buf = b""
        return out, False


class LineEdit:
    """A one-line text field: insert, delete, move, kill, paste. Newlines in pastes become spaces."""

    def __init__(self, text: str = "", limit: int = 2000):
        self.text, self.pos, self.limit = text, len(text), limit

    def set(self, text: str):
        self.text, self.pos = text, len(text)

    def insert(self, s: str):
        s = clean(s).replace("\n", " ")[:max(0, self.limit - len(self.text))]
        self.text = self.text[:self.pos] + s + self.text[self.pos:]
        self.pos += len(s)

    def key(self, k) -> bool:
        t, p = self.text, self.pos
        if isinstance(k, tuple):
            self.insert(k[1])
        elif len(k) == 1:
            self.insert(k)
        elif k == "bs" and p:
            self.text, self.pos = t[:p - 1] + t[p:], p - 1
        elif k == "del":
            self.text = t[:p] + t[p + 1:]
        elif k == "left":
            self.pos = max(0, p - 1)
        elif k == "right":
            self.pos = min(len(t), p + 1)
        elif k in ("home", "ctrl-a"):
            self.pos = 0
        elif k in ("end", "ctrl-e"):
            self.pos = len(t)
        elif k == "ctrl-u":
            self.text, self.pos = t[p:], 0
        elif k == "ctrl-k":
            self.text = t[:p]
        elif k == "ctrl-w":
            q = len(t[:p].rstrip())
            q = t.rfind(" ", 0, q) + 1
            self.text, self.pos = t[:q] + t[p:], q
        elif k == "word-left":
            q = len(t[:p].rstrip())
            self.pos = t.rfind(" ", 0, q) + 1
        elif k == "word-right":
            q = t.find(" ", p + 1)
            self.pos = len(t) if q < 0 else q
        else:
            return k == "bs"
        return True

    def draw(self, scr: Screen, x: int, y: int, w: int, style: str, focused: bool, placeholder: str = "", ph_style: str = ""):
        if w <= 1:
            return
        if not self.text:
            if focused:
                scr.put(x, y, " ", sty(BG, INK))
            scr.put(x + (1 if focused else 0), y, fit(placeholder, w - 1), ph_style)
            return
        start = 0
        while tw(self.text[start:self.pos]) > w - 2:       # scroll so the cursor stays in view
            start += max(1, (self.pos - start) // 4)
        vis = cut(self.text[start:], w - 1)
        scr.put(x, y, vis, style)
        if focused:
            cx = x + tw(self.text[start:self.pos])
            under = self.text[self.pos] if self.pos < len(self.text) else " "
            scr.put(cx, y, under if cw(under) == 1 else " ", sty(BG, INK))


NEWLINE_KEYS = ("alt-enter", "shift-enter", "ctrl-j")


class TextEdit(LineEdit):
    """A text field over several lines, for a task or an answer: newlines are kept (in pastes, and with alt+enter,
    shift+enter or ctrl+j), lines wrap at words, and up/down move a line (False at the first or last one, so a form
    can move to the next field)."""

    def __init__(self, text: str = "", limit: int = 20000):
        super().__init__(text, limit)
        self.w = 60                 # the width it was last drawn at: up/down move by what you see

    def insert(self, s: str):
        s = clean(str(s).replace("\r\n", "\n").replace("\r", "\n"))[:max(0, self.limit - len(self.text))]
        self.text = self.text[:self.pos] + s + self.text[self.pos:]
        self.pos += len(s)

    def rows(self, w: int) -> list[tuple[int, int]]:
        """(start, end) of each line as drawn at width w: paragraphs, wrapped at spaces."""
        out, i, t = [], 0, self.text
        for para in t.split("\n"):
            end, a = i + len(para), i
            while a < end:
                b, width = a, 0
                while b < end and width + cw(t[b]) <= w:
                    width += cw(t[b])
                    b += 1
                if b < end:                                  # break at the last space that fits, if there is one
                    sp = t.rfind(" ", a, b)
                    b = sp + 1 if sp > a else b
                out.append((a, b))
                a = b
            if a == i:
                out.append((i, i))
            i = end + 1
        return out or [(0, 0)]

    def where(self, rows: list) -> int:
        for n, (a, b) in enumerate(rows):
            if a <= self.pos < b or (self.pos == b and (n == len(rows) - 1 or rows[n + 1][0] > b)):
                return n
        return len(rows) - 1

    def key(self, k) -> bool:
        if k in NEWLINE_KEYS:
            self.insert("\n")
            return True
        if k in ("up", "down"):
            rows = self.rows(self.w)
            n = self.where(rows)
            m = n - 1 if k == "up" else n + 1
            if not 0 <= m < len(rows):
                return False
            col = tw(self.text[rows[n][0]:self.pos])
            a, b = rows[m]
            q = a
            while q < b and tw(self.text[a:q + 1]) <= col and self.text[q] != "\n":
                q += 1
            self.pos = q
            return True
        if k in ("home", "ctrl-a", "end", "ctrl-e"):
            rows = self.rows(self.w)
            a, b = rows[self.where(rows)]
            self.pos = a if k in ("home", "ctrl-a") else (b - 1 if b > a and self.text[b - 1:b] in (" ", "\n") and b < len(self.text) else b)
            return True
        return super().key(k)

    def height(self, w: int) -> int:
        return len(self.rows(max(4, w)))

    def draw(self, scr: Screen, x: int, y: int, w: int, style: str, focused: bool, placeholder: str = "", ph_style: str = "", h: int = 1) -> int:
        """Draw in a w x h box (scrolled so the cursor shows). -> the lines used."""
        if w <= 1:
            return 1
        self.w = w - 1
        if not self.text:
            if focused:
                scr.put(x, y, " ", sty(BG, INK))
            scr.put(x + (1 if focused else 0), y, fit(placeholder, w - 1), ph_style)
            return 1
        rows = self.rows(self.w)
        n = self.where(rows)
        h = max(1, min(h, len(rows)))
        top = min(max(0, n - h + 1), max(0, len(rows) - h))
        for i, (a, b) in enumerate(rows[top:top + h]):
            line = self.text[a:b].replace("\n", "")
            scr.put(x, y + i, cut(line, w - 1), style)
            if focused and top + i == n:
                cx = x + tw(self.text[a:self.pos].replace("\n", ""))
                under = self.text[self.pos] if self.pos < len(self.text) and self.text[self.pos] != "\n" else " "
                scr.put(cx, y + i, under if cw(under) == 1 else " ", sty(BG, INK))
        if top > 0:
            scr.put(x + w - 1, y, "↑", sty(DIM))
        if top + h < len(rows):
            scr.put(x + w - 1, y + h - 1, "↓", sty(DIM))
        return h


def clipboard_files() -> tuple[list[Path], str]:
    """What's on the clipboard, as files to attach: an image (saved as a PNG for the upload) or files copied in the file
    manager. A terminal can't paste an image itself, so ctrl+v asks the system for it, as Claude Code does.
    -> (files, why not). NAVI_CLIPBOARD_FILE stands in for the clipboard in the tests."""
    fake = os.environ.get("NAVI_CLIPBOARD_FILE", "")
    if fake:
        return ([Path(fake)] if Path(fake).is_file() else []), "the clipboard has no image or file"
    png = Path(tempfile.gettempdir()) / f"pasted-image-{time.strftime('%H%M%S')}.png"

    def run(cmd, out=None) -> str:
        try:
            r = subprocess.run(cmd, capture_output=out is None, stdout=out, timeout=8)
            return "" if r.returncode else (r.stdout.decode("utf-8", "replace").strip() if out is None else "ok")
        except (OSError, subprocess.TimeoutExpired):
            return ""
    if sys.platform == "darwin":
        f = run(["osascript", "-e", "POSIX path of (the clipboard as «class furl»)"])        # a file copied in Finder
        if f and Path(f).is_file():
            return [Path(f)], ""
        script = (f'set d to (the clipboard as «class PNGf»)\nset f to open for access (POSIX file "{png}") with write permission\n'
                  f'write d to f\nclose access f')
        if run(["osascript", "-e", script]) == "" and png.is_file() and png.stat().st_size:
            return [png], ""
        return [], "the clipboard has no image or file (copy one, then ^V)"
    tool = "wl-paste" if shutil.which("wl-paste") and os.environ.get("WAYLAND_DISPLAY") else "xclip" if shutil.which("xclip") else ""
    if not tool:
        return [], "to paste images here, install wl-clipboard (Wayland) or xclip (X11); dragging a file onto the window works as it is"
    types = run(["wl-paste", "--list-types"] if tool == "wl-paste" else ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"])
    if "text/uri-list" in types:
        uris = run(["wl-paste", "--type", "text/uri-list"] if tool == "wl-paste" else ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"])
        files = dropped_files(uris)
        if files:
            return files, ""
    if "image/png" in types:
        with open(png, "wb") as out:
            ok = run(["wl-paste", "--type", "image/png"] if tool == "wl-paste" else ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"], out)
        if ok and png.stat().st_size:
            return [png], ""
    return [], "the clipboard has no image or file (copy one, then ^V)"


def dropped_files(text: str) -> list[Path]:
    """A file dragged onto the terminal arrives as its path (quoted, backslash-escaped or a file:// address). When
    everything pasted is files that exist, they're attachments; anything else is just text."""
    import shlex
    from urllib.parse import unquote
    t = text.strip()
    if not t or len(t) > 4000:
        return []
    try:
        parts = shlex.split(t) if ("\\" in t or "'" in t or '"' in t) else t.split("\n") if "\n" in t else [t]
    except ValueError:
        return []
    out = []
    for raw in parts:
        raw = raw.strip()
        if raw.startswith("file://"):
            raw = unquote(raw[7:])
        p = Path(raw).expanduser()
        if not raw or not p.is_absolute() and not raw.startswith("~") or not p.is_file():
            return []
        out.append(p)
    return out[:12]


# ---------------------------------------------------------------- the server's HTTP API

class Api:
    """The NAVI server, exactly as the web page talks to it: JSON in, JSON out, the token on every POST."""

    def __init__(self, P: Path, port: int, token: str):
        self.P, self.port, self.token = P, port, token
        self.op = build_opener(ProxyHandler({}))       # 127.0.0.1 never goes through a proxy
        if not token:
            self.refresh()

    def refresh(self):
        """Re-read server.json (the server may have restarted on another port, with another token)."""
        try:
            info = json.loads((self.P / "server.json").read_text(encoding="utf-8"))
            self.port, self.token = int(info.get("port") or self.port), str(info.get("token") or "")
        except (OSError, ValueError):
            pass
        if not self.token:     # a server started before tokens were written to server.json: the page carries it
            try:
                with self.op.open(f"http://127.0.0.1:{self.port}/", timeout=3) as r:
                    m = re.search(rb'name="navi-token" content="([^"]+)"', r.read())
                self.token = m.group(1).decode() if m else ""
            except (OSError, URLError):
                pass

    def get(self, path: str, timeout: float = 4):
        with self.op.open(f"http://127.0.0.1:{self.port}{path}", timeout=timeout) as r:
            return json.loads(r.read() or b"null")

    def upload(self, path: Path, session: str = "") -> tuple[bool, dict]:
        """A file to attach, sent the way the page sends one: its bytes, with its name and type. -> its upload record."""
        import mimetypes
        from urllib.parse import urlencode
        try:
            size = path.stat().st_size
            if size > 25 * 1024 * 1024:
                return False, {"error": f"{path.name} is over 25 MB"}
            data = path.read_bytes()
        except OSError as e:
            return False, {"error": f"can't read {path.name}: {e.strerror or e}"}
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        q = urlencode({"name": path.name, "type": ctype, **({"session": session} if session else {})})
        return self.post(f"/upload?{q}", None, timeout=120, raw=data, ctype=ctype)

    def post(self, path: str, body: dict | None, timeout: float = 20, raw: bytes | None = None, ctype: str = "application/json") -> tuple[bool, dict]:
        for attempt in (0, 1):
            req = Request(f"http://127.0.0.1:{self.port}{path}", data=raw if raw is not None else json.dumps(body).encode(), method="POST",
                          headers={"Content-Type": ctype, "X-Navi-Token": self.token})
            try:
                with self.op.open(req, timeout=timeout) as r:
                    return True, json.loads(r.read() or b"{}")
            except HTTPError as e:
                if e.code == 403 and not attempt:
                    self.refresh()
                    continue
                try:
                    data = json.loads(e.read() or b"{}")
                except ValueError:
                    data = {}
                return False, {"error": clean(data.get("error") or f"the server said {e.code}")}
            except (URLError, OSError) as e:
                if not attempt:
                    self.refresh()
                    continue
                return False, {"error": f"the NAVI server isn't answering ({getattr(e, 'reason', e)})"}
        return False, {"error": "the NAVI server refused the request"}


def ensure_server(N, P: Path) -> tuple[int, str]:
    """The project's interface server, started quietly if it isn't running. -> (port, token)."""
    info = N.server_alive(P) if P.exists() else None
    if not info:
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                N.cmd_up(types.SimpleNamespace(host="none", task=None, port=7701, open=False, quiet=True, prompt="",
                                               ensure_session=False, page="menu", no_browser=True))
        except SystemExit:
            raise RuntimeError((err.getvalue().strip() or "the interface server didn't start").removeprefix("navi: "))
        info = N.server_alive(P)
        if not info:
            raise RuntimeError(f"the interface server didn't start - see {P / 'serve.log'}")
    return int(info["port"]), str(info.get("token") or "")


# ---------------------------------------------------------------- the session, rebuilt from its log

class Node:
    __slots__ = ("name", "color", "role", "model", "state", "text", "since", "pulse", "pulse_c", "thought", "thought_t", "x", "y")

    def __init__(self, name: str, color: str, role: str = ""):
        self.name, self.color, self.role, self.model = name, color, role, ""
        self.state, self.text, self.since = "idle", "", time.time()
        self.pulse, self.pulse_c = -99.0, color          # when something last arrived here (monotonic), and its colour
        self.thought, self.thought_t = "", -99.0
        self.x = self.y = 0.0                             # the chip's centre, in cells

    def label(self) -> str:
        return {"navi": "NAVI", "user": "YOU"}.get(self.name, self.name.upper())

    def mono(self) -> str:
        return {"user": "Y"}.get(self.name, (self.name[:1] or "?").upper())


class Item:
    """One feed entry: a head line, text that flows after it (and wraps under it), then indented body lines."""
    IND = 6

    def __init__(self, head: list, tail: tuple | None = None, body: tuple = ()):
        self.head, self.tail, self.body, self._w, self._lines = head, tail, list(body), -1, []

    def lines(self, w: int) -> list[list]:
        if w == self._w:
            return self._lines
        first, used = [], 0
        for text, st in self.head:
            text = fit(text, w - used)
            if text:
                first.append((text, st))
                used += tw(text)
        out = [first]
        if self.tail and self.tail[0]:
            text, st, most = self.tail
            room = w - used - 1
            if room >= 12:
                rows = wrap(text, w - self.IND, first=room) or [""]
                first.append((" " + rows[0], st))
                rows = rows[1:]
            else:
                rows = wrap(text, w - self.IND)
                most += 1
            for i, r in enumerate(rows[:most - 1]):
                last = i == most - 2 and len(rows) > most - 1
                out.append([(" " * self.IND + (fit(r + " …", w - self.IND) if last else r), st)])
        for text, st, most in self.body:
            rows = wrap(text, w - self.IND)
            for i, r in enumerate(rows[:most]):
                out.append([(" " * self.IND + (fit(r + " …", w - self.IND) if i == most - 1 and len(rows) > most else r), st)])
        self._w, self._lines = w, out
        return out


QUIET = ("host", "boot", "join", "leave", "policy", "council", "model", "reset", "resume", "upload", "trace", "pace")


class Council:
    """Everything about one session that the screen shows, rebuilt from log.jsonl and kept current by tailing it."""

    def __init__(self, P: Path, sid: str):
        self.P, self.sid, self.dir = P, sid, P / "sessions" / sid
        self.log, self.trace = self.dir / "log.jsonl", P / "hosts" / f"{sid}.trace.jsonl"
        self.pos, self.ino, self.seq = 0, None, 0
        try:
            self.tpos = self.trace.stat().st_size      # the moderator's trace: only what happens from now on
        except OSError:
            self.tpos = 0
        self.live = False                               # False while the history loads: the past doesn't animate
        self.hub = Node("navi", WHITE)
        self.nodes: dict[str, Node] = {}
        self.user: Node | None = None
        self.feed: list[Item] = []
        self.pending: dict[str, dict] = {}
        self.packets: list[dict] = []
        self.links: dict = {}
        self.signals: list = []
        self.task, self.council, self.pace, self.policy, self.name = "", "", "", "", sid
        self.mod: dict = {}
        self.started: float | None = None
        self.ended: dict | None = None
        self.end_t: float | None = None
        self.msgs, self.files, self.unread = 0, [], 0
        self.guard = (-99.0, OK)
        self.hub_own = 0.0
        try:
            meta = json.loads((self.dir / "session.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        self.task = oneline(meta.get("task", ""))
        self.pace = str(meta.get("pace_chosen") or meta.get("pace") or "")
        self.perms = str(meta.get("permissions") or "")
        self.name = oneline(meta.get("name") or sid)
        self.started = epoch(meta.get("started"))
        self.cost = meta.get("cost")

    # -- reading
    def load(self):
        self.tail()
        self.live = True

    def tail(self) -> bool:
        """Apply what was appended to the log (and the moderator's trace). True if anything happened."""
        got = False
        try:
            st = os.stat(self.log)
        except OSError:
            return False
        if self.ino is not None and (st.st_ino != self.ino or st.st_size < self.pos):
            live = self.live
            self.__init__(self.P, self.sid)           # the log was replaced: start over, quietly
            self.tail()
            self.live = live
            return True
        self.ino = st.st_ino
        if st.st_size > self.pos:
            with open(self.log, "rb") as f:
                f.seek(self.pos)
                chunk = f.read()
            end = chunk.rfind(b"\n")
            if end >= 0:
                for line in chunk[:end].splitlines():
                    try:
                        ev = json.loads(line)
                        seq = int(ev.get("seq") or 0)
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if seq > self.seq:
                        self.seq = seq
                        self.apply(ev)
                        got = True
                self.pos += end + 1
        try:
            size = self.trace.stat().st_size
        except OSError:
            size = 0
        if size < self.tpos:
            self.tpos = 0
        if size > self.tpos:
            with open(self.trace, "rb") as f:
                f.seek(self.tpos)
                chunk = f.read()
            end = chunk.rfind(b"\n")
            if end >= 0:
                for line in chunk[:end].splitlines():
                    try:
                        tr = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(tr, dict):
                        self.on_trace(tr)
                        got = True
                self.tpos += end + 1
        return got

    # -- the model
    def node(self, name) -> Node:
        name = str(name or "navi").lower()
        if name in ("navi", "all", ""):
            return self.hub
        if name == "user":
            if self.user is None:
                self.user = Node("user", WHITE, "you")
            return self.user
        n = self.nodes.get(name)
        if n is None:
            n = self.nodes[name] = Node(name, agent_color(name))
        return n

    def status(self, n: Node, state: str, text: str, ev: dict | None = None):
        n.state, n.text = state, text
        n.since = epoch((ev or {}).get("ts")) or time.time()

    def send(self, a: Node, b: Node, kind: str, color=None, delay: float = 0.0):
        """A packet from a to b. While the history loads it only warms the link."""
        if a is b:
            return
        color = color or KIND_COLOR.get(kind) or a.color
        if not self.live:
            self.links[frozenset((a.name, b.name))] = [a, b, color, -99.0]
            return
        self.packets.append({"a": a, "b": b, "kind": kind, "color": color, "t0": time.monotonic() + delay})

    def add(self, item: Item):
        self.feed.append(item)
        if len(self.feed) > 600:
            del self.feed[:100]
        if self.live:
            self.unread += 1

    def sys(self, ev: dict, text: str, color=MUTED):
        self.add(Item([(hhmm(ev.get("ts")) + " ", sty(DIM)), ("·", sty(DIM))], (text, sty(color), 2)))

    def who(self, name: str, bold=True) -> tuple:
        n = self.node(name) if name not in ("all",) else None
        label = "ALL" if name == "all" else n.label()
        return label, sty(n.color if n else INK, bold=bold)

    def apply(self, ev: dict):
        t, ts = ev.get("type"), ev.get("ts")
        agent = str(ev.get("agent") or "navi").lower()
        body = clean(ev.get("body") or "").strip()
        if self.hub.text == CONNECTING and t not in QUIET:
            self.hub.state, self.hub.text = "idle", ""
        tm = hhmm(ts) + " "
        if t == "boot":
            self.task, self.started = oneline(body) or self.task, epoch(ts) or self.started
            self.sys(ev, "session opened")
        elif t == "join":
            n = self.node(agent)
            n.color, n.role, n.model = agent_color(agent, str(ev.get("color") or "")), oneline(ev.get("role")), str(ev.get("model") or "")
            self.status(n, "idle", "connected", ev)
            n.pulse = time.monotonic() if self.live else -99.0
            last = self.feed[-1] if self.feed else None
            if last is not None and getattr(last, "joins", None) is not None:
                last.joins.append(agent)
                last.tail = (", ".join(last.joins) + " joined", sty(MUTED), 2)
                last._w = -1
            else:
                self.sys(ev, f"{agent} joined" + (f" · {n.model}" if n.model else ""))
                self.feed[-1].joins = [agent]
        elif t == "leave":
            self.nodes.pop(agent, None)
            self.links = {k: v for k, v in self.links.items() if agent not in k}
            self.packets = [p for p in self.packets if agent not in (p["a"].name, p["b"].name)]
            self.sys(ev, f"{agent} left")
        elif t == "status":
            n = self.node(agent)
            self.status(n, ev.get("state") if ev.get("state") in STATE_ICON else "working", oneline(body), ev)
            if n is self.hub:
                self.hub_own = time.time()
            if ev.get("state") == "blocked":
                self.add(Item([(tm, sty(DIM)), ("✕ ", sty(RED, bold=True)), self.who(agent), (" blocked", sty(RED))],
                              (oneline(body), sty(INK), 3)))
        elif t == "think":
            n = self.node(agent)
            n.thought, n.thought_t = oneline(body), time.monotonic() if self.live else -99.0
            if n.state in ("idle", "done"):
                self.status(n, "working", "thinking", ev)
            label, _ = self.who(agent)
            self.add(Item([(tm, sty(DIM)), (label, sty(mix(n.color, BG, .45)))], (oneline(body), sty(MUTED, italic=True), 3)))
        elif t == "message":
            self.on_message(ev, agent, body, tm)
        elif t == "ask":
            qid = str(ev.get("id") or "")
            a = self.node(agent)
            if a is not self.hub:
                self.status(a, "waiting", "needs you", ev)
            a.pulse, a.pulse_c = (time.monotonic(), AMBER) if self.live else (-99.0, AMBER)
            if qid and not self.ended:
                self.pending[qid] = ev
                if self.live:
                    self.signals.append(("ask", qid))
            opts = [oneline(o) for o in ev.get("options") or []]
            self.add(Item([(tm, sty(DIM)), ("◆ ", sty(AMBER, bold=True)), self.who(agent), (" asks you", sty(AMBER))],
                          (oneline(body), sty(INK), 4), [(" · ".join(opts), sty(MUTED), 2)] if opts else []))
        elif t == "permit":                 # a background moderator's tool call waits for your OK
            qid = str(ev.get("id") or "")
            a = self.node(agent)
            if a is not self.hub:
                self.status(a, "waiting", "waiting for your OK", ev)
            a.pulse, a.pulse_c = (time.monotonic(), AMBER) if self.live else (-99.0, AMBER)
            if qid:
                self.pending[qid] = ev
                if self.live:
                    self.signals.append(("ask", qid))
            self.add(Item([(tm, sty(DIM)), ("◆ ", sty(AMBER, bold=True)), self.who(agent), (" " + permit_verb(ev), sty(AMBER))],
                          (oneline(ev.get("why") or ev.get("plain") or body), sty(INK), 4),
                          [(oneline(ev.get("plain")), sty(MUTED), 2)] if ev.get("why") and ev.get("plain") else []))
        elif t == "permitted":
            self.pending.pop(str(ev.get("id") or ""), None)
            dec, rules = str(ev.get("decision") or ""), ", ".join(str(r) for r in ev.get("rules") or [])
            if agent == "user":
                self.send(self.node("user"), self.node(ev.get("to")), "reply")
            self.add(Item([(tm, sty(DIM)), ("YOU", sty(WHITE, bold=True)) if agent == "user" else self.who(agent)],
                          (PERMIT_WORDS.get(dec, dec) + (f" · {rules}" if dec == "always" and rules else ""),
                           sty(OK if dec in ("once", "always") else MUTED), 2)))
        elif t == "reply":
            self.pending.pop(str(ev.get("id") or ""), None)
            u, to = self.node("user"), self.node(ev.get("to"))
            self.send(u, to, "reply")
            if to is not self.hub and not self.ended:
                self.status(to, "working", "got your answer", ev)
            ans = oneline(ev.get("choice") or "") or oneline(re.sub(r"\n\nattachments \(read[\s\S]*$", "", body))
            self.add(Item([(tm, sty(DIM)), ("YOU", sty(WHITE, bold=True)), (" → ", sty(DIM)), self.who(str(ev.get("to") or "navi"))],
                          ("answered: " + ans, sty(INK), 3)))
        elif t == "artifact":
            a = self.node(agent)
            self.send(a, self.hub, "artifact")
            path = oneline(ev.get("src") or ev.get("path"))      # the real file in the project when there is one
            self.files.append(path)
            self.add(Item([(tm, sty(DIM)), ("▣ ", sty(KIND_COLOR["artifact"], bold=True)), self.who(agent), (" wrote", sty(MUTED))],
                          (path + (f" · {oneline(ev.get('title'))}" if ev.get("title") else ""), sty(KIND_COLOR["artifact"]), 2)))
        elif t == "policy":
            self.policy = oneline(ev.get("sensitivity"))
            self.guard = (time.monotonic() if self.live else -99.0, OK)
            self.add(Item([(tm, sty(DIM)), ("◈ ", sty(OK)), ("WARDEN", sty(mix(OK, BG, .3), bold=True))],
                          (f"{self.policy or 'policy'} data · perimeter up", sty(MUTED), 1)))
        elif t in ("gate", "ruling"):
            dec = str(ev.get("decision") or "")
            c = DECISION_COLOR.get(dec, INK)
            warden = self.nodes.get("warden") or self.hub
            if t == "gate":
                a = self.node(agent)
                if a is not warden:
                    self.send(a, warden, "gate", c)
                what = f"{oneline(ev.get('action'))} {oneline(ev.get('target'))}"
                head = [(tm, sty(DIM)), ("◈ ", sty(c)), self.who(agent, bold=False)]
            else:
                target = self.node(ev.get("for")) if ev.get("for") else self.hub
                if target is not warden:
                    self.send(warden, target, "ruling", c)
                what = f"ruled {dec}: {oneline(ev.get('action'))} {oneline(ev.get('target'))}"
                head = [(tm, sty(DIM)), ("◈ ", sty(c)), ("WARDEN", sty(mix(OK, BG, .3), bold=True))]
            if dec != "allow":
                self.guard = (time.monotonic() if self.live else -99.0, c)
            why = oneline(ev.get("reason") or body)
            self.add(Item(head, (f"{what} · {dec.upper() or '?'}" + (f" · {why}" if why and dec != "allow" else ""),
                                 sty(c if dec != "allow" else MUTED), 1 if dec == "allow" else 3)))
        elif t == "redact":
            a = self.node(agent)
            a.pulse, a.pulse_c = (time.monotonic(), RED) if self.live else (-99.0, RED)
            self.guard = (time.monotonic() if self.live else -99.0, RED)
            n = int(ev.get("count") or 0)
            self.add(Item([(tm, sty(DIM)), ("◈ ", sty(RED)), ("WARDEN", sty(RED, bold=True))],
                          (f"{'blocked' if ev.get('blocked') else 'removed'} {n} sensitive item{'s' * (n != 1)} from {agent}"
                           + (f" · {oneline(body)}" if body else ""), sty(RED), 2)))
        elif t == "host":
            self.mod = {k: str(ev.get(k) or "") for k in ("host", "model", "effort", "mode")}
            if ev.get("mode") == "off":
                self.status(self.hub, "done" if self.ended else "idle", "finished" if self.ended else "paused", ev)
                for k in [k for k, p in self.pending.items() if p.get("type") == "permit"]:
                    self.pending.pop(k, None)          # nobody is waiting for these any more
            elif not ev.get("pending"):
                self.status(self.hub, "working", CONNECTING, ev)
            self.sys(ev, oneline(body) or "moderator")
        elif t == "council":
            self.council = oneline(ev.get("title") or ev.get("name"))
            self.sys(ev, f"council: {self.council}")
        elif t == "pace":
            self.pace = str(ev.get("pace") or self.pace)
            self.sys(ev, oneline(body) or f"pace: {self.pace}")
        elif t == "model":
            n = self.nodes.get(agent)
            if n:
                n.model = str(ev.get("model") or "")
            self.sys(ev, f"{agent} now on {ev.get('model') or 'the moderator model'}")
        elif t == "roster":
            self.sys(ev, f"{agent}: {oneline(ev.get('action'))} · {oneline(body)}".rstrip(" ·"))
        elif t == "resume":
            self.sys(ev, "session resumed")
        elif t == "next":
            self.sys(ev, f"continued in session {oneline(ev.get('session'))} ↗", CYAN)
            if self.live and ev.get("session"):
                self.signals.append(("next", str(ev["session"])))
        elif t == "chat":                  # after the end: NAVI answers you directly, one agent
            self.add(Item([(tm, sty(DIM)), ("NAVI", sty(CYAN, bold=True)), (" → ", sty(DIM)), ("YOU", sty(WHITE, bold=True))],
                          None, [(line, sty(INK), 80) for line in body.splitlines() if line.strip()] or [("", sty(INK), 3)]))   # in full
            self.status(self.hub, "done", "answered you", ev)
        elif t == "branch":
            self.add(Item([(tm, sty(DIM)), ("⎇ ", sty(CYAN)), (("new branch " if ev.get("created") else "switched to ") + oneline(ev.get("branch")), sty(CYAN, bold=True))],
                          (f"from {oneline(ev.get('from'))}", sty(MUTED), 2)))
        elif t == "notice":                # something you should know, from NAVI itself (auto mode is off, say)
            self.add(Item([(tm, sty(DIM)), ("! ", sty(AMBER, bold=True)), (oneline(ev.get("title")) or "note", sty(AMBER, bold=True))],
                          None, [(line, sty(INK), 6) for line in body.splitlines() if line.strip()] or [("", sty(INK), 1)]))
        elif t == "upload":
            if body:
                self.add(Item([(tm, sty(DIM)), ("◈ ", sty(AMBER)), ("WARDEN", sty(AMBER, bold=True))], (oneline(body), sty(AMBER), 2)))
        elif t == "end":
            self.ended, self.end_t = ev, epoch(ts) or time.time()
            for i, n in enumerate(self.nodes.values()):
                self.send(n, self.hub, "verdict", delay=i * .12)
                self.status(n, "offline", "offline", ev)       # the council goes offline: from here it's a chat with NAVI
            self.status(self.hub, "done", "finished", ev)
            self.pending.clear()
            mine = ev.get("by") == "user"                       # you closed it yourself: no CONSENSUS screen
            self.add(Item([(tm, sty(DIM)), ("✓ CLOSED" if mine else "✓ CONSENSUS", sty(OK, bold=True))], (oneline(body), sty(INK), 4)))
            if self.live and not mine:
                self.signals.append(("end", None))

    def on_message(self, ev: dict, agent: str, body: str, tm: str):
        kind, to = str(ev.get("kind") or "note"), str(ev.get("to") or "navi").lower()
        a = self.node(agent)
        if to == "all":
            targets = [n for n in self.nodes.values() if n is not a] or [self.hub]
        else:
            targets = [self.node(to)]
        for i, b in enumerate(targets):
            self.send(a, b, kind, delay=i * .14)
        self.msgs += 1
        subject = oneline(ev.get("subject"))
        text = re.sub(r"\n\nattachments \(read[\s\S]*$", "", body).strip()
        if agent == "user":
            intent = str(ev.get("intent") or "message")
            tag = [] if intent == "message" else [(" " + intent.upper(), sty(CYAN, bold=True))]
            self.add(Item([(tm, sty(DIM)), ("YOU", sty(WHITE, bold=True)), (" → ", sty(DIM)), self.who(to)] + tag,
                          (oneline(text) or subject, sty(INK), 4)))
            return
        label, color = KIND_LABEL.get(kind, kind.upper()), KIND_COLOR.get(kind, INK)
        if kind == "verdict":
            s = f"{subject} {text}".lower()
            label, color = (("NEEDS WORK", RED) if "needs work" in s else ("APPROVE · CONDITIONS", AMBER) if "condition" in s
                            else ("APPROVE", OK) if "approv" in s else ("VERDICT", WHITE))
            if self.pace == "quick":            # in QUICK the lead checks through this lens itself: say so
                label = "QUICK CHECK · " + label
        rest = oneline(text)
        self.add(Item([(tm, sty(DIM)), self.who(agent), (" → ", sty(DIM)), self.who(to, bold=False), ("  " + label, sty(color, bold=True))],
                      None, [(subject, sty(INK, bold=True), 3)] + ([(rest, sty(MUTED), 2)] if rest and rest != subject else [])))

    def on_trace(self, tr: dict):
        """What the background Claude Code is doing right now: shown on the hub while it hasn't said so itself."""
        if tr.get("kind") == "tool" and not self.ended and time.time() - self.hub_own > 20:
            self.hub.state, self.hub.text = "working", f"{oneline(tr.get('tool')).lower()} · {oneline(tr.get('text'))}"
            self.hub.since = time.time()


# ---------------------------------------------------------------- the terminal

class Term:
    """The tty: raw keys, the alternate screen, no cursor, no line wrap. leave() always puts everything back."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.saved = None
        self.resized = False
        self._old: dict = {}

    def write(self, s: str):
        try:
            sys.stdout.buffer.write(s.encode("utf-8", "replace"))
            sys.stdout.buffer.flush()
        except (OSError, ValueError):     # the terminal went away (SIGHUP): nothing left to draw on
            pass

    def size(self) -> tuple[int, int]:
        try:
            c, r = os.get_terminal_size(sys.stdout.fileno())
        except OSError:
            c, r = 80, 24
        return max(1, c), max(1, r)

    def enter(self):
        self.saved = termios.tcgetattr(self.fd)
        a = termios.tcgetattr(self.fd)
        a[0] &= ~(termios.BRKINT | termios.ICRNL | termios.INPCK | termios.ISTRIP | termios.IXON)
        a[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)   # ctrl-c / ctrl-z arrive as keys
        a[6][termios.VMIN], a[6][termios.VTIME] = 1, 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.write("\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[?2004h\x1b[0m\x1b[2J")

    def leave(self):
        if self.saved is None:
            return
        self.write("\x1b[0m\x1b[?2004l\x1b[?7h\x1b[?25h\x1b[?1049l")
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        except termios.error:
            pass
        self.saved = None

    def signals(self):
        def winch(*_):
            self.resized = True

        def bye(signum, _):
            raise SystemExit(128 + signum)
        for s, h in ((signal.SIGWINCH, winch), (signal.SIGTERM, bye), (signal.SIGHUP, bye)):
            self._old[s] = signal.signal(s, h)

    def restore_signals(self):
        for s, h in self._old.items():
            signal.signal(s, h)
        self._old = {}

    def suspend(self):
        """ctrl-z: give the shell its terminal back, stop, and come back drawn from scratch after `fg`."""
        self.leave()
        os.kill(os.getpid(), signal.SIGTSTP)
        self.enter()


# ---------------------------------------------------------------- the app

class App:
    FPS = 18

    def __init__(self, N, P: Path, api: Api, session: str | None):
        self.N, self.P, self.api = N, P, api
        self.project = N.project_root(P)
        self.branch = git_branch(self.project)
        self.term = Term()
        self.scr = Screen(self.term.write)
        self.jobs: Queue = Queue()
        self.done = False
        self.farewell = ""
        self.view, self.overlay = "start", None
        self.c: Council | None = None
        self.st: dict = {}                  # the last GET /status for the session
        self.st_t = 0.0
        self.link = True                    # False while the server doesn't answer
        self.flash_msg, self.flash_c, self.flash_t = "", MUTED, 0.0
        # the start form
        self.field = 0
        self.task = TextEdit()
        self.atts: list[dict] = []          # files and images dropped onto the start form (uploaded as they arrive)
        self.task_big = False               # ctrl+o: the task gets most of the screen
        self.picker: dict | None = None     # FOLDER and BRANCH: a list to choose from, or a line to type
        self.councils: list[dict] = []
        self.ci = 0
        self.pace, self.model, self.effort, self.agents, self.perms = "auto", "", "", "", "ask"
        self.engine, self.engines = os.environ.get("NAVI_ENGINE", ""), []       # `navi --engine X tui` starts on X
        self.demo = False                   # `navi tui --demo`: a scripted council, nothing runs for real
        self.open_s: dict | None = None
        self.n_open, self.endall_armed = 0, False         # END ALL SESSIONS on the start screen: how many, and "press again"
        self.err, self.launching, self.start_t = "", False, time.monotonic()
        # the session view
        self.input = TextEdit(limit=8000)
        self.sug_i, self.sug_key, self.sug_off = 0, None, None       # the @agent / /command suggestions while you type
        self.say_atts: list[dict] = []      # files dropped onto the console, sent with the next message
        self.focus = False
        self.scroll = 0
        self.ask_id, self.ask_i, self.ask_text, self.ask_err, self.ask_mode = None, 0, TextEdit(limit=8000), "", "options"
        self.ask_scroll, self.ask_more = 0, (False, False)        # a long question scrolls (PgUp/PgDn)
        self.ask_raw = False                                        # a card shows the command itself on c
        self.ask_atts: list[dict] = []      # files dropped into an answer
        self.sending = False
        self.cons_t = 0.0
        self.end_at = None
        self.follow = None
        self.session = session

    # -- plumbing
    def job(self, fn, then=None):
        """Run fn in the background (HTTP can be slow); `then(result)` runs on the main thread when it's done."""
        def run():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001 - surfaced on screen
                res = {"ok": False, "error": str(e)}
            self.jobs.put((then, res))
        threading.Thread(target=run, daemon=True).start()

    def drain(self):
        while True:
            try:
                then, res = self.jobs.get_nowait()
            except Empty:
                return
            if then:
                then(res)

    def flash(self, msg: str, color=MUTED):
        self.flash_msg, self.flash_c, self.flash_t = msg, color, time.monotonic()

    def working(self) -> bool:
        return bool(self.c and not self.c.ended and self.st.get("host"))

    # -- the loop
    def run(self):
        t = self.term
        t.signals()
        try:
            t.enter()
            self.keys = Keys(t.fd)
            if self.session:
                self.attach(self.session)
            else:
                self.open_start()
            nxt = 0.0
            while not self.done:
                now = time.monotonic()
                try:
                    ready = select.select([t.fd], [], [], max(0.0, nxt - now))[0]
                except InterruptedError:
                    ready = []
                if ready:
                    for k in self.keys.read():
                        self.on_key(k)
                        if self.done:
                            break
                self.drain()
                self.tick()
                if t.resized:
                    t.resized = False
                    self.scr.invalidate()
                now = time.monotonic()
                if ready or now >= nxt:
                    self.draw()
                    nxt = now + 1 / self.fps()
        except EOFError:
            pass
        finally:
            t.leave()
            t.restore_signals()

    def fps(self) -> int:
        """Full speed while something moves; the slow rings alone don't need it."""
        c, now = self.c, time.monotonic()
        if self.view == "consensus":
            return self.FPS if now - self.cons_t < 2 else 8      # the banner decodes, then only glitches now and then
        if self.view != "session" or not c or c.packets or self.focus:
            return self.FPS
        last = max([c.hub.pulse] + [n.pulse for n in c.nodes.values()] + [n.thought_t for n in c.nodes.values()])
        return self.FPS if now - last < 1.5 else 10

    def tick(self):
        now = time.monotonic()
        c = self.c
        if c and self.view in ("session", "consensus"):
            c.tail()
            for sig, arg in c.signals:
                if sig == "ask" and arg not in c.pending:
                    continue                          # already answered (in the same batch, or in the browser)
                if sig == "ask" and self.overlay is None and not (self.focus and self.input.text):
                    self.open_ask(arg)
                elif sig == "ask":
                    pev = c.pending[arg]
                    self.flash(f"◆ {str(pev.get('agent') or 'navi').upper()} "
                               f"{permit_verb(pev) if pev.get('type') == 'permit' else 'asks you'} · a to answer", AMBER)
                elif sig == "end":
                    self.end_at = now + 1.6           # let the last packets land first
                elif sig == "next":
                    self.follow = (now + 1.5, arg)
            c.signals.clear()
            if self.ask_id and self.ask_id not in c.pending:      # answered elsewhere (the browser) or the session ended
                self.overlay = None if self.overlay == "ask" else self.overlay
                self.ask_id = None
            if self.end_at and now >= self.end_at:
                self.end_at = None
                if self.view == "session" and self.overlay in (None, "help"):
                    self.overlay = None
                    self.show_consensus()
            if self.follow and now >= self.follow[0]:
                sid = self.follow[1]
                self.follow = None
                if self.N.SID.match(sid) and (self.P / "sessions" / sid / "log.jsonl").exists():
                    self.attach(sid)
            if now - self.st_t > 2.0:
                self.st_t = now
                sid = c.sid
                self.job(lambda: self.api.get(f"/status?session={sid}"), lambda r, sid=sid: self.got_status(sid, r))

    def got_status(self, sid: str, r):
        if not self.c or self.c.sid != sid:
            return
        self.link = isinstance(r, dict) and r.get("ok") is not False
        if not self.link:
            return
        self.st = r
        s = r.get("session") or {}
        c = self.c
        c.cost = s.get("cost") or c.cost
        if s.get("pace") in self.N.PACES:
            c.pace = s["pace"]
        if s.get("permissions") in self.N.PERMISSION_LEVELS:
            c.perms = s["permissions"]
        if (r.get("council") or {}).get("title"):
            c.council = oneline(r["council"]["title"])

    # -- keys
    def on_key(self, k):
        if k == "ctrl-z":
            self.term.suspend()
            self.scr.invalidate()
            return
        if k == "ctrl-l":
            self.scr.invalidate()
            return
        if self.overlay == "quit":
            if k in ("y", "Y", "enter", "q", "ctrl-c"):
                self.quit()
            elif k in ("n", "N", "esc"):
                self.overlay = None
            return
        if self.overlay == "help":
            self.overlay = None
            return
        if self.overlay == "chatintro":       # any key: got it (once; `navi --onboarding` shows it again)
            self.overlay = None
            self.job(lambda: self.api.post("/settings", {"chat_intro_seen": True}), lambda r: None)
            return
        if self.overlay == "ask":
            return self.key_ask(k)
        if self.view == "start" and self.picker:
            return self.key_picker(k)
        if self.view == "start":
            return self.key_start(k)
        if self.view == "consensus":
            if self.demo and k in ("o", "O"):
                return self.open_demo_page()
            if k in ("n", "N") and self.demo:
                self.flash("this is the demo · q leaves, then run navi for a real council", AMBER)
            elif k in ("n", "N"):
                self.open_start()
            elif k in ("q", "Q", "ctrl-c", "ctrl-d"):
                self.ask_quit()
            elif k in ("v", "V", "esc", "enter"):
                self.view, self.focus = "session", k == "enter"     # OK: straight into the chat with NAVI
                self.chat_intro()
            return
        self.key_session(k)

    def ask_quit(self):
        if self.demo:
            return self.quit()            # nothing keeps running after the demo
        if self.view in ("session", "consensus") and self.working():
            self.overlay = "quit"
        else:
            self.quit()

    def quit(self):
        self.done = True
        if self.c and self.working():
            self.farewell = (f"navi: the council keeps working in the background · `navi tui --session {self.c.sid}` "
                             f"or the web interface brings you back")

    # -- start screen
    def change_dir(self, arg: str):
        """`/cd <folder>`: work in another project folder (its own NAVI server, started if needed), from the start screen."""
        here = self.N.project_root(self.P)
        if not arg:
            return self.flash(f"you are in {self.N.tilde(here)} · /cd <folder> works somewhere else", CYAN)
        target = Path(arg).expanduser()
        target = (target if target.is_absolute() else here / target).resolve()
        if not target.is_dir():
            return self.flash(f"there's no folder {arg}", RED)
        if target in (Path.home().resolve(), Path(target.anchor)):
            return self.flash("pick a project folder, not your whole disk or home folder", RED)
        try:
            P2 = self.N.ensure_project(self.N.project_dir(target))      # its data in ~/.navi/projects, never in the folder
            os.environ["NAVI_DIR"] = str(P2)
            os.chdir(target)
            port, token = ensure_server(self.N, P2)
        except (OSError, RuntimeError) as e:
            return self.flash(str(e), RED)
        self.P, self.api = P2, Api(P2, port, token)
        self.N.remember_project(target)
        self.open_start()
        self.flash(f"now working in {self.N.tilde(target)}", OK)

    def open_start(self):
        self.view, self.overlay, self.c, self.st = "start", None, None, {}
        self.field, self.err, self.launching, self.start_t = 0, "", False, time.monotonic()
        self.task.set("")
        self.job(self.load_start, self.got_start)

    def load_start(self):
        return {"councils": (self.api.get("/councils") or {}).get("councils") or [], "status": self.api.get("/status") or {},
                "sessions": self.api.get("/sessions") or []}

    def got_start(self, r):
        if r.get("ok") is False:
            self.err = f"the NAVI server isn't answering: {r.get('error')}"
            return
        self.councils = [c for c in r["councils"] if isinstance(c, dict) and c.get("name")]
        self.update = (r["status"] or {}).get("update") or {}
        last = (r["status"] or {}).get("last") or {}
        names = [c["name"] for c in self.councils]
        want = last.get("council") if last.get("council") in names else next((c["name"] for c in self.councils if c.get("default")), "")
        self.ci = names.index(want) if want in names else 0
        self.pace = last.get("pace") if last.get("pace") in self.N.PACES else "auto"
        dp = (r["status"] or {}).get("permissions")
        self.perms = dp if dp in self.N.PERMISSION_LEVELS else "auto"
        self.engines = [e for e in (r["status"] or {}).get("engines") or [] if isinstance(e, dict) and e.get("on", e.get("installed"))]   # the ones you use
        ids = [e["id"] for e in self.engines if e.get("ready")]
        self.engine = self.engine if self.engine in ids else (r["status"] or {}).get("engine") if (r["status"] or {}).get("engine") in ids else (ids[0] if ids else "")
        self.model = last.get("model") if last.get("model") in self.models() else ""
        self.effort = last.get("effort") if last.get("effort") in EFFORTS else ""
        self.council_defaults()
        cur = next((s for s in r["sessions"] if isinstance(s, dict) and s.get("current")), None)
        self.open_s = cur if cur and not cur.get("ended") else None
        self.n_open = sum(1 for x in r["sessions"] if isinstance(x, dict) and not x.get("ended"))
        if not ids:
            e = next((e for e in self.engines if e["id"] == (r["status"] or {}).get("engine")), {})
            self.err = f"{e.get('name', 'Your engine')} can't run yet: {e.get('why') or 'nothing is installed'} (`navi engine` sets it up)"

    def eng(self, eid: str = "") -> dict:
        eid = eid or self.engine
        return next((e for e in self.engines if e.get("id") == eid), {}) or next((e for e in (self.st or {}).get("engines") or [] if e.get("id") == eid), {})

    def models(self) -> list[str]:
        return list(self.N.MODERATOR_MODELS["claude"]) if (self.engine or "claude") == "claude" else ["", *TIERS]

    def model_label(self, m: str, eid: str = "") -> tuple[str, str]:
        e = self.eng(eid)
        if not e or e.get("id") == "claude":
            return (m or "default"), MODEL_INFO.get(m, "")
        t = TIER_OF.get(m)
        return (t, (e.get("tiers") or {}).get(t) or "its default") if t else ((m or "default"), "" if m else f"{e.get('name')}'s default")

    def fields(self) -> list[str]:
        eng = ["engine"] if len([e for e in self.engines if e.get("ready")]) > 1 else []
        eff = ["effort"] if (self.eng() or {}).get("efforts", ["low"]) else []
        return (["task", "files", "folder"] + (["branch"] if self.branch else [])
                + ["council", "pace", *eng, "model", *eff, "agents", "perms", "start"] + (["continue"] if self.open_s else [])
                + (["endall"] if self.n_open else []) + ["quit"])

    def key_start(self, k):
        if self.launching:
            if k in ("ctrl-c", "esc"):
                self.quit()
            return
        fs = self.fields()
        self.field = min(self.field, len(fs) - 1)
        f = fs[self.field]
        if k == "esc" and self.task_big:
            self.task_big = False
            return
        if k in ("esc", "ctrl-c") or (k == "ctrl-d" and not self.task.text):
            return self.quit()
        if isinstance(k, tuple) and k[0] == "paste" and dropped_files(k[1]):     # a file or image dragged onto the terminal
            return self.add_files(dropped_files(k[1]), self.atts)
        if k == "ctrl-v" or (isinstance(k, tuple) and k[0] == "paste" and not k[1].strip()):   # an image (or a copied file)
            return self.paste_clipboard(self.atts)
        if f in ("folder", "branch") and k in ("enter", "right", " "):
            return self.open_picker(f)
        if f == "files" and k in ("bs", "del"):
            if self.atts:
                self.atts.pop()
            return
        if k == "ctrl-o":
            self.field, self.task_big = 0, not self.task_big
            return
        if k == "ctrl-g":
            self.field = 0
            return self.edit_outside(self.task)
        if f == "task" and k in ("up", "down") and self.task.key(k):
            return                                                      # a line up or down inside a long task
        if k in ("up", "btab", "down", "tab"):
            self.endall_armed = False
        if k in ("up", "btab"):
            self.field = (self.field - 1) % len(fs)
        elif k in ("down", "tab"):
            self.field = (self.field + 1) % len(fs)
        elif k == "enter" and f == "quit":
            self.quit()
        elif k == "enter" and f == "endall":
            if not self.endall_armed:
                self.endall_armed = True            # one more ⏎: it ends every open session here
                return
            self.endall_armed = False
            n = self.n_open

            def done(r):
                ok, data = r if isinstance(r, tuple) else (False, r)
                if ok:
                    self.flash(f"ended {data.get('closed', n)} session{'s' * (data.get('closed', n) != 1)} · nothing deleted, any can be resumed", OK)
                    self.job(self.load_start, self.got_start)
                else:
                    self.flash(data.get("error", "that didn't work"), RED)
            self.job(lambda: self.api.post("/sessions/end", {"which": "all"}), done)
        elif k == "enter":
            self.task_big = False
            self.launch("continue" if f == "continue" else "new")
        elif f in ("council", "pace", "engine", "model", "effort", "agents", "perms") and k in ("left", "right", " "):
            self.cycle(f, -1 if k == "left" else 1)
        elif f == "task" and k == "bs" and not self.task.text and self.atts:
            self.atts.pop()                                             # backspace on an empty task: the last attachment goes
        elif f == "task":
            self.task.key(k)
            self.err = ""
        elif isinstance(k, tuple) or (len(k) == 1 and k != " ") or k in NEWLINE_KEYS:     # typing anywhere edits the task
            self.field = 0
            self.task.key(k)

    # -- FOLDER and BRANCH: where the council works, switched right here
    def open_picker(self, what: str):
        self.picker = {"what": what, "title": "Work in another folder" if what == "folder" else "Switch branch", "items": [],
                       "i": 0, "input": None, "loading": True, "err": ""}

        def got(r):
            ok, data = r if isinstance(r, tuple) else (False, r)
            pk = self.picker
            if not pk:
                return
            pk["loading"] = False
            if not ok:
                pk["err"] = data.get("error") or "couldn't load them"
                return
            if what == "folder":
                pk["items"] = [(x["path"], x["tilde"], f"{x['sessions']} session{'s' if x['sessions'] != 1 else ''}"
                                + (f" · ⎇ {x['branch']}" if x.get("branch") else "")) for x in data.get("recent") or [] if not x.get("current")]
                pk["items"].append(("", "✎ type a path", "any folder on this machine"))
            else:
                pk["items"] = [(b["name"], ("● " if b.get("current") else "  ") + b["name"], b.get("when", "")) for b in data.get("branches") or []]
                pk["items"].append(("", "+ a new branch from here", "named as you like"))
                if data.get("live"):
                    pk["err"] = "a council is working in this folder: switching waits until it's done"
        self.job(lambda: self.api.post("/workspace" if what == "folder" else "/workspace/branches", {}), got)

    def key_picker(self, k):
        pk = self.picker
        if pk["input"] is not None:              # typing a path or a branch name
            if k == "esc":
                pk["input"], pk["err"] = None, ""
            elif k == "enter":
                self.pick(pk["input"].text.strip(), typed=True)
            else:
                pk["input"].key(k)
                pk["err"] = ""
            return
        n = len(pk["items"])
        if k in ("esc", "ctrl-c", "left"):
            self.picker = None
        elif k == "up" and n:
            pk["i"] = (pk["i"] - 1) % n
        elif k == "down" and n:
            pk["i"] = (pk["i"] + 1) % n
        elif k in ("enter", "right") and n:
            value = pk["items"][pk["i"]][0]
            if value:
                self.pick(value)
            else:
                pk["input"] = LineEdit("~/" if pk["what"] == "folder" else "")

    def pick(self, value: str, typed: bool = False):
        pk = self.picker
        if not value:
            pk["err"] = "type it first"
            return
        if pk["what"] == "folder":
            root = Path(value).expanduser()
            try:
                root = root.resolve(strict=True)
            except (OSError, RuntimeError):
                pk["err"] = "that folder doesn't exist"
                return
            if not root.is_dir():
                pk["err"] = "that's a file, not a folder"
            elif root in (Path(root.anchor), Path.home().resolve()):
                pk["err"] = "pick a project folder, not your whole disk or home folder"
            elif root == self.project.resolve():
                self.picker = None
            else:
                self.switch_folder(root)
            return
        body = {"branch": value, **({"create": True} if typed else {})}

        def done(r):
            ok, data = r if isinstance(r, tuple) else (False, r)
            if not ok:
                if self.picker:
                    self.picker["err"] = data.get("error") or "couldn't switch"
                return
            self.branch = git_branch(self.project)
            self.picker = None
        self.job(lambda: self.api.post("/workspace/branch", body), done)

    def switch_folder(self, root: Path):
        """A NAVI per folder: this TUI starts again in that one (its own server, sessions and branch)."""
        self.term.leave()
        os.chdir(root)
        os.environ["NAVI_DIR"] = str(self.N.project_dir(root))
        for k in ("NAVI_SESSION", "NAVI_HOST_ID"):
            os.environ.pop(k, None)
        os.execv(sys.executable, [sys.executable, str(Path(self.N.__file__).resolve()), "tui"])

    def draw_picker(self):
        s, W, H, pk = self.scr, self.scr.w, self.scr.h, self.picker
        bw = min(76, W - 6)
        iw = bw - 6
        rows = len(pk["items"]) if not pk["loading"] else 1
        bh = 4 + max(1, min(rows, H - 14)) + (2 if pk["input"] is not None else 0) + (2 if pk["err"] else 0) + 2
        x0, y0 = (W - bw) // 2, max(1, (H - bh) // 2)
        self.box(x0, y0, bw, bh, CYAN)
        s.put(x0 + 3, y0 + 1, pk["title"], sty(CYAN, bold=True))
        here = home(self.project) if pk["what"] == "folder" else self.branch
        s.put(x0 + 3 + tw(pk["title"]) + 2, y0 + 1, fit(f"now: {here}", iw - tw(pk["title"]) - 2), sty(MUTED))
        y = y0 + 3
        if pk["loading"]:
            s.put(x0 + 3, y, "…", sty(MUTED))
            y += 1
        top = max(0, pk["i"] - (H - 15))
        for i, (value, label, desc) in enumerate(pk["items"][top:top + max(1, H - 14)], top):
            on = i == pk["i"] and pk["input"] is None
            s.put(x0 + 3, y, "▸" if on else " ", sty(RED, bold=True))
            x = s.put(x0 + 5, y, fit(label, iw - 22), sty(INK, bold=True) if on else sty(INK))
            s.put(max(x + 2, x0 + bw - 3 - min(26, tw(desc))), y, fit(desc, 26), sty(MUTED if on else DIM))
            y += 1
        if pk["input"] is not None:
            y += 1
            x = s.put(x0 + 3, y, "› ", sty(RED, bold=True))
            pk["input"].draw(s, x, y, iw - 2, sty(INK, bold=True), True, "~/code/project" if pk["what"] == "folder" else "feature/name", sty(DIM))
            y += 1
        if pk["err"]:
            y += 1
            s.put(x0 + 3, y, fit(pk["err"], iw), sty(AMBER))
            y += 1
        y += 1
        self.hints(y, [("↑↓", "choose"), ("⏎", "go"), ("esc", "back")] if pk["input"] is None else [("⏎", "go"), ("esc", "back")], x=x0 + 3, w=iw)

    def paste_clipboard(self, into: list, session: str = ""):
        """ctrl+v: the clipboard's image (or copied files) as attachments; a terminal can't paste an image by itself."""
        def got(r):
            files, why = r if isinstance(r, tuple) else ([], str(r))
            if files:
                self.add_files(files, into, session)
            elif self.view == "start":
                self.err = why
            else:
                self.flash(why, AMBER)
        self.job(clipboard_files, got)

    def add_files(self, files: list, into: list, session: str = ""):
        """Upload dropped files as attachments: a chip each, uploading, then ready (or why not)."""
        for f in files:
            item = {"name": f.name, "state": "uploading"}
            into.append(item)

            def done(r, item=item, f=f):
                if f.name.startswith("pasted-image-") and f.parent == Path(tempfile.gettempdir()):
                    f.unlink(missing_ok=True)       # the clipboard's image: uploaded, so the temporary copy goes
                ok, data = r if isinstance(r, tuple) else (False, r)
                if ok and data.get("path"):
                    item.update(state="ok", path=data["path"], name=data.get("name") or item["name"], kind=data.get("kind", ""),
                                size=int(data.get("size") or 0), warning=data.get("warning", ""))
                else:
                    item.update(state="error", error=data.get("error") or "the upload failed")
            self.job(lambda f=f: self.api.upload(f, session), done)

    def edit_outside(self, field: "TextEdit"):
        """ctrl+g: the text in your own editor ($VISUAL, $EDITOR, else nano or vi), back here when you close it."""
        ed = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("nano" if shutil.which("nano") else "vi")
        with tempfile.NamedTemporaryFile("w+", suffix=".md", prefix="navi-task-", delete=False, encoding="utf-8") as f:
            f.write(field.text)
            path = f.name
        self.term.leave()
        try:
            subprocess.run(ed.split() + [path])
            field.set(open(path, encoding="utf-8").read().rstrip("\n"))
        except (OSError, ValueError) as e:
            self.err = f"couldn't open {ed}: {e}"
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
            self.term.enter()
            self.scr.invalidate()           # draw everything again after the editor

    def chips(self, items: list) -> list[tuple[str, str]]:
        """Attachments as chips: name and size, uploading, or what went wrong."""
        out = []
        for a in items:
            if a["state"] == "uploading":
                out.append((f"⧗ {a['name']}", sty(MUTED)))
            elif a["state"] == "error":
                out.append((f"✕ {a['name']}: {a.get('error', '')}", sty(RED)))
            else:                   # the same marks as the web's chips: an image, a PDF, any other file
                kb, mark = a.get("size", 0) / 1024, {"image": "▣", "pdf": "⧉"}.get(a.get("kind", ""), "▤")
                out.append((f"{mark} {a['name']} {kb / 1024:.1f} MB" if kb >= 1024 else f"{mark} {a['name']} {max(1, round(kb))} KB",
                            sty(AMBER if a.get("warning") else CYAN)))
        return out

    def council_defaults(self):
        """What the chosen council starts with (Councils > When it starts), where it says anything; the form shows it."""
        c = self.councils[self.ci] if self.councils else {}
        ids = [e["id"] for e in self.engines if e.get("ready")]
        if c.get("engine") in ids:
            self.engine = c["engine"]
        if c.get("pace") in self.N.PACES:
            self.pace = c["pace"]
        m = c.get("model") or ""
        m = {"strong": "opus", "balanced": "sonnet", "fast": "haiku"}.get(m, m) if self.engine == "claude" else TIER_OF.get(m, m)
        self.model = m if m and m in self.models() else self.model if self.model in self.models() else ""
        if c.get("effort") in EFFORTS:
            self.effort = c["effort"]
        if c.get("permissions") in self.N.PERMISSION_LEVELS:
            self.perms = c["permissions"]

    def cycle(self, f: str, d: int):
        if f == "council" and self.councils:
            self.ci = (self.ci + d) % len(self.councils)
            self.council_defaults()
        elif f == "pace":
            ps = list(self.N.PACES)
            self.pace = ps[(ps.index(self.pace) + d) % len(ps)]
        elif f == "engine":
            ids = [e["id"] for e in self.engines if e.get("ready")]
            if ids:
                self.engine = ids[(ids.index(self.engine) + d) % len(ids)] if self.engine in ids else ids[0]
                self.model = self.model if self.model in self.models() else ""
        elif f == "model":
            ms = self.models()
            self.model = ms[(ms.index(self.model) + d) % len(ms)] if self.model in ms else ms[0]
        elif f == "effort":
            self.effort = EFFORTS[(EFFORTS.index(self.effort) + d) % len(EFFORTS)] if self.effort in EFFORTS else ""
        elif f == "agents":       # the council's models · NAVI picks per task · all on the moderator's
            modes = ["", "auto", "moderator"]
            self.agents = modes[(modes.index(self.agents) + d) % len(modes)] if self.agents in modes else ""
        elif f == "perms":
            ps = list(self.N.PERMISSION_LEVELS)
            self.perms = ps[(ps.index(self.perms) + d) % len(ps)] if self.perms in ps else ps[0]

    def launch(self, action: str):
        if action == "new" and not self.councils:
            self.err = "still loading the councils · try again in a second"
            return
        body = {"action": action, "mode": "headless", "model": self.model, "effort": self.effort, "permissions": self.perms}
        if action == "new":
            body["engine"] = self.engine
            if any(a["state"] == "uploading" for a in self.atts):
                self.err = "still uploading an attachment · a second"
                return
            body.update(task=self.task.text.strip(), council=self.councils[self.ci]["name"] if self.councils else "", pace=self.pace,
                        agent_models=self.agents, attachments=[{"path": a["path"], "name": a["name"]} for a in self.atts if a["state"] == "ok"])
        else:
            body["target"] = (self.open_s or {}).get("id", "")
        self.launching, self.err = True, ""
        self.job(lambda: self.api.post("/launch", body), self.launched)

    def launched(self, r):
        ok, data = r if isinstance(r, tuple) else (False, r)
        self.launching = False
        if not ok or not data.get("session"):
            self.err = data.get("error") or "the launch failed"
            return
        self.attach(str(data["session"]))

    # -- the session
    def attach(self, sid: str):
        self.c = Council(self.P, sid)
        self.c.load()
        self.st, self.st_t, self.link = {}, 0.0, True
        self.input.set("")
        self.focus, self.scroll, self.overlay, self.ask_id = False, 0, None, None
        self.end_at = self.follow = None
        self.c.unread = 0
        if self.c.ended:
            self.show_consensus()
        else:
            self.view = "session"
            if self.c.pending:
                self.open_ask(next(iter(self.c.pending)))

    def show_consensus(self):
        self.view, self.cons_t = "consensus", time.monotonic()

    def key_session(self, k):
        c = self.c
        sigil, word, hits = self.suggest()
        if hits:            # the suggestions under the cursor: ↑↓ pick, tab or ⏎ take it, esc closes them
            i = self.sug_i % len(hits)
            if k in ("up", "down"):
                self.sug_i = (i + (1 if k == "down" else -1)) % len(hits)
                return
            if k in ("tab", "enter"):
                return self.take_suggestion(word, hits[i][0])
            if k == "esc":
                self.sug_off = (self.input.text, self.input.pos)
                return
        if self.focus:
            if k == "esc":
                self.focus = False
            elif k == "enter":
                self.submit()
            elif k == "tab":
                self.complete()
            elif k == "ctrl-c":
                if self.input.text:
                    self.input.set("")
                else:
                    self.focus = False
                    self.ask_quit()
            elif k in ("pgup", "pgdn"):
                self.scroll_feed(k)
            elif k in ("up", "down") and not self.input.text:
                self.scroll_feed(k)
            elif isinstance(k, tuple) and k[0] == "paste" and dropped_files(k[1]):
                self.add_files(dropped_files(k[1]), self.say_atts, c.sid)
            elif k == "ctrl-v" or (isinstance(k, tuple) and k[0] == "paste" and not k[1].strip()):
                self.paste_clipboard(self.say_atts, c.sid)
            elif k == "ctrl-g":
                self.edit_outside(self.input)
            elif k == "bs" and not self.input.text and self.say_atts:
                self.say_atts.pop()
            else:
                self.input.key(k)
            return
        if k in ("q", "Q", "ctrl-c", "ctrl-d"):
            return self.ask_quit()
        if k in ("enter", "i", "t"):
            self.focus = True
        elif isinstance(k, tuple) and k[0] == "paste" and dropped_files(k[1]):
            self.focus = True
            self.add_files(dropped_files(k[1]), self.say_atts, c.sid)
        elif k in ("/", "@") or isinstance(k, tuple):
            self.focus = True
            self.input.key(k)
        elif k == "a" and c and c.pending:
            self.open_ask(next(iter(c.pending)))
        elif k == "c" and c and c.ended:
            self.show_consensus()
        elif k == "?":
            self.overlay = "help"
        elif k in ("up", "down", "pgup", "pgdn", "k", "j"):
            self.scroll_feed({"k": "up", "j": "down"}.get(k, k))
        elif k in ("end", "G"):
            self.scroll = 0
        elif k in ("home", "g"):
            self.scroll = 10 ** 6

    def scroll_feed(self, k: str):
        step = {"up": 1, "down": -1, "pgup": 10, "pgdn": -10}[k]
        self.scroll = max(0, self.scroll + step)

    def suggest(self) -> tuple[str, str, list[tuple[str, str, str]]]:
        """What fits the @agent or /command being typed, as you type it: (sigil, the word so far, [(name, what it is,
        colour)]). Nothing once the word is complete, or after esc (until the text changes)."""
        if not self.focus or not self.c:
            return "", "", []
        t = self.input.text[:self.input.pos]
        m = re.search(r"(^|\s)([@/])([\w-]*)$", t)
        if not m or (m.group(2) == "/" and m.start(2) != 0) or self.sug_off == (self.input.text, self.input.pos):
            return "", "", []
        sigil, word = m.group(2), m.group(3).lower()
        if sigil == "/":
            pool = [(k, v, CYAN) for k, v in COMMANDS.items()]
        else:
            pool = [("all", "everyone in the council", WHITE), ("navi", "the moderator", WHITE)] + \
                   [(n.name, n.role or n.text or "", n.color) for n in self.c.nodes.values()]
        hits = [x for x in pool if x[0].startswith(word)] or [x for x in pool if word and word in x[0]]     # by the start, else anywhere
        if (sigil, word) != self.sug_key:
            self.sug_key, self.sug_i = (sigil, word), 0
        if len(hits) == 1 and hits[0][0] == word:
            return sigil, word, []
        return sigil, word, hits[:8]

    def take_suggestion(self, word: str, name: str):
        for _ in range(len(word)):
            self.input.key("bs")
        self.input.insert(name + " ")

    def complete(self):
        """tab: complete @agent names and /commands."""
        t = self.input.text[:self.input.pos]
        m = re.search(r"(^|\s)([@/])([\w-]*)$", t)
        if not m or (m.group(2) == "/" and m.start(2) != 0):
            return
        word, sigil = m.group(3).lower(), m.group(2)
        pool = list(COMMANDS) if sigil == "/" else ["all", "navi"] + list(self.c.nodes if self.c else [])
        hits = [p for p in pool if p.startswith(word)]
        if not hits:
            return self.flash(f"no {'command' if sigil == '/' else 'agent'} starts with {sigil}{word}", RED)
        if len(hits) == 1:
            self.input.insert(hits[0][len(word):] + " ")
        else:
            common = os.path.commonprefix(hits)
            self.input.insert(common[len(word):])
            self.flash("  ".join(sigil + h for h in hits), MUTED)

    def submit(self):
        text = self.input.text.strip()
        c = self.c
        if (not text and not self.say_atts) or not c:
            return
        if self.demo and text not in ("/help", "/quit"):
            self.input.set("")
            return self.flash("this is the demo: nobody reads that · answer the question when it comes · q leaves", AMBER)
        if text.startswith("/"):
            cmd = text[1:].split()[0].lower() if text[1:].split() else ""
            self.input.set("")
            if cmd == "help":
                self.overlay = "help"
            elif cmd == "quit":
                self.focus = False
                self.ask_quit()
            elif cmd in ("cd", "pwd"):
                parts = text[1:].split(None, 1)
                self.change_dir(parts[1].strip() if cmd == "cd" and len(parts) > 1 else "")
            elif cmd == "end" and c.ended:
                self.flash("this session is already done · /new <task> runs the council again · /quit leaves", AMBER)
            elif cmd == "end":
                self.post("/say", {"session": c.sid, "intent": "exit", "text": "close the session"},
                          "asked NAVI to wrap up and close the session",
                          lambda data: self.flash("session closed ✓", OK) if data.get("closed") else None)
            elif cmd == "new":
                task = text[1:].split(None, 1)[1].strip() if len(text[1:].split(None, 1)) > 1 else ""
                if not task:
                    return self.flash("/new <task>: what should the council do next?", AMBER)
                sid, idle = c.sid, not self.st.get("host")          # NAVI isn't running (finished, or paused)

                def wake_new(data: dict):
                    if idle and not data.get("started") and self.c and self.c.sid == sid:
                        self.post("/launch", {"action": "continue", "target": sid, "host": "claude", "mode": "headless",
                                              "model": self.model, "effort": self.effort}, "NAVI is resuming for the new run")
                self.post("/say", {"session": sid, "intent": "new-task", "text": task}, "the council starts a new run", wake_new)
            elif cmd in ("effort", "model"):
                arg = (text[1:].split(None, 1)[1].strip().lower() if len(text[1:].split(None, 1)) > 1 else "")
                h = self.st.get("host") or {}
                eid = ((self.st or {}).get("session") or {}).get("engine") or "claude"
                if not arg:
                    return self.flash(f"NAVI: model {h.get('model') or 'default'} · effort {h.get('effort') or 'default'} · "
                                      f"/{cmd} <{'low|medium|high|xhigh|max' if cmd == 'effort' else ('opus|sonnet|haiku|fable' if eid == 'claude' else 'strong|balanced|fast or a model name')}> switches it", INK)
                val = "" if arg == "default" else arg
                if cmd == "effort" and val not in EFFORTS_ALL:
                    return self.flash(f"/effort: one of {', '.join(x for x in EFFORTS_ALL if x)} (or default)", RED)
                if cmd == "model" and val and not (val in TIER_OF or re.fullmatch(r"[A-Za-z0-9][\w.:/@+-]{0,79}", val)):
                    return self.flash("/model: a tier (strong, balanced, fast), opus|sonnet|haiku|fable, or a model name", RED)
                self.post("/moderator/model", {"session": c.sid, cmd: val, "when": "checkpoint"},
                          f"NAVI switches to {cmd} {val or 'default'} at its next checkpoint")
            elif cmd == "stop":
                self.post("/moderator/stop", {"session": c.sid}, "NAVI paused · /continue resumes it where it stopped")
            elif cmd in ("continue", "resume"):
                if self.st.get("host"):
                    return self.flash("NAVI is already running on this session", AMBER)
                body = {"action": "continue", "target": c.sid, "host": "claude", "mode": "headless", "model": self.model,
                        "effort": self.effort}
                self.post("/launch", body, "NAVI is resuming on this session, where it stopped")
            else:
                self.flash(f"there's no /{cmd} · try /help", RED)
            return
        m = re.match(r"^@([a-z0-9_-]+)", text, re.I)
        if m and m.group(1).lower() not in ("all", "navi") and m.group(1).lower() not in c.nodes:
            return self.flash(f"no agent called @{m.group(1)} in this council", RED)
        self.input.set("")
        sid, idle = c.sid, not self.st.get("host")          # NAVI isn't running (finished, or paused): writing resumes it

        def wake(data: dict):
            if data.get("answered"):
                return self.flash("sent as your answer to the question ✓", OK)
            # after the end the server only wakes a moderator when the setting is headless; the TUI always runs one
            if idle and not data.get("started") and self.c and self.c.sid == sid:
                self.post("/launch", {"action": "continue", "target": sid, "host": "claude", "mode": "headless",
                                      "model": self.model, "effort": self.effort}, "sent · NAVI is resuming for it")
        if any(a["state"] == "uploading" for a in self.say_atts):
            self.input.set(text)
            return self.flash("still uploading an attachment · a second", AMBER)
        atts = [{"path": a["path"], "name": a["name"]} for a in self.say_atts if a["state"] == "ok"]
        self.say_atts = []
        self.post("/say", {"session": sid, "intent": "message", "text": text, "attachments": atts},
                  "sent · the moderator picks it up next", wake)

    def post(self, path: str, body: dict, ok_msg: str, then=None):
        self.flash("sending…", MUTED)

        def done(r):
            ok, data = r if isinstance(r, tuple) else (False, r)
            self.flash(ok_msg if ok else data.get("error", "that didn't work"), OK if ok else RED)
            self.st_t = 0.0                       # refresh the status now
            if ok and then:
                then(data)
        self.job(lambda: self.api.post(path, body), done)

    # -- questions
    def open_ask(self, qid: str):
        if not self.c or qid not in self.c.pending:
            return
        ev = self.c.pending[qid]
        self.overlay, self.ask_id, self.ask_i, self.ask_err = "ask", qid, 0, ""
        self.ask_scroll, self.ask_more, self.ask_raw = 0, (False, False), False
        self.ask_mode = "options" if ev.get("options") or ev.get("type") == "permit" else "text"
        self.ask_text.set("")

    def key_ask(self, k):
        c = self.c
        ev = c.pending.get(self.ask_id) if c else None
        if not ev:
            self.overlay = None
            return
        perm = ev.get("type") == "permit"
        opts = [label for label, _ in permit_opts(ev)] if perm else [oneline(o) for o in ev.get("options") or []]
        if k in ("pgdn", "pgup"):           # a long question scrolls (draw_ask keeps it in range)
            self.ask_scroll = max(0, self.ask_scroll + (8 if k == "pgdn" else -8))
            return
        if perm and k in ("c", "C"):        # the command itself, or back to the words
            self.ask_raw = not self.ask_raw
            return
        if self.sending:
            return
        if perm:
            decs = [d for _, d in permit_opts(ev)]
            pick = {"y": "once", "a": "always", "n": "deny", "d": "deny"}.get(k.lower() if isinstance(k, str) and len(k) == 1 else "")
            if k == "esc":
                self.overlay = None
                self.flash("it waits for your OK · a to answer", AMBER)
            elif k in ("up", "k", "btab"):
                self.ask_i = (self.ask_i - 1) % len(opts)
            elif k in ("down", "j", "tab"):
                self.ask_i = (self.ask_i + 1) % len(opts)
            elif isinstance(k, str) and k.isdigit() and 1 <= int(k) <= len(opts):
                self.permit(ev, decs[int(k) - 1])
            elif pick in decs:
                self.permit(ev, pick)
            elif k == "enter":
                self.permit(ev, decs[self.ask_i % len(decs)])
            elif k == "ctrl-c":
                self.overlay = None
            return
        if self.ask_mode == "options":
            n = len(opts) + 1
            if k == "esc":
                self.overlay = None
                self.flash("the question waits · a to answer it", AMBER)
            elif k in ("up", "k", "btab"):
                self.ask_i = (self.ask_i - 1) % n
            elif k in ("down", "j", "tab"):
                self.ask_i = (self.ask_i + 1) % n
            elif isinstance(k, str) and k.isdigit() and 1 <= int(k) <= len(opts):
                self.ask_i = int(k) - 1
                self.answer(ev, opts[self.ask_i], "")
            elif k == "enter":
                if self.ask_i < len(opts):
                    self.answer(ev, opts[self.ask_i], "")
                else:
                    self.ask_mode = "text"
            elif k == "ctrl-c":
                self.overlay = None
            return
        if k == "esc":
            if opts:
                self.ask_mode, self.ask_err = "options", ""
            else:
                self.overlay = None
                self.flash("the question waits · a to answer it", AMBER)
        elif k == "enter":
            if any(a["state"] == "uploading" for a in self.ask_atts):
                self.ask_err = "still uploading an attachment · a second"
            elif self.ask_text.text.strip() or self.ask_atts:
                self.answer(ev, "", self.ask_text.text.strip())
            else:
                self.ask_err = "write an answer first"
        elif k == "ctrl-c":
            self.overlay = None
        elif isinstance(k, tuple) and k[0] == "paste" and dropped_files(k[1]):
            self.add_files(dropped_files(k[1]), self.ask_atts, self.c.sid)
        elif k == "ctrl-v" or (isinstance(k, tuple) and k[0] == "paste" and not k[1].strip()):
            self.paste_clipboard(self.ask_atts, self.c.sid)
        elif k == "ctrl-g":
            self.edit_outside(self.ask_text)
        elif k == "bs" and not self.ask_text.text and self.ask_atts:
            self.ask_atts.pop()
        else:
            self.ask_text.key(k)
            self.ask_err = ""

    def permit(self, ev: dict, decision: str):
        qid, sid = str(ev.get("id")), self.c.sid
        self.sending, self.ask_err = True, ""

        def done(r):
            ok, data = r if isinstance(r, tuple) else (False, r)
            self.sending = False
            if not ok and "already answered" not in str(data.get("error")):
                self.ask_err = data.get("error") or "that didn't work"
                return
            if self.c and self.c.sid == sid:
                self.c.pending.pop(qid, None)
                self.flash({"once": "allowed once ✓", "always": "allowed for this session ✓", "deny": "denied ✓"}[decision],
                           OK if decision != "deny" else AMBER)
                if self.overlay == "ask":
                    self.overlay, self.ask_id = None, None
                if self.c.pending:
                    self.open_ask(next(iter(self.c.pending)))
        self.job(lambda: self.api.post("/permit", {"session": sid, "id": qid, "decision": decision}), done)

    def answer(self, ev: dict, choice: str, text: str):
        qid, sid = str(ev.get("id")), self.c.sid
        raw = next((o for o in ev.get("options") or [] if oneline(o) == choice), choice)   # the server wants it verbatim
        self.sending, self.ask_err = True, ""

        def done(r):
            ok, data = r if isinstance(r, tuple) else (False, r)
            self.sending = False
            if not ok and "already answered" not in str(data.get("error")):
                self.ask_err = data.get("error") or "that didn't work"
                return
            if self.c and self.c.sid == sid:
                self.c.pending.pop(qid, None)
                self.flash("answer sent ✓", OK)
                if self.overlay == "ask":
                    self.overlay, self.ask_id = None, None
                if self.c.pending:
                    self.open_ask(next(iter(self.c.pending)))
        atts = [{"path": a["path"], "name": a["name"]} for a in self.ask_atts if a["state"] == "ok"] if not choice else []
        if not choice:
            self.ask_text.set("")
            self.ask_atts = []
        self.job(lambda: self.api.post("/reply", {"session": sid, "id": qid, "choice": raw, "text": text, "attachments": atts}), done)

    # ---------------------------------------------------------------- drawing
    def draw(self):
        W, H = self.term.size()
        s = self.scr
        s.begin(W, H)
        t = time.monotonic()
        if W < 60 or H < 18:
            msg = f"NAVI needs at least 60 × 18 · this is {W} × {H}"
            s.put(max(0, (W - tw(msg)) // 2), H // 2, fit(msg, W), sty(MUTED))
        elif self.view == "start":
            self.draw_start(t)
            if self.picker:
                s.dim(sty(mix(DIM, BG, .35)))
                self.draw_picker()
        elif self.view == "consensus" and self.c:
            self.draw_consensus(t)
        elif self.c:
            self.draw_session(t)
            if self.overlay == "ask":
                s.dim(sty(mix(DIM, BG, .35)))
                self.draw_ask(t)
        if W >= 60 and H >= 18:
            if self.overlay in ("quit", "help", "chatintro"):
                s.dim(sty(mix(DIM, BG, .35)))
            if self.overlay == "quit":
                self.draw_quit()
            elif self.overlay == "chatintro":
                self.draw_chat_intro()
            elif self.overlay == "help":
                self.draw_help()
        s.flush()

    def box(self, x: int, y: int, w: int, h: int, color, title: str = "", title_st: str = ""):
        s = self.scr
        s.fill(x, y, w, h)
        bs = sty(color)
        s.put(x, y, "╭" + "─" * (w - 2) + "╮", bs)
        for r in range(y + 1, y + h - 1):
            s.put(x, r, "│", bs)
            s.put(x + w - 1, r, "│", bs)
        s.put(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", bs)
        if title:
            s.put(x + 2, y, f" {title} ", title_st or sty(color, bold=True))

    def hints(self, y: int, parts: list[tuple[str, str]], x: int = 1, w: int | None = None):
        """key · what, key · what ... in one muted line."""
        s = self.scr
        w = w or s.w - 2
        end = x + w
        for i, (key, what) in enumerate(parts):
            seg = len(key) + (1 + tw(what) if what else 0) + (3 if i else 0)
            if x + seg > end:
                break
            if i:
                x = s.put(x, y, " · ", sty(DIM))
            x = s.put(x, y, key, sty(INK, bold=True))
            if what:
                x = s.put(x, y, " " + what, sty(MUTED))
        return x

    # -- start
    def draw_start(self, t: float):
        s, W, H = self.scr, self.scr.w, self.scr.h
        logo = self.N.logo_lines()
        lw = max(len(r) for r in logo)
        fs = self.fields()
        on_task = self.field == 0 and not self.launching
        tw_ = min(86, W - 4) - 12
        th = max(4, H - 18) if self.task_big else min(6, self.task.height(tw_ - 1))      # the task grows with what you write
        under = 1 if on_task else 0                                                         # its hint line
        rows = 5 + 2 + 1 + 2 + 1 + 2 + 5 + 2 + len(fs) - 5 + 3 + th - 1 + under
        y = max(0, (H - rows) // 2 - 1)
        if self.task_big or rows > H:       # room for the task: the logo steps aside
            y, logo = 0, []
        x0 = max(0, (W - lw) // 2)
        age = t - self.start_t
        reveal = (lw + 6) * age / 0.9
        glitch = random.random() < .025 and age > 1.2
        grow = random.randrange(5)
        for r, line in enumerate(logo):
            rowc = (255, 42 + r * 40, 74 + r * 30)
            for c, ch in enumerate(line):
                if ch == " ":
                    continue
                if c < reveal - 3:
                    st, g = sty(rowc), ch
                elif c < reveal:
                    st, g = sty(INK), ch
                elif random.random() < .55:
                    st, g = sty(CYAN if random.random() < .3 else DIM), random.choice(GLYPHS)
                else:
                    continue
                if glitch and r == grow:
                    st = sty(CYAN)
                s.put(x0 + c + (2 if glitch and r == grow else 0), y + r, g, st)
        if logo and halloween() and x0 + lw + 4 + len(PUMPKIN[0]) < W:     # HALLOWEEN 2026: delete at the start of November
            flick = (255, 214, 94) if math.sin(t * 7) + math.sin(t * 2.3) > -0.6 else (255, 150, 40)
            for r, line in enumerate(PUMPKIN):
                for c, ch in enumerate(line):
                    if ch != " ":
                        s.put(x0 + lw + 4 + c, y + r + 1, ch, sty(flick if ch in "^v" else (95, 154, 60) if r == 0 else (240, 132, 31), bold=True))
        y += 6 if logo else 0
        k = max(1, (lw - 9) // 2)
        wire = "──◉" + "─" * k + "◎" + "─" * k + "◉──"
        wx = max(0, (W - len(wire)) // 2)
        head = int((t * 14) % (len(wire) + 18)) - 9            # a packet rides the wire, forever
        for i, ch in enumerate(wire):
            d = head - i
            st = sty(RED, bold=True) if ch in "◉◎" else sty(WHITE, bold=True) if d == 0 else sty(mix(RED, DIM, d / 6)) if 0 < d < 6 else sty(DIM)
            s.put(wx + i, y, ch, st)
        sub = "T H E   W I R E D   ·   T E R M I N A L"
        up = getattr(self, "update", {}) or {}
        if up.get("installed"):          # a newer NAVI: said in green where the subtitle goes
            sub = f"✔ Update installed · NAVI {up.get('version')}: restart NAVI to use it"
        elif up.get("available") and up.get("git"):
            sub = f"↑ NAVI {up.get('latest')} is out · run navi update (you have {up.get('version')})"
        s.put(max(0, (W - tw(sub)) // 2), y + 1, fit(sub, W - 2), sty(OK, bold=True) if sub[0] in "✔↑" else sty(MUTED))
        y += 3
        y += 1                          # where it works is in the form now (FOLDER, BRANCH)
        fw = min(86, W - 4)
        fx = (W - fw) // 2
        vx = fx + 14
        names = {"task": "TASK", "files": "FILES", "folder": "FOLDER", "branch": "BRANCH", "council": "COUNCIL", "pace": "PACE", "engine": "ENGINE",
                 "model": "MODEL", "effort": "EFFORT", "agents": "AGENTS", "perms": "PERMISSIONS"}
        nf = fs.index("start")
        for i, f in enumerate(fs[:nf]):
            if f in ("folder", "council"):  # three groups: what (task, files), where (folder, branch), how (the rest)
                y += 1
            on = i == self.field and not self.launching
            s.put(fx, y, "▸" if on else " ", sty(RED, bold=True))
            s.put(fx + 2, y, names[f], sty(INK, bold=True) if on else sty(MUTED))
            if f == "task":
                y += self.task.draw(s, vx, y, fw - 12, sty(INK, bold=True), on, "what should the council work on? Files, images and links welcome",
                                    sty(DIM), h=th) - 1
                if on:
                    y += 1
                    tip = "⌥⏎ new line · ^O " + ("smaller" if self.task_big else "bigger") + " · ^G your editor · ^V paste an image"
                    s.put(vx, y, fit(tip, fw - 12), sty(DIM))
            elif f in ("folder", "branch"):   # where it works: ⏎ to switch, right here
                val = home(self.project) if f == "folder" else self.branch
                x = s.put(vx, y, fit(val, 44), sty(INK, bold=True) if on else sty(INK))
                s.put(max(x + 3, vx + 26), y, fit("⏎ another folder" if f == "folder" else "⏎ switch, or make one", fx + fw - max(x + 3, vx + 26)),
                      sty(MUTED if on else DIM))
            elif f == "files":              # what goes with the task: images, files (links are fine in the text itself)
                x = vx
                if not self.atts:
                    s.put(x, y, fit("^V pastes an image or a copied file · or drag files onto this window", fx + fw - x), sty(MUTED if on else DIM))
                for text, st in self.chips(self.atts):
                    if fx + fw - x < 8:
                        s.put(x, y, "…", sty(DIM))
                        break
                    x = s.put(x, y, fit(text, fx + fw - x), st) + 2
                if on and self.atts and fx + fw - x > 14:
                    s.put(x, y, "⌫ removes one", sty(DIM))
            else:
                val, info = self.form_value(f)
                arrows = sty(RED if on else DIM)
                x = s.put(vx, y, "◂ ", arrows)
                x = s.put(x, y, fit(val, 20), sty(INK, bold=True) if on else sty(INK))
                x = s.put(x, y, " ▸", arrows)
                s.put(max(x + 3, vx + 26), y, fit(info, fx + fw - max(x + 3, vx + 26)), sty(MUTED if on else DIM))
            y += 1
        y += 1
        for i, f in enumerate(fs[nf:], nf):
            on = i == self.field
            if f == "start":
                if self.launching:
                    s.put(vx, y, f"{SPIN[int(t * 12) % len(SPIN)]} seating the council…", sty(CYAN, bold=True))
                else:
                    label = " ▶ START THE COUNCIL "
                    s.put(fx, y, "▸" if on else " ", sty(RED, bold=True))
                    x = s.put(vx, y, label, sty(BG, RED, bold=True) if on else sty(RED, bold=True))
                    if on:
                        s.put(x + 2, y, "⏎", sty(MUTED))
            elif f == "endall":
                s.put(fx, y, "▸" if on else " ", sty(RED, bold=True))
                armed = on and self.endall_armed
                x = s.put(vx, y, " ■ END ALL SESSIONS ", sty(BG, AMBER, bold=True) if on else sty(AMBER, bold=True))
                desc = (f"⏎ again to end all {self.n_open}: each one's NAVI stops" if armed else
                        f"{self.n_open} open in this folder · their NAVI stops, nothing is deleted, any can be resumed")
                s.put(x + 2, y, fit(desc, fx + fw - x - 2), sty(AMBER if armed else INK if on else MUTED))
            elif f == "quit":
                s.put(fx, y, "▸" if on else " ", sty(RED, bold=True))
                x = s.put(vx, y, " ✕ QUIT ", sty(BG, INK, bold=True) if on else sty(MUTED, bold=True))
                s.put(x + 2, y, fit("leave the TUI · a council that runs keeps running", fx + fw - x - 2), sty(INK if on else DIM))
            else:
                o = self.open_s or {}
                s.put(fx, y, "▸" if on else " ", sty(RED, bold=True))
                x = s.put(vx, y, " ↺ CONTINUE ", sty(BG, CYAN, bold=True) if on else sty(CYAN, bold=True))
                desc = f"{oneline(o.get('task')) or 'the open session'} · {'running now' if o.get('live') else 'open'} · {o.get('events', 0)} events"
                s.put(x + 2, y, fit(desc, fx + fw - x - 2), sty(INK if on else MUTED))
            y += 1
        if self.err:
            y += 1
            for line in wrap(self.err, fw - 12)[:3]:
                s.put(vx, y, line, sty(RED))
                y += 1
        hint = [("↑↓", "field"), ("←→", "change"), ("⏎", "start"), ("esc", "quit")]
        width = sum(len(k) + 1 + len(w) for k, w in hint) + 3 * (len(hint) - 1)
        self.hints(H - 1, hint, x=max(1, (W - width) // 2))

    def form_value(self, f: str) -> tuple[str, str]:
        if f == "council":
            if not self.councils:
                return "…", "loading the councils"
            c = self.councils[self.ci]
            members = "recruits agents as the work needs them" if c.get("mode") == "auto" else " · ".join(c.get("members") or [])
            return oneline(c.get("title") or c["name"]).split(" · ")[0], members
        if f == "pace":
            return self.pace, PACE_INFO.get(self.pace, "")
        if f == "perms":
            return self.N.PERMISSION_WORDS.get(self.perms, self.perms).lower(), PERMS_INFO.get(self.perms, "")
        if f == "engine":
            e = self.eng()
            return (e.get("name") or "?"), ("your default" if e.get("id") == (self.st or {}).get("engine") else e.get("blurb", ""))
        if f == "model":
            return self.model_label(self.model)
        if f == "agents":
            mod = " · ".join(x for x in self.model_label(self.model) if x) if self.model else "the default model"
            if self.pace == "quick":
                return "council's models" if not self.agents else f"all on {mod}", f"QUICK: NAVI plays every seat itself, on {mod}"
            ms = (self.councils[self.ci].get("models") or {}) if self.councils else {}
            mix = " · ".join(f"{a} {self.model_label(m)[1] or m}" for a, m in ms.items() if m)
            if self.agents == "auto":
                return "NAVI picks per task", "a strong model for hard design and security, a fast one for summaries and light checks"
            return ("council's models", mix or f"every agent on {mod}") if not self.agents else (f"all on {mod}", "every agent thinks with the moderator's model")
        pe = self.N.PACE_EFFORT.get(self.pace, "medium")
        return (self.effort or "by pace"), (f"{pe}, from the pace" if not self.effort else "how long it thinks before each step")

    # -- session
    def draw_session(self, t: float):
        s, W, H, c = self.scr, self.scr.w, self.scr.h, self.c
        self.draw_header(t)
        body_y, body_h = 3, H - 6
        if W >= 100:
            fw = max(40, min(66, int(W * 0.40)))
            gw = W - fw - 1
            self.draw_graph(t, 0, body_y, gw, body_h)
            for r in range(body_y, body_y + body_h):
                s.put(gw, r, "│", sty(DIM))
            self.draw_feed(gw + 2, body_y, fw - 3, body_h)
        else:
            gh = max(9, int(body_h * 0.48))
            self.draw_graph(t, 0, body_y, W, gh)
            s.put(0, body_y + gh, "─" * W, sty(DIM))
            self.draw_feed(1, body_y + gh + 1, W - 2, body_h - gh - 1)
        s.put(0, H - 3, "─" * W, sty(DIM))
        where = self.N.tilde(self.N.project_root(self.P))
        where = where if len(where) <= 28 else "…/" + "/".join(where.split("/")[-2:])
        x = s.put(1, H - 2, where + " ", sty(MUTED if self.focus else DIM))          # where commands run, like a shell prompt
        x = s.put(x, H - 2, "› ", sty(RED, bold=True) if self.focus else sty(DIM))
        ph = (("the demo · answer the question when it comes · q leaves" if self.demo else
               "chat with NAVI · /new <task> runs the council again · drop files to attach" if c.ended else
               "talk to the council · @agent · ^V pastes an image, or drop a file")
              + ("" if self.focus else "   (⏎ to type)"))
        if self.say_atts:                   # what goes with the next message, on the rule above the console
            x2 = 2
            for text, st in self.chips(self.say_atts):
                if x2 + tw(text) > W - 2:
                    break
                x2 = s.put(x2, H - 3, f" {text} ", st) + 1
        self.input.draw(s, x, H - 2, W - x - 2, sty(INK), self.focus, ph, sty(MUTED if self.focus else DIM))
        sigil, word, hits = self.suggest()
        if hits and not self.overlay:        # what you can @ or / here, above the console
            nw = max(len(h[0]) for h in hits) + 2
            bw = min(W - x, max(34, nw + 6 + max(tw(h[1]) for h in hits)))
            by = H - 3 - len(hits) - 2
            self.box(x - 2, by, bw, len(hits) + 2, DIM)
            for j, (name, what, col) in enumerate(hits):
                on = j == self.sug_i % len(hits)
                y = by + 1 + j
                if on:
                    s.put(x - 1, y, " " * (bw - 2), sty(INK, bg=RAISE) if "RAISE" in globals() else sty(INK))
                s.put(x - 1, y, "▸" if on else " ", sty(RED, bold=True))
                s.put(x + 1, y, sigil + name, sty(col, bold=True) if on else sty(col))
                s.put(x + 1 + nw + 1, y, fit(what, bw - nw - 5), sty(INK) if on else sty(MUTED))
        if self.focus:
            hint = ([("↑↓", "pick"), ("tab", "take it"), ("esc", "close")] if self.suggest()[2] else
                    [("⏎", "send"), ("esc", "done"), ("/new", "council again"), ("/quit", ""), ("/help", "")] if c.ended else
                    [("⏎", "send"), ("@", "an agent"), ("/", "a command"), ("esc", "done"), ("/end", ""), ("/stop", ""), ("/help", "")])
        else:
            hint = [("⏎", "chat with NAVI" if c.ended else "talk")]
            if c.pending:
                hint.append(("a", f"answer ({len(c.pending)})"))
            if c.ended:
                hint.append(("c", "consensus"))
            hint += [("↑↓", "scroll"), ("?", "help"), ("q", "quit")]
        msg = fit(self.flash_msg, max(20, W * 3 // 5)) if self.flash_msg and t - self.flash_t < 6 else ""
        self.hints(H - 1, hint, w=W - 2 - (tw(msg) + 3 if msg else 0))     # a message wins over the hints
        if msg:
            s.put(W - 1 - tw(msg), H - 1, msg, sty(self.flash_c))

    def draw_header(self, t: float):
        s, W, c = self.scr, self.scr.w, self.c
        live = self.working()
        x = s.put(1, 0, "◉", sty(mix(RED, BG, .5 - .5 * math.sin(t * 3)) if live else DIM))
        x = s.put(x + 1, 0, "NAVI", sty(RED, bold=True))
        now = time.time()
        el = dur(((c.end_t if c.ended else now) - c.started)) if c.started else "-:--"
        if not self.link:
            badge, bc = "○ LINK LOST", RED
        elif c.ended:
            badge, bc = "✓ DONE", OK
        elif c.pending:
            badge, bc = f"◆ NEEDS YOU ({len(c.pending)})", AMBER
        elif self.demo:
            badge, bc = "◉ DEMO", CYAN
        elif live:
            badge, bc = "● LIVE", OK
        elif self.st:
            badge, bc = "○ PAUSED · /continue resumes", MUTED
        else:
            badge, bc = "· linking", DIM
        right = f"{badge}   {el}"
        s.put(x + 2, 0, fit(c.task or "(no task yet: NAVI will ask)", W - x - 2 - tw(right) - 4), sty(INK, bold=True))
        rx = W - 1 - tw(right)
        s.put(rx, 0, badge, sty(bc, bold=True))
        s.put(W - 1 - tw(el), 0, el, sty(INK))
        mod = c.mod or {}
        h = self.st.get("host") or {}
        mode = h.get("mode") or mod.get("mode") or "off"
        parts = ([("council", c.council)] if c.council else []) + [("pace", c.pace or "auto")]
        if c.perms in self.N.PERMISSION_WORDS:
            parts.append(("permissions", self.N.PERMISSION_WORDS[c.perms].lower()))
        ses = self.st.get("session") or {}
        tok = sum(int(u.get(f) or 0) for src in ((ses.get("usage") or {}).get("models") or {}, ses.get("usage_live") or {})
                  for u in src.values() for f in ("in", "out", "cache_read", "cache_write"))
        if tok:
            usd = (ses.get("cost") or {}).get("usd")
            parts.append(("tokens", fmt_tok(tok) + (f" · ${usd:.2f}" if usd else "")))
        eid = ses.get("engine") or "claude"
        if eid != "claude":
            parts.insert(0, ("engine", self.eng(eid).get("name") or eid))
        if h or mode != "off":
            m0 = h.get("model", mod.get("model", ""))
            label = self.model_label(m0, eid)
            model = (label[1] if TIER_OF.get(m0) and eid != "claude" else label[0]) if m0 else (self.eng(eid).get("default") or "default")
            effort = h.get("effort", mod.get("effort", "")) or "default"
            no_effort = eid != "claude" and not (self.eng(eid).get("efforts") or [])
            parts += [("NAVI", model if no_effort else f"{model} · {effort}"), ("", {"headless": "background", "terminal": "in a terminal"}.get(mode, mode))]
        else:
            parts.append(("NAVI", "paused"))
        x = 1
        for i, (k, v) in enumerate(parts):
            if i:
                x = s.put(x, 1, "  ·  ", sty(DIM))
            if k:
                x = s.put(x, 1, k + " ", sty(MUTED))
            x = s.put(x, 1, v, sty(INK))
        where = home(self.project) + (f"  ⎇ {self.branch}" if self.branch else "")
        if x + 4 + tw(where) < W:
            s.put(W - 1 - tw(where), 1, where, sty(MUTED))
        # the separator: a slow scan runs along it while the council works
        s.put(0, 2, "─" * W, sty(DIM))
        if live:
            p = int((t * 22) % (W + 40)) - 20
            for i in range(14):
                xx = p - i
                if 0 <= xx < W:
                    s.put(xx, 2, "━" if i < 4 else "─", sty(mix(RED, DIM, i / 14)))

    def draw_feed(self, x: int, y: int, w: int, h: int):
        s, c = self.scr, self.c
        title = "FEED"
        s.put(x, y, title, sty(MUTED, bold=True))
        info = f"{c.msgs} message{'s' * (c.msgs != 1)}" + (f" · {len(c.files)} file{'s' * (len(c.files) != 1)}" if c.files else "")
        s.put(x + w - tw(info), y, info, sty(DIM))
        lines: list = []
        for it in c.feed:
            lines += it.lines(w)
        room = h - 1
        most = max(0, len(lines) - room)
        self.scroll = min(self.scroll, most)
        if self.scroll == 0:
            c.unread = 0
        top = max(0, len(lines) - room - self.scroll)
        for i, line in enumerate(lines[top:top + room]):
            xx = x
            for text, st in line:
                xx = s.put(xx, y + 1 + i, text, st, maxw=x + w - xx)
        if self.scroll:
            tag = f" ↓ {c.unread} new · end " if c.unread else f" ↑ {self.scroll} lines up · end "
            s.put(x + w - tw(tag), y + h - 1, tag, sty(BG, AMBER if c.unread else MUTED, bold=True))

    def layout(self, gx: int, gy: int, gw: int, gh: int):
        """Place the hub in the middle and the agents on an ellipse around it (cells). -> geometry dict."""
        c = self.c
        compact = gh < 19
        ring = list(c.nodes.values())
        n = len(ring)
        if compact:           # short and wide: labels sit right of the chips, so spread the ring sideways
            ry = max(2.0, (gh - 3) / 2)
            cy = gy + 1 + ry
            rx = max(8.0, gw / 2 - 15)
        else:
            ry = max(3.0, (gh - 7) / 2)
            cy = gy + 3 + ry
            rx = max(10.0, min(gw / 2 - 10, ry * 2.6))
        cx = gx + gw / 2
        off = 0.5 if n % 2 == 0 else 0.0       # an even council leaves the top and bottom free (the bottom is yours)
        for i, nd in enumerate(ring):
            a = -math.pi / 2 + (i + off) * math.tau / max(1, n)
            nd.x, nd.y = cx + math.cos(a) * rx, cy + math.sin(a) * ry
        if c.user:
            c.user.x, c.user.y = cx, cy + ry
        c.hub.x, c.hub.y = cx, cy
        if compact:                                     # little room: two rings around a plain NAVI
            return {"compact": True, "rx": rx, "ry": ry, "r": (5.5, max(7.0, min(9.5, ry * 2.4))), "wide_label": False}
        room = min(ry * 4, rx * 2)                      # the agents' ring radius, in braille dots
        r3 = max(10.0, min(22.0, room * .42))
        r1 = max(6.0, r3 - 8)
        return {"compact": False, "rx": rx, "ry": ry, "r": (r1, (r1 + r3) / 2, r3), "wide_label": r1 >= 10}

    def effective_model(self, nd) -> str:
        """In QUICK NAVI plays every seat itself, and a seat without a model uses the moderator's: show what's real."""
        c = self.c
        if not c or nd is c.user or nd.name in ("user", "navi"):
            return ""
        eid = ((self.st or {}).get("session") or {}).get("engine") or "claude"
        mod = (getattr(c, "mod", None) or {}).get("model") or ("" if eid != "claude" else ((self.st or {}).get("claude_defaults") or {}).get("model") or "")
        mod = next((k for k in ("opus", "sonnet", "haiku", "fable") if k in mod), mod)
        use = mod if (c.pace == "quick" or not nd.model) else nd.model
        if eid != "claude" and TIER_OF.get(use):         # a tier on another engine: show the model it is there
            return (self.eng(eid).get("tiers") or {}).get(TIER_OF[use]) or use
        return use

    def draw_graph(self, t: float, gx: int, gy: int, gw: int, gh: int):
        s, c = self.scr, self.c
        geo = self.layout(gx, gy, gw, gh)
        compact = geo["compact"]
        cv = Canvas(gw, gh)
        px = lambda n: ((int(n.x + .5) - gx) * 2 + 1, (int(n.y + .5) - gy) * 4 + 1.5)  # noqa: E731 - cell centre -> dots
        hub = px(c.hub)
        r3 = geo["r"][-1]
        nodes = list(c.nodes.values()) + ([c.user] if c.user else [])
        nr = 3.5 if compact else 5.5              # an agent's ring, in dots

        def trim(a, b, ra, rb):
            """The straight wire from a to b without the parts inside the two rings."""
            dx, dy = b[0] - a[0], b[1] - a[1]
            d = math.hypot(dx, dy) or 1.0
            n = int(d)
            lo, hi = int(ra + 2), int(d - rb - 2)
            return [(a[0] + dx * i / n, a[1] + dy * i / n) for i in range(lo, hi + 1)] if n else []
        flow = int(t * 9) % 4
        for nd in nodes:          # the wires: dotted, and the dots flow out from the hub
            cv.path(trim(hub, px(nd), r3, nr), WIRE, 0, (4, 2), flow)
        now = time.monotonic()
        for a, b, color, hot in c.links.values():     # links that carried messages glow, then cool to an ember
            if a.name not in c.nodes and a is not c.user and a is not c.hub:
                continue
            if b.name not in c.nodes and b is not c.user and b is not c.hub:
                continue
            if c.hub in (a, b):
                continue
            pa, pb = px(a), px(b)
            heat = max(0.0, 1 - (now - hot) / 6)
            col = mix(color, BG, .8 - .55 * heat)
            d = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            n = int(d * 1.2) or 1
            bend = outward(pa, pb, hub)
            pts = [bez(pa, pb, bend, i / n) for i in range(n + 1)]
            pts = [p for p in pts if math.hypot(p[0] - pa[0], p[1] - pa[1]) > nr + 2 and math.hypot(p[0] - pb[0], p[1] - pb[1]) > nr + 2]
            cv.path(pts, col, 1)
        # the hub: three rings turning at their own speeds, brighter when something lands
        hp = max(0.0, 1 - (now - c.hub.pulse) / .8)
        for i, r in enumerate(geo["r"]):
            a0 = t * (.35 + i * .22) * (-1 if i % 2 else 1)
            col = mix(c.hub.pulse_c if hp > .05 else RED, BG, i * .22 + (1 - hp) * .1)
            cv.ring(hub[0], hub[1], r + hp * 2, col, 3, a0, math.pi * (1.1 + i * .3))
        # the agents' rings: dashed and turning; a spinner while they work; a shockwave when something lands
        for nd in nodes:
            p = px(nd)
            pulse = max(0.0, 1 - (now - nd.pulse) / .7)
            base = nd.color
            if nd.state == "working":
                col = mix(base, BG, .1 + .3 * (.5 + .5 * math.sin(t * 5 + len(nd.name))))
            elif nd.state == "waiting":
                col = AMBER if int(t * 3) % 2 else mix(AMBER, BG, .5)
            elif nd.state == "done":
                col = mix(base, BG, .45)
            elif nd.state == "offline":
                col = mix(base, BG, .62)
            else:
                col = mix(base, BG, .35)
            if not compact:
                spin = (1 if len(nd.name) % 2 else -1) * t * (7.0 if nd.state == "working" else 1.2)
                cv.ring(p[0], p[1], nr, col, 4, spin, math.tau, (5, 3))
            if pulse > 0:
                cv.ring(p[0], p[1], nr + (1 - pulse) * 9, mix(nd.pulse_c, BG, 1 - pulse), 2)
        # the packets: a bright head and a fading tail, travelling the wire (or a curve between two agents)
        alive = []
        for pk in c.packets:
            a, b = pk["a"], pk["b"]
            if (a is not c.hub and a is not c.user and a.name not in c.nodes) or (b is not c.hub and b is not c.user and b.name not in c.nodes):
                continue
            pa, pb = px(a), px(b)
            d = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) or 1.0
            span = max(.55, min(1.5, d / 60))
            u = (now - pk["t0"]) / span
            if u >= 1:
                b.pulse, b.pulse_c = now, pk["color"]
                c.links[frozenset((a.name, b.name))] = [a, b, pk["color"], now]
                continue
            alive.append(pk)
            if u < 0:
                continue
            bend = 0.0 if c.hub in (a, b) else outward(pa, pb, hub)
            for j in range(9):
                v = u - j * .022
                if v < 0:
                    break
                x, y = bez(pa, pb, bend, v)
                cv.dot(x, y, mix(pk["color"], BG, j / 10), 9 - j)
                if j == 0:
                    for ox, oy in ((1, 0), (0, 1), (1, 1)):
                        cv.dot(x + ox, y + oy, pk["color"], 9)
        c.packets = alive
        cv.blit(s, gx, gy)
        # text on top. The agents first (chip, name, status): they matter most. Then what fits around them.
        boxes: list[tuple] = []            # cells taken: (x0, y0, x1, y1)
        lw = max(10, min(26, int(math.tau * geo["rx"] / max(1, len(c.nodes)) * .9)))   # a crowded ring gets shorter labels
        hx, hy = int(c.hub.x + .5), int(c.hub.y + .5)
        for nd in nodes:
            x, y = int(nd.x + .5), int(nd.y + .5)
            pulse = max(0.0, 1 - (now - nd.pulse) / .6)
            base = WHITE if pulse > .5 else nd.color
            if nd.state == "waiting" and int(t * 3) % 2:
                base = AMBER
            s.put(x - 1, y, "▐", sty(base))
            s.put(x, y, nd.mono(), sty(BG, base, bold=True))
            s.put(x + 1, y, "▌", sty(base))
            em = self.effective_model(nd)
            name = nd.label() + (f" · {em}" if em and not compact else "")
            status, timer = "", ""
            if nd.state != "idle" or nd.text:
                icon = SPIN[int(t * 10 + len(nd.name)) % len(SPIN)] if nd.state == "working" else STATE_ICON.get(nd.state, "·")
                status = f"{icon} {nd.text or nd.state}"
                timer = f" {dur(time.time() - nd.since)}" if nd.state in ("working", "waiting") and nd.text else ""
            say = lambda w: status + timer if tw(status + timer) <= w else fit(status, w)  # noqa: E731 - a timer fits whole or not at all
            col = (RED if nd.state == "blocked" else AMBER if nd.state == "waiting" else
                   mix(nd.color, INK, .3) if nd.state == "working" else DIM)
            if compact:          # ▐A▌ NAME, the status under it (and never into the hub)
                stop = hx - 5 if x < hx and hy - 1 <= y + 1 and y <= hy + 1 else gx + gw - 1
                name = fit(name, max(6, stop - x - 3))
                text = say(min(lw, max(6, stop - x + 1)))
                s.label(x + 3, y, name, sty(nd.color, bold=True))
                s.label(x - 1, y + 1, text, sty(col))
                boxes.append((x - 1, y, max(x + 3 + tw(name), x - 1 + tw(text)), y + 1))
            else:                # the chip in its ring, the name and the status centred under it (two lines when it needs them)
                name = fit(name, min(22, max(12, lw)))
                rows = [status + timer] if tw(status + timer) <= lw else wrap(status, lw)
                if len(rows) > 1:
                    lx0, lx1 = x - lw // 2, x + lw // 2
                    if y + 4 >= gy + gh or any(b[1] <= y + 4 <= b[3] and b[0] <= lx1 and lx0 <= b[2] for b in boxes):
                        rows = [say(lw)]                              # no free row under it: one line, cut
                    else:
                        rows = [rows[0], fit(" ".join(rows[1:]) + (timer if tw(" ".join(rows[1:]) + timer) <= lw else ""), lw)]
                nx = min(max(gx + 1, x - tw(name) // 2), gx + gw - 1 - tw(name))
                s.label(nx, y + 2, name, sty(nd.color, bold=True))
                left, right = nx, nx + tw(name)
                for i, text in enumerate(rows):
                    tx = min(max(gx + 1, x - tw(text) // 2), gx + gw - 1 - tw(text))
                    s.label(tx, y + 3 + i, text, sty(col))
                    left, right = min(left, tx), max(right, tx + tw(text))
                boxes.append((min(left, x - 3), y - 1, max(right, x + 3), y + 2 + len(rows)))
        free = lambda x0, y0, x1, y1, me=None: not any(  # noqa: E731
            b is not me and x0 <= b[2] and b[0] <= x1 and y0 <= b[3] and b[1] <= y1 for b in boxes)
        # the hub's name, glitching now and then
        label = "N A V I" if geo["wide_label"] else "NAVI"
        if random.random() < .04:
            i = random.randrange(len(label))
            if label[i] != " ":
                label = label[:i] + random.choice(GLYPHS) + label[i + 1:]
        s.label(hx - len(label) // 2, hy, label, sty(WHITE, bold=True))
        boxes.append((hx - len(label) // 2 - 1, hy, hx + len(label) // 2 + 1, hy))
        # the panel's top line: its name, WARDEN's perimeter, and the moderator's status when there's no room under the hub
        tag = f"◈ WARDEN · {c.policy}" if c.policy else ""
        tag_x = gx + gw - 1 - tw(tag)
        if tag:
            gt, gc = c.guard
            hot = now - gt < 1.6
            s.put(tag_x, gy, tag, sty(gc if hot else mix(OK, BG, .45), bold=hot))
        head = "" if compact else ("THE COUNCIL · offline · chat with NAVI" if c.ended else "THE COUNCIL")
        top_x = gx + 1 + (tw(head) + 3 if head else 0)          # the moderator's status starts after the panel's name, never on it
        if head:
            s.put(gx + 1, gy, head, sty(MUTED, bold=True))
        hs = c.hub
        if hs.text and hs.state != "idle" or hs.text == CONNECTING:
            icon = SPIN[int(t * 10) % len(SPIN)] if hs.state == "working" else STATE_ICON.get(hs.state, "·")
            live = hs.state in ("working", "waiting")
            text = f"{icon} {hs.text}" + (f"  {dur(time.time() - hs.since)}" if live else "")
            col = RED if hs.state == "blocked" else AMBER if hs.state == "waiting" else MUTED
            uy = hy + int(geo["r"][-1] / 4) + 2
            row = [b for b in boxes if b[1] <= uy <= b[3]]        # under the hub, as wide as the agents there allow
            lo = max([b[2] for b in row if b[2] < hx] + [gx]) + 2
            hi = min([b[0] for b in row if b[0] > hx] + [gx + gw]) - 2
            room = 0 if any(b[0] <= hx <= b[2] for b in row) else min(64, 2 * min(hx - lo, hi - hx))
            if not compact and uy < gy + gh and room >= 18:
                rows = wrap(text, room)
                below = [b for b in boxes if b[1] <= uy + 1 <= b[3] and b[0] <= hx + room // 2 and hx - room // 2 <= b[2]]
                if len(rows) > 1 and (below or uy + 1 >= gy + gh):      # no second line free: one line, cut
                    rows = [fit(text, room)]
                rows = rows[:2] if len(rows) <= 2 else [rows[0], fit(" ".join(rows[1:]), room)]
                for i, under in enumerate(rows):                        # the whole status, on two lines when it needs them
                    ux = hx - tw(under) // 2
                    s.label(ux, uy + i, under, sty(col))
                    boxes.append((ux - 1, uy + i, ux + tw(under), uy + i))
            else:                                                   # no room there: the panel's top line
                room = (tag_x - 2 if tag else gx + gw - 1) - top_x
                x = s.put(top_x, gy, fit("NAVI ", room), sty(INK, bold=True))
                s.put(x, gy, fit(text, room - 5), sty(col))
        # thoughts, typed out above their agent, where they don't cover anyone else
        for nd, box in zip(nodes, boxes):
            age = now - nd.thought_t
            if not nd.thought or age >= 10 or compact:
                continue
            x, y = int(nd.x + .5), int(nd.y + .5)
            st = sty(mix(nd.color, BG, .35 + max(0.0, age - 8) / 2.5), italic=True)
            n = int(age * 42)                                        # typed out, then the whole thought
            wide = max(18, min(38, gw // 3))
            for where, width, most in (("above", wide, 4), ("right", min(wide, 30), 4), ("left", min(wide, 30), 4), ("above", wide, 2), ("above", 26, 1)):
                rows = wrap(nd.thought, width)                       # up to four lines above the agent, else beside it, else fewer, cut
                rows = rows if len(rows) <= most else rows[:most - 1] + [fit(" ".join(rows[most - 1:]), width)]
                bw = max(tw(r) for r in rows)
                if where == "above":
                    tx, top = min(max(gx + 1, x - bw // 2), gx + gw - 1 - bw), y - 1 - len(rows)
                else:
                    tx, top = (x + 5 if where == "right" else x - 5 - bw), y - len(rows) // 2
                    if tx < gx + 1 or tx + bw > gx + gw - 1:
                        continue
                if top > gy and top + len(rows) - 1 < gy + gh and free(tx - 1, top, tx + bw, top + len(rows) - 1, box):
                    left = n
                    for i, r in enumerate(rows):
                        part = r[:max(0, left)]
                        left -= len(r) + 1
                        if part:
                            s.label(tx + (bw - tw(r)) // 2, top + i, part, st)
                    break

    # -- overlays
    def draw_ask(self, t: float):
        s, W, H, c = self.scr, self.scr.w, self.scr.h, self.c
        ev = c.pending.get(self.ask_id)
        if not ev:
            return
        perm = ev.get("type") == "permit"
        body = clean(ev.get("body") or "")
        long = len(body) > 500 or body.count("\n") > 6
        bw = min(110 if long else 78, W - 6)
        iw = bw - 6
        opts = [label for label, _ in permit_opts(ev)] if perm else [oneline(o) for o in ev.get("options") or []]
        if perm:          # in words first; the command itself on c
            head, plain = clean(ev.get("why") or ev.get("plain") or ""), clean(ev.get("plain") or "") if ev.get("why") else ""
            allq = [(x, "head") for x in paragraphs(head, iw)] + [(x, "plain") for x in paragraphs(("It runs: " if ev.get("tool") == "Bash" else "") + plain, iw) if plain]
            allq += [(x, "cmd") for x in paragraphs(body, iw - 2)] if self.ask_raw or not head else [("c shows the command" if ev.get("tool") == "Bash" else "c shows the details", "hint")]
        else:
            allq = md_lines(body, iw)
        room = max(3, H - len(opts) - 14 - (8 if not perm and self.ask_mode == "text" else 0))
        self.ask_scroll = max(0, min(self.ask_scroll, len(allq) - room))
        q = allq[self.ask_scroll:self.ask_scroll + room] or [("(no question text)", False)]
        more = len(allq) - self.ask_scroll - len(q)
        self.ask_more = (self.ask_scroll > 0, more > 0)
        rows: list[tuple] = [("title",), ("",)] + [(("cmd" if b == "cmd" else "pl") if perm else "q", line, b) for line, b in q]
        rows += [("more", more)] if more > 0 or self.ask_scroll else []
        rows += [("",)]
        if perm:
            notes = [(n, AMBER) for n in paragraphs("WARDEN: " + clean(ev.get("warden")), iw)[:2]] if ev.get("warden") else []
            notes += [(n, AMBER) for n in paragraphs(clean(ev.get("auto_off")), iw)[:3]] if ev.get("auto_off") else []
            notes += [(f"Auto: if nobody answers within {ev['auto_wait']} seconds, the council goes on without it", MUTED)] if ev.get("auto_wait") else []
            rows += [("note", n, c) for n, c in notes] + ([("",)] if notes else [])
            rows += [("opt", i, o) for i, o in enumerate(opts)]
        elif self.ask_mode == "options":
            rows += [("opt", i, o) for i, o in enumerate(opts + ["✎ write my own answer"])]
        else:
            ih = max(3, min(10, self.ask_text.height(iw - 2)))           # room to write: three lines, more as it grows
            rows += [("input",)] + [("pad",)] * (ih - 1) + ([("chips",)] if self.ask_atts else [])
        if self.ask_err:
            rows += [("",), ("err",)]
        rows += [("",), ("hints",)]
        bh = len(rows) + 2
        x0, y0 = (W - bw) // 2, max(1, (H - bh) // 2)
        who = c.node(ev.get("agent") or "navi")
        self.box(x0, y0, bw, bh, AMBER)
        for i, row in enumerate(rows):
            y, kind = y0 + 1 + i, row[0]
            if kind == "title":
                x = s.put(x0 + 3, y, "◆ ", sty(AMBER, bold=True))
                x = s.put(x, y, who.label(), sty(who.color, bold=True))
                s.put(x, y, " " + permit_verb(ev) if perm else " asks you", sty(AMBER, bold=True))
                if len(c.pending) > 1:
                    more = f"1 of {len(c.pending)}"
                    s.put(x0 + bw - 3 - len(more), y, more, sty(MUTED))
            elif kind == "q":
                s.put(x0 + 3, y, row[1], sty(WHITE, bold=True) if row[2] else sty(INK))
            elif kind == "more":
                s.put(x0 + 3, y, (f"↓ {row[1]} more line{'s' * (row[1] != 1)} · PgDn" if row[1] > 0 else "↑ the start · PgUp"), sty(CYAN))
            elif kind == "cmd":
                s.put(x0 + 3, y, "› " + row[1], sty(WHITE, bold=True))
            elif kind == "pl":
                s.put(x0 + 3, y, row[1], {"head": sty(WHITE, bold=True), "plain": sty(INK), "hint": sty(CYAN)}.get(row[2], sty(INK)))
            elif kind == "note":
                s.put(x0 + 3, y, row[1], sty(row[2]))
            elif kind == "opt":
                on = row[1] == self.ask_i
                s.put(x0 + 3, y, "▸" if on else " ", sty(RED, bold=True))
                s.put(x0 + 5, y, f"{row[1] + 1}" if row[1] < len(opts) and row[1] < 9 else " ", sty(DIM))
                s.put(x0 + 7, y, fit(row[2], iw - 4), sty(INK, bold=True) if on else sty(MUTED))
            elif kind == "input":
                x = s.put(x0 + 3, y, "› ", sty(RED, bold=True))
                self.ask_text.draw(s, x, y, iw - 2, sty(INK), True, "your answer · files, images and links welcome", sty(DIM),
                                   h=max(3, min(10, self.ask_text.height(iw - 2))))
            elif kind == "chips":
                x = x0 + 5
                for text, st in self.chips(self.ask_atts):
                    if x + tw(text) > x0 + bw - 3:
                        break
                    x = s.put(x, y, text, st) + 2
            elif kind == "err":
                s.put(x0 + 3, y, fit(self.ask_err, iw), sty(RED))
            elif kind == "hints":
                if self.sending:
                    s.put(x0 + 3, y, f"{SPIN[int(t * 12) % len(SPIN)]} sending…", sty(CYAN))
                elif perm:
                    self.hints(y, [("y", "allow once")] + ([("a", "this session")] if len(opts) > 2 else []) +
                               [("n", "deny"), ("c", "hide the command" if self.ask_raw else "the command"), ("esc", "later")], x=x0 + 3, w=iw)
                elif self.ask_mode == "options":
                    self.hints(y, [("↑↓", "choose"), ("⏎", "send"), ("1-9", "pick")] + ([("PgUp/PgDn", "read")] if any(self.ask_more) else [])
                               + [("esc", "later")], x=x0 + 3, w=iw)
                else:
                    self.hints(y, [("⏎", "send"), ("⌥⏎", "new line"), ("^G", "your editor"), ("^V", "paste an image"),
                                   ("esc", "back" if opts else "later")], x=x0 + 3, w=iw)

    def open_demo_page(self):
        f = self.P / "sessions" / self.c.sid / "out" / "index.html" if self.c else None
        if f and f.exists():
            import webbrowser
            webbrowser.open(f.as_uri())
            self.flash("the page it built is open in your browser", OK)
        else:
            self.flash("the page isn't built yet", AMBER)

    def chat_intro(self):
        """The first time you're back in the chat after CONSENSUS: say what changed (once per machine)."""
        if getattr(self, "intro_checked", False) or self.demo:
            return
        self.intro_checked = True

        def done(cfg):
            if isinstance(cfg, dict) and "setup_complete" in cfg and not cfg.get("chat_intro_seen") and self.overlay is None:
                self.overlay = "chatintro"
        self.job(lambda: self.api.get("/settings"), done)

    def draw_chat_intro(self):
        s, W, H = self.scr, self.scr.w, self.scr.h
        bw = min(74, W - 6)
        rows = [("Like any coding agent.", "Ask NAVI to fix something, run the tests, explain a file or open what was built. One agent, no rounds."),
                ("The council rests.", "Its agents show offline on the graph, and they cost nothing while they rest."),
                ("Want them back?", "Say it in words, like \"run the council on the login flow\", or type /new and the task.")]
        lines: list[tuple[str, str]] = []
        for head, body in rows:
            lines += [(head, "b")] + [(ln, "") for ln in wrap(body, bw - 8)] + [("", "")]
        bh = len(lines) + 6
        x0, y0 = (W - bw) // 2, max(1, (H - bh) // 2)
        self.box(x0, y0, bw, bh, CYAN)
        s.put(x0 + 3, y0 + 1, "Back in the chat: the council is offline", sty(INK, bold=True))
        for i, (ln, kind) in enumerate(lines):
            s.put(x0 + 3 + (0 if kind else 2), y0 + 3 + i, ln, sty(WHITE, bold=True) if kind else sty(MUTED))
        self.hints(y0 + bh - 2, [("any key", "got it")], x=x0 + 3)

    def draw_quit(self):
        s, W, H = self.scr, self.scr.w, self.scr.h
        bw = min(70, W - 6)
        lines = wrap("The council is still working. It keeps running in the background either way: "
                     f"`navi tui --session {self.c.sid if self.c else ''}` or the web interface brings you back.", bw - 6)
        bh = len(lines) + 6
        x0, y0 = (W - bw) // 2, max(1, (H - bh) // 2)
        self.box(x0, y0, bw, bh, RED)
        s.put(x0 + 3, y0 + 1, "Leave the TUI?", sty(INK, bold=True))
        for i, line in enumerate(lines):
            s.put(x0 + 3, y0 + 3 + i, line, sty(MUTED))
        self.hints(y0 + bh - 2, [("y", "leave"), ("n", "stay")], x=x0 + 3)

    def draw_help(self):
        s, W, H = self.scr, self.scr.w, self.scr.h
        rows = [("⏎  i", "talk to the council (type, ⏎ sends, esc stops typing)"), ("@agent …", "a message to one agent · tab completes"),
                ("/end", COMMANDS["end"]), ("/stop", COMMANDS["stop"]), ("/continue", COMMANDS["continue"]),
                ("a", "answer a waiting question"), ("c", "the consensus, once there is one"),
                ("↑↓ pgup pgdn", "scroll the feed · end jumps to the latest"), ("q", "leave (the council keeps running in the background)"),
                ("ctrl-z  ctrl-l", "suspend · redraw")]
        bw = min(76, W - 6)
        bh = len(rows) + 5
        x0, y0 = (W - bw) // 2, max(1, (H - bh) // 2)
        self.box(x0, y0, bw, bh, CYAN, "KEYS")
        for i, (k, what) in enumerate(rows):
            s.put(x0 + 3, y0 + 2 + i, k, sty(INK, bold=True))
            s.put(x0 + 20, y0 + 2 + i, fit(what, bw - 23), sty(MUTED))
        s.put(x0 + 3, y0 + bh - 2, "any key closes this", sty(DIM))

    # -- consensus
    def draw_consensus(self, t: float):
        s, W, H, c = self.scr, self.scr.w, self.scr.h, self.c
        banner = big("CONSENSUS") if W >= 76 else ["C O N S E N S U S"]
        bw = max(len(r) for r in banner)
        summary = paragraphs(clean((c.ended or {}).get("body") or ""), min(72, W - 8)) or ["(no summary)"]
        files = " · ".join(dict.fromkeys(c.files))
        avail = H - (len(banner) + 12 + (2 if files else 0))
        summary = summary[:max(2, avail)]
        rows = len(banner) + 6 + len(summary) + (2 if files else 0) + 2
        y = max(0, (H - rows) // 2)
        x0 = max(0, (W - bw) // 2)
        age = t - self.cons_t
        reveal = (bw + 8) * age / 1.1
        tear = int(t * 10) % 31 == 0 and age > 1.5
        trow = int(t * 7) % len(banner)
        for r, line in enumerate(banner):
            rowc = mix(OK, CYAN, r / 4)
            shift = (2 if tear and r == trow else 0)
            for i, ch in enumerate(line):
                if ch == " ":
                    continue
                if i < reveal - 4:
                    st, g = sty(CYAN if shift else rowc, bold=True), ch
                    if age > 1.5 and random.random() < .004:
                        st, g = sty(RED), random.choice(GLYPHS)
                elif i < reveal:
                    st, g = sty(WHITE, bold=True), ch
                elif random.random() < .5:
                    st, g = sty(CYAN if random.random() < .3 else DIM), random.choice(GLYPHS)
                else:
                    continue
                s.put(x0 + i + shift, y + r, g, st)
        y += len(banner) + 1
        k = max(1, (bw - 9) // 2)
        wire = "──◉" + "─" * k + "◎" + "─" * k + "◉──"
        wx = max(0, (W - len(wire)) // 2)
        for i, ch in enumerate(wire):
            s.put(wx + i, y, ch, sty(OK, bold=True) if ch in "◉◎" else sty(DIM))
        y += 1
        sub = "L A Y E R   C L O S E D"
        s.put((W - len(sub)) // 2, y, sub, sty(MUTED))
        y += 2
        cost = c.cost or {}
        took = dur(c.end_t - c.started) if c.end_t and c.started else ""
        meta = " · ".join(x for x in (f"done in {took}" if took else "", f"{cost.get('turns')} moderator turns" if cost.get("turns") else "",
                                      f"${float(cost.get('usd') or 0):.2f}" if cost else "", c.council) if x)
        if meta:
            s.put(max(0, (W - tw(meta)) // 2), y, fit(meta, W - 2), sty(INK))
        y += 2
        sw = max(tw(line) for line in summary)
        sx = max(1, (W - sw) // 2)
        for line in summary:
            s.put(sx, y, line, sty(INK))
            y += 1
        if files:
            y += 1
            text = fit("files  " + files, W - 4)
            s.put(max(1, (W - tw(text)) // 2), y, text, sty(MUTED))
            y += 1
        y += 1
        ok = "  ⏎  OK  "                    # one button: back to the session, where NAVI keeps chatting with you
        oy = min(H - 3, y + 1)
        s.put(max(1, (W - tw(ok)) // 2), oy, ok, sty(BG, OK, bold=True))
        after = ("o opens the page it built, with your line in it · q leaves the demo" if self.demo else
                 "then chat with NAVI right in the session · /new <task> runs the council again · /quit leaves")
        s.put(max(1, (W - tw(after)) // 2), min(H - 1, oy + 2), fit(after, W - 2), sty(MUTED))


# ---------------------------------------------------------------- entry point

# ---------------------------------------------------------------- the demo (`navi tui --demo`)

DEMO_TASK = "Build a hello-world page for NAVI: one HTML file, no dependencies, and it has to look like it belongs here"


def make_demo(N) -> tuple[Path, Path, str]:
    """A throwaway project with an empty demo session: the script fills it as it plays. -> (folder, .navi, session id)."""
    root = Path(tempfile.mkdtemp(prefix="navi-demo-"))
    P = root / ".navi"
    sid = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = P / "sessions" / sid
    d.mkdir(parents=True)
    (d / "log.jsonl").touch()
    (d / "session.json").write_text(json.dumps({"task": DEMO_TASK, "name": "demo", "started": N.now(), "pace": "standard",
                                                "demo": True}), encoding="utf-8")
    (P / "current").write_text(sid, encoding="utf-8")
    os.environ["NAVI_DIR"] = str(P)
    os.environ["NAVI_EXIT_WITH"] = str(os.getpid())     # the demo's server ends with this TUI, however it ends
    os.environ["NAVI_DEMO_ROOT"] = str(root)
    return root, P, sid


def play_demo(N, d: Path, stop: threading.Event):
    """The demo council from demo/script.json (the browser's /demo plays the same one), written into the session as it
    plays, so the TUI shows it like a live council. It waits for your answer to its one question; the page it 'builds'
    is the real one, with your line in it."""
    script = json.loads((N.HOME / "demo" / "script.json").read_text(encoding="utf-8"))
    line = script.get("default_line") or ""
    try:
        speed = max(.1, float(os.environ.get("NAVI_DEMO_SPEED", "1")))      # the tests play it faster
    except ValueError:
        speed = 1.0
    for delay, ev in script.get("events") or []:
        if stop.wait(delay / 1000 / speed):
            return
        ev = {k: v.replace("{{line}}", line) if isinstance(v, str) else v for k, v in ev.items()}
        if ev.get("type") == "ask":
            ev["id"] = os.urandom(4).hex()
        if ev.get("type") == "artifact" and ev.get("path"):
            f = d / ev["path"]
            f.parent.mkdir(parents=True, exist_ok=True)
            if ev["path"].endswith("index.html"):
                page = (N.HOME / "demo" / "hello" / "index.html").read_text(encoding="utf-8")
                f.write_text(page.replace("|| 'everything is connected.'", "|| " + json.dumps(line).replace("<", "\\u003c")), encoding="utf-8")
            else:
                f.write_text(str((script.get("files") or {}).get(ev["path"], "")).replace("{{line}}", line), encoding="utf-8")
        with N.in_session(d):
            N.emit(ev)
        if ev.get("type") == "ask":
            reply = d / "replies" / f"{ev['id']}.json"
            while not reply.exists():
                if stop.wait(0.3):
                    return
            try:
                r = json.loads(reply.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                r = {}
            line = re.sub(r"\s+", " ", str(r.get("text") or r.get("choice") or "")).strip()[:80] or line


def end_demo(N, root: Path, P: Path):
    try:
        os.kill(int(json.loads((P / "server.json").read_text(encoding="utf-8"))["pid"]), signal.SIGTERM)
    except (OSError, ValueError, KeyError):
        pass
    shutil.rmtree(root, ignore_errors=True)


def run(N, session: str | None = None, demo: bool = False) -> int:
    """`navi tui`: returns the exit code."""
    if termios is None or not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("navi: `navi tui` needs an interactive terminal (try `navi` for the web interface)", file=sys.stderr)
        return 1
    try:
        apply_palette(N.load_config().get("preset", "ice"))
    except Exception:
        pass
    root = None
    if demo:
        root, P, session = make_demo(N)
    else:
        P = N.navi_dir()
    if session and not (N.SID.match(session) and (P / "sessions" / session / "log.jsonl").exists()):
        print(f"navi: no session '{session}' in {P} (see `navi sessions`)", file=sys.stderr)
        return 1
    try:
        port, token = ensure_server(N, P)
    except RuntimeError as e:
        print(f"navi: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:      # ctrl-c while the server starts, before the TUI takes the keyboard
        return 130
    app = App(N, P, Api(P, port, token), session)
    stop = threading.Event()
    if demo:
        app.demo = True
        threading.Thread(target=play_demo, args=(N, P / "sessions" / session, stop), daemon=True).start()
    try:
        app.run()
    except KeyboardInterrupt:
        return 130
    finally:
        if root:
            stop.set()
            end_demo(N, root, P)
    if app.farewell and not demo:
        print(app.farewell)
    return 0
