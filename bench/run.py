"""NAVI's benchmark: real councils on real engines, on small tasks that a script can check. On paid engines it costs
tokens (each run's cost is recorded).
usage: python3 bench/run.py --engine local [--model strong] [--tasks quick-hello,quick-fix-test] [--minutes 30]

For each task (bench/tasks/<name>/: task.json, project/, check.py):
- a fresh git project in a scratch folder, and NAVI's own server with settings of its own (yours are never touched;
  only your engine's model choices are copied from them),
- the council launched the way the Start button does it (The Knights, the task's pace, Allow all),
- questions answered the way a person would ("go ahead", or the first option), and permission cards refused (Allow all
  still asks before anything outside the project),
- then the task's check.py on what the council left behind.
One line per run goes to bench/results.jsonl; bench/report.py turns them into docs/BENCHMARKS.md."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAVI = HERE.parent / "scripts" / "navi.py"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]


def your_engines() -> dict:
    """The models you chose per engine (read only), so a benchmark runs what you'd run."""
    p = Path(os.environ.get("NAVI_CONFIG") or Path.home() / ".config" / "navi" / "config.json")
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("engines") or {}
    except (OSError, ValueError):
        return {}


def run_task(name: str, engine: str, model: str, minutes: float) -> dict:
    tdir = HERE / "tasks" / name
    spec = json.loads((tdir / "task.json").read_text(encoding="utf-8"))
    root = Path(tempfile.mkdtemp(prefix=f"navi-bench-{name}-"))
    proj = root / "proj"
    shutil.copytree(tdir / "project", proj, ignore=shutil.ignore_patterns("__pycache__", ".keep"))
    (proj / ".keep").unlink(missing_ok=True)
    git = ["git", "-c", "user.name=bench", "-c", "user.email=bench@navi.test"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj, check=True)
    subprocess.run(git + ["add", "-A"], cwd=proj, check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "the task as given"], cwd=proj, check=True)
    (proj / ".navi").mkdir()             # NAVI's folder for this project: the server keeps its address and token there
    cfg = root / "config.json"
    cfg.write_text(json.dumps({"setup_complete": True, "moderator": "headless", "guides": False, "engine": engine,
                               "engine_chosen": True, "engines": your_engines()}), encoding="utf-8")
    # NAVI_AFTER_END_WAIT: after the end a moderator stays for a while in case you write; nobody will here
    env = {**os.environ, "NAVI_DIR": str(proj / ".navi"), "NAVI_CONFIG": str(cfg), "NAVI_NO_INTRO": "1", "BROWSER": "true", "NAVI_AFTER_END_WAIT": "5",
           "NAVI_LIBRARY": str(root / "agents"), "NAVI_COUNCILS": str(root / "councils")}
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(NAVI), "serve", "--port", str(port)], cwd=proj, env=env,
                           stdout=open(root / "serve.log", "w"), stderr=subprocess.STDOUT)
    base, tok = f"http://127.0.0.1:{port}", ""
    for _ in range(100):
        try:
            tok = json.loads((proj / ".navi" / "server.json").read_text())["token"]
            urllib.request.urlopen(base + "/status", timeout=5)
            break
        except Exception:
            time.sleep(0.3)
    if not tok:
        srv.terminate()
        sys.exit(f"NAVI's server didn't start: see {root / 'serve.log'}")

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"content-type": "application/json", "X-Navi-Token": tok})
        return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"{}")

    rec = {"date": time.strftime("%Y-%m-%d"), "navi": (HERE.parent / "VERSION").read_text().strip(), "engine": engine,
           "model": model or "default", "task": name, "pace": spec["pace"]}
    t0, ended, restarts, seen, sid, t_end = time.time(), False, 0, 0, "", 0.0
    try:
        sid = post("/launch", {"action": "new", "task": spec["task"], "engine": engine, "pace": spec["pace"], "council": "knights",
                               "permissions": "all", "sensitivity": "public", **({"model": model} if model else {})})["session"]
        logf = proj / ".navi" / "sessions" / sid / "log.jsonl"
        while time.time() - t0 < minutes * 60:
            lines = logf.read_text(encoding="utf-8").splitlines() if logf.exists() else []
            for line in lines[seen:]:
                e = json.loads(line)
                if e.get("type") == "end" and not ended:
                    ended, t_end = True, time.time()
                if e.get("type") == "host" and "restarting" in str(e.get("body")):
                    restarts += 1
                if e.get("type") == "permit":          # a permission card: refused, as a careful person would (Allow all
                    post("/permit", {"id": e.get("id"), "session": sid, "decision": "deny"})   # still asks outside the project)
                    rec["cards"] = rec.get("cards", 0) + 1
                if e.get("type") == "ask":
                    post("/reply", {"id": e.get("id"), "session": sid, "choice": (e.get("options") or [""])[0],
                                    "text": "" if e.get("options") else "Go ahead with your recommendation."})
            seen = len(lines)
            live = [f for f in (proj / ".navi" / "hosts").glob("*.json") if not f.name.endswith("relaunch.json")] if (proj / ".navi" / "hosts").exists() else []
            if ended and not live:
                break
            time.sleep(3)
    finally:
        subprocess.run([sys.executable, str(NAVI), "down"], cwd=proj, env=env, capture_output=True, timeout=60)
        srv.terminate()
    rec["secs"] = round((t_end or time.time()) - t0)          # to the session's end (the moderator may stay a little after)
    rec["ended"] = ended
    meta = {}
    if sid:
        try:
            meta = json.loads((proj / ".navi" / "sessions" / sid / "session.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    models = (meta.get("usage") or {}).get("models") or {}
    rec["models"] = sorted(models)
    rec["tokens_in"] = sum(int(m.get("in", 0)) + int(m.get("cache_read", 0)) + int(m.get("cache_write", 0)) for m in models.values())
    rec["tokens_out"] = sum(int(m.get("out", 0)) for m in models.values())
    rec["usd"] = round(float((meta.get("cost") or {}).get("usd") or 0), 4)
    rec["pace_chosen"] = meta.get("pace_chosen") or spec["pace"]
    rec["restarts"] = restarts
    runs = proj / ".navi" / "sessions" / sid / "runs"
    rec["member_runs"] = len(list(runs.glob("*.json"))) if sid and runs.exists() else 0
    chk = subprocess.run([sys.executable, str(tdir / "check.py")], cwd=proj, env={**os.environ, "BENCH_TASK_DIR": str(tdir)},
                         capture_output=True, text=True, timeout=300)
    rec["check"] = "pass" if chk.returncode == 0 else "fail"
    rec["why"] = ((chk.stdout or "") + (chk.stderr or "")).strip().splitlines()[-1:][0][:200] if (chk.stdout or chk.stderr).strip() else ""
    print(f"  (its project and logs: {root})", flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", required=True)
    ap.add_argument("--model", default="", help="a tier (strong, balanced, fast) or a model; default: the engine's default")
    ap.add_argument("--tasks", default="", help="comma separated; default: every task in bench/tasks")
    ap.add_argument("--minutes", type=float, default=30, help="per task, then it counts as not finished")
    a = ap.parse_args()
    names = [t for t in a.tasks.split(",") if t] or sorted(p.name for p in (HERE / "tasks").iterdir() if (p / "task.json").exists())
    for name in names:
        rec = run_task(name, a.engine, a.model, a.minutes)
        with open(os.environ.get("NAVI_BENCH_RESULTS") or HERE / "results.jsonl", "a", encoding="utf-8") as f:     # tests: elsewhere
            f.write(json.dumps(rec) + "\n")
        print(f"{rec['engine']:<12} {name:<24} {rec['check']:<5} {rec['secs']:>5}s  ended={rec['ended']}  "
              f"{rec['tokens_in'] + rec['tokens_out']:>9} tokens  ${rec['usd']:<7} restarts={rec['restarts']}  {rec['why']}", flush=True)


if __name__ == "__main__":
    main()
