import os

# Base Paths
# src/core/constants.py -> ../../ -> project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')

# Fonts
FONT_OPENSANS = os.path.join(ASSETS_DIR, 'fonts', 'OpenSans', 'OpenSans.ttf')
FONT_POPPINS = os.path.join(ASSETS_DIR, 'fonts', 'Poppins', 'Poppins.ttf')

# Icons
ICON_SETTING = os.path.join(ASSETS_DIR, 'icons', 'icon_1.svg')
ICON_UPLOAD = os.path.join(ASSETS_DIR, 'icons', 'icon_2.svg')
ICON_RUN = os.path.join(ASSETS_DIR, 'icons', 'icon_4.svg')
ICON_STOP = os.path.join(ASSETS_DIR, 'icons', 'stop_icon.svg')

# Colors
COLOR_WHITE             = (255, 255, 255, 1)
COLOR_WHITE_TRANSPARENT = (255, 255, 255, 0)
COLOR_BLUE_PRIMARY      = (107, 159, 226, 1)
COLOR_BLUE_BG           = (80, 160, 225, 1)
COLOR_BORDER_GRAY       = (100, 100, 100, 1)
COLOR_PURPLE_TRANSPARENT= (124, 53, 163, 0)
COLOR_BLACK_BORDER      = (0, 0, 0, 1)
COLOR_RED_STOP          = (231, 76, 60, 1)
