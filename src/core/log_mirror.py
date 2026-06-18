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

from src.core.logger import logger

# Diag target (temporary). scp overwrites the remote file on every push, so the
# server always shows the latest full session log — no append, no duplicates.
_REMOTE = "root@149.28.57.61:/root/vultr-configs/shalom.5784.link/logs/automation_debug.log"
_KEY = os.path.join(os.path.expanduser("~"), ".ssh", "netlog")
_LOCAL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "debug.log",
)


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
    if not os.path.exists(_LOCAL):
        return
    # ponytail: scp reads the file while the file-logger may still append to it
    # (no shared lock across the external process). Worst case a push trails the
    # newest line by one — acceptable for a diag mirror. Upgrade path: snapshot
    # to a temp copy under the logger lock before scp if it ever matters.
    try:
        r = subprocess.run(
            _build_cmd(_LOCAL, _REMOTE, _KEY),
            capture_output=True, text=True, timeout=30,
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
