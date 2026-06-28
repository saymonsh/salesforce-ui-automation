"""Best-effort SSH mirror of the debug log to the diag server (diag/netfree-machine).

On the filtered (Netfree) machine, HTTPS *out* is blocked but SSH works, so after
each run we ``scp`` the on-disk debug log to a Vultr box where it can be viewed
over HTTPS from an unfiltered machine:

    https://shalom.5784.link/api/netlog   (Basic auth)

Deliberately self-contained and easy to rip out: delete this file plus its single
call site in ``worker.py``. Every failure is swallowed — mirroring must never
affect a run.
"""
import os
import subprocess
import threading

from src.core.config import config_instance as parm
from src.core.logger import logger
from src.core.paths import logs_dir
from src.core.utils import CREATE_NO_WINDOW

# Same on-disk debug log main.py binds (app-data logs dir — project root in a
# source run, %APPDATA%\WelfareSFAutomation when frozen; see ADR-001).
_LOCAL = os.path.join(logs_dir(), "debug.log")


def _build_cmd(local: str, remote: str, key: str) -> list[str]:
    """scp argv tuned to NEVER block: a host-key prompt or a blocked/slow network
    must fail fast, because this runs unattended off-thread (no one to type 'yes').
    Removing any of the three -o flags reintroduces a silent hang on the machine
    we can least afford to debug — the self-check guards them."""
    return [
        "scp",
        "-i", key,
        "-o", "BatchMode=yes",                  # never prompt for a password
        "-o", "StrictHostKeyChecking=accept-new",  # auto-accept first host key, don't prompt
        "-o", "ConnectTimeout=10",              # give up fast if the box is unreachable
        local, remote,
    ]


def _push() -> None:
    if not parm.DEV_MODE or not parm.SSH_MIRROR_ENABLED:
        return
    if not parm.SSH_REMOTE or not parm.SSH_KEY_PATH:
        logger.debug("SSH mirror enabled but remote/key not configured", stage="mirror")
        return
    if not os.path.exists(_LOCAL):
        return
    try:
        r = subprocess.run(
            _build_cmd(_LOCAL, parm.SSH_REMOTE, parm.SSH_KEY_PATH),
            capture_output=True, text=True, timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            logger.debug("debug log mirrored to diag server", stage="mirror")
        else:
            logger.debug(f"log mirror failed (rc={r.returncode}): {r.stderr.strip()}", stage="mirror")
    except Exception as e:
        logger.debug(f"log mirror error: {e}", stage="mirror")


def push_async() -> None:
    """Fire-and-forget mirror on a daemon thread (never blocks the caller)."""
    threading.Thread(target=_push, daemon=True).start()
