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

Then from an unfiltered machine open **`https://shalom.5784.link/api/netlog`**
(Basic auth = the dashboard credentials; not stored in this repo).

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
