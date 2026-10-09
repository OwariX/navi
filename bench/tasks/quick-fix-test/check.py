"""The tests are untouched and pass, and so do cases they don't cover."""
import os
import subprocess
import sys
orig = os.path.join(os.environ["BENCH_TASK_DIR"], "project", "test_fizzbuzz.py")   # the runner says where the task is
if open("test_fizzbuzz.py", "rb").read() != open(orig, "rb").read():
    sys.exit("test_fizzbuzz.py was changed")
r = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_fizzbuzz"], capture_output=True, text=True)
if r.returncode:
    sys.exit("the tests fail: " + (r.stderr.strip().splitlines() or ["?"])[-1])
sys.path.insert(0, ".")
from fizzbuzz import fizzbuzz  # noqa: E402
cases = {2: "2", 3: "Fizz", 5: "Buzz", 30: "FizzBuzz", 98: "98", 99: "Fizz", 100: "Buzz"}
bad = {n: fizzbuzz(n) for n, v in cases.items() if fizzbuzz(n) != v}
if bad:
    sys.exit(f"wrong for {bad}")
print("ok: the tests pass, unchanged, and so do 7 more cases")
