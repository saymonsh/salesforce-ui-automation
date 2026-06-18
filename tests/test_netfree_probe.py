"""Self-check for the netfree probe's verdict logic (diag/netfree-machine) — no framework.

    python tests/test_netfree_probe.py

The probe's whole value is telling CERT (fixable in one line) apart from BLOCKPAGE
(a real per-URL block) apart from OK (the assumption was wrong). If classify()
mislabels, the off-machine log misleads the diagnosis. This pins each branch.
"""
import os
import ssl
import sys
import urllib.error

# Runnable as `python tests/test_netfree_probe.py` too: put the project root (not
# tests/) on the path so `tools` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.netfree_probe import classify  # noqa: E402


def check() -> None:
    # Transport-level failures.
    assert classify(ssl.SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer"),
                    None, b"") == "CERT", "cert-verify failure must be CERT"
    assert classify(ssl.SSLError("handshake failure"), None, b"") == "SSL", "other TLS error is SSL"
    assert classify(urllib.error.URLError("timed out"), None, b"") == "NETFAIL", "timeout/refused is NETFAIL"

    # Reachable responses.
    assert classify(None, 206, b"PK\x03\x04") == "OK", "partial binary content is OK"
    assert classify(None, 200, b'{"versions": []}') == "OK", "JSON 200 is OK"
    assert classify(None, 200, b"<!DOCTYPE html><html>netfree block</html>") == "BLOCKPAGE", \
        "injected HTML where binary/JSON expected is a BLOCKPAGE"

    # HTTPError carries a status+body → classified as a response, not a transport fault.
    he = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    assert classify(he, 403, b"<html>blocked by netfree</html>") == "BLOCKPAGE", "403+HTML is BLOCKPAGE"
    assert classify(he, 404, b"") == "HTTP_404", "non-2xx without HTML is HTTP_nnn"


def main() -> None:
    check()
    print("OK: netfree probe classify() distinguishes CERT / SSL / NETFAIL / BLOCKPAGE / OK / HTTP_nnn")


if __name__ == "__main__":
    main()
