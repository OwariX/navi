"""`navi engine`, the wizard, in a real pseudo-terminal (fakes on the PATH, a fake Ollama: tests/run.sh).
usage: python3 -I engine_wizard_test.py <scratch dir>
- tick the engines you use (space), pick the default when there are several: only those show up in NAVI
- Local: its checks, the models it suggests, keep them, the free test answers, it's saved
- Codex: change one tier's model, no paid test · q changes nothing · `navi engine add` ticks one more"""
import json
import os
import pty
import re
import select
import subprocess
import sys
import time

sp = sys.argv[1]
os.makedirs(f"{sp}/wzhome", exist_ok=True)
cfgp = f"{sp}/wzhome/config.json"
json.dump({"setup_complete": True, "guides": False}, open(cfgp, "w"))
env = {**os.environ, "NAVI_CONFIG": cfgp, "NAVI_NO_INTRO": "1", "TERM": "xterm-256color", "COLUMNS": "100", "LINES": "40"}
fails = []


def check(ok, what, extra=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"  · {extra}" if extra and not ok else ""))
    if not ok:
        fails.append(what)


class Term:
    def __init__(self, *args):
        self.master, slave = pty.openpty()
        self.p = subprocess.Popen(["navi", *args], cwd=sp, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        self.buf = b""

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    self.buf += os.read(self.master, 65536)
                except OSError:
                    return

    def text(self):
        return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", self.buf).decode("utf-8", "replace")

    def wait_for(self, pat, secs=10):
        end = time.time() + secs
        while time.time() < end:
            self.pump(0.2)
            if re.search(pat, self.text()):
                return True
        return False

    def keys(self, *ks):
        for k in ks:
            os.write(self.master, k)
            self.pump(0.25)

    def done(self):
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()
        return self.p.returncode


UP, DOWN, ENTER, SPACE = b"\x1b[A", b"\x1b[B", b"\r", b" "
t = Term("engine")
check(t.wait_for(r"Which AI programs do you use\?") and all(w in t.text() for w in ("CLAUDE", "LOCAL (OLLAMA)", "CODEX", "GEMINI")),
      "the wizard asks which AI programs you use, and lists every engine", t.text()[-600:])
check(re.search(r"\[✓\] CLAUDE", t.text()) is not None and re.search(r"\[ \] LOCAL", t.text()) is not None,
      "...with the default ticked and the rest not (nothing you didn't choose)", t.text()[-600:])
t.keys(DOWN, SPACE, ENTER)     # Claude (your default) is first; tick Local, the next one
check(t.wait_for(r"Which one runs NAVI by default\?"), "two ticked: it asks which one runs NAVI by default", t.text()[-400:])
t.keys(DOWN, ENTER)            # Claude, then Local
check(t.wait_for(r"Keep these models\?"), "Local: it shows its checks and the models it suggests, and asks to keep them", t.text()[-800:])
tx = t.text()
check("Ollama answering at" in tx and "qwen3-coder:30b" in tx and "qwen2.5:7b" in tx, "...Ollama is checked, the tiers come from what it has", tx[-700:])
t.keys(ENTER)                  # keep them (the default)
check(t.wait_for(r"Try it now\? \(free"), "it offers a free test on this machine", t.text()[-400:])
t.keys(ENTER)                  # yes (the default for a free one)
check(t.wait_for(r"NAVI runs on Local", 30) and re.search(r"answered in [\d.]+s: 'NAVI ONLINE'", t.text()), "the test answers, and NAVI runs on Local now", t.text()[-500:])
check(t.done() == 0, "the wizard ends cleanly")
c = json.load(open(cfgp))
check(c.get("engine") == "local" and c.get("engine_chosen") is True and (c.get("engines") or {}).get("local", {}).get("models", {}).get("strong") == "qwen3-coder:30b",
      "saved: the engine, and the models it suggested (so a new pull doesn't move them)", json.dumps(c.get("engines")))
check(c.get("engines_on") == ["claude", "local"], "...and the two you use: only they show up in NAVI", json.dumps(c.get("engines_on")))

t = Term("engine")
t.wait_for(r"Which AI programs do you use\?")
order = re.findall(r"(CLAUDE|LOCAL \(OLLAMA\)(?: VIA)?|CODEX|GEMINI)", t.text())
check(order[:2] == ["LOCAL (OLLAMA)", "CLAUDE"], "the next time, your engine is first, then the others you use", str(order[:6]))
t.keys(DOWN, SPACE, DOWN, SPACE, ENTER)      # untick Claude, tick Codex
t.wait_for(r"Which one runs NAVI by default\?")
t.keys(DOWN, ENTER)            # Local (yours), then Codex
check(t.wait_for(r"Keep these models\?"), "Codex: its checks and its models", t.text()[-600:])
check("signed in to Codex" in t.text() and "gpt-test-sol" in t.text(), "...signed in, tiers from its own model list", t.text()[-600:])
t.keys(b"n", ENTER)
check(t.wait_for(r"Strong"), "changing them asks per tier", t.text()[-300:])
t.keys(ENTER)                  # strong: KEEP
t.wait_for(r"Balanced")
t.keys(DOWN, ENTER)            # balanced: the first other model
t.wait_for(r"Fast")
t.keys(ENTER)                  # fast: KEEP
check(t.wait_for(r"Try it now\? \(one short question: a few tokens\)"), "for a paid engine the test asks first (a few tokens)", t.text()[-300:])
t.keys(ENTER)                  # no (the default when it costs)
check(t.wait_for(r"NAVI runs on Codex") and "answered in" not in t.text().split("Try it now")[-1], "no test unless you say so; NAVI runs on Codex")
t.done()
c = json.load(open(cfgp))
m = (c.get("engines") or {}).get("codex", {}).get("models", {})
check(c.get("engine") == "codex" and m.get("strong") == "gpt-test-sol" and m.get("balanced") not in ("", None, "gpt-test-sol-2"),
      "saved: Codex, with the balanced model you picked", json.dumps(m))
check(c.get("engines_on") == ["local", "codex"], "...Claude unticked is gone from what NAVI offers", json.dumps(c.get("engines_on")))

t = Term("engine")
t.wait_for(r"Which AI programs do you use\?")
t.keys(b"q")
check(t.wait_for(r"nothing changed"), "q: nothing changed, and it says what NAVI runs on", t.text()[-300:])
t.done()
check(json.load(open(cfgp)).get("engine") == "codex", "...and the setting stays")

t = Term("engine", "add")        # more later: the same ticks, the default stays
t.wait_for(r"Which AI programs do you use\?")
order = re.findall(r"\[[ ✓]\] (CLAUDE|LOCAL \(OLLAMA\) VIA CODEX|LOCAL \(OLLAMA\)|CODEX|GEMINI)", t.text())
t.keys(*([DOWN] * order.index("GEMINI")), SPACE, ENTER)
check(t.wait_for(r"NAVI offers Local \(Ollama\), Codex, Gemini · Codex by default"), "navi engine add: tick one more, the default stays", t.text()[-300:])
t.done()
check(json.load(open(cfgp)).get("engines_on") == ["local", "codex", "gemini"], "...saved", json.dumps(json.load(open(cfgp)).get("engines_on")))
print("ENGINE WIZARD SUITE PASSED" if not fails else f"ENGINE WIZARD SUITE FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
