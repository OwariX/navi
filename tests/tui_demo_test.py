"""`navi tui --demo` in a real pseudo-terminal: the scripted council plays, its one question waits for an answer,
the page it 'builds' carries that answer, q leaves, the throwaway project is gone, and no real moderator ever started.
usage: python3 -I tui_demo_test.py <scratch dir>"""
import codecs
import fcntl
import glob
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time

sp = sys.argv[1]
tmp = os.path.join(sp, "demotmp")
os.makedirs(tmp, exist_ok=True)
fake_log = os.path.join(sp, "demo-fake.log")
open(fake_log, "w").close()
env = {**os.environ, "TMPDIR": tmp, "NAVI_DEMO_SPEED": "8", "BROWSER": "true", "TERM": "xterm-256color", "COLUMNS": "120",
       "LINES": "40", "FAKE_LOG": fake_log}
env.pop("NAVI_DIR", None)
m, s = pty.openpty()
fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
p = subprocess.Popen(["navi", "tui", "--demo"], cwd=sp, env=env, stdin=s, stdout=s, stderr=s, start_new_session=True)
os.close(s)
dec, txt, fails = codecs.getincrementaldecoder("utf-8")("replace"), "", []
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b.")


def pump(secs):
    global txt
    end = time.time() + secs
    while time.time() < end:
        if select.select([m], [], [], .05)[0]:
            try:
                txt += ANSI.sub("", dec.decode(os.read(m, 65536)))
            except OSError:
                return


def wait(sub, secs, what):
    end = time.time() + secs
    while time.time() < end:
        if sub in txt[-60000:]:
            return True
        pump(.2)
    fails.append(what)
    print(f"--- TIMEOUT waiting for: {what}\n{txt[-1500:]}\n--- end")
    return False


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        fails.append(what)


check(wait("DEMO", 25, "the demo starts"), "navi tui --demo opens with the DEMO badge")
check(wait("asks you", 60, "the architect's question"), "the scripted council plays and asks its one question")
for ch in "the tui demo works":
    os.write(m, ch.encode())
    pump(.03)
os.write(m, b"\r")
check(wait("CONSENSUS", 60, "the end"), "the answer goes back, the council finishes: CONSENSUS")
check(wait("o opens the page it built", 15, "the CONSENSUS screen"), "the CONSENSUS screen says o opens the page it built")
pages = glob.glob(os.path.join(tmp, "navi-demo-*", ".navi", "sessions", "*", "out", "index.html"))
check(len(pages) == 1 and "the tui demo works" in open(pages[0], encoding="utf-8").read(), "the page it built carries your line")
os.write(m, b"q")
end = time.time() + 15
while p.poll() is None and time.time() < end:
    pump(.2)
check(p.poll() == 0, f"q leaves cleanly (code {p.poll()})")
check(not glob.glob(os.path.join(tmp, "navi-demo-*")), "the throwaway project is gone")
check(os.path.getsize(fake_log) == 0, "no moderator was ever started (claude never ran)")
# killed instead of quit (a closed terminal): its server still goes away, and its folder with it
for f in glob.glob(os.path.join(tmp, "*")):
    pass
m2, s2 = pty.openpty()
fcntl.ioctl(s2, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
p2 = subprocess.Popen(["navi", "tui", "--demo"], cwd=sp, env=env, stdin=s2, stdout=s2, stderr=s2, start_new_session=True)
os.close(s2)
end = time.time() + 20
while time.time() < end and not glob.glob(os.path.join(tmp, "navi-demo-*", ".navi", "server.json")):
    if select.select([m2], [], [], .2)[0]:
        try:
            os.read(m2, 65536)
        except OSError:
            break
srv = glob.glob(os.path.join(tmp, "navi-demo-*", ".navi", "server.json"))
pid = __import__("json").load(open(srv[0]))["pid"] if srv else 0
p2.kill()
p2.wait()
gone = False
for _ in range(40):
    time.sleep(.25)
    try:
        os.kill(pid, 0)
    except OSError:
        gone = True
        break
check(bool(pid) and gone, "killed instead of quit: the demo's server ends by itself")
time.sleep(.5)
check(not glob.glob(os.path.join(tmp, "navi-demo-*")), "...and its throwaway folder is removed")
if p.poll() is None:
    p.kill()
print("TUI DEMO SUITE PASSED" if not fails else f"TUI DEMO SUITE FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
