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


def _direct_opener(ctx: ssl.SSLContext | None = None) -> urllib.request.OpenerDirector:
    """An opener that bypasses any system proxy (the proven-working direct path)."""
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx or ssl.create_default_context()),
        urllib.request.ProxyHandler({}),
    )


def _envproxy_source_probe() -> None:
    """Pinpoint WHERE the HTTP(S)_PROXY env var is defined: User vs Machine scope.

    `os.environ` shows the value but not its origin. Persistent env vars live in the
    registry — User scope at HKCU\\Environment, Machine scope at HKLM\\…\\Session
    Manager\\Environment. Reporting which scope carries it tells us who set the stray
    proxy and where to remove it (Machine scope ⇒ pushed by org/admin tooling).
    """
    import winreg

    names = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    scopes = [
        ("User (HKCU\\Environment)", winreg.HKEY_CURRENT_USER, r"Environment"),
        ("Machine (HKLM\\…\\Session Manager\\Environment)", winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for label, hive, sub in scopes:
        try:
            k = winreg.OpenKey(hive, sub)
        except OSError as e:
            logger.info(f"[envproxy-source] {label}: can't open ({e})", stage="netfree-probe")
            continue
        found = {}
        for n in names:
            try:
                found[n] = winreg.QueryValueEx(k, n)[0]
            except OSError:
                pass
        winreg.CloseKey(k)
        logger.info(f"[envproxy-source] {label}: {found or 'none'}", stage="netfree-probe")


def _proxies_from_wininet(server: str) -> dict:
    """Turn a WinINET ``ProxyServer`` value into a urllib proxies dict.

    Value is either ``host:port`` (all schemes) or ``http=h:p;https=h:p;…``.
    """
    if "=" in server:
        out = {}
        for part in server.split(";"):
            scheme, _, hp = part.partition("=")
            if hp:
                out[scheme.strip()] = hp if "://" in hp else "http://" + hp.strip()
        return out
    return {"http": "http://" + server, "https": "http://" + server}


def _proxy_config_probe() -> str | None:
    """Read the REAL Windows proxy config and return the registry ``ProxyServer``.

    ``getproxies()`` reads ENV vars first (``getproxies_environment() or
    getproxies_registry()``), so a stray ``HTTP_PROXY`` makes Python use a totally
    different proxy than the browser, which reads the WinINET registry. Logging both
    side by side is how we caught that divergence. Also dumps the proxy env vars to
    pin the source.
    """
    env = {k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
    logger.info(f"[proxy-config] proxy env vars={ {k: v for k, v in env.items() if v} }",
                stage="netfree-probe")
    _envproxy_source_probe()
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
    except OSError as e:
        logger.info(f"[proxy-config] couldn't open registry: {e}", stage="netfree-probe")
        return None

    def _get(name):
        try:
            import winreg
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    enable, server = _get("ProxyEnable"), _get("ProxyServer")
    pac, override = _get("AutoConfigURL"), _get("ProxyOverride")
    logger.info(
        f"[proxy-config] registry ProxyEnable={enable} ProxyServer={server!r} "
        f"AutoConfigURL={pac!r}", stage="netfree-probe")
    logger.info(f"[proxy-config] registry ProxyOverride={override!r}", stage="netfree-probe")

    if pac:
        try:
            with _direct_opener().open(urllib.request.Request(pac), timeout=15) as r:
                body = r.read(8000).decode("utf-8", "replace")
            logger.info(f"[proxy-config] PAC fetched ({len(body)}b shown):\n{body}",
                        stage="netfree-probe")
        except Exception as e:
            logger.info(f"[proxy-config] PAC fetch failed: {type(e).__name__}: {e}",
                        stage="netfree-probe")
    return server if (enable and server) else None


def _ca_contexts() -> list[tuple[str, ssl.SSLContext]]:
    """(label, context) for the system trust store and the certifi bundle.

    The system store trusts the Netfree root (installed machine-wide); certifi does
    not. Any place that store-choice flips the result, a Netfree MITM cert is the
    gate — which is the whole certs question.
    """
    out = [("system store", ssl.create_default_context())]
    try:
        import certifi
        out.append(("certifi bundle", ssl.create_default_context(cafile=certifi.where())))
    except ImportError:
        pass
    return out


def _proxy_tls_probe() -> None:
    """Is the system proxy a TLS (HTTPS) proxy gated by the Netfree cert?

    The through-proxy failures were 'connection closed' BEFORE any cert exchange —
    which is ALSO exactly what Python speaking plaintext to a TLS proxy looks like.
    So we can't yet rule certs in or out for the proxy path. This handshakes TLS
    straight at the proxy under each CA store to settle it:

      TLS-OK (system) + CERT (certifi) → it's a TLS proxy whose cert chains to the
          Netfree root → CERTS ARE the gate for the proxy path.
      NOT-TLS on both → the proxy speaks plaintext; the CONNECT drop is policy /
          client-fingerprint, not certs.
    """
    import socket

    target = urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http")
    if not target:
        logger.info("[SKIP] no system proxy configured — nothing to TLS-probe", stage="netfree-probe")
        return
    netloc = target.split("//", 1)[-1].rstrip("/")
    host, _, port_s = netloc.partition(":")
    port = int(port_s or "443")

    for tag, ctx in _ca_contexts():
        # We're probing the proxy endpoint itself; its cert won't match a hostname,
        # so disable hostname check but KEEP chain verification — that's the certs test.
        ctx.check_hostname = False
        try:
            with socket.create_connection((host, port), timeout=10) as raw:
                with ctx.wrap_socket(raw, server_hostname=host) as tls:
                    cert = tls.getpeercert() or {}
                    subject = dict(x[0] for x in cert.get("subject", []))
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    logger.info(
                        f"[TLS-OK] proxy {host}:{port} ({tag}) — cert chain verified; "
                        f"subject={subject} issuer={issuer}", stage="netfree-probe")
        except ssl.SSLCertVerificationError as e:
            logger.info(f"[CERT] proxy {host}:{port} ({tag}) — chain NOT trusted: {e}",
                        stage="netfree-probe")
        except ssl.SSLError as e:
            logger.info(f"[NOT-TLS] proxy {host}:{port} ({tag}) — {type(e).__name__}: {e} "
                        f"(proxy likely speaks plaintext, not TLS)", stage="netfree-probe")
        except Exception as e:
            logger.info(f"[FAIL] proxy {host}:{port} ({tag}) — {type(e).__name__}: {e}",
                        stage="netfree-probe")


def _proxy_connect_probe() -> None:
    """Send a raw plaintext CONNECT to the proxy and READ the reply.

    urllib reported 'closed without response', but its strict HTTP parser may have
    discarded a non-standard reply. A manual recv catches what the proxy actually
    says — a 407 auth challenge, an HTML 'site not approved' notice, or a redirect
    to Netfree's review page — i.e. what it wants that the browser provides and
    Python doesn't. A browser-like User-Agent is sent in case it fingerprints that.
    """
    import socket

    target = urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http")
    if not target:
        logger.info("[SKIP] no system proxy — nothing to CONNECT-probe", stage="netfree-probe")
        return
    netloc = target.split("//", 1)[-1].rstrip("/")
    host, _, port_s = netloc.partition(":")
    port = int(port_s or "8080")
    dest = "storage.googleapis.com:443"
    req = (
        f"CONNECT {dest} HTTP/1.1\r\nHost: {dest}\r\n"
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0 Safari/537.36\r\n"
        "Proxy-Connection: keep-alive\r\n\r\n"
    )
    try:
        with socket.create_connection((host, port), timeout=10) as s:
            s.sendall(req.encode())
            s.settimeout(10)
            data = b""
            try:
                while len(data) < 4096:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass
            if data:
                snippet = data[:600].decode("latin-1", "replace").replace("\r\n", " | ")
                logger.info(f"[CONNECT-REPLY] proxy {host}:{port} → {snippet}", stage="netfree-probe")
            else:
                logger.info(f"[CONNECT-SILENT] proxy {host}:{port} sent no bytes then closed",
                            stage="netfree-probe")
    except Exception as e:
        logger.info(f"[CONNECT-FAIL] proxy {host}:{port} — {type(e).__name__}: {e}",
                    stage="netfree-probe")


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
    # The real config — Python (env var) and the browser (registry) may use totally
    # different proxies. This is the leading explanation for 'browser works, Python
    # silent'. Returns the registry ProxyServer = the proxy the BROWSER really uses.
    reg_proxy = _proxy_config_probe()

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

    # The decisive test: go through the BROWSER's actual proxy (registry ProxyServer),
    # not the env-var one Python defaulted to. A 407 here = it's integrated Windows
    # auth (the browser does SSO, Python doesn't); an OK/418 = it's the live filter.
    if reg_proxy:
        rp = _proxies_from_wininet(reg_proxy)
        _http_probe(f"binary-cdn (registry proxy {reg_proxy})", URL_BINARY, system_ctx,
                    {"Range": "bytes=0-0"}, rp)
        _http_probe(f"metadata-json (registry proxy {reg_proxy})", URL_META, system_ctx,
                    None, rp)

    # Settle the open question: is the proxy itself a TLS endpoint gated by the
    # Netfree cert (→ certs DO matter for the proxy path), or plaintext (→ not certs)?
    _proxy_tls_probe()
    # And read what the proxy actually replies to a raw CONNECT — reveals whether
    # it wants auth / approval / a browser identity (not a cert).
    _proxy_connect_probe()

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
