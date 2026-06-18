"""Proxy / env-var diagnostic for the managed (gov-proxy) machine — NOT for merge.

This started as a chromedriver-download chase; that's solved (see DIAG_NETFREE.md):
a stray **User-scope** ``HTTP_PROXY=http://49.13.92.53:1919`` (a dead Hetzner box)
sent Python/requests/webdriver-manager to a dead proxy, while the browser used the
WinINET registry gov proxy. Not certs, not the port, not Netfree.

The probes that proved all that have served their purpose and are gone. What's left
open is **what set that env var**, so this tool is now focused there — it dumps the
proxy config, locates the env var's scope + write time, sweeps the whole registry
for the proxy IP, and lists installed programs by date to cross-reference. Output
goes to the SSH-mirrored debug log (read at https://shalom.5784.link/api/netlog).

    python -m tools.netfree_probe
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
import winreg

# Runnable as a script too, not just `-m` (puts project root on the path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import log_mirror  # noqa: E402
from src.core.logger import logger  # noqa: E402

NEEDLE = "49.13.92.53"  # the stray proxy IP we're hunting the source of
PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def _filetime_to_dt(ticks: int) -> datetime.datetime:
    """Windows FILETIME (100-ns ticks since 1601-01-01) → UTC datetime."""
    return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ticks / 10)


def _scope_values(hive, sub) -> dict | None:
    """The PROXY_NAMES present under a registry env key (None if the key is absent)."""
    try:
        k = winreg.OpenKey(hive, sub)
    except OSError:
        return None
    found = {}
    for n in PROXY_NAMES:
        try:
            found[n] = winreg.QueryValueEx(k, n)[0]
        except OSError:
            pass
    winreg.CloseKey(k)
    return found


def _proxy_state() -> None:
    """The proxy facts: live env, which registry scope defines it + when, and the
    WinINET proxy the browser actually uses. Re-run after removing the env var to
    verify (live env → none, scope → none)."""
    live = {n: os.environ.get(n) for n in PROXY_NAMES if os.environ.get(n)}
    logger.info(f"[proxy] live env: {live or 'none'}", stage="netfree-probe")

    user = _scope_values(winreg.HKEY_CURRENT_USER, r"Environment")
    machine = _scope_values(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
    )
    logger.info(f"[proxy] env scope — User={user or 'none'}  Machine={machine or 'none'}",
                stage="netfree-probe")

    # When the user env block last changed → the proxy was set at/before this.
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
        logger.info(f"[proxy] HKCU\\Environment last modified: {_filetime_to_dt(winreg.QueryInfoKey(k)[2])} UTC",
                    stage="netfree-probe")
        winreg.CloseKey(k)
    except OSError as e:
        logger.info(f"[proxy] mtime read failed: {e}", stage="netfree-probe")

    # WinINET proxy = what the browser uses (different from the env-var one).
    try:
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )

        def _g(n):
            try:
                return winreg.QueryValueEx(k, n)[0]
            except OSError:
                return None

        logger.info(f"[proxy] WinINET ProxyEnable={_g('ProxyEnable')} "
                    f"ProxyServer={_g('ProxyServer')!r} AutoConfigURL={_g('AutoConfigURL')!r}",
                    stage="netfree-probe")
        winreg.CloseKey(k)
    except OSError as e:
        logger.info(f"[proxy] WinINET read failed: {e}", stage="netfree-probe")


def _hunt(needle: str = NEEDLE) -> None:
    """Search the registry for the proxy IP — catches any tool that stores or
    re-applies it. The env var lives in HKCU, so the whole HKCU hive is worth a
    sweep; a whole-HKLM sweep is minutes-slow and low-value, so HKLM is narrowed to
    the autostart/service/policy subtrees where a re-applier would live. Each call
    is time-bounded so the probe can never wedge on a slow hive."""
    roots = [
        "HKCU",  # whole current-user hive — where the env var (and likely its setter) sits
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        r"HKLM\SYSTEM\CurrentControlSet\Services",
        r"HKLM\SOFTWARE\Policies",
    ]
    for root in roots:
        try:
            r = subprocess.run(["reg", "query", root, "/f", needle, "/s"],
                               capture_output=True, text=True, timeout=45)
            out = (r.stdout or "").strip()
            logger.info(f"[hunt] {root} → {out or '(no matches)'}", stage="netfree-probe")
        except subprocess.TimeoutExpired:
            logger.info(f"[hunt] {root} → (timed out at 45s — skipped)", stage="netfree-probe")
        except Exception as e:
            logger.info(f"[hunt] {root} → failed: {type(e).__name__}: {e}", stage="netfree-probe")
    _programs_by_date()
    _history_hunt()


def _programs_by_date() -> None:
    """Installed programs sorted by InstallDate — cross-reference against the
    HKCU\\Environment mtime above to spot what landed in that window."""
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    rows = []
    for hive, sub in roots:
        try:
            base = winreg.OpenKey(hive, sub)
        except OSError:
            continue
        i = 0
        while True:
            try:
                child = winreg.EnumKey(base, i)
                i += 1
            except OSError:
                break
            try:
                ck = winreg.OpenKey(base, child)
                try:
                    name = winreg.QueryValueEx(ck, "DisplayName")[0]
                except OSError:
                    name = None
                if name:
                    try:
                        date = str(winreg.QueryValueEx(ck, "InstallDate")[0])
                    except OSError:
                        date = "00000000"
                    rows.append((date, name))
                winreg.CloseKey(ck)
            except OSError:
                pass
        winreg.CloseKey(base)
    rows.sort()
    listing = "\n".join(f"  {d}  {n}" for d, n in rows) or "  (none found)"
    logger.info(f"[hunt] installed programs by InstallDate:\n{listing}", stage="netfree-probe")


def _history_hunt(needle: str = NEEDLE) -> None:
    """Search the PowerShell command history for a proxy-set command.

    The registry can't date a single value, but if the env var was set by a typed
    command (`setx HTTP_PROXY …` / `[Environment]::SetEnvironmentVariable(…)`),
    PSReadLine logged it here verbatim. The best shot at naming the actual setter.
    """
    path = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "PowerShell", "PSReadLine", "ConsoleHost_history.txt")
    if not os.path.exists(path):
        logger.info(f"[hunt] no PSReadLine history at {path}", stage="netfree-probe")
        return
    markers = (needle, "http_proxy", "https_proxy", "setenvironmentvariable", "setx")
    hits = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                low = line.lower()
                if any(m in low for m in markers):
                    hits.append(line.strip())
    except OSError as e:
        logger.info(f"[hunt] history read failed: {e}", stage="netfree-probe")
        return
    body = "\n".join(f"  {h}" for h in hits) if hits else "  (no proxy/env-setting commands found)"
    logger.info(f"[hunt] PowerShell history (proxy/env commands):\n{body}", stage="netfree-probe")


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    logger.bind_file(os.path.join(root, "logs", "debug.log"))
    logger.set_verbose(True)

    logger.info("=== proxy/env probe start ===", stage="netfree-probe")
    # finally-mirror: even if a step is slow and you Ctrl+C, what was logged so far
    # still gets pushed to the endpoint (the mirror only ever ran at the very end).
    try:
        logger.info(f"python {sys.version.split()[0]}", stage="netfree-probe")
        _proxy_state()
        _hunt()
    finally:
        logger.info("=== probe done — mirroring log out ===", stage="netfree-probe")
        log_mirror.push_async()
        import threading
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon:
                t.join(timeout=35)


if __name__ == "__main__":
    main()
