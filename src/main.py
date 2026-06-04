import os
import sys

# Ensure src is in path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from src.ui.controller import Controller
from src.ui.main_window import MainView


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
    view = MainView(page)
    Controller(page, view)
    # Route the running automation's terminal output into the activity feed.
    sys.stdout = _FeedStream(page, view, sys.stdout, is_err=False)
    sys.stderr = _FeedStream(page, view, sys.stderr, is_err=True)


def main() -> None:
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
