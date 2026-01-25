import sys
import os

# Ensure src is in path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyvisual as pv
from src.ui.main_window import create_window, create_ui
from src.ui.controller import Controller

def main():
    try:
        app = pv.PvApp()
        window = create_window()
        ui = create_ui(window)
        
        # Initialize Controller
        controller = Controller(app, window, ui)
        
        window.show()
        app.run()
    except (FileNotFoundError, KeyError, ValueError) as e:
        # Minimal dependency way to show error on Windows
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f"Startup Error:\n{str(e)}", "Salesforce Automation Error", 0x10)
        sys.exit(1)
    except Exception as e:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f"Unexpected Error:\n{str(e)}", "Salesforce Automation Error", 0x10)
        sys.exit(1)

if __name__ == '__main__':
    main()
