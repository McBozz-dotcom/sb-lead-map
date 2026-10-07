#!/usr/bin/env python3
"""Serve the map locally and save your lead statuses to data/lead_status.json.

    python serve.py            # http://127.0.0.1:8000
    python serve.py --port 9000 --no-browser
"""
import argparse
import datetime
import http.server
import json
import os
import posixpath
import threading
import urllib.parse
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(ROOT, "data", "lead_status.json")
VALID = {"new", "contacted", "interested", "not_interested"}
_lock = threading.Lock()


def load_statuses():
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if self.command == "POST" or (args and str(args[1]).startswith(("4", "5"))):
            super().log_message(fmt, *args)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        if self.path == "/api/status":
            return self._json(200, load_statuses())
        # Only expose the web app and the generated businesses file (never .env or lead_status.json).
        clean = posixpath.normpath(urllib.parse.unquote(self.path.split("?")[0]))
        if not (clean.startswith("/web/") or clean == "/web" or clean == "/data/businesses.json"):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/status":
            return self.send_error(404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(min(length, 100_000)))
            lead_id, status = str(req["id"]), req.get("status", "new")
            note = str(req.get("note", ""))[:5000]
            if status not in VALID:
                raise ValueError("bad status")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"error": str(e)})
        with _lock:
            data = load_statuses()
            if status == "new" and not note:
                data.pop(lead_id, None)
            else:
                data[lead_id] = {"status": status, "note": note,
                                 "updated": datetime.datetime.now().isoformat(timespec="seconds")}
            tmp = STATUS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, STATUS_PATH)
        return self._json(200, {"ok": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", "businesses.json")):
        print("Note: data/businesses.json not found yet - run `python collect.py` first.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/web/"
    print(f"SB Lead Map running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
