"""A fake Ollama for the tests: the parts of its API NAVI uses (version, tags, show, ps, chat), canned answers, and a
log of every request. usage: python3 -I fake_ollama.py <port> <log file>"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port, logf = int(sys.argv[1]), sys.argv[2]
MODELS = {"qwen3-coder:30b": (18_600_000_000, "30.5B", ["completion", "tools"]),
          "qwen2.5:7b": (4_700_000_000, "7.6B", ["completion", "tools"]),
          "gpt-oss:20b": (13_000_000_000, "20.9B", ["completion", "tools", "thinking"]),
          "nomic-embed-text:latest": (274_000_000, "137M", ["embedding"]),
          "tinyllama:latest": (640_000_000, "1.1B", ["completion"])}
PERSONA = """---
name: NAME_HERE
description: "Written by the fake Ollama for the tests."
role: "tester"
color: "#9ae6b4"
model: ""
---
You are **UPPER_HERE**, the council's tester.

You check one thing well and leave design and building to the lead.

- Read your inbox before acting, and review every `proposal` and `revision` sent to you.
- Back every claim with the real code or config: gate every read with `navi gate` first.
- End every round with a `verdict` to `all`: approve, approve with conditions, or needs work.
- Never approve what you haven't checked."""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _log(self, what):
        with open(logf, "a") as f:
            f.write(json.dumps(what) + "\n")

    def do_GET(self):
        self._log({"GET": self.path})
        if self.path == "/api/version":
            return self._json({"version": "0.0.0-fake"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": n, "model": n, "size": s, "details": {"parameter_size": p, "family": n.split(":")[0]},
                                           "capabilities": c} for n, (s, p, c) in MODELS.items()]})
        if self.path == "/api/ps":
            return self._json({"models": [{"name": "qwen3-coder:30b", "context_length": 65536}]})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self._log({"POST": self.path, "model": body.get("model"), "options": body.get("options")})
        if self.path == "/api/show":
            m = MODELS.get(body.get("model") or "")
            return self._json({"capabilities": m[2]}) if m else self._json({"error": "model not found"}, 404)
        if self.path == "/api/create":          # a copy of a model with other parameters (NAVI's bigger context window)
            base = MODELS.get(body.get("from") or "")
            if not base or body.get("stream") is not False:
                return self._json({"error": "from: no such model (or not stream: false)"}, 400)
            MODELS[body["model"]] = base
            return self._json({"status": "success"})
        if self.path == "/api/chat":
            if body.get("model") not in MODELS:
                return self._json({"error": f"model '{body.get('model')}' not found"}, 404)
            prompt = (body.get("messages") or [{}])[-1].get("content") or ""
            if "NAVI ONLINE" in prompt:
                ans = "NAVI ONLINE"
            elif "NAVI's checker scored this persona file" in prompt:      # the repair round: what it found, fixed
                import re
                n = (re.search(r"You are \*\*([A-Z0-9_-]+)\*\*", prompt) or [None, "AGENT"])[1]
                ans = (PERSONA.replace("NAME_HERE", n.lower()).replace("UPPER_HERE", n)
                       + "\n- Run the tests with `python3 -m unittest -v` and quote the line that proves your verdict."
                       + "\n\nYour lens is test coverage: whether each change is proven by a test that fails without it. "
                         "Design and cost belong to the other members.")
            elif "You write council-member personas for NAVI" in prompt:
                import re
                n = (re.search(r'Write the complete persona file for "([a-z0-9_-]+)"', prompt) or [None, "agent"])[1]
                ans = PERSONA.replace("NAME_HERE", n).replace("UPPER_HERE", n.upper())
            elif "<task>navi-read-sources</task>" in prompt:
                ans = json.dumps({"sources": [{"kind": "web", "value": "learn.microsoft.com/azure", "note": "Azure docs"}], "question": ""})
            else:
                ans = "OK"
            return self._json({"model": body.get("model"), "message": {"role": "assistant", "content": ans}, "done": True})
        self._json({"error": "not found"}, 404)


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
