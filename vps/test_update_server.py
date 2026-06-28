#!/usr/bin/env python3
"""Self-check for kivun_update_server: starts it on localhost and exercises the
auth + upload + manifest path. Framework-free; run directly:

    python3 vps/test_update_server.py
"""
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request

os.environ["KIVUN_UPLOAD_TOKEN"] = "test-token-123"
os.environ["UPDATE_DIR"] = tempfile.mkdtemp(prefix="kivun_upd_")

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "kivun_update_server", os.path.join(os.path.dirname(__file__), "kivun_update_server.py"))
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)

from http.server import ThreadingHTTPServer

httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{port}/"


def post(body: bytes, token="test-token-123", version="0.9.6"):
    req = urllib.request.Request(url, data=body, method="POST")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    if version is not None:
        req.add_header("X-Kivun-Version", version)
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


import hashlib

payload = b"fake-installer-bytes" * 100
expected_sha = hashlib.sha256(payload).hexdigest()

# Wrong token -> 401, nothing written.
assert post(payload, token="nope")[0] == 401
# Missing/blank version -> 400.
assert post(payload, version="")[0] == 400
# Bad version with path chars -> 400 (defense at the trust boundary).
assert post(payload, version="../etc")[0] == 400

# Happy path -> 200, files written, sha matches.
code, msg = post(payload)
assert code == 200, (code, msg)
d = os.environ["UPDATE_DIR"]
with open(os.path.join(d, "Setup-latest.exe"), "rb") as f:
    assert f.read() == payload
with open(os.path.join(d, "latest.json"), encoding="utf-8") as f:
    man = json.load(f)
assert man == {"version": "0.9.6", "file": "Setup-latest.exe", "sha256": expected_sha}, man

# A second upload overwrites (no accumulation): only the two files exist.
assert post(payload, version="0.9.7")[0] == 200
assert sorted(os.listdir(d)) == ["Setup-latest.exe", "latest.json"]

httpd.shutdown()
print("OK — kivun_update_server self-checks passed")
