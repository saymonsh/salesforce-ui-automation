# DIAG — Netfree machine log mirror

**Temporary diagnostics branch (`diag/netfree-machine`). Not for merge.**

## Why this branch exists

The app must run on a machine behind **Netfree** (partial-internet filtering). On
that machine the real failure we're chasing is the **chromedriver / port 9515**
startup: a hardcoded `chromedriver.exe` plus `--port=9515` were adopted after
`webdriver-manager` crashed there (either a not-yet-reviewed URL hard-blocked by
Netfree, or a Python-vs-Netfree-root cert error — still open).

The blocker to diagnosing it is **observability**: the debug channel only goes to
the in-app feed and console, and that machine is hard to read remotely (debug
used to come out via cumbersome emails). This branch fixes that — it gets the
full debug log **off the machine** so we can finally see *what* chromedriver dies
on.

## The constraint that shapes the design

On the filtered machine, **HTTPS out is blocked but SSH works**. So:

```
filtered machine                         Vultr server (149.28.57.61)        you
  logs/debug.log  ──scp over SSH──▶  .../logs/automation_debug.log  ──HTTPS──▶  browser
  (full record)    (passwordless)        (overwritten each push)     GET /api/netlog
```

SSH is the transport (the channel that works); the server endpoint is just a
read-only viewer reached over HTTPS from an **unfiltered** machine.

## Components (this repo)

| File | Role |
|---|---|
| `src/core/logger.py` | `bind_file()` mirrors every emitted line to a rotating `logs/debug.log`. Captures `DEBUG` **even when the feed runs quiet** — the file is the complete record regardless of `set_verbose`. |
| `src/main.py` | Binds the file sink at startup (`_bind_debug_file`). |
| `src/core/log_mirror.py` | Best-effort `scp` of `logs/debug.log` to the server. Off-thread, with `BatchMode=yes` / `StrictHostKeyChecking=accept-new` / `ConnectTimeout=10` so an unattended push can **never hang** on a prompt or a dead network. `scp` overwrites, so the server always shows the latest full log. |
| `src/ui/worker.py` | Fires `push_async()` after `finished.emit` — so even a crash traceback is pushed. |
| `tests/test_logger_file_sink.py` | Self-check: file captures `DEBUG` while verbose is off. |
| `tests/test_log_mirror.py` | Self-check: the `scp` command keeps its non-interactive / bounded flags (guards against the silent-hang regression). |
| `tools/netfree_probe.py` | **The experiment.** Deliberately exercises the conventional driver-acquisition paths production avoids — system-store vs `certifi` HTTPS to the Chrome-for-Testing CDN + metadata, and (gated) Selenium Manager driving real Chrome. Emits a one-word verdict per probe into the mirrored log. |
| `tests/test_netfree_probe.py` | Self-check: `classify()` distinguishes CERT / SSL / NETFAIL / BLOCKPAGE / OK / HTTP_nnn. |

## Components (server repo — `vultr-configs`)

- `server.js` → `GET /api/netlog`: returns `automation_debug.log` as `text/plain`,
  behind the existing dashboard Basic auth. No nginx change, no new volume (reuses
  the `/host-configs:ro` mount).
- One `authorized_keys` line for the `netlog` key (currently unrestricted).

## Use

On the filtered machine:

```powershell
git fetch
git checkout diag/netfree-machine
python -m src.main      # run once — a chromedriver failure here is exactly what we want
```

Or run the isolated experiment instead of (or before) a full run — it tests the
conventional paths production avoids and writes a verdict per hypothesis:

```powershell
python -m tools.netfree_probe                       # network probes only (safe)
python -m tools.netfree_probe --with-selenium-manager  # also drive real Chrome
```

Then from an unfiltered machine open **`https://shalom.5784.link/api/netlog`**
(Basic auth = the dashboard credentials; not stored in this repo).

### Reading the probe verdicts

- **`OK` direct but `CERT` on certifi** → a cert-bundle problem. Fix is one line —
  `truststore.inject_into_ssl()` (py3.10+) — and the hardcoded pin can go.
