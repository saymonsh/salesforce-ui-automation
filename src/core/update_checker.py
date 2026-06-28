"""In-app update check — two channels, same offer (stdlib only, no new dep).

* **GitHub Releases** (default): the open-network path. The app asks GitHub for
  the latest published release and, if newer than the running
  :data:`~src.core.version.__version__`, offers a one-click download+install.
* **SSH/VPS mirror** (filtered machine): on the gov machine HTTPS *out* is
  blocked but SSH works, so GitHub is unreachable. Instead the app ``scp``-pulls
  a manifest + installer from the VPS mirror (the same box and key the log mirror
  already uses, see ``log_mirror.py``). CI pushes new builds to that mirror over
  HTTPS (it is *not* filtered). See ``docs/packaging.md``.

The checkers return a **status dict** (``state`` in ``available`` / ``current`` /
``error``), never ``None`` — the settings panel needs to tell "you're up to date"
apart from "we couldn't even check" (so it can hint at SSH). Everything here is
best-effort and offline-safe: a blocked/filtered network just yields an ``error``
state and the app starts normally — the check must never delay or break startup,
so the caller runs it on a daemon thread.

Both download paths report real progress via an optional ``on_progress(percent)``
callback (GitHub via ``urlretrieve``'s reporthook; SSH by polling the partly
written file against the manifest's ``size``), and launch the installer
**``/SILENT``** — the deployment progress bar shows, but every wizard page (incl.
the "create desktop shortcut?" question) is skipped. A human double-clicking
Setup.exe still gets the full interactive wizard; only the in-app update is silent.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request

from src.core.utils import CREATE_NO_WINDOW
from src.core.version import __version__

REPO = "saymonsh/salesforce-ui-automation"
_LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT = 5  # seconds; a filtered network must fail fast, not hang the thread

# VPS mirror layout (must match where the upload endpoint writes and where SSH
# can read). The endpoint lives in the shalom.5784.link Node app and writes into
# its host-mounted project dir, so the files land here on the box. See vps/.
REMOTE_UPDATE_DIR = "/root/vultr-configs/shalom.5784.link/kivun-updates"
_MANIFEST_NAME = "latest.json"
_SCP_OPTS = [  # mirror log_mirror.py: never prompt, never hang on a dead box
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
]

# /SILENT shows the deployment progress bar but skips every wizard page (no
# "create desktop shortcut?" question); SUPPRESSMSGBOXES answers any prompt with
# its default; NORESTART so Setup never reboots. installer.iss drops `skipifsilent`
# from its [Run] entry so the app still relaunches after a silent update.
_SILENT_FLAGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]


def _run_installer(path: str) -> None:
    """Launch the just-downloaded installer silently (no wizard questions)."""
    subprocess.Popen([path, *_SILENT_FLAGS], creationflags=CREATE_NO_WINDOW)


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


def check_for_update(current: str = __version__) -> dict:
    """Query GitHub Releases. Returns a status dict (never ``None``):

    * ``{"state": "available", "channel": "github", "version", "url", "page"}``
      — a newer release exists; ``url`` is its installer ``.exe`` asset (``None``
      if the release has no .exe — then only ``page`` is offered).
    * ``{"state": "current", "installed"}`` — running the latest.
    * ``{"state": "error", "reason": "network"}`` — couldn't reach/parse GitHub.
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
        return {"state": "error", "reason": "network"}

    tag = data.get("tag_name") or ""
    if not tag:
        return {"state": "error", "reason": "network"}
    if not is_newer(tag, current):
        return {"state": "current", "installed": current}

    exe = next((a.get("browser_download_url")
                for a in data.get("assets", [])
                if str(a.get("name", "")).lower().endswith(".exe")), None)
    return {"state": "available", "channel": "github",
            "version": tag.lstrip("vV"), "url": exe, "page": data.get("html_url")}


def download_and_launch(url: str, on_progress=None) -> str:
    """Download the installer to %TEMP%, launch it silently, return its path.

    ``on_progress(percent)`` (0-100) is called as the download proceeds. The
    caller exits the app right after so the per-user installer can overwrite the
    (otherwise locked) program files; the close-then-install race is handled
    installer-side via ``AppMutex`` (installer.iss waits for the app to exit).
    """
    dest = os.path.join(tempfile.gettempdir(), os.path.basename(url) or "Kivun-Setup.exe")

    def _hook(count, block_size, total):
        if on_progress and total > 0:
            on_progress(min(100, int(count * block_size * 100 / total)))

    urllib.request.urlretrieve(url, dest, reporthook=_hook if on_progress else None)
    _run_installer(dest)
    return dest


# ---------------------------------------------------------------------------
# SSH / VPS-mirror channel (filtered machine)
# ---------------------------------------------------------------------------

