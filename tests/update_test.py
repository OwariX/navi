"""`navi update` against a throwaway origin (no network): a clone on 0.9.001, a 0.9.002 release on its origin.
usage: python3 -I update_test.py <navi.py> <scratch dir>"""
import json
import os
import shutil
import subprocess
import sys

navi, sp = sys.argv[1], sys.argv[2]
T = os.path.join(sp, "upd")
shutil.rmtree(T, ignore_errors=True)
os.makedirs(T)
fails = []
env = {**os.environ, "NAVI_CONFIG": os.path.join(T, "cfg", "config.json"), "GIT_CONFIG_GLOBAL": "/dev/null",
       "GIT_AUTHOR_NAME": "navi-tests", "GIT_AUTHOR_EMAIL": "t@navi.test", "GIT_COMMITTER_NAME": "navi-tests",
       "GIT_COMMITTER_EMAIL": "t@navi.test"}


def check(ok, what, extra=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"  · {extra}" if extra and not ok else ""))
    if not ok:
        fails.append(what)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def run_navi(clone, *args):
    r = subprocess.run([sys.executable, os.path.join(clone, "scripts", "navi.py"), *args], env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


src, bare, clone = (os.path.join(T, x) for x in ("src", "origin.git", "clone"))
for part in ("scripts", "councils", "agents", "web"):      # a NAVI as people have it (the menu needs its councils)
    shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(navi))), part), os.path.join(src, part),
                    ignore=shutil.ignore_patterns("__pycache__"))
open(os.path.join(src, "VERSION"), "w").write("0.9.001\n")
open(os.path.join(src, "CHANGELOG.md"), "w").write("# Changelog\n\n## 0.9.001 (2026-10-07)\n\n- the first one\n")
git(src, "init", "-q", "-b", "main")
git(src, "add", "-A")
git(src, "commit", "-qm", "0.9.001")
git(src, "tag", "-a", "v0.9.001", "-m", "NAVI 0.9.001")
git(T, "clone", "-q", "--bare", src, bare)
git(src, "remote", "add", "origin", bare)
git(T, "clone", "-q", bare, clone)

code, out = run_navi(clone, "--version")
check(code == 0 and "NAVI 0.9.001" in out, "navi --version says which NAVI this is", out)
code, out = run_navi(clone, "update", "--check")
check(code == 0 and "up to date (0.9.001)" in out, "nothing newer yet: up to date", out)

# a new release on GitHub (here: the throwaway origin)
open(os.path.join(src, "VERSION"), "w").write("0.9.002\n")
open(os.path.join(src, "CHANGELOG.md"), "a").write("\n## 0.9.002 (2026-10-08)\n\n- something new for the test\n")
git(src, "commit", "-qam", "0.9.002")
git(src, "tag", "-a", "v0.9.002", "-m", "NAVI 0.9.002")
git(src, "push", "-q", "origin", "main", "v0.9.001", "v0.9.002")

code, out = run_navi(clone, "update", "--check")
check(code == 0 and "0.9.002 is out (you have 0.9.001)" in out, "update --check sees the new release and changes nothing", out)
check(open(os.path.join(clone, "VERSION")).read().strip() == "0.9.001", "...still on 0.9.001")
note = json.load(open(os.path.join(T, "cfg", "update.json")))
check(note.get("latest") == "0.9.002", "the check is remembered for the interface (update.json)", json.dumps(note))

nav = os.path.join(clone, "scripts", "navi.py")
keep = open(nav).read()
open(nav, "a").write("\n# a local change\n")
code, out = run_navi(clone, "update")
check(code != 0 and "local changes" in out, "update refuses to run over your local changes", out)
open(nav, "w").write(keep)

code, out = run_navi(clone, "update")
check(code == 0 and "updated to 0.9.002" in out and "something new for the test" in out, "update fast-forwards to 0.9.002 and shows what's new", out)
check(open(os.path.join(clone, "VERSION")).read().strip() == "0.9.002", "...the clone is on 0.9.002")
code, out = run_navi(clone, "update")
check(code == 0 and "up to date (0.9.002)" in out, "a second update: up to date", out)

