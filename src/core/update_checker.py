"""In-app update check against GitHub Releases (stdlib only — no new dep).

On launch the app asks GitHub for the latest published release; if its tag is
newer than the running :data:`~src.core.version.__version__`, the operator is
offered a one-click download-and-install of the per-user installer (ADR-001).

Everything here is best-effort and offline-safe: a blocked/filtered network
(the gov machine) just yields ``None`` and the app starts normally — the check
must never delay or break startup, so the caller runs it on a daemon thread.
"""
import json
import os
import subprocess
import tempfile
import urllib.request

from src.core.version import __version__

REPO = "saymonsh/salesforce-ui-automation"
_LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT = 5  # seconds; a filtered network must fail fast, not hang the thread


def _parse(tag: str) -> tuple:
    """`v1.2.3` / `1.2.3-dev` -> (1, 2, 3). Non-numeric parts -> 0 (lazy but
    total: any tag compares without raising)."""
    nums = []
    for part in tag.lstrip("vV").split("."):
        digits = "".join(c for c in part if c.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums)


def is_newer(latest: str, current: str) -> bool:
    """True iff release tag ``latest`` is a strictly higher version than
    ``current``. Pads the shorter tuple so (1,2) == (1,2,0)."""
    a, b = _parse(latest), _parse(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def check_for_update(current: str = __version__) -> dict | None:
    """Return ``{"version", "url", "page"}`` for a newer release, else ``None``.

    ``url`` is the installer ``.exe`` asset download link (``None`` if the
    release has no .exe asset — then only ``page`` is offered). Any failure
    (no network, rate limit, malformed JSON) returns ``None`` silently.
    """
    try:
        req = urllib.request.Request(
            _LATEST_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"Kivun/{current}"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.load(resp)
    except Exception:
        return None

    tag = data.get("tag_name") or ""
    if not tag or not is_newer(tag, current):
        return None

    exe = next((a.get("browser_download_url")
                for a in data.get("assets", [])
                if str(a.get("name", "")).lower().endswith(".exe")), None)
    return {"version": tag.lstrip("vV"), "url": exe, "page": data.get("html_url")}


def download_and_launch(url: str) -> str:
    """Download the installer to %TEMP% and launch it, returning its path.

    The caller is expected to exit the app right after so the per-user installer
    can overwrite the (otherwise locked) program files.

    ponytail: there's a small race — the installer starts while this process is
    still closing. The operator-driven Inno wizard takes seconds to reach the
    copy step, by which point the app is gone, so it holds in practice. The
    robust upgrade path is an AppMutex + CloseApplications in installer.iss so
    Inno itself waits for / closes the running app.
    """
    dest = os.path.join(tempfile.gettempdir(), os.path.basename(url) or "Kivun-Setup.exe")
    urllib.request.urlretrieve(url, dest)
    os.startfile(dest)  # noqa: S606 — launch the trusted, just-downloaded installer
    return dest


if __name__ == "__main__":
    # Self-check for the version comparison (the only non-trivial logic here;
    # the network path needs a live release and isn't unit-testable offline).
    assert is_newer("v1.0.1", "1.0.0")
    assert is_newer("v1.1.0", "1.0.9")
    assert is_newer("2.0.0", "1.9.9")
    assert is_newer("v1.2", "1.1.5")            # padded compare
    assert not is_newer("1.0.0", "1.0.0")       # equal
    assert not is_newer("1.0.0", "v1.0.0")      # equal, mixed prefix
    assert not is_newer("0.9.9", "1.0.0")       # older
    assert not is_newer("1.0.0-dev", "1.0.0")   # suffix stripped -> equal
    assert _parse("v1.0.0-dev") == (1, 0, 0)
    print("OK — update_checker self-checks passed")
