"""find_user works for ordinary names, injection payloads find nobody, and the council's test exists and passes."""
import os
import re
import subprocess
import sys
sys.path.insert(0, ".")
import users  # noqa: E402
conn = users.connect()
users.add_user(conn, "alice", "a@example.com")
users.add_user(conn, "bob", "b@example.com")
users.add_user(conn, "O'Brien", "o@example.com")
row = users.find_user(conn, "alice")
if not row or tuple(row)[1:] != ("alice", "a@example.com"):
    sys.exit(f"find_user('alice') gave {row}")
if users.find_user(conn, "carol") is not None:
    sys.exit("a name nobody has should give None")
try:
    if not users.find_user(conn, "O'Brien"):
        sys.exit("a name with an apostrophe isn't found")
except Exception as e:
    sys.exit(f"a name with an apostrophe raised {e!r}")
for payload in ("' OR '1'='1", "x' OR 1=1 --", "'; DROP TABLE users; --"):
    try:
        got = users.find_user(conn, payload)
    except Exception as e:
        sys.exit(f"{payload!r} raised {e!r} (it should just find nobody)")
    if got is not None:
        sys.exit(f"injection {payload!r} returned {got}")
if conn.execute("SELECT count(*) FROM users").fetchone()[0] != 3:
    sys.exit("the users table changed")
src = open("users.py", encoding="utf-8").read()
if re.search(r"execute\(\s*f[\"']|execute\([^)]*%\s*\(|execute\([^)]*\.format\(", src):
    sys.exit("users.py still builds SQL from strings")
if not os.path.exists("test_users.py"):
    sys.exit("no test_users.py")
r = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_users"], capture_output=True, text=True, timeout=120)
if r.returncode:
    sys.exit("its test fails: " + (r.stderr.strip().splitlines() or ["?"])[-1])
print("ok: ordinary names, an apostrophe, 3 injection payloads, and its own test")
