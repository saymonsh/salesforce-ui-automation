import sys
import os

# Ensure src is in path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyvisual as pv
from src.ui.main_window import create_window, create_ui
from src.ui.controller import Controller

def main():
    app = pv.PvApp()
    window = create_window()
    ui = create_ui(window)
    
    # Initialize Controller
    controller = Controller(app, window, ui)
    
    window.show()
    app.run()

if __name__ == '__main__':
    main()
