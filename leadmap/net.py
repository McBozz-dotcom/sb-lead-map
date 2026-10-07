"""Small stdlib-only HTTP helpers: .env loading, polite rate-limited requests."""
import json
import os
import time
import urllib.error
import urllib.request

USER_AGENT = "SBLeadMap/1.0 (local small-business lead research; contact: {contact})"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """Load KEY=VALUE pairs from .env into os.environ (existing vars win)."""
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


def user_agent():
    return USER_AGENT.format(contact=os.environ.get("CONTACT_EMAIL") or "not provided")


class RateLimiter:
    """Ensures at least `interval` seconds between calls."""

    def __init__(self, interval):
        self.interval = interval
        self._last = 0.0

    def wait(self):
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


def request(url, data=None, headers=None, method=None, timeout=30, max_bytes=None):
    """Return (status, final_url, headers, body_bytes, elapsed_seconds). Raises on network errors."""
    hdrs = {"User-Agent": user_agent()}
    hdrs.update(headers or {})
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes) if max_bytes else resp.read()
            return resp.status, resp.geturl(), dict(resp.headers), body, time.monotonic() - start
    except urllib.error.HTTPError as e:
        body = e.read(max_bytes) if max_bytes else e.read()
        return e.code, url, dict(e.headers or {}), body, time.monotonic() - start


def get_json(url, **kw):
    status, _, _, body, _ = request(url, **kw)
    if status >= 400:
        raise RuntimeError(f"HTTP {status} from {url.split('?')[0]}: {body[:300]!r}")
    return json.loads(body)
