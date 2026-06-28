#!/usr/bin/env python3
"""Kivun update-mirror upload endpoint (runs on the VPS).

CI POSTs each tagged installer here over HTTPS (the CI runner is unfiltered);
the gov machine then pulls it over SSH (HTTPS out is blocked there — see
src/core/update_checker.py and log_mirror.py). This server only handles the
*upload* side; the *download* side is plain scp of the files this writes.

Contract (must match update_checker.py + the CI step in build-release.yml):

    POST /  (whatever path the reverse proxy maps here)
      Authorization: Bearer <KIVUN_UPLOAD_TOKEN>
      X-Kivun-Version: 0.9.6
      Content-Type: application/octet-stream
      body: the raw .exe bytes

  On success it writes, into UPDATE_DIR (default /srv/kivun-updates):
      Setup-latest.exe          (atomic: tmp file -> os.replace)
      latest.json               {"version","file":"Setup-latest.exe","sha256"}
  and returns 200 with the sha256.

Run behind the existing TLS reverse proxy (nginx) — bind localhost only:

    KIVUN_UPLOAD_TOKEN=... UPDATE_DIR=/srv/kivun-updates \
        python3 kivun_update_server.py 127.0.0.1 8099

ponytail: single-file stdlib server, no framework. Keeps only the latest build
(overwrite) — zero disk accumulation. For rollback, keep last N here instead.
"""
import hashlib
import hmac
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPDATE_DIR = os.environ.get("UPDATE_DIR", "/srv/kivun-updates")
TOKEN = os.environ.get("KIVUN_UPLOAD_TOKEN", "")
MAX_BYTES = 200 * 1024 * 1024          # 200 MB cap — installer is ~65 MB
EXE_NAME = "Setup-latest.exe"          # stable name the gov machine pulls
_VERSION_RE = re.compile(r"^[0-9A-Za-z.\-]{1,32}$")  # no path chars / no spaces


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, msg: str) -> None:
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        # --- auth (constant-time) ---
        auth = self.headers.get("Authorization", "")
        sent = auth[7:] if auth.startswith("Bearer ") else ""
        if not TOKEN or not hmac.compare_digest(sent, TOKEN):
            return self._reply(401, "unauthorized")

        # --- validate version (it names nothing on disk, but sanitize anyway) ---
        version = (self.headers.get("X-Kivun-Version") or "").strip()
        if not _VERSION_RE.match(version):
            return self._reply(400, "bad or missing X-Kivun-Version")

        # --- bounded body read ---
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._reply(400, "bad Content-Length")
        if length <= 0 or length > MAX_BYTES:
            return self._reply(413, "missing body or too large")

        os.makedirs(UPDATE_DIR, exist_ok=True)
        tmp = os.path.join(UPDATE_DIR, EXE_NAME + ".tmp")
        h = hashlib.sha256()
        got = 0
        try:
            with open(tmp, "wb") as f:
                while got < length:
                    chunk = self.rfile.read(min(1 << 20, length - got))
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
            if got != length:
                os.remove(tmp)
                return self._reply(400, "truncated upload")
            # Atomic publish so a concurrent scp never sees a half-written exe.
            os.replace(tmp, os.path.join(UPDATE_DIR, EXE_NAME))
        except Exception as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return self._reply(500, f"write failed: {e}")

        sha = h.hexdigest()
        manifest = {"version": version, "file": EXE_NAME, "sha256": sha}
        with open(os.path.join(UPDATE_DIR, "latest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        return self._reply(200, f"ok {version} {sha}")

    def log_message(self, fmt, *args):  # quieter default logging
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("KIVUN_UPLOAD_TOKEN env var is required")
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8099
    print(f"kivun update server on {host}:{port}, UPDATE_DIR={UPDATE_DIR}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