# ---- the setting: NAVI updates itself, or tells you
code, out = run_navi(clone, "update", "--auto", "on")
check(code == 0 and json.load(open(os.path.join(T, "cfg", "config.json"))).get("auto_update") is True and "updates itself" in out,
      "navi update --auto on: NAVI installs new releases by itself", out)
code, out = run_navi(clone, "update", "--auto", "off")
check(code == 0 and json.load(open(os.path.join(T, "cfg", "config.json"))).get("auto_update") is False and "tells you" in out,
      "...--auto off: it only tells you", out)


def release(v, note):
    open(os.path.join(src, "VERSION"), "w").write(v + "\n")
    open(os.path.join(src, "CHANGELOG.md"), "a").write(f"\n## {v} (2026-10-09)\n\n- {note}\n")
    git(src, "commit", "-qam", v)
    git(src, "tag", "-a", f"v{v}", "-m", f"NAVI {v}")
    git(src, "push", "-q", "origin", "main", f"v{v}")


# ---- the interface: Update installs it, this server says "installed", Restart brings it back up on the new one
import socket, time, urllib.request  # noqa: E401,E402
release("0.9.003", "the interface update")
proj = os.path.join(T, "proj")
os.makedirs(os.path.join(proj, ".navi"), exist_ok=True)
s_ = socket.socket(); s_.bind(("127.0.0.1", 0)); port = s_.getsockname()[1]; s_.close()
senv = {**env, "NAVI_DIR": os.path.join(proj, ".navi"), "NAVI_NO_INTRO": "1", "BROWSER": "true"}
srv = subprocess.Popen([sys.executable, os.path.join(clone, "scripts", "navi.py"), "serve", "--port", str(port)], cwd=proj, env=senv,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get(path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10).read())


def post(path, body=None):
    tok = json.load(open(os.path.join(proj, ".navi", "server.json")))["token"]
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body or {}).encode(),
                                 headers={"content-type": "application/json", "X-Navi-Token": tok})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as e:
        return {"status": e.code, **json.loads(e.read() or b"{}")}


def until(fn, secs=30):
    end = time.time() + secs
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(.3)
    return None


try:
    until(lambda: get("/version"))
    j = post("/update")
    res = until(lambda: (lambda x: x.get("result") if x.get("state") == "done" else None)(get(f"/jobs?id={j.get('job')}")), 60) or {}
    st = (get("/status") or {}).get("update") or {}
    check(res.get("ok") and st.get("installed") and st.get("version") == "0.9.003" and st.get("running") == "0.9.002",
          "Update in the interface: 0.9.003 installed; this server says it still runs 0.9.002 (restart to update)", json.dumps([res, st]))
    r = post("/restart")
    back = until(lambda: (lambda v: v if v.get("running") == "0.9.003" else None)(get("/version")), 30) or {}
    check(r.get("restarting") and back.get("version") == "0.9.003" and not back.get("installed"),
          "...Restart: the server comes back on 0.9.003", json.dumps([r, back]))
finally:
    for _ in range(2):
        try:
            pid = json.load(open(os.path.join(proj, ".navi", "server.json")))["pid"]
            os.kill(pid, 15)
        except Exception:
            pass
    srv.terminate()

# ---- the terminal menu: says an update is out; with auto updates on, it installs it and starts on it
import pty, select, re  # noqa: E401,E402


