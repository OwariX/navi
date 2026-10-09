"""TokenBucket behaves as asked (with a fake clock), and the council's own tests exist and pass."""
import os
import subprocess
import sys
sys.path.insert(0, ".")
try:
    from ratelimit import TokenBucket
except Exception as e:
    sys.exit(f"can't import ratelimit.TokenBucket: {e}")
now = [1000.0]
b = TokenBucket(3, 60, clock=lambda: now[0])
got = [b.allow("a") for _ in range(4)]
if got != [True, True, True, False]:
    sys.exit(f"3 per minute: the first four calls gave {got}")
if not b.allow("b"):
    sys.exit("another key was limited too")
now[0] += 20
if [b.allow("a"), b.allow("a")] != [True, False]:
    sys.exit("after 20 s exactly one more request should pass (a token every 20 s)")
now[0] += 600
if [b.allow("a") for _ in range(4)] != [True, True, True, False]:
    sys.exit("after a long wait it should hold `capacity` tokens, no more")
if not os.path.exists("test_ratelimit.py"):
    sys.exit("no test_ratelimit.py")
r = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_ratelimit"], capture_output=True, text=True, timeout=120)
if r.returncode:
    sys.exit("its tests fail: " + (r.stderr.strip().splitlines() or ["?"])[-1])
print("ok: 5 behaviours checked with a fake clock, and its own tests pass")
