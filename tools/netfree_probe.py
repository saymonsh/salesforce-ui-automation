"""Netfree connectivity probe (diag/netfree-machine) — NOT for merge.

Production code *avoids* the normal driver-acquisition paths on the filtered
machine (hardcoded chromedriver + ``--port=9515``), so it can never tell us
whether those paths actually fail there or whether that was cargo-cult. This
script does the opposite: it deliberately exercises the conventional paths,
isolates each hypothesis, and writes a precise verdict into the debug channel —
which the SSH mirror already carries off the machine (see DIAG_NETFREE.md).

Run on the filtered machine from the project root::

    python -m tools.netfree_probe                      # network probes only (safe)
    python -m tools.netfree_probe --with-selenium-manager  # also drive real Chrome

Then read the result on an unfiltered machine at  https://shalom.5784.link/api/netlog

The verdicts map 1:1 to the discrimination matrix in DIAG_NETFREE.md:
    CERT      — Python's CA store doesn't trust the Netfree root (the "certs" theory).
                Fix is trivial: use the OS trust store (truststore / system certs).
    SSL       — some other TLS failure on the handshake.
    BLOCKPAGE — reachable, but an HTML page was injected where a binary/JSON was
                expected → Netfree hard-block of that specific URL.
    NETFAIL   — refused / timeout / DNS → possible L4 block.
    HTTP_nnn  — a non-2xx HTTP status.
    OK        — the path works as-is (the assumption it can't is false).
"""
from __future__ import annotations

import os
import ssl
import sys
import urllib.error
import urllib.request

# Allow `python tools/netfree_probe.py` too, not just `-m` (puts project root on path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.logger import logger  # noqa: E402
from src.core import log_mirror  # noqa: E402

# A real Chrome-for-Testing binary URL (the kind the user confirmed is reachable
# via the browser). The exact version doesn't matter — we test reachability + TLS
# with a 1-byte Range request, not an actual install.
URL_BINARY = (
    "https://storage.googleapis.com/chrome-for-testing-public/"
    "150.0.7871.24/win64/chromedriver-win64.zip"
)
# The version-metadata endpoint webdriver-manager-style tools hit first. If this
# is blocked but the binary CDN isn't, that's a per-URL block, not a cert issue.
URL_META = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "known-good-versions-with-downloads.json"
)


def classify(exc, status, body) -> str:
    """Pure verdict from (exception, http status, body snippet). See module docstring.

    HTTPError is treated as a *response* (it carries a status + body) rather than a
    transport failure — a Netfree block can arrive as a 200 OR a 4xx with HTML.
    """
    text = (
        body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray))
        else (body or "")
    ).lower()
    looks_html = "<html" in text or "<!doctype html" in text or "netfree" in text

    if exc is not None and not isinstance(exc, urllib.error.HTTPError):
        s = str(exc)
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in s:
            return "CERT"
        if isinstance(exc, ssl.SSLError):
            return "SSL"
        return "NETFAIL"

    # We have an HTTP response (possibly surfaced via HTTPError for 4xx/5xx).
    if looks_html:
        return "BLOCKPAGE"
    if status and 200 <= status < 300:
        return "OK"
    return "HTTP_%s" % status


def _http_probe(label: str, url: str, ctx: ssl.SSLContext, headers: dict | None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            body = resp.read(2048)
            verdict = classify(None, resp.status, body)
            detail = (
                f"status={resp.status} bytes={len(body)} "
                f"ct={resp.headers.get('Content-Type')}"
            )
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read(2048)
        except Exception:
            pass
        verdict = classify(e, e.code, body)
        detail = f"HTTPError {e.code} {e.reason}"
    except Exception as e:  # URLError, SSLError, timeout, …
        verdict = classify(e, None, b"")
        detail = f"{type(e).__name__}: {e}"
    logger.info(f"[{verdict}] {label} — {detail}", stage="netfree-probe")
    return verdict


def _selenium_manager_probe() -> None:
    """Let Selenium 4.6+ resolve & download the driver itself (no Service/path).

    This is THE direct test of the modern conventional path. Gated behind a flag
    because, unlike the network probes, it launches real Chrome. Headless so no
    window appears; the full traceback is logged on any failure.
    """
    logger.info("driving Selenium Manager (real Chrome, headless)…", stage="netfree-probe")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        drv = webdriver.Chrome(options=opts)  # no Service → Selenium Manager acquires the driver
        try:
            ver = drv.capabilities.get("browserVersion", "?")
            logger.info(f"[OK] selenium-manager — Chrome {ver} launched via auto-resolved driver",
                        stage="netfree-probe")
        finally:
            drv.quit()
    except Exception as e:
        logger.error(f"[FAIL] selenium-manager — {type(e).__name__}: {e}",
                     stage="netfree-probe", exc=True)


def main(argv: list[str]) -> None:
    # Stand-alone: bind the debug file ourselves (the app's startup binding isn't
    # running here) so every line lands in logs/debug.log → SSH mirror.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.bind_file(os.path.join(log_dir, "debug.log"))
    logger.set_verbose(True)

    logger.info("=== netfree probe start ===", stage="netfree-probe")
    logger.info(f"python {sys.version.split()[0]}  openssl {ssl.OPENSSL_VERSION}",
                stage="netfree-probe")

    # (1) system trust store — what the browser & stdlib urllib use. On Windows
    # create_default_context() loads the system ROOT store, which trusts the
    # Netfree root. Expect OK if the only problem is whose CA bundle is used.
    system_ctx = ssl.create_default_context()
    _http_probe("binary-cdn (system store)", URL_BINARY, system_ctx, {"Range": "bytes=0-0"})
    _http_probe("metadata-json (system store)", URL_META, system_ctx, None)

    # (3) certifi — what requests / webdriver-manager use. If this is CERT while
    # (1) was OK, the "can't use webdriver-manager here" assumption is FALSE: the
    # network is fine, only the CA bundle is wrong, and the fix is one line.
    try:
        import certifi
        certifi_ctx = ssl.create_default_context(cafile=certifi.where())
        _http_probe("binary-cdn (certifi bundle)", URL_BINARY, certifi_ctx, {"Range": "bytes=0-0"})
    except ImportError:
        logger.info("[SKIP] certifi not installed — can't run the CA-bundle contrast",
                    stage="netfree-probe")

    if "--with-selenium-manager" in argv:
        _selenium_manager_probe()
    else:
        logger.info("selenium-manager probe skipped (pass --with-selenium-manager to run it)",
                    stage="netfree-probe")

    logger.info("=== netfree probe done — mirroring log out ===", stage="netfree-probe")
    log_mirror.push_async()
    # Give the off-thread scp a moment to finish before the process exits.
    import threading
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=35)


if __name__ == "__main__":
    main(sys.argv[1:])