def menu_output(secs=25, want=None):
    m, sl = pty.openpty()
    p = subprocess.Popen([sys.executable, os.path.join(clone, "scripts", "navi.py")], cwd=proj, stdin=sl, stdout=sl, stderr=sl,
                         env={**senv, "TERM": "xterm-256color", "COLUMNS": "100", "LINES": "40"}, start_new_session=True)
    os.close(sl)
    buf, end = b"", time.time() + secs
    while time.time() < end:
        if select.select([m], [], [], .2)[0]:
            try:
                buf += os.read(m, 65536)
            except OSError:
                break
        if want and re.search(want, re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", buf).decode("utf-8", "replace")):
            break
    p.kill()
    return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", buf).decode("utf-8", "replace")


# END SESSIONS is in the menu, and says what's open
subprocess.run([sys.executable, os.path.join(clone, "scripts", "navi.py"), "init", "--task", "an open one"], cwd=proj, env=senv, capture_output=True, timeout=60)
out = menu_output(want=r"END SESSIONS.*open here")
check(re.search(r"END SESSIONS\s+1 open here", out) is not None, "the terminal menu has END SESSIONS, with how many are open here", out[-500:])
release("0.9.004", "the menu update")
# the last check is two hours old and knew nothing newer (it used to wait a day, so a release went unnoticed): the menu
# asks again while its intro plays, and already says so this time
json.dump({"latest": "0.9.003", "checked": time.time() - 7200}, open(os.path.join(T, "cfg", "update.json"), "w"))
out = menu_output(want=r"0\.9\.004 is out")
check("NAVI 0.9.004 is out" in out and "UPDATE" in out and open(os.path.join(clone, "VERSION")).read().strip() == "0.9.003",
      "a new release shows in the terminal menu the first time it opens (an old check is asked again), with UPDATE to get it", out[-600:])
check(json.load(open(os.path.join(T, "cfg", "update.json"))).get("latest") == "0.9.004", "...and the interface knows it too (update.json)")
run_navi(clone, "update", "--auto", "on")
out = menu_output(want=r"Updated to NAVI 0\.9\.004")
check("Updated to NAVI 0.9.004" in out and "from 0.9.003" in out and open(os.path.join(clone, "VERSION")).read().strip() == "0.9.004",
      "with auto updates on, the menu installs 0.9.004 and starts again on it", out[-600:])

# NAVI's repository starts over (deleted and made again with one fresh commit, no shared history): a copy that sits on a
# release follows it with `navi update`; one with commits of its own is never overwritten
import shutil  # noqa: E402
mine = os.path.join(T, "clone-with-my-commit")
git(T, "clone", "-q", bare, mine)
git(mine, "checkout", "-q", "v0.9.004")
git(mine, "checkout", "-q", "-B", "main")
open(os.path.join(mine, "MY-NOTES.md"), "w").write("my own work\n")
git(mine, "add", "MY-NOTES.md")
git(mine, "-c", "user.email=t@navi.test", "-c", "user.name=t", "commit", "-qm", "my own commit")
fresh = os.path.join(T, "fresh")
shutil.copytree(src, fresh, ignore=shutil.ignore_patterns(".git"))
open(os.path.join(fresh, "VERSION"), "w").write("0.9.005\n")
git(fresh, "init", "-q", "-b", "main")
git(fresh, "add", "-A")
git(fresh, "-c", "user.email=t@navi.test", "-c", "user.name=t", "commit", "-qm", "NAVI 0.9.005")
git(fresh, "-c", "user.email=t@navi.test", "-c", "user.name=t", "tag", "-a", "v0.9.005", "-m", "NAVI 0.9.005")
shutil.rmtree(bare)                                    # the repository, deleted and made again with only the new commit
git(T, "clone", "-q", "--bare", fresh, bare)
code, out = run_navi(clone, "update")
check(code == 0 and "updated to 0.9.005" in out and open(os.path.join(clone, "VERSION")).read().strip() == "0.9.005",
      "the repository started over (no shared history): navi update follows it to the new release", out)
check(git(clone, "rev-parse", "HEAD").strip() == git(fresh, "rev-parse", "HEAD").strip(), "...and the copy is exactly that release")
code, out = run_navi(mine, "update")
check(code != 0 and "own commits" in out and os.path.exists(os.path.join(mine, "MY-NOTES.md")),
      "...while a copy with commits of its own is never overwritten (it says to update by hand)", out)

print("UPDATE SUITE PASSED" if not fails else f"UPDATE SUITE FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
