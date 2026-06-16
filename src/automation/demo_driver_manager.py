"""Dry-run stand-in for :class:`DriverManager` (--dry_run, see constants.DRY_RUN).

It exposes the exact surface the worker and ``BaseProcessor._setup_driver`` drive
(`on_browser_ready`, `check_stop`, `driver`, `launch_chromedriver`,
`create_driver`, `close_driver`) but launches a throwaway window (mspaint) in
place of Chrome and reports its handle through the same ``on_browser_ready``
channel — so the owned-overlay embedding panel (issue #19) is exercised for real.

Because it plugs into the same seams, the whole lifecycle works unchanged:
`create_driver` brings the placeholder up and embeds it; `close_driver` tears it
down — both on a normal finish and on the TYPE 2 handoff "done" button (which the
controller routes to ``close_driver`` on the kept-alive manager).

Windows-only and best-effort, like the rest of the embedding: if the placeholder
can't be launched or found, the demo run still completes, just unembedded.
"""
import subprocess

from src.automation.win_window import (
    find_window_by_title,
    list_top_level_windows,
    reframe_as_owned,
    window_pid,
)
from src.core.constants import APP_WINDOW_TITLE
from src.core.logger import logger
from src.core.utils import smart_sleep

# ponytail: mspaint is the placeholder (a big blank canvas reads clearly as
# "embedded content"). Any classic top-level window would do — swap the command
# here if mspaint is ever unavailable.
_PLACEHOLDER_CMD = ["mspaint.exe"]


class DemoDriverManager:
    def __init__(self):
        self.driver = None  # no Selenium in dry-run — processors must not touch it
        self.on_browser_ready = None
        self.check_stop = None
        self._proc = None
        self._hwnd = None

    def launch_chromedriver(self):
        # No chromedriver in dry-run. Kept so _setup_driver's call is a no-op.
        return None

    def create_driver(self):
        """Launch the placeholder window and hand its handle to the UI to embed."""
        self._spawn_placeholder()
        if self._hwnd and self.on_browser_ready:
            try:
                self.on_browser_ready(self._hwnd)
            except Exception as e:  # pragma: no cover - best-effort embed
                logger.debug(f"demo on_browser_ready failed: {e}", stage="driver")
        return None

    def _spawn_placeholder(self):
        before = list_top_level_windows()
        try:
            self._proc = subprocess.Popen(_PLACEHOLDER_CMD)
        except Exception as e:
            logger.debug(f"demo placeholder launch failed: {e}", stage="driver")
            return
        # Poll for the new window (snapshot diff — robust to single-instance /
        # packaged launchers). Cooperative wait so Stop is honoured mid-poll.
        for _ in range(50):  # up to ~5s
            smart_sleep(0.1, self.check_stop, interval=0.1)
            new = list_top_level_windows() - before
            if new:
                self._hwnd = next(iter(new))
                break
        if not self._hwnd:
            logger.debug("demo placeholder window not found — no embedded panel", stage="driver")
            return
        # Mirror the real driver: reframe as a frameless owned tool-window the
        # instant it's found, so it doesn't flash a taskbar button before the
        # overlay grabs it.
        host = find_window_by_title(APP_WINDOW_TITLE)
        if host:
            reframe_as_owned(self._hwnd, host)
        logger.info("demo placeholder ready for embedding", stage="driver")

    def close_driver(self):
        """Force-close the placeholder by its window's process tree (no save
        prompt). Keyed off the window's live PID, mirroring the real teardown."""
        pid = window_pid(self._hwnd) if self._hwnd else None
        if pid is None and self._proc is not None:
            pid = self._proc.pid
        if pid:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, check=False)
            except Exception:
                pass
        self._proc = None
        self._hwnd = None
        logger.debug("demo placeholder closed", stage="driver")
