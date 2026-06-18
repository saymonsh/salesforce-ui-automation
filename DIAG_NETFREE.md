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
| `tools/netfree_probe.py` | Proxy/env diagnostic (refocused once the network/cert question was solved). Dumps the proxy config, locates the stray `HTTP_PROXY` env var's scope + write time, sweeps the whole registry for the proxy IP, and lists installed programs by date — to find what set it. (The earlier network/cert/Selenium probes did their job and were removed; their findings live in the result sections below.) |
| `tests/test_netfree_probe.py` | Self-check: the FILETIME→datetime conversion (used to date the env var) has the right epoch and scale. |

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

Or run the focused proxy/env diagnostic (no full run needed):

```powershell
python -m tools.netfree_probe
```

It prints the proxy config, the stray env var's scope + `HKCU\Environment` write
time, a full-registry sweep for the proxy IP, and installed programs by date — to
find what set the env var. Then from an unfiltered machine open
**`https://shalom.5784.link/api/netlog`** (Basic auth = the dashboard credentials).

The result sections below are the **history** of how the root cause was found (with
the earlier multi-verdict probe, since removed). Read top-down; the latest is first.

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

**Confirmed (Run 3, `--cold`):** wiping the cache forced a real download (~7s vs
~1s) and Selenium Manager still launched Chrome 149 — so a fresh DOWNLOAD works
direct too. Note: Selenium Manager's Rust binary ignores the system proxy and
goes direct.

**Caveat — direct = bypassing the org filter.** The proxy is a *deliberate* org
policy on a fully-managed machine, not an oversight. "Direct works" relies on a
policy gap the org can close at any time; an approach whose startup depends on it
is fragile. The pre-staged driver needs zero egress to launch — keep it as the
robust core; treat any direct download (e.g. an updater) as non-fatal convenience.

## ROOT CAUSE (Run 5) — a stray env-var proxy, and it isn't Netfree

`49.13.92.53:1919` is NOT the browser's proxy. It comes from **environment
variables** (`HTTP_PROXY`/`HTTPS_PROXY` all set to it), and `urllib.getproxies()`
reads env *before* the registry — so Python defaulted to it while the browser uses
the **registry** `ProxyServer` `10.39.37.100:8080`. They were never on the same
proxy. Probing the browser's real proxy:

```
[proxy-config] env vars HTTP_PROXY=…=http://49.13.92.53:1919   (dead/silent)
[proxy-config] registry ProxyServer='10.39.37.100:8080' AutoConfigURL=None
[OK]   binary-cdn   (registry proxy 10.39.37.100:8080)  status=206
[CERT] metadata-json(registry proxy 10.39.37.100:8080)  Missing Authority Key Identifier
```

- **What actually broke `webdriver-manager`: the stray env-var proxy** `49.13.92.53:1919`
  (a dead Hetzner box). Nothing to do with certs, the port, or filtering — Python
  honoured an env proxy the browser never saw.
- **It's not Netfree.** The `ProxyOverride` bypass list (`ladpc.net.il`, `bbm.org.il`,
  municipal/gov hosts) shows a **government/municipal proxy** (`10.39.37.100:8080`).
  That's why there was never a Netfree 418.
- **Certs DO appear — on the corporate proxy's MITM path.** Through `10.39.37.100:8080`,
  tunnelled hosts (storage.googleapis.com) work (206), but MITM-inspected hosts
  (googlechromelabs.github.io) fail `CERTIFICATE_VERIFY_FAILED: Missing Authority
  Key Identifier` — the corporate inspection CA is malformed and OpenSSL 3.x rejects
  it. Real, but a different layer than the original failure.
- **Direct works for everything** (both CA bundles, both hosts), and Selenium
  Manager downloads direct (incl. cold). That's the clean path.

## Conclusion

- **Root cause = the env-var proxy, not certs/port/Netfree.** First fix is to drop
  `HTTP_PROXY`/`HTTPS_PROXY` (production's `setup_proxy()` already pops them) — then
  go **direct** for driver acquisition (proven for all hosts; what Selenium Manager
  does anyway). Don't rely on the gov proxy: it MITM-fails some hosts under OpenSSL 3.x.
- **Investigate the stray env var.** An `HTTP_PROXY` to an external Hetzner IP on a
  managed gov machine is unusual; find who set it (System vs User env).
- **Production stance unchanged & vindicated.** Keep the pre-staged `C:\chromedriver`
  as the launch core (zero egress; don't refactor the lifecycle). `setup_proxy()` was
  right — just for the real reason (a bad env proxy), not the folklore (port 9515 /
  certs). Optional: a direct-download updater to kill version-drift toil. Fix the
  cargo-cult comments so the 9515/cert/Netfree folklore doesn't outlive this branch.

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