- **`OK` on `system-proxy` but `NETFAIL` on `direct`** → Python wasn't using the
  proxy the browser uses. Not certs, not a hard block — route downloads through
  the system proxy and the conventional paths work.
- **`NETFAIL` on BOTH proxy modes for BOTH CA bundles** → a real connection-level
  block of that host from Python; keep pre-staging the artifact.
- **`OK` on the Selenium Manager probe** → the modern built-in path works there;
  the hardcoded chromedriver + port 9515 were never needed.

### Run 2 result (2026-06-18) — DECISIVE: the system proxy is the whole problem

```
getproxies()={'https':'http://49.13.92.53:1919','http':'http://49.13.92.53:1919'}
[OK]      binary-cdn  (system store, direct)        status=206
[OK]      metadata-json (system store, direct)      status=200
[NETFAIL] binary-cdn  (system store, system-proxy)  connection closed
[NETFAIL] metadata-json (system store, system-proxy) connection closed
[OK]      binary-cdn  (certifi bundle, direct)      status=206
[NETFAIL] binary-cdn  (certifi bundle, system-proxy) connection closed
[OK]      selenium-manager — Chrome 149 launched via auto-resolved driver
```

**Every assumption was wrong.** It was never certs, never blocked URLs, never the
port. The machine has a system proxy configured (`49.13.92.53:1919` — Netfree's
proxy). Routing through it closes the connection; connecting **direct bypasses it
and reaches the open internet** (both CA bundles, binary + JSON, all `OK`).
Selenium Manager — the modern conventional path — launches Chrome 149 fine once
the proxy is stripped. So:

- `webdriver-manager` crashed because `requests` honours `getproxies()` → the
  Netfree proxy → closed connection. Bypass the proxy and it works.
- The hardcoded `C:\chromedriver` path "worked" only by avoiding downloads
  entirely; port 9515 was a confound. The real fix all along was `setup_proxy()`
  stripping the proxy.
- **The normal methods are viable here.** The hardcoded path + port 9515 can go,
  and Selenium Manager can own driver acquisition + version-matching — *provided*
  its download runs direct (proxy stripped).

**Still open:** the Selenium Manager `OK` used a *cached* driver (launched in ~1s).
Re-run with `--cold` to wipe the cache and prove a fresh DOWNLOAD also works on
this machine before retiring the hardcoded path.

### Run 1 result (2026-06-18) — cert theory falsified

All three network probes returned `NETFAIL` (`Remote end closed connection
without response`) on **both** the system store and certifi — identically. A cert
problem would have failed certifi with `CERTIFICATE_VERIFY_FAILED` while the
system store succeeded; instead Netfree closes the connection *before* the cert
exchange. So `truststore` won't help — the block is at the connection layer.
The Selenium Manager probe failed with `'str' object has no attribute 'get'`
because that run didn't strip the proxy (production's `setup_proxy` does), so the
**localhost** WebDriver call was routed through the Netfree proxy and came back as
a block page — which actually validates the `setup_proxy` decision. Both issues
are now fixed in the probe; the open question is the direct-vs-proxy matrix above
(why the browser reaches these URLs and direct Python doesn't).

### Reading the result — what the chromedriver failure tells us

- `SSLError` / `CERTIFICATE_VERIFY_FAILED` → cert theory (Python's CA store vs the Netfree root).
- A Netfree HTML block page, or `ConnectionRefused` / timeout to a specific URL → hard block of a not-yet-reviewed address.
- Failure on `127.0.0.1:9515` itself → back to `setup_proxy` / the proxy path.

## Security

The `netlog` key grants **full root SSH** to the server and its private half lives
on the filtered machine (and is now that machine's global SSH identity). Fine
while this is temporary; treat the key as live and tear it down when done.

## Cleanup (when the chromedriver/port issue is solved)

1. Server: remove the `netlog` line from `/root/.ssh/authorized_keys`.
2. Server: delete the `GET /api/netlog` block in `server.js`, then `docker compose restart app`.
3. Filtered machine: remove the `Host 149.28.57.61` block from `~/.ssh/config` and the `netlog` key.
4. Delete this branch — nothing here is meant to merge.
