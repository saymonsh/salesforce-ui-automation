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

    python -m tools.netfree_probe                     # diagnose (read-only)
    python -m tools.netfree_probe --remove-env-proxy  # delete the stray env proxy, then verify
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
    if live and not user and not machine:
        logger.info("[proxy] NOTE: live env has the proxy but the registry is clean → STALE SHELL. "
                    "This process inherited the pre-deletion env; open a NEW terminal to clear it.",
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
    _filesystem_hunt()


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


def _filesystem_hunt(needle: str = NEEDLE) -> None:
    """Search the user profile for a file containing the proxy IP.

    Last automated lead: a setup script (.ps1/.bat/.reg/…) run once to set the var
    would still hold the literal IP. ``findstr /s`` is the fast native tool. Our own
    repo legitimately contains the IP now, so its hits are filtered out.
    """
    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        logger.info("[hunt] no USERPROFILE — skipping file search", stage="netfree-probe")
        return
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).lower()
    exts = ("ps1", "bat", "cmd", "reg", "vbs", "txt", "ini", "env", "config", "json", "py")
    specs = [os.path.join(userprofile, f"*.{e}") for e in exts]
    try:
        r = subprocess.run(["findstr", "/s", "/i", "/m", needle, *specs],
                           capture_output=True, text=True, timeout=120)
        files = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        files = [f for f in files if repo not in f.lower()]  # drop our own repo
        body = "\n".join(f"  {f}" for f in files) if files else "  (none outside this repo)"
    except subprocess.TimeoutExpired:
        body = "  (timed out at 120s)"
    except Exception as e:
        body = f"  failed: {type(e).__name__}: {e}"
    logger.info(f"[hunt] files under USERPROFILE containing {needle}:\n{body}", stage="netfree-probe")


def _verify() -> None:
    """Prove the fix: the conventional driver-acquisition paths work now.

    The original failure was env-respecting tools (webdriver-manager) hitting the
    dead env proxy. With it gone, a DEFAULT-proxy request (honouring getproxies,
    like those tools) should no longer NETFAIL, and Selenium Manager — the modern
    method that 'crashed' before — should acquire + launch Chrome end to end.
    """
    import urllib.request

    logger.info(f"[verify] getproxies() now = {urllib.request.getproxies()}", stage="netfree-probe")
    targets = [
        ("binary-cdn", "https://storage.googleapis.com/chrome-for-testing-public/"
                       "150.0.7871.24/win64/chromedriver-win64.zip", {"Range": "bytes=0-0"}),
        ("metadata-json", "https://googlechromelabs.github.io/chrome-for-testing/"
                          "known-good-versions-with-downloads.json", {}),
    ]
    for label, url, headers in targets:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                logger.info(f"[verify] default-path {label}: OK status={r.status}", stage="netfree-probe")
        except Exception as e:
            logger.info(f"[verify] default-path {label}: {type(e).__name__}: {e}", stage="netfree-probe")

    # Production parity for the driver acquisition: strip the proxy env + exempt
    # localhost (what setup_proxy does), so a stale shell or the gov proxy can't
    # route the localhost WebDriver call and trigger the 'str' has no 'get' crash.
    for n in PROXY_NAMES:
        os.environ.pop(n, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        drv = webdriver.Chrome(options=opts)  # no Service → Selenium Manager acquires the driver
        try:
            logger.info(f"[verify] Selenium Manager OK — Chrome {drv.capabilities.get('browserVersion','?')} "
                        "launched via auto-resolved driver", stage="netfree-probe")
        finally:
            drv.quit()
    except Exception as e:
        logger.error(f"[verify] Selenium Manager FAILED: {type(e).__name__}: {e}",
                     stage="netfree-probe", exc=True)


def _remove_env_proxy() -> None:
    """Delete the stray HTTP(S)_PROXY values from HKCU\\Environment.

    Baked into the probe because the filtered machine has no clipboard in — the only
    way to act there is `git pull` + run this. Gated behind --remove-env-proxy so a
    normal diagnostic run never mutates. HKCU is the user's own hive: no admin needed.
    """
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
    except OSError as e:
        logger.info(f"[remove] can't open HKCU\\Environment for write: {e}", stage="netfree-probe")
        return
    deleted = []
    for n in PROXY_NAMES:
        try:
            winreg.DeleteValue(k, n)
            deleted.append(n)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.info(f"[remove] {n}: {e}", stage="netfree-probe")
    winreg.CloseKey(k)
    for n in PROXY_NAMES:
        os.environ.pop(n, None)  # reflect in this process so the verification below is accurate
    logger.info(f"[remove] deleted from HKCU\\Environment: {deleted or 'none (already absent)'}",
                stage="netfree-probe")
    # Tell other apps to re-read the environment (best-effort; existing shells may ignore it).
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x1A, 0, "Environment", 0, 5000, ctypes.byref(ctypes.c_ulong()))
        logger.info("[remove] broadcast WM_SETTINGCHANGE", stage="netfree-probe")
    except Exception as e:
        logger.info(f"[remove] broadcast failed: {e}", stage="netfree-probe")
    logger.info("[remove] done — open a NEW terminal for the change to fully take effect",
                stage="netfree-probe")


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    logger.bind_file(os.path.join(root, "logs", "debug.log"))
    logger.set_verbose(True)

    remove = "--remove-env-proxy" in sys.argv
    verify = "--verify" in sys.argv
    logger.info("=== proxy/env probe start ===", stage="netfree-probe")
    # finally-mirror: even if a step is slow and you Ctrl+C, what was logged so far
    # still gets pushed to the endpoint (the mirror only ever ran at the very end).
    try:
        logger.info(f"python {sys.version.split()[0]}", stage="netfree-probe")
        if remove:
            _remove_env_proxy()
        _proxy_state()          # after removal, shows live env / User scope → none = verified
        if verify:
            _verify()
        if not remove and not verify:
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