def _ssh_host(ssh_remote: str) -> str:
    """Extract ``user@host`` from an scp destination (``user@host:/path``).

    SSH_REMOTE is the log-mirror destination; we reuse just its host part and
    pull updates from REMOTE_UPDATE_DIR on the same box. No ``:`` -> whole
    string is the host."""
    return ssh_remote.split(":", 1)[0].strip()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scp(remote_src: str, local_dst: str, key: str, timeout: int) -> bool:
    """Best-effort scp of a single (small) remote file to a local path. False on
    any failure (unreachable box, missing file, bad key) — never raises."""
    try:
        r = subprocess.run(
            ["scp", "-i", key, *_SCP_OPTS, remote_src, local_dst],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return r.returncode == 0 and os.path.exists(local_dst)
    except Exception:
        return False


def _scp_with_progress(remote_src: str, local_dst: str, key: str, timeout: int,
                       total: int | None, on_progress) -> bool:
    """scp a (large) file while reporting progress. scp suppresses its own meter
    when its output is piped (not a TTY), so instead we run it in the background
    and poll the partly-written destination size against ``total`` (from the
    manifest). Falls back to no progress when ``total``/``on_progress`` is absent.
    False on any failure — never raises."""
    try:
        if os.path.exists(local_dst):
            os.remove(local_dst)
        p = subprocess.Popen(
            ["scp", "-i", key, *_SCP_OPTS, remote_src, local_dst],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
        start = time.time()
        while p.poll() is None:
            if on_progress and total:
                try:  # cap at 99 — 100 is reserved for "verified, launching"
                    on_progress(min(99, int(os.path.getsize(local_dst) * 100 / total)))
                except OSError:
                    pass  # file not created yet
            if time.time() - start > timeout:
                p.kill()
                return False
            time.sleep(0.2)
        return p.returncode == 0 and os.path.exists(local_dst)
    except Exception:
        return False


def check_for_update_ssh(ssh_remote: str, key: str,
                         current: str = __version__) -> dict:
    """Pull the VPS manifest over scp. Returns a status dict (never ``None``):

    * ``{"state": "available", "channel": "ssh", "version", "remote_exe",
      "sha256", "size"}`` — a newer build exists (``size`` is ``None`` for an old
      manifest predating the field, which just disables the progress percentage).
    * ``{"state": "current", "installed"}`` — running the latest.
    * ``{"state": "error", "reason": "no_channel"|"ssh"}`` — SSH not configured,
      or the box/manifest was unreachable/unparseable.
    """
    if not ssh_remote or not key:
        return {"state": "error", "reason": "no_channel"}
    host = _ssh_host(ssh_remote)
    tmp = os.path.join(tempfile.gettempdir(), _MANIFEST_NAME)
    if not _scp(f"{host}:{REMOTE_UPDATE_DIR}/{_MANIFEST_NAME}", tmp, key, _TIMEOUT + 10):
        return {"state": "error", "reason": "ssh"}
    try:
        with open(tmp, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"state": "error", "reason": "ssh"}
    version, file_name, sha = data.get("version"), data.get("file"), data.get("sha256")
    if not version or not file_name or not sha:
        return {"state": "error", "reason": "ssh"}
    if not is_newer(version, current):
        return {"state": "current", "installed": current}
    return {"state": "available", "channel": "ssh",
            "version": version.lstrip("vV"),
            "remote_exe": f"{host}:{REMOTE_UPDATE_DIR}/{file_name}",
            "sha256": sha, "size": data.get("size")}


def download_and_launch_ssh(remote_exe: str, key: str, sha256: str,
                            size: int | None = None, on_progress=None) -> str:
    """scp the installer from the VPS, verify its sha256, launch it silently.
    Returns the local path. ``on_progress(percent)`` reports download progress
    when ``size`` is known. Raises on download failure or checksum mismatch (the
    caller surfaces it instead of running a corrupt/tampered file)."""
    host, _, path = remote_exe.partition(":")
    dest = os.path.join(tempfile.gettempdir(), os.path.basename(path) or "Kivun-Setup.exe")
    if not _scp_with_progress(remote_exe, dest, key, 300, size, on_progress):  # tens of MB
        raise RuntimeError("scp of installer from VPS failed")
    actual = _sha256(dest)
    if actual.lower() != sha256.lower():
        os.remove(dest)
        raise RuntimeError(f"checksum mismatch (expected {sha256[:12]}…, got {actual[:12]}…)")
    _run_installer(dest)
    return dest


if __name__ == "__main__":
    # Self-check for the version comparison and the offline-testable state
    # branches (the network paths need a live release/box and aren't unit-testable
    # offline).
    assert is_newer("v1.0.1", "1.0.0")
    assert is_newer("v1.1.0", "1.0.9")
    assert is_newer("2.0.0", "1.9.9")
    assert is_newer("v1.2", "1.1.5")            # padded compare
    assert not is_newer("1.0.0", "1.0.0")       # equal
    assert not is_newer("1.0.0", "v1.0.0")      # equal, mixed prefix
    assert not is_newer("0.9.9", "1.0.0")       # older
    assert not is_newer("1.0.0-dev", "1.0.0")   # suffix stripped -> equal
    assert _parse("v1.0.0-dev") == (1, 0, 0)

    # Status-dict shape: the only branch reachable without a network is the
    # SSH "no channel configured" error.
    assert check_for_update_ssh("", "") == {"state": "error", "reason": "no_channel"}
    assert check_for_update_ssh("root@host", "") == {"state": "error", "reason": "no_channel"}

    # SSH host extraction from an scp destination.
    assert _ssh_host("root@149.28.57.61:/srv/logs/") == "root@149.28.57.61"
    assert _ssh_host("root@host") == "root@host"
    assert _ssh_host("") == ""

    # sha256 of a known input (matches `printf 'kivun' | sha256sum`).
    import hashlib as _hl
    _t = os.path.join(tempfile.gettempdir(), "_uc_sha_check.bin")
    with open(_t, "wb") as _f:
        _f.write(b"kivun")
    try:
        assert _sha256(_t) == _hl.sha256(b"kivun").hexdigest()
    finally:
        os.remove(_t)

    print("OK — update_checker self-checks passed")
