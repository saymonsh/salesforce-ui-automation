import os
import sys

# Ensure src is in path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from src.core.logger import logger
from src.ui.controller import Controller
from src.ui.main_window import MainView


def _bind_debug_file() -> None:
    """Mirror the debug channel to logs/debug.log (diag/netfree-machine).

    On the filtered machine the in-app feed can't be read remotely, so this
    on-disk file is what gets pulled out over SSH. Best-effort: a failure here
    must never block startup."""
    try:
        from src.core.paths import logs_dir
        logger.bind_file(os.path.join(logs_dir(), "debug.log"))
    except Exception:
        pass


class _FeedStream:
    """Tees stdout/stderr to the original console AND into the app's activity feed,
    so the panel shows the real terminal output of a run, line by line."""

    def __init__(self, page, view, original, is_err: bool = False):
        self._page = page
        self._view = view
        self._orig = original
        self._is_err = is_err
        self._buf = ""

    def write(self, s):
        try:
            self._orig.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                # Thread-safe enqueue; the UI drains it on its own loop (no flooding).
                self._view.enqueue_terminal_line(line, self._is_err)

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def isatty(self):
        return False


def build_app(page: ft.Page) -> None:
    _bind_debug_file()
    view = MainView(page)
    Controller(page, view)
    # Route the running automation's terminal output into the activity feed.
    sys.stdout = _FeedStream(page, view, sys.stdout, is_err=False)
    sys.stderr = _FeedStream(page, view, sys.stderr, is_err=True)


_INSTANCE_MUTEX = None  # held for the process lifetime so the single-instance lock stays owned


def _acquire_single_instance_lock() -> bool:
    """Named-mutex single-instance guard (Windows). Returns True if THIS process is
    the sole instance (or the check is unavailable — fail open), False if another
    instance already holds the lock. The handle is kept in a module global so the
    lock stays owned until the process exits.

    This replaces the old startup sweep that force-killed every chromedriver and
    automation Chrome on the machine. The real risk it guarded against was a second
    accidental launch colliding with a live run (a duplicate browser/driver and
    embedding); the mutex prevents that outright without touching any unrelated
    process (issue #19 review)."""
    global _INSTANCE_MUTEX
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, "SalesforceUIAutomation.SingleInstance")
        if not handle:
            return True  # couldn't create the lock — don't block the app
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        _INSTANCE_MUTEX = handle  # keep the handle alive for the whole run
        return True
    except Exception:
        return True  # any failure → fail open, never block startup


def main() -> None:
    if not _acquire_single_instance_lock():
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "האפליקציה כבר פועלת.\nסגור את החלון הקיים לפני הפעלה מחדש.",
            "Salesforce Automation",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)
    try:
        # Absolute path so assets resolve regardless of the launch cwd.
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        ft.run(main=build_app, assets_dir=assets_dir)
    except (FileNotFoundError, KeyError, ValueError) as e:
        # Minimal dependency way to show error on Windows
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, f"Startup Error:\n{str(e)}", "Salesforce Automation Error", 0x10
        )
        sys.exit(1)
    except Exception as e:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, f"Unexpected Error:\n{str(e)}", "Salesforce Automation Error", 0x10
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
