"""Netfree connectivity probe (diag/netfree-machine) — NOT for merge.

Production code *avoids* the normal driver-acquisition paths on the filtered
machine (hardcoded chromedriver + ``--port=9515``), so it can never tell us
whether those paths actually fail there or whether that was cargo-cult. This
script does the opposite: it deliberately exercises the conventional paths,
isolates each hypothesis, and writes a precise verdict into the debug channel —
which the SSH mirror already carries off the machine (see DIAG_NETFREE.md).

Run on the filtered machine from the project root::

    python -m tools.netfree_probe                          # network probes only (safe)
    python -m tools.netfree_probe --with-selenium-manager  # also drive real Chrome
    python -m tools.netfree_probe --with-selenium-manager --cold  # force a fresh driver DOWNLOAD

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


def _http_probe(label: str, url: str, ctx: ssl.SSLContext, headers: dict | None,
                proxies: dict | None) -> str:
    """One HTTPS attempt. ``proxies={}`` forces a DIRECT connection (bypass any
    system proxy); ``proxies=None`` lets urllib use the system/env proxy — the
    browser presumably reaches these URLs *through* the Netfree proxy, so this
    dimension is how we test whether the proxy is the difference."""
    handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
    if proxies is not None:
        handlers.append(urllib.request.ProxyHandler(proxies))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with opener.open(req, timeout=15) as resp:
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


def _selenium_manager_probe(cold: bool = False) -> None:
    """Let Selenium 4.6+ resolve & download the driver itself (no Service/path).

    This is THE direct test of the modern conventional path. Gated behind a flag
    because, unlike the network probes, it launches real Chrome. Headless so no
    window appears; the full traceback is logged on any failure.

    ``cold=True`` wipes the Selenium Manager cache first, forcing an actual DOWNLOAD
    over the network — otherwise a cached driver makes this prove only "can launch",
    not "can download here" (the part that touches the filter).
    """
    if cold:
        import shutil
        cache = os.path.join(os.path.expanduser("~"), ".cache", "selenium")
        try:
            shutil.rmtree(cache)
            logger.info(f"cold start: wiped {cache}", stage="netfree-probe")
        except FileNotFoundError:
            logger.info(f"cold start: no cache at {cache} (already cold)", stage="netfree-probe")
        except OSError as e:
            logger.info(f"cold start: couldn't wipe cache: {e}", stage="netfree-probe")
    logger.info("driving Selenium Manager (real Chrome, headless)…", stage="netfree-probe")
    # Mirror production's setup_proxy(): strip proxy env + exempt localhost. Without
    # this the WebDriver call to the local chromedriver gets routed through the
    # Netfree proxy and comes back as a block page (str), not JSON — which is the
    # 'str' object has no attribute 'get' we saw. This makes the test fair.
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(var, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
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
    # Is a system/env proxy configured at all? The browser likely reaches these
    # URLs *through* the Netfree proxy; if Python sees no proxy it connects direct
    # and Netfree drops it. This line tells us which world we're in.
    logger.info(f"getproxies()={urllib.request.getproxies()}", stage="netfree-probe")

    system_ctx = ssl.create_default_context()
    # Proxy matrix: DIRECT (proxies={}) vs SYSTEM proxy (proxies=None). If SYSTEM
    # succeeds where DIRECT fails, the block is "Python wasn't using the proxy the
    # browser uses" — not certs, not a hard block.
    for ptag, proxies in (("direct", {}), ("system-proxy", None)):
        _http_probe(f"binary-cdn (system store, {ptag})", URL_BINARY, system_ctx,
                    {"Range": "bytes=0-0"}, proxies)
        _http_probe(f"metadata-json (system store, {ptag})", URL_META, system_ctx,
                    None, proxies)

    # CA-bundle contrast — certifi is what requests / webdriver-manager use. Run it
    # over BOTH proxy modes so a cert failure can't be masked by a proxy failure.
    try:
        import certifi
        certifi_ctx = ssl.create_default_context(cafile=certifi.where())
        for ptag, proxies in (("direct", {}), ("system-proxy", None)):
            _http_probe(f"binary-cdn (certifi bundle, {ptag})", URL_BINARY, certifi_ctx,
                        {"Range": "bytes=0-0"}, proxies)
    except ImportError:
        logger.info("[SKIP] certifi not installed — can't run the CA-bundle contrast",
                    stage="netfree-probe")

    if "--with-selenium-manager" in argv:
        _selenium_manager_probe(cold="--cold" in argv)
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
