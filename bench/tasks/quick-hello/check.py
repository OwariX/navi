"""hello.html has an <h1> that says Hello from NAVI, and a sentence."""
import re
import sys
try:
    page = open("hello.html", encoding="utf-8").read()
except OSError:
    sys.exit("no hello.html")
if not re.search(r"<h1[^>]*>\s*Hello from NAVI\s*</h1>", page):
    sys.exit("no <h1>Hello from NAVI</h1>")
text = re.sub(r"<[^>]+>", " ", page.split("</h1>", 1)[1])
if not re.search(r"[A-Za-z][^.!?]{5,}[.!?]", text):
    sys.exit("no sentence under the heading")
print("ok: the heading and a sentence")
