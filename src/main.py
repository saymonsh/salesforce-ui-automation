import os
import sys

# Ensure src is in path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from src.ui.controller import Controller
from src.ui.main_window import MainView


def build_app(page: ft.Page) -> None:
    view = MainView(page)
    Controller(page, view)


def main() -> None:
    try:
        ft.app(target=build_app, assets_dir="assets")
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
