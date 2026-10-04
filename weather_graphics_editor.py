#!/usr/bin/env python3
"""Weather Graphics Editor: local editor for config.json and overrides.json.

    python weather_graphics_editor.py            -> opens http://localhost:8770 in your browser

Loads/saves the two JSON files in place (a .bak copy is kept), shows the latest forecast so you can
see what you're overriding, and can run the graphics from the page. Standard library only; it only
listens on this computer (127.0.0.1).
"""
import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8770
PAGE = ROOT / "Weather Graphics Editor.html"
FILES = {"config": ROOT / "config.json", "overrides": ROOT / "overrides.json",
         "forecast": ROOT / "output" / "latest" / "forecast.json"}
RUN_FLAGS = {"--sample", "--no-overrides", "--outlook-debug"}
_run_lock = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, PAGE.read_bytes(), "text/html")
        if path.startswith("/api/") and path[5:] in FILES:
            f = FILES[path[5:]]
            return self._send(200, f.read_text(encoding="utf-8") if f.exists() else "null")
        if path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "root": str(ROOT)}))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        if path in ("/api/config", "/api/overrides"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                return self._send(400, json.dumps({"error": f"Invalid JSON: {e}"}))
            f = FILES[path[5:]]
            if f.exists():
                shutil.copyfile(f, f.with_suffix(".json.bak"))
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return self._send(200, json.dumps({"ok": True, "saved": f.name}))
        if path == "/api/run":
            try:
                req = json.loads(raw or "{}")
            except json.JSONDecodeError:
                req = {}
            args = [a for a in req.get("flags", []) if a in RUN_FLAGS]
            only = [g for g in req.get("only", []) if g.replace("_", "").isalnum()]
            if only:
                args += ["--only", ",".join(only)]
            if not _run_lock.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "A render is already running."}))
            try:
                p = subprocess.run([sys.executable, str(ROOT / "run.py"), *args], cwd=ROOT, capture_output=True,
                                   text=True, timeout=900)
                return self._send(200, json.dumps({"ok": p.returncode == 0, "log": (p.stdout + p.stderr)[-12000:]}))
            except subprocess.TimeoutExpired:
                return self._send(500, json.dumps({"error": "Render timed out."}))
            finally:
                _run_lock.release()
        self._send(404, json.dumps({"error": "not found"}))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://localhost:{PORT}/"
    print(f"Weather Graphics Editor running at {url}  (close this window or Ctrl+C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
