"""Drive the `navi` terminal menu in a real pseudo-terminal: pick START, hand off to the web menu, watch the launch.

usage: python3 -I term_start.py <project-dir> <scratch-dir> <council> <task>
The fake Claude (tests/fake-claude) must be first on PATH as `claude`; run.sh arranges that.
"""
import os
import pty
import re
import select
import subprocess
import sys
import time

proj, sp, council, task = sys.argv[1:5]
tests = os.path.dirname(os.path.abspath(__file__))
env = {**os.environ, "NAVI_CONFIG": f"{sp}/home/config.json", "NAVI_LIBRARY": f"{sp}/home/agents",
       "NAVI_COUNCILS": f"{sp}/home/councils", "NAVI_NO_INTRO": "1", "BROWSER": "true",
       "FAKE_LOG": f"{sp}/tfake.log", "FAKE_SLEEP": "6", "TERM": "xterm-256color"}
env.pop("NAVI_DIR", None)
master, slave = pty.openpty()
p = subprocess.Popen(["navi"], cwd=proj, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
os.close(slave)
buf = b""


def pump(secs):
    global buf
    end = time.time() + secs
    while time.time() < end:
        if select.select([master], [], [], 0.1)[0]:
            try:
                buf += os.read(master, 65536)
            except OSError:
                return


def text():
    return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", buf).decode("utf-8", "replace")


pump(2.5)
print("--- menu shows START:", "START" in text() and "START IN THIS TERMINAL" in text())
os.write(master, b"\x1b[B"); pump(0.2); os.write(master, b"\x1b[B"); pump(0.2)   # START, START TUI, START IN THIS TERMINAL
os.write(master, b"\r")
m = None
for _ in range(60):
    pump(0.3)
    m = re.search(r"main menu open at (http://127\.0\.0\.1:\d+/)", text())
    if m:
        break
url = m.group(1) if m else None
print("--- web menu url:", url)
if url:
    r = subprocess.run(["node", f"{tests}/e2e/web_start.js", url, sp, council, task], cwd=f"{tests}/e2e",
                       capture_output=True, text=True, timeout=90)
    print("--- browser:\n" + r.stdout + r.stderr)
pump(10)
p.wait(timeout=20)
print("--- launcher exit code:", p.returncode)
log = open(f"{sp}/tfake.log").read() if os.path.exists(f"{sp}/tfake.log") else ""
ok = p.returncode == 0 and "argv:" in log and "lead=architect" in log and "\n  [-p]\n" not in log.split("hid=")[0]
print("--- the moderator ran in the terminal (no -p), as the launcher:", ok)
sys.exit(0 if ok else 1)
